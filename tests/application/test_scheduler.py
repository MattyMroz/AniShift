from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from anishift.application import scheduler as scheduler_module
from anishift.application import scheduler_runtime
from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import CancellationToken, EventCancellationToken, NeverCancelledToken
from anishift.application.events import RunEvent, RunEventKind, WorkerNotification, WorkerNotificationKind
from anishift.application.intents import GroupIntent, ProductIntent, ProductKind, RunMode
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanProblem,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
    stable_topological_order,
)
from anishift.application.results import ArtifactSnapshot, GroupStatus, ProducedArtifact, RunResult, TaskResult
from anishift.application.scheduler import GraphScheduler, NaturalOrderGate, ResourceLimits, TaskProgressSink
from anishift.application.sessions import RunSession
from anishift.errors import ExecutionError, FatalError


@dataclass(frozen=True, slots=True)
class _TaskSpec:
    group_id: str
    task_id: str
    depends_on: tuple[str, ...] = ()
    resource_key: str = "translation:google"
    durable: bool = False


class _CollectingSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []
        self._lock: threading.Lock = threading.Lock()

    def emit(self, event: RunEvent) -> None:
        with self._lock:
            self.events.append(event)


class _FakeHandler:
    def __init__(  # noqa: PLR0913
        self,
        run_root: Path,
        *,
        delays: dict[str, float] | None = None,
        failures: dict[str, Exception] | None = None,
        modes: dict[str, str] | None = None,
        notifications: dict[str, tuple[WorkerNotificationKind, ...]] | None = None,
        ignore_cancel: frozenset[str] = frozenset(),
        barriers: dict[str, threading.Barrier] | None = None,
    ) -> None:
        self.run_root: Path = run_root
        self.delays: dict[str, float] = delays or {}
        self.failures: dict[str, Exception] = failures or {}
        self.modes: dict[str, str] = modes or {}
        self.notifications: dict[str, tuple[WorkerNotificationKind, ...]] = notifications or {}
        self.ignore_cancel: frozenset[str] = ignore_cancel
        self.barriers: dict[str, threading.Barrier] = barriers or {}
        self.calls: list[str] = []
        self.started: dict[str, float] = {}
        self.finished: dict[str, float] = {}
        self.max_active: dict[str, int] = {}
        self._active: dict[str, int] = {}
        self._lock: threading.Lock = threading.Lock()
        self.entered: threading.Event = threading.Event()

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        resource_bucket: str = task.resource_key.casefold()
        with self._lock:
            self.calls.append(task.task_id)
            self.started[task.task_id] = time.monotonic()
            active: int = self._active.get(resource_bucket, 0) + 1
            self._active[resource_bucket] = active
            self.max_active[resource_bucket] = max(self.max_active.get(resource_bucket, 0), active)
        self.entered.set()
        try:
            barrier: threading.Barrier | None = self.barriers.get(task.task_id)
            if barrier is not None:
                barrier.wait(timeout=5)
            for kind in self.notifications.get(task.task_id, ()):
                percentage: int | None = 50 if kind is WorkerNotificationKind.PROGRESS else None
                progress.emit(WorkerNotification(kind, task.task_id, percentage, "worker update"))
            self._wait(task, cancel)
            failure: Exception | None = self.failures.get(task.task_id)
            if failure is not None:
                raise failure
            outputs: tuple[ProducedArtifact, ...] = tuple(
                self._produce(task, artifacts.require_output(artifact_id)) for artifact_id in task.produces
            )
            return TaskResult(task.task_id, outputs)
        finally:
            with self._lock:
                self.finished[task.task_id] = time.monotonic()
                self._active[resource_bucket] -= 1

    def _wait(
        self,
        task: PlanTask,
        cancel: CancellationToken,
    ) -> None:
        delay: float = self.delays.get(task.task_id, 0.0)
        deadline: float = time.monotonic() + delay
        while time.monotonic() < deadline:
            if task.task_id not in self.ignore_cancel:
                cancel.raise_if_cancelled()
            time.sleep(0.002)

    def _produce(self, task: PlanTask, planned: Artifact) -> ProducedArtifact:
        mode: str = self.modes.get(task.task_id, "normal")
        if mode == "wrong_id":
            path: Path = self.run_root / task.group_id / f"{planned.artifact_id}.bin"
            path.write_bytes(b"result")
            return ProducedArtifact("another-artifact", path, {})
        if planned.lifetime is ArtifactLifetime.DURABLE:
            destination: Path | None = planned.planned_destination
            assert destination is not None
            path = self.run_root / task.group_id / f"{planned.artifact_id}{destination.suffix}"
            metadata: dict[str, str | int | bool] = {"validated": mode != "unpublished"}
        else:
            path = self.run_root / task.group_id / f"{planned.artifact_id}.bin"
            metadata = {}
        if mode == "escape":
            path = self.run_root.parent / f"escaped-{planned.artifact_id}.bin"
        if mode != "missing":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"result")
        return ProducedArtifact(planned.artifact_id, path, metadata)

    def wait_finished(self, task_id: str, timeout: float) -> bool:
        deadline: float = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if task_id in self.finished:
                    return True
            time.sleep(0.002)
        return False


