from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.config import model_catalog
from anishift.config.model_catalog import (
    CATALOG_EXAMPLE_FILE_NAME,
    CATALOG_FILE_NAME,
    CATALOG_SCHEMA_VERSION,
    CatalogDefaults,
    CatalogIssue,
    ModelCatalog,
    ModelCatalogError,
    ModelEntry,
    ModelLimits,
    ModelProtocol,
    ProviderEntry,
    ensure_model_catalog_file,
    load_model_catalog,
    model_catalog_example_path,
    model_catalog_path,
    parse_model_catalog,
)
from anishift.errors import ErrorCode

_POLISH_LETTERS: Final[re.Pattern[str]] = re.compile(
    r"[\u0104-\u0107\u0118\u0119\u0141\u0142\u0143\u0144"
    r"\u00d3\u00f3\u015a\u015b\u0179-\u017c]"
)

_POLISH_LABEL: Final[str] = "Foundry: model główny"

_SECRET_LIKE_FIELD_NAMES = (
    "token",
    "api_key",
    "apiKey",
    "Authorization",
    "access_token",
    "client-secret",
    "password",
    "private_key",
    "credentials",
)


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "providers": {
            "foundry-openai": {"protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1"},
            "foundry-anthropic": {"protocol": "anthropic_messages", "path": "/api/v2/llm/proxy/anthropic/v1"},
        },
        "models": {
            "foundry/gpt-main": {
                "provider": "foundry-openai",
                "model": "exact-model-id-or-rid",
                "label": "Foundry: model główny",
                "experimental": False,
                "limits": {"context": 128000, "input": None, "output": 4096},
            },
        },
        "defaults": {"primary": "foundry/gpt-main", "translation": "foundry/gpt-main"},
    }
    payload.update(overrides)
    return payload


def _source(**overrides: Any) -> str:
    return json.dumps(_payload(**overrides), ensure_ascii=False)


def _issue_keys(catalog: ModelCatalog) -> set[str]:
    return {issue.key for issue in catalog.issues}


@pytest.fixture
def catalog_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(model_catalog, "config_path", lambda: tmp_path / "settings.json")
    return tmp_path


def test_parse_exposes_schema_providers_models_and_defaults() -> None:
    catalog = parse_model_catalog(_source())

    assert catalog.schema_version == CATALOG_SCHEMA_VERSION
    assert catalog.providers["foundry-openai"] == ProviderEntry(
        provider_id="foundry-openai",
        protocol=ModelProtocol.OPENAI_CHAT,
        path="/api/v2/llm/proxy/openai/v1",
    )
    assert catalog.models["foundry/gpt-main"] == ModelEntry(
        alias="foundry/gpt-main",
        provider_id="foundry-openai",
        model_id="exact-model-id-or-rid",
        label="Foundry: model główny",
        experimental=False,
        limits=ModelLimits(context=128000, input=None, output=4096),
    )
    assert catalog.defaults == CatalogDefaults(primary="foundry/gpt-main", translation="foundry/gpt-main")
    assert catalog.issues == ()


def test_parse_keeps_provider_proxy_path_relative() -> None:
    catalog = parse_model_catalog(_source())

    assert all(entry.path.startswith("/") for entry in catalog.providers.values())
    assert all("://" not in entry.path for entry in catalog.providers.values())


def test_parse_accepts_the_four_supported_protocols() -> None:
    providers = {
        "foundry-openai": {"protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1"},
        "foundry-anthropic": {"protocol": "anthropic_messages", "path": "/api/v2/llm/proxy/anthropic/v1"},
        "foundry-google": {"protocol": "google_generate", "path": "/api/v2/llm/proxy/google/v1"},
        "foundry-xai": {"protocol": "xai_responses", "path": "/api/v2/llm/proxy/xai/v1"},
    }

    catalog = parse_model_catalog(_source(providers=providers))

    assert {entry.protocol for entry in catalog.providers.values()} == set(ModelProtocol)
    assert catalog.issues == ()


def test_parse_reads_jsonc_comments_and_trailing_commas() -> None:
    source = """
    // Local catalog
    {
      "schema_version": 1,
      /* relative proxy routes only */
      "providers": {
        "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" },
      },
      "models": {
        "foundry/gpt-main": { "provider": "foundry-openai", "model": "id-1" },
      },
      "defaults": { "primary": "foundry/gpt-main" },
    }
    """

    catalog = parse_model_catalog(source)

    assert catalog.issues == ()
    assert catalog.models["foundry/gpt-main"].model_id == "id-1"


