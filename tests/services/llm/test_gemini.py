from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines import create_engine, suggested_model_ids
from anishift.services.llm.engines.gemini.service import GeminiService
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmContextLengthError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart


class FakeModels:
    def __init__(self, *, response: object | None = None, error: BaseException | None = None) -> None:
        self.response: object = response or _gemini_response()
        self.error: BaseException | None = error
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeGeminiClient:
    def __init__(self, models: FakeModels) -> None:
        self.models: FakeModels = models
        self.close_calls: int = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeGeminiFactory:
    def __init__(self, client: FakeGeminiClient) -> None:
        self.client: FakeGeminiClient = client
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        api_key: str,
        http_options: object,
    ) -> FakeGeminiClient:
        self.calls.append({"api_key": api_key, "http_options": http_options})
        return self.client


def test_gemini_registry_and_suggestions_are_lazy() -> None:
    for module_name in ("google.genai", "google.genai.types", "google.genai.errors"):
        sys.modules.pop(module_name, None)

    engine = create_engine(_gemini_config())

    assert isinstance(engine, GeminiService)
    assert suggested_model_ids("gemini") == (
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
    )
    assert "google.genai" not in sys.modules


def test_gemini_maps_ordered_contents_and_normalizes_response() -> None:
    models = FakeModels()
    client = FakeGeminiClient(models)
    factory = FakeGeminiFactory(client)
    service = GeminiService(_gemini_config(), _client_factory=factory)

    assert factory.calls == []

    response = service.complete(_conversation_request())
    kwargs = models.calls[0]
    http_options = cast("Any", factory.calls[0]["http_options"])
    config = cast("Any", kwargs["config"])
    contents = cast("list[Any]", kwargs["contents"])

    assert factory.calls[0]["api_key"] == "gemini-key"
    assert http_options.timeout == 12500
    assert http_options.retry_options.attempts == 1
    assert kwargs["model"] == "custom-gemini"
    assert [part.text for part in config.system_instruction] == ["Translate naturally."]
    assert config.temperature is None
    assert config.top_p is None
    assert config.max_output_tokens is None
    assert [content.role for content in contents] == ["user", "model", "user"]
    assert [[part.text for part in content.parts] for content in contents] == [
        ["First", "Second"],
        ["Previous"],
        ["Continue"],
    ]
    assert response.text == "Translated text"
    assert response.engine_id == "gemini"
    assert response.provider_model_id == "gemini-returned-model"
    assert response.finish_reason == "stop"
    assert response.usage.input_tokens == 13
    assert response.usage.output_tokens == 8
    assert response.usage.total_tokens == 21
    assert response.usage.reported_cost is None


def test_gemini_maps_safety_finish_to_file_local_block() -> None:
    response = _gemini_response(parts=[])
    response.candidates[0].finish_reason = "SAFETY"
    models = FakeModels(response=response)
    service = GeminiService(
        _gemini_config(),
        _client_factory=FakeGeminiFactory(FakeGeminiClient(models)),
    )

    with pytest.raises(LlmOutputBlockedError) as error:
        service.complete(_conversation_request())

    assert error.value.context.code is ErrorCode.LLM_OUTPUT_BLOCKED


@pytest.mark.parametrize("block_reason", ["SPII", "JAILBREAK", "MODEL_ARMOR", "OTHER"])
def test_gemini_maps_prompt_feedback_block_without_candidates(block_reason: str) -> None:
    response = SimpleNamespace(
        candidates=[],
        prompt_feedback=SimpleNamespace(block_reason=block_reason),
    )
    models = FakeModels(response=response)
    service = GeminiService(
        _gemini_config(),
        _client_factory=FakeGeminiFactory(FakeGeminiClient(models)),
    )

    with pytest.raises(LlmOutputBlockedError):
        service.complete(_conversation_request())


def test_gemini_sends_only_explicit_generation_parameters() -> None:
    models = FakeModels()
    client = FakeGeminiClient(models)
    config = LlmConfig(
        engine_id="gemini",
        provider_model_id="custom-gemini",
        api_key="gemini-key",
        temperature=0.3,
        top_p=0.7,
        max_output_tokens=2345,
    )
    service = GeminiService(config, _client_factory=FakeGeminiFactory(client))

    service.complete(_conversation_request())

    generate_config = models.calls[0]["config"]
    assert generate_config.temperature == 0.3
    assert generate_config.top_p == 0.7
    assert generate_config.max_output_tokens == 2345


