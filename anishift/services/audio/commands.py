"""Safe FFmpeg-family command construction and subprocess execution."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, Never, Protocol

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioCancelledError, AudioProcessError
from anishift.services.audio.types import AudioFormat
from anishift.utils.logger import get_logger
from anishift.utils.timer import Timer

__all__ = [
    "CommandResult",
    "CommandRunner",
    "PcmTarget",
    "SubprocessRunner",
    "decode_command",
    "decode_duration_command",
    "ffmpeg_progress_reader",
    "join_clips_command",
    "narrator_wav_command",
    "normalize_command",
    "probe_command",
    "scan_duration_command",
    "transcode_command",
]

# ── Constants ────────────────────────────────────────────────────────────────

_POLL_SECONDS: Final[float] = 0.1
"""Maximum wait between timeout and cancellation checks."""

_IN_PROGRESS_PERCENT: Final[int] = 99
"""Maximum measured progress before the caller validates its output."""

_STDERR_TAIL_LINES: Final[int] = 8
"""Trailing stderr lines retained in a safe process error."""

_STDERR_TAIL_CHARS: Final[int] = 2_000
"""Maximum diagnostic stderr characters retained in an error."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag preventing console Ctrl+C from leaking into child processes."""

_MINIMUM_JOIN_SOURCES: Final[int] = 2
"""Minimum number of parts that require provider-native assembly."""

_JOIN_OUTPUT_ARGS: Final[dict[AudioFormat, tuple[str, ...]]] = {
    AudioFormat.AAC: ("-c:a", "aac", "-f", "adts"),
    AudioFormat.FLAC: ("-c:a", "flac", "-f", "flac"),
    AudioFormat.MP3: ("-c:a", "libmp3lame", "-f", "mp3"),
    AudioFormat.OGG: ("-c:a", "libvorbis", "-f", "ogg"),
    AudioFormat.OPUS: ("-c:a", "libopus", "-f", "ogg"),
    AudioFormat.WAV: ("-c:a", "pcm_s16le", "-f", "wav"),
}
"""Explicit encoder and muxer for provider-native multipart clip assembly."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured output from one successful external process."""

    command: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True, slots=True)
class PcmTarget:
    """Raw PCM target used by a normalization command."""

    sample_rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class _ProcessFailure:
    operation: str
    command: tuple[str, ...]
    returncode: int | None
    stderr: str
    code: ErrorCode


