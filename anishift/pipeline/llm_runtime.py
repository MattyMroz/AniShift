"""Composition adapter between provider-neutral LLM and translation domains."""

from __future__ import annotations

import threading
from types import TracebackType
from typing import Self

from anishift.errors import AniShiftError, TransientError
from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmConfig,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
    LlmMessage,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequest,
    LlmRequestError,
    LlmRole,
    LlmService,
    LlmTimeoutError,
    TextPart,
)
from anishift.services.llm.protocols import LlmAttemptObserver
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines import create_engine
from anishift.services.translation.engines.llm import LlmTranslateConfig, LlmTranslateService
from anishift.services.translation.engines.llm.prompts import PromptRegistry
from anishift.services.translation.engines.llm.prompts.types import PromptContext
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationContextLengthError,
    TranslationEngineError,
    TranslationError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.protocols import (
    LlmCompletionRequest,
    LlmCompletionResult,
    TranslationEngine,
    TranslationEngineFactory,
)

from .types import LlmCallRecord, LlmSettings

__all__ = ["PipelineLlmRuntime"]


class PipelineLlmRuntime:
    """Own one worker-local LLM facade, translation adapter, and call records."""

    __slots__ = (
        "_attempt_observer",
        "_cancel",
        "_closed",
        "_service",
        "_settings",
        "_title",
        "records",
    )

    def __init__(
        self,
        settings: LlmSettings,
        *,
        cancel: threading.Event,
        observer: LlmAttemptObserver | None = None,
        title: str = "",
    ) -> None:
        """Store lightweight settings and defer provider construction."""
        self._settings = settings
        self._title = title
        self._cancel = cancel
        self._attempt_observer = _CountingObserver(observer)
        self._service: LlmService | None = None
        self._closed = False
        self.records: list[LlmCallRecord] = []

    def complete(self, request: LlmCompletionRequest) -> LlmCompletionResult:
        """Adapt one translation-owned completion into the LLM domain."""
        llm_request = LlmRequest(
            messages=(
                LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart(request.system),)),
                LlmMessage(role=LlmRole.USER, parts=(TextPart(request.user),)),
            )
        )
        attempts_before = self._attempt_observer.attempts
        try:
            response = self._get_service().complete(llm_request, cancel=self._cancel)
        except LlmError as error:
            retries = max(0, self._attempt_observer.attempts - attempts_before - 1)
            self.records.append(self._failure_record(request, error, retries=retries))
            self._raise_translation_error(error)
        retries = max(0, self._attempt_observer.attempts - attempts_before - 1)
        self.records.append(
            LlmCallRecord(
                purpose=request.identity.purpose,
                provider=response.engine_id,
                model=response.provider_model_id,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
                reported_cost=response.usage.reported_cost,
                latency_ms=response.latency_ms,
                finish_reason=response.finish_reason,
                prompt_id=request.identity.prompt_id,
                prompt_version=request.identity.prompt_version,
                style_id=request.identity.style_id,
                prompt_fingerprint=request.identity.fingerprint,
                transport_retries=retries,
                omitted_context_items=request.omitted_context_items,
            )
        )
        return LlmCompletionResult(text=response.text, finish_reason=response.finish_reason)

    def engine_factory(self) -> TranslationEngineFactory:
        """Return a file-local factory wiring LLM and registry translation engines."""

        def build(engine_id: str, config: TranslationConfig) -> TranslationEngine:
            if engine_id == "llm":
                llm_config = LlmTranslateConfig(
                    prompt_id=self._settings.prompt_id,
                    style_id=self._settings.style_id,
                    module_ids=self._settings.module_ids,
                    context=PromptContext(title=self._title),
                )
                return LlmTranslateService(
                    llm_config,
                    completer=self,
                    prompt_registry=PromptRegistry(
                        custom_root=self._settings.prompt_root,
                    ),
                )
            engine_config = TranslationConfig(
                engine=engine_id,
                source_lang=config.source_lang,
                batch_size=config.batch_size,
                max_retries=config.max_retries,
                api_key=config.api_key,
            )
            return create_engine(engine_config)

        return build

    def close(self) -> None:
        """Close the worker-local provider facade once."""
        if self._closed:
            return
        self._closed = True
        if self._service is not None:
            self._service.close()

    def __enter__(self) -> Self:
        """Enter the worker-local lifecycle."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the provider facade on every exit path."""
        self.close()

    def _get_service(self) -> LlmService:
        """Build the worker-local LLM facade only for the first completion."""
        if self._service is None:
            settings = self._settings
            base_url = settings.openai_compatible_base_url or None
            self._service = LlmService(
                LlmConfig(
                    engine_id=settings.provider,
                    provider_model_id=settings.model,
                    api_key=settings.api_key(),
                    base_url=base_url,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    max_output_tokens=settings.max_output_tokens,
                    timeout_s=settings.timeout_s,
                    max_retries=settings.max_retries,
                ),
                observer=self._attempt_observer,
            )
        return self._service

    def _failure_record(
        self,
        request: LlmCompletionRequest,
        error: LlmError,
        *,
        retries: int,
    ) -> LlmCallRecord:
        """Build content-free metadata for a failed logical completion."""
        return LlmCallRecord(
            purpose=request.identity.purpose,
            provider=self._settings.provider,
            model=self._settings.model,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            reported_cost=None,
            latency_ms=None,
            finish_reason="",
            prompt_id=request.identity.prompt_id,
            prompt_version=request.identity.prompt_version,
            style_id=request.identity.style_id,
            prompt_fingerprint=request.identity.fingerprint,
            transport_retries=retries,
            omitted_context_items=request.omitted_context_items,
            error_code=error.context.code.value,
        )

    @staticmethod
    def _raise_translation_error(error: LlmError) -> None:
        """Map a typed LLM failure to the corresponding translation error."""
        context = error.context
        if isinstance(error, LlmCancelledError):
            raise TranslationError(context=context) from error
        if isinstance(error, LlmContextLengthError):
            raise TranslationContextLengthError(context=context) from error
        if isinstance(error, LlmAuthError):
            raise TranslationAuthError(context=context) from error
        if isinstance(error, LlmRateLimitError):
            raise TranslationRateLimitError(context=context) from error
        if isinstance(error, (LlmQuotaError, LlmPaymentError)):
            raise TranslationQuotaError(context=context) from error
        if isinstance(
            error,
            (
                LlmTimeoutError,
                LlmProviderUnavailableError,
                LlmConfigError,
                LlmModelError,
                LlmOutputBlockedError,
                LlmRequestError,
            ),
        ):
            raise TranslationEngineError(context=context) from error
        raise TranslationEngineError(context=context) from error


class _CountingObserver:
    """Count transient attempts while forwarding scheduler notifications."""

    __slots__ = ("_delegate", "attempts")

    def __init__(self, delegate: LlmAttemptObserver | None) -> None:
        """Store an optional shared observer."""
        self._delegate = delegate
        self.attempts = 0

    def before_attempt(self) -> None:
        """Forward permission to start the next provider attempt."""
        if self._delegate is not None:
            self._delegate.before_attempt()
        self.attempts += 1

    def on_transient_failure(self, error: TransientError) -> None:
        """Forward one retryable provider failure."""
        if self._delegate is not None:
            self._delegate.on_transient_failure(error)

    def on_success(self) -> None:
        """Forward one successful provider attempt."""
        if self._delegate is not None:
            self._delegate.on_success()

    def on_fatal_failure(self, error: AniShiftError) -> None:
        """Forward one non-retryable provider failure."""
        if self._delegate is not None:
            self._delegate.on_fatal_failure(error)
