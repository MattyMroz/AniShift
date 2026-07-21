"""Engine contract for the translation domain (sync).

``TranslationEngine`` is the contract every engine satisfies; the facade only
talks to this protocol. ``LlmCompleter`` is the minimal LLM contract the LLM
engine depends on - injected from the composition root so translation never
imports ``anishift.services.llm`` directly (independence contract, stage 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from anishift.services._base import EngineInfo

if TYPE_CHECKING:
    from anishift.services.translation.types import BatchedLine


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
    ) -> list[BatchedLine]:
        """Translate one batch; output length must equal input length."""
        ...

    def close(self) -> None:
        """Release resources held by the engine."""
        ...


@runtime_checkable
class LlmCompleter(Protocol):
    """Minimal LLM contract the LLM translation engine depends on (sync).

    Injected from the composition root (stage 5). The engine knows only this
    protocol, never the concrete LLM service.
    """

    def complete(self, system: str, user: str) -> str:
        """Run a single chat completion and return the assistant text."""
        ...


__all__ = ["LlmCompleter", "TranslationEngine"]
