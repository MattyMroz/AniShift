from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.errors import ErrorCode
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.restyle import DialogueFont, restyle_dialogue
from anishift.services.subtitles.types import LayoutReport

_SYSTEM_FONTS: Final[Path] = Path("C:/Windows/Fonts")
_NEEDED: Final[tuple[str, ...]] = ("arial.ttf", "arialbd.ttf", "marlett.ttf", "times.ttf")
_needs_fonts = pytest.mark.skipif(
    not all((_SYSTEM_FONTS / name).is_file() for name in _NEEDED), reason="Windows system fonts are not available"
)


def _folder(target: Path, *names: str) -> Path:
    for name in names:
        shutil.copyfile(_SYSTEM_FONTS / name, target / name)
    return target


@_needs_fonts
@pytest.mark.integration
def test_dialogue_font_takes_the_windows_family_and_its_sibling_variants_with_polish_letters(tmp_path: Path) -> None:
    folder: Path = _folder(tmp_path, *_NEEDED)
    (folder / "notes.txt").write_text("not a font", encoding="utf-8")

    font: DialogueFont = DialogueFont.from_file(folder / "arial.ttf")

    assert font == DialogueFont("arial", (folder / "arial.ttf", folder / "arialbd.ttf"))


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
def test_restyle_dialogue_keeps_the_file_unchanged() -> None:
    subs: SSAFile = SSAFile()
    subs.events.append(SSAEvent(text="Hello"))

    assert restyle_dialogue(subs, ("spoken",), DialogueFont("arial", ()), LayoutReport()) is subs
