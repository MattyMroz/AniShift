"""FFprobe metadata parsing and complete FFmpeg decode validation."""

from __future__ import annotations

import json
import threading
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.commands import (
    CommandRunner,
    decode_command,
    decode_duration_command,
    probe_command,
    scan_duration_command,
)
from anishift.services.audio.errors import (
    AudioDecodeError,
    AudioProbeError,
    AudioProcessError,
)
from anishift.services.audio.mp3 import (
    Mp3StreamProperties,
    read_mp3_stream_properties,
)
from anishift.services.audio.types import AudioProbe

__all__ = [
    "measure_audio_duration",
    "measure_decoded_duration",
    "parse_probe_json",
    "probe_audio",
    "probe_decoded_mp3",
    "validate_decode",
]


def measure_audio_duration(
    path: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    timeout_s: float,
    cancel: threading.Event | None = None,
) -> int:
    """Return exact packet timeline duration, falling back to full decode."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_decode_duration("Audio duration input is missing or empty")
    try:
        result = runner.run(
            scan_duration_command(ffmpeg, path),
            operation="scan_duration",
            timeout_s=timeout_s,
            cancel=cancel,
        )
        return _duration_from_progress(result.stdout)
    except AudioProcessError as error:
        if error.context.code is not ErrorCode.AUDIO_FAILED:
            raise
        return measure_decoded_duration(
            path,
            ffmpeg=ffmpeg,
            runner=runner,
            timeout_s=timeout_s,
            cancel=cancel,
        )
    except AudioDecodeError:
        return measure_decoded_duration(
            path,
            ffmpeg=ffmpeg,
            runner=runner,
            timeout_s=timeout_s,
            cancel=cancel,
        )


def parse_probe_json(path: Path, payload: str) -> AudioProbe:
    """Parse FFprobe JSON and select its first audio stream."""
    try:
        raw: object = json.loads(payload)
        if not isinstance(raw, dict):
            _raise_probe(path, "FFprobe returned a non-object JSON document")
        streams_raw: object = raw.get("streams")
        if not isinstance(streams_raw, list):
            _raise_probe(path, "FFprobe JSON has no streams list")
        streams: list[object] = streams_raw
        stream: dict[str, Any] | None = next(
            (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"),
            None,
        )
        if stream is None:
            _raise_probe(path, "File contains no audio stream")
        format_raw: object = raw.get("format", {})
        if not isinstance(format_raw, dict):
            _raise_probe(path, "FFprobe JSON has an invalid format object")
        media_format: dict[str, Any] = format_raw
        duration_value: object = stream.get("duration", media_format.get("duration"))
        duration_ms: int = _duration_ms(duration_value)
        sample_rate: int = _positive_int(stream.get("sample_rate"), "sample_rate")
        channels: int = _positive_int(stream.get("channels"), "channels")
        bit_rate: int | None = _optional_positive_int(stream.get("bit_rate", media_format.get("bit_rate")))
        codec_name: str = _non_empty_str(stream.get("codec_name"), "codec_name")
        format_name: str = _non_empty_str(media_format.get("format_name"), "format_name")
        channel_layout_value: object = stream.get("channel_layout")
        channel_layout: str = (
            channel_layout_value
            if isinstance(channel_layout_value, str) and channel_layout_value
            else _default_layout(channels)
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        _raise_probe(path, "FFprobe JSON contains invalid audio metadata", cause=error)
    return AudioProbe(
        path=path,
        codec_name=codec_name,
        format_name=format_name,
        sample_rate=sample_rate,
        channels=channels,
        channel_layout=channel_layout,
        duration_ms=duration_ms,
        bit_rate=bit_rate,
    )


def probe_audio(
    path: Path,
    *,
    ffprobe: Path,
    runner: CommandRunner,
    timeout_s: float,
    cancel: threading.Event | None = None,
) -> AudioProbe:
    """Probe one file through FFprobe's JSON output."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_probe(path, "Audio file is missing or empty")
    result = runner.run(
        probe_command(ffprobe, path),
        operation="probe",
        timeout_s=timeout_s,
        cancel=cancel,
    )
    return parse_probe_json(path, result.stdout)


