from __future__ import annotations

from typing import Final

from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingObjectFieldSpec,
    SettingScope,
    SettingSpec,
    SettingValue,
    SettingValueType,
    setting_catalog,
)
from anishift.services.tts.engines.edge.constants import EDGE_PROVIDER_MODEL_ID, MAREK_VOICE_ID
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS
from anishift.services.tts.engines.elevenlabs.constants import DEFAULT_MODEL_ID
from anishift.tui.settings.editors import EditorKind, editor_for

_DEFAULTS: Final[dict[SettingValueType, SettingValue]] = {
    SettingValueType.STRING: "value",
    SettingValueType.OPTIONAL_STRING: None,
    SettingValueType.INTEGER: 0,
    SettingValueType.OPTIONAL_INTEGER: None,
    SettingValueType.FLOAT: 0.0,
    SettingValueType.OPTIONAL_FLOAT: None,
    SettingValueType.BOOLEAN: False,
    SettingValueType.STRING_LIST: (),
    SettingValueType.STRING_SET: frozenset(),
    SettingValueType.OBJECT_LIST: (),
}

_EXPECTED: Final[dict[SettingValueType, EditorKind]] = {
    SettingValueType.STRING: EditorKind.TEXT,
    SettingValueType.OPTIONAL_STRING: EditorKind.TEXT,
    SettingValueType.INTEGER: EditorKind.NUMBER,
    SettingValueType.OPTIONAL_INTEGER: EditorKind.NUMBER,
    SettingValueType.FLOAT: EditorKind.NUMBER,
    SettingValueType.OPTIONAL_FLOAT: EditorKind.NUMBER,
    SettingValueType.BOOLEAN: EditorKind.TOGGLE,
    SettingValueType.STRING_LIST: EditorKind.REORDER,
    SettingValueType.STRING_SET: EditorKind.MULTI_SELECT,
    SettingValueType.OBJECT_LIST: EditorKind.OBJECT_WIZARD,
}

_CONTEXTS: Final[tuple[SettingCatalogContext, ...]] = (
    SettingCatalogContext(),
    SettingCatalogContext(llm_provider="openai_compatible"),
    SettingCatalogContext(tts_engine="edge", tts_provider_model_id=EDGE_PROVIDER_MODEL_ID, tts_voice_id=MAREK_VOICE_ID),
    SettingCatalogContext(
        tts_engine="elevenbytes",
        tts_provider_model_id="run7",
        tts_voice_id=DALLIN_ALIAS,
        elevenbytes_custom_voice_aliases=("studio",),
    ),
    SettingCatalogContext(tts_engine="elevenlabs", tts_provider_model_id=DEFAULT_MODEL_ID, tts_voice_id=""),
    SettingCatalogContext(tts_engine="sapi", tts_provider_model_id="sapi5", tts_voice_id="agnieszka"),
)


def _probe_spec(value_type: SettingValueType) -> SettingSpec:
    if value_type is SettingValueType.OBJECT_LIST:
        return SettingSpec(
            setting_id="probe",
            label="Probe",
            description="Probe setting.",
            value_type=value_type,
            default=(),
            scope=SettingScope.GLOBAL,
            object_fields=(
                SettingObjectFieldSpec(
                    field_id="alias",
                    label="Alias",
                    description="Alias field.",
                    value_type=SettingValueType.STRING,
                ),
            ),
        )
    return SettingSpec(
        setting_id="probe",
        label="Probe",
        description="Probe setting.",
        value_type=value_type,
        default=_DEFAULTS[value_type],
        scope=SettingScope.GLOBAL,
    )


def test_editor_for_maps_every_value_type() -> None:
    assert set(_EXPECTED) == set(SettingValueType)
    for value_type, kind in _EXPECTED.items():
        assert editor_for(_probe_spec(value_type)) is kind


def test_editor_for_selects_when_a_field_offers_values() -> None:
    spec: SettingSpec = SettingSpec(
        setting_id="probe",
        label="Probe",
        description="Probe setting.",
        value_type=SettingValueType.STRING,
        default="a",
        scope=SettingScope.GLOBAL,
        allowed_values=("a", "b"),
    )
    assert editor_for(spec) is EditorKind.SELECT


def test_editor_for_handles_every_catalog_spec() -> None:
    seen: set[SettingValueType] = set()
    for context in _CONTEXTS:
        for spec in setting_catalog(context):
            assert isinstance(editor_for(spec), EditorKind)
            seen.add(spec.value_type)
    assert seen == set(SettingValueType)
