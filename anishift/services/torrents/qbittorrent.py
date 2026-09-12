"""qBittorrent Web UI client with one lazy login retry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.torrents.errors import TorrentClientError
from anishift.services.torrents.types import TorrentInfo
from anishift.utils.logger import get_logger

__all__ = ["QBittorrentClient"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

API_PREFIX: Final[str] = "/api/v2"
"""Path prefix of the Web UI API."""

DEFAULT_TIMEOUT_S: Final[float] = 10.0
"""Timeout applied to one Web UI request."""

OK_BODY: Final[str] = "Ok."
"""Body the Web UI returns for an accepted command."""

_AUTH_SUGGESTION: Final[str] = (
    "Set ANISHIFT_QBITTORRENT_USERNAME and ANISHIFT_QBITTORRENT_PASSWORD, "
    "or allow localhost without authentication in qBittorrent Web UI options"
)
"""Recovery hint for a rejected Web UI login."""

_UNAVAILABLE_SUGGESTION: Final[str] = (
    "In qBittorrent open Options → Web UI, enable the Web User Interface and allow localhost without authentication"
)
"""Recovery hint for a Web UI that does not answer at all."""

_REFUSAL_SUGGESTION: Final[str] = "Check the qBittorrent Web UI version and permissions"
"""Recovery hint for a request the Web UI refused."""


class _Refusal(StrEnum):
    """Ways one Web UI answer can be unusable."""

    REQUEST = "request"
    PREFERENCES = "preferences"
    TORRENT_LIST = "torrent_list"
    BODY = "body"


_REFUSAL_MESSAGES: Final[dict[_Refusal, str]] = {
    _Refusal.REQUEST: "qBittorrent rejected the request",
    _Refusal.PREFERENCES: "qBittorrent returned unreadable preferences",
    _Refusal.TORRENT_LIST: "qBittorrent returned an unreadable torrent list",
    _Refusal.BODY: "qBittorrent returned an unreadable response",
}
"""Message shown for each refused Web UI answer."""


class QBittorrentClient:
    """Synchronous Web UI boundary: version, preferences, add, and list."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str = "",
        password: str = "",
        http: httpx.Client,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        """Bind the client to one Web UI address and the caller-owned HTTP client."""
        self._base_url: str = base_url.rstrip("/")
        self._username: str = username
        self._password: str = password
        self._http: httpx.Client = http
        self._timeout_s: float = timeout_s

    def version(self) -> str:
        """Return the running qBittorrent version without its ``v`` prefix."""
        return self._request("GET", "/app/version").text.strip().removeprefix("v")

    def preferences(self) -> dict[str, object]:
        """Return the current Web UI preferences."""
        payload: object = self._decode(self._request("GET", "/app/preferences"))
        if not isinstance(payload, dict):
            raise self._refused(_Refusal.PREFERENCES)
        return payload

    def set_preferences(self, values: Mapping[str, object]) -> None:
        """Apply the given preference values."""
        self._request("POST", "/app/setPreferences", data={"json": json.dumps(dict(values))})

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        """Hand one torrent URL to the client, saving it under *save_path*."""
        response: httpx.Response = self._request(
            "POST",
            "/torrents/add",
            data={"urls": torrent_url, "savepath": str(save_path), "category": category},
            accept_errors=True,
        )
        if not _torrent_accepted(response):
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_REFUSED,
                    message="qBittorrent refused the torrent",
                    suggestion="It may already be in the client",
                    details={"operation": "qbittorrent_add", "status": response.status_code},
                )
            )
        logger.info("Added a torrent to qBittorrent", category=category)

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        """Return the torrents the client tracks under *category*."""
        payload: object = self._decode(self._request("GET", "/torrents/info", params={"category": category}))
        if not isinstance(payload, list):
            raise self._refused(_Refusal.TORRENT_LIST)
        return tuple(_torrent_info(entry) for entry in payload if isinstance(entry, dict))

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        accept_errors: bool = False,
    ) -> httpx.Response:
        """Send one API request, logging in once when the Web UI answers with 403."""
        response: httpx.Response = self._send(method, path, data=data, params=params)
        if response.status_code == HTTPStatus.FORBIDDEN:
            self._login()
            response = self._send(method, path, data=data, params=params)
            if response.status_code == HTTPStatus.FORBIDDEN:
                raise self._unauthorized()
        if not accept_errors and response.status_code >= HTTPStatus.BAD_REQUEST:
            raise self._refused(_Refusal.REQUEST)
        return response

    def _send(
        self,
        method: str,
        path: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Perform one transport call, mapping an unreachable Web UI onto a domain error."""
        try:
            return self._http.request(
                method,
                f"{self._base_url}{API_PREFIX}{path}",
                data=dict(data) if data is not None else None,
                params=dict(params) if params is not None else None,
                headers=dict(headers) if headers is not None else None,
                timeout=self._timeout_s,
            )
        except httpx.TransportError as error:
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                    message="qBittorrent Web UI is not reachable",
                    suggestion=_UNAVAILABLE_SUGGESTION,
                    details={"operation": "qbittorrent_request"},
                )
            ) from error

    def _login(self) -> None:
        """Authenticate once against the Web UI."""
        response: httpx.Response = self._send(
            "POST",
            "/auth/login",
            data={"username": self._username, "password": self._password},
            headers={"Referer": self._base_url},
        )
        if response.status_code != HTTPStatus.OK or response.text.strip() != OK_BODY:
            raise self._unauthorized()

    def _decode(self, response: httpx.Response) -> object:
        """Return the decoded JSON body of one response."""
        try:
            return response.json()
        except ValueError as error:
            raise self._refused(_Refusal.BODY) from error

    def _unauthorized(self) -> TorrentClientError:
        """Build the rejected-credentials failure."""
        return TorrentClientError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_CLIENT_UNAUTHORIZED,
                message="qBittorrent rejected the credentials",
                suggestion=_AUTH_SUGGESTION,
                details={"operation": "qbittorrent_login"},
            )
        )

    def _refused(self, refusal: _Refusal) -> TorrentClientError:
        """Build a refused-request failure."""
        return TorrentClientError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_CLIENT_REFUSED,
                message=_REFUSAL_MESSAGES[refusal],
                suggestion=_REFUSAL_SUGGESTION,
                details={"operation": "qbittorrent_request", "reason": refusal.value},
            )
        )


def _torrent_accepted(response: httpx.Response) -> bool:
    """Whether ``torrents/add`` took the torrent: ``Ok.`` before Web API 2.11, else a 202 report without failures."""
    if response.status_code == HTTPStatus.OK:
        return response.text.strip() == OK_BODY
    if response.status_code != HTTPStatus.ACCEPTED:
        return False
    try:
        report: object = response.json()
    except ValueError:
        return False
    return isinstance(report, dict) and report.get("failure_count") == 0


def _torrent_info(entry: Mapping[str, object]) -> TorrentInfo:
    """Map one torrent list entry onto the neutral contract."""
    progress: object = entry.get("progress", 0.0)
    return TorrentInfo(
        name=str(entry.get("name", "")),
        info_hash=str(entry.get("hash", "")),
        progress=float(progress) if isinstance(progress, int | float) else 0.0,
        state=str(entry.get("state", "")),
        save_path=str(entry.get("save_path", "")),
    )
