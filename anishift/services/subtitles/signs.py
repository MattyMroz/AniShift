"""Fuzzy weights for and against the narrator reading an on-screen sign."""

from __future__ import annotations

from typing import Final

from anishift.services.subtitles.fuzzy import fall, nor, rise

__all__ = ["SIGN_AFTER_MS", "SIGN_MARGIN", "place_margin", "static_weights"]

# ── Constants ─────────────────────────────────────────────────────────────────

SIGN_MARGIN: Final[float] = 0.15
"""Smallest lead of the weight for over the weight against at which a sign is read."""

SIGN_AFTER_MS: Final[int] = 3000
"""Longest time after a sign leaves the screen by which its reading must end."""

_HEIGHT_LARGE: Final[tuple[float, float]] = (0.06, 0.10)
"""Line height, as a share of the script height, over which a sign becomes large."""

_HEIGHT_SMALL: Final[tuple[float, float]] = (0.03, 0.05)
"""Line height, as a share of the script height, under which a sign becomes small."""

_ON_SCREEN_MS: Final[tuple[float, float]] = (1500.0, 4000.0)
"""Time on screen over which a sign becomes long lasting."""

_SHORT_READING_MS: Final[tuple[float, float]] = (3000.0, 6000.0)
"""Reading length under which a sign becomes short."""

_LONG_READING_MS: Final[tuple[float, float]] = (5000.0, 8000.0)
"""Reading length over which a sign becomes a wall of text."""

_OVERRUN_MS: Final[tuple[float, float]] = (1000.0, float(SIGN_AFTER_MS))
"""Time a reading runs past the sign over which it becomes late, tolerated up to the first and capped at the second."""

_REPEAT_MS: Final[tuple[float, float]] = (10_000.0, 60_000.0)
"""Time since the same sign was read under which a reading becomes a repeat."""


def static_weights(  # noqa: PLR0913 - one argument per weighed feature
    *, height: float, centre: float, on_screen_ms: int, alone: bool, edge: float, echo: bool, sound: bool
) -> tuple[float, float]:
    """Return the weight for reading a sign and its weight against that do not depend on its reading."""
    weight_for: float = nor(
        0.5 * rise(height, *_HEIGHT_LARGE),
        0.4 * centre,
        0.3 * rise(on_screen_ms, *_ON_SCREEN_MS),
        0.2 * float(alone),
    )
    weight_against: float = nor(
        0.4 * fall(height, *_HEIGHT_SMALL) * edge,
        0.7 * float(echo),
        0.8 * float(sound),
    )
    return weight_for, weight_against


def place_margin(
    static_for: float, static_against: float, *, reading_ms: float, overrun_ms: float, repeat_gap_ms: float | None
) -> float:
    """Return the lead of the weight for over the weight against reading a sign at one place."""
    repeat: float = 0.0 if repeat_gap_ms is None else fall(repeat_gap_ms, *_REPEAT_MS)
    weight_for: float = nor(static_for, 0.5 * fall(reading_ms, *_SHORT_READING_MS))
    weight_against: float = nor(
        static_against,
        0.8 * rise(reading_ms, *_LONG_READING_MS),
        0.6 * rise(overrun_ms, *_OVERRUN_MS),
        0.8 * repeat,
    )
    return weight_for - weight_against
