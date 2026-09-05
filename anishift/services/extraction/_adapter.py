"""Shared safety checks for one-track extraction adapters."""

from __future__ import annotations

from anishift.application.cancellation import CancellationToken
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import ExtractionRequest, ExtractionResult
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    ProcessRunner,
)
from anishift.utils.logger import get_logger

logger = get_logger(__name__)


def execute_extraction(  # noqa: PLR0913 - command and execution policy are separate inputs
    request: ExtractionRequest,
    command: tuple[str, ...],
    *,
    cancel: CancellationToken,
    timeout_s: float,
    runner: ProcessRunner,
    allow_warnings: bool = False,
) -> ExtractionResult:
    """Execute one adapter command and require a new non-empty target."""
    if request.target_path.exists():
        raise _error(
            ErrorCode.IO_ERROR,
            request,
            "Extraction target already exists",
            reason="target_exists",
        )
    warning: bool = False
    try:
        runner.run(command, cancel=cancel, timeout_s=timeout_s)
    except ProcessExecutionError as error:
        warning = allow_warnings and error.reason is ProcessFailureReason.NONZERO_EXIT and error.returncode == 1
        if not warning:
            request.target_path.unlink(missing_ok=True)
            code_by_reason: dict[ProcessFailureReason, ErrorCode] = {
                ProcessFailureReason.START_FAILED: ErrorCode.IO_ERROR,
                ProcessFailureReason.CANCELLED: ErrorCode.CANCELLED,
                ProcessFailureReason.TIMED_OUT: ErrorCode.TIMEOUT,
                ProcessFailureReason.NONZERO_EXIT: ErrorCode.EXTRACTION_FAILED,
            }
            raise _error(
                code_by_reason[error.reason],
                request,
                "Embedded track extraction failed",
                reason=error.reason.value,
                returncode=error.returncode,
            ) from error
    _raise_if_cancelled(request, cancel)
    try:
        size: int = request.target_path.stat().st_size
    except OSError as error:
        request.target_path.unlink(missing_ok=True)
        raise _error(
            ErrorCode.EXTRACTION_FAILED,
            request,
            "Extraction completed without a readable output",
            reason="missing_output",
        ) from error
    if size <= 0:
        request.target_path.unlink(missing_ok=True)
        raise _error(
            ErrorCode.EXTRACTION_FAILED,
            request,
            "Extraction completed with an empty output",
            reason="empty_output",
        )
    if warning:
        logger.warning(
            "Track extraction completed with warnings", source=request.media_path.name, track_id=request.track_id
        )
    _raise_if_cancelled(request, cancel)
    return ExtractionResult(
        media_path=request.media_path,
        track_id=request.track_id,
        target_format=request.target_format,
        target_path=request.target_path,
        bytes_written=size,
    )


def _raise_if_cancelled(request: ExtractionRequest, cancel: CancellationToken) -> None:
    """Discard the new target when cancellation wins before result delivery."""
    if not cancel.is_cancelled():
        return
    request.target_path.unlink(missing_ok=True)
    raise _error(
        ErrorCode.CANCELLED,
        request,
        "Embedded track extraction was cancelled",
        reason=ProcessFailureReason.CANCELLED.value,
    )


def _error(
    code: ErrorCode,
    request: ExtractionRequest,
    message: str,
    *,
    reason: str,
    returncode: int | None = None,
) -> ExtractionError:
    return ExtractionError(
        context=ErrorContext(
            code=code,
            message=f"{message}: {request.media_path.name}",
            suggestion="Check the selected track, external tools, and run temp directory.",
            details={
                "operation": "track_extraction",
                "track_id": request.track_id,
                "reason": reason,
                "returncode": returncode,
            },
        )
    )
