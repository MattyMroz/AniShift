"""UI-independent typed catalog of AniShift workflow and engine settings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

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
from anishift.config.user_settings import (
    BATCH_SIZE_RANGE,
    CONCURRENCY_RANGE,
    LLM_MAX_CONCURRENCY_RANGE,
    LLM_MAX_TOKENS_RANGE,
    LLM_TEMPERATURE_RANGE,
    LLM_TOP_P_RANGE,
    MAX_RETRIES_RANGE,
    PALANTIR_ENROLLMENT_URL_PATTERN,
    TEMPO_RANGE,
    TTS_CONCURRENCY_RANGE,
    TTS_MAX_RETRIES_RANGE,
    CustomVoiceSetting,
    TtsVoiceProfileSettings,
    UserSettings,
    default_tts_voice_profiles,
    tts_profile_key,
)
from anishift.services.audio.types import AudioCodecProfile
from anishift.services.llm.engines import available_engine_ids as available_llm_engine_ids
from anishift.services.translation.engines import available_engine_ids as available_translation_engine_ids
from anishift.services.translation.engines.llm.prompts import available_style_names
from anishift.services.tts.engines import available_engine_ids as available_tts_engine_ids
from anishift.services.tts.engines.edge.constants import (
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS, DALLIN_VOICE_ID, ENDPOINTS
from anishift.services.tts.engines.elevenbytes.vpn import VPN_MAX_CONCURRENCY
from anishift.services.tts.engines.elevenlabs.constants import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    OUTPUT_FORMATS,
    POLISH_TTS_MODEL_IDS,
)
from anishift.services.tts.engines.sapi.constants import SAPI_PROFILES, SAPI_RATE_MAX, SAPI_RATE_MIN
from anishift.services.tts.engines.sapi.types import SapiVoiceProfile

__all__ = [
    "USER_SETTING_DISPOSITIONS",
    "SettingCatalogContext",
    "SettingCondition",
    "SettingDisposition",
    "SettingObjectFieldSpec",
    "SettingScope",
    "SettingSpec",
    "SettingValue",
    "SettingValueType",
    "setting_catalog",
]

type SettingValue = str | int | float | bool | None | tuple[str, ...] | tuple[CustomVoiceSetting, ...] | frozenset[str]
"""Immutable values represented by the settings catalog."""


class SettingValueType(StrEnum):
    """Editor kinds needed to render and validate settings without UI imports."""

    STRING = "string"
    OPTIONAL_STRING = "optional_string"
    INTEGER = "integer"
    OPTIONAL_INTEGER = "optional_integer"
    FLOAT = "float"
    OPTIONAL_FLOAT = "optional_float"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"
    STRING_SET = "string_set"
    OBJECT_LIST = "object_list"


class SettingScope(StrEnum):
    """Lifetime and ownership of one editable setting."""

    GLOBAL = "global"
    ENGINE_PROFILE = "engine_profile"
    AUTO_PRESET = "auto_preset"
    MANUAL_RUN = "manual_run"
    SECRET = "secret"  # noqa: S105
    INTERNAL = "internal"


class SettingDisposition(StrEnum):
    """Explicit catalog decision for every persisted ``UserSettings`` field."""

    VISIBLE = "visible"
    CONDITIONAL = "conditional"
    INTERNAL = "internal"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class SettingCondition:
    """A field is active when another setting equals or contains a listed value."""

    setting_id: str
    allowed_values: tuple[SettingValue, ...]

    def __post_init__(self) -> None:
        if not self.setting_id.strip() or not self.allowed_values:
            msg = "Setting condition requires an ID and at least one value"
            raise ValueError(msg)
        if len(self.allowed_values) != len(set(self.allowed_values)):
            msg = "Setting condition values must be unique"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SettingObjectFieldSpec:
    """Typed field belonging to one object-list item editor."""

    field_id: str
    label: str
    description: str
    value_type: SettingValueType

    def __post_init__(self) -> None:
        if not self.field_id.strip() or not self.label.strip() or not self.description.strip():
            msg = "Object fields require a stable ID, label, and description"
            raise ValueError(msg)
        if self.value_type not in {SettingValueType.STRING, SettingValueType.OPTIONAL_STRING}:
            msg = "Object-list fields currently support only textual values"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """Complete UI-neutral contract for one editable setting."""

    setting_id: str
    label: str
    description: str
    value_type: SettingValueType
    default: SettingValue
    scope: SettingScope
    allowed_values: tuple[SettingValue, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    validation_pattern: str | None = None
    depends_on: tuple[SettingCondition, ...] = ()
    invalidates: frozenset[ArtifactKind] = frozenset()
    object_fields: tuple[SettingObjectFieldSpec, ...] = ()
    is_secret: bool = False

    def __post_init__(self) -> None:
        if not self.setting_id.strip() or not self.label.strip() or not self.description.strip():
            msg = "Setting specs require a stable ID, label, and description"
            raise ValueError(msg)
        if len(self.allowed_values) != len(set(self.allowed_values)):
            msg = f"Allowed values for {self.setting_id!r} must be unique"
            raise ValueError(msg)
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            msg = f"Invalid numeric range for {self.setting_id!r}"
            raise ValueError(msg)
        if self.is_secret is not (self.scope is SettingScope.SECRET):
            msg = "Secret settings must use the secret scope and only that scope"
            raise ValueError(msg)
        if any(condition.setting_id == self.setting_id for condition in self.depends_on):
            msg = f"Setting {self.setting_id!r} cannot depend on itself"
            raise ValueError(msg)
        if self.value_type is SettingValueType.OBJECT_LIST:
            object_field_ids: tuple[str, ...] = tuple(field.field_id for field in self.object_fields)
            if not object_field_ids or len(object_field_ids) != len(set(object_field_ids)):
                msg = "Object-list settings require unique typed object fields"
                raise ValueError(msg)
        elif self.object_fields:
            msg = "Only object-list settings can declare object fields"
            raise ValueError(msg)
        if self.validation_pattern is not None:
            if self.value_type not in {SettingValueType.STRING, SettingValueType.OPTIONAL_STRING}:
                msg = "Validation patterns require a textual setting type"
                raise ValueError(msg)
            re.compile(self.validation_pattern)
        self.validate_value(self.default)

    def validate_value(self, value: SettingValue) -> None:
        """Reject a value that violates this field's type and local constraints."""
        if not _value_matches_type(value, self.value_type):
            msg = f"Value for {self.setting_id!r} does not match its declared type"
            raise TypeError(msg)
        _validate_value_range(self, value)
        _validate_allowed_value(self, value)
        if (
            self.validation_pattern is not None
            and isinstance(value, str)
            and re.fullmatch(self.validation_pattern, value) is None
        ):
            msg = f"Value for {self.setting_id!r} does not match its required format"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SettingCatalogContext:
    """Selections that determine which provider-specific fields are available."""

    run_mode: RunMode = RunMode.AUTO
    llm_provider: str = "gemini"
    tts_engine: str = "elevenbytes"
    tts_provider_model_id: str = "run6"
    tts_voice_id: str = DALLIN_ALIAS
    elevenbytes_vpn_enabled: bool = True
    elevenbytes_custom_voice_aliases: tuple[str, ...] = ()

    @classmethod
    def from_user_settings(
        cls,
        settings: UserSettings,
        *,
        run_mode: RunMode = RunMode.AUTO,
    ) -> SettingCatalogContext:
        """Create a catalog context without retaining mutable user settings."""
        aliases: tuple[str, ...] = tuple(voice.alias for voice in settings.elevenbytes_custom_voices)
        return cls(
            run_mode=run_mode,
            llm_provider=settings.llm_provider,
            tts_engine=settings.tts_engine,
            tts_provider_model_id=settings.tts_provider_model_id,
            tts_voice_id=settings.tts_voice_id,
            elevenbytes_vpn_enabled=settings.elevenbytes_vpn_enabled,
            elevenbytes_custom_voice_aliases=aliases,
        )


