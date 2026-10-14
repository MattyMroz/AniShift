from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import replace
from typing import cast

import httpx
import pytest
from loguru import logger as loguru_logger

from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmConfig,
    LlmConfigError,
    LlmEngine,
    LlmMessage,
    LlmOutputBlockedError,
    LlmRequest,
    LlmRequestError,
    LlmResponse,
    LlmRole,
    TextPart,
    create_engine,
)
from anishift.services.llm._retry import retry_transient
from anishift.services.llm.engines.palantir.auth import resolve_palantir_token
from anishift.services.llm.engines.palantir.errors import PalantirResponseDefect
from anishift.services.llm.engines.palantir.normalize import normalize_palantir_response
from anishift.services.llm.engines.palantir.service import PalantirService
from anishift.services.llm.errors import LlmProviderUnavailableError, LlmRateLimitError
from anishift.services.llm.wire_protocol import ModelProtocol

_TOKEN = "palantir-token-sentinel-deadbeef"  # noqa: S105
_BODY_SENTINEL = "palantir-body-sentinel-hunter2"
_ENROLLMENT = "https://example.palantirfoundry.com"
_OPENAI_ROUTE = "/api/v2/llm/proxy/openai/v1"
_XAI_ROUTE = "/api/v2/llm/proxy/xai/v1"
_ANTHROPIC_ROUTE = "/api/v2/llm/proxy/anthropic/v1"
_GOOGLE_ROUTE = "/api/v2/llm/proxy/google/v1"
_IMPORT_PROBE = (
    "import json, sys\n"
    "before = set(sys.modules)\n"
    "import {module}\n"
    "print(json.dumps(sorted(set(sys.modules) - before)))\n"
)


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)


def _config(
    *,
    protocol: ModelProtocol = ModelProtocol.OPENAI_RESPONSES,
    provider_path: str = _OPENAI_ROUTE,
    provider_model_id: str = "gpt-main-5",
    max_output_tokens: int | None = 256,
    api_key: str = _TOKEN,
) -> LlmConfig:
    return LlmConfig(
        engine_id="palantir",
        provider_model_id=provider_model_id,
        api_key=api_key,
        alias={
            ModelProtocol.OPENAI_RESPONSES: "foundry/gpt-5.6-sol",
            ModelProtocol.XAI_RESPONSES: "foundry-xai/grok-4.6",
            ModelProtocol.ANTHROPIC_MESSAGES: "foundry-anthropic/claude-sonnet-5",
            ModelProtocol.GOOGLE_GENERATE: "foundry-google/gemini-3.8-flash",
        }[protocol],
        provider_id="foundry-openai",
        protocol=protocol,
        base_url=f"{_ENROLLMENT}{provider_path}",
        temperature=0.2,
        top_p=0.9,
        max_output_tokens=max_output_tokens,
    )


def _request() -> LlmRequest:
    return LlmRequest(
        messages=(
            LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart(text="You translate subtitles."),)),
            LlmMessage(role=LlmRole.USER, parts=(TextPart(text="First line."), TextPart(text="Second line."))),
            LlmMessage(role=LlmRole.ASSISTANT, parts=(TextPart(text="Ready."),)),
        ),
    )


def _engine(handler: httpx.MockTransport | None, config: LlmConfig | None = None) -> PalantirService:
    client = httpx.Client(transport=handler) if handler is not None else None
    return PalantirService(config or _config(), client=client)


def _recording_transport(response: httpx.Response, sink: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sink.append(request)
        return response

    return httpx.MockTransport(handler)


def _modules_added_by_importing(module: str) -> list[str]:
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _IMPORT_PROBE.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return cast("list[str]", json.loads(completed.stdout))


@pytest.mark.integration
def test_openai_responses_maps_the_request_and_normalizes_the_response() -> None:
    captured: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "model": "gpt-main-5",
            "system_fingerprint": _BODY_SENTINEL,
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Przetłumaczony tekst."}]}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        },
    )
    engine = _engine(_recording_transport(response, captured))

    result = engine.complete(_request())

    sent = captured[0]
    body = json.loads(sent.content)
    assert str(sent.url) == f"{_ENROLLMENT}{_OPENAI_ROUTE}/responses"
    assert sent.headers["authorization"] == f"Bearer {_TOKEN}"
    assert body["model"] == "gpt-main-5"
    assert body["input"][1] == {
        "role": "user",
        "content": [{"type": "input_text", "text": "First line.\nSecond line."}],
    }
    assert body["max_output_tokens"] == 256
    assert result.text == "Przetłumaczony tekst."
    assert result.engine_id == "palantir"
    assert result.provider_model_id == "gpt-main-5"
    assert result.finish_reason == "completed"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.total_tokens == 15


