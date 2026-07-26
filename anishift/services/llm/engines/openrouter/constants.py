"""Lightweight OpenRouter model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "google/gemini-3.1-flash-lite",
    "anthropic/claude-sonnet-5",
    "openai/gpt-5.4-mini",
)
"""Small non-binding list of popular general-purpose OpenRouter model slugs."""
