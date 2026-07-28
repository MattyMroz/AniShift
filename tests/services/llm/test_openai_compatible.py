from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from anishift.errors import ErrorCode
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.openai_compatible import OpenaiCompatibleService
from anishift.services.llm.engines.openai_compatible.constants import SUGGESTED_MODEL_IDS
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmConfigError,
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


@dataclass(slots=True)
class FakeCompletions:
    response: object
    error: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list, init=False)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


@dataclass(slots=True)
class FakeClient:
    completions: FakeCompletions
    chat: object = field(init=False)
    close_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self.completions)

    def close(self) -> None:
        self.close_calls += 1


class FakeClientFactory:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        timeout: float,
        max_retries: int,
    ) -> FakeClient:
        self.calls.append(
            {
                "api_key": api_key,
                "base_url": base_url,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        return self.client


def _response(
    *,
    text: str | None = "translated",
    finish_reason: object = "STOP",
    model: str = "custom-model",
    cost: float | None = None,
    refusal: str | None = None,
) -> object:
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18, cost=cost)
    message = SimpleNamespace(content=text, refusal=refusal)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


def _request() -> LlmRequest:
    return LlmRequest(
        messages=(
            LlmMessage(
                role=LlmRole.SYSTEM,
                parts=(TextPart("system first"), TextPart("system second")),
            ),
            LlmMessage(
                role=LlmRole.USER,
                parts=(TextPart("user first"), TextPart("user second")),
            ),
        )
    )


def _service(
    *,
    response: object | None = None,
    error: BaseException | None = None,
    config: LlmConfig | None = None,
) -> tuple[OpenaiCompatibleService, FakeClientFactory, FakeClient, FakeCompletions]:
    completions = FakeCompletions(response=response or _response(), error=error)
    client = FakeClient(completions)
    factory = FakeClientFactory(client)
    resolved_config = config or LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="custom-model",
        base_url="http://localhost:11434/v1",
        timeout_s=12.5,
        max_retries=9,
    )
    service = OpenaiCompatibleService(resolved_config, _client_factory=factory)
    return service, factory, client, completions


def _status_error(
    error_type: type[openai.APIStatusError],
    status_code: int,
    *,
    body: object,
    headers: dict[str, str] | None = None,
) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx.Response(status_code, request=request, headers=headers)
    return error_type("provider error", response=response, body=body)


def test_openai_compatible_maps_ordered_messages_and_optional_parameters() -> None:
    config = LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="custom-model",
        base_url="http://localhost:11434/v1",
        temperature=0.4,
        top_p=0.8,
        max_output_tokens=321,
        timeout_s=12.5,
        max_retries=9,
    )
    service, factory, _, completions = _service(config=config)

    result = service.complete(_request())

    assert completions.calls == [
        {
            "messages": [
                {"role": "system", "content": "system first\nsystem second"},
                {"role": "user", "content": "user first\nuser second"},
            ],
            "model": "custom-model",
            "temperature": 0.4,
            "top_p": 0.8,
            "max_tokens": 321,
        }
    ]
    assert factory.calls[0]["base_url"] == "http://localhost:11434/v1"
    assert factory.calls[0]["timeout"] == 12.5
    assert factory.calls[0]["max_retries"] == 0
    assert factory.calls[0]["api_key"]
    assert result.text == "translated"
    assert result.engine_id == "openai_compatible"
    assert result.provider_model_id == "custom-model"
    assert result.finish_reason == "stop"
    assert result.latency_ms >= 0
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 18


def test_openai_compatible_omits_unset_generation_parameters() -> None:
    service, _, _, completions = _service()

    service.complete(_request())

    assert set(completions.calls[0]) == {"messages", "model"}


def test_openai_compatible_maps_content_filter_to_file_local_block() -> None:
    service, _, _, _ = _service(response=_response(text="", finish_reason="content_filter"))

    with pytest.raises(LlmOutputBlockedError) as error:
        service.complete(_request())

    assert error.value.context.code is ErrorCode.LLM_OUTPUT_BLOCKED


def test_openai_compatible_maps_message_refusal_to_file_local_block() -> None:
    service, _, _, _ = _service(
        response=_response(text=None, finish_reason="stop", refusal="refused"),
    )

    with pytest.raises(LlmOutputBlockedError):
        service.complete(_request())


def test_openai_compatible_reuses_and_closes_client_once() -> None:
    service, factory, client, _ = _service()

    service.complete(_request())
    service.complete(_request())
    service.close()
    service.close()

    assert len(factory.calls) == 1
    assert client.close_calls == 1
    assert service.is_available is False
    with pytest.raises(LlmRequestError):
        service.complete(_request())


def test_openai_compatible_context_manager_closes_after_error() -> None:
    service, _, client, _ = _service()

    with pytest.raises(RuntimeError), service:
        raise RuntimeError

    assert client.close_calls == 0
    with pytest.raises(LlmRequestError):
        service.complete(_request())


