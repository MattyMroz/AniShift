from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, cast

import httpx
import pytest

from anishift.config.model_catalog import ModelCatalog, parse_model_catalog
from anishift.config.model_catalog import ModelProtocol as CatalogModelProtocol
from anishift.errors import ErrorCode, FatalError, TransientError
from anishift.services.llm.engines.palantir import (
    PalantirGenerationOptions,
    PalantirHttpRequest,
    PalantirModelConfig,
    PalantirResponseDefect,
    build_palantir_request,
    palantir_blocked_error,
    palantir_model_config,
    palantir_response_error,
    palantir_status_error,
    palantir_timeout_error,
    palantir_unavailable_error,
    request_builder,
)
from anishift.services.llm.engines.palantir import auth as palantir_auth
from anishift.services.llm.engines.palantir import config as palantir_config
from anishift.services.llm.engines.palantir import errors as palantir_errors
from anishift.services.llm.engines.palantir import protocols as palantir_protocols
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart
from anishift.services.llm.wire_protocol import ModelProtocol

_CANARY = "palantir-canary-value-c0ffee"
_ENROLLMENT = "https://example.palantirfoundry.com"
_ROUTE = "/api/v2/llm/proxy/openai/v1"
_PROVIDER_SDK_ROOTS = frozenset({"anthropic", "deepl", "elevenlabs", "google", "openai"})
_HEAVY_ROOTS = _PROVIDER_SDK_ROOTS | {"httpcore", "httpx"}
_SHARED_ENGINE_MODULES = frozenset(
    {
        "anishift.services.llm.engines",
        "anishift.services.llm.engines._sdk_helpers",
    },
)
_IMPORT_PROBE = (
    "import json, sys\n"
    "before = set(sys.modules)\n"
    "import {module}\n"
    "print(json.dumps(sorted(set(sys.modules) - before)))\n"
)


def _modules_added_by_importing(module: str) -> list[str]:
    completed = subprocess.run(  # noqa: S603 - fixed probe script on this interpreter
        [sys.executable, "-c", _IMPORT_PROBE.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return cast("list[str]", json.loads(completed.stdout))


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)


@dataclass(frozen=True, slots=True)
class _UnsupportedPart:
    kind: str


def _config(
    *,
    protocol: ModelProtocol = ModelProtocol.OPENAI_CHAT,
    enrollment_base_url: str = _ENROLLMENT,
    provider_path: str = _ROUTE,
    provider_model_id: str = "gpt-main-5",
    token: str = _CANARY,
) -> PalantirModelConfig:
    return palantir_model_config(
        alias="foundry/gpt-main",
        provider_id="foundry-openai",
        protocol=protocol,
        enrollment_base_url=enrollment_base_url,
        provider_path=provider_path,
        provider_model_id=provider_model_id,
        token=token,
    )


def _request() -> LlmRequest:
    return LlmRequest(
        messages=(
            LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart(text="You translate subtitles."),)),
            LlmMessage(
                role=LlmRole.USER,
                parts=(TextPart(text="First line."), TextPart(text="Second line.")),
            ),
            LlmMessage(role=LlmRole.ASSISTANT, parts=(TextPart(text="Ready."),)),
        ),
    )


def _catalog_source(providers: dict[str, Any], models: dict[str, Any]) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "enrollment": {"base_url": _ENROLLMENT},
            "providers": providers,
            "models": models,
        },
    )


def test_palantir_model_config_joins_the_enrollment_address_with_the_provider_route() -> None:
    config = _config()

    assert config.base_url == f"{_ENROLLMENT}{_ROUTE}"
    assert config.protocol is ModelProtocol.OPENAI_CHAT
    assert config.provider_model_id == "gpt-main-5"


def test_palantir_model_config_keeps_an_enrollment_path_prefix_and_normalizes_slashes() -> None:
    config = _config(
        enrollment_base_url="https://example.palantirfoundry.com/tenant/",
        provider_path="/api/v2/llm/proxy/openai/v1/",
    )

    assert config.base_url == "https://example.palantirfoundry.com/tenant/api/v2/llm/proxy/openai/v1"


