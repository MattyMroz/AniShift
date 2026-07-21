"""Retry helpers shared by the network translation engines.

No tenacity dependency (``anishift.utils`` is untouchable and tenacity is not a
dependency). Retries a callable on a given exception type with exponential
backoff; the sync variant serves DeepL, the async variant serves the async
googletrans client. Both share the same backoff formula.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


def _backoff_s(attempt: int, base_s: float, cap_s: float) -> float:
    """Return the exponential backoff delay for ``attempt`` capped at ``cap_s``."""
    return min(base_s * (2.0 ** (attempt - 1)), cap_s)


def call_with_retry[T](
    func: Callable[[], T],
    *,
    max_attempts: int,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    base_s: float = 1.0,
    cap_s: float = 15.0,
) -> T:
    """Call ``func`` up to ``max_attempts`` times, backing off on ``retry_on``.

    Uses exponential backoff (``base_s * 2**(attempt-1)``) capped at ``cap_s``.

    Args:
        func: Zero-arg callable to invoke.
        max_attempts: Total number of calls (not extra retries).
        retry_on: Exception type(s) that trigger a retry; anything else raises.
        base_s: Base delay in seconds.
        cap_s: Upper bound on a single wait.

    Returns:
        The value returned by ``func``.

    Raises:
        BaseException: The last ``retry_on`` error when attempts run out, or any
            non-retryable error immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on:
            if attempt >= max_attempts:
                raise
            time.sleep(_backoff_s(attempt, base_s, cap_s))
    msg = "call_with_retry exhausted without returning"  # unreachable: loop returns or re-raises
    raise RuntimeError(msg)


async def call_with_retry_async[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    retry_on: type[BaseException] | tuple[type[BaseException], ...],
    base_s: float = 1.0,
    cap_s: float = 15.0,
) -> T:
    """Await ``func()`` up to ``max_attempts`` times, backing off on ``retry_on``.

    The async twin of :func:`call_with_retry` with identical semantics, for
    engines whose client is async (googletrans).

    Args:
        func: Zero-arg callable returning an awaitable to await.
        max_attempts: Total number of calls (not extra retries).
        retry_on: Exception type(s) that trigger a retry; anything else raises.
        base_s: Base delay in seconds.
        cap_s: Upper bound on a single wait.

    Returns:
        The value returned by ``func``.

    Raises:
        BaseException: The last ``retry_on`` error when attempts run out, or any
            non-retryable error immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except retry_on:
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_s(attempt, base_s, cap_s))
    msg = "call_with_retry_async exhausted without returning"  # unreachable: loop returns or re-raises
    raise RuntimeError(msg)


__all__ = ["call_with_retry", "call_with_retry_async"]
