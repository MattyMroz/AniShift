from __future__ import annotations

import pytest

from anishift.cli.interactive.settings import (
    _AUTO_FIELDS,
    _FIELDS_COVERED_ELSEWHERE,
    _GENERAL_FIELDS,
    _KNOWN_LAYOUT_GAPS,
    _SUBTITLE_FIELDS,
    _TRANSLATION_FIELDS,
    _TTS_FIELDS,
    _SettingField,
)
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingScope,
    SettingSpec,
    setting_catalog,
)
from anishift.config.user_settings import UserSettings

_PANEL_SCOPES = (SettingScope.GLOBAL, SettingScope.ENGINE_PROFILE, SettingScope.AUTO_PRESET)

_TTS_ENGINES = ("edge", "elevenbytes", "elevenlabs", "sapi")

_TRANSLATION_ENGINES = ("llm", "deepl", "google")


def _layout_fields() -> tuple[_SettingField, ...]:
    return (*_GENERAL_FIELDS, *_SUBTITLE_FIELDS, *_TRANSLATION_FIELDS, *_TTS_FIELDS, *_AUTO_FIELDS)


def _layout_ids() -> tuple[str, ...]:
    return tuple(setting_id for setting_id, _label, _section in _layout_fields())


def _normalised(**changes: object) -> UserSettings:
    settings = UserSettings()
    for name, value in changes.items():
        setattr(settings, name, value)
    settings.__post_init__()
    return settings


def _panel_specs(settings: UserSettings) -> dict[str, SettingSpec]:
    context = SettingCatalogContext.from_user_settings(settings)
    return {spec.setting_id: spec for spec in setting_catalog(context) if spec.scope in _PANEL_SCOPES}


def test_layout_never_repeats_a_setting() -> None:
    identifiers = _layout_ids()
    assert len(identifiers) == len(set(identifiers))


def test_excuse_lists_do_not_overlap_the_layout() -> None:
    identifiers = set(_layout_ids())
    assert not identifiers & set(_FIELDS_COVERED_ELSEWHERE)
    assert not identifiers & set(_KNOWN_LAYOUT_GAPS)


def test_excuse_lists_are_disjoint() -> None:
    assert not set(_FIELDS_COVERED_ELSEWHERE) & set(_KNOWN_LAYOUT_GAPS)


def test_every_excuse_carries_a_reason() -> None:
    for reason in (*_FIELDS_COVERED_ELSEWHERE.values(), *_KNOWN_LAYOUT_GAPS.values()):
        assert reason.strip()


@pytest.mark.parametrize("engine", _TTS_ENGINES)
def test_narration_engine_exposes_every_editable_field(engine: str) -> None:
    settings = _normalised(tts_engine=engine)
    unreachable = set(_panel_specs(settings)) - set(_layout_ids())
    assert unreachable <= set(_FIELDS_COVERED_ELSEWHERE) | set(_KNOWN_LAYOUT_GAPS)


@pytest.mark.parametrize("engine", _TRANSLATION_ENGINES)
def test_translation_engine_exposes_every_editable_field(engine: str) -> None:
    settings = _normalised(translation_engine=engine)
    unreachable = set(_panel_specs(settings)) - set(_layout_ids())
    assert unreachable <= set(_FIELDS_COVERED_ELSEWHERE) | set(_KNOWN_LAYOUT_GAPS)


@pytest.mark.parametrize("model_id", ["run6", "run7"])
def test_elevenbytes_models_expose_every_editable_field(model_id: str) -> None:
    settings = _normalised(tts_engine="elevenbytes", tts_provider_model_id=model_id)
    unreachable = set(_panel_specs(settings)) - set(_layout_ids())
    assert unreachable <= set(_FIELDS_COVERED_ELSEWHERE) | set(_KNOWN_LAYOUT_GAPS)


def test_layout_only_names_settings_the_catalog_can_produce() -> None:
    known: set[str] = set()
    for engine in _TTS_ENGINES:
        known |= set(_panel_specs(_normalised(tts_engine=engine)))
    for engine in _TRANSLATION_ENGINES:
        known |= set(_panel_specs(_normalised(translation_engine=engine)))
    assert set(_layout_ids()) <= known


def test_every_editable_field_is_reachable_so_no_gap_is_tracked() -> None:
    assert _KNOWN_LAYOUT_GAPS == {}


def test_every_auto_preset_policy_has_a_row_and_products_have_their_own_screen() -> None:
    preset_ids: set[str] = {spec.setting_id for spec in setting_catalog() if spec.scope is SettingScope.AUTO_PRESET}
    auto_ids: set[str] = {setting_id for setting_id, _label, _section in _AUTO_FIELDS}

    assert auto_ids == preset_ids - {"requested_products"}
    assert "requested_products" in _FIELDS_COVERED_ELSEWHERE
