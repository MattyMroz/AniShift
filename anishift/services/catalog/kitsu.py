"""Resolve the Kitsu ID of one AniList entry from Kitsu mappings confirmed in both directions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT
from anishift.utils.logger import get_logger

__all__ = ["KITSU_URL", "KitsuCatalog"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

KITSU_URL: Final[str] = "https://kitsu.io/api/edge"
"""Public Kitsu JSON:API root."""

_ANILIST_SITE: Final[str] = "anilist/anime"
"""Kitsu external site name of AniList anime entries."""

_PAGE_LIMIT: Final[str] = "20"
"""Mappings asked for in one page; a longer answer is left unresolved."""

_TIMEOUT_S: Final[float] = 20.0
"""Timeout for one mappings request."""


class KitsuCatalog:
    """Fetch Kitsu mappings through a caller-owned HTTP client."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = _TIMEOUT_S) -> None:
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def kitsu_id(self, anilist_id: int) -> int | None:
        """Return the one Kitsu anime whose own mappings name *anilist_id*, else ``None``; at most two requests."""
        rows, complete = self._page(
            "/mappings",
            {
                "filter[externalSite]": _ANILIST_SITE,
                "filter[externalId]": str(anilist_id),
                "include": "item",
                "page[limit]": _PAGE_LIMIT,
            },
        )
        items: set[str] = {item for row in rows if (item := _anime_item(row)) is not None}
        if not complete or len(rows) != 1 or len(items) != 1:
            logger.info("Kitsu ID unresolved", provider="kitsu", step="forward")
            return None
        candidate: str = items.pop()
        if not candidate.isascii() or not candidate.isdecimal():
            logger.info("Kitsu ID unresolved", provider="kitsu", step="forward")
            return None
        rows, complete = self._page(f"/anime/{candidate}/mappings", {"page[limit]": _PAGE_LIMIT})
        if not complete or (_ANILIST_SITE, str(anilist_id)) not in {_attributes(row) for row in rows}:
            logger.info("Kitsu ID unresolved", provider="kitsu", step="reverse")
            return None
        logger.info("Kitsu ID resolved", provider="kitsu")
        return int(candidate)

    def _page(self, path: str, params: Mapping[str, str]) -> tuple[Sequence[object], bool]:
        try:
            response: httpx.Response = self._http.get(
                f"{KITSU_URL}{path}",
                params=dict(params),
                headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.api+json"},
                timeout=self._timeout_s,
            )
            if response.status_code != HTTPStatus.OK:
                raise _kitsu_error()
            body: object = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Kitsu mappings failed", provider="kitsu", code=ErrorCode.EPISODE_CATALOG_FAILED)
            raise _kitsu_error() from error
        rows: object = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(body, Mapping) or not isinstance(rows, list):
            raise _kitsu_error()
        links: object = body.get("links")
        return rows, not isinstance(links, Mapping) or not links.get("next")


def _anime_item(row: object) -> str | None:
    if not isinstance(row, Mapping):
        return None
    relationships: object = row.get("relationships")
    item: object = relationships.get("item") if isinstance(relationships, Mapping) else None
    data: object = item.get("data") if isinstance(item, Mapping) else None
    if not isinstance(data, Mapping) or data.get("type") != "anime":
        return None
    identifier: object = data.get("id")
    return identifier if isinstance(identifier, str) else None


def _attributes(row: object) -> tuple[object, object] | None:
    attributes: object = row.get("attributes") if isinstance(row, Mapping) else None
    if not isinstance(attributes, Mapping):
        return None
    return attributes.get("externalSite"), attributes.get("externalId")


def _kitsu_error() -> TitleCatalogError:
    return TitleCatalogError(
        context=ErrorContext(
            code=ErrorCode.EPISODE_CATALOG_FAILED,
            message="Kitsu returned no usable mappings",
            suggestion="Try the episode catalog again later",
        )
    )
