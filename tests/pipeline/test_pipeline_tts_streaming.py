from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline import runner
from anishift.pipeline.narration import NarrationBatch, NarrationItem, scope_id_for_source
from anishift.pipeline.recovery import RecoveryAction, RecoveryContext
from anishift.pipeline.tts_queue import (
    TtsQueueFailure,
    TtsQueueJob,
    TtsQueueOutcome,
)
from anishift.pipeline.tts_runtime import PipelineTtsProgressSink, PipelineTtsRuntime
from anishift.pipeline.types import FileOutcome, TrackPriorities
from anishift.services.audio import AudioConfig, AudioRenderResult, AudioRenderStatus
from anishift.services.audio.types import PlacementReason, TimelinePlacement
from anishift.services.extraction.types import MediaInfo
from anishift.services.subtitles.types import SubtitleSplit
from anishift.services.tts import (
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechRequest,
    TtsConfig,
)
from anishift.services.tts.protocols import TtsProgressSink

_PRIORITIES = TrackPriorities(audio=("jpn", "eng"), subtitle=("pol", "eng"))


def _context(root: Path) -> AppContext:
    return AppContext(Settings(), UserSettings(), root)


def _narration(path: Path, root: Path, rank: int) -> NarrationBatch:
    request = SpeechRequest(
        request_id=f"request-{rank}",
        text="Tekst",
        request_rank=0,
    )
    return NarrationBatch(
        speech=SpeechBatch(
            scope_id=scope_id_for_source(path, workspace_root=root),
            batch_rank=rank,
            requests=(request,),
        ),
        items=(
            NarrationItem(
                request=request,
                start_ms=0,
                end_ms=1_000,
                source_order=0,
            ),
        ),
    )


class _FakeRuntime:
    def __init__(self, root: Path, discovery_order: tuple[Path, ...]) -> None:
        self.root = root
        self.discovery_order = discovery_order
        self.jobs: list[TtsQueueJob] = []
        self.started = threading.Event()
        self.cancelled = False
        self.closed_input = False
        self.closed = False
        self.failures: dict[Path, TtsQueueFailure] = {}

    def put(
        self,
        source: Path,
        narration: NarrationBatch,
        *,
        source_audio_path: Path | None,
    ) -> None:
        self.jobs.append(
            TtsQueueJob(
                source=source,
                narration=narration,
                source_audio_path=source_audio_path,
                temporary_root=self.root / "temp" / narration.speech.scope_id / "audio",
                post_process_tempo=1.0,
            ),
        )
        self.started.set()

    def close_input(self) -> None:
        self.closed_input = True

    def skip(self, source: Path) -> None:
        del source

    def wait(self) -> dict[Path, TtsQueueOutcome]:
        outcomes: dict[Path, TtsQueueOutcome] = {}
        for job in self.jobs:
            failure = self.failures.get(job.source)
            speech = (
                None
                if failure is not None
                else SpeechBatchResult(
                    scope_id=job.narration.speech.scope_id,
                    status=SpeechBatchStatus.COMPLETED,
                    requests=(),
                    stats=SpeechBatchStats(
                        total_requests=0,
                        synthesized=0,
                        resume_hits=0,
                        skipped=0,
                        failed=0,
                        provider_calls=0,
                        retries=0,
                        synthesis_time_ms=0.0,
                        engine_id="fake",
                        provider_model_id="fake",
                        voice_id="fake",
                    ),
                    failure=None,
                )
            )
            audio = (
                None
                if failure is not None
                else AudioRenderResult(
                    scope_id=job.narration.speech.scope_id,
                    status=AudioRenderStatus.COMPLETED,
                    narrator_path=self.root / f"{job.source.stem}.narrator.wav",
                    output_path=self.root / f"{job.source.stem}.eac3",
                    output_probe=None,
                    placements=(),
                    warnings=(),
                    narration_fingerprint="narration",
                    mix_fingerprint="mix",
                )
            )
            outcomes[job.source] = TtsQueueOutcome(
                job=job,
                speech=speech,
                audio=audio,
                failure=failure,
            )
        return outcomes

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


