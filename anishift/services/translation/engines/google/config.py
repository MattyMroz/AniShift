"""Google engine runtime config."""

from __future__ import annotations

from dataclasses import dataclass

from anishift.services.translation.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RETRIES,
)
from anishift.services.translation.engines.google.constants import MAX_CHARS_PER_REQUEST


@dataclass(slots=True)
class GoogleConfig:
    """Runtime config for the free Google Translate engine.

    Attributes:
        batch_size: Lines joined per request.
        max_chars_per_request: Character budget per request.
        max_retries: Retry attempts on transient errors.
        concurrency: Concurrent requests per file; kept low as Google
            rate-limits the free endpoint aggressively.
    """

    batch_size: int = DEFAULT_BATCH_SIZE
    max_chars_per_request: int = MAX_CHARS_PER_REQUEST
    max_retries: int = DEFAULT_MAX_RETRIES
    concurrency: int = 1

    def __post_init__(self) -> None:
        """Validate numeric ranges."""
        if self.batch_size < 1:
            msg = f"batch_size must be >= 1, got {self.batch_size}"
            raise ValueError(msg)
        if self.max_chars_per_request < 1:
            msg = f"max_chars_per_request must be >= 1, got {self.max_chars_per_request}"
            raise ValueError(msg)


__all__ = ["GoogleConfig"]
