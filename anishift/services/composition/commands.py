"""Command construction and streaming subprocess execution for composition."""

from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionProcessError,
)
from anishift.services.composition.paths import escape_filter_path
from anishift.services.composition.types import CompositionPlan, ContainerCompositionRequest
from anishift.utils.logger import get_logger
from anishift.utils.timer import Timer

__all__ = [
    "NARRATION_TRACK_NAME",
    "CommandOutcome",
    "ProgressReader",
    "StreamingRunner",
    "burn_command",
    "container_burn_command",
    "container_merge_command",
    "merge_command",
    "mp4_audio_is_copyable",
    "parse_ffmpeg_progress",
    "parse_mkvmerge_progress",
    "subtitle_filter_argument",
]

# ── Constants ────────────────────────────────────────────────────────────────

_POLL_SECONDS: Final[float] = 0.2
"""Interval between cancellation checks while a process is streaming."""

_STDERR_TAIL_LINES: Final[int] = 8
"""Trailing stderr lines retained in a safe process error."""

_STDERR_TAIL_CHARS: Final[int] = 2_000
"""Maximum diagnostic stderr characters retained in an error."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag preventing console Ctrl+C from leaking into child processes."""

_GUI_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^#GUI#progress (\d+)%")
"""mkvmerge --gui-mode progress line."""

_FFMPEG_PROGRESS: Final[re.Pattern[str]] = re.compile(r"^out_time_us=(\d+)")
"""FFmpeg -progress microsecond position line."""

_FULL_PERCENT: Final[int] = 100
"""Upper bound reported to progress observers."""

_MP4_COPYABLE_AUDIO: Final[frozenset[str]] = frozenset({"aac", "eac3", "ac3", "mp3", "opus", "flac"})
"""FFprobe audio codec names that mux into MP4 without re-encoding."""

_POLISH_LANGUAGE: Final[str] = "pol"
"""BCP 47 language assigned to every track this application adds."""

NARRATION_TRACK_NAME: Final[str] = "Lektor PL"
"""Track name carried by the narration audio in every merged container."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Captured result of one streamed external process."""

    command: tuple[str, ...]
    returncode: int
    stderr: str
    had_warnings: bool


type ProgressReader = Callable[[str], int | None]
"""Translate one output line into a percentage, or ``None`` when irrelevant."""


def merge_command(
    plan: CompositionPlan,
    *,
    mkvmerge: Path,
    destination: Path,
) -> tuple[str, ...]:
    """Build the mkvmerge invocation adding lector and subtitle tracks.

    Original tracks, attachments, chapters, and tags are copied by default, so
    only the appended files carry explicit metadata. No ``--track-order`` is
    passed: mkvmerge lays files out in command order, which already puts every
    appended track after the whole source. Naming only the added tracks would
    instead push the source's own audio and subtitles behind them.
    """
    arguments: list[str] = [
        str(mkvmerge),
        "--gui-mode",
        "--output",
        str(destination),
        str(plan.source_path),
    ]
    if plan.narration_audio is not None:
        arguments.extend(_appended_track_arguments(NARRATION_TRACK_NAME, plan.narration_audio))
    for subtitle in plan.subtitles:
        arguments.extend(_appended_track_arguments(subtitle.track_name, subtitle.path))
    return tuple(arguments)


def container_merge_command(
    request: ContainerCompositionRequest,
    *,
    mkvmerge: Path,
    destination: Path,
) -> tuple[str, ...]:
    """Build one MKV command from the target-specific composition contract."""
    arguments: list[str] = [str(mkvmerge), "--gui-mode", "--output", str(destination)]
    if not request.keep_original_audio:
        arguments.append("--no-audio")
    arguments.append(str(request.source_video))
    if request.narration_audio is not None:
        arguments.extend(_appended_track_arguments(NARRATION_TRACK_NAME, request.narration_audio))
    for subtitle in request.attached_subtitles:
        arguments.extend(
            _appended_track_arguments(
                subtitle.track_name,
                subtitle.path,
                language=subtitle.language,
            )
        )
    return tuple(arguments)


def _appended_track_arguments(
    track_name: str,
    path: Path,
    *,
    language: str = _POLISH_LANGUAGE,
) -> tuple[str, ...]:
    """Return per-track options plus the file they apply to."""
    return (
        "--language",
        f"0:{language}",
        "--track-name",
        f"0:{track_name}",
        "--default-track-flag",
        "0:no",
        "--forced-display-flag",
        "0:no",
        str(path),
    )


