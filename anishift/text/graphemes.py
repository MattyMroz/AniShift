"""Unicode extended-grapheme segmentation helpers."""

from __future__ import annotations

from typing import Final

import regex

# ── Constants ─────────────────────────────────────────────────────────────────

_GRAPHEME_PATTERN: Final[regex.Pattern[str]] = regex.compile(r"\X")
"""Unicode extended grapheme cluster pattern."""


def split_graphemes(text: str) -> tuple[str, ...]:
    """Return Unicode extended grapheme clusters in source order."""
    return tuple(_GRAPHEME_PATTERN.findall(text))


def hard_split_graphemes(text: str, limit: int) -> list[str]:
    """Split text to a strict character limit while preserving graphemes when possible."""
    if type(limit) is not int or limit <= 0:
        message: str = "Grapheme split limit must be a positive integer"
        raise ValueError(message)
    if not text:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_length: int = 0
    for grapheme in split_graphemes(text):
        grapheme_length: int = len(grapheme)
        if current and current_length + grapheme_length > limit:
            chunks.append("".join(current))
            current = []
            current_length = 0
        if grapheme_length > limit:
            chunks.extend(grapheme[start : start + limit] for start in range(0, grapheme_length, limit))
            continue
        current.append(grapheme)
        current_length += grapheme_length
    if current:
        chunks.append("".join(current))
    return chunks
