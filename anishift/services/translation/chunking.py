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
import unicodedata
from collections.abc import Callable
from typing import Final

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_CHAR_LIMIT: Final[int] = 750
"""Default maximum size of one output chunk (one translator request)."""

DEFAULT_CHUNK_LIMIT: Final[int] = 250
"""Default maximum size of the natural pieces chunks are packed from."""

_LATIN_SENTENCE_ENDINGS: Final[str] = ".!?…"
"""Sentence-ending marks that need trailing whitespace to end a sentence."""

_CJK_SENTENCE_ENDINGS: Final[str] = "。！？"  # noqa: RUF001 - fullwidth CJK marks are intentional
"""Fullwidth marks that end a sentence even without trailing whitespace."""

SENTENCE_ENDINGS: Final[str] = _LATIN_SENTENCE_ENDINGS + _CJK_SENTENCE_ENDINGS
"""Sentence-ending marks (Latin plus fullwidth CJK); shared with linebreak."""

ZERO_WIDTH: Final[str] = "\u200b"
"""Zero-width space some subtitle sources emit after a sentence mark."""

_APOSTROPHES: Final[str] = "'’"  # noqa: RUF001 - typographic apostrophe is intentional
"""Apostrophes (ASCII and typographic) are excluded so ``don't`` stays whole."""


def _punctuation_chars(categories: frozenset[str], *, exclude: str) -> str:
    """Return every Unicode character whose category is in ``categories``.

    Built from ``unicodedata`` so every script is covered without hand-written
    per-language lists; ``exclude`` removes characters handled elsewhere.
    """
    excluded = set(exclude)
    return "".join(
        char
        for code_point in range(0x110000)
        if (char := chr(code_point)) not in excluded and unicodedata.category(char) in categories
    )


_PHRASE_CUT_CHARS: Final[str] = _punctuation_chars(
    frozenset({"Pd", "Pe", "Pf", "Po"}),
    exclude=SENTENCE_ENDINGS + _APOSTROPHES,
)
"""Phrase separators of every script.

Opening marks (categories ``Ps``/``Pi``) are excluded because a phrase never
starts right after an opening bracket or quote.
"""

_CLOSING_MARKS: Final[str] = _punctuation_chars(frozenset({"Pe", "Pf"}), exclude="")
"""Closing brackets and final quotes of every script.

A sentence never breaks right before one of these - the closer stays glued to
the sentence it closes.
"""

# source: https://en.wiktionary.org/wiki/Category:English_abbreviations
_ABBREVIATIONS_EN: Final[frozenset[str]] = frozenset(
    [
        "adm",
        "al",
        "approx",
        "apr",
        "apt",
        "assn",
        "assoc",
        "aug",
        "ave",
        "blvd",
        "bros",
        "ca",
        "capt",
        "cf",
        "ch",
        "chap",
        "co",
        "col",
        "comdr",
        "corp",
        "cpl",
        "dec",
        "dept",
        "dist",
        "div",
        "dr",
        "ed",
        "eg",
        "esp",
        "est",
        "etc",
        "feb",
        "fig",
        "fr",
        "gen",
        "gov",
        "govt",
        "hon",
        "ie",
        "inc",
        "incl",
        "jan",
        "jr",
        "jul",
        "jun",
        "lieut",
        "lt",
        "ltd",
        "maj",
        "mar",
        "max",
        "messrs",
        "min",
        "misc",
        "mount",
        "mr",
        "mrs",
        "ms",
        "mt",
        "no",
        "nov",
        "obj",
        "oct",
        "orig",
        "p",
        "par",
        "pp",
        "prof",
        "rd",
        "ref",
        "rev",
        "sec",
        "sep",
        "sept",
        "sgt",
        "sir",
        "sr",
        "st",
        "subj",
        "transl",
        "univ",
        "viz",
        "vol",
        "vs",
    ]
)
"""English abbreviations written with a trailing dot (support for the capitalised-word case)."""