def test_gemini_reuses_and_closes_client_once() -> None:
    models = FakeModels()
    client = FakeGeminiClient(models)
    factory = FakeGeminiFactory(client)
    service = GeminiService(_gemini_config(), _client_factory=factory)

    service.complete(_conversation_request())
    service.complete(_conversation_request())
    service.close()
    service.close()

    assert len(factory.calls) == 1
    assert len(models.calls) == 2
    assert client.close_calls == 1
    assert service.is_available is False


def test_gemini_missing_key_fails_before_client_creation() -> None:
    client = FakeGeminiClient(FakeModels())
    factory = FakeGeminiFactory(client)
    config = LlmConfig(engine_id="gemini", provider_model_id="custom-gemini")
    service = GeminiService(config, _client_factory=factory)

    with pytest.raises(LlmAuthError):
        service.complete(_conversation_request())

    assert factory.calls == []


def test_gemini_missing_sdk_maps_to_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_module = cast("Any", importlib.import_module("anishift.services.llm.engines.gemini.service"))
    real_import = importlib.import_module

    def missing_sdk(module_name: str) -> object:
        if module_name.startswith("google.genai"):
            raise ImportError("missing Google Gen AI SDK", name=module_name)
        return real_import(module_name)

    monkeypatch.setattr(provider_module.importlib, "import_module", missing_sdk)
    service = GeminiService(_gemini_config())

    with pytest.raises(LlmProviderUnavailableError):
        service.complete(_conversation_request())


def test_gemini_empty_text_candidate_is_request_error() -> None:
    response = _gemini_response(parts=[SimpleNamespace(function_call=object())])
    models = FakeModels(response=response)
    service = GeminiService(
        _gemini_config(),
        _client_factory=FakeGeminiFactory(FakeGeminiClient(models)),
    )

    with pytest.raises(LlmRequestError):
        service.complete(_conversation_request())


def test_gemini_rejects_unsupported_content_part() -> None:
    unsupported_part = cast("Any", SimpleNamespace(kind="image"))
    request = LlmRequest(messages=(LlmMessage(role=LlmRole.USER, parts=(unsupported_part,)),))
    service = GeminiService(
        _gemini_config(),
        _client_factory=FakeGeminiFactory(FakeGeminiClient(FakeModels())),
    )

    with pytest.raises(LlmRequestError):
        service.complete(request)


@pytest.mark.parametrize(
    ("code", "status", "expected_error"),
    [
        pytest.param(401, "UNAUTHENTICATED", LlmAuthError, id="auth"),
        pytest.param(403, "PERMISSION_DENIED", LlmAuthError, id="permission"),
        pytest.param(404, "NOT_FOUND", LlmModelError, id="model"),
        pytest.param(400, "INVALID_ARGUMENT", LlmRequestError, id="request"),
        pytest.param(500, "INTERNAL", LlmProviderUnavailableError, id="internal"),
        pytest.param(503, "UNAVAILABLE", LlmProviderUnavailableError, id="unavailable"),
        pytest.param(504, "GATEWAY_TIMEOUT", LlmProviderUnavailableError, id="gateway-timeout"),
        pytest.param(408, "DEADLINE_EXCEEDED", LlmTimeoutError, id="deadline"),
    ],
)
def test_gemini_maps_typed_sdk_errors(
    code: int,
    status: str,
    expected_error: type[Exception],
) -> None:
    error: BaseException = _gemini_error(code, status)
    service = _gemini_service_raising(error)

    with pytest.raises(expected_error):
        service.complete(_conversation_request())


def test_gemini_maps_structured_payment_marker() -> None:
    error = _gemini_error(
        400,
        "FAILED_PRECONDITION",
        details=[{"reason": "BILLING_ACCOUNT_REQUIRED"}],
    )
    service = _gemini_service_raising(error)

    with pytest.raises(LlmPaymentError):
        service.complete(_conversation_request())


