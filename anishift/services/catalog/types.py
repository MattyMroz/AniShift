"""Title candidate contract returned by an anime catalog."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final

# ── Constants ─────────────────────────────────────────────────────────────────

_COUR_RE: Final[re.Pattern[str]] = re.compile(r"\b(?:part|cour)\s*\d+\b", re.IGNORECASE)
"""Marker of a later broadcast block of one season, which the catalog lists as its own entry."""


class TitleStatus(StrEnum):
    """Airing state of one catalog title."""

    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EpisodeAiring:
    """A numbered episode and its known UTC airing instant."""

    episode: int
    airing_at: datetime | None


@dataclass(frozen=True, slots=True)
class SeasonAiring:
    """The known schedule and airing status of one explicitly identified season."""

    anilist_id: int
    status: TitleStatus
    episode_count: int | None
    episodes: tuple[EpisodeAiring, ...]
    start_date: date | None = None


def is_cour_title(*names: str | None) -> bool:
    """Whether any of *names* marks a later cour of one season instead of a new season."""
    return any(_COUR_RE.search(name) is not None for name in names if name)


@dataclass(frozen=True, slots=True)
class PrequelEntry:
    """One catalog entry airing before a title."""

    episodes: int
    cour: bool


@dataclass(frozen=True, slots=True)
class TitleCandidate:
    """One anime title as the catalog describes it."""

    anilist_id: int
    romaji: str
    english: str | None
    native: str | None
    synonyms: tuple[str, ...]
    year: int | None
    season: str | None
    format: str | None
    episodes: int | None
    status: TitleStatus
    prequel_ids: tuple[int, ...]

    def aliases(self) -> tuple[str, ...]:
        """Return the Latin-script names of this title, in catalog order, without repeats."""
        names: tuple[str | None, ...] = (self.romaji, self.english, *self.synonyms)
        seen: set[str] = set()
        aliases: list[str] = []
        for name in names:
            text: str = (name or "").strip()
            if not text or not _is_latin(text) or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            aliases.append(text)
        return tuple(aliases)

    def is_cour(self) -> bool:
        """Whether this entry continues the season before it instead of opening a new one."""
        return is_cour_title(self.romaji, self.english)

    def folder_title(self) -> str:
        """Return the name used for the library folder: English when known, else romaji."""
        english: str = (self.english or "").strip()
        return english or self.romaji


def _is_latin(text: str) -> bool:
    """Whether every letter and digit of *text* belongs to the Latin script."""
    return all(_is_latin_character(character) for character in text)


def _is_latin_character(character: str) -> bool:
    """Whether one character is punctuation, a space, or a Latin letter or digit."""
    if not character.isalnum():
        return True
    return unicodedata.name(character, "").startswith(("LATIN", "DIGIT"))
