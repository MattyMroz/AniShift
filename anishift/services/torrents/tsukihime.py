"""Read TsukiHime episode pages and complete torrent inventories without following mirrors."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Final

import httpx

from anishift.application.episode_releases import ListedFile, TsukiHimeFiles, info_hash_hex
from anishift.application.episode_search import TsukiHimeLookup, TsukiHimePage
from anishift.application.episode_selection import StreamCandidate
from anishift.services.torrents._source import (
    get_response,
    integer,
    languages,
    object_list,
    object_map,
    source_error,
    text,
)
from anishift.utils.rich_console import format_bytes

# ── Constants ─────────────────────────────────────────────────────────────────

TSUKIHIME_URL: Final[str] = "https://api.tsukihime.org/v1"
"""Public TsukiHime API origin and version."""

PAGE_SIZE: Final[int] = 100
"""Maximum episode page size accepted by TsukiHime."""


class TsukiHimeSource:
    """Fetch one source response per call using a caller-owned controlled HTTP client."""

    def __init__(self, http: httpx.Client) -> None:
        self._http: httpx.Client = http

    def anime_id(self, anilist_id: int) -> int | None:
        """Resolve an AniList title, returning None only when the source reports 404."""
        response: httpx.Response = get_response(
            self._http, f"{TSUKIHIME_URL}/animes/anilist/{anilist_id}", "tsukihime", statuses=(200, 404)
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        try:
            return _identifier(object_map(response.json()).get("id"))
        except (TypeError, ValueError) as error:
            raise source_error("tsukihime") from error

    def episode_page(self, anime_id: int, number: int, offset: int) -> TsukiHimePage:
        """Read one episode page, preserving the server's start and total fields."""
        response: httpx.Response = get_response(
            self._http,
            f"{TSUKIHIME_URL}/animes/{anime_id}/episodes/{number}",
            "tsukihime",
            params={"limit": PAGE_SIZE, "offset": offset},
            statuses=(200, 404),
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return TsukiHimePage((), 0, offset, PAGE_SIZE)
        try:
            body: Mapping[str, object] = object_map(response.json())
            if body.get("error"):
                msg: str = "Source reported an episode error"
                raise source_error("tsukihime") from ValueError(msg)
            return TsukiHimePage(
                tuple(_candidate(object_map(row)) for row in object_list(body.get("results"))),
                integer(body.get("total")),
                integer(body.get("start")),
                integer(body.get("limit")),
            )
        except (TypeError, ValueError) as error:
            raise source_error("tsukihime") from error

    def torrent_by_hash(self, info_hash: str) -> TsukiHimeLookup:
        """Return a hash lookup with inline files only when the inventory is complete."""
        normalized: str | None = info_hash_hex(info_hash)
        if normalized is None:
            msg: str = "Invalid BTIH lookup key"
            raise ValueError(msg)
        return self._lookup(f"/torrents/btih/{normalized}")

    def torrent_files(self, torrent_id: int) -> TsukiHimeLookup:
        """Fetch one torrent detail response, retaining pending and incomplete outcomes."""
        return self._lookup(f"/torrents/{torrent_id}")

    def _lookup(self, path: str) -> TsukiHimeLookup:
        response: httpx.Response = get_response(
            self._http, TSUKIHIME_URL + path, "tsukihime", statuses=(200, 202, 404, 429)
        )
        if response.status_code in (404, 429):
            return TsukiHimeLookup(response.status_code)
        try:
            body: Mapping[str, object] = object_map(response.json())
            identifier: int = _identifier(body.get("id"))
            if response.status_code == HTTPStatus.ACCEPTED:
                return TsukiHimeLookup(202, identifier)
            rows: list[object] = object_list(body.get("files", []))
            count: object = body.get("filecount")
            if count is None or not rows or integer(count) != len(rows):
                return TsukiHimeLookup(200, identifier)
            files: TsukiHimeFiles = TsukiHimeFiles(tuple(_file(object_map(row)) for row in rows))
            return TsukiHimeLookup(200, identifier, files)
        except (TypeError, ValueError) as error:
            raise source_error("tsukihime") from error


def _identifier(value: object) -> int:
    identifier: int = integer(value)
    if identifier == 0:
        msg: str = "Source identifier must be positive"
        raise ValueError(msg)
    return identifier


def _candidate(row: Mapping[str, object]) -> StreamCandidate:
    info_hash: str | None = info_hash_hex(text(row.get("btih")))
    if info_hash is None:
        msg: str = "Invalid source BTIH"
        raise ValueError(msg)
    size: object = row.get("totalsize")
    count: object = row.get("filecount")
    return StreamCandidate(
        info_hash=info_hash,
        name=None,
        file_index=None,
        file_name=None,
        release=text(row.get("name")),
        path=None,
        seeders=None,
        size_text=format_bytes(integer(size)) if size is not None else None,
        provider="TsukiHime",
        tags=(),
        trackers=(),
        source="tsukihime",
        subtitle_languages=languages(row.get("sublangs", [])),
        audio_languages=languages(row.get("audiolangs", [])),
        file_count=integer(count) if count is not None else None,
        torrent_id=_identifier(row.get("id")),
    )


def _file(row: Mapping[str, object]) -> ListedFile:
    size: object = row.get("size")
    return ListedFile(
        text(row.get("filename")),
        integer(size) if size is not None else None,
        languages(row.get("sublangs", [])),
        languages(row.get("audiolangs", [])),
    )
