"""TTS domain exception hierarchy."""

from __future__ import annotations

from typing import ClassVar

from anishift.errors import AniShiftError, ErrorCode, ErrorContext, FatalError, TransientError

__all__ = [
    "TtsAuthError",
    "TtsCancelledError",
    "TtsClipValidationError",
    "TtsConfigError",
    "TtsError",
    "TtsInputError",
    "TtsNetworkError",
    "TtsProviderUnavailableError",
    "TtsRateLimitError",
    "TtsResumeConflictError",
    "TtsResumeError",
    "TtsResumeSchemaError",
    "TtsTimeoutError",
    "TtsUnsupportedError",
    "TtsVoiceError",
]


class TtsError(AniShiftError):
    """Base class for every TTS-domain failure."""

    error_code: ClassVar[ErrorCode] = ErrorCode.TTS_FAILED

    def __init__(
        self,
        message: str = "",
        *,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialize a TTS error with its specific default error code."""
        resolved_context: ErrorContext = context or ErrorContext(
            code=self.error_code,
            message=message,
        )
        super().__init__(message, context=resolved_context)


class TtsConfigError(TtsError, FatalError):
    """Invalid TTS configuration."""

    error_code = ErrorCode.TTS_CONFIG_INVALID


class TtsAuthError(TtsError, FatalError):
    """Missing or rejected TTS provider credentials."""

    error_code = ErrorCode.TTS_AUTH_FAILED


class TtsVoiceError(TtsError, FatalError):
    """Unknown, unavailable, or incompatible voice."""

    error_code = ErrorCode.TTS_VOICE_INVALID


class TtsInputError(TtsError, FatalError):
    """Invalid text or synthesis request contract."""

    error_code = ErrorCode.TTS_INPUT_INVALID


class TtsUnsupportedError(TtsError, FatalError):
    """Input or capability unsupported by the selected engine."""

    error_code = ErrorCode.TTS_UNSUPPORTED


class TtsResumeError(TtsError, FatalError):
    """Persistent TTS resume state cannot be safely used or updated."""

    error_code = ErrorCode.TTS_RESUME_ERROR


class TtsResumeSchemaError(TtsResumeError):
    """Resume manifest uses a newer unsupported schema."""

    error_code = ErrorCode.TTS_RESUME_SCHEMA


class TtsResumeConflictError(TtsResumeError):
    """Concurrent resume update conflicts with the active generation."""

    error_code = ErrorCode.TTS_RESUME_CONFLICT


class TtsClipValidationError(TtsError, TransientError):
    """Provider output is empty, corrupt, or not decodable."""

    error_code = ErrorCode.TTS_CLIP_INVALID


class TtsCancelledError(TtsError, FatalError):
    """TTS operation cancelled by its caller."""

    error_code = ErrorCode.CANCELLED


class TtsRateLimitError(TtsError, TransientError):
    """Provider rate limit reached."""

    error_code = ErrorCode.TTS_RATE_LIMITED

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


class TtsTimeoutError(TtsError, TransientError):
    """Provider or worker request timed out."""

    error_code = ErrorCode.TTS_TIMEOUT


class TtsNetworkError(TtsError, TransientError):
    """Network transport failed before synthesis completed."""

    error_code = ErrorCode.TTS_NETWORK_ERROR


class TtsProviderUnavailableError(TtsError, TransientError):
    """Provider is temporarily unavailable."""

    error_code = ErrorCode.TTS_ENGINE_UNAVAILABLE

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
