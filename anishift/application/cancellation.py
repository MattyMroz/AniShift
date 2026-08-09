"""Minimal cancellation contract for services, handlers, and schedulers."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from anishift.errors import ErrorCode, ErrorContext, ExecutionError

__all__ = [
    "CancellationToken",
    "CommitCancellationToken",
    "EventCancellationToken",
    "NeverCancelledToken",
]


class CancellationToken(Protocol):
    """Cooperative cancellation view passed across application boundaries."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        ...

    def raise_if_cancelled(self) -> None:
        """Raise the token's cancellation error when cancellation was requested."""
        ...


class CommitCancellationToken(CancellationToken, Protocol):
    """Run-level cancellation token that guards the final durable commit."""

    def commit_if_active(self, action: Callable[[], None]) -> bool:
        """Run one final commit atomically against a concurrent cancel request."""
        ...


class NeverCancelledToken:
    """No-op cancellation token used by deterministic unit tests."""

    def is_cancelled(self) -> bool:
        """Return false because this token never transitions."""
        return False

    def raise_if_cancelled(self) -> None:
        """Return without raising because this token never transitions."""

    def commit_if_active(self, action: Callable[[], None]) -> bool:
        """Run the commit because this token never transitions."""
        action()
        return True


class EventCancellationToken:
    """Idempotent thread-safe cancellation source implementing the narrow token."""

    __slots__ = ("_event", "_lock")

    def __init__(self) -> None:
        """Create a token with cancellation initially open."""
        self._event: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()

    def cancel(self) -> None:
        """Request cancellation; repeated requests have no additional effect."""
        with self._lock:
            self._event.set()

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raise a structured execution error after cancellation is requested."""
        if not self._event.is_set():
            return
        context: ErrorContext = ErrorContext(
            code=ErrorCode.CANCELLED,
            message="Workflow execution was cancelled",
        )
        raise ExecutionError(context=context)

    def commit_if_active(self, action: Callable[[], None]) -> bool:
        """Serialize one final commit with the cancellation transition."""
        with self._lock:
            if self._event.is_set():
                return False
            action()
            return True