def _settings(policy: ProcessingOrderPolicy = ProcessingOrderPolicy.READY_FIRST) -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="google",
        translation_max_retries=3,
        translation_concurrency=2,
        llm_profile_id="gemini",
        llm_max_concurrency=4,
        tts_profile_id="edge",
        tts_max_retries=3,
        tts_group_jobs=3,
        audio_profile_id="eac3",
        composition_profile_id="default",
        processing_order_policy=policy,
    )


def _intent(group_id: str) -> GroupIntent:
    return GroupIntent(
        group_id=group_id,
        mode=RunMode.AUTO,
        products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    )


def _plan(
    tmp_path: Path,
    specs: tuple[_TaskSpec, ...],
    *,
    policy: ProcessingOrderPolicy = ProcessingOrderPolicy.READY_FIRST,
    extra_groups: tuple[str, ...] = (),
    problem: PlanProblem | None = None,
) -> ExecutionPlan:
    group_ids: list[str] = list(dict.fromkeys((*extra_groups, *(spec.group_id for spec in specs))))
    artifacts: list[Artifact] = []
    tasks: list[PlanTask] = []
    output_by_task: dict[str, str] = {}
    for group_id in group_ids:
        source_path: Path = tmp_path / f"{group_id}.source.ass"
        source_path.write_bytes(b"source")
        artifacts.append(
            Artifact(
                artifact_id=f"source-{group_id}",
                group_id=group_id,
                kind=ArtifactKind.SOURCE_SUBTITLES,
                path=source_path,
                state=ArtifactState.READY,
                lifetime=ArtifactLifetime.SOURCE,
                planned_destination=source_path,
            )
        )
    for spec in specs:
        output_id: str = f"output-{spec.task_id}"
        output_by_task[spec.task_id] = output_id
        lifetime: ArtifactLifetime = ArtifactLifetime.DURABLE if spec.durable else ArtifactLifetime.INTERMEDIATE
        destination: Path | None = tmp_path / f"{spec.task_id}.pl.ass" if spec.durable else None
        artifacts.append(
            Artifact(
                artifact_id=output_id,
                group_id=spec.group_id,
                kind=ArtifactKind.FULL_PL,
                path=None,
                state=ArtifactState.MISSING,
                lifetime=lifetime,
                planned_destination=destination,
            )
        )
        required: tuple[str, ...] = (
            tuple(output_by_task[dependency] for dependency in spec.depends_on)
            if spec.depends_on
            else (f"source-{spec.group_id}",)
        )
        tasks.append(
            PlanTask(
                task_id=spec.task_id,
                group_id=spec.group_id,
                kind=TaskKind.PUBLISH_ARTIFACT,
                requires=required,
                produces=(output_id,),
                depends_on=spec.depends_on,
                resource_key=spec.resource_key,
            )
        )
    problems: tuple[PlanProblem, ...] = (problem,) if problem is not None else ()
    groups: tuple[GroupPlan, ...] = tuple(
        GroupPlan(
            group_id,
            _intent(group_id),
            tuple(artifact.artifact_id for artifact in artifacts if artifact.group_id == group_id),
            tuple(task.task_id for task in tasks if task.group_id == group_id),
            tuple(item for item in problems if item.group_id in {None, group_id}),
        )
        for group_id in group_ids
    )
    ordered_tasks: tuple[PlanTask, ...] = stable_topological_order(tasks)
    return ExecutionPlan(groups, tuple(artifacts), ordered_tasks, _settings(policy), problems)


