"""Speech bounds in short-term energy levels of mono PCM S16 audio."""

from __future__ import annotations

from itertools import pairwise

from anishift.utils.pauses import FRAME_MS

__all__ = ["speech_bounds"]


def speech_bounds(
    levels: list[float], threshold_dbfs: float, *, click_ms: float, pause_ms: float
) -> tuple[int, int] | None:
    """Return the first and last frame index above the threshold past a leading click, or None when no frame is."""
    loud: list[int] = [index for index, level in enumerate(levels) if level > threshold_dbfs]
    if not loud:
        return None
    first: int = 0
    for position, (frame, following) in enumerate(pairwise(loud)):
        if (following - frame - 1) * FRAME_MS < pause_ms:
            continue
        if (frame - loud[first] + 1) * FRAME_MS > click_ms:
            break
        first = position + 1
    return loud[first], loud[-1]
