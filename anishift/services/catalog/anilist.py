"""AniList GraphQL catalog: title search and prequel episode offset."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Any, Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.types import TitleCandidate, TitleStatus
from anishift.utils.logger import get_logger

__all__ = [
    "ANILIST_URL",
    "DEFAULT_SEARCH_LIMIT",
    "MAX_PREQUEL_HOPS",
    "OFFSET_FORMATS",
    "AniListCatalog",
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
query ($id: Int) { Media(id: $id) { id episodes format
  relations { edges { relationType node { id episodes format } } } } }
"""
"""Single-title request used while walking the prequel chain."""

_PREQUEL_RELATION: Final[str] = "PREQUEL"
"""Relation type naming the entry that airs before the current one."""

_MIN_SHORTENED_WORD: Final[int] = 3
"""Shortest a word may become when a search is retried."""

_SHORTENED_WORD_RATIO: Final[float] = 0.6
"""Fraction of a word kept when a search is retried."""

_CATALOG_SUGGESTION: Final[str] = "Search again in a minute or type the title exactly"
"""Recovery hint shown for every catalog failure."""


class _CatalogFailure(StrEnum):
    """Ways one AniList request or body can be unusable."""

    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    MALFORMED = "malformed"


_CATALOG_MESSAGES: Final[dict[_CatalogFailure, str]] = {
    _CatalogFailure.UNREACHABLE: "AniList could not be reached",
    _CatalogFailure.REJECTED: "AniList rejected the title search",
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
        """Return the candidates AniList proposes for *text*, in its own order.

        An empty answer is retried once with every word cut to sixty percent of its length,
        which recovers phrases typed with an extra letter at the end.

        Raises:
            TitleCatalogError: AniList is unreachable, rejects the request, or answers with no media.
        """
        candidates: tuple[TitleCandidate, ...] = self._search_once(text, limit)
        shortened: str | None = _shorten_words(text) if not candidates else None
        retried: bool = shortened is not None
        if shortened is not None:
            candidates = self._search_once(shortened, limit)
        logger.info("Searched AniList for titles", hits=len(candidates), retried=retried)
        return candidates

    def episode_offset(self, candidate: TitleCandidate) -> int:
        """Return how many episodes aired before *candidate*, following its prequel chain.

        Only television and web formats count, unknown episode counts count as zero, and
        the walk stops after ``MAX_PREQUEL_HOPS`` entries.

        Raises:
            TitleCatalogError: AniList is unreachable or rejects one of the requests.
        """
        seen: set[int] = {candidate.anilist_id}
        pending: list[int] = [prequel_id for prequel_id in candidate.prequel_ids if prequel_id not in seen]
        total: int = 0
        hops: int = 0
        while pending and hops < MAX_PREQUEL_HOPS:
            current: int = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            hops += 1
            media: Mapping[str, Any] | None = self._media(current)
            if media is None:
                continue
            total += _episodes(media) or 0
            pending.extend(prequel_id for prequel_id in _prequel_ids(media) if prequel_id not in seen)
        return total

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
        """Send one GraphQL request and return its ``data`` object.

        Raises:
            TitleCatalogError: The endpoint is unreachable, answers with an error status,
                or returns a body without a ``data`` object.
        """
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
        data: object = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(data, Mapping):
            raise _catalog_error(_CatalogFailure.MALFORMED)
        return data


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
    """Cut every word of *text* to sixty percent of its length, never below three letters.

    Returns ``None`` when no word is long enough to lose a letter, so the caller skips a
    retry that would repeat the same request.
    """
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