def test_polish_narration_starts_before_foreign_translation_finishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    polish = tmp_path / "Episode 1.mkv"
    foreign = tmp_path / "Episode 2.mkv"
    polish.touch()
    foreign.touch()
    runtime = _FakeRuntime(tmp_path, (polish, foreign))

    def runtime_factory(
        context: AppContext,
        discovery_order: tuple[Path, ...],
        cancel: threading.Event,
        callbacks: object | None,
    ) -> _FakeRuntime:
        del context, cancel, callbacks
        runtime.discovery_order = discovery_order
        return runtime

    def extract_phase(
        mkvs: tuple[Path, ...],
        *_: object,
        on_complete: object,
        **__: object,
    ) -> dict[Path, runner._MkvState]:
        callback = cast("Callable[[Path, runner._MkvState], None]", on_complete)
        polish_state = runner._MkvState(
            FileOutcome(polish, "done", source_audio_path=tmp_path / "polish.flac"),
            None,
            source_rank=0,
            scope_id=scope_id_for_source(polish, workspace_root=tmp_path),
            narration=_narration(polish, tmp_path, 0),
        )
        foreign_state = runner._MkvState(
            FileOutcome(foreign, "done"),
            cast("SubtitleSplit", object()),
            source_rank=1,
            scope_id=scope_id_for_source(foreign, workspace_root=tmp_path),
        )
        callback(polish, polish_state)
        callback(foreign, foreign_state)
        return {polish: polish_state, foreign: foreign_state}

    def translate_phase(
        states: dict[Path, runner._MkvState],
        *_: object,
        on_spoken_ready: runner.SpokenReadyHandler | None,
        **__: object,
    ) -> None:
        assert runtime.started.is_set()
        state = states[foreign]
        state.narration = _narration(foreign, tmp_path, 1)
        runner._notify_spoken_ready(foreign, state, on_spoken_ready)

    monkeypatch.setattr(runner, "_extract_phase", extract_phase)
    monkeypatch.setattr(runner, "_translate_phase", translate_phase)

    report = runner.run_pipeline(
        _context(tmp_path),
        input_paths=(foreign, polish),
        tts_runtime_factory=runtime_factory,
    )

    assert runtime.discovery_order == (polish, foreign)
    assert [job.source for job in runtime.jobs] == [polish, foreign]
    assert all(outcome.mixed_audio_path is not None for outcome in report.outcomes)
    assert runtime.closed_input
    assert runtime.closed


def test_tts_failure_preserves_subtitles_and_does_not_rollback_other_file(
    tmp_path: Path,
) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    first_outcome = FileOutcome(first, "done", translated_path=tmp_path / "first.pl.ass")
    second_outcome = FileOutcome(second, "done", translated_path=tmp_path / "second.pl.ass")
    first_state = runner._MkvState(first_outcome, None, narration=_narration(first, tmp_path, 0))
    second_state = runner._MkvState(second_outcome, None, narration=_narration(second, tmp_path, 1))
    runtime = _FakeRuntime(tmp_path, (first, second))
    runtime.put(
        first,
        cast("NarrationBatch", first_state.narration),
        source_audio_path=None,
    )
    runtime.put(
        second,
        cast("NarrationBatch", second_state.narration),
        source_audio_path=None,
    )
    runtime.failures[second] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(
            code=ErrorCode.TTS_FAILED,
            message="provider failed",
            suggestion="retry",
        ),
    )

    runner._apply_tts_outcomes(
        {first: first_state, second: second_state},
        runtime.wait(),
    )

    assert first_outcome.status == "done"
    assert first_outcome.mixed_audio_path is not None
    assert second_outcome.status == "failed"
    assert second_outcome.failure is not None
    assert second_outcome.failure.step == "tts"
    assert second_outcome.translated_path == tmp_path / "second.pl.ass"


def test_deferred_tts_outcome_is_not_processed_in_final_report(tmp_path: Path) -> None:
    source = tmp_path / "Episode.mkv"
    narration = _narration(source, tmp_path, 0)
    state = runner._MkvState(
        FileOutcome(source, "done"),
        None,
        narration=narration,
    )
    job = TtsQueueJob(
        source=source,
        narration=narration,
        source_audio_path=None,
        temporary_root=tmp_path / "temp",
        post_process_tempo=1.0,
    )
    failure = TtsQueueFailure(
        step="tts",
        context=ErrorContext(
            code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
            message="paused",
        ),
        disposition="not_processed",
    )

    runner._apply_tts_outcomes(
        {source: state},
        {
            source: TtsQueueOutcome(
                job=job,
                speech=None,
                audio=None,
                failure=failure,
            ),
        },
    )

    assert state.outcome.status == "not_processed"


