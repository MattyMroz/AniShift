from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.errors import ErrorCode
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.subtitles.restyle import DIALOGUE_CLONE_SUFFIX, DialogueFont, restyle_dialogue
from anishift.services.subtitles.service import load_subtitles, split_subtitles, write_translated
from anishift.services.subtitles.types import LayoutReport

if TYPE_CHECKING:
    from anishift.services.subtitles.types import Decision

_SYSTEM_FONTS: Final[Path] = Path("C:/Windows/Fonts")
_NEEDED: Final[tuple[str, ...]] = ("arial.ttf", "arialbd.ttf", "marlett.ttf", "times.ttf")
_needs_fonts = pytest.mark.skipif(
    not all((_SYSTEM_FONTS / name).is_file() for name in _NEEDED), reason="Windows system fonts are not available"
)
_OWNER_FONT: Final[Path] = (
    Path.home() / "Videos" / "mpv" / "portable_config" / "fonts" / "ITC Officina Sans Std PL - Bold.ttf"
)
_FAMILY: Final[str] = "ITC Officina Sans Std PL Book"
_FONT: Final[DialogueFont] = DialogueFont(_FAMILY, ())
_DECISIONS: Final[tuple[Decision, ...]] = ("spoken", "displayed", "spoken", "displayed", "spoken")


def _folder(target: Path, *names: str) -> Path:
    for name in names:
        shutil.copyfile(_SYSTEM_FONTS / name, target / name)
    return target


def _subs() -> SSAFile:
    subs: SSAFile = SSAFile()
    subs.styles["Default"] = SSAStyle(fontname="Gandhi Sans", fontsize=75.0, bold=True, outline=3.0)
    subs.styles["Sign"] = SSAStyle(fontname="Grobold", fontsize=60.0)
    subs.events.extend(
        [
            SSAEvent(start=0, end=1000, style="Default", text="{\\i1}Hello{\\i0} there"),
            SSAEvent(start=1000, end=2000, style="Default", text="{\\pos(960,100)}ROOM 12"),
            SSAEvent(start=2000, end=3000, style="Default", text="Wait{\\rSign} sign {\\rDefault}back{\\r} done"),
            SSAEvent(start=3000, end=4000, style="Sign", text="Shop"),
            SSAEvent(start=4000, end=5000, style="Default", text="Note", type="Comment"),
            SSAEvent(start=5000, end=6000, style="Default", text="Bye"),
        ]
    )
    return subs


@_needs_fonts
@pytest.mark.integration
def test_dialogue_font_takes_the_windows_family_as_written_and_its_sibling_variants(tmp_path: Path) -> None:
    folder: Path = _folder(tmp_path, *_NEEDED)
    (folder / "notes.txt").write_text("not a font", encoding="utf-8")

    font: DialogueFont = DialogueFont.from_file(folder / "arial.ttf")

    assert font == DialogueFont("Arial", (folder / "arial.ttf", folder / "arialbd.ttf"))


@pytest.mark.skipif(not _OWNER_FONT.is_file(), reason="the owner's dialogue font is not available")
@pytest.mark.integration
def test_dialogue_font_of_the_owner_keeps_the_family_spelling_and_finds_the_bold_italic_variant() -> None:
    font: DialogueFont = DialogueFont.from_file(_OWNER_FONT)

    assert font.family == _FAMILY
    assert [path.name for path in font.files] == [
        "ITC Officina Sans Std PL - Bold.ttf",
        "ITC Officina Sans Std PL - Bold Italic.ttf",
    ]


@_needs_fonts
@pytest.mark.integration
def test_dialogue_font_without_polish_letters_is_rejected(tmp_path: Path) -> None:
    folder: Path = _folder(tmp_path, "marlett.ttf")

    with pytest.raises(SubtitleError) as error:
        DialogueFont.from_file(folder / "marlett.ttf")

    assert error.value.context.code is ErrorCode.CONFIG_INVALID


@pytest.mark.integration
def test_dialogue_font_file_that_is_missing_or_not_a_font_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "notes.ttf").write_text("not a font", encoding="utf-8")

    with pytest.raises(SubtitleError) as missing:
        DialogueFont.from_file(tmp_path / "gone.ttf")
    with pytest.raises(SubtitleError) as broken:
        DialogueFont.from_file(tmp_path / "notes.ttf")

    assert missing.value.context.code is ErrorCode.FILE_NOT_FOUND
    assert broken.value.context.code is ErrorCode.CONFIG_INVALID


