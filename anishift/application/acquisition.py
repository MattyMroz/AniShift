"""Release discovery and download hand-off through one torrent source and one torrent client."""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from collections import Counter, OrderedDict
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

from anishift.application.acquisition_decisions import offer_check, source_error
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_search import (
    EpisodeRequest,
    EpisodeSearch,
    SourceSwitches,
    episode_phrases,
    offer_status,
    source_line,
)
from anishift.application.episode_selection import (
    AniZipMapping,
    EpisodeOffer,
    ListedEpisode,
    episode_listing,
    franchise_traversal,
    franchise_view,
    identity_target,
    numbering_gap,
    rank_candidates,
    streams_releases,
    suggestion,
)
from anishift.errors import AniShiftError, ErrorCode
from anishift.services.torrents.categories import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    SEARCH_CATEGORIES,
)
from anishift.services.torrents.names import base_title, parse_release_name, season_hint, title_forms
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator, Mapping, Sequence

    from anishift.application.cancellation import CancellationToken
    from anishift.application.episode_search import SearchOutcome, SearchSnapshot
    from anishift.application.episode_selection import (
        EpisodeKey,
        EpisodeListing,
        Franchise,
        FranchiseGraph,
        RankedCandidate,
        StreamCandidate,
    )
    from anishift.services.catalog import ArmIds, PrequelEntry, SeasonAiring, TitleCandidate
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
    "AnidbCatalog",
    "CatalogOrder",
    "ClientStatus",
    "DownloadReceipt",
    "EpisodeCatalog",
    "EpisodeReading",
    "IdCatalog",
    "KitsuLookup",
    "ListingRead",
    "ReleaseCatalog",
    "ReleaseChoice",
    "SeasonContext",
    "SelectiveTorrentClient",
    "SeriesGroup",
    "StreamSource",
    "TitleCatalog",
    "TorrentClient",
    "TorrentSource",
    "catalog_releases",
    "episode_read_timeout_s",
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

CONFIRM_ATTEMPTS: Final[int] = 3
"""Maximum fresh client reads to confirm a just-added release without resending it."""

CONFIRM_DELAY_S: Final[float] = 1.0
"""Delay between confirmation reads while the client asynchronously resolves an added URL."""

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

_FALLBACK_CACHE_S: Final[int] = 900
"""Freshness of remembered entry data when ani.zip omits it; its ``Cache-Control`` measured 2026-09-22."""

_REMEMBERED_ENTRIES: Final[int] = 64
"""Entries the resident process keeps in memory before forgetting the least recently used one."""

_SCHEDULE_WARNING: Final[str] = "TITLE_CATALOG_FAILED"
"""Listing warning code when the airing schedule is unavailable."""

_UNKNOWN_STATUS: Final[str] = "UNKNOWN"
"""Status value used when no catalog source names one."""

_MOVIE_FORMAT: Final[str] = "MOVIE"
"""AniList format whose only row is fetched as a Torrentio movie."""

_DONGHUA_COUNTRY: Final[str] = "CN"
"""AniList country of origin whose original audio also includes Chinese."""


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

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> FranchiseGraph:
        """Return the anime relation graph rooted at one entry, stopping before a request after *cancel*."""
        ...


class EpisodeCatalog(Protocol):
    """Episode mapping of one catalog entry."""

    def mapping(self, anilist_id: int) -> AniZipMapping:
        """Return the episode mapping, empty for an unknown entry."""
        ...


class AnidbCatalog(Protocol):
    """Episode mapping of one AniDB entry."""

    def mapping_by_anidb(self, anidb_id: int) -> AniZipMapping:
        """Return the episode mapping, empty for an unknown entry."""
        ...


class IdCatalog(Protocol):
    """Bridge from an AniList entry to its AniDB ID and TheTVDB season."""

    def ids(self, anilist_id: int) -> ArmIds:
        """Return the bridge IDs, ``None`` where unknown."""
        ...


class KitsuLookup(Protocol):
    """Kitsu ID of an AniList entry confirmed in both directions."""

    def kitsu_id(self, anilist_id: int) -> int | None:
        """Return the Kitsu ID, ``None`` when unresolved."""
        ...


