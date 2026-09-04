"""LLM translation engine using a strict numbered-line response contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.translation.constants import TARGET_LANG
from anishift.services.translation.engines.llm.config import LlmTranslateConfig
from anishift.services.translation.engines.llm.constants import RETRY_ERROR_PLACEHOLDER
from anishift.services.translation.engines.llm.line_contract import LINE_PATTERN, parse_response, serialize_request
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
    from collections.abc import Mapping, Sequence

    from anishift.services.translation.protocols import LlmCompleter

# ── Constants ────────────────────────────────────────────────────────────────

_OUTPUT_LIMIT_REASONS: Final[frozenset[str]] = frozenset(("length", "max_tokens", "max_output_tokens", "model_length"))
"""Normalized finish reasons that require adaptive splitting."""


class _StreamProgress:
    """Count closed numbered lines within the current provider attempt."""

    __slots__ = ("_base", "_buffer", "_done", "_engine_id", "_expected", "_observer", "_seen", "_total")

    def __init__(
        self,
        observer: TranslationObserver | None,
        engine_id: str,
        *,
        done: int,
        total: int,
    ) -> None:
        """Bind one batch to its observer and the file-wide line counters."""
        self._observer: TranslationObserver | None = observer
        self._engine_id: str = engine_id
        self._done: int = done
        self._total: int = total
        self._base: int = 0
        self._buffer: str = ""
        self._seen: set[int] = set()
        self._expected: set[int] = set()

    def restart(self, trusted: int, pending: tuple[int, ...]) -> None:
        """Begin one attempt, keeping the lines earlier attempts already earned."""
        self._base = trusted
        self._expected = set(pending)

    def reset_transport(self) -> None:
        """Discard provisional text when a transport attempt restarts."""
        self._buffer = ""
        self._seen.clear()
        self._report()

    def branch(self, offset: int) -> _StreamProgress:
        """Keep the file offset when a size-limited batch splits."""
        return _StreamProgress(self._observer, self._engine_id, done=self._done + offset, total=self._total)

    def retry(self, attempt: int, maximum: int) -> None:
        """Expose a numbered-response repair as a distinct retry."""
        if self._observer is not None:
            self._observer.retry(self._engine_id, attempt, maximum, "response_contract")

    def consume(self, delta: str) -> None:
        """Fold one arriving text delta into the reported line count."""
        if self._observer is None:
            return
        parts: list[str] = (self._buffer + delta).split("\n")
        self._buffer = parts.pop()
        for line in parts:
            match = LINE_PATTERN.match(line.strip())
            if match is None:
                continue
            number: int = int(match.group(1))
            if (
                number in self._expected
                and number not in self._seen
                and parse_response(line, (number,)).violation is None
            ):
                self._seen.add(number)
                self._report()

    def _report(self) -> None:
        """Reserve completion for a validated full response."""
        if self._observer is not None:
            completed: int = min(self._done + self._base + len(self._seen), self._total - 1)
            self._observer.progress(self._engine_id, completed, self._total)


class LlmTranslateService:
    """Translation engine prompting an injected LLM for numbered output lines."""

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
        limit: int = self._config.max_batch_lines or len(texts)
        done: int = 0
        for start in range(0, len(texts), limit):
            batch = texts[start : start + limit]
            reporter = _StreamProgress(observer, self.engine_id, done=done, total=len(texts))
            translated.extend(self._translate_batch(batch, reporter))
            done += len(batch)
            if observer is not None:
                observer.progress(self.engine_id, done, len(texts))
        return translated

    def _translate_batch(self, texts: list[str], reporter: _StreamProgress) -> list[BatchedLine]:
        """Translate one bounded batch, repairing only the numbers that failed."""
        expected: tuple[int, ...] = tuple(range(len(texts)))
        results: dict[int, str] = {}
        pending: tuple[int, ...] = expected
        validation_error: str | None = None
        for attempt in range(self._config.max_contract_retries + 1):
            request_body = serialize_request([(number, texts[number]) for number in pending])
            if attempt:
                reporter.retry(attempt + 1, self._config.max_contract_retries + 1)
            reporter.restart(len(results), pending)
            response = self._try_complete(request_body, reporter, validation_error=validation_error)
            if response is None or self._hit_output_limit(response):
                return self._split(texts, reporter)
            parsed = parse_response(response.text, pending)
            results.update(parsed.entries)
            pending = tuple(number for number in expected if number not in results)
            if not pending:
                return self._as_lines(expected, results)
            if parsed.violation is not None:
                validation_error = parsed.violation.message

        last_violation = validation_error or "No validation diagnosis was available."
        context = ErrorContext(
            code=ErrorCode.TRANSLATION_FAILED,
            message=(f"LLM did not return valid numbered translation lines. Last contract violation: {last_violation}"),
            suggestion="Check the selected model and packaged translation prompts.",
        )
        raise TranslationEngineError(context=context)

    def _try_complete(
        self,
        request_body: str,
        reporter: _StreamProgress,
        *,
        validation_error: str | None,
    ) -> LlmCompletionResult | None:
        """Return a completion or None when context length requires splitting."""
        try:
            return self._complete(request_body, reporter, validation_error=validation_error)
        except TranslationContextLengthError:
            return None

    def _split(self, texts: list[str], reporter: _StreamProgress) -> list[BatchedLine]:
        """Split a size-limited batch into stable halves or fail one line."""
        if len(texts) == 1:
            context = ErrorContext(
                code=ErrorCode.TRANSLATION_FAILED,
                message="LLM could not process a single-line translation batch.",
                suggestion="Check the selected model and translation prompt.",
            )
            raise TranslationEngineError(context=context)
        mid = len(texts) // 2
        left = self._translate_batch(texts[:mid], reporter.branch(0))
        right = self._translate_batch(texts[mid:], reporter.branch(mid))
        return left + right

    def _complete(
        self,
        request_body: str,
        reporter: _StreamProgress,
        *,
        validation_error: str | None,
    ) -> LlmCompletionResult:
        """Build and execute one typed completion request."""
        user_parts: list[str] = [
            self._prompts.translation,
            self._prompts.style,
            request_body,
        ]
        if validation_error is not None:
            retry = self._prompts.retry.replace(RETRY_ERROR_PLACEHOLDER, validation_error)
            user_parts.append(retry)
        request = LlmCompletionRequest(
            system=self._prompts.system,
            user_parts=tuple(user_parts),
        )
        return self._completer.complete(request, on_text=reporter.consume, on_start=reporter.reset_transport)

    @staticmethod
    def _as_lines(expected: Sequence[int], results: Mapping[int, str]) -> list[BatchedLine]:
        """Wrap trusted translations as engine results, in request order."""
        return [BatchedLine(text=results[number]) for number in expected]

    @staticmethod
    def _hit_output_limit(response: LlmCompletionResult) -> bool:
        """Return whether the provider stopped because of an output limit."""
        return response.finish_reason.strip().lower() in _OUTPUT_LIMIT_REASONS


__all__ = ["LlmTranslateService"]
