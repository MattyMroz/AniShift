from __future__ import annotations

import pytest

from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.subtitles.linebreak import DEFAULT_MAX_CHARS, MAX_LINES, split_for_layout, split_line

_LONG_LINE = "Zupełnie przypadkowe zdanie o tym jak długo potrafi ciągnąć się jedna kwestia bohatera"


def test_defaults_match_the_shipped_pipeline() -> None:
    assert LayoutLimits() == LayoutLimits(max_chars=DEFAULT_MAX_CHARS, max_lines=MAX_LINES)


@pytest.mark.parametrize("changes", [{"max_chars": 0}, {"max_chars": -1}, {"max_lines": 0}])
def test_a_limit_that_cannot_produce_output_is_rejected(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LayoutLimits(**changes)


@pytest.mark.parametrize("budget", [1, 2, 3])
def test_a_line_never_exceeds_its_verse_budget(budget: int) -> None:
    verses = split_line(_LONG_LINE, max_chars=20, max_lines=budget)
    assert len(verses) <= budget


def test_a_single_verse_budget_keeps_the_line_intact() -> None:
    assert split_line(_LONG_LINE, max_chars=20, max_lines=1) == (_LONG_LINE,)


def test_a_wider_budget_splits_further_than_a_narrow_one() -> None:
    narrow = split_line(_LONG_LINE, max_chars=20, max_lines=2)
    wide = split_line(_LONG_LINE, max_chars=20, max_lines=4)
    assert len(wide) > len(narrow)


def test_the_layout_splitter_honours_the_verse_budget() -> None:
    verses = split_for_layout(_LONG_LINE, ("jedna kwestia",), max_chars=20, max_lines=1)
    assert verses == (_LONG_LINE,)


def test_a_shorter_line_is_left_alone_by_every_budget() -> None:
    for budget in (1, 2, 3, 4):
        assert split_line("Krótko", max_chars=42, max_lines=budget) == ("Krótko",)
