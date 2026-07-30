"""Provider-neutral Unicode text primitives."""

from __future__ import annotations

from anishift.text.boundaries import (
    CJK_SENTENCE_ENDINGS,
    CLOSING_MARKS,
    LATIN_SENTENCE_ENDINGS,
    PHRASE_CUT_CHARS,
    SENTENCE_ENDINGS,
    ZERO_WIDTH,
    is_false_sentence_break,
    period_ends_sentence,
)
from anishift.text.graphemes import hard_split_graphemes, split_graphemes

__all__ = [
    "CJK_SENTENCE_ENDINGS",
    "CLOSING_MARKS",
    "LATIN_SENTENCE_ENDINGS",
    "PHRASE_CUT_CHARS",
    "SENTENCE_ENDINGS",
    "ZERO_WIDTH",
    "hard_split_graphemes",
    "is_false_sentence_break",
    "period_ends_sentence",
    "split_graphemes",
]
