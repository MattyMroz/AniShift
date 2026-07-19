import sys
from typing import get_args

import pytest

from anishift.services.translation.config import TranslationConfig
from anishift.services.translation.constants import TARGET_LANG
from anishift.services.translation.engines import (
    TranslationEngineId,
    available_engine_ids,
    create_engine,
)
from anishift.services.translation.errors import TranslationConfigError


def test_target_language_is_always_polish() -> None:
    assert TARGET_LANG == "pl"


def test_available_engine_ids_returns_registry_keys() -> None:
    assert available_engine_ids() == ("google", "deepl", "llm")


def test_engine_id_literal_matches_registry() -> None:
    assert set(get_args(TranslationEngineId)) == set(available_engine_ids())


def test_create_engine_unknown_id_raises_with_sorted_list() -> None:
    config = TranslationConfig(engine="does_not_exist")
    with pytest.raises(TranslationConfigError) as exc:
        create_engine(config)
    assert "deepl, google, llm" in str(exc.value)


def test_create_engine_llm_requires_injected_completer() -> None:
    config = TranslationConfig(engine="llm")
    with pytest.raises(TranslationConfigError) as exc:
        create_engine(config)
    assert "completer" in str(exc.value)


def test_config_without_engine_raises() -> None:
    with pytest.raises(TranslationConfigError):
        TranslationConfig()


def test_registry_import_does_not_load_provider_sdks() -> None:
    # Importing the registry must NOT pull googletrans/deepl (lazy import).
    for module in ("googletrans", "deepl"):
        sys.modules.pop(module, None)
    import importlib  # noqa: PLC0415 - reload requires a fresh in-function import

    import anishift.services.translation.engines as registry  # noqa: PLC0415

    importlib.reload(registry)
    assert "googletrans" not in sys.modules
    assert "deepl" not in sys.modules
