from __future__ import annotations

import pytest

from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT, DEFAULT_CHUNK_LIMIT
from anishift.services.translation.layout_config import LayoutConfig
from anishift.services.translation.linebreak import DEFAULT_MAX_CHARS, MAX_LINES, split_for_layout, split_line

_LONG_LINE = "Zupełnie przypadkowe zdanie o tym jak długo potrafi ciągnąć się jedna kwestia bohatera"


def test_defaults_match_the_shipped_pipeline() -> None:
    config = LayoutConfig()
    assert config.max_chars_per_line == DEFAULT_MAX_CHARS
    assert config.max_lines_per_event == MAX_LINES
    assert config.chunk_chars == DEFAULT_CHAR_LIMIT


def test_the_default_chunk_size_keeps_the_shipped_piece_size() -> None:
    assert LayoutConfig().chunk_pieces == DEFAULT_CHUNK_LIMIT


@pytest.mark.parametrize(("chunk_chars", "pieces"), [(300, 100), (900, 300), (4000, 1333)])
def test_the_piece_size_follows_the_request_size(chunk_chars: int, pieces: int) -> None:
    assert LayoutConfig(chunk_chars=chunk_chars).chunk_pieces == pieces


def test_a_tiny_request_still_leaves_a_usable_piece() -> None:
    assert LayoutConfig(chunk_chars=1).chunk_pieces == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"max_chars_per_line": 0},
        {"max_chars_per_line": -1},
        {"max_lines_per_event": 0},
        {"chunk_chars": 0},
    ],
)
def test_a_limit_that_cannot_produce_output_is_rejected(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LayoutConfig(**changes)


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
