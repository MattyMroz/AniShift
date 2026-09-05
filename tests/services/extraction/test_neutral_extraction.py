from __future__ import annotations

from collections.abc import Callable
from os import stat_result
from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, EventCancellationToken, NeverCancelledToken
from anishift.errors import ErrorCode
from anishift.services.extraction import mkv, mp4
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.service import ExtractionService
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionTargetFormat,
)
from anishift.services.media._process import ProcessExecutionError, ProcessFailureReason, ProcessResult


class _WritingRunner:
    def __init__(
        self,
        target: Path,
        *,
        returncode: int = 0,
        payload: bytes = b"subtitle",
        after_run: Callable[[], None] | None = None,
    ) -> None:
        self.target: Path = target
        self.commands: list[tuple[str, ...]] = []
        self.returncode: int = returncode
        self.payload: bytes = payload
        self.after_run: Callable[[], None] | None = after_run

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        self.commands.append(command)
        self.target.write_bytes(self.payload)
        if self.after_run is not None:
            self.after_run()
        if self.returncode:
            raise ProcessExecutionError(ProcessFailureReason.NONZERO_EXIT, returncode=self.returncode)
        return ProcessResult("", "", 0)


def test_extraction_service_dispatches_mkv_to_exact_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExtractionRequest(
        media_path=tmp_path / "episode.mkv",
        track_id=3,
        target_format=ExtractionTargetFormat.ASS,
        target_path=tmp_path / "run" / "subtitle.ass",
    )
    request.target_path.parent.mkdir()
    runner = _WritingRunner(request.target_path)
    monkeypatch.setattr(mkv, "require_binary", lambda binary: Path("mkvextract.exe"))
    result = ExtractionService(runner=runner).extract(
        request,
        cancel=NeverCancelledToken(),
        timeout_s=6.0,
    )
    command = runner.commands[0]
    assert command[-1] == f"3:{request.target_path}"
    assert result.target_path == request.target_path
    assert result.bytes_written == len(b"subtitle")


@pytest.mark.parametrize(
    ("track_id", "target_name", "message"),
    [(-1, "subtitle.ass", "negative"), (1, "subtitle.srt", "must use .ass")],
)
def test_extraction_request_validates_track_and_target_suffix(
    tmp_path: Path,
    track_id: int,
    target_name: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ExtractionRequest(
            media_path=tmp_path / "episode.mkv",
            track_id=track_id,
            target_format=ExtractionTargetFormat.ASS,
            target_path=tmp_path / target_name,
        )


@pytest.mark.parametrize(
    ("returncode", "payload", "success"), [(1, b"valid", True), (1, b"", False), (2, b"valid", False)]
)
def test_neutral_mkv_accepts_only_valid_warning_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    payload: bytes,
    success: bool,
) -> None:
    request: ExtractionRequest = ExtractionRequest(
        tmp_path / "source.mkv", 2, ExtractionTargetFormat.ASS, tmp_path / "subs.ass"
    )
    runner: _WritingRunner = _WritingRunner(request.target_path, returncode=returncode, payload=payload)
    monkeypatch.setattr(mkv, "require_binary", lambda _: Path("mkvextract.exe"))
    service: ExtractionService = ExtractionService(runner=runner)

    if success:
        result = service.extract(request, cancel=NeverCancelledToken(), timeout_s=1.0)
        assert result.target_path.read_bytes() == payload
    else:
        with pytest.raises(ExtractionError):
            service.extract(request, cancel=NeverCancelledToken(), timeout_s=1.0)
        assert not request.target_path.exists()


@pytest.mark.parametrize("container", ["mkv", "mp4"])
@pytest.mark.parametrize("cancel_at", ["process", "validation"])
def test_neutral_extraction_rejects_late_cancel_and_removes_own_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    container: str,
    cancel_at: str,
) -> None:
    source: Path = tmp_path / f"episode.{container}"
    source.write_bytes(b"original source")
    request: ExtractionRequest = ExtractionRequest(source, 2, ExtractionTargetFormat.SRT, tmp_path / "subtitle.srt")
    token: EventCancellationToken = EventCancellationToken()
    runner: _WritingRunner = _WritingRunner(
        request.target_path, after_run=token.cancel if cancel_at == "process" else None
    )
    original_stat: Callable[..., stat_result] = Path.stat

    def stat(path: Path, *, follow_symlinks: bool = True) -> stat_result:
        result: stat_result = original_stat(path, follow_symlinks=follow_symlinks)
        if path == request.target_path and cancel_at == "validation":
            token.cancel()
        return result

    monkeypatch.setattr(mkv, "require_binary", lambda _: Path("mkvextract.exe"))
    monkeypatch.setattr(mp4, "require_binary", lambda _: Path("ffmpeg.exe"))
    monkeypatch.setattr(Path, "stat", stat)

    with pytest.raises(ExtractionError) as captured:
        ExtractionService(runner=runner).extract(request, cancel=token, timeout_s=1.0)

    assert captured.value.context.code is ErrorCode.CANCELLED
    assert not request.target_path.exists()
    assert source.read_bytes() == b"original source"
