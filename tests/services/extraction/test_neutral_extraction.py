from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.services.extraction import mkv
from anishift.services.extraction.service import ExtractionService
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionTargetFormat,
)
from anishift.services.media._process import ProcessResult


class _WritingRunner:
    def __init__(self, target: Path) -> None:
        self.target: Path = target
        self.commands: list[tuple[str, ...]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        self.commands.append(command)
        self.target.write_bytes(b"subtitle")
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
