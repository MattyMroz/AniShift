"""Lightweight custom OpenAI-compatible model suggestions."""

from __future__ import annotations

from typing import Final

__all__ = ["SUGGESTED_MODEL_IDS"]

SUGGESTED_MODEL_IDS: Final[tuple[str, ...]] = ()
"""Custom endpoints intentionally have no model suggestions."""
