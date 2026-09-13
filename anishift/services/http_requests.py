"""Shared request admission, active-read coalescing and provider cooldowns."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future
from contextlib import AbstractContextManager, contextmanager, suppress
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from typing import Final

import httpx

from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_RETRY_AFTER_S: Final[float] = 60.0
"""Fallback cooldown when a provider omits its retry deadline."""

_MAX_BODY_BYTES: Final[int] = 8 * 1024 * 1024
"""Maximum buffered metadata response shared by concurrent callers."""

_REMOTE_INTERVAL_S: Final[float] = 1.0
"""Minimum separation of actual calls to each remote metadata provider."""


@dataclass(slots=True)
class _Operation:
    reason: str
    limits: Mapping[str, int]
    sent: Counter[str] = field(default_factory=Counter)


_OPERATION: Final[ContextVar[_Operation | None]] = ContextVar("http_operation", default=None)
"""Budget shared by nested adapter calls during one application operation."""


@contextmanager
def request_scope(reason: str, limits: Mapping[str, int]) -> Iterator[None]:
    """Count actual requests against one operation without resetting nested budgets."""
    if _OPERATION.get() is not None:
        yield
        return
    token: Token[_Operation | None] = _OPERATION.set(_Operation(reason, limits))
    try:
        yield
    finally:
        _OPERATION.reset(token)


class RequestControl(httpx.BaseTransport):
    """Apply shared admission to each physical request made by an HTTPX client."""

    def __init__(
        self,
        transport: httpx.BaseTransport,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport: httpx.BaseTransport = transport
        self._clock: Callable[[], float] = clock
        self._sleep: Callable[[float], None] = sleep
        self._lock: threading.Lock = threading.Lock()
        self._active: dict[str, Future[httpx.Response]] = {}
        self._until: dict[str, float] = {}
        self._next: dict[str, float] = {}
        self._counts: Counter[tuple[str, str, str, str]] = Counter()
        self._persist: Callable[[str, float], None] | None = None

    def restore(self, deadlines: Mapping[str, float], persist: Callable[[str, float], None]) -> None:
        """Restore durable cooldowns and attach their owner's persistence boundary."""
        with self._lock:
            for provider, until in deadlines.items():
                self._until[provider] = max(until, self._until.get(provider, 0.0))
            self._persist = persist

    def blocked_until(self, providers: tuple[str, ...]) -> float:
        """Return the shared earliest retry time for the named providers."""
        with self._lock:
            return max((self._until.get(provider, 0.0) for provider in providers), default=0.0)

    def counts(self) -> list[dict[str, object]]:
        """Return actual request counts without URLs, payloads or credentials."""
        with self._lock:
            return [
                {"provider": key[0], "operation": key[1], "reason": key[2], "result": key[3], "count": count}
                for key, count in sorted(self._counts.items())
            ]

    def scope(self, reason: str, limits: Mapping[str, int]) -> AbstractContextManager[None]:
        """Set the reason and request budget of one application operation."""
        return request_scope(reason, limits)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send one admitted request or join the equivalent read already in progress."""
        provider: str = _provider(request)
        shared: bool = request.method == "GET" or (provider == "anilist" and request.method == "POST")
        key: str = _key(request) if shared else ""
        with self._lock:
            future: Future[httpx.Response] | None = self._active.get(key) if shared else None
            follower: bool = future is not None
            if future is None:
                future = Future()
                if shared:
                    self._active[key] = future
        if follower:
            return _copy_response(future.result())
        try:
            self._admit(provider, request)
            response: httpx.Response = self._send(provider, request)
            future.set_result(response)
            return _copy_response(response)
        except BaseException as problem:
            future.set_exception(problem)
            raise
        finally:
            if shared:
                with self._lock:
                    self._active.pop(key, None)

    def close(self) -> None:
        """Close the wrapped connection pool."""
        self._transport.close()

    def _admit(self, provider: str, request: httpx.Request) -> None:
        while True:
            with self._lock:
                now: float = self._clock()
                if self._until.get(provider, 0.0) > now:
                    message: str = "Provider cooldown is active"
                    raise httpx.TransportError(message, request=request)
                delay: float = self._next.get(provider, 0.0) - now
                if delay <= 0:
                    self._charge(provider, request)
                    if provider in {"anilist", "nyaa"}:
                        self._next[provider] = now + _REMOTE_INTERVAL_S
                    return
            self._sleep(delay)

    def _charge(self, provider: str, request: httpx.Request) -> None:
        operation: _Operation | None = _OPERATION.get()
        if operation is None:
            return
        limit: int | None = operation.limits.get(provider)
        if limit is not None and operation.sent[provider] >= limit:
            message: str = "Operation request budget is exhausted"
            raise httpx.TransportError(message, request=request)
        operation.sent[provider] += 1

    def _send(self, provider: str, request: httpx.Request) -> httpx.Response:
        result: str = "transport_error"
        operation: _Operation | None = _OPERATION.get()
        reason: str = operation.reason if operation is not None else "user"
        kind: str = request.url.path.removeprefix("/api/v2/") if provider == "qbittorrent" else "metadata"
        try:
            response: httpx.Response = self._transport.handle_request(request)
            result = str(response.status_code)
            try:
                self._cooldown(provider, response)
                return _buffer_response(response, request)
            finally:
                response.close()
        finally:
            with self._lock:
                self._counts[(provider, kind, reason, result)] += 1
            logger.debug("HTTP request completed", provider=provider, operation=kind, reason=reason, result=result)

    def _cooldown(self, provider: str, response: httpx.Response) -> None:
        until: float = _retry_deadline(response, self._clock())
        if not until:
            return
        with self._lock:
            until = max(until, self._until.get(provider, 0.0))
            self._until[provider] = until
            persist: Callable[[str, float], None] | None = self._persist
        if persist is not None:
            persist(provider, until)


def _provider(request: httpx.Request) -> str:
    if request.url.host == "graphql.anilist.co":
        return "anilist"
    if request.url.host == "nyaa.si":
        return "nyaa"
    return "qbittorrent" if request.url.path.startswith("/api/v2/") else "other"


def _key(request: httpx.Request) -> str:
    values: tuple[bytes, ...] = (
        request.method.encode(),
        str(request.url).encode(),
        request.content,
        *(part for pair in request.headers.raw for part in pair),
    )
    return hashlib.sha256(b"".join(len(value).to_bytes(8) + value for value in values)).hexdigest()


def _copy_response(response: httpx.Response) -> httpx.Response:
    headers: httpx.Headers = httpx.Headers(response.headers)
    headers.pop("content-encoding", None)
    headers.pop("content-length", None)
    return httpx.Response(response.status_code, headers=headers, content=response.content)


def _buffer_response(response: httpx.Response, request: httpx.Request) -> httpx.Response:
    if response.is_stream_consumed:
        return _copy_response(response)
    body: bytearray = bytearray()
    for chunk in response.iter_raw():
        body.extend(chunk)
        if len(body) > _MAX_BODY_BYTES:
            message: str = "Metadata response is too large"
            raise httpx.TransportError(message, request=request)
    return httpx.Response(response.status_code, headers=response.headers, content=bytes(body))


def _retry_deadline(response: httpx.Response, now: float) -> float:
    retry: str | None = response.headers.get("retry-after")
    exhausted: bool = response.headers.get("x-ratelimit-remaining") == "0"
    if retry is None and not exhausted and response.status_code != HTTPStatus.TOO_MANY_REQUESTS:
        return 0.0
    until: float = now + _RETRY_AFTER_S
    if retry is not None:
        try:
            until = now + max(0.0, float(retry))
        except ValueError:
            try:
                parsed: datetime = parsedate_to_datetime(retry)
                until = parsed.replace(tzinfo=UTC).timestamp() if parsed.tzinfo is None else parsed.timestamp()
            except ValueError, TypeError, OverflowError:
                pass
    reset: str | None = response.headers.get("x-ratelimit-reset")
    if reset is not None:
        with suppress(ValueError):
            until = max(until, float(reset))
    return max(now, until)
