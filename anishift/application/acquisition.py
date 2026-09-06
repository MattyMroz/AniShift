"""Release discovery and download hand-off through one torrent source and one torrent client."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from anishift.errors import AniShiftError
from anishift.services.torrents.names import season_hint, strip_season
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from anishift.services.catalog import TitleCandidate
    from anishift.services.torrents import Release, ReleaseName, TorrentInfo
    from anishift.services.torrents.query import EpisodeRange

__all__ = [
    "DOWNLOAD_CATEGORY",
    "MAX_GROUP_QUERIES",
    "MIN_RESOLUTION",
    "TITLE_SEARCH_LIMIT",
    "AcquisitionService",
    "CatalogOrder",
    "ClientStatus",
    "DownloadReceipt",
    "EpisodeReading",
    "ReleaseCatalog",
    "ReleaseChoice",
    "SeasonContext",
    "SeriesGroup",
    "TitleCatalog",
    "TorrentClient",
    "TorrentSource",
    "catalog_releases",
    "read_episode",
    "series_directory_name",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_RESOLUTION: Final[int] = 1080
"""Lowest vertical resolution a release must declare to be listed."""

DOWNLOAD_CATEGORY: Final[str] = "AniShift"
"""Category every torrent added by AniShift carries inside the client."""

MAX_GROUP_QUERIES: Final[int] = 5
"""Release groups asked for their own complete listing after a title search."""

TITLE_SEARCH_LIMIT: Final[int] = 7
"""Title candidates a catalog is asked for by default."""

INCOMPLETE_EXTENSION_PREFERENCE: Final[str] = "incomplete_files_ext"
"""Client preference appending ``.!qB`` to files still being downloaded, which the watch skips."""

_INVALID_NAME_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
"""Characters Windows refuses inside one path component."""

_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)
"""Device names Windows refuses as a file or directory name regardless of extension."""

_FALLBACK_DIRECTORY: Final[str] = "Nieznana seria"
"""Directory used when a release title leaves nothing usable for a folder name."""


class TorrentSource(Protocol):
    """Index of public releases answering one free-text title query."""

    def search(self, query: str) -> tuple[Release, ...]:
        """Return the releases matching *query*, newest first as the index lists them."""
        ...


class TitleCatalog(Protocol):
    """Anime catalog naming the title behind a human phrase and how deep its season sits."""

    def search(self, text: str, *, limit: int = TITLE_SEARCH_LIMIT) -> tuple[TitleCandidate, ...]:
        """Return the candidates the catalog proposes for *text*, in its own order."""
        ...

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[int, ...]:
        """Return the episode count of every entry airing before *candidate*, direct prequel first."""
        ...


class TorrentClient(Protocol):
    """Local torrent client that stores files where AniShift tells it to."""

    def version(self) -> str:
        """Return the client version, proving the Web UI answers."""
        ...

    def preferences(self) -> dict[str, object]:
        """Return the client preferences relevant checks read."""
        ...

    def set_preferences(self, values: Mapping[str, object]) -> None:
        """Change the given client preferences."""
        ...

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        """Queue one torrent so its files land in *save_path*."""
        ...

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        """Return the torrents the client tracks under *category*."""
        ...


class CatalogOrder(StrEnum):
    """Order the release groups of one catalog are listed in."""

    NEWEST = "newest"
    SEEDERS = "seeders"


@dataclass(frozen=True, slots=True)
class SeasonContext:
    """Where one season sits inside the absolute numbering of its series."""

    index: int
    offset: int
    episodes: int | None


@dataclass(frozen=True, slots=True)
class EpisodeReading:
    """Episode of one release read in the numbering of the chosen season.

    ``absolute`` carries the number printed on the release when it counts from the
    first season, and ``other_season`` marks a release that belongs elsewhere.
    """

    episode: Decimal | None
    absolute: Decimal | None = None
    other_season: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseChoice:
    """One release together with the facts parsed from its name and its episode reading."""

    release: Release
    name: ReleaseName
    reading: EpisodeReading | None = None

    @property
    def episode(self) -> Decimal | None:
        """Episode in the numbering of the chosen season, or the printed one when unread."""
        return self.reading.episode if self.reading is not None else self.name.episode

    @property
    def absolute(self) -> Decimal | None:
        """Episode as printed on the release when it counts from the first season."""
        return self.reading.absolute if self.reading is not None else None

    @property
    def other_season(self) -> bool:
        """Whether this release belongs to a season other than the chosen one."""
        return self.reading is not None and self.reading.other_season


@dataclass(frozen=True, slots=True)
class SeriesGroup:
    """Releases of one series by one release group, newest episode first."""

    series: str
    group: str
    choices: tuple[ReleaseChoice, ...]
    subtitle_language: str | None = None
    newest: datetime | None = None
    matches_title: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseCatalog:
    """Listed release groups, releases hidden by quality, and releases outside the episode filter."""

    groups: tuple[SeriesGroup, ...]
    hidden: int
    filtered: int = 0


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    """What was handed to the client and where its files will appear."""

    count: int
    directory: Path


@dataclass(frozen=True, slots=True)
class ClientStatus:
    """Whether the client answers and whether it marks incomplete files."""

    reachable: bool
    version: str = ""
    incomplete_extension: bool = False
    problem: str = ""
    suggestion: str = ""


def read_episode(name: ReleaseName, context: SeasonContext | None) -> EpisodeReading:
    """Read the episode of *name* in the numbering of the season *context* describes.

    A name carrying its own season marker keeps its number and is flagged when the marker
    names another season. A name without one is read as absolute numbering once its number
    passes the episodes aired before the season, and is flagged as another season when it
    does not, because a season that follows others never restarts below its own offset.
    """
    episode: Decimal | None = name.episode
    if episode is None:
        return EpisodeReading(None)
    if context is None:
        return EpisodeReading(episode)
    marker: int | None = name.season if name.season is not None else season_hint(name.series)
    if marker is not None:
        return EpisodeReading(episode, other_season=marker != context.index)
    if context.index == 1:
        return EpisodeReading(episode)
    if episode > context.offset:
        return EpisodeReading(episode - context.offset, absolute=episode)
    return EpisodeReading(episode, other_season=True)


def catalog_releases(  # noqa: PLR0913 - every listing rule stays an explicit call-site choice
    releases: Sequence[Release],
    parse_name: Callable[[str], ReleaseName],
    *,
    min_resolution: int = MIN_RESOLUTION,
    aliases: Sequence[str] = (),
    order: CatalogOrder = CatalogOrder.SEEDERS,
    episodes: EpisodeRange | None = None,
    context: SeasonContext | None = None,
) -> ReleaseCatalog:
    """Group listable releases by series and release group, reading every episode in *context*.

    Releases below *min_resolution*, dubbed ones, and ones whose subtitle language the index
    never stated are hidden. When *episodes* is given, releases outside that span, packs, and
    releases without a number are counted as filtered instead. Series titles are compared with
    punctuation and case removed, so one series never splits over its own spelling.
    """
    buckets: dict[tuple[str, str], list[ReleaseChoice]] = {}
    labels: dict[tuple[str, str], tuple[str, str]] = {}
    hidden: int = 0
    filtered: int = 0
    for release in releases:
        name: ReleaseName = parse_name(release.title)
        if _is_hidden(release, name, min_resolution):
            hidden += 1
            continue
        reading: EpisodeReading = read_episode(name, context)
        if episodes is not None and _is_filtered(name, reading, episodes):
            filtered += 1
            continue
        group: str = name.group or "?"
        key: tuple[str, str] = (_normalize(name.series), group.casefold())
        labels.setdefault(key, (name.series, group))
        buckets.setdefault(key, []).append(ReleaseChoice(release, name, reading))
    alias_keys: frozenset[str] = frozenset(_normalize(strip_season(alias)) for alias in aliases)
    groups: list[SeriesGroup] = [
        _series_group(labels[key][0], labels[key][1], choices, alias_keys) for key, choices in buckets.items()
    ]
    groups.sort(key=lambda group: _group_order(group, order, ranked=bool(aliases)))
    return ReleaseCatalog(tuple(groups), hidden, filtered)


def series_directory_name(series: str) -> str:
    """Turn a series title into one directory name Windows accepts."""
    cleaned: str = _INVALID_NAME_CHARACTERS.sub("", series)
    cleaned = " ".join(cleaned.split()).rstrip(". ")
    if not cleaned:
        return _FALLBACK_DIRECTORY
    if cleaned.split(".", maxsplit=1)[0].upper() in _RESERVED_NAMES:
        return f"_{cleaned}"
    return cleaned


class AcquisitionService:
    """Search releases and hand the chosen ones to the client, saving into the library."""

    def __init__(  # noqa: PLR0913 - explicit composition-boundary dependencies
        self,
        *,
        source: TorrentSource,
        client: TorrentClient,
        workspace_root: Path,
        parse_name: Callable[[str], ReleaseName],
        category: str = DOWNLOAD_CATEGORY,
        title_catalog: TitleCatalog | None = None,
    ) -> None:
        self._source: TorrentSource = source
        self._client: TorrentClient = client
        self._workspace_root: Path = workspace_root
        self._parse_name: Callable[[str], ReleaseName] = parse_name
        self._category: str = category
        self._title_catalog: TitleCatalog | None = title_catalog

    def search(self, query: str) -> ReleaseCatalog:
        """Return the listed releases for *query*, grouped and filtered by quality."""
        releases: tuple[Release, ...] = self._source.search(query)
        catalog: ReleaseCatalog = catalog_releases(releases, self._parse_name)
        logger.info(
            "Releases searched", listed=sum(len(group.choices) for group in catalog.groups), hidden=catalog.hidden
        )
        return catalog

    def find_titles(self, text: str) -> tuple[TitleCandidate, ...]:
        """Return the title candidates for *text*, or none when no catalog is composed.

        Raises:
            TitleCatalogError: The catalog is unreachable or rejects the search.
        """
        if self._title_catalog is None:
            return ()
        return self._title_catalog.search(text)

    def season_context(self, candidate: TitleCandidate) -> SeasonContext:
        """Return which season *candidate* is and how many episodes aired before it.

        Raises:
            TitleCatalogError: The catalog is unreachable or rejects one of the requests.
        """
        if self._title_catalog is None:
            return SeasonContext(index=1, offset=0, episodes=candidate.episodes)
        prequels: tuple[int, ...] = self._title_catalog.prequel_episodes(candidate)
        return SeasonContext(index=len(prequels) + 1, offset=sum(prequels), episodes=candidate.episodes)

    def search_title(
        self,
        candidate: TitleCandidate,
        *,
        episodes: EpisodeRange | None = None,
        order: CatalogOrder = CatalogOrder.NEWEST,
        context: SeasonContext | None = None,
    ) -> ReleaseCatalog:
        """Return the complete listing for *candidate*, asking the index once per matching group.

        The index answers one free-text query with its newest entries only, so the titles of
        *candidate* are searched first and every group they reveal is then asked for its own
        episodes.
        """
        aliases: tuple[str, ...] = candidate.aliases()
        merged: dict[str, Release] = {}
        queries: int = 0
        for query in _title_queries(candidate):
            queries += 1
            _merge(merged, self._source.search(query))
        preliminary: ReleaseCatalog = catalog_releases(
            tuple(merged.values()), self._parse_name, aliases=aliases, order=order, context=context
        )
        for group in _group_queries(preliminary):
            queries += 1
            _merge(merged, self._source.search(f"{group.series} {group.group}"))
        catalog: ReleaseCatalog = catalog_releases(
            tuple(merged.values()), self._parse_name, aliases=aliases, order=order, episodes=episodes, context=context
        )
        logger.info(
            "Title releases searched",
            queries=queries,
            listed=sum(len(group.choices) for group in catalog.groups),
            hidden=catalog.hidden,
            filtered=catalog.filtered,
        )
        return catalog

    def download(self, choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        """Queue every chosen release, into *directory_name* when given, else per series."""
        if not choices:
            msg = "At least one release must be chosen"
            raise ValueError(msg)
        chosen_directory: str | None = None if directory_name is None else series_directory_name(directory_name)
        fixed: Path | None = None if chosen_directory is None else self._workspace_root / chosen_directory
        directory: Path = fixed if fixed is not None else self.series_directory(choices[0])
        for choice in choices:
            self._client.add_torrent(
                choice.release.torrent_url,
                save_path=directory if fixed is not None else self.series_directory(choice),
                category=self._category,
            )
        logger.info("Releases queued in the torrent client", count=len(choices), fixed_directory=fixed is not None)
        return DownloadReceipt(len(choices), directory)

    def queued_hashes(self) -> frozenset[str]:
        """Lowercase info hashes of every torrent the client already tracks under the AniShift category."""
        return frozenset(info.info_hash.casefold() for info in self._client.torrents(self._category))

    def series_directory(self, choice: ReleaseChoice) -> Path:
        """Return the library directory the files of *choice* will be saved into."""
        return self._workspace_root / series_directory_name(choice.name.series)

    def client_status(self) -> ClientStatus:
        """Report whether the client answers and marks incomplete files."""
        try:
            version: str = self._client.version()
            preferences: dict[str, object] = self._client.preferences()
        except AniShiftError as problem:
            logger.warning("Torrent client unavailable", error_class=type(problem).__name__)
            return ClientStatus(reachable=False, problem=str(problem), suggestion=problem.context.suggestion)
        return ClientStatus(
            reachable=True,
            version=version,
            incomplete_extension=bool(preferences.get(INCOMPLETE_EXTENSION_PREFERENCE, False)),
        )

    def setup_client(self) -> ClientStatus:
        """Make the client mark incomplete files, so the watch never takes a partial download."""
        status: ClientStatus = self.client_status()
        if not status.reachable:
            return status
        self._client.set_preferences({INCOMPLETE_EXTENSION_PREFERENCE: True})
        logger.info("Torrent client configured for incomplete-file suffixes")
        return self.client_status()


def _title_queries(candidate: TitleCandidate) -> tuple[str, ...]:
    """Return the candidate titles worth sending to the index, without repeating one spelling."""
    english: str = (candidate.english or "").strip()
    if not english or english.casefold() == candidate.romaji.casefold():
        return (candidate.romaji,)
    return (candidate.romaji, english)


def _group_queries(catalog: ReleaseCatalog) -> tuple[SeriesGroup, ...]:
    """Return the groups whose own listing is worth asking for, in catalog order."""
    matching: list[SeriesGroup] = [
        group
        for group in catalog.groups
        if group.matches_title and any(choice.episode is not None for choice in group.choices)
    ]
    return tuple(matching[:MAX_GROUP_QUERIES])


def _merge(merged: dict[str, Release], releases: Sequence[Release]) -> None:
    """Add the releases the merge does not hold yet, keeping the entry seen first."""
    for release in releases:
        merged.setdefault(release.info_hash.casefold(), release)


def _is_hidden(release: Release, name: ReleaseName, min_resolution: int) -> bool:
    """Whether one release is never worth listing, whatever the episode filter says."""
    below_quality: bool = name.resolution is None or name.resolution < min_resolution
    return below_quality or name.dubbed or release.subtitle_language is None


def _is_filtered(name: ReleaseName, reading: EpisodeReading, episodes: EpisodeRange) -> bool:
    """Whether one release falls outside the episodes the search asked for."""
    if reading.episode is None or name.is_pack:
        return True
    return not episodes.contains(reading.episode)


def _series_group(
    series: str,
    group: str,
    choices: Sequence[ReleaseChoice],
    alias_keys: frozenset[str],
) -> SeriesGroup:
    """Build one listed group with its dominant subtitle language and newest publication."""
    languages: Counter[str] = Counter(
        choice.release.subtitle_language for choice in choices if choice.release.subtitle_language is not None
    )
    published: list[datetime] = [choice.release.published for choice in choices if choice.release.published is not None]
    return SeriesGroup(
        series=series,
        group=group,
        choices=tuple(sorted(choices, key=_choice_order)),
        subtitle_language=languages.most_common(1)[0][0] if languages else None,
        newest=max(published) if published else None,
        matches_title=_normalize(strip_season(series)) in alias_keys,
    )


def _normalize(text: str) -> str:
    """Fold *text* to letters, digits, and single spaces, so spelling never splits one series."""
    folded: str = unicodedata.normalize("NFKC", text).casefold()
    kept: str = "".join(character for character in folded if character.isalnum() or character.isspace())
    return " ".join(kept.split())


def _choice_order(choice: ReleaseChoice) -> tuple[int, int, Decimal, int]:
    episode: Decimal | None = choice.episode
    if episode is None:
        return (int(choice.other_season), 1, Decimal(0), 0)
    return (int(choice.other_season), 0, -episode, -(choice.name.version or 0))


def _group_order(group: SeriesGroup, order: CatalogOrder, *, ranked: bool) -> tuple[int, int, float, str, str]:
    priority: int = int(not group.matches_title) if ranked else 0
    if order is CatalogOrder.NEWEST:
        missing: int = int(group.newest is None)
        weight: float = 0.0 if group.newest is None else -group.newest.timestamp()
    else:
        missing = 0
        weight = -float(sum(choice.release.seeders for choice in group.choices))
    return (priority, missing, weight, group.series.casefold(), group.group.casefold())
