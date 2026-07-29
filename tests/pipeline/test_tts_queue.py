from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline.narration import NarrationBatch
from anishift.pipeline.tts_queue import (
    TtsQueueConfig,
    TtsQueueFailure,
    TtsQueueInput,
    TtsQueueJob,
    TtsQueueOutcome,
    run_tts_queue,
)
from anishift.services.tts import SpeechBatch


def _job(path: Path, rank: int, tmp_path: Path) -> TtsQueueJob:
    narration = NarrationBatch(
        speech=SpeechBatch(scope_id=f"scope-{rank}", batch_rank=rank, requests=()),
        items=(),
    )
    return TtsQueueJob(
        source=path,
        narration=narration,
        source_audio_path=None,
        temporary_root=tmp_path / f"scope-{rank}" / "audio",
        post_process_tempo=1.0,
    )


def _completed(job: TtsQueueJob) -> TtsQueueOutcome:
    return TtsQueueOutcome(job=job, speech=None, audio=None, failure=None)


def _cancelled(job: TtsQueueJob) -> TtsQueueOutcome:
    context = ErrorContext(code=ErrorCode.CANCELLED, message="cancelled")
    return TtsQueueOutcome(
        job=job,
        speech=None,
        audio=None,
        failure=TtsQueueFailure(step="tts", context=context),
    )


def _failed(job: TtsQueueJob) -> TtsQueueOutcome:
    context = ErrorContext(code=ErrorCode.TTS_AUTH_FAILED, message="auth")
    return TtsQueueOutcome(
        job=job,
        speech=None,
        audio=None,
        failure=TtsQueueFailure(step="tts", context=context),
    )


def _not_processed(job: TtsQueueJob) -> TtsQueueOutcome:
    context = ErrorContext(code=ErrorCode.TTS_ENGINE_UNAVAILABLE, message="paused")
    return TtsQueueOutcome(
        job=job,
        speech=None,
        audio=None,
        failure=TtsQueueFailure(
            step="tts",
            context=context,
            disposition="not_processed",
        ),
    )


def test_tts_queue_starts_ready_job_before_producer_close(tmp_path: Path) -> None:
    source = tmp_path / "Episode 1.mkv"
    queue_input = TtsQueueInput((source,))
    started = threading.Event()
    release = threading.Event()

    def worker(job: TtsQueueJob) -> TtsQueueOutcome:
        started.set()
        assert release.wait(timeout=1.0)
        return _completed(job)

    with ThreadPoolExecutor(max_workers=1) as pool:
        queued = pool.submit(
            run_tts_queue,
            queue_input,
            worker=worker,
            config=TtsQueueConfig(
                max_active_batches=1,
                cancel=threading.Event(),
                terminal_factory=_cancelled,
            ),
        )
        queue_input.put(_job(source, 0, tmp_path))
        assert started.wait(timeout=1.0)
        queue_input.close()
        release.set()
        outcomes = queued.result(timeout=1.0)

    assert outcomes[source].failure is None


def test_tts_queue_orders_all_ready_jobs_by_discovery_rank(tmp_path: Path) -> None:
    paths = (
        tmp_path / "Episode 1.mkv",
        tmp_path / "Episode 2.mkv",
        tmp_path / "Episode 10.mkv",
    )
    queue_input = TtsQueueInput(paths)
    queue_input.put(_job(paths[2], 2, tmp_path))
    queue_input.put(_job(paths[1], 1, tmp_path))
    queue_input.put(_job(paths[0], 0, tmp_path))
    queue_input.close()
    observed: list[Path] = []

    def worker(job: TtsQueueJob) -> TtsQueueOutcome:
        observed.append(job.source)
        return _completed(job)

    run_tts_queue(
        queue_input,
        worker=worker,
        config=TtsQueueConfig(
            max_active_batches=1,
            cancel=threading.Event(),
            terminal_factory=_cancelled,
        ),
    )

    assert observed == list(paths)


def test_tts_queue_marks_unsubmitted_jobs_after_cancel(tmp_path: Path) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    cancel = threading.Event()
    queue_input = TtsQueueInput((first, second))
    queue_input.put(_job(first, 0, tmp_path))
    queue_input.put(_job(second, 1, tmp_path))
    queue_input.close()

    def worker(job: TtsQueueJob) -> TtsQueueOutcome:
        cancel.set()
        return _completed(job)

    outcomes = run_tts_queue(
        queue_input,
        worker=worker,
        config=TtsQueueConfig(
            max_active_batches=1,
            cancel=cancel,
            terminal_factory=_cancelled,
        ),
    )

    assert outcomes[first].failure is None
    failure = outcomes[second].failure
    assert failure is not None
    assert failure.context.code is ErrorCode.CANCELLED


def test_tts_queue_pauses_unsubmitted_jobs_after_provider_failure(tmp_path: Path) -> None:
    paths = tuple(tmp_path / f"Episode {index}.mkv" for index in range(1, 4))
    queue_input = TtsQueueInput(paths)
    for rank, path in enumerate(paths):
        queue_input.put(_job(path, rank, tmp_path))
    queue_input.close()
    observed: list[Path] = []

    def worker(job: TtsQueueJob) -> TtsQueueOutcome:
        observed.append(job.source)
        return _failed(job)

    outcomes = run_tts_queue(
        queue_input,
        worker=worker,
        config=TtsQueueConfig(
            max_active_batches=1,
            cancel=threading.Event(),
            terminal_factory=_cancelled,
            pause_on_result=lambda outcome: outcome.failure is not None,
            paused_factory=_not_processed,
        ),
    )

    assert observed == [paths[0]]
    first_failure = outcomes[paths[0]].failure
    assert first_failure is not None
    assert first_failure.disposition == "failed"
    deferred_failures = [outcomes[path].failure for path in paths[1:]]
    assert all(failure is not None for failure in deferred_failures)
    assert all(failure.disposition == "not_processed" for failure in deferred_failures if failure is not None)