# ── Constants ────────────────────────────────────────────────────────────────

_TRANSLATION_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset(
    {
        ArtifactKind.FULL_PL,
        ArtifactKind.SPOKEN_PL,
        ArtifactKind.DISPLAYED_PL,
        ArtifactKind.NARRATION_AUDIO,
        ArtifactKind.FINAL_MKV,
        ArtifactKind.FINAL_MP4,
    }
)
"""Artifacts invalidated by translation configuration or source policy."""

_TTS_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset(
    {
        ArtifactKind.TTS_CLIP,
        ArtifactKind.TTS_MANIFEST,
        ArtifactKind.NARRATION_AUDIO,
        ArtifactKind.FINAL_MKV,
        ArtifactKind.FINAL_MP4,
    }
)
"""Artifacts invalidated by synthesis engine or active voice profile changes."""

_AUDIO_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.NARRATION_AUDIO, ArtifactKind.FINAL_MKV, ArtifactKind.FINAL_MP4}
)
"""Artifacts invalidated by narration encoding or mix settings."""

_AUDIO_SOURCE_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset({ArtifactKind.SOURCE_AUDIO, *_AUDIO_INVALIDATES})
"""Source audio and derived products invalidated by choosing another audio input."""

_COMPOSITION_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset({ArtifactKind.FINAL_MKV, ArtifactKind.FINAL_MP4})
"""Container products invalidated by product or composition settings."""

_SOURCE_INVALIDATES: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.SOURCE_SUBTITLES, *_TRANSLATION_INVALIDATES}
)
"""All subtitle-derived products invalidated by selecting another source."""

_LOSSY_AUDIO_PROFILES: Final[tuple[str, ...]] = ("aac", "eac3", "mp3", "opus")
"""Final narration profiles that accept an explicit bitrate."""

_COMPOSITION_PRESETS: Final[tuple[str, ...]] = ("high", "balanced", "compact")
"""Stable user-facing hardsub quality presets."""

_PROCESSING_ORDER_POLICIES: Final[tuple[str, ...]] = ("ready_first", "strict_natural")
"""Stable cross-file scheduling policies."""

_EDGE_PERCENT_PATTERN: Final[str] = r"[+-](?:100|[0-9]{1,2})%"
"""Accepted Edge rate and volume adjustments from minus to plus one hundred percent."""

_EDGE_PITCH_PATTERN: Final[str] = r"[+-](?:100|[0-9]{1,2})Hz"
"""Accepted Edge pitch adjustment from minus to plus one hundred hertz."""

