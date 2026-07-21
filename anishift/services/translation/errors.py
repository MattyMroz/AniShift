"""Translation domain exception hierarchy (all inherit ``AniShiftError``)."""

from __future__ import annotations

from anishift.errors import AniShiftError, FatalError, TransientError


class TranslationError(AniShiftError):
    """Base class for every translation-domain failure."""


class TranslationEngineError(TranslationError):
    """An engine failed to produce a translation."""


class TranslationConfigError(TranslationError, FatalError):
    """Invalid translation configuration (non-retryable)."""


class TranslationRateLimitError(TranslationError, TransientError):
    """Provider rate-limit hit (HTTP 429/503) - retryable with backoff."""


class TranslationQuotaError(TranslationError, FatalError):
    """Provider character quota exhausted - non-retryable until reset."""


class TranslationAuthError(TranslationError, FatalError):
    """Invalid or missing API key - non-retryable."""


__all__ = [
    "TranslationAuthError",
    "TranslationConfigError",
    "TranslationEngineError",
    "TranslationError",
    "TranslationQuotaError",
    "TranslationRateLimitError",
]
