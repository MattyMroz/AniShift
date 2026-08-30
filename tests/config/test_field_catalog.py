from __future__ import annotations

from dataclasses import fields

import pytest

from anishift.application.artifacts import ArtifactKind
from anishift.application.intents import (
    BurnSubtitleProduct,
    ExternalAudioRole,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.config.field_catalog import (
    USER_SETTING_DISPOSITIONS,
    SettingCatalogContext,
    SettingDisposition,
    SettingScope,
    SettingSpec,
    SettingValueType,
    setting_catalog,
)
from anishift.config.settings import Settings
from anishift.config.user_settings import CustomVoiceSetting, UserSettings
from anishift.services.llm.engines import available_engine_ids as available_llm_engine_ids
from anishift.services.translation.engines import available_engine_ids as available_translation_engine_ids
from anishift.services.tts.engines import available_engine_ids as available_tts_engine_ids
from anishift.services.tts.engines.edge.constants import (
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS, ENDPOINTS
from anishift.services.tts.engines.elevenbytes.vpn import VPN_MAX_CONCURRENCY
from anishift.services.tts.engines.elevenlabs.constants import OUTPUT_FORMATS, POLISH_TTS_MODEL_IDS
from anishift.services.tts.engines.sapi.constants import SAPI_PROFILES


def _catalog(context: SettingCatalogContext | None = None) -> dict[str, SettingSpec]:
    return {spec.setting_id: spec for spec in setting_catalog(context)}


def test_catalog_contract_is_complete_and_self_consistent() -> None:
    specs = setting_catalog()
    catalog = _catalog()
    expected_ids: set[str] = {
        "anthropic_api_key",
        "audio_language_priority",
        "burn_subtitle_product",
        "composition_quality_preset",
        "deepl_api_key",
        "deepseek_api_key",
        "elevenbytes_custom_voices",
        "elevenbytes_vpn_enabled",
        "elevenlabs_api_key",
        "external_audio_role",
        "gemini_api_key",
        "llm_max_concurrency",
        "llm_max_output_tokens",
        "llm_provider",
        "llm_provider_model_id",
        "llm_temperature",
        "llm_top_p",
        "llm_translation_style",
        "mkv_tracks",
        "mp4_audio_source",
        "narrator_mix_base_gain_db",
        "openai_api_key",
        "openai_compatible_api_key",
        "openai_compatible_base_url",
        "openrouter_api_key",
        "original_gain_db",
        "palantir_enrollment_base_url",
        "palantir_token",
        "preferred_video_artifact_id",
        "primary_model_alias",
        "processing_order_policy",
        "requested_products",
        "selected_audio_artifact_id",
        "selected_audio_track_id",
        "selected_subtitle_artifact_id",
        "selected_subtitle_track_id",
        "source_subtitle_language",
        "subtitle_language_priority",
        "subtitle_output_format",
        "subtitle_source_policy",
        "translation_action",
        "translation_batch_size",
        "translation_concurrency",
        "translation_engine",
        "translation_fallback_chain",
        "translation_max_retries",
        "tts_engine",
        "tts_max_retries",
        "tts_output_bitrate",
        "tts_output_profile",
        "tts_profile.concurrency",
        "tts_profile.postprocess_tempo",
        "tts_profile.voice_mix_offset_db",
        "tts_provider_model_id",
        "tts_voice_id",
    }

    assert set(catalog) == expected_ids
    assert len(catalog) == len(specs)
    assert all(spec.label.strip() and spec.description.strip() for spec in specs)
    assert all(spec.minimum is None or spec.maximum is None or spec.minimum <= spec.maximum for spec in specs)
    assert all(condition.setting_id in catalog for spec in specs for condition in spec.depends_on)
    assert all(spec.is_secret is (spec.scope is SettingScope.SECRET) for spec in specs)
    assert catalog["translation_engine"].allowed_values == tuple(available_translation_engine_ids())
    assert catalog["llm_provider"].allowed_values == tuple(available_llm_engine_ids())
    assert catalog["llm_translation_style"].allowed_values == ("neutral",)
    assert catalog["llm_max_concurrency"].default == 4
    assert catalog["llm_max_concurrency"].maximum == 4
    assert catalog["tts_engine"].allowed_values == tuple(available_tts_engine_ids())


def test_every_user_setting_has_an_explicit_catalog_disposition() -> None:
    persisted_fields = {field.name for field in fields(UserSettings)}
    catalog = _catalog()
    catalog_fields = set(catalog)
    visible_fields = {
        setting_id
        for setting_id, disposition in USER_SETTING_DISPOSITIONS.items()
        if disposition in {SettingDisposition.VISIBLE, SettingDisposition.CONDITIONAL}
    }

    assert set(USER_SETTING_DISPOSITIONS) == persisted_fields
    assert visible_fields - {"tts_voice_profiles"} <= catalog_fields
    assert {
        setting_id
        for setting_id, disposition in USER_SETTING_DISPOSITIONS.items()
        if disposition in {SettingDisposition.INTERNAL, SettingDisposition.REMOVED}
    }.isdisjoint(catalog_fields)


def test_workflow_contract_exposes_every_intent_choice() -> None:
    catalog = _catalog()
    manual_catalog = _catalog(SettingCatalogContext(run_mode=RunMode.MANUAL))

    assert catalog["subtitle_source_policy"].allowed_values == tuple(
        value.value
        for value in SubtitleSourcePolicy
        if value not in {SubtitleSourcePolicy.EXTERNAL, SubtitleSourcePolicy.READY_POLISH}
    )
    assert manual_catalog["subtitle_source_policy"].allowed_values == tuple(
        value.value for value in SubtitleSourcePolicy
    )
    assert catalog["requested_products"].scope is SettingScope.AUTO_PRESET
    assert manual_catalog["requested_products"].scope is SettingScope.MANUAL_RUN
    assert catalog["external_audio_role"].allowed_values == tuple(value.value for value in ExternalAudioRole)
    assert catalog["subtitle_output_format"].allowed_values == tuple(value.value for value in SubtitleOutputFormat)
    assert catalog["translation_action"].allowed_values == tuple(value.value for value in TranslationAction)
    assert catalog["requested_products"].allowed_values == tuple(value.value for value in ProductKind)
    assert catalog["burn_subtitle_product"].allowed_values == tuple(value.value for value in BurnSubtitleProduct)
    assert catalog["mkv_tracks"].allowed_values == tuple(value.value for value in MkvTrackProduct)
    assert catalog["mp4_audio_source"].allowed_values == tuple(value.value for value in Mp4AudioSource)
    assert catalog["selected_subtitle_track_id"].minimum == 0
    assert catalog["selected_audio_track_id"].minimum == 0
    assert catalog["selected_subtitle_artifact_id"].scope is SettingScope.MANUAL_RUN
    assert catalog["selected_audio_artifact_id"].scope is SettingScope.MANUAL_RUN
    assert manual_catalog["mp4_audio_source"].scope is SettingScope.MANUAL_RUN
    assert catalog["burn_subtitle_product"].depends_on[0].allowed_values == (ProductKind.MP4.value,)
    assert catalog["mkv_tracks"].depends_on[0].allowed_values == (ProductKind.MKV.value,)
    assert catalog["mp4_audio_source"].depends_on[0].allowed_values == (ProductKind.MP4.value,)
    assert ArtifactKind.SOURCE_AUDIO in catalog["audio_language_priority"].invalidates
    assert ArtifactKind.SOURCE_AUDIO in catalog["selected_audio_artifact_id"].invalidates
    assert ArtifactKind.SOURCE_SUBTITLES in catalog["subtitle_output_format"].invalidates


def test_edge_catalog_uses_static_models_voices_and_native_controls() -> None:
    catalog = _catalog(
        SettingCatalogContext(
            tts_engine="edge",
            tts_provider_model_id=EDGE_PROVIDER_MODEL_ID,
            tts_voice_id=MAREK_VOICE_ID,
        )
    )

    assert catalog["tts_provider_model_id"].allowed_values == (EDGE_PROVIDER_MODEL_ID,)
    assert catalog["tts_voice_id"].allowed_values == (MAREK_VOICE_ID, ZOFIA_VOICE_ID)
    assert catalog["tts_profile.native_rate"].value_type is SettingValueType.STRING
    assert catalog["tts_profile.native_volume"].value_type is SettingValueType.STRING
    assert catalog["tts_profile.native_pitch"].value_type is SettingValueType.STRING
    assert "tts_profile.concurrency" in catalog
    catalog["tts_profile.native_rate"].validate_value("-100%")
    catalog["tts_profile.native_volume"].validate_value("+100%")
    catalog["tts_profile.native_pitch"].validate_value("+100Hz")
    with pytest.raises(ValueError, match="required format"):
        catalog["tts_profile.native_rate"].validate_value("101%")


@pytest.mark.parametrize("endpoint", ["run6", "run7"])
def test_elevenbytes_catalog_switches_run7_options(endpoint: str) -> None:
    catalog = _catalog(
        SettingCatalogContext(
            tts_engine="elevenbytes",
            tts_provider_model_id=endpoint,
            tts_voice_id=DALLIN_ALIAS,
            elevenbytes_custom_voice_aliases=("custom",),
        )
    )
    option_ids = {
        "tts_profile.engine_options.stability",
        "tts_profile.engine_options.similarity_boost",
        "tts_profile.engine_options.style",
        "tts_profile.engine_options.use_speaker_boost",
    }

    assert catalog["tts_provider_model_id"].allowed_values == tuple(ENDPOINTS)
    assert catalog["tts_voice_id"].allowed_values == (DALLIN_ALIAS, "custom")
    assert option_ids <= set(catalog) if endpoint == "run7" else option_ids.isdisjoint(catalog)
    assert catalog["tts_profile.concurrency"].maximum == VPN_MAX_CONCURRENCY


def test_custom_voice_list_has_a_typed_object_editor_contract() -> None:
    spec = _catalog()["elevenbytes_custom_voices"]
    voice = CustomVoiceSetting(alias="reader", label="Reader", voice_id="provider-id")

    assert tuple(field.field_id for field in spec.object_fields) == ("alias", "label", "voice_id")
    spec.validate_value((voice,))
    with pytest.raises(TypeError, match="declared type"):
        spec.validate_value(("reader",))


def test_elevenlabs_catalog_uses_official_static_options() -> None:
    catalog = _catalog(
        SettingCatalogContext(
            tts_engine="elevenlabs",
            tts_provider_model_id=POLISH_TTS_MODEL_IDS[0],
            tts_voice_id="provider-voice-id",
        )
    )

    assert catalog["tts_provider_model_id"].allowed_values == tuple(POLISH_TTS_MODEL_IDS)
    assert catalog["tts_voice_id"].allowed_values == ()
    assert catalog["tts_profile.engine_options.output_format"].allowed_values == tuple(OUTPUT_FORMATS)
    assert catalog["tts_profile.engine_options.speed"].minimum == 0.7
    assert catalog["tts_profile.engine_options.speed"].maximum == 1.2


@pytest.mark.parametrize(
    ("voice_id", "expected"),
    [
        (
            "agnieszka",
            (SettingValueType.INTEGER, -10.0, 10.0, SettingValueType.INTEGER, 100.0),
        ),
        (
            SAPI_PROFILES["zosia"].resolved_voice_id,
            (SettingValueType.FLOAT, 1.0, None, SettingValueType.FLOAT, 1.0),
        ),
    ],
)
def test_sapi_catalog_uses_voice_specific_scales_without_false_concurrency(
    voice_id: str,
    expected: tuple[SettingValueType, float, float | None, SettingValueType, float],
) -> None:
    catalog = _catalog(
        SettingCatalogContext(
            tts_engine="sapi",
            tts_provider_model_id="sapi5",
            tts_voice_id=voice_id,
        )
    )
    rate_type: SettingValueType = expected[0]
    rate_minimum: float = expected[1]
    rate_maximum: float | None = expected[2]
    volume_type: SettingValueType = expected[3]
    volume_maximum: float = expected[4]

    assert catalog["tts_voice_id"].allowed_values == tuple(SAPI_PROFILES)
    assert catalog["tts_profile.native_rate"].value_type is rate_type
    assert catalog["tts_profile.native_rate"].minimum == rate_minimum
    assert catalog["tts_profile.native_rate"].maximum == rate_maximum
    assert catalog["tts_profile.native_volume"].value_type is volume_type
    assert catalog["tts_profile.native_volume"].maximum == volume_maximum
    assert "tts_profile.concurrency" not in catalog
    assert "tts_profile.native_pitch" not in catalog


def test_secret_catalog_covers_environment_keys_without_exposing_workspace() -> None:
    catalog = _catalog()
    secret_ids = {setting_id for setting_id, spec in catalog.items() if spec.is_secret}
    expected_secret_ids = {field_name for field_name in Settings.model_fields if field_name.endswith("_api_key")} | {
        "palantir_token",
    }

    assert secret_ids == expected_secret_ids
    assert secret_ids <= set(Settings.model_fields)
    assert all(catalog[setting_id].default == "" for setting_id in secret_ids)
    assert catalog["openai_compatible_base_url"].is_secret is False
    assert "workspace_root" not in catalog


def test_context_copies_only_catalog_selections_from_mutable_settings() -> None:
    settings = UserSettings()
    settings.elevenbytes_custom_voices.append(
        CustomVoiceSetting(
            alias="narrator",
            label="Narrator",
            voice_id="provider-id",
        )
    )

    context = SettingCatalogContext.from_user_settings(settings)
    settings.elevenbytes_custom_voices.clear()

    assert context.elevenbytes_custom_voice_aliases == ("narrator",)


def test_unknown_tts_engine_cannot_build_a_partial_catalog() -> None:
    with pytest.raises(ValueError, match="Unknown TTS engine"):
        setting_catalog(SettingCatalogContext(tts_engine="missing"))
