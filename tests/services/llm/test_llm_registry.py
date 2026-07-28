from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from types import ModuleType
from typing import get_args

import pytest

from anishift.errors import AniShiftError, ErrorCode, FatalError, TransientError
from anishift.services.llm import (
    LlmAttemptObserver,
    LlmConfig,
    LlmConfigError,
    LlmEngine,
    LlmEngineId,
    LlmMessage,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequest,
    LlmRequestError,
    LlmResponse,
    LlmRole,
    LlmUsage,
    TextPart,
    available_engine_ids,
    create_engine,
    suggested_model_ids,
)

EXPECTED_ENGINE_IDS = (
    "anthropic",
    "deepseek",
    "gemini",
    "openai",
    "openai_compatible",
    "openrouter",
)


class FakeEngine:
    engine_id = "openai"
    is_available = True

    def complete(self, request: LlmRequest) -> LlmResponse:
        return LlmResponse(
            text=request.messages[0].parts[0].text,
            engine_id=self.engine_id,
            provider_model_id="custom-model",
            finish_reason="stop",
            latency_ms=1.0,
            usage=LlmUsage(),
        )

    def close(self) -> None:
        return None


class FakeObserver:
    def before_attempt(self) -> None:
        return None

    def on_transient_failure(self, error: TransientError) -> None:
        return None

    def on_success(self) -> None:
        return None

    def on_fatal_failure(self, error: AniShiftError) -> None:
        del error


def test_available_engine_ids_returns_exact_registry_order() -> None:
    assert available_engine_ids() == EXPECTED_ENGINE_IDS


def test_engine_id_literal_matches_registry() -> None:
    assert get_args(LlmEngineId) == available_engine_ids()


def test_unknown_engine_raises_structured_config_error() -> None:
    config = LlmConfig(engine_id="unknown", provider_model_id="custom-model")
    with pytest.raises(LlmConfigError) as exc_info:
        create_engine(config)
    assert exc_info.value.context.code is ErrorCode.LLM_CONFIG_INVALID
    assert ", ".join(EXPECTED_ENGINE_IDS) in str(exc_info.value)


def test_create_engine_imports_only_selected_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    imported_modules: list[str] = []
    fake_module = ModuleType("anishift.services.llm.engines.openai")

    def fake_factory(config: LlmConfig) -> LlmEngine:
        assert config.engine_id == "openai"
        return FakeEngine()

    def fake_import_module(module_path: str) -> ModuleType:
        imported_modules.append(module_path)
        return fake_module

    fake_module.__dict__["OpenaiService"] = fake_factory
    registry = importlib.import_module("anishift.services.llm.engines")
    monkeypatch.setattr(registry.importlib, "import_module", fake_import_module)

    config = LlmConfig(engine_id="openai", provider_model_id="custom-model")
    engine = create_engine(config)

    assert isinstance(engine, LlmEngine)
    assert imported_modules == ["anishift.services.llm.engines.openai"]


def test_suggested_models_import_only_lightweight_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    imported_modules: list[str] = []
    fake_constants = ModuleType("anishift.services.llm.engines.gemini.constants")
    fake_constants.__dict__["SUGGESTED_MODEL_IDS"] = ("gemini-3.5-flash-lite",)

    def fake_import_module(module_path: str) -> ModuleType:
        imported_modules.append(module_path)
        return fake_constants

    registry = importlib.import_module("anishift.services.llm.engines")
    monkeypatch.setattr(registry.importlib, "import_module", fake_import_module)

    assert suggested_model_ids("gemini") == ("gemini-3.5-flash-lite",)
    assert imported_modules == ["anishift.services.llm.engines.gemini.constants"]


def test_openai_compatible_has_no_model_suggestions() -> None:
    assert suggested_model_ids("openai_compatible") == ()


def test_domain_import_does_not_load_provider_sdks() -> None:
    sdk_modules = ("anthropic", "google.genai", "openai")
    for module_name in sdk_modules:
        sys.modules.pop(module_name, None)

    domain = importlib.import_module("anishift.services.llm")
    importlib.reload(domain)

    for module_name in sdk_modules:
        assert module_name not in sys.modules


