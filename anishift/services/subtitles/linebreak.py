"""Lay out translated dialogue with the layout core and re-split displayed text into authored verses."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.geometry import measure_text, safe_width, style_changes, wrap_text
from anishift.services.subtitles.layout import (
    DEFAULT_MAX_CHARS,
    DIALOGUE_MAX_WIDTH,
    MAX_LINES,
    Field,
    Flag,
    Layout,
    chars_measure,
    dialogue_field,
    lay_out,
)
from anishift.services.subtitles.text import (
    RE_TAG_BLOCK,
    reflow_visible_text,
    replace_visible_text,
    restore_markers,
    visible_text,
)
from anishift.text.boundaries import BREAKABLE_SPACES, PHRASE_CUT_CHARS, SENTENCE_ENDINGS
from anishift.text.gaps import CONJUNCTIONS, CONJUNCTIONS_MULTIWORD, PREPOSITIONS, PREPOSITIONS_MULTIWORD
from anishift.text.markers import strip_span_markers

if TYPE_CHECKING:
    from pysubs2 import SSAEvent, SSAStyle

    from anishift.services.subtitles.geometry import RenderProfile
    from anishift.services.subtitles.layout import Measure

# ── Constants ──────────────────────────────────────────────────────────────

_STRONG_CUT: Final[str] = SENTENCE_ENDINGS + ":"
"""Strong cut points (sentence endings plus colon); cut just after the mark."""

_WEAK_CUT: Final[str] = PHRASE_CUT_CHARS
"""Weak cut points: every Unicode phrase separator (commas, dashes, closers)."""

_TRAILING_PUNCT: Final[str] = _STRONG_CUT + _WEAK_CUT
"""Characters stripped from a word before matching it against the word lists."""

_MAX_PHRASE_WORDS: Final[int] = 4
"""Longest multi-word phrase looked up (``w związku z czym``)."""

_LAYOUT_WINDOW_MIN_CHARS: Final[int] = 8
"""Smallest search window around one proportional layout boundary target."""

_TRAILING_CONJUNCTION_PENALTY: Final[float] = 8.0
"""Distance multiplier for a cut that leaves a conjunction ending the line."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Whitespace run, collapsed to a single space before splitting."""

_RE_WORD_BREAK: Final[re.Pattern[str]] = re.compile(r"(\{[^}]*\}|\\[Nn]|" + BREAKABLE_SPACES.pattern + ")")
"""Override block, line break escape or breakable whitespace run of tagged event text."""

_NO_WRAP: Final[str] = "{\\q2}"
"""Override that stops libass from wrapping the lines the layout core chose."""


@dataclass(frozen=True, slots=True)
class DialogueLayout:
    """Laid-out event text of one dialogue line, the rescue steps its layout needed and its measurement quality."""

    text: str
    flags: frozenset[Flag]
    approximate: bool = False


def layout_dialogue(event: SSAEvent, text: str, profile: RenderProfile | None) -> DialogueLayout:
    """Lay out the unbroken translation ``text`` of a dialogue event and place it in the event with its tags.

    Without a render profile (SRT) lines are measured by their graphemes; otherwise with the event's fonts and the
    tags of each line, inside the safe screen area from the event's anchor, and libass never wraps the chosen lines.
    """
    tagged: str = _tagged_line(event, text, profile)
    plain: str = visible_text(tagged, preserve_hard_spaces=True)
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(plain) if word)
    if profile is None:
        chosen: Layout = lay_out(plain, dialogue_field(), chars_measure)
        return DialogueLayout(reflow_visible_text(tagged, chosen.lines), chosen.flags)
    field: Field = dialogue_field(max_width=safe_width(event, profile, DIALOGUE_MAX_WIDTH) / profile.play_res_x)
    changes: tuple[bool, ...] = style_changes(event, tagged, profile)
    if len(changes) == len(words) - 1:
        field = replace(field, style_breaks=frozenset(index for index, change in enumerate(changes) if change))
    chosen = lay_out(plain, field, _measure(event, profile, words, _tagged_words(tagged, words)))
    laid_out: str = reflow_visible_text(tagged, chosen.lines)
    if wrap_text(event, laid_out, profile) != laid_out:
        laid_out = _NO_WRAP + laid_out
    approximate: bool = measure_text(event, laid_out, profile).status == "approximate"
    return DialogueLayout(laid_out, chosen.flags, approximate)


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