def test_xai_responses_maps_the_request_and_normalizes_the_response() -> None:
    captured: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hidden"}]},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Odpowiedź xAI."}],
                },
            ],
            "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        },
    )
    config = _config(protocol=ModelProtocol.XAI_RESPONSES, provider_path=_XAI_ROUTE, provider_model_id="grok-4")
    engine = _engine(_recording_transport(response, captured), config)

    result = engine.complete(_request())

    body = json.loads(captured[0].content)
    assert str(captured[0].url) == f"{_ENROLLMENT}{_XAI_ROUTE}/responses"
    assert body["stream"] is False
    assert body["max_output_tokens"] == 256
    assert result.text == "Odpowiedź xAI."
    assert result.finish_reason == "completed"
    assert result.usage.input_tokens == 4
    assert result.usage.output_tokens == 2
    assert result.usage.total_tokens == 6


def test_anthropic_messages_maps_the_request_and_normalizes_the_response() -> None:
    captured: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": "Odpowiedź."}, {"type": "thinking", "text": _BODY_SENTINEL}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 8, "output_tokens": 4},
        },
    )
    config = _config(
        protocol=ModelProtocol.ANTHROPIC_MESSAGES,
        provider_path=_ANTHROPIC_ROUTE,
        provider_model_id="claude-sonnet-5",
    )
    engine = _engine(_recording_transport(response, captured), config)

    result = engine.complete(_request())

    sent = captured[0]
    body = json.loads(sent.content)
    assert str(sent.url) == f"{_ENROLLMENT}{_ANTHROPIC_ROUTE}/messages"
    assert sent.headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == [{"type": "text", "text": "You translate subtitles."}]
    assert result.text == "Odpowiedź."
    assert result.finish_reason == "end_turn"
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 12


def test_google_generate_maps_the_request_and_normalizes_the_response() -> None:
    captured: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "Cześć"}, {"text": " świat"}]},
                    "finishReason": "STOP",
                },
            ],
            "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 3, "totalTokenCount": 9},
        },
    )
    config = _config(
        protocol=ModelProtocol.GOOGLE_GENERATE,
        provider_path=_GOOGLE_ROUTE,
        provider_model_id="ri.models.main:gemini-3-pro",
    )
    engine = _engine(_recording_transport(response, captured), config)

    result = engine.complete(_request())

    sent = captured[0]
    body = json.loads(sent.content)
    assert str(sent.url) == (f"{_ENROLLMENT}{_GOOGLE_ROUTE}/models/ri.models.main%3Agemini-3-pro:generateContent")
    assert body["systemInstruction"] == {"parts": [{"text": "You translate subtitles."}]}
    assert result.text == "Cześć świat"
    assert result.finish_reason == "stop"
    assert result.usage.input_tokens == 6
    assert result.usage.output_tokens == 3
    assert result.usage.total_tokens == 9


def test_google_generate_streams_sse_chunks_and_assembles_the_response() -> None:
    captured: list[httpx.Request] = []
    chunks = [
        {"candidates": [{"content": {"role": "model", "parts": [{"text": '{"translations":'}]}}]},
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": "[]}"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 3, "totalTokenCount": 9},
        },
    ]
    stream_body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    response = httpx.Response(200, text=stream_body, headers={"content-type": "text/event-stream"})
    config = _config(
        protocol=ModelProtocol.GOOGLE_GENERATE,
        provider_path=_GOOGLE_ROUTE,
        provider_model_id="ri.models.main:gemini-3.7-flash",
    )
    engine = _engine(_recording_transport(response, captured), config)

    result = engine.complete_stream(_request())

    assert str(captured[0].url) == (
        f"{_ENROLLMENT}{_GOOGLE_ROUTE}/models/ri.models.main%3Agemini-3.7-flash:streamGenerateContent?alt=sse"
    )
    assert result.text == '{"translations":[]}'
    assert result.finish_reason == "stop"
    assert result.usage.total_tokens == 9


