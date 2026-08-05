from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.config import user_settings
from anishift.config.user_settings import (
    CustomVoiceSetting,
    SettingsSchemaWarning,
    TtsVoiceProfileSettings,
    UserSettings,
    default_tts_voice_profiles,
    load_user_settings,
    save_user_settings,
    tts_profile_key,
)
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_VOICE_ID
from anishift.services.tts.engines.sapi.constants import SAPI_PROFILES


@pytest.fixture
def config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "config_path", lambda: target)
    return target


@pytest.mark.usefixtures("config_file")
def test_load_missing_file_returns_defaults() -> None:
    settings = load_user_settings()
    assert settings == UserSettings()
    assert settings.mode == "auto"
    assert settings.processing_order_policy == "ready_first"
    assert settings.output_variant == "players"
    assert settings.composition_quality_preset == "balanced"


@pytest.mark.usefixtures("config_file")
def test_save_then_load_roundtrip() -> None:
    save_user_settings(UserSettings(mode="manual", composition_quality_preset="compact"))
    loaded = load_user_settings()
    assert loaded.mode == "manual"
    assert loaded.composition_quality_preset == "compact"


def test_save_creates_parent_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "config" / "settings.json"
    monkeypatch.setattr(user_settings, "config_path", lambda: nested)
    save_user_settings(UserSettings())
    assert nested.is_file()


def test_load_ignores_unknown_keys(config_file: Path) -> None:
    config_file.write_text(json.dumps({"mode": "manual", "bogus": 123}), encoding="utf-8")
    loaded = load_user_settings()
    assert loaded.mode == "manual"
    assert not hasattr(loaded, "bogus")


def test_load_invalid_mode_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"mode": "nonsense"}), encoding="utf-8")
    assert load_user_settings().mode == "auto"


def test_load_invalid_processing_order_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(
        json.dumps({"processing_order_policy": "random"}),
        encoding="utf-8",
    )

    assert load_user_settings().processing_order_policy == "ready_first"


def test_processing_order_roundtrip_preserves_strict_policy(config_file: Path) -> None:
    del config_file
    save_user_settings(UserSettings(processing_order_policy="strict_natural"))

    assert load_user_settings().processing_order_policy == "strict_natural"


def test_load_corrupt_json_returns_defaults(config_file: Path) -> None:
    config_file.write_text("{ not valid json ", encoding="utf-8")
    assert load_user_settings() == UserSettings()


def test_load_non_object_json_returns_defaults(config_file: Path) -> None:
    config_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_user_settings() == UserSettings()


def test_load_non_utf8_file_returns_defaults(config_file: Path) -> None:
    config_file.write_bytes(b"\xff\xfe not utf-8 \x80\x81")
    assert load_user_settings() == UserSettings()


@pytest.mark.usefixtures("config_file")
def test_defaults_include_all_panel_fields() -> None:
    s = UserSettings()
    assert s.translation_engine == "google"
    assert s.schema_version == 2
    assert s.tts_engine == "elevenbytes"
    assert s.tts_provider_model_id == "run6"
    assert s.tts_voice_id == "dallin"
    assert s.tts_max_retries == 3
    assert s.elevenbytes_vpn_enabled
    assert s.tts_output_profile == "eac3"
    assert s.tts_output_bitrate is None
    assert s.tts_timeline_policy == "serialize"
    assert s.narrator_mix_base_gain_db == 7.0
    assert s.original_gain_db == 0.0
    assert s.output_variant == "players"
    assert s.composition_quality_preset == "balanced"
    assert s.audio_language_priority == ("jpn", "eng", "zho")
    assert s.subtitle_language_priority == ("pol", "eng")
    assert s.llm_provider == "gemini"
    assert s.llm_provider_model_id == "gemini-3.5-flash-lite"
    assert s.llm_max_concurrency == 4


@pytest.mark.usefixtures("config_file")
def test_full_roundtrip_preserves_every_field() -> None:
    prompt_root = user_settings.config_path().parent / "prompts"
    for directory, name in (
        ("tasks", "custom_task.txt"),
        ("styles", "custom_style.txt"),
        ("modules", "honorifics.txt"),
        ("modules", "names.txt"),
    ):
        path = prompt_root / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    profiles = default_tts_voice_profiles()
    profiles["elevenlabs:custom-voice-id"] = TtsVoiceProfileSettings(
        postprocess_tempo=1.1,
        voice_mix_offset_db=1.5,
        concurrency=4,
        native_rate=0.9,
        engine_options={"stability": 0.5, "speaker_boost": True},
    )
    original = UserSettings(
        mode="manual",
        translation_engine="deepl",
        tts_engine="elevenlabs",
        tts_provider_model_id="eleven_multilingual_v2",
        tts_voice_id="custom-voice-id",
        tts_max_retries=5,
        elevenbytes_vpn_enabled=False,
        tts_output_profile="opus",
        tts_output_bitrate="192k",
        narrator_mix_base_gain_db=6.0,
        original_gain_db=-1.5,
        tts_voice_profiles=profiles,
        elevenbytes_custom_voices=[
            CustomVoiceSetting(
                alias="narrator",
                label="Narrator",
                voice_id="provider-voice-id",
            )
        ],
        output_variant="burn",
        composition_quality_preset="high",
        audio_language_priority=("eng", "jpn"),
        subtitle_language_priority=("eng", "pol"),
        llm_provider="openrouter",
        llm_provider_model_id="vendor/custom-model",
        llm_temperature=0.2,
        llm_top_p=0.9,
        llm_max_output_tokens=4096,
        llm_prompt_id="custom_task",
        llm_style_id="custom_style",
        llm_module_ids=["honorifics", "names"],
        llm_max_concurrency=3,
    )
    save_user_settings(original)
    assert load_user_settings() == original