def test_palantir_model_config_rejects_a_missing_token_before_any_request() -> None:
    with pytest.raises(LlmAuthError) as rejected:
        _config(token="")

    assert rejected.value.context.code is ErrorCode.LLM_AUTH_FAILED
    assert rejected.value.context.details["field"] == palantir_auth.PALANTIR_TOKEN_ENV_VAR
    assert isinstance(rejected.value, FatalError)
    assert palantir_auth.PALANTIR_TOKEN_ENV_VAR in rejected.value.context.suggestion


@pytest.mark.parametrize("token", ["   ", "with space", "with\ttab", "with\nnewline", "bad\x00byte"])
def test_palantir_model_config_rejects_a_token_that_cannot_be_sent_in_a_header(token: str) -> None:
    with pytest.raises(LlmAuthError) as rejected:
        _config(token=token)

    assert rejected.value.context.code is ErrorCode.LLM_AUTH_FAILED
    assert token not in str(rejected.value)
    assert token not in repr(rejected.value.context)


def test_only_a_token_failure_is_an_auth_error_and_every_other_defect_is_a_configuration_error() -> None:
    with pytest.raises(LlmAuthError):
        _config(token="")
    with pytest.raises(LlmConfigError):
        _config(enrollment_base_url="http://example.palantirfoundry.com")
    with pytest.raises(LlmConfigError):
        _config(provider_path="https://elsewhere.example.com/v1")
    with pytest.raises(LlmConfigError):
        _config(provider_model_id="  ")
    with pytest.raises(LlmConfigError):
        _config(protocol=cast("ModelProtocol", "made_up_protocol"))
    with pytest.raises(LlmConfigError):
        request_builder(cast("ModelProtocol", "made_up_protocol"))


@pytest.mark.parametrize(
    ("alias", "provider_id", "provider_model_id"),
    [
        ("", "foundry-openai", "gpt-main-5"),
        ("foundry/gpt-main", "  ", "gpt-main-5"),
        ("foundry/gpt-main", "foundry-openai", ""),
    ],
)
def test_palantir_model_config_rejects_a_blank_identifier(
    alias: str,
    provider_id: str,
    provider_model_id: str,
) -> None:
    with pytest.raises(LlmConfigError) as rejected:
        palantir_model_config(
            alias=alias,
            provider_id=provider_id,
            protocol=ModelProtocol.OPENAI_CHAT,
            enrollment_base_url=_ENROLLMENT,
            provider_path=_ROUTE,
            provider_model_id=provider_model_id,
            token=_CANARY,
        )

    assert rejected.value.context.code is ErrorCode.LLM_CONFIG_INVALID


@pytest.mark.parametrize(
    "enrollment_base_url",
    [
        "http://example.palantirfoundry.com",
        "example.palantirfoundry.com",
        "https://example.palantirfoundry.com/?tenant=1",
        "https://example.palantirfoundry.com/#fragment",
        "",
    ],
)
def test_palantir_model_config_rejects_an_enrollment_address_that_is_not_plain_https(
    enrollment_base_url: str,
) -> None:
    with pytest.raises(LlmConfigError) as rejected:
        _config(enrollment_base_url=enrollment_base_url)

    assert rejected.value.context.details["field"] == "base_url"


@pytest.mark.parametrize(
    "provider_path",
    [
        "https://other.example.com/v1",
        "api/v2/llm/proxy/openai/v1",
        "/api/v2/llm/proxy/openai/v1?beta=1",
        "/api/v2/llm/proxy/openai/v1#anchor",
    ],
)
def test_palantir_model_config_rejects_a_provider_route_that_is_not_relative(provider_path: str) -> None:
    with pytest.raises(LlmConfigError) as rejected:
        _config(provider_path=provider_path)

    assert rejected.value.context.details["field"] == "provider_path"


def test_palantir_model_config_rejects_a_protocol_outside_the_catalog_vocabulary() -> None:
    with pytest.raises(LlmConfigError) as rejected:
        _config(protocol=cast("ModelProtocol", "cohere_chat"))

    assert rejected.value.context.details["field"] == "protocol"