@pytest.mark.integration
def test_responses_stream_reports_deltas_and_uses_terminal_response() -> None:
    captured: list[httpx.Request] = []
    chunks: list[dict[str, object]] = [
        {"type": "response.reasoning_text.delta", "delta": "hidden"},
        {"type": "response.output_text.delta", "delta": "[0] Pierwsza"},
        {"type": "response.output_text.delta", "delta": "\n[1] Druga"},
        {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "Terminal text"}]}],
                "usage": {"input_tokens": 6, "output_tokens": 3, "total_tokens": 9},
            },
        },
    ]
    arrived: list[str] = []

    class _Stream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield f"data: {json.dumps(chunks[0])}\n\n".encode()
            yield f"data: {json.dumps(chunks[1])}\n\n".encode()
            assert arrived == ["[0] Pierwsza"]
            yield f"data: {json.dumps(chunks[2])}\n\n".encode()
            assert arrived == ["[0] Pierwsza", "\n[1] Druga"]
            yield f"data: {json.dumps(chunks[3])}\n\n".encode()

    response: httpx.Response = httpx.Response(200, stream=_Stream(), headers={"content-type": "text/event-stream"})
    with _engine(_recording_transport(response, captured)) as engine:
        result: LlmResponse = engine.complete_stream(_request(), on_text=arrived.append)

    assert str(captured[0].url) == f"{_ENROLLMENT}{_OPENAI_ROUTE}/responses"
    assert json.loads(captured[0].content)["stream"] is True
    assert result.text == "Terminal text"
    assert result.finish_reason == "completed"
    assert result.usage.total_tokens == 9


@pytest.mark.integration
@pytest.mark.parametrize("protocol", [ModelProtocol.OPENAI_RESPONSES, ModelProtocol.GOOGLE_GENERATE])
def test_stream_without_terminal_reason_rejects_partial_translation(protocol: ModelProtocol) -> None:
    chunk: dict[str, object] = (
        {"type": "response.output_text.delta", "delta": "[0] Urwane zdanie"}
        if protocol is ModelProtocol.OPENAI_RESPONSES
        else {"candidates": [{"content": {"parts": [{"text": "[0] Urwane zdanie"}]}}]}
    )
    response = httpx.Response(200, text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
    with (
        _engine(_recording_transport(response, []), _config(protocol=protocol)) as engine,
        pytest.raises(LlmProviderUnavailableError),
    ):
        engine.complete_stream(_request())


@pytest.mark.integration
def test_stream_error_event_is_not_silently_ignored() -> None:
    chunks: list[dict[str, object]] = [
        {"candidates": [{"content": {"parts": [{"text": "[0] Partial"}]}}]},
        {"error": {"code": 429, "message": _BODY_SENTINEL}},
    ]
    response = httpx.Response(200, text="".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks))
    engine: PalantirService = _engine(
        _recording_transport(response, []), _config(protocol=ModelProtocol.GOOGLE_GENERATE)
    )
    try:
        with pytest.raises(LlmRateLimitError) as raised:
            engine.complete_stream(_request())
        assert _BODY_SENTINEL not in str(raised.value)
    finally:
        engine.close()


@pytest.mark.integration
@pytest.mark.parametrize("text", ["[0] Urwane", ""])
@pytest.mark.parametrize("protocol", [ModelProtocol.OPENAI_RESPONSES, ModelProtocol.XAI_RESPONSES])
def test_responses_token_limit_preserves_split_signal(text: str, protocol: ModelProtocol) -> None:
    payload: dict[str, object] = {
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]
        if text
        else [{"type": "reasoning", "summary": []}],
    }
    response: httpx.Response = (
        httpx.Response(200, text=f"data: {json.dumps({'type': 'response.incomplete', 'response': payload})}\n\n")
        if protocol is ModelProtocol.OPENAI_RESPONSES
        else httpx.Response(200, json=payload)
    )
    with _engine(_recording_transport(response, []), _config(protocol=protocol)) as engine:
        result: LlmResponse = engine.complete_stream(_request())
    assert result.finish_reason == "max_output_tokens"
    assert result.text == text


