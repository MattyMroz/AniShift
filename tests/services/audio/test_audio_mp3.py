from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.audio.errors import AudioProbeError
from anishift.services.audio.mp3 import read_mp3_stream_properties


def _layer3_frame(*, version: int = 3, mono: bool = True) -> bytes:
    channel_mode = 0b11 if mono else 0
    bitrate_index = 9 if version == 3 else 8
    bitrate = 128_000 if version == 3 else 64_000
    sample_rate = {0: 11_025, 2: 22_050, 3: 44_100}[version]
    header = (0x7FF << 21) | (version << 19) | (0b01 << 17) | (1 << 16) | (bitrate_index << 12) | (channel_mode << 6)
    frame_scale = 144 if version == 3 else 72
    frame_length = frame_scale * bitrate // sample_rate
    return header.to_bytes(4, byteorder="big") + bytes(frame_length - 4)


def test_read_mp3_stream_properties_accepts_consecutive_frames(
    tmp_path: Path,
) -> None:
    path = tmp_path / "voice.mp3"
    frame = _layer3_frame()
    path.write_bytes(frame + frame)

    properties = read_mp3_stream_properties(path)

    assert properties.sample_rate == 44_100
    assert properties.channels == 1


@pytest.mark.parametrize(
    ("version", "sample_rate"),
    [(2, 22_050), (0, 11_025)],
)
def test_read_mp3_stream_properties_accepts_lower_mpeg_versions(
    tmp_path: Path,
    version: int,
    sample_rate: int,
) -> None:
    path = tmp_path / f"mpeg-{version}.mp3"
    frame = _layer3_frame(version=version)
    path.write_bytes(frame + frame)

    properties = read_mp3_stream_properties(path)

    assert properties.sample_rate == sample_rate
    assert properties.channels == 1


def test_read_mp3_stream_properties_skips_id3v2_tag(tmp_path: Path) -> None:
    path = tmp_path / "tagged.mp3"
    tag_payload = b"provider=elevenbytes"
    tag_size = len(tag_payload)
    syncsafe_size = bytes(
        (
            (tag_size >> 21) & 0x7F,
            (tag_size >> 14) & 0x7F,
            (tag_size >> 7) & 0x7F,
            tag_size & 0x7F,
        )
    )
    frame = _layer3_frame(mono=False)
    path.write_bytes(b"ID3\x04\x00\x00" + syncsafe_size + tag_payload + frame + frame)

    properties = read_mp3_stream_properties(path)

    assert properties.sample_rate == 44_100
    assert properties.channels == 2


def test_read_mp3_stream_properties_rejects_single_false_header(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.mp3"
    path.write_bytes(_layer3_frame())

    with pytest.raises(AudioProbeError, match="consecutive valid"):
        read_mp3_stream_properties(path)


def test_read_mp3_stream_properties_rejects_invalid_id3_size(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid-tag.mp3"
    path.write_bytes(b"ID3\x04\x00\x00\x80\x00\x00\x00")

    with pytest.raises(AudioProbeError, match="invalid ID3v2 size"):
        read_mp3_stream_properties(path)
