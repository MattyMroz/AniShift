from __future__ import annotations

from pathlib import Path

from anishift.services.composition.fonts import attachment_font_names, font_names, missing_fonts

_ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Open Sans Semibold,45
Style: Signs,Trebuchet MS,40

[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,{\\fnComic Sans MS}Hello
"""


def test_font_names_reads_styles_and_inline_overrides(tmp_path: Path) -> None:
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text(_ASS, encoding="utf-8")

    names = font_names(subtitle)

    assert "Open Sans Semibold" in names
    assert "Trebuchet MS" in names
    assert "Comic Sans MS" in names


def test_font_names_survives_unreadable_file(tmp_path: Path) -> None:
    assert font_names(tmp_path / "absent.ass") == frozenset()


def test_attachment_font_names_keeps_only_fonts() -> None:
    names = attachment_font_names(("OpenSans-Semibold.ttf", "cover.jpg", "Trebuchet.otf"))

    assert names == frozenset({"opensans-semibold", "trebuchet"})


def test_missing_fonts_reports_only_absent_ones(tmp_path: Path) -> None:
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text(_ASS, encoding="utf-8")

    missing = missing_fonts(subtitle, frozenset({"open sans semibold"}))

    assert "Trebuchet MS" in missing
    assert "Open Sans Semibold" not in missing
