"""Re-split a translated line into readable on-screen subtitle verses."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from anishift.text.boundaries import (
    BREAKABLE_SPACES,
    CLOSING_MARKS,
    PHRASE_CUT_CHARS,
    SENTENCE_ENDINGS,
    is_false_sentence_break,
)

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_MAX_CHARS: Final[int] = 42
"""Preferred readable line length for on-screen subtitles (Netflix/BBC-ish)."""

MAX_LINES: Final[int] = 2
"""Maximum on-screen verses before an over-length line is accepted."""

_STRONG_CUT: Final[str] = SENTENCE_ENDINGS + ":"
"""Strong cut points (sentence endings plus colon); cut just after the mark."""

_WEAK_CUT: Final[str] = PHRASE_CUT_CHARS
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
        "bez", "beze", "dla", "do", "ku", "między", "na", "nad", "nade", "o", "od", "ode",
        "po", "pod", "pode", "przed", "przede", "przez", "przeze", "przy", "u", "w", "we", "z", "za", "ze",
        "według", "wśród", "obok", "zza", "spod", "poza", "wobec", "podczas", "około", "ponad", "pomiędzy",
    }
)  # fmt: skip
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

_LAYOUT_WINDOW_MIN_CHARS: Final[int] = 8
"""Smallest search window around one proportional layout boundary target."""

_TRAILING_CONJUNCTION_PENALTY: Final[float] = 8.0
"""Distance multiplier for a cut that leaves a conjunction ending the line."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Whitespace run, collapsed to a single space before splitting."""

_DIALOGUE_DASHES: Final[frozenset[str]] = frozenset({"-", "–", "—"})
"""Standalone or attached markers introducing a speaker's turn."""

_PRONOUN_HEADS: Final[frozenset[str]] = frozenset(
    [
        "ja", "ty", "on", "ona", "ono", "my", "wy", "oni", "one", "ten", "ta", "to", "te",
        "tego", "tej", "temu", "tym", "tych", "tamten", "taki", "taka", "takie", "mój", "moja",
        "moje", "twój", "twoja", "twoje", "swój", "nasz", "wasz", "każdy", "każda", "każde",
        "jakiś", "jakaś", "które", "który", "która",
    ]
)  # fmt: skip
"""Common personal pronouns and determiners kept with their following phrase."""

_VERB_HEADS: Final[frozenset[str]] = frozenset(
    [
        "będę", "będziesz", "będzie", "będziemy", "będziecie", "będą", "był", "była", "było", "byli", "były",
        "jestem", "jesteś", "jest", "jesteśmy", "jesteście", "są", "musi", "muszę", "musisz", "musimy", "musicie",
        "muszą", "mogę", "możesz", "może", "możemy", "możecie", "mogą", "mógł", "mogła", "mogli", "powinien",
        "powinna", "powinno", "powinni", "powinny", "chciał", "chciała", "chcę", "chcesz", "chce",
    ]
)  # fmt: skip
"""Common auxiliary and modal forms kept with the following predicate component."""

_TITLE_HEADS: Final[frozenset[str]] = frozenset(
    ["dr", "mgr", "prof", "pan", "pani", "panie", "profesor", "doktor", "kapitan", "król"]
)
"""Titles and undotted abbreviations kept with the name that follows."""

_ADJECTIVE_ENDINGS: Final[tuple[str, ...]] = ("ego", "emu", "ych", "ymi", "ym", "ny", "na", "ne", "ry", "ra", "re")
"""Conservative surface hints for an attributive adjective, without a morphological parser."""

_TOP_HEAVY_PENALTY: Final[int] = 6
"""Extra imbalance characters assigned to a longer upper dialogue verse."""

_OVERFLOW_TOLERANCE: Final[int] = 2
"""Extra characters allowed for safer syntax only when every legal cut overflows."""

_REFLEXIVE_HEADS: Final[frozenset[str]] = _PRONOUN_HEADS | _CONJUNCTIONS | {"nie"}
"""Heads that bind a following reflexive particle to its predicate."""


