"""Semantic design tokens and every AniShift theme; the only owner of colours."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any, Final

from textual.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Iterator

    from textual.app import App

__all__ = [
    "DARK_PALETTE",
    "DARK_THEME_ID",
    "DEFAULT_THEME_ID",
    "LIGHT_PALETTE",
    "LIGHT_THEME_ID",
    "MINIMAL_PALETTE",
    "MINIMAL_THEME_ID",
    "THEME_IDS",
    "Palette",
    "anishift_themes",
    "on_primary",
    "register_themes",
]


@dataclass(frozen=True, slots=True)
class Palette:
    """The fifteen semantic colour tokens one AniShift theme is built from."""

    primary: str
    secondary: str
    accent: str
    error: str
    warning: str
    success: str
    info: str
    text: str
    text_muted: str
    background: str
    background_panel: str
    background_element: str
    border: str
    border_active: str
    border_subtle: str


# ── Constants ──────────────────────────────────────────────────────────────

DARK_THEME_ID: Final[str] = "anishift-dark"
"""Stable id of the dark theme."""

LIGHT_THEME_ID: Final[str] = "anishift-light"
"""Stable id of the light theme."""

MINIMAL_THEME_ID: Final[str] = "anishift-light-minimal"
"""Stable id of the minimal light variant."""

THEME_IDS: Final[tuple[str, str, str]] = (DARK_THEME_ID, LIGHT_THEME_ID, MINIMAL_THEME_ID)
"""The only theme ids AniShift registers, dark first and the canonical pair before the variant."""

DEFAULT_THEME_ID: Final[str] = DARK_THEME_ID
"""Theme selected when the persisted preference is missing or unknown."""

DARK_PALETTE: Final[Palette] = Palette(
    primary="#fab283",
    secondary="#5c9cf5",
    accent="#9d7cd8",
    error="#e06c75",
    warning="#f5a742",
    success="#7fd88f",
    info="#56b6c2",
    text="#eeeeee",
    text_muted="#808080",
    background="#0a0a0a",
    background_panel="#141414",
    background_element="#1e1e1e",
    border="#484848",
    border_active="#606060",
    border_subtle="#3c3c3c",
)
"""Token values of the dark theme."""

LIGHT_PALETTE: Final[Palette] = Palette(
    primary="#3b7dd8",
    secondary="#7b5bb6",
    accent="#d68c27",
    error="#d1383d",
    warning="#d68c27",
    success="#3d9a57",
    info="#318795",
    text="#1a1a1a",
    text_muted="#8a8a8a",
    background="#ffffff",
    background_panel="#fafafa",
    background_element="#f5f5f5",
    border="#b8b8b8",
    border_active="#a0a0a0",
    border_subtle="#d4d4d4",
)
"""Token values of the light theme."""

MINIMAL_PALETTE: Final[Palette] = Palette(
    primary=LIGHT_PALETTE.primary,
    secondary=LIGHT_PALETTE.primary,
    accent=LIGHT_PALETTE.primary,
    error=LIGHT_PALETTE.error,
    warning=LIGHT_PALETTE.warning,
    success=LIGHT_PALETTE.success,
    info=LIGHT_PALETTE.info,
    text=LIGHT_PALETTE.text,
    text_muted=LIGHT_PALETTE.text_muted,
    background=LIGHT_PALETTE.background,
    background_panel=LIGHT_PALETTE.background_panel,
    background_element=LIGHT_PALETTE.background_element,
    border=LIGHT_PALETTE.border,
    border_active=LIGHT_PALETTE.border_active,
    border_subtle=LIGHT_PALETTE.border_subtle,
)
"""Token values of the minimal light variant: the light theme reduced to its single accent."""

_BLACK: Final[str] = "#000000"
"""Text drawn on a selection background bright enough to carry it."""

_WHITE: Final[str] = "#ffffff"
"""Text drawn on a selection background too dark to carry black."""

_LUMINANCE_WEIGHTS: Final[tuple[float, float, float]] = (0.299, 0.587, 0.114)
"""Perceptual weights of red, green and blue in the luminance of a colour."""

_MID_LUMINANCE: Final[float] = 0.5
"""Luminance above which a background needs black rather than white text."""

_CHANNEL_MAX: Final[float] = 255.0
"""Largest value one colour channel of a hex triplet can hold."""


def _channels(colour: str) -> Iterator[float]:
    """Yield the three channels of a ``#rrggbb`` string, normalised to 0..1."""
    digits: str = colour.lstrip("#")
    for start in (0, 2, 4):
        yield int(digits[start : start + 2], 16) / _CHANNEL_MAX


def on_primary(palette: Palette) -> str:
    """Return the text colour a selection painted in ``primary`` can carry."""
    channels: Iterator[float] = _channels(palette.primary)
    luminance: float = sum(weight * channel for weight, channel in zip(_LUMINANCE_WEIGHTS, channels, strict=True))
    return _BLACK if luminance > _MID_LUMINANCE else _WHITE


def _theme_variables(palette: Palette) -> dict[str, str]:
    """Pin every palette token as a TCSS variable, plus the derived selection text."""
    variables: dict[str, str] = {
        field.name.replace("_", "-"): getattr(palette, field.name) for field in fields(palette)
    }
    variables["border-blurred"] = palette.border
    variables["on-primary"] = on_primary(palette)
    return variables


def _build_theme(theme_id: str, palette: Palette, *, dark: bool) -> Theme:
    """Map one palette onto a Textual theme plus its semantic variables."""
    return Theme(
        name=theme_id,
        primary=palette.primary,
        secondary=palette.secondary,
        accent=palette.accent,
        foreground=palette.text,
        background=palette.background,
        surface=palette.background_panel,
        panel=palette.background_element,
        success=palette.success,
        warning=palette.warning,
        error=palette.error,
        dark=dark,
        variables=_theme_variables(palette),
    )


def anishift_themes() -> tuple[Theme, Theme, Theme]:
    """Return every AniShift theme in ``THEME_IDS`` order."""
    return (
        _build_theme(DARK_THEME_ID, DARK_PALETTE, dark=True),
        _build_theme(LIGHT_THEME_ID, LIGHT_PALETTE, dark=False),
        _build_theme(MINIMAL_THEME_ID, MINIMAL_PALETTE, dark=False),
    )


def register_themes(app: App[Any]) -> None:
    """Register every AniShift theme with ``app``."""
    for theme in anishift_themes():
        app.register_theme(theme)
