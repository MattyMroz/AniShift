from __future__ import annotations

import threading
from concurrent.futures import Future
from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline import discover_inputs, run_pipeline, runner
from anishift.pipeline.runner import _worker_count
from anishift.pipeline.types import FileOutcome, TranslationSettings
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import MediaInfo


class _NullPhase:
    def __enter__(self) -> _NullPhase:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def add_task(self, description: str, *, total: int = 100) -> int:
        return 0

    def update(self, task_id: int, completed: int) -> None:
        return None


def _context(root: Path) -> AppContext:
    return AppContext(Settings(), UserSettings(), root)


def _ts() -> TranslationSettings:
    return TranslationSettings(
        engine="google",
        fallback_chain=("google",),
        batch_size=0,
        max_retries=3,
        deepl_api_key="",
    )


def test_discover_inputs_uses_top_level_natural_order(tmp_path: Path) -> None:
    (tmp_path / "episode 10.mkv").touch()
    (tmp_path / "episode 2.mkv").touch()
    (tmp_path / "episode.displayed.ass").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "episode 1.mkv").touch()

    assert [path.name for path in discover_inputs(tmp_path)] == ["episode 2.mkv", "episode 10.mkv"]


def test_run_pipeline_isolates_identify_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = tmp_path / "bad.mkv"
    good = tmp_path / "good.mkv"
    bad.touch()
    good.touch()

    def fake_identify(path: Path) -> MediaInfo:
        if path == bad:
            context = ErrorContext(code=ErrorCode.EXTRACTION_FAILED, message="bad input")
            raise ExtractionError(context=context)
        return MediaInfo(path, ())

    monkeypatch.setattr("anishift.pipeline.runner.identify", fake_identify)
    report = run_pipeline(_context(tmp_path))

    assert [outcome.source for outcome in report.outcomes] == [bad, good]
    assert report.outcomes[0].status == "failed"
    assert report.outcomes[0].failure is not None
    assert report.outcomes[1].status == "done"


def test_worker_count_scales_with_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: 20)
    assert _worker_count(100) == 6


def test_worker_count_never_exceeds_item_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: 20)
    assert _worker_count(2) == 2


def test_worker_count_is_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: None)
    assert _worker_count(5) == 3


def test_extract_phase_reraises_interrupt_after_cancelling_workers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mkv = tmp_path / "episode.mkv"
    mkv.touch()
    worker_cancel: threading.Event | None = None
    waits = 0

    def fake_extract_mkv(*_: object, cancel: threading.Event, **__: object) -> runner._MkvState:
        nonlocal worker_cancel
        worker_cancel = cancel
        return runner._MkvState(FileOutcome(mkv, "cancelled"), None)

    def interrupted_wait(*_: object, **__: object) -> tuple[set[Future[object]], set[Future[object]]]:
        nonlocal waits
        waits += 1
        if waits == 1:
            raise KeyboardInterrupt
        return set(), set()

    monkeypatch.setattr(runner, "_extract_mkv", fake_extract_mkv)
    monkeypatch.setattr(runner, "wait", interrupted_wait)

    def factory() -> _NullPhase:
        return _NullPhase()

    with pytest.raises(KeyboardInterrupt):
        runner._extract_phase((mkv,), tmp_path, None, factory, threading.Event())

    assert worker_cancel is not None
    assert worker_cancel.is_set()
