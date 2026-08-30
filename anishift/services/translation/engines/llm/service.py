"""LLM translation engine using a strict JSON response contract.

The engine is provider-agnostic and never imports ``anishift.services.llm``.
Invalid model output gets bounded contract retries. Context and output limits
use deterministic binary splitting; invalid JSON is never hidden by splitting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.constants import TARGET_LANG
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.constants import RETRY_ERROR_PLACEHOLDER
from anishift.services.translation.engines.llm.json_contract import (
    JsonContractError,
    parse_translation_response,
    serialize_translation_request,
)
from anishift.services.translation.engines.llm.prompts import PromptLoader
from anishift.services.translation.errors import (
    TranslationConfigError,
    TranslationContextLengthError,
    TranslationEngineError,
)
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
    TranslationInputPolicy,
    TranslationObserver,
    TranslationStream,
)
from anishift.services.translation.types import BatchedLine

if TYPE_CHECKING:
    from anishift.services.translation.protocols import LlmCompleter

# ── Constants ────────────────────────────────────────────────────────────────

_OUTPUT_LIMIT_REASONS: Final[frozenset[str]] = frozenset(("length", "max_tokens", "max_output_tokens", "model_length"))
"""Normalized finish reasons that require adaptive splitting."""


class LlmTranslateService:
    """Translation engine prompting an injected LLM for strict JSON output."""

    __slots__ = ("_completer", "_config", "_prompts")

    def __init__(
        self,
        config: LlmTranslateConfig,
        *,
        completer: LlmCompleter,
        prompt_loader: PromptLoader | None = None,
    ) -> None:
        """Store config, completer and the selected packaged prompts."""
        if not isinstance(config, LlmTranslateConfig):
            msg = "LlmTranslateService requires LlmTranslateConfig"
            raise TypeError(msg)
        self._config = config
        self._completer = completer
        self._prompts = (prompt_loader or PromptLoader()).load(self._config.style_name)

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
        observer: TranslationObserver | None = None,
    ) -> list[BatchedLine]:
        """Translate lines with bounded batches and deterministic recovery."""
        del source_lang
        if target_lang != TARGET_LANG:
            context = ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message="The LLM translation engine supports Polish output only.",
                suggestion=f"Set target_lang to '{TARGET_LANG}'.",
            )
            raise TranslationConfigError(context=context)
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            context = ErrorContext(
                code=ErrorCode.TRANSLATION_FAILED,
                message="LLM translation batches cannot contain blank text.",
                suggestion="Remove blank subtitle entries before translation.",
            )
            raise TranslationEngineError(context=context)
        translated: list[BatchedLine] = []
        for start in range(0, len(texts), self._config.max_batch_lines):
            batch = texts[start : start + self._config.max_batch_lines]
            translated.extend(self._translate_batch(batch))
            if observer is not None:
                observer.progress(self.engine_id, min(start + len(batch), len(texts)), len(texts))
        return translated

    def _translate_batch(self, texts: list[str]) -> list[BatchedLine]:
        """Translate one bounded batch under the strict response contract."""
        request_json = serialize_translation_request(texts)
        validation_error: str | None = None
        for _attempt in range(self._config.max_contract_retries + 1):
            response = self._try_complete(request_json, validation_error=validation_error)
            if response is None or self._hit_output_limit(response):
                return self._split(texts)
            try:
                parsed = parse_translation_response(response.text, len(texts))
            except JsonContractError as error:
                validation_error = str(error)
                continue
            return self._as_lines(parsed)

        last_violation = validation_error or "No validation diagnosis was available."
        context = ErrorContext(
            code=ErrorCode.TRANSLATION_FAILED,
            message=(
                f"LLM did not return a valid translation JSON document. Last contract violation: {last_violation}"
            ),
            suggestion="Check the selected model and packaged translation prompts.",
        )
        raise TranslationEngineError(context=context)

    def _try_complete(
        self,
        request_json: str,
        *,
        validation_error: str | None,
    ) -> LlmCompletionResult | None:
        """Return a completion or None when context length requires splitting."""
        try:
            return self._complete(request_json, validation_error=validation_error)
        except TranslationContextLengthError:
            return None

    def _split(self, texts: list[str]) -> list[BatchedLine]:
        """Split a size-limited batch into stable halves or fail one line."""
        if len(texts) == 1:
            context = ErrorContext(
                code=ErrorCode.TRANSLATION_FAILED,
                message="LLM could not process a single-line translation batch.",
                suggestion="Check the selected model and translation prompt.",
            )
            raise TranslationEngineError(context=context)
        mid = len(texts) // 2
        left = self._translate_batch(texts[:mid])
        right = self._translate_batch(texts[mid:])
        return left + right

    def _complete(
        self,
        request_json: str,
        *,
        validation_error: str | None,
    ) -> LlmCompletionResult:
        """Build and execute one typed completion request."""
        user_parts: list[str] = [
            self._prompts.translation,
            self._prompts.style,
            request_json,
        ]
        if validation_error is not None:
            retry = self._prompts.retry.replace(RETRY_ERROR_PLACEHOLDER, validation_error)
            user_parts.append(retry)
        request = LlmCompletionRequest(
            system=self._prompts.system,
            user_parts=tuple(user_parts),
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
