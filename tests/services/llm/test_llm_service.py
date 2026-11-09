from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Never

import pytest

from anishift.errors import AniShiftError, ErrorCode
from anishift.services.llm import (
    LlmAuthError,
    LlmConfig,
    LlmConfigError,
    LlmContentPart,
    LlmMessage,
    LlmProviderUnavailableError,
    LlmQuotaError,
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
        part: LlmContentPart = request.messages[0].parts[0]
        assert isinstance(part, TextPart)
        return _response(part.text)

    def close(self) -> None:
        self.close_calls += 1


class FakeStreamingEngine(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.stream_calls: int = 0

    def complete_stream(
        self,
        request: LlmRequest,
        *,
        on_text: Callable[[str], None] | None = None,
    ) -> LlmResponse:
        self.stream_calls += 1
        part: LlmContentPart = request.messages[0].parts[0]
        assert isinstance(part, TextPart)
        response: LlmResponse = _response(part.text)
        if on_text is not None:
            on_text(response.text)
        return response


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[str] = []

    def before_attempt(self) -> None:
        self.events.append("before")

    def on_retry(self, error: AniShiftError, *, attempt: int, max_attempts: int) -> None:
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


class KeyEngine:
    engine_id = "fake"
    is_available = True

    def __init__(self, key: str, outcomes: dict[str, list[Exception]], used: list[str]) -> None:
        self.key: str = key
        self.outcomes: dict[str, list[Exception]] = outcomes
        self.used: list[str] = used
        self.closed: bool = False

    def complete(self, request: LlmRequest) -> LlmResponse:
        self.used.append(self.key)
        pending: list[Exception] = self.outcomes.get(self.key, [])
        if pending:
            raise pending.pop(0)
        return _response(self.key)

    def close(self) -> None:
        self.closed = True


def _key_service(
    monkeypatch: pytest.MonkeyPatch,
    keys: tuple[str, ...],
    *,
    mode: str = "failover",
    outcomes: dict[str, list[Exception]] | None = None,
) -> tuple[LlmService, list[str], list[KeyEngine]]:
    used: list[str] = []
    engines: list[KeyEngine] = []

    def fake_create_engine(config: LlmConfig) -> KeyEngine:
        engine = KeyEngine(config.api_key, outcomes if outcomes is not None else {}, used)
        engines.append(engine)
        return engine

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    monkeypatch.setattr("anishift.services.llm.service._ROTATION", {})
    config: LlmConfig = replace(_config(), api_keys=keys, api_key_mode=mode)  # type: ignore[arg-type]
    return LlmService(config), used, engines


@pytest.mark.unit
def test_failover_starts_every_request_on_the_first_key(monkeypatch: pytest.MonkeyPatch) -> None:
    service, used, _engines = _key_service(monkeypatch, ("private", "business"))

    texts: list[str] = [service.complete(_request("text")).text for _ in range(3)]

    assert texts == ["private", "private", "private"]
    assert used == ["private", "private", "private"]


@pytest.mark.unit
def test_failover_moves_to_the_next_key_after_any_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: dict[str, list[Exception]] = {"private": [LlmQuotaError("daily"), LlmProviderUnavailableError("busy")]}
    service, used, _engines = _key_service(monkeypatch, ("private", "business"), outcomes=outcomes)

    first: str = service.complete(_request("text")).text
    second: str = service.complete(_request("text")).text

    assert (first, second) == ("business", "business")
    assert used == ["private", "business", "private", "business"]


@pytest.mark.unit
def test_rotate_starts_each_request_on_the_next_key_across_services(monkeypatch: pytest.MonkeyPatch) -> None:
    service, used, _engines = _key_service(monkeypatch, ("a", "b", "c"), mode="rotate")
    other = LlmService(service.config)

    texts: list[str] = [service.complete(_request("text")).text, other.complete(_request("text")).text]
    texts += [service.complete(_request("text")).text, other.complete(_request("text")).text]

    assert texts == ["a", "b", "c", "a"]
    assert used == texts


@pytest.mark.unit
def test_each_key_gets_its_own_engine_and_close_releases_them_all(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: dict[str, list[Exception]] = {"first": [LlmProviderUnavailableError("busy")]}
    service, _used, engines = _key_service(monkeypatch, ("first", "second"), outcomes=outcomes)

    service.complete(_request("text"))
    service.complete(_request("text"))
    service.close()

    assert [engine.key for engine in engines] == ["first", "second"]
    assert all(engine.closed for engine in engines)


@pytest.mark.unit
def test_engine_config_never_carries_the_other_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_create_engine(config: LlmConfig) -> FakeEngine:
        seen.append(config.api_keys)
        return FakeEngine()

    monkeypatch.setattr("anishift.services.llm.service.create_engine", fake_create_engine)
    LlmService(replace(_config(), api_keys=("one", "two"))).complete(_request("text"))

    assert seen == [("one",)]


def _config() -> LlmConfig:
    return LlmConfig(
        engine_id="gemini",
        provider_model_id="gemini-3.5-flash-lite",
        api_keys=("test-key",),
        retry_waits_s=(),
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
