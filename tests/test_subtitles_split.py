from pathlib import Path

from pysubs2 import SSAEvent, SSAFile

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
