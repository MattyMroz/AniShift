"""Panel preferences persisted to ``config/settings.json`` next to the code.

These are the choices the settings screens of the shell edit (mode, engines,
voice, output placement...). They live in ``<repo>/config/settings.json`` — OUTSIDE the
workspace, so the folder the user drops MKV files into stays clean, while the
file stays visible and hand-editable. The file is created on first save.

Public API:
    UserSettings: Dataclass holding panel preferences.
    Mode: Processing mode literal.
    OutputVariant: Output-assembly variant literal.
    config_path: Location of ``settings.json``.
    load_user_settings: Read the file (defaults when absent / unreadable).
    save_user_settings: Write the file atomically (creates ``config/`` if needed).
"""

from __future__ import annotations

import json
import math
import re
import warnings
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Final, Literal

from anishift.paths import config_path
from anishift.services.audio.types import AudioCodecProfile, TimelinePolicy
from anishift.services.extraction.tracks import DEFAULT_AUDIO_PRIORITY, DEFAULT_SUBTITLE_PRIORITY
from anishift.services.llm.engines import available_engine_ids as available_llm_engine_ids
from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT
from anishift.services.translation.engines import available_engine_ids
from anishift.services.translation.engines.llm.constants import DEFAULT_STYLE_NAME
from anishift.services.translation.engines.llm.prompts import available_style_names
from anishift.services.translation.linebreak import DEFAULT_MAX_CHARS, MAX_LINES
from anishift.services.tts.engines import available_engine_ids as available_tts_engine_ids
from anishift.services.tts.engines.edge.constants import (
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.elevenbytes.constants import (
    DALLIN_ALIAS,
    DALLIN_VOICE_ID,
    ENDPOINTS,
)
from anishift.services.tts.engines.elevenlabs.constants import DEFAULT_MODEL_ID
from anishift.services.tts.engines.sapi.constants import SAPI_PROFILES
from anishift.utils.logger import get_logger

__all__ = [
    "PALANTIR_ENROLLMENT_URL_PATTERN",
    "CompositionQualityPreset",
    "CustomVoiceSetting",
    "JsonScalar",
    "Mode",
    "OutputVariant",
    "ProcessingOrderPolicy",
    "SettingsSchemaWarning",
    "TtsVoiceProfileSettings",
    "UserSettings",
    "config_path",
    "default_tts_voice_profiles",
    "load_user_settings",
    "save_user_settings",
    "tts_profile_key",
]

logger = get_logger(__name__)

Mode = Literal["auto", "manual"]
"""Processing mode: ``auto`` (Enter processes everything) or ``manual``."""

OutputVariant = Literal["players", "merge", "burn"]
"""Output assembly: soft players, MKV merge, or burned-in MP4."""

CompositionQualityPreset = Literal["high", "balanced", "compact"]
"""Named quality target for hardsub rendering."""

ProcessingOrderPolicy = Literal["ready_first", "strict_natural"]
"""Cross-file scheduling policy for translation, TTS, and audio."""

type JsonScalar = str | int | float | bool | None
"""JSON scalar accepted by provider-specific TTS options."""

# ── Constants ──────────────────────────────────────────────────────────────

SETTINGS_SCHEMA_VERSION: Final[int] = 3
"""Current persisted user-settings schema."""

TEMPO_RANGE: Final[tuple[float, float]] = (0.5, 2.0)
"""Allowed inclusive range for the speech tempo multiplier."""

VOLUME_RANGE: Final[tuple[int, int]] = (0, 100)
"""Allowed inclusive range for the output volume percentage."""

BATCH_SIZE_RANGE: Final[tuple[int, int]] = (0, 500)
"""Allowed inclusive range for the translation batch size (0 = engine default)."""

CONCURRENCY_RANGE: Final[tuple[int, int]] = (1, 16)
"""Allowed inclusive range for the translation batch concurrency."""

MAX_RETRIES_RANGE: Final[tuple[int, int]] = (0, 10)
"""Allowed inclusive range for the translation retry count."""

LINE_CHARS_RANGE: Final[tuple[int, int]] = (20, 120)
"""Allowed inclusive range for the characters one subtitle verse may hold."""

EVENT_LINES_RANGE: Final[tuple[int, int]] = (1, 4)
"""Allowed inclusive range for the verses one subtitle event may occupy."""

CHUNK_CHARS_RANGE: Final[tuple[int, int]] = (200, 4000)
"""Allowed inclusive range for the characters packed into one translation request."""

LLM_TEMPERATURE_RANGE: Final[tuple[float, float]] = (0.0, 2.0)
"""Allowed inclusive range for the LLM sampling temperature."""

LLM_TOP_P_RANGE: Final[tuple[float, float]] = (0.0, 1.0)
"""Allowed inclusive range for the LLM nucleus-sampling top-p."""

LLM_MAX_TOKENS_RANGE: Final[tuple[int, int]] = (1, 32000)
"""Allowed inclusive range for explicit LLM max output tokens."""

LLM_MAX_CONCURRENCY_RANGE: Final[tuple[int, int]] = (1, 16)
"""Allowed inclusive range for concurrent LLM file requests."""

TTS_MAX_RETRIES_RANGE: Final[tuple[int, int]] = (0, 10)
"""Allowed inclusive range for TTS retry attempts."""

TTS_CONCURRENCY_RANGE: Final[tuple[int, int]] = (1, 100)
"""Allowed inclusive range for persisted per-voice concurrency."""

PALANTIR_ENROLLMENT_URL_PATTERN: Final[str] = r"(?:https://[^\s/?#]+(?:/[^\s?#]*)?)?"
"""Accepted Palantir enrollment address, or the empty "not configured" value.

An absolute ``https`` address with a host and an optional path prefix, carrying
neither a query nor a fragment — the rule the model catalog applied before the
address became a panel preference. This expression is its single owner: the
settings catalog validates an edit with it and the tolerant loader matches
persisted text against it, so an editor and the preference file cannot disagree.
"""

_MODES: Final[frozenset[str]] = frozenset(("auto", "manual"))
"""Accepted values for the ``mode`` field."""

_PROCESSING_ORDER_POLICIES: Final[frozenset[str]] = frozenset(("ready_first", "strict_natural"))
"""Accepted values for the ``processing_order_policy`` field."""

_OUTPUT_VARIANTS: Final[frozenset[str]] = frozenset(("players", "merge", "burn"))
"""Accepted values for the ``output_variant`` field."""

_COMPOSITION_PRESETS: Final[frozenset[str]] = frozenset(("high", "balanced", "compact"))
"""Accepted values for the ``composition_quality_preset`` field."""

_DEFAULT_AUDIO_LANGUAGES: Final[tuple[str, ...]] = DEFAULT_AUDIO_PRIORITY
"""Preferred source audio languages, most wanted first."""

_DEFAULT_SUBTITLE_LANGUAGES: Final[tuple[str, ...]] = DEFAULT_SUBTITLE_PRIORITY
"""Preferred source subtitle languages, most wanted first."""

_TTS_OUTPUT_PROFILES: Final[frozenset[str]] = frozenset(profile.value for profile in AudioCodecProfile)
"""Accepted final narration sidecar profiles."""

_TTS_TIMELINE_POLICIES: Final[frozenset[str]] = frozenset(policy.value for policy in TimelinePolicy)
"""Accepted narration timeline policies."""

_LOSSY_OUTPUT_PROFILES: Final[frozenset[str]] = frozenset(("aac", "eac3", "mp3", "opus"))
"""Output profiles for which a bitrate may be persisted."""

_BITRATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[1-9][0-9]*[kKmM]\Z")
"""Accepted FFmpeg bitrate syntax for lossy output profiles."""

_ENROLLMENT_URL_RE: Final[re.Pattern[str]] = re.compile(PALANTIR_ENROLLMENT_URL_PATTERN)
"""Compiled ``PALANTIR_ENROLLMENT_URL_PATTERN`` used by the tolerant loader."""

_DALLIN_PROFILE_KEY: Final[str] = f"elevenbytes:{DALLIN_VOICE_ID}"
"""Stable profile key for the built-in ElevenBytes voice."""

_SAPI_AGNIESZKA_PROFILE_KEY: Final[str] = f"sapi:{SAPI_PROFILES['agnieszka'].resolved_voice_id}"
"""Stable architecture-qualified profile key for Agnieszka."""

_SAPI_ZOSIA_PROFILE_KEY: Final[str] = f"sapi:{SAPI_PROFILES['zosia'].resolved_voice_id}"
"""Stable architecture-qualified profile key for Zosia."""

_EDGE_MAREK_PROFILE_KEY: Final[str] = f"edge:{MAREK_VOICE_ID}"
"""Stable profile key for Edge Marek."""

_EDGE_ZOFIA_PROFILE_KEY: Final[str] = f"edge:{ZOFIA_VOICE_ID}"
"""Stable profile key for Edge Zofia."""

_MISSING: Final[object] = object()
"""Sentinel distinguishing an omitted nested profile field from JSON null."""

_SAPI_PROVIDER_MODEL_ID: Final[str] = "sapi5"
"""Stable provider model identity shown for the Windows SAPI adapter."""


class SettingsSchemaWarning(UserWarning):
    """Warning emitted when persisted settings use an unsupported schema."""


@dataclass(slots=True)
class TtsVoiceProfileSettings:
    """Persistent synthesis and post-processing values for one resolved voice."""

    postprocess_tempo: float = 1.0
    voice_mix_offset_db: float = 0.0
    concurrency: int | None = None
    native_rate: str | float | None = None
    native_volume: str | float | None = None
    native_pitch: str | float | None = None
    engine_options: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CustomVoiceSetting:
    """One user-defined ElevenBytes voice alias."""

    alias: str
    label: str
    voice_id: str


def tts_profile_key(engine_id: str, resolved_voice_id: str) -> str:
    """Build a stable profile key from an engine and resolved voice identity."""
    return f"{engine_id}:{resolved_voice_id}"


def default_tts_voice_profiles() -> dict[str, TtsVoiceProfileSettings]:
    """Return independent built-in profile defaults for every bundled voice."""
    return {
        _DALLIN_PROFILE_KEY: TtsVoiceProfileSettings(
            postprocess_tempo=1.25,
            voice_mix_offset_db=-2.0,
            concurrency=85,
        ),
        _SAPI_AGNIESZKA_PROFILE_KEY: TtsVoiceProfileSettings(
            voice_mix_offset_db=2.0,
            concurrency=1,
            native_rate=5,
            native_volume=65,
        ),
        _SAPI_ZOSIA_PROFILE_KEY: TtsVoiceProfileSettings(
            concurrency=1,
            native_rate=200,
            native_volume=0.7,
        ),
        _EDGE_MAREK_PROFILE_KEY: TtsVoiceProfileSettings(
            concurrency=16,
            native_rate=DEFAULT_RATE,
            native_volume=DEFAULT_VOLUME,
        ),
        _EDGE_ZOFIA_PROFILE_KEY: TtsVoiceProfileSettings(
            concurrency=16,
            native_rate=DEFAULT_RATE,
            native_volume=DEFAULT_VOLUME,
        ),
    }


@dataclass(slots=True)
class UserSettings:
    """Panel preferences (mode, engines, voice, output placement).

    Attributes:
        mode: ``"auto"`` (Enter processes everything) or ``"manual"``.
        processing_order_policy: Ready-first throughput or strict natural order.
        translation_engine: Selected translation engine id.
        subtitle_max_chars_per_line: Characters one displayed verse may hold.
        subtitle_max_lines_per_event: Verses one subtitle event may occupy.
        translation_chunk_chars: Characters packed into one translation request.
        translation_batch_size: Lines per request (0 = engine default).
        translation_concurrency: Concurrent batches per file (semaphore).
        translation_max_retries: Retry attempts per batch.
        llm_provider: Selected LLM provider id.
        llm_provider_model_id: Arbitrary provider model id.
        llm_temperature: LLM sampling temperature; low keeps translation repeatable.
        llm_top_p: LLM nucleus-sampling top-p; the range maximum filters nothing.
        llm_max_output_tokens: Explicit provider output limit, in tokens.
        llm_translation_style: Selected packaged translation style name.
        llm_max_concurrency: Maximum concurrently translated LLM files.
        primary_model_alias: Catalog alias of the main model role, independent of
            the translation model; empty means no main model is selected.
        palantir_enrollment_base_url: HTTPS address of the Palantir enrollment
            serving the proxy routes; empty means it is not configured. Owned
            here, never in the model catalog, because ``/connect`` edits it.
        schema_version: Persisted settings schema.
        tts_engine: Selected text-to-speech engine id.
        tts_provider_model_id: Provider model or endpoint variant.
        tts_voice_id: Selected TTS alias or provider voice id.
        tts_max_retries: Retry attempts for transient synthesis failures.
        elevenbytes_vpn_enabled: Whether ElevenBytes traffic must use the VPN.
        tts_output_profile: Final narration sidecar codec profile.
        tts_output_bitrate: Optional FFmpeg bitrate for lossy profiles.
        tts_timeline_policy: Narration overlap placement policy.
        narrator_mix_base_gain_db: Base narrator gain used only while mixing.
        original_gain_db: Original soundtrack gain used while mixing.
        tts_voice_profiles: Settings keyed by engine and resolved voice id.
        elevenbytes_custom_voices: User-defined ElevenBytes aliases.
        output_variant: Output assembly variant.
        composition_quality_preset: Quality target for burned-in rendering.
        audio_language_priority: Preferred source audio languages, best first.
        subtitle_language_priority: Preferred source subtitle languages, best
            first. Both lists drive automatic track selection only; manual mode
            still asks per file.
    """

    schema_version: int = SETTINGS_SCHEMA_VERSION
    mode: Mode = "auto"
    processing_order_policy: ProcessingOrderPolicy = "ready_first"
    translation_engine: str = "google"
    subtitle_max_chars_per_line: int = DEFAULT_MAX_CHARS
    subtitle_max_lines_per_event: int = MAX_LINES
    translation_chunk_chars: int = DEFAULT_CHAR_LIMIT
    translation_batch_size: int = 0
    translation_concurrency: int = 1
    translation_max_retries: int = 3
    llm_provider: str = "gemini"
    llm_provider_model_id: str = "gemini-3.5-flash-lite"
    llm_temperature: float | None = 0.3
    llm_top_p: float | None = 1.0
    llm_max_output_tokens: int | None = 8192
    llm_translation_style: str = DEFAULT_STYLE_NAME
    llm_max_concurrency: int = 4
    primary_model_alias: str = ""
    palantir_enrollment_base_url: str = ""
    tts_engine: str = "elevenbytes"
    tts_provider_model_id: str = "run6"
    tts_voice_id: str = DALLIN_ALIAS
    tts_max_retries: int = 3
    elevenbytes_vpn_enabled: bool = False
    tts_output_profile: str = AudioCodecProfile.EAC3.value
    tts_output_bitrate: str | None = None
    tts_timeline_policy: str = TimelinePolicy.SERIALIZE.value
    narrator_mix_base_gain_db: float = 7.0
    original_gain_db: float = 0.0
    tts_voice_profiles: dict[str, TtsVoiceProfileSettings] = field(
        default_factory=default_tts_voice_profiles,
    )
    elevenbytes_custom_voices: list[CustomVoiceSetting] = field(default_factory=list)
    output_variant: OutputVariant = "players"
    composition_quality_preset: CompositionQualityPreset = "balanced"
    audio_language_priority: tuple[str, ...] = _DEFAULT_AUDIO_LANGUAGES
    subtitle_language_priority: tuple[str, ...] = _DEFAULT_SUBTITLE_LANGUAGES

    def __post_init__(self) -> None:
        """Normalize engine-bound selections and materialize the active profile."""
        self._normalize_tts_selection()
        self._drop_incompatible_tts_options()
        self.ensure_active_tts_profile()

    @property
    def voice(self) -> str:
        """Expose the selected voice to the legacy panel until its TTS rewrite."""
        return self.tts_voice_id

    @voice.setter
    def voice(self, value: str) -> None:
        self.tts_voice_id = value

    @property
    def tempo(self) -> float:
        """Expose the active profile tempo to the legacy panel."""
        return self._active_tts_profile().postprocess_tempo

    @tempo.setter
    def tempo(self, value: float) -> None:
        key: str = self._active_tts_profile_key()
        current: TtsVoiceProfileSettings = self.tts_voice_profiles.get(key, TtsVoiceProfileSettings())
        self.tts_voice_profiles[key] = replace(current, postprocess_tempo=value)

    @property
    def volume(self) -> int:
        """Return the neutral legacy percentage without mapping it to dB."""
        return 100

    @volume.setter
    def volume(self, value: int) -> None:
        del value

    def _active_tts_profile(self) -> TtsVoiceProfileSettings:
        return self.tts_voice_profiles.get(self._active_tts_profile_key(), TtsVoiceProfileSettings())

    @property
    def active_tts_profile(self) -> TtsVoiceProfileSettings:
        """Return the selected voice profile using its resolved identity."""
        return self._active_tts_profile()

    @property
    def tts_voice_label(self) -> str:
        """Return the human voice label used by legacy progress rows."""
        voice_id: str = self.tts_voice_id
        if self.tts_engine == "elevenbytes":
            if voice_id.casefold() == DALLIN_ALIAS:
                return "Dallin"
            custom: CustomVoiceSetting | None = next(
                (item for item in self.elevenbytes_custom_voices if item.alias.casefold() == voice_id.casefold()),
                None,
            )
            return custom.label if custom is not None else voice_id
        if self.tts_engine == "edge":
            return {
                MAREK_VOICE_ID: "Marek",
                ZOFIA_VOICE_ID: "Zofia",
            }.get(voice_id, voice_id)
        if self.tts_engine == "sapi":
            return voice_id.title()
        return voice_id

    @property
    def resolved_tts_voice_id(self) -> str:
        """Resolve a built-in or custom alias to the engine-facing voice id."""
        voice_id: str = self.tts_voice_id
        if self.tts_engine == "elevenbytes":
            if voice_id.casefold() == DALLIN_ALIAS:
                return DALLIN_VOICE_ID
            custom: CustomVoiceSetting | None = next(
                (item for item in self.elevenbytes_custom_voices if item.alias.casefold() == voice_id.casefold()),
                None,
            )
            return custom.voice_id if custom is not None else voice_id
        if self.tts_engine == "sapi" and voice_id.casefold() in SAPI_PROFILES:
            return SAPI_PROFILES[voice_id.casefold()].resolved_voice_id
        return voice_id

    def _active_tts_profile_key(self) -> str:
        return tts_profile_key(self.tts_engine, self.resolved_tts_voice_id)

    def ensure_active_tts_profile(self) -> TtsVoiceProfileSettings:
        """Return a mutable persisted profile for the active engine and voice."""
        key: str = self._active_tts_profile_key()
        profile: TtsVoiceProfileSettings | None = self.tts_voice_profiles.get(key)
        if profile is None:
            profile = TtsVoiceProfileSettings(
                concurrency=1 if self.tts_engine == "sapi" else None,
            )
            self.tts_voice_profiles[key] = profile
        return profile

    def add_elevenbytes_voice(
        self,
        *,
        alias: str,
        label: str,
        voice_id: str,
    ) -> None:
        """Add one case-insensitively unique custom ElevenBytes voice."""
        resolved_alias, resolved_label, resolved_voice_id = _validate_custom_voice(
            alias,
            label,
            voice_id,
            existing=self.elevenbytes_custom_voices,
        )
        self.elevenbytes_custom_voices.append(
            CustomVoiceSetting(
                alias=resolved_alias,
                label=resolved_label,
                voice_id=resolved_voice_id,
            ),
        )

    def update_elevenbytes_voice(
        self,
        current_alias: str,
        *,
        alias: str,
        label: str,
        voice_id: str,
    ) -> None:
        """Replace one custom ElevenBytes voice while preserving old profiles."""
        current_index: int = _custom_voice_index(
            self.elevenbytes_custom_voices,
            current_alias,
        )
        remaining: list[CustomVoiceSetting] = [
            item for index, item in enumerate(self.elevenbytes_custom_voices) if index != current_index
        ]
        resolved_alias, resolved_label, resolved_voice_id = _validate_custom_voice(
            alias,
            label,
            voice_id,
            existing=remaining,
        )
        self.elevenbytes_custom_voices[current_index] = CustomVoiceSetting(
            alias=resolved_alias,
            label=resolved_label,
            voice_id=resolved_voice_id,
        )
        if self.tts_engine == "elevenbytes" and self.tts_voice_id.casefold() == current_alias.casefold():
            self.tts_voice_id = resolved_alias
            self.ensure_active_tts_profile()

    def remove_elevenbytes_voice(self, alias: str) -> None:
        """Remove one custom voice and select Dallin when it was active."""
        index: int = _custom_voice_index(self.elevenbytes_custom_voices, alias)
        removed: CustomVoiceSetting = self.elevenbytes_custom_voices.pop(index)
        if self.tts_engine == "elevenbytes" and self.tts_voice_id.casefold() == removed.alias.casefold():
            self.tts_voice_id = DALLIN_ALIAS
            self.ensure_active_tts_profile()

    def _normalize_tts_selection(self) -> None:
        allowed_engines: tuple[str, ...] = tuple(available_tts_engine_ids())
        if self.tts_engine not in allowed_engines:
            self.tts_engine = "elevenbytes"
        if self.tts_engine == "elevenbytes":
            if self.tts_provider_model_id not in ENDPOINTS:
                self.tts_provider_model_id = "run6"
            if _is_sapi_voice(self.tts_voice_id) or self.tts_voice_id in {MAREK_VOICE_ID, ZOFIA_VOICE_ID}:
                self.tts_voice_id = DALLIN_ALIAS
            return
        if self.tts_engine == "edge":
            self.tts_provider_model_id = EDGE_PROVIDER_MODEL_ID
            if self.tts_voice_id not in {MAREK_VOICE_ID, ZOFIA_VOICE_ID}:
                self.tts_voice_id = MAREK_VOICE_ID
            return
        if self.tts_engine == "sapi":
            self.tts_provider_model_id = _SAPI_PROVIDER_MODEL_ID
            if not _is_sapi_voice(self.tts_voice_id):
                self.tts_voice_id = "agnieszka"
            return
        if (
            not self.tts_provider_model_id.strip()
            or self.tts_provider_model_id in ENDPOINTS
            or self.tts_provider_model_id
            in {
                EDGE_PROVIDER_MODEL_ID,
                _SAPI_PROVIDER_MODEL_ID,
            }
        ):
            self.tts_provider_model_id = DEFAULT_MODEL_ID

    def _drop_incompatible_tts_options(self) -> None:
        profile: TtsVoiceProfileSettings | None = self.tts_voice_profiles.get(
            self._active_tts_profile_key(),
        )
        if profile is None:
            return
        if self.tts_engine in {"edge", "sapi"} or (
            self.tts_engine == "elevenbytes" and self.tts_provider_model_id == "run6"
        ):
            profile.engine_options = {}


def _clean_string(raw: dict[str, Any], key: str, allowed: frozenset[str]) -> None:
    """Drop ``key`` from ``raw`` when its value is not in ``allowed``."""
    if raw.get(key) not in allowed:
        raw.pop(key, None)


def _clean_bool(raw: dict[str, Any], key: str) -> None:
    """Drop ``key`` from ``raw`` when its value is not a real boolean."""
    if not isinstance(raw.get(key), bool):
        raw.pop(key, None)


def _clean_number(raw: dict[str, Any], key: str, low: float, high: float) -> None:
    """Drop ``key`` from ``raw`` when it is non-numeric or out of range."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raw.pop(key, None)
        return
    if not low <= value <= high:
        raw.pop(key, None)


def _clean_optional_number(raw: dict[str, Any], key: str, low: float, high: float) -> None:
    """Keep None or an in-range real number and drop every other value."""
    if raw.get(key) is None:
        return
    _clean_number(raw, key, low, high)


def _clean_language_tuple(raw: dict[str, Any], key: str) -> None:
    """Keep a list of plain language codes as a tuple, or drop the field."""
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raw.pop(key, None)
        return
    raw[key] = tuple(dict.fromkeys(item.strip().casefold() for item in value))


def _clean_free_string(raw: dict[str, Any], key: str) -> None:
    """Strip a non-empty string or drop the field."""
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raw.pop(key, None)
        return
    raw[key] = value.strip()


def _clean_enrollment_base_url(raw: dict[str, Any]) -> None:
    """Keep a valid https enrollment address, or drop the field to its default.

    An empty string is a legal "not configured" value, so it is kept as is; a
    malformed address is dropped instead of being carried into a request.
    """
    key: str = "palantir_enrollment_base_url"
    value = raw.get(key)
    if not isinstance(value, str):
        raw.pop(key, None)
        return
    candidate: str = value.strip()
    if _ENROLLMENT_URL_RE.fullmatch(candidate) is None:
        raw.pop(key, None)
        return
    raw[key] = candidate


def _clean_free_str_list(raw: dict[str, Any], key: str) -> None:
    """Strip a list of non-empty unique strings or drop the field."""
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raw.pop(key, None)
        return
    raw[key] = list(dict.fromkeys(item.strip() for item in value))


def _clean_prompt_selection(raw: dict[str, Any]) -> None:
    """Normalize a style selection against packaged prompt resources."""
    available_styles = available_style_names()
    selected: object = raw.get("llm_translation_style")
    if isinstance(selected, str) and selected.strip() in available_styles:
        raw["llm_translation_style"] = selected.strip()
        return
    fallback = DEFAULT_STYLE_NAME if DEFAULT_STYLE_NAME in available_styles else available_styles[0]
    raw["llm_translation_style"] = fallback


def _clean_finite_number(raw: dict[str, Any], key: str) -> None:
    value: object = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raw.pop(key, None)
        return
    raw[key] = float(value)


def _clean_tts_bitrate(raw: dict[str, Any]) -> None:
    bitrate: object = raw.get("tts_output_bitrate")
    output_profile: object = raw.get("tts_output_profile", AudioCodecProfile.EAC3.value)
    if bitrate is None:
        return
    if (
        not isinstance(bitrate, str)
        or output_profile not in _LOSSY_OUTPUT_PROFILES
        or _BITRATE_PATTERN.fullmatch(bitrate.strip()) is None
    ):
        raw.pop("tts_output_bitrate", None)
        return
    raw["tts_output_bitrate"] = bitrate.strip().lower()


def _load_voice_profiles(value: object) -> dict[str, TtsVoiceProfileSettings]:
    profiles: dict[str, TtsVoiceProfileSettings] = default_tts_voice_profiles()
    if not isinstance(value, dict):
        return profiles
    allowed_engines: frozenset[str] = frozenset(available_tts_engine_ids())
    for raw_key, raw_profile in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_profile, dict):
            continue
        engine_id, separator, voice_id = raw_key.partition(":")
        if not separator or engine_id not in allowed_engines or not voice_id.strip():
            continue
        key: str = tts_profile_key(engine_id, voice_id.strip())
        base: TtsVoiceProfileSettings = profiles.get(key, TtsVoiceProfileSettings())
        profiles[key] = _load_voice_profile(raw_profile, base)
    return profiles


def _load_voice_profile(
    raw: dict[Any, Any],
    base: TtsVoiceProfileSettings,
) -> TtsVoiceProfileSettings:
    tempo: float = _profile_float(
        raw.get("postprocess_tempo"),
        default=base.postprocess_tempo,
        minimum=TEMPO_RANGE[0],
        maximum=TEMPO_RANGE[1],
    )
    mix_offset: float = _profile_float(
        raw.get("voice_mix_offset_db"),
        default=base.voice_mix_offset_db,
    )
    concurrency: int | None = _profile_concurrency(raw.get("concurrency", _MISSING), base.concurrency)
    return TtsVoiceProfileSettings(
        postprocess_tempo=tempo,
        voice_mix_offset_db=mix_offset,
        concurrency=concurrency,
        native_rate=_profile_native(raw.get("native_rate", _MISSING), base.native_rate),
        native_volume=_profile_native(raw.get("native_volume", _MISSING), base.native_volume),
        native_pitch=_profile_native(raw.get("native_pitch", _MISSING), base.native_pitch),
        engine_options=_profile_engine_options(raw.get("engine_options"), base.engine_options),
    )


def _profile_float(
    value: object,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    resolved: float = float(value)
    if minimum is not None and resolved < minimum:
        return default
    if maximum is not None and resolved > maximum:
        return default
    return resolved


def _profile_concurrency(value: object, default: int | None) -> int | None:
    if value is _MISSING:
        return default
    if value is None:
        return None
    if type(value) is not int or not TTS_CONCURRENCY_RANGE[0] <= value <= TTS_CONCURRENCY_RANGE[1]:
        return default
    return value


def _profile_native(
    value: object,
    default: str | float | None,
) -> str | float | None:
    if value is _MISSING:
        return default
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return float(value)


def _profile_engine_options(
    value: object,
    default: dict[str, JsonScalar],
) -> dict[str, JsonScalar]:
    if not isinstance(value, dict):
        return dict(default)
    options: dict[str, JsonScalar] = {}
    for key, option in value.items():
        if not isinstance(key, str) or not key:
            return dict(default)
        if option is not None and type(option) not in {str, int, float, bool}:
            return dict(default)
        if type(option) is float and not math.isfinite(option):
            return dict(default)
        options[key] = option
    return options


def _load_custom_voices(value: object) -> list[CustomVoiceSetting]:
    if not isinstance(value, list):
        return []
    voices: list[CustomVoiceSetting] = []
    aliases: set[str] = {DALLIN_ALIAS}
    for item in value:
        if not isinstance(item, dict):
            continue
        alias: str | None = _nonempty_string(item.get("alias"))
        label: str | None = _nonempty_string(item.get("label"))
        voice_id: str | None = _nonempty_string(item.get("voice_id"))
        if alias is None or label is None or voice_id is None or alias.casefold() in aliases:
            continue
        aliases.add(alias.casefold())
        voices.append(CustomVoiceSetting(alias=alias, label=label, voice_id=voice_id))
    return voices


def _nonempty_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _validate_custom_voice(
    alias: str,
    label: str,
    voice_id: str,
    *,
    existing: list[CustomVoiceSetting],
) -> tuple[str, str, str]:
    resolved_alias: str = alias.strip()
    resolved_label: str = label.strip()
    resolved_voice_id: str = voice_id.strip()
    if not resolved_alias or not resolved_label or not resolved_voice_id:
        message: str = "Custom voice alias, label, and provider id cannot be empty"
        raise ValueError(message)
    aliases: set[str] = {DALLIN_ALIAS, *(item.alias.casefold() for item in existing)}
    if resolved_alias.casefold() in aliases:
        message = f"Custom voice alias is reserved or duplicated: {resolved_alias}"
        raise ValueError(message)
    return resolved_alias, resolved_label, resolved_voice_id


def _custom_voice_index(
    voices: list[CustomVoiceSetting],
    alias: str,
) -> int:
    index: int | None = next(
        (candidate for candidate, item in enumerate(voices) if item.alias.casefold() == alias.strip().casefold()),
        None,
    )
    if index is None:
        message: str = f"Unknown custom ElevenBytes voice: {alias}"
        raise ValueError(message)
    return index


def _is_sapi_voice(value: str) -> bool:
    candidate: str = value.casefold()
    return any(
        candidate
        in {
            alias,
            profile.voice_name.casefold(),
            profile.resolved_voice_id.casefold(),
        }
        for alias, profile in SAPI_PROFILES.items()
    )


def _migrate_schema(raw: dict[str, Any]) -> bool:
    version: object = raw.get("schema_version", 1)
    if type(version) is not int or version not in {1, 2, SETTINGS_SCHEMA_VERSION}:
        warnings.warn(
            "Unsupported settings schema; safe defaults were loaded",
            SettingsSchemaWarning,
            stacklevel=2,
        )
        return False
    if version == 1:
        legacy_voice: object = raw.get("voice")
        if "tts_voice_id" not in raw and isinstance(legacy_voice, str) and legacy_voice.strip():
            raw["tts_voice_id"] = legacy_voice.strip()
    raw["schema_version"] = SETTINGS_SCHEMA_VERSION
    raw.pop("tempo", None)
    raw.pop("volume", None)
    raw.pop("llm_prompt_id", None)
    raw.pop("llm_style_id", None)
    raw.pop("llm_module_ids", None)
    return True


def load_user_settings() -> UserSettings:  # noqa: PLR0915 - explicit tolerant field validation
    """Load panel preferences, falling back to defaults.

    Unknown keys are ignored; missing, unreadable, wrong-typed or out-of-range
    fields fall back to their defaults instead of raising.
    """
    path = config_path()
    if not path.is_file():
        logger.debug("User settings missing; defaults selected")
        return UserSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        logger.warning("User settings unreadable; defaults selected")
        return UserSettings()
    if not isinstance(raw, dict) or not _migrate_schema(raw):
        logger.warning("User settings schema invalid; defaults selected")
        return UserSettings()

    legacy_model = raw.get("llm_model")
    if "llm_provider_model_id" not in raw and isinstance(legacy_model, str):
        raw["llm_provider_model_id"] = legacy_model.strip()

    known = set(UserSettings.__dataclass_fields__)
    filtered: dict[str, Any] = {k: v for k, v in raw.items() if k in known}
    engine_ids = frozenset(available_engine_ids())
    llm_engine_ids = frozenset(available_llm_engine_ids())
    tts_engine_ids = frozenset(available_tts_engine_ids())
    _clean_string(filtered, "mode", _MODES)
    _clean_string(filtered, "processing_order_policy", _PROCESSING_ORDER_POLICIES)
    _clean_string(filtered, "output_variant", _OUTPUT_VARIANTS)
    _clean_string(filtered, "translation_engine", engine_ids)
    _clean_number(filtered, "subtitle_max_chars_per_line", *LINE_CHARS_RANGE)
    _clean_number(filtered, "subtitle_max_lines_per_event", *EVENT_LINES_RANGE)
    _clean_number(filtered, "translation_chunk_chars", *CHUNK_CHARS_RANGE)
    _clean_number(filtered, "translation_batch_size", *BATCH_SIZE_RANGE)
    _clean_number(filtered, "translation_concurrency", *CONCURRENCY_RANGE)
    _clean_number(filtered, "translation_max_retries", *MAX_RETRIES_RANGE)
    _clean_string(filtered, "llm_provider", llm_engine_ids)
    _clean_free_string(filtered, "llm_provider_model_id")
    _clean_optional_number(filtered, "llm_temperature", *LLM_TEMPERATURE_RANGE)
    _clean_optional_number(filtered, "llm_top_p", *LLM_TOP_P_RANGE)
    _clean_optional_number(filtered, "llm_max_output_tokens", *LLM_MAX_TOKENS_RANGE)
    _clean_free_string(filtered, "llm_translation_style")
    _clean_prompt_selection(filtered)
    _clean_number(filtered, "llm_max_concurrency", *LLM_MAX_CONCURRENCY_RANGE)
    _clean_free_string(filtered, "primary_model_alias")
    _clean_enrollment_base_url(filtered)
    filtered["schema_version"] = SETTINGS_SCHEMA_VERSION
    _clean_string(filtered, "tts_engine", tts_engine_ids)
    _clean_free_string(filtered, "tts_provider_model_id")
    _clean_free_string(filtered, "tts_voice_id")
    _clean_number(filtered, "tts_max_retries", *TTS_MAX_RETRIES_RANGE)
    _clean_bool(filtered, "elevenbytes_vpn_enabled")
    _clean_string(filtered, "tts_output_profile", _TTS_OUTPUT_PROFILES)
    _clean_tts_bitrate(filtered)
    _clean_string(filtered, "tts_timeline_policy", _TTS_TIMELINE_POLICIES)
    _clean_finite_number(filtered, "narrator_mix_base_gain_db")
    _clean_finite_number(filtered, "original_gain_db")
    filtered["tts_voice_profiles"] = _load_voice_profiles(filtered.get("tts_voice_profiles"))
    filtered["elevenbytes_custom_voices"] = _load_custom_voices(filtered.get("elevenbytes_custom_voices"))
    _clean_string(filtered, "composition_quality_preset", _COMPOSITION_PRESETS)
    _clean_language_tuple(filtered, "audio_language_priority")
    _clean_language_tuple(filtered, "subtitle_language_priority")
    settings = UserSettings(**filtered)
    logger.debug(
        "User settings loaded",
        translation_engine=settings.translation_engine,
        llm_provider=settings.llm_provider,
        tts_engine=settings.tts_engine,
        processing_order=settings.processing_order_policy,
    )
    return settings


def save_user_settings(settings: UserSettings) -> None:
    """Persist panel preferences atomically to ``config/settings.json``."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized: dict[str, Any] = asdict(settings)
    serialized["schema_version"] = SETTINGS_SCHEMA_VERSION
    payload = json.dumps(serialized, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    logger.info(
        "User settings saved",
        translation_engine=settings.translation_engine,
        llm_provider=settings.llm_provider,
        tts_engine=settings.tts_engine,
        processing_order=settings.processing_order_policy,
    )
