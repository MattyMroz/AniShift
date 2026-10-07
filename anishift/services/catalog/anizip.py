"""Read ani.zip episode mappings without altering their raw identity facts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from http import HTTPStatus
from time import perf_counter
from typing import Any, Final

import httpx

from anishift.application.episode_selection import AniZipMapping, ListedEpisode, ListedSpecial
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ANIZIP_URL: Final[str] = "https://api.ani.zip/mappings"
"""Public episode mapping endpoint."""

_TIMEOUT_S: Final[float] = 20.0
"""Timeout for one mapping request."""


class AniZipCatalog:
    """Fetch mappings through a caller-owned HTTP client."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = _TIMEOUT_S) -> None:
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def mapping(self, anilist_id: int) -> AniZipMapping:
        """Return episode metadata, or an empty mapping for an unknown entry."""
        return self._read("anilist_id", anilist_id)

    def mapping_by_anidb(self, anidb_id: int) -> AniZipMapping:
        """Return the episode metadata of one AniDB entry, or an empty mapping for an unknown one."""
        return self._read("anidb_id", anidb_id)

    def _read(self, key: str, identifier: int) -> AniZipMapping:
        started: float = perf_counter()
        try:
            response: httpx.Response = self._http.get(
                ANIZIP_URL,
                params={key: identifier},
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout_s,
            )
            if response.status_code == HTTPStatus.NOT_FOUND:
                result: AniZipMapping = AniZipMapping(None, None, None, (), (), None, {})
            else:
                response.raise_for_status()
                if response.status_code != HTTPStatus.OK:
                    raise _mapping_error()
                result = parse_mapping(response.json(), response.headers.get("cache-control"))
        except (httpx.HTTPError, ValueError, TitleCatalogError) as error:
            logger.warning("Episode mapping failed", provider="anizip", code=ErrorCode.EPISODE_CATALOG_FAILED)
            raise _mapping_error() from error
        logger.info(
            "Episode mapping completed",
            provider="anizip",
            operation="mapping",
            lookup=key,
            count=len(result.episodes),
            elapsed_s=perf_counter() - started,
        )
        return result


def parse_mapping(body: object, cache_control: str | None = None) -> AniZipMapping:
    """Parse a mapping while preserving every raw episode and its insertion order."""
    if not isinstance(body, Mapping):
        raise _mapping_error()
    raw: object = body.get("episodes")
    mappings: object = body.get("mappings")
    if not isinstance(raw, dict) or not isinstance(mappings, Mapping):
        raise _mapping_error()
    episodes: list[ListedEpisode] = []
    specials: list[ListedSpecial] = []
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise _mapping_error()
        when: datetime | None = _air_date(value.get("airDateUtc"))
        if re.fullmatch(r"[1-9][0-9]*", key):
            episodes.append(
                ListedEpisode(
                    int(key),
                    _title(value),
                    when,
                    _number(value.get("seasonNumber")),
                    _number(value.get("episodeNumber")),
                    _number(value.get("absoluteEpisodeNumber")),
                )
            )
        elif re.fullmatch(r"S[0-9]+", key):
            specials.append(ListedSpecial(key, _title(value), when.date() if when else None))
    kitsu: object = mappings.get("kitsu_id")
    if isinstance(kitsu, str) and kitsu.isascii() and kitsu.isdecimal():
        kitsu = int(kitsu)
    age: re.Match[str] | None = re.search(r'(?:^|,)\s*max-age\s*=\s*"?([0-9]+)"?\s*(?:,|$)', cache_control or "", re.I)
    kind: object = mappings.get("type")
    return AniZipMapping(
        _number(kitsu),
        kind if isinstance(kind, str) else None,
        _number(body.get("episodeCount")),
        tuple(sorted(episodes, key=lambda episode: episode.number)),
        tuple(specials),
        int(age.group(1)) if age else None,
        deepcopy(raw),
    )


def _number(value: object) -> int | None:
    return value if type(value) is int else None


def _title(value: Mapping[str, Any]) -> str | None:
    title: object = value.get("title")
    if isinstance(title, Mapping):
        title = title.get("en") or title.get("x-jat")
    return title if isinstance(title, str) and title else None


def _air_date(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _mapping_error()
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError as error:
        raise _mapping_error() from error
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _mapping_error() -> TitleCatalogError:
    return TitleCatalogError(
        context=ErrorContext(
            code=ErrorCode.EPISODE_CATALOG_FAILED,
            message="ani.zip returned no usable episode mapping",
            suggestion="Try the episode catalog again later",
        )
    )
