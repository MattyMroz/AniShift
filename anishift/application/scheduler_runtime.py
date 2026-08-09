"""Private mutable state and transitions used by the graph coordinator."""

from __future__ import annotations

import queue
import re
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from anishift.application.artifacts import Artifact, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import CommitCancellationToken
from anishift.application.events import RunEventEmitter, RunEventKind, WorkerNotification, sanitize_event_message
from anishift.application.planning import ExecutionPlan, PlanTask, ProcessingOrderPolicy, TaskState
from anishift.application.results import (
    ArtifactSnapshot,
    GroupResult,
    GroupStatus,
    ProducedArtifact,
    RunResult,
    TaskResult,
)
from anishift.application.scheduler_contracts import NaturalOrderGate, normalize_resource_key
from anishift.errors import AniShiftError, ExecutionError

# ── Constants ────────────────────────────────────────────────────────────────

TERMINAL_TASK_STATES: Final[frozenset[TaskState]] = frozenset(
    {TaskState.BLOCKED, TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}
)
"""Task states that require no further scheduler work."""

_VALIDATED_STAGING_KEY: Final[str] = "validated"
"""Produced-artifact metadata flag allowing coordinator-owned publication."""


@dataclass(frozen=True, slots=True)
class TaskStarted:
    """Internal worker-start notification consumed only by the coordinator."""

    task_id: str


@dataclass(frozen=True, slots=True)
class SubmittedTask:
    """Future ownership needed to maintain one resource admission window."""

    task: PlanTask
    resource_key: str


@dataclass(slots=True)
class RunState:
    """Mutable graph state owned exclusively by the coordinator thread."""

    task_states: dict[str, TaskState]
    unresolved: dict[str, int]
    dependants: dict[str, tuple[str, ...]]
    task_groups: dict[str, str]
    task_results: dict[str, TaskResult] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    terminal_groups: set[str] = field(default_factory=set)
    reported_groups: set[str] = field(default_factory=set)


@dataclass(slots=True)
class SchedulerRuntime:
    """Per-run objects shared by small coordinator methods."""

    plan: ExecutionPlan
    cancel: CommitCancellationToken
    emitter: RunEventEmitter
    generation: int
    store: ArtifactStore
    state: RunState
    gate: NaturalOrderGate | None
    ready: dict[str, deque[PlanTask]]
    executors: dict[str, ThreadPoolExecutor]
    futures: dict[Future[TaskResult], SubmittedTask]
    submitted: dict[str, int]
    held: dict[str, list[tuple[PlanTask, TaskResult]]]
    updates: queue.SimpleQueue[TaskStarted | WorkerNotification]
    task_by_id: dict[str, PlanTask]
    commit_if_current: Callable[[Callable[[], None]], bool]


class QueuedProgressSink:
    """Validate task ownership before queueing one worker notification."""

    __slots__ = ("_task_id", "_updates")

    def __init__(self, task_id: str, updates: queue.SimpleQueue[TaskStarted | WorkerNotification]) -> None:
        self._task_id: str = task_id
        self._updates: queue.SimpleQueue[TaskStarted | WorkerNotification] = updates

    def emit(self, notification: WorkerNotification) -> None:
        """Queue a notification belonging to this sink's task."""
        if notification.task_id != self._task_id:
            msg = "Worker notification task ID does not match its running task"
            raise ExecutionError(msg)
        self._updates.put(notification)