def _limits(settings: RunSettingsSnapshot, *, pending: int = 1) -> ResourceLimits:
    return ResourceLimits.from_settings(
        settings,
        extraction=2,
        audio=2,
        composition=1,
        max_pending_per_resource=pending,
    )


def _run(
    tmp_path: Path,
    plan: ExecutionPlan,
    handler_factory: Callable[[Path], _FakeHandler],
    *,
    cancel: EventCancellationToken | NeverCancelledToken | None = None,
) -> tuple[RunResult, _FakeHandler, _CollectingSink]:
    run_root: Path = tmp_path / "temp" / "run-1"
    sink: _CollectingSink = _CollectingSink()
    token: EventCancellationToken | NeverCancelledToken = cancel or NeverCancelledToken()
    with RunSession(run_root) as session:
        handler: _FakeHandler = handler_factory(run_root)
        scheduler: GraphScheduler = GraphScheduler(
            handler,
            limits=_limits(plan.settings),
            run_id="run-1",
            session=session,
        )
        result: RunResult = scheduler.run(plan, cancel=token, events=sink)
    return result, handler, sink


def test_natural_order_gate_skips_resolved_later_group_without_deadlock() -> None:
    gate = NaturalOrderGate(("group-1", "group-2", "group-3"))

    assert gate.skip("group-2") == ()
    assert gate.current_group == "group-1"
    assert gate.skip("group-1") == ("group-1", "group-2")
    assert gate.can_release("group-3") is True


def test_resource_limits_cap_sapi_and_llm_and_copy_provider_mapping() -> None:
    settings: RunSettingsSnapshot = _settings()
    providers: dict[str, int] = {"Google": 3}
    limits = ResourceLimits(2, providers, 5, 2, 1, 0)
    providers["Google"] = 9

    assert limits.worker_limit("translation:google", settings) == 3
    assert limits.worker_limit("tts:sapi", settings) == 1
    assert limits.worker_limit("llm:gemini", settings) == 4
    with pytest.raises(ValueError, match="non-negative"):
        ResourceLimits(1, {}, 1, 1, 1, -1)


def test_dependent_task_streams_before_another_group_finishes(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "slow-first"),
        _TaskSpec("group-1", "slow-second", ("slow-first",)),
        _TaskSpec("group-2", "fast-first"),
        _TaskSpec("group-2", "fast-second", ("fast-first",)),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs)
    overlap_barrier: threading.Barrier = threading.Barrier(2)

    result, handler, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(
            run_root,
            barriers={"slow-first": overlap_barrier, "fast-second": overlap_barrier},
        ),
    )

    assert result.succeeded is True
    assert handler.started["fast-second"] < handler.finished["slow-first"]


def test_audio_for_one_group_overlaps_tts_for_the_next_group(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "tts-1", resource_key="tts:sapi"),
        _TaskSpec("group-1", "audio-1", ("tts-1",), resource_key="audio"),
        _TaskSpec("group-2", "tts-2", resource_key="tts:sapi"),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs)

    result, handler, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(
            run_root,
            delays={"tts-1": 0.01, "audio-1": 0.08, "tts-2": 0.08},
        ),
    )

    assert result.succeeded is True
    assert handler.started["audio-1"] < handler.finished["tts-2"]
    assert handler.started["tts-2"] < handler.finished["audio-1"]


