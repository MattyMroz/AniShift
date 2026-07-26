"""Lightweight DeepSeek model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
)
"""Small non-binding list of current official DeepSeek models."""
