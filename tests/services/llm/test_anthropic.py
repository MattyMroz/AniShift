from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines import create_engine, suggested_model_ids
from anishift.services.llm.engines.anthropic.constants import DEFAULT_MAX_OUTPUT_TOKENS
from anishift.services.llm.engines.anthropic.service import AnthropicService
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmContextLengthError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart


class FakeMessages:
    def __init__(self, *, response: object | None = None, error: BaseException | None = None) -> None:
        self.response: object = response or _anthropic_response()
        self.error: BaseException | None = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAnthropicClient:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages: FakeMessages = messages
        self.close_calls: int = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeAnthropicFactory:
    def __init__(self, client: FakeAnthropicClient) -> None:
        self.client: FakeAnthropicClient = client
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        api_key: str,
        timeout: float,
        max_retries: int,
    ) -> FakeAnthropicClient:
        self.calls.append(
            {
                "api_key": api_key,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        return self.client


def test_anthropic_registry_and_suggestions_are_lazy() -> None:
    sys.modules.pop("anthropic", None)

    engine = create_engine(_anthropic_config())

    assert isinstance(engine, AnthropicService)
    assert suggested_model_ids("anthropic") == (
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-opus-5",
    )
    assert "anthropic" not in sys.modules


def test_anthropic_maps_ordered_messages_and_normalizes_response() -> None:
    messages = FakeMessages()
    client = FakeAnthropicClient(messages)
    factory = FakeAnthropicFactory(client)
    service = AnthropicService(_anthropic_config(), _client_factory=factory)

    assert factory.calls == []

    response = service.complete(_conversation_request())
    kwargs = messages.calls[0]

    assert factory.calls == [{"api_key": "anthropic-key", "timeout": 12.5, "max_retries": 0}]
    assert kwargs["model"] == "custom-claude"
    assert kwargs["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert kwargs["system"] == [{"type": "text", "text": "Translate naturally."}]
    assert kwargs["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "First"}, {"type": "text", "text": "Second"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Previous"}]},
        {"role": "user", "content": [{"type": "text", "text": "Continue"}]},
    ]
    assert response.text == "Translated text"
    assert response.engine_id == "anthropic"
    assert response.provider_model_id == "claude-returned-model"
    assert response.finish_reason == "end_turn"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 18
    assert response.usage.reported_cost is None


def test_anthropic_sends_explicit_generation_parameters() -> None:
    messages = FakeMessages()
    client = FakeAnthropicClient(messages)
    config = LlmConfig(
        engine_id="anthropic",
        provider_model_id="custom-claude",
        api_key="anthropic-key",
        temperature=0.4,
        top_p=0.8,
        max_output_tokens=1234,
    )
    service = AnthropicService(config, _client_factory=FakeAnthropicFactory(client))

    service.complete(_conversation_request())

    kwargs = messages.calls[0]
    assert kwargs["temperature"] == 0.4
    assert kwargs["top_p"] == 0.8
    assert kwargs["max_tokens"] == 1234


def test_anthropic_maps_refusal_stop_to_file_local_block() -> None:
    response = _anthropic_response(
        content=[SimpleNamespace(type="text", text="I cannot comply")],
        stop_reason="refusal",
    )
    messages = FakeMessages(response=response)
    service = AnthropicService(
        _anthropic_config(),
        _client_factory=FakeAnthropicFactory(FakeAnthropicClient(messages)),
    )

    with pytest.raises(LlmOutputBlockedError):
        service.complete(_conversation_request())


def test_anthropic_reuses_and_closes_client_once() -> None:
    messages = FakeMessages()
    client = FakeAnthropicClient(messages)
    factory = FakeAnthropicFactory(client)
    service = AnthropicService(_anthropic_config(), _client_factory=factory)

    service.complete(_conversation_request())
    service.complete(_conversation_request())
    service.close()
    service.close()

    assert len(factory.calls) == 1
    assert len(messages.calls) == 2
    assert client.close_calls == 1
    assert service.is_available is False


def test_anthropic_missing_key_fails_before_client_creation() -> None:
    client = FakeAnthropicClient(FakeMessages())
    factory = FakeAnthropicFactory(client)
    config = LlmConfig(engine_id="anthropic", provider_model_id="custom-claude")
    service = AnthropicService(config, _client_factory=factory)

    with pytest.raises(LlmAuthError):
        service.complete(_conversation_request())

    assert factory.calls == []


def test_anthropic_missing_sdk_maps_to_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_module = cast("Any", importlib.import_module("anishift.services.llm.engines.anthropic.service"))
    real_import = importlib.import_module

    def missing_sdk(module_name: str) -> object:
        if module_name == "anthropic":
            raise ImportError("missing Anthropic SDK", name="anthropic")
        return real_import(module_name)

    monkeypatch.setattr(provider_module.importlib, "import_module", missing_sdk)
    service = AnthropicService(_anthropic_config())

    with pytest.raises(LlmProviderUnavailableError):
        service.complete(_conversation_request())


