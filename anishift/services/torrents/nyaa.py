"""Nyaa RSS release source: one search request and a feed reader."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from http import HTTPStatus
from typing import Final
from xml.etree import ElementTree

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.types import Release
from anishift.utils.logger import get_logger

__all__ = [
    "CATEGORY_ENGLISH_TRANSLATED",
    "MAX_BODY_BYTES",
    "NYAA_NAMESPACE",
    "NYAA_RSS_URL",
    "USER_AGENT",
    "parse_feed",
    "search_releases",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

NYAA_RSS_URL: Final[str] = "https://nyaa.si/"
"""Feed endpoint; the RSS view is selected by the ``page`` query parameter."""

NYAA_NAMESPACE: Final[str] = "https://nyaa.si/xmlns/nyaa"
"""XML namespace carrying the index-specific item fields."""

CATEGORY_ENGLISH_TRANSLATED: Final[str] = "1_2"
"""Nyaa category identifier for English-translated anime."""

MAX_BODY_BYTES: Final[int] = 4 * 1024 * 1024
"""Largest feed body accepted before the response is rejected."""

USER_AGENT: Final[str] = "AniShift/0.1"
"""Client identity sent with every search request."""

DEFAULT_SEARCH_TIMEOUT_S: Final[float] = 20.0
"""Timeout applied to one search request."""

_XML_CONTENT_TYPES: Final[str] = "xml"
"""Marker required in the response content type to accept a body as a feed."""


class _SourceFailure(StrEnum):
    """Ways one Nyaa request or body can be unusable."""

    UNREACHABLE = "unreachable"
    REJECTED = "rejected"
    OVERSIZED = "oversized"
    NOT_A_FEED = "not_a_feed"
    MALFORMED = "malformed"


_SOURCE_TEXTS: Final[dict[_SourceFailure, tuple[str, str]]] = {
    _SourceFailure.UNREACHABLE: ("Nyaa could not be reached", "Check the connection and try again"),
    _SourceFailure.REJECTED: ("Nyaa rejected the search", "Try the search again in a moment"),
    _SourceFailure.OVERSIZED: ("Nyaa returned an oversized feed", "Narrow the search and try again"),
    _SourceFailure.NOT_A_FEED: ("Nyaa did not answer with a feed", "Open nyaa.si in a browser and try again later"),
    _SourceFailure.MALFORMED: ("Nyaa returned a malformed feed", "Try the search again in a moment"),
}
"""Message and suggestion shown for each release-source failure."""


def parse_feed(xml_text: str) -> tuple[Release, ...]:
    """Read releases from one Nyaa RSS body, in document order.

    Items without an info hash or a torrent link are skipped.

    Raises:
        TorrentSourceError: The body is not well-formed XML.
    """
    try:
        root: ElementTree.Element = ElementTree.fromstring(xml_text)  # noqa: S314 - bounded public feed
    except ElementTree.ParseError as error:
        raise _source_error(_SourceFailure.MALFORMED) from error
    releases: list[Release] = []
    for item in root.iter("item"):
        release: Release | None = _release_from_item(item)
        if release is not None:
            releases.append(release)
    return tuple(releases)


def search_releases(
    query: str,
    *,
    http: httpx.Client,
    timeout_s: float = DEFAULT_SEARCH_TIMEOUT_S,
) -> tuple[Release, ...]:
    """Search Nyaa for *query* and return the released entries of the anime category.

    Raises:
        TorrentSourceError: The index is unreachable, rejects the request, or answers with no feed.
    """
    try:
        response: httpx.Response = http.get(
            NYAA_RSS_URL,
            params={"page": "rss", "q": query, "c": CATEGORY_ENGLISH_TRANSLATED, "f": "0"},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_s,
        )
    except httpx.HTTPError as error:
        raise _source_error(_SourceFailure.UNREACHABLE) from error
    if response.status_code != HTTPStatus.OK:
        raise _source_error(_SourceFailure.REJECTED)
    if len(response.content) > MAX_BODY_BYTES:
        raise _source_error(_SourceFailure.OVERSIZED)
    content_type: str = response.headers.get("content-type", "").lower()
    if _XML_CONTENT_TYPES not in content_type:
        raise _source_error(_SourceFailure.NOT_A_FEED)
    releases: tuple[Release, ...] = parse_feed(response.text)
    logger.info("Searched Nyaa for releases", releases=len(releases))
    return releases


def _release_from_item(item: ElementTree.Element) -> Release | None:
    """Build one release, or ``None`` when the item lacks an info hash or a link."""
    torrent_url: str = _text(item, "link")
    info_hash: str = _text(item, f"{{{NYAA_NAMESPACE}}}infoHash")
    if not torrent_url or not info_hash:
        return None
    return Release(
        title=_text(item, "title"),
        torrent_url=torrent_url,
        info_hash=info_hash,
        seeders=_seeders(_text(item, f"{{{NYAA_NAMESPACE}}}seeders")),
        size_text=_text(item, f"{{{NYAA_NAMESPACE}}}size"),
        published=_published(_text(item, "pubDate")),
    )


def _text(item: ElementTree.Element, tag: str) -> str:
    """Return the trimmed text of one child element, empty when it is absent."""
    child: ElementTree.Element | None = item.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _seeders(raw: str) -> int:
    """Return the seeder count, falling back to zero for an unreadable value."""
    try:
        return int(raw)
    except ValueError:
        return 0


def _published(raw: str) -> datetime | None:
    """Return the publication moment as an aware UTC value, or ``None`` when unreadable."""
    if not raw:
        return None
    try:
        parsed: datetime = parsedate_to_datetime(raw)
    except TypeError, ValueError:
        return None
    # Nyaa stamps "-0000", which RFC 2822 defines as an unknown zone and email.utils leaves naive.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _source_error(failure: _SourceFailure) -> TorrentSourceError:
    """Build one release-source failure with a stable code."""
    message, suggestion = _SOURCE_TEXTS[failure]
    return TorrentSourceError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_SOURCE_FAILED,
            message=message,
            suggestion=suggestion,
            details={"operation": "nyaa_search", "reason": failure.value},
        )
    )
