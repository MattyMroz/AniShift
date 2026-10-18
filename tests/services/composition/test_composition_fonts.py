from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest

from anishift.services.composition.fonts import (
    attachment_font_names,
    font_attachments,
    font_embedding_warnings,
    font_names,
    used_font_files,
)

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

_FAMILY_ASS = _ASS.replace("Open Sans Semibold", "Arial").replace("Trebuchet MS", "Times New Roman")
_SYSTEM_FONTS: Final[Path] = Path("C:/Windows/Fonts")
_needs_fonts = pytest.mark.skipif(
    not all((_SYSTEM_FONTS / name).is_file() for name in ("arial.ttf", "times.ttf")),
    reason="Windows system fonts are not available",
)


def _subtitle(tmp_path: Path, text: str) -> Path:
    subtitle: Path = tmp_path / "episode.ass"
    subtitle.write_text(text, encoding="utf-8")
    return subtitle


def _file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_font_names_reads_styles_and_inline_overrides(tmp_path: Path) -> None:
    names = font_names(_subtitle(tmp_path, _ASS))

    assert "Open Sans Semibold" in names
    assert "Trebuchet MS" in names
    assert "Comic Sans MS" in names


def test_font_names_survives_unreadable_file(tmp_path: Path) -> None:
    assert font_names(tmp_path / "absent.ass") == frozenset()


def test_attachment_font_names_keeps_only_fonts() -> None:
    names = attachment_font_names(("OpenSans-Semibold.ttf", "cover.jpg", "Trebuchet.otf"))

    assert names == frozenset({"opensans-semibold", "trebuchet"})


@_needs_fonts
@pytest.mark.parametrize(
    ("files", "missing"),
    [
        ((), ("Arial", "Comic Sans MS", "Times New Roman")),
        ((("arial.ttf", "arial.ttf"),), ("Comic Sans MS", "Times New Roman")),
        ((("arial.ttf", "Times New Roman.ttf"),), ("Comic Sans MS", "Times New Roman")),
        ((("arial.ttf", "a.ttf"), ("times.ttf", "b.ttf")), ("Comic Sans MS",)),
    ],
)
def test_font_embedding_warnings_check_families_inside_the_font_files_not_their_names(
    tmp_path: Path,
    files: tuple[tuple[str, str], ...],
    missing: tuple[str, ...],
) -> None:
    fonts: list[Path] = []
    for system, name in files:
        fonts.append(Path(shutil.copyfile(_SYSTEM_FONTS / system, tmp_path / name)))

    warnings: tuple[str, ...] = font_embedding_warnings((_subtitle(tmp_path, _FAMILY_ASS),), fonts)

    assert warnings == tuple(f"font not embedded: {name}" for name in missing)


@_needs_fonts
def test_used_font_files_keep_only_files_whose_family_the_subtitles_name(tmp_path: Path) -> None:
    arial: Path = Path(shutil.copyfile(_SYSTEM_FONTS / "arial.ttf", tmp_path / "Officina - Bold.ttf"))
    times: Path = Path(shutil.copyfile(_SYSTEM_FONTS / "times.ttf", tmp_path / "Times.ttf"))
    plain: Path = tmp_path / "plain.srt"
    plain.write_text("1\n00:00:01,000 --> 00:00:02,000\nArial\n", encoding="utf-8")

    assert used_font_files((arial, times), (_subtitle(tmp_path, _FAMILY_ASS),)) == (arial, times)
    assert used_font_files((arial, times), (_subtitle(tmp_path, _ASS),)) == ()
    assert used_font_files((arial, times), (plain,)) == ()


def test_font_attachments_skip_content_the_container_has_and_rename_a_taken_name(tmp_path: Path) -> None:
    present: tuple[Path, ...] = (
        _file(tmp_path / "source" / "Officina - Bold.ttf", b"source bold"),
        _file(tmp_path / "source" / "Gandhi.otf", b"gandhi"),
    )
    same: Path = _file(tmp_path / "owner" / "Officina Copy.ttf", b"gandhi")
    renamed: Path = _file(tmp_path / "owner" / "officina - bold.TTF", b"owner bold")
    kept: Path = _file(tmp_path / "owner" / "Officina - Bold Italic.ttf", b"owner italic")
    repeated: Path = _file(tmp_path / "other" / "Repeat.ttf", b"owner italic")

    chosen = font_attachments((same, renamed, kept, repeated), present)

    assert chosen == ((renamed, "officina - bold (2).TTF"), (kept, "Officina - Bold Italic.ttf"))


def test_font_attachments_keep_every_new_file_under_its_own_name(tmp_path: Path) -> None:
    bold: Path = _file(tmp_path / "Officina - Bold.ttf", b"bold")
    italic: Path = _file(tmp_path / "Officina - Bold Italic.ttf", b"italic")

    assert font_attachments((bold, italic), ()) == ((bold, bold.name), (italic, italic.name))
