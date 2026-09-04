"""Brand palette measured on the mascot and shared by every interactive view."""

from __future__ import annotations

from typing import Final

from rich.theme import Theme

__all__ = [
    "BRAND_THEME",
    "MASCOT_AZURE",
    "MASCOT_RED",
    "MASCOT_VIOLET",
    "hex_color",
    "mix",
    "rim_color",
]

# ── Constants ─────────────────────────────────────────────────────────────────

MASCOT_AZURE: Final[tuple[int, int, int]] = (0x00, 0x62, 0xFA)
"""Azure measured on the mascot's left rim, where the brand gradient starts."""

MASCOT_VIOLET: Final[tuple[int, int, int]] = (0x4C, 0x03, 0xD9)
"""Violet measured inside the mascot, which the brand gradient passes through."""

MASCOT_RED: Final[tuple[int, int, int]] = (0xF9, 0x01, 0x1A)
"""Red measured on the mascot's right rim, where the brand gradient ends."""

_GRADIENT_MIDPOINT: Final[float] = 0.5
"""Position where the brand gradient passes through the mascot's violet body."""


def hex_color(color: tuple[int, int, int]) -> str:
    """Format one color as a Rich hex style."""
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def mix(start: tuple[int, int, int], end: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    """Blend two colors by a normalized weight."""
    return (
        round(start[0] + (end[0] - start[0]) * weight),
        round(start[1] + (end[1] - start[1]) * weight),
        round(start[2] + (end[2] - start[2]) * weight),
    )


def rim_color(position: float) -> tuple[int, int, int]:
    """Read the brand gradient, azure through violet to red, at one position."""
    clamped: float = min(max(position, 0.0), 1.0)
    if clamped <= _GRADIENT_MIDPOINT:
        return mix(MASCOT_AZURE, MASCOT_VIOLET, clamped / _GRADIENT_MIDPOINT)
    return mix(MASCOT_VIOLET, MASCOT_RED, (clamped - _GRADIENT_MIDPOINT) / (1.0 - _GRADIENT_MIDPOINT))


BRAND_THEME: Final[Theme] = Theme(
    {
        "brand_accent": f"{hex_color(mix(MASCOT_AZURE, (255, 255, 255), 0.35))} bold",
        "gray": "#8892ad",
        "white_bold": "#e2e7f5 bold",
        "progress_track": "#303a54",
    },
)
"""Accent style every interactive view uses on top of the shared Rich theme."""