class ArtifactStore:
    """Coordinator-owned artifact state hidden from task workers."""

    __slots__ = ("_artifacts", "_group_roots")

    def __init__(self, artifacts: tuple[Artifact, ...], group_roots: dict[str, Path]) -> None:
        self._artifacts: dict[str, Artifact] = {artifact.artifact_id: artifact for artifact in artifacts}
        self._group_roots: dict[str, Path] = dict(group_roots)

    def snapshot(self, task: PlanTask) -> ArtifactSnapshot:
        """Copy ready inputs and missing output descriptors for one task."""
        inputs: dict[str, Artifact] = {}
        for artifact_id in task.requires:
            artifact: Artifact = self._artifacts[artifact_id]
            if artifact.state is not ArtifactState.READY:
                msg = f"Scheduler admitted task with unready artifact: {artifact_id}"
                raise ExecutionError(msg)
            inputs[artifact_id] = artifact
        outputs: dict[str, Artifact] = {artifact_id: self._artifacts[artifact_id] for artifact_id in task.produces}
        return ArtifactSnapshot(inputs, outputs)

    def register(
        self,
        task: PlanTask,
        result: TaskResult,
        commit_if_current: Callable[[Callable[[], None]], bool],
    ) -> TaskResult:
        """Validate every result and commit durable staging files atomically."""
        if result.task_id != task.task_id:
            msg = "Task result ID does not match the completed task"
            raise ExecutionError(msg)
        expected_ids: frozenset[str] = frozenset(task.produces)
        actual_ids: frozenset[str] = frozenset(output.artifact_id for output in result.outputs)
        if actual_ids != expected_ids or len(result.outputs) != len(task.produces):
            msg = "Task result outputs do not match the execution plan"
            raise ExecutionError(msg)
        durable_outputs: tuple[ProducedArtifact, ...] = tuple(
            output
            for output in result.outputs
            if self._artifacts[output.artifact_id].lifetime is ArtifactLifetime.DURABLE
        )
        if durable_outputs and len(result.outputs) != 1:
            msg = "A durable publication task must produce exactly one artifact"
            raise ExecutionError(msg)
        replacements: dict[str, Artifact] = {}
        registered_outputs: list[ProducedArtifact] = []
        for output in result.outputs:
            planned: Artifact = self._artifacts[output.artifact_id]
            artifact, registered = self._validate_output(task, planned, output, commit_if_current)
            replacements[output.artifact_id] = artifact
            registered_outputs.append(registered)
        self._artifacts.update(replacements)
        return TaskResult(result.task_id, tuple(registered_outputs))

    def artifact(self, artifact_id: str) -> Artifact:
        """Return the coordinator's latest immutable artifact value."""
        return self._artifacts[artifact_id]

    def _validate_output(
        self,
        task: PlanTask,
        planned: Artifact,
        output: ProducedArtifact,
        commit_if_current: Callable[[Callable[[], None]], bool],
    ) -> tuple[Artifact, ProducedArtifact]:
        if planned.state is not ArtifactState.MISSING:
            msg = f"Artifact already has a runtime result: {planned.artifact_id}"
            raise ExecutionError(msg)
        try:
            is_file: bool = output.path.is_file()
        except OSError as error:
            msg = "Produced artifact cannot be inspected"
            raise ExecutionError(msg) from error
        if not is_file:
            msg = "Produced artifact file is missing"
            raise ExecutionError(msg)
        resolved_output: Path = output.path.resolve()
        if planned.lifetime is ArtifactLifetime.SOURCE:
            msg = "A task cannot register a source artifact"
            raise ExecutionError(msg)
        group_root: Path = self._group_roots[task.group_id].resolve()
        if resolved_output == group_root or not resolved_output.is_relative_to(group_root):
            msg = "Produced artifact escaped its exact run group scope"
            raise ExecutionError(msg)
        if planned.lifetime is ArtifactLifetime.INTERMEDIATE:
            artifact: Artifact = replace(planned, path=output.path, state=ArtifactState.READY)
            return artifact, output
        destination: Path | None = planned.planned_destination
        if destination is None:
            msg = "Durable artifact lacks its planned destination"
            raise ExecutionError(msg)
        if output.metadata.get(_VALIDATED_STAGING_KEY) is not True:
            msg = "Durable artifact staging file lacks validation confirmation"
            raise ExecutionError(msg)
        destination.parent.mkdir(parents=True, exist_ok=True)

        def publish() -> None:
            output.path.replace(destination)

        try:
            committed: bool = commit_if_current(publish)
        except OSError as error:
            msg = "Durable artifact could not be published atomically"
            raise ExecutionError(msg) from error
        if not committed:
            msg = "Durable artifact publication was cancelled"
            raise ExecutionError(msg)
        metadata: dict[str, str | int | bool] = dict(output.metadata)
        metadata["published"] = True
        registered = ProducedArtifact(output.artifact_id, destination, metadata)
        artifact = replace(planned, path=destination, state=ArtifactState.READY)
        return artifact, registered


