from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli.settings_panel import _tts_model_is_freeform, _visible_fields
from anishift.cli.tts_settings import (
    TtsPanelCatalog,
    remove_elevenlabs_key,
    save_elevenlabs_key,
    step_tts_field,
    tts_field_value,
    tts_model_ids,
    tts_voice_choices,
)
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.services.audio.types import AudioCodecProfile
from anishift.services.tts import (
    AvailabilitySource,
    AvailabilityStatus,
    EngineAvailability,
    VoiceInfo,
)
from anishift.services.tts.engines import available_engine_ids
from anishift.services.tts.engines.edge.constants import (
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.elevenlabs.constants import DEFAULT_MODEL_ID


def _availability(
    engine_id: str,
    *,
    status: AvailabilityStatus = AvailabilityStatus.READY,
    voices: tuple[VoiceInfo, ...] = (),
) -> EngineAvailability:
    return EngineAvailability(
        status=status,
        message=status.value,
        checked_at=datetime.now(UTC),
        source=AvailabilitySource.CONFIG,
        voices=voices,
    )


def _catalog(
    *,
    elevenlabs_status: AvailabilityStatus = AvailabilityStatus.MISSING_KEY,
    elevenlabs_voices: tuple[VoiceInfo, ...] = (),
) -> TtsPanelCatalog:
    engine_ids = tuple(available_engine_ids())
    return TtsPanelCatalog(
        engine_ids=engine_ids,
        availability={
            engine_id: _availability(
                engine_id,
                status=(elevenlabs_status if engine_id == "elevenlabs" else AvailabilityStatus.READY),
                voices=elevenlabs_voices if engine_id == "elevenlabs" else (),
            )
            for engine_id in engine_ids
        },
    )


def _context(
    settings: UserSettings | None = None,
    *,
    key: str = "",
) -> AppContext:
    preferences = settings or UserSettings()
    return AppContext(
        settings=Settings(elevenlabs_api_key=key),
        user_settings=preferences,
        workspace_root=Path("workspace"),
    )


def test_catalog_uses_registry_order_and_keeps_missing_key_visible() -> None:
    catalog = _catalog()
    settings = UserSettings(tts_engine="elevenlabs")
    context = _context(settings)

    assert catalog.engine_ids == tuple(available_engine_ids())
    assert tts_field_value(context, settings, "tts_engine", catalog) == ("elevenlabs (missing key)")


def test_engine_switch_sets_compatible_model_voice_and_profile() -> None:
    settings = UserSettings()
    catalog = _catalog()

    assert step_tts_field(settings, "tts_engine", -1, catalog)

    assert settings.tts_engine == "edge"
    assert settings.tts_provider_model_id == EDGE_PROVIDER_MODEL_ID
    assert settings.tts_voice_id == MAREK_VOICE_ID
    assert settings.active_tts_profile.concurrency == 16


def test_engine_switch_skips_registry_entries_without_panel_defaults() -> None:
    settings = UserSettings(tts_engine="sapi")
    catalog = _catalog()
    catalog = TtsPanelCatalog(
        engine_ids=(*catalog.engine_ids, "future"),
        availability=catalog.availability,
    )

    assert step_tts_field(settings, "tts_engine", 1, catalog)

    assert settings.tts_engine == "edge"


def test_invalid_fixed_engine_voices_normalize_but_custom_engines_preserve_ids() -> None:
    edge = UserSettings(
        tts_engine="edge",
        tts_provider_model_id="run6",
        tts_voice_id="unknown-edge",
    )
    sapi = UserSettings(
        tts_engine="sapi",
        tts_provider_model_id="run6",
        tts_voice_id="unknown-sapi",
    )
    elevenbytes = UserSettings(
        tts_engine="elevenbytes",
        tts_voice_id="custom-provider-id",
    )

    assert edge.tts_provider_model_id == EDGE_PROVIDER_MODEL_ID
    assert edge.tts_voice_id == MAREK_VOICE_ID
    assert sapi.tts_provider_model_id == "sapi5"
    assert sapi.tts_voice_id == "agnieszka"
    assert elevenbytes.tts_voice_id == "custom-provider-id"


def test_switch_to_elevenlabs_uses_cached_voice_or_explicit_unselected_state() -> None:
    cached_voice = VoiceInfo(
        id="voice-cached",
        label="Cached",
        engine_id="elevenlabs",
        language="pl",
    )
    cached = UserSettings()
    empty = UserSettings()

    step_tts_field(
        cached,
        "tts_engine",
        1,
        _catalog(
            elevenlabs_status=AvailabilityStatus.READY,
            elevenlabs_voices=(cached_voice,),
        ),
    )
    step_tts_field(empty, "tts_engine", 1, _catalog())

    assert cached.tts_engine == "elevenlabs"
    assert cached.tts_provider_model_id == DEFAULT_MODEL_ID
    assert cached.tts_voice_id == "voice-cached"
    assert empty.tts_voice_id == "<select-voice>"
    assert tts_voice_choices(empty, _catalog())[-1].label == ("select voice id (press e)")


def test_custom_tts_model_editing_is_only_available_for_elevenlabs() -> None:
    assert not _tts_model_is_freeform(UserSettings(tts_engine="edge"))
    assert not _tts_model_is_freeform(UserSettings(tts_engine="sapi"))
    assert not _tts_model_is_freeform(UserSettings(tts_engine="elevenbytes"))
    assert _tts_model_is_freeform(UserSettings(tts_engine="elevenlabs"))


def test_voice_profiles_restore_after_switching_back() -> None:
    settings = UserSettings(tts_engine="edge", tts_voice_id=MAREK_VOICE_ID)
    catalog = _catalog()
    settings.active_tts_profile.postprocess_tempo = 1.1

    step_tts_field(settings, "tts_voice_id", 1, catalog)
    assert settings.tts_voice_id == ZOFIA_VOICE_ID
    settings.active_tts_profile.postprocess_tempo = 1.55
    step_tts_field(settings, "tts_voice_id", 1, catalog)

    assert settings.tts_voice_id == MAREK_VOICE_ID
    assert settings.active_tts_profile.postprocess_tempo == 1.1


def test_conditional_rows_follow_selected_engine_and_codec() -> None:
    settings = UserSettings(tts_engine="elevenbytes", tts_provider_model_id="run6")

    run6_keys = {field.key for field in _visible_fields(settings)}
    settings.tts_provider_model_id = "run7"
    run7_keys = {field.key for field in _visible_fields(settings)}
    settings.tts_engine = "elevenlabs"
    elevenlabs_keys = {field.key for field in _visible_fields(settings)}
    settings.tts_output_profile = "flac"
    lossless_keys = {field.key for field in _visible_fields(settings)}

    assert "tts_option_stability" not in run6_keys
    assert "tts_option_stability" in run7_keys
    assert "elevenlabs_api_key" in elevenlabs_keys
    assert "tts_output_bitrate" not in lossless_keys


def test_all_audio_codecs_cycle_and_lossless_clears_bitrate() -> None:
    settings = UserSettings()
    catalog = _catalog()
    observed: set[str] = set()
    settings.tts_output_bitrate = "384k"

    for _ in AudioCodecProfile:
        observed.add(settings.tts_output_profile)
        step_tts_field(settings, "tts_output_profile", 1, catalog)

    assert observed == {profile.value for profile in AudioCodecProfile}
    while settings.tts_output_profile != "flac":
        step_tts_field(settings, "tts_output_profile", 1, catalog)
    assert settings.tts_output_bitrate is None


def test_bitrate_picker_uses_codec_compatible_values() -> None:
    settings = UserSettings(
        tts_output_profile="mp3",
        tts_output_bitrate=None,
    )
    catalog = _catalog()
    observed: set[str | None] = set()

    for _ in range(4):
        observed.add(settings.tts_output_bitrate)
        step_tts_field(settings, "tts_output_bitrate", 1, catalog)

    assert observed == {None, "192k", "256k", "320k"}


def test_run7_and_elevenlabs_options_are_bounded() -> None:
    settings = UserSettings(tts_provider_model_id="run7")
    catalog = _catalog()

    step_tts_field(settings, "tts_provider_model_id", 1, catalog)
    step_tts_field(settings, "tts_provider_model_id", -1, catalog)
    for _ in range(30):
        step_tts_field(settings, "tts_option_stability", 1, catalog)
    step_tts_field(settings, "tts_option_use_speaker_boost", 1, catalog)

    assert settings.active_tts_profile.engine_options["stability"] == 1.0
    assert settings.active_tts_profile.engine_options["use_speaker_boost"] is False

    settings.tts_engine = "elevenlabs"
    settings.tts_provider_model_id = DEFAULT_MODEL_ID
    settings.ensure_active_tts_profile()
    for _ in range(20):
        step_tts_field(settings, "tts_option_speed", -1, catalog)
    assert settings.active_tts_profile.engine_options["speed"] == 0.7


def test_edge_and_sapi_native_controls_use_engine_units() -> None:
    catalog = _catalog()
    edge = UserSettings(tts_engine="edge", tts_voice_id=MAREK_VOICE_ID)

    step_tts_field(edge, "tts_native_rate", 1, catalog)
    step_tts_field(edge, "tts_native_pitch", -1, catalog)

    assert edge.active_tts_profile.native_rate == "+45%"
    assert edge.active_tts_profile.native_pitch == "-5Hz"

    sapi = UserSettings(tts_engine="sapi", tts_voice_id="zosia")
    step_tts_field(sapi, "tts_concurrency", 1, catalog)
    step_tts_field(sapi, "tts_native_rate", 1, catalog)
    step_tts_field(sapi, "tts_native_volume", -1, catalog)

    assert sapi.active_tts_profile.concurrency == 1
    assert sapi.active_tts_profile.native_rate == 225.0
    assert sapi.active_tts_profile.native_volume == 0.65


def test_cached_and_custom_elevenlabs_voices_need_no_network() -> None:
    voices = (
        VoiceInfo(
            id="voice-cached",
            label="Cached voice",
            engine_id="elevenlabs",
            language="pl",
        ),
    )
    settings = UserSettings(
        tts_engine="elevenlabs",
        tts_provider_model_id=DEFAULT_MODEL_ID,
        tts_voice_id="voice-custom",
    )

    choices = tts_voice_choices(
        settings,
        _catalog(
            elevenlabs_status=AvailabilityStatus.READY,
            elevenlabs_voices=voices,
        ),
    )

    assert [(choice.value, choice.label) for choice in choices] == [
        ("voice-cached", "Cached voice"),
        ("voice-custom", "voice-custom (custom id)"),
    ]
    assert tts_model_ids(settings) == (
        "eleven_multilingual_v2",
        "eleven_flash_v2_5",
        "eleven_v3",
    )


def test_custom_elevenbytes_voice_crud_preserves_old_profile() -> None:
    settings = UserSettings()

    settings.add_elevenbytes_voice(
        alias="narrator",
        label="Narrator",
        voice_id="voice-one",
    )
    settings.tts_voice_id = "narrator"
    settings.ensure_active_tts_profile().postprocess_tempo = 1.4
    settings.update_elevenbytes_voice(
        "narrator",
        alias="reader",
        label="Reader",
        voice_id="voice-two",
    )

    assert settings.tts_voice_id == "reader"
    assert "elevenbytes:voice-one" in settings.tts_voice_profiles
    settings.remove_elevenbytes_voice("reader")
    assert settings.tts_voice_id == "dallin"


@pytest.mark.parametrize("alias", ["dallin", "DALLIN"])
def test_custom_voice_rejects_reserved_alias(alias: str) -> None:
    settings = UserSettings()

    with pytest.raises(ValueError, match="reserved"):
        settings.add_elevenbytes_voice(
            alias=alias,
            label="Voice",
            voice_id="id",
        )


def test_secret_save_remove_and_render_never_expose_value(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    settings = UserSettings(tts_engine="elevenlabs")
    context = _context(settings)
    catalog = _catalog()
    value = "paid-" + "value"

    save_elevenlabs_key(context, value, path=path)
    rendered = tts_field_value(
        context,
        settings,
        "elevenlabs_api_key",
        catalog,
    )
    editing = tts_field_value(
        context,
        settings,
        "elevenlabs_api_key",
        catalog,
        secret_editing=True,
    )

    assert rendered == "configured"
    assert editing == "••••••••"
    assert value not in repr(context.settings)
    remove_elevenlabs_key(context, path=path)
    assert context.settings.elevenlabs_api_key == ""


def test_process_environment_keeps_precedence_after_panel_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    context = _context()
    monkeypatch.setenv("ANISHIFT_ELEVENLABS_API_KEY", "process-secret")

    save_elevenlabs_key(context, "file-secret", path=path)

    assert context.settings.elevenlabs_api_key == "process-secret"
    assert "file-secret" in path.read_text(encoding="utf-8")
