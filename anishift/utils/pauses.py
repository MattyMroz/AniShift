"""Frame energy levels of mono PCM and where to cut a recording between consecutive spoken lines."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import groupby, pairwise
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from array import array
    from collections.abc import Sequence

__all__ = [
    "AFTER_MS",
    "BEFORE_MS",
    "BIAS_MS",
    "DISTANCE_WEIGHT",
    "ENVELOPE_RATE",
    "FRAME_MS",
    "MIN_SILENCE_MS",
    "NOISE_DBFS",
    "OPEN_MIN_SILENCE_MS",
    "SILENT_DBFS",
    "CutDecision",
    "LineSpan",
    "best_pause",
    "clip_ranges",
    "cut_points",
    "frame_levels",
    "server_frame_times",
    "silent_cut",
]

# ── Constants ────────────────────────────────────────────────────────────────

FRAME_MS: Final[int] = 10
"""Duration of one level frame in milliseconds."""

ENVELOPE_RATE: Final[int] = 16_000
"""Sample rate of the mono PCM whose frame levels the rule is tuned on."""

NOISE_DBFS: Final[float] = -35.0
"""Frame level below which a frame counts as a pause, breaths included."""

SILENT_DBFS: Final[float] = -45.0
"""Frame level at or below which a frame inside a pause is silent enough to cut in."""

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

_FULL_SCALE: Final[float] = 32768.0
"""Magnitude of a full-scale signed 16-bit sample."""

_ENERGY_FLOOR: Final[float] = 1e-12
"""Mean-square floor that keeps digital silence finite in dBFS."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""


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


def frame_levels(pcm: array[int], sample_rate: int) -> list[float]:
    """Return the RMS level in dBFS of every complete 10 ms frame."""
    frame_size, remainder = divmod(sample_rate * FRAME_MS, _MS_PER_SECOND)
    if frame_size <= 0 or remainder:
        message: str = "Sample rate must split into whole 10 ms frames"
        raise ValueError(message)
    scale: float = _FULL_SCALE * _FULL_SCALE * frame_size
    levels: list[float] = []
    for start in range(0, len(pcm) - frame_size + 1, frame_size):
        frame: array[int] = pcm[start : start + frame_size]
        levels.append(10.0 * math.log10(math.sumprod(frame, frame) / scale + _ENERGY_FLOOR))
    return levels


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


def best_pause(
    levels: Sequence[float], times: Sequence[float], line: LineSpan, following: LineSpan
) -> tuple[float, float] | None:
    """Return the start and end of the best pause between *line* and *following*, or None when none is long enough."""
    min_silence_ms: float = OPEN_MIN_SILENCE_MS if line.open_end else MIN_SILENCE_MS
    low, high = _window(line, following)
    pauses: list[tuple[float, float]] = [
        (start, end) for start, end in _quiet_runs(levels, times, low, high) if end - start >= min_silence_ms
    ]
    if not pauses:
        return None
    anchor: float = _anchor(line, following)
    return max(pauses, key=lambda pause: _score(pause, anchor))


def silent_cut(levels: Sequence[float], times: Sequence[float], start: float, end: float) -> float:
    """Return the middle of the pause, or of its longest silent run when the middle is still heard."""
    middle: float = (start + end) / 2
    window: range = range(bisect_left(times, start), bisect_left(times, end))
    if levels[max(bisect_right(times, middle) - 1, window.start)] <= SILENT_DBFS:
        return middle
    silent: list[list[int]] = [
        list(group) for heard, group in groupby(window, key=lambda index: levels[index] > SILENT_DBFS) if not heard
    ]
    if not silent:
        return middle
    longest: list[int] = max(silent, key=len)
    return (times[longest[0]] + times[longest[-1]] + FRAME_MS) / 2


def _cut(levels: Sequence[float], times: Sequence[float], line: LineSpan, following: LineSpan) -> CutDecision:
    pause: tuple[float, float] | None = best_pause(levels, times, line, following)
    if pause is None:
        low, high = _window(line, following)
        return CutDecision(at_ms=min(max(_anchor(line, following), low), high), uncertain=True)
    start, end = pause
    return CutDecision(at_ms=silent_cut(levels, times, start, end), uncertain=False)


def _anchor(line: LineSpan, following: LineSpan) -> float:
    return (line.end_ms + following.start_ms) / 2 + BIAS_MS


def _window(line: LineSpan, following: LineSpan) -> tuple[float, float]:
    low: float = max(line.end_ms - BEFORE_MS, (line.start_ms + line.end_ms) / 2)
    high: float = min(following.start_ms + AFTER_MS, (following.start_ms + following.end_ms) / 2)
    return low, high


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
