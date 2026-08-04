"""Provider-neutral TTS service configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsConfigError
from anishift.services.tts.types import EngineOptions

__all__ = ["DEFAULT_RETRY_BACKOFF_SECONDS", "TtsConfig"]

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_RETRY_BACKOFF_SECONDS: Final[tuple[float, ...]] = (15.0, 30.0, 60.0, 120.0)
"""Provider-neutral retry delays capped at two minutes."""


@dataclass(frozen=True, slots=True)
class TtsConfig:
    """Synthesis settings for one TTS service lifecycle."""

    engine_id: str
    provider_model_id: str
    voice_id: str
    max_concurrency: int
    queue_capacity: int
    max_retries: int = 3
    retry_backoff_seconds: tuple[float, ...] = DEFAULT_RETRY_BACKOFF_SECONDS
    request_timeout_s: float = 30.0
    scheduler_timeout_enabled: bool = True
    shutdown_deadline_s: float = 5.0
    native_rate: str | float | None = None
    native_volume: str | float | None = None
    native_pitch: str | float | None = None
    engine_options: EngineOptions = field(default_factory=dict)
    elevenbytes_vpn_enabled: bool = True
    elevenlabs_api_key: str = field(default="", repr=False)
    metadata_cache_root: Path | None = None

    def __post_init__(self) -> None:
        """Validate shared constraints and freeze provider-specific options."""
        if not self.engine_id.strip():
            _raise_config_error("TTS engine id cannot be empty", field_name="engine_id")
        if not self.provider_model_id.strip():
            _raise_config_error(
                "TTS provider model id cannot be empty",
                field_name="provider_model_id",
            )
        if not self.voice_id.strip():
            _raise_config_error("TTS voice id cannot be empty", field_name="voice_id")
        if self.max_concurrency <= 0:
            _raise_config_error(
                "TTS max concurrency must be greater than zero",
                field_name="max_concurrency",
            )
        if self.max_retries < 0:
            _raise_config_error("TTS max retries cannot be negative", field_name="max_retries")
        if not self.retry_backoff_seconds or any(
            not math.isfinite(delay) or delay < 0 for delay in self.retry_backoff_seconds
        ):
            _raise_config_error(
                "TTS retry backoff values must be finite and non-negative",
                field_name="retry_backoff_seconds",
            )
        _validate_positive_finite(self.request_timeout_s, field_name="request_timeout_s")
        _validate_positive_finite(
            self.shutdown_deadline_s,
            field_name="shutdown_deadline_s",
        )
        if self.queue_capacity <= 0:
            _raise_config_error(
                "TTS queue capacity must be greater than zero",
                field_name="queue_capacity",
            )
        frozen_options: EngineOptions = MappingProxyType(dict(self.engine_options))
        object.__setattr__(self, "engine_options", frozen_options)


def _validate_positive_finite(value: float, *, field_name: str) -> None:
    if math.isfinite(value) and value > 0:
        return
    _raise_config_error(
        f"TTS {field_name} must be finite and greater than zero",
        field_name=field_name,
    )


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Check the selected TTS engine, model, voice, and request limits.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)
