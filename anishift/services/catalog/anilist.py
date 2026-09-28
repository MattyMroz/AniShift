"""AniList GraphQL catalog: title search and prequel episode offset."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime
from enum import StrEnum
from http import HTTPStatus
from time import perf_counter
from typing import Any, Final

import httpx

from anishift.application.episode_selection import FranchiseGraph, JsonObject, franchise_traversal
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.types import (
    EpisodeAiring,
    PrequelEntry,
    SeasonAiring,
    TitleCandidate,
    TitleStatus,
    is_cour_title,
)
from anishift.utils.logger import get_logger

__all__ = [
    "ANILIST_URL",
    "DEFAULT_SEARCH_LIMIT",
    "MAX_PREQUEL_HOPS",
    "OFFSET_FORMATS",
    "AniListCatalog",
    "parse_franchise_page",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ANILIST_URL: Final[str] = "https://graphql.anilist.co"
"""Public GraphQL endpoint; no key, roughly thirty requests per minute."""

DEFAULT_SEARCH_LIMIT: Final[int] = 7
"""Number of candidates requested for one search."""

DEFAULT_TIMEOUT_S: Final[float] = 20.0
"""Timeout applied to one GraphQL request."""

MAX_PREQUEL_HOPS: Final[int] = 8
"""Largest number of prequel entries read while summing an episode offset."""

OFFSET_FORMATS: Final[frozenset[str]] = frozenset({"TV", "TV_SHORT", "ONA"})
"""Formats counted into an episode offset; movies, specials, and OVAs are skipped."""

SEARCH_QUERY: Final[str] = """
query ($search: String, $limit: Int) { Page(perPage: $limit) { media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
  id title { romaji english native } synonyms seasonYear season format episodes status
  relations { edges { relationType node { id episodes format } } } } } }
"""
"""Search request returning the candidate fields and the direct relation edges."""

RELATIONS_QUERY: Final[str] = """
query ($id: Int) { Media(id: $id) { id episodes format title { romaji english }
  relations { edges { relationType node { id episodes format } } } } }
"""
"""Single-title request used while walking the prequel chain."""

SCHEDULE_QUERY: Final[str] = """
query ($id: Int!, $page: Int!) { Media(id: $id, type: ANIME) {
  id status episodes startDate { year month day }
  airingSchedule(page: $page, perPage: 25) {
    pageInfo { currentPage hasNextPage }
    nodes { episode airingAt }
  }
} }
"""
"""Known airing dates for one season, without filtering out its past episodes."""

MAX_SCHEDULE_PAGES: Final[int] = 200
"""Bound for a schedule fetch, covering up to five thousand episode entries."""

_PREQUEL_RELATION: Final[str] = "PREQUEL"
"""Relation type naming the entry that airs before the current one."""

_MIN_SHORTENED_WORD: Final[int] = 3
"""Shortest a word may become when a search is retried."""

_SHORTENED_WORD_RATIO: Final[float] = 0.6
"""Fraction of a word kept when a search is retried."""

_CATALOG_SUGGESTION: Final[str] = "Search again in a minute or type the title exactly"
"""Recovery hint shown for every catalog failure."""

_MAX_FRANCHISE_REQUESTS: Final[int] = 4
"""Bound entry latency under AniList's roughly thirty requests per minute limit."""

_FRANCHISE_FIELDS: Final[str] = (
    "id type format status seasonYear startDate { year month day } title { romaji english native }"
)
"""Entry projection preserved at every franchise depth."""


def _franchise_query() -> str:
    fragment: str = _FRANCHISE_FIELDS
    for _ in range(3):
        fragment = _FRANCHISE_FIELDS + " relations { edges { relationType node { " + fragment + " } } }"
    return "query ($ids: [Int]) { Page(perPage: 50) { media(id_in: $ids, type: ANIME) { " + fragment + " } } }"


class _CatalogFailure(StrEnum):
    """Ways one AniList request or body can be unusable."""

    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    MALFORMED = "malformed"


_CATALOG_MESSAGES: Final[dict[_CatalogFailure, str]] = {
    _CatalogFailure.UNREACHABLE: "AniList could not be reached",
    _CatalogFailure.REJECTED: "AniList rejected the request",
    _CatalogFailure.MALFORMED: "AniList returned an unreadable answer",
}
"""Message shown for each catalog failure."""


