from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.geometry import RenderProfile
from anishift.services.subtitles.layout import Flag, LayoutLimits
from anishift.services.subtitles.linebreak import DialogueLayout, layout_dialogue
from anishift.services.subtitles.service import layout_translated, load_subtitles, split_subtitles, write_translated
from anishift.services.subtitles.text import visible_text

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.subtitles.types import SubtitleKind, SubtitleSplit, TranslatedLayout

_TRANSLATION = "Wczoraj widziałem ogromnego smoka daleko stąd, a potem jeszcze dwa inne smoki."
_LAID_OUT = r"Wczoraj widziałem ogromnego smoka daleko\Nstąd, a potem jeszcze dwa inne smoki."


def _profile(*, margin: int = 0, size: float = 50.0) -> RenderProfile:
    subs: SSAFile = SSAFile()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080", "WrapStyle": "0"})
    subs.styles["Default"] = SSAStyle(fontname="Arial", fontsize=size, marginl=margin, marginr=margin)
    return RenderProfile.from_subs(subs, None)


@pytest.mark.unit
def test_layout_dialogue_breaks_a_new_translation_and_keeps_the_event_tags() -> None:
    event: SSAEvent = SSAEvent(text=r"{\an8}Yesterday I saw a dragon")

    layout: DialogueLayout = layout_dialogue(event, _TRANSLATION, None)

    assert layout == DialogueLayout("{\\an8}" + _LAID_OUT, frozenset())


@pytest.mark.unit
def test_layout_dialogue_reflows_unchanged_text_without_moving_tags() -> None:
    event: SSAEvent = SSAEvent(text=_TRANSLATION.replace("widziałem", r"{\i1}widziałem{\i0}"))

    layout: DialogueLayout = layout_dialogue(event, _TRANSLATION, None)

    assert layout.text == _LAID_OUT.replace("widziałem", r"{\i1}widziałem{\i0}")


@pytest.mark.unit
def test_layout_dialogue_restores_span_markers_into_the_new_lines() -> None:
    event: SSAEvent = SSAEvent(text=r"Why are you after {\i1}me{\i0}?!")
    translation: str = "Czemu uwziąłeś się akurat na <s1>mnie</s1>, skoro nigdy nic złego ci nie zrobiłem?!"

    layout: DialogueLayout = layout_dialogue(event, translation, None)

    assert layout.text == r"Czemu uwziąłeś się akurat na {\i1}mnie{\i0},\Nskoro nigdy nic złego ci nie zrobiłem?!"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("Krótkie zdanie.", ("Krótkie zdanie.",)),
        (
            "- Idziesz już do domu? - Za chwilę, tylko się spakuję.",
            ("- Idziesz już do domu?", "- Za chwilę, tylko się spakuję."),
        ),
        (
            "Wczoraj wieczorem Jan\u00a0Kowalski przyniósł nam wszystkim mnóstwo pysznego jedzenia.",
            ("Wczoraj wieczorem Jan\u00a0Kowalski przyniósł", "nam wszystkim mnóstwo pysznego jedzenia."),
        ),
    ],
)
def test_layout_dialogue_without_a_profile_measures_graphemes(text: str, lines: tuple[str, ...]) -> None:
    layout: DialogueLayout = layout_dialogue(SSAEvent(text="x"), text, None)

    assert tuple(layout.text.split("\\N")) == lines


@pytest.mark.unit
def test_layout_dialogue_never_cuts_at_a_hard_space_of_the_event() -> None:
    event: SSAEvent = SSAEvent(
        text=r"Wczoraj wieczorem Jan\hKowalski przyniósł nam wszystkim mnóstwo pysznego jedzenia."
    )

    layout: DialogueLayout = layout_dialogue(event, visible_text(event.text, preserve_hard_spaces=True), _profile())

    assert "Jan\\hKowalski" in layout.text
    assert layout.text.count("\\N") == 1


@pytest.mark.unit
def test_layout_dialogue_stops_libass_wrapping_lines_wider_than_the_style_margins() -> None:
    layout: DialogueLayout = layout_dialogue(SSAEvent(text="x"), _TRANSLATION, _profile(margin=700, size=70.0))

    assert layout.text.startswith("{\\q2}")
    assert layout.approximate


@pytest.mark.unit
def test_layout_dialogue_fits_the_safe_area_from_the_event_anchor() -> None:
    text: str = "Wróciłem do domu bardzo późno, bo autobus się spóźnił."
    centred: DialogueLayout = layout_dialogue(SSAEvent(text="x"), text, _profile(size=40.0))
    near_edge: DialogueLayout = layout_dialogue(SSAEvent(text=r"{\an1\pos(1100,1000)}x"), text, _profile(size=40.0))

    assert centred.text.count("\\N") == 0
    assert near_edge.text.count("\\N") == 1
    assert Flag.OUTSIDE not in near_edge.flags