@pytest.mark.parametrize(
    ("build_config", "field_name"),
    [
        pytest.param(
            lambda: LlmConfig(engine_id="", provider_model_id="custom-model"),
            "engine_id",
            id="empty-engine",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id=" "),
            "provider_model_id",
            id="empty-model",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", timeout_s=0),
            "timeout_s",
            id="zero-timeout",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", timeout_s=float("nan")),
            "timeout_s",
            id="nan-timeout",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", timeout_s=float("inf")),
            "timeout_s",
            id="infinite-timeout",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", max_retries=-1),
            "max_retries",
            id="negative-retries",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", max_output_tokens=0),
            "max_output_tokens",
            id="zero-output-tokens",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", temperature=-0.1),
            "temperature",
            id="low-temperature",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", temperature=2.1),
            "temperature",
            id="high-temperature",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", top_p=-0.1),
            "top_p",
            id="low-top-p",
        ),
        pytest.param(
            lambda: LlmConfig(engine_id="gemini", provider_model_id="custom-model", top_p=1.1),
            "top_p",
            id="high-top-p",
        ),
    ],
)
def test_config_rejects_invalid_fields(build_config: Callable[[], LlmConfig], field_name: str) -> None:
    with pytest.raises(LlmConfigError) as exc_info:
        build_config()
    assert exc_info.value.context.code is ErrorCode.LLM_CONFIG_INVALID
    assert exc_info.value.context.details == {"field": field_name}


def test_config_accepts_custom_model_empty_key_and_empty_compatible_url() -> None:
    config = LlmConfig(
        engine_id="openai_compatible",
        provider_model_id="my-private-model",
        api_key="",
        base_url="",
        temperature=None,
        top_p=None,
        max_output_tokens=None,
    )
    assert config.provider_model_id == "my-private-model"


def test_config_is_frozen_and_hides_api_key_from_repr() -> None:
    config = LlmConfig(
        engine_id="gemini",
        provider_model_id="custom-model",
        api_key="top-secret-key",
    )
    assert "top-secret-key" not in repr(config)
    attribute_name: str = "engine_id"
    with pytest.raises(FrozenInstanceError):
        setattr(config, attribute_name, "openai")


def test_request_requires_user_message_and_non_empty_text() -> None:
    assistant_message = LlmMessage(
        role=LlmRole.ASSISTANT,
        parts=(TextPart("answer"),),
    )
    with pytest.raises(LlmRequestError) as request_exc:
        LlmRequest(messages=(assistant_message,))
    assert request_exc.value.context.code is ErrorCode.LLM_REQUEST_FAILED

    with pytest.raises(LlmRequestError):
        TextPart("  ")


def test_usage_derives_total_only_from_complete_components() -> None:
    complete_usage = LlmUsage(input_tokens=10, output_tokens=5)
    partial_usage = LlmUsage(input_tokens=10)
    provider_total = LlmUsage(input_tokens=10, output_tokens=5, total_tokens=20)

    assert complete_usage.total_tokens == 15
    assert partial_usage.total_tokens is None
    assert provider_total.total_tokens == 20


def test_usage_preserves_provider_reported_cost() -> None:
    usage = LlmUsage(reported_cost=0.0125)
    assert usage.reported_cost == 0.0125


def test_error_categories_and_attempt_observer_protocol() -> None:
    rate_limit = LlmRateLimitError("slow down", retry_after_s=2.5)
    unavailable = LlmProviderUnavailableError("maintenance", retry_after_s=5.0)
    config_error = LlmConfigError("bad config")

    assert isinstance(rate_limit, TransientError)
    assert rate_limit.retry_after_s == 2.5
    assert rate_limit.context.code is ErrorCode.LLM_RATE_LIMITED
    assert unavailable.retry_after_s == 5.0
    assert isinstance(config_error, FatalError)
    assert isinstance(FakeObserver(), LlmAttemptObserver)