def test_extract_cleanup_preserves_tts_and_audio_scope_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mkv"
    source.touch()
    scope_id = scope_id_for_source(source, workspace_root=tmp_path)
    scope_root = tmp_path / "temp" / scope_id
    tts_marker = scope_root / "tts" / "clip.bin"
    audio_marker = scope_root / "audio" / "mix.bin"
    scratch_marker = scope_root / "extract-scratch" / "stale.bin"
    for marker in (tts_marker, audio_marker, scratch_marker):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    monkeypatch.setattr(runner, "identify", lambda path: MediaInfo(path, ()))

    state = runner._extract_mkv(
        source,
        tmp_path,
        source_rank=0,
        interaction=None,
        on_progress=None,
        cancel=threading.Event(),
        priorities=_PRIORITIES,
    )

    assert state.outcome.status == "done"
    assert tts_marker.exists()
    assert audio_marker.exists()
    assert not scratch_marker.exists()


def test_tts_outcome_exposes_speech_stats_and_timeline_placements(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mkv"
    narration = _narration(source, tmp_path, 0)
    state = runner._MkvState(
        FileOutcome(source, "done"),
        None,
        narration=narration,
    )
    stats = SpeechBatchStats(
        total_requests=1,
        synthesized=1,
        resume_hits=0,
        skipped=0,
        failed=0,
        provider_calls=1,
        retries=0,
        synthesis_time_ms=123.0,
        engine_id="edge",
        provider_model_id="edge",
        voice_id="voice",
    )
    speech = SpeechBatchResult(
        scope_id=narration.speech.scope_id,
        status=SpeechBatchStatus.COMPLETED,
        requests=(),
        stats=stats,
        failure=None,
    )
    placement = TimelinePlacement(
        request_id="request-0",
        source_order=0,
        planned_start_ms=0,
        planned_end_ms=1_000,
        actual_start_ms=0,
        actual_end_ms=900,
        drift_ms=0,
        reason=PlacementReason.ON_TIME,
        overlap_group_id=None,
        clip_duration_ms=900,
        window_duration_ms=1_000,
        start_frame=0,
        end_frame=43_200,
    )
    audio = AudioRenderResult(
        scope_id=narration.speech.scope_id,
        status=AudioRenderStatus.COMPLETED,
        narrator_path=tmp_path / "Episode.narrator.wav",
        output_path=tmp_path / "Episode.eac3",
        output_probe=None,
        placements=(placement,),
        warnings=(),
        narration_fingerprint="narration",
        mix_fingerprint="mix",
    )
    job = TtsQueueJob(
        source=source,
        narration=narration,
        source_audio_path=None,
        temporary_root=tmp_path / "temp",
        post_process_tempo=1.0,
    )

    runner._apply_tts_outcomes(
        {source: state},
        {
            source: TtsQueueOutcome(
                job=job,
                speech=speech,
                audio=audio,
                failure=None,
            ),
        },
    )

    assert state.outcome.tts_stats is stats
    assert state.outcome.audio_placements == (placement,)


def test_tts_recovery_retries_failed_file_before_deferred_files(tmp_path: Path) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    first_narration = _narration(first, tmp_path, 0)
    second_narration = _narration(second, tmp_path, 1)
    states = {
        first: runner._MkvState(
            FileOutcome(first, "done"),
            None,
            narration=first_narration,
        ),
        second: runner._MkvState(
            FileOutcome(second, "done"),
            None,
            narration=second_narration,
        ),
    }
    initial = _FakeRuntime(tmp_path, (first, second))
    initial.put(first, first_narration, source_audio_path=None)
    initial.put(second, second_narration, source_audio_path=None)
    initial.failures[first] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(
            code=ErrorCode.TTS_AUTH_FAILED,
            message="auth",
        ),
    )
    initial.failures[second] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(
            code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
            message="paused",
        ),
        disposition="not_processed",
    )
    decisions: list[RecoveryContext] = []
    retries: list[_FakeRuntime] = []

    def runtime_factory(
        _context: AppContext,
        discovery_order: tuple[Path, ...],
        _cancel: threading.Event,
        _callbacks: PipelineTtsProgressSink | None,
    ) -> _FakeRuntime:
        runtime = _FakeRuntime(tmp_path, discovery_order)
        retries.append(runtime)
        return runtime

    def recover(context: RecoveryContext) -> RecoveryAction:
        decisions.append(context)
        return RecoveryAction.RETRY

    recovered_runtime, outcomes = runner._recover_tts_outcomes(
        _context(tmp_path),
        states,
        initial,
        initial.wait(),
        runtime_factory=runtime_factory,
        failure_handler=recover,
        progress_callbacks=None,
        cancel=threading.Event(),
    )

    assert initial.closed
    assert recovered_runtime is retries[0]
    assert retries[0].discovery_order == (first, second)
    assert [job.source for job in retries[0].jobs] == [first, second]
    assert decisions[0].failed_files == (first,)
    assert decisions[0].pending_files == (second,)
    assert all(outcome.failure is None for outcome in outcomes.values())


