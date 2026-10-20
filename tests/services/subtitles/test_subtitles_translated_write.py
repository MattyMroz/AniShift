from __future__ import annotations

import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from conftest import MM_AVH_TEMP
from loguru import logger as loguru_logger
from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.classifier import Category, StyleVerdict
from anishift.services.subtitles.service import (
    layout_translated,
    load_subtitles,
    reflow_polish_dialogue,
    split_subtitles,
    write_displayed,
    write_full,
    write_spoken,
    write_translated,
)
from anishift.services.subtitles.text import visible_text
from anishift.services.subtitles.types import LayoutReport, SubtitleKind, SubtitleSplit, TranslatedLayout

if TYPE_CHECKING:
    from loguru import Record

_REAL_ASS_NAME = "006___shisha__Genjitsu_no_Yohane_-_Sunshine_in_the_Mirror_-_01__1080p_.mkv.ass"
_REAL_ASS = MM_AVH_TEMP / "dataset_ass" / _REAL_ASS_NAME
_RE_TAGS = re.compile(r"\{[^}]*\}")
_RE_SCALE = re.compile(r"\\fsc[xy]?(?:-?[0-9]*\.?[0-9]+)?")
_LONG_TRANSLATION = "Pierwszy wers jest tutaj całkiem długi, a drugi wers też ma sporo słów."
_LONG_TRANSLATION_LINES = "Pierwszy wers jest tutaj całkiem długi,\na drugi wers też ma sporo słów."


def _tags_without_scale(text: str) -> list[str]:
    blocks: list[str] = [_RE_SCALE.sub("", block) for block in _RE_TAGS.findall(text)]
    return [block for block in blocks if block != "{}"]


def _ass_with_both_streams() -> SSAFile:
    subs = SSAFile()
    subs.info["Title"] = "Round trip"
    subs.styles["Dialog"] = SSAStyle(fontname="Arial", fontsize=48.0)
    subs.styles["Sign"] = SSAStyle(fontname="Verdana", fontsize=64.0, bold=True)
    subs.events.extend(
        [
            SSAEvent(start=1000, end=2500, style="Dialog", text="Hello there"),
            SSAEvent(start=2500, end=4000, style="Sign", text="{\\pos(960,120)\\fs64}Welcome to the city"),
            SSAEvent(
                start=4000,
                end=6000,
                style="Sign",
                text="{\\an8}This sign is quite long and should be wrapped onto two lines for reading",
            ),
        ]
    )
    return subs


def _fake_translation(split: SubtitleSplit, prefix: str = "PL:") -> dict[int, str]:
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    displayed: dict[int, str] = {
        index: f"{prefix}{visible_text(event.text)}"
        for index, (event, decision) in enumerate(zip(dialogue, split.decisions, strict=True))
        if decision == "displayed"
    }
    return displayed | {line.order: f"{prefix}{line.text}" for line in split.spoken}


def _write(split: SubtitleSplit, translations: dict[int, str], dest: Path) -> Path | None:
    return write_translated(split, translations, dest, fonts=None, dialogue_font=None)


def test_returns_none_when_no_dialogue_events(tmp_path: Path) -> None:
    split = split_subtitles(SSAFile(), kind="ass", spoken_styles=set())
    assert _write(split, {}, tmp_path / "out.ass") is None


@pytest.mark.integration
@pytest.mark.parametrize("stream", ["translated", "full", "spoken", "displayed"])
def test_writers_preserve_embedded_assets_and_editor_metadata(tmp_path: Path, stream: str) -> None:
    subs: SSAFile = _ass_with_both_streams()
    subs.fonts_opaque = {"sample.ttf": ["!!!!"]}
    subs.graphics_opaque = {"sample.bmp": ["!!!!"]}
    subs.aegisub_project = {"Last Style Storage": "Default", "Video Zoom Percent": "1.000000"}
    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    dest: Path = tmp_path / "out.ass"
    if stream == "translated":
        _write(split, _fake_translation(split), dest)
    else:
        {"full": write_full, "spoken": write_spoken, "displayed": write_displayed}[stream](split, dest)
    after: SSAFile = load_subtitles(dest)
    assert after.fonts_opaque == subs.fonts_opaque
    assert after.graphics_opaque == subs.graphics_opaque
    assert after.aegisub_project == subs.aegisub_project


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"{\i1}-Idziesz?{\i0}\N-Tak.", r"{\i1}-Idziesz?{\i0}\N-Tak."),
        (r"{\i1}–Idziesz?{\i0} –Tak.", r"{\i1}–Idziesz?{\i0}\N–Tak."),
        ("- Myślę - powiedział cicho.", "- Myślę - powiedział cicho."),
    ],
)
def test_polish_reflow_preserves_speakers_and_inline_tags(source: str, expected: str) -> None:
    subs: SSAFile = SSAFile()
    subs.events.append(SSAEvent(start=1230, end=4560, text=source))
    result: SubtitleSplit = reflow_polish_dialogue(split_subtitles(subs, kind="srt"))
    assert result.subs.events[0].text == expected
    assert (result.subs.events[0].start, result.subs.events[0].end) == (1230, 4560)
    assert subs.events[0].text == source


