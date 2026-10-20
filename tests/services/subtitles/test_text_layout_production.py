from __future__ import annotations

import json
import re
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from anishift.paths import default_workspace_dir
from anishift.services.fonts import FontIndex
from anishift.services.subtitles.geometry import Rect, RenderProfile, screen_rects
from anishift.services.subtitles.layout import Field, Layout, Scale, candidates, lay_out
from anishift.services.subtitles.restyle import DialogueFont
from anishift.services.subtitles.service import layout_translated, load_subtitles, split_subtitles
from anishift.services.subtitles.text import is_drawing, visible_text, visible_verses
from scripts.subtitle_quality.episode import SOURCE_NAME, pair_fonts
from scripts.subtitle_quality.layout_catalogue import CATALOGUE, CatalogueCase, faults, load

if TYPE_CHECKING:
    from pysubs2 import SSAEvent, SSAFile, SSAStyle

    from anishift.services.subtitles.types import FontSources, SubtitleSplit, TranslatedLayout

_QUALITY: Final[Path] = default_workspace_dir() / ".quality"
_HARD: Final[Path] = _QUALITY / "experiments" / "v4-hard" / "cases.json"
_OWNER_FONT: Final[Path] = (
    Path.home() / "Videos" / "mpv" / "portable_config" / "fonts" / "ITC Officina Sans Std PL - Bold.ttf"
)
_TOLERANCE: Final[float] = 0.07
_LINE_BREAK: Final[str] = chr(92) + "N"
_ENTRIES: Final[dict[str, dict[str, Any]]] = {
    entry["id"]: entry for entry in json.loads(CATALOGUE.read_text(encoding="utf-8"))["cases"]
}
_CORE: Final[list[CatalogueCase]] = [case for case in load() if "pair" in _ENTRIES[case.id]]
_CASES: Final[list[CatalogueCase]] = [
    case for case in _CORE if _ENTRIES[case.id]["field"]["kind"] == "dialogue" and case.id[0] in {"d", "q", "r", "t"}
]
_NARROWER_THAN_THE_SCREEN: Final[pytest.MarkDecorator] = pytest.mark.xfail(
    strict=True, reason="the source column is partly off screen, so two lines would shrink below the readable scale"
)
_SIGNS: Final[list[Any]] = [
    pytest.param(case, id=case.id, marks=[_NARROWER_THAN_THE_SCREEN] if case.id == "s13" else [])
    for case in _CORE
    if _ENTRIES[case.id]["field"]["kind"] == "sign" and case.id[0] == "s"
]
_SCENE: Final[list[str]] = [f"s{number:02}" for number in range(1, 31)]


@cache
def _split(pair: str) -> SubtitleSplit:
    return split_subtitles(load_subtitles(_QUALITY / pair / SOURCE_NAME), kind="ass")


@cache
def _hard() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in json.loads(_HARD.read_text(encoding="utf-8"))}


def _laid_out(pair: str, event: int, text: str, decision: str) -> TranslatedLayout:
    if not (_QUALITY / pair / SOURCE_NAME).is_file() or not _OWNER_FONT.is_file():
        pytest.skip("quality pair or the owner's dialogue font is not available")
    split: SubtitleSplit = _split(pair)
    if split.decisions[event] != decision:
        pytest.skip(f"the catalogue event is not {decision} in its pair")
    return layout_translated(
        split,
        {event: text},
        fonts=pair_fonts(_QUALITY / pair),
        dialogue_font=DialogueFont.from_file(_OWNER_FONT),
    )


def _dialogue(subs: SSAFile) -> list[SSAEvent]:
    return [event for event in subs.events if event.type == "Dialogue"]


def _scale(subs: SSAFile, event: SSAEvent) -> Scale:
    found: re.Match[str] | None = re.match(r"\{\\fscx(-?[\d.]+)\\fscy(-?[\d.]+)", event.text)
    if found is None:
        return Scale()
    style: SSAStyle = subs.styles[event.style]
    return Scale(round(float(found[1]) / style.scalex, 2), round(float(found[2]) / style.scaley, 2))


def _cuts(lines: tuple[str, ...]) -> frozenset[int]:
    cuts: list[int] = []
    count: int = -1
    for line in lines[:-1]:
        count += len(line.split(" "))
        cuts.append(count)
    return frozenset(cuts)


