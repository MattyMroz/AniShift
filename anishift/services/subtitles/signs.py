"""Fuzzy weights for and against the narrator reading an on-screen sign."""

from __future__ import annotations

from typing import Final

from anishift.services.subtitles.fuzzy import fall, nor, rise

__all__ = ["SIGN_AFTER_MS", "SIGN_MARGIN", "place_weight_against", "static_weights"]

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

_FEW_WORDS: Final[tuple[float, float]] = (4.0, 12.0)
"""Word count under which a sign becomes brief."""

_MANY_WORDS: Final[tuple[float, float]] = (8.0, 20.0)
"""Word count over which a sign becomes long."""

_TIGHT_SLACK: Final[tuple[float, float]] = (0.0, 0.5)
"""Free room left after the reading, as a share of its length, under which a pause becomes tight."""

_OVERRUN_MS: Final[tuple[float, float]] = (0.0, 1500.0)
"""Time a reading runs past the sign over which it becomes late."""

_REPEAT_MS: Final[tuple[float, float]] = (10_000.0, 60_000.0)
"""Time since the same sign was read under which a reading becomes a repeat."""


def static_weights(  # noqa: PLR0913 - one argument per weighed feature
    *, height: float, centre: float, on_screen_ms: int, words: int, alone: bool, edge: float, echo: bool
) -> tuple[float, float]:
    """Return the weight for reading a sign and its weight against that do not depend on the pause."""
    weight_for: float = nor(
        0.5 * rise(height, *_HEIGHT_LARGE),
        0.4 * centre,
        0.3 * rise(on_screen_ms, *_ON_SCREEN_MS),
        0.3 * fall(words, *_FEW_WORDS),
        0.2 * float(alone),
    )
    weight_against: float = nor(
        0.4 * rise(words, *_MANY_WORDS),
        0.4 * fall(height, *_HEIGHT_SMALL) * edge,
        0.7 * float(echo),
    )
    return weight_for, weight_against


def place_weight_against(
    static_against: float, *, slack: float, overrun_ms: float, repeat_gap_ms: float | None
) -> float:
    """Return the full weight against reading a sign in one pause, given its static weight against."""
    repeat: float = 0.0 if repeat_gap_ms is None else fall(repeat_gap_ms, *_REPEAT_MS)
    return nor(
        static_against,
        0.6 * fall(slack, *_TIGHT_SLACK),
        0.6 * rise(overrun_ms, *_OVERRUN_MS),
        0.8 * repeat,
    )