def test_ass_keeps_every_event_and_translates_both_streams(tmp_path: Path) -> None:
    subs = _ass_with_both_streams()
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    translated = _write(split, _fake_translation(split), tmp_path / "out.pl.ass")
    assert translated is not None

    after = load_subtitles(translated)
    after_events = [event for event in after.events if event.type == "Dialogue"]
    assert len(after_events) == split.stats.total_events == 3

    assert after.styles.keys() == subs.styles.keys()
    for name in subs.styles:
        assert after.styles[name].as_dict() == subs.styles[name].as_dict()

    for source, result in zip(subs.events, after_events, strict=True):
        assert result.start == source.start
        assert result.end == source.end
        assert result.style == source.style
        assert visible_text(result.text) == f"PL:{visible_text(source.text)}"


def test_ass_stamps_anishift_notice(tmp_path: Path) -> None:
    subs = _ass_with_both_streams()
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    translated = _write(split, _fake_translation(split), tmp_path / "out.pl.ass")
    assert translated is not None
    header = translated.read_text(encoding="utf-8")
    assert "Script generated by AniShift" in header
    assert "https://github.com/MattyMroz/AniShift" in header
    assert "pysubs2" not in header


def test_ass_preserves_override_tags(tmp_path: Path) -> None:
    subs = _ass_with_both_streams()
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    translated = _write(split, _fake_translation(split), tmp_path / "out.pl.ass")
    assert translated is not None
    after = load_subtitles(translated)
    signs = [event for event in after.events if event.style == "Sign"]
    assert any("\\pos(960,120)" in event.text for event in signs)
    assert any("\\an8" in event.text for event in signs)


def test_ass_uses_hard_backslash_n_between_verses(tmp_path: Path) -> None:
    subs = _ass_with_both_streams()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080"})
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    texts: dict[int, str] = dict.fromkeys(_fake_translation(split), _LONG_TRANSLATION)
    translated = _write(split, texts, tmp_path / "out.pl.ass")
    assert translated is not None
    body = translated.read_text(encoding="utf-8")
    assert _LONG_TRANSLATION_LINES.replace("\n", "\\N") in body


def test_srt_round_trip_keeps_all_events_and_uses_newline(tmp_path: Path) -> None:
    source = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=1000, end=2000, text="First subtitle"),
            SSAEvent(start=2000, end=3000, text="Second subtitle"),
        ]
    )
    source_path = tmp_path / "in.srt"
    source_path.write_text(source.to_string(format_="srt"), encoding="utf-8")

    split = split_subtitles(load_subtitles(source_path), kind="srt")
    texts: dict[int, str] = {line.order: _LONG_TRANSLATION for line in split.spoken}
    translated = _write(split, texts, tmp_path / "out.pl.srt")
    assert translated is not None

    after = load_subtitles(translated)
    after_events = [event for event in after.events if event.type == "Dialogue"]
    assert len(after_events) == split.stats.total_events == 2
    for source_event, result in zip(split.subs.events, after_events, strict=True):
        assert result.start == source_event.start
        assert result.end == source_event.end

    body = translated.read_text(encoding="utf-8")
    assert _LONG_TRANSLATION_LINES in body
    assert "\\N" not in body


def test_duplicate_spoken_occurrences_keep_distinct_translations(
    tmp_path: Path,
) -> None:
    source = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=1000, end=2000, style="Dialog", text="Same"),
            SSAEvent(start=5000, end=6000, style="Dialog", text="Same"),
        ]
    )
    split = split_subtitles(source, kind="ass", spoken_styles={"Dialog"})
    assert len(split.spoken) == 2
    translated = _write(split, {0: "Pierwszy kontekst", 1: "Drugi kontekst"}, tmp_path / "out.pl.ass")
    assert translated is not None
    after = load_subtitles(translated)
    visible = [visible_text(event.text) for event in after.events if event.type == "Dialogue"]
    assert visible == ["Pierwszy kontekst", "Drugi kontekst"]