USER_SETTING_DISPOSITIONS: Final[MappingProxyType[str, SettingDisposition]] = MappingProxyType(
    {
        "schema_version": SettingDisposition.INTERNAL,
        "mode": SettingDisposition.REMOVED,
        "processing_order_policy": SettingDisposition.VISIBLE,
        "translation_engine": SettingDisposition.VISIBLE,
        "translation_fallback_chain": SettingDisposition.VISIBLE,
        "translation_batch_size": SettingDisposition.VISIBLE,
        "translation_concurrency": SettingDisposition.VISIBLE,
        "translation_max_retries": SettingDisposition.VISIBLE,
        "llm_provider": SettingDisposition.VISIBLE,
        "llm_provider_model_id": SettingDisposition.VISIBLE,
        "llm_temperature": SettingDisposition.VISIBLE,
        "llm_top_p": SettingDisposition.VISIBLE,
        "llm_max_output_tokens": SettingDisposition.VISIBLE,
        "llm_translation_style": SettingDisposition.VISIBLE,
        "llm_max_concurrency": SettingDisposition.VISIBLE,
        "primary_model_alias": SettingDisposition.VISIBLE,
        "palantir_enrollment_base_url": SettingDisposition.VISIBLE,
        "tts_engine": SettingDisposition.VISIBLE,
        "tts_provider_model_id": SettingDisposition.CONDITIONAL,
        "tts_voice_id": SettingDisposition.CONDITIONAL,
        "tts_max_retries": SettingDisposition.VISIBLE,
        "elevenbytes_vpn_enabled": SettingDisposition.CONDITIONAL,
        "tts_output_profile": SettingDisposition.VISIBLE,
        "tts_output_bitrate": SettingDisposition.CONDITIONAL,
        "tts_timeline_policy": SettingDisposition.INTERNAL,
        "narrator_mix_base_gain_db": SettingDisposition.VISIBLE,
        "original_gain_db": SettingDisposition.VISIBLE,
        "tts_voice_profiles": SettingDisposition.CONDITIONAL,
        "elevenbytes_custom_voices": SettingDisposition.CONDITIONAL,
        "output_variant": SettingDisposition.REMOVED,
        "composition_quality_preset": SettingDisposition.VISIBLE,
        "audio_language_priority": SettingDisposition.VISIBLE,
        "subtitle_language_priority": SettingDisposition.VISIBLE,
    }
)
"""Explicit visible, conditional, internal, or removed decision for each persisted field."""


def setting_catalog(context: SettingCatalogContext | None = None) -> tuple[SettingSpec, ...]:
    """Build the complete stable catalog without network access or synthesis."""
    resolved_context: SettingCatalogContext = context or SettingCatalogContext()
    defaults = UserSettings()
    catalog: tuple[SettingSpec, ...] = (
        *_workflow_specs(resolved_context),
        *_global_specs(defaults),
        *_translation_specs(defaults, resolved_context),
        *_model_specs(defaults),
        *_tts_specs(defaults, resolved_context),
        *_profile_specs(resolved_context),
        *_audio_and_composition_specs(defaults),
        *_environment_specs(),
    )
    setting_ids: tuple[str, ...] = tuple(spec.setting_id for spec in catalog)
    if len(setting_ids) != len(set(setting_ids)):
        msg = "Settings catalog contains duplicate IDs"
        raise ValueError(msg)
    known_ids: frozenset[str] = frozenset(setting_ids)
    missing_dependencies: set[str] = {
        condition.setting_id
        for spec in catalog
        for condition in spec.depends_on
        if condition.setting_id not in known_ids
    }
    if missing_dependencies:
        rendered: str = ", ".join(sorted(missing_dependencies))
        msg = f"Settings catalog references unknown dependencies: {rendered}"
        raise ValueError(msg)
    return catalog


def _value_matches_type(value: SettingValue, value_type: SettingValueType) -> bool:
    if value_type is SettingValueType.STRING:
        matches: bool = isinstance(value, str)
    elif value_type is SettingValueType.OPTIONAL_STRING:
        matches = value is None or isinstance(value, str)
    elif value_type is SettingValueType.INTEGER:
        matches = type(value) is int
    elif value_type is SettingValueType.OPTIONAL_INTEGER:
        matches = value is None or type(value) is int
    elif value_type is SettingValueType.FLOAT:
        matches = not isinstance(value, bool) and isinstance(value, (int, float))
    elif value_type is SettingValueType.OPTIONAL_FLOAT:
        matches = value is None or (not isinstance(value, bool) and isinstance(value, (int, float)))
    elif value_type is SettingValueType.BOOLEAN:
        matches = isinstance(value, bool)
    elif value_type is SettingValueType.STRING_LIST:
        matches = isinstance(value, tuple) and all(isinstance(item, str) for item in value)
    elif value_type is SettingValueType.OBJECT_LIST:
        matches = isinstance(value, tuple) and all(isinstance(item, CustomVoiceSetting) for item in value)
    else:
        matches = isinstance(value, frozenset) and all(isinstance(item, str) for item in value)
    return matches


def _validate_value_range(spec: SettingSpec, value: SettingValue) -> None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    if spec.minimum is not None and value < spec.minimum:
        msg = f"Value for {spec.setting_id!r} is below its minimum"
        raise ValueError(msg)
    if spec.maximum is not None and value > spec.maximum:
        msg = f"Value for {spec.setting_id!r} is above its maximum"
        raise ValueError(msg)


def _validate_allowed_value(spec: SettingSpec, value: SettingValue) -> None:
    if not spec.allowed_values or value is None:
        return
    collection_allowed: bool = (
        spec.value_type is SettingValueType.STRING_LIST
        and isinstance(value, tuple)
        and all(item in spec.allowed_values for item in value)
    ) or (
        spec.value_type is SettingValueType.STRING_SET
        and isinstance(value, frozenset)
        and all(item in spec.allowed_values for item in value)
    )
    if collection_allowed or value in spec.allowed_values:
        return
    msg = f"Value for {spec.setting_id!r} is not allowed"
    raise ValueError(msg)


