"""The static ANISHIFT wordmark, six-row and single-row variants."""

from __future__ import annotations

from typing import Final, Literal

from textual.content import Content

__all__ = [
    "BRAND_ACCENT_STYLE",
    "BRAND_MUTED_STYLE",
    "LOGO_MIN_HEIGHT",
    "LOGO_MIN_WIDTH",
    "LOGO_ROWS",
    "LOGO_WIDTH",
    "WORDMARK",
    "LogoVariant",
    "full_logo",
    "full_logo_lines",
    "logo_for_size",
    "logo_variant",
]

type LogoVariant = Literal["full", "hidden"]
"""Wordmark variant the terminal shows: the block wordmark, or nothing at all."""

# ── Constants ──────────────────────────────────────────────────────────────

WORDMARK: Final[str] = "ANISHIFT"
"""Product wordmark rendered by both logo variants."""

_MUTED_PREFIX: Final[str] = "ANI"
"""Leading half of the wordmark rendered in the muted token."""

_FULL_LOGO_ROWS: Final[tuple[str, ...]] = (
    " █████╗ ███╗   ██╗██╗███████╗██╗  ██╗██╗███████╗████████╗",
    "██╔══██╗████╗  ██║██║██╔════╝██║  ██║██║██╔════╝╚══██╔══╝",
    "███████║██╔██╗ ██║██║███████╗███████║██║█████╗     ██║   ",
    "██╔══██║██║╚██╗██║██║╚════██║██╔══██║██║██╔══╝     ██║   ",
    "██║  ██║██║ ╚████║██║███████║██║  ██║██║██║        ██║   ",
    "╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   ",
)
"""Full block wordmark, one entry per row, every row the same cell width."""

LOGO_ROWS: Final[int] = len(_FULL_LOGO_ROWS)
"""Row count of the full wordmark."""

LOGO_WIDTH: Final[int] = len(_FULL_LOGO_ROWS[0])
"""Cell width of every full-wordmark row."""

_SPLIT_COLUMN: Final[int] = 21
"""Column where the accented ``SHIFT`` half of the full wordmark begins."""

BRAND_MUTED_STYLE: Final[str] = "$text-muted"
"""Theme variable styling the toned-down ``ANI`` half."""

BRAND_ACCENT_STYLE: Final[str] = "$text"
"""Theme variable styling the highlighted ``SHIFT`` half."""

LOGO_MIN_HEIGHT: Final[int] = 20
"""Terminal height below which the controls take the rows the wordmark wants."""

LOGO_MIN_WIDTH: Final[int] = LOGO_WIDTH
"""Terminal width below which the wordmark leaves rather than wrap or lose glyphs."""


def full_logo_lines() -> tuple[str, ...]:
    """Return the six plain rows of the block wordmark."""
    return _FULL_LOGO_ROWS


def full_logo() -> Content:
    """Return the six-row wordmark with a muted ``ANI`` and accented ``SHIFT``."""
    return Content("\n").join(
        Content.assemble(
            (line[:_SPLIT_COLUMN], BRAND_MUTED_STYLE),
            (line[_SPLIT_COLUMN:], BRAND_ACCENT_STYLE),
        )
        for line in full_logo_lines()
    )


def logo_variant(*, width: int, height: int) -> LogoVariant:
    """Pick the wordmark a ``width`` x ``height`` terminal shows: the whole one, or none."""
    if width < LOGO_MIN_WIDTH or height < LOGO_MIN_HEIGHT:
        return "hidden"
    return "full"


def logo_for_size(*, width: int, height: int) -> Content | None:
    """Render the wordmark at its one size, or ``None`` when controls take the rows."""
    if logo_variant(width=width, height=height) == "full":
        return full_logo()
    return None
