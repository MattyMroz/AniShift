from __future__ import annotations

import pytest

from anishift.config.field_access import (
    assign_setting_value,
    read_setting_value,
    setting_is_active,
    setting_is_persisted,
)
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingCondition,
    SettingScope,
    SettingSpec,
    SettingValue,
    SettingValueType,
    setting_catalog,
)
from anishift.config.user_settings import CustomVoiceSetting, UserSettings, tts_profile_key
from anishift.services.tts.engines.edge.constants import DEFAULT_PITCH, MAREK_VOICE_ID, ZOFIA_VOICE_ID
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS, DALLIN_VOICE_ID


def _engine_selections() -> tuple[UserSettings, ...]:
    return (
        UserSettings(),
        UserSettings(tts_engine="elevenbytes", tts_provider_model_id="run7"),
        UserSettings(tts_engine="edge", tts_voice_id=MAREK_VOICE_ID),
        UserSettings(tts_engine="sapi", tts_voice_id="agnieszka"),
        UserSettings(tts_engine="sapi", tts_voice_id="zosia"),
        UserSettings(tts_engine="elevenlabs", tts_voice_id="provider-voice"),
        UserSettings(translation_engine="llm", tts_output_profile="mp3"),
    )


def _addressable_specs(settings: UserSettings) -> tuple[SettingSpec, ...]:
    catalog: tuple[SettingSpec, ...] = setting_catalog(SettingCatalogContext.from_user_settings(settings))
    return tuple(
        spec
        for spec in catalog
        if spec.scope in {SettingScope.GLOBAL, SettingScope.ENGINE_PROFILE}
        and not spec.is_secret
        and setting_is_persisted(spec)
    )


def _spec(settings: UserSettings, setting_id: str) -> SettingSpec:
    catalog: tuple[SettingSpec, ...] = setting_catalog(SettingCatalogContext.from_user_settings(settings))
    return next(spec for spec in catalog if spec.setting_id == setting_id)


def _with_custom_voice(alias: str, *, active: bool) -> UserSettings:
    settings: UserSettings = UserSettings(tts_engine="elevenbytes")
    settings.add_elevenbytes_voice(alias=alias, label=alias.title(), voice_id=f"{alias}-provider-id")
    if active:
        settings.tts_voice_id = alias
        settings.ensure_active_tts_profile()
    return settings


def test_field_access_covers_every_persisted_setting_value_type() -> None:
    covered: set[SettingValueType] = set()

    for settings in _engine_selections():
        for spec in _addressable_specs(settings):
            value: SettingValue = read_setting_value(settings, spec)
            spec.validate_value(value)
            assert isinstance(setting_is_active(spec, settings), bool)
            assign_setting_value(settings, spec, value)
            assert read_setting_value(settings, spec) == value
            covered.add(spec.value_type)

    assert covered == set(SettingValueType) - {SettingValueType.STRING_SET}


def test_unsupported_value_type_fails_loudly_instead_of_guessing() -> None:
    spec: SettingSpec = SettingSpec(
        setting_id="translation_engine",
        label="Future",
        description="Type the catalog does not know yet.",
        value_type="future_value_type",  # type: ignore[arg-type]
        default=frozenset(),
        scope=SettingScope.GLOBAL,
    )
    settings: UserSettings = UserSettings()

    with pytest.raises(ValueError, match="Unsupported setting value type"):
        read_setting_value(settings, spec)
    with pytest.raises(ValueError, match="Unsupported setting value type"):
        assign_setting_value(settings, spec, frozenset())


def test_environment_and_workflow_specs_are_not_persisted_preferences() -> None:
    settings: UserSettings = UserSettings()
    environment_spec: SettingSpec = _spec(settings, "openai_compatible_base_url")
    workflow_spec: SettingSpec = _spec(settings, "mkv_tracks")

    assert not setting_is_persisted(environment_spec)
    assert not setting_is_persisted(workflow_spec)
    assert setting_is_persisted(_spec(settings, "translation_engine"))
    assert setting_is_persisted(_spec(settings, "tts_profile.postprocess_tempo"))
    with pytest.raises(ValueError, match="not a persisted user preference"):
        read_setting_value(settings, environment_spec)
    with pytest.raises(ValueError, match="not a persisted user preference"):
        assign_setting_value(settings, environment_spec, "https://example.invalid")
    with pytest.raises(ValueError, match="not a persisted user preference"):
        setting_is_active(workflow_spec, settings)


