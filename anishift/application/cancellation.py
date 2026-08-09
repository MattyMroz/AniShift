"""Minimal cancellation contract for services, handlers, and schedulers."""

from __future__ import annotations

import threading
from typing import Protocol

from anishift.errors import ErrorCode, ErrorContext, ExecutionError

__all__ = ["CancellationToken", "EventCancellationToken", "NeverCancelledToken"]


class CancellationToken(Protocol):
    """Cooperative cancellation view passed across application boundaries."""

    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        ...

    def raise_if_cancelled(self) -> None:
        """Raise the token's cancellation error when cancellation was requested."""
        ...


class NeverCancelledToken:
    """No-op cancellation token used by deterministic unit tests."""

    def is_cancelled(self) -> bool:
        """Return false because this token never transitions."""
        return False

    def raise_if_cancelled(self) -> None:
        """Return without raising because this token never transitions."""


class EventCancellationToken:
    """Idempotent thread-safe cancellation source implementing the narrow token."""

    __slots__ = ("_event",)

    def __init__(self) -> None:
        """Create a token with cancellation initially open."""
        self._event: threading.Event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation; repeated requests have no additional effect."""
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
