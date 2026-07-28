from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.pipeline.llm_queue import (
    LlmFailureAction,
    LlmQueueConfig,
    LlmQueueInput,
    SharedProviderState,
    run_llm_queue,
)
from anishift.pipeline.types import FileFailure, FileOutcome
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmContextLengthError,
    LlmOutputBlockedError,
    LlmRateLimitError,
)


def _done(path: Path) -> FileOutcome:
    return FileOutcome(path, "done")


def _failed(path: Path, code: ErrorCode) -> FileOutcome:
    return FileOutcome(
        path,
        "failed",
        failure=FileFailure("translate", code.value, f"{code.value} failure", "fix settings"),
    )


def _not_processed(path: Path, context: ErrorContext) -> FileOutcome:
    return FileOutcome(
        path,
        "not_processed",
        failure=FileFailure(
            "translate",
            context.code.value,
            context.message,
            context.suggestion,
        ),
    )


def test_queue_preserves_submission_order_and_ramps_above_one_slot(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"episode{index}.mkv" for index in range(1, 6)]
    started: list[Path] = []
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    pair_started = threading.Barrier(2)

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _state: SharedProviderState) -> FileOutcome:
            nonlocal active, maximum_active
            with lock:
                started.append(path)
                active += 1
                maximum_active = max(maximum_active, active)
            if path in paths[1:3]:
                pair_started.wait()
            state.on_success()
            with lock:
                active -= 1
            return _done(path)

        return worker

    outcomes = run_llm_queue(
        paths,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(configured_limit=lambda: 4, cancel=threading.Event()),
    )
    assert started[0] == paths[0]
    assert set(started) == set(paths)
    assert maximum_active >= 2
    assert [outcomes[path].status for path in paths] == ["done"] * 5


def test_healthy_limit_starts_configured_and_recovery_ramps_one_two_four() -> None:
    state = SharedProviderState(threading.Event())
    assert state.concurrency_limit(4) == 4
    state.on_transient_failure(LlmRateLimitError("rate"))
    assert state.concurrency_limit(4) == 1
    state.on_success()
    assert state.concurrency_limit(4) == 2
    state.on_success()
    assert state.concurrency_limit(4) == 4


@pytest.mark.parametrize(
    "error",
    [
        LlmContextLengthError("too large"),
        LlmOutputBlockedError("safety"),
    ],
)
def test_file_local_fatal_error_does_not_disable_provider(error: AniShiftError) -> None:
    state = SharedProviderState(threading.Event())
    state.before_attempt()

    state.on_fatal_failure(error)

    assert state.can_submit
    assert state.concurrency_limit(4) == 4


def test_attempt_limiter_allows_one_probe_then_two_recovering_attempts() -> None:
    state = SharedProviderState(threading.Event())
    initial_started = threading.Barrier(4)
    first_failed = threading.Event()
    all_failed = threading.Event()
    probe_started = threading.Event()
    two_followups_started = threading.Event()
    release_probe = threading.Event()
    release_followups = threading.Event()
    lock = threading.Lock()
    failed_count = 0
    retry_threads: list[int] = []

    def worker(index: int) -> None:
        nonlocal failed_count
        state.before_attempt()
        initial_started.wait()
        if index == 0:
            state.on_transient_failure(LlmRateLimitError("rate"))
            first_failed.set()
        else:
            assert first_failed.wait(timeout=2)
            state.on_transient_failure(LlmRateLimitError("rate"))
        with lock:
            failed_count += 1
            if failed_count == 4:
                all_failed.set()
        state.before_attempt()
        with lock:
            retry_threads.append(index)
            if len(retry_threads) == 1:
                probe_started.set()
            if len(retry_threads) == 3:
                two_followups_started.set()
        if index == 0:
            release_probe.wait()
        else:
            release_followups.wait()
        state.on_success()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, index) for index in range(4)]
        assert all_failed.wait(timeout=2)
        assert probe_started.wait(timeout=2)
        assert retry_threads == [0]
        release_probe.set()
        assert two_followups_started.wait(timeout=2)
        assert len(retry_threads) == 3
        release_followups.set()
        for future in futures:
            future.result(timeout=2)
    assert sorted(retry_threads) == [0, 1, 2, 3]


