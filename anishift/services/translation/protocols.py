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

PromptPurpose = Literal["translation", "translation_repair"]
"""Stable purpose identifier attached to a translation LLM request."""

type TranslationEngineFactory = Callable[
    [str, TranslationConfig],
    TranslationEngine,
]
"""Build a translation engine for one fallback-chain entry."""


@dataclass(frozen=True, slots=True)
class PromptIdentity:
    """Identity of the static prompt assets used for a completion.

    Attributes:
        prompt_id: Selected translation task identifier.
        prompt_version: Version of the selected task.
        style_id: Selected translation style identifier.
        fingerprint: SHA-256 fingerprint of all static prompt assets.
        purpose: Translation or output-format repair.
    """

    prompt_id: str
    prompt_version: int
    style_id: str
    fingerprint: str
    purpose: PromptPurpose


@dataclass(frozen=True, slots=True)
class LlmCompletionRequest:
    """Translation-owned LLM completion input."""

    system: str
    user: str
    identity: PromptIdentity
    omitted_context_items: int = 0


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
    ) -> list[BatchedLine]:
        """Translate one batch; output length must equal input length."""
        ...

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        """Return the preparation policy for one subtitle stream."""
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

    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        """Run one completion and return normalized text plus finish reason."""
        ...


__all__ = [
    "LlmCompleter",
    "LlmCompletionRequest",
    "LlmCompletionResult",
    "PromptIdentity",
    "PromptPurpose",
    "TranslationEngine",
    "TranslationEngineFactory",
    "TranslationInputPolicy",
    "TranslationStream",
]
