from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from anishift.paths import default_workspace_dir
from anishift.services.subtitles.layout import Layout, LayoutLimits, candidates
from anishift.services.subtitles.restyle import DialogueFont
from anishift.services.subtitles.service import layout_translated, load_subtitles, split_subtitles
from anishift.services.subtitles.text import visible_verses
from scripts.subtitle_quality.episode import SOURCE_NAME, pair_fonts
from scripts.subtitle_quality.layout_catalogue import CATALOGUE, CatalogueCase, faults, load

if TYPE_CHECKING:
    from anishift.services.subtitles.types import SubtitleSplit, TranslatedLayout

_QUALITY: Final[Path] = default_workspace_dir() / ".quality"
_OWNER_FONT: Final[Path] = (
    Path.home() / "Videos" / "mpv" / "portable_config" / "fonts" / "ITC Officina Sans Std PL - Bold.ttf"
)
_ENTRIES: Final[dict[str, dict[str, Any]]] = {
    entry["id"]: entry for entry in json.loads(CATALOGUE.read_text(encoding="utf-8"))["cases"]
}
_CASES: Final[list[CatalogueCase]] = [
    case
    for case in load()
    if _ENTRIES[case.id]["field"]["kind"] == "dialogue"
    and "pair" in _ENTRIES[case.id]
    and case.id[0] in {"d", "q", "r", "t"}
]


@cache
def _split(pair: str) -> SubtitleSplit:
    return split_subtitles(load_subtitles(_QUALITY / pair / SOURCE_NAME), kind="ass")


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("case", _CASES, ids=[case.id for case in _CASES])
def test_dialogue_case_gets_an_acceptable_layout_through_the_production_writer(case: CatalogueCase) -> None:
    entry: dict[str, Any] = _ENTRIES[case.id]
    if not (_QUALITY / entry["pair"] / SOURCE_NAME).is_file() or not _OWNER_FONT.is_file():
        pytest.skip("quality pair or the owner's dialogue font is not available")
    split: SubtitleSplit = _split(entry["pair"])
    if split.decisions[entry["event"]] != "spoken":
        pytest.skip("the catalogue event is not read aloud in its pair")

    laid_out: TranslatedLayout = layout_translated(
        split,
        {entry["event"]: case.text},
        fonts=pair_fonts(_QUALITY / entry["pair"]),
        limits=LayoutLimits(),
        dialogue_font=DialogueFont.from_file(_OWNER_FONT),
    )
    event_text: str = [event for event in laid_out.subs.events if event.type == "Dialogue"][entry["event"]].text
    lines: tuple[str, ...] = visible_verses(event_text)
    found: list[Layout] = candidates(case.text, case.field, case.measure)
    chosen: list[Layout] = [layout for layout in found if layout.lines == lines]

    assert chosen, " / ".join(lines)
    assert faults(case, chosen[0], found) == [], " / ".join(lines)
