"""Fast structural inspection of MPEG Layer III streams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioProbeError
from anishift.utils.mp3_frames import HEADER_BYTES, ID3_HEADER_BYTES, FrameHeader, audio_offset, parse_frame_header

__all__ = ["Mp3StreamProperties", "read_mp3_stream_properties"]

_MAX_FRAME_SCAN_BYTES: Final[int] = 128 * 1024
"""Maximum MPEG payload prefix inspected after an optional ID3v2 tag."""


@dataclass(frozen=True, slots=True)
class Mp3StreamProperties:
    """Technical properties established from consecutive MPEG frames."""

    sample_rate: int
    channels: int


def read_mp3_stream_properties(path: Path) -> Mp3StreamProperties:
    """Read stable stream properties from two consecutive Layer III frames."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_mp3_probe(path, "MP3 file is missing or empty")
    try:
        with path.open("rb") as stream:
            prefix: bytes = stream.read(ID3_HEADER_BYTES)
            stream.seek(_audio_offset(path, prefix))
            payload: bytes = stream.read(_MAX_FRAME_SCAN_BYTES)
    except OSError as error:
        _raise_mp3_probe(path, "MP3 file could not be inspected", cause=error)
    for offset in range(0, len(payload) - (HEADER_BYTES * 2) + 1):
        first: FrameHeader | None = parse_frame_header(payload, offset)
        if first is None:
            continue
        second: FrameHeader | None = parse_frame_header(
            payload,
            offset + first.size,
        )
        if second is not None and _same_stream(first, second):
            return Mp3StreamProperties(
                sample_rate=first.sample_rate,
                channels=first.channels,
            )
    return _raise_mp3_probe(
        path,
        "MP3 file has no consecutive valid Layer III frames",
    )


def _audio_offset(path: Path, prefix: bytes) -> int:
    try:
        return audio_offset(prefix)
    except ValueError as error:
        _raise_mp3_probe(path, f"MP3 file has an unusable ID3v2 tag: {error}", cause=error)


def _same_stream(first: FrameHeader, second: FrameHeader) -> bool:
    return (
        first.version == second.version
        and first.sample_rate == second.sample_rate
        and first.channels == second.channels
    )


def _raise_mp3_probe(
    path: Path,
    message: str,
    *,
    cause: BaseException | None = None,
) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Regenerate the provider audio artifact.",
        details={"operation": "inspect_mp3", "path": str(path)},
    )
    error: AudioProbeError = AudioProbeError(context=context)
    if cause is not None:
        raise error from cause
    raise error