def test_palantir_model_config_keeps_the_token_out_of_its_repr() -> None:
    config = _config()

    assert _CANARY not in repr(config)
    assert _CANARY not in str(config)
    assert config.token == _CANARY


def test_model_catalog_load_keeps_an_unsupported_protocol_visible_as_a_configuration_issue() -> None:
    source = _catalog_source(
        {
            "foundry-openai": {"protocol": "openai_chat", "path": _ROUTE},
            "foundry-legacy": {"protocol": "cohere_chat", "path": "/api/v2/llm/proxy/legacy/v1"},
        },
        {
            "foundry/gpt-main": {"provider": "foundry-openai", "model": "gpt-main-5"},
            "foundry/legacy": {"provider": "foundry-legacy", "model": "legacy-1"},
        },
    )

    catalog: ModelCatalog = parse_model_catalog(source)

    assert set(catalog.providers) == {"foundry-openai"}
    assert set(catalog.models) == {"foundry/gpt-main"}
    assert {issue.key for issue in catalog.issues} == {"foundry-legacy", "foundry/legacy"}


def test_request_builder_covers_every_protocol_the_catalog_can_declare() -> None:
    builders = {protocol: request_builder(protocol) for protocol in ModelProtocol}

    assert len(builders) == 4
    assert all(callable(builder) for builder in builders.values())
    assert len(set(builders.values())) == 4


def test_request_builder_rejects_a_protocol_outside_the_catalog_vocabulary() -> None:
    with pytest.raises(LlmConfigError) as rejected:
        request_builder(cast("ModelProtocol", "cohere_chat"))

    assert rejected.value.context.details["field"] == "protocol"
    assert "openai_chat" in rejected.value.context.suggestion


def test_openai_chat_request_posts_to_chat_completions_with_the_openai_output_limit() -> None:
    config = _config(protocol=ModelProtocol.OPENAI_CHAT)

    built: PalantirHttpRequest = build_palantir_request(
        config,
        _request(),
        PalantirGenerationOptions(temperature=0.2, top_p=0.9, max_output_tokens=512),
    )

    assert built.method == "POST"
    assert built.url == f"{_ENROLLMENT}{_ROUTE}/chat/completions"
    assert built.headers["Authorization"] == f"Bearer {_CANARY}"
    assert built.headers["Content-Type"] == "application/json"
    assert built.body["model"] == "gpt-main-5"
    assert built.body["messages"] == [
        {"role": "system", "content": "You translate subtitles."},
        {"role": "user", "content": "First line.\nSecond line."},
        {"role": "assistant", "content": "Ready."},
    ]
    assert built.body["max_completion_tokens"] == 512
    assert built.body["temperature"] == 0.2
    assert built.body["top_p"] == 0.9
    assert "max_tokens" not in built.body


def test_xai_chat_request_uses_the_compatible_output_limit_keyword() -> None:
    config = _config(
        protocol=ModelProtocol.XAI_CHAT,
        provider_path="/api/v2/llm/proxy/xai/v1",
        provider_model_id="grok-4",
    )

    built = build_palantir_request(config, _request(), PalantirGenerationOptions(max_output_tokens=256))

    assert built.url == f"{_ENROLLMENT}/api/v2/llm/proxy/xai/v1/chat/completions"
    assert built.body["max_tokens"] == 256
    assert "max_completion_tokens" not in built.body


def test_chat_completions_request_omits_generation_limits_that_are_unset() -> None:
    built = build_palantir_request(_config(), _request())

    assert set(built.body) == {"model", "messages"}


def test_anthropic_messages_request_hoists_system_content_and_always_sets_max_tokens() -> None:
    config = _config(
        protocol=ModelProtocol.ANTHROPIC_MESSAGES,
        provider_path="/api/v2/llm/proxy/anthropic/v1",
        provider_model_id="claude-sonnet-5",
    )

    built = build_palantir_request(config, _request())

    assert built.url == f"{_ENROLLMENT}/api/v2/llm/proxy/anthropic/v1/messages"
    assert built.headers["anthropic-version"] == "2023-06-01"
    assert built.body["system"] == [{"type": "text", "text": "You translate subtitles."}]
    assert built.body["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "First line."}, {"type": "text", "text": "Second line."}],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "Ready."}]},
    ]
    assert isinstance(built.body["max_tokens"], int)
    assert built.body["max_tokens"] > 0


