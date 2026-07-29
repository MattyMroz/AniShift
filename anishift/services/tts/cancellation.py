"""Thread-safe cancellation and late-result commit gating for TTS."""

from __future__ import annotations

import asyncio
import threading

__all__ = ["TtsCancellation"]


class TtsCancellation:
    """One run-scoped cancellation token shared by sync and async callers."""

    __slots__ = ("_event", "_generation", "_lock")

    def __init__(self) -> None:
        """Create an open commit gate for the first run generation."""
        self._event: threading.Event = threading.Event()
        self._generation: int = 1
        self._lock: threading.Lock = threading.Lock()

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
        await asyncio.to_thread(self._event.wait)

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
