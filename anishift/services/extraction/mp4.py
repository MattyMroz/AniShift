"""Single-track MP4 extraction and subtitle normalization adapter."""

from __future__ import annotations

from pathlib import Path

from anishift.application.cancellation import CancellationToken
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, require_binary
from anishift.services.extraction._adapter import execute_extraction
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionTargetFormat,
)
from anishift.services.media._process import ProcessRunner


def extract_mp4_track(
    request: ExtractionRequest,
    *,
    cancel: CancellationToken,
    timeout_s: float,
    runner: ProcessRunner,
) -> ExtractionResult:
    """Extract one MP4 track, normalizing text subtitles to SubRip."""
    executable: Path = require_binary(Binary.FFMPEG)
    output_args: tuple[str, ...] = _output_args(request)
    command: tuple[str, ...] = (
        str(executable),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(request.media_path),
        "-map",
        f"0:{request.track_id}",
        *output_args,
        "-y",
        str(request.target_path),
    )
    return execute_extraction(
        request,
        command,
        cancel=cancel,
        timeout_s=timeout_s,
        runner=runner,
    )


def _output_args(request: ExtractionRequest) -> tuple[str, ...]:
    if request.target_format is ExtractionTargetFormat.SRT:
        return "-c:s", "srt", "-f", "srt"
    if request.target_format is ExtractionTargetFormat.AUDIO_COPY:
        return "-c", "copy"
    raise ExtractionError(
        context=ErrorContext(
            code=ErrorCode.EXTRACTION_FAILED,
            message=f"MP4 subtitle extraction requires SRT output: {request.media_path.name}",
            suggestion="Normalize mov_text or tx3g subtitles to SRT.",
            details={"operation": "track_extraction", "target_format": request.target_format.value},
        )
    )
