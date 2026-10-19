"""Agreement of a Polish adjective with a neighbouring noun from Morfeusz 2 analyses, without disambiguation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Final

import morfeusz2  # type: ignore[import-untyped]

from anishift.text.gaps import word_core

__all__ = ["agrees"]


@dataclass(frozen=True, slots=True)
class _Reading:
    part: str
    number: str
    cases: frozenset[str]
    genders: frozenset[str]


# ── Constants ─────────────────────────────────────────────────────────────────

_ADJECTIVES: Final[frozenset[str]] = frozenset({"adj", "pact", "ppas"})
"""Morfeusz parts of speech of an adjective or an adjectival participle."""

_NOUNS: Final[frozenset[str]] = frozenset({"subst", "depr", "ger"})
"""Morfeusz parts of speech of a noun, a depreciative noun or a gerund."""

_VERBS: Final[frozenset[str]] = frozenset(
    {"fin", "bedzie", "aglt", "praet", "impt", "imps", "inf", "pcon", "pant", "winien"}
)
"""Morfeusz parts of speech of a verb form; a word with such a reading never counts as agreeing."""

_INFLECTED_FIELDS: Final[int] = 4
"""Tag fields up to the gender: part of speech, number, case and gender."""


def agrees(left: str, right: str) -> bool:
    """Return whether ``left`` and ``right`` can be read as an adjective and a noun agreeing with each other."""
    if not left or unicodedata.category(left[-1]).startswith("P"):
        return False
    lefts: tuple[_Reading, ...] | None = _readings(word_core(left))
    rights: tuple[_Reading, ...] | None = _readings(word_core(right))
    if lefts is None or rights is None:
        return False
    return any(_agree(first, second) for first in lefts for second in rights)


def _agree(first: _Reading, second: _Reading) -> bool:
    if {first.part in _ADJECTIVES, second.part in _ADJECTIVES} != {True, False}:
        return False
    return first.number == second.number and bool(first.cases & second.cases) and bool(first.genders & second.genders)


@cache
def _readings(word: str) -> tuple[_Reading, ...] | None:
    if not word:
        return None
    readings: list[_Reading] = []
    for start, end, (_, _, tag, _, _) in _analyser().analyse(word):
        fields: list[str] = tag.split(":")
        if start != 0 or end != 1 or fields[0] in _VERBS:
            return None
        if fields[0] in _ADJECTIVES | _NOUNS and len(fields) >= _INFLECTED_FIELDS:
            readings.append(
                _Reading(fields[0], fields[1], frozenset(fields[2].split(".")), frozenset(fields[3].split(".")))
            )
    return tuple(readings)


@cache
def _analyser() -> morfeusz2.Morfeusz:
    return morfeusz2.Morfeusz()
