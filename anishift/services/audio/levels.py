"""Short-term energy levels of mono PCM S16 audio."""

from __future__ import annotations

import math
from array import array
from typing import Final

__all__ = ["FRAME_MS", "frame_levels", "speech_bounds"]

# ── Constants ────────────────────────────────────────────────────────────────

FRAME_MS: Final[int] = 10
"""Duration of one level frame in milliseconds."""

_FULL_SCALE: Final[float] = 32768.0
"""Magnitude of a full-scale signed 16-bit sample."""

_ENERGY_FLOOR: Final[float] = 1e-12
"""Mean-square floor that keeps digital silence finite in dBFS."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""


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


def speech_bounds(levels: list[float], threshold_dbfs: float) -> tuple[int, int] | None:
    """Return the first and last frame index above the threshold, or None when no frame is."""
    loud: list[int] = [index for index, level in enumerate(levels) if level > threshold_dbfs]
    if not loud:
        return None
    return loud[0], loud[-1]