@pytest.mark.integration
@pytest.mark.parametrize("event_type", ["response.failed", "error"])
def test_responses_stream_reports_generation_failure(event_type: str) -> None:
    event: dict[str, object] = (
        {"type": "error", "code": "server_error", "message": _BODY_SENTINEL}
        if event_type == "error"
        else {
            "type": "response.failed",
            "response": {"status": "failed", "error": {"code": "server_error", "message": _BODY_SENTINEL}},
        }
    )
    response: httpx.Response = httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")
    with _engine(_recording_transport(response, [])) as engine, pytest.raises(LlmProviderUnavailableError) as failure:
        engine.complete_stream(_request())
    assert _BODY_SENTINEL not in repr(failure.value.context)


@pytest.mark.integration
@pytest.mark.parametrize("stream", [False, True])
def test_google_filters_thought_parts(*, stream: bool) -> None:
    payload: dict[str, object] = {
        "candidates": [
            {
                "content": {"parts": [{"text": _BODY_SENTINEL, "thought": True}, {"text": "Visible"}]},
                "finishReason": "STOP",
            }
        ],
    }
    response: httpx.Response = (
        httpx.Response(200, text=f"data: {json.dumps(payload)}\n\n") if stream else httpx.Response(200, json=payload)
    )
    arrived: list[str] = []
    with _engine(_recording_transport(response, []), _config(protocol=ModelProtocol.GOOGLE_GENERATE)) as engine:
        result: LlmResponse = (
            engine.complete_stream(_request(), on_text=arrived.append) if stream else engine.complete(_request())
        )
    assert result.text == "Visible"
    assert arrived == (["Visible"] if stream else [])


@pytest.mark.unit
def test_palantir_rejects_unknown_alias() -> None:
    with pytest.raises(LlmConfigError) as rejected:
        PalantirService(replace(_config(), alias="foundry/absent"))
    assert rejected.value.context.details["field"] == "alias"


@pytest.mark.parametrize("status", ["incomplete", "failed", "in_progress", "queued"])
def test_xai_does_not_accept_unfinished_status(status: str) -> None:
    payload: dict[str, object] = {
        "status": status,
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "[0] Partial"}]}],
    }
    with pytest.raises(LlmRequestError):
        normalize_palantir_response(
            ModelProtocol.XAI_RESPONSES,
            payload,
            alias="test",
            engine_id="palantir",
            provider_model_id="test",
            latency_ms=0,
        )


def test_a_protocol_without_a_stream_shape_uses_the_normal_path_and_never_reports() -> None:
    captured: list[httpx.Request] = []
    response = httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": "Gotowe."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 2, "output_tokens": 1},
        },
    )
    config = _config(protocol=ModelProtocol.ANTHROPIC_MESSAGES, provider_path=_ANTHROPIC_ROUTE)
    engine = _engine(_recording_transport(response, captured), config)
    arrived: list[str] = []

    result = engine.complete_stream(_request(), on_text=arrived.append)

    assert result.text == "Gotowe."
    assert arrived == []
    assert "stream" not in json.loads(captured[0].content)


def test_google_stream_rejects_a_malformed_sse_event() -> None:
    response = httpx.Response(200, text="data: not-json\n\n", headers={"content-type": "text/event-stream"})
    config = _config(protocol=ModelProtocol.GOOGLE_GENERATE, provider_path=_GOOGLE_ROUTE)
    engine = _engine(httpx.MockTransport(lambda request: response), config)

    with pytest.raises(LlmRequestError) as rejected:
        engine.complete_stream(_request())

    assert rejected.value.context.details["defect"] == PalantirResponseDefect.UNREADABLE_BODY.value


@pytest.mark.integration
def test_a_stream_shaped_body_is_rejected_as_a_typed_defect_without_leaking_chunks() -> None:
    captured: list[str] = []
    handler_id = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    stream_body = (
        f'data: {{"type":"response.output_text.delta","delta":"{_BODY_SENTINEL}"}}\n\n'
        'data: {"type":"response.output_text.delta","delta":" tail"}\n\n'
        "data: [DONE]\n\n"
    )
    response = httpx.Response(200, text=stream_body, headers={"content-type": "text/event-stream"})
    engine = _engine(httpx.MockTransport(lambda request: response))
    try:
        with pytest.raises(LlmRequestError) as rejected:
            engine.complete(_request())
    finally:
        loguru_logger.remove(handler_id)

    error = rejected.value
    assert error.context.details["defect"] == PalantirResponseDefect.UNREADABLE_BODY.value
    assert "streamed or non-JSON body" in error.context.suggestion
    surfaces = [str(error), repr(error), repr(error.context), *captured]
    assert captured
    assert all(_BODY_SENTINEL not in surface for surface in surfaces)
    assert all(_TOKEN not in surface for surface in surfaces)


