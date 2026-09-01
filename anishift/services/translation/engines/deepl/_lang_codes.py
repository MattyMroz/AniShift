"""DeepL language code mapping.

DeepL uses uppercase codes and needs a regional variant for a few languages
(English, Portuguese). ``auto`` maps to ``None`` because DeepL signals
auto-detect by omitting source_lang.
"""

from __future__ import annotations

from typing import Final

_OVERRIDES: Final[dict[str, str]] = {
    "en": "EN-US",
    "pt": "PT-PT",
}
"""Codes where DeepL needs a regional variant instead of the bare code."""


def to_deepl_code(code: str) -> str | None:
    """Map a caller-facing language code to DeepL's expected target form.

    Args:
        code: Caller code (lowercase ISO, e.g. ``pl``, or ``auto``).

    Returns:
        DeepL code (uppercase, regional variant where required). ``None`` for
        ``auto`` so the caller omits source_lang.
    """
    normalized = code.lower()
    if normalized == "auto":
        return None
    if normalized in _OVERRIDES:
        return _OVERRIDES[normalized]
    return normalized.upper()


def to_deepl_source_code(code: str) -> str | None:
    """Map a caller-facing language code to DeepL's expected source form.

    Args:
        code: Caller code (lowercase ISO, e.g. ``en``, or ``auto``).

    Returns:
        Bare uppercase code, or ``None`` for ``auto`` and for a missing code so
        the caller omits source_lang.

    DeepL requires a regional variant for a few target languages but rejects one
    for the source, so ``en`` must travel as ``EN`` and never as ``EN-US``.
    """
    normalized = code.lower().strip()
    if not normalized or normalized == "auto":
        return None
    return normalized.split("-", 1)[0].upper()


__all__ = ["to_deepl_code", "to_deepl_source_code"]
