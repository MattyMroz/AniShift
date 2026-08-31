"""Typed scalar conversion for interactive product settings."""

from __future__ import annotations

from typing import Final

from anishift.config.field_catalog import SettingSpec, SettingValue, SettingValueType
from anishift.config.user_settings import CustomVoiceSetting

__all__ = ["VOICE_SEPARATOR", "format_voice_input", "parse_setting_input", "parse_voice_input"]

VOICE_SEPARATOR: Final[str] = "|"
"""Separator between the three parts of one custom voice in the text editor."""

_VOICE_PART_COUNT: Final[int] = 3
"""Number of parts one custom voice line carries: alias, label and provider ID."""


def parse_setting_input(spec: SettingSpec, raw_value: str) -> SettingValue:
    """Convert one textual editor value and validate it through its catalog spec."""
    value: SettingValue
    cleaned: str = raw_value.strip()
    match spec.value_type:
        case SettingValueType.INTEGER:
            value = int(cleaned)
        case SettingValueType.OPTIONAL_INTEGER:
            value = int(cleaned) if cleaned else None
        case SettingValueType.FLOAT:
            value = float(cleaned)
        case SettingValueType.OPTIONAL_FLOAT:
            value = float(cleaned) if cleaned else None
        case SettingValueType.STRING:
            value = cleaned
        case SettingValueType.OPTIONAL_STRING:
            value = cleaned or None
        case SettingValueType.BOOLEAN:
            value = _parse_boolean(cleaned)
        case SettingValueType.STRING_LIST:
            value = tuple(_split_items(cleaned))
        case SettingValueType.STRING_SET:
            value = frozenset(_split_items(cleaned))
        case _:
            msg = f"Interactive scalar editor does not support {spec.value_type.value}"
            raise TypeError(msg)
    spec.validate_value(value)
    return value


def parse_voice_input(raw_value: str) -> CustomVoiceSetting:
    """Convert one ``alias | label | provider ID`` line into a custom voice."""
    parts: list[str] = [part.strip() for part in raw_value.split(VOICE_SEPARATOR)]
    if len(parts) != _VOICE_PART_COUNT or not all(parts):
        msg = f"Custom voice needs alias {VOICE_SEPARATOR} label {VOICE_SEPARATOR} provider ID"
        raise ValueError(msg)
    alias, label, voice_id = parts
    return CustomVoiceSetting(alias=alias, label=label, voice_id=voice_id)


def format_voice_input(voice: CustomVoiceSetting) -> str:
    """Render one custom voice as the editable line accepted back by the parser."""
    return f" {VOICE_SEPARATOR} ".join((voice.alias, voice.label, voice.voice_id))


def _parse_boolean(value: str) -> bool:
    normalized: str = value.casefold()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    msg = "Boolean setting accepts true or false"
    raise ValueError(msg)


def _split_items(value: str) -> tuple[str, ...]:
    items: tuple[str, ...] = tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(dict.fromkeys(items))
