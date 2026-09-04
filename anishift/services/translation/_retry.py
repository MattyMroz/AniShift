"""Retry helpers shared by the network translation engines."""

from __future__ import annotations

import time
from collections.abc import Callable

from anishift.utils.logger import get_logger

logger = get_logger(__name__)


def _backoff_s(attempt: int, base_s: float, cap_s: float) -> float:
    """Return the exponential backoff delay for ``attempt`` capped at ``cap_s``."""
    return min(base_s * (2.0 ** (attempt - 1)), cap_s)


def call_with_retry[T](  # noqa: PLR0913 - retry policy remains explicit at provider call sites
    func: Callable[[], T],
    *,
    max_attempts: int,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    base_s: float = 1.0,
    cap_s: float = 15.0,
    on_retry: Callable[[int, int], None] | None = None,
) -> T:
    """Call ``func`` up to ``max_attempts`` times, backing off on ``retry_on``."""
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as error:
            if attempt >= max_attempts:
                logger.exception(
                    "Translation provider retries exhausted",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_type=type(error).__name__,
                )
                raise
            delay_s: float = _backoff_s(attempt, base_s, cap_s)
            if on_retry is not None:
                on_retry(attempt + 1, max_attempts)
            logger.warning(
                "Translation provider retry scheduled",
                attempt=attempt,
                max_attempts=max_attempts,
                delay_s=delay_s,
                error_type=type(error).__name__,
            )
            time.sleep(delay_s)
    msg = "call_with_retry exhausted without returning"  # unreachable: loop returns or re-raises
    raise RuntimeError(msg)


__all__ = ["call_with_retry"]
