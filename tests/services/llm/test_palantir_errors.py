from __future__ import annotations

import json
import os
from dataclasses import replace

import httpx
import pytest
from loguru import logger as loguru_logger

from anishift.errors import FatalError, TransientError
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.palantir import service as palantir_service
from anishift.services.llm.engines.palantir.service import PalantirService
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmError,
    LlmModelError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.service import LlmService
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart
from anishift.services.llm.wire_protocol import ModelProtocol

_TOKEN = "palantir-token-sentinel-deadbeef"  # noqa: S105
_BODY_SENTINEL = "secret subtitle line hunter2"
_ENROLLMENT = "https://example.palantirfoundry.com"
_OPENAI_ROUTE = "/api/v2/llm/proxy/openai/v1"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)


def _config(*, api_key: str = _TOKEN) -> LlmConfig:
    return LlmConfig(
        engine_id="palantir",
        provider_model_id="gpt-main-5",
        api_key=api_key,
        alias="foundry/gpt-5.6-sol",
        provider_id="foundry-openai",
        protocol=ModelProtocol.OPENAI_RESPONSES,
        base_url=f"{_ENROLLMENT}{_OPENAI_ROUTE}",
    )


def _request() -> LlmRequest:
    return LlmRequest(messages=(LlmMessage(role=LlmRole.USER, parts=(TextPart(text="Translate this line."),)),))


def _engine_returning(response: httpx.Response) -> PalantirService:
    return PalantirService(_config(), client=httpx.Client(transport=httpx.MockTransport(lambda request: response)))


def _engine_raising(error: BaseException) -> PalantirService:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return PalantirService(_config(), client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (401, None, LlmAuthError),
        (403, None, LlmAuthError),
        (404, None, LlmModelError),
        (408, None, LlmTimeoutError),
        (429, None, LlmRateLimitError),
        (429, {"error": {"code": "insufficient_quota"}}, LlmQuotaError),
        (402, None, LlmPaymentError),
        (500, None, LlmProviderUnavailableError),
        (503, None, LlmProviderUnavailableError),
    ],
)
def test_status_codes_map_onto_the_existing_taxonomy(
    status_code: int,
    payload: object,
    expected: type[LlmError],
) -> None:
    response = httpx.Response(status_code, json=payload if payload is not None else {})
    engine = _engine_returning(response)

    with pytest.raises(expected) as failure:
        engine.complete(_request())

    assert failure.value.context.details["alias"] == "foundry/gpt-5.6-sol"
    assert failure.value.context.details["engine_id"] == "palantir"


@pytest.mark.parametrize(
    ("status_code", "transient"),
    [(401, False), (404, False), (408, True), (429, True), (500, True)],
)
def test_status_codes_keep_the_taxonomy_retry_semantics(status_code: int, transient: bool) -> None:
    engine = _engine_returning(httpx.Response(status_code, json={}))

    with pytest.raises(LlmError) as failure:
        engine.complete(_request())

    assert isinstance(failure.value, TransientError) is transient
    assert isinstance(failure.value, FatalError) is not transient


def test_a_timeout_exception_becomes_a_transient_timeout() -> None:
    engine = _engine_raising(httpx.ReadTimeout("timed out"))

    with pytest.raises(LlmTimeoutError):
        engine.complete(_request())


def test_a_transport_error_becomes_a_transient_unavailable() -> None:
    engine = _engine_raising(httpx.ConnectError("enrollment down"))

    with pytest.raises(LlmProviderUnavailableError):
        engine.complete(_request())


def test_a_rate_limit_carries_the_retry_after_hint() -> None:
    response = httpx.Response(429, json={}, headers={"retry-after": "7"})
    engine = _engine_returning(response)

    with pytest.raises(LlmRateLimitError) as limited:
        engine.complete(_request())

    assert limited.value.retry_after_s == 7.0


def test_a_missing_token_is_a_typed_auth_error() -> None:
    with pytest.raises(LlmAuthError):
        PalantirService(_config(api_key=""))


