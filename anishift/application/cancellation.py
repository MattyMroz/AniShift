"""Minimal cancellation contract for services, handlers, and schedulers."""

from __future__ import annotations

from typing import Protocol


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