def test_load_stale_prompt_selection_falls_back_to_defaults(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_prompt_id": "missing_task",
                "llm_style_id": "missing_style",
                "llm_module_ids": ["missing_module"],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_user_settings()

    assert loaded.llm_prompt_id == UserSettings().llm_prompt_id
    assert loaded.llm_style_id == UserSettings().llm_style_id
    assert loaded.llm_module_ids == []


def test_load_does_not_migrate_legacy_tempo(config_file: Path) -> None:
    config_file.write_text(json.dumps({"tempo": 1.85}), encoding="utf-8")
    profile = load_user_settings().tts_voice_profiles[f"elevenbytes:{DALLIN_VOICE_ID}"]
    assert profile.postprocess_tempo == 1.25


def test_load_does_not_migrate_legacy_volume_to_mix_gain(config_file: Path) -> None:
    config_file.write_text(json.dumps({"volume": 60}), encoding="utf-8")
    loaded = load_user_settings()
    assert loaded.narrator_mix_base_gain_db == 7.0
    assert loaded.original_gain_db == 0.0


def test_load_invalid_output_variant_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"output_variant": "bogus"}), encoding="utf-8")
    assert load_user_settings().output_variant == "players"


def test_load_migrates_legacy_voice_without_tempo_or_volume(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tts_engine": "edge",
                "voice": "pl-PL-ZofiaNeural",
                "tempo": 1.85,
                "volume": 60,
            }
        ),
        encoding="utf-8",
    )

    loaded = load_user_settings()

    assert loaded.schema_version == 2
    assert loaded.tts_engine == "edge"
    assert loaded.tts_voice_id == "pl-PL-ZofiaNeural"
    assert loaded.tempo == 1.0
    assert loaded.volume == 100


def test_load_migrates_legacy_llm_model(config_file: Path) -> None:
    config_file.write_text(json.dumps({"llm_model": " legacy/model "}), encoding="utf-8")
    loaded = load_user_settings()
    assert loaded.llm_provider_model_id == "legacy/model"


def test_load_prefers_new_llm_model_field(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_model": "legacy/model",
                "llm_provider_model_id": "new/model",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_user_settings()
    assert loaded.llm_provider_model_id == "new/model"


def test_load_optional_llm_values_accept_none(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_temperature": None,
                "llm_top_p": None,
                "llm_max_output_tokens": None,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_user_settings()
    assert loaded.llm_temperature is None
    assert loaded.llm_top_p is None
    assert loaded.llm_max_output_tokens is None


@pytest.mark.parametrize("value", [0, 5, "4", True])
def test_load_invalid_llm_concurrency_uses_default(value: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"llm_max_concurrency": value}), encoding="utf-8")
    assert load_user_settings().llm_max_concurrency == 4


@pytest.mark.parametrize("raw", ["balanced", "bogus", 1, None])
def test_load_invalid_quality_preset_falls_back_to_default(raw: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"composition_quality_preset": raw}), encoding="utf-8")
    expected = raw if raw == "balanced" else "balanced"
    assert load_user_settings().composition_quality_preset == expected


@pytest.mark.parametrize("raw", ["jpn", [""], [1], None])
def test_load_invalid_language_priority_falls_back_to_default(raw: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"audio_language_priority": raw}), encoding="utf-8")
    assert load_user_settings().audio_language_priority == ("jpn", "eng", "zho")


def test_load_language_priority_normalizes_case_and_duplicates(config_file: Path) -> None:
    config_file.write_text(json.dumps({"audio_language_priority": [" ENG ", "jpn", "eng"]}), encoding="utf-8")
    assert load_user_settings().audio_language_priority == ("eng", "jpn")


def test_dropped_legacy_output_switch_is_ignored(config_file: Path) -> None:
    config_file.write_text(json.dumps({"move_results_to_output": True}), encoding="utf-8")
    assert not hasattr(load_user_settings(), "move_results_to_output")


