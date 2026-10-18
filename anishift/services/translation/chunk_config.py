"""Translation request size chosen for one run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from anishift.services.translation.chunking import DEFAULT_CHAR_LIMIT

__all__ = ["ChunkConfig"]

# ── Constants ─────────────────────────────────────────────────────────────────

_CHUNK_SPLIT_RATIO: Final[int] = 3
"""Ratio between a packed request and the natural pieces packed into it."""


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Request size chosen by the user for one run."""

    chunk_chars: int = DEFAULT_CHAR_LIMIT

    def __post_init__(self) -> None:
        """Reject a request size that would make the chunker unable to produce output."""
        if self.chunk_chars <= 0:
            msg = "Chunk size must be positive"
            raise ValueError(msg)

    @property
    def chunk_pieces(self) -> int:
        """Return the natural piece size packed into one request."""
        return max(self.chunk_chars // _CHUNK_SPLIT_RATIO, 1)
