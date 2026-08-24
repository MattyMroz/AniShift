from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.errors import ErrorCode
from anishift.services.extraction import mp4
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.mp4 import extract_mp4_track
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionTargetFormat,
)
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    ProcessResult,
)


class _WritingRunner:
    def __init__(
        self,
        target: Path,
        *,
        content: bytes = b"subtitle",
        failure: ProcessFailureReason | None = None,
    ) -> None:
        self.target: Path = target
        self.content: bytes = content
        self.failure: ProcessFailureReason | None = failure
        self.calls: list[tuple[tuple[str, ...], CancellationToken, float]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        self.calls.append((command, cancel, timeout_s))
        self.target.write_bytes(self.content)
        if self.failure is not None:
            raise ProcessExecutionError(self.failure)
        return ProcessResult("", "", 0)


def _request(tmp_path: Path, target_format: ExtractionTargetFormat) -> ExtractionRequest:
    suffix = ".srt" if target_format is ExtractionTargetFormat.SRT else ".m4a"
    return ExtractionRequest(
        media_path=tmp_path / "[Group] episode & 01.mp4",
        track_id=2,
        target_format=target_format,
        target_path=tmp_path / f"result{suffix}",
    )


def test_mp4_mov_text_extraction_normalizes_to_srt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path, ExtractionTargetFormat.SRT)
    runner = _WritingRunner(request.target_path)
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    result = extract_mp4_track(
        request,
        cancel=NeverCancelledToken(),
        timeout_s=5.0,
        runner=runner,
    )
    command, _, timeout_s = runner.calls[0]
    assert command[command.index("-map") + 1] == "0:2"
    assert command[command.index("-c:s") : -2] == ("-c:s", "srt", "-f", "srt")
    assert command[command.index("-i") + 1] == str(request.media_path)
    assert command[-1] == str(request.target_path)
    assert timeout_s == 5.0
    assert result.bytes_written == len(b"subtitle")


def test_mp4_audio_extraction_copies_selected_track(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path, ExtractionTargetFormat.AUDIO_COPY)
    runner = _WritingRunner(request.target_path, content=b"audio")
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    extract_mp4_track(request, cancel=NeverCancelledToken(), timeout_s=5.0, runner=runner)
    command = runner.calls[0][0]
    assert command[command.index("-c") : -2] == ("-c", "copy")


def test_mp4_rejects_ass_as_direct_embedded_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExtractionRequest(
        media_path=tmp_path / "episode.mp4",
        track_id=2,
        target_format=ExtractionTargetFormat.ASS,
        target_path=tmp_path / "result.ass",
    )
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    with pytest.raises(ExtractionError, match="requires SRT"):
        extract_mp4_track(
            request,
            cancel=NeverCancelledToken(),
            timeout_s=5.0,
            runner=_WritingRunner(request.target_path),
        )


def test_empty_mp4_output_is_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path, ExtractionTargetFormat.SRT)
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    with pytest.raises(ExtractionError, match="empty output"):
        extract_mp4_track(
            request,
            cancel=NeverCancelledToken(),
            timeout_s=5.0,
            runner=_WritingRunner(request.target_path, content=b""),
        )
    assert request.target_path.exists() is False


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        (ProcessFailureReason.CANCELLED, ErrorCode.CANCELLED),
        (ProcessFailureReason.TIMED_OUT, ErrorCode.TIMEOUT),
        (ProcessFailureReason.NONZERO_EXIT, ErrorCode.EXTRACTION_FAILED),
    ],
)
def test_failed_mp4_extraction_removes_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: ProcessFailureReason,
    code: ErrorCode,
) -> None:
    request = _request(tmp_path, ExtractionTargetFormat.SRT)
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    with pytest.raises(ExtractionError) as raised:
        extract_mp4_track(
            request,
            cancel=NeverCancelledToken(),
            timeout_s=5.0,
            runner=_WritingRunner(request.target_path, failure=reason),
        )
    assert raised.value.context.code is code
    assert request.target_path.exists() is False


def test_extraction_never_replaces_existing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path, ExtractionTargetFormat.SRT)
    request.target_path.write_bytes(b"committed")
    runner = _WritingRunner(request.target_path, content=b"replacement")
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffmpeg.exe"))
    with pytest.raises(ExtractionError, match="already exists"):
        extract_mp4_track(
            request,
            cancel=NeverCancelledToken(),
            timeout_s=5.0,
            runner=runner,
        )
    assert request.target_path.read_bytes() == b"committed"
    assert runner.calls == []
