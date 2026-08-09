from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from anishift.application.events import (
    EventBuffer,
    RunEvent,
    RunEventEmitter,
    RunEventKind,
)
from anishift.application.planning import TaskState


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


class _FailingSink:
    def emit(self, event: RunEvent) -> None:
        del event
        raise RuntimeError("observer failed")


def _event(sequence: int, kind: RunEventKind, *, task_id: str | None = None, progress: int | None = None) -> RunEvent:
    return RunEvent(
        run_id="run-1",
        sequence=sequence,
        kind=kind,
        group_id="group-1",
        task_id=task_id,
        progress_percent=progress,
    )


def test_emitter_owns_monotonic_sequence_and_run_identity() -> None:
    sink = _CollectingSink()
    emitter = RunEventEmitter("run-1", sink)

    first = emitter.emit(RunEventKind.RUN_STARTED)
    second = emitter.emit(
        RunEventKind.TASK_QUEUED,
        group_id="group-1",
        task_id="task-1",
        state=TaskState.QUEUED,
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert {event.run_id for event in sink.events} == {"run-1"}


def test_observer_failure_does_not_change_emitted_event() -> None:
    emitter = RunEventEmitter("run-1", _FailingSink())

    event = emitter.emit(RunEventKind.RUN_STARTED)

    assert event.sequence == 1
    assert emitter.emit(RunEventKind.RUN_FINISHED).sequence == 2


def test_event_buffer_keeps_state_and_only_latest_progress_per_task() -> None:
    buffer = EventBuffer()
    buffer.push(_event(1, RunEventKind.TASK_QUEUED, task_id="task-1"))
    buffer.push(_event(2, RunEventKind.TASK_PROGRESS, task_id="task-1", progress=10))
    buffer.push(_event(3, RunEventKind.TASK_PROGRESS, task_id="task-1", progress=90))
    buffer.push(_event(4, RunEventKind.TASK_FINISHED, task_id="task-1"))

    drained = buffer.drain()

    assert tuple(event.sequence for event in drained) == (1, 3, 4)
    assert buffer.drain() == ()


def test_event_buffer_keeps_highest_sequence_when_progress_arrives_out_of_order() -> None:
    buffer = EventBuffer()
    buffer.push(_event(10, RunEventKind.TASK_PROGRESS, task_id="task-1", progress=90))
    buffer.push(_event(9, RunEventKind.TASK_PROGRESS, task_id="task-1", progress=80))

    drained = buffer.drain()

    assert tuple(event.sequence for event in drained) == (10,)


def test_event_buffer_push_is_thread_safe() -> None:
    buffer = EventBuffer()

    def push_progress(task_number: int) -> None:
        task_id: str = f"task-{task_number % 4}"
        buffer.push(_event(task_number + 1, RunEventKind.TASK_PROGRESS, task_id=task_id, progress=task_number))

    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(push_progress, range(100)))

    drained = buffer.drain()

    assert len(drained) == 4
    assert {event.task_id for event in drained} == {"task-0", "task-1", "task-2", "task-3"}


def test_public_event_message_redacts_paths_and_secrets() -> None:
    event = RunEvent(
        run_id="run-1",
        sequence=1,
        kind=RunEventKind.RUN_FINISHED,
        message=r"failed C:\Users\Matty\secret.txt api_key=abc123 Bearer xyz sk-private",
    )

    assert event.message is not None
    assert r"C:\Users" not in event.message
    assert "abc123" not in event.message
    assert "xyz" not in event.message
    assert "sk-private" not in event.message


def test_public_event_message_redacts_unc_posix_and_quoted_secret() -> None:
    event = RunEvent(
        run_id="run-1",
        sequence=1,
        kind=RunEventKind.RUN_FINISHED,
        message=r'failed \\server\share\private.txt /secret.txt api_key="abc def"',
    )

    assert event.message is not None
    assert "server" not in event.message
    assert "/secret.txt" not in event.message
    assert "abc" not in event.message
    assert "def" not in event.message
