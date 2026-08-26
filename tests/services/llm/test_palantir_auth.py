from __future__ import annotations

import os
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from anishift.config.settings import Settings
from anishift.errors import ErrorCode
from anishift.services.llm.engines.palantir import (
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
    PALANTIR_TOKEN_ENV_VAR,
    PALANTIR_TOKEN_ENV_VARS,
    REDACTED_HEADER_VALUE,
    PalantirHttpRequest,
    PalantirModelConfig,
    authorization_headers,
    build_palantir_request,
    palantir_model_config,
    palantir_status_error,
    redacted_headers,
    require_palantir_token,
    resolve_palantir_token,
)
from anishift.services.llm.errors import LlmAuthError, LlmError
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart
from anishift.services.llm.wire_protocol import ModelProtocol

_CANARY = "palantir-canary-value-c0ffee"
_ENROLLMENT = "https://example.palantirfoundry.com"
_ROUTE = "/api/v2/llm/proxy/openai/v1"
_CANONICAL_NAME = "ANISHIFT_PALANTIR_TOKEN"
_COMPAT_NAME = "FOUNDRY_API_TOKEN"
_CANONICAL_VALUE = "canonical-value"
_COMPAT_VALUE = "compatibility-value"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, raising=False)


def _config(token: str = _CANARY) -> PalantirModelConfig:
    return palantir_model_config(
        alias="foundry/gpt-main",
        provider_id="foundry-openai",
        protocol=ModelProtocol.OPENAI_CHAT,
        enrollment_base_url=_ENROLLMENT,
        provider_path=_ROUTE,
        provider_model_id="gpt-main-5",
        token=token,
    )


def _request() -> LlmRequest:
    return LlmRequest(
        messages=(LlmMessage(role=LlmRole.USER, parts=(TextPart(text="Translate this line."),)),),
    )


def test_canonical_and_compatibility_variable_names_are_the_documented_ones() -> None:
    assert PALANTIR_TOKEN_ENV_VAR == _CANONICAL_NAME
    assert PALANTIR_TOKEN_COMPAT_ENV_VAR == _COMPAT_NAME
    assert PALANTIR_TOKEN_ENV_VARS == (PALANTIR_TOKEN_ENV_VAR, PALANTIR_TOKEN_COMPAT_ENV_VAR)


def test_resolve_palantir_token_prefers_the_canonical_variable() -> None:
    environ = {PALANTIR_TOKEN_ENV_VAR: "canonical", PALANTIR_TOKEN_COMPAT_ENV_VAR: "compatibility"}

    assert resolve_palantir_token(environ) == "canonical"


def test_resolve_palantir_token_reads_the_compatibility_variable_when_the_canonical_one_is_absent() -> None:
    assert resolve_palantir_token({PALANTIR_TOKEN_COMPAT_ENV_VAR: "compatibility"}) == "compatibility"


def test_resolve_palantir_token_skips_a_blank_canonical_value_and_strips_the_result() -> None:
    environ = {PALANTIR_TOKEN_ENV_VAR: "   ", PALANTIR_TOKEN_COMPAT_ENV_VAR: "  compatibility  "}

    assert resolve_palantir_token(environ) == "compatibility"


def test_resolve_palantir_token_returns_empty_when_neither_variable_is_configured() -> None:
    assert resolve_palantir_token({}) == ""
    assert resolve_palantir_token() == ""


def test_resolve_palantir_token_reads_the_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, "from-process")

    assert resolve_palantir_token() == "from-process"

    monkeypatch.setenv(PALANTIR_TOKEN_ENV_VAR, "from-process-canonical")

    assert resolve_palantir_token() == "from-process-canonical"


def test_require_palantir_token_raises_a_typed_auth_error_naming_the_canonical_variable() -> None:
    with pytest.raises(LlmAuthError) as rejected:
        require_palantir_token({})

    assert rejected.value.context.code is ErrorCode.LLM_AUTH_FAILED
    assert rejected.value.context.details["field"] == PALANTIR_TOKEN_ENV_VAR
    assert PALANTIR_TOKEN_ENV_VAR in rejected.value.context.suggestion
    assert PALANTIR_TOKEN_COMPAT_ENV_VAR not in rejected.value.context.suggestion


@pytest.mark.parametrize(
    ("canonical", "compatibility", "expected"),
    [
        (_CANONICAL_VALUE, _COMPAT_VALUE, _CANONICAL_VALUE),
        (_CANONICAL_VALUE, "", _CANONICAL_VALUE),
        ("", _COMPAT_VALUE, _COMPAT_VALUE),
        ("   ", _COMPAT_VALUE, _COMPAT_VALUE),
        ("\t\n", _COMPAT_VALUE, _COMPAT_VALUE),
        (f"  {_CANONICAL_VALUE}  ", _COMPAT_VALUE, _CANONICAL_VALUE),
        ("   ", f"  {_COMPAT_VALUE}  ", _COMPAT_VALUE),
        ("", "", ""),
        ("   ", "   ", ""),
    ],
)
def test_settings_and_the_auth_module_resolve_one_environment_identically(
    monkeypatch: pytest.MonkeyPatch,
    canonical: str,
    compatibility: str,
    expected: str,
) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_ENV_VAR, canonical)
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, compatibility)

    assert resolve_palantir_token() == expected
    assert Settings(_env_file=None).palantir_token == expected


def test_settings_delegates_precedence_instead_of_declaring_a_second_mechanism() -> None:
    token_field = Settings.model_fields["palantir_token"]

    assert token_field.validation_alias is None
    assert Settings.model_config.get("populate_by_name") is not True
    assert PALANTIR_TOKEN_ENV_VARS == (PALANTIR_TOKEN_ENV_VAR, PALANTIR_TOKEN_COMPAT_ENV_VAR)


