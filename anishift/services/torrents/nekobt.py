"""Read bounded nekoBT Torznab pages and their role-qualified language tags."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from xml.etree import ElementTree

import httpx

from anishift.application.episode_releases import info_hash_hex
from anishift.application.episode_search import TextPage
from anishift.application.episode_selection import StreamCandidate
from anishift.application.release_quality import LanguageDeclaration, language_code, tag_declaration
from anishift.services.torrents._source import get_response, integer, magnet_fields, source_error, text
from anishift.services.torrents.nyaa import MAX_BODY_BYTES
from anishift.utils.rich_console import format_bytes

# ── Constants ─────────────────────────────────────────────────────────────────

NEKOBT_URL: Final[str] = "https://nekobt.to/api/torznab/api"
"""Public nekoBT Torznab endpoint."""

PAGE_SIZE: Final[int] = 100
"""Maximum number of items requested per nekoBT page."""

_NAMESPACE: Final[str] = "http://torznab.com/schemas/2015/feed"
"""Torznab namespace for item attributes and response totals."""

_TAG_BLOCK: Final[re.Pattern[str]] = re.compile(r"\s*\{Tags:([^{}]*)\}\s*$", re.IGNORECASE)
"""Trailing nekoBT metadata block, separate from the release name."""

_REGIONAL_CODES: Final[dict[str, str]] = {
    "es419": "es",
    "eses": "es",
    "frfr": "fr",
    "ptbr": "pt",
    "ptpt": "pt",
    "zhhans": "zh",
    "zhhant": "zh",
}
"""Concatenated regional codes used by nekoBT, normalized before quality resolution."""


@dataclass(frozen=True, slots=True)
class NekoTags:
    """Normalized subtitle and audio languages plus unqualified metadata flags."""

    subtitles: frozenset[str]
    audio: frozenset[str]
    flags: tuple[str, ...]


def language_tags(value: str) -> NekoTags:
    """Read the trailing Tags block and union fansub and official subtitle languages."""
    match: re.Match[str] | None = _TAG_BLOCK.search(value)
    if match is None:
        return NekoTags(frozenset(), frozenset(), ())
    normalized: list[str] = []
    flags: list[str] = []
    for tag in match.group(1).split(";"):
        role, separator, codes = tag.strip().partition("=")
        if not separator:
            if role:
                flags.append(role.upper())
            continue
        normalized.append(
            role.upper()
            + "="
            + ",".join(
                _REGIONAL_CODES.get(code.strip().casefold(), language_code(code))
                for code in codes.split(",")
                if code.strip()
            )
        )
    declaration: LanguageDeclaration = tag_declaration(normalized)
    return NekoTags(declaration.subtitles or frozenset(), declaration.audio or frozenset(), tuple(dict.fromkeys(flags)))


class NekoBTSource:
    """Fetch one Torznab page using a caller-owned controlled HTTP client."""

    def __init__(self, http: httpx.Client) -> None:
        self._http: httpx.Client = http

    def search(self, phrase: str, page: int) -> TextPage:
        """Request one page without following magnets or fetching additional pages."""
        response: httpx.Response = get_response(
            self._http,
            NEKOBT_URL,
            "nekobt",
            params={"t": "search", "q": phrase, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
        )
        if "xml" not in response.headers.get("content-type", "").casefold():
            msg: str = "Source response is not XML"
            raise source_error("nekobt") from ValueError(msg)
        return parse_feed(response.text)


def parse_feed(xml_text: str) -> TextPage:
    """Parse one bounded feed with absent totals left unknown and malformed bodies rejected."""
    try:
        if len(xml_text.encode("utf-8")) > MAX_BODY_BYTES:
            msg: str = "Source feed is too large"
            raise source_error("nekobt") from ValueError(msg)
        root: ElementTree.Element = ElementTree.fromstring(xml_text)  # noqa: S314 - bounded public feed
        if root.tag != "rss" or root.find("channel") is None:
            msg = "Source did not return an RSS channel"
            raise source_error("nekobt") from ValueError(msg)
        response: ElementTree.Element | None = root.find(f".//{{{_NAMESPACE}}}response")
        total: str | None = response.get("total") if response is not None else None
        return TextPage(tuple(_candidate(item) for item in root.iter("item")), integer(int(total)) if total else None)
    except (ValueError, ElementTree.ParseError) as error:
        raise source_error("nekobt") from error


def _candidate(item: ElementTree.Element) -> StreamCandidate:
    attributes: dict[str, str] = {
        tag.attrib["name"]: tag.attrib["value"]
        for tag in item.findall(f"{{{_NAMESPACE}}}attr")
        if "name" in tag.attrib and "value" in tag.attrib
    }
    magnet_hash: str | None
    trackers: tuple[str, ...]
    magnet_hash, trackers = magnet_fields(attributes.get("magneturl") or item.findtext("link"))
    info_hash: str | None = info_hash_hex(attributes.get("infohash", "")) or magnet_hash
    if info_hash is None:
        msg: str = "Invalid source BTIH"
        raise ValueError(msg)
    title: str = text(item.findtext("title"))
    tags: NekoTags = language_tags(title)
    seeders: str | None = attributes.get("seeders")
    size: str | None = attributes.get("size") or item.findtext("size")
    return StreamCandidate(
        info_hash=info_hash,
        name=None,
        file_index=None,
        file_name=None,
        release=_TAG_BLOCK.sub("", title),
        path=None,
        seeders=integer(int(seeders)) if seeders is not None else None,
        size_text=format_bytes(integer(int(size))) if size is not None else None,
        provider="nekoBT",
        tags=tags.flags,
        trackers=trackers,
        source="nekobt",
        subtitle_languages=tuple(sorted(tags.subtitles)),
        audio_languages=tuple(sorted(tags.audio)),
        language_tags=("A=" + ",".join(sorted(tags.audio)), "S=" + ",".join(sorted(tags.subtitles))),
    )
