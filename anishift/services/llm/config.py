"""LLM service configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, Literal, Never, get_args

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import LlmConfigError
from anishift.services.llm.wire_protocol import ModelProtocol

__all__ = ["API_KEY_MODES", "DEFAULT_RETRY_WAITS_S", "ApiKeyMode", "LlmConfig"]

# ── Constants ────────────────────────────────────────────────────────────────

type ApiKeyMode = Literal["failover", "rotate"]
"""How several keys of one provider share requests: first key first, or in turn."""

API_KEY_MODES: Final[tuple[ApiKeyMode, ...]] = get_args(ApiKeyMode.__value__)
"""Every accepted way of using several keys of one provider."""

DEFAULT_RETRY_WAITS_S: Final[tuple[float, ...]] = (10.0, 30.0, 60.0, 60.0)
"""Waits between rounds over all keys; one round more than waits is attempted."""

MAX_TEMPERATURE: Final[float] = 2.0
"""Maximum provider-independent sampling temperature."""


@dataclass(frozen=True, slots=True)
class LlmConfig:
    """Provider and generation settings for one LLM service lifecycle."""

    engine_id: str
    provider_model_id: str
    api_keys: tuple[str, ...] = field(default=(), repr=False)
    api_key_mode: ApiKeyMode = "failover"
    base_url: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    timeout_s: float = 300.0
    retry_waits_s: tuple[float, ...] = DEFAULT_RETRY_WAITS_S
    alias: str = ""
    provider_id: str = ""
    protocol: ModelProtocol | None = None
    reasoning_variant: str | None = None
    fallback_origin: str = field(default="", repr=False)
    fallback_api_key: str = field(default="", repr=False)

    @property
    def api_key(self) -> str:
        """Return the key an engine built for this configuration uses: the first one."""
        return self.api_keys[0] if self.api_keys else ""

    def __post_init__(self) -> None:
        """Validate provider-independent configuration constraints."""
        if not self.engine_id.strip():
            _raise_config_error("LLM engine id cannot be empty", field_name="engine_id")
        if not self.provider_model_id.strip():
            _raise_config_error("LLM provider model id cannot be empty", field_name="provider_model_id")
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            _raise_config_error("LLM timeout must be finite and greater than zero", field_name="timeout_s")
        if self.api_key_mode not in API_KEY_MODES:
            _raise_config_error("LLM API key mode must be failover or rotate", field_name="api_key_mode")
        if any(not math.isfinite(wait_s) or wait_s < 0 for wait_s in self.retry_waits_s):
            _raise_config_error("LLM retry waits must be finite and non-negative", field_name="retry_waits_s")
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
        if self.engine_id == "palantir":
            return
        for field_name, configured in (
            ("reasoning_variant", self.reasoning_variant is not None),
            ("fallback_origin", bool(self.fallback_origin)),
            ("fallback_api_key", bool(self.fallback_api_key)),
        ):
            if configured:
                _raise_config_error("LLM setting requires the palantir engine", field_name=field_name)


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_CONFIG_INVALID,
        message=message,
        suggestion="Check the selected LLM provider, model, and generation settings.",
        details={"field": field_name},
    )
    raise LlmConfigError(context=context)
