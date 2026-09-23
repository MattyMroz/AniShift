"""Nyaa RSS release source: one search request and a feed reader."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, Final
from xml.etree import ElementTree

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.torrents.categories import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    SEARCH_CATEGORIES,
)
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.types import Release
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "CATEGORY_ENGLISH_TRANSLATED",
    "CATEGORY_NON_ENGLISH_TRANSLATED",
    "MAX_BODY_BYTES",
    "NYAA_NAMESPACE",
    "NYAA_RSS_URL",
    "SEARCH_CATEGORIES",
    "USER_AGENT",
    "parse_feed",
    "search_releases",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_PUBLIC_TORRENT_LINK: Final[re.Pattern[str]] = re.compile(r"https://nyaa\.si/download/([1-9][0-9]*)\.torrent")
"""Canonical public source links safe to retain as numeric references without credentials."""

NYAA_RSS_URL: Final[str] = "https://nyaa.si/"
"""Feed endpoint; the RSS view is selected by the ``page`` query parameter."""

NYAA_NAMESPACE: Final[str] = "https://nyaa.si/xmlns/nyaa"
"""XML namespace carrying the index-specific item fields."""

_ENGLISH_SUBTITLES: Final[str] = "en"
"""Subtitle language assumed for an English-category release that declares no other one."""

_DEFAULT_LANGUAGES: Final[dict[str, str | None]] = {
    CATEGORY_ENGLISH_TRANSLATED: _ENGLISH_SUBTITLES,
    CATEGORY_NON_ENGLISH_TRANSLATED: None,
}
"""Subtitle language assumed for a release of each category that declares none."""

MAX_BODY_BYTES: Final[int] = 4 * 1024 * 1024
"""Largest feed body accepted before the response is rejected."""

USER_AGENT: Final[str] = "AniShift/0.1"
"""Client identity sent with every search request."""

DEFAULT_SEARCH_TIMEOUT_S: Final[float] = 20.0
"""Timeout applied to one search request."""

_XML_CONTENT_TYPES: Final[str] = "xml"
"""Marker required in the response content type to accept a body as a feed."""


def retained_release_id(url: str) -> int | None:
    """Recognize only a trusted canonical public Nyaa torrent link."""
    match: re.Match[str] | None = _PUBLIC_TORRENT_LINK.fullmatch(url)
    return int(match.group(1)) if match is not None else None


def retained_torrent_url(release_id: int) -> str:
    """Restore the canonical locator of a previously verified public Nyaa reference."""
    if type(release_id) is not int or release_id <= 0:
        msg = "A Nyaa reference requires a positive release identifier"
        raise ValueError(msg)
    return f"https://nyaa.si/download/{release_id}.torrent"


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
    """Read releases from one Nyaa RSS body, in document order."""
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
    categories: Sequence[str] = SEARCH_CATEGORIES,
) -> tuple[Release, ...]:
    """Search *categories* for *query* with one request each, in the order given."""
    merged: dict[str, Release] = {}
    for category in categories:
        default_language: str | None = _DEFAULT_LANGUAGES.get(category)
        for release in _search_category(query, category, http=http, timeout_s=timeout_s):
            key: str = release.info_hash.casefold()
            if key in merged:
                continue
            language: str | None = parse_release_name(release.title).subtitle_language or default_language
            merged[key] = replace(release, subtitle_language=language)
    logger.info("Searched Nyaa for releases", releases=len(merged), requests=len(categories))
    return tuple(merged.values())


def _search_category(
    query: str,
    category: str,
    *,
    http: httpx.Client,
    timeout_s: float,
) -> tuple[Release, ...]:
    """Run one search request and read the feed it answers with."""
    try:
        response: httpx.Response = http.get(
            NYAA_RSS_URL,
            params={"page": "rss", "q": query, "c": category, "f": "0"},
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
    return parse_feed(response.text)


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
