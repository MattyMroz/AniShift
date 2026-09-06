"""Mapping between catalog specs and the preferences or preset fields they describe."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final

from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.config.field_catalog import SettingCondition, SettingSpec, SettingValue, SettingValueType
from anishift.config.user_settings import CustomVoiceSetting, JsonScalar, TtsVoiceProfileSettings, UserSettings

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "assign_setting_value",
    "preset_setting_is_active",
    "preset_with_value",
    "read_preset_value",
    "read_setting_value",
    "setting_is_active",
    "setting_is_persisted",
]

# ── Constants ────────────────────────────────────────────────────────────────

_PROFILE_PREFIX: Final[str] = "tts_profile."
"""Setting-ID prefix addressing a field of the active TTS voice profile."""

_CUSTOM_VOICES_FIELD: Final[str] = "elevenbytes_custom_voices"
"""Preference whose removals must run through the ``UserSettings`` helper."""

_ENGINE_OPTIONS_PREFIX: Final[str] = "tts_profile.engine_options."
"""Setting-ID prefix addressing one provider option of that voice profile."""

_SCALAR_VALUE_TYPES: Final[frozenset[SettingValueType]] = frozenset(
    {
        SettingValueType.STRING,
        SettingValueType.OPTIONAL_STRING,
        SettingValueType.INTEGER,
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.FLOAT,
        SettingValueType.OPTIONAL_FLOAT,
        SettingValueType.BOOLEAN,
    }
)
"""Catalog types persisted as a single JSON scalar."""

_COLLECTION_VALUE_TYPES: Final[frozenset[SettingValueType]] = frozenset(
    {
        SettingValueType.STRING_LIST,
        SettingValueType.STRING_SET,
        SettingValueType.OBJECT_LIST,
    }
)
"""Catalog types persisted as an ordered list or an unordered set."""

_OPTIONAL_VALUE_TYPES: Final[frozenset[SettingValueType]] = frozenset(
    {
        SettingValueType.OPTIONAL_STRING,
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.OPTIONAL_FLOAT,
    }
)
"""Catalog types for which ``None`` is a real choice, not a missing value."""

_MISSING: Final[object] = object()
"""Sentinel separating an absent stored value from a persisted ``None``."""

_PRESET_IDENTITY: Final[frozenset[str]] = frozenset({"preset_id", "name", "products"})
"""Preset fields that name it or nest others, so no catalog spec addresses them."""


def read_setting_value(settings: UserSettings, spec: SettingSpec) -> SettingValue:
    """Return the value *settings* holds for *spec*, or the spec default."""
    raw: object = _stored_value(settings, spec.setting_id)
    if raw is _MISSING or (raw is None and spec.value_type not in _OPTIONAL_VALUE_TYPES):
        return spec.default
    if _is_collection_type(spec.value_type):
        return _collection_value(spec, raw)
    return _scalar_value(spec, raw)


def assign_setting_value(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None:
    """Write *value* into *settings* at the location *spec* addresses."""
    option_key: str | None = _engine_option_key(spec.setting_id)
    if option_key is not None:
        _reject_collection_type(spec)
        settings.ensure_active_tts_profile().engine_options[option_key] = _json_scalar(spec, value)
        return
    profile_field: str | None = _profile_field(spec.setting_id)
    if profile_field is not None:
        _reject_collection_type(spec)
        setattr(settings.ensure_active_tts_profile(), profile_field, _scalar_value(spec, value))
        return
    _assign_preference(settings, spec, value)


def setting_is_active(spec: SettingSpec, settings: UserSettings) -> bool:
    """Report whether every dependency of *spec* holds for *settings*."""
    return all(
        _condition_holds(condition, _preference_value(settings, condition.setting_id)) for condition in spec.depends_on
    )


def setting_is_persisted(spec: SettingSpec) -> bool:
    """Report whether *spec* addresses a field of the panel preferences."""
    return spec.setting_id.startswith(_PROFILE_PREFIX) or spec.setting_id in UserSettings.__dataclass_fields__


def read_preset_value(preset: AutoPreset, spec: SettingSpec) -> SettingValue:
    """Return the catalog value *preset* holds for *spec*."""
    return _catalog_value(_preset_value(preset, spec.setting_id))


def preset_setting_is_active(spec: SettingSpec, preset: AutoPreset) -> bool:
    """Report whether every dependency of *spec* holds for *preset*."""
    return all(
        _condition_holds(condition, _catalog_value(_preset_value(preset, condition.setting_id)))
        for condition in spec.depends_on
    )


def preset_with_value(preset: AutoPreset, spec: SettingSpec, value: SettingValue) -> AutoPreset:
    """Return *preset* with the field *spec* addresses replaced by a validated *value*."""
    _preset_value(preset, spec.setting_id)
    spec.validate_value(value)
    if spec.setting_id in ProductIntent.__dataclass_fields__:
        return replace(preset, products=_products_with_value(preset.products, spec, value))
    if spec.setting_id == "source_subtitle_language":
        return replace(preset, source_subtitle_language=None if value is None else _text(spec, value))
    text: str = _text(spec, value)
    if spec.setting_id == "subtitle_source_policy":
        return replace(preset, subtitle_source_policy=SubtitleSourcePolicy(text))
    if spec.setting_id == "translation_action":
        return replace(preset, translation_action=TranslationAction(text))
    if spec.setting_id == "subtitle_output_format":
        return replace(preset, subtitle_output_format=SubtitleOutputFormat(text))
    msg: str = f"Setting {spec.setting_id!r} has no preset writer"
    raise ValueError(msg)


def _condition_holds(condition: SettingCondition, current: object) -> bool:
    if isinstance(current, (list, tuple, frozenset, set)):
        return any(item in condition.allowed_values for item in current)
    return current in condition.allowed_values


def _preset_value(preset: AutoPreset, setting_id: str) -> object:
    if setting_id in ProductIntent.__dataclass_fields__:
        return getattr(preset.products, setting_id)
    if setting_id in AutoPreset.__dataclass_fields__ and setting_id not in _PRESET_IDENTITY:
        return getattr(preset, setting_id)
    msg: str = f"Setting {setting_id!r} is not an automatic preset field"
    raise ValueError(msg)


def _catalog_value(raw: object) -> SettingValue:
    if isinstance(raw, frozenset):
        return frozenset(str(item) for item in raw)
    if raw is None:
        return None
    return str(raw)


def _products_with_value(products: ProductIntent, spec: SettingSpec, value: SettingValue) -> ProductIntent:
    if spec.setting_id == "requested_products":
        requested: frozenset[ProductKind] = frozenset(ProductKind(item) for item in _string_set(spec, value))
        return _products_with_requested(products, requested)
    if spec.setting_id == "mkv_tracks":
        return replace(products, mkv_tracks=frozenset(MkvTrackProduct(item) for item in _string_set(spec, value)))
    text: str = _text(spec, value)
    if spec.setting_id == "burn_subtitle_product":
        return replace(products, burn_subtitle_product=BurnSubtitleProduct(text))
    return replace(products, mp4_audio_source=Mp4AudioSource(text))


def _products_with_requested(products: ProductIntent, requested: frozenset[ProductKind]) -> ProductIntent:
    has_mkv: bool = ProductKind.MKV in requested
    has_mp4: bool = ProductKind.MP4 in requested
    # Dropping a container also drops the choices that exist only for it, so the
    # intent stays valid without asking the user to clear them first.
    return ProductIntent(
        requested_products=requested,
        burn_subtitle_product=products.burn_subtitle_product if has_mp4 else BurnSubtitleProduct.NONE,
        mkv_tracks=products.mkv_tracks if has_mkv else frozenset(),
        mp4_audio_source=products.mp4_audio_source if has_mp4 else Mp4AudioSource.AUTO,
    )


def _text(spec: SettingSpec, value: object) -> str:
    if isinstance(value, str):
        return value
    msg: str = f"Value of {spec.setting_id!r} is not text"
    raise TypeError(msg)


def _string_set(spec: SettingSpec, value: object) -> frozenset[str]:
    return frozenset(_string_items(spec, _collection_items(spec, value)))


def _stored_value(settings: UserSettings, setting_id: str) -> object:
    option_key: str | None = _engine_option_key(setting_id)
    if option_key is not None:
        return settings.active_tts_profile.engine_options.get(option_key, _MISSING)
    profile_field: str | None = _profile_field(setting_id)
    if profile_field is not None:
        return getattr(settings.active_tts_profile, profile_field)
    return _preference_value(settings, setting_id)


def _assign_preference(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None:
    _preference_value(settings, spec.setting_id)
    if not _is_collection_type(spec.value_type):
        setattr(settings, spec.setting_id, _scalar_value(spec, value))
        return
    if spec.setting_id == _CUSTOM_VOICES_FIELD:
        _assign_custom_voices(settings, spec, value)
        return
    setattr(settings, spec.setting_id, _ordered_items(_collection_value(spec, value)))


def _assign_custom_voices(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None:
    voices: tuple[CustomVoiceSetting, ...] = _voice_items(spec, _collection_items(spec, value))
    kept: frozenset[str] = frozenset(voice.alias.casefold() for voice in voices)
    for voice in tuple(settings.elevenbytes_custom_voices):
        if voice.alias.casefold() in kept:
            continue
        # The domain helper re-selects the built-in voice when the retired
        # alias was the active one, so no selection can dangle.
        settings.remove_elevenbytes_voice(voice.alias)
    settings.elevenbytes_custom_voices = list(voices)


def _preference_value(settings: UserSettings, setting_id: str) -> object:
    if setting_id not in UserSettings.__dataclass_fields__:
        msg = f"Setting {setting_id!r} is not a persisted user preference"
        raise ValueError(msg)
    return getattr(settings, setting_id)


def _engine_option_key(setting_id: str) -> str | None:
    if not setting_id.startswith(_ENGINE_OPTIONS_PREFIX):
        return None
    key: str = setting_id[len(_ENGINE_OPTIONS_PREFIX) :]
    if not key:
        msg = f"Setting {setting_id!r} names no provider option"
        raise ValueError(msg)
    return key


def _profile_field(setting_id: str) -> str | None:
    if not setting_id.startswith(_PROFILE_PREFIX):
        return None
    name: str = setting_id[len(_PROFILE_PREFIX) :]
    if name not in TtsVoiceProfileSettings.__dataclass_fields__:
        msg = f"Setting {setting_id!r} names no voice profile field"
        raise ValueError(msg)
    return name


def _is_collection_type(value_type: SettingValueType) -> bool:
    if value_type in _COLLECTION_VALUE_TYPES:
        return True
    if value_type in _SCALAR_VALUE_TYPES:
        return False
    msg = f"Unsupported setting value type: {value_type!r}"
    raise ValueError(msg)


def _reject_collection_type(spec: SettingSpec) -> None:
    if _is_collection_type(spec.value_type):
        msg = f"Setting {spec.setting_id!r} cannot store a collection in a voice profile"
        raise TypeError(msg)


def _scalar_value(spec: SettingSpec, value: object) -> SettingValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = f"Value of {spec.setting_id!r} is not a scalar preference"
    raise TypeError(msg)


def _json_scalar(spec: SettingSpec, value: object) -> JsonScalar:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = f"Value of {spec.setting_id!r} is not a provider option scalar"
    raise TypeError(msg)


def _collection_items(spec: SettingSpec, value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple, frozenset, set)):
        msg = f"Value of {spec.setting_id!r} is not a collection preference"
        raise TypeError(msg)
    return tuple(value)


def _collection_value(
    spec: SettingSpec,
    value: object,
) -> tuple[str, ...] | frozenset[str] | tuple[CustomVoiceSetting, ...]:
    items: tuple[object, ...] = _collection_items(spec, value)
    if spec.value_type is SettingValueType.OBJECT_LIST:
        return _voice_items(spec, items)
    if spec.value_type is SettingValueType.STRING_SET:
        return frozenset(_string_items(spec, items))
    return _string_items(spec, items)


def _ordered_items(checked: tuple[str, ...] | frozenset[str] | tuple[CustomVoiceSetting, ...]) -> tuple[object, ...]:
    if isinstance(checked, frozenset):
        # A set has no order, so persist it sorted to keep settings.json stable.
        return tuple(sorted(checked))
    return checked


def _string_items(spec: SettingSpec, value: Iterable[object]) -> tuple[str, ...]:
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            msg = f"Value of {spec.setting_id!r} accepts strings only"
            raise TypeError(msg)
        items.append(item)
    return tuple(items)


def _voice_items(spec: SettingSpec, value: Iterable[object]) -> tuple[CustomVoiceSetting, ...]:
    items: list[CustomVoiceSetting] = []
    for item in value:
        if not isinstance(item, CustomVoiceSetting):
            msg = f"Value of {spec.setting_id!r} accepts custom voices only"
            raise TypeError(msg)
        items.append(item)
    return tuple(items)
