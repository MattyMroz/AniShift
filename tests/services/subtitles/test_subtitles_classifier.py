import pysubs2
import pytest
from pysubs2 import SSAEvent, SSAFile

from anishift.paths import quality_dir
from anishift.services.subtitles.classifier import Category, classify_styles, written_in_capitals
from anishift.services.subtitles.service import collapse_fbf

_FUJI_ASS = quality_dir() / "dataset_ass" / "140___Fuji__Kimi_to_Koete_Koi_ni_Naru_-_03__1080p_.mkv.ass"


def _event(text: str, *, start: int, style: str = "Default", end: int | None = None) -> SSAEvent:
    return SSAEvent(start=start, end=end if end is not None else start + 40, style=style, text=text)


@pytest.mark.skipif(not _FUJI_ASS.is_file(), reason="Fuji dataset file not available")
def test_collapse_fbf_reduces_fuji_signs_to_a_handful_of_lines() -> None:
    subs = pysubs2.load(str(_FUJI_ASS), encoding="utf-8")
    signs = [event for event in subs.events if event.style == "Znaki" and event.type == "Dialogue"]

    lines, _removed = collapse_fbf(signs)

    assert len(signs) == 1381
    assert len(lines) == 20
    assert len({line.text for line in lines}) == 18


def _subs(events: list[SSAEvent]) -> SSAFile:
    subs = SSAFile()
    subs.events.extend(events)
    return subs


def test_classify_styles_deduplicates_animation_but_keeps_raw_count() -> None:
    subs = _subs([_event("same", start=index * 40) for index in range(6)])

    verdict = classify_styles(subs)[0]

    assert verdict.category is Category.DIALOG
    assert verdict.line_count == 1
    assert verdict.raw_line_count == 6


def test_collapse_fbf_drops_drawings_and_merges_continuous_text() -> None:
    events = [
        _event("{\\p1}m 0 0", start=0),
        _event("hello", start=0),
        _event("hello", start=40),
        _event("hello", start=1000),
    ]

    lines, removed = collapse_fbf(events)

    assert len(lines) == 2
    assert removed == 1
    assert lines[0].text == "hello"


def test_collapse_fbf_keeps_distant_repeats_separate() -> None:
    events = [_event("hello", start=0), _event("hello", start=2000)]

    lines, removed = collapse_fbf(events)

    assert len(lines) == 2
    assert removed == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("style", "category"),
    [
        ("EDup", Category.SIGN),
        ("OPdown", Category.SIGN),
        ("OP_EN_blue", Category.SIGN),
        ("ED1 - ENG", Category.SIGN),
        ("IN01", Category.SIGN),
        ("NCOP2", Category.SIGN),
        ("OP1-Light_cyber_main", Category.SIGN),
        ("Main", Category.DIALOG),
        ("Speed", Category.DIALOG),
        ("Insanity", Category.DIALOG),
    ],
)
def test_classify_styles_treats_release_coded_song_styles_as_signs(style: str, category: Category) -> None:
    subs: SSAFile = _subs([_event(f"Sung line number {index}.", start=index * 3000, style=style) for index in range(8)])

    assert classify_styles(subs)[0].category is category


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "capitals"),
    [("YAY", True), ("NUMBER ONE...", True), ("Yay!", False), ("OK", True), ("Ok", False), ("I", False), ("", False)],
)
def test_written_in_capitals_needs_most_of_at_least_two_letters_in_capitals(text: str, *, capitals: bool) -> None:
    assert written_in_capitals(text) is capitals
