"""Free 1VPN routing used natively by the ElevenBytes engine."""

from __future__ import annotations

import random
import ssl
import statistics
import time
from functools import cache
from typing import Final

import httpx

__all__ = [
    "HOSTS",
    "VPN_CONNECT_TIMEOUT_SECONDS",
    "VPN_MAX_CONCURRENCY",
    "VpnError",
    "VpnTransport",
]

# ── Constants ─────────────────────────────────────────────────────────────────────────

_USERNAME: Final[str] = "a2epfq5ugq0u"
"""Free-tier username published by the 1VPN browser extension."""

_PASSWORD: Final[str] = "ptkx3fqg6v7n"  # noqa: S105
"""Free-tier password published by the 1VPN browser extension."""

_PORT: Final[int] = 443
"""HTTPS proxy port used by every 1VPN server."""

HOSTS: Final[dict[str, tuple[str, ...]]] = {
    "ams": (
        "free-amsterdam-https-1.cloudburstcdn.com",
        "free-amsterdam-https-2.cloudflingcdn.com",
        "free-amsterdam-https-3.cloudflaracdn.com",
        "free-amsterdam-https-4.cloudflaracdn.com",
        "free-amsterdam-https-5.cloudflingcdn.com",
        "free-amsterdam-https-6.cloudflingcdn.com",
    ),
    "sgp": (
        "free-singapore-https-1.cloudburstcdn.com",
        "free-singapore-https-2.cloudtimecdn.com",
        "free-singapore-https-3.weathercloudapp.com",
        "free-singapore-https-4.cloudflingcdn.com",
    ),
    "lax": (
        "free-los-angeles-https-1.cloudburstcdn.com",
        "free-los-angeles-https-2.cloudtimecdn.com",
        "free-los-angeles-https-3.cloudflaracdn.com",
        "free-los-angeles-https-4.cloudflaracdn.com",
        "free-los-angeles-https-5.cloudflingcdn.com",
        "free-los-angeles-https-6.cloudflingcdn.com",
        "usa-west-free-https-1.weathercloudapp.com",
    ),
}
"""Free 1VPN servers grouped by location code."""

_PER_SERVER_PARALLEL: Final[int] = 6
"""Maximum simultaneous requests assigned to one VPN server."""

_SHARE_FACTOR: Final[float] = 1.5
"""Maximum multiple of one server's fair share of dispatched requests."""

_SLOW_FACTOR: Final[float] = 5.0
"""Maximum multiple of median latency kept in normal rotation."""

_RECENT_WINDOW: Final[int] = 5
"""Recent successful response times retained for each server."""

_WARMUP_PICKS: Final[int] = 2
"""Successful requests required before a server's latency is trusted."""

_POOL_LIMIT: Final[int] = 100
"""Connection-pool headroom for each server-specific transport."""

_KEEPALIVE_EXPIRY_SECONDS: Final[float] = 60.0
"""Time an idle proxy connection remains reusable."""

_TRANSPORT_RETRIES: Final[int] = 1
"""Connect retries used by the original standalone VPN transport."""

VPN_CONNECT_TIMEOUT_SECONDS: Final[float] = 8.0
"""Maximum proxy handshake time before httpx reports a timeout."""

VPN_MAX_CONCURRENCY: Final[int] = 100
"""Global request ceiling across the bundled VPN servers."""

_RETRYABLE: Final[tuple[type[httpx.TransportError], ...]] = (
    httpx.ConnectError,
    httpx.ProxyError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.TimeoutException,
)
"""Network failures that move the same request to another VPN server."""


class VpnError(Exception):
    """No configured VPN server could serve a request."""


@cache
def _tls_context() -> ssl.SSLContext:
    """Return the TLS context shared by every proxy hop and tunnelled request.

    httpcore builds a fresh context and reparses the whole CA bundle for each
    connection left without one, blocking the event loop for hundreds of
    milliseconds per route.
    """
    return httpx.create_ssl_context()


def _proxy_urls(location: str | None = None) -> list[str]:
    """Return proxy URLs in a new random order for this process."""
    if location is None:
        hosts: list[str] = [host for group in HOSTS.values() for host in group]
    elif location in HOSTS:
        hosts = list(HOSTS[location])
    else:
        message: str = f"Unknown VPN location {location!r}; available: {', '.join(HOSTS)}"
        raise VpnError(message)
    random.shuffle(hosts)
    return [f"https://{_USERNAME}:{_PASSWORD}@{host}:{_PORT}" for host in hosts]


