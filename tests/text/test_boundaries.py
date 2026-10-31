from __future__ import annotations

import pytest

from anishift.text.boundaries import (
    CLOSING_MARKS,
    PHRASE_CUT_CHARS,
    ends_sentence,
    is_false_sentence_break,
    period_ends_sentence,
)


def test_unicode_boundary_sets_cover_multiple_scripts() -> None:
    assert all(character in PHRASE_CUT_CHARS for character in ("،", "\uff1b", "—", "、"))
    assert all(character in CLOSING_MARKS for character in (")", "»", "”", "」"))


@pytest.mark.parametrize("character", ["(", "«", "“", "「", "'", "\u2019"])
def test_opening_marks_and_apostrophes_are_not_phrase_boundaries(character: str) -> None:
    assert character not in PHRASE_CUT_CHARS


@pytest.mark.parametrize(
    ("previous", "following"),
    [
        ("Dr. ", "Smith wrócił."),
        ("prof. ", "Nowak wrócił."),
        ("A. ", "Mickiewicz wrócił."),
        ("1798. ", "roku wrócił."),
    ],
)
def test_ambiguous_dots_are_not_sentence_breaks(previous: str, following: str) -> None:
    assert is_false_sentence_break(previous, following)


def test_unambiguous_dot_is_a_sentence_break() -> None:
    assert not is_false_sentence_break("Wrócił. ", "Potem wyszedł.")


def test_decimal_dot_is_not_a_sentence_end() -> None:
    assert not period_ends_sentence(
        "1",
        "5 kg",
        previous_character="1",
        next_character="5",
    )


@pytest.mark.parametrize(
    "text", ["Tak.", "Stój!", "Kto?", "No i…", 'Powiedział "dość"', "Mówi „dość”", "To «on»", "Tak.  "]
)
def test_ends_sentence_closed_line_returns_true(text: str) -> None:
    assert ends_sentence(text)


@pytest.mark.parametrize("text", ["Ale wtedy,", "I wtedy", "", "   "])
def test_ends_sentence_open_line_returns_false(text: str) -> None:
    assert not ends_sentence(text)
