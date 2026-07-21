"""DeepL engine constants."""

from __future__ import annotations

from typing import Final

MAX_PAYLOAD_BYTES: Final[int] = 128 * 1024
"""DeepL request payload limit (128 KiB); SSOT of this limit."""

RATE_LIMIT_BASE_DELAY_S: Final[float] = 1.0
"""Base backoff delay for DeepL rate-limit retries."""


__all__ = [
    "MAX_PAYLOAD_BYTES",
    "RATE_LIMIT_BASE_DELAY_S",
]