def test_gemini_maps_structured_context_length_marker() -> None:
    error = _gemini_error(
        400,
        "INVALID_ARGUMENT",
        details=[{"reason": "CONTEXT_LENGTH_EXCEEDED"}],
    )
    service = _gemini_service_raising(error)

    with pytest.raises(LlmContextLengthError):
        service.complete(_conversation_request())


def test_gemini_maps_structured_daily_quota_before_rate_limit() -> None:
    error = _gemini_error(
        429,
        "RESOURCE_EXHAUSTED",
        details=[
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerDay"}],
            }
        ],
    )
    service = _gemini_service_raising(error)

    with pytest.raises(LlmQuotaError):
        service.complete(_conversation_request())


def test_gemini_rate_limit_preserves_retry_after() -> None:
    response = httpx.Response(
        429,
        headers={"retry-after": "4.25"},
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com"),
    )
    error = _gemini_error(429, "RESOURCE_EXHAUSTED", response=response)
    service = _gemini_service_raising(error)

    with pytest.raises(LlmRateLimitError) as exc_info:
        service.complete(_conversation_request())

    assert exc_info.value.retry_after_s == 4.25


def test_gemini_per_minute_quota_failure_remains_retryable() -> None:
    error = _gemini_error(
        429,
        "RESOURCE_EXHAUSTED",
        details=[
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaId": "GenerateRequestsPerMinute"}],
            }
        ],
    )
    service = _gemini_service_raising(error)

    with pytest.raises(LlmRateLimitError):
        service.complete(_conversation_request())


@pytest.mark.parametrize(
    ("error_kind", "expected_error"),
    [
        pytest.param("timeout", LlmTimeoutError, id="timeout"),
        pytest.param("connection", LlmProviderUnavailableError, id="connection"),
    ],
)
def test_gemini_maps_httpx_transport_errors(
    error_kind: str,
    expected_error: type[Exception],
) -> None:
    error: BaseException = _httpx_timeout_error() if error_kind == "timeout" else _httpx_network_error()
    service = _gemini_service_raising(error)

    with pytest.raises(expected_error):
        service.complete(_conversation_request())


def _gemini_config() -> LlmConfig:
    return LlmConfig(
        engine_id="gemini",
        provider_model_id="custom-gemini",
        api_key="gemini-key",
        timeout_s=12.5,
    )


def _conversation_request() -> LlmRequest:
    return LlmRequest(
        messages=(
            LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart("Translate naturally."),)),
            LlmMessage(role=LlmRole.USER, parts=(TextPart("First"), TextPart("Second"))),
            LlmMessage(role=LlmRole.ASSISTANT, parts=(TextPart("Previous"),)),
            LlmMessage(role=LlmRole.USER, parts=(TextPart("Continue"),)),
        )
    )


def _gemini_response(*, parts: list[object] | None = None) -> SimpleNamespace:
    candidate = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text="Translated text")] if parts is None else parts,
        ),
        finish_reason="STOP",
    )
    return SimpleNamespace(
        candidates=[candidate],
        model_version="gemini-returned-model",
        usage_metadata=SimpleNamespace(
            prompt_token_count=13,
            candidates_token_count=8,
            total_token_count=21,
        ),
    )


def _gemini_service_raising(error: BaseException) -> GeminiService:
    models = FakeModels(error=error)
    client = FakeGeminiClient(models)
    return GeminiService(_gemini_config(), _client_factory=FakeGeminiFactory(client))


def _gemini_error(
    code: int,
    status: str,
    *,
    details: list[object] | None = None,
    response: httpx.Response | None = None,
) -> BaseException:
    errors_module = importlib.import_module("google.genai.errors")
    error_name: str = "ServerError" if code >= 500 else "ClientError"
    error_type = cast("Callable[..., BaseException]", getattr(errors_module, error_name))
    body: dict[str, object] = {
        "error": {
            "code": code,
            "status": status,
            "message": "provider failure",
            "details": details or [],
        }
    }
    return error_type(code, body, response=response)


def _httpx_timeout_error() -> BaseException:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    return httpx.ReadTimeout("timed out", request=request)


def _httpx_network_error() -> BaseException:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    return httpx.ConnectError("connection failed", request=request)
