"""Re-split a translated line into readable on-screen subtitle verses.

A translated line is often too long to read at a glance, so it is split into at
most two short verses at a natural boundary. The source layout is never
reconstructed (Polish syntax differs); a new readable split is built instead.

Cut hierarchy (best first): strong punctuation -> weak punctuation -> before a
conjunction/preposition -> closest to the centre on a word boundary (the
``split_at_half`` idea). Protective rules: preferred max length, at most two
verses, no single-word orphan verse, never split a fixed multi-word phrase or
detach a short preposition from its noun.

Punctuation classes reuse the chunker's Unicode-derived sets (one source of
truth); the conjunction and preposition lists are the complete Polish word
lists from Wiktionary.
"""

from __future__ import annotations

import re
from typing import Final

from anishift.services.translation.chunking import SENTENCE_ENDINGS, phrase_cut_chars

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_MAX_CHARS: Final[int] = 42
"""Preferred readable line length for on-screen subtitles (Netflix/BBC-ish)."""

MAX_LINES: Final[int] = 2
"""Maximum on-screen verses before an over-length line is accepted."""

_STRONG_CUT: Final[str] = SENTENCE_ENDINGS + ":"
"""Strong cut points (sentence endings plus colon); cut just after the mark."""

_WEAK_CUT: Final[str] = phrase_cut_chars()
"""Weak cut points: every Unicode phrase separator (commas, dashes, closers)."""