def test_failed_tts_runtime_rebuild_returns_to_recovery_with_preserved_outcomes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "episode1.mkv"
    second = tmp_path / "episode2.mkv"
    first_narration = _narration(first, tmp_path, 0)
    second_narration = _narration(second, tmp_path, 1)
    states = {
        first: runner._MkvState(FileOutcome(first, "done"), None, narration=first_narration),
        second: runner._MkvState(FileOutcome(second, "done"), None, narration=second_narration),
    }
    initial = _FakeRuntime(tmp_path, (first, second))
    initial.put(first, first_narration, source_audio_path=None)
    initial.put(second, second_narration, source_audio_path=None)
    initial.failures[first] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(code=ErrorCode.TTS_AUTH_FAILED, message="auth"),
    )
    initial.failures[second] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(code=ErrorCode.TTS_ENGINE_UNAVAILABLE, message="paused"),
        disposition="not_processed",
    )
    original_outcomes = initial.wait()
    decisions: list[RecoveryContext] = []

    def runtime_factory(
        _context: AppContext,
        _discovery_order: tuple[Path, ...],
        _cancel: threading.Event,
        _callbacks: PipelineTtsProgressSink | None,
    ) -> _FakeRuntime:
        raise RuntimeError("invalid updated TTS settings")

    def recover(context: RecoveryContext) -> RecoveryAction:
        decisions.append(context)
        return RecoveryAction.SETTINGS if len(decisions) == 1 else RecoveryAction.FINISH

    recovered_runtime, outcomes = runner._recover_tts_outcomes(
        _context(tmp_path),
        states,
        initial,
        original_outcomes,
        runtime_factory=runtime_factory,
        failure_handler=recover,
        progress_callbacks=None,
        cancel=threading.Event(),
    )

    assert initial.closed
    assert recovered_runtime is initial
    assert outcomes == original_outcomes
    assert [decision.error.code for decision in decisions] == [
        ErrorCode.TTS_AUTH_FAILED,
        ErrorCode.TTS_CONFIG_INVALID,
    ]
    assert decisions[1].error.message == "invalid updated TTS settings"
    assert decisions[1].failed_files == (first,)
    assert decisions[1].pending_files == (second,)


def test_tts_runtime_rebuild_can_succeed_after_invalid_updated_settings(
    tmp_path: Path,
) -> None:
    first = tmp_path / "episode1.mkv"
    second = tmp_path / "episode2.mkv"
    first_narration = _narration(first, tmp_path, 0)
    second_narration = _narration(second, tmp_path, 1)
    states = {
        first: runner._MkvState(FileOutcome(first, "done"), None, narration=first_narration),
        second: runner._MkvState(FileOutcome(second, "done"), None, narration=second_narration),
    }
    initial = _FakeRuntime(tmp_path, (first, second))
    initial.put(first, first_narration, source_audio_path=None)
    initial.put(second, second_narration, source_audio_path=None)
    initial.failures[first] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(code=ErrorCode.TTS_AUTH_FAILED, message="auth"),
    )
    initial.failures[second] = TtsQueueFailure(
        step="tts",
        context=ErrorContext(code=ErrorCode.TTS_ENGINE_UNAVAILABLE, message="paused"),
        disposition="not_processed",
    )
    factory_calls = 0
    decisions: list[RecoveryContext] = []
    recovered: list[_FakeRuntime] = []

    def runtime_factory(
        _context: AppContext,
        discovery_order: tuple[Path, ...],
        _cancel: threading.Event,
        _callbacks: PipelineTtsProgressSink | None,
    ) -> _FakeRuntime:
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            raise ValueError("voice configuration is incomplete")
        runtime = _FakeRuntime(tmp_path, discovery_order)
        recovered.append(runtime)
        return runtime

    def recover(context: RecoveryContext) -> RecoveryAction:
        decisions.append(context)
        return RecoveryAction.SETTINGS

    recovered_runtime, outcomes = runner._recover_tts_outcomes(
        _context(tmp_path),
        states,
        initial,
        initial.wait(),
        runtime_factory=runtime_factory,
        failure_handler=recover,
        progress_callbacks=None,
        cancel=threading.Event(),
    )

    assert factory_calls == 2
    assert recovered_runtime is recovered[0]
    assert [decision.error.code for decision in decisions] == [
        ErrorCode.TTS_AUTH_FAILED,
        ErrorCode.TTS_CONFIG_INVALID,
    ]
    assert [job.source for job in recovered[0].jobs] == [first, second]
    assert all(outcome.failure is None for outcome in outcomes.values())