def test_unknown_voice_profile_field_is_rejected() -> None:
    spec: SettingSpec = SettingSpec(
        setting_id="tts_profile.unknown_field",
        label="Unknown",
        description="Profile field that does not exist.",
        value_type=SettingValueType.FLOAT,
        default=1.0,
        scope=SettingScope.ENGINE_PROFILE,
    )

    with pytest.raises(ValueError, match="names no voice profile field"):
        read_setting_value(UserSettings(), spec)


def test_profile_fields_and_engine_options_follow_the_active_voice() -> None:
    settings: UserSettings = UserSettings(tts_engine="elevenbytes", tts_provider_model_id="run7")
    tempo_spec: SettingSpec = _spec(settings, "tts_profile.postprocess_tempo")
    stability_spec: SettingSpec = _spec(settings, "tts_profile.engine_options.stability")

    assign_setting_value(settings, tempo_spec, 1.75)
    assign_setting_value(settings, stability_spec, 0.25)
    dallin_key: str = tts_profile_key("elevenbytes", DALLIN_VOICE_ID)

    assert settings.tts_voice_profiles[dallin_key].postprocess_tempo == 1.75
    assert settings.tts_voice_profiles[dallin_key].engine_options == {"stability": 0.25}
    assert read_setting_value(settings, tempo_spec) == 1.75
    assert read_setting_value(settings, stability_spec) == 0.25


def test_switching_the_voice_reads_and_writes_another_profile() -> None:
    settings: UserSettings = UserSettings(tts_engine="edge", tts_voice_id=MAREK_VOICE_ID)
    tempo_spec: SettingSpec = _spec(settings, "tts_profile.postprocess_tempo")
    assign_setting_value(settings, tempo_spec, 1.4)

    settings.tts_voice_id = ZOFIA_VOICE_ID

    assert read_setting_value(settings, tempo_spec) == 1.0
    assign_setting_value(settings, tempo_spec, 1.1)
    assert settings.tts_voice_profiles[tts_profile_key("edge", MAREK_VOICE_ID)].postprocess_tempo == 1.4
    assert settings.tts_voice_profiles[tts_profile_key("edge", ZOFIA_VOICE_ID)].postprocess_tempo == 1.1


def test_missing_profile_value_falls_back_to_the_spec_default() -> None:
    settings: UserSettings = UserSettings(tts_engine="edge", tts_voice_id=MAREK_VOICE_ID)
    pitch_spec: SettingSpec = _spec(settings, "tts_profile.native_pitch")

    assert settings.active_tts_profile.native_pitch is None
    assert read_setting_value(settings, pitch_spec) == DEFAULT_PITCH


def test_optional_preference_keeps_none_instead_of_its_default() -> None:
    settings: UserSettings = UserSettings(translation_engine="llm", llm_temperature=None)
    temperature_spec: SettingSpec = _spec(settings, "llm_temperature")

    assert read_setting_value(settings, temperature_spec) is None
    assign_setting_value(settings, temperature_spec, 0.4)
    assert settings.llm_temperature == 0.4


def test_string_list_persists_every_ordered_field_as_a_tuple() -> None:
    settings: UserSettings = UserSettings()
    audio_spec: SettingSpec = _spec(settings, "audio_language_priority")
    subtitle_spec: SettingSpec = _spec(settings, "subtitle_language_priority")

    assign_setting_value(settings, audio_spec, ("jpn", "eng"))
    assign_setting_value(settings, subtitle_spec, ("eng", "pol"))

    assert settings.audio_language_priority == ("jpn", "eng")
    assert settings.subtitle_language_priority == ("eng", "pol")
    assert read_setting_value(settings, audio_spec) == ("jpn", "eng")
    assert read_setting_value(settings, subtitle_spec) == ("eng", "pol")


