from __future__ import annotations

from collections.abc import Mapping

import pytest

from anishift.services.llm.engines import suggested_model_ids
from anishift.services.llm.engines.palantir.constants import PALANTIR_MODELS

pytestmark = pytest.mark.unit


def test_palantir_model_aliases_are_unique() -> None:
    aliases: tuple[str, ...] = tuple(model.alias for model in PALANTIR_MODELS)

    assert len(set(aliases)) == len(aliases)


def test_palantir_suggestions_expose_model_aliases() -> None:
    assert suggested_model_ids("palantir") == tuple(model.alias for model in PALANTIR_MODELS)


@pytest.mark.parametrize(
    ("provider_id", "option_paths", "variant_paths"),
    [
        ("foundry-openai", {"store"}, {"reasoning.effort"}),
        (
            "foundry-anthropic",
            {"thinking.type", "thinking.display"},
            {"output_config.effort"},
        ),
        (
            "foundry-google",
            {"generationConfig.thinkingConfig.includeThoughts", "generationConfig.thinkingConfig.thinkingBudget"},
            {"generationConfig.thinkingConfig.includeThoughts", "generationConfig.thinkingConfig.thinkingBudget"},
        ),
        ("foundry-xai", {"store"}, {"reasoning.effort"}),
    ],
)
def test_palantir_options_and_variants_use_known_request_fields(
    provider_id: str, option_paths: set[str], variant_paths: set[str]
) -> None:
    for model in (model for model in PALANTIR_MODELS if model.provider_id == provider_id):
        if model.model_id == "claude-opus-4-5":
            assert model.options == {}
            assert model.variants == {}
            continue
        assert _field_paths(model.options) == option_paths
        assert model.variants
        assert all(_field_paths(options) == variant_paths for options in model.variants.values())


def _field_paths(options: Mapping[str, object]) -> set[str]:
    paths: set[str] = set()
    for key, value in options.items():
        if isinstance(value, Mapping):
            paths.update(f"{key}.{nested}" for nested in _field_paths(value))
        else:
            paths.add(key)
    return paths
