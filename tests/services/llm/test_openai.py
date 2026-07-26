from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.openai import OpenaiService
from anishift.services.llm.engines.openai.constants import SUGGESTED_MODEL_IDS
from anishift.services.llm.errors import LlmAuthError
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart


@dataclass(slots=True)
class FakeClient:
    calls: list[dict[str, object]] = field(default_factory=list, init=False)
    chat: object = field(init=False)
    closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        message = SimpleNamespace(content="ok")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            model="gpt-custom",
            usage=None,
        )

    def close(self) -> None:
        self.closed = True


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
    return LlmRequest(
        messages=(
            LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart("rules"),)),
            LlmMessage(role=LlmRole.USER, parts=(TextPart("translate"),)),
        )
    )


def test_openai_uses_direct_max_completion_tokens_and_default_url() -> None:
    client = FakeClient()
    factory = FakeFactory(client)
    config = LlmConfig(
        engine_id="openai",
        provider_model_id="gpt-custom",
        api_key="secret",
        max_output_tokens=200,
    )
    service = OpenaiService(config, _client_factory=factory)

    result = service.complete(_request())

    assert client.calls[0]["max_completion_tokens"] == 200
    assert "max_tokens" not in client.calls[0]
    assert factory.kwargs["base_url"] is None
    assert factory.kwargs["max_retries"] == 0
    assert result.provider_model_id == "gpt-custom"


def test_openai_missing_key_is_unavailable_and_fatal() -> None:
    client = FakeClient()
    service = OpenaiService(
        LlmConfig(engine_id="openai", provider_model_id="gpt-custom"),
        _client_factory=FakeFactory(client),
    )

    assert service.is_available is False
    with pytest.raises(LlmAuthError) as error_info:
        service.complete(_request())
    assert "ANISHIFT_OPENAI_API_KEY" in error_info.value.context.suggestion
    assert not client.calls


def test_openai_suggestions_are_small_unique_strings() -> None:
    assert 2 <= len(SUGGESTED_MODEL_IDS) <= 4
    assert len(SUGGESTED_MODEL_IDS) == len(set(SUGGESTED_MODEL_IDS))
    assert all(model.strip() for model in SUGGESTED_MODEL_IDS)
