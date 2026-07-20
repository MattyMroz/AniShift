"""Google engine constants."""

from __future__ import annotations

from typing import Final

from anishift.services.translation.chunking import ZERO_WIDTH

MAX_CHARS_PER_REQUEST: Final[int] = 15000
"""Google Translate hard limit per request (~15000 chars); SSOT of this limit."""

RETRY_BACKOFF_BASE_S: Final[float] = 2.0
"""Base seconds for the shared exponential backoff on transient errors."""

RETRY_MAX_WAIT_S: Final[float] = 5.0
"""Cap on a single backoff wait."""

LINE_SEPARATOR: Final[str] = f"{ZERO_WIDTH}###{ZERO_WIDTH}"
"""Marker joining lines within one batched request."""


__all__ = [
    "LINE_SEPARATOR",
    "MAX_CHARS_PER_REQUEST",
    "RETRY_BACKOFF_BASE_S",
    "RETRY_MAX_WAIT_S",
]
