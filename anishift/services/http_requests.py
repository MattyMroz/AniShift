"""Shared request admission, active-read coalescing and provider cooldowns."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter, deque
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager, suppress
from contextvars import ContextVar, Token, copy_context
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from types import MappingProxyType
from typing import Final

import httpx

from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

USER_AGENT: Final[str] = "AniShift/0.1"
"""Client identity sent with public metadata requests."""

_RETRY_AFTER_S: Final[float] = 60.0
"""Fallback cooldown when a provider omits its retry deadline."""

_MAX_BODY_BYTES: Final[int] = 8 * 1024 * 1024
"""Maximum buffered metadata response shared by concurrent callers."""

REMOTE_INTERVAL_S: Final[float] = 1.0
"""Minimum separation of actual calls to each remote metadata provider."""

_REQUEST_WORKERS: Final[int] = 10
"""Maximum concurrent physical requests for operations with caller deadlines."""

_TSUKIHIME_WINDOWS: Final[tuple[tuple[int, float], ...]] = ((25, 10.0), (60, 30.0), (100, 60.0))
"""Simultaneous sliding request limits advertised by TsukiHime."""

_PROVIDERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "graphql.anilist.co": "anilist",
        "nyaa.si": "nyaa",
        "api.ani.zip": "anizip",
        "arm.haglund.dev": "arm",
        "kitsu.io": "kitsu",
        "torrentio.strem.fun": "torrentio",
        "api.tsukihime.org": "tsukihime",
        "api.knaben.org": "knaben",
        "nekobt.to": "nekobt",
    }
)
"""Independent admission and cooldown identities of public metadata hosts."""


class DeadlineExceeded(httpx.TimeoutException):
    """The caller's operation deadline expired without cancelling a shared physical request."""


class ProviderCooldown(httpx.TransportError):
    """A provider's shared retry deadline prevents sending a request."""


class BudgetExhausted(httpx.TransportError):
    """An operation has already sent its allowed number of requests to this provider."""


@dataclass(slots=True)
class _Operation:
    reason: str
    limits: Mapping[str, int]
    deadline: float | None = None
    sent: Counter[str] = field(default_factory=Counter)


_OPERATION: Final[ContextVar[_Operation | None]] = ContextVar("http_operation", default=None)
"""Budget shared by nested adapter calls during one application operation."""


@contextmanager
def request_scope(reason: str, limits: Mapping[str, int], *, deadline_s: float | None = None) -> Iterator[None]:
    """Count actual requests against one operation without resetting nested budgets."""
    if _OPERATION.get() is not None:
        yield
        return
    deadline: float | None = None if deadline_s is None else time.monotonic() + deadline_s
    token: Token[_Operation | None] = _OPERATION.set(_Operation(reason, limits, deadline))
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
        self._pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=_REQUEST_WORKERS, thread_name_prefix="http-request"
        )
        self._tsukihime_sent: deque[float] = deque()
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

    def scope(
        self, reason: str, limits: Mapping[str, int], *, deadline_s: float | None = None
    ) -> AbstractContextManager[None]:
        """Set the reason and request budget of one application operation."""
        return request_scope(reason, limits, deadline_s=deadline_s)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send one admitted request or join the equivalent read already in progress."""
        future: Future[httpx.Response]
        follower: bool
        while True:
            future, follower = self._request_future(request)
            try:
                return _wait_response(future, request)
            except DeadlineExceeded, BudgetExhausted:
                if not follower:
                    raise
                _remaining(request)
                with self._lock:
                    self._check_budget(_provider(request), request)

    def _request_future(self, request: httpx.Request) -> tuple[Future[httpx.Response], bool]:
        provider: str = _provider(request)
        remaining: float | None = _remaining(request)
        shared: bool = request.method == "GET" or (provider == "anilist" and request.method == "POST")
        key: str = _key(request) if shared else ""
        with self._lock:
            future: Future[httpx.Response] | None = self._active.get(key) if shared else None
            follower: bool = future is not None
            if future is None:
                future = (
                    self._pool.submit(copy_context().run, self._perform, provider, request, key)
                    if remaining is not None
                    else Future()
                )
                if shared:
                    self._active[key] = future
        if follower or remaining is not None:
            return future, follower
        try:
            future.set_result(self._perform(provider, request, key))
        except BaseException as problem:
            future.set_exception(problem)
            raise
        return future, follower

    def close(self) -> None:
        """Cancel queued deadline work without waiting for running requests, then close the transport."""
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._transport.close()

    def _perform(self, provider: str, request: httpx.Request, key: str) -> httpx.Response:
        try:
            self._admit(provider, request)
            return self._send(provider, request)
        finally:
            if key:
                with self._lock:
                    self._active.pop(key, None)

    def _admit(self, provider: str, request: httpx.Request) -> None:
        while True:
            remaining: float | None = _remaining(request)
            with self._lock:
                now: float = self._clock()
                if self._until.get(provider, 0.0) > now:
                    message: str = "Provider cooldown is active"
                    raise ProviderCooldown(message, request=request)
                delay: float = self._next.get(provider, 0.0) - now
                if provider == "tsukihime":
                    delay = max(delay, self._tsukihime_delay(now))
                if delay <= 0:
                    self._charge(provider, request)
                    if provider in {"anilist", "nyaa"}:
                        self._next[provider] = now + REMOTE_INTERVAL_S
                    if provider == "tsukihime":
                        self._tsukihime_sent.append(now)
                    return
            self._sleep(delay if remaining is None else min(delay, remaining))

    def _tsukihime_delay(self, now: float) -> float:
        while self._tsukihime_sent and self._tsukihime_sent[0] <= now - _TSUKIHIME_WINDOWS[-1][1]:
            self._tsukihime_sent.popleft()
        return max(
            (
                self._tsukihime_sent[-limit] + window - now
                for limit, window in _TSUKIHIME_WINDOWS
                if len(self._tsukihime_sent) >= limit
            ),
            default=0.0,
        )

    def _charge(self, provider: str, request: httpx.Request) -> None:
        self._check_budget(provider, request)
        operation: _Operation | None = _OPERATION.get()
        if operation is not None:
            operation.sent[provider] += 1

    def _check_budget(self, provider: str, request: httpx.Request) -> None:
        operation: _Operation | None = _OPERATION.get()
        if operation is None:
            return
        limit: int | None = operation.limits.get(provider)
        if limit is not None and operation.sent[provider] >= limit:
            message: str = "Operation request budget is exhausted"
            raise BudgetExhausted(message, request=request)

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
    return _PROVIDERS.get(request.url.host, "qbittorrent" if request.url.path.startswith("/api/v2/") else "other")


def _remaining(request: httpx.Request) -> float | None:
    operation: _Operation | None = _OPERATION.get()
    if operation is None or operation.deadline is None:
        return None
    remaining: float = operation.deadline - time.monotonic()
    if remaining <= 0:
        message: str = "Operation deadline exceeded"
        raise DeadlineExceeded(message, request=request)
    return remaining


def _wait_response(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
    try:
        try:
            return _copy_response(future.result(timeout=_remaining(request)))
        except TimeoutError as problem:
            if future.done():
                return _copy_response(future.result())
            message: str = "Operation deadline exceeded"
            raise DeadlineExceeded(message, request=request) from problem
    except CancelledError as problem:
        message = "Request control closed before sending the request"
        raise httpx.TransportError(message, request=request) from problem


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