def test_pipeline_interrupt_cancels_tts_runtime_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Episode.mkv"
    source.touch()

    class _BlockingTts:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()
            self.cancel_calls = 0
            self.closed = False

        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            del callbacks
            self.started.set()
            assert self.release.wait(timeout=2.0)
            return SpeechBatchResult(
                scope_id=batch.scope_id,
                status=SpeechBatchStatus.CANCELLED,
                requests=(),
                stats=SpeechBatchStats(
                    total_requests=len(batch.requests),
                    synthesized=0,
                    resume_hits=0,
                    skipped=0,
                    failed=0,
                    provider_calls=0,
                    retries=0,
                    synthesis_time_ms=0.0,
                    engine_id="fake",
                    provider_model_id="fake",
                    voice_id="fake",
                ),
                failure=ErrorContext(
                    code=ErrorCode.CANCELLED,
                    message="cancelled",
                ),
            )

        def cancel(self) -> None:
            self.cancel_calls += 1
            self.release.set()

        def close(self) -> None:
            self.closed = True

    class _UnusedAudio:
        def render(
            self,
            request: object,
            *,
            callbacks: object | None = None,
            cancel: threading.Event | None = None,
        ) -> AudioRenderResult:
            del request, callbacks, cancel
            raise AssertionError("audio must not run after cancelled TTS")

    blocking_tts = _BlockingTts()
    runtime: PipelineTtsRuntime | None = None

    def runtime_factory(
        context: AppContext,
        discovery_order: tuple[Path, ...],
        cancel: threading.Event,
        callbacks: object | None,
    ) -> PipelineTtsRuntime:
        nonlocal runtime
        runtime = PipelineTtsRuntime(
            tts_config=TtsConfig(
                engine_id="fake",
                provider_model_id="fake",
                voice_id="fake",
                max_concurrency=1,
                queue_capacity=2,
            ),
            audio_config=AudioConfig(),
            workspace_root=context.workspace_root,
            discovery_order=discovery_order,
            cancel=cancel,
            post_process_tempo=1.0,
            callbacks=cast("PipelineTtsProgressSink | None", callbacks),
            tts_service=blocking_tts,
            audio_service=_UnusedAudio(),
        )
        return runtime

    def interrupt_extract(
        *_: object,
        on_complete: object,
        **__: object,
    ) -> dict[Path, runner._MkvState]:
        callback = cast("Callable[[Path, runner._MkvState], None]", on_complete)
        narration = _narration(source, tmp_path, 0)
        callback(
            source,
            runner._MkvState(
                FileOutcome(source, "done"),
                None,
                source_rank=0,
                scope_id=narration.speech.scope_id,
                narration=narration,
            ),
        )
        assert blocking_tts.started.wait(timeout=1.0)
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_extract_phase", interrupt_extract)

    started_at = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        runner.run_pipeline(
            _context(tmp_path),
            input_paths=(source,),
            tts_runtime_factory=runtime_factory,
        )
    elapsed = time.monotonic() - started_at

    assert elapsed < 1.0
    assert blocking_tts.cancel_calls == 1
    assert blocking_tts.closed
    assert runtime is not None
