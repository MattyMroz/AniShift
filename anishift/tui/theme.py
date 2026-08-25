"""Semantic design tokens and the two AniShift themes; the only owner of colours."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from textual.theme import Theme

if TYPE_CHECKING:
    from textual.app import App

__all__ = [
    "DARK_PALETTE",
    "DARK_THEME_ID",
    "DEFAULT_THEME_ID",
    "LIGHT_PALETTE",
    "LIGHT_THEME_ID",
    "THEME_IDS",
    "Palette",
    "anishift_themes",
    "register_themes",
]


@dataclass(frozen=True, slots=True)
class Palette:
    """The twelve semantic colour tokens one AniShift theme is built from."""

    background: str
    surface: str
    elevated: str
    border: str
    focus: str
    text: str
    muted: str
    accent_soft: str
    success: str
    warning: str
    error: str
    info: str


# ── Constants ──────────────────────────────────────────────────────────────

DARK_THEME_ID: Final[str] = "anishift-dark"
"""Stable id of the dark theme."""

LIGHT_THEME_ID: Final[str] = "anishift-light"
"""Stable id of the light theme."""

THEME_IDS: Final[tuple[str, str]] = (DARK_THEME_ID, LIGHT_THEME_ID)
"""The only theme ids AniShift registers, dark first."""

DEFAULT_THEME_ID: Final[str] = DARK_THEME_ID
"""Theme selected when the persisted preference is missing or unknown."""

DARK_PALETTE: Final[Palette] = Palette(
    background="#0B0D10",
    surface="#11141A",
    elevated="#171B22",
    border="#2A303B",
    focus="#7AA2F7",
    text="#E6E9EF",
    muted="#8B93A5",
    accent_soft="#283457",
    success="#9ECE6A",
    warning="#E0AF68",
    error="#F7768E",
    info="#7DCFFF",
)
"""Token values of the dark theme."""

LIGHT_PALETTE: Final[Palette] = Palette(
    background="#F5F7FA",
    surface="#FFFFFF",
    elevated="#EEF1F5",
    border="#CDD3DD",
    focus="#3B6EDC",
    text="#1F2430",
    muted="#667085",
    accent_soft="#DCE7FF",
    success="#2F7D32",
    warning="#9A6700",
    error="#C6283D",
    info="#1F6FA8",
)
"""Token values of the light theme."""


def _theme_variables(palette: Palette) -> dict[str, str]:
    """Pin the semantic CSS variables that Textual would otherwise derive."""
    return {
        "accent-soft": palette.accent_soft,
        "border": palette.border,
        "border-blurred": palette.border,
        "elevated": palette.elevated,
        "focus": palette.focus,
        "info": palette.info,
        "text": palette.text,
        "text-muted": palette.muted,
    }


def _build_theme(theme_id: str, palette: Palette, *, dark: bool) -> Theme:
    """Map one palette onto a Textual theme plus its semantic variables."""
    return Theme(
        name=theme_id,
        primary=palette.focus,
        secondary=palette.accent_soft,
        accent=palette.info,
        foreground=palette.text,
        background=palette.background,
        surface=palette.surface,
        panel=palette.elevated,
        success=palette.success,
        warning=palette.warning,
        error=palette.error,
        dark=dark,
        variables=_theme_variables(palette),
    )


def anishift_themes() -> tuple[Theme, Theme]:
    """Return both AniShift themes in ``THEME_IDS`` order."""
    return (
        _build_theme(DARK_THEME_ID, DARK_PALETTE, dark=True),
        _build_theme(LIGHT_THEME_ID, LIGHT_PALETTE, dark=False),
    )


def register_themes(app: App[Any]) -> None:
    """Register both AniShift themes with ``app``."""
    for theme in anishift_themes():
        app.register_theme(theme)
