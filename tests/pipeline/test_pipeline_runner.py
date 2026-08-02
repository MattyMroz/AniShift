from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest
from pysubs2 import SSAFile

from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline import discover_inputs, run_pipeline, runner
from anishift.pipeline.llm_queue import LlmProgressState, LlmQueueConfig, LlmQueueInput
from anishift.pipeline.narration import NarrationBatch
from anishift.pipeline.recovery import RecoveryAction
from anishift.pipeline.runner import _LlmProgressGate, _worker_count
from anishift.pipeline.tts_queue import TtsQueueOutcome
from anishift.pipeline.types import FileFailure, FileOutcome, TranslationSettings
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import MediaInfo
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.types import SplitStats, SpokenLine, SubtitleSplit
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.services.tts import SpeechBatch


class _NullPhase:
    def __enter__(self) -> _NullPhase:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def add_task(self, description: str, *, total: int = 100) -> int:
        return 0

    def update(self, task_id: int, completed: int) -> None:
        return None


class _NullTtsRuntime:
    def put(self, *_: object, **__: object) -> None:
        return None

    def close_input(self) -> None:
        return None

    def skip(self, source: Path) -> None:
        del source

    def wait(self) -> dict[Path, TtsQueueOutcome]:
        return {}

    def cancel(self) -> None:
        return None

    def close(self) -> None:
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


def test_run_pipeline_uses_supplied_input_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_discovery(workspace_root: Path) -> list[Path]:
        pytest.fail(f"unexpected discovery for {workspace_root}")

    monkeypatch.setattr(runner, "discover_inputs", fail_discovery)

    report = run_pipeline(_context(tmp_path), input_paths=())

    assert report.outcomes == ()


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

    def runtime_factory(*_: object) -> _NullTtsRuntime:
        return _NullTtsRuntime()

    monkeypatch.setattr("anishift.pipeline.runner.identify", fake_identify)
    report = run_pipeline(_context(tmp_path), tts_runtime_factory=runtime_factory)

    assert [outcome.source for outcome in report.outcomes] == [bad, good]
    assert report.outcomes[0].status == "failed"
    assert report.outcomes[0].failure is not None
    assert report.outcomes[1].status == "done"


def test_strict_pipeline_resolves_failed_extraction_before_later_translation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failed = tmp_path / "episode 1.mkv"
    later = tmp_path / "episode 2.mkv"
    failed.touch()
    later.touch()
    failed_outcome = FileOutcome(
        failed,
        "failed",
        failure=FileFailure("write", ErrorCode.PIPELINE_STEP_FAILED.value, "bad timing", ""),
    )
    states = {
        failed: runner._MkvState(failed_outcome, None, source_rank=0),
        later: runner._MkvState(FileOutcome(later, "done"), cast("SubtitleSplit", object()), source_rank=1),
    }
    translated: list[Path] = []
    skipped_tts: list[Path] = []

    class _RecordingRuntime(_NullTtsRuntime):
        def skip(self, source: Path) -> None:
            skipped_tts.append(source)

    def runtime_factory(*_: object) -> _RecordingRuntime:
        return _RecordingRuntime()

    def fake_extract_phase(
        *_: object,
        on_complete: object,
        **__: object,
    ) -> dict[Path, runner._MkvState]:
        callback = cast("Callable[[Path, runner._MkvState], None]", on_complete)
        callback(failed, states[failed])
        callback(later, states[later])
        return states

    def fake_translate_inputs(
        ready_paths: object,
        *_: object,
        **__: object,
    ) -> dict[Path, FileOutcome]:
        queue_input = cast("LlmQueueInput", ready_paths)
        while True:
            ready, closed = queue_input.drain()
            translated.extend(ready)
            if closed:
                break
            queue_input.wait()
        return {}

    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(
            processing_order_policy="strict_natural",
            translation_engine="llm",
        ),
        tmp_path,
    )
    monkeypatch.setattr(runner, "_extract_phase", fake_extract_phase)
    monkeypatch.setattr(runner, "_translate_llm_inputs", fake_translate_inputs)

    run_pipeline(context, tts_runtime_factory=runtime_factory)

    assert translated == [later]
    assert skipped_tts == [failed]


def test_worker_count_scales_with_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: 20)
    assert _worker_count(100) == 6


def test_worker_count_never_exceeds_item_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: 20)
    assert _worker_count(2) == 2


def test_worker_count_is_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("anishift.pipeline.runner.os.cpu_count", lambda: None)
    assert _worker_count(5) == 3