def test_scheduler_respects_provider_and_sapi_worker_limits(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        *(_TaskSpec("group-1", f"translate-{index}") for index in range(6)),
        *(_TaskSpec("group-1", f"llm-{index}", resource_key="llm:gemini") for index in range(6)),
        *(
            _TaskSpec(
                "group-1",
                f"sapi-{index}",
                resource_key="tts:sapi" if index % 2 == 0 else "tts:SAPI",
            )
            for index in range(3)
        ),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs)
    translation_barrier: threading.Barrier = threading.Barrier(2)
    llm_barrier: threading.Barrier = threading.Barrier(4)
    barriers: dict[str, threading.Barrier] = {
        "translate-0": translation_barrier,
        "translate-1": translation_barrier,
        "llm-0": llm_barrier,
        "llm-1": llm_barrier,
        "llm-2": llm_barrier,
        "llm-3": llm_barrier,
    }

    result, handler, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(
            run_root,
            barriers=barriers,
        ),
    )

    assert result.succeeded is True
    assert handler.max_active["translation:google"] == 2
    assert handler.max_active["llm:gemini"] == 4
    assert handler.max_active["tts:sapi"] == 1


def test_failed_group_does_not_stop_independent_group(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "fails"),
        _TaskSpec("group-1", "blocked", ("fails",), durable=True),
        _TaskSpec("group-2", "succeeds", durable=True),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs)

    result, handler, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(run_root, failures={"fails": FatalError("fatal input")}),
    )

    assert tuple(group.status for group in result.groups) == (GroupStatus.FAILED, GroupStatus.SUCCEEDED)
    assert "blocked" not in handler.calls
    assert (tmp_path / "succeeds.pl.ass").is_file()


def test_overwrite_reports_preserved_product_only_when_publication_fails(tmp_path: Path) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "publish", durable=True),))
    target: Artifact = next(artifact for artifact in plan.artifacts if artifact.lifetime is ArtifactLifetime.DURABLE)
    destination: Path = tmp_path / "publish.pl.ass"
    destination.write_bytes(b"old")
    target = Artifact(
        target.artifact_id,
        target.group_id,
        target.kind,
        target.path,
        target.state,
        target.lifetime,
        target.planned_destination,
        preserved_path=destination,
    )
    plan = ExecutionPlan(
        plan.groups,
        tuple(target if artifact.artifact_id == target.artifact_id else artifact for artifact in plan.artifacts),
        plan.tasks,
        plan.settings,
        plan.problems,
    )

    succeeded, _, _ = _run(tmp_path, plan, _FakeHandler)
    assert succeeded.groups[0].status is GroupStatus.SUCCEEDED
    assert succeeded.groups[0].products
    assert succeeded.groups[0].preserved_products == ()

    destination.write_bytes(b"old-again")
    failed, _, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(run_root, failures={"publish": FatalError("failed")}),
    )
    assert failed.groups[0].status is GroupStatus.FAILED
    assert failed.groups[0].preserved_products[0].path == destination


def test_strict_natural_holds_later_result_and_group_event(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "slow"),
        _TaskSpec("group-1", "slow-next", ("slow",)),
        _TaskSpec("group-2", "fast"),
        _TaskSpec("group-2", "fast-next", ("fast",)),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs, policy=ProcessingOrderPolicy.STRICT_NATURAL)

    result, handler, sink = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(run_root, delays={"slow": 0.08, "fast": 0.01}),
    )

    group_events: tuple[str | None, ...] = tuple(
        event.group_id for event in sink.events if event.kind is RunEventKind.GROUP_FINISHED
    )
    assert result.succeeded is True
    assert handler.finished["fast"] < handler.finished["slow"]
    assert handler.started["fast-next"] >= handler.finished["slow"]
    assert group_events == ("group-1", "group-2")