def test_parse_rejects_a_duplicate_model_alias() -> None:
    source = """
    {
      "schema_version": 1,
      "providers": { "p": { "protocol": "openai_chat", "path": "/v1" } },
      "models": {
        "foundry/gpt-main": { "provider": "p", "model": "id-1" },
        "foundry/gpt-main": { "provider": "p", "model": "id-2" }
      }
    }
    """

    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(source)

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert raised.value.context.suggestion


def test_parse_reports_an_unknown_provider_reference_and_keeps_the_alias_visible() -> None:
    models = {"foundry/ghost": {"provider": "foundry-missing", "model": "id-1"}}

    catalog = parse_model_catalog(_source(models=models, defaults={}))

    assert catalog.models == {}
    assert _issue_keys(catalog) == {"foundry/ghost"}
    assert "foundry-missing" in catalog.issues[0].message


def test_parse_reports_an_empty_model_identifier() -> None:
    models = {"foundry/gpt-main": {"provider": "foundry-openai", "model": "   "}}

    catalog = parse_model_catalog(_source(models=models, defaults={}))

    assert catalog.models == {}
    assert _issue_keys(catalog) == {"foundry/gpt-main"}
    assert "model identifier" in catalog.issues[0].message


def test_parse_keeps_an_unsupported_protocol_visible_without_falling_back() -> None:
    providers = {
        "foundry-openai": {"protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1"},
        "foundry-legacy": {"protocol": "cohere_chat", "path": "/api/v2/llm/proxy/legacy/v1"},
    }
    models = {
        "foundry/gpt-main": {"provider": "foundry-openai", "model": "id-1"},
        "foundry/legacy": {"provider": "foundry-legacy", "model": "id-2"},
    }

    catalog = parse_model_catalog(_source(providers=providers, models=models))

    assert set(catalog.providers) == {"foundry-openai"}
    assert set(catalog.models) == {"foundry/gpt-main"}
    assert _issue_keys(catalog) == {"foundry-legacy", "foundry/legacy"}
    assert any(issue.section == "providers" and "cohere_chat" in issue.message for issue in catalog.issues)
    assert any(issue.section == "models" and issue.key == "foundry/legacy" for issue in catalog.issues)


def test_parse_reports_a_provider_path_that_is_not_relative() -> None:
    providers = {"foundry-openai": {"protocol": "openai_chat", "path": "https://other.example.com/v1"}}

    catalog = parse_model_catalog(_source(providers=providers, models={}, defaults={}))

    assert catalog.providers == {}
    assert _issue_keys(catalog) == {"foundry-openai"}


def test_parse_reports_a_leftover_enrollment_section_as_an_unknown_root_key() -> None:
    catalog = parse_model_catalog(_source(enrollment={"base_url": "https://example.palantirfoundry.com"}))

    assert _issue_keys(catalog) == {"enrollment"}
    assert set(catalog.models) == {"foundry/gpt-main"}


def test_parse_reports_a_default_role_pointing_at_an_unknown_alias() -> None:
    catalog = parse_model_catalog(_source(defaults={"primary": "foundry/absent", "translation": "foundry/gpt-main"}))

    assert catalog.defaults.primary is None
    assert catalog.defaults.translation == "foundry/gpt-main"
    assert _issue_keys(catalog) == {"primary"}


@pytest.mark.parametrize("field_name", _SECRET_LIKE_FIELD_NAMES)
def test_parse_rejects_a_root_field_whose_name_suggests_a_secret(field_name: str) -> None:
    payload = _payload()
    payload[field_name] = "value-that-must-never-be-read"

    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(json.dumps(payload, ensure_ascii=False))

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert field_name in raised.value.context.message
    assert "value-that-must-never-be-read" not in raised.value.context.message


def test_parse_rejects_a_nested_field_whose_name_suggests_a_secret() -> None:
    models = {
        "foundry/gpt-main": {
            "provider": "foundry-openai",
            "model": "id-1",
            "headers": [{"authorization": "Bearer nope"}],
        },
    }

    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(_source(models=models))

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert "authorization" in raised.value.context.message


def test_parse_accepts_a_provider_id_that_ends_with_a_secret_word() -> None:
    providers = {"foundry-oauth": {"protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1"}}
    models = {"foundry/gpt-main": {"provider": "foundry-oauth", "model": "id-1"}}

    catalog = parse_model_catalog(_source(providers=providers, models=models))

    assert set(catalog.providers) == {"foundry-oauth"}
    assert catalog.models["foundry/gpt-main"].provider_id == "foundry-oauth"
    assert catalog.issues == ()


