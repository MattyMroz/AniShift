from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.fonts import system_font_paths
from scripts.subtitle_quality.episode import FONTS_NAME, OUTPUT_NAME, SOURCE_NAME, analyse, pair_fonts

if TYPE_CHECKING:
    from pathlib import Path

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, \
Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, \
MarginV, Encoding
Style: Default,Arial,26,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,20,1
Style: Sign,Arial,22,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,20,20,20,1
Style: Sign Odd,Missing Font,22,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _write(path: Path, texts: tuple[str, str, str]) -> None:
    dialogue, sign, odd = texts
    events = [
        *(f"Dialogue: 0,0:00:{second:02d}.00,0:00:{second + 1:02d}.00,Default,,0,0,0,,{dialogue}" for second in (1, 3)),
        *(f"Dialogue: 0,0:00:{second:02d}.00,0:00:{second + 1:02d}.00,Sign,,0,0,0,,{sign}" for second in (5, 7)),
        *(f"Dialogue: 0,0:00:{second:02d}.00,0:00:{second + 1:02d}.00,Sign Odd,,0,0,0,,{odd}" for second in (9, 11)),
    ]
    path.write_text(_HEADER + "\n".join(events) + "\n", encoding="utf-8")


@pytest.mark.unit
def test_pair_fonts_takes_the_files_of_the_fonts_folder_and_the_system_fonts(tmp_path: Path) -> None:
    (tmp_path / FONTS_NAME).mkdir()
    (tmp_path / FONTS_NAME / "b.ttf").write_bytes(b"")
    (tmp_path / FONTS_NAME / "a.otf").write_bytes(b"")

    fonts = pair_fonts(tmp_path)

    assert fonts.episode == (tmp_path / FONTS_NAME / "a.otf", tmp_path / FONTS_NAME / "b.ttf")
    assert fonts.system == system_font_paths()
    assert pair_fonts(tmp_path / "missing").episode == ()


@pytest.mark.integration
def test_analyse_flags_signs_whose_glyphs_a_substitute_face_draws(tmp_path: Path) -> None:
    if resolve_binary(Binary.FFMPEG) is None:
        pytest.skip("ffmpeg is not installed")
    if not any(path.name.casefold() == "arial.ttf" for path in system_font_paths()):
        pytest.skip("system Arial is not available")
    directory = tmp_path / "episode"
    directory.mkdir()
    _write(directory / SOURCE_NAME, ("Hello there.", r"{\pos(320,100)}Station", r"{\pos(320,200)}Exit"))
    _write(directory / OUTPUT_NAME, ("Cześć.", r"{\pos(320,100)}Stacja", r"{\pos(320,200)}Wyjście"))

    result = analyse(directory, tmp_path / "cache", render=True)

    assert {finding.sign.style: finding.sign.font_fallback for finding in result.signs} == {
        "Sign": False,
        "Sign Odd": True,
    }
