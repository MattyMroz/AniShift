"""Choose where to cut one long recording between consecutive spoken lines from frame energy levels."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import groupby, pairwise
from typing import TYPE_CHECKING, Final

from anishift.services.audio.levels import FRAME_MS

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["ENVELOPE_RATE", "CutDecision", "LineSpan", "clip_ranges", "cut_points", "server_frame_times"]

# ── Constants ────────────────────────────────────────────────────────────────

NOISE_DBFS: Final[float] = -35.0
"""Frame level below which a frame counts as a pause, breaths included."""

MIN_SILENCE_MS: Final[float] = 80.0
"""Shortest pause that may end a line closed by a sentence mark."""

OPEN_MIN_SILENCE_MS: Final[float] = 150.0
"""Shortest pause that may end a line cut off mid-sentence."""

BEFORE_MS: Final[float] = 600.0
"""How far before the server end of a line the pause search starts."""

AFTER_MS: Final[float] = 900.0
"""How far after the server start of the next line the pause search ends."""

BIAS_MS: Final[float] = 200.0
"""Shift of the anchor past the midpoint of the server gap, which starts lines early."""

DISTANCE_WEIGHT: Final[float] = 0.25
"""Score lost per millisecond between a pause midpoint and the anchor."""

ENVELOPE_RATE: Final[int] = 16_000
"""Sample rate of the mono PCM whose frame levels the rule is tuned on."""


@dataclass(frozen=True, slots=True)
class LineSpan:
    """Server-timeline span of one spoken line and whether it stops mid-sentence."""

    start_ms: float
    end_ms: float
    open_end: bool


@dataclass(frozen=True, slots=True)
class CutDecision:
    """Server time of the cut after one line; uncertain when no pause was long enough."""

    at_ms: float
    uncertain: bool


def server_frame_times(frame_count: int, splices: Sequence[float], frame_ms: float) -> list[float]:
    """Return the server time of every level frame, adding ``frame_ms`` for each splice decoded at or before it."""
    times: list[float] = []
    for index in range(frame_count):
        decoded_ms: float = index * FRAME_MS
        times.append(decoded_ms + frame_ms * bisect_right(splices, decoded_ms))
    return times


def cut_points(levels: Sequence[float], times: Sequence[float], spans: Sequence[LineSpan]) -> list[CutDecision]:
    """Return the cut after every span except the last, choosing the best pause between it and the next."""
    if len(levels) != len(times):
        message: str = "Every level frame needs a server time"
        raise ValueError(message)
    return [_cut(levels, times, line, following) for line, following in pairwise(spans)]


def clip_ranges(cuts: Sequence[CutDecision], times: Sequence[float]) -> list[tuple[float, float]]:
    """Return the server span of every clip: from zero through each cut to the end of the last frame."""
    if not times:
        message: str = "A recording without level frames has no clips"
        raise ValueError(message)
    edges: list[float] = [0.0, *(cut.at_ms for cut in cuts), times[-1] + FRAME_MS]
    return list(pairwise(edges))


def _cut(levels: Sequence[float], times: Sequence[float], line: LineSpan, following: LineSpan) -> CutDecision:
    min_silence_ms: float = OPEN_MIN_SILENCE_MS if line.open_end else MIN_SILENCE_MS
    anchor: float = (line.end_ms + following.start_ms) / 2 + BIAS_MS
    low: float = max(line.end_ms - BEFORE_MS, (line.start_ms + line.end_ms) / 2)
    high: float = min(following.start_ms + AFTER_MS, (following.start_ms + following.end_ms) / 2)
    pauses: list[tuple[float, float]] = [
        (start, end) for start, end in _quiet_runs(levels, times, low, high) if end - start >= min_silence_ms
    ]
    if not pauses:
        return CutDecision(at_ms=min(max(anchor, low), high), uncertain=True)
    start, end = max(pauses, key=lambda pause: _score(pause, anchor))
    return CutDecision(at_ms=(start + end) / 2, uncertain=False)


def _quiet_runs(levels: Sequence[float], times: Sequence[float], low: float, high: float) -> list[tuple[float, float]]:
    window: range = range(bisect_left(times, low), bisect_left(times, high))
    runs: list[tuple[float, float]] = []
    for quiet, group in groupby(window, key=lambda index: levels[index] < NOISE_DBFS):
        frames: list[int] = list(group)
        if quiet:
            runs.append((times[frames[0]], times[frames[-1]] + FRAME_MS))
    return runs


def _score(pause: tuple[float, float], anchor: float) -> float:
    start, end = pause
    return end - start - DISTANCE_WEIGHT * abs((start + end) / 2 - anchor)