def split_line(text: str, *, max_chars: int = DEFAULT_MAX_CHARS, max_lines: int = MAX_LINES) -> tuple[str, ...]:
    """Split ``text`` into readable verses; return one entry when it fits."""
    text = BREAKABLE_SPACES.sub(" ", text).strip()
    words: list[str] = text.split(" ")
    markers: list[int] = [index for index in range(len(words)) if _speaker_start(words, index)]
    if max_lines >= MAX_LINES and len(markers) == MAX_LINES and markers[0] == 0:
        return " ".join(words[: markers[1]]), " ".join(words[markers[1] :])
    return _split(text, max_chars, max_lines, dialogue=True)


def _speaker_start(words: list[str], index: int) -> bool:
    word: str = words[index]
    if word[:1] not in _DIALOGUE_DASHES:
        return False
    spoken: str = word[1:] if len(word) > 1 else " ".join(words[index + 1 : index + 2])
    if not spoken:
        return False
    if index == 0:
        return True
    return _tail(words[index - 1])[-1:] in SENTENCE_ENDINGS or (word in _DIALOGUE_DASHES and spoken[0].isupper())


def split_for_layout(
    text: str,
    source_verses: tuple[str, ...],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_lines: int = MAX_LINES,
) -> tuple[str, ...]:
    """Split displayed text using authored verse count as the layout contract."""
    normalised = _RE_SPACES.sub(" ", text).strip()
    if len(source_verses) <= 1:
        return _split(normalised, max_chars, max_lines)
    words = normalised.split()
    if len(words) < len(source_verses):
        return tuple(words) if words else ("",)
    boundaries = _proportional_boundaries(words, source_verses)
    starts = (0, *boundaries)
    ends = (*boundaries, len(words))
    return tuple(" ".join(words[start:end]) for start, end in zip(starts, ends, strict=True))


def _proportional_boundaries(words: list[str], source_verses: tuple[str, ...]) -> tuple[int, ...]:
    """Choose natural target boundaries near authored relative line lengths."""
    weights = [max(len(verse), 1) for verse in source_verses]
    total_weight = sum(weights)
    offsets = _word_offsets(words)
    text_length = len(" ".join(words))
    # Punctuation preference stays local to this window; without it a distant
    # sentence end outweighs the authored proportions and the tail collapses
    # into one-word lines.
    radius = max(_LAYOUT_WINDOW_MIN_CHARS, round(text_length / (2 * len(source_verses))))
    boundaries: list[int] = []
    previous = 0
    for line_index in range(1, len(source_verses)):
        remaining_lines = len(source_verses) - line_index
        desired = round(text_length * sum(weights[:line_index]) / total_weight)
        candidates = [
            index for index in range(previous + 1, len(words) - remaining_lines + 1) if not _protected(words, index)
        ]
        if not candidates:
            candidates = list(range(previous + 1, len(words) - remaining_lines + 1))
        near = [index for index in candidates if abs(offsets[index] - desired) <= radius]
        # Linear weights on purpose: squared bonuses would let a mere comma or
        # percent sign drag the boundary across the whole window and overflow
        # the line, while linear ones cap the pull at a few characters.
        boundary = min(
            near or candidates,
            key=lambda index: (abs(offsets[index] - desired) + 1.0) * _weight(words[index - 1], words, index),
        )
        boundaries.append(boundary)
        previous = boundary
    return tuple(boundaries)


def _split(text: str, max_chars: int, budget: int, *, dialogue: bool = False) -> tuple[str, ...]:
    """Recursively split ``text`` into at most ``budget`` verses."""
    if len(text) <= max_chars or " " not in text or budget <= 1:
        return (text,)
    point: int = _dialogue_cut(text, max_chars, budget) if dialogue else _best_cut(text, max_chars)
    left = text[:point].strip()
    right = text[point:].strip()
    if not left or not right:
        return (text,)
    if dialogue:
        return (left, *_split(right, max_chars, budget - 1, dialogue=True))
    verses = _split(left, max_chars, budget - 1)
    return verses + _split(right, max_chars, budget - len(verses))


