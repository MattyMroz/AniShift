from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken
from anishift.services.composition.errors import CompositionCancelledError, CompositionValidationError
from anishift.services.composition.probe import source_duration_us, validate_burned, validate_merged
from anishift.services.media._process import ProcessExecutionError, ProcessFailureReason, ProcessResult


class _BlockingRunner:
    def __init__(self) -> None:
        self.entered: threading.Event = threading.Event()

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        del command, timeout_s
        self.entered.set()
        while not cancel.is_cancelled():
            time.sleep(0.005)
        raise ProcessExecutionError(ProcessFailureReason.CANCELLED)


class _ProbeRunner:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload: str = json.dumps(payload)

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        del command, cancel, timeout_s
        return ProcessResult(self.payload, "", 0)


@pytest.mark.parametrize(
    "stream",
    [{"duration": "1.000"}, {"duration": "N/A", "tags": {"DURATION": "00:00:01.000000000"}}],
)
def test_video_duration_ignores_longer_container_audio(stream: dict[str, object]) -> None:
    runner: _ProbeRunner = _ProbeRunner({"streams": [stream], "format": {"duration": "4.0"}})

    assert source_duration_us(Path("source.mkv"), ffprobe=Path("ffprobe"), video_only=True, runner=runner) == 1_000_000


def test_unknown_video_duration_is_not_inferred_from_other_streams() -> None:
    runner: _ProbeRunner = _ProbeRunner({"streams": [{}], "format": {"duration": "4.0"}})

    assert source_duration_us(Path("source.mkv"), ffprobe=Path("ffprobe"), video_only=True, runner=runner) == 0


@pytest.mark.parametrize("duration", ["NaN", "Infinity", "1e308", "N/A", "-1", "1:2:3:4"])
def test_invalid_duration_metadata_is_not_a_process_crash(duration: str) -> None:
    runner: _ProbeRunner = _ProbeRunner({"format": {"duration": duration}})

    assert source_duration_us(Path("source.mp4"), ffprobe=Path("ffprobe"), runner=runner) == 0


def test_output_audio_cannot_hide_truncated_video(tmp_path: Path) -> None:
    output: Path = tmp_path / "result.mp4"
    output.write_bytes(b"container")
    runner: _ProbeRunner = _ProbeRunner(
        {
            "streams": [{"codec_type": "video", "duration": "1.0"}],
            "format": {"duration": "10.0"},
        }
    )

    with pytest.raises(CompositionValidationError, match="expected video"):
        validate_burned(
            output,
            expected_duration_us=10_000_000,
            expected_video_duration_us=10_000_000,
            ffprobe=Path("ffprobe"),
            runner=runner,
        )


def test_validate_merged_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(tmp_path / "absent.mkv", expected_track_names=("Napisy PL",))


def test_validate_merged_rejects_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.mkv"
    target.write_bytes(b"")

    with pytest.raises(CompositionValidationError, match="missing or empty"):
        validate_merged(target, expected_track_names=("Napisy PL",))


def test_probe_cancellation_stops_controlled_process_runner(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    source.write_bytes(b"source")
    cancel = threading.Event()
    runner = _BlockingRunner()
    failures: list[CompositionCancelledError] = []

    def probe() -> None:
        try:
            source_duration_us(source, ffprobe=Path("ffprobe"), cancel=cancel, runner=runner)
        except CompositionCancelledError as error:
            failures.append(error)

    worker = threading.Thread(target=probe)
    worker.start()
    assert runner.entered.wait(1.0)
    cancel.set()
    worker.join(1.0)

    assert worker.is_alive() is False
    assert failures[0].context.code.value == "CANCELLED"