def test_google_generate_request_encodes_the_model_in_the_route_and_maps_roles() -> None:
    config = _config(
        protocol=ModelProtocol.GOOGLE_GENERATE,
        provider_path="/api/v2/llm/proxy/google/v1",
        provider_model_id="ri.models.main:gemini-3-pro",
    )

    built = build_palantir_request(config, _request(), PalantirGenerationOptions(top_p=0.8, max_output_tokens=128))

    assert built.url == (
        f"{_ENROLLMENT}/api/v2/llm/proxy/google/v1/models/ri.models.main%3Agemini-3-pro:generateContent"
    )
    assert built.body["systemInstruction"] == {"parts": [{"text": "You translate subtitles."}]}
    assert built.body["contents"] == [
        {"role": "user", "parts": [{"text": "First line."}, {"text": "Second line."}]},
        {"role": "model", "parts": [{"text": "Ready."}]},
    ]
    assert built.body["generationConfig"] == {"topP": 0.8, "maxOutputTokens": 128}


@pytest.mark.parametrize("protocol", list(ModelProtocol))
def test_every_protocol_rejects_an_unsupported_content_part(protocol: ModelProtocol) -> None:
    request = LlmRequest(
        messages=(
            LlmMessage(
                role=LlmRole.USER,
                parts=(cast("TextPart", _UnsupportedPart(kind="image")),),
            ),
        ),
    )

    with pytest.raises(LlmRequestError):
        build_palantir_request(_config(protocol=protocol), request)


@pytest.mark.parametrize("protocol", list(ModelProtocol))
def test_every_protocol_rejects_a_message_without_any_text_part(protocol: ModelProtocol) -> None:
    request = LlmRequest(messages=(LlmMessage(role=LlmRole.USER, parts=()),))

    with pytest.raises(LlmRequestError):
        build_palantir_request(_config(protocol=protocol), request)


@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (401, None, LlmAuthError),
        (403, None, LlmAuthError),
        (402, None, LlmPaymentError),
        (400, {"error": {"code": "insufficient_credits"}}, LlmPaymentError),
        (408, None, LlmTimeoutError),
        (429, None, LlmRateLimitError),
        (429, {"error": {"code": "insufficient_quota"}}, LlmQuotaError),
        (429, {"error": {"status": "resource_exhausted"}}, LlmRateLimitError),
        (404, None, LlmModelError),
        (400, {"error": {"code": "model_not_found"}}, LlmModelError),
        (400, {"error": {"code": "context_length_exceeded"}}, LlmContextLengthError),
        (413, None, LlmContextLengthError),
        (400, {"error": {"type": "content_filter"}}, LlmOutputBlockedError),
        (500, None, LlmProviderUnavailableError),
        (503, None, LlmProviderUnavailableError),
        (418, None, LlmRequestError),
        (400, None, LlmRequestError),
    ],
)
def test_status_errors_map_onto_the_existing_llm_taxonomy(
    status_code: int,
    payload: object,
    expected: type[LlmError],
) -> None:
    error = palantir_status_error(status_code, alias="foundry/gpt-main", payload=payload)

    assert type(error) is expected
    assert error.context.details["alias"] == "foundry/gpt-main"
    assert error.context.details["engine_id"] == "palantir"


@pytest.mark.parametrize(
    ("status_code", "transient"),
    [(401, False), (404, False), (429, True), (500, True), (408, True), (400, False)],
)
def test_status_errors_keep_the_retry_semantics_of_the_taxonomy(status_code: int, transient: bool) -> None:
    error = palantir_status_error(status_code, alias="foundry/gpt-main")

    assert isinstance(error, TransientError) is transient
    assert isinstance(error, FatalError) is not transient