def _dialogue_cut(text: str, max_chars: int, budget: int) -> int:
    candidates: list[tuple[tuple[int, bool, int, bool, int], int]] = _dialogue_candidates(
        text, max_chars, budget, keep_names=True
    ) or _dialogue_candidates(text, max_chars, budget, keep_names=False)
    if not candidates:
        return len(text)
    minimum: int = min(rank[0] for rank, _ in candidates)
    if minimum == 0:
        return min(candidates)[1]
    return min(
        (candidate for candidate in candidates if candidate[0][0] <= minimum + _OVERFLOW_TOLERANCE),
        key=lambda candidate: (candidate[0][1], candidate[0][0], *candidate[0][2:]),
    )[1]


def _dialogue_candidates(
    text: str, max_chars: int, budget: int, *, keep_names: bool
) -> list[tuple[tuple[int, bool, int, bool, int], int]]:
    words: list[str] = text.split(" ")
    candidates: list[tuple[tuple[int, bool, int, bool, int], int]] = []
    for index, offset in enumerate(_word_offsets(words)[1:], start=1):
        if _dialogue_protected(words, index, keep_names=keep_names):
            continue
        cut: int = offset - 1
        left: str = text[:cut]
        right: str = text[offset:]
        overflow: int = max(0, len(left) - max_chars, len(right) - max_chars * (budget - 1))
        rank: tuple[int, bool, int, bool, int] = (
            overflow,
            _syntactic_risk(words, index),
            _boundary_rank(words, index),
            _is_orphan(left, right),
            abs(len(left) - len(right)) + _TOP_HEAVY_PENALTY * (len(left) > len(right)),
        )
        candidates.append((rank, cut))
    return candidates


def _dialogue_protected(words: list[str], index: int, *, keep_names: bool = True) -> bool:
    previous: str = words[index - 1]
    following: str = words[index]
    tail: str = _tail(previous)
    clean: str = _clean(previous)
    if is_false_sentence_break(tail, following):
        return True
    if tail[-1:] in SENTENCE_ENDINGS + ",;:":
        return False
    if _protected(words, index) or previous in _DIALOGUE_DASHES:
        return True
    if clean == "nie" or clean in _TITLE_HEADS:
        return True
    return (
        (keep_names and _names_pair(previous, following))
        or (len(clean) == 1 and clean.isalpha() and clean.isascii())
        or unicodedata.category(previous[-1]) in {"Ps", "Pi"}
        or following[0] in CLOSING_MARKS + ",.;:!?%"
        or (clean == "się" and index > 1 and _clean(words[index - 2]) in _REFLEXIVE_HEADS)
    )


def _names_pair(previous: str, following: str) -> bool:
    return previous[0].isupper() and following[0].isupper() and not previous.isupper() and not following.isupper()


def _syntactic_risk(words: list[str], index: int) -> bool:
    previous: str = words[index - 1]
    following: str = words[index]
    clean: str = _clean(previous)
    if _tail(previous)[-1:] in SENTENCE_ENDINGS + ",;:":
        return False
    return clean in _PRONOUN_HEADS | _VERB_HEADS | _CONJUNCTIONS or (
        clean.endswith(_ADJECTIVE_ENDINGS) and _clean(following) not in _NON_BREAKING_HEADS | _CONJUNCTIONS
    )


def _boundary_rank(words: list[str], index: int) -> int:
    tail: str = _tail(words[index - 1])
    if tail[-1:] in SENTENCE_ENDINGS:
        return 0
    if _starts_conjunction(words, index):
        return 1
    if tail[-1:] in ",;:":
        return 2
    return 3


def _tail(word: str) -> str:
    return word.rstrip(CLOSING_MARKS + '"')


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
        # The +1 base keeps multipliers meaningful for a cut exactly at the
        # centre; a bare zero distance would erase every penalty and bonus.
        distance = float(abs(cut - center)) + 1.0
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
    if _clean(prev_word) in _CONJUNCTIONS:
        return _TRAILING_CONJUNCTION_PENALTY
    if _starts_conjunction(words, word_index):
        return 1 / 3
    return 1.0


def _protected(words: list[str], word_index: int) -> bool:
    """True when a cut before ``words[word_index]`` would break a fixed phrase."""
    if _clean(words[word_index]) == "się" or _clean(words[word_index - 1]) in _NON_BREAKING_HEADS:
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


__all__ = ["DEFAULT_MAX_CHARS", "MAX_LINES", "split_for_layout", "split_line"]
