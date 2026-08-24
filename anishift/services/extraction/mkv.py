"""Single-track Matroska extraction adapter."""

from __future__ import annotations

from pathlib import Path

from anishift.application.cancellation import CancellationToken
from anishift.platform.binaries import Binary, require_binary
from anishift.services.extraction._adapter import execute_extraction
from anishift.services.extraction.types import ExtractionRequest, ExtractionResult
from anishift.services.media._process import ProcessRunner


def extract_mkv_track(
    request: ExtractionRequest,
    *,
    cancel: CancellationToken,
    timeout_s: float,
    runner: ProcessRunner,
) -> ExtractionResult:
    """Extract one Matroska track to the request's exact target path."""
    executable: Path = require_binary(Binary.MKVEXTRACT)
    command: tuple[str, ...] = (
        str(executable),
        "--ui-language",
        "en",
        "--gui-mode",
        str(request.media_path),
        "tracks",
        f"{request.track_id}:{request.target_path}",
    )
    return execute_extraction(
        request,
        command,
        cancel=cancel,
        timeout_s=timeout_s,
        runner=runner,
    )
