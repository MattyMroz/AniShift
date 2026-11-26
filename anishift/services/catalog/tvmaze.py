"""Read the English episode titles of one TheTVDB series from TVmaze."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from http import HTTPStatus
from typing import Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT
from anishift.utils.logger import get_logger

__all__ = ["TVMAZE_URL", "TvMazeCatalog"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

TVMAZE_URL: Final[str] = "https://api.tvmaze.com"
"""Public TVmaze API root."""

_TIMEOUT_S: Final[float] = 10.0
"""Timeout for one TVmaze request."""

_PLACEHOLDER_TITLE: Final[re.Pattern[str]] = re.compile(r"Episode \d+", re.IGNORECASE)
"""Whole name TVmaze shows before an episode gets its own title."""

_REGULAR: Final[str] = "regular"
"""TVmaze type of an episode inside the numbered season."""


class TvMazeCatalog:
    """Fetch episode titles through a caller-owned HTTP client."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = _TIMEOUT_S) -> None:
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def episode_titles(self, tvdb_show_id: int) -> dict[tuple[int, int], str]:
        """Return English titles keyed by ``(season, number)``, empty for a series TVmaze does not know."""
        try:
            show: httpx.Response = self._get("/lookup/shows", {"thetvdb": tvdb_show_id})
            if show.status_code == HTTPStatus.NOT_FOUND:
                logger.info("Episode titles read", provider="tvmaze", count=0)
                return {}
            episodes: httpx.Response = self._get(f"/shows/{_show_id(_body(show))}/episodes")
            titles: dict[tuple[int, int], str] = _titles(_body(episodes))
        except (httpx.HTTPError, ValueError, TitleCatalogError) as error:
            logger.warning("Episode titles failed", provider="tvmaze", code=ErrorCode.EPISODE_CATALOG_FAILED)
            raise _titles_error() from error
        logger.info("Episode titles read", provider="tvmaze", count=len(titles))
        return titles

    def _get(self, path: str, params: Mapping[str, int] | None = None) -> httpx.Response:
        return self._http.get(
            f"{TVMAZE_URL}{path}",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=self._timeout_s,
            follow_redirects=True,
        )


def _body(response: httpx.Response) -> object:
    if response.status_code != HTTPStatus.OK:
        raise _titles_error()
    return response.json()


def _show_id(body: object) -> int:
    show: object = body.get("id") if isinstance(body, Mapping) else None
    if type(show) is not int:
        raise _titles_error()
    return show


def _titles(body: object) -> dict[tuple[int, int], str]:
    if not isinstance(body, list) or not all(isinstance(item, Mapping) for item in body):
        raise _titles_error()
    named: list[tuple[tuple[int, int], str | None]] = [
        ((item["season"], item["number"]), _clean(item.get("name")))
        for item in body
        if item.get("type") == _REGULAR and type(item.get("season")) is int and type(item.get("number")) is int
    ]
    seen: Counter[tuple[int, int]] = Counter(pair for pair, _ in named)
    return {pair: name for pair, name in named if name is not None and seen[pair] == 1}


def _clean(name: object) -> str | None:
    if not isinstance(name, str):
        return None
    cleaned: str = " ".join(
        "".join(" " if unicodedata.category(char).startswith("C") else char for char in name).split()
    )
    return cleaned if cleaned and not _PLACEHOLDER_TITLE.fullmatch(cleaned) else None


def _titles_error() -> TitleCatalogError:
    return TitleCatalogError(
        context=ErrorContext(
            code=ErrorCode.EPISODE_CATALOG_FAILED,
            message="TVmaze returned no usable episode titles",
            suggestion="Try the episode list again later",
        )
    )