def test_anthropic_empty_text_response_is_request_error() -> None:
    response = _anthropic_response(content=[SimpleNamespace(type="tool_use")])
    messages = FakeMessages(response=response)
    service = AnthropicService(
        _anthropic_config(),
        _client_factory=FakeAnthropicFactory(FakeAnthropicClient(messages)),
    )

    with pytest.raises(LlmRequestError):
        service.complete(_conversation_request())


def test_anthropic_rejects_unsupported_content_part() -> None:
    unsupported_part = cast("Any", SimpleNamespace(kind="image"))
    request = LlmRequest(messages=(LlmMessage(role=LlmRole.USER, parts=(unsupported_part,)),))
    service = AnthropicService(
        _anthropic_config(),
        _client_factory=FakeAnthropicFactory(FakeAnthropicClient(FakeMessages())),
    )

    with pytest.raises(LlmRequestError):
        service.complete(request)


@pytest.mark.parametrize(
    ("error_name", "status_code", "expected_error"),
    [
        ("AuthenticationError", 401, LlmAuthError),
        ("PermissionDeniedError", 403, LlmAuthError),
        ("NotFoundError", 404, LlmModelError),
        ("RequestTooLargeError", 413, LlmContextLengthError),
        ("InternalServerError", 500, LlmProviderUnavailableError),
        ("OverloadedError", 529, LlmProviderUnavailableError),
        ("APIStatusError", 400, LlmRequestError),
    ],
)
def test_anthropic_maps_typed_status_errors(
    error_name: str,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    error = _anthropic_status_error(error_name, status_code=status_code)
    service = _anthropic_service_raising(error)

    with pytest.raises(expected_error):
        service.complete(_conversation_request())


def test_anthropic_maps_structured_payment_marker_before_rate_limit() -> None:
    error = _anthropic_status_error(
        "RateLimitError",
        status_code=429,
        body={"error": {"type": "billing_hard_limit_reached"}},
    )
    service = _anthropic_service_raising(error)

    with pytest.raises(LlmPaymentError):
        service.complete(_conversation_request())


def test_anthropic_rate_limit_preserves_retry_after() -> None:
    error = _anthropic_status_error("RateLimitError", status_code=429, retry_after="3.5")
    service = _anthropic_service_raising(error)

    with pytest.raises(LlmRateLimitError) as exc_info:
        service.complete(_conversation_request())

    assert exc_info.value.retry_after_s == 3.5


@pytest.mark.parametrize(
    ("error_kind", "expected_error"),
    [
        pytest.param("timeout", LlmTimeoutError, id="timeout"),
        pytest.param("connection", LlmProviderUnavailableError, id="connection"),
    ],
)
def test_anthropic_maps_transport_errors(
    error_kind: str,
    expected_error: type[Exception],
) -> None:
    error: BaseException = _anthropic_timeout_error() if error_kind == "timeout" else _anthropic_connection_error()
    service = _anthropic_service_raising(error)

    with pytest.raises(expected_error):
        service.complete(_conversation_request())


def _anthropic_config() -> LlmConfig:
    return LlmConfig(
        engine_id="anthropic",
        provider_model_id="custom-claude",
        api_key="anthropic-key",
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


def _anthropic_response(
    *,
    content: list[object] | None = None,
    stop_reason: str = "END_TURN",
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content or [SimpleNamespace(type="text", text="Translated text")],
        model="claude-returned-model",
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
    )


def _anthropic_service_raising(error: BaseException) -> AnthropicService:
    messages = FakeMessages(error=error)
    client = FakeAnthropicClient(messages)
    return AnthropicService(_anthropic_config(), _client_factory=FakeAnthropicFactory(client))


def _anthropic_status_error(
    error_name: str,
    *,
    status_code: int,
    body: object | None = None,
    retry_after: str | None = None,
) -> BaseException:
    sdk = importlib.import_module("anthropic")
    error_type = cast("Callable[..., BaseException]", getattr(sdk, error_name))
    headers: dict[str, str] = {"retry-after": retry_after} if retry_after is not None else {}
    response = httpx.Response(
        status_code,
        headers=headers,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    return error_type("provider failure", response=response, body=body or {})


def _anthropic_timeout_error() -> BaseException:
    sdk = importlib.import_module("anthropic")
    error_type = cast("Callable[..., BaseException]", sdk.APITimeoutError)
    return error_type(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def _anthropic_connection_error() -> BaseException:
    sdk = importlib.import_module("anthropic")
    error_type = cast("Callable[..., BaseException]", sdk.APIConnectionError)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return error_type(message="connection failed", request=request)
