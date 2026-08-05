from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from anishift.pipeline.compose_only import extracted_polish_outcome, product_outcome
from anishift.platform.binaries import Binary, resolve_binary

FFMPEG = resolve_binary(Binary.FFMPEG)
MKVMERGE = resolve_binary(Binary.MKVMERGE)

_ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,0,2,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.20,0:00:01.50,Default,,0,0,0,,Zażółć gęślą jaźń
"""


def _mkv_with_polish_subtitles(tmp_path: Path) -> Path:
    raw = tmp_path / "raw.mkv"
    subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10:duration=2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(raw),
        ],
        check=True,
        capture_output=True,
    )
    subtitle = tmp_path / "subs.ass"
    subtitle.write_text(_ASS, encoding="utf-8")
    source = tmp_path / "Episode.mkv"
    subprocess.run(  # noqa: S603
        [
            str(MKVMERGE),
            "--output",
            str(source),
            str(raw),
            "--language",
            "0:pol",
            str(subtitle),
        ],
        check=True,
        capture_output=True,
    )
    raw.unlink()
    subtitle.unlink()
    return source


def test_product_outcome_collects_products_from_an_earlier_run(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"x")
    (tmp_path / "Episode.pl.ass").write_text("", encoding="utf-8")
    (tmp_path / "Episode.displayed.pl.ass").write_text("", encoding="utf-8")
    (tmp_path / "Episode.eac3").write_bytes(b"a")

    outcome = product_outcome(source, workspace_root=tmp_path)

    assert outcome is not None
    assert outcome.translated_path == tmp_path / "Episode.pl.ass"
    assert outcome.displayed_path == tmp_path / "Episode.displayed.pl.ass"
    assert outcome.mixed_audio_path == tmp_path / "Episode.eac3"


def test_product_outcome_accepts_srt_products(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"x")
    (tmp_path / "Episode.pl.srt").write_text("", encoding="utf-8")

    outcome = product_outcome(source, workspace_root=tmp_path)

    assert outcome is not None
    assert outcome.translated_path == tmp_path / "Episode.pl.srt"


def test_product_outcome_is_none_without_any_product(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"x")

    assert product_outcome(source, workspace_root=tmp_path) is None


@pytest.mark.skipif(MKVMERGE is None or FFMPEG is None, reason="bundled tools are unavailable")
def test_polish_source_without_any_previous_run_yields_subtitles(tmp_path: Path) -> None:
    source = _mkv_with_polish_subtitles(tmp_path)

    outcome = extracted_polish_outcome(source, workspace_root=tmp_path)

    assert outcome is not None
    assert outcome.already_polish is True
    assert outcome.translated_path is not None
    assert outcome.translated_path.stat().st_size > 0


@pytest.mark.skipif(MKVMERGE is None or FFMPEG is None, reason="bundled tools are unavailable")
def test_source_without_polish_subtitles_yields_nothing(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10:duration=1",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    assert extracted_polish_outcome(source, workspace_root=tmp_path) is None