def test_openai_compatible_requires_base_url_but_not_api_key() -> None:
    config = LlmConfig(engine_id="openai_compatible", provider_model_id="custom-model")
    service, factory, _, _ = _service(config=config)

    assert service.is_available is False
    with pytest.raises(LlmConfigError) as error_info:
        service.complete(_request())
    assert error_info.value.context.code is ErrorCode.LLM_CONFIG_INVALID
    assert not factory.calls


def test_openai_compatible_maps_missing_sdk_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_sdk(name: str) -> object:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(importlib, "import_module", missing_sdk)
    config = LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="custom-model",
        base_url="http://localhost:11434/v1",
    )
    service = OpenaiCompatibleService(config)

    with pytest.raises(LlmProviderUnavailableError):
        service.complete(_request())


def test_openai_compatible_does_not_mask_nested_sdk_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_dependency(name: str) -> object:
        del name
        raise ModuleNotFoundError(name="sdk_dependency")

    monkeypatch.setattr(importlib, "import_module", broken_dependency)
    config = LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="custom-model",
        base_url="http://localhost:11434/v1",
    )
    service = OpenaiCompatibleService(config)

    with pytest.raises(ModuleNotFoundError) as error_info:
        service.complete(_request())
    assert error_info.value.name == "sdk_dependency"


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        pytest.param(
            _status_error(openai.AuthenticationError, 401, body={"error": {"code": "invalid_api_key"}}),
            LlmAuthError,
            id="authentication",
        ),
        pytest.param(
            _status_error(openai.PermissionDeniedError, 403, body={"error": {"code": "permission_denied"}}),
            LlmAuthError,
            id="permission",
        ),
        pytest.param(
            _status_error(openai.APIStatusError, 402, body={"error": {"code": "payment_required"}}),
            LlmPaymentError,
            id="payment",
        ),
        pytest.param(
            _status_error(openai.RateLimitError, 429, body={"error": {"code": "insufficient_quota"}}),
            LlmQuotaError,
            id="quota",
        ),
        pytest.param(
            _status_error(openai.NotFoundError, 404, body={"error": {"code": "model_not_found"}}),
            LlmModelError,
            id="model",
        ),
        pytest.param(
            _status_error(openai.NotFoundError, 404, body={"error": {"code": "not_found"}}),
            LlmRequestError,
            id="endpoint",
        ),
        pytest.param(
            _status_error(openai.BadRequestError, 400, body={"error": {"code": "context_length_exceeded"}}),
            LlmContextLengthError,
            id="context",
        ),
        pytest.param(
            _status_error(openai.InternalServerError, 503, body={"error": {"code": "unavailable"}}),
            LlmProviderUnavailableError,
            id="server",
        ),
    ],
)
def test_openai_compatible_maps_typed_status_errors(
    provider_error: BaseException,
    expected_error: type[Exception],
) -> None:
    service, _, _, _ = _service(error=provider_error)

    with pytest.raises(expected_error):
        service.complete(_request())


def test_openai_compatible_maps_rate_limit_retry_after() -> None:
    provider_error = _status_error(
        openai.RateLimitError,
        429,
        body={"error": {"code": "rate_limit_exceeded"}},
        headers={"Retry-After": "3.5"},
    )
    service, _, _, _ = _service(error=provider_error)

    with pytest.raises(LlmRateLimitError) as error_info:
        service.complete(_request())

    assert error_info.value.retry_after_s == 3.5


def test_openai_compatible_resource_exhausted_429_remains_retryable() -> None:
    provider_error = _status_error(
        openai.RateLimitError,
        429,
        body={"error": {"code": "resource_exhausted"}},
    )
    service, _, _, _ = _service(error=provider_error)

    with pytest.raises(LlmRateLimitError):
        service.complete(_request())


def test_openai_compatible_maps_timeout_and_connection_errors() -> None:
    request = httpx.Request("POST", "https://provider.invalid")
    timeout_service, _, _, _ = _service(error=openai.APITimeoutError(request=request))
    connection_service, _, _, _ = _service(error=openai.APIConnectionError(request=request))

    with pytest.raises(LlmTimeoutError):
        timeout_service.complete(_request())
    with pytest.raises(LlmProviderUnavailableError):
        connection_service.complete(_request())


def test_openai_compatible_rejects_empty_completion() -> None:
    service, _, _, _ = _service(response=_response(text=" "))

    with pytest.raises(LlmRequestError):
        service.complete(_request())


def test_openai_compatible_reports_usage_cost_when_present() -> None:
    service, _, _, _ = _service(response=_response(cost=0.0125))

    result = service.complete(_request())

    assert result.usage.reported_cost == 0.0125


def test_openai_compatible_suggestions_are_empty() -> None:
    assert SUGGESTED_MODEL_IDS == ()