_TRAILING_PUNCT: Final[str] = _STRONG_CUT + _WEAK_CUT
"""Characters stripped from a word before matching it against the word lists."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_spójniki
_CONJUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "aby",
        "aczkolwiek",
        "albo",
        "albowiem",
        "ale",
        "ani",
        "aniżeli",
        "atoli",
        "aż",
        "ażeby",
        "bądź",
        "bo",
        "bodaj",
        "bowiem",
        "by",
        "byle",
        "choć",
        "chociaż",
        "choćby",
        "czy",
        "czyli",
        "dlatego",
        "dopóki",
        "dopóty",
        "dotąd",
        "gdy",
        "gdyby",
        "gdyż",
        "i",
        "ile",
        "ilekroć",
        "im",
        "iż",
        "jak",
        "jakby",
        "jakkolwiek",
        "jako",
        "jakoby",
        "jednak",
        "jednakże",
        "jeśli",
        "jeżeli",
        "kiedy",
        "lecz",
        "ledwie",
        "ledwo",
        "lub",
        "mianowicie",
        "minus",
        "natomiast",
        "niby",
        "niczym",
        "niemniej",
        "nim",
        "niż",
        "niżeli",
        "oraz",
        "plus",
        "ponieważ",
        "póki",
        "póty",
        "przeto",
        "skoro",
        "toteż",
        "tudzież",
        "tylko",
        "więc",
        "wprawdzie",
        "wszelako",
        "zanim",
        "zarówno",
        "zaś",
        "zatem",
        "że",
        "żeby",
    }
)
"""All single-word Polish conjunctions; a cut is preferred just before one."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_spójniki
_CONJUNCTIONS_MULTIWORD: Final[frozenset[tuple[str, ...]]] = frozenset(
    {
        ("a", "co", "więcej"),
        ("a", "również"),
        ("a", "także"),
        ("a", "w", "szczególności"),
        ("a", "zwłaszcza"),
        ("ale", "również"),
        ("ale", "też"),
        ("chyba", "że"),
        ("co", "gorsza"),
        ("dlatego", "że"),
        ("gdy", "tylko"),
        ("jak", "gdyby"),
        ("jak", "i"),
        ("jako", "że"),
        ("mimo", "to"),
        ("mimo", "że"),
        ("niemniej", "jednak"),
        ("o", "ile"),
        ("oprócz", "tego"),
        ("po", "czym"),
        ("podczas", "gdy"),
        ("poza", "tym"),
        ("przy", "czym"),
        ("przy", "tym"),
        ("to", "jest"),
        ("to", "znaczy"),
        ("w", "przeciwnym", "razie"),
        ("w", "sensie"),
        ("w", "takim", "razie"),
        ("w", "związku", "z", "czym"),
        ("wobec", "tego"),
        ("z", "tego", "powodu"),
        ("z", "tym", "że"),
        ("za", "to"),
        ("żeby", "tylko"),
    }
)
"""Multi-word Polish conjunctions; a cut is preferred just before the phrase."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_przyimki
_NON_BREAKING_HEADS: Final[frozenset[str]] = frozenset(
    {
        "bez",
        "beze",
        "dla",
        "do",
        "ku",
        "między",
        "na",
        "nad",
        "nade",
        "o",
        "od",
        "ode",
        "po",
        "pod",
        "pode",
        "przed",
        "przede",
        "przez",
        "przeze",
        "przy",
        "u",
        "w",
        "we",
        "z",
        "za",
        "ze",
    }
)
"""Simple prepositions (with phonetic variants) never detached from their noun."""

# source: https://pl.wiktionary.org/wiki/Kategoria:Język_polski_-_przyimki
_PREPOSITIONS_MULTIWORD: Final[frozenset[tuple[str, ...]]] = frozenset(
    {
        ("aż", "do"),
        ("bez", "względu", "na"),
        ("na", "czele"),
        ("na", "korzyść"),
        ("na", "podstawie"),
        ("na", "przekór"),
        ("na", "rzecz"),
        ("na", "skutek"),
        ("na", "temat"),
        ("na", "tle"),
        ("na", "wzór"),
        ("na", "zewnątrz"),
        ("o", "włos", "od"),
        ("odnośnie", "do"),
        ("począwszy", "od"),
        ("pod", "kątem"),
        ("pod", "względem"),
        ("przy", "pomocy"),
        ("przy", "użyciu"),
        ("w", "celu"),
        ("w", "ciągu"),
        ("w", "czasie"),
        ("w", "imieniu"),
        ("w", "imię"),
        ("w", "miarę"),
        ("w", "obliczu"),
        ("w", "obrębie"),
        ("w", "odniesieniu", "do"),
        ("w", "oparciu", "o"),
        ("w", "porównaniu", "z"),
        ("w", "przeciwieństwie", "do"),
        ("w", "ramach"),
        ("w", "razie"),
        ("w", "sprawie"),
        ("w", "stosunku", "do"),
        ("w", "wyniku"),
        ("w", "zależności", "od"),
        ("w", "związku", "z"),
        ("w", "ślad", "za"),
        ("z", "okazji"),
        ("z", "powodu"),
        ("z", "punktu", "widzenia"),
        ("z", "uwagi", "na"),
        ("z", "wyjątkiem"),
        ("z", "wyłączeniem"),
        ("za", "pomocą"),
        ("za", "pośrednictwem"),
        ("za", "sprawą"),
        ("ze", "strony"),
        ("ze", "względu", "na"),
    }
)
"""Multi-word Polish prepositions; never cut inside one of these phrases."""

_MAX_PHRASE_WORDS: Final[int] = 4
"""Longest multi-word phrase looked up (``w związku z czym``)."""

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
    return (left, right)


def _best_cut(text: str, max_chars: int) -> int:
    """Return the best space index to cut at, honouring the cut hierarchy."""
    words = text.split(" ")
    offsets = _word_offsets(words)
    center = len(text) // 2
    scored: list[tuple[float, int]] = []
    for word_index, offset in enumerate(offsets[1:], start=1):
        cut = offset - 1
        prev_word = words[word_index - 1]
        if _protected(words, word_index):
            continue
        distance = float(abs(cut - center))
        distance *= _weight(prev_word, words, word_index)
        if _is_orphan(text[:cut], text[cut:]):
            distance *= 10
        scored.append((distance, cut))
    if not scored:
        return _greedy_cut(text, max_chars)
    return min(scored, key=lambda pair: pair[0])[1]


def _word_offsets(words: list[str]) -> list[int]:
    """Return the start offset of every word in a single-space-joined text."""
    offsets: list[int] = []
    cursor = 0
    for word in words:
        offsets.append(cursor)
        cursor += len(word) + 1
    return offsets


def _weight(prev_word: str, words: list[str], word_index: int) -> float:
    """Return the distance multiplier for cutting before ``words[word_index]``."""
    last_char = prev_word[-1:]
    if last_char in _STRONG_CUT:
        return 1 / 8
    if last_char in _WEAK_CUT:
        return 1 / 4
    if _starts_conjunction(words, word_index):
        return 1 / 3
    return 1.0


def _protected(words: list[str], word_index: int) -> bool:
    """True when a cut before ``words[word_index]`` would break a fixed phrase.

    A cut sits between ``word_index - 1`` and ``word_index``; it breaks a phrase
    occupying ``words[start:start + length]`` whenever ``start < word_index <
    start + length``.
    """
    if _clean(words[word_index - 1]) in _NON_BREAKING_HEADS:
        return True
    for length in range(2, _MAX_PHRASE_WORDS + 1):
        for start in range(max(0, word_index - length + 1), word_index):
            end = start + length
            if end > len(words) or word_index >= end:
                continue
            phrase = tuple(_clean(w) for w in words[start:end])
            if phrase in _PREPOSITIONS_MULTIWORD or phrase in _CONJUNCTIONS_MULTIWORD:
                return True
    return False


def _starts_conjunction(words: list[str], word_index: int) -> bool:
    """True when ``words[word_index]`` begins a conjunction (single or phrase)."""
    if _clean(words[word_index]) in _CONJUNCTIONS:
        return True
    return any(
        tuple(_clean(w) for w in words[word_index : word_index + length]) in _CONJUNCTIONS_MULTIWORD
        for length in range(2, _MAX_PHRASE_WORDS + 1)
    )


def _clean(word: str) -> str:
    """Lowercase ``word`` and strip surrounding punctuation for list matching."""
    return word.lower().strip(_TRAILING_PUNCT)


def _is_orphan(left: str, right: str) -> bool:
    """True when either side is a single word (an orphan verse)."""
    return " " not in left.strip() or " " not in right.strip()


def _greedy_cut(text: str, max_chars: int) -> int:
    """Fallback: last space at or before ``max_chars`` (greedy)."""
    cut = text.rfind(" ", 0, max_chars + 1)
    return cut if cut > 0 else text.find(" ")


__all__ = ["DEFAULT_MAX_CHARS", "MAX_LINES", "split_line"]
