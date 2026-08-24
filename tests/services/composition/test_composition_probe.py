from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken
from anishift.services.composition.errors import CompositionCancelledError, CompositionValidationError
from anishift.services.composition.probe import source_duration_us, validate_merged
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