@pytest.mark.unit
def test_an_empty_completion_is_a_typed_defect() -> None:
    payload: dict[str, object] = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "   "}]}],
    }
    with pytest.raises(LlmRequestError) as rejected:
        normalize_palantir_response(
            ModelProtocol.OPENAI_RESPONSES,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert rejected.value.context.details["defect"] == PalantirResponseDefect.EMPTY_TEXT.value


@pytest.mark.unit
def test_a_missing_choice_is_a_typed_defect() -> None:
    with pytest.raises(LlmRequestError) as rejected:
        normalize_palantir_response(
            ModelProtocol.OPENAI_RESPONSES,
            {"status": "completed", "output": []},
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert rejected.value.context.details["defect"] == PalantirResponseDefect.MISSING_CHOICE.value


@pytest.mark.unit
@pytest.mark.parametrize("payload", [[], {"status": "completed", "output": ["not-a-mapping"]}])
def test_a_malformed_shape_is_a_typed_defect(payload: object) -> None:
    with pytest.raises(LlmRequestError) as rejected:
        normalize_palantir_response(
            ModelProtocol.OPENAI_RESPONSES,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert rejected.value.context.details["defect"] == PalantirResponseDefect.UNEXPECTED_SHAPE.value


@pytest.mark.unit
def test_a_responses_content_filter_finish_reason_is_a_blocked_error() -> None:
    payload: dict[str, object] = {
        "status": "incomplete",
        "incomplete_details": {"reason": "content_filter"},
        "output": [],
    }
    with pytest.raises(LlmOutputBlockedError) as blocked:
        normalize_palantir_response(
            ModelProtocol.OPENAI_RESPONSES,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert blocked.value.context.details["finish_reason"] == "content_filter"


def test_a_google_prompt_block_is_a_blocked_error() -> None:
    payload = {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
    with pytest.raises(LlmOutputBlockedError) as blocked:
        normalize_palantir_response(
            ModelProtocol.GOOGLE_GENERATE,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gemini-3-pro",
            latency_ms=1.0,
        )

    assert blocked.value.context.details["finish_reason"] == "safety"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("protocol", "payload", "finish_reason"),
    [
        pytest.param(
            ModelProtocol.OPENAI_RESPONSES,
            {"status": "incomplete", "incomplete_details": {"reason": "content_filter"}, "output": None},
            "content_filter",
            id="openai-null-content",
        ),
        pytest.param(
            ModelProtocol.GOOGLE_GENERATE,
            {"candidates": [{"finishReason": "SAFETY"}], "usageMetadata": {"promptTokenCount": 5}},
            "safety",
            id="google-candidate-without-content",
        ),
        pytest.param(
            ModelProtocol.ANTHROPIC_MESSAGES,
            {"content": [], "stop_reason": "refusal", "usage": {"input_tokens": 3, "output_tokens": 0}},
            "refusal",
            id="anthropic-empty-content",
        ),
    ],
)
def test_a_blocked_completion_wins_over_a_text_shape_defect(
    protocol: ModelProtocol,
    payload: object,
    finish_reason: str,
) -> None:
    with pytest.raises(LlmOutputBlockedError) as blocked:
        normalize_palantir_response(
            protocol,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert blocked.value.context.details["finish_reason"] == finish_reason
    assert "defect" not in blocked.value.context.details


@pytest.mark.unit
@pytest.mark.parametrize(
    ("protocol", "payload", "defect"),
    [
        pytest.param(
            ModelProtocol.OPENAI_RESPONSES,
            {"status": "completed", "output": [{"type": "message", "content": None}]},
            PalantirResponseDefect.UNEXPECTED_SHAPE,
            id="openai-null-content-without-block",
        ),
        pytest.param(
            ModelProtocol.GOOGLE_GENERATE,
            {"candidates": [{"finishReason": "STOP"}]},
            PalantirResponseDefect.UNEXPECTED_SHAPE,
            id="google-candidate-without-content-or-block",
        ),
        pytest.param(
            ModelProtocol.ANTHROPIC_MESSAGES,
            {"content": [], "stop_reason": "end_turn"},
            PalantirResponseDefect.MISSING_CHOICE,
            id="anthropic-empty-content-without-block",
        ),
    ],
)
def test_a_malformed_body_without_a_blocking_signal_keeps_its_typed_defect(
    protocol: ModelProtocol,
    payload: object,
    defect: PalantirResponseDefect,
) -> None:
    with pytest.raises(LlmRequestError) as rejected:
        normalize_palantir_response(
            protocol,
            payload,
            alias="foundry/main",
            engine_id="palantir",
            provider_model_id="gpt-main-5",
            latency_ms=1.0,
        )

    assert rejected.value.context.details["defect"] == defect.value
    assert "finish_reason" not in rejected.value.context.details


@pytest.mark.integration
def test_the_token_reaches_the_engine_through_the_config_not_the_environment() -> None:
    assert resolve_palantir_token() == ""
    captured: list[httpx.Request] = []
    response: httpx.Response = httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
        },
    )
    engine = _engine(_recording_transport(response, captured), _config(api_key=_TOKEN))

    engine.complete(_request())

    assert captured[0].headers["authorization"] == f"Bearer {_TOKEN}"


def test_a_blank_api_key_raises_auth_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent without a token")

    with pytest.raises(LlmAuthError):
        PalantirService(_config(api_key=""), client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_llm_config_repr_hides_the_palantir_token() -> None:
    config = _config(api_key=_TOKEN)

    assert _TOKEN not in repr(config)
    assert _TOKEN not in str(config)
    assert config.api_key == _TOKEN


def test_the_registry_creates_the_palantir_engine() -> None:
    engine = create_engine(_config())

    assert isinstance(engine, LlmEngine)
    assert engine.engine_id == "palantir"


def test_importing_the_engine_registry_loads_no_http_client_and_no_palantir_service() -> None:
    added = _modules_added_by_importing("anishift.services.llm.engines")

    heavy = [name for name in added if name.split(".")[0] in {"httpx", "httpcore"}]
    assert "anishift.services.llm.engines" in added
    assert heavy == []
    assert "anishift.services.llm.engines.palantir.service" not in added


def test_close_is_idempotent_and_closes_the_owned_client_once() -> None:
    class _CloseSpy:
        def __init__(self) -> None:
            self.closes = 0

        def close(self) -> None:
            self.closes += 1

    spy = _CloseSpy()
    engine = PalantirService(_config(), client=cast("httpx.Client", spy))

    engine.close()
    engine.close()

    assert spy.closes == 1
    assert engine.is_available is False
    with pytest.raises(LlmRequestError):
        engine.complete(_request())


@pytest.mark.integration
def test_cancellation_before_an_attempt_rejects_the_operation() -> None:
    response: httpx.Response = httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
        },
    )
    engine = _engine(httpx.MockTransport(lambda request: response))
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(LlmCancelledError):
        retry_transient(lambda: engine.complete(_request()), max_retries=0, cancel=cancel)


@pytest.mark.integration
def test_a_provider_success_completed_after_cancel_is_rejected() -> None:
    cancel = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        cancel.set()
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            },
        )

    engine = _engine(httpx.MockTransport(handler))

    with pytest.raises(LlmCancelledError):
        retry_transient(lambda: engine.complete(_request()), max_retries=0, cancel=cancel)


def test_cancellation_between_attempts_stops_before_a_second_attempt() -> None:
    cancel = threading.Event()
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        cancel.set()
        raise httpx.ConnectError("enrollment down")

    engine = _engine(httpx.MockTransport(handler))

    with pytest.raises(LlmCancelledError):
        retry_transient(lambda: engine.complete(_request()), max_retries=3, cancel=cancel)
    assert len(calls) == 1


@pytest.mark.integration
def test_the_success_path_never_leaks_the_token_or_provider_body_fields() -> None:
    captured: list[str] = []
    handler_id = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    response = httpx.Response(
        200,
        json={
            "model": "gpt-main-5",
            "system_fingerprint": _BODY_SENTINEL,
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Bezpieczny tekst."}]}],
            "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
        },
    )
    engine = _engine(httpx.MockTransport(lambda request: response))
    try:
        result: LlmResponse = engine.complete(_request())
    finally:
        loguru_logger.remove(handler_id)

    surfaces = [repr(result), str(result), *captured]
    assert captured
    assert result.text == "Bezpieczny tekst."
    assert all(_TOKEN not in surface for surface in surfaces)
    assert all(_BODY_SENTINEL not in surface for surface in surfaces)
    assert all("Bearer" not in surface for surface in captured)
