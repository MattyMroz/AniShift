"""Lightweight Gemini model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = (
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-pro-preview",
)
"""Small non-binding list of current general-purpose Gemini models."""
