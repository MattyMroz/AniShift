"""Internal mapping from controlled subprocess failures to media errors."""

from __future__ import annotations

from pathlib import Path

from anishift.errors import ErrorCode, ErrorContext, MediaProbeError
from anishift.services.media._process import ProcessExecutionError, ProcessFailureReason


def process_probe_error(path: Path, tool: str, failure: ProcessExecutionError) -> MediaProbeError:
    """Map one internal process failure to the public media hierarchy."""
    code_by_reason: dict[ProcessFailureReason, ErrorCode] = {
        ProcessFailureReason.START_FAILED: ErrorCode.IO_ERROR,
        ProcessFailureReason.CANCELLED: ErrorCode.CANCELLED,
        ProcessFailureReason.TIMED_OUT: ErrorCode.TIMEOUT,
        ProcessFailureReason.NONZERO_EXIT: ErrorCode.MEDIA_PROBE_FAILED,
    }
    return MediaProbeError(
        context=ErrorContext(
            code=code_by_reason[failure.reason],
            message=f"{tool} could not identify {path.name}",
            suggestion="Check the media file and installed external tools.",
            details={
                "operation": "media_probe",
                "tool": tool,
                "reason": failure.reason.value,
                "returncode": failure.returncode,
            },
        )
    )


def invalid_probe_payload(path: Path, tool: str, cause: BaseException) -> MediaProbeError:
    """Build a public error for malformed identify output."""
    return MediaProbeError(
        context=ErrorContext(
            code=ErrorCode.MEDIA_PROBE_FAILED,
            message=f"{tool} returned invalid metadata for {path.name}",
            suggestion="Check that the media file is complete and readable.",
            details={"operation": "media_probe", "tool": tool},
        )
    )