class VpnTransport(httpx.AsyncBaseTransport):
    """Spread requests across stable per-server connection pools.

    Selection matches the original standalone ``one_vpn.py`` transport: slow,
    busy, and overused servers are filtered when alternatives exist, while a
    network failure immediately moves the request to an untried server. The
    transport never falls back to the local connection.
    """

    def __init__(
        self,
        location: str | None = None,
        parallel: int = _PER_SERVER_PARALLEL,
        share: float = _SHARE_FACTOR,
    ) -> None:
        """Open one persistent connection pool per selected VPN server."""
        urls: list[str] = _proxy_urls(location)
        limits: httpx.Limits = httpx.Limits(
            max_connections=_POOL_LIMIT,
            max_keepalive_connections=_POOL_LIMIT,
            keepalive_expiry=_KEEPALIVE_EXPIRY_SECONDS,
        )
        tls_context: ssl.SSLContext = _tls_context()
        self.hosts: list[str] = [url.rsplit("@", 1)[-1] for url in urls]
        self.pools: list[httpx.AsyncBaseTransport] = [
            httpx.AsyncHTTPTransport(
                proxy=httpx.Proxy(url=url, ssl_context=tls_context),
                verify=tls_context,
                retries=_TRANSPORT_RETRIES,
                limits=limits,
            )
            for url in urls
        ]
        self.sent: list[int] = [0] * len(urls)
        self.times: dict[str, list[float]] = {host: [] for host in self.hosts}
        self.parallel: int = parallel
        self.share: float = share
        self._busy: list[int] = [0] * len(urls)

    @property
    def concurrency(self) -> int:
        """Return total simultaneous request capacity across all pools."""
        return min(len(self.pools) * self.parallel, VPN_MAX_CONCURRENCY)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Send through the best server and fail over on network errors."""
        last_error: httpx.TransportError | None = None
        tried: set[int] = set()
        while len(tried) < len(self.pools):
            index: int = self._select(tried)
            tried.add(index)
            self._busy[index] += 1
            self.sent[index] += 1
            started_at: float = time.perf_counter()
            try:
                response: httpx.Response = await self.pools[index].handle_async_request(request)
            except _RETRYABLE as error:
                last_error = error
            else:
                elapsed_seconds: float = time.perf_counter() - started_at
                self.times[self.hosts[index]].append(elapsed_seconds)
                return response
            finally:
                self._busy[index] -= 1
        message: str = f"All {len(self.pools)} VPN servers failed"
        raise VpnError(message) from last_error

    async def aclose(self) -> None:
        """Close every server-specific connection pool."""
        for pool in self.pools:
            await pool.aclose()

    def _speed(self, index: int) -> float | None:
        recent: list[float] = self.times[self.hosts[index]][-_RECENT_WINDOW:]
        if len(recent) < _WARMUP_PICKS:
            return None
        return statistics.median(recent)

    def _score(self, index: int) -> float:
        speed: float | None = self._speed(index)
        if speed is None:
            return self._busy[index] * 0.001
        return speed * (self._busy[index] + 1)

    def _fast_enough(self, index: int) -> bool:
        speed: float | None = self._speed(index)
        if speed is None:
            return True
        known: list[float] = [
            known_speed for pool_index in range(len(self.pools)) if (known_speed := self._speed(pool_index)) is not None
        ]
        return not known or speed <= statistics.median(known) * _SLOW_FACTOR

    def _fair_share(self, index: int) -> bool:
        total: int = sum(self.sent)
        if total < len(self.pools) * _WARMUP_PICKS:
            return True
        return self.sent[index] <= (total / len(self.pools)) * self.share

    def _select(self, tried: set[int]) -> int:
        free: list[int] = [index for index in range(len(self.pools)) if index not in tried]
        healthy: list[int] = [index for index in free if self._fast_enough(index)]
        room: list[int] = [index for index in healthy if self._busy[index] < self.parallel]
        fair: list[int] = [index for index in room if self._fair_share(index)]
        return min(fair or room or healthy or free, key=self._score)
