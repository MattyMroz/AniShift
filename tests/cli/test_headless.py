from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Final, cast

import pytest

from anishift.application import (
    AppService,
    ExecutionPlan,
    GroupResult,
    GroupStatus,
    RunEvent,
    RunEventKind,
    RunEventSink,
    RunResult,
    TaskKind,
    TaskState,
)
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.cli import headless as cli_headless
from anishift.cli.exit_codes import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.headless import run_batch
from anishift.cli.run import AutoRunRefusal
from anishift.errors import ExecutionError

_PRESET_ID: Final[str] = "default"

_GROUP_ID: Final[str] = "group-a"

_TASK_ID: Final[str] = "task-1"

_RUN_ID: Final[str] = "run-1"

_REFUSAL: Final[AutoRunRefusal] = AutoRunRefusal("The workspace holds no source group to run.")


class _Service:
    def __init__(
        self,
        *,
        failure: Exception | None = None,
        result: RunResult | None = None,
        events: Sequence[RunEvent] = (),
    ) -> None:
        self.failure: Exception | None = failure
        self.result: RunResult | None = result
        self.events: tuple[RunEvent, ...] = tuple(events)
        self.cancelled: list[str] = []
        self.executed: int = 0

    def default_preset_id(self) -> str:
        return _PRESET_ID

    def execute(self, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del plan
        self.executed += 1
        for event in self.events:
            sink.emit(event)
        if self.failure is not None:
            raise self.failure
        assert self.result is not None
        return self.result

    def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


def _as_service(service: _Service) -> AppService:
    return cast("AppService", service)


def _prepared() -> object:
    plan = SimpleNamespace(tasks=(SimpleNamespace(task_id=_TASK_ID, kind=TaskKind.TRANSLATE_SUBTITLES),))
    return SimpleNamespace(preset_id=_PRESET_ID, workspace=object(), group_ids=(_GROUP_ID,), plan=plan)


def _run_result(status: GroupStatus) -> RunResult:
    errors: tuple[str, ...] = () if status is GroupStatus.SUCCEEDED else ("engine refused",)
    return RunResult(run_id=_RUN_ID, groups=(GroupResult(_GROUP_ID, status, error_messages=errors),))


def _event(kind: RunEventKind, state: TaskState, sequence: int) -> RunEvent:
    task_id: str | None = None if kind is RunEventKind.GROUP_FINISHED else _TASK_ID
    return RunEvent(run_id=_RUN_ID, sequence=sequence, kind=kind, group_id=_GROUP_ID, task_id=task_id, state=state)


def _install_preparation(monkeypatch: pytest.MonkeyPatch, outcome: object) -> list[tuple[str, tuple[str, ...]]]:
    seen: list[tuple[str, tuple[str, ...]]] = []

    def prepare(
        service: AppService,
        preset_id: str,
        *,
        cancel: object = None,
        group_ids: Sequence[str] | None = None,
    ) -> object:
        del service, cancel
        seen.append((preset_id, tuple(group_ids or ())))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cli_headless, "prepare_auto_run", prepare)
    return seen


def test_a_successful_batch_runs_the_default_preset_over_the_named_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_preparation(monkeypatch, _prepared())
    service = _Service(result=_run_result(GroupStatus.SUCCEEDED))

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_SUCCESS
    assert seen == [(_PRESET_ID, (_GROUP_ID,))]
    assert service.executed == 1


def test_a_refused_preparation_never_executes_and_reports_the_refusal_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _REFUSAL)
    service = _Service()

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_REFUSED
    assert service.executed == 0


def test_a_cancelled_run_reports_the_cancellation_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _prepared())
    service = _Service(result=_run_result(GroupStatus.CANCELLED))

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_CANCELLED


def test_a_cancellation_raised_while_planning_reports_the_cancellation_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = EventCancellationToken()
    token.cancel()
    _install_preparation(monkeypatch, ExecutionError("Workflow execution was cancelled"))

    code: int = run_batch(_as_service(_Service()), [_GROUP_ID], cancel=token)

    assert code == EXIT_CANCELLED


def test_a_failed_run_reports_the_incomplete_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _prepared())
    service = _Service(result=_run_result(GroupStatus.FAILED))

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_INCOMPLETE


def test_an_execution_error_is_reported_as_a_refusal_instead_of_escaping(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _prepared())
    service = _Service(failure=ExecutionError("mkvmerge is unavailable"))

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_REFUSED


def test_an_operating_system_error_is_reported_as_a_refusal_instead_of_escaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_preparation(monkeypatch, OSError("workspace is gone"))

    code: int = run_batch(_as_service(_Service()), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_REFUSED


def test_a_requested_stop_reaches_the_run_the_events_belong_to(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _prepared())
    token = EventCancellationToken()
    token.cancel()
    service = _Service(
        result=_run_result(GroupStatus.CANCELLED),
        events=(_event(RunEventKind.TASK_STARTED, TaskState.RUNNING, 1),),
    )

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=token)

    assert code == EXIT_CANCELLED
    assert service.cancelled == [_RUN_ID]


def test_a_live_run_is_left_alone_while_no_stop_was_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_preparation(monkeypatch, _prepared())
    service = _Service(
        result=_run_result(GroupStatus.SUCCEEDED),
        events=(
            _event(RunEventKind.TASK_STARTED, TaskState.RUNNING, 1),
            _event(RunEventKind.TASK_FINISHED, TaskState.SUCCEEDED, 2),
            _event(RunEventKind.GROUP_FINISHED, TaskState.FAILED, 3),
        ),
    )

    code: int = run_batch(_as_service(service), [_GROUP_ID], cancel=NeverCancelledToken())

    assert code == EXIT_SUCCESS
    assert service.cancelled == []
