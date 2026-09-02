"""Protocols exposed by the LLM domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from anishift.errors import AniShiftError, TransientError
from anishift.services._base import EngineInfo

if TYPE_CHECKING:
    from collections.abc import Callable

    from anishift.services.llm.types import LlmRequest, LlmResponse

__all__ = ["LlmAttemptObserver", "LlmEngine", "StreamingLlmEngine"]


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
class StreamingLlmEngine(Protocol):
    """Optional engine capability for incrementally received completions."""

    def complete_stream(
        self,
        request: LlmRequest,
        *,
        on_text: Callable[[str], None] | None = None,
    ) -> LlmResponse:
        """Run one completion while consuming provider chunks incrementally.

        Text is handed to *on_text* as it arrives, so a caller can report real
        progress rather than waiting for the completed response.
        """
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
