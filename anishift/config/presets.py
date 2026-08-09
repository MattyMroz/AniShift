"""Versioned, atomic persistence for reusable automatic workflow presets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

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
from anishift.config.user_settings import config_path

__all__ = [
    "AutoPresetFile",
    "default_preset_file",
    "load_presets",
    "presets_path",
    "save_presets",
]

# ── Constants ────────────────────────────────────────────────────────────────

PRESET_SCHEMA_VERSION: Final[int] = 1
"""Current schema of the independent auto-preset file."""

DEFAULT_PRESET_ID: Final[str] = "default"
"""Stable identifier of the safe bundled auto preset."""

_PRESETS_FILE_NAME: Final[str] = "presets.json"
"""Filename stored beside user settings outside the media workspace."""

_ROOT_KEYS: Final[frozenset[str]] = frozenset({"schema_version", "presets", "default_preset_id"})
"""Only root keys accepted from a persisted preset document."""

_PRESET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "preset_id",
        "name",
        "products",
        "subtitle_source_policy",
        "translation_action",
        "source_subtitle_language",
        "subtitle_output_format",
    }
)
"""Only keys accepted for one serialized auto preset."""

_PRODUCT_KEYS: Final[frozenset[str]] = frozenset(
    {"requested_products", "burn_subtitle_product", "mkv_tracks", "mp4_audio_source"}
)
"""Only keys accepted for serialized product intent."""


@dataclass(frozen=True, slots=True)
class AutoPresetFile:
    """One complete, versioned collection of named automatic presets."""

    schema_version: int
    presets: tuple[AutoPreset, ...]
    default_preset_id: str

    def __post_init__(self) -> None:
        if self.schema_version != PRESET_SCHEMA_VERSION:
            msg = "Unsupported auto-preset schema version"
            raise ValueError(msg)
        if not self.presets:
            msg = "Auto-preset file requires at least one preset"
            raise ValueError(msg)
        preset_ids: tuple[str, ...] = tuple(preset.preset_id for preset in self.presets)
        if len(preset_ids) != len(set(preset_ids)):
            msg = "Auto-preset IDs must be unique"
            raise ValueError(msg)
        if self.default_preset_id not in preset_ids:
            msg = "Default auto-preset ID must reference a stored preset"
            raise ValueError(msg)


def default_preset_file() -> AutoPresetFile:
    """Return an independent safe default without reading or writing disk."""
    preset = AutoPreset(
        preset_id=DEFAULT_PRESET_ID,
        name="Polish subtitles",
        products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    )
    return AutoPresetFile(
        schema_version=PRESET_SCHEMA_VERSION,
        presets=(preset,),
        default_preset_id=preset.preset_id,
    )


def presets_path() -> Path:
    """Return the auto-preset file beside ``config/settings.json``."""
    return config_path().with_name(_PRESETS_FILE_NAME)


def load_presets() -> AutoPresetFile:
    """Load one complete preset file or return defaults without partial recovery."""
    path: Path = presets_path()
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        return _decode_file(raw)
    except OSError, json.JSONDecodeError, KeyError, TypeError, ValueError:
        return default_preset_file()


def save_presets(preset_file: AutoPresetFile) -> None:
    """Atomically persist a fully validated auto-preset collection."""
    payload: str = json.dumps(_encode_file(preset_file), indent=2, ensure_ascii=False) + "\n"
    path: Path = presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_name(f"{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _decode_file(raw: object) -> AutoPresetFile:
    document: dict[str, object] = _strict_object(raw, _ROOT_KEYS, "preset file")
    schema_version: object = document["schema_version"]
    default_preset_id: object = document["default_preset_id"]
    presets_raw: object = document["presets"]
    if type(schema_version) is not int or not isinstance(default_preset_id, str) or not isinstance(presets_raw, list):
        msg = "Auto-preset file carries invalid root values"
        raise TypeError(msg)
    presets: tuple[AutoPreset, ...] = tuple(_decode_preset(item) for item in presets_raw)
    return AutoPresetFile(
        schema_version=schema_version,
        presets=presets,
        default_preset_id=default_preset_id,
    )


def _decode_preset(raw: object) -> AutoPreset:
    document: dict[str, object] = _strict_object(raw, _PRESET_KEYS, "preset")
    preset_id: object = document["preset_id"]
    name: object = document["name"]
    source_language: object = document["source_subtitle_language"]
    if not isinstance(preset_id, str) or not isinstance(name, str):
        msg = "Auto-preset identity must be textual"
        raise TypeError(msg)
    if source_language is not None and not isinstance(source_language, str):
        msg = "Auto-preset source language must be text or null"
        raise TypeError(msg)
    return AutoPreset(
        preset_id=preset_id,
        name=name,
        products=_decode_products(document["products"]),
        subtitle_source_policy=SubtitleSourcePolicy(_required_string(document, "subtitle_source_policy")),
        translation_action=TranslationAction(_required_string(document, "translation_action")),
        source_subtitle_language=source_language,
        subtitle_output_format=SubtitleOutputFormat(_required_string(document, "subtitle_output_format")),
    )


def _decode_products(raw: object) -> ProductIntent:
    document: dict[str, object] = _strict_object(raw, _PRODUCT_KEYS, "product intent")
    requested: object = document["requested_products"]
    tracks: object = document["mkv_tracks"]
    if not isinstance(requested, list) or not isinstance(tracks, list):
        msg = "Preset product collections must be lists"
        raise TypeError(msg)
    return ProductIntent(
        requested_products=frozenset(ProductKind(_list_string(value)) for value in requested),
        burn_subtitle_product=BurnSubtitleProduct(_required_string(document, "burn_subtitle_product")),
        mkv_tracks=frozenset(MkvTrackProduct(_list_string(value)) for value in tracks),
        mp4_audio_source=Mp4AudioSource(_required_string(document, "mp4_audio_source")),
    )


def _encode_file(preset_file: AutoPresetFile) -> dict[str, object]:
    return {
        "schema_version": preset_file.schema_version,
        "presets": [_encode_preset(preset) for preset in preset_file.presets],
        "default_preset_id": preset_file.default_preset_id,
    }


def _encode_preset(preset: AutoPreset) -> dict[str, object]:
    return {
        "preset_id": preset.preset_id,
        "name": preset.name,
        "products": {
            "requested_products": sorted(product.value for product in preset.products.requested_products),
            "burn_subtitle_product": preset.products.burn_subtitle_product.value,
            "mkv_tracks": sorted(track.value for track in preset.products.mkv_tracks),
            "mp4_audio_source": preset.products.mp4_audio_source.value,
        },
        "subtitle_source_policy": preset.subtitle_source_policy.value,
        "translation_action": preset.translation_action.value,
        "source_subtitle_language": preset.source_subtitle_language,
        "subtitle_output_format": preset.subtitle_output_format.value,
    }


def _strict_object(raw: object, expected_keys: frozenset[str], label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"Serialized {label} must be an object with text keys"
        raise TypeError(msg)
    document: dict[str, object] = raw
    if frozenset(document) != expected_keys:
        msg = f"Serialized {label} has missing or unknown fields"
        raise ValueError(msg)
    return document


def _required_string(document: dict[str, object], key: str) -> str:
    value: object = document[key]
    if not isinstance(value, str):
        msg = f"Preset field {key!r} must be text"
        raise TypeError(msg)
    return value


def _list_string(value: object) -> str:
    if not isinstance(value, str):
        msg = "Preset collection values must be text"
        raise TypeError(msg)
    return value