@pytest.mark.parametrize("second_start", [0, 600])
@pytest.mark.parametrize("output_kind", ["srt", "ass"])
def test_repeated_srt_occurrences_keep_individual_translations(
    tmp_path: Path,
    second_start: int,
    output_kind: SubtitleKind,
) -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=0, end=500, text="No!"),
            SSAEvent(start=second_start, end=second_start + 500, text="No!"),
        ]
    )
    split: SubtitleSplit = split_subtitles(source, kind="srt")
    split = replace(split, kind=output_kind)

    translated: Path | None = _write(split, {0: "Nie!", 1: "Nie, nie!"}, tmp_path / f"out.pl.{output_kind}")

    assert translated is not None
    after: SSAFile = load_subtitles(translated)
    assert [event.text for event in after.events] == ["Nie!", "Nie, nie!"]
    assert [(event.start, event.end) for event in after.events] == [(0, 500), (second_start, second_start + 500)]


@pytest.mark.unit
@pytest.mark.parametrize("output_kind", ["srt", "ass"])
def test_every_copy_of_an_ass_spoken_line_keeps_its_translation_whatever_format_is_written(
    tmp_path: Path, output_kind: SubtitleKind
) -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=1000, end=1500, style="Main", text="Hello."),
            SSAEvent(start=1500, end=2000, style="Main", text="Hello."),
            SSAEvent(start=1000, end=2000, style="Overlap", text="Hello."),
            SSAEvent(start=4000, end=5000, style="Main", text="Bye."),
        ]
    )
    split: SubtitleSplit = split_subtitles(source, kind="ass", spoken_styles={"Main", "Overlap"})
    assert [line.order for line in split.spoken] == [0, 3]

    translated: Path | None = _write(
        replace(split, kind=output_kind), {0: "Cześć.", 3: "Pa."}, tmp_path / f"out.pl.{output_kind}"
    )

    assert translated is not None
    assert [visible_text(event.text) for event in load_subtitles(translated).events] == [
        "Cześć.",
        "Cześć.",
        "Cześć.",
        "Pa.",
    ]


def test_source_products_split_polish_ass_without_changing_events(tmp_path: Path) -> None:
    source = _ass_with_both_streams()
    split = split_subtitles(source, kind="ass", spoken_styles={"Dialog"})

    full = write_full(split, tmp_path / "show.pl.ass")
    spoken = write_spoken(split, tmp_path / "show.spoken.pl.ass")
    displayed = write_displayed(split, tmp_path / "show.displayed.pl.ass")

    assert full is not None
    assert spoken is not None
    assert displayed is not None
    full_events = [event for event in load_subtitles(full).events if event.type == "Dialogue"]
    spoken_events = [event for event in load_subtitles(spoken).events if event.type == "Dialogue"]
    displayed_events = [event for event in load_subtitles(displayed).events if event.type == "Dialogue"]
    assert [event.text for event in full_events] == [event.text for event in source.events]
    assert [event.text for event in spoken_events] == [source.events[0].text]
    assert [event.text for event in displayed_events] == [event.text for event in source.events[1:]]


@pytest.mark.skipif(not _REAL_ASS.is_file(), reason="dataset_ass corpus not available")
def test_real_ass_bit_round_trip_keeps_every_event(tmp_path: Path) -> None:
    before = load_subtitles(_REAL_ASS)
    split = split_subtitles(before, kind="ass")
    translated = _write(split, _fake_translation(split), tmp_path / "out.pl.ass")
    assert translated is not None

    after = load_subtitles(translated)
    before_dialogue = [event for event in before.events if event.type == "Dialogue"]
    after_dialogue = [event for event in after.events if event.type == "Dialogue"]
    assert len(after_dialogue) == len(before_dialogue) == split.stats.total_events
    assert len(after.events) == len(before.events)

    assert after.styles.keys() == before.styles.keys()
    for name in before.styles:
        assert after.styles[name].as_dict() == before.styles[name].as_dict()

    translated_events = 0
    for source, result, decision in zip(before_dialogue, after_dialogue, split.decisions, strict=True):
        assert result.start == source.start
        assert result.end == source.end
        assert result.style == source.style
        if decision == "displayed":
            assert _tags_without_scale(result.text) == _tags_without_scale(source.text)
        else:
            assert _RE_TAGS.findall(result.text) == _RE_TAGS.findall(source.text)
        source_visible = visible_text(source.text)
        if source_visible:
            assert visible_text(result.text) == f"PL:{source_visible}"
            translated_events += 1
        else:
            assert result.text == source.text
    assert translated_events > 0
    assert split.stats.spoken_events > 0
    assert split.stats.displayed_events > 0


@pytest.mark.parametrize(("style", "actor"), [("Black", "SIGN"), ("Default", "YUNO"), ("Black", "")])
def test_uncertain_style_line_is_translated_in_whole_file(tmp_path: Path, style: str, actor: str) -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=0, end=1000, style="Speech", text="Hello there."),
            SSAEvent(start=1000, end=2000, style=style, name=actor, text="Club Activities"),
        ]
    )
    verdicts: tuple[StyleVerdict, ...] = (
        StyleVerdict("Speech", Category.DIALOG, 0.9, 1, 1),
        StyleVerdict(style, Category.UNCERTAIN, 0.5, 1, 1),
    )
    split: SubtitleSplit = split_subtitles(source, kind="ass", verdicts=verdicts)
    translated: Path | None = _write(split, _fake_translation(split), tmp_path / "out.pl.ass")

    assert translated is not None
    after: SSAFile = load_subtitles(translated)
    assert [visible_text(event.text) for event in after.events] == ["PL:Hello there.", "PL:Club Activities"]


