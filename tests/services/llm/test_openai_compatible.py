from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from chat_stream_helpers import FakeChatStream, chat_chunk, chat_stream

from anishift.errors import ErrorCode
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.deepseek import DeepseekService
from anishift.services.llm.engines.openai import OpenaiService
from anishift.services.llm.engines.openai_compatible import OpenaiCompatibleService
from anishift.services.llm.engines.openrouter import OpenrouterService
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmCancelledError,
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
from anishift.services.llm.protocols import StreamingLlmEngine
from anishift.services.llm.types import FilePart, LlmMessage, LlmRequest, LlmRole, TextPart


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
    return chat_stream(text=text, finish_reason=finish_reason, model=model, usage=usage, refusal=refusal)


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
    service_type: type[
        OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService
    ] = OpenaiCompatibleService,
    response: object | None = None,
    error: BaseException | None = None,
    config: LlmConfig | None = None,
) -> tuple[
    OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService,
    FakeClientFactory,
    FakeClient,
    FakeCompletions,
]:
    completions = FakeCompletions(response=response or _response(), error=error)
    client = FakeClient(completions)
    factory = FakeClientFactory(client)
    resolved_config = config or LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="custom-model",
        base_url="http://localhost:11434/v1",
        timeout_s=12.5,
    )
    service: OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService = service_type(
        resolved_config, _client_factory=factory
    )
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service_type", "engine_id", "max_tokens_parameter"),
    [
        (OpenaiCompatibleService, "openai_compatible", "max_tokens"),
        (OpenaiService, "openai", "max_completion_tokens"),
        (OpenrouterService, "openrouter", "max_tokens"),
        (DeepseekService, "deepseek", "max_tokens"),
    ],
)
def test_openai_compatible_maps_ordered_messages_and_optional_parameters(
    service_type: type[OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService],
    engine_id: str,
    max_tokens_parameter: str,
) -> None:
    config: LlmConfig = LlmConfig(
        engine_id=engine_id,
        provider_model_id="custom-model",
        api_keys=("test-key",),
        base_url="http://localhost:11434/v1",
        temperature=0.4,
        top_p=0.8,
        max_output_tokens=321,
        timeout_s=12.5,
    )
    service, factory, _, completions = _service(config=config, service_type=service_type)

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
            max_tokens_parameter: 321,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    ]
    assert factory.calls[0]["base_url"] == "http://localhost:11434/v1"
    assert factory.calls[0]["timeout"] == 12.5
    assert factory.calls[0]["max_retries"] == 0
    assert factory.calls[0]["api_key"]
    assert result.text == "translated"
    assert result.engine_id == engine_id
    assert result.provider_model_id == "custom-model"
    assert result.finish_reason == "stop"
    assert result.latency_ms >= 0
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 18


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service_type", "engine_id", "media_type", "name", "file_block"),
    [
        (
            OpenaiService,
            "openai",
            "image/png",
            "",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmlsZQ=="}},
        ),
        (
            OpenrouterService,
            "openrouter",
            "image/png",
            "",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmlsZQ=="}},
        ),
        (
            OpenaiCompatibleService,
            "openai_compatible",
            "image/png",
            "",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmlsZQ=="}},
        ),
        (
            DeepseekService,
            "deepseek",
            "image/png",
            "",
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmlsZQ=="}},
        ),
        (
            OpenaiService,
            "openai",
            "application/pdf",
            "",
            {"type": "file", "file": {"filename": "document.pdf", "file_data": "data:application/pdf;base64,ZmlsZQ=="}},
        ),
        (
            OpenrouterService,
            "openrouter",
            "application/pdf",
            "chapter.pdf",
            {"type": "file", "file": {"filename": "chapter.pdf", "file_data": "data:application/pdf;base64,ZmlsZQ=="}},
        ),
    ],
)
def test_chat_provider_maps_mixed_file_content(
    service_type: type[OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService],
    engine_id: str,
    media_type: str,
    name: str,
    file_block: dict[str, object],
) -> None:
    config: LlmConfig = LlmConfig(
        engine_id=engine_id,
        provider_model_id="custom-model",
        api_keys=("test-key",),
        base_url="https://provider.invalid/v1",
    )
    service, _, _, completions = _service(config=config, service_type=service_type)
    request: LlmRequest = LlmRequest(
        messages=(
            LlmMessage(
                role=LlmRole.USER,
                parts=(
                    TextPart("First"),
                    TextPart("Second"),
                    FilePart(media_type=media_type, data=b"file", name=name),
                    TextPart("Third"),
                    TextPart("Fourth"),
                ),
            ),
        ),
    )

    service.complete(request)

    assert completions.calls[0]["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "First\nSecond"},
                file_block,
                {"type": "text", "text": "Third\nFourth"},
            ],
        },
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service_type", "engine_id", "media_type"),
    [
        (OpenaiService, "openai", "audio/mpeg"),
        (OpenaiService, "openai", "video/mp4"),
        (OpenrouterService, "openrouter", "audio/mpeg"),
        (OpenrouterService, "openrouter", "video/mp4"),
        (OpenaiCompatibleService, "openai_compatible", "application/pdf"),
        (OpenaiCompatibleService, "openai_compatible", "audio/mpeg"),
        (OpenaiCompatibleService, "openai_compatible", "video/mp4"),
        (DeepseekService, "deepseek", "application/pdf"),
        (DeepseekService, "deepseek", "audio/mpeg"),
        (DeepseekService, "deepseek", "video/mp4"),
    ],
)
def test_chat_provider_rejects_unsupported_file_before_sdk_call(
    service_type: type[OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService],
    engine_id: str,
    media_type: str,
) -> None:
    config: LlmConfig = LlmConfig(
        engine_id=engine_id,
        provider_model_id="custom-model",
        api_keys=("test-key",),
        base_url="https://provider.invalid/v1",
    )
    service, factory, _, completions = _service(config=config, service_type=service_type)
    request: LlmRequest = LlmRequest(
        messages=(
            LlmMessage(role=LlmRole.USER, parts=(TextPart("Describe"), FilePart(media_type=media_type, data=b"file"))),
        ),
    )

    with pytest.raises(LlmRequestError, match=f"{engine_id}.*{media_type}"):
        service.complete(request)
    assert completions.calls == []
    assert factory.calls == []