class StreamSource(Protocol):
    """Live stream candidates of one episode or movie."""

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        """Return the candidates of one local episode."""
        ...

    def movie_streams(self, kitsu_id: int) -> tuple[StreamCandidate, ...]:
        """Return the candidates of one movie."""
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

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str, stopped: bool = False) -> None:
        """Queue one torrent so its files land in *save_path*, optionally without writing content yet."""
        ...

    def rename_file(self, info_hash: str, old_path: str, new_path: str) -> None:
        """Move one file of a torrent to *new_path* relative to its save path."""
        ...

    def resume(self, info_hash: str) -> None:
        """Let one queued torrent write its content."""
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

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        """Make the owned client available again for ordered transfers still awaiting confirmation."""
        ...

    def prepare(self) -> None:
        """Reconnect or restart the owned client for unfinished work when the application starts."""
        ...

    def finish_transfers(self) -> None:
        """Stop completed seeds and an idle owned process."""
        ...

    def close_owned(self) -> None:
        """Shut the owned client down on an explicit end."""
        ...

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        """Release only confirmed complete jobs without deleting their media."""
        ...

    def released_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        """Read persisted release evidence without activating or changing the client."""
        ...

    def finalizable_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        """Return released or still managed hashes that can make finalization progress."""
        ...

    def transfer_action(self, info_hash: str, action: str) -> None:
        """Apply an explicit action to a managed transfer."""
        ...

    def close(self) -> None:
        """Release process management resources."""
        ...


class SelectiveTorrentClient(TorrentClient, Protocol):
    """Metadata-only admission and verified selection supported by a managed private client."""

    def add_metadata(self, info_hash: str, *, trackers: tuple[str, ...] = (), save_path: Path, category: str) -> None:
        """Fetch metadata of a recorded new hash and stop before downloading its content."""
        ...

    def select_files(
        self, info_hash: str, files: tuple[TorrentFile, ...], selected: frozenset[int], *, save_path: Path
    ) -> tuple[TorrentFile, ...]:
        """Apply the saved union to a stopped owned transfer and verify it without resuming."""
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
class ListingRead:
    """One episode list with the exact mapping it was built from, whether it was read live, and its numbering facts."""

    listing: EpisodeListing
    mapping: AniZipMapping
    live: bool
    tvdb_season: int | None = None
    numbering_source: str = "anilist"
    movie: bool = False


@dataclass(frozen=True, slots=True)
class ClientStatus:
    """Whether the client answers and whether it marks incomplete files."""

    reachable: bool
    version: str = ""
    incomplete_extension: bool = False
    seeding_stops: bool = False
    problem: str = ""
    suggestion: str = ""


@dataclass(slots=True)
class _Remembered:
    graph: FranchiseGraph | None = None
    graph_at: float = 0.0
    mapping: AniZipMapping | None = None
    mapping_at: float = 0.0
    schedule: SeasonAiring | None = None
    schedule_at: float = 0.0

    def fresh(self, fetched_at: float, now: float) -> bool:
        age: int | None = self.mapping.max_age_s if self.mapping is not None else None
        return now - fetched_at < (age if age is not None else _FALLBACK_CACHE_S)


def _movie(graph_movie: bool | None, mapping: AniZipMapping) -> bool:
    return graph_movie if graph_movie is not None else mapping.catalog_type == _MOVIE_FORMAT


def _bridge_failed(provider: str, error: AniShiftError | OSError | ValueError) -> None:
    code: ErrorCode | None = error.context.code if isinstance(error, AniShiftError) else None
    logger.warning("Numbering bridge failed", provider=provider, code=code, error_class=type(error).__name__)


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


