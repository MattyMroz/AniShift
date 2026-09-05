"""Google engine constants."""

from __future__ import annotations

from typing import Final

from anishift.services.translation.chunking import ZERO_WIDTH

BASE_URL: Final[str] = "https://translate.google.com/m"
"""Free Google Translate mobile page; the JSON endpoint now answers 429."""

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
"""Browser User-Agent; Google serves the page without a result to other clients."""

REQUEST_TIMEOUT_S: Final[float] = 20.0
"""Per-request timeout for one mobile page fetch."""

MAX_CHARS_PER_REQUEST: Final[int] = 15000
"""Google Translate hard limit per request (~15000 chars); SSOT of this limit."""

RETRY_BACKOFF_BASE_S: Final[float] = 2.0
"""Base seconds for the shared exponential backoff on transient errors."""

RETRY_MAX_WAIT_S: Final[float] = 5.0
"""Cap on a single backoff wait."""

LINE_SEPARATOR: Final[str] = f"{ZERO_WIDTH}###{ZERO_WIDTH}"
"""Marker joining lines within one batched request."""


__all__ = [
    "BASE_URL",
    "LINE_SEPARATOR",
    "MAX_CHARS_PER_REQUEST",
    "REQUEST_TIMEOUT_S",
    "RETRY_BACKOFF_BASE_S",
    "RETRY_MAX_WAIT_S",
    "USER_AGENT",
]
