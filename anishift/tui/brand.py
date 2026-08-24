"""Static ANISHIFT wordmark drawn with a four-row block font.

The wordmark never animates and never changes width: both variants are built
from a fixed glyph table, so the same terminal size always yields the same
render. Colours come from theme variables, never from literals.

Public API:
    LogoVariant: Which wordmark fits the current terminal.
    WORDMARK: Product wordmark rendered by both variants.
    LOGO_ROWS: Row count of the full wordmark.
    LOGO_WIDTH: Cell width of every full-wordmark row.
    BRAND_MUTED_STYLE: Theme variable styling the ``ANI`` half.
    BRAND_ACCENT_STYLE: Theme variable styling the ``SHIFT`` half.
    full_logo_lines: Plain rows of the full wordmark.
    full_logo: Styled four-row wordmark.
    compact_logo: Styled single-row wordmark.
    logo_variant: Pick a variant from terminal dimensions.
    logo_for_size: Render the fitting variant, or nothing.
"""

from __future__ import annotations

from typing import Final, Literal

from textual.content import Content

__all__ = [
    "BRAND_ACCENT_STYLE",
    "BRAND_MUTED_STYLE",
    "COMPACT_LOGO_MIN_HEIGHT",
    "COMPACT_LOGO_MIN_WIDTH",
    "FULL_LOGO_MIN_HEIGHT",
    "FULL_LOGO_MIN_WIDTH",
    "LOGO_ROWS",
    "LOGO_WIDTH",
    "WORDMARK",
    "LogoVariant",
    "compact_logo",
    "full_logo",
    "full_logo_lines",
    "logo_for_size",
    "logo_variant",
]

type LogoVariant = Literal["full", "compact", "hidden"]
"""Wordmark variant that fits the terminal, or ``hidden`` when controls win."""

# ── Constants ──────────────────────────────────────────────────────────────

WORDMARK: Final[str] = "ANISHIFT"
"""Product wordmark rendered by both logo variants."""

_MUTED_PREFIX: Final[str] = "ANI"
"""Leading half of the wordmark rendered in the muted token."""

_GLYPH_GAP: Final[str] = " "
"""Separator inserted between two block glyphs."""

_GLYPH_WIDTH: Final[int] = 4
"""Cell width of every block glyph."""

_GLYPHS: Final[dict[str, tuple[str, str, str, str]]] = {
    "A": ("▄▀▀▄", "█▄▄█", "█  █", "▀  ▀"),
    "F": ("█▀▀▀", "█▄▄ ", "█   ", "▀   "),
    "H": ("█  █", "█▄▄█", "█  █", "▀  ▀"),
    "I": ("▀██▀", " ██ ", " ██ ", "▀▀▀▀"),
    "N": ("█▄ █", "█▀▄█", "█ ▀█", "▀  ▀"),
    "S": ("█▀▀▀", "█▄▄▄", "   █", "▀▀▀▀"),
    "T": ("▀██▀", " ██ ", " ██ ", " ▀▀ "),
}
"""Four-row block glyph for every letter of the wordmark."""

LOGO_ROWS: Final[int] = 4
"""Row count of the full wordmark."""

LOGO_WIDTH: Final[int] = len(WORDMARK) * _GLYPH_WIDTH + (len(WORDMARK) - 1) * len(_GLYPH_GAP)
"""Cell width of every full-wordmark row."""

_SPLIT_COLUMN: Final[int] = len(_MUTED_PREFIX) * (_GLYPH_WIDTH + len(_GLYPH_GAP))
"""Column where the accented ``SHIFT`` half of the full wordmark begins."""

BRAND_MUTED_STYLE: Final[str] = "$text-muted"
"""Theme variable styling the toned-down ``ANI`` half."""

BRAND_ACCENT_STYLE: Final[str] = "$focus"
"""Theme variable styling the highlighted ``SHIFT`` half."""

FULL_LOGO_MIN_WIDTH: Final[int] = 100
"""Terminal width from which the full four-row wordmark is shown."""

FULL_LOGO_MIN_HEIGHT: Final[int] = 30
"""Terminal height from which the full four-row wordmark is shown."""

COMPACT_LOGO_MIN_WIDTH: Final[int] = 40
"""Narrowest terminal that still has room for a wordmark beside the context."""

COMPACT_LOGO_MIN_HEIGHT: Final[int] = 10
"""Shortest terminal that still has room for a wordmark above the controls."""


def full_logo_lines() -> tuple[str, ...]:
    """Return the four plain rows of the block wordmark."""
    return tuple(_GLYPH_GAP.join(_GLYPHS[letter][row] for letter in WORDMARK) for row in range(LOGO_ROWS))


def full_logo() -> Content:
    """Return the four-row wordmark with a muted ``ANI`` and accented ``SHIFT``."""
    return Content("\n").join(
        Content.assemble(
            (line[:_SPLIT_COLUMN], BRAND_MUTED_STYLE),
            (line[_SPLIT_COLUMN:], BRAND_ACCENT_STYLE),
        )
        for line in full_logo_lines()
    )


def compact_logo() -> Content:
    """Return the single-row wordmark used on small terminals."""
    return Content.assemble(
        (_MUTED_PREFIX, BRAND_MUTED_STYLE),
        (WORDMARK.removeprefix(_MUTED_PREFIX), BRAND_ACCENT_STYLE),
    )


def logo_variant(*, width: int, height: int) -> LogoVariant:
    """Pick the wordmark variant that fits a ``width`` x ``height`` terminal.

    Below the compact thresholds the wordmark is dropped entirely: the composer,
    the footer, and the work area always outrank decoration.
    """
    if width >= FULL_LOGO_MIN_WIDTH and height >= FULL_LOGO_MIN_HEIGHT:
        return "full"
    if width >= COMPACT_LOGO_MIN_WIDTH and height >= COMPACT_LOGO_MIN_HEIGHT:
        return "compact"
    return "hidden"


def logo_for_size(*, width: int, height: int) -> Content | None:
    """Render the fitting wordmark, or ``None`` when controls take priority."""
    variant: LogoVariant = logo_variant(width=width, height=height)
    if variant == "full":
        return full_logo()
    if variant == "compact":
        return compact_logo()
    return None
