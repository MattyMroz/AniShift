from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from anishift.platform.binaries import Binary, resolve_binary
from scripts.subtitle_quality import frames

if TYPE_CHECKING:
    from pathlib import Path

_SCRIPT = """[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,First line
Dialogue: 0,0:00:01.20,0:00:03.00,Default,,0,0,0,,Close to the first
Dialogue: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,{\\pos(10,10)}Sign
Dialogue: 0,0:00:07.00,0:00:08.00,Default,,0,0,0,,{\\p1}m 0 0 l 10 0 10 10
Dialogue: 0,0:00:08.00,0:00:09.00,Default,,0,0,0,,{\\i1}
Comment: 0,0:00:09.00,0:00:09.50,Default,,0,0,0,,Note
"""


def _pair(tmp_path: Path) -> Path:
    pair = tmp_path / "pair"
    pair.mkdir()
    (pair / "source.en.ass").write_text(_SCRIPT, encoding="utf-8")
    return pair


def test_moments_keep_visible_midpoints_at_least_half_a_second_apart(tmp_path: Path) -> None:
    pair = _pair(tmp_path)
    output = _SCRIPT.replace("0:00:05.00,0:00:06.00", "0:00:06.00,0:00:07.00")
    (pair / "output.pl.ass").write_text(output, encoding="utf-8")
    assert frames.moments(pair) == [2000, 5500, 6500]


def test_frame_filter_selects_the_first_frame_at_each_moment() -> None:
    assert frames.frame_filter([1500]) == "select='gte(t,1.500)*not(gte(prev_t,1.500))',scale='min(1920,iw)':-2"
    assert frames.frame_filter([1, 2, 3]).startswith("select='(gte(t,0.001)*not(gte(prev_t,0.001))+(gte(t,0.002)")


@pytest.mark.integration
def test_extract_writes_frames_named_by_their_time_at_subtitle_moments(tmp_path: Path) -> None:
    ffmpeg = resolve_binary(Binary.FFMPEG)
    if ffmpeg is None or resolve_binary(Binary.MKVMERGE) is None:
        pytest.skip("ffmpeg or mkvmerge is not installed")
    video = tmp_path / "video.mkv"
    subprocess.run(  # noqa: S603
        [str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:r=24:d=8", str(video)],
        check=True,
        timeout=60,
    )
    pair = _pair(tmp_path)
    (pair / "video.txt").write_text(str(video), encoding="utf-8")
    assert frames.extract(pair) == 2
    times = sorted(int(path.stem) for path in (pair / "frames").glob("*.jpg"))
    assert len(times) == 2
    assert 2000 <= times[0] < 2042
    assert 5500 <= times[1] < 5542
    assert not (pair / "fonts").exists()
    assert frames.extract(pair) == 2
