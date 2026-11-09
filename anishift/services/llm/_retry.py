"""Retry policy for synchronous LLM completion attempts across provider keys."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Final

from anishift.errors import AniShiftError, ErrorContext, TransientError
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmCancelledError,
    LlmError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
)
from anishift.services.llm.protocols import LlmAttemptObserver
from anishift.services.llm.types import LlmResponse
from anishift.utils.logger import get_logger

__all__ = ["retry_across_keys"]

# ── Constants ────────────────────────────────────────────────────────────────

_KEY_REJECTIONS: Final[tuple[type[LlmError], ...]] = (LlmAuthError, LlmQuotaError, LlmPaymentError)
"""Failures that refuse the key itself, so the key is not tried again for this request."""

logger = get_logger(__name__)


def retry_across_keys(  # noqa: PLR0913 - the policy inputs stay explicit at the single call site
    operation: Callable[[int], LlmResponse],
    *,
    provider: str,
    key_count: int,
    waits_s: tuple[float, ...],
    observer: LlmAttemptObserver | None = None,
    cancel: threading.Event | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> LlmResponse:
    """Try every key once per round, wait between rounds, and fail once no round is left."""
    active: list[int] = list(range(key_count))
    max_attempts: int = key_count * (len(waits_s) + 1)
    attempt: int = 0
    last_error: AniShiftError | None = None
    for round_index in range(len(waits_s) + 1):
        if round_index:
            _wait(_round_wait(waits_s[round_index - 1], last_error), cancel=cancel, sleep=sleep)
        for key_index in tuple(active):
            _raise_if_cancelled(cancel)
            attempt += 1
            if observer is not None:
                observer.before_attempt()
            try:
                response: LlmResponse = operation(key_index)
            except AniShiftError as error:
                if not _depends_on_key(error):
                    _record_failure(error, observer=observer, provider=provider)
                    raise
                last_error = error
                if isinstance(error, _KEY_REJECTIONS):
                    active.remove(key_index)
                _report_retry(error, observer=observer, attempt=attempt, max_attempts=max_attempts)
                logger.warning(
                    "LLM provider attempt failed",
                    provider=provider,
                    key=key_index + 1,
                    attempt=attempt,
                    error_type=type(error).__name__,
                    error_code=error.context.code.value,
                )
                continue
            _raise_if_cancelled(cancel)
            if observer is not None:
                observer.on_success()
            return response
        if not active:
            break
    if last_error is None:
        message: str = f"LLM provider {provider!r} has no key to try"
        raise LlmAuthError(message)
    exhausted: AniShiftError = _exhausted_error(last_error, provider=provider, key_count=key_count, attempts=attempt)
    _record_failure(exhausted, observer=observer, provider=provider)
    raise exhausted from last_error


def _depends_on_key(error: AniShiftError) -> bool:
    return isinstance(error, (TransientError, *_KEY_REJECTIONS))


def _report_retry(
    error: AniShiftError,
    *,
    observer: LlmAttemptObserver | None,
    attempt: int,
    max_attempts: int,
) -> None:
    if observer is not None and attempt < max_attempts:
        observer.on_retry(error, attempt=attempt + 1, max_attempts=max_attempts)


def _exhausted_error(error: AniShiftError, *, provider: str, key_count: int, attempts: int) -> AniShiftError:
    noun: str = "key" if key_count == 1 else "keys"
    context: ErrorContext = ErrorContext(
        code=error.context.code,
        message=(
            f"All {key_count} {provider} API {noun} failed after {attempts} attempts; "
            f"last error: {error.context.message}"
        ),
        suggestion=error.context.suggestion,
    )
    if isinstance(error, LlmError):
        return type(error)(context=context)
    return error


def _record_failure(error: AniShiftError, *, observer: LlmAttemptObserver | None, provider: str) -> None:
    if observer is not None:
        observer.on_fatal_failure(error)
    logger.error(
        "LLM provider request failed",
        provider=provider,
        error_type=type(error).__name__,
        error_code=error.context.code.value,
    )


def _round_wait(scheduled_s: float, error: AniShiftError | None) -> float:
    if isinstance(error, (LlmRateLimitError, LlmProviderUnavailableError)):
        retry_after_s: float | None = error.retry_after_s
        if retry_after_s is not None and math.isfinite(retry_after_s) and 0 <= retry_after_s <= scheduled_s:
            return retry_after_s
    return scheduled_s


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
