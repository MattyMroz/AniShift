"""Engine contract for the translation domain (sync).

``TranslationEngine`` is the contract every engine satisfies; the facade only
talks to this protocol. ``LlmCompleter`` is the minimal LLM contract the LLM
engine depends on - injected from the composition root so translation never
imports ``anishift.services.llm`` directly (independence contract, stage 5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from anishift.services._base import EngineInfo

if TYPE_CHECKING:
    from anishift.services.translation.config import TranslationConfig
    from anishift.services.translation.types import BatchedLine

TranslationInputPolicy = Literal["deduplicate", "preserve"]
"""Preparation policy applied before an engine receives a stream."""

TranslationStream = Literal["spoken", "displayed"]
"""Subtitle text stream translated by an engine."""

type TranslationEngineFactory = Callable[
    [str, TranslationConfig],
    TranslationEngine,
]
"""Build a translation engine for one fallback-chain entry."""


@dataclass(frozen=True, slots=True)
class LlmCompletionRequest:
    """Translation-owned LLM completion input."""

    system: str
    user_parts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LlmCompletionResult:
    """Translation-owned LLM completion output."""

    text: str
    finish_reason: str


@runtime_checkable
class TranslationEngine(EngineInfo, Protocol):
    """Sync contract for a translation engine.

    The facade hands each engine an already-deduplicated set of single-line
    texts and a caller language code; the engine returns one ``BatchedLine`` per
    input line, same order (failed lines carry source + ``ok=False``).
    """

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        observer: TranslationObserver | None = None,
    ) -> list[BatchedLine]:
        """Translate one batch; output length must equal input length."""
        ...

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        """Return the preparation policy for one subtitle stream."""
        ...

    def close(self) -> None:
        """Release resources held by the engine."""
        ...


class TranslationCancellation(Protocol):
    """Minimal cancellation view accepted by the synchronous facade."""

    def is_set(self) -> bool:
        """Return whether the caller requested cancellation."""
        ...


class TranslationObserver(Protocol):
    """Observer of translation progress, retry and fallback decisions."""

    def progress(self, engine_id: str, completed: int, total: int) -> None:
        """Observe completed provider input lines."""
        ...

    def retry(
        self,
        engine_id: str,
        attempt: int,
        max_attempts: int,
        reason: str | None = None,
    ) -> None:
        """Observe one provider request being scheduled again."""
        ...

    def fallback(self, failed_engine_id: str, next_engine_id: str) -> None:
        """Observe the facade selecting the next configured engine."""
        ...


@runtime_checkable
class LlmCompleter(Protocol):
    """Minimal LLM contract the LLM translation engine depends on (sync).

    Injected from the composition root (stage 5). The engine knows only this
    protocol, never the concrete LLM service.
    """

    def complete(
        self,
        request: LlmCompletionRequest,
        *,
        on_text: Callable[[str], None] | None = None,
    ) -> LlmCompletionResult:
        """Run one completion and return normalized text plus finish reason.

        Text reaches *on_text* while the provider is still producing it, which is
        what lets the engine report progress inside one request. A provider that
        cannot stream simply never calls it.
        """
        ...


__all__ = [
    "LlmCompleter",
    "LlmCompletionRequest",
    "LlmCompletionResult",
    "TranslationCancellation",
    "TranslationEngine",
    "TranslationEngineFactory",
    "TranslationInputPolicy",
    "TranslationObserver",
    "TranslationStream",
]
