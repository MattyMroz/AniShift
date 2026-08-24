"""Bounded streaming execution of immutable application task graphs."""

from __future__ import annotations

import queue
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Final

from anishift.application.cancellation import CancellationToken, CommitCancellationToken
from anishift.application.events import (
    RunEventEmitter,
    RunEventKind,
    RunEventSink,
    WorkerNotification,
    WorkerNotificationKind,
)
from anishift.application.planning import ExecutionPlan, PlanTask, TaskState
from anishift.application.results import ArtifactSnapshot, GroupResult, RunResult, TaskResult
from anishift.application.scheduler_contracts import (
    NaturalOrderGate,
    ResourceLimits,
    TaskHandler,
    TaskProgressSink,
)
from anishift.application.scheduler_runtime import (
    ArtifactStore,
    QueuedProgressSink,
    SchedulerRuntime,
    SubmittedTask,
    TaskStarted,
    all_tasks_terminal,
    build_group_result,
    commit_success,
    create_run_state,
    detect_terminal_groups,
    finish_cancelled,
    finish_failed,
    group_event_state,
    natural_gate,
    queue_task,
    run_result_state,
    thread_prefix,
)
from anishift.application.sessions import RunSession
from anishift.errors import ErrorCode, ErrorContext, ExecutionError

__all__ = [
    "GraphScheduler",
    "NaturalOrderGate",
    "ResourceLimits",
    "TaskHandler",
    "TaskProgressSink",
]

# ── Constants ────────────────────────────────────────────────────────────────

_COORDINATOR_POLL_S: Final[float] = 0.05
"""Maximum delay before the coordinator forwards worker notifications."""


