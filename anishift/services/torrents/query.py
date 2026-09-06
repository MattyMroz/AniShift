"""Reading a user search phrase as a title plus an optional episode range."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

__all__ = ["EpisodeRange", "SearchQuery", "parse_query"]

# ── Constants ─────────────────────────────────────────────────────────────────

EPISODE_LABEL_PREFIX: Final[str] = "odc."
"""Polish word opening the episode label shown by the interface."""

RANGE_DASH: Final[str] = "–"
"""En dash separating both ends of an episode label."""

FIRST_CALENDAR_YEAR: Final[int] = 1900
"""Lowest bare number read as a release year instead of an episode."""

LAST_CALENDAR_YEAR: Final[int] = 2100
"""Highest bare number read as a release year instead of an episode."""

_EPISODE_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)(?:episode|odc|ep|e)?\.?\s*"
    r"(?:(?P<first>\d{1,4}(?:\.\d)?)(?:\s*(?P<dash>-)\s*(?P<last>\d{1,4}(?:\.\d)?)?)?"
    r"|-\s*(?P<upto>\d{1,4}(?:\.\d)?))$",
    re.IGNORECASE,
)
"""Trailing episode marker: an optional word, one number, and an optional range."""


@dataclass(frozen=True, slots=True)
class EpisodeRange:
    """Closed, half-open, or open-ended span of episode numbers.

    At least one end is always known; ``first`` alone means "from here on".
    """

    first: Decimal | None
    last: Decimal | None

    @property
    def label(self) -> str:
        """Return the Polish label shown next to the results, such as ``odc. 4–10``."""
        if self.first is not None and self.first == self.last:
            return f"{EPISODE_LABEL_PREFIX} {self.first}"
        first_text: str = "" if self.first is None else str(self.first)
        last_text: str = "" if self.last is None else str(self.last)
        return f"{EPISODE_LABEL_PREFIX} {first_text}{RANGE_DASH}{last_text}"

    def contains(self, episode: Decimal) -> bool:
        """Whether *episode* falls inside this span."""
        below: bool = self.first is not None and episode < self.first
        above: bool = self.last is not None and episode > self.last
        return not (below or above)


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Search intent read from one typed phrase."""

    title: str
    episodes: EpisodeRange | None


def parse_query(text: str) -> SearchQuery:
    """Split *text* into a title and the episode range its trailing marker asks for.

    A number that reads as a year or carries a resolution suffix stays part of the title,
    and a marker that would leave no title is kept as the title instead.
    """
    collapsed: str = " ".join(text.split())
    match: re.Match[str] | None = _EPISODE_MARKER_RE.search(collapsed)
    if match is None:
        return SearchQuery(title=collapsed, episodes=None)
    episodes: EpisodeRange | None = _range_of(match)
    title: str = collapsed[: match.start()].strip()
    if episodes is None or not title:
        return SearchQuery(title=collapsed, episodes=None)
    return SearchQuery(title=title, episodes=episodes)


def _range_of(match: re.Match[str]) -> EpisodeRange | None:
    """Build the span the marker describes, or ``None`` when it is not an episode."""
    upto: str | None = match.group("upto")
    if upto is not None:
        return EpisodeRange(first=None, last=Decimal(upto))
    first: Decimal = Decimal(match.group("first"))
    if match.group("dash") is None:
        return None if _is_year(first) else EpisodeRange(first=first, last=first)
    last: str | None = match.group("last")
    return EpisodeRange(first=first, last=None if last is None else Decimal(last))


def _is_year(number: Decimal) -> bool:
    """Whether a bare number reads as a release year rather than an episode."""
    return FIRST_CALENDAR_YEAR <= number <= LAST_CALENDAR_YEAR
