"""Source contracts for paged episode acquisition and complete torrent inventories."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from threading import Lock
from typing import TYPE_CHECKING, Final, Protocol

import httpx

from anishift.application.episode_releases import NAME_PRIORITY, EpisodeRelease, TsukiHimeFiles, merge_releases
from anishift.application.episode_selection import (
    EpisodeKey,
    RankedCandidate,
    StreamCandidate,
    list_order,
    rank_candidates,
)
from anishift.errors import AniShiftError
from anishift.services.http_requests import BudgetExhausted, DeadlineExceeded, ProviderCooldown, RequestControl
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.application.acquisition import SeasonContext, StreamSource, TorrentSource
    from anishift.application.episode_releases import SourceName
    from anishift.services.catalog.types import TitleCandidate
    from anishift.services.torrents.types import Release

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SOURCE_TIMEOUT_S: Final[float] = 30.0
"""Caller deadline for an entire source operation, including admission and pagination."""

FIRST_SNAPSHOT_S: Final[float] = 3.0
"""Maximum initial wait before publishing even an empty search snapshot."""

COMPLETION_READS: Final[int] = 10
"""Maximum inventory requests per episode search."""


class SourceState(StrEnum):
    """Completeness and availability of one source operation."""

    DONE = "done"
    UNFINISHED = "unfinished"
    FAILED = "failed"
    DISABLED = "disabled"
    SKIPPED = "skipped"
    NO_TITLE = "no_title"
    NO_KITSU = "no_kitsu"


class FailureKind(StrEnum):
    """Safe source failure categories independent of adapter wrappers."""

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class ReadOutcome(StrEnum):
    """Outcome of a complete inventory visit, never of its intermediate ID lookup."""

    LISTED = "listed"
    EMPTY = "empty"
    NO_HASH = "no_hash"
    PENDING = "pending"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class SourceSwitches:
    """Source preferences captured once at the start of an episode search."""

    tsukihime: bool = True
    torrentio: bool = True
    nyaa: bool = True
    knaben: bool = True
    nekobt: bool = True

    def enabled(self, source: SourceName) -> bool:
        """Return whether this snapshot allows reads from the source."""
        return bool(getattr(self, source))


@dataclass(frozen=True, slots=True)
class EpisodeRequest:
    """One local episode and its catalog identity shared by all release sources."""

    key: EpisodeKey
    number: int
    movie: bool
    donghua: bool
    kitsu_id: int | None
    tsukihime_id: int | None
    phrases: tuple[str, ...]
    target: Mapping[str, object]
    numbering: bool


@dataclass(frozen=True, slots=True)
class SourceResult:
    """Complete or partial source answer with a payload-free failure description."""

    source: SourceName
    state: SourceState
    streams: tuple[StreamCandidate, ...] = ()
    failure: FailureKind | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SearchSnapshot:
    """Full current ranking and source state, safe to replace an earlier snapshot."""

    candidates: tuple[RankedCandidate, ...]
    sources: tuple[SourceResult, ...]
    pending: tuple[SourceName, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Final search snapshot and inventory outcomes for the caller."""

    snapshot: SearchSnapshot
    outcomes: Mapping[str, ReadOutcome]


def http_status(error: BaseException) -> int | None:
    """Extract an HTTP status from a preserved adapter exception chain."""
    while True:
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code
        if error.__cause__ is None:
            return None
        error = error.__cause__


def failure_kind(error: BaseException) -> FailureKind:
    """Classify an adapter failure by its original transport cause."""
    if http_status(error) == HTTPStatus.TOO_MANY_REQUESTS:
        return FailureKind.RATE_LIMITED
    while True:
        if isinstance(error, httpx.TimeoutException):
            return FailureKind.TIMEOUT
        if isinstance(error, ProviderCooldown):
            return FailureKind.RATE_LIMITED
        if error.__cause__ is None:
            return FailureKind.ERROR
        error = error.__cause__


def _caused_by(error: BaseException, kind: type[BaseException]) -> bool:
    return isinstance(error, kind) or (error.__cause__ is not None and _caused_by(error.__cause__, kind))


