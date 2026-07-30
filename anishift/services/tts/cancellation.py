"""Thread-safe cancellation and late-result commit gating for TTS."""

from __future__ import annotations

import asyncio
import threading
from contextlib import suppress

__all__ = ["TtsCancellation"]


class TtsCancellation:
    """One run-scoped cancellation token shared by sync and async callers."""

    __slots__ = ("_event", "_generation", "_lock", "_waiters")

    def __init__(self) -> None:
        """Create an open commit gate for the first run generation."""
        self._event: threading.Event = threading.Event()
        self._generation: int = 1
        self._lock: threading.Lock = threading.Lock()
        self._waiters: dict[asyncio.Future[None], asyncio.AbstractEventLoop] = {}

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation was requested."""
        return self._event.is_set()

    @property
    def generation(self) -> int:
        """Return the generation captured by submitted work."""
        with self._lock:
            return self._generation

    async def wait(self) -> None:
        """Wait without binding the thread-safe event to one event loop."""
        if self._event.is_set():
            return
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        with self._lock:
            if self._event.is_set():
                return
            self._waiters[waiter] = loop
        try:
            await waiter
        finally:
            with self._lock:
                self._waiters.pop(waiter, None)

    def can_commit(self, generation: int) -> bool:
        """Allow commits only from the current non-cancelled generation."""
        with self._lock:
            return not self._event.is_set() and generation == self._generation

    def cancel(self) -> None:
        """Close the commit gate and wake every cancellation waiter."""
        with self._lock:
            if self._event.is_set():
                return
            self._generation += 1
            self._event.set()
            waiters: tuple[tuple[asyncio.Future[None], asyncio.AbstractEventLoop], ...] = tuple(
                self._waiters.items(),
            )
            self._waiters.clear()
        for waiter, loop in waiters:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(_resolve_waiter, waiter)


def _resolve_waiter(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)
