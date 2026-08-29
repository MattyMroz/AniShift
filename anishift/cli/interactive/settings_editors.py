"""Typed scalar conversion for interactive product settings."""

from __future__ import annotations

from anishift.config.field_catalog import SettingSpec, SettingValue, SettingValueType

__all__ = ["parse_setting_input"]


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
