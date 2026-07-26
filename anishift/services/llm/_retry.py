"""Retry policy for synchronous LLM completion attempts."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Final

from anishift.errors import AniShiftError, TransientError
from anishift.services.llm.errors import (
    LlmCancelledError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
)
from anishift.services.llm.protocols import LlmAttemptObserver
from anishift.services.llm.types import LlmResponse

__all__ = ["retry_transient"]

RETRY_BACKOFF_CAP_S: Final[float] = 4.0
"""Maximum deterministic delay between LLM completion attempts."""


def retry_transient(
    operation: Callable[[], LlmResponse],
    *,
    max_retries: int,
    observer: LlmAttemptObserver | None = None,
    cancel: threading.Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmResponse:
    """Run an LLM operation and retry only transient domain failures.

    Args:
        operation: One synchronous provider attempt.
        max_retries: Maximum retries after the initial attempt.
        observer: Optional attempt lifecycle observer.
        cancel: Optional cooperative cancellation event.
        sleep: Backoff waiter used when no cancellation event is present.

    Returns:
        The first successful LLM response.

    Raises:
        LlmCancelledError: Cancellation was requested before an attempt or during backoff.
        TransientError: All allowed attempts failed transiently.
    """
    retry_index: int = 0
    while True:
        _raise_if_cancelled(cancel)
        if observer is not None:
            observer.before_attempt()
        try:
            response: LlmResponse = operation()
        except TransientError as error:
            if observer is not None:
                observer.on_transient_failure(error)
            if retry_index >= max_retries:
                raise
            delay_s: float = _retry_delay(error, retry_index)
            retry_index += 1
            _wait(delay_s, cancel=cancel, sleep=sleep)
        except AniShiftError as error:
            if observer is not None:
                observer.on_fatal_failure(error)
            raise
        else:
            if observer is not None:
                observer.on_success()
            return response


def _retry_delay(error: TransientError, retry_index: int) -> float:
    if isinstance(error, (LlmRateLimitError, LlmProviderUnavailableError)):
        retry_after_s: float | None = error.retry_after_s
        if retry_after_s is not None and math.isfinite(retry_after_s) and retry_after_s >= 0:
            return retry_after_s
    return min(2.0**retry_index, RETRY_BACKOFF_CAP_S)


def _wait(
    delay_s: float,
    *,
    cancel: threading.Event | None,
    sleep: Callable[[float], None],
) -> None:
    if cancel is not None:
        if cancel.wait(delay_s):
            message: str = "LLM operation was cancelled"
            raise LlmCancelledError(message)
        return
    sleep(delay_s)


def _raise_if_cancelled(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        message: str = "LLM operation was cancelled"
        raise LlmCancelledError(message)
