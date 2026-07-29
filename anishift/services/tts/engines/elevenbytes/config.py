"""Validated configuration for the ElevenBytes proxy engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Never, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import TtsConfigError, TtsUnsupportedError
from anishift.services.tts.types import EngineOptions

from .constants import DALLIN_ALIAS, DALLIN_VOICE_ID, ENDPOINTS
from .types import ElevenBytesEndpointVariant, ElevenBytesV3Settings

__all__ = ["ElevenBytesConfig", "resolve_voice_id"]

_RUN7_OPTION_KEYS: Final[frozenset[str]] = frozenset(
    {"similarity_boost", "stability", "style", "use_speaker_boost"},
)
"""Provider options accepted only by the run7 endpoint."""


@dataclass(frozen=True, slots=True)
class ElevenBytesConfig:
    """Provider settings resolved from the shared TTS configuration."""

    endpoint_variant: ElevenBytesEndpointVariant
    voice_id: str
    timeout_s: float
    run7_settings: ElevenBytesV3Settings | None

    @classmethod
    def from_tts_config(cls, config: TtsConfig) -> ElevenBytesConfig:
        """Resolve and validate ElevenBytes-specific settings."""
        raw_endpoint_variant: str = config.provider_model_id.strip().lower()
        if raw_endpoint_variant not in ENDPOINTS:
            _raise_config_error(
                f"Unknown ElevenBytes endpoint variant: {config.provider_model_id!r}",
                field_name="provider_model_id",
            )
        endpoint_variant = cast("ElevenBytesEndpointVariant", raw_endpoint_variant)
        run7_settings: ElevenBytesV3Settings | None = _resolve_run7_settings(
            endpoint_variant,
            config.engine_options,
        )
        return cls(
            endpoint_variant=endpoint_variant,
            voice_id=resolve_voice_id(config.voice_id),
            timeout_s=config.request_timeout_s,
            run7_settings=run7_settings,
        )

    @property
    def endpoint(self) -> str:
        """Return the exact endpoint URL for this variant."""
        return ENDPOINTS[self.endpoint_variant]

    @property
    def is_experimental(self) -> bool:
        """Whether the selected proxy variant is experimental."""
        return self.endpoint_variant == "run7"


def resolve_voice_id(alias_or_id: str) -> str:
    """Resolve Dallin while preserving caller-resolved custom voice IDs."""
    voice: str = alias_or_id.strip()
    if not voice:
        _raise_config_error("ElevenBytes voice id cannot be empty", field_name="voice_id")
    if voice.casefold() == DALLIN_ALIAS:
        return DALLIN_VOICE_ID
    return voice


def _resolve_run7_settings(
    endpoint_variant: str,
    options: EngineOptions,
) -> ElevenBytesV3Settings | None:
    unknown_keys: set[str] = set(options) - _RUN7_OPTION_KEYS
    if unknown_keys:
        rendered: str = ", ".join(sorted(unknown_keys))
        _raise_unsupported_options(f"Unsupported ElevenBytes options: {rendered}")
    if endpoint_variant == "run6":
        if options:
            _raise_unsupported_options("ElevenBytes run6 does not accept run7 voice settings")
        return None
    return ElevenBytesV3Settings(
        stability=_read_float_option(options, "stability", 0.5),
        similarity_boost=_read_float_option(options, "similarity_boost", 0.75),
        style=_read_float_option(options, "style", 0.0),
        use_speaker_boost=_read_bool_option(options, "use_speaker_boost", True),
    )


def _read_float_option(options: EngineOptions, key: str, default: float) -> float:
    value: str | int | float | bool | None = options.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_unsupported_options(f"ElevenBytes {key} must be numeric")
    resolved_value: float = float(value)
    if not 0.0 <= resolved_value <= 1.0:
        _raise_unsupported_options(f"ElevenBytes {key} must be between 0 and 1")
    return resolved_value


def _read_bool_option(options: EngineOptions, key: str, default: bool) -> bool:
    value: str | int | float | bool | None = options.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        _raise_unsupported_options(f"ElevenBytes {key} must be boolean")
    return value


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Select run6 or run7 and a non-empty ElevenBytes voice.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)


def _raise_unsupported_options(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message=message,
        suggestion="Remove unsupported settings or select the run7 endpoint.",
    )
    raise TtsUnsupportedError(context=context)