@pytest.mark.parametrize("alias", ["my-token", "nova-key", "foundry/turbo-secret", "team.credentials"])
def test_parse_accepts_a_model_alias_that_ends_with_a_secret_word(alias: str) -> None:
    models = {alias: {"provider": "foundry-openai", "model": "id-1"}}

    catalog = parse_model_catalog(_source(models=models, defaults={"primary": alias}))

    assert set(catalog.models) == {alias}
    assert catalog.defaults.primary == alias
    assert catalog.issues == ()


def test_parse_rejects_a_secret_field_inside_a_provider_entry() -> None:
    providers = {
        "foundry-openai": {
            "protocol": "openai_chat",
            "path": "/api/v2/llm/proxy/openai/v1",
            "token": "must-never-be-read",
        },
    }

    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(_source(providers=providers))

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert "token" in raised.value.context.message
    assert "must-never-be-read" not in raised.value.context.message


def test_parse_rejects_a_secret_field_inside_a_model_entry() -> None:
    models = {
        "foundry/gpt-main": {
            "provider": "foundry-openai",
            "model": "id-1",
            "api_key": "must-never-be-read",
        },
    }

    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(_source(models=models))

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert "api_key" in raised.value.context.message
    assert "must-never-be-read" not in raised.value.context.message


def test_parse_does_not_treat_a_plural_token_count_as_a_secret() -> None:
    catalog = parse_model_catalog(_source(max_tokens=1024))

    assert _issue_keys(catalog) == {"max_tokens"}
    assert catalog.models["foundry/gpt-main"].model_id == "exact-model-id-or-rid"


@pytest.mark.parametrize(
    "dto",
    [ProviderEntry, ModelEntry, ModelLimits, CatalogDefaults, CatalogIssue, ModelCatalog],
)
def test_catalog_dataclass_declares_no_secret_or_availability_field(dto: Any) -> None:
    forbidden = ("token", "api_key", "apikey", "authorization", "secret", "password", "credential")
    stateful = ("status", "available", "availability", "verified", "probe", "unverified")
    names = {name.casefold() for name in dto.__dataclass_fields__}

    assert not [name for name in names if any(word in name for word in forbidden)]
    assert not [name for name in names if any(word in name for word in stateful)]


def test_parse_rejects_an_unsupported_schema_version() -> None:
    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog(_source(schema_version=99))

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID


def test_parse_rejects_malformed_jsonc() -> None:
    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog('{"schema_version": 1, "providers": ')

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID


def test_parse_rejects_a_root_that_is_not_an_object() -> None:
    with pytest.raises(ModelCatalogError) as raised:
        parse_model_catalog("[1, 2, 3]")

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID


def test_parse_gives_omitted_model_fields_safe_defaults() -> None:
    models = {"foundry/gpt-main": {"provider": "foundry-openai", "model": "id-1"}}

    catalog = parse_model_catalog(_source(models=models, defaults={}))

    entry = catalog.models["foundry/gpt-main"]
    assert entry.label == "foundry/gpt-main"
    assert entry.experimental is False
    assert entry.limits == ModelLimits()
    assert catalog.defaults == CatalogDefaults()


def test_parse_keeps_a_model_whose_limit_value_is_invalid() -> None:
    models = {
        "foundry/gpt-main": {
            "provider": "foundry-openai",
            "model": "id-1",
            "limits": {"context": 0, "output": 4096},
        },
    }

    catalog = parse_model_catalog(_source(models=models))

    assert catalog.models["foundry/gpt-main"].limits == ModelLimits(context=None, input=None, output=4096)
    assert _issue_keys(catalog) == {"foundry/gpt-main"}


def test_parse_reports_an_unknown_root_key_without_losing_the_rest() -> None:
    catalog = parse_model_catalog(_source(modles={}))

    assert _issue_keys(catalog) == {"modles"}
    assert set(catalog.models) == {"foundry/gpt-main"}
    assert catalog.defaults.primary == "foundry/gpt-main"


@pytest.mark.usefixtures("catalog_dir")
def test_load_missing_runtime_file_raises_a_typed_error_with_instructions() -> None:
    with pytest.raises(ModelCatalogError) as raised:
        load_model_catalog()

    assert raised.value.context.code is ErrorCode.CONFIG_MISSING
    assert CATALOG_EXAMPLE_FILE_NAME in raised.value.context.suggestion
    assert not model_catalog_path().exists()


def test_load_reads_the_runtime_file(catalog_dir: Path) -> None:
    (catalog_dir / CATALOG_FILE_NAME).write_text(_source(), encoding="utf-8")

    catalog = load_model_catalog()

    assert catalog.models["foundry/gpt-main"].provider_id == "foundry-openai"


