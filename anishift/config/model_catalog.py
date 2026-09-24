"""Application catalog projected from the built-in Palantir model list."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from anishift.services.llm.engines.palantir.constants import PALANTIR_MODELS, PALANTIR_PROVIDERS
from anishift.services.llm.wire_protocol import ModelProtocol

__all__ = [
    "ModelCatalog",
    "ModelEntry",
    "ModelProtocol",
    "ProviderEntry",
    "load_model_catalog",
]


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    """One Foundry proxy provider: its protocol and its relative route."""

    provider_id: str
    protocol: ModelProtocol
    path: str


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """One model alias bound to a provider and a provider model identifier."""

    alias: str
    provider_id: str
    model_id: str
    label: str


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Application model catalog with providers and model aliases."""

    providers: Mapping[str, ProviderEntry]
    models: Mapping[str, ModelEntry]


def load_model_catalog() -> ModelCatalog:
    """Project the built-in Palantir list without file or network access."""
    return ModelCatalog(
        providers=MappingProxyType(
            {
                provider.provider_id: ProviderEntry(provider.provider_id, provider.protocol, provider.path)
                for provider in PALANTIR_PROVIDERS
            }
        ),
        models=MappingProxyType(
            {
                model.alias: ModelEntry(
                    alias=model.alias,
                    provider_id=model.provider_id,
                    model_id=model.model_id,
                    label=model.label,
                )
                for model in PALANTIR_MODELS
            }
        ),
    )
