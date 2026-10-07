"""Read one Knaben v2 search page without deduplicating source hits."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import httpx

from anishift.application.episode_releases import info_hash_hex
from anishift.application.episode_search import TextPage
from anishift.application.episode_selection import StreamCandidate
from anishift.services.torrents._source import (
    get_response,
    integer,
    magnet_fields,
    object_list,
    object_map,
    source_error,
    text,
)
from anishift.utils.rich_console import format_bytes

# ── Constants ─────────────────────────────────────────────────────────────────

KNABEN_URL: Final[str] = "https://api.knaben.org/v2/search"
"""Public Knaben GET search endpoint."""

PAGE_SIZE: Final[int] = 300
"""Number of hits requested per Knaben page."""


class KnabenSource:
    """Fetch one zero-based search page through the caller's controlled client."""

    def __init__(self, http: httpx.Client) -> None:
        self._http: httpx.Client = http

    def search(self, phrase: str, page: int) -> TextPage:
        """Issue the recorded GET query and normalize every returned BTIH."""
        response: httpx.Response = get_response(
            self._http,
            KNABEN_URL,
            "knaben",
            params={"q": phrase, "s": PAGE_SIZE, "o": "date", "f": page * PAGE_SIZE, "dead": ""},
        )
        try:
            body: Mapping[str, object] = object_map(response.json())
            total: object = body.get("total")
            return TextPage(
                tuple(_candidate(object_map(hit)) for hit in object_list(body.get("hits"))),
                integer(object_map(total).get("value")) if total is not None else None,
            )
        except (TypeError, ValueError) as error:
            raise source_error("knaben") from error


def _candidate(row: Mapping[str, object]) -> StreamCandidate:
    magnet_hash: str | None
    trackers: tuple[str, ...]
    magnet_hash, trackers = magnet_fields(row.get("magnetUrl"))
    raw_hash: object = row.get("hash")
    info_hash: str | None = (info_hash_hex(raw_hash) if isinstance(raw_hash, str) else None) or magnet_hash
    if info_hash is None:
        msg: str = "Invalid source BTIH"
        raise ValueError(msg)
    seeders: object = row.get("seeders")
    size: object = row.get("bytes")
    return StreamCandidate(
        info_hash=info_hash,
        name=None,
        file_index=None,
        file_name=None,
        release=text(row.get("title")),
        path=None,
        seeders=integer(seeders) if seeders is not None else None,
        size_text=format_bytes(integer(size)) if size is not None else None,
        provider="Knaben",
        tags=(),
        trackers=trackers,
        source="knaben",
    )