def _workflow_specs(context: SettingCatalogContext) -> tuple[SettingSpec, ...]:
    shared_scope: SettingScope = (
        SettingScope.AUTO_PRESET if context.run_mode is RunMode.AUTO else SettingScope.MANUAL_RUN
    )
    subtitle_source_values: tuple[SettingValue, ...] = tuple(
        policy.value
        for policy in SubtitleSourcePolicy
        if context.run_mode is RunMode.MANUAL
        or policy not in {SubtitleSourcePolicy.EXTERNAL, SubtitleSourcePolicy.READY_POLISH}
    )
    return (
        SettingSpec(
            setting_id="subtitle_source_policy",
            label="Subtitle source",
            description="Choose automatic, sidecar, embedded, external, ready Polish, or no subtitles.",
            value_type=SettingValueType.STRING,
            default=SubtitleSourcePolicy.AUTO.value,
            scope=shared_scope,
            allowed_values=subtitle_source_values,
            invalidates=_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="preferred_video_artifact_id",
            label="Preferred video",
            description="Select the MKV or MP4 source when one group contains both.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            invalidates=_COMPOSITION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="selected_subtitle_artifact_id",
            label="External subtitle",
            description="Select one registered ASS or SRT artifact for this group.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            invalidates=_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="selected_subtitle_track_id",
            label="Embedded subtitle track",
            description="Select one embedded subtitle track instead of automatic discovery.",
            value_type=SettingValueType.OPTIONAL_INTEGER,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            minimum=0,
            invalidates=_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="selected_audio_artifact_id",
            label="External audio",
            description="Select one registered external audio artifact for this group.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            invalidates=_AUDIO_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="selected_audio_track_id",
            label="Embedded audio track",
            description="Select one embedded audio track instead of automatic discovery.",
            value_type=SettingValueType.OPTIONAL_INTEGER,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            minimum=0,
            invalidates=_AUDIO_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="source_subtitle_language",
            label="Source subtitle language",
            description="Override missing or incorrect subtitle language metadata with an ISO code.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=None,
            scope=shared_scope,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="external_audio_role",
            label="External audio role",
            description="Treat selected external audio as source audio or a ready narration mix.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=None,
            scope=SettingScope.MANUAL_RUN,
            allowed_values=tuple(role.value for role in ExternalAudioRole),
            invalidates=_AUDIO_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="subtitle_output_format",
            label="Subtitle output format",
            description="Preserve the source format or normalize durable subtitles to ASS or SRT.",
            value_type=SettingValueType.STRING,
            default=SubtitleOutputFormat.PRESERVE.value,
            scope=shared_scope,
            allowed_values=tuple(output_format.value for output_format in SubtitleOutputFormat),
            invalidates=_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="translation_action",
            label="Translation action",
            description="Choose automatic language handling, force translation, or keep source text.",
            value_type=SettingValueType.STRING,
            default=TranslationAction.AUTO.value,
            scope=shared_scope,
            allowed_values=tuple(action.value for action in TranslationAction),
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="requested_products",
            label="Products",
            description="Select independent subtitle, narration, MKV, and MP4 products.",
            value_type=SettingValueType.STRING_SET,
            default=frozenset({ProductKind.FULL_PL.value, ProductKind.NARRATION_AUDIO.value}),
            scope=shared_scope,
            allowed_values=tuple(product.value for product in ProductKind),
            invalidates=_COMPOSITION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="burn_subtitle_product",
            label="Burned subtitle product",
            description="Choose which subtitle document is burned into an MP4 product.",
            value_type=SettingValueType.STRING,
            default=BurnSubtitleProduct.NONE.value,
            scope=shared_scope,
            allowed_values=tuple(product.value for product in BurnSubtitleProduct),
            depends_on=(SettingCondition("requested_products", (ProductKind.MP4.value,)),),
            invalidates=_COMPOSITION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="mkv_tracks",
            label="MKV tracks",
            description="Select subtitle and narration tracks attached to the MKV product.",
            value_type=SettingValueType.STRING_SET,
            default=frozenset(),
            scope=shared_scope,
            allowed_values=tuple(track.value for track in MkvTrackProduct),
            depends_on=(SettingCondition("requested_products", (ProductKind.MKV.value,)),),
            invalidates=_COMPOSITION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="mp4_audio_source",
            label="MP4 audio",
            description="Use automatic, original, or narration audio for the MP4 product.",
            value_type=SettingValueType.STRING,
            default=Mp4AudioSource.AUTO.value,
            scope=shared_scope,
            allowed_values=tuple(source.value for source in Mp4AudioSource),
            depends_on=(SettingCondition("requested_products", (ProductKind.MP4.value,)),),
            invalidates=_COMPOSITION_INVALIDATES,
        ),
    )


def _global_specs(defaults: UserSettings) -> tuple[SettingSpec, ...]:
    return (
        SettingSpec(
            setting_id="processing_order_policy",
            label="Processing order",
            description="Prefer ready work for throughput or preserve strict natural file order.",
            value_type=SettingValueType.STRING,
            default=defaults.processing_order_policy,
            scope=SettingScope.GLOBAL,
            allowed_values=_PROCESSING_ORDER_POLICIES,
        ),
        SettingSpec(
            setting_id="audio_language_priority",
            label="Audio language priority",
            description="Order language codes used by automatic audio-track selection.",
            value_type=SettingValueType.STRING_LIST,
            default=defaults.audio_language_priority,
            scope=SettingScope.GLOBAL,
            invalidates=_AUDIO_SOURCE_INVALIDATES,
        ),
        SettingSpec(
            setting_id="subtitle_language_priority",
            label="Subtitle language priority",
            description="Order language codes used by automatic subtitle-track selection.",
            value_type=SettingValueType.STRING_LIST,
            default=defaults.subtitle_language_priority,
            scope=SettingScope.GLOBAL,
            invalidates=_SOURCE_INVALIDATES,
        ),
    )


