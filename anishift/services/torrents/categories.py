"""Nyaa index categories one release search can be narrowed to."""

from __future__ import annotations

from typing import Final

__all__ = ["CATEGORY_ENGLISH_TRANSLATED", "CATEGORY_NON_ENGLISH_TRANSLATED", "SEARCH_CATEGORIES"]

# ── Constants ─────────────────────────────────────────────────────────────────

CATEGORY_ENGLISH_TRANSLATED: Final[str] = "1_2"
"""Nyaa category identifier for English-translated anime."""

CATEGORY_NON_ENGLISH_TRANSLATED: Final[str] = "1_3"
"""Nyaa category identifier for anime translated into another language."""

SEARCH_CATEGORIES: Final[tuple[str, ...]] = (CATEGORY_ENGLISH_TRANSLATED, CATEGORY_NON_ENGLISH_TRANSLATED)
"""Categories one search covers when the caller names none, English-translated first."""
