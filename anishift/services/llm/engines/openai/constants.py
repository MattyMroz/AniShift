"""Lightweight OpenAI model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "gpt-6-luna",
    "gpt-6-sol",
    "gpt-6-astra",
)
"""Small non-binding list of current general-purpose OpenAI models."""
