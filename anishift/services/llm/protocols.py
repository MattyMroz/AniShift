"""Protocols exposed by the LLM domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from anishift.errors import AniShiftError, TransientError
from anishift.services._base import EngineInfo

if TYPE_CHECKING:
    from anishift.services.llm.types import LlmRequest, LlmResponse

__all__ = ["LlmAttemptObserver", "LlmEngine"]


@runtime_checkable
class LlmEngine(EngineInfo, Protocol):
    """Synchronous contract implemented by every LLM provider engine."""

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one completion request."""
        ...

    def close(self) -> None:
        """Release resources held by the provider client."""
        ...


@runtime_checkable
class LlmAttemptObserver(Protocol):
    """Observe provider attempts without coupling the LLM domain to a scheduler."""

    def before_attempt(self) -> None:
        """Allow or reject the next provider attempt."""
        ...

    def on_transient_failure(self, error: TransientError) -> None:
        """Observe a retryable failure."""
        ...

    def on_success(self) -> None:
        """Observe a successful provider attempt."""
        ...

    def on_fatal_failure(self, error: AniShiftError) -> None:
        """Observe a non-retryable provider failure."""
        ...