def test_strict_natural_keeps_later_durable_staging_private(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "slow"),
        _TaskSpec("group-2", "fast-durable", durable=True),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs, policy=ProcessingOrderPolicy.STRICT_NATURAL)
    run_root: Path = tmp_path / "temp" / "run-1"
    destination: Path = tmp_path / "fast-durable.pl.ass"
    sink: _CollectingSink = _CollectingSink()
    with RunSession(run_root) as session:
        handler = _FakeHandler(run_root, delays={"slow": 0.08, "fast-durable": 0.01})
        scheduler = GraphScheduler(handler, limits=_limits(plan.settings), run_id="run-1", session=session)
        captured: list[RunResult] = []
        thread = threading.Thread(
            target=lambda: captured.append(scheduler.run(plan, cancel=NeverCancelledToken(), events=sink))
        )
        thread.start()
        assert handler.wait_finished("fast-durable", 1.0)
        assert destination.exists() is False
        assert handler.wait_finished("slow", 0.005) is False
        thread.join(timeout=2.0)
        assert thread.is_alive() is False

    assert captured[0].succeeded is True
    assert destination.is_file()


def test_cancel_before_admission_executes_no_handler(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (_TaskSpec("group-1", "never"),)
    plan: ExecutionPlan = _plan(tmp_path, specs)
    token: EventCancellationToken = EventCancellationToken()
    token.cancel()

    result, handler, _ = _run(tmp_path, plan, _FakeHandler, cancel=token)

    assert result.cancelled is True
    assert handler.calls == []


def test_cancel_rejects_noncooperative_late_durable_result(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (_TaskSpec("group-1", "late", durable=True),)
    plan: ExecutionPlan = _plan(tmp_path, specs)
    run_root: Path = tmp_path / "temp" / "run-1"
    token: EventCancellationToken = EventCancellationToken()
    sink: _CollectingSink = _CollectingSink()
    with RunSession(run_root) as session:
        handler = _FakeHandler(
            run_root,
            delays={"late": 0.05},
            ignore_cancel=frozenset({"late"}),
        )
        scheduler = GraphScheduler(handler, limits=_limits(plan.settings), run_id="run-1", session=session)
        captured: list[RunResult] = []

        def execute() -> None:
            captured.append(scheduler.run(plan, cancel=token, events=sink))

        thread = threading.Thread(target=execute)
        thread.start()
        assert handler.entered.wait(timeout=1.0)
        token.cancel()
        thread.join(timeout=2.0)
        assert thread.is_alive() is False
        result: RunResult = captured[0]

    assert result.cancelled is True
    assert result.groups[0].task_results == ()
    assert (tmp_path / "late.pl.ass").exists() is False
    assert run_root.exists() is False


@pytest.mark.parametrize("mode", ["missing", "escape", "wrong_id", "unpublished"])
def test_invalid_handler_output_fails_only_its_group(tmp_path: Path, mode: str) -> None:
    specs: tuple[_TaskSpec, ...] = (
        _TaskSpec("group-1", "invalid", durable=mode == "unpublished"),
        _TaskSpec("group-2", "valid", durable=True),
    )
    plan: ExecutionPlan = _plan(tmp_path, specs)

    result, _, _ = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(run_root, modes={"invalid": mode}),
    )

    assert tuple(group.status for group in result.groups) == (GroupStatus.FAILED, GroupStatus.SUCCEEDED)


def test_worker_notifications_become_monotonic_coordinator_events(tmp_path: Path) -> None:
    specs: tuple[_TaskSpec, ...] = (_TaskSpec("group-1", "notify"),)
    plan: ExecutionPlan = _plan(tmp_path, specs)
    notification_kinds: tuple[WorkerNotificationKind, ...] = (
        WorkerNotificationKind.PROGRESS,
        WorkerNotificationKind.RETRY,
        WorkerNotificationKind.FALLBACK,
    )

    _, _, sink = _run(
        tmp_path,
        plan,
        lambda run_root: _FakeHandler(run_root, notifications={"notify": notification_kinds}),
    )

    kinds: tuple[RunEventKind, ...] = tuple(event.kind for event in sink.events)
    sequences: tuple[int, ...] = tuple(event.sequence for event in sink.events)
    assert RunEventKind.TASK_PROGRESS in kinds
    assert RunEventKind.TASK_RETRY in kinds
    assert RunEventKind.TASK_FALLBACK in kinds
    assert sequences == tuple(range(1, len(sequences) + 1))


def test_blocking_plan_is_rejected_before_run_event(tmp_path: Path) -> None:
    problem = PlanProblem("blocked", "Resolve input", "group-1")
    plan: ExecutionPlan = _plan(tmp_path, (), extra_groups=("group-1",), problem=problem)
    sink: _CollectingSink = _CollectingSink()
    run_root: Path = tmp_path / "temp" / "run-1"
    with RunSession(run_root) as session:
        scheduler = GraphScheduler(
            _FakeHandler(run_root),
            limits=_limits(plan.settings),
            run_id="run-1",
            session=session,
        )
        with pytest.raises(ExecutionError, match="blocking"):
            scheduler.run(plan, cancel=NeverCancelledToken(), events=sink)

    assert sink.events == []


def test_executors_shutdown_without_named_thread_leaks(tmp_path: Path) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "work"),))

    result, _, _ = _run(tmp_path, plan, _FakeHandler)

    thread_names: tuple[str, ...] = tuple(thread.name for thread in threading.enumerate())
    assert result.succeeded is True
    assert not any(name.startswith("anishift-") for name in thread_names)


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_coordinator_failure_cancels_workers_before_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "work"),))
    entered: threading.Event = threading.Event()
    observed_cancellation: list[bool] = []

    def wait_for_cancel(self: _FakeHandler, task: PlanTask, cancel: CancellationToken) -> None:
        entered.set()
        deadline: float = time.monotonic() + 1.0
        while not cancel.is_cancelled() and time.monotonic() < deadline:
            time.sleep(0.002)
        observed_cancellation.append(cancel.is_cancelled())
        cancel.raise_if_cancelled()

    def interrupt_wait(*_: object, **__: object) -> None:
        assert entered.wait(timeout=1.0)
        raise failure("coordinator interrupted")

    monkeypatch.setattr(_FakeHandler, "_wait", wait_for_cancel)
    monkeypatch.setattr(scheduler_module, "wait", interrupt_wait)

    with pytest.raises(failure, match="coordinator interrupted"):
        _run(tmp_path, plan, _FakeHandler)

    assert observed_cancellation == [True]


