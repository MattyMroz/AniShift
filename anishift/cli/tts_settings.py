"""Pure TTS/audio settings operations used by the interactive panel."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from anishift.bootstrap import AppContext
from anishift.config.env_file import env_path, update_env_value
from anishift.config.settings import Settings
from anishift.config.user_settings import (
    MAX_RETRIES_RANGE,
    TEMPO_RANGE,
    TTS_CONCURRENCY_RANGE,
    TtsVoiceProfileSettings,
    UserSettings,
)
from anishift.services.audio.types import AudioCodecProfile
from anishift.services.tts import (
    AvailabilitySource,
    AvailabilityStatus,
    EngineAvailability,
    TtsConfig,
)
from anishift.services.tts.engines import (
    available_engine_ids,
    create_engine,
)
from anishift.services.tts.engines.edge.constants import (
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.elevenbytes.constants import (
    DALLIN_ALIAS,
    DALLIN_LABEL,
    DALLIN_VOICE_ID,
    ENDPOINTS,
)
from anishift.services.tts.engines.elevenlabs.constants import (
    DEFAULT_MODEL_ID,
    FLASH_MODEL_ID,
    OUTPUT_FORMATS,
)
from anishift.services.tts.engines.sapi.constants import (
    SAPI_PROFILES,
    SAPI_RATE_MAX,
    SAPI_RATE_MIN,
)
from anishift.services.tts.engines.sapi.types import SapiVoiceProfile
from anishift.services.tts.errors import TtsError
from anishift.services.tts.protocols import TtsEngine
from anishift.services.tts.types import VoiceInfo

__all__ = [
    "TtsPanelCatalog",
    "VoiceChoice",
    "build_tts_catalog",
    "remove_elevenlabs_key",
    "save_elevenlabs_key",
    "step_tts_field",
    "tts_field_value",
    "tts_model_ids",
    "tts_voice_choices",
]

# ── Constants ──────────────────────────────────────────────────────────────

_SAPI_PROVIDER_MODEL_ID: Final[str] = "sapi5"
"""Stable settings identity for the SAPI 5 adapter."""

_ELEVENLABS_UNSELECTED_VOICE_ID: Final[str] = "<select-voice>"
"""Invalid provider id that prevents accidental paid synthesis before selection."""

_ENGINE_DEFAULTS: Final[dict[str, tuple[str, str]]] = {
    "edge": (EDGE_PROVIDER_MODEL_ID, MAREK_VOICE_ID),
    "elevenbytes": ("run6", DALLIN_ALIAS),
    "elevenlabs": (DEFAULT_MODEL_ID, _ELEVENLABS_UNSELECTED_VOICE_ID),
    "sapi": (_SAPI_PROVIDER_MODEL_ID, "agnieszka"),
}
"""Compatible model and voice defaults for engine transitions."""

_BITRATE_OPTIONS: Final[dict[str, tuple[str | None, ...]]] = {
    "aac": (None, "128k", "192k", "256k", "320k", "384k", "512k", "768k"),
    "eac3": (None, "192k", "384k", "640k"),
    "mp3": (None, "192k", "256k", "320k"),
    "opus": (None, "96k", "128k", "192k", "256k", "384k", "512k"),
}
"""Codec-compatible explicit bitrates plus automatic mode."""

_LOSSY_PROFILES: Final[frozenset[str]] = frozenset(("aac", "eac3", "mp3", "opus"))
"""Final codecs that accept a persisted bitrate."""

_STATUS_LABELS: Final[dict[AvailabilityStatus, str]] = {
    AvailabilityStatus.READY: "ready",
    AvailabilityStatus.MISSING_KEY: "missing key",
    AvailabilityStatus.MISSING_VOICE: "missing voice",
    AvailabilityStatus.MISSING_BINARY: "missing binary",
    AvailabilityStatus.OFFLINE: "offline",
    AvailabilityStatus.SERVICE_UNAVAILABLE: "unavailable",
    AvailabilityStatus.UNSUPPORTED_PLATFORM: "unsupported",
}
"""Concise non-secret labels shown next to every registered engine."""


@dataclass(frozen=True, slots=True)
class VoiceChoice:
    """One user-facing voice label and persisted selection value."""

    value: str
    label: str


@dataclass(frozen=True, slots=True)
class TtsPanelCatalog:
    """Non-live availability and voice snapshot used for one panel session."""

    engine_ids: tuple[str, ...]
    availability: dict[str, EngineAvailability]


def build_tts_catalog(context: AppContext) -> TtsPanelCatalog:
    """Probe every registered engine without network synthesis or paid calls."""
    engine_ids: tuple[str, ...] = tuple(available_engine_ids())
    availability: dict[str, EngineAvailability] = {}
    for engine_id in engine_ids:
        try:
            engine: TtsEngine = create_engine(_probe_config(context, engine_id))
            availability[engine_id] = asyncio.run(_availability_and_close(engine))
        except (TtsError, KeyError, OSError, RuntimeError, ValueError) as error:
            availability[engine_id] = EngineAvailability(
                status=AvailabilityStatus.SERVICE_UNAVAILABLE,
                message=str(error),
                checked_at=datetime.now(UTC),
                source=AvailabilitySource.CONFIG,
            )
    return TtsPanelCatalog(engine_ids=engine_ids, availability=availability)


async def _availability_and_close(engine: TtsEngine) -> EngineAvailability:
    availability: EngineAvailability = await engine.availability(live=False)
    with suppress(TtsError, OSError, RuntimeError, ValueError):
        await engine.close()
    return availability


def _probe_config(context: AppContext, engine_id: str) -> TtsConfig:
    settings: UserSettings = context.user_settings
    if engine_id == settings.tts_engine:
        model_id: str = settings.tts_provider_model_id
        voice_id: str = settings.resolved_tts_voice_id
        if engine_id == "elevenlabs" and voice_id == _ELEVENLABS_UNSELECTED_VOICE_ID:
            voice_id = "voice-probe-placeholder"
        profile: TtsVoiceProfileSettings = settings.active_tts_profile
    else:
        model_id, voice_id = _ENGINE_DEFAULTS[engine_id]
        if engine_id == "elevenbytes":
            voice_id = DALLIN_VOICE_ID
        elif engine_id == "elevenlabs":
            voice_id = settings.tts_voice_id or "unselected"
        elif engine_id == "sapi":
            voice_id = SAPI_PROFILES["agnieszka"].resolved_voice_id
        profile = TtsVoiceProfileSettings(concurrency=1 if engine_id == "sapi" else None)
    concurrency: int = 1 if engine_id == "sapi" else profile.concurrency or 1
    return TtsConfig(
        engine_id=engine_id,
        provider_model_id=model_id,
        voice_id=voice_id,
        max_concurrency=concurrency,
        queue_capacity=max(2, 2 * concurrency),
        max_retries=settings.tts_max_retries,
        native_rate=profile.native_rate,
        native_volume=profile.native_volume,
        native_pitch=profile.native_pitch,
        engine_options=profile.engine_options,
        elevenlabs_api_key=context.settings.elevenlabs_api_key,
        metadata_cache_root=env_path().parent / "config",
    )


def tts_model_ids(settings: UserSettings) -> tuple[str, ...]:
    """Return valid built-ins plus the current custom official model."""
    if settings.tts_engine == "elevenbytes":
        return tuple(ENDPOINTS)
    if settings.tts_engine == "edge":
        return (EDGE_PROVIDER_MODEL_ID,)
    if settings.tts_engine == "sapi":
        return (_SAPI_PROVIDER_MODEL_ID,)
    builtins: tuple[str, ...] = (DEFAULT_MODEL_ID, FLASH_MODEL_ID)
    if settings.tts_provider_model_id in builtins:
        return builtins
    return (*builtins, settings.tts_provider_model_id)


def tts_voice_choices(
    settings: UserSettings,
    catalog: TtsPanelCatalog,
) -> tuple[VoiceChoice, ...]:
    """Return engine-compatible voices without triggering a network refresh."""
    if settings.tts_engine == "elevenbytes":
        voices: list[VoiceChoice] = [VoiceChoice(DALLIN_ALIAS, DALLIN_LABEL)]
        voices.extend(VoiceChoice(item.alias, item.label) for item in settings.elevenbytes_custom_voices)
        known: set[str] = {voice.value.casefold() for voice in voices}
        if settings.tts_voice_id.casefold() not in known:
            voices.append(
                VoiceChoice(
                    settings.tts_voice_id,
                    f"{settings.tts_voice_id} (custom id)",
                ),
            )
        return tuple(voices)
    if settings.tts_engine == "edge":
        return (
            VoiceChoice(MAREK_VOICE_ID, "Marek — Edge"),
            VoiceChoice(ZOFIA_VOICE_ID, "Zofia — Edge"),
        )
    if settings.tts_engine == "sapi":
        return tuple(VoiceChoice(alias, profile.label) for alias, profile in SAPI_PROFILES.items())
    cached: tuple[VoiceInfo, ...] = catalog.availability.get(
        "elevenlabs",
        _unavailable("ElevenLabs availability missing"),
    ).voices
    voices = [VoiceChoice(voice.id, voice.label) for voice in cached]
    if settings.tts_voice_id == _ELEVENLABS_UNSELECTED_VOICE_ID:
        voices.append(
            VoiceChoice(
                _ELEVENLABS_UNSELECTED_VOICE_ID,
                "select voice id (press e)",
            ),
        )
        return tuple(voices)
    if settings.tts_voice_id and all(voice.value != settings.tts_voice_id for voice in voices):
        voices.append(
            VoiceChoice(settings.tts_voice_id, f"{settings.tts_voice_id} (custom id)"),
        )
    return tuple(voices)


def step_tts_field(  # noqa: C901, PLR0912 - typed row dispatcher
    settings: UserSettings,
    field_key: str,
    delta: int,
    catalog: TtsPanelCatalog,
) -> bool:
    """Advance one TTS/audio field and return whether it was handled."""
    if field_key == "tts_engine":
        selectable_engine_ids: tuple[str, ...] = tuple(
            engine_id for engine_id in catalog.engine_ids if engine_id in _ENGINE_DEFAULTS
        )
        engine_id: str = _cycle(selectable_engine_ids, settings.tts_engine, delta)
        _switch_engine(settings, engine_id, catalog)
    elif field_key == "tts_provider_model_id":
        settings.tts_provider_model_id = _cycle(
            tts_model_ids(settings),
            settings.tts_provider_model_id,
            delta,
        )
        _normalize_engine_options(settings)
    elif field_key == "tts_voice_id":
        choices: tuple[VoiceChoice, ...] = tts_voice_choices(settings, catalog)
        if choices:
            settings.tts_voice_id = _cycle(
                tuple(choice.value for choice in choices),
                settings.tts_voice_id,
                delta,
            )
            settings.ensure_active_tts_profile()
    elif field_key == "tts_max_retries":
        settings.tts_max_retries = _clamp_int(
            settings.tts_max_retries + delta,
            *MAX_RETRIES_RANGE,
        )
    elif field_key == "tts_concurrency":
        profile = settings.ensure_active_tts_profile()
        if settings.tts_engine == "sapi":
            profile.concurrency = 1
        else:
            current: int = profile.concurrency or 1
            profile.concurrency = _clamp_int(
                current + delta,
                *TTS_CONCURRENCY_RANGE,
            )
    elif field_key == "tts_postprocess_tempo":
        profile = settings.ensure_active_tts_profile()
        profile.postprocess_tempo = _clamp_float(
            profile.postprocess_tempo + delta * 0.05,
            *TEMPO_RANGE,
        )
    elif field_key == "tts_voice_mix_offset_db":
        profile = settings.ensure_active_tts_profile()
        profile.voice_mix_offset_db = _clamp_float(
            profile.voice_mix_offset_db + delta * 0.5,
            -30.0,
            30.0,
        )
    elif field_key.startswith("tts_option_"):
        _step_engine_option(settings, field_key.removeprefix("tts_option_"), delta)
    elif field_key in {"tts_native_rate", "tts_native_volume", "tts_native_pitch"}:
        _step_native_value(settings, field_key, delta)
    elif field_key == "tts_output_profile":
        settings.tts_output_profile = _cycle(
            tuple(profile.value for profile in AudioCodecProfile),
            settings.tts_output_profile,
            delta,
        )
        if settings.tts_output_profile not in _LOSSY_PROFILES:
            settings.tts_output_bitrate = None
    elif field_key == "tts_output_bitrate":
        if settings.tts_output_profile in _LOSSY_PROFILES:
            settings.tts_output_bitrate = _cycle_optional(
                _BITRATE_OPTIONS[settings.tts_output_profile],
                settings.tts_output_bitrate,
                delta,
            )
    elif field_key == "narrator_mix_base_gain_db":
        settings.narrator_mix_base_gain_db = _clamp_float(
            settings.narrator_mix_base_gain_db + delta * 0.5,
            -30.0,
            30.0,
        )
    elif field_key == "original_gain_db":
        settings.original_gain_db = _clamp_float(
            settings.original_gain_db + delta * 0.5,
            -30.0,
            30.0,
        )
    elif field_key in {
        "elevenlabs_api_key",
        "tts_sapi_architecture",
        "tts_timeline_policy",
        "tts_resume_enabled",
        "tts_debug_artifacts",
    }:
        pass
    else:
        return False
    return True


def tts_field_value(  # noqa: C901, PLR0911, PLR0912 - typed row renderer
    context: AppContext,
    settings: UserSettings,
    field_key: str,
    catalog: TtsPanelCatalog,
    *,
    secret_editing: bool = False,
) -> str | None:
    """Render one TTS/audio field without exposing secret material."""
    profile: TtsVoiceProfileSettings = settings.active_tts_profile
    if field_key == "tts_engine":
        availability: EngineAvailability = catalog.availability.get(
            settings.tts_engine,
            _unavailable("availability missing"),
        )
        return f"{settings.tts_engine} ({_STATUS_LABELS[availability.status]})"
    if field_key == "tts_provider_model_id":
        return settings.tts_provider_model_id
    if field_key == "tts_voice_id":
        choices: tuple[VoiceChoice, ...] = tts_voice_choices(settings, catalog)
        selected: VoiceChoice | None = next(
            (choice for choice in choices if choice.value == settings.tts_voice_id),
            None,
        )
        return selected.label if selected is not None else settings.tts_voice_id
    if field_key == "tts_max_retries":
        return str(settings.tts_max_retries)
    if field_key == "tts_concurrency":
        suffix: str = " (fixed)" if settings.tts_engine == "sapi" else ""
        return f"{profile.concurrency or 1}{suffix}"
    if field_key == "tts_postprocess_tempo":
        return f"{profile.postprocess_tempo:.2f}x"
    if field_key == "tts_voice_mix_offset_db":
        return f"{profile.voice_mix_offset_db:+.1f} dB"
    if field_key == "elevenlabs_api_key":
        if secret_editing:
            return "••••••••"
        return "configured" if context.settings.elevenlabs_api_key else "missing key"
    if field_key.startswith("tts_option_"):
        return _engine_option_value(profile, field_key.removeprefix("tts_option_"))
    if field_key in {"tts_native_rate", "tts_native_volume", "tts_native_pitch"}:
        return _native_value(settings, field_key)
    if field_key == "tts_sapi_architecture":
        sapi_profile = _sapi_profile(settings.tts_voice_id)
        return sapi_profile.architecture.value
    if field_key == "tts_output_profile":
        return settings.tts_output_profile
    if field_key == "tts_output_bitrate":
        return settings.tts_output_bitrate or "auto"
    if field_key == "narrator_mix_base_gain_db":
        return f"{settings.narrator_mix_base_gain_db:+.1f} dB"
    if field_key == "original_gain_db":
        return f"{settings.original_gain_db:+.1f} dB"
    if field_key == "tts_timeline_policy":
        return f"{settings.tts_timeline_policy} (implemented)"
    if field_key == "tts_resume_enabled":
        return "enabled"
    if field_key == "tts_debug_artifacts":
        return "resume clips + manifests"
    return None


def save_elevenlabs_key(
    context: AppContext,
    value: str,
    *,
    path: Path | None = None,
) -> None:
    """Persist one literal key and refresh the in-memory env settings."""
    resolved: str = value.strip()
    if not resolved:
        message: str = "ElevenLabs API key cannot be empty"
        raise ValueError(message)
    target: Path = path or env_path()
    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", resolved, path=target)
    context.settings = Settings(_env_file=target)


def remove_elevenlabs_key(
    context: AppContext,
    *,
    path: Path | None = None,
) -> None:
    """Remove the file-backed key and refresh process-precedence settings."""
    target: Path = path or env_path()
    update_env_value("ANISHIFT_ELEVENLABS_API_KEY", None, path=target)
    context.settings = Settings(_env_file=target)


def _switch_engine(
    settings: UserSettings,
    engine_id: str,
    catalog: TtsPanelCatalog,
) -> None:
    model_id, default_voice = _ENGINE_DEFAULTS[engine_id]
    settings.tts_engine = engine_id
    settings.tts_provider_model_id = model_id
    if engine_id == "elevenlabs":
        cached: tuple[VoiceInfo, ...] = catalog.availability.get(
            engine_id,
            _unavailable("ElevenLabs availability missing"),
        ).voices
        settings.tts_voice_id = cached[0].id if cached else _ELEVENLABS_UNSELECTED_VOICE_ID
    else:
        settings.tts_voice_id = default_voice
    settings.ensure_active_tts_profile()
    _normalize_engine_options(settings)


def _normalize_engine_options(settings: UserSettings) -> None:
    profile: TtsVoiceProfileSettings = settings.ensure_active_tts_profile()
    if settings.tts_engine == "elevenbytes":
        if settings.tts_provider_model_id == "run6":
            profile.engine_options = {}
            return
        profile.engine_options = {
            "similarity_boost": _option_float(profile, "similarity_boost", 0.75),
            "stability": _option_float(profile, "stability", 0.5),
            "style": _option_float(profile, "style", 0.0),
            "use_speaker_boost": _option_bool(profile, "use_speaker_boost", True),
        }
        return
    if settings.tts_engine == "elevenlabs":
        profile.engine_options = {
            "output_format": _option_string(
                profile,
                "output_format",
                "mp3_44100_128",
            ),
            "similarity_boost": _option_float(profile, "similarity_boost", 0.75),
            "speed": _option_float(profile, "speed", 1.0),
            "stability": _option_float(profile, "stability", 0.5),
            "style": _option_float(profile, "style", 0.0),
            "use_speaker_boost": _option_bool(profile, "use_speaker_boost", True),
        }
        return
    profile.engine_options = {}


def _step_engine_option(
    settings: UserSettings,
    key: str,
    delta: int,
) -> None:
    profile: TtsVoiceProfileSettings = settings.ensure_active_tts_profile()
    if key == "output_format":
        profile.engine_options[key] = _cycle(
            tuple(OUTPUT_FORMATS),
            _option_string(profile, key, "mp3_44100_128"),
            delta,
        )
        return
    if key == "use_speaker_boost":
        profile.engine_options[key] = not _option_bool(profile, key, True)
        return
    default: float = (
        1.0 if key == "speed" else 0.75 if key == "similarity_boost" else 0.5 if key == "stability" else 0.0
    )
    minimum: float = 0.7 if key == "speed" else 0.0
    maximum: float = 1.2 if key == "speed" else 1.0
    profile.engine_options[key] = _clamp_float(
        _option_float(profile, key, default) + delta * 0.05,
        minimum,
        maximum,
    )


def _step_native_value(
    settings: UserSettings,
    field_key: str,
    delta: int,
) -> None:
    profile: TtsVoiceProfileSettings = settings.ensure_active_tts_profile()
    if settings.tts_engine == "edge":
        if field_key == "tts_native_rate":
            profile.native_rate = _step_unit_string(
                profile.native_rate,
                default=DEFAULT_RATE,
                suffix="%",
                delta=delta * 5,
                minimum=-100,
                maximum=100,
            )
        elif field_key == "tts_native_volume":
            profile.native_volume = _step_unit_string(
                profile.native_volume,
                default=DEFAULT_VOLUME,
                suffix="%",
                delta=delta * 5,
                minimum=-100,
                maximum=100,
            )
        else:
            profile.native_pitch = _step_unit_string(
                profile.native_pitch,
                default=DEFAULT_PITCH,
                suffix="Hz",
                delta=delta * 5,
                minimum=-100,
                maximum=100,
            )
        return
    sapi_profile = _sapi_profile(settings.tts_voice_id)
    if field_key == "tts_native_rate":
        current_rate: float = float(
            profile.native_rate if profile.native_rate is not None else sapi_profile.default_native_rate
        )
        if sapi_profile.uses_wpm_rate:
            profile.native_rate = _clamp_float(
                current_rate + delta * 25,
                50.0,
                500.0,
            )
        else:
            profile.native_rate = _clamp_int(
                round(current_rate) + delta,
                SAPI_RATE_MIN,
                SAPI_RATE_MAX,
            )
    elif field_key == "tts_native_volume":
        current_volume: float = float(
            profile.native_volume if profile.native_volume is not None else sapi_profile.default_native_volume
        )
        if sapi_profile.uses_fractional_volume:
            profile.native_volume = _clamp_float(
                current_volume + delta * 0.05,
                0.0,
                1.0,
            )
        else:
            profile.native_volume = _clamp_int(
                round(current_volume) + delta * 5,
                0,
                100,
            )


def _native_value(settings: UserSettings, field_key: str) -> str:
    profile: TtsVoiceProfileSettings = settings.active_tts_profile
    if settings.tts_engine == "edge":
        value: str | float | None = {
            "tts_native_rate": profile.native_rate or DEFAULT_RATE,
            "tts_native_volume": profile.native_volume or DEFAULT_VOLUME,
            "tts_native_pitch": profile.native_pitch or DEFAULT_PITCH,
        }[field_key]
        return str(value)
    sapi_profile = _sapi_profile(settings.tts_voice_id)
    value = profile.native_rate if field_key == "tts_native_rate" else profile.native_volume
    if value is None:
        value = (
            sapi_profile.default_native_rate if field_key == "tts_native_rate" else sapi_profile.default_native_volume
        )
    if field_key == "tts_native_rate" and sapi_profile.uses_wpm_rate:
        return f"{float(value):g} WPM"
    if field_key == "tts_native_rate":
        return f"{int(float(value))}"
    if sapi_profile.uses_fractional_volume:
        return f"{float(value):.2f}"
    return f"{int(float(value))}"


def _engine_option_value(
    profile: TtsVoiceProfileSettings,
    key: str,
) -> str:
    if key == "output_format":
        return _option_string(profile, key, "mp3_44100_128")
    if key == "use_speaker_boost":
        return "yes" if _option_bool(profile, key, True) else "no"
    default: float = (
        1.0 if key == "speed" else 0.75 if key == "similarity_boost" else 0.5 if key == "stability" else 0.0
    )
    return f"{_option_float(profile, key, default):.2f}"


def _option_float(
    profile: TtsVoiceProfileSettings,
    key: str,
    default: float,
) -> float:
    value: object = profile.engine_options.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _option_bool(
    profile: TtsVoiceProfileSettings,
    key: str,
    default: bool,
) -> bool:
    value: object = profile.engine_options.get(key)
    return value if isinstance(value, bool) else default


def _option_string(
    profile: TtsVoiceProfileSettings,
    key: str,
    default: str,
) -> str:
    value: object = profile.engine_options.get(key)
    return value if isinstance(value, str) and value else default


def _sapi_profile(value: str) -> SapiVoiceProfile:
    candidate: str = value.casefold()
    for alias, profile in SAPI_PROFILES.items():
        if candidate in {
            alias,
            profile.voice_name.casefold(),
            profile.resolved_voice_id.casefold(),
        }:
            return profile
    return SAPI_PROFILES["agnieszka"]


def _step_unit_string(  # noqa: PLR0913 - explicit numeric unit contract
    value: str | float | None,
    *,
    default: str,
    suffix: str,
    delta: int,
    minimum: int,
    maximum: int,
) -> str:
    raw: str = str(value if value is not None else default)
    numeric: int = int(raw.removesuffix(suffix))
    stepped: int = _clamp_int(numeric + delta, minimum, maximum)
    sign: str = "+" if stepped >= 0 else ""
    return f"{sign}{stepped}{suffix}"


def _cycle(options: tuple[str, ...], current: str, delta: int) -> str:
    if not options:
        return current
    index: int = options.index(current) if current in options else 0
    return options[(index + delta) % len(options)]


def _cycle_optional(
    options: tuple[str | None, ...],
    current: str | None,
    delta: int,
) -> str | None:
    index: int = options.index(current) if current in options else 0
    return options[(index + delta) % len(options)]


def _clamp_float(value: float, low: float, high: float) -> float:
    return round(min(max(value, low), high), 2)


def _clamp_int(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


def _unavailable(message: str) -> EngineAvailability:
    return EngineAvailability(
        status=AvailabilityStatus.SERVICE_UNAVAILABLE,
        message=message,
        checked_at=datetime.now(UTC),
        source=AvailabilitySource.CONFIG,
    )
