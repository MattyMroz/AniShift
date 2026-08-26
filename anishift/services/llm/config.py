"""LLM service configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import LlmConfigError
from anishift.services.llm.wire_protocol import ModelProtocol

__all__ = ["LlmConfig"]

MAX_TEMPERATURE: Final[float] = 2.0
"""Maximum provider-independent sampling temperature."""


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Provider and generation settings for one LLM service lifecycle."""

    engine_id: str
    provider_model_id: str
    api_key: str = field(default="", repr=False)
    base_url: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_s: float = 60.0
    max_retries: int = 2
    alias: str = ""
    provider_id: str = ""
    protocol: ModelProtocol | None = None

    def __post_init__(self) -> None:
        """Validate provider-independent configuration constraints."""
        if not self.engine_id.strip():
            _raise_config_error("LLM engine id cannot be empty", field_name="engine_id")
        if not self.provider_model_id.strip():
            _raise_config_error("LLM provider model id cannot be empty", field_name="provider_model_id")
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            _raise_config_error("LLM timeout must be finite and greater than zero", field_name="timeout_s")
        if self.max_retries < 0:
            _raise_config_error("LLM max retries cannot be negative", field_name="max_retries")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            _raise_config_error(
                "LLM max output tokens must be greater than zero",
                field_name="max_output_tokens",
            )
        if self.temperature is not None and not 0 <= self.temperature <= MAX_TEMPERATURE:
            _raise_config_error(
                "LLM temperature must be between 0 and 2",
                field_name="temperature",
            )
        if self.top_p is not None and not 0 <= self.top_p <= 1:
            _raise_config_error("LLM top-p must be between 0 and 1", field_name="top_p")


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_CONFIG_INVALID,
        message=message,
        suggestion="Check the selected LLM provider, model, and generation settings.",
        details={"field": field_name},
    )
    raise LlmConfigError(context=context)
