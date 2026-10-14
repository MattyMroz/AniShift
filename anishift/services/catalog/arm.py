"""Read the AniDB ID and TheTVDB season of one AniList entry from arm-server."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT
from anishift.utils.logger import get_logger

__all__ = ["ARM_URL", "ArmCatalog", "ArmIds"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ARM_URL: Final[str] = "https://arm.haglund.dev/api/v2/ids"
"""Public ID bridge endpoint."""

_TIMEOUT_S: Final[float] = 20.0
"""Timeout for one ID request."""


@dataclass(frozen=True, slots=True)
class ArmIds:
    """Bridge IDs of one AniList entry; ``None`` where arm-server knows none."""

    anidb_id: int | None
    tvdb_season: int | None


class ArmCatalog:
    """Fetch bridge IDs through a caller-owned HTTP client."""

    def __init__(self, http: httpx.Client, *, timeout_s: float = _TIMEOUT_S) -> None:
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def ids(self, anilist_id: int) -> ArmIds:
        """Return the AniDB ID and TheTVDB season, both ``None`` for an unknown entry."""
        try:
            response: httpx.Response = self._http.get(
                ARM_URL,
                params={"source": "anilist", "id": anilist_id},
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout_s,
            )
            if response.status_code == HTTPStatus.NOT_FOUND:
                return ArmIds(None, None)
            if response.status_code != HTTPStatus.OK:
                raise _ids_error()
            body: object = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Bridge IDs failed", provider="arm", code=ErrorCode.EPISODE_CATALOG_FAILED)
            raise _ids_error() from error
        if not isinstance(body, Mapping):
            raise _ids_error()
        result: ArmIds = ArmIds(_number(body.get("anidb")), _number(body.get("thetvdb-season")))
        logger.info("Bridge IDs read", provider="arm", anidb=result.anidb_id is not None)
        return result


def _number(value: object) -> int | None:
    return value if type(value) is int else None


def _ids_error() -> TitleCatalogError:
    return TitleCatalogError(
        context=ErrorContext(
            code=ErrorCode.EPISODE_CATALOG_FAILED,
            message="arm-server returned no usable bridge IDs",
            suggestion="Try the episode catalog again later",
        )
    )