def _translation_specs(
    defaults: UserSettings,
    context: SettingCatalogContext,
) -> tuple[SettingSpec, ...]:
    llm_condition = (SettingCondition("translation_engine", ("llm",)),)
    return (
        SettingSpec(
            setting_id="translation_engine",
            label="Translation engine",
            description="Select the registered engine used for subtitle translation.",
            value_type=SettingValueType.STRING,
            default=defaults.translation_engine,
            scope=SettingScope.GLOBAL,
            allowed_values=tuple(available_translation_engine_ids()),
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="translation_fallback_chain",
            label="Translation fallbacks",
            description="Order unique fallback engines used after retryable translation failures.",
            value_type=SettingValueType.STRING_LIST,
            default=tuple(defaults.translation_fallback_chain),
            scope=SettingScope.GLOBAL,
            allowed_values=tuple(available_translation_engine_ids()),
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="translation_batch_size",
            label="Translation batch size",
            description="Set lines per request; zero uses the selected engine default.",
            value_type=SettingValueType.INTEGER,
            default=defaults.translation_batch_size,
            scope=SettingScope.GLOBAL,
            minimum=BATCH_SIZE_RANGE[0],
            maximum=BATCH_SIZE_RANGE[1],
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="translation_concurrency",
            label="Translation concurrency",
            description="Limit concurrent translation batches for one file.",
            value_type=SettingValueType.INTEGER,
            default=defaults.translation_concurrency,
            scope=SettingScope.GLOBAL,
            minimum=CONCURRENCY_RANGE[0],
            maximum=CONCURRENCY_RANGE[1],
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="translation_max_retries",
            label="Translation retries",
            description="Retry transient translation failures up to this count.",
            value_type=SettingValueType.INTEGER,
            default=defaults.translation_max_retries,
            scope=SettingScope.GLOBAL,
            minimum=MAX_RETRIES_RANGE[0],
            maximum=MAX_RETRIES_RANGE[1],
        ),
        SettingSpec(
            setting_id="llm_provider",
            label="LLM provider",
            description="Select the registered LLM provider used by the LLM translation engine.",
            value_type=SettingValueType.STRING,
            default=defaults.llm_provider,
            scope=SettingScope.GLOBAL,
            allowed_values=tuple(available_llm_engine_ids()),
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_provider_model_id",
            label="LLM model",
            description=f"Enter a provider model ID for {context.llm_provider}.",
            value_type=SettingValueType.STRING,
            default=defaults.llm_provider_model_id,
            scope=SettingScope.GLOBAL,
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_temperature",
            label="LLM temperature",
            description="Optionally override provider sampling temperature.",
            value_type=SettingValueType.OPTIONAL_FLOAT,
            default=defaults.llm_temperature,
            scope=SettingScope.GLOBAL,
            minimum=LLM_TEMPERATURE_RANGE[0],
            maximum=LLM_TEMPERATURE_RANGE[1],
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_top_p",
            label="LLM top-p",
            description="Optionally override provider nucleus sampling.",
            value_type=SettingValueType.OPTIONAL_FLOAT,
            default=defaults.llm_top_p,
            scope=SettingScope.GLOBAL,
            minimum=LLM_TOP_P_RANGE[0],
            maximum=LLM_TOP_P_RANGE[1],
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_max_output_tokens",
            label="LLM output tokens",
            description="Optionally cap provider output tokens for one request.",
            value_type=SettingValueType.OPTIONAL_INTEGER,
            default=defaults.llm_max_output_tokens,
            scope=SettingScope.GLOBAL,
            minimum=LLM_MAX_TOKENS_RANGE[0],
            maximum=LLM_MAX_TOKENS_RANGE[1],
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_translation_style",
            label="Translation style",
            description="Select the style prompt used for subtitle translation.",
            value_type=SettingValueType.STRING,
            default=defaults.llm_translation_style,
            scope=SettingScope.GLOBAL,
            allowed_values=available_style_names(),
            depends_on=llm_condition,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
        SettingSpec(
            setting_id="llm_max_concurrency",
            label="LLM file concurrency",
            description="Limit files translated concurrently through the LLM provider.",
            value_type=SettingValueType.INTEGER,
            default=defaults.llm_max_concurrency,
            scope=SettingScope.GLOBAL,
            minimum=LLM_MAX_CONCURRENCY_RANGE[0],
            maximum=LLM_MAX_CONCURRENCY_RANGE[1],
            depends_on=llm_condition,
        ),
    )


def _model_specs(defaults: UserSettings) -> tuple[SettingSpec, ...]:
    """Build the main model role and the Palantir connection address.

    Neither spec depends on the translation provider. The main model role and the
    translation model are separate choices, and the enrollment address must stay
    editable whichever provider translation currently uses.
    """
    return (
        SettingSpec(
            setting_id="primary_model_alias",
            label="Main model",
            description="Select the catalog alias of the main model, independent of the translation model.",
            value_type=SettingValueType.STRING,
            default=defaults.primary_model_alias,
            scope=SettingScope.GLOBAL,
        ),
        SettingSpec(
            setting_id="palantir_enrollment_base_url",
            label="Palantir enrollment address",
            description="Configure the https address of the enrollment serving the Foundry proxy routes.",
            value_type=SettingValueType.STRING,
            default=defaults.palantir_enrollment_base_url,
            scope=SettingScope.GLOBAL,
            validation_pattern=PALANTIR_ENROLLMENT_URL_PATTERN,
            invalidates=_TRANSLATION_INVALIDATES,
        ),
    )


def _tts_specs(defaults: UserSettings, context: SettingCatalogContext) -> tuple[SettingSpec, ...]:
    model_values, model_default = _tts_model_values(context)
    voice_values, voice_default = _tts_voice_values(context)
    elevenbytes_condition = (SettingCondition("tts_engine", ("elevenbytes",)),)
    return (
        SettingSpec(
            setting_id="tts_engine",
            label="TTS engine",
            description="Select the registered speech engine used for Polish narration.",
            value_type=SettingValueType.STRING,
            default=defaults.tts_engine,
            scope=SettingScope.GLOBAL,
            allowed_values=tuple(available_tts_engine_ids()),
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_provider_model_id",
            label="TTS model",
            description="Select the endpoint or provider model for the active speech engine.",
            value_type=SettingValueType.STRING,
            default=model_default,
            scope=SettingScope.ENGINE_PROFILE,
            allowed_values=model_values,
            depends_on=(SettingCondition("tts_engine", (context.tts_engine,)),),
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_voice_id",
            label="TTS voice",
            description="Select a built-in alias or enter a provider voice ID when supported.",
            value_type=SettingValueType.STRING,
            default=voice_default,
            scope=SettingScope.ENGINE_PROFILE,
            allowed_values=voice_values,
            depends_on=(SettingCondition("tts_engine", (context.tts_engine,)),),
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_max_retries",
            label="TTS retries",
            description="Retry transient speech-provider failures up to this count.",
            value_type=SettingValueType.INTEGER,
            default=defaults.tts_max_retries,
            scope=SettingScope.GLOBAL,
            minimum=TTS_MAX_RETRIES_RANGE[0],
            maximum=TTS_MAX_RETRIES_RANGE[1],
        ),
        SettingSpec(
            setting_id="elevenbytes_vpn_enabled",
            label="ElevenBytes VPN routing",
            description="Require the ElevenBytes proxy request to use the configured VPN route.",
            value_type=SettingValueType.BOOLEAN,
            default=defaults.elevenbytes_vpn_enabled,
            scope=SettingScope.GLOBAL,
            depends_on=elevenbytes_condition,
        ),
        SettingSpec(
            setting_id="elevenbytes_custom_voices",
            label="ElevenBytes custom voices",
            description="Manage aliases, labels, and provider IDs for custom ElevenBytes voices.",
            value_type=SettingValueType.OBJECT_LIST,
            default=tuple(defaults.elevenbytes_custom_voices),
            scope=SettingScope.GLOBAL,
            depends_on=elevenbytes_condition,
            invalidates=_TTS_INVALIDATES,
            object_fields=(
                SettingObjectFieldSpec(
                    field_id="alias",
                    label="Alias",
                    description="Stable unique name used to select this voice.",
                    value_type=SettingValueType.STRING,
                ),
                SettingObjectFieldSpec(
                    field_id="label",
                    label="Label",
                    description="Human-readable voice name shown in the interface.",
                    value_type=SettingValueType.STRING,
                ),
                SettingObjectFieldSpec(
                    field_id="voice_id",
                    label="Provider voice ID",
                    description="Exact ElevenBytes provider identifier resolved by this alias.",
                    value_type=SettingValueType.STRING,
                ),
            ),
        ),
    )


def _profile_specs(context: SettingCatalogContext) -> tuple[SettingSpec, ...]:
    profile: TtsVoiceProfileSettings = _profile_defaults(context)
    engine_condition = (SettingCondition("tts_engine", (context.tts_engine,)),)
    common: tuple[SettingSpec, ...] = (
        SettingSpec(
            setting_id="tts_profile.postprocess_tempo",
            label="Post-process tempo",
            description="Adjust rendered speech tempo for the active engine and voice.",
            value_type=SettingValueType.FLOAT,
            default=profile.postprocess_tempo,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=TEMPO_RANGE[0],
            maximum=TEMPO_RANGE[1],
            depends_on=engine_condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.voice_mix_offset_db",
            label="Voice mix offset",
            description="Adjust this voice relative to the global narrator mix gain.",
            value_type=SettingValueType.FLOAT,
            default=profile.voice_mix_offset_db,
            scope=SettingScope.ENGINE_PROFILE,
            depends_on=engine_condition,
            invalidates=_AUDIO_INVALIDATES,
        ),
    )
    concurrency: tuple[SettingSpec, ...] = ()
    if context.tts_engine != "sapi":
        concurrency = (
            SettingSpec(
                setting_id="tts_profile.concurrency",
                label="TTS concurrency",
                description="Limit simultaneous requests for the active engine and voice.",
                value_type=SettingValueType.INTEGER,
                default=profile.concurrency or 1,
                scope=SettingScope.ENGINE_PROFILE,
                minimum=TTS_CONCURRENCY_RANGE[0],
                maximum=_tts_concurrency_max(context),
                depends_on=engine_condition,
                invalidates=_TTS_INVALIDATES,
            ),
        )
    return (*common, *concurrency, *_engine_profile_specs(context, profile))


def _engine_profile_specs(
    context: SettingCatalogContext,
    profile: TtsVoiceProfileSettings,
) -> tuple[SettingSpec, ...]:
    if context.tts_engine == "edge":
        return _edge_profile_specs(profile)
    if context.tts_engine == "elevenbytes" and context.tts_provider_model_id == "run7":
        return _elevenbytes_run7_specs()
    if context.tts_engine == "elevenlabs":
        return _elevenlabs_profile_specs()
    if context.tts_engine == "sapi":
        return _sapi_profile_specs(context)
    return ()


def _edge_profile_specs(profile: TtsVoiceProfileSettings) -> tuple[SettingSpec, ...]:
    condition = (SettingCondition("tts_engine", ("edge",)),)
    return (
        SettingSpec(
            setting_id="tts_profile.native_rate",
            label="Edge native rate",
            description="Set the provider-native speech rate from -100% through +100%.",
            value_type=SettingValueType.STRING,
            default=profile.native_rate or DEFAULT_RATE,
            scope=SettingScope.ENGINE_PROFILE,
            validation_pattern=_EDGE_PERCENT_PATTERN,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.native_volume",
            label="Edge native volume",
            description="Set the provider-native speech volume from -100% through +100%.",
            value_type=SettingValueType.STRING,
            default=profile.native_volume or DEFAULT_VOLUME,
            scope=SettingScope.ENGINE_PROFILE,
            validation_pattern=_EDGE_PERCENT_PATTERN,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.native_pitch",
            label="Edge native pitch",
            description="Set the provider-native pitch from -100Hz through +100Hz.",
            value_type=SettingValueType.STRING,
            default=profile.native_pitch or DEFAULT_PITCH,
            scope=SettingScope.ENGINE_PROFILE,
            validation_pattern=_EDGE_PITCH_PATTERN,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
    )


def _elevenbytes_run7_specs() -> tuple[SettingSpec, ...]:
    condition = (
        SettingCondition("tts_engine", ("elevenbytes",)),
        SettingCondition("tts_provider_model_id", ("run7",)),
    )
    return _voice_option_specs(condition, include_speed=False, include_output=False)


def _elevenlabs_profile_specs() -> tuple[SettingSpec, ...]:
    condition = (SettingCondition("tts_engine", ("elevenlabs",)),)
    return _voice_option_specs(condition, include_speed=True, include_output=True)


def _voice_option_specs(
    condition: tuple[SettingCondition, ...],
    *,
    include_speed: bool,
    include_output: bool,
) -> tuple[SettingSpec, ...]:
    specs: tuple[SettingSpec, ...] = (
        SettingSpec(
            setting_id="tts_profile.engine_options.stability",
            label="Voice stability",
            description="Set provider voice stability for the active profile.",
            value_type=SettingValueType.FLOAT,
            default=0.5,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=0.0,
            maximum=1.0,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.engine_options.similarity_boost",
            label="Similarity boost",
            description="Set provider voice similarity for the active profile.",
            value_type=SettingValueType.FLOAT,
            default=0.75,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=0.0,
            maximum=1.0,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.engine_options.style",
            label="Voice style",
            description="Set provider style exaggeration for the active profile.",
            value_type=SettingValueType.FLOAT,
            default=0.0,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=0.0,
            maximum=1.0,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.engine_options.use_speaker_boost",
            label="Speaker boost",
            description="Enable provider speaker boost for the active profile.",
            value_type=SettingValueType.BOOLEAN,
            default=True,
            scope=SettingScope.ENGINE_PROFILE,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
    )
    speed: tuple[SettingSpec, ...] = ()
    if include_speed:
        speed = (
            SettingSpec(
                setting_id="tts_profile.engine_options.speed",
                label="Native speed",
                description="Set official ElevenLabs native speed before post-processing.",
                value_type=SettingValueType.FLOAT,
                default=1.0,
                scope=SettingScope.ENGINE_PROFILE,
                minimum=0.7,
                maximum=1.2,
                depends_on=condition,
                invalidates=_TTS_INVALIDATES,
            ),
        )
    output: tuple[SettingSpec, ...] = ()
    if include_output:
        output = (
            SettingSpec(
                setting_id="tts_profile.engine_options.output_format",
                label="Native output format",
                description="Select an official ElevenLabs output token.",
                value_type=SettingValueType.STRING,
                default=DEFAULT_OUTPUT_FORMAT,
                scope=SettingScope.ENGINE_PROFILE,
                allowed_values=tuple(OUTPUT_FORMATS),
                depends_on=condition,
                invalidates=_TTS_INVALIDATES,
            ),
        )
    return (*specs, *speed, *output)


def _sapi_profile_specs(context: SettingCatalogContext) -> tuple[SettingSpec, ...]:
    profile = _sapi_profile(context.tts_voice_id)
    condition = (
        SettingCondition("tts_engine", ("sapi",)),
        SettingCondition("tts_voice_id", (profile.alias, profile.resolved_voice_id)),
    )
    rate_type: SettingValueType = SettingValueType.FLOAT if profile.uses_wpm_rate else SettingValueType.INTEGER
    rate_minimum: float = 1.0 if profile.uses_wpm_rate else float(SAPI_RATE_MIN)
    rate_maximum: float | None = None if profile.uses_wpm_rate else float(SAPI_RATE_MAX)
    volume_type: SettingValueType = (
        SettingValueType.FLOAT if profile.uses_fractional_volume else SettingValueType.INTEGER
    )
    volume_maximum: float = 1.0 if profile.uses_fractional_volume else 100.0
    return (
        SettingSpec(
            setting_id="tts_profile.native_rate",
            label="SAPI native rate",
            description="Set native rate using the scale required by the selected SAPI voice.",
            value_type=rate_type,
            default=profile.default_native_rate,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=rate_minimum,
            maximum=rate_maximum,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_profile.native_volume",
            label="SAPI native volume",
            description="Set native volume using the scale required by the selected SAPI voice.",
            value_type=volume_type,
            default=profile.default_native_volume,
            scope=SettingScope.ENGINE_PROFILE,
            minimum=0.0,
            maximum=volume_maximum,
            depends_on=condition,
            invalidates=_TTS_INVALIDATES,
        ),
    )


def _audio_and_composition_specs(defaults: UserSettings) -> tuple[SettingSpec, ...]:
    return (
        SettingSpec(
            setting_id="tts_output_profile",
            label="Narration output codec",
            description="Select the durable AAC, EAC3, FLAC, MP3, Opus, or WAV narration profile.",
            value_type=SettingValueType.STRING,
            default=defaults.tts_output_profile,
            scope=SettingScope.GLOBAL,
            allowed_values=tuple(profile.value for profile in AudioCodecProfile),
            invalidates=_AUDIO_INVALIDATES,
        ),
        SettingSpec(
            setting_id="tts_output_bitrate",
            label="Narration bitrate",
            description="Optionally set an FFmpeg bitrate for a lossy narration codec.",
            value_type=SettingValueType.OPTIONAL_STRING,
            default=defaults.tts_output_bitrate,
            scope=SettingScope.GLOBAL,
            depends_on=(SettingCondition("tts_output_profile", _LOSSY_AUDIO_PROFILES),),
            invalidates=_AUDIO_INVALIDATES,
        ),
        SettingSpec(
            setting_id="narrator_mix_base_gain_db",
            label="Narrator base gain",
            description="Set the global narrator gain used while mixing narration audio.",
            value_type=SettingValueType.FLOAT,
            default=defaults.narrator_mix_base_gain_db,
            scope=SettingScope.GLOBAL,
            invalidates=_AUDIO_INVALIDATES,
        ),
        SettingSpec(
            setting_id="original_gain_db",
            label="Original audio gain",
            description="Set the original soundtrack gain used while mixing narration audio.",
            value_type=SettingValueType.FLOAT,
            default=defaults.original_gain_db,
            scope=SettingScope.GLOBAL,
            invalidates=_AUDIO_INVALIDATES,
        ),
        SettingSpec(
            setting_id="composition_quality_preset",
            label="Composition quality",
            description="Select the high, balanced, or compact hardsub quality target.",
            value_type=SettingValueType.STRING,
            default=defaults.composition_quality_preset,
            scope=SettingScope.GLOBAL,
            allowed_values=_COMPOSITION_PRESETS,
            invalidates=_COMPOSITION_INVALIDATES,
        ),
    )


def _environment_specs() -> tuple[SettingSpec, ...]:
    secret_specs: tuple[SettingSpec, ...] = tuple(
        SettingSpec(
            setting_id=setting_id,
            label=label,
            description=description,
            value_type=SettingValueType.STRING,
            default="",
            scope=SettingScope.SECRET,
            depends_on=depends_on,
            is_secret=True,
        )
        for setting_id, label, description, depends_on in (
            (
                "deepl_api_key",
                "DeepL API key",
                "Configure the key used only by the DeepL translation engine.",
                (SettingCondition("translation_engine", ("deepl",)),),
            ),
            (
                "elevenlabs_api_key",
                "ElevenLabs API key",
                "Configure the key used only by the official ElevenLabs engine.",
                (SettingCondition("tts_engine", ("elevenlabs",)),),
            ),
            ("anthropic_api_key", "Anthropic API key", "Configure the Anthropic provider key.", ()),
            ("gemini_api_key", "Gemini API key", "Configure the Google Gemini provider key.", ()),
            ("openai_api_key", "OpenAI API key", "Configure the OpenAI provider key.", ()),
            ("deepseek_api_key", "DeepSeek API key", "Configure the DeepSeek provider key.", ()),
            ("openrouter_api_key", "OpenRouter API key", "Configure the OpenRouter provider key.", ()),
            (
                "openai_compatible_api_key",
                "OpenAI-compatible API key",
                "Configure the optional key for an OpenAI-compatible endpoint.",
                (),
            ),
            (
                "palantir_token",
                "Palantir token",
                "Configure the Foundry token used by every Palantir model.",
                (),
            ),
        )
    )
    return (
        *secret_specs,
        SettingSpec(
            setting_id="openai_compatible_base_url",
            label="OpenAI-compatible base URL",
            description="Configure the self-hosted or gateway endpoint base URL.",
            value_type=SettingValueType.STRING,
            default="",
            scope=SettingScope.GLOBAL,
            depends_on=(SettingCondition("llm_provider", ("openai_compatible",)),),
            invalidates=_TRANSLATION_INVALIDATES,
        ),
    )


def _tts_model_values(context: SettingCatalogContext) -> tuple[tuple[SettingValue, ...], str]:
    if context.tts_engine == "edge":
        return (EDGE_PROVIDER_MODEL_ID,), EDGE_PROVIDER_MODEL_ID
    if context.tts_engine == "elevenbytes":
        return tuple(ENDPOINTS), "run6"
    if context.tts_engine == "elevenlabs":
        return tuple(POLISH_TTS_MODEL_IDS), DEFAULT_MODEL_ID
    if context.tts_engine == "sapi":
        return ("sapi5",), "sapi5"
    msg = f"Unknown TTS engine in catalog context: {context.tts_engine!r}"
    raise ValueError(msg)


def _tts_concurrency_max(context: SettingCatalogContext) -> int:
    if context.tts_engine == "elevenbytes" and context.elevenbytes_vpn_enabled:
        return min(TTS_CONCURRENCY_RANGE[1], VPN_MAX_CONCURRENCY)
    return TTS_CONCURRENCY_RANGE[1]


def _tts_voice_values(context: SettingCatalogContext) -> tuple[tuple[SettingValue, ...], str]:
    if context.tts_engine == "edge":
        return (MAREK_VOICE_ID, ZOFIA_VOICE_ID), MAREK_VOICE_ID
    if context.tts_engine == "elevenbytes":
        aliases: tuple[str, ...] = (DALLIN_ALIAS, *context.elevenbytes_custom_voice_aliases)
        return aliases, DALLIN_ALIAS
    if context.tts_engine == "elevenlabs":
        return (), ""
    if context.tts_engine == "sapi":
        return tuple(SAPI_PROFILES), "agnieszka"
    msg = f"Unknown TTS engine in catalog context: {context.tts_engine!r}"
    raise ValueError(msg)


def _profile_defaults(context: SettingCatalogContext) -> TtsVoiceProfileSettings:
    resolved_voice_id: str = context.tts_voice_id
    if context.tts_engine == "elevenbytes" and resolved_voice_id.casefold() == DALLIN_ALIAS:
        resolved_voice_id = DALLIN_VOICE_ID
    elif context.tts_engine == "sapi":
        resolved_voice_id = _sapi_profile(resolved_voice_id).resolved_voice_id
    profiles: dict[str, TtsVoiceProfileSettings] = default_tts_voice_profiles()
    key: str = tts_profile_key(context.tts_engine, resolved_voice_id)
    return profiles.get(key, TtsVoiceProfileSettings(concurrency=1 if context.tts_engine == "sapi" else None))


def _sapi_profile(voice_id: str) -> SapiVoiceProfile:
    candidate: str = voice_id.casefold()
    direct = SAPI_PROFILES.get(candidate)
    if direct is not None:
        return direct
    for profile in SAPI_PROFILES.values():
        if candidate == profile.resolved_voice_id.casefold():
            return profile
    msg = f"Unknown SAPI voice in catalog context: {voice_id!r}"
    raise ValueError(msg)
