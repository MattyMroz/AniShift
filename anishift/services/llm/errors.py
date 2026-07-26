"""LLM domain exception hierarchy."""

from __future__ import annotations

from typing import ClassVar

from anishift.errors import AniShiftError, ErrorCode, ErrorContext, FatalError, TransientError

__all__ = [
    "LlmAuthError",
    "LlmCancelledError",
    "LlmConfigError",
    "LlmContextLengthError",
    "LlmError",
    "LlmModelError",
    "LlmOutputBlockedError",
    "LlmPaymentError",
    "LlmProviderUnavailableError",
    "LlmQuotaError",
    "LlmRateLimitError",
    "LlmRequestError",
    "LlmTimeoutError",
]


class LlmError(AniShiftError):
    """Base class for every LLM-domain failure."""

    error_code: ClassVar[ErrorCode] = ErrorCode.LLM_REQUEST_FAILED

    def __init__(
        self,
        message: str = "",
        *,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize an LLM error with its specific default error code."""
        resolved_context: ErrorContext = context or ErrorContext(
            code=self.error_code,
            message=message,
        )
        super().__init__(message, context=resolved_context)


class LlmConfigError(LlmError, FatalError):
    """Invalid LLM configuration."""

    error_code = ErrorCode.LLM_CONFIG_INVALID


class LlmAuthError(LlmError, FatalError):
    """Missing or rejected provider credentials."""

    error_code = ErrorCode.LLM_AUTH_FAILED


class LlmModelError(LlmError, FatalError):
    """Unknown, unavailable, or unsupported provider model."""

    error_code = ErrorCode.LLM_MODEL_INVALID


class LlmContextLengthError(LlmError, FatalError):
    """Provider context window was exceeded."""

    error_code = ErrorCode.LLM_CONTEXT_EXCEEDED


class LlmOutputBlockedError(LlmError, FatalError):
    """Provider safety policy blocked this completion."""

    error_code = ErrorCode.LLM_OUTPUT_BLOCKED


class LlmQuotaError(LlmError, FatalError):
    """Provider quota was exhausted."""

    error_code = ErrorCode.LLM_QUOTA_EXHAUSTED


class LlmPaymentError(LlmError, FatalError):
    """Provider requires payment or sufficient account credit."""

    error_code = ErrorCode.LLM_PAYMENT_REQUIRED


class LlmRequestError(LlmError, FatalError):
    """The LLM request or response contract is invalid."""

    error_code = ErrorCode.LLM_REQUEST_FAILED


class LlmRateLimitError(LlmError, TransientError):
    """Provider rate limit was reached and the request may be retried."""

    error_code = ErrorCode.LLM_RATE_LIMITED

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float | None = None,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize a rate-limit error with an optional retry delay."""
        self.retry_after_s: float | None = retry_after_s
        super().__init__(message, context=context)


class LlmTimeoutError(LlmError, TransientError):
    """Provider request timed out and may be retried."""

    error_code = ErrorCode.TIMEOUT


class LlmProviderUnavailableError(LlmError, TransientError):
    """Provider is temporarily unavailable."""

    error_code = ErrorCode.LLM_PROVIDER_UNAVAILABLE

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float | None = None,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize an availability error with an optional retry delay."""
        self.retry_after_s: float | None = retry_after_s
        super().__init__(message, context=context)


class LlmCancelledError(LlmError, FatalError):
    """LLM operation was cancelled by the caller."""

    error_code = ErrorCode.CANCELLED