def test_object_list_roundtrips_custom_voices() -> None:
    settings: UserSettings = UserSettings()
    voices_spec: SettingSpec = _spec(settings, "elevenbytes_custom_voices")
    voice: CustomVoiceSetting = CustomVoiceSetting(alias="reader", label="Reader", voice_id="provider-id")

    assign_setting_value(settings, voices_spec, (voice,))

    assert settings.elevenbytes_custom_voices == [voice]
    assert read_setting_value(settings, voices_spec) == (voice,)


def test_object_list_rejects_a_plain_string_item() -> None:
    settings: UserSettings = UserSettings()
    voices_spec: SettingSpec = _spec(settings, "elevenbytes_custom_voices")

    with pytest.raises(TypeError, match="accepts custom voices only"):
        assign_setting_value(settings, voices_spec, ("reader",))


def test_removing_the_active_custom_voice_selects_the_built_in_voice() -> None:
    settings: UserSettings = _with_custom_voice("reader", active=True)
    voices_spec: SettingSpec = _spec(settings, "elevenbytes_custom_voices")

    assign_setting_value(settings, voices_spec, ())
    settings.__post_init__()

    assert settings.elevenbytes_custom_voices == []
    assert settings.tts_voice_id == DALLIN_ALIAS
    assert settings.resolved_tts_voice_id == DALLIN_VOICE_ID
    assert tts_profile_key("elevenbytes", DALLIN_VOICE_ID) in settings.tts_voice_profiles
    assert tts_profile_key("elevenbytes", "reader") not in settings.tts_voice_profiles


def test_removing_an_inactive_custom_voice_keeps_the_current_selection() -> None:
    settings: UserSettings = _with_custom_voice("reader", active=False)
    voices_spec: SettingSpec = _spec(settings, "elevenbytes_custom_voices")

    assign_setting_value(settings, voices_spec, ())
    settings.__post_init__()

    assert settings.elevenbytes_custom_voices == []
    assert settings.tts_voice_id == DALLIN_ALIAS


def test_renaming_a_custom_voice_never_leaves_a_dangling_selection() -> None:
    settings: UserSettings = _with_custom_voice("reader", active=True)
    voices_spec: SettingSpec = _spec(settings, "elevenbytes_custom_voices")
    renamed: CustomVoiceSetting = CustomVoiceSetting(alias="narrator", label="Narrator", voice_id="reader-provider-id")

    assign_setting_value(settings, voices_spec, (renamed,))
    settings.__post_init__()

    assert settings.elevenbytes_custom_voices == [renamed]
    assert settings.tts_voice_id == DALLIN_ALIAS
    assert settings.resolved_tts_voice_id == DALLIN_VOICE_ID


def test_setting_is_active_follows_the_selected_engines() -> None:
    google_settings: UserSettings = UserSettings(translation_engine="google", tts_output_profile="flac")
    llm_settings: UserSettings = UserSettings(translation_engine="llm", tts_output_profile="mp3")

    assert not setting_is_active(_spec(google_settings, "llm_temperature"), google_settings)
    assert not setting_is_active(_spec(google_settings, "tts_output_bitrate"), google_settings)
    assert setting_is_active(_spec(llm_settings, "llm_temperature"), llm_settings)
    assert setting_is_active(_spec(llm_settings, "tts_output_bitrate"), llm_settings)
    assert setting_is_active(_spec(llm_settings, "translation_engine"), llm_settings)


def test_setting_is_active_matches_a_condition_against_a_stored_sequence() -> None:
    settings: UserSettings = UserSettings()
    spec: SettingSpec = SettingSpec(
        setting_id="translation_batch_size",
        label="English audio detail",
        description="Active only while English is one of the preferred audio languages.",
        value_type=SettingValueType.INTEGER,
        default=0,
        scope=SettingScope.GLOBAL,
        depends_on=(SettingCondition("audio_language_priority", ("eng",)),),
    )
    settings.audio_language_priority = ("jpn",)

    assert not setting_is_active(spec, settings)

    settings.audio_language_priority = ("jpn", "eng")

    assert setting_is_active(spec, settings)
