"""AniShift base error hierarchy.

3-level hierarchy: AniShiftError -> {Domain}Error -> Specific.
ErrorCode(StrEnum) + ErrorContext for structured error metadata.
TransientError / FatalError mixins for retry dispatch inside engines.

Usage:
    >>> from anishift.errors import AniShiftError, ErrorCode, ErrorContext
    >>> raise AniShiftError(
    ...     context=ErrorContext(
    ...         code=ErrorCode.CONFIG_INVALID,
    ...         message="Unknown engine id",
    ...         suggestion="Pick one of the available engines",
    ...     ),
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "AniShiftError",
    "ErrorCode",
    "ErrorContext",
    "FatalError",
    "TransientError",
]


class ErrorCode(StrEnum):
    """Enumerated error codes across all domains."""

    # Generic
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"

    # Config
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"

    # Input / IO
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    IO_ERROR = "IO_ERROR"

    # Workspace / binaries
    WORKSPACE_NOT_RESOLVED = "WORKSPACE_NOT_RESOLVED"
    BINARY_NOT_FOUND = "BINARY_NOT_FOUND"
    BINARY_HASH_MISMATCH = "BINARY_HASH_MISMATCH"

    # Extraction
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    TRACK_NOT_FOUND = "TRACK_NOT_FOUND"

    # Subtitles
    SUBTITLE_PARSE_FAILED = "SUBTITLE_PARSE_FAILED"

    # Translation
    TRANSLATION_FAILED = "TRANSLATION_FAILED"
    TRANSLATION_ENGINE_ERROR = "TRANSLATION_ENGINE_ERROR"
    TRANSLATION_RATE_LIMITED = "TRANSLATION_RATE_LIMITED"

    # LLM
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    LLM_REQUEST_FAILED = "LLM_REQUEST_FAILED"

    # TTS
    TTS_FAILED = "TTS_FAILED"
    TTS_ENGINE_ERROR = "TTS_ENGINE_ERROR"
    TTS_ENGINE_UNAVAILABLE = "TTS_ENGINE_UNAVAILABLE"

    # Audio
    AUDIO_FAILED = "AUDIO_FAILED"

    # Composition
    COMPOSITION_FAILED = "COMPOSITION_FAILED"

    # Pipeline
    PIPELINE_FAILED = "PIPELINE_FAILED"
    PIPELINE_STEP_FAILED = "PIPELINE_STEP_FAILED"

    # Network / API
    NETWORK_ERROR = "NETWORK_ERROR"
    API_ERROR = "API_ERROR"


@dataclass(frozen=True, slots=True)
class ErrorContext:
    """Structured error metadata — code + message + suggestion + docs link.

    Attributes:
        code: Machine-readable error code from the ErrorCode enum.
        message: Human-readable error description.
        suggestion: Actionable fix suggestion for the user.
        docs_url: Optional link to documentation / troubleshooting page.
        details: Additional key-value context data.
    """

    code: ErrorCode
    message: str
    suggestion: str = ""
    docs_url: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class AniShiftError(Exception):
    """Base exception for all AniShift errors.

    All domain errors inherit from this. Carries a structured ``ErrorContext``
    so callers can programmatically inspect error code, message and suggestion.

    Attributes:
        context: Structured error metadata attached to this exception.
    """

    def __init__(
        self,
        message: str = "",
        *,
        context: ErrorContext | None = None,
    ) -> None:
        """Initialise with an optional plain *message* or structured *context*.

        When *context* is provided but *message* is empty, ``context.message``
        is used as the exception string. When *context* is omitted a default
        ``UNKNOWN`` context is built from *message*.

        Args:
            message: Human-readable error description (may be empty).
            context: Pre-built ``ErrorContext`` with code + suggestion.
        """
        if context and not message:
            message = context.message
        super().__init__(message)
        self.context = context or ErrorContext(
            code=ErrorCode.UNKNOWN,
            message=message,
        )


class TransientError(AniShiftError):
    """Base class for retryable errors (network, rate-limit, timeout).

    Engine retry logic should retry on ``isinstance(err, TransientError)``.
    """


class FatalError(AniShiftError):
    """Base class for non-retryable errors (config, missing binary, bad input).

    These should NOT be retried — they require user intervention.
    """
