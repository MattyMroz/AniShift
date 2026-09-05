from __future__ import annotations

import os

import httpx
import pytest
from loguru import logger as loguru_logger

from anishift.errors import FatalError, TransientError
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.palantir.service import PalantirService
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmError,
    LlmModelError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmTimeoutError,
)
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
        alias="foundry/main",
        provider_id="foundry-openai",
        protocol=ModelProtocol.OPENAI_CHAT,
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

    assert failure.value.context.details["alias"] == "foundry/main"
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
