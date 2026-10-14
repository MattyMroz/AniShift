from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace

import httpx
import pytest

from anishift.services.llm import (
    LlmAuthError,
    LlmConfig,
    LlmConfigError,
    LlmMessage,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequest,
    LlmRequestError,
    LlmRole,
    LlmService,
    LlmTimeoutError,
    TextPart,
)
from anishift.services.llm.engines.palantir import accounts
from anishift.services.llm.engines.palantir import service as palantir_service
from anishift.services.llm.errors import LlmError
from anishift.services.llm.wire_protocol import ModelProtocol

pytestmark = pytest.mark.integration

_MODELS: tuple[tuple[str, str, ModelProtocol, str], ...] = (
    ("foundry/gpt-5.6-sol", "foundry-openai", ModelProtocol.OPENAI_RESPONSES, "openai"),
    ("foundry-anthropic/claude-opus-5", "foundry-anthropic", ModelProtocol.ANTHROPIC_MESSAGES, "anthropic"),
    ("foundry-google/gemini-3.8-flash", "foundry-google", ModelProtocol.GOOGLE_GENERATE, "google"),
    ("foundry-xai/grok-4.6", "foundry-xai", ModelProtocol.XAI_RESPONSES, "xai"),
)
_ORIGINS: tuple[str, str] = ("https://primary.example.invalid", "https://fallback.example.invalid")
_TOKENS: tuple[str, str] = ("primary-synthetic-token", "fallback-synthetic-token")


@pytest.fixture(autouse=True)
def cooldown_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    clock: list[float] = [100.0]
    accounts.reset_cooldowns()
    monkeypatch.setattr(accounts, "monotonic", lambda: clock[0])
    try:
        yield clock
    finally:
        accounts.reset_cooldowns()


def _config(family: int = 0) -> LlmConfig:
    alias: str
    provider: str
    protocol: ModelProtocol
    route: str
    alias, provider, protocol, route = _MODELS[family]
    return LlmConfig(
        engine_id="palantir",
        provider_model_id=alias.split("/")[1],
        alias=alias,
        provider_id=provider,
        protocol=protocol,
        base_url=f"{_ORIGINS[0]}/api/v2/llm/proxy/{route}/v1",
        api_key=_TOKENS[0],
        fallback_origin=_ORIGINS[1],
        fallback_api_key=_TOKENS[1],
        max_retries=0,
    )


