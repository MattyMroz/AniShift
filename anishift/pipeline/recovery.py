"""Shared user-decision contract for recoverable pipeline domains."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from anishift.errors import AniShiftError, ErrorCode, ErrorContext

__all__ = [
    "RecoveryAction",
    "RecoveryContext",
    "RecoveryDomain",
    "RecoveryHandler",
    "rebuild_error_context",
]


class RecoveryAction(StrEnum):
    """Explicit action selected after recoverable work has drained."""

    RETRY = "retry"
    SETTINGS = "settings"
    FINISH = "finish"


class RecoveryDomain(StrEnum):
    """Pipeline domain whose queue requires a user decision."""

    LLM = "llm"
    TTS = "tts"


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """Describe preserved and waiting files at one recovery boundary."""

    domain: RecoveryDomain
    error: ErrorContext
    completed_files: tuple[Path, ...]
    failed_files: tuple[Path, ...]
    pending_files: tuple[Path, ...]


type RecoveryHandler = Callable[[RecoveryContext], RecoveryAction]
"""Choose how one drained recoverable queue should continue."""


def rebuild_error_context(
    error: AniShiftError | OSError | RuntimeError | ValueError,
    domain: RecoveryDomain,
) -> ErrorContext:
    """Describe a provider rebuild failure for another recovery decision."""
    if isinstance(error, AniShiftError):
        return error.context
    code: ErrorCode
    if isinstance(error, OSError):
        code = ErrorCode.IO_ERROR
    elif domain is RecoveryDomain.LLM:
        code = ErrorCode.LLM_CONFIG_INVALID
    else:
        code = ErrorCode.TTS_CONFIG_INVALID
    message: str = str(error) or f"{domain.value.upper()} configuration could not be applied"
    return ErrorContext(
        code=code,
        message=message,
        suggestion="Open settings and correct the provider configuration, or finish with completed files.",
    )