def _failed(
    source: SourceName, streams: Sequence[StreamCandidate], completed: int, error: BaseException
) -> SourceResult:
    unfinished: bool = completed > 0 or _caused_by(error, DeadlineExceeded) or _caused_by(error, BudgetExhausted)
    failure: FailureKind | None = None if _caused_by(error, BudgetExhausted) else failure_kind(error)
    status: int | None = http_status(error)
    logger.warning("Episode source interrupted", provider=source, failure=failure, completed=completed)
    return SourceResult(
        source,
        SourceState.UNFINISHED if unfinished else SourceState.FAILED,
        tuple(streams),
        failure,
        str(status) if status is not None else failure,
    )


def episode_phrases(
    candidate: TitleCandidate, context: SeasonContext, number: int, *, manual: bool, absolute: int | None
) -> tuple[str, ...]:
    """Build shared local and season queries, appending absolute queries only for manual search."""
    from anishift.services.torrents.names import base_title  # noqa: PLC0415

    full: bool = candidate.format in {"OVA", "SPECIAL"}
    titles: tuple[str, ...] = tuple(
        dict.fromkeys(title if full else base_title(title) for title in (candidate.romaji, candidate.english) if title)
    )
    if candidate.format == "MOVIE":
        return titles
    phrases: list[str] = []
    for title in titles:
        phrases.append(f"{title} - {number:02d}")
        if not full and (context.index > 1 or candidate.format == "TV"):
            phrases.append(f"{title} S{context.index:02d}E{number:02d}")
    if manual and not full and absolute is not None and absolute != number:
        phrases.extend(f"{title} - {absolute:02d}" for title in titles)
    return tuple(dict.fromkeys(phrases))


def _release_stream(release: Release) -> StreamCandidate:
    return StreamCandidate(
        release.info_hash,
        None,
        None,
        None,
        release.title,
        None,
        release.seeders,
        release.size_text,
        "Nyaa",
        (),
        (),
        source="nyaa",
        subtitle_languages=(release.subtitle_language,) if release.subtitle_language else (),
    )


def source_line(result: SourceResult) -> str:
    """Render a source status without exposing adapter messages or URLs."""
    label: str = {
        "tsukihime": "TsukiHime",
        "nyaa": "Nyaa",
        "nekobt": "nekoBT",
        "knaben": "Knaben",
        "torrentio": "Torrentio",
    }[result.source]
    state: str = {
        SourceState.DONE: "gotowe",
        SourceState.UNFINISHED: "niedokończone",
        SourceState.FAILED: "niedostępne",
        SourceState.DISABLED: "wyłączone",
        SourceState.SKIPPED: "pominięte",
        SourceState.NO_TITLE: "brak tytułu",
        SourceState.NO_KITSU: "brak Kitsu ID",
    }[result.state]
    detail: str | None = (
        {FailureKind.TIMEOUT: "limit czasu", FailureKind.RATE_LIMITED: "limit dostawcy", FailureKind.ERROR: "błąd"}.get(
            result.failure
        )
        if result.failure
        else None
    )
    return f"{label}: {state}" + (
        f" ({result.detail if result.detail and result.detail.isdigit() else detail})" if detail else ""
    )


def offer_status(results: Sequence[SourceResult]) -> str | None:
    """Distinguish unavailable sources from an ordinary successful empty search."""
    enabled: tuple[SourceResult, ...] = tuple(row for row in results if row.state is not SourceState.DISABLED)
    if not enabled:
        return "Wszystkie źródła wyłączone (Ustawienia)"
    if all(
        row.state in {SourceState.FAILED, SourceState.NO_TITLE, SourceState.NO_KITSU, SourceState.UNFINISHED}
        and not row.streams
        for row in enabled
    ):
        return "Brak wyników — źródła niedostępne"
    return None


@dataclass(slots=True)
class _ListingCache:
    files: dict[str, TsukiHimeFiles] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def remember(self, info_hash: str, files: TsukiHimeFiles | None) -> None:
        if files is not None and files.files:
            with self.lock:
                self.files[info_hash] = files

    def snapshot(self) -> dict[str, TsukiHimeFiles]:
        with self.lock:
            return dict(self.files)