def test_ensure_creates_the_runtime_catalog_from_the_example(catalog_dir: Path) -> None:
    (catalog_dir / CATALOG_EXAMPLE_FILE_NAME).write_text(_source(), encoding="utf-8")

    created = ensure_model_catalog_file()

    assert created is True
    assert model_catalog_path().read_text(encoding="utf-8") == _source()
    assert load_model_catalog().issues == ()


def test_ensure_never_overwrites_a_valid_runtime_catalog(catalog_dir: Path) -> None:
    models = {"foundry/mine": {"provider": "foundry-openai", "model": "id-mine", "label": "Mój model"}}
    runtime_text = _source(models=models, defaults={"primary": "foundry/mine"})
    (catalog_dir / CATALOG_FILE_NAME).write_text(runtime_text, encoding="utf-8")
    (catalog_dir / CATALOG_EXAMPLE_FILE_NAME).write_text(_source(), encoding="utf-8")

    created = ensure_model_catalog_file()

    assert created is False
    assert model_catalog_path().read_text(encoding="utf-8") == runtime_text
    assert set(load_model_catalog().models) == {"foundry/mine"}


def test_ensure_never_overwrites_a_corrupt_runtime_catalog(catalog_dir: Path) -> None:
    corrupt = '{"schema_version": 1, "providers": '
    (catalog_dir / CATALOG_FILE_NAME).write_text(corrupt, encoding="utf-8")
    (catalog_dir / CATALOG_EXAMPLE_FILE_NAME).write_text(_source(), encoding="utf-8")

    created = ensure_model_catalog_file()

    assert created is False
    assert model_catalog_path().read_text(encoding="utf-8") == corrupt
    with pytest.raises(ModelCatalogError) as raised:
        load_model_catalog()
    assert raised.value.context.code is ErrorCode.CONFIG_INVALID


@pytest.mark.usefixtures("catalog_dir")
def test_ensure_without_an_example_raises_a_typed_error() -> None:
    with pytest.raises(ModelCatalogError) as raised:
        ensure_model_catalog_file()

    assert raised.value.context.code is ErrorCode.CONFIG_MISSING
    assert not model_catalog_path().exists()


def test_ensure_creates_the_configuration_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "config"
    nested.mkdir(parents=True)
    (nested / CATALOG_EXAMPLE_FILE_NAME).write_text(_source(), encoding="utf-8")
    monkeypatch.setattr(model_catalog, "config_path", lambda: nested / "child" / "settings.json")
    monkeypatch.setattr(
        model_catalog,
        "model_catalog_example_path",
        lambda: nested / CATALOG_EXAMPLE_FILE_NAME,
    )

    assert ensure_model_catalog_file() is True
    assert (nested / "child" / CATALOG_FILE_NAME).is_file()


def test_loading_and_filtering_the_catalog_performs_no_network_access(
    catalog_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (catalog_dir / CATALOG_FILE_NAME).write_text(_source(), encoding="utf-8")

    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("catalog loading must not touch the network")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)

    catalog = load_model_catalog()
    selected = [entry for entry in catalog.models.values() if entry.provider_id == "foundry-openai"]

    assert [entry.alias for entry in selected] == ["foundry/gpt-main"]


def test_shipped_example_catalog_is_valid_and_free_of_real_identifiers() -> None:
    catalog = parse_model_catalog(model_catalog_example_path().read_text(encoding="utf-8"))

    assert catalog.issues == ()
    assert {entry.protocol for entry in catalog.providers.values()} == set(ModelProtocol)
    assert catalog.defaults.primary in catalog.models
    assert catalog.defaults.translation in catalog.models
    assert all(entry.model_id.startswith("replace-with-") for entry in catalog.models.values())
    assert all(entry.path.startswith("/api/v2/llm/proxy/") for entry in catalog.providers.values())


def test_shipped_example_catalog_names_every_model_in_english() -> None:
    source: str = model_catalog_example_path().read_text(encoding="utf-8")
    catalog: ModelCatalog = parse_model_catalog(source)
    labels: list[str] = [entry.label for entry in catalog.models.values()]

    assert labels
    assert [label for label in labels if _POLISH_LETTERS.search(label)] == []
    assert [number for number, line in enumerate(source.splitlines(), 1) if _POLISH_LETTERS.search(line)] == []


def test_the_catalog_language_guard_flags_a_polish_label() -> None:
    assert _POLISH_LETTERS.search(_POLISH_LABEL) is not None
    assert _POLISH_LETTERS.search("Foundry: main model") is None
