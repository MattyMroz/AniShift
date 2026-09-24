from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from anishift.services.llm import (
    FilePart,
    LlmConfig,
    LlmConfigError,
    LlmMessage,
    LlmRequest,
    LlmRequestError,
    LlmRole,
    TextPart,
)
from anishift.services.llm.engines.palantir.service import PalantirService
from anishift.services.llm.types import LlmContentPart
from anishift.services.llm.wire_protocol import ModelProtocol

_MODELS: dict[ModelProtocol, tuple[str, str, str]] = {
    ModelProtocol.OPENAI_RESPONSES: ("foundry/gpt-5.6-sol", "foundry-openai", "openai"),
    ModelProtocol.XAI_RESPONSES: ("foundry-xai/grok-4.6", "foundry-xai", "xai"),
    ModelProtocol.ANTHROPIC_MESSAGES: ("foundry-anthropic/claude-opus-5", "foundry-anthropic", "anthropic"),
    ModelProtocol.GOOGLE_GENERATE: ("foundry-google/gemini-3.8-flash", "foundry-google", "google"),
}
_SUCCESS: dict[ModelProtocol, dict[str, object]] = {
    ModelProtocol.OPENAI_RESPONSES: {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
    },
    ModelProtocol.XAI_RESPONSES: {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
    },
    ModelProtocol.ANTHROPIC_MESSAGES: {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"},
    ModelProtocol.GOOGLE_GENERATE: {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]},
}


def _config(protocol: ModelProtocol, variant: str | None = None) -> LlmConfig:
    alias: str
    provider_id: str
    route: str
    alias, provider_id, route = _MODELS[protocol]
    return LlmConfig(
        engine_id="palantir",
        alias=alias,
        provider_id=provider_id,
        provider_model_id=alias.split("/")[1],
        protocol=protocol,
        base_url=f"https://example.invalid/api/v2/llm/proxy/{route}/v1",
        api_key="synthetic-token",
        reasoning_variant=variant,
        temperature=0.3,
        top_p=0.8,
        max_output_tokens=256,
    )


def _send(config: LlmConfig, request: LlmRequest, captured: list[httpx.Request]) -> dict[str, Any]:
    def handler(sent: httpx.Request) -> httpx.Response:
        captured.append(sent)
        assert config.protocol is not None
        return httpx.Response(200, json=_SUCCESS[config.protocol])

    with PalantirService(config, client=httpx.Client(transport=httpx.MockTransport(handler))) as engine:
        engine.complete(request)
    body: dict[str, Any] = json.loads(captured[0].content)
    return body


def _request(parts: tuple[LlmContentPart, ...] = (TextPart("First"),)) -> LlmRequest:
    return LlmRequest((LlmMessage(LlmRole.USER, parts),))


@pytest.mark.integration
@pytest.mark.parametrize("protocol", list(ModelProtocol))
@pytest.mark.parametrize("media_type", [None, "image/png", "application/pdf", "audio/mpeg", "video/mp4"])
def test_palantir_request_maps_protocol_and_content(protocol: ModelProtocol, media_type: str | None) -> None:
    captured: list[httpx.Request] = []
    parts: tuple[LlmContentPart, ...] = (TextPart("First"),)
    if media_type is not None:
        parts += (FilePart(media_type, b"file"),)
    unsupported: bool = (
        media_type in {"audio/mpeg", "video/mp4"} and protocol is not ModelProtocol.GOOGLE_GENERATE
    ) or (media_type == "application/pdf" and protocol is ModelProtocol.XAI_RESPONSES)
    if unsupported:
        with pytest.raises(LlmRequestError) as rejected:
            _send(_config(protocol), _request(parts), captured)
        assert "palantir" in str(rejected.value)
        assert media_type is not None
        assert media_type in str(rejected.value)
        assert captured == []
        return
    body: dict[str, Any] = _send(_config(protocol), _request(parts), captured)
    if protocol is ModelProtocol.GOOGLE_GENERATE:
        expected_google: list[dict[str, object]] = [{"text": "First"}]
        if media_type is not None:
            expected_google.append({"inlineData": {"mimeType": media_type, "data": "ZmlsZQ=="}})
        assert body["contents"] == [{"role": "user", "parts": expected_google}]
        assert captured[0].url.path.endswith("/models/gemini-3.8-flash:generateContent")
    elif protocol is ModelProtocol.ANTHROPIC_MESSAGES:
        expected_anthropic: list[dict[str, object]] = [{"type": "text", "text": "First"}]
        if media_type is not None:
            expected_anthropic.append(
                {
                    "type": "image" if media_type == "image/png" else "document",
                    "source": {"type": "base64", "media_type": media_type, "data": "ZmlsZQ=="},
                }
            )
        assert body["messages"] == [{"role": "user", "content": expected_anthropic}]
        assert captured[0].url.path.endswith("/messages")
        assert captured[0].headers["anthropic-version"] == "2023-06-01"
    else:
        expected_responses: list[dict[str, object]] = [{"type": "input_text", "text": "First"}]
        if media_type == "image/png":
            expected_responses.append({"type": "input_image", "image_url": "data:image/png;base64,ZmlsZQ=="})
        elif media_type == "application/pdf":
            expected_responses.append(
                {"type": "input_file", "filename": "document.pdf", "file_data": "data:application/pdf;base64,ZmlsZQ=="}
            )
        assert body["input"] == [{"role": "user", "content": expected_responses}]
        assert captured[0].url.path.endswith("/responses")


