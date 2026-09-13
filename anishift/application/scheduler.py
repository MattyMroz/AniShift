"""Bounded streaming execution of immutable application task graphs."""

from __future__ import annotations

import queue
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Final

from anishift.application.cancellation import CommitCancellationToken
from anishift.application.events import RunEventKind, RunEventSink, WorkerNotification, WorkerNotificationKind
from anishift.application.intents import RequestOrigin
from anishift.application.planning import ExecutionPlan, PlanTask, TaskState
from anishift.application.results import ArtifactSnapshot, GroupResult, RunResult, TaskResult
from anishift.application.scheduler_contracts import (
    NaturalOrderGate,
    ResourceLimits,
    RunRequest,
    TaskHandler,
    TaskProgressSink,
    extraction_worker_count,
)
from anishift.application.scheduler_runtime import (
    PendingPublication,
    QueuedProgressSink,
    ReadyTask,
    RunUpdate,
    SchedulerRuntime,
    SubmittedTask,
    TaskStarted,
    UpdateChannel,
    all_tasks_terminal,
    build_group_result,
    commit_success,
    create_runtime,
    detect_terminal_groups,
    finish_cancelled,
    finish_failed,
    group_event_state,
    queue_task,
    run_result_state,
    thread_prefix,
)
from anishift.application.sessions import RunSession
from anishift.errors import ErrorCode, ErrorContext, ExecutionError

__all__ = [
    "GraphCoordinator",
    "GraphScheduler",
    "NaturalOrderGate",
    "ResourceLimits",
    "RunHandle",
    "RunRequest",
    "TaskHandler",
    "TaskProgressSink",
]

# ── Constants ────────────────────────────────────────────────────────────────

EXECUTOR_THREAD_CEILING: Final[int] = 100
"""Thread pool size per resource, matching the largest settable limit; admission enforces the real limit."""

_COORDINATOR_THREAD_NAME: Final[str] = "anishift-coordinator"
"""Name of the single thread owning every graph transition."""

_ADMISSIBLE_STATES: Final[frozenset[TaskState]] = frozenset({TaskState.READY, TaskState.QUEUED})
"""Task states that a cancellation must still turn into a terminal state."""

_PROGRESS_EVENT_KINDS: Final[dict[WorkerNotificationKind, RunEventKind]] = {
    WorkerNotificationKind.PROGRESS: RunEventKind.TASK_PROGRESS,
    WorkerNotificationKind.RETRY: RunEventKind.TASK_RETRY,
    WorkerNotificationKind.FALLBACK: RunEventKind.TASK_FALLBACK,
}
"""Public event kind published for every worker notification kind."""


def wait_for_updates(
    condition: threading.Condition,
    timeout: float | None,
    has_work: Callable[[], bool],
) -> bool:
    """Sleep until a wake-up call or deadline; return whether the loop really slept."""
    with condition:
        if has_work():
            return False
        condition.wait(timeout)
        return True


class RunHandle:
    """Caller-side view of one submitted graph and its eventual result."""

    __slots__ = ("_cancel", "_done", "_error", "_result", "run_id")

    def __init__(self, run_id: str, cancel: Callable[[], None]) -> None:
        """Bind one run identity to the callback cancelling its context."""
        self.run_id: str = run_id
        self._cancel: Callable[[], None] = cancel
        self._done: threading.Event = threading.Event()
        self._result: RunResult | None = None
        self._error: BaseException | None = None

    def done(self) -> bool:
        """Return whether this run already produced a result or a failure."""
        return self._done.is_set()

    def result(self, timeout: float | None = None) -> RunResult:
        """Wait for the run outcome, raising its failure or a timeout error."""
        if not self._done.wait(timeout):
            msg = "Workflow run did not finish before the requested timeout"
            raise TimeoutError(msg)
        error: BaseException | None = self._error
        if error is not None:
            raise error
        result: RunResult | None = self._result
        if result is None:
            msg = "Finished workflow run produced no result"
            raise ExecutionError(msg)
        return result

    def cancel(self) -> None:
        """Request cancellation of this run without touching other runs."""
        self._cancel()

    def resolve(self, result: RunResult) -> None:
        """Publish the final result; only the run's owner may call this."""
        self._result = result
        self._done.set()

    def fail(self, error: BaseException) -> None:
        """Publish a coordination failure; only the run's owner may call this."""
        self._error = error
        self._done.set()


