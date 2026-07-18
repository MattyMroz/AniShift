"""Identify Matroska files and extract selected tracks."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import (
    ExtractionResult,
    MediaInfo,
    TrackInfo,
    TrackSelection,
    format_extension,
    is_text_subtitle_codec,
)
from anishift.setup.installer import ensure_binary

__all__ = [
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
    """Parse ``mkvmerge -J`` JSON output into a typed :class:`MediaInfo`.

    Args:
        path: The container the payload describes.
        payload: Raw stdout of ``mkvmerge -J``.

    Returns:
        The typed container description, tracks sorted by id.

    Raises:
        ExtractionError: When the payload is not valid identify JSON.
    """
    try:
        raw: dict[str, Any] = json.loads(payload)
        container: dict[str, Any] = raw["container"]
        if container["recognized"] is False or container["supported"] is False:
            msg = f"{path}: not a supported Matroska file"
            raise _fail(ErrorCode.EXTRACTION_FAILED, msg)
        tracks = tuple(_parse_track(track) for track in raw["tracks"])
    except KeyError as exc:
        msg = f"{path}: identify JSON is missing field {exc}"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    except ValueError as exc:
        msg = f"{path}: identify JSON is invalid"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    except TypeError as exc:
        msg = f"{path}: identify JSON has invalid data"
        raise _fail(ErrorCode.EXTRACTION_FAILED, msg) from exc
    return MediaInfo(path=path, tracks=tuple(sorted(tracks, key=lambda track: track.id)))


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
    )


def identify(path: Path) -> MediaInfo:
    """Identify an MKV container with ``mkvmerge -J``.

    Args:
        path: The MKV file to identify.

    Returns:
        The typed container description.

    Raises:
        ExtractionError: When mkvmerge fails, times out or emits bad JSON.
    """
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
    return parse_media_info(path, completed.stdout)


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


def _cancel(process: subprocess.Popen[str], specs: list[tuple[int, Path]]) -> None:
    """Terminate an extraction and remove its partial outputs."""
    process.terminate()
    process.wait()
    _remove_outputs(specs)
    msg = "mkvextract extraction cancelled"
    raise _fail(ErrorCode.CANCELLED, msg)


def extract_tracks(
    info: MediaInfo,
    selection: TrackSelection,
    dest_dir: Path,
    *,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExtractionResult:
    """Extract the selected tracks into *dest_dir* with live progress.

    Runs a single ``mkvextract --gui-mode`` process covering both tracks and
    reports its ``#GUI#progress N%`` lines through *on_progress*. Validates
    that every requested output file exists and is non-empty afterwards.
    """
    specs = _build_specs(info, selection, dest_dir)
    if not specs:
        return ExtractionResult(None, None)
    audio_path = next((destination for track_id, destination in specs if track_id == selection.audio_id), None)
    subtitle_path = next((destination for track_id, destination in specs if track_id == selection.subtitle_id), None)

    exe = ensure_binary(Binary.MKVEXTRACT)
    command = [str(exe), "--ui-language", "en", "--gui-mode", str(info.path), "tracks"]
    command.extend(f"{track_id}:{destination}" for track_id, destination in specs)
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if cancel is not None and cancel.is_set():
            _cancel(process, specs)
        tail: deque[str] = deque(maxlen=_ERROR_TAIL_LINES)
        for line in process.stdout or ():
            if cancel is not None and cancel.is_set():
                _cancel(process, specs)
            match = _RE_GUI_PROGRESS.match(line)
            if match is not None:
                if on_progress is not None:
                    on_progress(min(100, int(match.group(1))))
                continue
            tail.append(line.strip())
        returncode = process.wait()
        if returncode != 0:
            detail = " | ".join(line for line in tail if line)
            msg = f"{info.path}: mkvextract failed: {detail}"
            raise _fail(
                ErrorCode.EXTRACTION_FAILED,
                msg,
                "Check the MKV is readable and the disk has free space",
                details={"command": command, "tail": list(tail)},
            )
        for _, destination in specs:
            if not destination.is_file() or destination.stat().st_size == 0:
                msg = f"{info.path}: mkvextract exited 0 but wrote no data"
                raise _fail(ErrorCode.EXTRACTION_FAILED, msg, details={"output": str(destination)})
    except OSError as exc:
        msg = f"{info.path}: extraction I/O failed: {exc}"
        raise _fail(ErrorCode.IO_ERROR, msg) from exc
    if on_progress is not None:
        on_progress(100)
    return ExtractionResult(audio_path, subtitle_path)
