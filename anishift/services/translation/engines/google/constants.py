"""Google engine constants."""

from __future__ import annotations

from typing import Final

MAX_CHARS_PER_REQUEST: Final[int] = 15000
"""Google Translate hard limit per request (~15000 chars); SSOT of this limit."""

RETRY_BACKOFF_BASE_S: Final[float] = 2.0
"""Base seconds for capped linear backoff on transient errors."""

RETRY_MAX_WAIT_S: Final[float] = 5.0
"""Cap on a single backoff wait."""

ZERO_WIDTH: Final[str] = chr(0x200B)
"""Zero-width space; building block for join markers Google leaves intact."""

LINE_SEPARATOR: Final[str] = f"{ZERO_WIDTH}###{ZERO_WIDTH}"
"""Marker joining lines within one batched request."""

NEWLINE_MARKER: Final[str] = f"{ZERO_WIDTH}##{ZERO_WIDTH}"
"""Marker standing in for newlines inside a single multi-line line."""


__all__ = [
    "LINE_SEPARATOR",
    "MAX_CHARS_PER_REQUEST",
    "NEWLINE_MARKER",
    "RETRY_BACKOFF_BASE_S",
    "RETRY_MAX_WAIT_S",
    "ZERO_WIDTH",
]
