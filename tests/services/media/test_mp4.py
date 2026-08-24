from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.errors import MediaProbeError
from anishift.services.media import mp4
from anishift.services.media._process import ProcessResult
from anishift.services.media.mp4 import identify_mp4, parse_mp4_catalog


class _RecordingRunner:
    def __init__(self, stdout: str) -> None:
        self.stdout: str = stdout
        self.calls: list[tuple[tuple[str, ...], CancellationToken, float]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        self.calls.append((command, cancel, timeout_s))
        return ProcessResult(self.stdout, "", 0)


def test_identify_mp4_preserves_safe_path_as_one_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "[Group] episode & 01.mp4"
    payload = '{"streams": [], "format": {"duration": "1"}}'
    runner = _RecordingRunner(payload)
    monkeypatch.setattr(mp4, "require_binary", lambda binary: Path("ffprobe.exe"))
    identify_mp4(media, cancel=NeverCancelledToken(), timeout_s=4.0, runner=runner)
    command, _, timeout_s = runner.calls[0]
    assert command[-1] == str(media)
    assert timeout_s == 4.0


@pytest.mark.parametrize("payload", ["[]", "{}", '{"streams": "bad"}'])
def test_parse_mp4_catalog_rejects_invalid_payload(payload: str) -> None:
    with pytest.raises(MediaProbeError):
        parse_mp4_catalog(Path("episode.mp4"), payload)
