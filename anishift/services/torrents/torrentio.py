"""Read Torrentio series and movie streams without ranking or deduplicating files."""

from __future__ import annotations

import re
from collections.abc import Mapping
from http import HTTPStatus
from time import perf_counter
from typing import Final

import httpx

from anishift.application.episode_selection import StreamCandidate
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.http_requests import USER_AGENT
from anishift.services.torrents.errors import TorrentSourceError
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

TORRENTIO_URL: Final[str] = "https://torrentio.strem.fun"
"""Public Torrentio origin."""

_TIMEOUT_S: Final[float] = 20.0
"""Timeout for one stream request."""


class TorrentioSource:
    """Fetch stream candidates through a caller-owned client."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = _TIMEOUT_S) -> None:
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        """Return streams for one local episode number."""
        return self._streams(f"/stream/series/kitsu:{kitsu_id}:{number}.json", "streams")

    def movie_streams(self, kitsu_id: int) -> tuple[StreamCandidate, ...]:
        """Return movie streams without an episode suffix."""
        return self._streams(f"/stream/movie/kitsu:{kitsu_id}.json", "movie_streams")

    def _streams(self, path: str, operation: str) -> tuple[StreamCandidate, ...]:
        started: float = perf_counter()
        try:
            response: httpx.Response = self._http.get(
                TORRENTIO_URL + path,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            if response.status_code != HTTPStatus.OK:
                raise _source_error()
            result: tuple[StreamCandidate, ...] = parse_streams(response.json())
        except (httpx.HTTPError, ValueError, TorrentSourceError) as error:
            logger.warning(
                "Stream lookup failed", provider="torrentio", operation=operation, code=ErrorCode.TORRENT_SOURCE_FAILED
            )
            raise _source_error() from error
        logger.info(
            "Stream lookup completed",
            provider="torrentio",
            operation=operation,
            count=len(result),
            elapsed_s=perf_counter() - started,
        )
        return result


def parse_streams(body: object) -> tuple[StreamCandidate, ...]:
    """Parse every returned torrent file in source order, retaining absent metadata."""
    if not isinstance(body, Mapping) or not isinstance(body.get("streams"), list):
        raise _source_error()
    return tuple(_stream(raw) for raw in body["streams"])


def _stream(raw: object) -> StreamCandidate:
    if not isinstance(raw, Mapping):
        raise _source_error()
    title: object = raw.get("title")
    info_hash: object = raw.get("infoHash")
    hints: object = raw.get("behaviorHints", {})
    index: object = raw.get("fileIdx")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(info_hash, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40}", info_hash)
        or not isinstance(hints, Mapping)
        or (index is not None and (type(index) is not int or index < 0))
    ):
        raise _source_error()
    lines: list[str] = title.splitlines()
    stats_index: int | None = next((i for i, line in enumerate(lines) if line.startswith("👤")), None)
    stats: str = lines[stats_index] if stats_index is not None else ""
    seeders: re.Match[str] | None = re.search(r"👤\s*([0-9]+)", stats)
    size: re.Match[str] | None = re.search(r"💾\s*(.*?)(?=⚙|$)", stats)
    provider: re.Match[str] | None = re.search(r"⚙️?\s*(.+)$", stats)
    sources: object = raw.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
        raise _source_error()
    return StreamCandidate(
        source="torrentio",
        info_hash=info_hash.lower(),
        name=_text(raw.get("name")),
        file_index=index if type(index) is int else None,
        file_name=_text(hints.get("filename")),
        release=lines[0],
        path=lines[1] if len(lines) > 1 and not lines[1].startswith("👤") else None,
        seeders=int(seeders.group(1)) if seeders else None,
        size_text=size.group(1).strip() if size else None,
        provider=provider.group(1).strip() if provider else None,
        tags=tuple(lines[stats_index + 1].split(" / "))
        if stats_index is not None and stats_index + 1 < len(lines)
        else (),
        trackers=tuple(source.removeprefix("tracker:") for source in sources if source.startswith("tracker:")),
    )


def _text(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _source_error()
    return value


def _source_error() -> TorrentSourceError:
    return TorrentSourceError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_SOURCE_FAILED,
            message="Torrentio returned no usable stream response",
            suggestion="Try the release source again later",
        )
    )