@pytest.mark.unit
def test_restyle_dialogue_clones_a_mostly_spoken_style_with_the_family_and_keeps_its_other_fields() -> None:
    report: LayoutReport = LayoutReport()

    restyled: SSAFile = restyle_dialogue(_subs(), _DECISIONS, _FONT, report)

    clone: SSAStyle = restyled.styles["Default (dialog)"]
    original: SSAStyle = restyled.styles["Default"]
    assert list(restyled.styles) == ["Default", "Default (dialog)", "Sign"]
    assert clone.fontname == _FAMILY
    assert original.fontname == "Gandhi Sans"
    assert {**clone.as_dict(), "fontname": original.fontname} == original.as_dict()
    assert report.restyled_styles == 1


@pytest.mark.unit
def test_restyle_dialogue_moves_spoken_lines_and_points_named_resets_of_cloned_styles_at_the_clone() -> None:
    restyled: SSAFile = restyle_dialogue(_subs(), _DECISIONS, _FONT, LayoutReport())

    assert [(event.style, event.text) for event in restyled.events] == [
        ("Default (dialog)", "{\\i1}Hello{\\i0} there"),
        ("Default", "{\\pos(960,100)}ROOM 12"),
        ("Default (dialog)", "Wait{\\rSign} sign {\\rDefault (dialog)}back{\\r} done"),
        ("Sign", "Shop"),
        ("Default", "Note"),
        ("Default (dialog)", "Bye"),
    ]


@pytest.mark.unit
def test_restyle_dialogue_keeps_displayed_lines_byte_identical_and_leaves_the_source_untouched() -> None:
    subs: SSAFile = _subs()
    before: str = subs.to_string("ass")

    restyled: SSAFile = restyle_dialogue(subs, _DECISIONS, _FONT, LayoutReport())

    original_lines: list[str] = before.splitlines()
    restyled_lines: list[str] = restyled.to_string("ass").splitlines()
    for text in ("ROOM 12", "Shop", "Note"):
        assert [line for line in restyled_lines if text in line] == [line for line in original_lines if text in line]
    assert restyled.events[1] is subs.events[1]
    assert subs.to_string("ass") == before


@pytest.mark.unit
def test_restyle_dialogue_clones_only_the_mostly_spoken_style() -> None:
    decisions: tuple[Decision, ...] = ("displayed", "displayed", "spoken", "spoken", "displayed")
    report: LayoutReport = LayoutReport()

    restyled: SSAFile = restyle_dialogue(_subs(), decisions, _FONT, report)

    assert list(restyled.styles) == ["Default", "Sign", "Sign (dialog)"]
    assert [event.style for event in restyled.events] == [
        "Default",
        "Default",
        "Default",
        "Sign (dialog)",
        "Default",
        "Default",
    ]
    assert restyled.events[2].text == "Wait{\\rSign} sign {\\rDefault}back{\\r} done"
    assert report.restyled_styles == 1


@pytest.mark.unit
def test_restyle_dialogue_adds_another_suffix_when_the_clone_name_is_taken() -> None:
    subs: SSAFile = _subs()
    subs.styles["Default" + DIALOGUE_CLONE_SUFFIX] = SSAStyle(fontname="Other")

    restyled: SSAFile = restyle_dialogue(subs, _DECISIONS, _FONT, LayoutReport())

    assert restyled.events[0].style == "Default (dialog) (dialog)"
    assert restyled.styles["Default (dialog)"].fontname == "Other"
    assert restyled.styles["Default (dialog) (dialog)"].fontname == _FAMILY


@pytest.mark.unit
def test_restyle_dialogue_without_spoken_lines_returns_the_file_itself() -> None:
    subs: SSAFile = _subs()
    report: LayoutReport = LayoutReport()

    assert restyle_dialogue(subs, ("displayed",) * 5, _FONT, report) is subs
    assert report.restyled_styles == 0


@pytest.mark.integration
def test_write_translated_with_the_dialogue_font_writes_the_clone_and_keeps_untranslated_signs_identical(
    tmp_path: Path,
) -> None:
    source: Path = tmp_path / "source.ass"
    source.write_text(_subs().to_string("ass"), encoding="utf-8")
    split = split_subtitles(load_subtitles(source), kind="ass", spoken_styles={"Default"})
    destination: Path = tmp_path / "out.pl.ass"

    write_translated(split, {0: "Cześć"}, destination, fonts=None, limits=LayoutLimits(), dialogue_font=_FONT)

    written: SSAFile = load_subtitles(destination)
    assert written.styles["Default (dialog)"].fontname == _FAMILY
    assert [event.style for event in written.events] == [
        "Default (dialog)",
        "Default (dialog)",
        "Default (dialog)",
        "Sign",
        "Default",
        "Default (dialog)",
    ]
    sign: str = next(line for line in source.read_text(encoding="utf-8").splitlines() if "Shop" in line)
    assert sign in destination.read_text(encoding="utf-8").splitlines()
