from pathlib import Path

from pysubs2 import SSAEvent, SSAFile

from anishift.services.subtitles.classifier import Category, StyleVerdict
from anishift.services.subtitles.service import split_subtitles, write_displayed


def _event(text: str, *, style: str, start: int = 0) -> SSAEvent:
    return SSAEvent(start=start, end=start + 1000, style=style, text=text)


def _subs(events: list[SSAEvent]) -> SSAFile:
    subs = SSAFile()
    subs.events.extend(events)
    return subs


def test_split_subtitles_marks_lines_individually_and_preserves_source() -> None:
    subs = _subs([_event("{\\pos(1,2)}Hello", style="Dialog"), _event("Sign", style="Sign")])
    original = subs.events[0].text

    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})

    assert split.decisions == ("spoken", "displayed")
    assert split.spoken[0].text == "Hello"
    assert subs.events[0].text == original


def test_write_displayed_creates_new_tag_safe_file(tmp_path: Path) -> None:
    subs = _subs(
        [
            _event("{\\pos(1,2)}Sign", style="Sign"),
            _event("Narration", style="Dialog", start=1000),
        ]
    )
    split = split_subtitles(subs, kind="ass", spoken_styles={"Dialog"})
    dest = tmp_path / "source.displayed.ass"

    result = write_displayed(split, dest)

    assert result == dest
    content = dest.read_text(encoding="utf-8")
    assert "{\\pos(1,2)}Sign" in content


def test_split_subtitles_treats_srt_lines_as_spoken() -> None:
    split = split_subtitles(_subs([_event("<i>Hello</i>", style="Default")]), kind="srt")

    assert split.decisions == ("spoken",)
    assert split.spoken[0].text == "Hello"
    assert split.verdicts == ()


def test_split_srt_preserves_repeated_utterances() -> None:
    subs: SSAFile = _subs(
        [
            SSAEvent(start=0, end=500, text="No!"),
            SSAEvent(start=600, end=1100, text="No!"),
        ]
    )

    split = split_subtitles(subs, kind="srt")

    assert [(line.start, line.end, line.text, line.order) for line in split.spoken] == [
        (0, 500, "No!", 0),
        (600, 1100, "No!", 1),
    ]
    assert split.stats.collapsed_away == 0


def test_split_honors_explicit_empty_spoken_selection() -> None:
    subs: SSAFile = _subs([_event("Sign", style="Signs")])

    split = split_subtitles(subs, kind="ass", spoken_styles=())

    assert split.decisions == ("displayed",)
    assert split.spoken == ()
    assert split.stats.spoken_events == 0


def test_split_retains_automatic_fallback_when_styles_are_not_selected() -> None:
    subs: SSAFile = _subs([_event("Sign", style="Signs")])
    verdicts: tuple[StyleVerdict, ...] = (StyleVerdict("Signs", Category.SIGN, 1.0, 1, 1),)

    split = split_subtitles(subs, kind="ass", verdicts=verdicts)

    assert split.decisions == ("spoken",)
