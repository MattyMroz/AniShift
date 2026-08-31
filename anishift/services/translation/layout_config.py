"""Text layout limits the translation handler applies to finished subtitles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT
from anishift.services.translation.linebreak import DEFAULT_MAX_CHARS, MAX_LINES

__all__ = ["LayoutConfig"]

# ── Constants ─────────────────────────────────────────────────────────────────

_CHUNK_SPLIT_RATIO: Final[int] = 3
"""Ratio between a packed request and the natural pieces packed into it.

The shipped defaults are 750 characters per request built from pieces of at most
250, so one exposed number keeps that proportion instead of asking the user for
two values that only make sense together.
"""


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    """Line and chunk limits chosen by the user for one run."""

    max_chars_per_line: int = DEFAULT_MAX_CHARS
    max_lines_per_event: int = MAX_LINES
    chunk_chars: int = DEFAULT_CHAR_LIMIT

    def __post_init__(self) -> None:
        """Reject limits that would make the splitters unable to produce output."""
        if self.max_chars_per_line <= 0:
            msg = "Maximum characters per line must be positive"
            raise ValueError(msg)
        if self.max_lines_per_event <= 0:
            msg = "Maximum lines per event must be positive"
            raise ValueError(msg)
        if self.chunk_chars <= 0:
            msg = "Chunk size must be positive"
            raise ValueError(msg)

    @property
    def chunk_pieces(self) -> int:
        """Return the natural piece size packed into one request."""
        return max(self.chunk_chars // _CHUNK_SPLIT_RATIO, 1)
