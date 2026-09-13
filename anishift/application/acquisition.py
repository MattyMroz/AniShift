"""Release discovery and download hand-off through one torrent source and one torrent client."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from anishift.errors import AniShiftError
from anishift.services.torrents.categories import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    SEARCH_CATEGORIES,
)
from anishift.services.torrents.names import base_title, season_hint, title_forms
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from anishift.services.catalog import PrequelEntry, SeasonAiring, TitleCandidate
    from anishift.services.http_requests import RequestControl
    from anishift.services.torrents import Release, ReleaseName, TorrentFile, TorrentInfo
    from anishift.services.torrents.query import EpisodeRange

__all__ = [
    "DOWNLOAD_CATEGORY",
    "MAX_GROUP_QUERIES",
    "MAX_REQUESTS",
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
    "normalize_series",
    "order_groups",
    "read_episode",
    "series_directory_name",
    "series_forms",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_RESOLUTION: Final[int] = 1080
"""Lowest vertical resolution a release must declare to be listed."""

DOWNLOAD_CATEGORY: Final[str] = "AniShift"
"""Category every torrent added by AniShift carries inside the client."""

MAX_GROUP_QUERIES: Final[int] = 5
"""Release groups asked for their own complete listing after a title search."""

MAX_REQUESTS: Final[int] = 16
"""HTTP GET requests one title search may spend; a query covering both categories costs two."""

MAX_EPISODE_SPAN: Final[int] = 3
"""Widest episode range still asked for by number, one set of queries per episode."""

TITLE_SEARCH_LIMIT: Final[int] = 7
"""Title candidates a catalog is asked for by default."""

INCOMPLETE_EXTENSION_PREFERENCE: Final[str] = "incomplete_files_ext"
"""Client preference appending ``.!qB`` to files still being downloaded, which the watch skips."""

SEEDING_STOP_PREFERENCES: Final[Mapping[str, object]] = {
    "max_ratio_enabled": True,
    "max_ratio": 0,
    "max_ratio_act": 0,
    "max_seeding_time_enabled": True,
    "max_seeding_time": 0,
}
"""Client preferences stopping every torrent the moment its download completes, so nothing is seeded."""

_INVALID_NAME_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
"""Characters Windows refuses inside one path component."""

_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)
"""Device names Windows refuses as a file or directory name regardless of extension."""

_FALLBACK_DIRECTORY: Final[str] = "Nieznana seria"
"""Directory used when a release title leaves nothing usable for a folder name."""

_NON_ENGLISH_LANGUAGE: Final[str] = "fr"
"""Subtitle language whose releases the index keeps outside the English-translated category."""


class TorrentSource(Protocol):
    """Index of public releases answering one free-text title query."""

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        """Return the releases matching *query* in *categories*, newest first as the index lists them."""
        ...


class TitleCatalog(Protocol):
    """Anime catalog naming the title behind a human phrase and how deep its season sits."""

    def search(self, text: str, *, limit: int = TITLE_SEARCH_LIMIT) -> tuple[TitleCandidate, ...]:
        """Return the candidates the catalog proposes for *text*, in its own order."""
        ...

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        """Return every entry airing before *candidate*, direct prequel first."""
        ...

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        """Return the known episode dates of one season."""
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

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Return selection and completion of the torrent files."""
        ...


class TorrentManagement(Protocol):
    """Lifecycle operations supplied only for a separately owned torrent client."""

    def download_scope(self, hashes: frozenset[str]) -> AbstractContextManager[None]:
        """Record ownership before downloads are submitted."""
        ...

    def finish_transfers(self) -> None:
        """Stop completed seeds and an idle owned process."""
        ...

    def transfer_action(self, info_hash: str, action: str) -> None:
        """Apply an explicit action to a managed transfer."""
        ...

    def close(self) -> None:
        """Release process management resources."""
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
    """Episode of one release read in the numbering of the chosen season."""

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
    """Listed release groups and the three reasons a release was left out of them."""

    groups: tuple[SeriesGroup, ...]
    hidden: int
    filtered: int = 0
    excluded: int = 0


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
    seeding_stops: bool = False
    problem: str = ""
    suggestion: str = ""