def test_save_writes_schema_v2_without_legacy_tts_placeholders(config_file: Path) -> None:
    settings = UserSettings()
    settings.tempo = 1.4
    settings.volume = 50

    save_user_settings(settings)

    payload = json.loads(config_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["tts_voice_id"] == "dallin"
    assert "voice" not in payload
    assert "tempo" not in payload
    assert "volume" not in payload


@pytest.mark.parametrize("schema_version", [3, 999, "2", None])
def test_unknown_schema_returns_safe_defaults_with_warning(
    config_file: Path,
    schema_version: object,
) -> None:
    config_file.write_text(
        json.dumps({"schema_version": schema_version, "mode": "manual"}),
        encoding="utf-8",
    )

    with pytest.warns(SettingsSchemaWarning):
        loaded = load_user_settings()

    assert loaded == UserSettings()


def test_default_voice_profiles_match_stage_six_decisions() -> None:
    profiles = default_tts_voice_profiles()
    dallin = profiles[f"elevenbytes:{DALLIN_VOICE_ID}"]
    agnieszka = profiles[f"sapi:{SAPI_PROFILES['agnieszka'].resolved_voice_id}"]
    zosia = profiles[f"sapi:{SAPI_PROFILES['zosia'].resolved_voice_id}"]
    marek = profiles["edge:pl-PL-MarekNeural"]
    zofia = profiles["edge:pl-PL-ZofiaNeural"]

    assert (dallin.postprocess_tempo, dallin.voice_mix_offset_db, dallin.concurrency) == (1.25, -2.0, 100)
    assert (agnieszka.native_rate, agnieszka.native_volume, agnieszka.voice_mix_offset_db) == (5, 65, 2.0)
    assert (zosia.native_rate, zosia.native_volume, zosia.voice_mix_offset_db) == (200, 0.7, 0.0)
    assert (marek.native_rate, marek.native_volume, marek.voice_mix_offset_db) == ("+40%", "+0%", 0.0)
    assert (zofia.native_rate, zofia.native_volume, zofia.voice_mix_offset_db) == ("+40%", "+0%", 0.0)
    assert marek.concurrency == 16
    assert zofia.concurrency == 16


def test_partial_builtin_profile_override_preserves_other_defaults(config_file: Path) -> None:
    key = f"sapi:{SAPI_PROFILES['agnieszka'].resolved_voice_id}"
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "tts_voice_profiles": {
                    key: {
                        "postprocess_tempo": 1.2,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    profile = load_user_settings().tts_voice_profiles[key]

    assert profile.postprocess_tempo == 1.2
    assert profile.native_rate == 5
    assert profile.native_volume == 65
    assert profile.concurrency == 1


def test_profile_map_roundtrip_restores_each_voice_independently(config_file: Path) -> None:
    marek_key = tts_profile_key("edge", "pl-PL-MarekNeural")
    zofia_key = tts_profile_key("edge", "pl-PL-ZofiaNeural")
    settings = UserSettings()
    settings.tts_voice_profiles[marek_key] = TtsVoiceProfileSettings(postprocess_tempo=1.1)
    settings.tts_voice_profiles[zofia_key] = TtsVoiceProfileSettings(postprocess_tempo=1.3)

    save_user_settings(settings)
    loaded = load_user_settings()

    assert loaded.tts_voice_profiles[marek_key].postprocess_tempo == 1.1
    assert loaded.tts_voice_profiles[zofia_key].postprocess_tempo == 1.3


def test_custom_voice_loader_rejects_reserved_and_duplicate_aliases(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "elevenbytes_custom_voices": [
                    {"alias": "DALLIN", "label": "Override", "voice_id": "bad"},
                    {"alias": "reader", "label": "Reader", "voice_id": "voice-1"},
                    {"alias": "READER", "label": "Duplicate", "voice_id": "voice-2"},
                    {"alias": "", "label": "Missing", "voice_id": "voice-3"},
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_user_settings()

    assert loaded.elevenbytes_custom_voices == [CustomVoiceSetting(alias="reader", label="Reader", voice_id="voice-1")]


@pytest.mark.parametrize(
    ("profile", "bitrate", "expected"),
    [
        ("eac3", "192K", "192k"),
        ("opus", "96k", "96k"),
        ("wav", "192k", None),
        ("flac", "192k", None),
        ("eac3", "fast", None),
    ],
)
def test_codec_specific_bitrate_validation(
    config_file: Path,
    profile: str,
    bitrate: str,
    expected: str | None,
) -> None:
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "tts_output_profile": profile,
                "tts_output_bitrate": bitrate,
            }
        ),
        encoding="utf-8",
    )

    assert load_user_settings().tts_output_bitrate == expected


def test_default_profile_maps_are_not_shared() -> None:
    first = UserSettings()
    second = UserSettings()
    key = f"elevenbytes:{DALLIN_VOICE_ID}"

    first.tts_voice_profiles[key].postprocess_tempo = 1.5

    assert second.tts_voice_profiles[key].postprocess_tempo == 1.25


def test_custom_elevenbytes_alias_resolves_profile_by_provider_voice_id() -> None:
    settings = UserSettings(
        tts_voice_id="reader",
        elevenbytes_custom_voices=[
            CustomVoiceSetting(
                alias="reader",
                label="Reader",
                voice_id="provider-voice-id",
            ),
        ],
        tts_voice_profiles={
            "elevenbytes:provider-voice-id": TtsVoiceProfileSettings(
                postprocess_tempo=1.4,
            ),
        },
    )

    assert settings.resolved_tts_voice_id == "provider-voice-id"
    assert settings.active_tts_profile.postprocess_tempo == 1.4