class GraphScheduler:
    """Coordinate one immutable graph through bounded per-resource executors."""

    __slots__ = ("_handler", "_limits", "_run_id", "_session")

    def __init__(
        self,
        handler: TaskHandler,
        *,
        limits: ResourceLimits,
        run_id: str,
        session: RunSession,
    ) -> None:
        """Bind a task dispatcher, explicit limits, and one active run scope."""
        if not run_id.strip():
            msg = "Graph scheduler requires a run ID"
            raise ValueError(msg)
        self._handler: TaskHandler = handler
        self._limits: ResourceLimits = limits
        self._run_id: str = run_id
        self._session: RunSession = session

    def run(
        self,
        plan: ExecutionPlan,
        *,
        cancel: CommitCancellationToken,
        events: RunEventSink,
    ) -> RunResult:
        """Execute an admissible graph and preserve independent group outcomes."""
        self._validate_plan(plan)
        generation: int = self._session.generation
        group_roots: dict[str, Path] = {
            group.group_id: self._session.group_temp(group.group_id) for group in plan.groups
        }
        emitter: RunEventEmitter = RunEventEmitter(self._run_id, events)
        runtime: SchedulerRuntime = SchedulerRuntime(
            plan=plan,
            cancel=cancel,
            emitter=emitter,
            generation=generation,
            store=ArtifactStore(plan.artifacts, group_roots),
            state=create_run_state(plan),
            gate=natural_gate(plan),
            ready=defaultdict(deque),
            executors={},
            futures={},
            submitted=defaultdict(int),
            held=defaultdict(list),
            updates=queue.SimpleQueue(),
            task_by_id={task.task_id: task for task in plan.tasks},
            commit_if_current=lambda action: self._commit_if_current(generation, cancel, action),
        )
        emitter.emit(RunEventKind.RUN_STARTED)
        self._queue_initial(runtime)
        try:
            self._coordinate(runtime)
        finally:
            for executor in runtime.executors.values():
                executor.shutdown(wait=True, cancel_futures=True)
        groups: tuple[GroupResult, ...] = tuple(build_group_result(group.group_id, runtime) for group in plan.groups)
        result: RunResult = RunResult(run_id=self._run_id, groups=groups)
        emitter.emit(RunEventKind.RUN_FINISHED, state=run_result_state(result))
        return result

    def _coordinate(self, runtime: SchedulerRuntime) -> None:
        while not all_tasks_terminal(runtime.state):
            self._drain_updates(runtime)
            if runtime.cancel.is_cancelled():
                self._cancel_unfinished(runtime)
            else:
                self._release_results(runtime)
                self._admit(runtime)
            if not runtime.futures:
                self._release_results(runtime)
                if all_tasks_terminal(runtime.state):
                    break
                msg = "Execution graph stopped before reaching terminal task states"
                raise ExecutionError(msg)
            done, _ = wait(
                tuple(runtime.futures),
                timeout=_COORDINATOR_POLL_S,
                return_when=FIRST_COMPLETED,
            )
            self._drain_updates(runtime)
            for future in sorted(done, key=lambda item: runtime.futures[item].task.task_id):
                submitted_task: SubmittedTask = runtime.futures.pop(future)
                runtime.submitted[submitted_task.resource_key] -= 1
                self._finish_future(future, submitted_task.task, runtime)
        self._drain_updates(runtime)
        self._release_results(runtime)
        self._report_terminal_groups(runtime)

    def _queue_initial(self, runtime: SchedulerRuntime) -> None:
        for task in runtime.plan.tasks:
            if runtime.state.unresolved[task.task_id] == 0:
                queue_task(task, runtime)

    def _admit(self, runtime: SchedulerRuntime) -> None:
        for resource_key in tuple(runtime.ready):
            worker_limit: int = self._limits.worker_limit(resource_key, runtime.plan.settings)
            admission_limit: int = worker_limit + self._limits.max_pending_per_resource
            executor: ThreadPoolExecutor | None = runtime.executors.get(resource_key)
            while runtime.ready[resource_key] and runtime.submitted[resource_key] < admission_limit:
                if executor is None:
                    executor = ThreadPoolExecutor(
                        max_workers=worker_limit,
                        thread_name_prefix=thread_prefix(resource_key),
                    )
                    runtime.executors[resource_key] = executor
                task: PlanTask = runtime.ready[resource_key].popleft()
                snapshot: ArtifactSnapshot = runtime.store.snapshot(task)
                future: Future[TaskResult] = executor.submit(
                    self._execute_task,
                    task,
                    snapshot,
                    runtime.cancel,
                    runtime.updates,
                )
                runtime.futures[future] = SubmittedTask(task, resource_key)
                runtime.submitted[resource_key] += 1

    def _execute_task(
        self,
        task: PlanTask,
        snapshot: ArtifactSnapshot,
        cancel: CancellationToken,
        updates: queue.SimpleQueue[TaskStarted | WorkerNotification],
    ) -> TaskResult:
        updates.put(TaskStarted(task.task_id))
        cancel.raise_if_cancelled()
        progress: TaskProgressSink = QueuedProgressSink(task.task_id, updates)
        return self._handler.execute(task, snapshot, cancel, progress)

    def _finish_future(
        self,
        future: Future[TaskResult],
        task: PlanTask,
        runtime: SchedulerRuntime,
    ) -> None:
        if (
            future.cancelled()
            or runtime.cancel.is_cancelled()
            or not self._session.accepts_generation(runtime.generation)
        ):
            finish_cancelled(task, runtime)
            return
        try:
            result: TaskResult = future.result()
            if runtime.gate is not None and not runtime.gate.can_release(task.group_id):
                runtime.held[task.group_id].append((task, result))
                return
            commit_success(task, result, runtime)
        except Exception as error:  # noqa: BLE001
            if runtime.cancel.is_cancelled() or not self._session.accepts_generation(runtime.generation):
                finish_cancelled(task, runtime)
            else:
                finish_failed(task, error, runtime)

    def _release_results(self, runtime: SchedulerRuntime) -> None:
        if runtime.gate is None:
            self._report_terminal_groups(runtime)
            return
        changed: bool = True
        while changed:
            changed = False
            current: str | None = runtime.gate.current_group
            if current is not None and runtime.held[current]:
                pending: list[tuple[PlanTask, TaskResult]] = runtime.held.pop(current)
                pending.sort(key=lambda item: runtime.plan.tasks.index(item[0]))
                for task, result in pending:
                    try:
                        commit_success(task, result, runtime)
                    except Exception as error:  # noqa: BLE001
                        if runtime.cancel.is_cancelled() or not self._session.accepts_generation(runtime.generation):
                            finish_cancelled(task, runtime)
                        else:
                            finish_failed(task, error, runtime)
                changed = True
            if self._report_terminal_groups(runtime):
                changed = True

    def _report_terminal_groups(self, runtime: SchedulerRuntime) -> bool:
        newly_terminal: tuple[str, ...] = detect_terminal_groups(runtime.plan, runtime.state)
        if runtime.gate is None:
            visible: tuple[str, ...] = newly_terminal
        else:
            released: list[str] = []
            for group_id in newly_terminal:
                released.extend(runtime.gate.skip(group_id))
            visible = tuple(released)
        for group_id in visible:
            if group_id in runtime.state.reported_groups:
                continue
            runtime.state.reported_groups.add(group_id)
            runtime.emitter.emit(
                RunEventKind.GROUP_FINISHED,
                group_id=group_id,
                state=group_event_state(group_id, runtime.state),
            )
        return bool(newly_terminal or visible)

    def _drain_updates(self, runtime: SchedulerRuntime) -> None:
        while True:
            try:
                update: TaskStarted | WorkerNotification = runtime.updates.get_nowait()
            except queue.Empty:
                return
            if isinstance(update, TaskStarted):
                if runtime.state.task_states[update.task_id] is TaskState.QUEUED:
                    runtime.state.task_states[update.task_id] = TaskState.RUNNING
                    runtime.emitter.emit(
                        RunEventKind.TASK_STARTED,
                        group_id=runtime.state.task_groups[update.task_id],
                        task_id=update.task_id,
                        state=TaskState.RUNNING,
                    )
                continue
            task_state: TaskState = runtime.state.task_states[update.task_id]
            if task_state not in {TaskState.QUEUED, TaskState.RUNNING}:
                continue
            event_kind: RunEventKind = {
                WorkerNotificationKind.PROGRESS: RunEventKind.TASK_PROGRESS,
                WorkerNotificationKind.RETRY: RunEventKind.TASK_RETRY,
                WorkerNotificationKind.FALLBACK: RunEventKind.TASK_FALLBACK,
            }[update.kind]
            runtime.emitter.emit(
                event_kind,
                group_id=runtime.state.task_groups[update.task_id],
                task_id=update.task_id,
                state=task_state,
                progress_percent=update.progress_percent,
                message=update.message,
            )

    def _cancel_unfinished(self, runtime: SchedulerRuntime) -> None:
        for tasks in runtime.ready.values():
            tasks.clear()
        for group_items in runtime.held.values():
            for held_task, _ in group_items:
                finish_cancelled(held_task, runtime)
            group_items.clear()
        submitted_futures: tuple[tuple[Future[TaskResult], SubmittedTask], ...] = tuple(runtime.futures.items())
        for future, submitted_task in submitted_futures:
            if not future.cancel():
                continue
            runtime.futures.pop(future)
            runtime.submitted[submitted_task.resource_key] -= 1
            finish_cancelled(submitted_task.task, runtime)
        active_task_ids: frozenset[str] = frozenset(item.task.task_id for item in runtime.futures.values())
        for task_id, task_state in tuple(runtime.state.task_states.items()):
            if task_state not in {TaskState.READY, TaskState.QUEUED} or task_id in active_task_ids:
                continue
            task: PlanTask = runtime.task_by_id[task_id]
            finish_cancelled(task, runtime, message="Cancelled before admission")

    def _validate_plan(self, plan: ExecutionPlan) -> None:
        if not plan.groups:
            msg = "Execution plan must contain at least one group"
            raise ExecutionError(msg)
        if not plan.can_execute:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.PIPELINE_FAILED,
                message="Execution plan contains blocking problems",
                suggestion="Resolve the problems shown in plan preview and try again.",
            )
            raise ExecutionError(context=context)

    def _commit_if_current(
        self,
        generation: int,
        cancel: CommitCancellationToken,
        action: Callable[[], None],
    ) -> bool:
        committed: bool = False

        def commit_if_active() -> None:
            nonlocal committed
            committed = cancel.commit_if_active(action)

        generation_active: bool = self._session.commit_if_generation(generation, commit_if_active)
        return generation_active and committed
