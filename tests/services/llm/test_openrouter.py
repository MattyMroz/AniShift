from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.openrouter import OpenrouterService
from anishift.services.llm.engines.openrouter.constants import SUGGESTED_MODEL_IDS
from anishift.services.llm.errors import LlmPaymentError, LlmProviderUnavailableError
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart


@dataclass(slots=True)
class FakeClient:
    error: BaseException | None = None
    calls: list[dict[str, object]] = field(default_factory=list, init=False)
    chat: object = field(init=False)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5, cost=0.001)
        return SimpleNamespace(choices=[choice], model="vendor/custom", usage=usage)

    def close(self) -> None:
        return None


class FakeFactory:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.kwargs: dict[str, object] = {}

    def __call__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        timeout: float,
        max_retries: int,
    ) -> FakeClient:
        self.kwargs = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        return self.client


def _request() -> LlmRequest:
    message = LlmMessage(role=LlmRole.USER, parts=(TextPart("translate"),))
    return LlmRequest(messages=(message,))


def _status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError("provider error", response=response, body={"error": {"code": status_code}})


def test_openrouter_uses_default_url_custom_slug_and_cost() -> None:
    client = FakeClient()
    factory = FakeFactory(client)
    config = LlmConfig(
        engine_id="openrouter",
        provider_model_id="vendor/custom",
        api_key="secret",
        max_output_tokens=90,
    )
    service = OpenrouterService(config, _client_factory=factory)

    result = service.complete(_request())

    assert factory.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert factory.kwargs["max_retries"] == 0
    assert client.calls[0]["model"] == "vendor/custom"
    assert client.calls[0]["max_tokens"] == 90
    assert result.usage.reported_cost == 0.001


def test_openrouter_payment_required_is_fatal() -> None:
    client = FakeClient(error=_status_error(402))
    config = LlmConfig(
        engine_id="openrouter",
        provider_model_id="vendor/model",
        api_key="secret",
    )
    service = OpenrouterService(config, _client_factory=FakeFactory(client))

    with pytest.raises(LlmPaymentError):
        service.complete(_request())


def test_openrouter_server_error_is_transient() -> None:
    client = FakeClient(error=_status_error(503))
    config = LlmConfig(
        engine_id="openrouter",
        provider_model_id="vendor/model",
        api_key="secret",
    )
    service = OpenrouterService(config, _client_factory=FakeFactory(client))

    with pytest.raises(LlmProviderUnavailableError):
        service.complete(_request())


def test_openrouter_suggestions_are_small_unique_slugs() -> None:
    assert 2 <= len(SUGGESTED_MODEL_IDS) <= 4
    assert len(SUGGESTED_MODEL_IDS) == len(set(SUGGESTED_MODEL_IDS))
    assert all("/" in model for model in SUGGESTED_MODEL_IDS)