@pytest.mark.unit
@pytest.mark.parametrize("text", [r"Ja {\b1}naprawdę{\b0} cię kocham.", r"To jest {\fs70}naprawdę{\fs50} ważne."])
def test_layout_dialogue_keeps_a_short_line_with_an_emphasised_word_whole(text: str) -> None:
    layout: DialogueLayout = layout_dialogue(SSAEvent(text=text), visible_text(text), _profile())

    assert layout.text == text


@pytest.mark.unit
def test_layout_dialogue_stops_wrapping_after_the_event_own_wrap_style() -> None:
    event: SSAEvent = SSAEvent(text="{\\q1}" + _TRANSLATION)

    layout: DialogueLayout = layout_dialogue(event, _TRANSLATION, _profile(margin=700, size=70.0))

    assert layout.text.startswith("{\\q1}{\\q2}")


@pytest.mark.unit
def test_layout_dialogue_reports_a_translation_it_cannot_measure_with_its_tags() -> None:
    event: SSAEvent = SSAEvent(text=r"Jan \h Kowalski przyszedł")

    layout: DialogueLayout = layout_dialogue(event, visible_text(event.text, preserve_hard_spaces=True), _profile())

    assert layout.untagged


@pytest.mark.unit
def test_layout_translated_keeps_a_dialogue_line_equal_to_the_source_byte_for_byte() -> None:
    subs: SSAFile = SSAFile()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080"})
    subs.styles["Default"] = SSAStyle(fontname="Arial", fontsize=70.0, marginl=700, marginr=700)
    source: str = r"Yesterday I saw a huge dragon far from here,\Nand then two more dragons."
    subs.events.append(SSAEvent(start=0, end=1000, text=source))
    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Default"})

    laid_out: TranslatedLayout = layout_translated(
        split, {0: visible_text(source)}, fonts=None, limits=LayoutLimits(), dialogue_font=None
    )

    assert laid_out.subs.events[0].text == source


def _write(tmp_path: Path, subs: SSAFile, texts: dict[int, str], name: str, kind: SubtitleKind) -> SSAFile:
    split: SubtitleSplit = split_subtitles(subs, kind=kind, spoken_styles=None if kind == "srt" else {"Default"})
    written: Path | None = write_translated(
        split, texts, tmp_path / name, fonts=None, limits=LayoutLimits(), dialogue_font=None
    )
    assert written is not None
    return load_subtitles(written)


@pytest.mark.integration
def test_translated_ass_keeps_italics_hard_spaces_speakers_and_marked_words(tmp_path: Path) -> None:
    subs: SSAFile = SSAFile()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080"})
    subs.styles["Default"] = SSAStyle(fontname="Arial", fontsize=60.0, marginl=40, marginr=40)
    subs.events.extend(
        [
            SSAEvent(start=0, end=1000, text=r"I really {\i1}did{\i0} knock on the door yesterday evening, twice."),
            SSAEvent(start=1000, end=2000, text=r"Mr.\hSmith brought us loads of tasty food again yesterday evening."),
            SSAEvent(start=2000, end=3000, text=r"- Going home? - In a minute."),
        ]
    )
    texts: dict[int, str] = {
        0: "Naprawdę <s1>pukałem</s1> wczoraj wieczorem do tych drzwi, i to dwa razy, ale nikt nie otworzył.",
        1: "Pan Smith znowu przyniósł nam wczoraj wieczorem mnóstwo pysznego jedzenia.",
        2: "- Idziesz już do domu? - Za chwilę.",
    }

    events: list[SSAEvent] = _write(tmp_path, subs, texts, "out.pl.ass", "ass").events

    assert events[0].text.count("\\N") == 1
    assert "{\\i1}pukałem{\\i0}" in events[0].text
    assert "Pan\\hSmith" in events[1].text
    assert events[1].text.count("\\N") == 1
    assert events[2].text == "- Idziesz już do domu?\\N- Za chwilę."


@pytest.mark.integration
def test_translated_srt_breaks_dialogue_by_graphemes_with_a_new_line(tmp_path: Path) -> None:
    subs: SSAFile = SSAFile()
    subs.events.append(SSAEvent(start=0, end=1000, text="I saw a dragon"))

    events: list[SSAEvent] = _write(tmp_path, subs, {0: _TRANSLATION}, "out.pl.srt", "srt").events
    body: str = (tmp_path / "out.pl.srt").read_text(encoding="utf-8")

    assert events[0].text == _LAID_OUT
    assert "daleko\nstąd," in body