def read_episode(name: ReleaseName, context: SeasonContext | None) -> EpisodeReading:
    """Read the episode of *name* in the numbering of the season *context* describes."""
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
    """Group listable releases by series and release group, reading every episode in *context*."""
    buckets: dict[tuple[str, str], list[ReleaseChoice]] = {}
    labels: dict[tuple[str, str], tuple[str, str]] = {}
    hidden: int = 0
    excluded: int = 0
    filtered: int = 0
    for release in releases:
        name: ReleaseName = parse_name(release.title)
        if _is_hidden(name, min_resolution):
            hidden += 1
            continue
        if _is_excluded(release, name):
            excluded += 1
            continue
        reading: EpisodeReading = read_episode(name, context)
        if episodes is not None and _is_filtered(name, reading, episodes):
            filtered += 1
            continue
        group: str = name.group or "?"
        key: tuple[str, str] = (normalize_series(name.series), group.casefold())
        labels.setdefault(key, (name.series, group))
        buckets.setdefault(key, []).append(ReleaseChoice(release, name, reading))
    alias_keys: frozenset[str] = frozenset(form for alias in aliases for form in series_forms(alias))
    groups: list[SeriesGroup] = [
        _series_group(labels[key][0], labels[key][1], choices, alias_keys) for key, choices in buckets.items()
    ]
    return ReleaseCatalog(order_groups(groups, order, ranked=bool(aliases)), hidden, filtered, excluded)


def order_groups(groups: Sequence[SeriesGroup], order: CatalogOrder, *, ranked: bool) -> tuple[SeriesGroup, ...]:
    """Return *groups* in the order a catalog lists them, so no caller reinvents the rule."""
    return tuple(sorted(groups, key=lambda group: _group_order(group, order, ranked=ranked)))


def series_forms(text: str) -> frozenset[str]:
    """Return the normalized spellings a series title may be recognized by, empty ones dropped."""
    return frozenset(form for raw in title_forms(text) if (form := normalize_series(raw)))


