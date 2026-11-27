"""Levels of a recording in 10 ms frames and the best pause between two stretches of speech."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from array import array
    from collections.abc import Sequence

__all__ = ["ENVELOPE_RATE", "FRAME_MS", "NOISE_DBFS", "Span", "best_pause", "frame_levels"]

# ── Constants ─────────────────────────────────────────────────────────────────

FRAME_MS: Final[int] = 10
"""Duration of one level frame in milliseconds."""

ENVELOPE_RATE: Final[int] = 16_000
"""Sample rate of the mono PCM whose frame levels the rule is tuned on."""

NOISE_DBFS: Final[float] = -35.0
"""Frame level below which a frame counts as a pause, breaths included."""

MIN_SILENCE_MS: Final[float] = 80.0
"""Shortest pause that may end a part; parts are separated by a pause paragraph, so they end closed."""

BEFORE_MS: Final[float] = 600.0
"""How far before the server end of a line the pause search starts."""

AFTER_MS: Final[float] = 900.0
"""How far after the server start of the next line the pause search ends."""

BIAS_MS: Final[float] = 200.0
"""Shift of the anchor past the midpoint of the server gap, because the server times lines early."""

DISTANCE_WEIGHT: Final[float] = 0.25
"""Score lost per millisecond between a pause midpoint and the anchor."""

_FULL_SCALE: Final[float] = 32768.0
"""Magnitude of a full-scale signed 16-bit sample."""

_ENERGY_FLOOR: Final[float] = 1e-12
"""Mean-square floor that keeps digital silence finite in dBFS."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""


@dataclass(frozen=True, slots=True)
class Span:
    """Server-timeline span of one stretch of speech."""

    start_ms: float
    end_ms: float


def frame_levels(pcm: array[int]) -> list[float]:
    """Return the RMS level in dBFS of every complete ``FRAME_MS`` frame of mono PCM S16 at ``ENVELOPE_RATE``."""
    size: int = ENVELOPE_RATE * FRAME_MS // _MS_PER_SECOND
    scale: float = _FULL_SCALE * _FULL_SCALE * size
    levels: list[float] = []
    for start in range(0, len(pcm) - size + 1, size):
        frame: array[int] = pcm[start : start + size]
        levels.append(10.0 * math.log10(math.sumprod(frame, frame) / scale + _ENERGY_FLOOR))
    return levels


def best_pause(
    levels: Sequence[float], times: Sequence[float], line: Span, following: Span
) -> tuple[float, float] | None:
    """Return the start and end of the best pause between *line* and *following*, or None when none is long enough."""
    low: float = max(line.end_ms - BEFORE_MS, (line.start_ms + line.end_ms) / 2)
    high: float = min(following.start_ms + AFTER_MS, (following.start_ms + following.end_ms) / 2)
    anchor: float = (line.end_ms + following.start_ms) / 2 + BIAS_MS
    window: range = range(bisect_left(times, low), bisect_left(times, high))
    pauses: list[tuple[float, float]] = []
    for quiet, group in groupby(window, key=lambda index: levels[index] < NOISE_DBFS):
        frames: list[int] = list(group)
        start, end = times[frames[0]], times[frames[-1]] + FRAME_MS
        if quiet and end - start >= MIN_SILENCE_MS:
            pauses.append((start, end))
    if not pauses:
        return None
    return max(
        pauses, key=lambda pause: pause[1] - pause[0] - DISTANCE_WEIGHT * abs((pause[0] + pause[1]) / 2 - anchor)
    )
