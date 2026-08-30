from __future__ import annotations

from typing import Never

import pytest

from anishift.errors import AniShiftError, ErrorCode, TransientError
from anishift.services.llm import (
    LlmAuthError,
    LlmConfig,
    LlmConfigError,
    LlmMessage,
    LlmRequest,
    LlmResponse,
    LlmRole,
    LlmUsage,
    TextPart,
)
from anishift.services.llm.service import LlmService


class FakeEngine:
    engine_id = "fake"
    is_available = True

    def __init__(self) -> None:
        self.complete_calls: int = 0
        self.close_calls: int = 0

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.complete_calls += 1
        return _response(request.messages[0].parts[0].text)

    def close(self) -> None:
        self.close_calls += 1


class FakeStreamingEngine(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.stream_calls: int = 0

    def complete_stream(self, request: LlmRequest) -> LlmResponse:
        self.stream_calls += 1
        return _response(request.messages[0].parts[0].text)


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[str] = []

    def before_attempt(self) -> None:
        self.events.append("before")

    def on_transient_failure(self, error: TransientError) -> None:
        self.events.append("transient")

    def on_success(self) -> None:
        self.events.append("success")

    def on_fatal_failure(self, error: AniShiftError) -> None:
        self.events.append(f"fatal:{type(error).__name__}")


def test_service_constructs_engine_lazily_and_reuses_it(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    factory_calls: list[LlmConfig] = []

    def fake_create_engine(config: LlmConfig) -> FakeEngine:
        factory_calls.append(config)
        return engine

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    service = LlmService(_config())

    assert factory_calls == []
    first: LlmResponse = service.complete(_request("first"))
    second: LlmResponse = service.complete(_request("second"))

    assert first.text == "first"
    assert second.text == "second"
    assert factory_calls == [service.config]
    assert engine.complete_calls == 2


def test_service_close_is_idempotent_after_engine_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr("anishift.services.llm.service.create_engine", lambda config: engine)
    service = LlmService(_config())
    service.complete(_request("text"))

    service.close()
    service.close()

    assert engine.close_calls == 1
    assert service.is_available is False


def test_service_close_without_completion_does_not_create_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    factory_calls: int = 0

    def fake_create_engine(config: LlmConfig) -> FakeEngine:
        nonlocal factory_calls
        factory_calls += 1
        return FakeEngine()

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    service = LlmService(_config())

    service.close()

    assert factory_calls == 0


def test_service_context_manager_closes_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    monkeypatch.setattr("anishift.services.llm.service.create_engine", lambda config: engine)

    def run() -> Never:
        with LlmService(_config()) as service:
            service.complete(_request("text"))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run()

    assert engine.close_calls == 1


def test_service_rejects_completion_after_close(monkeypatch: pytest.MonkeyPatch) -> None:
    factory_calls: int = 0

    def fake_create_engine(config: LlmConfig) -> FakeEngine:
        nonlocal factory_calls
        factory_calls += 1
        return FakeEngine()

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    service = LlmService(_config())
    service.close()

    with pytest.raises(LlmConfigError) as exc_info:
        service.complete(_request("text"))

    assert exc_info.value.context.code is ErrorCode.LLM_CONFIG_INVALID
    assert factory_calls == 0


def test_service_reports_missing_key_without_creating_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    factory_calls: int = 0

    def fake_create_engine(config: LlmConfig) -> FakeEngine:
        nonlocal factory_calls
        factory_calls += 1
        return FakeEngine()

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    service = LlmService(
        LlmConfig(engine_id="gemini", provider_model_id="gemini-3.5-flash-lite"),
    )

    assert service.is_available is False
    with pytest.raises(LlmAuthError) as exc_info:
        service.complete(_request("text"))

    assert exc_info.value.context.code is ErrorCode.LLM_AUTH_FAILED
    assert factory_calls == 0


def test_service_requires_compatible_base_url_but_not_key() -> None:
    missing_url = LlmService(
        LlmConfig(engine_id="openai_compatible", provider_model_id="custom"),
    )
    configured = LlmService(
        LlmConfig(
            engine_id="openai_compatible",
            provider_model_id="custom",
            base_url="http://localhost:11434/v1",
        ),
    )

    assert missing_url.is_available is False
    assert configured.is_available is True
    with pytest.raises(LlmConfigError) as exc_info:
        missing_url.complete(_request("text"))
    assert exc_info.value.context.code is ErrorCode.LLM_CONFIG_INVALID


def test_default_completion_timeout_allows_multi_minute_generation() -> None:
    config = LlmConfig(engine_id="gemini", provider_model_id="gemini-3.7-flash")

    assert config.timeout_s == 300.0


def test_service_forwards_attempt_observer(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeEngine()
    observer = RecordingObserver()
    monkeypatch.setattr("anishift.services.llm.service.create_engine", lambda config: engine)
    service = LlmService(_config(), observer=observer)

    service.complete(_request("text"))

    assert observer.events == ["before", "success"]


def test_service_prefers_streaming_when_the_engine_supports_it(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = FakeStreamingEngine()
    monkeypatch.setattr("anishift.services.llm.service.create_engine", lambda config: engine)

    result = LlmService(_config()).complete(_request("text"))

    assert result.text == "text"
    assert engine.stream_calls == 1
    assert engine.complete_calls == 0


def _config() -> LlmConfig:
    return LlmConfig(
        engine_id="gemini",
        provider_model_id="gemini-3.5-flash-lite",
        api_key="test-key",
        max_retries=0,
    )


def _request(text: str) -> LlmRequest:
    return LlmRequest(
        messages=(LlmMessage(role=LlmRole.USER, parts=(TextPart(text),)),),
    )


def _response(text: str) -> LlmResponse:
    return LlmResponse(
        text=text,
        engine_id="fake",
        provider_model_id="fake-model",
        finish_reason="stop",
        latency_ms=1.0,
        usage=LlmUsage(),
    )
