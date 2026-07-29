"""Validated options for the official ElevenLabs TTS engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsConfigError, TtsUnsupportedError
from anishift.services.tts.types import EngineOptions

from .constants import DEFAULT_OUTPUT_FORMAT, OUTPUT_FORMATS, ElevenLabsOutputSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ElevenLabsAttempt",
    "ElevenLabsOptions",
    "ElevenLabsOutputSpec",
    "ElevenLabsVoiceSettings",
    "resolve_elevenlabs_options",
]

_OPTION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "output_format",
        "similarity_boost",
        "speed",
        "stability",
        "style",
        "use_speaker_boost",
    },
)
"""Provider-specific options accepted by the official SDK adapter."""


@dataclass(frozen=True, slots=True)
class ElevenLabsVoiceSettings:
    """Validated voice controls sent to one official SDK request."""

    stability: float
    similarity_boost: float
    style: float
    use_speaker_boost: bool
    speed: float

    def as_options(self) -> dict[str, float | bool]:
        """Return the exact scalar settings used by fingerprinting and SDK calls."""
        return {
            "similarity_boost": self.similarity_boost,
            "speed": self.speed,
            "stability": self.stability,
            "style": self.style,
            "use_speaker_boost": self.use_speaker_boost,
        }


@dataclass(frozen=True, slots=True)
class ElevenLabsAttempt:
    """Resolved inputs for one official ElevenLabs payload submission."""

    text: str
    voice_id: str
    model_id: str
    output_format: str
    voice_settings: ElevenLabsVoiceSettings
    deadline_s: float


@dataclass(frozen=True, slots=True)
class ElevenLabsOptions:
    """Resolved official ElevenLabs request options."""

    output: ElevenLabsOutputSpec
    voice_settings: ElevenLabsVoiceSettings

    def as_engine_options(self) -> dict[str, str | float | bool]:
        """Return every resolved provider option in canonical scalar form."""
        return {
            "output_format": self.output.token,
            **self.voice_settings.as_options(),
        }


def resolve_elevenlabs_options(options: EngineOptions) -> ElevenLabsOptions:
    """Resolve and validate official ElevenLabs options before a paid request."""
    unknown_keys: set[str] = set(options) - _OPTION_KEYS
    if unknown_keys:
        rendered: str = ", ".join(sorted(unknown_keys))
        _raise_unsupported(f"Unsupported ElevenLabs options: {rendered}")
    output_token: str = _read_output_token(options, DEFAULT_OUTPUT_FORMAT)
    output: ElevenLabsOutputSpec | None = OUTPUT_FORMATS.get(output_token)
    if output is None:
        _raise_unsupported(
            f"Unsupported ElevenLabs output format: {output_token!r}",
        )
    return ElevenLabsOptions(
        output=output,
        voice_settings=ElevenLabsVoiceSettings(
            stability=_read_float(options, "stability", default=0.5, minimum=0.0, maximum=1.0),
            similarity_boost=_read_float(
                options,
                "similarity_boost",
                default=0.75,
                minimum=0.0,
                maximum=1.0,
            ),
            style=_read_float(options, "style", default=0.0, minimum=0.0, maximum=1.0),
            use_speaker_boost=_read_bool(options, "use_speaker_boost", default=True),
            speed=_read_float(options, "speed", default=1.0, minimum=0.7, maximum=1.2),
        ),
    )


def _read_output_token(options: EngineOptions, default: str) -> str:
    value: str | int | float | bool | None = options.get("output_format")
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        _raise_config("ElevenLabs output_format must be a non-empty token", "output_format")
    return value.strip()


def _read_float(
    options: Mapping[str, str | int | float | bool | None],
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value: str | int | float | bool | None = options.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_config(f"ElevenLabs {key} must be numeric", key)
    resolved: float = float(value)
    if not math.isfinite(resolved) or not minimum <= resolved <= maximum:
        _raise_config(
            f"ElevenLabs {key} must be between {minimum} and {maximum}",
            key,
        )
    return resolved


def _read_bool(
    options: Mapping[str, str | int | float | bool | None],
    key: str,
    *,
    default: bool,
) -> bool:
    value: str | int | float | bool | None = options.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        _raise_config(f"ElevenLabs {key} must be boolean", key)
    return value


def _raise_config(message: str, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Check the official ElevenLabs model, voice, and voice settings.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)


def _raise_unsupported(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message=message,
        suggestion="Select a supported official ElevenLabs output token and option set.",
    )
    raise TtsUnsupportedError(context=context)