def burn_command(  # noqa: PLR0913 - render inputs stay explicit instead of a wrapper object
    plan: CompositionPlan,
    *,
    ffmpeg: Path,
    config: CompositionConfig,
    subtitle_argument: str | None,
    audio_codec: str,
    destination: Path,
) -> tuple[str, ...]:
    """Build the FFmpeg invocation rendering one MP4.

    The picture is always re-encoded when a subtitle filter is present; a copy
    of the video stream is impossible while libass composites frames.
    ``audio_codec`` describes the stream actually mapped into the result — the
    narration sidecar when one exists, otherwise the source's own audio.
    """
    arguments: list[str] = [str(ffmpeg), "-y", "-hide_banner", "-nostats"]
    arguments.extend(("-i", str(plan.source_path)))
    if plan.narration_audio is not None:
        arguments.extend(("-i", str(plan.narration_audio)))
        arguments.extend(("-map", "0:v:0", "-map", "1:a:0"))
    else:
        arguments.extend(("-map", "0:v:0", "-map", "0:a:0?"))
    if subtitle_argument is not None:
        arguments.extend(("-vf", subtitle_argument))
        arguments.extend(("-c:v", config.video_encoder))
        arguments.extend(("-crf", str(config.crf)))
        arguments.extend(("-preset", config.encoder_preset))
        arguments.extend(("-pix_fmt", "yuv420p"))
    else:
        arguments.extend(("-c:v", "copy"))
    arguments.extend(("-c:a", "copy") if mp4_audio_is_copyable(audio_codec) else ("-c:a", "aac"))
    arguments.extend(("-movflags", "+faststart"))
    arguments.extend(("-progress", "pipe:1"))
    arguments.append(str(destination))
    return tuple(arguments)


def container_burn_command(  # noqa: PLR0913 - explicit process inputs avoid hidden policy
    request: ContainerCompositionRequest,
    *,
    ffmpeg: Path,
    config: CompositionConfig,
    subtitle_argument: str | None,
    audio_codec: str,
    destination: Path,
) -> tuple[str, ...]:
    """Build one MP4 command without deriving burn or audio policy from presence alone."""
    arguments: list[str] = [str(ffmpeg), "-y", "-hide_banner", "-nostats", "-i", str(request.source_video)]
    if request.narration_audio is not None:
        arguments.extend(("-i", str(request.narration_audio)))
    arguments.extend(("-map", "0:v:0"))
    if request.keep_original_audio:
        arguments.extend(("-map", "0:a:0?"))
    if request.narration_audio is not None:
        arguments.extend(("-map", "1:a:0"))
    if subtitle_argument is not None:
        arguments.extend(("-vf", subtitle_argument))
        arguments.extend(("-c:v", config.video_encoder))
        arguments.extend(("-crf", str(config.crf)))
        arguments.extend(("-preset", config.encoder_preset))
        arguments.extend(("-pix_fmt", "yuv420p"))
    else:
        arguments.extend(("-c:v", "copy"))
    if request.keep_original_audio and request.narration_audio is not None:
        arguments.extend(("-c:a", "aac"))
    elif request.keep_original_audio or request.narration_audio is not None:
        arguments.extend(("-c:a", "copy") if mp4_audio_is_copyable(audio_codec) else ("-c:a", "aac"))
    arguments.extend(("-movflags", "+faststart", "-progress", "pipe:1", str(destination)))
    return tuple(arguments)


def subtitle_filter_argument(
    subtitle: Path,
    *,
    kind: str,
    fonts_dir: Path | None = None,
) -> str:
    """Return the ``-vf`` value rendering one subtitle file.

    ``ass`` preserves every V4+ style verbatim; ``subtitles`` is used only for
    SRT, which libass renders with its default style.
    """
    filter_name: str = "ass" if kind == "ass" else "subtitles"
    value: str = f"{filter_name}={escape_filter_path(subtitle)}"
    if fonts_dir is not None:
        value = f"{value}:fontsdir={escape_filter_path(fonts_dir)}"
    return value


def mp4_audio_is_copyable(codec: str) -> bool:
    """Return whether an FFprobe audio codec muxes into MP4 as is."""
    return codec.casefold() in _MP4_COPYABLE_AUDIO


def parse_mkvmerge_progress(line: str) -> int | None:
    """Return the percentage reported by one ``--gui-mode`` line."""
    match: re.Match[str] | None = _GUI_PROGRESS.match(line.strip())
    return int(match.group(1)) if match is not None else None


def parse_ffmpeg_progress(line: str, *, total_us: int) -> int | None:
    """Return the percentage derived from one ``-progress`` line."""
    match: re.Match[str] | None = _FFMPEG_PROGRESS.match(line.strip())
    if match is None or total_us <= 0:
        return None
    position_us: int = int(match.group(1))
    return min(_FULL_PERCENT, round(position_us * _FULL_PERCENT / total_us))