def test_provider_failure_stops_unsent_files_and_preserves_completed(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"episode{index}.mkv" for index in range(1, 4)]
    decisions: list[tuple[int, int]] = []

    def factory(_state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            return _failed(path, ErrorCode.LLM_AUTH_FAILED)

        return worker

    def decide(
        _outcome: FileOutcome,
        completed: int,
        pending: int,
    ) -> LlmFailureAction:
        decisions.append((completed, pending))
        return "finish"

    outcomes = run_llm_queue(
        paths,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(
            configured_limit=lambda: 1,
            cancel=threading.Event(),
            on_provider_failure=decide,
        ),
    )
    assert outcomes[paths[0]].status == "failed"
    assert outcomes[paths[1]].status == "not_processed"
    assert outcomes[paths[2]].status == "not_processed"
    assert decisions == [(0, 2)]


def test_progress_reports_start_terminal_and_unsent_files(tmp_path: Path) -> None:
    paths = [tmp_path / f"episode{index}.mkv" for index in range(1, 4)]
    transitions: list[tuple[Path, str]] = []

    def factory(_state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            return _failed(path, ErrorCode.LLM_AUTH_FAILED)

        return worker

    run_llm_queue(
        paths,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(
            configured_limit=lambda: 1,
            cancel=threading.Event(),
            on_progress=lambda path, state: transitions.append((path, state)),
        ),
    )

    assert transitions == [
        (paths[0], "translating"),
        (paths[0], "failed"),
        (paths[1], "not_processed"),
        (paths[2], "not_processed"),
    ]


def test_settings_action_retries_failed_file_before_pending_files(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"episode{index}.mkv" for index in range(1, 4)]
    generation = 0
    starts: list[tuple[int, Path]] = []

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        nonlocal generation
        generation += 1
        current = generation

        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            starts.append((current, path))
            if current == 1:
                return _failed(path, ErrorCode.LLM_MODEL_INVALID)
            state.on_success()
            return _done(path)

        return worker

    outcomes = run_llm_queue(
        paths,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(
            configured_limit=lambda: 1,
            cancel=threading.Event(),
            on_provider_failure=lambda _outcome, _completed, _pending: "settings",
        ),
    )
    assert starts[:2] == [(1, paths[0]), (2, paths[0])]
    assert all(outcomes[path].status == "done" for path in paths)


def test_file_local_translation_failure_does_not_pause_queue(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "episode1.mkv", tmp_path / "episode2.mkv"]

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            state.on_success()
            if path == paths[0]:
                return _failed(path, ErrorCode.TRANSLATION_FAILED)
            return _done(path)

        return worker

    outcomes = run_llm_queue(
        paths,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(configured_limit=lambda: 4, cancel=threading.Event()),
    )
    assert outcomes[paths[0]].status == "failed"
    assert outcomes[paths[1]].status == "done"


def test_streaming_input_starts_ready_file_before_producer_closes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "episode1.mkv"
    second = tmp_path / "episode2.mkv"
    queue_input = LlmQueueInput()
    first_started = threading.Event()
    release_first = threading.Event()

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            if path == first:
                first_started.set()
                release_first.wait()
            state.on_success()
            return _done(path)

        return worker

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            run_llm_queue,
            queue_input,
            worker_factory=factory,
            not_processed_factory=_not_processed,
            config=LlmQueueConfig(
                configured_limit=lambda: 4,
                cancel=threading.Event(),
            ),
        )
        queue_input.put(first)
        assert first_started.wait(timeout=2)
        queue_input.put(second)
        queue_input.close()
        release_first.set()
        outcomes = result.result(timeout=2)
    assert outcomes[first].status == "done"
    assert outcomes[second].status == "done"


def test_streaming_input_uses_discovery_rank_not_arrival_order(
    tmp_path: Path,
) -> None:
    first = tmp_path / "episode1.mkv"
    second = tmp_path / "episode2.mkv"
    queue_input = LlmQueueInput((first, second))
    queue_input.put(second)
    queue_input.put(first)
    queue_input.close()
    starts: list[Path] = []

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            starts.append(path)
            state.on_success()
            return _done(path)

        return worker

    run_llm_queue(
        queue_input,
        worker_factory=factory,
        not_processed_factory=_not_processed,
        config=LlmQueueConfig(
            configured_limit=lambda: 1,
            cancel=threading.Event(),
        ),
    )
    assert starts == [first, second]


def test_fatal_observer_blocks_file_enqueued_before_future_is_reaped(
    tmp_path: Path,
) -> None:
    first = tmp_path / "episode1.mkv"
    second = tmp_path / "episode2.mkv"
    queue_input = LlmQueueInput((first, second))
    fatal_observed = threading.Event()
    release_first = threading.Event()
    starts: list[Path] = []

    def factory(state: SharedProviderState) -> Callable[[Path, SharedProviderState], FileOutcome]:
        def worker(path: Path, _worker_state: SharedProviderState) -> FileOutcome:
            starts.append(path)
            state.before_attempt()
            state.on_fatal_failure(LlmAuthError("auth"))
            fatal_observed.set()
            release_first.wait()
            return _failed(path, ErrorCode.LLM_AUTH_FAILED)

        return worker

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            run_llm_queue,
            queue_input,
            worker_factory=factory,
            not_processed_factory=_not_processed,
            config=LlmQueueConfig(
                configured_limit=lambda: 4,
                cancel=threading.Event(),
            ),
        )
        queue_input.put(first)
        assert fatal_observed.wait(timeout=2)
        queue_input.put(second)
        queue_input.close()
        release_first.set()
        outcomes = result.result(timeout=2)
    assert starts == [first]
    assert outcomes[first].status == "failed"
    assert outcomes[second].status == "not_processed"