def test_translation_settings_routes_llm_preferences_and_env_secrets(
    tmp_path: Path,
) -> None:
    context = AppContext(
        Settings(
            gemini_api_key="gemini-secret",
            openrouter_api_key="router-secret",
        ),
        UserSettings(
            translation_engine="llm",
            llm_provider="gemini",
            llm_provider_model_id="gemini-model",
            llm_max_concurrency=4,
        ),
        tmp_path,
    )
    settings = runner._translation_settings(context)
    assert settings.llm is not None
    assert settings.llm.provider == "gemini"
    assert settings.llm.model == "gemini-model"
    assert settings.llm.api_key() == "gemini-secret"
    assert settings.fallback_chain == ()
    assert "gemini-secret" not in repr(settings.llm)
    assert "router-secret" not in repr(settings.llm)


def test_strict_llm_queue_respects_configured_concurrency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: LlmQueueConfig | None = None

    def fake_run_llm_queue(
        *_: object,
        config: LlmQueueConfig,
        **__: object,
    ) -> dict[Path, FileOutcome]:
        nonlocal captured
        captured = config
        return {}

    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(
            translation_engine="llm",
            processing_order_policy="strict_natural",
            llm_max_concurrency=4,
        ),
        tmp_path,
    )
    monkeypatch.setattr("anishift.pipeline.llm_queue.run_llm_queue", fake_run_llm_queue)

    runner._translate_llm_inputs((), {}, context, threading.Event())

    assert captured is not None
    assert captured.configured_limit() == 4
    assert captured.stop_on_failure


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


def test_llm_queue_isolates_mkv_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bad = tmp_path / "episode1.mkv"
    good = tmp_path / "episode2.mkv"
    states = {
        bad: runner._MkvState(FileOutcome(bad, "done"), cast("SubtitleSplit", object())),
        good: runner._MkvState(FileOutcome(good, "done"), cast("SubtitleSplit", object())),
    }
    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(translation_engine="llm"),
        tmp_path,
    )
    published: list[Path] = []

    class _FakeRuntime:
        def __init__(self, *_: object, **__: object) -> None:
            self.records: list[object] = []

        def __enter__(self) -> _FakeRuntime:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def engine_factory(self) -> None:
            return None

    def fake_translate(
        path: Path,
        state: runner._MkvState,
        *_: object,
        on_spoken_ready: runner.SpokenReadyHandler | None,
        **__: object,
    ) -> None:
        if path == bad:
            error_context = ErrorContext(
                code=ErrorCode.IO_ERROR,
                message="write failed",
            )
            raise SubtitleError(context=error_context)
        state.outcome.translated_path = path.with_suffix(".pl.ass")
        narration = NarrationBatch(
            speech=SpeechBatch(scope_id="scope-good", batch_rank=1, requests=()),
            items=(),
        )
        state.narration = narration
        runner._notify_spoken_ready(path, state, on_spoken_ready)

    monkeypatch.setattr("anishift.pipeline.llm_runtime.PipelineLlmRuntime", _FakeRuntime)
    monkeypatch.setattr(runner, "_translate_one", fake_translate)

    runner._translate_llm_inputs(
        (bad, good),
        states,
        context,
        threading.Event(),
        on_provider_failure=None,
        on_spoken_ready=lambda path, _batch: published.append(path),
    )

    assert states[bad].outcome.status == "failed"
    assert states[bad].outcome.failure is not None
    assert states[good].outcome.status == "done"
    assert published == [good]


def test_llm_retry_clears_previous_failure_before_publishing_narration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mkv"
    spoken = SpokenLine(
        start=1_000,
        end=2_000,
        text="Good evening",
        style="Default",
    )
    split = SubtitleSplit(
        kind="ass",
        subs=SSAFile(),
        decisions=("spoken",),
        verdicts=(),
        spoken=(spoken,),
        stats=SplitStats(1, 1, 1, 0, 0, 0),
    )
    state = runner._MkvState(
        FileOutcome(source, "done"),
        split,
        "ass",
        scope_id="scope-episode",
    )
    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(translation_engine="llm"),
        tmp_path,
    )
    attempts: int = 0
    published: list[Path] = []

    class _FakeRuntime:
        def __init__(self, *_: object, **__: object) -> None:
            self.records: list[object] = []

        def __enter__(self) -> _FakeRuntime:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def engine_factory(self) -> None:
            return None

    def translate_split(*_: object, **__: object) -> FileTranslation:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FileTranslation(
                error="Gemini overloaded",
                error_context=ErrorContext(
                    code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                    message="Gemini overloaded",
                ),
            )
        return FileTranslation(
            spoken=(
                TranslatedLine(
                    start=spoken.start,
                    end=spoken.end,
                    source_text=spoken.text,
                    text="Dobry wieczór",
                    lines=("Dobry wieczór",),
                    style=spoken.style,
                ),
            ),
            engine_id="llm",
        )

    monkeypatch.setattr("anishift.pipeline.llm_runtime.PipelineLlmRuntime", _FakeRuntime)
    monkeypatch.setattr(runner, "_translate_split", translate_split)
    monkeypatch.setattr(runner, "_write_translation_products", lambda *_: None)

    runner._translate_llm_inputs(
        (source,),
        {source: state},
        context,
        threading.Event(),
        on_provider_failure=lambda _context: RecoveryAction.RETRY,
        on_spoken_ready=lambda path, _batch: published.append(path),
    )

    assert attempts == 2
    assert published == [source]
    assert state.enqueue_generation == 1
    assert state.outcome.status == "done"
    assert state.outcome.failure is None


