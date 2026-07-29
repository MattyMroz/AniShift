"""Configuration for the official ElevenLabs TTS engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import TtsConfigError, TtsUnsupportedError

from .options import ElevenLabsOptions, resolve_elevenlabs_options

__all__ = ["ElevenLabsConfig"]

_PROVIDER_ID: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
"""Safe grammar for caller-selected ElevenLabs model and voice identifiers."""


@dataclass(frozen=True, slots=True)
class ElevenLabsConfig:
    """Resolved settings for the official ElevenLabs SDK."""

    api_key: str = field(repr=False)
    provider_model_id: str
    voice_id: str
    timeout_s: float
    options: ElevenLabsOptions

    @classmethod
    def from_tts_config(cls, config: TtsConfig) -> ElevenLabsConfig:
        """Resolve official ElevenLabs settings without importing its SDK."""
        model_id: str = _validate_provider_id(
            config.provider_model_id,
            field_name="provider_model_id",
        )
        voice_id: str = _validate_provider_id(config.voice_id, field_name="voice_id")
        if any(value is not None for value in (config.native_rate, config.native_volume, config.native_pitch)):
            message: str = "ElevenLabs native controls must use engine_options"
            raise TtsUnsupportedError(message)
        return cls(
            api_key=config.elevenlabs_api_key.strip(),
            provider_model_id=model_id,
            voice_id=voice_id,
            timeout_s=config.request_timeout_s,
            options=resolve_elevenlabs_options(config.engine_options),
        )


def _validate_provider_id(value: str, *, field_name: str) -> str:
    resolved: str = value.strip()
    if _PROVIDER_ID.fullmatch(resolved) is None:
        _raise_config(
            f"ElevenLabs {field_name} must be a stable provider identifier",
            field_name,
        )
    return resolved


def _raise_config(message: str, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Select a valid official ElevenLabs model and voice ID.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)