class StreamingRunner:
    """Run one external process while reporting progress line by line."""

    def __init__(self, *, shutdown_grace_s: float = 5.0) -> None:
        """Store the grace period applied before a hard kill."""
        self._shutdown_grace_s: float = shutdown_grace_s

    def run(  # noqa: PLR0913 - each argument is one explicit process concern
        self,
        command: Sequence[str],
        *,
        operation: str,
        timeout_s: float,
        progress: ProgressReader | None = None,
        on_percent: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
        warning_exit_code: int | None = None,
    ) -> CommandOutcome:
        """Execute one command, streaming stdout and enforcing cancellation.

        Both pipes are drained by daemon threads: a process that stops printing
        still meets its cancellation and timeout checks every poll interval,
        and a noisy stderr never fills its buffer and deadlocks the run.
        """
        timer: Timer = Timer(operation, auto_start=True)
        logger.debug("Composition subprocess starting", operation=operation)
        process: subprocess.Popen[str] = _spawn(command, operation)
        lines: queue.Queue[str | None] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
        _drain(process.stdout, lines.put, done=lambda: lines.put(None))
        _drain(process.stderr, stderr_tail.append)
        last_percent: int = -1
        while True:
            self._guard(process, operation=operation, timer=timer, timeout_s=timeout_s, cancel=cancel)
            try:
                line: str | None = lines.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                continue
            if line is None:
                break
            last_percent = _report(line, progress=progress, on_percent=on_percent, last_percent=last_percent)
        returncode: int = process.wait()
        timer.stop()
        stderr: str = _safe_stderr(stderr_tail)
        had_warnings: bool = warning_exit_code is not None and returncode == warning_exit_code
        if returncode != 0 and not had_warnings:
            _raise_process(operation, returncode, stderr, ErrorCode.COMPOSITION_FAILED)
        logger.info(
            "Composition subprocess completed",
            operation=operation,
            duration_ms=round(timer.duration_ms),
            had_warnings=had_warnings,
        )
        return CommandOutcome(
            command=tuple(command),
            returncode=returncode,
            stderr=stderr,
            had_warnings=had_warnings,
        )

    def _guard(
        self,
        process: subprocess.Popen[str],
        *,
        operation: str,
        timer: Timer,
        timeout_s: float,
        cancel: threading.Event | None,
    ) -> None:
        """Stop the process when cancellation or the time budget demands it."""
        if cancel is not None and cancel.is_set():
            self._stop(process)
            _raise_cancelled(operation)
        if timer.duration_s <= timeout_s:
            return
        self._stop(process)
        _raise_process(operation, None, "operation timed out", ErrorCode.TIMEOUT)

    def _stop(self, process: subprocess.Popen[str]) -> None:
        """Terminate a running process, killing it after the grace period."""
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=self._shutdown_grace_s)
        except subprocess.TimeoutExpired:
            process.kill()


def _spawn(command: Sequence[str], operation: str) -> subprocess.Popen[str]:
    """Start one external process with both pipes captured as text."""
    try:
        return subprocess.Popen(  # noqa: S603 - command built from validated binaries and paths
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_NEW_PROCESS_GROUP,
        )
    except OSError as error:
        _raise_process(operation, None, str(error), ErrorCode.IO_ERROR, cause=error)


def _drain(stream: IO[str] | None, sink: Callable[[str], None], *, done: Callable[[], None] | None = None) -> None:
    """Consume one pipe in a daemon thread so its buffer never fills."""

    def _pump() -> None:
        for line in stream or ():
            sink(line)
        if done is not None:
            done()

    threading.Thread(target=_pump, name="composition-pipe", daemon=True).start()


def _report(
    line: str,
    *,
    progress: ProgressReader | None,
    on_percent: Callable[[int], None] | None,
    last_percent: int,
) -> int:
    """Return the percentage after reporting one changed progress line."""
    if progress is None or on_percent is None:
        return last_percent
    percent: int | None = progress(line)
    if percent is None or percent == last_percent:
        return last_percent
    on_percent(percent)
    return percent


def _safe_stderr(lines: Iterable[str]) -> str:
    """Return a short diagnostic tail free of full commands and paths."""
    kept: list[str] = [line.strip() for line in lines if line.strip()]
    return " | ".join(kept)[-_STDERR_TAIL_CHARS:]


def _raise_cancelled(operation: str) -> Never:
    """Raise the typed cancellation error for one composition operation."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message=f"Composition cancelled: {operation}",
        suggestion="Run the file again to assemble it from existing products.",
        details={"operation": operation},
    )
    raise CompositionCancelledError(context=context)


def _raise_process(
    operation: str,
    returncode: int | None,
    stderr: str,
    code: ErrorCode,
    *,
    cause: OSError | None = None,
) -> Never:
    """Raise the typed process failure carrying a safe diagnostic tail."""
    context: ErrorContext = ErrorContext(
        code=code,
        message=f"Composition process failed: {operation}",
        suggestion="Check the source file, free disk space, and the bundled tools.",
        details={"operation": operation, "returncode": returncode, "stderr_tail": stderr},
    )
    error: CompositionProcessError = CompositionProcessError(context=context)
    if cause is not None:
        raise error from cause
    raise error