class _LockedDestinationError(PermissionError):
    def __init__(self) -> None:
        super().__init__(13, "target locked")
        self.winerror: int = 32


def test_locked_publication_allows_other_group_to_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: ExecutionPlan = _plan(
        tmp_path,
        (_TaskSpec("group-1", "locked", durable=True), _TaskSpec("group-2", "independent", durable=True)),
    )
    attempted: threading.Event = threading.Event()
    released: threading.Event = threading.Event()
    original_replace: Callable[[Path, Path], Path] = Path.replace
    original_wait: Callable[[_FakeHandler, PlanTask, CancellationToken], None] = _FakeHandler._wait

    def replace(staging: Path, destination: Path) -> Path:
        if destination.name == "locked.pl.ass" and not released.is_set():
            attempted.set()
            raise _LockedDestinationError
        return original_replace(staging, destination)

    def wait_for_attempt(self: _FakeHandler, task: PlanTask, cancel: CancellationToken) -> None:
        if task.task_id == "independent":
            assert attempted.wait(timeout=1.0)
        original_wait(self, task, cancel)

    class ReleasingSink(_CollectingSink):
        def emit(self, event: RunEvent) -> None:
            super().emit(event)
            if event.kind is RunEventKind.GROUP_FINISHED and event.group_id == "group-2":
                released.set()

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(_FakeHandler, "_wait", wait_for_attempt)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRIES", 3)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRY_DELAY_S", 0.01)
    sink: ReleasingSink = ReleasingSink()
    run_root: Path = tmp_path / "temp" / "run-1"
    with RunSession(run_root) as session:
        handler: _FakeHandler = _FakeHandler(run_root)
        scheduler: GraphScheduler = GraphScheduler(
            handler, limits=_limits(plan.settings), run_id="run-1", session=session
        )
        result: RunResult = scheduler.run(plan, cancel=NeverCancelledToken(), events=sink)

    assert result.succeeded
    assert handler.calls.count("locked") == 1
    finished_groups: list[str | None] = [
        event.group_id for event in sink.events if event.kind is RunEventKind.GROUP_FINISHED
    ]
    assert finished_groups == ["group-2", "group-1"]


