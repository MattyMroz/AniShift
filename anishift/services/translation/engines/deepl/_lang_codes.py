"""DeepL language code mapping."""

from __future__ import annotations

from typing import Final

_OVERRIDES: Final[dict[str, str]] = {
    "en": "EN-US",
    "pt": "PT-PT",
}
"""Codes where DeepL needs a regional variant instead of the bare code."""


def to_deepl_code(code: str) -> str | None:
    """Map a caller-facing language code to DeepL's expected target form."""
    normalized = code.lower()
    if normalized == "auto":
        return None
    if normalized in _OVERRIDES:
        return _OVERRIDES[normalized]
    return normalized.upper()


def to_deepl_source_code(code: str) -> str | None:
    """Map a caller-facing language code to DeepL's expected source form."""
    normalized = code.lower().strip()
    if not normalized or normalized == "auto":
        return None
    return normalized.split("-", 1)[0].upper()


__all__ = ["to_deepl_code", "to_deepl_source_code"]