class CompletionQueue:
    """Visit each release once per check, retaining retry order across checks."""

    def __init__(self, order: Callable[[Sequence[RankedCandidate]], tuple[RankedCandidate, ...]]) -> None:
        self._order: Callable[[Sequence[RankedCandidate]], tuple[RankedCandidate, ...]] = order
        self._visits: dict[EpisodeKey, dict[str, int]] = {}
        self._lock: Lock = Lock()

    def next(
        self,
        key: EpisodeKey,
        candidates: Sequence[RankedCandidate],
        visited: set[str],
        listed: Mapping[str, TsukiHimeFiles],
    ) -> RankedCandidate | None:
        """Choose an unvisited row, preferring releases not visited in previous checks."""
        available: tuple[RankedCandidate, ...] = tuple(
            row
            for row in self._order(candidates)
            if row.stream.info_hash not in visited and row.stream.info_hash not in listed
        )
        with self._lock:
            previous: dict[str, int] = self._visits.setdefault(key, {})
            chosen: RankedCandidate | None = min(
                available, key=lambda row: previous.get(row.stream.info_hash, 0), default=None
            )
            if chosen is not None:
                info_hash: str = chosen.stream.info_hash
                previous[info_hash] = previous.get(info_hash, 0) + 1
        return chosen


def _listing_read(lookup: TsukiHimeLookup) -> ReadOutcome:
    if lookup.status == HTTPStatus.ACCEPTED:
        return ReadOutcome.PENDING
    if lookup.status == HTTPStatus.NOT_FOUND:
        return ReadOutcome.NO_HASH
    if lookup.status == HTTPStatus.TOO_MANY_REQUESTS:
        return ReadOutcome.RATE_LIMITED
    return ReadOutcome.LISTED if lookup.files and lookup.files.files else ReadOutcome.EMPTY


def _wait_sources(futures: Sequence[Future[SourceResult]], timeout: float | None) -> set[Future[SourceResult]]:
    return wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)[0]


def _has_more(page: TextPage, received: int, size: int) -> bool:
    return received < page.total if page.total is not None else len(page.streams) >= size


