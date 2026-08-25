"""The static ANISHIFT wordmark, six-row and single-row variants."""

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

BRAND_ACCENT_STYLE: Final[str] = "$primary"
"""Theme variable styling the highlighted ``SHIFT`` half."""

FULL_LOGO_MIN_WIDTH: Final[int] = 100
"""Terminal width from which the full six-row wordmark is shown."""

FULL_LOGO_MIN_HEIGHT: Final[int] = 30
"""Terminal height from which the full six-row wordmark is shown."""

COMPACT_LOGO_MIN_WIDTH: Final[int] = 40
"""Narrowest terminal that still shows the single-row wordmark."""

COMPACT_LOGO_MIN_HEIGHT: Final[int] = 10
"""Shortest terminal that still shows the single-row wordmark."""


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


def compact_logo() -> Content:
    """Return the single-row wordmark used on small terminals."""
    return Content.assemble(
        (_MUTED_PREFIX, BRAND_MUTED_STYLE),
        (WORDMARK.removeprefix(_MUTED_PREFIX), BRAND_ACCENT_STYLE),
    )


def logo_variant(*, width: int, height: int) -> LogoVariant:
    """Pick the wordmark variant that fits a ``width`` x ``height`` terminal."""
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
