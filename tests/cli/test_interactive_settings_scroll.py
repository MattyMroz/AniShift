from __future__ import annotations

import pytest

from anishift.cli.interactive.settings import (
    _sectioned_row_count,
    _visible_window,
    _window_end,
)

_SECTIONS = (
    *("PODSTAWOWE",) * 3,
    *("WYDAJNOŚĆ",) * 3,
    *("GŁOS",) * 10,
    *("DŹWIĘK",) * 4,
    "",
)

_BUDGETS = [4, 8, 10, 18, 24, 60]


def _rows_used(start: int, end: int) -> int:
    indicators = int(start > 0) + int(end < len(_SECTIONS))
    return _sectioned_row_count(_SECTIONS[start:end]) + indicators


@pytest.mark.parametrize("budget", _BUDGETS)
def test_cursor_stays_visible_at_every_position(budget: int) -> None:
    offset = 0
    for cursor in range(len(_SECTIONS)):
        start, end = _visible_window(_SECTIONS, cursor, offset, budget, follow_cursor=True)
        offset = start
        assert start <= cursor < end


@pytest.mark.parametrize("budget", _BUDGETS)
def test_cursor_stays_visible_when_walking_back_up(budget: int) -> None:
    offset = len(_SECTIONS) - 1
    for cursor in reversed(range(len(_SECTIONS))):
        start, end = _visible_window(_SECTIONS, cursor, offset, budget, follow_cursor=True)
        offset = start
        assert start <= cursor < end


@pytest.mark.parametrize("budget", _BUDGETS)
def test_window_never_exceeds_the_row_budget(budget: int) -> None:
    offset = 0
    for cursor in range(len(_SECTIONS)):
        start, end = _visible_window(_SECTIONS, cursor, offset, budget, follow_cursor=True)
        offset = start
        assert _rows_used(start, end) <= max(budget, _rows_used(start, start + 1))


@pytest.mark.parametrize("budget", _BUDGETS)
def test_offset_only_moves_forward_while_the_cursor_descends(budget: int) -> None:
    offset = 0
    for cursor in range(len(_SECTIONS)):
        start, _end = _visible_window(_SECTIONS, cursor, offset, budget, follow_cursor=True)
        assert start >= offset
        offset = start


def test_a_detached_view_keeps_its_offset_away_from_the_cursor() -> None:
    start, end = _visible_window(_SECTIONS, 0, 12, 8, follow_cursor=False)
    assert start == 12
    assert end > 12


def test_a_following_view_pulls_back_to_the_cursor() -> None:
    start, end = _visible_window(_SECTIONS, 0, 12, 8, follow_cursor=True)
    assert start == 0
    assert end > 0


def test_an_empty_list_has_an_empty_window() -> None:
    assert _visible_window((), 0, 0, 10, follow_cursor=True) == (0, 0)


def test_a_single_row_survives_a_budget_that_cannot_hold_it() -> None:
    start, end = _visible_window(_SECTIONS, 7, 7, 1, follow_cursor=True)
    assert end == start + 1


def test_offset_beyond_the_list_is_clamped() -> None:
    start, end = _visible_window(_SECTIONS, 3, 900, 10, follow_cursor=True)
    assert start <= 3 < end


def test_a_generous_budget_shows_everything_without_indicators() -> None:
    start, end = _visible_window(_SECTIONS, 0, 0, 60, follow_cursor=True)
    assert (start, end) == (0, len(_SECTIONS))


def test_window_end_reserves_a_row_for_each_indicator() -> None:
    end = _window_end(_SECTIONS, 5, 6)
    assert _rows_used(5, end) <= 6