def test_openai_compatible_omits_unset_generation_parameters() -> None:
    service, _, _, completions = _service()

    service.complete(_request())

    assert set(completions.calls[0]) == {"messages", "model", "stream", "stream_options"}


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


@pytest.mark.parametrize("service_type", [OpenaiCompatibleService, OpenaiService, OpenrouterService, DeepseekService])
def test_chat_provider_streams_answer_deltas_in_arrival_order(
    service_type: type[OpenaiCompatibleService | OpenaiService | OpenrouterService | DeepseekService],
) -> None:
    engine_id: str = {
        OpenaiCompatibleService: "openai_compatible",
        OpenaiService: "openai",
        OpenrouterService: "openrouter",
        DeepseekService: "deepseek",
    }[service_type]
    config = LlmConfig(
        engine_id=engine_id,
        provider_model_id="custom-model",
        api_keys=("test-key",),
        base_url="http://localhost:11434/v1",
    )
    service, _, _, completions = _service(
        config=config, service_type=service_type, response=_response(text="[0] raz\n[1] dwa\n")
    )
    seen: list[str] = []

    result = service.complete_stream(_request(), on_text=seen.append)

    assert isinstance(service, StreamingLlmEngine)
    assert seen == ["[0] raz\n", "[1] dwa\n"]
    assert result.text == "[0] raz\n[1] dwa\n"
    assert result.usage.output_tokens == 7
    assert completions.calls[0]["stream"] is True


def test_openai_compatible_answer_without_content_reports_no_text() -> None:
    stream = FakeChatStream((chat_chunk(content=None), chat_chunk(content="", finish_reason="stop")))
    service, _, _, _ = _service(response=stream)
    seen: list[str] = []

    with pytest.raises(LlmRequestError):
        service.complete_stream(_request(), on_text=seen.append)

    assert seen == []
    assert stream.closed


def test_openai_compatible_maps_an_interrupted_stream_to_transient_errors() -> None:
    request = httpx.Request("POST", "https://provider.invalid")
    dropped, _, _, _ = _service(response=chat_stream(error=httpx.RemoteProtocolError("closed", request=request)))
    stalled, _, _, _ = _service(response=chat_stream(error=httpx.ReadTimeout("stalled", request=request)))

    with pytest.raises(LlmProviderUnavailableError):
        dropped.complete(_request())
    with pytest.raises(LlmTimeoutError):
        stalled.complete(_request())


def test_openai_compatible_closes_the_stream_when_the_observer_stops_it() -> None:
    stream = chat_stream(text="[0] raz\n[1] dwa\n")
    service, _, _, _ = _service(response=stream)

    def stop(delta: str) -> None:
        raise LlmCancelledError(f"stopped after {delta!r}")

    with pytest.raises(LlmCancelledError):
        service.complete_stream(_request(), on_text=stop)

    assert stream.closed
