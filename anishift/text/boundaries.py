"""Unicode punctuation and sentence-boundary primitives."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

# ── Constants ─────────────────────────────────────────────────────────────────

LATIN_SENTENCE_ENDINGS: Final[str] = ".!?…"
"""Sentence-ending marks that need trailing whitespace to end a sentence."""

CJK_SENTENCE_ENDINGS: Final[str] = "。！？"  # noqa: RUF001 - fullwidth CJK marks are intentional
"""Fullwidth marks that can end a sentence without trailing whitespace."""

SENTENCE_ENDINGS: Final[str] = LATIN_SENTENCE_ENDINGS + CJK_SENTENCE_ENDINGS
"""Sentence-ending marks used by translation, TTS and subtitle line breaking."""

ZERO_WIDTH: Final[str] = "\u200b"
"""Zero-width space some subtitle sources emit after a sentence mark."""

_APOSTROPHES: Final[str] = "'’"  # noqa: RUF001 - typographic apostrophe is intentional
"""Apostrophes excluded from phrase boundaries so contractions stay whole."""


def _punctuation_chars(categories: frozenset[str], *, exclude: str) -> str:
    """Return Unicode characters in the requested categories."""
    excluded: set[str] = set(exclude)
    return "".join(
        character
        for code_point in range(0x110000)
        if (character := chr(code_point)) not in excluded and unicodedata.category(character) in categories
    )


PHRASE_CUT_CHARS: Final[str] = _punctuation_chars(
    frozenset({"Pd", "Pe", "Pf", "Po"}),
    exclude=SENTENCE_ENDINGS + _APOSTROPHES,
)
"""Phrase separators from every Unicode script, excluding opening marks."""

CLOSING_MARKS: Final[str] = _punctuation_chars(frozenset({"Pe", "Pf"}), exclude="")
"""Closing brackets and final quotes kept with the text they close."""

_ABBREVIATIONS_EN: Final[frozenset[str]] = frozenset(
    {
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
    }
)
"""English abbreviations written with a trailing dot."""

_ABBREVIATIONS_PL: Final[frozenset[str]] = frozenset(
    {
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
    }
)
"""Polish abbreviations written with a trailing dot."""

_ABBREVIATIONS: Final[frozenset[str]] = _ABBREVIATIONS_EN | _ABBREVIATIONS_PL
"""Known abbreviations used only for ambiguous capitalised continuations."""

_RE_DOTTED_TAIL: Final[re.Pattern[str]] = re.compile(r"(\w+)\.[\s\u200b]*$")
"""A word followed by exactly one trailing dot."""


def period_ends_sentence(
    token: str,
    following: str,
    *,
    previous_character: str = "",
    next_character: str = "",
) -> bool:
    """Return whether a dot after ``token`` is a sentence boundary."""
    if previous_character.isdigit() and next_character.isdigit():
        return False
    first_letter: str = next((character for character in following if character.isalpha()), "")
    if first_letter.islower():
        return False
    if len(token) == 1 and token.isalpha():
        return False
    return token.casefold() not in _ABBREVIATIONS


def is_false_sentence_break(previous: str, following: str) -> bool:
    """Return whether the trailing dot in ``previous`` is not a sentence end."""
    tail: re.Match[str] | None = _RE_DOTTED_TAIL.search(previous)
    if tail is None:
        return False
    token: str = tail.group(1)
    return not period_ends_sentence(token, following)
