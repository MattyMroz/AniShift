"""Lightweight Anthropic model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["DEFAULT_MAX_OUTPUT_TOKENS", "SUGGESTED_MODEL_IDS"]

DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 8192
"""Fallback output limit required by the Anthropic Messages API."""

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-opus-5",
)
"""Small non-binding list of current general-purpose Claude models."""
