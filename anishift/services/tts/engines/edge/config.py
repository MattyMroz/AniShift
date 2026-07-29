"""Validated configuration for the Edge speech engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import TtsConfigError, TtsUnsupportedError

from .constants import (
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    EDGE_PROVIDER_MODEL_ID,
)

__all__ = ["EdgeConfig"]

_PERCENT_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?P<sign>[+-])(?P<value>\d{1,3})%$")
"""Accepted Edge percentage syntax for rate and volume."""

_PITCH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?P<sign>[+-])(?P<value>\d{1,3})Hz$")
"""Accepted Edge pitch syntax."""

_VOICE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-.+Neural$")
"""Accepted short-name syntax used by the Edge voice service."""

_MAX_NATIVE_ADJUSTMENT: Final[int] = 100
"""Largest absolute native adjustment exposed by AniShift."""


@dataclass(frozen=True, slots=True)
class EdgeConfig:
    """Fully resolved provider settings for one Edge engine lifecycle."""

    provider_model_id: str
    voice_id: str
    rate: str
    volume: str
    pitch: str
    timeout_s: float

    @classmethod
    def from_tts_config(cls, config: TtsConfig) -> EdgeConfig:
        """Resolve and validate Edge-specific settings."""
        if config.provider_model_id.casefold() != EDGE_PROVIDER_MODEL_ID:
            _raise_config_error(
                f"Unknown Edge provider model: {config.provider_model_id!r}",
                field_name="provider_model_id",
            )
        voice_id: str = config.voice_id.strip()
        if _VOICE_PATTERN.fullmatch(voice_id) is None:
            _raise_config_error(
                "Edge voice id must use a provider neural short name",
                field_name="voice_id",
            )
        if config.engine_options:
            rendered: str = ", ".join(sorted(config.engine_options))
            _raise_unsupported_error(f"Unsupported Edge options: {rendered}")
        rate: str = _resolve_native_value(
            config.native_rate,
            default=DEFAULT_RATE,
            field_name="native_rate",
            pattern=_PERCENT_PATTERN,
        )
        volume: str = _resolve_native_value(
            config.native_volume,
            default=DEFAULT_VOLUME,
            field_name="native_volume",
            pattern=_PERCENT_PATTERN,
        )
        pitch: str = _resolve_native_value(
            config.native_pitch,
            default=DEFAULT_PITCH,
            field_name="native_pitch",
            pattern=_PITCH_PATTERN,
        )
        return cls(
            provider_model_id=EDGE_PROVIDER_MODEL_ID,
            voice_id=voice_id,
            rate=rate,
            volume=volume,
            pitch=pitch,
            timeout_s=config.request_timeout_s,
        )


def _resolve_native_value(
    value: str | float | None,
    *,
    default: str,
    field_name: str,
    pattern: re.Pattern[str],
) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        _raise_config_error(
            f"Edge {field_name} must use a signed provider string",
            field_name=field_name,
        )
    match: re.Match[str] | None = pattern.fullmatch(value)
    if match is None or int(match.group("value")) > _MAX_NATIVE_ADJUSTMENT:
        _raise_config_error(
            f"Edge {field_name} must be a signed adjustment between -100 and +100",
            field_name=field_name,
        )
    return value


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Select edge-default and valid Edge voice, rate, volume, and pitch settings.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)


def _raise_unsupported_error(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message=message,
        suggestion="Use the dedicated native rate, volume, and pitch fields.",
    )
    raise TtsUnsupportedError(context=context)