def _split(text: str, max_chars: int, budget: int) -> tuple[str, ...]:
    """Recursively split ``text`` into at most ``budget`` verses."""
    if len(text) <= max_chars or " " not in text or budget <= 1:
        return (text,)
    point: int = _best_cut(text, max_chars)
    left = text[:point].strip()
    right = text[point:].strip()
    if not left or not right:
        return (text,)
    verses = _split(left, max_chars, budget - 1)
    return verses + _split(right, max_chars, budget - len(verses))


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
    if _clean(prev_word) in CONJUNCTIONS:
        return _TRAILING_CONJUNCTION_PENALTY
    if _starts_conjunction(words, word_index):
        return 1 / 3
    return 1.0


def _protected(words: list[str], word_index: int) -> bool:
    """True when a cut before ``words[word_index]`` would break a fixed phrase."""
    if _clean(words[word_index]) == "się" or _clean(words[word_index - 1]) in PREPOSITIONS:
        return True
    for length in range(2, _MAX_PHRASE_WORDS + 1):
        for start in range(max(0, word_index - length + 1), word_index):
            end = start + length
            if end > len(words) or word_index >= end:
                continue
            phrase = tuple(_clean(w) for w in words[start:end])
            if phrase in PREPOSITIONS_MULTIWORD or phrase in CONJUNCTIONS_MULTIWORD:
                return True
    return False


def _starts_conjunction(words: list[str], word_index: int) -> bool:
    """True when ``words[word_index]`` begins a conjunction (single or phrase)."""
    if _clean(words[word_index]) in CONJUNCTIONS:
        return True
    return any(
        tuple(_clean(w) for w in words[word_index : word_index + length]) in CONJUNCTIONS_MULTIWORD
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


def _tagged_line(event: SSAEvent, text: str, profile: RenderProfile | None) -> str:
    plain: str = strip_span_markers(text)
    if visible_text(event.text) == visible_text(plain):
        return event.text
    style: SSAStyle | None = profile.styles.get(event.style) if profile is not None else None
    return replace_visible_text(event.text, restore_markers(text, (plain,))[0], style)


def _tagged_words(tagged: str, words: tuple[str, ...]) -> tuple[str, ...]:
    found: list[str] = [""]
    for piece in _RE_WORD_BREAK.split(tagged):
        if RE_TAG_BLOCK.fullmatch(piece) or not _RE_WORD_BREAK.fullmatch(piece):
            found[-1] += piece
        elif visible_text(found[-1]):
            found.append("")
    if len(found) > 1 and not visible_text(found[-1]):
        found[-2] += found.pop()
    visible: tuple[str, ...] = tuple(visible_text(word, preserve_hard_spaces=True) for word in found)
    return tuple(found) if visible == words else words


def _measure(event: SSAEvent, profile: RenderProfile, words: tuple[str, ...], tagged: tuple[str, ...]) -> Measure:
    spans: dict[str, list[str]] = {}
    prefix: str = ""
    for start in range(len(words)):
        for end in range(start + 1, len(words) + 1):
            spans.setdefault(" ".join(words[start:end]), []).append(prefix + " ".join(tagged[start:end]))
        prefix += "".join(RE_TAG_BLOCK.findall(tagged[start]))

    def width(line: str, fx: float) -> float:
        texts: list[str] = spans.get(line, [line])
        return max(measure_text(event, text, profile, fx=fx).width for text in texts) / profile.play_res_x

    return width


__all__ = ["DialogueLayout", "layout_dialogue", "split_for_layout"]