def test_settings_canonical_variable_matches_the_prefixed_field_name() -> None:
    prefix = Settings.model_config.get("env_prefix", "")

    assert f"{prefix}palantir_token".upper() == PALANTIR_TOKEN_ENV_VAR
    assert "palantir_token" in Settings.model_fields


def test_settings_prefers_the_canonical_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, _COMPAT_VALUE)

    assert Settings(_env_file=None).palantir_token == _COMPAT_VALUE

    monkeypatch.setenv(PALANTIR_TOKEN_ENV_VAR, _CANONICAL_VALUE)

    assert Settings(_env_file=None).palantir_token == _CANONICAL_VALUE


def test_settings_reads_both_names_from_an_isolated_env_file(tmp_path: Path) -> None:
    compat_file = tmp_path / "compat.env"
    compat_file.write_text(f'{PALANTIR_TOKEN_COMPAT_ENV_VAR}="{_COMPAT_VALUE}"\n', encoding="utf-8")
    both_file = tmp_path / "both.env"
    both_file.write_text(
        f'{PALANTIR_TOKEN_COMPAT_ENV_VAR}="{_COMPAT_VALUE}"\n{PALANTIR_TOKEN_ENV_VAR}="{_CANONICAL_VALUE}"\n',
        encoding="utf-8",
    )

    assert Settings(_env_file=compat_file).palantir_token == _COMPAT_VALUE
    assert Settings(_env_file=both_file).palantir_token == _CANONICAL_VALUE


def test_a_canonical_value_in_the_env_file_beats_a_stale_exported_compatibility_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, "stale-exported-value")
    canonical_file = tmp_path / "canonical.env"
    canonical_file.write_text(f'{PALANTIR_TOKEN_ENV_VAR}="{_CANONICAL_VALUE}"\n', encoding="utf-8")

    assert Settings(_env_file=canonical_file).palantir_token == _CANONICAL_VALUE


def test_a_blank_canonical_value_in_the_env_file_falls_back_to_the_compatibility_variable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, _COMPAT_VALUE)
    blank_file = tmp_path / "blank.env"
    blank_file.write_text(f'{PALANTIR_TOKEN_ENV_VAR}="   "\n', encoding="utf-8")

    assert Settings(_env_file=blank_file).palantir_token == _COMPAT_VALUE


def test_settings_clears_the_compatibility_field_after_folding_it_into_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_COMPAT_ENV_VAR, _CANARY)
    settings = Settings(_env_file=None)

    assert settings.palantir_token == _CANARY
    assert settings.palantir_token_compat == ""
    assert "palantir_token_compat" not in settings.model_dump()
    assert _CANARY not in repr(settings)
    assert _CANARY not in str(settings)


def test_settings_defaults_to_an_empty_token_and_keeps_other_secrets_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANISHIFT_GEMINI_API_KEY", "gemini-value")
    settings = Settings(_env_file=None)

    assert settings.palantir_token == ""
    assert settings.gemini_api_key == "gemini-value"


def test_settings_still_accepts_every_field_by_its_name() -> None:
    settings = Settings(_env_file=None, palantir_token=_CANARY, gemini_api_key="gemini-value")

    assert settings.palantir_token == _CANARY
    assert settings.gemini_api_key == "gemini-value"


def test_settings_keeps_the_palantir_token_out_of_its_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_ENV_VAR, _CANARY)
    settings = Settings(_env_file=None)

    assert _CANARY not in repr(settings)
    assert _CANARY not in str(settings)
    assert settings.palantir_token == _CANARY


def test_authorization_headers_carry_one_bearer_token_and_json_negotiation() -> None:
    headers = authorization_headers(_CANARY)

    assert headers == {
        "Authorization": f"Bearer {_CANARY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@pytest.mark.parametrize("token", ["", "   ", "with space", "with\ttab", "with\nnewline", "bad\x00byte"])
def test_authorization_headers_reject_a_token_that_cannot_be_sent(token: str) -> None:
    with pytest.raises(LlmAuthError) as rejected:
        authorization_headers(token)

    assert rejected.value.context.code is ErrorCode.LLM_AUTH_FAILED
    assert rejected.value.context.details["field"] == PALANTIR_TOKEN_ENV_VAR


def test_redacted_headers_replace_the_whole_authorization_value() -> None:
    masked = redacted_headers(authorization_headers(_CANARY))

    assert masked["Authorization"] == REDACTED_HEADER_VALUE
    assert masked["Content-Type"] == "application/json"
    assert _CANARY not in repr(masked)
    assert _CANARY[:8] not in repr(masked)


def test_the_token_never_reaches_reprs_errors_or_debug_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PALANTIR_TOKEN_ENV_VAR, _CANARY)
    captured: list[str] = []
    handler_id = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    try:
        token = require_palantir_token()
        config = _config(token)
        built: PalantirHttpRequest = build_palantir_request(config, _request())
        masked = redacted_headers(built.headers)
        settings = Settings(_env_file=None)
        failure: LlmError = palantir_status_error(
            401,
            alias=config.alias,
            payload={"error": {"code": "unauthorized", "token": _CANARY}},
        )
        with pytest.raises(LlmAuthError) as missing:
            _config("")
    finally:
        loguru_logger.remove(handler_id)

    surfaces = [
        repr(config),
        str(config),
        repr(built),
        str(built),
        repr(masked),
        repr(settings),
        str(failure),
        repr(failure),
        repr(failure.context),
        str(missing.value),
        repr(missing.value),
        repr(missing.value.context),
        *captured,
    ]

    assert captured
    assert token == _CANARY
    assert built.headers["Authorization"] == f"Bearer {_CANARY}"
    assert all(_CANARY not in surface for surface in surfaces)
    assert all("Bearer" not in surface for surface in captured)