def _transport(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    monkeypatch.setattr(
        palantir_service,
        "build_palantir_client",
        lambda timeout_s: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _complete(config: LlmConfig) -> None:
    with LlmService(config) as service:
        service.complete(LlmRequest((LlmMessage(LlmRole.USER, (TextPart("Translate"),)),)))


def _success(family: int) -> httpx.Response:
    if family == 1:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"})
    if family == 2:
        return httpx.Response(
            200,
            text='data: {"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}\n\n',
        )
    payload: dict[str, object] = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
    }
    if family == 3:
        return httpx.Response(200, json=payload)
    return httpx.Response(200, text=f"data: {json.dumps({'type': 'response.completed', 'response': payload})}\n\n")


@pytest.mark.parametrize("family", range(4))
@pytest.mark.parametrize("status", [429, 500])
def test_http_limit_or_server_error_switches_account(monkeypatch: pytest.MonkeyPatch, family: int, status: int) -> None:
    sent: list[httpx.Request] = []
    closed: list[bool] = []

    class _SkippedBody(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            raise AssertionError("Failover must not read the skipped response body")

        def close(self) -> None:
            closed.append(True)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(status, stream=_SkippedBody())
        assert closed == [True]
        return _success(family)

    _transport(monkeypatch, handler)
    _complete(_config(family))

    assert [request.url.host for request in sent] == ["primary.example.invalid", "fallback.example.invalid"]
    assert [request.headers["authorization"] for request in sent] == [f"Bearer {token}" for token in _TOKENS]
    assert sent[0].content == sent[1].content
    assert sent[0].url.raw_path == sent[1].url.raw_path
    assert {key: value for key, value in sent[0].headers.items() if key not in {"host", "authorization"}} == {
        key: value for key, value in sent[1].headers.items() if key not in {"host", "authorization"}
    }
    if family == 1:
        assert sent[1].headers["anthropic-version"] == "2023-06-01"
    if family == 2:
        assert sent[1].url.query == b"alt=sse"


@pytest.mark.parametrize("family", [0, 3], ids=["stream", "json"])
@pytest.mark.parametrize(
    ("failure", "expected", "attempts"),
    [
        ("auth", LlmAuthError, 1),
        ("network", LlmProviderUnavailableError, 2),
        ("body_timeout", LlmTimeoutError, 2),
        ("generation", LlmRateLimitError, 2),
        ("malformed_body", LlmRequestError, 1),
    ],
)
def test_non_failover_failure_stays_on_account(
    monkeypatch: pytest.MonkeyPatch, family: int, failure: str, expected: type[LlmError], attempts: int
) -> None:
    sent: list[httpx.Request] = []
    closed: list[bool] = []

    class _TimedOutBody(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            raise httpx.ReadTimeout("Synthetic body timeout")

        def close(self) -> None:
            closed.append(True)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if failure == "network":
            raise httpx.ConnectError("Synthetic connection failure")
        if failure == "auth":
            return httpx.Response(401, json={})
        if failure == "body_timeout":
            return httpx.Response(200, stream=_TimedOutBody())
        if failure == "malformed_body":
            return httpx.Response(200, text="data: not-json\n\n" if family == 0 else "not-json")
        payload: dict[str, object] = {"status": "failed", "error": {"code": "rate_limit_exceeded"}}
        if family == 3:
            return httpx.Response(200, json=payload)
        return httpx.Response(200, text=f"data: {json.dumps({'type': 'response.failed', 'response': payload})}\n\n")

    _transport(monkeypatch, handler)
    with pytest.raises(expected):
        _complete(replace(_config(family), max_retries=1))
    assert [request.url.host for request in sent] == ["primary.example.invalid"] * attempts
    if failure == "body_timeout":
        assert closed == [True] * attempts


def test_account_cooldown_is_shared_between_services(
    monkeypatch: pytest.MonkeyPatch, cooldown_clock: list[float]
) -> None:
    sent: list[httpx.Request] = []
    family: int = 0

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(429, json={}) if len(sent) == 1 else _success(family)

    _transport(monkeypatch, handler)
    _complete(_config(family))
    cooldown_clock[0] += 59.0
    family = 3
    _complete(_config(family))
    cooldown_clock[0] += 1.0
    _complete(_config(family))
    assert [request.url.host for request in sent] == [
        "primary.example.invalid",
        "fallback.example.invalid",
        "fallback.example.invalid",
        "primary.example.invalid",
    ]


@pytest.mark.parametrize("family", [0, 3], ids=["stream", "json"])
def test_retry_uses_accounts_when_both_are_cooling_down(monkeypatch: pytest.MonkeyPatch, family: int) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(500 if request.url.host == "primary.example.invalid" else 429, json={})

    _transport(monkeypatch, handler)
    with pytest.raises(LlmRateLimitError):
        _complete(replace(_config(family), max_retries=1))
    assert [request.url.host for request in sent] == ["primary.example.invalid", "fallback.example.invalid"] * 2


@pytest.mark.parametrize("family", [0, 3], ids=["stream", "json"])
@pytest.mark.parametrize("missing", ["both", "origin", "token"])
def test_single_account_preserves_retry_behavior(monkeypatch: pytest.MonkeyPatch, family: int, missing: str) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(429, json={}) if len(sent) == 1 else _success(family)

    _transport(monkeypatch, handler)
    config: LlmConfig = replace(
        _config(family),
        fallback_origin="" if missing in {"both", "origin"} else _ORIGINS[1],
        fallback_api_key="" if missing in {"both", "token"} else _TOKENS[1],
        max_retries=1,
    )
    _complete(config)
    assert [request.url.host for request in sent] == ["primary.example.invalid"] * 2


@pytest.mark.parametrize(
    "origin",
    [
        "http://fallback.example.invalid",
        "https://fallback.example.invalid/path",
        "https://fallback.example.invalid/?q=1",
    ],
)
def test_fallback_origin_rejects_invalid_origin(monkeypatch: pytest.MonkeyPatch, origin: str) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return _success(0)

    _transport(monkeypatch, handler)
    with pytest.raises(LlmConfigError) as rejected:
        _complete(replace(_config(), fallback_origin=origin))
    assert rejected.value.context.details["field"] == "fallback_origin"
    assert origin not in repr(rejected.value.context)
    assert sent == []