class AniListCatalog:
    """Synchronous AniList boundary: search titles, then measure a season offset on demand."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        """Bind the catalog to the caller-owned HTTP client."""
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def search(self, text: str, *, limit: int = DEFAULT_SEARCH_LIMIT) -> tuple[TitleCandidate, ...]:
        """Return the candidates AniList proposes for *text*, in its own order."""
        candidates: tuple[TitleCandidate, ...] = self._search_once(text, limit)
        shortened: str | None = _shorten_words(text) if not candidates else None
        retried: bool = shortened is not None
        if shortened is not None:
            candidates = self._search_once(shortened, limit)
        logger.info("Searched AniList for titles", hits=len(candidates), retried=retried)
        return candidates

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        """Return every entry airing before *candidate*, direct prequel first."""
        seen: set[int] = {candidate.anilist_id}
        pending: list[int] = [prequel_id for prequel_id in candidate.prequel_ids if prequel_id not in seen]
        entries: list[PrequelEntry] = []
        while pending and len(entries) < MAX_PREQUEL_HOPS:
            current: int = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            media: Mapping[str, Any] | None = self._media(current)
            entries.append(_prequel_entry(media))
            if media is not None:
                pending.extend(prequel_id for prequel_id in _prequel_ids(media) if prequel_id not in seen)
        return tuple(entries)

    def episode_offset(self, candidate: TitleCandidate) -> int:
        """Return how many episodes aired before *candidate*, following its prequel chain."""
        return sum(entry.episodes for entry in self.prequel_episodes(candidate))

    def franchise(self, anilist_id: int) -> FranchiseGraph:
        """Fetch the depth-three anime graph, expanding missing chain frontiers at most four times."""
        started: float = perf_counter()
        graph: FranchiseGraph = FranchiseGraph(anilist_id, {}, frozenset(), False)
        pending: list[int] = [anilist_id]
        try:
            for _ in range(_MAX_FRANCHISE_REQUESTS):
                data: Mapping[str, Any] = self._post(_franchise_query(), {"ids": pending})
                graph = parse_franchise_page(data, anilist_id, frozenset(pending), graph)
                if graph.complete:
                    break
                _, _, missing = franchise_traversal(anilist_id, graph.nodes, graph.queried)
                pending = sorted(missing)
        except TitleCatalogError:
            logger.warning("Franchise lookup failed", provider="anilist", code=ErrorCode.TITLE_CATALOG_FAILED)
            raise
        logger.info(
            "Franchise lookup completed",
            provider="anilist",
            operation="franchise",
            count=len(graph.nodes),
            complete=graph.complete,
            elapsed_s=perf_counter() - started,
        )
        return graph

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        """Read all available episode dates for that season without inventing missing history."""
        episodes: dict[int, EpisodeAiring] = {}
        for page in range(1, MAX_SCHEDULE_PAGES + 1):
            data: Mapping[str, Any] = self._post(SCHEDULE_QUERY, {"id": anilist_id, "page": page})
            media: object = data.get("Media")
            if not isinstance(media, Mapping) or media.get("id") != anilist_id:
                raise _catalog_error(_CatalogFailure.MALFORMED)
            entries: tuple[EpisodeAiring, ...]
            more: bool
            entries, more = _schedule_page(media.get("airingSchedule"), page)
            if any(entry.episode in episodes and episodes[entry.episode] != entry for entry in entries):
                raise _catalog_error(_CatalogFailure.MALFORMED)
            episodes.update((entry.episode, entry) for entry in entries)
            if not more:
                return SeasonAiring(
                    anilist_id,
                    _status(media.get("status")),
                    _episodes(media),
                    tuple(episodes[number] for number in sorted(episodes)),
                    _start_date(media.get("startDate")),
                )
        raise _catalog_error(_CatalogFailure.MALFORMED)

    def _search_once(self, text: str, limit: int) -> tuple[TitleCandidate, ...]:
        """Send one search request and read its media list."""
        data: Mapping[str, Any] = self._post(SEARCH_QUERY, {"search": text, "limit": limit})
        page: object = data.get("Page")
        media: object = page.get("media") if isinstance(page, Mapping) else None
        if not isinstance(media, list):
            raise _catalog_error(_CatalogFailure.MALFORMED)
        candidates: list[TitleCandidate] = []
        for node in media:
            candidate: TitleCandidate | None = _candidate(node) if isinstance(node, Mapping) else None
            if candidate is not None:
                candidates.append(candidate)
        return tuple(candidates)

    def _media(self, anilist_id: int) -> Mapping[str, Any] | None:
        """Return one title with its relation edges, or ``None`` when AniList knows no such id."""
        data: Mapping[str, Any] = self._post(RELATIONS_QUERY, {"id": anilist_id})
        media: object = data.get("Media")
        if not isinstance(media, Mapping):
            return None
        return media

    def _post(self, query: str, variables: Mapping[str, object]) -> Mapping[str, Any]:
        """Send one GraphQL request and return its ``data`` object."""
        try:
            response: httpx.Response = self._http.post(
                ANILIST_URL,
                json={"query": query, "variables": dict(variables)},
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as error:
            raise _catalog_error(_CatalogFailure.UNREACHABLE) from error
        if response.status_code != HTTPStatus.OK:
            raise _catalog_error(_CatalogFailure.REJECTED)
        try:
            body: object = response.json()
        except ValueError as error:
            raise _catalog_error(_CatalogFailure.MALFORMED) from error
        if isinstance(body, Mapping) and body.get("errors"):
            raise _catalog_error(_CatalogFailure.REJECTED)
        data: object = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(data, Mapping):
            raise _catalog_error(_CatalogFailure.MALFORMED)
        return data


def parse_franchise_page(
    data: object,
    root_id: int,
    queried: frozenset[int],
    previous: FranchiseGraph | None = None,
) -> FranchiseGraph:
    """Merge one GraphQL data page without reordering nodes, titles or relation edges."""
    page: object = data.get("Page") if isinstance(data, Mapping) else None
    media: object = page.get("media") if isinstance(page, Mapping) else None
    if not isinstance(media, list):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    nodes: dict[int, JsonObject] = dict(previous.nodes) if previous else {}
    for node in media:
        _collect_franchise(deepcopy(node), nodes)
    if root_id not in nodes:
        raise _catalog_error(_CatalogFailure.MALFORMED)
    all_queried: frozenset[int] = queried | (previous.queried if previous else frozenset())
    _, _, missing = franchise_traversal(root_id, nodes, all_queried)
    return FranchiseGraph(root_id, nodes, all_queried, not missing)


def _collect_franchise(raw: object, nodes: dict[int, JsonObject]) -> None:
    if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    if raw["type"] != "ANIME":
        return
    identifier: object = raw.get("id")
    if type(identifier) is not int or identifier <= 0 or "format" not in raw:
        raise _catalog_error(_CatalogFailure.MALFORMED)
    title: object = raw.get("title")
    if not isinstance(title, dict) or any(value is not None and not isinstance(value, str) for value in title.values()):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    relations: object = raw.get("relations", {"edges": []})
    if not isinstance(relations, Mapping) or not isinstance(relations.get("edges"), list):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    edges: list[Any] = relations["edges"]
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("relationType"), str):
            raise _catalog_error(_CatalogFailure.MALFORMED)
        child: object = edge.get("node")
        if not isinstance(child, dict) or type(child.get("id")) is not int:
            raise _catalog_error(_CatalogFailure.MALFORMED)
    if identifier not in nodes:
        nodes[identifier] = raw
    elif "relations" in raw:
        previous: JsonObject = nodes[identifier]
        merged: dict[tuple[int, str], JsonObject] = {
            (edge["node"]["id"], edge["relationType"]): edge for edge in previous.get("relations", {}).get("edges", [])
        }
        merged.update({(edge["node"]["id"], edge["relationType"]): edge for edge in edges})
        nodes[identifier] = {**previous, "relations": {"edges": list(merged.values())}}
    for edge in edges:
        _collect_franchise(edge["node"], nodes)


def _schedule_page(raw: object, page: int) -> tuple[tuple[EpisodeAiring, ...], bool]:
    if not isinstance(raw, Mapping):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    info: object = raw.get("pageInfo")
    nodes: object = raw.get("nodes")
    if (
        not isinstance(info, Mapping)
        or type(info.get("currentPage")) is not int
        or info["currentPage"] != page
        or not isinstance(nodes, list)
    ):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    more: object = info.get("hasNextPage")
    if not isinstance(more, bool) or (more and not nodes):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    return tuple(_episode_airing(node) for node in nodes), more


def _episode_airing(raw: object) -> EpisodeAiring:
    if not isinstance(raw, Mapping):
        raise _catalog_error(_CatalogFailure.MALFORMED)
    episode: object = raw.get("episode")
    timestamp: object = raw.get("airingAt")
    if type(episode) is not int or episode < 1:
        raise _catalog_error(_CatalogFailure.MALFORMED)
    if timestamp is None:
        return EpisodeAiring(episode, None)
    if type(timestamp) is not int or timestamp <= 0:
        raise _catalog_error(_CatalogFailure.MALFORMED)
    try:
        return EpisodeAiring(episode, datetime.fromtimestamp(timestamp, tz=UTC))
    except (ValueError, OverflowError, OSError) as error:
        raise _catalog_error(_CatalogFailure.MALFORMED) from error


def _start_date(raw: object) -> date | None:
    if not isinstance(raw, Mapping):
        return None
    year: object = raw.get("year")
    month: object = raw.get("month")
    day: object = raw.get("day")
    if type(year) is not int or type(month) is not int or type(day) is not int:
        return None
    try:
        return date(year, month, day)
    except ValueError as error:
        raise _catalog_error(_CatalogFailure.MALFORMED) from error


def _candidate(node: Mapping[str, Any]) -> TitleCandidate | None:
    """Build one candidate, or ``None`` when the node carries no id or romaji title."""
    anilist_id: object = node.get("id")
    title: object = node.get("title")
    names: Mapping[str, Any] = title if isinstance(title, Mapping) else {}
    romaji: str = _text(names.get("romaji"))
    if not isinstance(anilist_id, int) or not romaji:
        return None
    return TitleCandidate(
        anilist_id=anilist_id,
        romaji=romaji,
        english=_text(names.get("english")) or None,
        native=_text(names.get("native")) or None,
        synonyms=_synonyms(node.get("synonyms")),
        year=_number(node.get("seasonYear")),
        season=_text(node.get("season")) or None,
        format=_text(node.get("format")) or None,
        episodes=_number(node.get("episodes")),
        status=_status(node.get("status")),
        prequel_ids=_prequel_ids(node),
    )


def _prequel_ids(node: Mapping[str, Any]) -> tuple[int, ...]:
    """Return the ids of the direct prequel edges whose format counts into an offset."""
    relations: object = node.get("relations")
    edges: object = relations.get("edges") if isinstance(relations, Mapping) else None
    if not isinstance(edges, list):
        return ()
    ids: list[int] = []
    for edge in edges:
        if not isinstance(edge, Mapping) or edge.get("relationType") != _PREQUEL_RELATION:
            continue
        child: object = edge.get("node")
        if not isinstance(child, Mapping) or child.get("format") not in OFFSET_FORMATS:
            continue
        child_id: object = child.get("id")
        if isinstance(child_id, int):
            ids.append(child_id)
    return tuple(ids)


def _prequel_entry(media: Mapping[str, Any] | None) -> PrequelEntry:
    """Build one hop of the prequel chain; an entry AniList cannot serve counts as a season of zero."""
    if media is None:
        return PrequelEntry(episodes=0, cour=False)
    title: object = media.get("title")
    names: Mapping[str, Any] = title if isinstance(title, Mapping) else {}
    return PrequelEntry(
        episodes=_episodes(media) or 0,
        cour=is_cour_title(_text(names.get("romaji")), _text(names.get("english"))),
    )


def _episodes(media: Mapping[str, Any]) -> int | None:
    """Return the episode count of one title, or ``None`` when AniList does not know it."""
    return _number(media.get("episodes"))


def _synonyms(raw: object) -> tuple[str, ...]:
    """Return the non-empty alternative names carried by one node."""
    if not isinstance(raw, list):
        return ()
    return tuple(text for value in raw if (text := _text(value)))


def _status(raw: object) -> TitleStatus:
    """Map an AniList airing status onto the closed set, unknown values included."""
    if not isinstance(raw, str):
        return TitleStatus.UNKNOWN
    try:
        return TitleStatus(raw)
    except ValueError:
        return TitleStatus.UNKNOWN


def _text(raw: object) -> str:
    """Return a trimmed string value, empty for anything that is not a string."""
    return raw.strip() if isinstance(raw, str) else ""


def _number(raw: object) -> int | None:
    """Return an integer value, ``None`` for anything else including booleans."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def _shorten_words(text: str) -> str | None:
    """Cut every word of *text* to sixty percent of its length, never below three letters."""
    words: list[str] = text.split()
    shortened: list[str] = [word[: max(_MIN_SHORTENED_WORD, int(len(word) * _SHORTENED_WORD_RATIO))] for word in words]
    if shortened == words:
        return None
    return " ".join(shortened)


def _catalog_error(failure: _CatalogFailure) -> TitleCatalogError:
    """Build one catalog failure with a stable code."""
    return TitleCatalogError(
        context=ErrorContext(
            code=ErrorCode.TITLE_CATALOG_FAILED,
            message=_CATALOG_MESSAGES[failure],
            suggestion=_CATALOG_SUGGESTION,
            details={"operation": "anilist_search", "reason": failure.value},
        )
    )
