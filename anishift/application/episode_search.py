"""Source contracts for paged episode acquisition and complete torrent inventories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from anishift.application.episode_releases import TsukiHimeFiles
    from anishift.application.episode_selection import StreamCandidate


@dataclass(frozen=True, slots=True)
class TextPage:
    """One source page with an optional advertised total result count."""

    streams: tuple[StreamCandidate, ...]
    total: int | None


class PagedSource(Protocol):
    """Text source returning exactly one page per request."""

    def search(self, phrase: str, page: int) -> TextPage:
        """Fetch one zero-based page of results."""
        ...


@dataclass(frozen=True, slots=True)
class TsukiHimePage:
    """Episode releases with the server's pagination metadata."""

    streams: tuple[StreamCandidate, ...]
    total: int
    start: int
    limit: int


@dataclass(frozen=True, slots=True)
class TsukiHimeLookup:
    """HTTP lookup outcome with an optional ID and only a complete, nonempty inventory."""

    status: int
    torrent_id: int | None = None
    files: TsukiHimeFiles | None = None


class TsukiHimeApi(Protocol):
    """Single-request boundary for title, episode and torrent metadata."""

    def anime_id(self, anilist_id: int) -> int | None:
        """Resolve AniList to the source title ID, or return None for 404."""
        ...

    def episode_page(self, anime_id: int, number: int, offset: int) -> TsukiHimePage:
        """Fetch one episode page using an offset."""
        ...

    def torrent_by_hash(self, info_hash: str) -> TsukiHimeLookup:
        """Read one hash lookup without automatically fetching torrent details."""
        ...

    def torrent_files(self, torrent_id: int) -> TsukiHimeLookup:
        """Read one torrent detail response and validate inventory completeness."""
        ...
