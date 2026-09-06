"""Batch execution without a terminal, used by a watch running as a service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.application.events import RunEventKind
from anishift.application.planning import TaskState
from anishift.cli.exit_codes import EXIT_CANCELLED, EXIT_REFUSED, run_exit_code
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun, execute_plan, prepare_auto_run
from anishift.errors import AniShiftError
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from anishift.application import AppService, ExecutionPlan, RunResult
    from anishift.application.cancellation import CancellationToken
    from anishift.application.events import RunEvent

__all__ = ["run_batch"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_UNKNOWN_STAGE: Final[str] = "unknown"
"""Stage logged for a task the executed plan does not name."""

_UNKNOWN_STATE: Final[str] = "unknown"
"""Terminal state logged for a group event that carries none."""


def run_batch(service: AppService, group_ids: Sequence[str], *, cancel: CancellationToken) -> int:
    """Plan and execute one batch of source groups in this process, returning its exit code.

    A refusal and a terminal error both end the batch with ``EXIT_REFUSED`` and leave the
    caller free to keep watching; cancellation requested through *cancel* gives
    ``EXIT_CANCELLED``.
    """
    try:
        prepared: PreparedAutoRun | AutoRunRefusal = prepare_auto_run(
            service,
            service.default_preset_id(),
            cancel=cancel,
            group_ids=group_ids,
        )
        if isinstance(prepared, AutoRunRefusal):
            logger.warning("Batch refused", groups=len(group_ids), reason=prepared.message)
            return EXIT_REFUSED
        sink: _HeadlessRunEvents = _HeadlessRunEvents(service, cancel, _stage_names(prepared.plan))
        result: RunResult = execute_plan(service, prepared.plan, sink)
    except (AniShiftError, OSError) as problem:
        if cancel.is_cancelled():
            logger.info("Batch cancelled", groups=len(group_ids))
            return EXIT_CANCELLED
        logger.warning("Batch failed", groups=len(group_ids), error_class=type(problem).__name__)
        return EXIT_REFUSED
    return run_exit_code(result)


class _HeadlessRunEvents:
    """Run-event observer logging stage transitions and forwarding a stop to the live run."""

    __slots__ = ("_cancel", "_service", "_stages")

    def __init__(self, service: AppService, cancel: CancellationToken, stages: Mapping[str, str]) -> None:
        """Bind the observer to the facade owning the run and to the batch cancellation."""
        self._service: AppService = service
        self._cancel: CancellationToken = cancel
        self._stages: Mapping[str, str] = stages

    def emit(self, event: RunEvent) -> None:
        """Log one public transition, then hand a requested stop to the run it belongs to."""
        self._log(event)
        if self._cancel.is_cancelled():
            self._service.cancel(event.run_id)

    def _log(self, event: RunEvent) -> None:
        if event.kind is RunEventKind.TASK_STARTED:
            logger.info("Stage started", stage=self._stage(event.task_id), group=event.group_id)
            return
        if event.kind is RunEventKind.TASK_FINISHED:
            logger.info(
                "Stage finished",
                stage=self._stage(event.task_id),
                group=event.group_id,
                ok=event.state is TaskState.SUCCEEDED,
            )
            return
        if event.kind is RunEventKind.GROUP_FINISHED and event.state is not TaskState.SUCCEEDED:
            logger.warning("Group failed", group=event.group_id, state=_state_name(event.state))

    def _stage(self, task_id: str | None) -> str:
        return self._stages.get(task_id or "", _UNKNOWN_STAGE)


def _stage_names(plan: ExecutionPlan) -> dict[str, str]:
    """Map every planned task to the stage name its log lines carry."""
    return {task.task_id: task.kind.value for task in plan.tasks}


def _state_name(state: TaskState | None) -> str:
    """Return the terminal state of a group event without exposing its text."""
    return _UNKNOWN_STATE if state is None else state.value