def probe_decoded_mp3(
    path: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    timeout_s: float,
    cancel: threading.Event | None = None,
) -> AudioProbe:
    """Inspect MPEG metadata and return duration from one complete decode."""
    properties: Mp3StreamProperties = read_mp3_stream_properties(path)
    duration_ms: int = measure_decoded_duration(
        path,
        ffmpeg=ffmpeg,
        runner=runner,
        timeout_s=timeout_s,
        cancel=cancel,
    )
    return AudioProbe(
        path=path,
        codec_name="mp3",
        format_name="mp3",
        sample_rate=properties.sample_rate,
        channels=properties.channels,
        channel_layout=_default_layout(properties.channels),
        duration_ms=duration_ms,
        bit_rate=None,
    )


def validate_decode(
    path: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    timeout_s: float,
    cancel: threading.Event | None = None,
) -> None:
    """Require FFmpeg to decode the complete first audio stream."""
    if not path.is_file() or path.stat().st_size == 0:
        context: ErrorContext = ErrorContext(
            code=ErrorCode.AUDIO_FAILED,
            message="Audio decode input is missing or empty",
            suggestion="Regenerate the audio artifact.",
            details={"operation": "decode"},
        )
        raise AudioDecodeError(context=context)
    try:
        runner.run(
            decode_command(ffmpeg, path),
            operation="decode",
            timeout_s=timeout_s,
            cancel=cancel,
        )
    except AudioProcessError as error:
        context = ErrorContext(
            code=ErrorCode.AUDIO_FAILED,
            message="Audio file failed its complete decode check",
            suggestion="Regenerate the audio artifact and inspect FFmpeg diagnostics.",
            details={"operation": "decode"},
        )
        raise AudioDecodeError(context=context) from error


def measure_decoded_duration(
    path: Path,
    *,
    ffmpeg: Path,
    runner: CommandRunner,
    timeout_s: float,
    cancel: threading.Event | None = None,
) -> int:
    """Return exact milliseconds from a complete first-stream audio decode."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_decode_duration("Audio duration input is missing or empty")
    result = runner.run(
        decode_duration_command(ffmpeg, path),
        operation="measure_duration",
        timeout_s=timeout_s,
        cancel=cancel,
    )
    return _duration_from_progress(result.stdout)


def _duration_from_progress(progress: str) -> int:
    values: dict[str, str] = {}
    progress_is_complete: bool = False
    for raw_line in progress.splitlines():
        key, separator, value = raw_line.partition("=")
        if not separator:
            continue
        values[key] = value
        if key == "progress" and value == "end":
            progress_is_complete = True
    if not progress_is_complete:
        _raise_decode_duration("Audio decode did not report completed duration")
    try:
        duration_us: Decimal = Decimal(values["out_time_us"])
    except KeyError, InvalidOperation:
        _raise_decode_duration("Audio decode reported an invalid duration")
    if not duration_us.is_finite() or duration_us <= 0:
        _raise_decode_duration("Audio decode reported an invalid duration")
    return int((duration_us / 1000).to_integral_value(rounding=ROUND_HALF_UP))


def _duration_ms(value: object) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError
    duration: Decimal = Decimal(str(value))
    if not duration.is_finite() or duration <= 0:
        raise ValueError
    return int((duration * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise TypeError(field)
    if type(value) is int:
        parsed: int = value
    elif isinstance(value, str) and value.isdecimal():
        parsed = int(value)
    else:
        raise TypeError(field)
    if parsed <= 0:
        raise ValueError(field)
    return parsed


def _optional_positive_int(value: object) -> int | None:
    if value is None or value == "N/A":
        return None
    return _positive_int(value, "bit_rate")


def _non_empty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(field)
    return value


def _default_layout(channels: int) -> str:
    if channels == 1:
        return "mono"
    if channels == 2:  # noqa: PLR2004
        return "stereo"
    raise ValueError("channel_layout")


def _raise_probe(path: Path, message: str, *, cause: BaseException | None = None) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Check that the file contains a complete supported audio stream.",
        details={"operation": "probe", "path": str(path)},
    )
    error: AudioProbeError = AudioProbeError(context=context)
    if cause is not None:
        raise error from cause
    raise error


def _raise_decode_duration(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Regenerate the source audio and inspect FFmpeg diagnostics.",
        details={"operation": "measure_duration"},
    )
    raise AudioDecodeError(context=context)
