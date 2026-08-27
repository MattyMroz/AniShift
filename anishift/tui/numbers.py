"""The one text form every surface gives to a number it shows."""

from __future__ import annotations

from typing import Final

__all__ = [
    "SIGNIFICANT_DIGITS",
    "number_text",
]

# ── Constants ──────────────────────────────────────────────────────────────

SIGNIFICANT_DIGITS: Final[int] = 12
"""Digits a number keeps before the noise of binary storage begins."""


def number_text(value: int | float) -> str:
    """Return the plain decimal text of one number, free of storage artifacts."""
    if isinstance(value, int):
        return str(int(value))
    shortened: float = float(f"{value:.{SIGNIFICANT_DIGITS}g}")
    if shortened.is_integer():
        return str(int(shortened))
    return format(shortened, "f").rstrip("0")