def _positioned(case: CatalogueCase) -> str:
    words: list[str] = case.text.split(" ")
    return "".join(
        word + (_LINE_BREAK if index in case.field.breaks else " ") for index, word in enumerate(words)
    ).strip()


def _loss(rects: tuple[Rect, ...], width: float, height: float) -> float:
    return max(
        (max(0.0, -r.left) + max(0.0, r.right - width) + max(0.0, -r.top) + max(0.0, r.bottom - height) for r in rects),
        default=0.0,
    )


def _overlap(rects: tuple[Rect, ...], others: tuple[Rect, ...]) -> float:
    return sum(
        max(0.0, min(a.right, b.right) - max(a.left, b.left)) * max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
        for a in rects
        for b in others
    )


def _profile(subs: SSAFile, pair: str) -> RenderProfile:
    fonts: FontSources = pair_fonts(_QUALITY / pair)
    owner: tuple[Path, ...] = DialogueFont.from_file(_OWNER_FONT).files
    return RenderProfile.from_subs(subs, FontIndex.build((*fonts.episode, *owner), fonts.system))


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("case", _CASES, ids=[case.id for case in _CASES])
def test_dialogue_case_gets_an_acceptable_layout_through_the_production_writer(case: CatalogueCase) -> None:
    entry: dict[str, Any] = _ENTRIES[case.id]
    laid_out: TranslatedLayout = _laid_out(entry["pair"], entry["event"], case.text, "spoken")
    lines: tuple[str, ...] = visible_verses(_dialogue(laid_out.subs)[entry["event"]].text)
    found: list[Layout] = candidates(case.text, case.field, case.measure)
    chosen: list[Layout] = [layout for layout in found if layout.lines == lines]

    assert chosen, " / ".join(lines)
    assert faults(case, chosen[0], found) == [], " / ".join(lines)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("case", _SIGNS)
def test_sign_case_gets_an_acceptable_layout_through_the_production_writer(case: CatalogueCase) -> None:
    entry: dict[str, Any] = _ENTRIES[case.id]
    laid_out: TranslatedLayout = _laid_out(entry["pair"], entry["event"], _positioned(case), "displayed")
    event: SSAEvent = _dialogue(laid_out.subs)[entry["event"]]
    lines: tuple[str, ...] = tuple(verse for verse in visible_verses(event.text) if verse)
    field: Field = replace(case.field, breaks=case.field.breaks | _cuts(lines))
    layout: Layout = replace(lay_out(case.text, field, case.measure), scale=_scale(laid_out.subs, event))

    assert layout.lines == lines, " / ".join(lines)
    assert faults(case, layout, [layout]) == [], f"{' / '.join(lines)} at {layout.scale}"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("case_id", _SCENE)
def test_sign_case_leaves_the_screen_and_covers_other_text_no_more_than_its_original(case_id: str) -> None:
    if not _HARD.is_file():
        pytest.skip("hard case set is not available")
    hard: dict[str, Any] = _hard()[case_id]
    index: int = hard["event_index"]
    laid_out: TranslatedLayout = _laid_out(hard["pair"], index, visible_text(hard["pl_baseline"]), "displayed")
    source: list[SSAEvent] = _dialogue(_split(hard["pair"]).subs)
    output: list[SSAEvent] = _dialogue(laid_out.subs)
    profile: RenderProfile = _profile(laid_out.subs, hard["pair"])
    before: tuple[Rect, ...] = screen_rects(source[index], source[index].text, profile)
    after: tuple[Rect, ...] = screen_rects(output[index], output[index].text, profile)
    near: tuple[Rect, ...] = tuple(
        rect
        for other, event in enumerate(output)
        if other != index
        and not is_drawing(event.text)
        and event.start < output[index].end
        and output[index].start < event.end
        and visible_text(source[other].text) != visible_text(source[index].text)
        for rect in screen_rects(event, event.text, profile)
    )
    width: float = max((rect.right - rect.left for rect in after), default=0.0)
    height: float = max((rect.bottom - rect.top for rect in after), default=0.0)
    screen: float = _loss(after, profile.play_res_x, profile.play_res_y) - _loss(
        before, profile.play_res_x, profile.play_res_y
    )
    covered: float = _overlap(after, near) - _overlap(before, near)

    assert screen <= 1 + _TOLERANCE * (width + height) or laid_out.report.signs_fallback_screen
    assert covered <= 1 + _TOLERANCE * width * height or laid_out.report.signs_fallback_collision