def test_llm_pipeline_sets_cancel_before_executor_wait_on_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.txt"
    source.write_text("Source", encoding="utf-8")
    worker_observed_cancel = threading.Event()

    def fake_translate_inputs(
        _paths: object,
        _states: object,
        _context: object,
        cancel: threading.Event,
        **_: object,
    ) -> dict[Path, FileOutcome]:
        if cancel.wait(timeout=2):
            worker_observed_cancel.set()
        return {}

    def interrupt_extract(*_: object, **__: object) -> dict[Path, runner._MkvState]:
        raise KeyboardInterrupt

    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(translation_engine="llm"),
        tmp_path,
    )
    monkeypatch.setattr(runner, "_translate_llm_inputs", fake_translate_inputs)
    monkeypatch.setattr(runner, "_extract_phase", interrupt_extract)

    with pytest.raises(KeyboardInterrupt):
        run_pipeline(context)

    assert worker_observed_cancel.wait(timeout=1)


def test_non_llm_text_input_reports_translation_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.txt"
    source.write_text("Source", encoding="utf-8")
    transitions: list[tuple[Path, LlmProgressState]] = []
    context = AppContext(
        Settings(),
        UserSettings(translation_engine="google"),
        tmp_path,
    )

    def fake_process_txt(
        path: Path,
        _settings: object,
        *,
        cancel: threading.Event,
    ) -> FileOutcome:
        del cancel
        return FileOutcome(path, "done")

    monkeypatch.setattr(runner, "_process_txt", fake_process_txt)

    report = run_pipeline(
        context,
        input_paths=(source,),
        llm_progress_handler=lambda path, state: transitions.append((path, state)),
    )

    assert report.outcomes[0].status == "done"
    assert transitions == [(source, "translating"), (source, "done")]


def test_llm_pipeline_interrupt_does_not_wait_for_blocked_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.txt"
    source.write_text("Source", encoding="utf-8")
    worker_started = threading.Event()
    release_worker = threading.Event()
    worker_finished = threading.Event()

    def fake_translate_inputs(*_: object, **__: object) -> dict[Path, FileOutcome]:
        worker_started.set()
        release_worker.wait(timeout=2)
        worker_finished.set()
        return {}

    def interrupt_extract(*_: object, **__: object) -> dict[Path, runner._MkvState]:
        assert worker_started.wait(timeout=1)
        raise KeyboardInterrupt

    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(translation_engine="llm"),
        tmp_path,
    )
    monkeypatch.setattr(runner, "_translate_llm_inputs", fake_translate_inputs)
    monkeypatch.setattr(runner, "_extract_phase", interrupt_extract)
    started_at = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            run_pipeline(context)
        elapsed = time.monotonic() - started_at
    finally:
        release_worker.set()

    assert elapsed < 1
    assert worker_finished.wait(timeout=1)


def test_llm_progress_gate_closes_atomically_with_active_callback(
    tmp_path: Path,
) -> None:
    path = tmp_path / "episode.mkv"
    cancel = threading.Event()
    callback_started = threading.Event()
    release_callback = threading.Event()
    transitions: list[tuple[Path, str]] = []

    def handler(progress_path: Path, state: LlmProgressState) -> None:
        transitions.append((progress_path, state))
        callback_started.set()
        assert release_callback.wait(timeout=2.0)

    gate = _LlmProgressGate(cancel, handler)

    with ThreadPoolExecutor(max_workers=2) as executor:
        callback = executor.submit(gate.notify, path, "done")
        assert callback_started.wait(timeout=2.0)
        closing = executor.submit(gate.close)
        assert not closing.done()
        release_callback.set()
        callback.result(timeout=2.0)
        closing.result(timeout=2.0)

    gate.notify(path, "failed")

    assert transitions == [(path, "done")]
