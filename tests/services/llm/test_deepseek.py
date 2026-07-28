from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.deepseek import DeepseekService
from anishift.services.llm.engines.deepseek.constants import SUGGESTED_MODEL_IDS
from anishift.services.llm.errors import LlmProviderUnavailableError
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart


@dataclass(slots=True)
class FakeClient:
    finish_reason: str = "stop"
    calls: list[dict[str, object]] = field(default_factory=list, init=False)
    chat: object = field(init=False)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message, finish_reason=self.finish_reason)
        return SimpleNamespace(choices=[choice], model="deepseek-chat", usage=None)

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


def test_deepseek_uses_compatible_max_tokens_and_default_url() -> None:
    client = FakeClient()
    factory = FakeFactory(client)
    config = LlmConfig(
        engine_id="deepseek",
        provider_model_id="custom-deepseek",
        api_key="secret",
        max_output_tokens=150,
    )
    service = DeepseekService(config, _client_factory=factory)

    service.complete(_request())

    assert client.calls[0]["max_tokens"] == 150
    assert "max_completion_tokens" not in client.calls[0]
    assert factory.kwargs["base_url"] == "https://api.deepseek.com"
    assert factory.kwargs["max_retries"] == 0


def test_deepseek_insufficient_system_resource_is_transient() -> None:
    client = FakeClient(finish_reason="insufficient_system_resource")
    config = LlmConfig(
        engine_id="deepseek",
        provider_model_id="deepseek-chat",
        api_key="secret",
    )
    service = DeepseekService(config, _client_factory=FakeFactory(client))

    with pytest.raises(LlmProviderUnavailableError):
        service.complete(_request())


def test_deepseek_suggestions_are_official_aliases() -> None:
    assert SUGGESTED_MODEL_IDS == ("deepseek-v4-flash", "deepseek-v4-pro")