class EpisodeSearch:
    """Query all enabled sources concurrently and complete ranked inventory visits."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        torrentio: StreamSource,
        nyaa: TorrentSource,
        knaben: PagedSource,
        nekobt: PagedSource,
        tsukihime: TsukiHimeApi,
        request_control: RequestControl,
        pack_name: Callable[[str], bool],
        clock: Callable[[], float] = time.monotonic,
        source_timeout_s: float = SOURCE_TIMEOUT_S,
        wait_sources: Callable[
            [Sequence[Future[SourceResult]], float | None], set[Future[SourceResult]]
        ] = _wait_sources,
    ) -> None:
        self._torrentio: StreamSource = torrentio
        self._nyaa: TorrentSource = nyaa
        self._paged: dict[SourceName, tuple[PagedSource, int]] = {"knaben": (knaben, 300), "nekobt": (nekobt, 100)}
        self._tsukihime: TsukiHimeApi = tsukihime
        self._control: RequestControl = request_control
        self._pack_name: Callable[[str], bool] = pack_name
        self._clock: Callable[[], float] = clock
        self._timeout: float = source_timeout_s
        self._wait_sources: Callable[[Sequence[Future[SourceResult]], float | None], set[Future[SourceResult]]] = (
            wait_sources
        )
        self._listings: _ListingCache = _ListingCache()
        self._completion: CompletionQueue = CompletionQueue(list_order)

    def forget(self, source: SourceName) -> None:
        """Discard source-owned inventory memory after disabling TsukiHime."""
        if source == "tsukihime":
            with self._listings.lock:
                self._listings.files.clear()

    def manual_offer(
        self,
        request: EpisodeRequest,
        switches: SourceSwitches,
        on_partial: Callable[[SearchSnapshot], None] | None = None,
    ) -> SearchOutcome:
        """Return the final ranked offer, publishing full snapshots as source answers arrive."""
        results: dict[SourceName, SourceResult] = {}
        for source in NAME_PRIORITY:
            if not switches.enabled(source):
                self.forget(source)
                results[source] = SourceResult(source, SourceState.DISABLED)
        first_at: float = self._clock() + FIRST_SNAPSHOT_S
        first_sent: bool = False
        with ThreadPoolExecutor(max_workers=len(NAME_PRIORITY), thread_name_prefix="episode-source") as pool:
            pending: dict[Future[SourceResult], SourceName] = {
                pool.submit(self._answer, source, request): source
                for source in NAME_PRIORITY
                if switches.enabled(source)
            }
            while pending:
                done: set[Future[SourceResult]] = self._wait_sources(
                    tuple(pending), None if first_sent else max(0.0, first_at - self._clock())
                )
                for future in done:
                    results[pending.pop(future)] = future.result()
                if not first_sent and self._clock() >= first_at:
                    first_sent = True
                if on_partial is not None:
                    on_partial(self._snapshot(request, results, tuple(pending.values()), switches))
            outcomes: dict[str, ReadOutcome] = (
                pool.submit(self._complete, request, results, switches, on_partial).result()
                if switches.tsukihime
                else {}
            )
        return SearchOutcome(self._snapshot(request, results, (), switches), outcomes)

    def _snapshot(
        self,
        request: EpisodeRequest,
        results: Mapping[SourceName, SourceResult],
        pending: tuple[SourceName, ...],
        switches: SourceSwitches,
    ) -> SearchSnapshot:
        streams: tuple[StreamCandidate, ...] = tuple(
            stream for source in NAME_PRIORITY if source in results for stream in results[source].streams
        )
        releases: tuple[EpisodeRelease, ...] = merge_releases(
            streams, self._listings.snapshot() if switches.tsukihime else {}, pack_name=self._pack_name
        )
        return SearchSnapshot(
            rank_candidates(request.target, releases, donghua=request.donghua),
            tuple(results[source] for source in NAME_PRIORITY if source in results),
            tuple(source for source in NAME_PRIORITY if source in pending),
        )

    def _answer(self, source: SourceName, request: EpisodeRequest) -> SourceResult:
        with self._control.scope("episode_search", {}, deadline_s=self._timeout):
            if source == "tsukihime":
                return self._tsukihime_answer(request, [])
            if source == "nyaa":
                return self._nyaa_answer(request)
            if source in self._paged:
                return self._paged_answer(source, request)
            try:
                return self._torrentio_answer(request)
            except (AniShiftError, httpx.HTTPError, OSError, ValueError) as error:
                return _failed(source, (), 0, error)

    def _nyaa_answer(self, request: EpisodeRequest) -> SourceResult:
        from anishift.services.torrents.categories import SEARCH_CATEGORIES  # noqa: PLC0415

        streams: list[StreamCandidate] = []
        completed: int = 0
        try:
            for phrase, category in (
                (phrase, category) for phrase in request.phrases for category in SEARCH_CATEGORIES
            ):
                streams.extend(_release_stream(row) for row in self._nyaa.search(phrase, categories=(category,)))
                completed += 1
        except (AniShiftError, httpx.HTTPError, OSError, ValueError) as error:
            return _failed("nyaa", streams, completed, error)
        return SourceResult("nyaa", SourceState.DONE, tuple(streams))

    def _paged_answer(self, source: SourceName, request: EpisodeRequest) -> SourceResult:
        streams: list[StreamCandidate] = []
        completed: int = 0
        complete: bool = True
        adapter, size = self._paged[source]
        try:
            for phrase in request.phrases:
                first: TextPage = adapter.search(phrase, 0)
                streams.extend(first.streams)
                completed += 1
                if not _has_more(first, len(first.streams), size):
                    continue
                second: TextPage = adapter.search(phrase, 1)
                streams.extend(second.streams)
                completed += 1
                complete = complete and not _has_more(second, len(first.streams) + len(second.streams), size)
        except (AniShiftError, httpx.HTTPError, OSError, ValueError) as error:
            return _failed(source, streams, completed, error)
        return SourceResult(source, SourceState.DONE if complete else SourceState.UNFINISHED, tuple(streams))

    def _torrentio_answer(self, request: EpisodeRequest) -> SourceResult:
        if request.kitsu_id is None:
            return SourceResult("torrentio", SourceState.NO_KITSU)
        streams: tuple[StreamCandidate, ...] = (
            self._torrentio.movie_streams(request.kitsu_id)
            if request.movie
            else self._torrentio.streams(request.kitsu_id, request.number)
        )
        return SourceResult("torrentio", SourceState.DONE, streams)

    def _tsukihime_answer(self, request: EpisodeRequest, streams: list[StreamCandidate]) -> SourceResult:
        identifier: int | None = request.tsukihime_id
        completed: int = 0
        try:
            if identifier is None:
                identifier = self._tsukihime.anime_id(request.key.anilist_id)
            if identifier is None:
                return SourceResult("tsukihime", SourceState.NO_TITLE)
            offset: int = 0
            for _ in range(2):
                page: TsukiHimePage = self._tsukihime.episode_page(
                    identifier, 1 if request.movie else request.number, offset
                )
                streams.extend(page.streams)
                completed += 1
                offset = page.start + len(page.streams)
                if offset >= page.total:
                    return SourceResult("tsukihime", SourceState.DONE, tuple(streams))
                if not page.streams:
                    break
            return SourceResult("tsukihime", SourceState.UNFINISHED, tuple(streams))
        except (AniShiftError, httpx.HTTPError, OSError, ValueError) as error:
            return _failed("tsukihime", streams, completed, error)

    def _complete(
        self,
        request: EpisodeRequest,
        results: Mapping[SourceName, SourceResult],
        switches: SourceSwitches,
        on_partial: Callable[[SearchSnapshot], None] | None,
    ) -> dict[str, ReadOutcome]:
        outcomes: dict[str, ReadOutcome] = {}
        visited: set[str] = set()
        remaining: int = COMPLETION_READS
        with self._control.scope("episode_listings", {"tsukihime": COMPLETION_READS}, deadline_s=self._timeout):
            while remaining:
                snapshot: SearchSnapshot = self._snapshot(request, results, (), switches)
                chosen: RankedCandidate | None = self._completion.next(
                    request.key, snapshot.candidates, visited, self._listings.snapshot()
                )
                if chosen is None:
                    break
                info_hash: str = chosen.stream.info_hash
                visited.add(info_hash)
                outcome, used = self._visit(chosen.stream, remaining)
                remaining -= used
                if outcome is not None:
                    outcomes[info_hash] = outcome
                if on_partial is not None:
                    on_partial(self._snapshot(request, results, (), switches))
        return outcomes

    def _visit(self, stream: StreamCandidate, budget: int) -> tuple[ReadOutcome | None, int]:
        used: int = 0
        try:
            used += 1
            lookup: TsukiHimeLookup = (
                self._tsukihime.torrent_files(stream.torrent_id)
                if stream.torrent_id is not None
                else self._tsukihime.torrent_by_hash(stream.info_hash)
            )
            if (
                stream.torrent_id is None
                and lookup.status == HTTPStatus.OK
                and lookup.files is None
                and lookup.torrent_id is not None
            ):
                if used == budget:
                    return None, used
                used += 1
                lookup = self._tsukihime.torrent_files(lookup.torrent_id)
            outcome: ReadOutcome = _listing_read(lookup)
            if outcome is ReadOutcome.LISTED:
                self._listings.remember(stream.info_hash, lookup.files)
        except (AniShiftError, httpx.HTTPError, OSError, ValueError) as error:
            if _caused_by(error, BudgetExhausted):
                return None, budget
            return {
                FailureKind.TIMEOUT: ReadOutcome.TIMEOUT,
                FailureKind.RATE_LIMITED: ReadOutcome.RATE_LIMITED,
                FailureKind.ERROR: ReadOutcome.FAILED,
            }[failure_kind(error)], used
        else:
            return outcome, used


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
