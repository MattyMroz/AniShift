"""Mapping between catalog specs and the panel preferences they describe.

``field_catalog`` says what one setting means; ``user_settings`` stores it. This
module is the only translation between the two, so no frontend needs to know
that ``tts_profile.engine_options.stability`` lives in the voice profile of the
currently selected engine and voice.

Only persisted ``UserSettings`` fields are addressable. Workflow scopes
(``auto_preset``, ``manual_run``), environment secrets and unknown value types
are rejected loudly instead of being silently ignored.

Public API:
    read_setting_value: Stored value of one spec, or its default when unset.
    assign_setting_value: Write one value into mutable settings.
    setting_is_active: Whether every dependency of one spec is satisfied.
    setting_is_persisted: Whether one spec addresses the preference file at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.config.field_catalog import SettingCondition, SettingSpec, SettingValue, SettingValueType
from anishift.config.user_settings import CustomVoiceSetting, JsonScalar, TtsVoiceProfileSettings, UserSettings

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["assign_setting_value", "read_setting_value", "setting_is_active", "setting_is_persisted"]

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


def read_setting_value(settings: UserSettings, spec: SettingSpec) -> SettingValue:
    """Return the value *settings* holds for *spec*, or the spec default.

    Args:
        settings: Panel preferences to read.
        spec: Catalog contract of one addressable preference.

    Returns:
        The stored value, normalized to the container the spec declares. An
        absent value, and a ``None`` under a non-optional type, yield the
        spec default so every active field has something to render.

    Raises:
        ValueError: The spec addresses no persisted preference, or declares an
            unsupported value type.
        TypeError: The stored value cannot represent the declared type.
    """
    raw: object = _stored_value(settings, spec.setting_id)
    if raw is _MISSING or (raw is None and spec.value_type not in _OPTIONAL_VALUE_TYPES):
        return spec.default
    if _is_collection_type(spec.value_type):
        return _collection_value(spec, raw)
    return _scalar_value(spec, raw)


def assign_setting_value(settings: UserSettings, spec: SettingSpec, value: SettingValue) -> None:
    """Write *value* into *settings* at the location *spec* addresses.

    Validate through :meth:`SettingSpec.validate_value` first; this function
    only rejects values it physically cannot store. Assigning a voice-profile
    field materializes the profile of the active engine and voice. Dropping a
    custom ElevenBytes voice runs through ``remove_elevenbytes_voice``, so the
    active selection can never point at a retired alias.

    Args:
        settings: Mutable panel preferences to update in place.
        spec: Catalog contract of one addressable preference.
        value: Value already accepted by the spec.

    Raises:
        ValueError: The spec addresses no persisted preference, or declares an
            unsupported value type.
        TypeError: The value cannot be stored under the declared type.
    """
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
    """Report whether every dependency of *spec* holds for *settings*.

    Args:
        spec: Catalog contract whose ``depends_on`` conditions are evaluated.
        settings: Panel preferences the conditions are read from.

    Returns:
        ``True`` when the spec has no dependency or all of them match.

    Raises:
        ValueError: One condition names a field no preference file stores.
    """
    return all(_condition_holds(condition, settings) for condition in spec.depends_on)


def setting_is_persisted(spec: SettingSpec) -> bool:
    """Report whether *spec* addresses a field of the panel preferences.

    Workflow scopes and environment values describe state that lives outside
    ``UserSettings``; only a persisted spec can be read, assigned, or asked
    whether its dependencies hold.

    Args:
        spec: Catalog contract to classify.

    Returns:
        ``True`` for a persisted preference or a voice-profile field.
    """
    return spec.setting_id.startswith(_PROFILE_PREFIX) or spec.setting_id in UserSettings.__dataclass_fields__


def _condition_holds(condition: SettingCondition, settings: UserSettings) -> bool:
    current: object = _preference_value(settings, condition.setting_id)
    if isinstance(current, (list, tuple, frozenset, set)):
        return any(item in condition.allowed_values for item in current)
    return current in condition.allowed_values


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
