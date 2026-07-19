"""Re-split a translated line into readable subtitle verses.

We never reconstruct the source layout (Polish syntax differs); we build a new
readable split. Cut hierarchy: strong punctuation -> weak punctuation ->
conjunction/preposition boundary -> closest to centre on a word boundary (the
``split_at_half`` idea, borrowed from srt_equalizer). Protective rules: max line
length, max two verses, no orphan words, do not split fixed phrases.
"""

from __future__ import annotations

import re
from typing import Final

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_MAX_CHARS: Final[int] = 42
"""Default readable line length for on-screen subtitles (Netflix/BBC-ish)."""

MAX_LINES: Final[int] = 2
"""Maximum on-screen verses before we accept an over-length line."""

_STRONG_PUNCT: Final[str] = ".!?…:"
"""Strong sentence punctuation; best cut points (cut after the mark)."""

_WEAK_PUNCT: Final[str] = ",;—"
"""Weak punctuation incl. the Polish dialogue dash; second-best cut points."""

_TRAILING_PUNCT: Final[str] = ".,!?…:;—"
"""Characters stripped from a word before matching conjunctions."""

_CONJUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "i",
        "oraz",
        "ale",
        "że",
        "więc",
        "bo",
        "aby",
        "lub",
        "a",
        "czy",
        "gdy",
        "jak",
        "kiedy",
        "który",
        "ponieważ",
    }
)
"""Words we prefer to cut before (keeps the clause head with its clause)."""

_NON_BREAKING_HEADS: Final[frozenset[str]] = frozenset(
    {"w", "we", "z", "ze", "na", "do", "od", "po", "za", "o", "u", "pod", "nad", "przy", "bez", "dla"}
)
"""Short prepositions that must stay glued to the following word."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Whitespace run, collapsed to a single space before splitting."""


def split_line(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, ...]:
    """Split ``text`` into readable verses; return one entry when it fits.

    Args:
        text: Single-line text to split.
        max_chars: Preferred maximum length of one verse.

    Returns:
        One or more verses; a single-entry tuple when the text already fits.
    """
    text = _RE_SPACES.sub(" ", text).strip()
    if len(text) <= max_chars or " " not in text:
        return (text,)
    point = _best_cut(text, max_chars)
    left = text[:point].strip()
    right = text[point:].strip()
    if not left or not right:
        return (text,)
    return _cap((left, right), max_chars)


def _cap(parts: tuple[str, ...], max_chars: int) -> tuple[str, ...]:
    """Recurse into any part still over ``max_chars`` (bounded by content)."""
    out: list[str] = []
    for part in parts:
        out.extend(split_line(part, max_chars=max_chars) if len(part) > max_chars else (part,))
    return tuple(out)


def _best_cut(text: str, max_chars: int) -> int:
    """Return the best space index to cut at, honouring the hierarchy."""
    center = len(text) // 2
    scored: list[tuple[float, int]] = []
    for index, char in enumerate(text):
        if char != " ":
            continue
        prev_word = text[:index].rsplit(" ", 1)[-1]
        if prev_word.lower().strip(_TRAILING_PUNCT) in _NON_BREAKING_HEADS:
            continue  # do not split a preposition from its noun
        next_word = text[index + 1 :].split(" ", 1)[0].strip(_TRAILING_PUNCT)
        distance = float(abs(index - center))
        last_char = prev_word[-1:]
        if last_char in _STRONG_PUNCT:
            distance /= 8
        elif last_char in _WEAK_PUNCT:
            distance /= 4
        elif next_word.lower() in _CONJUNCTIONS:
            distance /= 2
        if _is_orphan(text[:index], text[index + 1 :]):
            distance *= 10
        scored.append((distance, index))
    if not scored:
        return _greedy_cut(text, max_chars)
    return min(scored, key=lambda pair: pair[0])[1]


def _is_orphan(left: str, right: str) -> bool:
    """True when either side is a single word (an orphan verse)."""
    return " " not in left.strip() or " " not in right.strip()


def _greedy_cut(text: str, max_chars: int) -> int:
    """Fallback: last space at or before ``max_chars`` (greedy)."""
    cut = text.rfind(" ", 0, max_chars + 1)
    return cut if cut > 0 else text.find(" ")


__all__ = ["DEFAULT_MAX_CHARS", "MAX_LINES", "split_line"]
