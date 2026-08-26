from __future__ import annotations

from anishift.application.events import (
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