def create_run_state(plan: ExecutionPlan) -> RunState:
    """Build dependency counters and reverse edges from a validated plan."""
    task_states: dict[str, TaskState] = dict.fromkeys((task.task_id for task in plan.tasks), TaskState.READY)
    unresolved: dict[str, int] = {task.task_id: len(task.depends_on) for task in plan.tasks}
    task_groups: dict[str, str] = {task.task_id: task.group_id for task in plan.tasks}
    mutable_dependants: dict[str, list[str]] = {task.task_id: [] for task in plan.tasks}
    for task in plan.tasks:
        for dependency_id in task.depends_on:
            mutable_dependants[dependency_id].append(task.task_id)
    dependants: dict[str, tuple[str, ...]] = {
        task_id: tuple(task_ids) for task_id, task_ids in mutable_dependants.items()
    }
    return RunState(task_states, unresolved, dependants, task_groups)


def natural_gate(plan: ExecutionPlan) -> NaturalOrderGate | None:
    """Create the ordered forwarding gate only for strict-natural runs."""
    if plan.settings.processing_order_policy is ProcessingOrderPolicy.READY_FIRST:
        return None
    return NaturalOrderGate(tuple(group.group_id for group in plan.groups))


def queue_task(task: PlanTask, runtime: SchedulerRuntime) -> None:
    """Move one dependency-ready task into its bounded resource queue."""
    runtime.state.task_states[task.task_id] = TaskState.QUEUED
    resource_key: str = normalize_resource_key(task.resource_key)
    runtime.ready[resource_key].append(task)
    runtime.emitter.emit(
        RunEventKind.TASK_QUEUED,
        group_id=task.group_id,
        task_id=task.task_id,
        state=TaskState.QUEUED,
    )


def commit_success(task: PlanTask, result: TaskResult, runtime: SchedulerRuntime) -> None:
    """Register outputs and forward readiness to direct dependants."""
    registered: TaskResult = runtime.store.register(task, result, runtime.commit_if_current)
    runtime.state.task_results[task.task_id] = registered
    runtime.state.task_states[task.task_id] = TaskState.SUCCEEDED
    runtime.emitter.emit(
        RunEventKind.TASK_FINISHED,
        group_id=task.group_id,
        task_id=task.task_id,
        state=TaskState.SUCCEEDED,
    )
    for dependant_id in runtime.state.dependants[task.task_id]:
        runtime.state.unresolved[dependant_id] -= 1
        if runtime.state.unresolved[dependant_id] == 0 and runtime.state.task_states[dependant_id] is TaskState.READY:
            queue_task(runtime.task_by_id[dependant_id], runtime)


def finish_failed(task: PlanTask, error: BaseException, runtime: SchedulerRuntime) -> None:
    """Fail one task and block only its same-group dependency descendants."""
    message: str = public_error(error)
    runtime.state.errors[task.group_id].append(message)
    runtime.state.task_states[task.task_id] = TaskState.FAILED
    runtime.emitter.emit(
        RunEventKind.TASK_FINISHED,
        group_id=task.group_id,
        task_id=task.task_id,
        state=TaskState.FAILED,
        message=message,
    )
    pending: deque[str] = deque(runtime.state.dependants[task.task_id])
    while pending:
        dependant_id: str = pending.popleft()
        dependant_state: TaskState = runtime.state.task_states[dependant_id]
        if dependant_state in TERMINAL_TASK_STATES:
            continue
        dependant: PlanTask = runtime.task_by_id[dependant_id]
        runtime.state.task_states[dependant_id] = TaskState.BLOCKED
        runtime.emitter.emit(
            RunEventKind.TASK_FINISHED,
            group_id=dependant.group_id,
            task_id=dependant_id,
            state=TaskState.BLOCKED,
            message="Blocked by a failed dependency",
        )
        pending.extend(runtime.state.dependants[dependant_id])


