"""Fast structural inspection of MPEG Layer III streams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioProbeError

__all__ = ["Mp3StreamProperties", "read_mp3_stream_properties"]

_HEADER_BYTES: Final[int] = 4
"""Number of bytes in one MPEG audio frame header."""

_ID3_HEADER_BYTES: Final[int] = 10
"""Number of bytes in an ID3v2 header or footer."""

_MAX_FRAME_SCAN_BYTES: Final[int] = 128 * 1024
"""Maximum MPEG payload prefix inspected after an optional ID3v2 tag."""

_MPEG_LAYER_III: Final[int] = 1
"""Bit-field value identifying MPEG Layer III."""

_MPEG_SYNC_WORD: Final[int] = 0x7FF
"""Eleven-bit synchronization word starting every MPEG audio frame."""

_MPEG1_VERSION: Final[int] = 3
"""Bit-field value identifying MPEG-1."""

_RESERVED_SAMPLE_RATE: Final[int] = 3
"""Reserved sample-rate index rejected by the MPEG audio specification."""

_SINGLE_CHANNEL_MODE: Final[int] = 3
"""Channel-mode value identifying a single-channel stream."""

_MPEG1_BITRATES_KBPS: Final[tuple[int, ...]] = (
    0,
    32,
    40,
    48,
    56,
    64,
    80,
    96,
    112,
    128,
    160,
    192,
    224,
    256,
    320,
)
"""Layer III bitrates indexed by an MPEG-1 frame header."""

_MPEG2_BITRATES_KBPS: Final[tuple[int, ...]] = (
    0,
    8,
    16,
    24,
    32,
    40,
    48,
    56,
    64,
    80,
    96,
    112,
    128,
    144,
    160,
)
"""Layer III bitrates indexed by an MPEG-2 or MPEG-2.5 frame header."""

_SAMPLE_RATES: Final[dict[int, tuple[int, int, int]]] = {
    0: (11_025, 12_000, 8_000),
    2: (22_050, 24_000, 16_000),
    3: (44_100, 48_000, 32_000),
}
"""Sample rates indexed first by MPEG version bits, then frequency bits."""


@dataclass(frozen=True, slots=True)
class Mp3StreamProperties:
    """Technical properties established from consecutive MPEG frames."""

    sample_rate: int
    channels: int


@dataclass(frozen=True, slots=True)
class _FrameHeader:
    version: int
    sample_rate: int
    channels: int
    frame_length: int


def read_mp3_stream_properties(path: Path) -> Mp3StreamProperties:
    """Read stable stream properties from two consecutive Layer III frames."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_mp3_probe(path, "MP3 file is missing or empty")
    try:
        with path.open("rb") as stream:
            prefix: bytes = stream.read(_ID3_HEADER_BYTES)
            audio_offset: int = _id3_audio_offset(path, prefix)
            stream.seek(audio_offset)
            payload: bytes = stream.read(_MAX_FRAME_SCAN_BYTES)
    except OSError as error:
        _raise_mp3_probe(path, "MP3 file could not be inspected", cause=error)
    for offset in range(0, len(payload) - (_HEADER_BYTES * 2) + 1):
        first: _FrameHeader | None = _parse_frame_header(payload, offset)
        if first is None:
            continue
        second: _FrameHeader | None = _parse_frame_header(
            payload,
            offset + first.frame_length,
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


def _id3_audio_offset(path: Path, prefix: bytes) -> int:
    if not prefix.startswith(b"ID3"):
        return 0
    if len(prefix) < _ID3_HEADER_BYTES:
        _raise_mp3_probe(path, "MP3 file has a truncated ID3v2 header")
    size_bytes: bytes = prefix[6:10]
    if any(byte & 0x80 for byte in size_bytes):
        _raise_mp3_probe(path, "MP3 file has an invalid ID3v2 size")
    tag_size: int = 0
    for byte in size_bytes:
        tag_size = (tag_size << 7) | byte
    footer_size: int = _ID3_HEADER_BYTES if prefix[5] & 0x10 else 0
    return _ID3_HEADER_BYTES + tag_size + footer_size


def _parse_frame_header(payload: bytes, offset: int) -> _FrameHeader | None:
    if offset < 0 or offset + _HEADER_BYTES > len(payload):
        return None
    header: int = int.from_bytes(payload[offset : offset + _HEADER_BYTES])
    if header >> 21 != _MPEG_SYNC_WORD:
        return None
    version: int = (header >> 19) & 0b11
    layer: int = (header >> 17) & 0b11
    bitrate_index: int = (header >> 12) & 0b1111
    sample_rate_index: int = (header >> 10) & 0b11
    if (
        version == 1
        or layer != _MPEG_LAYER_III
        or bitrate_index in {0, 0b1111}
        or sample_rate_index == _RESERVED_SAMPLE_RATE
    ):
        return None
    bitrate_table: tuple[int, ...] = _MPEG1_BITRATES_KBPS if version == _MPEG1_VERSION else _MPEG2_BITRATES_KBPS
    bitrate: int = bitrate_table[bitrate_index] * 1000
    sample_rate: int = _SAMPLE_RATES[version][sample_rate_index]
    padding: int = (header >> 9) & 1
    frame_scale: int = 144 if version == _MPEG1_VERSION else 72
    frame_length: int = (frame_scale * bitrate // sample_rate) + padding
    channel_mode: int = (header >> 6) & 0b11
    return _FrameHeader(
        version=version,
        sample_rate=sample_rate,
        channels=1 if channel_mode == _SINGLE_CHANNEL_MODE else 2,
        frame_length=frame_length,
    )


def _same_stream(first: _FrameHeader, second: _FrameHeader) -> bool:
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
