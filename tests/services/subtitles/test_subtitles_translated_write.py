from __future__ import annotations

from pathlib import Path

from pysubs2 import SSAEvent, SSAFile, SSAStyle

from anishift.services.subtitles.service import (
    load_subtitles,
    split_subtitles,
    write_displayed,
    write_translated_displayed,
)
from anishift.services.subtitles.text import visible_text
from anishift.services.subtitles.types import SplitStats, SubtitleSplit


def _ass_with_displayed() -> SSAFile:
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


def _split(subs: SSAFile):  # type: ignore[no-untyped-def]
    return split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})


def _translate_displayed(split, prefix: str = "PL:"):  # type: ignore[no-untyped-def]
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    texts = [
        visible_text(event.text)
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed"
    ]
    return [(f"{prefix}{text}",) for text in texts]


def test_returns_none_when_no_displayed_events(tmp_path: Path) -> None:
    subs = SSAFile()
    subs.events.append(SSAEvent(start=0, end=1000, style="Dialog", text="spoken only"))
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    assert write_translated_displayed(split, [], tmp_path / "out.ass") is None


def test_ass_round_trip_changes_only_dialogue_text(tmp_path: Path) -> None:
    subs = _ass_with_displayed()
    split = _split(subs)
    original = write_displayed(split, tmp_path / "orig.displayed.ass")
    translated = write_translated_displayed(split, _translate_displayed(split), tmp_path / "out.pl.ass")
    assert original is not None
    assert translated is not None

    before = load_subtitles(original)
    after = load_subtitles(translated)

    before_events = [event for event in before.events if event.type == "Dialogue"]
    after_events = [event for event in after.events if event.type == "Dialogue"]
    assert len(after_events) == len(before_events) == split.stats.displayed_events

    assert after.styles.keys() == before.styles.keys()
    for name in before.styles:
        assert after.styles[name].as_dict() == before.styles[name].as_dict()

    for source, result in zip(before_events, after_events, strict=True):
        assert result.start == source.start
        assert result.end == source.end
        assert result.style == source.style
        assert result.text != source.text
        assert visible_text(result.text).startswith("PL:")


def test_ass_preserves_override_tags(tmp_path: Path) -> None:
    subs = _ass_with_displayed()
    split = _split(subs)
    translated = write_translated_displayed(split, _translate_displayed(split), tmp_path / "out.pl.ass")
    assert translated is not None
    after = load_subtitles(translated)
    signs = [event for event in after.events if event.style == "Sign"]
    assert any("\\pos(960,120)" in event.text for event in signs)
    assert any("\\an8" in event.text for event in signs)


def test_ass_uses_hard_backslash_n_between_verses(tmp_path: Path) -> None:
    subs = _ass_with_displayed()
    split = _split(subs)
    verses = [("Pierwszy wers", "drugi wers")] * split.stats.displayed_events
    translated = write_translated_displayed(split, verses, tmp_path / "out.pl.ass")
    assert translated is not None
    body = translated.read_text(encoding="utf-8")
    assert "Pierwszy wers\\Ndrugi wers" in body


def test_srt_round_trip_uses_newline_between_verses(tmp_path: Path) -> None:
    subs = SSAFile()
    subs.events.extend(
        [
            SSAEvent(start=1000, end=2000, text="First subtitle"),
            SSAEvent(start=2000, end=3000, text="Second subtitle"),
        ]
    )
    stats = SplitStats(
        total_events=2, spoken_events=0, spoken_lines=0, displayed_events=2, drawing_events=0, collapsed_away=0
    )
    split = SubtitleSplit(
        kind="srt", subs=subs, decisions=("displayed", "displayed"), verdicts=(), spoken=(), stats=stats
    )
    verses = [("Pierwszy wers", "drugi wers")] * 2
    translated = write_translated_displayed(split, verses, tmp_path / "out.pl.srt")
    assert translated is not None
    body = translated.read_text(encoding="utf-8")
    assert "Pierwszy wers\ndrugi wers" in body
    assert "\\N" not in body
