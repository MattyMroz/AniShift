"""Lightweight OpenAI model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
)
"""Small non-binding list of current general-purpose OpenAI models."""