class CommandRunner(Protocol):
    """Execution boundary used by probe, normalization, and output services."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        """Execute one argument-list command or raise a typed audio error."""
        ...


class SubprocessRunner:
    """Run bounded FFmpeg-family processes without a shell."""

    def __init__(self, *, shutdown_grace_s: float = 5.0) -> None:
        """Store the bounded grace period used before hard kill."""
        self._shutdown_grace_s: float = shutdown_grace_s

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        """Execute one command with timeout, cancellation, and safe stderr."""
        timer: Timer = Timer(operation, auto_start=True)
        logger.debug("Audio subprocess starting", operation=operation, timeout_s=timeout_s)
        try:
            process: subprocess.Popen[str] = subprocess.Popen(  # noqa: S603
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_NEW_PROCESS_GROUP,
            )
        except OSError as error:
            failure: _ProcessFailure = _ProcessFailure(
                operation=operation,
                command=command,
                returncode=None,
                stderr=str(error),
                code=ErrorCode.IO_ERROR,
            )
            _raise_process(failure, cause=error)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        readers: tuple[threading.Thread, ...] = ()
        if on_stdout_line is not None:
            readers = (
                _read_stream(process.stdout, stdout_lines, observer=on_stdout_line),
                _read_stream(process.stderr, stderr_lines),
            )
        stdout: str = ""
        stderr: str = ""
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    _raise_cancelled(operation)
                remaining_s: float = timeout_s - timer.duration_s
                if remaining_s <= 0:
                    _raise_process(_ProcessFailure(operation, command, None, "operation timed out", ErrorCode.TIMEOUT))
                try:
                    if readers:
                        process.wait(timeout=min(_POLL_SECONDS, remaining_s))
                    else:
                        stdout, stderr = process.communicate(timeout=min(_POLL_SECONDS, remaining_s))
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            self._stop(process, streaming=bool(readers))
            for reader in readers:
                reader.join(timeout=self._shutdown_grace_s)
        if readers:
            stdout, stderr = "".join(stdout_lines), "".join(stderr_lines)

        result: CommandResult = CommandResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            returncode=process.returncode,
        )
        if result.returncode != 0:
            _raise_process(
                _ProcessFailure(
                    operation=operation,
                    command=command,
                    returncode=result.returncode,
                    stderr=_safe_stderr(result.stderr),
                    code=ErrorCode.AUDIO_FAILED,
                ),
            )
        timer.stop()
        logger.debug(
            "Audio subprocess completed",
            operation=operation,
            duration_ms=round(timer.duration_ms),
        )
        return result

    def _stop(self, process: subprocess.Popen[str], *, streaming: bool = False) -> None:
        if process.poll() is not None:
            return
        wait: Callable[..., object] = process.wait if streaming else process.communicate
        process.terminate()
        try:
            wait(timeout=self._shutdown_grace_s)
        except subprocess.TimeoutExpired:
            process.kill()
            wait(timeout=self._shutdown_grace_s)


def _read_stream(
    stream: IO[str] | None,
    lines: list[str],
    *,
    observer: Callable[[str], None] | None = None,
) -> threading.Thread:
    """Drain one pipe and isolate optional progress observers from execution."""

    def read() -> None:
        try:
            for line in stream or ():
                lines.append(line)
                if observer is not None:
                    _notify_line(observer, line)
        finally:
            if stream is not None:
                stream.close()

    reader: threading.Thread = threading.Thread(target=read, name="audio-pipe", daemon=True)
    reader.start()
    return reader


def _notify_line(observer: Callable[[str], None], line: str) -> None:
    """Report one progress line without letting an observer own execution."""
    try:
        observer(line)
    except Exception:  # noqa: BLE001 - progress observers never own audio execution
        logger.warning("Audio progress observer failed")


def ffmpeg_progress_reader(
    on_percent: Callable[[int], None] | None,
    *,
    duration_ms: int,
) -> Callable[[str], None] | None:
    """Report measured FFmpeg output time when the total duration is known."""
    if on_percent is None or duration_ms <= 0:
        return None
    last_percent: int = -1

    def read(line: str) -> None:
        nonlocal last_percent
        key, separator, value = line.strip().partition("=")
        if key != "out_time_us" or not separator:
            return
        try:
            position_us: int = int(value)
        except ValueError:
            return
        percent: int = min(_IN_PROGRESS_PERCENT, max(0, position_us * 100 // (duration_ms * 1000)))
        if percent <= last_percent:
            return
        last_percent = percent
        on_percent(percent)

    return read


def probe_command(ffprobe: Path, path: Path) -> tuple[str, ...]:
    """Build the machine-readable metadata probe command."""
    return (
        str(ffprobe),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    )


def decode_command(ffmpeg: Path, path: Path) -> tuple[str, ...]:
    """Build a complete decode check for the first audio stream."""
    return (
        str(ffmpeg),
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
    )


def decode_duration_command(ffmpeg: Path, path: Path) -> tuple[str, ...]:
    """Build a complete decode that reports the exact rendered duration."""
    return (
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "null",
        "-",
    )


def scan_duration_command(ffmpeg: Path, path: Path) -> tuple[str, ...]:
    """Build a packet-copy scan that reports exact stream timeline duration."""
    return (
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "copy",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "null",
        "-",
    )


def join_clips_command(
    ffmpeg: Path,
    sources: tuple[Path, ...],
    destination: Path,
    *,
    clip_format: AudioFormat,
) -> tuple[str, ...]:
    """Build one filter-concat command without an artificial gap."""
    if len(sources) < _MINIMUM_JOIN_SOURCES:
        message: str = "Clip assembly requires at least two source paths"
        raise ValueError(message)
    try:
        output_args: tuple[str, ...] = _JOIN_OUTPUT_ARGS[clip_format]
    except KeyError as error:
        message = f"Unsupported provider-native clip format: {clip_format}"
        raise ValueError(message) from error
    command: list[str] = [str(ffmpeg), "-v", "error", "-nostdin"]
    for source in sources:
        command.extend(("-i", str(source)))
    command.extend(
        (
            "-filter_complex",
            f"concat=n={len(sources)}:v=0:a=1[out]",
            "-map",
            "[out]",
            "-vn",
            "-sn",
            "-dn",
            *output_args,
            "-y",
            str(destination),
        ),
    )
    return tuple(command)


def normalize_command(
    ffmpeg: Path,
    source: Path,
    destination: Path,
    *,
    target: PcmTarget,
    tempo_filter: str | None,
) -> tuple[str, ...]:
    """Build source clip conversion to raw PCM S16LE."""
    command: list[str] = [
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
    ]
    if tempo_filter is not None:
        command.extend(("-af", tempo_filter))
    command.extend(
        (
            "-ac",
            str(target.channels),
            "-ar",
            str(target.sample_rate),
            "-sample_fmt",
            "s16",
            "-f",
            "s16le",
            "-y",
            str(destination),
        ),
    )
    return tuple(command)


def narrator_wav_command(
    ffmpeg: Path,
    raw_pcm: Path,
    destination: Path,
    *,
    sample_rate: int,
    channels: int,
) -> tuple[str, ...]:
    """Build raw PCM wrapping into PCM S16LE WAV with automatic RF64."""
    return (
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-i",
        str(raw_pcm),
        "-map",
        "0:a:0",
        "-c:a",
        "pcm_s16le",
        "-rf64",
        "auto",
        "-f",
        "wav",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        str(destination),
    )


def transcode_command(  # noqa: PLR0913 - explicit FFmpeg output contract
    ffmpeg: Path,
    source: Path,
    destination: Path,
    *,
    encoder: str,
    output_arguments: tuple[str, ...],
    container: str,
    output_layout: str,
    output_channels: int,
    sample_rate: int,
    source_filter: str | None,
) -> tuple[str, ...]:
    """Build one explicit single-stream audio transcode command."""
    command: list[str] = [
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
    ]
    if source_filter is not None:
        command.extend(("-af", source_filter))
    command.extend(
        (
            "-c:a",
            encoder,
            *output_arguments,
            "-ac",
            str(output_channels),
            "-channel_layout",
            output_layout,
            "-ar",
            str(sample_rate),
            "-f",
            container,
            "-y",
            "-progress",
            "pipe:1",
            "-nostats",
            str(destination),
        )
    )
    return tuple(command)


def _safe_stderr(stderr: str) -> str:
    lines: list[str] = [line.strip() for line in stderr.splitlines() if line.strip()]
    return " | ".join(lines[-_STDERR_TAIL_LINES:])[-_STDERR_TAIL_CHARS:]


def _raise_cancelled(operation: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message=f"Audio operation cancelled: {operation}",
        suggestion="Run the file again to resume from committed artifacts.",
        details={"operation": operation},
    )
    raise AudioCancelledError(context=context)


def _raise_process(
    failure: _ProcessFailure,
    *,
    cause: OSError | None = None,
) -> Never:
    context: ErrorContext = ErrorContext(
        code=failure.code,
        message=f"Audio process failed: {failure.operation}",
        suggestion="Check the input audio, FFmpeg installation, and free disk space.",
        details={
            "operation": failure.operation,
            "returncode": failure.returncode,
            "stderr_tail": _safe_stderr(failure.stderr),
            "executable": failure.command[0],
        },
    )
    error: AudioProcessError = AudioProcessError(context=context)
    if cause is not None:
        raise error from cause
    raise error
