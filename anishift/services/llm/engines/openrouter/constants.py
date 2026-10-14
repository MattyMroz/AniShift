"""Lightweight OpenRouter model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "openai/gpt-6-luna",
    "deepseek/deepseek-v4.1-flash",
    "google/gemini-3.5-flash-lite",
    "anthropic/claude-haiku-4.5",
)
"""Small non-binding list of popular general-purpose OpenRouter model slugs."""