def test_cancel_during_publication_retry_preserves_existing_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "locked", durable=True),))
    destination: Path = tmp_path / "locked.pl.ass"
    destination.write_bytes(b"existing")
    token: EventCancellationToken = EventCancellationToken()
    original_replace: Callable[[Path, Path], Path] = Path.replace
    attempts: list[Path] = []

    def replace(staging: Path, target: Path) -> Path:
        if target == destination:
            attempts.append(staging)
            raise _LockedDestinationError
        return original_replace(staging, target)

    def cancel_after_attempt(delay: float) -> None:
        token.cancel()

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(time, "sleep", cancel_after_attempt)

    result, _, _ = _run(tmp_path, plan, _FakeHandler, cancel=token)

    assert result.cancelled
    assert len(attempts) == 1
    assert destination.read_bytes() == b"existing"


def test_exhausted_publication_retries_preserve_existing_product(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "locked", durable=True),))
    destination: Path = tmp_path / "locked.pl.ass"
    destination.write_bytes(b"existing")
    attempts: list[Path] = []
    original_replace: Callable[[Path, Path], Path] = Path.replace

    def replace(staging: Path, target: Path) -> Path:
        if target == destination:
            attempts.append(staging)
            raise _LockedDestinationError
        return original_replace(staging, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRIES", 2)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRY_DELAY_S", 0.0)

    result, _, _ = _run(tmp_path, plan, _FakeHandler)

    assert result.groups[0].status is GroupStatus.FAILED
    assert len(attempts) == 3
    assert destination.read_bytes() == b"existing"


@pytest.mark.parametrize("policy", [ProcessingOrderPolicy.READY_FIRST, ProcessingOrderPolicy.STRICT_NATURAL])
def test_publication_retry_releases_dependants_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: ProcessingOrderPolicy,
) -> None:
    plan: ExecutionPlan = _plan(
        tmp_path,
        (_TaskSpec("group-1", "locked", durable=True), _TaskSpec("group-1", "next", ("locked",))),
        policy=policy,
    )
    attempts: list[Path] = []
    original_replace: Callable[[Path, Path], Path] = Path.replace

    def replace(staging: Path, target: Path) -> Path:
        if target.name == "locked.pl.ass":
            attempts.append(staging)
            if len(attempts) == 1:
                raise _LockedDestinationError
        return original_replace(staging, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRY_DELAY_S", 0.0)

    result, handler, _ = _run(tmp_path, plan, _FakeHandler)

    assert result.succeeded
    assert handler.calls == ["locked", "next"]
    assert len(attempts) == 2


def test_publication_retry_rechecks_session_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: ExecutionPlan = _plan(tmp_path, (_TaskSpec("group-1", "locked", durable=True),))
    destination: Path = tmp_path / "locked.pl.ass"
    destination.write_bytes(b"existing")
    attempts: list[Path] = []
    original_replace: Callable[[Path, Path], Path] = Path.replace
    original_commit: Callable[[RunSession, int, Callable[[], None]], bool] = RunSession.commit_if_generation

    def replace(staging: Path, target: Path) -> Path:
        if target == destination:
            attempts.append(staging)
            raise _LockedDestinationError
        return original_replace(staging, target)

    def commit_if_generation(session: RunSession, generation: int, action: Callable[[], None]) -> bool:
        if attempts:
            return False
        return original_commit(session, generation, action)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(RunSession, "commit_if_generation", commit_if_generation)
    monkeypatch.setattr(RunSession, "accepts_generation", lambda session, generation: not attempts)
    monkeypatch.setattr(scheduler_runtime, "_PUBLICATION_LOCK_RETRY_DELAY_S", 0.0)

    result, _, _ = _run(tmp_path, plan, _FakeHandler)

    assert result.cancelled
    assert len(attempts) == 1
    assert destination.read_bytes() == b"existing"
