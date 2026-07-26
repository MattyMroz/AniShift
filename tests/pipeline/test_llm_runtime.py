from __future__ import annotations

import threading
from typing import ClassVar

import pytest

import anishift.pipeline.llm_runtime as runtime_module
from anishift.errors import AniShiftError, ErrorCode, ErrorContext, TransientError
from anishift.pipeline.llm_runtime import PipelineLlmRuntime
from anishift.pipeline.types import LlmSettings
from anishift.services.llm import (
    LlmAuthError,
    LlmContextLengthError,
    LlmPaymentError,
    LlmRateLimitError,
)
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.protocols import LlmAttemptObserver
from anishift.services.llm.types import LlmResponse, LlmUsage
from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.engines.llm import LlmTranslateService
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationContextLengthError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.protocols import LlmCompletionRequest, PromptIdentity


class _FakeLlmService:
    instances: ClassVar[list[_FakeLlmService]] = []
    response: ClassVar[LlmResponse | None] = None
    error: ClassVar[Exception | None] = None
    emit_transient: ClassVar[bool] = False

    def __init__(self, config: LlmConfig, *, observer: object | None = None) -> None:
        self.config = config
        self.observer = observer
        self.closed = False
        self.cancel: threading.Event | None = None
        self.__class__.instances.append(self)

    def complete(
        self,
        _request: object,
        *,
        cancel: threading.Event | None = None,
    ) -> LlmResponse:
        self.cancel = cancel
        assert isinstance(self.observer, LlmAttemptObserver)
        self.observer.before_attempt()
        if self.emit_transient:
            self.observer.on_transient_failure(LlmRateLimitError("retry"))
            if self.error is None:
                self.observer.before_attempt()
        if self.error is not None:
            if isinstance(self.error, TransientError):
                if not self.emit_transient:
                    self.observer.on_transient_failure(self.error)
            elif isinstance(self.error, AniShiftError):
                self.observer.on_fatal_failure(self.error)
            raise self.error
        assert self.response is not None
        self.observer.on_success()
        return self.response

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeLlmService.instances = []
    _FakeLlmService.error = None
    _FakeLlmService.emit_transient = False
    _FakeLlmService.response = LlmResponse(
        text="[1] tłumaczenie",
        engine_id="gemini",
        provider_model_id="model",
        finish_reason="stop",
        latency_ms=12.5,
        usage=LlmUsage(input_tokens=10, output_tokens=4, reported_cost=0.01),
    )
    monkeypatch.setattr(runtime_module, "LlmService", _FakeLlmService)


def _settings() -> LlmSettings:
    return LlmSettings(
        provider="gemini",
        model="model",
        prompt_id="anime_translation_v1",
        style_id="natural_polish_v1",
        module_ids=(),
        max_concurrency=4,
        max_retries=2,
        gemini_api_key="secret",
    )


def _request() -> LlmCompletionRequest:
    return LlmCompletionRequest(
        system="system prompt",
        user="[1] source subtitle",
        identity=PromptIdentity(
            prompt_id="anime_translation_v1",
            prompt_version=1,
            style_id="natural_polish_v1",
            fingerprint="abc",
            purpose="translation",
        ),
    )


def test_runtime_is_lazy_and_closes_created_service() -> None:
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    assert not _FakeLlmService.instances
    runtime.complete(_request())
    runtime.close()
    assert len(_FakeLlmService.instances) == 1
    assert _FakeLlmService.instances[0].closed


def test_runtime_routes_selected_provider_secret_and_cancel_event() -> None:
    cancel = threading.Event()
    runtime = PipelineLlmRuntime(_settings(), cancel=cancel)
    runtime.complete(_request())
    service = _FakeLlmService.instances[0]
    assert service.config.api_key == "secret"
    assert service.cancel is cancel


def test_runtime_collects_content_free_usage_record() -> None:
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    result = runtime.complete(_request())
    assert result.text == "[1] tłumaczenie"
    assert runtime.records[0].total_tokens == 14
    assert runtime.records[0].reported_cost == 0.01
    assert runtime.records[0].prompt_fingerprint == "abc"
    assert "source subtitle" not in repr(runtime.records)


def test_runtime_records_transport_retry_count() -> None:
    _FakeLlmService.emit_transient = True
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    runtime.complete(_request())
    assert runtime.records[0].transport_retries == 1


def test_runtime_does_not_count_exhausted_first_attempt_as_retry() -> None:
    _FakeLlmService.error = LlmRateLimitError("exhausted")
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())

    with pytest.raises(TranslationRateLimitError):
        runtime.complete(_request())

    assert runtime.records[0].transport_retries == 0


@pytest.mark.parametrize(
    ("llm_error", "expected"),
    [
        (LlmAuthError("auth"), TranslationAuthError),
        (LlmRateLimitError("rate"), TranslationRateLimitError),
        (LlmPaymentError("payment"), TranslationQuotaError),
        (LlmContextLengthError("context"), TranslationContextLengthError),
    ],
)
def test_runtime_maps_typed_llm_errors(
    llm_error: Exception,
    expected: type[Exception],
) -> None:
    _FakeLlmService.error = llm_error
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    with pytest.raises(expected):
        runtime.complete(_request())
    assert runtime.records[0].error_code


def test_runtime_preserves_structured_error_code() -> None:
    context = ErrorContext(code=ErrorCode.LLM_AUTH_FAILED, message="safe")
    _FakeLlmService.error = LlmAuthError(context=context)
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    with pytest.raises(TranslationAuthError) as error:
        runtime.complete(_request())
    assert error.value.context is context


def test_engine_factory_builds_llm_translation_adapter() -> None:
    runtime = PipelineLlmRuntime(_settings(), cancel=threading.Event())
    engine = runtime.engine_factory()("llm", TranslationConfig(engine="llm"))
    assert isinstance(engine, LlmTranslateService)