def normalize_series(text: str) -> str:
    """Fold *text* to letters, digits, and single spaces, so spelling never splits one series."""
    folded: str = unicodedata.normalize("NFKC", text).casefold()
    kept: str = "".join(character for character in folded if character.isalnum() or character.isspace())
    return " ".join(kept.split())


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
        request_control: RequestControl | None = None,
        torrent_management: TorrentManagement | None = None,
    ) -> None:
        self._source: TorrentSource = source
        self._client: TorrentClient = client
        self._workspace_root: Path = workspace_root
        self._parse_name: Callable[[str], ReleaseName] = parse_name
        self._category: str = category
        self._title_catalog: TitleCatalog | None = title_catalog
        self.request_control: RequestControl | None = request_control
        self._torrent_management: TorrentManagement | None = torrent_management

    def requests(self, reason: str) -> AbstractContextManager[None]:
        """Share one metadata budget across the adapters used by an operation."""
        if self.request_control is None:
            return nullcontext()
        return self.request_control.scope(reason, {"nyaa": MAX_REQUESTS, "anilist": MAX_REQUESTS})

    def blocked_until(self, providers: tuple[str, ...]) -> float:
        """Return the earliest allowed provider retry, or zero when unblocked."""
        return self.request_control.blocked_until(providers) if self.request_control is not None else 0.0

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> ReleaseCatalog:
        """Return the listed releases for *query*, grouped and filtered by quality."""
        releases: tuple[Release, ...] = self._source.search(query, categories=categories)
        catalog: ReleaseCatalog = catalog_releases(releases, self._parse_name)
        logger.info(
            "Releases searched",
            listed=sum(len(group.choices) for group in catalog.groups),
            hidden=catalog.hidden,
            excluded=catalog.excluded,
        )
        return catalog

    def find_titles(self, text: str) -> tuple[TitleCandidate, ...]:
        """Return the title candidates for *text*, or none when no catalog is composed."""
        if self._title_catalog is None:
            return ()
        return self._title_catalog.search(text)

    def season_context(self, candidate: TitleCandidate) -> SeasonContext:
        """Return which season *candidate* is and how many episodes aired before it."""
        if self._title_catalog is None:
            return SeasonContext(index=1, offset=0, episodes=candidate.episodes)
        prequels: tuple[PrequelEntry, ...] = self._title_catalog.prequel_episodes(candidate)
        seasons: int = sum(1 for entry in prequels if not entry.cour)
        return SeasonContext(
            index=seasons + (0 if candidate.is_cour() else 1),
            offset=sum(entry.episodes for entry in prequels),
            episodes=candidate.episodes,
        )

    def search_title(
        self,
        candidate: TitleCandidate,
        *,
        episodes: EpisodeRange | None = None,
        order: CatalogOrder = CatalogOrder.NEWEST,
        context: SeasonContext | None = None,
    ) -> ReleaseCatalog:
        """Return the complete listing for *candidate*, asking the index once per matching group."""
        aliases: tuple[str, ...] = candidate.aliases()
        merged: dict[str, Release] = {}
        requests: int = 0
        for query in _search_queries(candidate, episodes, context):
            if requests + len(SEARCH_CATEGORIES) > MAX_REQUESTS:
                break
            requests += len(SEARCH_CATEGORIES)
            _merge(merged, self._source.search(query))
        preliminary: ReleaseCatalog = catalog_releases(
            tuple(merged.values()), self._parse_name, aliases=aliases, order=order, context=context
        )
        for group in _group_queries(preliminary, MAX_REQUESTS - requests):
            categories: tuple[str, ...] = _group_categories(group)
            requests += len(categories)
            _merge(merged, self._source.search(f"{group.series} {group.group}", categories=categories))
        catalog: ReleaseCatalog = catalog_releases(
            tuple(merged.values()), self._parse_name, aliases=aliases, order=order, episodes=episodes, context=context
        )
        logger.info(
            "Title releases searched",
            requests=requests,
            listed=sum(len(group.choices) for group in catalog.groups),
            hidden=catalog.hidden,
            excluded=catalog.excluded,
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
        hashes: frozenset[str] = frozenset(choice.release.info_hash.casefold() for choice in choices)
        scope: AbstractContextManager[None] = (
            self._torrent_management.download_scope(hashes) if self._torrent_management is not None else nullcontext()
        )
        with scope:
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

    def transfers(self) -> tuple[TorrentInfo, ...]:
        """Read the current state of every transfer in the AniShift category."""
        return self._client.torrents(self._category)

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        """Read known episode dates without another title or prequel search."""
        if self._title_catalog is None:
            msg = "No title catalog is configured"
            raise ValueError(msg)
        return self._title_catalog.airing_schedule(anilist_id)

    def transfer_files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Read selection and completion for one tracked transfer."""
        return self._client.files(info_hash)

    def finish_transfers(self) -> None:
        """Release completed seeds only through the private process owner."""
        if self._torrent_management is not None:
            self._torrent_management.finish_transfers()

    def control_transfer(self, info_hash: str, action: str) -> None:
        """Apply an explicit operation to a private transfer without deleting media."""
        if self._torrent_management is None:
            msg = "This torrent client is external and cannot be managed automatically"
            raise ValueError(msg)
        self._torrent_management.transfer_action(info_hash, action)

    def close(self) -> None:
        """Release private torrent process resources."""
        if self._torrent_management is not None:
            self._torrent_management.close()

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
            seeding_stops=_seeding_stops(preferences),
        )

    def setup_client(self) -> ClientStatus:
        """Make the client mark incomplete files and stop seeding once a download completes."""
        status: ClientStatus = self.client_status()
        if not status.reachable:
            return status
        self._client.set_preferences({INCOMPLETE_EXTENSION_PREFERENCE: True, **SEEDING_STOP_PREFERENCES})
        logger.info("Torrent client configured for incomplete-file suffixes and no seeding")
        return self.client_status()


def _title_queries(candidate: TitleCandidate) -> tuple[str, ...]:
    """Return the candidate titles worth sending to the index, without repeating one spelling."""
    english: str = (candidate.english or "").strip()
    if not english or english.casefold() == candidate.romaji.casefold():
        return (candidate.romaji,)
    return (candidate.romaji, english)


def _search_queries(
    candidate: TitleCandidate,
    episodes: EpisodeRange | None,
    context: SeasonContext | None,
) -> tuple[str, ...]:
    """Return the queries one title search sends before refining per group, without repeats."""
    planned: list[str] = []
    for query in (*_title_queries(candidate), *_episode_queries(candidate, episodes, context)):
        if query not in planned:
            planned.append(query)
    return tuple(planned)


def _episode_queries(
    candidate: TitleCandidate,
    episodes: EpisodeRange | None,
    context: SeasonContext | None,
) -> tuple[str, ...]:
    """Return the queries naming every episode a narrow request asks for, in both numberings."""
    numbers: tuple[int, ...] = _episode_numbers(episodes)
    base: str = _episode_base(candidate)
    if not numbers or not base:
        return ()
    queries: list[str] = []
    for number in numbers:
        queries.append(f"{base} - {number:02d}")
        if context is not None and context.index > 1:
            queries.append(f"{base} S{context.index:02d}E{number:02d}")
            queries.append(f"{base} - {number + context.offset:02d}")
    return tuple(queries)


def _episode_base(candidate: TitleCandidate) -> str:
    """Return the shortest spelling of *candidate* worth putting in front of an episode number."""
    return base_title(candidate.english or candidate.romaji)


def _episode_numbers(episodes: EpisodeRange | None) -> tuple[int, ...]:
    """Return the whole episode numbers a narrow closed range names, none when it names no such span."""
    if episodes is None or episodes.first is None or episodes.last is None:
        return ()
    first: Decimal = episodes.first
    last: Decimal = episodes.last
    if first != int(first) or last != int(last):
        return ()
    span: int = int(last) - int(first) + 1
    if span < 1 or span > MAX_EPISODE_SPAN:
        return ()
    return tuple(range(int(first), int(last) + 1))


def _group_categories(group: SeriesGroup) -> tuple[str, ...]:
    """Return the single category the releases of *group* were seen in."""
    if group.subtitle_language == _NON_ENGLISH_LANGUAGE:
        return (CATEGORY_NON_ENGLISH_TRANSLATED,)
    return (CATEGORY_ENGLISH_TRANSLATED,)


def _group_queries(catalog: ReleaseCatalog, budget: int) -> tuple[SeriesGroup, ...]:
    """Return the matching groups whose own listing is worth asking for, best seeded first."""
    ranked: list[tuple[SeriesGroup, int]] = []
    for group in catalog.groups:
        if not group.matches_title:
            continue
        listed: list[ReleaseChoice] = [
            choice for choice in group.choices if choice.episode is not None and not choice.other_season
        ]
        if listed:
            ranked.append((group, sum(choice.release.seeders for choice in listed)))
    ranked.sort(key=lambda entry: -entry[1])
    limit: int = min(MAX_GROUP_QUERIES, max(budget, 0))
    return tuple(group for group, _ in ranked[:limit])


def _merge(merged: dict[str, Release], releases: Sequence[Release]) -> None:
    """Add the releases the merge does not hold yet, keeping the entry seen first."""
    for release in releases:
        merged.setdefault(release.info_hash.casefold(), release)


def _is_hidden(name: ReleaseName, min_resolution: int) -> bool:
    """Whether one release stays below the quality worth listing."""
    return name.resolution is None or name.resolution < min_resolution


def _is_excluded(release: Release, name: ReleaseName) -> bool:
    """Whether one release carries the wrong audio or a subtitle language the index never stated."""
    return name.dubbed or release.subtitle_language is None


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
        matches_title=bool(series_forms(series) & alias_keys),
    )


def _seeding_stops(preferences: Mapping[str, object]) -> bool:
    """Whether the client stops a torrent right after its download completes."""
    return all(preferences.get(key) == value for key, value in SEEDING_STOP_PREFERENCES.items())


def _choice_order(choice: ReleaseChoice) -> tuple[int, int, Decimal, int]:
    episode: Decimal | None = choice.episode
    if episode is None:
        return (int(choice.other_season), 1, Decimal(0), 0)
    return (int(choice.other_season), 0, -episode, -(choice.name.version or 0))


def _group_order(group: SeriesGroup, order: CatalogOrder, *, ranked: bool) -> tuple[int, int, int, float, str, str]:
    priority: int = int(not group.matches_title) if ranked else 0
    foreign: int = int(all(choice.other_season for choice in group.choices))
    if order is CatalogOrder.NEWEST:
        missing: int = int(group.newest is None)
        weight: float = 0.0 if group.newest is None else -group.newest.timestamp()
    else:
        missing = 0
        weight = -float(sum(choice.release.seeders for choice in group.choices))
    return (priority, foreign, missing, weight, group.series.casefold(), group.group.casefold())