def finish_cancelled(
    task: PlanTask,
    runtime: SchedulerRuntime,
    *,
    message: str = "Cancelled",
) -> None:
    """Mark one unfinished task cancelled exactly once."""
    if runtime.state.task_states[task.task_id] in TERMINAL_TASK_STATES:
        return
    runtime.state.task_states[task.task_id] = TaskState.CANCELLED
    runtime.emitter.emit(
        RunEventKind.TASK_FINISHED,
        group_id=task.group_id,
        task_id=task.task_id,
        state=TaskState.CANCELLED,
        message=message,
    )


def detect_terminal_groups(plan: ExecutionPlan, state: RunState) -> tuple[str, ...]:
    """Record groups whose declared task set is fully terminal."""
    newly_terminal: list[str] = []
    for group in plan.groups:
        if group.group_id in state.terminal_groups:
            continue
        if all(state.task_states[task_id] in TERMINAL_TASK_STATES for task_id in group.task_ids):
            state.terminal_groups.add(group.group_id)
            newly_terminal.append(group.group_id)
    return tuple(newly_terminal)


def build_group_result(group_id: str, runtime: SchedulerRuntime) -> GroupResult:
    """Derive one immutable group result from coordinator-owned terminal state."""
    group = next(group for group in runtime.plan.groups if group.group_id == group_id)
    task_results: tuple[TaskResult, ...] = tuple(
        runtime.state.task_results[task_id] for task_id in group.task_ids if task_id in runtime.state.task_results
    )
    products: tuple[ProducedArtifact, ...] = tuple(
        output
        for result in task_results
        for output in result.outputs
        if runtime.store.artifact(output.artifact_id).lifetime is ArtifactLifetime.DURABLE
    )
    task_states: tuple[TaskState, ...] = tuple(runtime.state.task_states[task_id] for task_id in group.task_ids)
    errors: tuple[str, ...] = tuple(runtime.state.errors[group_id])
    if any(task_state is TaskState.CANCELLED for task_state in task_states):
        return GroupResult(group_id, GroupStatus.CANCELLED, task_results, products, (*errors, "Cancelled"))
    if any(task_state in {TaskState.FAILED, TaskState.BLOCKED} for task_state in task_states):
        status: GroupStatus = GroupStatus.PARTIAL if products else GroupStatus.FAILED
        failure_messages: tuple[str, ...] = errors or ("A required task failed",)
        return GroupResult(group_id, status, task_results, products, failure_messages)
    return GroupResult(group_id, GroupStatus.SUCCEEDED, task_results, products)


def group_event_state(group_id: str, state: RunState) -> TaskState:
    """Map terminal task states to the event model's shared state enum."""
    group_states: tuple[TaskState, ...] = tuple(
        task_state for task_id, task_state in state.task_states.items() if state.task_groups[task_id] == group_id
    )
    if any(task_state is TaskState.CANCELLED for task_state in group_states):
        return TaskState.CANCELLED
    failed: bool = any(task_state in {TaskState.FAILED, TaskState.BLOCKED} for task_state in group_states)
    if state.errors[group_id] or failed:
        return TaskState.FAILED
    return TaskState.SUCCEEDED


def run_result_state(result: RunResult) -> TaskState:
    """Map aggregate results to the event model's shared state enum."""
    if result.cancelled:
        return TaskState.CANCELLED
    return TaskState.SUCCEEDED if result.succeeded else TaskState.FAILED


def all_tasks_terminal(state: RunState) -> bool:
    """Return whether no task can produce another coordinator transition."""
    return all(task_state in TERMINAL_TASK_STATES for task_state in state.task_states.values())


def public_error(error: BaseException) -> str:
    """Convert a worker failure to sanitized public text."""
    if isinstance(error, AniShiftError):
        message: str = error.context.message or str(error)
    elif isinstance(error, OSError):
        message = "Task failed while accessing a file"
    else:
        message = str(error) or "Task handler failed unexpectedly"
    return sanitize_event_message(message) or "Task failed"


def thread_prefix(resource_key: str) -> str:
    """Create a stable safe executor thread-name prefix."""
    safe_key: str = re.sub(r"[^a-zA-Z0-9-]+", "-", resource_key).strip("-").casefold()
    return f"anishift-{safe_key or 'worker'}"
