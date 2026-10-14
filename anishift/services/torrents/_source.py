"""Shared request and metadata decoding primitives for paged torrent sources."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final
from urllib.parse import parse_qs, urlsplit

import httpx

from anishift.application.episode_releases import info_hash_hex
from anishift.application.release_quality import language_code
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.http_requests import USER_AGENT
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.nyaa import MAX_BODY_BYTES
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT_S: Final[float] = 20.0
"""Fixed socket timeout for a single source request beneath the caller's operation deadline."""


def source_error(provider: str) -> TorrentSourceError:
    """Build the shared source failure without copying remote payloads or locators."""
    logger.warning("Release source failed", provider=provider, code=ErrorCode.TORRENT_SOURCE_FAILED)
    return TorrentSourceError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_SOURCE_FAILED,
            message=f"{provider} returned no usable response",
            suggestion="Try the release source again later",
        )
    )


def get_response(
    http: httpx.Client,
    url: str,
    provider: str,
    *,
    params: Mapping[str, str | int] | None = None,
    statuses: tuple[int, ...] = (200,),
) -> httpx.Response:
    """Perform one bounded request through the caller-owned client and retain HTTP failure causes."""
    try:
        response: httpx.Response = http.get(
            url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_S
        )
    except httpx.HTTPError as error:
        raise source_error(provider) from error
    if response.status_code not in statuses:
        raise source_error(provider) from httpx.HTTPStatusError(
            "Source rejected the request", request=response.request, response=response
        )
    if len(response.content) > MAX_BODY_BYTES:
        msg: str = "Source response is too large"
        raise source_error(provider) from ValueError(msg)
    logger.info("Release source request completed", provider=provider, status=response.status_code)
    return response


def object_map(value: object) -> Mapping[str, object]:
    """Require a JSON object at a metadata boundary."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        msg: str = "Expected a metadata object"
        raise TypeError(msg)
    return value


def object_list(value: object) -> list[object]:
    """Require a JSON array without coercing null or arbitrary objects."""
    if not isinstance(value, list):
        msg: str = "Expected a metadata list"
        raise TypeError(msg)
    return value


def text(value: object) -> str:
    """Require a nonempty string while preserving the original source text."""
    if not isinstance(value, str) or not value.strip():
        msg: str = "Expected nonempty metadata text"
        raise ValueError(msg)
    return value


def integer(value: object) -> int:
    """Require a nonnegative integer without accepting boolean values."""
    if type(value) is not int or value < 0:
        msg: str = "Expected a nonnegative metadata integer"
        raise ValueError(msg)
    return value


def languages(value: object) -> tuple[str, ...]:
    """Normalize a source language list while preserving its first-seen order."""
    return tuple(dict.fromkeys(language_code(text(item)) for item in object_list(value)))


def magnet_fields(value: object) -> tuple[str | None, tuple[str, ...]]:
    """Extract only a v1 hash and trackers from a magnet, discarding webseeds and other fields."""
    if value is None:
        return None, ()
    url: str = text(value)
    if not url.startswith("magnet:?"):
        return None, ()
    params: dict[str, list[str]] = parse_qs(urlsplit(url).query)
    hashes: list[str] = [
        normalized
        for xt in params.get("xt", ())
        if xt.startswith("urn:btih:") and (normalized := info_hash_hex(xt.removeprefix("urn:btih:"))) is not None
    ]
    return (hashes[0] if hashes else None), tuple(dict.fromkeys(params.get("tr", ())))