class GraphCoordinator:
    """Long-lived owner of independent graph contexts sharing bounded resources."""

    __slots__ = (
        "_background_admission",
        "_closing",
        "_completions",
        "_condition",
        "_contexts",
        "_draining",
        "_executors",
        "_futures",
        "_handles",
        "_inbox",
        "_limits_provider",
        "_ready",
        "_running",
        "_sequence",
        "_signal",
        "_submitted",
        "_thread",
        "_updates",
        "_wakeups",
    )

    def __init__(self, limits_provider: Callable[[], ResourceLimits]) -> None:
        """Prepare shared queues; the coordination thread lives only while work does."""
        self._limits_provider: Callable[[], ResourceLimits] = limits_provider
        self._condition: threading.Condition = threading.Condition()
        self._updates: UpdateChannel = UpdateChannel(self._wake)
        self._completions: queue.SimpleQueue[Future[TaskResult]] = queue.SimpleQueue()
        self._inbox: list[SchedulerRuntime] = []
        self._contexts: dict[str, SchedulerRuntime] = {}
        self._handles: dict[str, RunHandle] = {}
        self._ready: dict[str, list[ReadyTask]] = {}
        self._submitted: dict[str, int] = defaultdict(int)
        self._executors: dict[str, ThreadPoolExecutor] = {}
        self._futures: dict[Future[TaskResult], SubmittedTask] = {}
        self._background_admission: bool = True
        self._closing: bool = False
        self._draining: bool = False
        self._sequence: int = 0
        self._signal: int = 0
        self._wakeups: int = 0
        self._running: bool = False
        self._thread: threading.Thread | None = None

    @property
    def wakeups(self) -> int:
        """Return how often the coordination loop left its sleeping state."""
        with self._condition:
            return self._wakeups

    def submit(self, request: RunRequest) -> RunHandle:
        """Accept one admissible graph and return the handle of its future result."""
        _validate_plan(request.plan)
        with self._condition:
            if self._closing:
                msg = "Graph coordinator no longer accepts work"
                raise ExecutionError(msg)
            if request.run_id in self._handles:
                msg = "Graph coordinator already owns this run ID"
                raise ExecutionError(msg)
            self._sequence += 1
            context: SchedulerRuntime = create_runtime(
                request,
                sequence=self._sequence,
                ready=self._ready,
                updates=self._updates,
            )
            handle = RunHandle(request.run_id, context.cancel.cancel)
            self._handles[request.run_id] = handle
            self._inbox.append(context)
            self._signal += 1
            self._start_locked()
            self._condition.notify_all()
        return handle

    def set_background_admission(self, enabled: bool) -> None:
        """Allow or hold back admission of tasks belonging to background requests."""
        with self._condition:
            self._background_admission = enabled
            self._signal += 1
            self._condition.notify_all()

    def active_run_ids(self) -> tuple[str, ...]:
        """Return every accepted or pending run that has not produced a result."""
        with self._condition:
            return (*self._contexts, *(context.run_id for context in self._inbox))

    def drain(self) -> None:
        """Finish active tasks and pause their remaining graphs without cancelling workers."""
        with self._condition:
            self._closing = True
            self._draining = True
            self._signal += 1
            self._condition.notify_all()

    def close(self, *, wait: bool = True) -> None:
        """Cancel unfinished contexts, close executors, and stop the loop."""
        with self._condition:
            self._closing = True
            targets: tuple[SchedulerRuntime, ...] = (*self._contexts.values(), *self._inbox)
            thread: threading.Thread | None = self._thread
            self._signal += 1
            self._condition.notify_all()
        for context in targets:
            context.cancel.cancel()
        self._wake()
        if wait:
            if thread is not None:
                thread.join()
            self._shutdown_executors()

    def _start_locked(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name=_COORDINATOR_THREAD_NAME, daemon=True)
        self._thread.start()

    def _wake(self) -> None:
        with self._condition:
            self._signal += 1
            self._condition.notify_all()

    def _loop(self) -> None:
        while True:
            try:
                if not self._round():
                    return
            except BaseException as error:  # noqa: BLE001 - the only boundary turning a fault into results
                self._fail_all(error)
                return

    def _round(self) -> bool:
        with self._condition:
            observed: int = self._signal
        self._accept_pending()
        self._apply_updates()
        self._collect_completions()
        self._advance_contexts()
        self._admit()
        if not self._contexts and not self._futures:
            self._shutdown_executors()
            with self._condition:
                if not self._inbox:
                    self._running = False
                    return False
        self._sleep(observed)
        return True

    def _sleep(self, observed: int) -> None:
        timeout: float | None = self._retry_timeout()
        if wait_for_updates(self._condition, timeout, lambda: self._signal != observed):
            with self._condition:
                self._wakeups += 1

    def _retry_timeout(self) -> float | None:
        deadlines: tuple[float, ...] = tuple(
            publication.retry_at
            for context in self._contexts.values()
            for publication in context.pending_publications.values()
        )
        if not deadlines:
            return None
        return max(0.0, min(deadlines) - time.monotonic())

    def _accept_pending(self) -> None:
        with self._condition:
            accepted: tuple[SchedulerRuntime, ...] = tuple(self._inbox)
            self._inbox.clear()
            self._contexts.update({context.run_id: context for context in accepted})
        for context in accepted:
            context.emitter.emit(RunEventKind.RUN_STARTED)
            for task in context.plan.tasks:
                if context.state.unresolved[task.task_id] == 0:
                    queue_task(task, context)

    def _apply_updates(self) -> None:
        for item in self._updates.drain():
            context: SchedulerRuntime | None = self._contexts.get(item.run_id)
            if context is not None:
                self._apply_update(context, item)

    def _apply_update(self, context: SchedulerRuntime, item: RunUpdate) -> None:
        update: TaskStarted | WorkerNotification = item.update
        if isinstance(update, TaskStarted):
            if context.state.task_states[update.task_id] is TaskState.QUEUED:
                context.state.task_states[update.task_id] = TaskState.RUNNING
                context.emitter.emit(
                    RunEventKind.TASK_STARTED,
                    group_id=context.state.task_groups[update.task_id],
                    task_id=update.task_id,
                    state=TaskState.RUNNING,
                )
            return
        task_state: TaskState = context.state.task_states[update.task_id]
        if task_state not in {TaskState.QUEUED, TaskState.RUNNING}:
            return
        context.emitter.emit(
            _PROGRESS_EVENT_KINDS[update.kind],
            group_id=context.state.task_groups[update.task_id],
            task_id=update.task_id,
            state=task_state,
            progress_percent=update.progress_percent,
            message=update.message,
        )

    def _collect_completions(self) -> None:
        finished: list[Future[TaskResult]] = []
        while True:
            try:
                finished.append(self._completions.get_nowait())
            except queue.Empty:
                break
        for future in sorted(finished, key=self._completion_order):
            submitted: SubmittedTask | None = self._futures.pop(future, None)
            if submitted is None:
                continue
            self._submitted[submitted.resource_key] -= 1
            context: SchedulerRuntime | None = self._contexts.get(submitted.run_id)
            if context is not None:
                self._finish_future(future, submitted.task, context)

    def _completion_order(self, future: Future[TaskResult]) -> tuple[str, str]:
        submitted: SubmittedTask | None = self._futures.get(future)
        if submitted is None:
            return "", ""
        return submitted.run_id, submitted.task.task_id

    def _advance_contexts(self) -> None:
        for context in tuple(self._contexts.values()):
            if context.cancel.is_cancelled():
                self._cancel_unfinished(context)
            else:
                self._release_results(context)
                if self._draining:
                    self._pause_pending(context)
            if all_tasks_terminal(context.state):
                self._finish_context(context)
            elif _is_stalled(context):
                message: str = "Execution graph stopped before reaching terminal task states"
                self._fail_context(context, ExecutionError(message))

    def _finish_context(self, context: SchedulerRuntime) -> None:
        self._release_results(context)
        self._report_terminal_groups(context)
        groups: tuple[GroupResult, ...] = tuple(
            build_group_result(group.group_id, context) for group in context.plan.groups
        )
        paused: bool = (
            self._draining
            and not context.cancel.is_cancelled()
            and TaskState.CANCELLED in context.state.task_states.values()
        )
        result: RunResult = RunResult(run_id=context.run_id, groups=groups, paused=paused)
        context.emitter.emit(RunEventKind.RUN_FINISHED, state=run_result_state(result))
        handle: RunHandle | None = self._detach(context.run_id)
        if handle is not None:
            handle.resolve(result)

    def _fail_context(self, context: SchedulerRuntime, error: BaseException) -> None:
        context.cancel.cancel()
        handle: RunHandle | None = self._detach(context.run_id)
        if handle is not None:
            handle.fail(error)

    def _detach(self, run_id: str) -> RunHandle | None:
        self._drop_ready(run_id)
        with self._condition:
            self._contexts.pop(run_id, None)
            return self._handles.pop(run_id, None)

    def _drop_ready(self, run_id: str) -> None:
        for resource_key, entries in self._ready.items():
            self._ready[resource_key] = [entry for entry in entries if entry.run_id != run_id]

    def _admit(self) -> None:
        if not any(self._ready.values()):
            return
        limits: ResourceLimits = replace(
            self._limits_provider(),
            extraction=extraction_worker_count(self._extraction_group_count()),
        )
        with self._condition:
            if self._draining:
                return
            background_admitted: bool = self._background_admission
            for resource_key in tuple(self._ready):
                self._admit_resource(resource_key, limits, background_admitted=background_admitted)

    def _admit_resource(
        self,
        resource_key: str,
        limits: ResourceLimits,
        *,
        background_admitted: bool,
    ) -> None:
        entries: list[ReadyTask] = self._ready[resource_key]
        while entries:
            candidate: ReadyTask | None = self._best_entry(entries, background_admitted=background_admitted)
            if candidate is None:
                return
            context: SchedulerRuntime = self._contexts[candidate.run_id]
            if self._submitted[resource_key] >= limits.worker_limit(resource_key, context.plan.settings):
                return
            entries.remove(candidate)
            self._submit_task(context, candidate.task_id, resource_key)

    def _best_entry(self, entries: list[ReadyTask], *, background_admitted: bool) -> ReadyTask | None:
        admissible: list[ReadyTask] = []
        for entry in tuple(entries):
            context: SchedulerRuntime | None = self._contexts.get(entry.run_id)
            if context is None:
                entries.remove(entry)
                continue
            if background_admitted or not context.automatic:
                admissible.append(entry)
        return min(admissible) if admissible else None

    def _submit_task(self, context: SchedulerRuntime, task_id: str, resource_key: str) -> None:
        task: PlanTask = context.task_by_id[task_id]
        try:
            snapshot: ArtifactSnapshot = context.store.snapshot(task)
        except ExecutionError as error:
            finish_failed(task, error, context)
            # The failure happened after this round's terminal check, so the loop must run again.
            self._wake()
            return
        executor: ThreadPoolExecutor = self._executor(resource_key)
        future: Future[TaskResult] = executor.submit(self._execute_task, context, task, snapshot)
        self._futures[future] = SubmittedTask(context.run_id, task, resource_key)
        self._submitted[resource_key] += 1
        future.add_done_callback(self._on_completed)

    def _executor(self, resource_key: str) -> ThreadPoolExecutor:
        executor: ThreadPoolExecutor | None = self._executors.get(resource_key)
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=EXECUTOR_THREAD_CEILING,
                thread_name_prefix=thread_prefix(resource_key),
            )
            self._executors[resource_key] = executor
        return executor

    def _on_completed(self, future: Future[TaskResult]) -> None:
        self._completions.put(future)
        self._wake()

    def _execute_task(
        self,
        context: SchedulerRuntime,
        task: PlanTask,
        snapshot: ArtifactSnapshot,
    ) -> TaskResult:
        context.updates.put(context.run_id, TaskStarted(task.task_id))
        context.cancel.raise_if_cancelled()
        progress: TaskProgressSink = QueuedProgressSink(task.task_id, context.run_id, context.updates)
        return context.handler.execute(task, snapshot, context.cancel, progress)

    def _extraction_group_count(self) -> int:
        return len(
            {
                (context.run_id, group_id)
                for context in self._contexts.values()
                for group_id in context.extraction_groups
            }
        )

    def _finish_future(
        self,
        future: Future[TaskResult],
        task: PlanTask,
        context: SchedulerRuntime,
    ) -> None:
        if (
            future.cancelled()
            or context.cancel.is_cancelled()
            or not context.session.accepts_generation(context.generation)
        ):
            finish_cancelled(task, context)
            return
        try:
            result: TaskResult = future.result()
            if context.gate is not None and not context.gate.can_release(task.group_id):
                context.held[task.group_id].append((task, result))
                return
            commit_success(task, result, context)
        except Exception as error:  # noqa: BLE001 - one boundary translating any worker fault
            self._finish_error(task, error, context)

    def _finish_error(self, task: PlanTask, error: BaseException, context: SchedulerRuntime) -> None:
        if context.cancel.is_cancelled() or not context.session.accepts_generation(context.generation):
            finish_cancelled(task, context)
        else:
            finish_failed(task, error, context)
        if context.journal is not None and context.journal.failed:
            self._block_uncheckpointed(context)

    def _block_uncheckpointed(self, context: SchedulerRuntime) -> None:
        active: frozenset[str] = frozenset(
            item.task.task_id for item in self._futures.values() if item.run_id == context.run_id
        )
        for task_id, state in tuple(context.state.task_states.items()):
            if task_id not in active and state in {*_ADMISSIBLE_STATES, TaskState.RUNNING}:
                context.state.task_states[task_id] = TaskState.BLOCKED
        context.pending_publications.clear()
        context.held.clear()
        self._drop_ready(context.run_id)

    def _release_results(self, context: SchedulerRuntime) -> None:
        for publication in tuple(context.pending_publications.values()):
            if time.monotonic() >= publication.retry_at:
                self._retry_publication(publication, context)
        if context.gate is None:
            self._report_terminal_groups(context)
            return
        changed: bool = True
        while changed:
            changed = False
            current: str | None = context.gate.current_group
            if current is not None and context.held[current]:
                pending: list[tuple[PlanTask, TaskResult]] = context.held.pop(current)
                pending.sort(key=lambda item: context.task_index[item[0].task_id])
                for task, result in pending:
                    try:
                        commit_success(task, result, context)
                    except Exception as error:  # noqa: BLE001 - one boundary translating any commit fault
                        self._finish_error(task, error, context)
                changed = True
            if self._report_terminal_groups(context):
                changed = True

    def _retry_publication(self, pending: PendingPublication, context: SchedulerRuntime) -> None:
        try:
            commit_success(pending.task, pending.result, context)
        except Exception as error:  # noqa: BLE001 - one boundary translating any publication fault
            context.pending_publications.pop(pending.task.task_id, None)
            self._finish_error(pending.task, error, context)

    def _report_terminal_groups(self, context: SchedulerRuntime) -> bool:
        newly_terminal: tuple[str, ...] = detect_terminal_groups(context.plan, context.state)
        if context.gate is None:
            visible: tuple[str, ...] = newly_terminal
        else:
            released: list[str] = []
            for group_id in newly_terminal:
                released.extend(context.gate.skip(group_id))
            visible = tuple(released)
        for group_id in visible:
            if group_id in context.state.reported_groups:
                continue
            context.state.reported_groups.add(group_id)
            context.emitter.emit(
                RunEventKind.GROUP_FINISHED,
                group_id=group_id,
                state=group_event_state(group_id, context.state),
            )
        return bool(newly_terminal or visible)

    def _cancel_unfinished(self, context: SchedulerRuntime) -> None:
        for pending in context.pending_publications.values():
            finish_cancelled(pending.task, context)
        context.pending_publications.clear()
        self._drop_ready(context.run_id)
        for group_items in context.held.values():
            for held_task, _ in group_items:
                finish_cancelled(held_task, context)
            group_items.clear()
        for future, submitted in tuple(self._futures.items()):
            if submitted.run_id != context.run_id or not future.cancel():
                continue
            if self._futures.pop(future, None) is None:
                continue
            self._submitted[submitted.resource_key] -= 1
            finish_cancelled(submitted.task, context)
        active_task_ids: frozenset[str] = frozenset(
            item.task.task_id for item in self._futures.values() if item.run_id == context.run_id
        )
        for task_id, task_state in tuple(context.state.task_states.items()):
            if task_state not in _ADMISSIBLE_STATES or task_id in active_task_ids:
                continue
            finish_cancelled(context.task_by_id[task_id], context, message="Cancelled before admission")

    def _pause_pending(self, context: SchedulerRuntime) -> None:
        active: frozenset[str] = frozenset(
            item.task.task_id for item in self._futures.values() if item.run_id == context.run_id
        )
        self._drop_ready(context.run_id)
        for task_id, state in tuple(context.state.task_states.items()):
            if state in _ADMISSIBLE_STATES and task_id not in active:
                finish_cancelled(context.task_by_id[task_id], context, message="Paused before admission")

    def _shutdown_executors(self) -> None:
        executors: tuple[ThreadPoolExecutor, ...] = tuple(self._executors.values())
        self._executors.clear()
        for executor in executors:
            executor.shutdown(wait=True, cancel_futures=True)

    def _fail_all(self, error: BaseException) -> None:
        with self._condition:
            targets: tuple[SchedulerRuntime, ...] = (*self._contexts.values(), *self._inbox)
        for context in targets:
            context.cancel.cancel()
        self._shutdown_executors()
        with self._condition:
            handles: tuple[RunHandle, ...] = tuple(self._handles.values())
            self._contexts.clear()
            self._handles.clear()
            self._inbox.clear()
            self._running = False
        for handle in handles:
            handle.fail(error)


class GraphScheduler:
    """Execute one immutable graph through a private short-lived coordinator."""

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
        coordinator = GraphCoordinator(lambda: self._limits)
        try:
            handle: RunHandle = coordinator.submit(
                RunRequest(
                    run_id=self._run_id,
                    plan=plan,
                    session=self._session,
                    handler=self._handler,
                    cancel=cancel,
                    events=events,
                    origin=RequestOrigin.USER,
                )
            )
            return handle.result()
        finally:
            coordinator.close()


def _is_stalled(context: SchedulerRuntime) -> bool:
    if context.pending_publications or any(context.held.values()):
        return False
    return not any(
        task_state in {TaskState.QUEUED, TaskState.RUNNING} for task_state in context.state.task_states.values()
    )


def _validate_plan(plan: ExecutionPlan) -> None:
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