def test_an_error_status_never_leaks_the_body_or_the_token() -> None:
    captured: list[str] = []
    handler_id = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    response = httpx.Response(
        404,
        json={"error": {"message": _BODY_SENTINEL, "code": "model_not_found"}},
    )
    engine = _engine_returning(response)
    try:
        with pytest.raises(LlmModelError) as failure:
            engine.complete(_request())
    finally:
        loguru_logger.remove(handler_id)

    error = failure.value
    surfaces = [str(error), repr(error), repr(error.context), *captured]
    assert all(_BODY_SENTINEL not in surface for surface in surfaces)
    assert all(_TOKEN not in surface for surface in surfaces)
    assert all("Bearer" not in surface for surface in captured)


@pytest.mark.integration
@pytest.mark.parametrize("shape", ["error", "response.failed", "json"])
@pytest.mark.parametrize(
    ("code", "expected", "attempts"),
    [
        ("server_error", LlmProviderUnavailableError, 2),
        ("rate_limit_exceeded", LlmRateLimitError, 2),
        ("invalid_request", LlmRequestError, 1),
    ],
)
def test_generation_failure_retry_through_llm_service(
    monkeypatch: pytest.MonkeyPatch, shape: str, code: str, expected: type[LlmError], attempts: int
) -> None:
    calls: list[httpx.Request] = []
    payload: dict[str, object] = {"status": "failed", "error": {"code": code, "message": _BODY_SENTINEL}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if shape == "json":
            return httpx.Response(200, json=payload)
        event: dict[str, object] = (
            {"type": "error", "code": code, "message": _BODY_SENTINEL}
            if shape == "error"
            else {"type": "response.failed", "response": payload}
        )
        return httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")

    client: httpx.Client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(palantir_service, "build_palantir_client", lambda timeout_s: client)
    config: LlmConfig = replace(_config(), max_retries=1)
    if shape == "json":
        config = replace(
            config,
            alias="foundry-xai/grok-4.6",
            provider_id="foundry-xai",
            provider_model_id="grok-4.6",
            protocol=ModelProtocol.XAI_RESPONSES,
            base_url=f"{_ENROLLMENT}/api/v2/llm/proxy/xai/v1",
        )
    with LlmService(config) as service, pytest.raises(expected) as failure:
        service.complete(_request())

    assert type(failure.value) is expected
    assert len(calls) == attempts
    assert _BODY_SENTINEL not in repr(failure.value.context)


@pytest.mark.integration
@pytest.mark.parametrize("body", ["", "data: [DONE]\n\n"], ids=["empty-body", "done-only"])
@pytest.mark.parametrize("protocol", [ModelProtocol.OPENAI_RESPONSES, ModelProtocol.GOOGLE_GENERATE])
def test_empty_stream_retries_through_llm_service(
    monkeypatch: pytest.MonkeyPatch, body: str, protocol: ModelProtocol
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=body)

    client: httpx.Client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(palantir_service, "build_palantir_client", lambda timeout_s: client)
    config: LlmConfig = replace(_config(), max_retries=1)
    if protocol is ModelProtocol.GOOGLE_GENERATE:
        config = replace(
            config,
            alias="foundry-google/gemini-3.8-flash",
            provider_id="foundry-google",
            provider_model_id="gemini-3.8-flash",
            protocol=protocol,
            base_url=f"{_ENROLLMENT}/api/v2/llm/proxy/google/v1",
        )
    with LlmService(config) as service, pytest.raises(LlmError) as failure:
        service.complete(_request())

    assert type(failure.value) is LlmProviderUnavailableError
    assert isinstance(failure.value, TransientError)
    assert len(calls) == 2


@pytest.mark.integration
def test_malformed_responses_stream_is_fatal_through_llm_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="data: {broken-json\n\n")

    client: httpx.Client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(palantir_service, "build_palantir_client", lambda timeout_s: client)
    with LlmService(replace(_config(), max_retries=1)) as service, pytest.raises(LlmRequestError) as failure:
        service.complete(_request())

    assert isinstance(failure.value, FatalError)
    assert len(calls) == 1
