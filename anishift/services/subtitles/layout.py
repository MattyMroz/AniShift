"""Line limits for laying out translated subtitle events."""

from __future__ import annotations

from dataclasses import dataclass

from anishift.services.subtitles.linebreak import DEFAULT_MAX_CHARS, MAX_LINES

__all__ = ["LayoutLimits"]


@dataclass(frozen=True, slots=True)
class LayoutLimits:
    """Line length and line count chosen by the user for one run."""

    max_chars: int = DEFAULT_MAX_CHARS
    max_lines: int = MAX_LINES

    def __post_init__(self) -> None:
        """Reject limits that would make the line breaker unable to produce output."""
        if self.max_chars <= 0:
            msg = "Maximum characters per line must be positive"
            raise ValueError(msg)
        if self.max_lines <= 0:
            msg = "Maximum lines per event must be positive"
            raise ValueError(msg)
