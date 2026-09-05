"""Identify Matroska files and extract selected tracks."""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from time import monotonic
from typing import Any, Final

from anishift.application.cancellation import CancellationToken
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.mkv import extract_mkv_track
from anishift.services.extraction.mp4 import extract_mp4_track
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionResult,
    LegacyExtractionResult,
    MediaInfo,
    TrackInfo,
    TrackSelection,
    format_extension,
    is_text_subtitle_codec,
)
from anishift.services.media._process import ProcessRunner, SubprocessRunner
from anishift.setup.installer import ensure_binary
from anishift.utils.logger import get_logger
from anishift.utils.timer import Timer

__all__ = [
    "ExtractionService",
    "extract_tracks",
    "format_extension",
    "identify",
    "is_text_subtitle_codec",
    "parse_media_info",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_RE_GUI_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^#GUI#progress\s+(\d+)%")
"""One ``--gui-mode`` progress line of mkvextract."""

_IDENTIFY_TIMEOUT_S: Final[float] = 120.0
"""Upper bound for ``mkvmerge -J`` on one file."""

_ERROR_TAIL_LINES: Final[int] = 8
"""How many trailing non-progress output lines land in an error message."""

_CANCEL_POLL_SECONDS: Final[float] = 0.1
"""Interval used to notice cancellation while stdout is blocked."""

_SHUTDOWN_GRACE_SECONDS: Final[float] = 5.0
"""Bound on each terminate, kill, and output-reader shutdown wait."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag isolating the child from the console Ctrl+C; zero elsewhere."""

logger = get_logger(__name__)


def _fail(
    code: ErrorCode,
    message: str,
    suggestion: str = "",
    *,
    details: dict[str, Any] | None = None,
) -> ExtractionError:
    """Build an extraction error with structured context."""
    return ExtractionError(
        context=ErrorContext(
            code=code,
            message=message,
            suggestion=suggestion,
            details={} if details is None else details,
        ),
    )


def parse_media_info(path: Path, payload: str) -> MediaInfo:
    """Parse ``mkvmerge -J`` JSON output into a typed :class:`MediaInfo`."""
    try:
        raw: dict[str, Any] = json.loads(payload)
        container: dict[str, Any] = raw["container"]
        if container["recognized"] is False or container["supported"] is False:
            msg = f"{path}: not a supported Matroska file"
            raise _fail(ErrorCode.EXTRACTION_FAILED, msg)
        tracks = tuple(_parse_track(track) for track in raw["tracks"])
        attachments = tuple(_parse_attachment(attachment) for attachment in raw.get("attachments", []))
        duration_us: int = _parse_duration_us(container)
    except KeyError as exc:
        msg = f"{path}: identify JSON is missing field {exc}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    except ValueError as exc:
        msg = f"{path}: identify JSON is invalid"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    except TypeError as exc:
        msg = f"{path}: identify JSON has invalid data"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    return MediaInfo(
        path=path,
        tracks=tuple(sorted(tracks, key=lambda track: track.id)),
        attachments=tuple(name for name in attachments if name),
        duration_us=duration_us,
    )


def _parse_attachment(raw: dict[str, Any]) -> str:
    """Return one attachment's file name, empty when the payload omits it."""
    return str(raw.get("file_name", ""))


def _parse_track(raw: dict[str, Any]) -> TrackInfo:
    """Parse one mkvmerge track object into a :class:`TrackInfo`."""
    properties: dict[str, Any] = raw.get("properties", {})
    return TrackInfo(
        id=raw["id"],
        type=raw["type"],
        codec_id=properties.get("codec_id", ""),
        language=properties.get("language", ""),
        language_ietf=properties.get("language_ietf", ""),
        name=properties.get("track_name", ""),
        default=properties.get("default_track", False),
        num_entries=properties.get("num_index_entries"),
        forced=properties.get("forced_track", False),
    )


def _parse_duration_us(container: dict[str, Any]) -> int:
    """Return Matroska nanosecond duration as microseconds, zero when absent."""
    properties: object = container.get("properties", {})
    if not isinstance(properties, dict):
        raise TypeError("container.properties")
    duration: object = properties.get("duration")
    if duration is None:
        return 0
    if isinstance(duration, bool) or not isinstance(duration, int | str):
        raise TypeError("container.properties.duration")
    duration_ns: int = int(duration)
    if duration_ns < 0:
        raise ValueError("container.properties.duration")
    return duration_ns // 1000


def identify(path: Path) -> MediaInfo:
    """Identify an MKV container with ``mkvmerge -J``."""
    timer: Timer = Timer("media_identification", auto_start=True)
    logger.debug("Media identification started", source=path.name)
    exe = ensure_binary(Binary.MKVMERGE)
    try:
        completed = subprocess.run(  # noqa: S603
            [str(exe), "--ui-language", "en", "-J", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_IDENTIFY_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"{path}: mkvmerge identify timed out"
        raise _fail(ErrorCode.TIMEOUT, msg) from exc
    except OSError as exc:
        msg = f"{path}: could not run mkvmerge: {exc}"
        raise _fail(ErrorCode.IO_ERROR, msg) from exc
    if completed.returncode != 0:
        msg = f"{path}: mkvmerge identify failed: {completed.stderr.strip()}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg, details={"file": str(path)})
    info: MediaInfo = parse_media_info(path, completed.stdout)
    timer.stop()
    logger.info(
        "Media identification completed",
        source=path.name,
        track_count=len(info.tracks),
        duration_ms=round(timer.duration_ms),
    )
    return info


def _track_for(info: MediaInfo, track_id: int) -> TrackInfo:
    """Return a selected track or raise a track-not-found error."""
    track = next((candidate for candidate in info.tracks if candidate.id == track_id), None)
    if track is not None:
        return track
    msg = f"{info.path}: track {track_id} not found"
    raise _fail(ErrorCode.TRACK_NOT_FOUND, msg)


def _build_specs(
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
) -> list[tuple[int, Path]]:
    """Build output specifications for the selected tracks."""
    stem = info.path.stem
    specs: list[tuple[int, Path]] = []
    for track_id in (selection.audio_id, selection.subtitle_id):
        if track_id is None:
            continue
        track = _track_for(info, track_id)
        specs.append((track.id, dest_dir / f"{stem}.{format_extension(track.codec_id)}"))
    return specs


def _remove_outputs(specs: list[tuple[int, Path]]) -> None:
    """Remove partial extraction outputs."""
    for _, destination in specs:
        destination.unlink(missing_ok=True)


def _validate_outputs(specs: list[tuple[int, Path]], source: Path, returncode: int) -> None:
    """Require every selected track to have a non-empty file."""
    for _, destination in specs:
        if not destination.is_file() or destination.stat().st_size == 0:
            msg = f"{source}: mkvextract exited {returncode} but wrote no data"
            raise _fail(ErrorCode.EXTRACTION_FAILED, msg, details={"output": str(destination)})


def _stop_extraction(process: subprocess.Popen[str]) -> None:
    """Reap the child, escalating to kill after a bounded grace period."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired as error:
            raise _fail(ErrorCode.TIMEOUT, "mkvextract did not exit after kill") from error


def _read_output(
    process: subprocess.Popen[str],
    output: queue.SimpleQueue[str | OSError | None],
) -> None:
    """Drain and close the owned pipe, including EOF after the caller's grace period."""
    if process.stdout is None:
        output.put(None)
        return
    try:
        with closing(process.stdout) as stream:
            for line in stream:
                output.put(line)
    except OSError as error:
        output.put(error)
    finally:
        output.put(None)


def _wait_for_extraction(
    process: subprocess.Popen[str],
    output: queue.SimpleQueue[str | OSError | None],
    *,
    cancel: threading.Event | None,
    deadline: float,
    on_progress: Callable[[int], None] | None,
) -> tuple[int, deque[str]]:
    """Watch both stdout and process exit under the same deadline."""
    output_finished: bool = False
    tail: deque[str] = deque(maxlen=_ERROR_TAIL_LINES)
    while True:
        if cancel is not None and cancel.is_set():
            raise _fail(ErrorCode.CANCELLED, "mkvextract extraction cancelled")
        remaining: float = deadline - monotonic()
        if remaining <= 0:
            raise _fail(ErrorCode.TIMEOUT, "mkvextract extraction timed out")
        interval: float = min(_CANCEL_POLL_SECONDS, remaining)
        if output_finished:
            try:
                return process.wait(timeout=interval), tail
            except subprocess.TimeoutExpired:
                continue
        try:
            line: str | OSError | None = output.get(timeout=interval)
        except queue.Empty:
            continue
        if isinstance(line, OSError):
            raise line
        if line is None:
            output_finished = True
            continue
        match: re.Match[str] | None = _RE_GUI_PROGRESS.match(line)
        if match is not None:
            if on_progress is not None:
                on_progress(min(100, int(match.group(1))))
            continue
        tail.append(line.strip())


def extract_tracks(  # noqa: PLR0912,PLR0913,PLR0915 - extraction lifecycle stays explicit
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
    *,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
    timeout_s: float = 3600.0,
) -> LegacyExtractionResult:
    """Extract the selected tracks into *dest_dir* with live progress."""
    if timeout_s <= 0:
        msg = "Extraction timeout must be positive"
        raise ValueError(msg)
    specs: list[tuple[int, Path]] = _build_specs(info, selection, dest_dir)
    if not specs:
        logger.debug("Track extraction skipped", source=info.path.name, reason="no_selected_tracks")
        return LegacyExtractionResult(None, None)
    if any(destination.exists() for _, destination in specs):
        raise _fail(ErrorCode.IO_ERROR, "Extraction target already exists")
    if cancel is not None and cancel.is_set():
        raise _fail(ErrorCode.CANCELLED, "mkvextract extraction cancelled")
    timer: Timer = Timer("track_extraction", auto_start=True)
    logger.debug(
        "Track extraction started",
        source=info.path.name,
        track_ids=tuple(track_id for track_id, _ in specs),
    )
    audio_path = next((destination for track_id, destination in specs if track_id == selection.audio_id), None)
    subtitle_path = next((destination for track_id, destination in specs if track_id == selection.subtitle_id), None)

    exe = ensure_binary(Binary.MKVEXTRACT)
    command = [str(exe), "--ui-language", "en", "--gui-mode", str(info.path), "tracks"]
    command.extend(f"{track_id}:{destination}" for track_id, destination in specs)
    process: subprocess.Popen[str] | None = None
    reader: threading.Thread | None = None
    succeeded: bool = False
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_NEW_PROCESS_GROUP,
        )
        output: queue.SimpleQueue[str | OSError | None] = queue.SimpleQueue()
        reader = threading.Thread(target=_read_output, args=(process, output), daemon=True)
        reader.start()
        returncode: int
        tail: deque[str]
        returncode, tail = _wait_for_extraction(
            process,
            output,
            cancel=cancel,
            deadline=monotonic() + timeout_s,
            on_progress=on_progress,
        )
        if returncode not in {0, 1}:
            detail = " | ".join(line for line in tail if line)
            msg = f"{info.path}: mkvextract failed: {detail}"
            raise _fail(
                ErrorCode.EXTRACTION_FAILED,
                msg,
                "Check the MKV is readable and the disk has free space",
                details={"command": command, "tail": list(tail)},
            )
        _validate_outputs(specs, info.path, returncode)
        if returncode == 1:
            logger.warning("Track extraction completed with warnings", source=info.path.name, output_count=len(specs))
        if on_progress is not None:
            on_progress(100)
        if cancel is not None and cancel.is_set():
            raise _fail(ErrorCode.CANCELLED, "mkvextract extraction cancelled")
        succeeded = True
    except OSError as exc:
        msg = f"{info.path}: extraction I/O failed: {exc}"
        raise _fail(ErrorCode.IO_ERROR, msg) from exc
    finally:
        try:
            if process is not None:
                _stop_extraction(process)
        finally:
            if reader is not None:
                reader.join(timeout=_SHUTDOWN_GRACE_SECONDS)
            if process is not None and process.stdout is not None and (reader is None or not reader.is_alive()):
                process.stdout.close()
            if not succeeded:
                _remove_outputs(specs)
    timer.stop()
    logger.info(
        "Track extraction completed",
        source=info.path.name,
        output_count=len(specs),
        duration_ms=round(timer.duration_ms),
    )
    return LegacyExtractionResult(audio_path, subtitle_path)


class ExtractionService:
    """Dispatch one neutral extraction request to its container adapter."""

    def __init__(self, *, runner: ProcessRunner | None = None) -> None:
        self._runner: ProcessRunner = runner or SubprocessRunner()

    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ExtractionResult:
        """Extract exactly one selected track into an explicit target path."""
        if request.media_path.suffix.casefold() == ".mkv":
            return extract_mkv_track(
                request,
                cancel=cancel,
                timeout_s=timeout_s,
                runner=self._runner,
            )
        if request.media_path.suffix.casefold() == ".mp4":
            return extract_mp4_track(
                request,
                cancel=cancel,
                timeout_s=timeout_s,
                runner=self._runner,
            )
        msg = f"Unsupported extraction container: {request.media_path.name}"
        raise ExtractionError(
            context=ErrorContext(
                code=ErrorCode.MEDIA_UNSUPPORTED,
                message=msg,
                suggestion="Use an MKV or MP4 source file.",
            )
        )