@pytest.mark.integration
@pytest.mark.parametrize("protocol", list(ModelProtocol))
def test_palantir_text_preserves_order_and_separators(protocol: ModelProtocol) -> None:
    request: LlmRequest = LlmRequest(
        tuple(
            LlmMessage(role, (TextPart(f"{role.value} first"), TextPart(f"{role.value} second")))
            for role in (LlmRole.SYSTEM, LlmRole.USER, LlmRole.ASSISTANT)
        )
    )
    body: dict[str, Any] = _send(_config(protocol), request, [])
    if protocol in {ModelProtocol.OPENAI_RESPONSES, ModelProtocol.XAI_RESPONSES}:
        assert body["input"] == [
            {"role": "system", "content": "system first\nsystem second"},
            {"role": "user", "content": [{"type": "input_text", "text": "user first\nuser second"}]},
            {"role": "assistant", "content": "assistant first\nassistant second"},
        ]
    elif protocol is ModelProtocol.ANTHROPIC_MESSAGES:
        assert body["system"] == [{"type": "text", "text": "system first"}, {"type": "text", "text": "system second"}]
        assert body["messages"] == [
            {
                "role": role,
                "content": [{"type": "text", "text": f"{role} first"}, {"type": "text", "text": f"{role} second"}],
            }
            for role in ("user", "assistant")
        ]
    else:
        assert body["systemInstruction"] == {"parts": [{"text": "system first"}, {"text": "system second"}]}
        assert body["contents"] == [
            {"role": "user", "parts": [{"text": "user first"}, {"text": "user second"}]},
            {"role": "model", "parts": [{"text": "assistant first"}, {"text": "assistant second"}]},
        ]


@pytest.mark.integration
@pytest.mark.parametrize("protocol", list(ModelProtocol))
def test_palantir_mixed_content_preserves_order(protocol: ModelProtocol) -> None:
    body: dict[str, Any] = _send(
        _config(protocol),
        _request(
            (
                TextPart("First"),
                TextPart("Second"),
                FilePart("image/png", b"file"),
                TextPart("Third"),
                TextPart("Fourth"),
            )
        ),
        [],
    )
    if protocol in {ModelProtocol.OPENAI_RESPONSES, ModelProtocol.XAI_RESPONSES}:
        assert body["input"][0]["content"] == [
            {"type": "input_text", "text": "First\nSecond"},
            {"type": "input_image", "image_url": "data:image/png;base64,ZmlsZQ=="},
            {"type": "input_text", "text": "Third\nFourth"},
        ]
    elif protocol is ModelProtocol.ANTHROPIC_MESSAGES:
        assert body["messages"][0]["content"] == [
            {"type": "text", "text": "First"},
            {"type": "text", "text": "Second"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "ZmlsZQ=="}},
            {"type": "text", "text": "Third"},
            {"type": "text", "text": "Fourth"},
        ]
    else:
        assert body["contents"][0]["parts"] == [
            {"text": "First"},
            {"text": "Second"},
            {"inlineData": {"mimeType": "image/png", "data": "ZmlsZQ=="}},
            {"text": "Third"},
            {"text": "Fourth"},
        ]


@pytest.mark.integration
@pytest.mark.parametrize("protocol", list(ModelProtocol))
def test_palantir_request_applies_reasoning_variant(protocol: ModelProtocol) -> None:
    body: dict[str, Any] = _send(_config(protocol, "high"), _request(), [])
    if protocol in {ModelProtocol.OPENAI_RESPONSES, ModelProtocol.XAI_RESPONSES}:
        assert body["reasoning"] == {"effort": "high"}
        assert body["store"] is False
        assert body["max_output_tokens"] == 256
    elif protocol is ModelProtocol.ANTHROPIC_MESSAGES:
        assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert body["output_config"] == {"effort": "high"}
        assert body["max_tokens"] == 256
    else:
        assert body["generationConfig"] == {
            "thinkingConfig": {"includeThoughts": True, "thinkingBudget": 16384},
            "temperature": 0.3,
            "topP": 0.8,
            "maxOutputTokens": 256,
        }


@pytest.mark.unit
def test_palantir_construction_rejects_unknown_variant() -> None:
    with pytest.raises(LlmConfigError) as rejected:
        PalantirService(_config(ModelProtocol.OPENAI_RESPONSES, "unknown"))
    assert rejected.value.context.details["field"] == "reasoning_variant"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("protocol", "variant", "opus45", "sampling"),
    [
        (ModelProtocol.OPENAI_RESPONSES, None, False, False),
        (ModelProtocol.OPENAI_RESPONSES, "high", False, False),
        (ModelProtocol.OPENAI_RESPONSES, "none", False, True),
        (ModelProtocol.XAI_RESPONSES, None, False, False),
        (ModelProtocol.XAI_RESPONSES, "low", False, False),
        (ModelProtocol.ANTHROPIC_MESSAGES, None, False, False),
        (ModelProtocol.ANTHROPIC_MESSAGES, None, True, True),
        (ModelProtocol.GOOGLE_GENERATE, None, False, True),
    ],
)
def test_palantir_sampling_follows_thinking_policy(
    protocol: ModelProtocol, variant: str | None, *, opus45: bool, sampling: bool
) -> None:
    config: LlmConfig = _config(protocol, variant)
    if opus45:
        config = replace(config, alias="foundry-anthropic/claude-opus-4-5", provider_model_id="claude-opus-4-5")
    body: dict[str, Any] = _send(config, _request(), [])
    parameters: dict[str, Any] = body["generationConfig"] if protocol is ModelProtocol.GOOGLE_GENERATE else body
    top_p: str = "topP" if protocol is ModelProtocol.GOOGLE_GENERATE else "top_p"
    if sampling:
        assert parameters["temperature"] == 0.3
        assert parameters[top_p] == 0.8
    else:
        assert "temperature" not in parameters
        assert top_p not in parameters