def episode_read_timeout_s() -> float:
    """Client wait for one budgeted episode read: every schedule page at the AniList spacing plus the answer margin."""
    from anishift.platform.local_control import DEFAULT_TIMEOUT_S  # noqa: PLC0415
    from anishift.services.catalog.anilist import MAX_SCHEDULE_PAGES  # noqa: PLC0415
    from anishift.services.http_requests import REMOTE_INTERVAL_S  # noqa: PLC0415

    return MAX_SCHEDULE_PAGES * REMOTE_INTERVAL_S + DEFAULT_TIMEOUT_S


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
        episode_catalog: EpisodeCatalog | None = None,
        stream_source: StreamSource | None = None,
        episode_search: EpisodeSearch | None = None,
        id_catalog: IdCatalog | None = None,
        anidb_catalog: AnidbCatalog | None = None,
        kitsu_catalog: KitsuLookup | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._source: TorrentSource = source
        self._client: TorrentClient = client
        self._workspace_root: Path = workspace_root
        self._parse_name: Callable[[str], ReleaseName] = parse_name
        self._category: str = category
        self._title_catalog: TitleCatalog | None = title_catalog
        self.request_control: RequestControl | None = request_control
        self._torrent_management: TorrentManagement | None = torrent_management
        self._episode_catalog: EpisodeCatalog | None = episode_catalog
        self._stream_source: StreamSource | None = stream_source
        self._episode_search: EpisodeSearch | None = episode_search
        self._id_catalog: IdCatalog | None = id_catalog
        self._anidb_catalog: AnidbCatalog | None = anidb_catalog
        self._kitsu_catalog: KitsuLookup | None = kitsu_catalog
        self._clock: Callable[[], float] = clock
        self._memory: OrderedDict[int, _Remembered] = OrderedDict()
        self._memory_lock: threading.Lock = threading.Lock()
        self._decision_sink: ContextVar[Callable[[dict[str, object]], None] | None] = ContextVar(
            "decision_sink", default=None
        )

    @contextmanager
    def observe_decisions(self, sink: Callable[[dict[str, object]], None]) -> Iterator[None]:
        """Forward actual source reads to the current operation's owner."""
        token: Token[Callable[[dict[str, object]], None] | None] = self._decision_sink.set(sink)
        try:
            yield
        finally:
            self._decision_sink.reset(token)

    def _decision(self, payload: dict[str, object]) -> None:
        sink: Callable[[dict[str, object]], None] | None = self._decision_sink.get()
        if sink is not None:
            sink(payload)

    def requests(self, reason: str) -> AbstractContextManager[None]:
        """Share one metadata budget across the adapters used by an operation."""
        if self.request_control is None:
            return nullcontext()
        return self.request_control.scope(reason, {"nyaa": MAX_REQUESTS, "anilist": MAX_REQUESTS})

    def episode_requests(self) -> AbstractContextManager[None]:
        """Budget one franchise, episode or offer read to the AniList schedule pagination."""
        from anishift.services.catalog.anilist import MAX_SCHEDULE_PAGES  # noqa: PLC0415

        if self.request_control is None:
            return nullcontext()
        return self.request_control.scope("user", {"anilist": MAX_SCHEDULE_PAGES})

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
        return _season_context(candidate, prequels)

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

    def download(self, choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        """Queue every chosen release into the flat workspace root, stopped until its names are reserved."""
        if not choices:
            msg = "At least one release must be chosen"
            raise ValueError(msg)
        hashes: frozenset[str] = frozenset(choice.release.info_hash.casefold() for choice in choices)
        scope: AbstractContextManager[None] = (
            self._torrent_management.download_scope(hashes) if self._torrent_management is not None else nullcontext()
        )
        with scope:
            for choice in choices:
                self._client.add_torrent(
                    choice.release.torrent_url,
                    save_path=self._workspace_root,
                    category=self._category,
                    stopped=True,
                )
        logger.info("Releases queued in the torrent client", count=len(choices))
        return DownloadReceipt(len(choices), self._workspace_root)

    @staticmethod
    def retained_reference(choice: ReleaseChoice) -> tuple[int | None, str | None]:
        """Keep a source-qualified reference when the chosen public link supports one."""
        from anishift.services.torrents.nyaa import retained_release_id  # noqa: PLC0415

        identifier: int | None = retained_release_id(choice.release.torrent_url)
        return (identifier, choice.release.title) if identifier is not None and choice.release.title else (None, None)

    def reacquire(self, release_id: int, title: str, info_hash: str, episode: str | None) -> DownloadReceipt:
        """Submit an explicitly repeated release stopped, preserving its admitted season numbering."""
        from anishift.services.torrents.nyaa import retained_torrent_url  # noqa: PLC0415
        from anishift.services.torrents.types import Release  # noqa: PLC0415

        release: Release = Release(title, retained_torrent_url(release_id), info_hash, 0, "", None)
        choice: ReleaseChoice = ReleaseChoice(
            release, self._parse_name(title), EpisodeReading(None if episode is None else Decimal(episode))
        )
        return self.download((choice,))

    def rename_transfer_file(self, info_hash: str, old_path: str, new_path: str) -> None:
        """Reserve one destination name inside a stopped transfer before any content is written."""
        self._client.rename_file(info_hash, old_path, new_path)

    def start_transfer(self, info_hash: str) -> None:
        """Let a transfer write content once every one of its names is reserved."""
        self._client.resume(info_hash)

    def add_metadata(self, info_hash: str, trackers: tuple[str, ...], save_path: Path) -> None:
        """Own one admitted hash and ask the private client for its file list only."""
        client: SelectiveTorrentClient = self._selective()
        with cast("TorrentManagement", self._torrent_management).download_scope(frozenset({info_hash.casefold()})):
            client.add_metadata(info_hash, trackers=trackers, save_path=save_path, category=self._category)

    def select_files(
        self, info_hash: str, files: tuple[TorrentFile, ...], selected: frozenset[int], save_path: Path
    ) -> tuple[TorrentFile, ...]:
        """Apply one recorded union to a stopped private transfer and return the verified readback."""
        return self._selective().select_files(info_hash, files, selected, save_path=save_path)

    @property
    def selective(self) -> bool:
        """Whether the private client can fetch metadata only and verify a file selection."""
        return self._torrent_management is not None and hasattr(self._client, "select_files")

    def _selective(self) -> SelectiveTorrentClient:
        if not self.selective:
            msg = "Selective downloads require the private torrent client"
            raise ValueError(msg)
        return cast("SelectiveTorrentClient", self._client)

    def queued_hashes(self) -> frozenset[str]:
        """Lowercase info hashes of every torrent the client already tracks under the AniShift category."""
        return frozenset(info.info_hash.casefold() for info in self._client.torrents(self._category))

    def observe_added(
        self,
        hashes: frozenset[str],
        *,
        sleep: Callable[[float], None] = time.sleep,
        may_observe: Callable[[], bool] | None = None,
    ) -> Iterator[frozenset[str]]:
        """Yield bounded fresh observations of this submission, stopping when all hashes are confirmed."""
        remaining: frozenset[str] = hashes
        for attempt in range(CONFIRM_ATTEMPTS):
            if not remaining or (may_observe is not None and not may_observe()):
                return
            if attempt:
                sleep(CONFIRM_DELAY_S)
            if may_observe is not None and not may_observe():
                return
            present: frozenset[str] = self.queued_hashes() & hashes
            yield present
            remaining -= present
        if remaining:
            logger.warning("Torrent add confirmation exhausted", unconfirmed=len(remaining), attempts=CONFIRM_ATTEMPTS)

    def transfers(self) -> tuple[TorrentInfo, ...]:
        """Read the current state of every transfer in the AniShift category."""
        return self._client.torrents(self._category)

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        """Ask an owned client to run again for ordered transfers this reconciliation must confirm."""
        if self._torrent_management is not None:
            self._torrent_management.resume_unconfirmed(hashes)

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        """Read known episode dates without another title or prequel search."""
        if self._title_catalog is None:
            msg = "No title catalog is configured"
            raise ValueError(msg)
        return self._title_catalog.airing_schedule(anilist_id)

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> Franchise:
        """Return the franchise view rooted at one entry, remembering its graph while fresh."""
        return franchise_view(self._franchise_graph(anilist_id, cancel), anilist_id)

    def _franchise_graph(self, anilist_id: int, cancel: CancellationToken | None = None) -> FranchiseGraph:
        now: float = self._clock()
        with self._memory_lock:
            entry: _Remembered = self._remembered(anilist_id)
            graph: FranchiseGraph | None = entry.graph if entry.fresh(entry.graph_at, now) else None
        if graph is None:
            fetched: FranchiseGraph = self._titles().franchise(anilist_id, cancel=cancel)
            with self._memory_lock:
                entry = self._remembered(anilist_id)
                if fetched.complete or entry.graph is None or not entry.graph.complete:
                    entry.graph = fetched
                entry.graph_at = now
                graph = entry.graph
        return graph

    def episodes(self, anilist_id: int) -> EpisodeListing:
        """Return the episode list, keeping ani.zip data when the airing schedule is unavailable."""
        return self.read_listing(anilist_id).listing

    def read_listing(
        self, anilist_id: int, *, saved: AniZipMapping | None = None, targets: Collection[int] = ()
    ) -> ListingRead:
        """Read the episode list with bridged numbering and saved mapping fallback.

        A remembered mapping leaving any of *targets* without numbering is read again from ani.zip.
        Without the franchise graph the list keeps a warning and the entry counts as a movie only when
        the chosen mapping says so.
        """
        now: float = self._clock()
        graph_movie: bool | None = self._graph_movie(anilist_id, now)
        remembered: bool = self._remembered_mapping(anilist_id, now) is not None
        empty: AniZipMapping = AniZipMapping(None, None, None, (), (), None, {})
        fresh: AniZipMapping | None
        try:
            fresh = self._mapping(anilist_id, now)
        except AniShiftError, OSError, ValueError:
            fresh = None
        ids: ArmIds | None = self._bridge_ids(anilist_id)
        tvdb_season: int | None = ids.tvdb_season if ids is not None else None
        if (
            remembered
            and fresh is not None
            and any(
                numbering_gap(fresh, number, tvdb_season, movie=_movie(graph_movie, fresh)) is not None
                for number in targets
            )
        ):
            try:
                fresh = self._mapping(anilist_id, now, refresh=True)
            except AniShiftError, OSError, ValueError:
                logger.info("Remembered episode mapping kept", provider="anizip")
        from_anidb: bool = False
        if fresh is not None:
            fresh, from_anidb = self._anidb_numbering(fresh, ids)
        live: bool = fresh is not None and bool(fresh.raw_episodes)
        mapping: AniZipMapping = fresh if fresh is not None and live else saved or fresh or empty
        if mapping is not fresh:
            from_anidb = False
        if saved is not None and mapping is saved:
            logger.info("Episode mapping snapshot used", provider="anizip")
        kitsu: int | None = mapping.kitsu_id if mapping.kitsu_id is not None else self._kitsu_id(anilist_id, fresh)
        if kitsu != mapping.kitsu_id:
            mapping = replace(mapping, kitsu_id=kitsu)
        movie: bool = _movie(graph_movie, mapping)
        schedule: SeasonAiring | None
        failed: bool
        schedule, failed = self._schedule(anilist_id, now)
        failed = failed or graph_movie is None
        retry: float = self.blocked_until(("anilist",)) if failed else 0.0
        listing: EpisodeListing = episode_listing(
            anilist_id,
            mapping,
            schedule.status.value if schedule is not None else self._known_status(anilist_id),
            schedule.episode_count if schedule is not None else None,
            tuple(ListedEpisode(item.episode, airs_at=item.airing_at) for item in schedule.episodes)
            if schedule is not None
            else (),
            datetime.fromtimestamp(now, UTC),
            schedule_warning=_SCHEDULE_WARNING if failed else None,
            schedule_retry_at=datetime.fromtimestamp(retry, UTC) if retry > now else None,
        )
        source: str = "anidb" if from_anidb else "anilist" if mapping.episodes else "none"
        return ListingRead(listing, mapping, live, tvdb_season, source, movie)

    def _bridge_ids(self, anilist_id: int) -> ArmIds | None:
        if self._id_catalog is None:
            return None
        try:
            return self._id_catalog.ids(anilist_id)
        except (AniShiftError, OSError, ValueError) as error:
            _bridge_failed("arm", error)
            return None

    def _graph_movie(self, anilist_id: int, now: float) -> bool | None:
        try:
            graph: FranchiseGraph = self._context_graph(anilist_id, now)
        except (AniShiftError, OSError, ValueError) as error:
            code: ErrorCode | None = error.context.code if isinstance(error, AniShiftError) else None
            logger.warning("Listing franchise unavailable", provider="anilist", code=code)
            return None
        return graph.nodes[anilist_id].get("format") == _MOVIE_FORMAT

    def _anidb_numbering(self, mapping: AniZipMapping, ids: ArmIds | None) -> tuple[AniZipMapping, bool]:
        anidb: AniZipMapping | None = None
        if not mapping.episodes and ids is not None and ids.anidb_id is not None and self._anidb_catalog is not None:
            try:
                anidb = self._anidb_catalog.mapping_by_anidb(ids.anidb_id)
            except (AniShiftError, OSError, ValueError) as error:
                _bridge_failed("anizip", error)
        if anidb is not None:
            mapping = replace(
                mapping,
                kitsu_id=anidb.kitsu_id if anidb.kitsu_id is not None else mapping.kitsu_id,
                catalog_type=anidb.catalog_type if anidb.catalog_type is not None else mapping.catalog_type,
            )
        if anidb is not None and anidb.raw_episodes:
            mapping = replace(
                mapping,
                episode_count=anidb.episode_count if anidb.episode_count is not None else mapping.episode_count,
                episodes=anidb.episodes,
                specials=anidb.specials or mapping.specials,
                raw_episodes=anidb.raw_episodes,
            )
        return mapping, anidb is not None and bool(anidb.episodes)

    def _kitsu_id(self, anilist_id: int, fresh: AniZipMapping | None) -> int | None:
        if fresh is not None and fresh.kitsu_id is not None:
            return fresh.kitsu_id
        if self._kitsu_catalog is None:
            return None
        try:
            return self._kitsu_catalog.kitsu_id(anilist_id)
        except (AniShiftError, OSError, ValueError) as error:
            _bridge_failed("kitsu", error)
            return None

    def offer(self, key: EpisodeKey, switches: SourceSwitches | None = None) -> EpisodeOffer:
        """Rank the live stream candidates of one episode against its remembered identity."""
        return self.search_episode(key, switches or SourceSwitches())[0]

    def search_episode(
        self,
        key: EpisodeKey,
        switches: SourceSwitches,
        *,
        read: ListingRead | None = None,
        on_partial: Callable[[SearchSnapshot], None] | None = None,
        exclude: Callable[[StreamCandidate], bool] | None = None,
    ) -> tuple[EpisodeOffer, dict[str, object]]:
        """Search the enabled sources using exactly the mapping used for the episode listing."""
        read = read or self.read_listing(key.anilist_id)
        if self._episode_search is None:
            legacy, legacy_target = self.prepare_episode(key, mapping=read.mapping, exclude=exclude)
            numbered: bool = numbering_gap(read.mapping, key.number, read.tvdb_season, movie=read.movie) is None
            return replace(
                legacy,
                numbering=numbered,
                suggestion=legacy.suggestion if numbered else None,
                status=None if numbered else "brak numeracji",
            ), legacy_target
        graph: FranchiseGraph = self._context_graph(key.anilist_id, self._clock())
        candidate: TitleCandidate = graph_candidate(graph, key.anilist_id)
        movie: bool = candidate.format == _MOVIE_FORMAT
        if movie and key.number != 1:
            msg: str = "A movie has only its first row"
            raise ValueError(msg)
        numbering: bool = numbering_gap(read.mapping, key.number, read.tvdb_season, movie=movie) is None
        target: dict[str, object] = identity_target(
            graph, key.anilist_id, read.mapping, key.number, numbering=numbering
        )
        absolute: object = target.get("absolute")
        request: EpisodeRequest = EpisodeRequest(
            key,
            key.number,
            movie,
            candidate.country == _DONGHUA_COUNTRY,
            read.mapping.kitsu_id,
            None,
            episode_phrases(
                candidate,
                graph_season_context(graph, candidate),
                key.number,
                manual=True,
                absolute=absolute if type(absolute) is int else None,
            ),
            target,
            numbering,
        )
        result: SearchOutcome = self._episode_search.manual_offer(request, switches, on_partial)
        ranked: tuple[RankedCandidate, ...] = tuple(
            row for row in result.snapshot.candidates if exclude is None or not exclude(row.stream)
        )
        counts: dict[str, int] = {
            verdict.value: sum(row.identity.verdict is verdict for row in ranked) for verdict in IdentityVerdict
        }
        offer: EpisodeOffer = EpisodeOffer(
            key,
            ranked,
            suggestion(ranked, numbering=numbering)[0],
            datetime.fromtimestamp(self._clock(), UTC),
            counts,
            numbering,
            tuple(source_line(row) for row in result.snapshot.sources),
            "brak numeracji" if not numbering else offer_status(result.snapshot.sources),
        )
        logger.info(
            "Episode search completed", count=len(ranked), numbering=numbering, suggested=offer.suggestion is not None
        )
        return offer, target

    def prepare_episode(
        self,
        key: EpisodeKey,
        *,
        mapping: AniZipMapping | None = None,
        exclude: Callable[[StreamCandidate], bool] | None = None,
    ) -> tuple[EpisodeOffer, dict[str, object]]:
        """Read one live offer and its target; *mapping* replaces ani.zip, *exclude* drops files before ranking."""
        now: float = self._clock()
        graph: FranchiseGraph = self._context_graph(key.anilist_id, now)
        if mapping is None:
            mapping = self._mapping(key.anilist_id, now)
        movie: bool = graph.nodes[key.anilist_id].get("format") == _MOVIE_FORMAT
        if movie and key.number != 1:
            msg = "A movie has only its first row"
            raise ValueError(msg)
        streams: tuple[StreamCandidate, ...] = ()
        target: dict[str, object] = identity_target(graph, key.anilist_id, mapping, key.number)
        try:
            if mapping.kitsu_id is not None and movie:
                streams = self._streams().movie_streams(mapping.kitsu_id)
            elif mapping.kitsu_id is not None:
                streams = self._streams().streams(mapping.kitsu_id, key.number)
        except (AniShiftError, OSError, ValueError) as error:
            self._decision(source_error("torrentio", key.anilist_id, key.number, error))
            raise
        if exclude is not None:
            streams = tuple(stream for stream in streams if not exclude(stream))
        donghua: bool = graph.nodes[key.anilist_id].get("countryOfOrigin") == _DONGHUA_COUNTRY
        ranked: tuple[RankedCandidate, ...] = rank_candidates(
            target, streams_releases(streams, pack_name=_pack_name), donghua=donghua
        )
        counts: dict[str, int] = {
            verdict.value: sum(1 for item in ranked if item.identity.verdict is verdict) for verdict in IdentityVerdict
        }
        suggested: int | None = suggestion(ranked, numbering=True)[0]
        logger.info("Episode offer ranked", count=len(ranked), suggested=suggested is not None, movie=movie)
        offer: EpisodeOffer = EpisodeOffer(key, ranked, suggested, datetime.fromtimestamp(self._clock(), UTC), counts)
        if mapping.kitsu_id is not None:
            self._decision(offer_check(offer, target, streams, donghua=donghua))
        return offer, target

    def _titles(self) -> TitleCatalog:
        if self._title_catalog is None:
            msg = "No title catalog is configured"
            raise ValueError(msg)
        return self._title_catalog

    def _streams(self) -> StreamSource:
        if self._stream_source is None:
            msg = "No stream source is configured"
            raise ValueError(msg)
        return self._stream_source

    def _remembered(self, anilist_id: int) -> _Remembered:
        entry: _Remembered = self._memory.setdefault(anilist_id, _Remembered())
        self._memory.move_to_end(anilist_id)
        while len(self._memory) > _REMEMBERED_ENTRIES:
            self._memory.popitem(last=False)
        return entry

    def _remembered_mapping(self, anilist_id: int, now: float) -> AniZipMapping | None:
        with self._memory_lock:
            entry: _Remembered = self._remembered(anilist_id)
            return entry.mapping if entry.mapping is not None and entry.fresh(entry.mapping_at, now) else None

    def _mapping(self, anilist_id: int, now: float, *, refresh: bool = False) -> AniZipMapping:
        remembered: AniZipMapping | None = None if refresh else self._remembered_mapping(anilist_id, now)
        if remembered is not None:
            return remembered
        if self._episode_catalog is None:
            msg = "No episode catalog is configured"
            raise ValueError(msg)
        try:
            mapping: AniZipMapping = self._episode_catalog.mapping(anilist_id)
        except (AniShiftError, OSError, ValueError) as error:
            self._decision(source_error("ani.zip", anilist_id, None, error))
            raise
        self._decision(
            {
                "source": "ani.zip",
                "key": {"anilist_id": anilist_id, "number": None},
                "episodes": len(mapping.raw_episodes),
                "with_length": sum(row.get("length") is not None for row in mapping.raw_episodes.values()),
            }
        )
        with self._memory_lock:
            entry: _Remembered = self._remembered(anilist_id)
            entry.mapping, entry.mapping_at = mapping, now
        return mapping

    def _schedule(self, anilist_id: int, now: float) -> tuple[SeasonAiring | None, bool]:
        with self._memory_lock:
            entry: _Remembered = self._remembered(anilist_id)
            if entry.schedule is not None and entry.fresh(entry.schedule_at, now):
                return entry.schedule, False
        if self.blocked_until(("anilist",)) > now:
            return None, True
        try:
            schedule: SeasonAiring = self._titles().airing_schedule(anilist_id)
        except AniShiftError as error:
            if error.context.code is not ErrorCode.TITLE_CATALOG_FAILED:
                raise
            logger.warning("Airing schedule unavailable", provider="anilist", code=error.context.code)
            return None, True
        with self._memory_lock:
            entry = self._remembered(anilist_id)
            entry.schedule, entry.schedule_at = schedule, now
        return schedule, False

    def _known_status(self, anilist_id: int) -> str:
        with self._memory_lock:
            for entry in self._memory.values():
                status: object = entry.graph.nodes.get(anilist_id, {}).get("status") if entry.graph else None
                if isinstance(status, str):
                    return status
        return _UNKNOWN_STATUS

    def _context_graph(self, anilist_id: int, now: float) -> FranchiseGraph:
        known: FranchiseGraph | None = self._known_graph(anilist_id, now)
        graph: FranchiseGraph = known if known is not None else self._franchise_graph(anilist_id)
        if anilist_id not in graph.nodes:
            msg = "The entry is absent from its own franchise"
            raise ValueError(msg)
        return graph

    def _known_graph(self, anilist_id: int, now: float) -> FranchiseGraph | None:
        """Pick a fresh graph holding the entry: complete traversal, then its own root, then the lowest root ID."""
        with self._memory_lock:
            known: list[tuple[bool, bool, int, FranchiseGraph]] = [
                (
                    bool(franchise_traversal(anilist_id, entry.graph.nodes, entry.graph.queried)[2]),
                    root != anilist_id,
                    root,
                    entry.graph,
                )
                for root, entry in self._memory.items()
                if entry.graph is not None and anilist_id in entry.graph.nodes and entry.fresh(entry.graph_at, now)
            ]
            if not known:
                return None
            chosen: tuple[bool, bool, int, FranchiseGraph] = min(known, key=lambda item: item[:3])
            self._memory.move_to_end(chosen[2])
        return chosen[3]

    def transfer_files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Read selection and completion for one tracked transfer."""
        return self._client.files(info_hash)

    def prepare_client(self) -> None:
        """Let an owned client take up its unfinished transfers again when the resident starts."""
        if self._torrent_management is not None:
            self._torrent_management.prepare()

    def finish_transfers(self) -> None:
        """Release completed seeds only through the private process owner."""
        if self._torrent_management is not None:
            self._torrent_management.finish_transfers()

    def close_client(self) -> None:
        """Close an owned client on an explicit end, leaving an external one running."""
        if self._torrent_management is not None:
            self._torrent_management.close_owned()

    def control_transfer(self, info_hash: str, action: str) -> None:
        """Apply an explicit operation to a private transfer without deleting media."""
        if self._torrent_management is None:
            msg = "This torrent client is external and cannot be managed automatically"
            raise ValueError(msg)
        self._torrent_management.transfer_action(info_hash, action)

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        """Return confirmed hashes whose private client no longer owns the media location."""
        if self._torrent_management is None:
            return frozenset()
        return self._torrent_management.release_completed(hashes)

    def released_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        """Read durable release evidence without contacting the torrent client."""
        if self._torrent_management is None or not hashes:
            return frozenset()
        return self._torrent_management.released_hashes(hashes)

    def close(self) -> None:
        """Release private torrent process resources."""
        if self._torrent_management is not None:
            self._torrent_management.close()

    def finalizable_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        """Read which hashes can progress without starting or contacting a torrent client."""
        if self._torrent_management is None:
            return frozenset()
        return self._torrent_management.finalizable_hashes(hashes)

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


def graph_candidate(graph: FranchiseGraph, selected_id: int) -> TitleCandidate:
    """Project an already fetched catalog node with the catalog's canonical decoder."""
    from anishift.services.catalog.anilist import candidate_from_node  # noqa: PLC0415

    candidate: TitleCandidate | None = candidate_from_node(graph.nodes[selected_id])
    if candidate is None:
        msg: str = "The selected catalog entry has no title"
        raise ValueError(msg)
    return candidate


def graph_season_context(graph: FranchiseGraph, candidate: TitleCandidate) -> SeasonContext:
    """Calculate the same season context as catalog traversal using only fetched nodes."""
    from anishift.services.catalog.anilist import graph_prequels  # noqa: PLC0415

    return _season_context(candidate, graph_prequels(graph, candidate))


def _season_context(candidate: TitleCandidate, prequels: Sequence[PrequelEntry]) -> SeasonContext:
    return SeasonContext(
        index=sum(not entry.cour for entry in prequels) + (0 if candidate.is_cour() else 1),
        offset=sum(entry.episodes for entry in prequels),
        episodes=candidate.episodes,
    )


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


def _pack_name(name: str) -> bool:
    return parse_release_name(name).is_pack


def _seeding_stops(preferences: Mapping[str, object]) -> bool:
    """Whether the client stops a torrent right after its download completes."""
    return all(preferences.get(key) == value for key, value in SEEDING_STOP_PREFERENCES.items())


def _choice_order(choice: ReleaseChoice) -> tuple[int, int, Decimal, int]:
    episode: Decimal | None = choice.episode
    if episode is None:
        return (int(choice.other_season), 1, Decimal(0), 0)
    return (int(choice.other_season), 0, episode, -(choice.name.version or 0))


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
