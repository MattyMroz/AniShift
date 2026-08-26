"""Off-thread launchers for every blocking facade call, and the bounded run-event pump."""

from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application import RunEventKind
from anishift.application.events import sanitize_event_message
from anishift.errors import AniShiftError
from anishift.tui.messages import (
    DoctorReported,
    GroupRegistered,
    PlanFailed,
    PlanReady,
    RunFailed,
    RunFinished,
    RunProgressed,
    SetupReported,
    WorkspaceFailed,
    WorkspaceLoaded,
)
from anishift.tui.strings import WORKER_FAILED
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from textual.message import Message

    from anishift.application import (
        AppService,
        AutoPreset,
        AutoPresetDraft,
        ExecutionPlan,
        ExternalAudioRole,
        GroupIntent,
        RunEvent,
        RunResult,
    )

__all__ = [
    "DRAIN_INTERVAL_SECONDS",
    "STATE_EVENT_LIMIT",
    "RunEventPump",
    "WorkerHost",
    "discover",
    "execute",
    "plan_auto",
    "plan_manual",
    "register_external_audio",
    "register_external_subtitle",
    "run_doctor",
    "run_setup",
    "worker_generation",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

DRAIN_INTERVAL_SECONDS: Final[float] = 0.075
"""Seconds between two drains of the run-event pump while a run is active."""

STATE_EVENT_LIMIT: Final[int] = 512
"""Non-terminal state events the pump holds before it drops its oldest one."""

_GENERATION_PREFIX: Final[str] = "generation="
"""Prefix under which a launched worker carries the generation that asked for it."""


class WorkerHost(Protocol):
    """The two shell capabilities a worker launcher needs, and nothing more."""

    def run_worker(
        self,
        work: Callable[[], None],
        *,
        name: str = ...,
        group: str = ...,
        exit_on_error: bool = ...,
        thread: bool = ...,
    ) -> object:
        """Run *work* outside the UI thread."""
        ...

    def post_message(self, message: Message) -> bool:
        """Deliver *message* to the shell from any thread."""
        ...


class RunEventPump:
    """Thread-safe run-event sink that coalesces progress and stays bounded."""

    __slots__ = ("_dropped", "_generation", "_lock", "_progress", "_run_id", "_states", "_terminals")

    def __init__(self, generation: int) -> None:
        """Create the pump of one run of *generation*, before that run emitted anything."""
        self._lock: threading.Lock = threading.Lock()
        self._states: deque[RunEvent] = deque()
        self._progress: dict[tuple[str, str], RunEvent] = {}
        self._terminals: list[RunEvent] = []
        self._dropped: int = 0
        self._run_id: str | None = None
        self._generation: int = generation

    @property
    def generation(self) -> int:
        """View this run belongs to, fixed when the run was started."""
        return self._generation

    @property
    def run_id(self) -> str | None:
        """Identity the run announced, or ``None`` while no event arrived yet."""
        with self._lock:
            return self._run_id

    def emit(self, event: RunEvent) -> None:
        """Accept one event from a worker thread without ever blocking the run."""
        with self._lock:
            if self._run_id is None:
                self._run_id = event.run_id
            self._keep(event)

    def drain(self) -> tuple[RunEvent, ...]:
        """Return every held event in run and sequence order, then forget them."""
        with self._lock:
            held: tuple[RunEvent, ...] = (*self._states, *self._progress.values(), *self._terminals)
            dropped: int = self._dropped
            self._states.clear()
            self._progress.clear()
            self._terminals.clear()
            self._dropped = 0
        if dropped:
            logger.warning("Run events dropped at the pump bound", dropped=dropped, limit=STATE_EVENT_LIMIT)
        return tuple(sorted(held, key=lambda event: (event.run_id, event.sequence)))

    def _keep(self, event: RunEvent) -> None:
        """Store one event under the rule its kind earns."""
        if event.kind is RunEventKind.RUN_FINISHED:
            self._terminals.append(event)
            return
        if event.kind is RunEventKind.TASK_PROGRESS and event.task_id is not None:
            self._coalesce(event, event.task_id)
            return
        if len(self._states) >= STATE_EVENT_LIMIT:
            self._states.popleft()
            self._dropped += 1
        self._states.append(event)

    def _coalesce(self, event: RunEvent, task_id: str) -> None:
        """Keep only the newest progress of one task of one run."""
        key: tuple[str, str] = (event.run_id, task_id)
        current: RunEvent | None = self._progress.get(key)
        if current is None or event.sequence > current.sequence:
            self._progress[key] = event


def worker_generation(name: str) -> int | None:
    """Return the generation a worker name carries, or ``None`` when it carries none."""
    if not name.startswith(_GENERATION_PREFIX):
        return None
    digits: str = name.removeprefix(_GENERATION_PREFIX)
    return int(digits) if digits.isdigit() else None


def discover(host: WorkerHost, service: AppService, *, generation: int) -> None:
    """Inspect the workspace off the UI thread and deliver it or its reason."""
    _deliver(
        host,
        lambda: WorkspaceLoaded(workspace=service.discover(), generation=generation),
        lambda reason: WorkspaceFailed(reason=reason, generation=generation),
        operation="discovery",
        generation=generation,
    )


def register_external_subtitle(  # noqa: PLR0913 - mirrors the facade signature
    host: WorkerHost,
    service: AppService,
    *,
    generation: int,
    group_id: str,
    path: Path,
    declared_language: str | None,
) -> None:
    """Validate one external subtitle off the UI thread and deliver the updated group."""
    _deliver(
        host,
        lambda: GroupRegistered(
            group=service.register_external_subtitle(group_id, path, declared_language),
            generation=generation,
        ),
        lambda reason: WorkspaceFailed(reason=reason, generation=generation),
        operation="register-subtitle",
        generation=generation,
    )


def register_external_audio(  # noqa: PLR0913 - mirrors the facade signature
    host: WorkerHost,
    service: AppService,
    *,
    generation: int,
    group_id: str,
    path: Path,
    role: ExternalAudioRole,
) -> None:
    """Validate one external audio source off the UI thread and deliver the updated group."""
    _deliver(
        host,
        lambda: GroupRegistered(
            group=service.register_external_audio(group_id, path, role),
            generation=generation,
        ),
        lambda reason: WorkspaceFailed(reason=reason, generation=generation),
        operation="register-audio",
        generation=generation,
    )


def plan_auto(
    host: WorkerHost,
    service: AppService,
    *,
    generation: int,
    group_ids: Sequence[str],
    preset: AutoPreset | AutoPresetDraft,
) -> None:
    """Build the automatic plan off the UI thread and deliver it or its reason."""
    _deliver(
        host,
        lambda: PlanReady(plan=service.plan_auto(group_ids, preset), generation=generation),
        lambda reason: PlanFailed(reason=reason, generation=generation),
        operation="plan-auto",
        generation=generation,
    )


def plan_manual(
    host: WorkerHost,
    service: AppService,
    *,
    generation: int,
    intents: Sequence[GroupIntent],
) -> None:
    """Build the manual plan off the UI thread and deliver it or its reason."""
    _deliver(
        host,
        lambda: PlanReady(plan=service.plan_manual(intents), generation=generation),
        lambda reason: PlanFailed(reason=reason, generation=generation),
        operation="plan-manual",
        generation=generation,
    )


def run_doctor(host: WorkerHost, service: AppService, *, generation: int) -> None:
    """Collect every diagnostic off the UI thread and deliver the checks or a reason."""
    _deliver(
        host,
        lambda: DoctorReported(checks=service.doctor(), generation=generation),
        lambda reason: WorkspaceFailed(reason=reason, generation=generation),
        operation="doctor",
        generation=generation,
    )


def run_setup(host: WorkerHost, service: AppService, *, generation: int, force: bool = False) -> None:
    """Install the configured external resources off the UI thread."""
    _deliver(
        host,
        lambda: SetupReported(resources=service.setup(force=force), generation=generation),
        lambda reason: WorkspaceFailed(reason=reason, generation=generation),
        operation="setup",
        generation=generation,
    )


def execute(host: WorkerHost, service: AppService, *, plan: ExecutionPlan, pump: RunEventPump) -> None:
    """Run one accepted plan off the UI thread, buffering its events in *pump*."""
    generation: int = pump.generation

    def work() -> None:
        """Deliver the remaining events and then the terminal answer of this run."""
        try:
            result: RunResult = service.execute(plan, pump)
        except AniShiftError as error:
            _log_failure(error, operation="execution", generation=generation)
            flush(host, pump)
            host.post_message(_execution_failure(pump.run_id, reason=_reason(error), generation=generation))
        else:
            flush(host, pump)
            host.post_message(RunFinished(result=result, run_id=result.run_id, generation=generation))

    _launch(host, work, operation="execution", generation=generation)


def flush(host: WorkerHost, pump: RunEventPump) -> None:
    """Deliver every event still held, so no terminal answer overtakes its progress."""
    events: tuple[RunEvent, ...] = pump.drain()
    run_id: str | None = pump.run_id
    if not events or run_id is None:
        return
    host.post_message(RunProgressed(events=events, run_id=run_id, generation=pump.generation))


def _execution_failure(run_id: str | None, *, reason: str, generation: int) -> Message:
    """Answer a failed execution as a run failure, or as a plan failure before any run."""
    if run_id is None:
        return PlanFailed(reason=reason, generation=generation)
    return RunFailed(reason=reason, run_id=run_id, generation=generation)


def _deliver(
    host: WorkerHost,
    call: Callable[[], Message],
    fail: Callable[[str], Message],
    *,
    operation: str,
    generation: int,
) -> None:
    """Launch *call* off the UI thread, answering a domain failure with *fail*."""

    def work() -> None:
        """Deliver the answer of the facade, or the redacted reason it refused."""
        try:
            message: Message = call()
        except AniShiftError as error:
            _log_failure(error, operation=operation, generation=generation)
            host.post_message(fail(_reason(error)))
        else:
            host.post_message(message)

    _launch(host, work, operation=operation, generation=generation)


def _launch(host: WorkerHost, work: Callable[[], None], *, operation: str, generation: int) -> None:
    """Start *work* in a thread worker tagged with the generation that asked for it."""
    logger.debug("Worker launched", operation=operation, generation=generation)
    host.run_worker(
        work,
        name=f"{_GENERATION_PREFIX}{generation}",
        group=operation,
        exit_on_error=False,
        thread=True,
    )


def _log_failure(error: AniShiftError, *, operation: str, generation: int) -> None:
    """Record one refused operation without its message, its details or its inputs."""
    logger.warning(
        "Worker operation refused",
        operation=operation,
        generation=generation,
        error_class=type(error).__name__,
        error_code=error.context.code.value,
    )


def _reason(error: AniShiftError) -> str:
    """Return the short redacted reason one refused operation may show a user."""
    return sanitize_event_message(error.context.message) or WORKER_FAILED