def test_layout_translated_gives_every_copy_of_a_spoken_line_its_translation_unless_keyed() -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=1000, end=1500, style="Dialog", text="Hold on!"),
            SSAEvent(start=1500, end=2000, style="Dialog", text="{\\fad(0,200)}Hold on!"),
            SSAEvent(start=4000, end=4500, style="Dialog", text="Run!"),
            SSAEvent(start=4500, end=5000, style="Dialog", text="Run!"),
        ]
    )
    split: SubtitleSplit = split_subtitles(source, kind="ass", spoken_styles={"Dialog"})
    assert [line.order for line in split.spoken] == [0, 2]
    laid_out: TranslatedLayout = layout_translated(
        split, {0: "Czekaj!", 2: "Uciekaj!", 3: "Biegnij!"}, fonts=None, dialogue_font=None
    )
    assert [event.text for event in laid_out.subs.events] == [
        "Czekaj!",
        "{\\fad(0,200)}Czekaj!",
        "Uciekaj!",
        "Biegnij!",
    ]
    assert source.events[0].text == "Hold on!"
    assert laid_out.report == LayoutReport(dialogue_unmeasured=4)


@pytest.mark.unit
def test_layout_translated_gives_a_copy_in_another_style_the_translation_of_the_line_read_once() -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=1000, end=2000, style="Main", text="Right away!"),
            SSAEvent(start=1000, end=2000, style="Overlap", text="{\\an8}Right away!"),
            SSAEvent(start=1000, end=2000, style="Echo", text="RIGHT AWAY"),
        ]
    )
    split: SubtitleSplit = split_subtitles(source, kind="ass", spoken_styles={"Main", "Overlap", "Echo"})
    assert [line.order for line in split.spoken] == [0]

    laid_out: TranslatedLayout = layout_translated(split, {0: "Już!", 2: "JUŻ"}, fonts=None, dialogue_font=None)

    assert [event.text for event in laid_out.subs.events] == ["Już!", "{\\an8}Już!", "JUŻ"]


def test_layout_translated_breaks_dialogue_and_keeps_drawings_and_events_without_translation() -> None:
    source: SSAFile = SSAFile()
    source.events.extend(
        [
            SSAEvent(start=0, end=1000, style="Dialog", text="{\\i1}Hello{\\i0} there, my friend"),
            SSAEvent(start=0, end=1000, style="Sign", text="{\\p1}m 0 0 l 10 10"),
            SSAEvent(start=0, end=1000, style="Sign", text="{\\pos(5,5)}Exit"),
        ]
    )
    split: SubtitleSplit = split_subtitles(source, kind="ass", spoken_styles={"Dialog"})
    laid_out: TranslatedLayout = layout_translated(
        split,
        {0: _LONG_TRANSLATION, 1: "rysunek"},
        fonts=None,
        dialogue_font=None,
    )
    assert laid_out.subs.events[0].text.count("\\N") == 1
    assert visible_text(laid_out.subs.events[0].text) == _LONG_TRANSLATION
    assert laid_out.subs.events[1].text == source.events[1].text
    assert laid_out.subs.events[2].text == source.events[2].text


def test_translated_writer_logs_one_layout_summary_without_texts_or_absolute_paths(tmp_path: Path) -> None:
    subs: SSAFile = _ass_with_both_streams()
    subs.info.update({"PlayResX": "1920", "PlayResY": "1080"})
    split: SubtitleSplit = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    records: list[Record] = []
    handler: int = loguru_logger.add(lambda message: records.append(message.record), level="DEBUG")
    try:
        _write(split, _fake_translation(split), tmp_path / "out.pl.ass")
    finally:
        loguru_logger.remove(handler)

    summaries: list[Record] = [record for record in records if record["message"] == "Subtitle layout summarized"]
    assert len(summaries) == 1
    extra: dict[str, Any] = summaries[0]["extra"]
    assert extra["destination"] == "out.pl.ass"
    assert extra["product"] == "Translated"
    assert {key: extra[key] for key in asdict(LayoutReport())} == asdict(
        LayoutReport(dialogue_unmeasured=1, signs_fitted=2, signs_approximate=2)
    )
    assert str(tmp_path) not in repr(summaries[0]["extra"])
    assert "PL:" not in repr(summaries[0]["extra"])
