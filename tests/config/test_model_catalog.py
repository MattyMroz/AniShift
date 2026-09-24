from __future__ import annotations

import re
import socket
from typing import Any, Final

import pytest

from anishift.config.model_catalog import (
    ModelCatalog,
    ModelEntry,
    ProviderEntry,
    load_model_catalog,
)
from anishift.services.llm.engines.palantir.constants import PALANTIR_MODELS, PALANTIR_PROVIDERS

_POLISH_LETTERS: Final[re.Pattern[str]] = re.compile(
    r"[\u0104-\u0107\u0118\u0119\u0141\u0142\u0143\u0144"
    r"\u00d3\u00f3\u015a\u015b\u0179-\u017c]"
)

_POLISH_LABEL: Final[str] = "Foundry: model główny"


@pytest.mark.unit
def test_load_model_catalog_maps_builtin_models() -> None:
    catalog: ModelCatalog = load_model_catalog()

    assert tuple(catalog.models) == tuple(model.alias for model in PALANTIR_MODELS)
    assert tuple(catalog.providers) == tuple(provider.provider_id for provider in PALANTIR_PROVIDERS)
    for provider in PALANTIR_PROVIDERS:
        assert catalog.providers[provider.provider_id] == ProviderEntry(
            provider.provider_id, provider.protocol, provider.path
        )
    for model in PALANTIR_MODELS:
        assert catalog.models[model.alias] == ModelEntry(
            alias=model.alias,
            provider_id=model.provider_id,
            model_id=model.model_id,
            label=model.label,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "dto",
    [ProviderEntry, ModelEntry, ModelCatalog],
)
def test_catalog_dataclass_declares_no_secret_or_availability_field(dto: Any) -> None:
    forbidden = ("token", "api_key", "apikey", "authorization", "secret", "password", "credential")
    stateful = ("status", "available", "availability", "verified", "probe", "unverified")
    names = {name.casefold() for name in dto.__dataclass_fields__}

    assert not [name for name in names if any(word in name for word in forbidden)]
    assert not [name for name in names if any(word in name for word in stateful)]


@pytest.mark.unit
def test_loading_and_filtering_the_catalog_performs_no_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("catalog loading must not touch the network")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)

    catalog: ModelCatalog = load_model_catalog()
    selected: list[ModelEntry] = [entry for entry in catalog.models.values() if entry.provider_id == "foundry-openai"]

    assert [entry.alias for entry in selected] == [
        model.alias for model in PALANTIR_MODELS if model.provider_id == "foundry-openai"
    ]


@pytest.mark.unit
def test_builtin_catalog_names_every_model_in_english() -> None:
    catalog: ModelCatalog = load_model_catalog()
    labels: list[str] = [entry.label for entry in catalog.models.values()]

    assert labels
    assert [label for label in labels if _POLISH_LETTERS.search(label)] == []


def test_the_catalog_language_guard_flags_a_polish_label() -> None:
    assert _POLISH_LETTERS.search(_POLISH_LABEL) is not None
    assert _POLISH_LETTERS.search("Foundry: main model") is None