# source: https://pl.wikipedia.org/wiki/Wikipedia:Skróty
_ABBREVIATIONS_PL: Final[frozenset[str]] = frozenset(
    [
        "adm",
        "afryk",
        "al",
        "alb",
        "alg",
        "amer",
        "argent",
        "arm",
        "art",
        "austr",
        "austral",
        "azerb",
        "azjat",
        "b",
        "bp",
        "bryt",
        "cd",
        "cdn",
        "cieśn",
        "cs",
        "cz",
        "dn",
        "doc",
        "dol",
        "dop",
        "dr",
        "duń",
        "dyr",
        "dzis",
        "el",
        "fl",
        "gen",
        "gm",
        "godz",
        "gr",
        "hab",
        "im",
        "inst",
        "inż",
        "itd",
        "itp",
        "jask",
        "jez",
        "jw",
        "k",
        "kan",
        "kl",
        "kol",
        "kpt",
        "ks",
        "l",
        "lic",
        "lp",
        "m",
        "marsz",
        "mec",
        "mgr",
        "mies",
        "mjr",
        "mld",
        "mln",
        "nadl",
        "nast",
        "ndm",
        "np",
        "nr",
        "o",
        "ob",
        "ok",
        "os",
        "pkt",
        "pl",
        "plut",
        "płk",
        "płw",
        "pn",
        "pol",
        "por",
        "pow",
        "ppor",
        "ppoż",
        "prof",
        "przeł",
        "przyl",
        "ps",
        "pt",
        "pust",
        "pw",
        "r",
        "red",
        "ryc",
        "rys",
        "rz",
        "s",
        "scs",
        "sierż",
        "ss",
        "st",
        "str",
        "szt",
        "św",
        "tab",
        "tel",
        "tj",
        "trb",
        "trl",
        "tys",
        "tzn",
        "tzw",
        "ul",
        "ur",
        "viz",
        "wdp",
        "wg",
        "wł",
        "właśc",
        "woj",
        "wulg",
        "ww",
        "wyb",
        "zam",
        "zat",
        "zb",
        "zm",
        "zob",
    ]
)
"""Polish abbreviations written with a trailing dot (support for the capitalised-word case)."""

_ABBREVIATIONS: Final[frozenset[str]] = _ABBREVIATIONS_EN | _ABBREVIATIONS_PL
"""Support list for the ambiguous dot followed by a capitalised word."""

_RE_PARAGRAPH_SEP: Final[re.Pattern[str]] = re.compile(r"((?:\r?\n\s*){2,})")
"""Blank-line paragraph separator."""

_RE_SENTENCE_SEP: Final[re.Pattern[str]] = re.compile(
    "(["
    + re.escape(_LATIN_SENTENCE_ENDINGS)
    + "]+[\\s"
    + ZERO_WIDTH
    + "]+|["
    + re.escape(_CJK_SENTENCE_ENDINGS)
    + "]+(?!["
    + re.escape(_CLOSING_MARKS)
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

_RE_DOTTED_TAIL: Final[re.Pattern[str]] = re.compile("(\\w+)\\.[\\s" + ZERO_WIDTH + "]*$")
"""A word plus exactly one trailing dot; runs like ``...``/``?!`` never match."""


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
        if pieces and _is_false_sentence_break(pieces[-1], part):
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


def _is_false_sentence_break(previous: str, following: str) -> bool:
    """Return True when the dot ending ``previous`` is an abbreviation dot.

    Language-independent heuristics run first: a lowercase continuation
    (``np. taki``, ``ca. fünf``, ``w 1798. roku``) or a single-letter initial
    (``A. Mickiewicz``) never ends a sentence. The abbreviation list only
    decides the remaining case of a capitalised word after the dot.
    """
    tail = _RE_DOTTED_TAIL.search(previous)
    if tail is None:
        return False
    first_letter = next((char for char in following if char.isalpha()), "")
    if first_letter.islower():
        return True
    token = tail.group(1)
    if len(token) == 1 and token.isalpha():
        return True
    return token.lower() in _ABBREVIATIONS


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
        return [text[start : start + limit] for start in range(0, len(text), limit)]
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
