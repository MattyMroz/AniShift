"""LLM translation engine using a strict numbered response protocol.

The engine is provider-agnostic and never imports ``anishift.services.llm``.
Malformed output gets one format-only repair before deterministic binary
splitting. A failed single line raises instead of returning source as success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.constants import LINE_PATTERN
from anishift.services.translation.engines.llm.prompts import PromptComposer, PromptRegistry
from anishift.services.translation.errors import TranslationContextLengthError, TranslationEngineError
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
    TranslationInputPolicy,
    TranslationStream,
)
from anishift.services.translation.types import BatchedLine

if TYPE_CHECKING:
    from anishift.services.translation.protocols import LlmCompleter

# ── Constants ──────────────────────────────────────────────────────────────

_OUTPUT_LIMIT_REASONS: Final[frozenset[str]] = frozenset(("length", "max_tokens", "max_output_tokens", "model_length"))
"""Normalized finish reasons that require adaptive splitting."""


def _parse_numbered(text: str, expected: int) -> list[str] | None:
    """Parse ``[N] text`` lines into ordered texts, or None on a mismatch.

    Args:
        text: Raw model output (may include intro/markdown/outro noise).
        expected: Number of lines that must be present (indices 1..expected).

    Returns:
        The translated texts in index order, or ``None`` when any index is
        missing, duplicated or out of range.
    """
    by_index: dict[int, str] = {}
    for line in text.splitlines():
        match = LINE_PATTERN.match(line)
        if match is None:
            continue
        index = int(match.group(1))
        if index in by_index:
            return None  # a duplicated index means the model repeated a line
        translated = match.group(2).strip()
        if not translated:
            return None
        by_index[index] = translated
    if set(by_index) != set(range(1, expected + 1)):
        return None
    return [by_index[index] for index in range(1, expected + 1)]


class LlmTranslateService:
    """Translation engine prompting an injected LLM for numbered [N] output."""

    __slots__ = ("_completer", "_composer", "_config")

    def __init__(
        self,
        config: LlmTranslateConfig,
        *,
        completer: LlmCompleter,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        """Store config and the injected completer."""
        if not isinstance(config, LlmTranslateConfig):
            msg = "LlmTranslateService requires LlmTranslateConfig"
            raise TypeError(msg)
        self._config = config
        self._completer = completer
        self._composer = PromptComposer(
            prompt_registry or PromptRegistry(),
            task_id=self._config.prompt_id,
            style_id=self._config.style_id,
            module_ids=self._config.module_ids,
            context=self._config.context,
        )

    @property
    def engine_id(self) -> str:
        """Stable engine identifier (registry key)."""
        return "llm"

    @property
    def is_available(self) -> bool:
        """Whether a completer is wired in."""
        return self._completer is not None

    def close(self) -> None:
        """No-op: the completer is owned by the composition root."""

    def input_policy(self, stream: TranslationStream) -> TranslationInputPolicy:
        """Preserve dialogue occurrences and deduplicate displayed signs."""
        return "preserve" if stream == "spoken" else "deduplicate"

    def translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Translate lines with one-shot batches and deterministic recovery."""
        if not texts:
            return []
        translated: list[BatchedLine] = []
        for start in range(0, len(texts), self._config.max_batch_lines):
            batch = texts[start : start + self._config.max_batch_lines]
            translated.extend(self._translate_batch(batch, source_lang=source_lang, target_lang=target_lang))
        return translated

    def _translate_batch(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Translate one bounded batch and recover malformed output."""
        response = self._try_complete(
            texts,
            source_lang=source_lang,
            target_lang=target_lang,
            repair=False,
        )
        if response is None or self._hit_output_limit(response):
            return self._split(texts, source_lang=source_lang, target_lang=target_lang)
        parsed = _parse_numbered(response.text, len(texts))
        if parsed is not None:
            return self._as_lines(parsed)

        repaired = self._try_complete(
            texts,
            source_lang=source_lang,
            target_lang=target_lang,
            repair=True,
        )
        if repaired is None or self._hit_output_limit(repaired):
            return self._split(texts, source_lang=source_lang, target_lang=target_lang)
        parsed = _parse_numbered(repaired.text, len(texts))
        if parsed is not None:
            return self._as_lines(parsed)
        return self._split(texts, source_lang=source_lang, target_lang=target_lang)

    def _try_complete(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        repair: bool,
    ) -> LlmCompletionResult | None:
        """Return a completion or None when context length requires splitting."""
        try:
            return self._complete(
                texts,
                source_lang=source_lang,
                target_lang=target_lang,
                repair=repair,
            )
        except TranslationContextLengthError:
            return None

    def _split(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
    ) -> list[BatchedLine]:
        """Split a failed batch into stable halves or fail one line."""
        if len(texts) == 1:
            context = ErrorContext(
                code=ErrorCode.TRANSLATION_FAILED,
                message="LLM returned invalid numbered output for a single line",
                suggestion="Check the selected model and translation prompt.",
            )
            raise TranslationEngineError(context=context)
        mid = len(texts) // 2
        left = self._translate_batch(texts[:mid], source_lang=source_lang, target_lang=target_lang)
        right = self._translate_batch(texts[mid:], source_lang=source_lang, target_lang=target_lang)
        return left + right

    def _complete(
        self,
        texts: list[str],
        *,
        source_lang: str,
        target_lang: str,
        repair: bool,
    ) -> LlmCompletionResult:
        """Build and execute one typed completion request."""
        prompt = self._composer.compose(
            texts,
            source_lang=source_lang,
            target_lang=target_lang,
            repair=repair,
        )
        request = LlmCompletionRequest(
            system=prompt.system,
            user=prompt.user,
            identity=prompt.identity,
            omitted_context_items=prompt.omitted_context_items,
        )
        return self._completer.complete(request)

    @staticmethod
    def _as_lines(texts: list[str]) -> list[BatchedLine]:
        """Wrap successful translated texts as engine results."""
        return [BatchedLine(text=text) for text in texts]

    @staticmethod
    def _hit_output_limit(response: LlmCompletionResult) -> bool:
        """Return whether the provider stopped because of an output limit."""
        return response.finish_reason.strip().lower() in _OUTPUT_LIMIT_REASONS


__all__ = ["LlmTranslateService"]
