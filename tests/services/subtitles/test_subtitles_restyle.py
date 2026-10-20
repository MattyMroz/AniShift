from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.errors import ErrorCode
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.restyle import (
    DialogueFont,
    clone_source,
    restyle_dialogue,
    restyle_signs,
    with_family,
)
from anishift.services.subtitles.service import (
    inherit_split,
    layout_translated,
    load_subtitles,
    split_subtitles,
    write_translated,
)
from anishift.services.subtitles.types import FontSources, LayoutReport

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
def test_restyle_dialogue_numbers_the_clone_when_its_name_is_taken() -> None:
    subs: SSAFile = _subs()
    subs.styles["Default (dialog)"] = SSAStyle(fontname="Other")
    subs.styles["Default (dialog 2)"] = SSAStyle(fontname="Other")

    restyled: SSAFile = restyle_dialogue(subs, _DECISIONS, _FONT, LayoutReport())

    assert restyled.events[0].style == "Default (dialog 3)"
    assert restyled.styles["Default (dialog)"].fontname == "Other"
    assert restyled.styles["Default (dialog 3)"].fontname == _FAMILY
    assert clone_source("Default (dialog 3)") == "Default"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("Default (dialog)", "Default"),
        ("Default (dialog 2)", "Default"),
        ("Main - Top (dialog 12)", "Main - Top"),
        ("Default (dialog) (dialog)", "Default (dialog)"),
        ("Default", "Default"),
        ("Default (dialog 1)", "Default (dialog 1)"),
        ("Default (dialogue)", "Default (dialogue)"),
        ("(dialog)", "(dialog)"),
    ],
)
def test_clone_source_names_the_style_a_clone_was_made_from(name: str, source: str) -> None:
    assert clone_source(name) == source


@pytest.mark.integration
def test_a_translation_with_a_numbered_clone_inherits_the_source_decisions(tmp_path: Path) -> None:
    subs: SSAFile = _subs()
    subs.styles["Default (dialog)"] = SSAStyle(fontname="Typesetter")
    subs.events.append(SSAEvent(start=6000, end=7000, style="Default (dialog)", text="{\\an8}Sign"))
    source: Path = tmp_path / "source.ass"
    source.write_text(subs.to_string("ass"), encoding="utf-8")
    split = split_subtitles(load_subtitles(source), kind="ass", spoken_styles={"Default"})
    destination: Path = tmp_path / "out.pl.ass"

    write_translated(split, {0: "Cześć"}, destination, fonts=None, dialogue_font=_FONT)

    written: SSAFile = load_subtitles(destination)
    inherited = inherit_split(split, written)
    assert [event.style for event in written.events if event.type == "Dialogue"][-2:] == [
        "Default (dialog 2)",
        "Default (dialog)",
    ]
    assert inherited is not None
    assert inherited.decisions == split.decisions


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

    write_translated(split, {0: "Cześć"}, destination, fonts=None, dialogue_font=_FONT)

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


def _signs() -> SSAFile:
    subs: SSAFile = SSAFile()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080"})
    subs.styles["Default"] = SSAStyle(fontname="Gandhi Sans", fontsize=75.0)
    subs.styles["Sign"] = SSAStyle(fontname="Arial", fontsize=60.0)
    subs.styles["Typeset"] = SSAStyle(fontname="Grobold", fontsize=60.0)
    subs.events.extend(
        [
            SSAEvent(start=0, end=1000, style="Default", text="Hello there"),
            SSAEvent(start=0, end=1000, style="Sign", text=r"{\pos(960,100)\c&H0000FF&\frz5}ROOM 12"),
            SSAEvent(start=0, end=1000, style="Typeset", text=r"{\pos(960,300)}Shop"),
            SSAEvent(start=0, end=1000, style="Sign", text=r"{\pos(960,500)\clip(0,0,1920,600)}Exit"),
            SSAEvent(start=0, end=1000, style="Sign", text=r"{\pos(960,700)\fnTimes New Roman\blur2}Soft"),
            SSAEvent(start=0, end=1000, style="Sign", text=r"{\pos(960,900)}Bar"),
            SSAEvent(start=0, end=1000, style="Sign", layer=1, text=r"{\pos(960,900)\bord0}Bar"),
            SSAEvent(start=0, end=1000, style="Sign", text=r"{\pos(200,900)\fnTimes New Roman}Note"),
        ]
    )
    return subs


_SIGN_DECISIONS: Final[tuple[Decision, ...]] = ("spoken", *("displayed",) * 7)


@pytest.mark.unit
def test_restyle_signs_moves_plain_system_font_signs_to_a_clone_drawn_with_the_dialogue_font() -> None:
    restyled, clones = restyle_signs(_signs(), _SIGN_DECISIONS, _FONT, frozenset({"grobold"}))

    assert clones == {1: "Sign (dialog)", 7: "Sign (dialog)"}
    assert restyled.styles["Sign (dialog)"].fontname == _FAMILY
    assert restyled.styles["Sign"].fontname == "Arial"


@pytest.mark.unit
def test_restyle_signs_keeps_signs_with_attached_fonts_or_fitted_to_the_picture() -> None:
    _, clones = restyle_signs(_signs(), _SIGN_DECISIONS, _FONT, frozenset({"grobold"}))

    assert not {2, 3, 4, 5, 6} & clones.keys()


@pytest.mark.unit
def test_restyle_signs_reuses_the_dialogue_clone_of_the_sign_style() -> None:
    subs: SSAFile = _signs()
    subs.styles["Sign (dialog)"] = SSAStyle(fontname=_FAMILY)

    restyled, clones = restyle_signs(subs, _SIGN_DECISIONS, _FONT, frozenset())

    assert clones[1] == "Sign (dialog)"
    assert "Sign (dialog 2)" not in restyled.styles


@pytest.mark.unit
def test_with_family_replaces_named_font_overrides_and_keeps_resets() -> None:
    assert with_family(r"{\fnArial\pos(1,2)}A{\fn}B", "Officina") == r"{\fnOfficina\pos(1,2)}A{\fn}B"


@pytest.mark.integration
def test_layout_with_episode_fonts_draws_plain_signs_with_the_dialogue_font_and_keeps_their_look() -> None:
    split = split_subtitles(_signs(), kind="ass", spoken_styles={"Default"})

    laid_out = layout_translated(
        split,
        {1: "POKÓJ 12", 7: "Notatka"},
        fonts=FontSources(episode=(), system=()),
        dialogue_font=_FONT,
    )

    events: list[SSAEvent] = [event for event in laid_out.subs.events if event.type == "Dialogue"]
    assert [event.style for event in events[1:3]] == ["Sign (dialog)", "Typeset"]
    assert r"\pos(960,100)\c&H0000FF&\frz5" in events[1].text
    assert rf"\fn{_FAMILY}" in events[7].text
    assert laid_out.report.signs_restyled == 2


@pytest.mark.integration
def test_layout_without_a_dialogue_font_keeps_sign_fonts() -> None:
    split = split_subtitles(_signs(), kind="ass", spoken_styles={"Default"})

    laid_out = layout_translated(split, {1: "POKÓJ 12"}, fonts=FontSources(episode=(), system=()), dialogue_font=None)

    assert [event.style for event in laid_out.subs.events if event.type == "Dialogue"][1] == "Sign"
    assert laid_out.report.signs_restyled == 0