def test_rate_limited_and_unavailable_errors_carry_the_retry_hint() -> None:
    limited = palantir_status_error(429, alias="foundry/gpt-main", retry_after_s=12.5)
    unavailable = palantir_unavailable_error(alias="foundry/gpt-main", retry_after_s=3.0)

    assert isinstance(limited, LlmRateLimitError)
    assert limited.retry_after_s == 12.5
    assert isinstance(unavailable, LlmProviderUnavailableError)
    assert unavailable.retry_after_s == 3.0


def test_status_errors_never_render_the_response_payload() -> None:
    payload = {"error": {"message": "prompt was: secret subtitle line", "code": "model_not_found"}}

    error = palantir_status_error(404, alias="foundry/gpt-main", payload=payload)

    assert "secret subtitle line" not in str(error)
    assert "secret subtitle line" not in repr(error)
    assert "secret subtitle line" not in repr(error.context)


def test_response_and_blocked_errors_report_only_a_safe_label() -> None:
    malformed = palantir_response_error(alias="foundry/gpt-main", defect=PalantirResponseDefect.EMPTY_TEXT)
    blocked = palantir_blocked_error(alias="foundry/gpt-main", finish_reason="SAFETY")
    timed_out = palantir_timeout_error(alias="foundry/gpt-main")

    assert isinstance(malformed, LlmRequestError)
    assert malformed.context.details["defect"] == "empty_text"
    assert isinstance(blocked, LlmOutputBlockedError)
    assert blocked.context.details["finish_reason"] == "safety"
    assert isinstance(timed_out, LlmTimeoutError)


def test_configuration_and_request_building_create_no_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Palantir configuration must not create an HTTP client")

    monkeypatch.setattr(httpx, "Client", _forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", _forbidden)

    for protocol in ModelProtocol:
        built = build_palantir_request(_config(protocol=protocol), _request())
        assert built.url.startswith(_ENROLLMENT)

    for module in (palantir_auth, palantir_config, palantir_errors, palantir_protocols):
        assert not hasattr(module, "httpx")


def test_importing_the_palantir_package_loads_no_http_client_no_sdk_and_no_other_engine() -> None:
    added = _modules_added_by_importing("anishift.services.llm.engines.palantir")

    heavy = [name for name in added if name.split(".")[0] in _HEAVY_ROOTS]
    other_engines = [
        name
        for name in added
        if name.startswith("anishift.services.llm.engines.")
        and not name.startswith("anishift.services.llm.engines.palantir")
        and name not in _SHARED_ENGINE_MODULES
    ]
    configuration_layer = [name for name in added if name.startswith("anishift.config")]

    assert added
    assert heavy == []
    assert other_engines == []
    assert configuration_layer == []


def test_the_shared_wire_protocol_module_is_a_leaf_the_configuration_layer_can_import() -> None:
    added = _modules_added_by_importing("anishift.services.llm.wire_protocol")

    heavy = [name for name in added if name.split(".")[0] in _HEAVY_ROOTS]
    configuration_layer = [name for name in added if name.startswith("anishift.config")]

    assert "anishift.services.llm.wire_protocol" in added
    assert heavy == []
    assert configuration_layer == []


def test_importing_the_model_catalog_reaches_no_provider_sdk_and_no_provider_engine() -> None:
    added = _modules_added_by_importing("anishift.config.model_catalog")

    provider_sdks = [name for name in added if name.split(".")[0] in _PROVIDER_SDK_ROOTS]
    provider_engines = [
        name
        for name in added
        if name.startswith("anishift.services.llm.engines.")
        and not name.startswith("anishift.services.llm.engines.palantir")
        and name not in _SHARED_ENGINE_MODULES
    ]

    assert "anishift.services.llm.wire_protocol" in added
    assert provider_sdks == []
    assert provider_engines == []


def test_the_model_catalog_reexports_the_shared_wire_protocol_enum() -> None:
    assert CatalogModelProtocol is ModelProtocol
    assert tuple(CatalogModelProtocol) == tuple(ModelProtocol)
