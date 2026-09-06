"""Title candidate contract returned by an anime catalog."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class TitleStatus(StrEnum):
    """Airing state of one catalog title."""

    FINISHED = "FINISHED"
    RELEASING = "RELEASING"
    NOT_YET_RELEASED = "NOT_YET_RELEASED"
    CANCELLED = "CANCELLED"
    HIATUS = "HIATUS"
    UNKNOWN = "UNKNOWN"


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
        """Return the Latin-script names of this title, in catalog order, without repeats.

        Names written in another script are dropped because the release index is searched
        with these values and only matches Latin release titles.
        """
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
