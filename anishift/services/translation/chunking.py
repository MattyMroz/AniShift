"""Multilingual text chunking for the plain-text (txt) translation path.

Cuts text in any language into translator-sized chunks at natural boundaries.
Cut points come from characters alone (ASCII plus Unicode punctuation), never
per-language word lists, so one code path handles EN/JP/PL and the rest. Two
limits drive it: text is broken into pieces of at most ``chunk_limit`` chars
(paragraph -> sentence -> phrase -> word), then packed up to ``char_limit``;
concatenating the chunks restores the input exactly. An ambiguous sentence dot
is resolved NLTK-Punkt style: heuristic first (lowercase continuation,
single-letter initial), then an abbreviation list for the ``Dr. Smith`` case.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from anishift.text.boundaries import (
    CJK_SENTENCE_ENDINGS,
    CLOSING_MARKS,
    LATIN_SENTENCE_ENDINGS,
    PHRASE_CUT_CHARS,
    SENTENCE_ENDINGS,
    ZERO_WIDTH,
    is_false_sentence_break,
)
from anishift.text.graphemes import hard_split_graphemes

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_CHAR_LIMIT: Final[int] = 750
"""Default maximum size of one output chunk (one translator request)."""

DEFAULT_CHUNK_LIMIT: Final[int] = 250
"""Default maximum size of the natural pieces chunks are packed from."""

_PHRASE_CUT_CHARS: Final[str] = PHRASE_CUT_CHARS
"""Compatibility alias for callers that inspect the translation cut set."""

_RE_PARAGRAPH_SEP: Final[re.Pattern[str]] = re.compile(r"((?:\r?\n\s*){2,})")
"""Blank-line paragraph separator."""

_RE_SENTENCE_SEP: Final[re.Pattern[str]] = re.compile(
    "(["
    + re.escape(LATIN_SENTENCE_ENDINGS)
    + "]+[\\s"
    + ZERO_WIDTH
    + "]+|["
    + re.escape(CJK_SENTENCE_ENDINGS)
    + "]+(?!["
    + re.escape(CLOSING_MARKS)
    + "])[\\s"
    + ZERO_WIDTH
    + "]*)"
)
"""A run of sentence-ending marks, plus the whitespace that follows it.

Latin marks need trailing whitespace (``e.g.`` mid-word dots must not split);
CJK fullwidth marks end a sentence even with no space, unless a closing quote
or bracket follows.
"""

_RE_PHRASE_SEP: Final[re.Pattern[str]] = re.compile("([" + re.escape(_PHRASE_CUT_CHARS) + "]+\\s*)")
"""A run of phrase-cut punctuation plus the whitespace that follows it."""

_RE_WORD_SEP: Final[re.Pattern[str]] = re.compile(r"(\s+)")
"""Whitespace between words."""


def _rejoin(tokens: list[str]) -> list[str]:
    """Merge ``re.split`` capture output back into whole pieces.

    Each captured separator is reattached to the piece on its left, so
    concatenating the result restores the input exactly.
    """
    pieces: list[str] = []
    for index in range(0, len(tokens), 2):
        separator = tokens[index + 1] if index + 1 < len(tokens) else ""
        part = tokens[index] + separator
        if part:
            pieces.append(part)
    return pieces


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on blank lines, separators kept attached."""
    return _rejoin(_RE_PARAGRAPH_SEP.split(text))


def split_sentences(text: str) -> list[str]:
    """Split text into sentences; an abbreviation dot does not end a sentence."""
    tokens = _RE_SENTENCE_SEP.split(text)
    pieces: list[str] = []
    for index in range(0, len(tokens), 2):
        separator = tokens[index + 1] if index + 1 < len(tokens) else ""
        part = tokens[index] + separator
        if not part:
            continue
        if pieces and is_false_sentence_break(pieces[-1], part):
            pieces[-1] += part
        else:
            pieces.append(part)
    return pieces


def split_phrases(sentence: str) -> list[str]:
    """Split a sentence into phrases after commas, dashes and closing marks."""
    return _rejoin(_RE_PHRASE_SEP.split(sentence))


def split_words(phrase: str) -> list[str]:
    """Split a phrase into words, whitespace kept attached to the left word."""
    return _rejoin(_RE_WORD_SEP.split(phrase))


_SPLITTERS: Final[tuple[Callable[[str], list[str]], ...]] = (
    split_paragraphs,
    split_sentences,
    split_phrases,
    split_words,
)
"""Boundary finders ordered from the widest cut to the narrowest."""


def _break(text: str, limit: int, level: int = 0) -> list[str]:
    """Break ``text`` into natural pieces of at most ``limit`` characters.

    Tries each splitter in ``_SPLITTERS`` order and recurses one level deeper
    only into pieces that are still oversized; a word longer than the limit is
    hard-cut as the last resort.
    """
    if len(text) <= limit:
        return [text]
    if level == len(_SPLITTERS):
        return hard_split_graphemes(text, limit)
    pieces: list[str] = []
    for part in _SPLITTERS[level](text):
        if len(part) <= limit:
            pieces.append(part)
        else:
            pieces.extend(_break(part, limit, level + 1))
    return pieces


def _pack(pieces: list[str], limit: int) -> list[str]:
    """Greedily join consecutive pieces without exceeding ``limit`` characters."""
    chunks: list[str] = []
    group: list[str] = []
    group_size = 0
    for piece in pieces:
        if group and group_size + len(piece) > limit:
            chunks.append("".join(group))
            group = []
            group_size = 0
        group.append(piece)
        group_size += len(piece)
    if group:
        chunks.append("".join(group))
    return chunks


def phrase_cut_chars() -> str:
    """Return every Unicode phrase-cut char; shared with ``linebreak`` as the one cutting base."""
    return _PHRASE_CUT_CHARS


def chunk_text(
    text: str,
    *,
    char_limit: int = DEFAULT_CHAR_LIMIT,
    chunk_limit: int = DEFAULT_CHUNK_LIMIT,
) -> list[str]:
    """Split ``text`` into translator-sized chunks at natural boundaries.

    The text is first broken into pieces no longer than ``chunk_limit``
    (paragraph -> sentence -> phrase -> word), then consecutive pieces are
    packed back together up to ``char_limit``, so every chunk boundary falls
    on a natural cut. A smaller ``chunk_limit`` packs chunks tighter.

    Args:
        text: Full text in any language.
        char_limit: Maximum characters of one output chunk.
        chunk_limit: Maximum characters of the pieces chunks are packed from.

    Returns:
        Chunks in reading order; concatenating them restores ``text`` exactly.
    """
    if not text:
        return []
    pieces = _break(text, min(chunk_limit, char_limit))
    return _pack(pieces, char_limit)


__all__ = [
    "DEFAULT_CHAR_LIMIT",
    "DEFAULT_CHUNK_LIMIT",
    "SENTENCE_ENDINGS",
    "ZERO_WIDTH",
    "chunk_text",
    "phrase_cut_chars",
    "split_paragraphs",
    "split_phrases",
    "split_sentences",
    "split_words",
]
