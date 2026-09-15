"""The one owner of the automation state, its reservations and its processing requests."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from queue import Empty, SimpleQueue
from secrets import token_hex
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from anishift.application.acquisition import (
    CatalogOrder,
    ReleaseChoice,
    SeasonContext,
    series_directory_name,
)
from anishift.application.artifacts import ArtifactKind, ArtifactLifetime, ArtifactState, create_group_id
from anishift.application.cancellation import EventCancellationToken
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    CommandReceipt,
    ManualHandledMarker,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    RefusalReason,
    RequestState,
    Reservation,
    SourceSelection,
    WatchState,
    auto_admissible,
    mark_manual_handled,
    record_command,
    record_request,
    release,
    reserve,
)
from anishift.application.control_payloads import decode_intent
from anishift.application.control_views import RunProgressSnapshot, decode_view, encode_view, preview_plan
from anishift.application.discovery import ArtifactName, classify_artifact, is_derived_product
from anishift.application.events import RunEventKind, failure_code, sanitize_event_message
from anishift.application.inspection import InspectedWorkspace
from anishift.application.intents import (
    AutoPreset,
    ExternalAudioRole,
    GroupIntent,
    RebuildRequest,
    RequestOrigin,
    RunMode,
)
from anishift.application.planner import auto_group_products
from anishift.application.planning import TaskState
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.recovery import RunJournal
from anishift.application.results import GroupResult, GroupStatus, ProducedArtifact, RunResult
from anishift.application.scheduler_runtime import TERMINAL_TASK_STATES
from anishift.application.selection import ready_group_ids
from anishift.application.subscriptions import SubscriptionOrder, subscription_id
from anishift.application.transfers import TransferInspector
from anishift.application.watch import SCAN_INTERVAL_S, WatchLedger, snapshot_sources, source_fingerprint
from anishift.application.workflows import resolve_route
from anishift.config.workspace import run_temp_dir
from anishift.errors import AniShiftError, ExecutionError
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import ControlErrorCode, ControlRequest, ControlResponse
from anishift.services.catalog import TitleCandidate
from anishift.services.torrents.query import EpisodeRange
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from decimal import Decimal

    from anishift.application.acquisition import AcquisitionService, ReleaseChoice
    from anishift.application.control import AutomationPolicy, CommandOutcome, SettingsSnapshot, SourceFingerprint
    from anishift.application.events import RunEvent
    from anishift.application.inspection import InspectedSourceGroup
    from anishift.application.intents import ProductKind
    from anishift.application.planning import ExecutionPlan, RunSettingsSnapshot
    from anishift.application.scheduler import RunHandle
    from anishift.application.service import AppService
    from anishift.application.subscriptions import (
        CheckOutcome,
        Subscription,
        SubscriptionService,
    )
    from anishift.application.watch_state import WatchStateStore

__all__ = ["AutomationOwner"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

OWNER_THREAD_NAME: Final[str] = "anishift-owner"
"""Name of the one thread every command of the resident is performed on."""

IO_THREAD_PREFIX: Final[str] = "anishift-owner-io"
"""Name prefix of the pool the slow input and output of a command runs on."""

IO_WORKERS: Final[int] = 2
"""Slow commands performed beside each other while the owner keeps answering."""

TRANSFER_CHECK_INTERVAL_S: Final[float] = 10.0
"""Delay between shared client reads while accepted transfers need completion proof."""

TRANSFER_BACKOFF_CEILING_S: Final[float] = 300.0
"""Longest delay between shared client reads while reconciliation keeps failing."""

_TRANSFER_BACKOFF_FACTOR: Final[float] = 2.0
"""Multiplier applied to the poll delay after one more failed reconciliation."""

_MAX_CHANGED_PATHS: Final[int] = 4096
"""Pending changed paths retained before falling back to one full reconciliation."""

_FINISHED_PROGRESS_LIMIT: Final[int] = 12
"""Recent completed runs kept in memory for reconnecting progress panels."""

_PANEL_START_GRACE_S: Final[float] = 5.0
"""Time allowed for a launched panel to connect before another tray launch."""

COMMAND_TIMEOUT_S: Final[float] = 300.0
"""Wait for one command before the connection is answered with an internal fault."""

_ID_BYTES: Final[int] = 8
"""Random bytes making one generated run, preview or command identifier unique."""

_UNKNOWN_COMMAND: Final[str] = "The resident does not know this command"
"""Reason returned for a command kind outside the documented set."""

_STALE_INSTANCE: Final[str] = "The resident restarted; refresh the state and try again"
"""Reason returned when a command names an instance that no longer owns the state."""

_STALE_PREVIEW: Final[str] = "The sources changed since the preview; ask for a new one"
"""Reason returned when a preview no longer describes the current sources."""

_UNKNOWN_PREVIEW: Final[str] = "The resident holds no such preview"
"""Reason returned for a preview identifier this instance never issued."""

_REFUSALS: Final[Mapping[RefusalReason, tuple[ControlErrorCode, str]]] = MappingProxyType(
    {
        RefusalReason.GROUP_RESERVED: (
            ControlErrorCode.CONFLICT,
            "Another client holds one of the requested groups",
        ),
        RefusalReason.GROUP_PROCESSING: (
            ControlErrorCode.ALREADY_PROCESSING,
            "The requested group is already being processed",
        ),
        RefusalReason.GROUP_RELOCATING: (
            ControlErrorCode.CONFLICT,
            "The finished group is being moved to the ready folder",
        ),
        RefusalReason.SESSION_CLOSED: (
            ControlErrorCode.REFUSED,
            "The session that sent this command was already closed",
        ),
        RefusalReason.CLIENT_BOUND: (
            ControlErrorCode.CONFLICT,
            "This client identity already belongs to another session",
        ),
        RefusalReason.NOT_RESERVED: (
            ControlErrorCode.REFUSED,
            "Only a client holding the group may register a file for it",
        ),
        RefusalReason.FOREIGN_PREVIEW: (
            ControlErrorCode.CONFLICT,
            "This preview belongs to another client",
        ),
        RefusalReason.NOT_RESUMABLE: (
            ControlErrorCode.REFUSED,
            "The run cannot be resumed; it is unknown, finished or still active",
        ),
    }
)
"""Protocol code and English message of every cause this owner refuses a command for."""

_STATE_NOT_SAVED: Final[str] = "The automation state could not be saved, so nothing changed"
"""Reason returned when the command was abandoned instead of applied unrecorded."""

_NO_ANSWER: Final[str] = "The resident did not finish the command in time"
"""Reason returned when the owner thread was still busy when the budget ran out."""

_COMMAND_FAILED: Final[str] = "The resident could not complete the command"
"""Reason returned when performing one command raised instead of answering."""

_SHUTTING_DOWN: Final[str] = "The resident is shutting down and admits no new work"
"""Reason returned for work requested after a shutdown was accepted."""

_NO_SUBSCRIPTIONS: Final[str] = "This resident was composed without a torrent client"
"""Reason returned for a subscription command with no subscription service behind it."""

_NOT_PLANNABLE: Final[str] = "The sources cannot be planned into an executable run"
"""Reason returned when planning fails or the plan carries a blocking problem."""

_MUTATING_KINDS: Final[frozenset[str]] = frozenset(
    {
        "set_auto",
        "set_directory_auto",
        "reserve",
        "release",
        "start",
        "cancel",
        "shutdown",
        "subscription_enable",
        "subscription_disable",
        "subscription_remove",
        "subscription_add",
        "download",
        "transfer",
    }
)
"""Commands whose outcome is recorded, so repeating an identifier repeats no effect."""

_SLOW_KINDS: Final[frozenset[str]] = frozenset(
    {"discover", "register_external", "preview", "resume_preview", "subscriptions_check", "acquisition", "download"}
)
"""Commands performed on the pool, because they scan the library or reach the network."""

_INSTANCE_CHECKED_KINDS: Final[frozenset[str]] = frozenset({"start", "reserve", "release", "cancel"})
"""Commands a client may only send to the instance it last read the state from."""

_ACTIVE_STATES: Final[frozenset[RequestState]] = frozenset(
    {RequestState.ACCEPTED, RequestState.RUNNING, RequestState.PAUSED}
)
"""Request states that still own their groups."""

_RESULT_STATES: Final[Mapping[GroupStatus, RequestState]] = {
    GroupStatus.SUCCEEDED: RequestState.SUCCEEDED,
    GroupStatus.PARTIAL: RequestState.PARTIAL,
    GroupStatus.FAILED: RequestState.FAILED,
    GroupStatus.CANCELLED: RequestState.CANCELLED,
}
"""Terminal group outcome mapped onto the state one request is recorded with."""

_WORST_FIRST: Final[tuple[RequestState, ...]] = (
    RequestState.CANCELLED,
    RequestState.FAILED,
    RequestState.PARTIAL,
)
"""Order deciding the state of a request whose groups ended differently."""

type Clock = Callable[[], datetime]
"""Source of the moment a command or a record was accepted."""

type Broadcast = Callable[[Mapping[str, object], bool], None]
"""Hands one event and its terminality to every subscriber of the control channel."""


@dataclass(frozen=True, slots=True)
class _Preview:
    """One planned answer a client may turn into a request while its sources hold."""

    preview_id: str
    client_id: str
    plan: ExecutionPlan
    groups: tuple[InspectedSourceGroup, ...]
    fingerprints: Mapping[str, SourceFingerprint]
    products: frozenset[ProductKind]
    origin: RequestOrigin
    source_selection: SourceSelection
    session_id: str | None
    rebuild: RebuildRequest | None
    automatic: bool = False
    file_version: int = 0
    resume_run_id: str | None = None
    recovering: bool = False


@dataclass(slots=True)
class _Command:
    """One command waiting for the owner thread, and the answer it will carry back."""

    request: ControlRequest
    done: threading.Event
    response: ControlResponse | None = None

    def answer(self, response: ControlResponse) -> None:
        """Publish the outcome to the connection thread that is waiting for it."""
        self.response = response
        self.done.set()


@dataclass(frozen=True, slots=True)
class _Completion:
    """One finished request the owner thread has to record."""

    request_id: str
    result: RunResult | None


@dataclass(frozen=True, slots=True)
class _Disconnected:
    session_id: str


@dataclass(frozen=True, slots=True)
class _FilesChanged:
    pass


@dataclass(frozen=True, slots=True)
class _Inspected:
    workspace: InspectedWorkspace | None


class AutomationOwner:
    """Owns the watch state, admits requests and answers every control command."""

    def __init__(  # noqa: PLR0913,PLR0915 - explicit owner state and composition dependencies
        self,
        service: AppService,
        store: WatchStateStore,
        *,
        instance_id: str,
        clock: Clock = lambda: datetime.now(UTC),
        broadcast: Broadcast | None = None,
        open_panel: Callable[[], None] | None = None,
        ready_store: ReadyStore | None = None,
    ) -> None:
        """Load the persisted state and prepare the owner thread and its pool."""
        self._service: AppService = service
        self._store: WatchStateStore = store
        self._instance_id: str = instance_id
        self._clock: Clock = clock
        self._broadcast: Broadcast | None = broadcast
        self._open_panel: Callable[[], None] | None = open_panel
        self._panels: set[str] = set()
        self._panel_opening_at: float = 0.0
        self._state: WatchState = store.load()
        self._restart_requests: tuple[ProcessingRequest, ...] = self._state.requests
        self._run_groups: dict[str, tuple[InspectedSourceGroup, ...]] = {}
        self._ready_store: ReadyStore | None = ready_store
        self._ready_moves: dict[str, ReadyMove] = {
            move.group_id: move for move in (() if ready_store is None else ready_store.pending())
        }
        self._ready_inflight: set[str] = set()
        self._ready_problems: dict[str, str] = {}
        self._recovery_started: bool = False
        self._recovering: bool = False
        service.retain_runs(
            tuple(item.request_id for item in self._state.requests if item.state is not RequestState.SUCCEEDED)
        )
        if self._state.reservations:
            self._state = replace(self._state, reservations=())
            self._save(self._state)
        self._queue: SimpleQueue[
            _Command | _Completion | _Disconnected | _FilesChanged | _Inspected | Callable[[], None] | None
        ] = SimpleQueue()
        self._pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=IO_WORKERS,
            thread_name_prefix=IO_THREAD_PREFIX,
        )
        self._previews: dict[str, _Preview] = {}
        self._previews_lock: threading.Lock = threading.Lock()
        self._source_checks: dict[str, EventCancellationToken] = {}
        self._closed_sessions: set[str] = set()
        self._sessions: set[str] = set()
        self._client_sessions: dict[str, str] = {}
        self._pending: dict[str, frozenset[ProductKind]] = {}
        self._run_results: dict[str, RunResult] = {}
        self._progress_lock: threading.Lock = threading.Lock()
        self._run_views: dict[str, RunProgressSnapshot] = {}
        self._run_events: dict[str, dict[tuple[str, str | None, str | None], RunEvent]] = {}
        self._run_products: dict[str, dict[str, ArtifactKind]] = {}
        self._shutting_down: bool = False
        self._active_io: int = 0
        self._transfers: TransferInspector | None = (
            TransferInspector(service.acquisition, service.workspace_root) if service.acquisition is not None else None
        )
        self._transfers_at: float | None = None
        self._transfers_inspecting: bool = False
        self._transfers_problem: str | None = None
        self._transfers_failure: tuple[str, str] | None = None
        self._transfers_delay: float = TRANSFER_CHECK_INTERVAL_S
        self._subscriptions_at: float | None = None
        self._subscriptions_checking: bool = False
        self._subscriptions_problem: str | None = None
        self._files_lock: threading.Lock = threading.Lock()
        self._changed_paths: set[Path] = set()
        self._reconcile: bool = False
        self._files_queued: bool = False
        self._inspecting: bool = False
        self._inspection_at: float | None = None
        self._library: InspectedWorkspace | None = None
        self._ledger: WatchLedger = WatchLedger()
        self._settle_at: float | None = None
        self._watch_mode: str = "inactive"
        self._fresh_sources: set[Path] = set()
        self._file_version: int = 0
        self._group_versions: dict[str, int] = {}
        self._reconciled_version: int = 0

    def files_changed(self, change: DirectoryChange) -> None:
        """Coalesce filesystem changes into one bounded owner notification."""
        if change.reason == "resume":
            if self._transfers is not None:
                self._transfers.reset_clock()
            self._queue.put(self._schedule_subscriptions)
        paths: set[Path] = {path for path in change.paths if self._watched_path(path)}
        if not paths and not change.reconcile:
            return
        self._invalidate_changed_inputs(paths, reconcile=change.reconcile)
        with self._files_lock:
            if change.reason not in {"transfer_complete", "resume"}:
                self._watch_mode = "polling" if change.reason == "polling_fallback" else "native"
            self._changed_paths.update(paths)
            self._fresh_sources.update(path for path in paths if not is_derived_product(path))
            self._reconcile |= change.reconcile or len(self._changed_paths) > _MAX_CHANGED_PATHS
            if self._reconcile:
                self._changed_paths.clear()
            if self._files_queued or (not self._changed_paths and not self._reconcile):
                return
            self._files_queued = True
        self._queue.put(_FilesChanged())

    def _invalidate_changed_inputs(self, paths: set[Path], *, reconcile: bool) -> None:
        with self._previews_lock:
            self._file_version += 1
            if reconcile:
                self._reconciled_version = self._file_version
            for path in paths:
                relative: Path = path.parent.relative_to(self._service.workspace_root)
                candidate: ArtifactName | None = classify_artifact(path, resolve_route(relative))
                if candidate is not None:
                    self._group_versions[create_group_id(relative, candidate.stem)] = self._file_version
                    continue
                affected: set[str] = {
                    group.group_id
                    for preview in self._previews.values()
                    for group in preview.groups
                    if group.source.directory.is_relative_to(path)
                }
                self._group_versions.update(dict.fromkeys(affected, self._file_version))

    def _watched_path(self, path: Path) -> bool:
        if not path.is_relative_to(self._service.workspace_root):
            return False
        parts: tuple[str, ...] = path.relative_to(self._service.workspace_root).parts
        return not any(part.startswith(".") for part in parts) and (not parts or parts[0].casefold() != "temp")

    @property
    def instance_id(self) -> str:
        """Identity every client must name on a command that owns a group."""
        return self._instance_id

    @property
    def state(self) -> WatchState:
        """The automation state as it was last persisted."""
        return self._state

    def attach_broadcast(self, broadcast: Broadcast) -> None:
        """Publish run events and state changes through *broadcast*."""
        self._broadcast = broadcast

    def handle(self, request: ControlRequest) -> ControlResponse:
        """Queue one command for the owner thread and wait for its answer."""
        command = _Command(request=request, done=threading.Event())
        self._queue.put(command)
        if not command.done.wait(COMMAND_TIMEOUT_S):
            logger.warning("A control command was not answered in time", command_kind=request.kind)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _NO_ANSWER)
        answered: ControlResponse | None = command.response
        return answered if answered is not None else ControlResponse.refused(ControlErrorCode.INTERNAL, _NO_ANSWER)

    def request_shutdown(self) -> None:
        """Ask the owner to stop admitting work and end once the active requests finish."""
        self._queue.put(None)

    def disconnect(self, session_id: str) -> None:
        """Release the editing state owned by a closed control connection."""
        self._queue.put(_Disconnected(session_id))

    def tray_action(self, action: str) -> None:
        """Queue a desktop action without blocking the Windows message thread."""
        self._queue.put(lambda: self._tray_action(action))

    def _tray_action(self, action: str) -> None:
        if action == "open":
            if self._panels:
                self._publish({"event": "panel_open", "payload": {}}, terminal=False)
            elif self._open_panel is not None and time.monotonic() - self._panel_opening_at > _PANEL_START_GRACE_S:
                self._panel_opening_at = time.monotonic()
                self._open_panel()
            return
        kind: str = "set_auto" if action == "toggle_auto" else "shutdown"
        self._perform(
            ControlRequest(
                command_id=f"tray-{token_hex(_ID_BYTES)}",
                kind=kind,
                payload={"enabled": not self._state.policy.auto_enabled} if kind == "set_auto" else {},
            )
        )

    def serve(self) -> None:
        """Run the owner loop until a shutdown drains every active request."""
        threading.current_thread().name = OWNER_THREAD_NAME
        self._restore_provider_locks()
        self._finish_pending_commands()
        self._reconcile_subscription_sources()
        self._service.set_background_admission(self._state.policy.auto_enabled)
        self._schedule_transfers()
        self._schedule_subscriptions()
        self._retry_ready()
        try:
            self._loop()
        finally:
            self._pool.shutdown(wait=True)

    def _loop(self) -> None:
        while True:
            try:
                deadlines: tuple[float, ...] = tuple(
                    deadline
                    for deadline in (self._settle_at, self._transfers_at, self._inspection_at, self._subscriptions_at)
                    if deadline is not None
                )
                timeout: float | None = max(0.0, min(deadlines) - time.monotonic()) if deadlines else None
                item = self._queue.get(timeout=timeout)
            except Empty:
                self._inspect_changes()
                self._refresh_automatic()
                self._poll_transfers()
                self._poll_subscriptions()
                continue
            except KeyboardInterrupt:
                item = None
            if item is None:
                self._begin_shutdown()
            elif isinstance(item, _Completion):
                self._record_completion(item)
                self._refresh_automatic()
            elif isinstance(item, _Disconnected):
                self._release_session(item.session_id)
                self._refresh_automatic()
            elif isinstance(item, _FilesChanged):
                self._inspection_at = None
                self._inspect_changes()
            elif callable(item):
                item()
            elif isinstance(item, _Inspected):
                self._record_inspection(item.workspace)
            else:
                self._dispatch(item)
            self._poll_transfers()
            self._poll_subscriptions()
            if self._drained():
                return

    def _drained(self) -> bool:
        if not self._shutting_down:
            return False
        return not self._pending and not self._service.active_run_ids() and not self._inspecting and not self._active_io

    def _record_inspection(self, workspace: InspectedWorkspace | None) -> None:
        self._inspecting = False
        if workspace is not None:
            self._library = workspace
            with self._files_lock:
                self._fresh_sources.intersection_update(
                    artifact.path for group in workspace.groups for artifact in group.artifacts
                )
                self._changed_paths.update(workspace.pending_paths)
            if not self._recovery_started:
                self._recovery_started = True
                self._recovering = True
                self._active_io += 1
                self._pool.submit(self._restore_runs, self._restart_requests)
            self._refresh_automatic()
            self._publish_state()
            if workspace.pending_paths:
                self._inspection_at = time.monotonic() + SCAN_INTERVAL_S
        self._inspect_changes()

    def _on_owner[T](self, action: Callable[[], T]) -> T:
        future: Future[T] = Future()

        def invoke() -> None:
            try:
                future.set_result(action())
            except Exception as problem:  # noqa: BLE001
                future.set_exception(problem)

        self._queue.put(invoke)
        return future.result()

    def _inspect_changes(self) -> None:
        if self._inspecting or self._shutting_down:
            return
        if self._inspection_at is not None and time.monotonic() < self._inspection_at:
            return
        self._inspection_at = None
        with self._files_lock:
            self._files_queued = False
            if not self._changed_paths and not self._reconcile:
                return
            paths: tuple[Path, ...] | None = None if self._reconcile else tuple(self._changed_paths)
            self._changed_paths.clear()
            self._reconcile = False
        self._inspecting = True
        self._pool.submit(self._inspect_library, paths)

    def _inspect_library(self, paths: tuple[Path, ...] | None) -> None:
        workspace: InspectedWorkspace | None = None
        try:
            workspace = self._service.discover(changed_paths=paths)
        except (AniShiftError, OSError) as problem:
            logger.warning("Library reconciliation failed", error_class=type(problem).__name__)
        finally:
            self._queue.put(_Inspected(workspace))

    def _refresh_automatic(self) -> None:
        self._settle_at = None
        if self._recovering:
            return
        if any(receipt.pending is not None for receipt in self._state.command_receipts):
            return
        workspace: InspectedWorkspace | None = self._library
        if self._shutting_down or not self._state.policy.auto_enabled or workspace is None or not workspace.groups:
            return
        try:
            self._admit_library(workspace)
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Automatic library admission failed", error_class=type(problem).__name__)

    def _admit_library(self, workspace: InspectedWorkspace) -> None:
        preset: AutoPreset = self._service.get_preset(self._service.default_preset_id())
        eligible: tuple[InspectedSourceGroup, ...] = tuple(
            group
            for group in workspace.groups
            if group.group_id not in self._relocating_groups()
            and auto_admissible(
                self._state,
                self._state.policy,
                group.group_id,
                ""
                if group.source.directory == self._service.workspace_root
                else group.source.directory.relative_to(self._service.workspace_root).as_posix(),
                _group_fingerprint(group),
                self._automatic_products(group, preset),
            )
        )
        ready: tuple[str, ...] = self._ledger.candidates(
            InspectedWorkspace(eligible, ()),
            preset,
            time.monotonic(),
            recipes=self._state.recipes,
        )
        self._settle_at = self._ledger.next_check_at
        for group in eligible:
            if group.group_id not in ready:
                continue
            self._start_automatic(group, preset)

    def _automatic_products(self, group: InspectedSourceGroup, preset: AutoPreset) -> frozenset[ProductKind]:
        return auto_group_products(group, preset.products, self._state.recipes).requested_products

    def _start_automatic(self, group: InspectedSourceGroup, preset: AutoPreset) -> None:
        origin: RequestOrigin | None = self._file_origin(group)
        if origin is None:
            return
        plan: ExecutionPlan = self._service.plan_auto((group.group_id,), preset, recipes=self._state.recipes)
        if not plan.can_execute or not plan.tasks:
            return
        preview: _Preview = _Preview(
            preview_id=f"preview-{token_hex(_ID_BYTES)}",
            client_id=self._instance_id,
            plan=plan,
            groups=(group,),
            fingerprints={group.group_id: _group_fingerprint(group)},
            products=self._automatic_products(group, preset),
            origin=origin,
            source_selection=SourceSelection.AUTO,
            session_id=None,
            rebuild=None,
            automatic=True,
        )
        command: ControlRequest = ControlRequest(command_id=f"auto-{token_hex(_ID_BYTES)}", kind="start", payload={})
        response: ControlResponse = self._admit(command, preview, (group.group_id,), self._instance_id)
        if response.ok:
            self._ledger.mark_started((group.group_id,))
            with self._files_lock:
                self._fresh_sources.difference_update(artifact.path for artifact in group.artifacts)

    def _file_origin(self, group: InspectedSourceGroup) -> RequestOrigin | None:
        paths: set[Path | None] = {artifact.path for artifact in group.artifacts}
        for acquisition in reversed(self._state.acquisitions):
            directory: Path = self._service.workspace_root / acquisition.directory
            matches: bool = (
                any(directory / name in paths for name in acquisition.required_files)
                if acquisition.required_files
                else any(path is not None and path.is_relative_to(directory) for path in paths)
            )
            if not matches:
                continue
            return acquisition.origin if acquisition.state is AcquisitionState.COMPLETE else None
        with self._files_lock:
            return RequestOrigin.USER if self._fresh_sources.intersection(paths) else RequestOrigin.BACKGROUND

    def _dispatch(self, command: _Command) -> None:
        request: ControlRequest = command.request
        if request.kind not in {"status", "shutdown"} and not self._finish_pending_commands():
            command.answer(ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED))
            return
        unbound: ControlResponse | None = self._bind_session(request)
        if unbound is not None:
            command.answer(unbound)
            return
        receipt: CommandReceipt | None = self._receipt(request)
        if receipt is not None:
            command.answer(ControlResponse.succeeded(dict(receipt.outcome)))
            return
        if request.kind in _INSTANCE_CHECKED_KINDS and request.instance_id not in {None, self._instance_id}:
            command.answer(ControlResponse.refused(ControlErrorCode.STALE_INSTANCE, _STALE_INSTANCE))
            return
        if request.kind in _SLOW_KINDS:
            if self._shutting_down:
                command.answer(ControlResponse.refused(ControlErrorCode.REFUSED, _SHUTTING_DOWN))
                return
            self._active_io += 1
            self._pool.submit(self._answer_slow, command)
            return
        self._answer(command)

    def _answer_slow(self, command: _Command) -> None:
        try:
            self._answer(command)
        finally:
            self._queue.put(self._finish_io)

    def _finish_io(self) -> None:
        self._active_io -= 1
        self._schedule_subscriptions()

    def _bind_session(self, request: ControlRequest) -> ControlResponse | None:
        if request.session_id is None:
            return None
        client_id: str | None = _text(request.payload, "client_id")
        with self._previews_lock:
            if request.session_id in self._closed_sessions:
                return _refuse(RefusalReason.SESSION_CLOSED)
            self._sessions.add(request.session_id)
            if client_id is None:
                return None
            if self._client_sessions.get(client_id) not in {None, request.session_id}:
                return _refuse(RefusalReason.CLIENT_BOUND)
            self._client_sessions[client_id] = request.session_id
        return None

    def _release_session(self, session_id: str) -> None:
        self._panels.discard(session_id)
        with self._previews_lock:
            self._sessions.discard(session_id)
            self._closed_sessions.add(session_id)
            token: EventCancellationToken | None = self._source_checks.pop(session_id, None)
            if token is not None:
                token.cancel()
            client_ids: set[str] = {
                client for client, session in self._client_sessions.items() if session == session_id
            }
            for client_id in client_ids:
                self._client_sessions.pop(client_id)
            self._previews = {
                key: preview for key, preview in self._previews.items() if preview.session_id != session_id
            }
        reservations: tuple[Reservation, ...] = tuple(
            item for item in self._state.reservations if item.client_id not in client_ids
        )
        if reservations != self._state.reservations:
            self._save(replace(self._state, reservations=reservations))

    def _answer(self, command: _Command) -> None:
        try:
            command.answer(self._perform(command.request))
        except Exception:  # noqa: BLE001 - the owner must survive any single faulty command
            logger.warning("A control command failed", command_kind=command.request.kind)
            receipt: CommandReceipt | None = self._receipt(command.request)
            if command.request.kind == "start" and receipt is not None:
                command.answer(ControlResponse.succeeded(dict(receipt.outcome)))
            else:
                command.answer(ControlResponse.refused(ControlErrorCode.INTERNAL, _COMMAND_FAILED))

    def _perform(self, request: ControlRequest) -> ControlResponse:  # noqa: C901, PLR0911, PLR0912
        match request.kind:
            case "status":
                return ControlResponse.succeeded(self._status())
            case "panel_attach":
                if request.session_id is None:
                    return _invalid("A panel requires a connected session")
                self._panels.add(request.session_id)
                return ControlResponse.succeeded({"attached": True})
            case "ready_retry":
                for result in tuple(self._run_results.values()):
                    if result.succeeded:
                        self._prepare_ready(result)
                self._retry_ready()
                return ControlResponse.succeeded({"pending": len(self._ready_moves)})
            case "set_auto":
                return self._set_auto(request)
            case "set_directory_auto":
                return self._set_directory_auto(request)
            case "reserve":
                return self._reserve(request)
            case "release":
                return self._release(request)
            case "discover":
                return ControlResponse.succeeded(encode_view(self._service.discover()))
            case "register_external":
                return self._register_external(request)
            case "preview":
                return self._preview(request)
            case "resume_preview":
                return self._resume_preview(request)
            case "run_result":
                return self._run_result(request)
            case "run_progress":
                run_id: str = str(request.payload.get("run_id", ""))
                with self._progress_lock:
                    view: RunProgressSnapshot | None = self._run_views.get(run_id)
                    if view is None:
                        return _invalid("The run progress is no longer available")
                    events: tuple[RunEvent, ...] = tuple(
                        sorted(
                            self._run_events[run_id].values(),
                            key=lambda event: event.sequence,
                        )
                    )
                    return ControlResponse.succeeded(encode_view(replace(view, events=events)))
            case "start":
                return self._start(request)
            case "cancel":
                return self._cancel(request)
            case "reload_settings":
                return self._reload_settings()
            case "shutdown":
                return self._shutdown(request)
            case "acquisition":
                return self._acquisition_command(request)
            case "download":
                return self._download_command(request)
            case "transfer":
                return self._transfer_command(request)
            case kind if kind.startswith("subscription"):
                return self._subscription_command(request)
            case _:
                return ControlResponse.refused(ControlErrorCode.UNKNOWN_COMMAND, _UNKNOWN_COMMAND)

    # ── Policy ────────────────────────────────────────────────────────────────

    def _status(self) -> dict[str, object]:
        policy = self._state.policy
        acquisition: AcquisitionService | None = self._service.acquisition
        return {
            "instance_id": self._instance_id,
            "pid": os.getpid(),
            "run_progress": self._progress_views(),
            "recovery_problems": [
                {"run_id": request.request_id, "group_ids": list(request.group_ids), "problem": request.problem}
                for request in self._state.requests
                if request.problem is not None
            ],
            "auto_enabled": policy.auto_enabled,
            "pending_commands": [
                {"command_id": receipt.command_id, "kind": receipt.pending}
                for receipt in self._state.command_receipts
                if receipt.pending is not None
            ],
            "watch_mode": self._watch_mode,
            "library_groups": 0 if self._library is None else len(self._library.groups),
            "directory_exceptions": dict(policy.directory_exceptions),
            "requests": [
                {
                    "request_id": request.request_id,
                    "origin": request.origin.value,
                    "source_selection": request.source_selection.value,
                    "state": request.state.value,
                    "group_ids": list(request.group_ids),
                }
                for request in self._state.requests
                if request.state in _ACTIVE_STATES
            ],
            "reservations": [
                {"group_id": item.group_id, "client_id": item.client_id} for item in self._state.reservations
            ],
            "subscriptions": self._subscription_counts(),
            "subscriptions_problem": self._subscriptions_problem,
            "http_requests": (
                acquisition.request_control.counts()
                if acquisition is not None and acquisition.request_control is not None
                else []
            ),
            "provider_locks": [
                {"provider": item.provider, "until": item.until, "reason": item.reason}
                for item in self._state.provider_locks
                if datetime.fromisoformat(item.until) > self._clock()
            ],
            "acquisitions": [
                {
                    "operation_id": item.operation_id,
                    "info_hash": item.info_hash,
                    "directory": item.directory,
                    "action": item.requested_action,
                    "action_pending": item.action_pending,
                    "problem": item.problem,
                    "subscription_id": item.subscription_id,
                    "episode": item.episode,
                    "state": item.state.value,
                    "stalled": self._transfers is not None and item.info_hash in self._transfers.stalled,
                }
                for item in self._state.acquisitions
            ],
            "transfers": [
                {"info_hash": item.info_hash, "name": item.name, "progress": item.progress, "state": item.state}
                for item in (() if self._transfers is None else self._transfers.snapshot())
            ],
            "transfers_problem": self._transfers_problem,
            "relocations": [
                {
                    "group_id": group_id,
                    "name": Path(self._ready_moves[group_id].files[0].source).name
                    if group_id in self._ready_moves and self._ready_moves[group_id].files
                    else group_id,
                    "problem": self._ready_problems.get(group_id),
                }
                for group_id in sorted(self._ready_moves.keys() | self._ready_problems.keys())
            ],
            "library": []
            if self._library is None
            else [
                {
                    "group_id": group.group_id,
                    "name": group.source.stem,
                    "directory": group.source.directory.relative_to(self._service.workspace_root).as_posix(),
                    "products": [{"kind": item.kind.value, "state": item.state.value} for item in group.artifacts],
                }
                for group in self._library.groups
            ],
            "shutting_down": self._shutting_down,
            "updated_at": self._now(),
        }

    def _set_auto(self, request: ControlRequest) -> ControlResponse:
        enabled: bool | None = _flag(request.payload, "enabled")
        if enabled is None:
            return _invalid("A switch command needs an `enabled` flag")
        policy = replace(self._state.policy, auto_enabled=enabled)
        outcome: dict[str, str | int | bool | None] = {"auto_enabled": enabled}
        refusal: ControlResponse | None = self._commit(request, replace(self._state, policy=policy), outcome)
        if refusal is not None:
            return refusal
        self._service.set_background_admission(enabled)
        self._refresh_automatic()
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _set_directory_auto(self, request: ControlRequest) -> ControlResponse:
        directory: str | None = _text(request.payload, "directory", allow_empty=True)
        exception: object = request.payload.get("enabled")
        if directory is None or (exception is not None and not isinstance(exception, bool)):
            return _invalid("A directory exception needs a `directory` and a boolean or null `enabled`")
        exceptions: dict[str, bool] = dict(self._state.policy.directory_exceptions)
        if exception is None:
            exceptions.pop(directory, None)
        else:
            exceptions[directory] = exception
        policy = replace(self._state.policy, directory_exceptions=exceptions)
        outcome: dict[str, str | int | bool | None] = {"directory": directory, "enabled": exception}
        refusal: ControlResponse | None = self._commit(request, replace(self._state, policy=policy), outcome)
        if refusal is not None:
            return refusal
        self._refresh_automatic()
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    # ── Reservations ──────────────────────────────────────────────────────────

    def _reserve(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        group_ids: tuple[str, ...] | None = _identifiers(request.payload, "group_ids")
        if client_id is None or group_ids is None:
            return _invalid("A reservation needs a `client_id` and `group_ids`")
        moment: str = self._now()
        candidate: WatchState = self._state
        for group_id in group_ids:
            held: WatchState | None = reserve(
                candidate,
                Reservation(
                    group_id=group_id,
                    fingerprint=self._previewed_fingerprint(group_id),
                    client_id=client_id,
                    reserved_at=moment,
                ),
            )
            if held is None:
                return _reservation_refusal(candidate, group_id, client_id)
            candidate = held
        outcome: dict[str, str | int | bool | None] = {"reserved": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    def _release(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        group_ids: tuple[str, ...] | None = _identifiers(request.payload, "group_ids")
        if client_id is None or group_ids is None:
            return _invalid("A release needs a `client_id` and `group_ids`")
        candidate: WatchState = self._state
        for group_id in group_ids:
            candidate = release(candidate, group_id, client_id)
        with self._previews_lock:
            self._previews = {
                key: preview
                for key, preview in self._previews.items()
                if preview.client_id != client_id or not set(group_ids).intersection(preview.fingerprints)
            }
        outcome: dict[str, str | int | bool | None] = {"released": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        if refusal is None:
            self._refresh_automatic()
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    # ── Preview and start ─────────────────────────────────────────────────────

    def _resume_preview(self, request: ControlRequest) -> ControlResponse:
        group_ids: tuple[str, ...] | None = _identifiers(request.payload, "group_ids")
        if not group_ids:
            return _invalid("A resume preview needs selected groups")
        saved: ProcessingRequest | None = self._on_owner(
            lambda: next(
                (
                    item
                    for item in reversed(self._state.requests)
                    if set(item.group_ids) == set(group_ids)
                    and item.state in {RequestState.PARTIAL, RequestState.FAILED, RequestState.PAUSED}
                    and item.request_id not in self._service.active_run_ids()
                ),
                None,
            )
        )
        if saved is None:
            return _invalid("No unfinished run matches the selected scope")
        return self._preview(
            replace(
                request,
                payload={
                    **request.payload,
                    "resume_run_id": saved.request_id,
                    "source_selection": saved.source_selection.value,
                    "rebuild": encode_view(saved.rebuild) if saved.rebuild is not None else None,
                },
            )
        )

    def _register_external(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        group_id: str | None = _text(request.payload, "group_id")
        path: str | None = _text(request.payload, "path")
        if client_id is None or group_id is None or path is None:
            return _invalid("External registration needs a client, a group and a path")
        if not self._on_owner(
            lambda: any(item.group_id == group_id and item.client_id == client_id for item in self._state.reservations)
        ):
            return _refuse(RefusalReason.NOT_RESERVED)
        token: EventCancellationToken = EventCancellationToken()
        identity: str = request.session_id or client_id
        with self._previews_lock:
            if identity in self._closed_sessions:
                return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
            self._source_checks[identity] = token
        try:
            return self._register_source(request, group_id, Path(path), token)
        finally:
            with self._previews_lock:
                self._source_checks.pop(identity, None)

    def _register_source(
        self, request: ControlRequest, group_id: str, path: Path, token: EventCancellationToken
    ) -> ControlResponse:
        updated: InspectedSourceGroup
        if request.payload.get("kind") == "subtitle":
            language: str | None = _text(request.payload, "language")
            updated = self._service.register_external_subtitle(group_id, path, language, cancel=token)
        elif request.payload.get("kind") == "audio":
            role: ExternalAudioRole = ExternalAudioRole(str(request.payload.get("role")))
            updated = self._service.register_external_audio(group_id, path, role, cancel=token)
        else:
            return _invalid("External registration needs a subtitle or audio kind")
        with self._previews_lock:
            self._previews = {
                key: preview for key, preview in self._previews.items() if group_id not in preview.fingerprints
            }
        return ControlResponse.succeeded(encode_view(updated))

    def _preview(self, request: ControlRequest) -> ControlResponse:
        with self._previews_lock:
            version: int = self._file_version
        client_id: str | None = _text(request.payload, "client_id")
        origin: RequestOrigin | None = _origin(request.payload)
        selection: SourceSelection | None = _selection(request.payload)
        if client_id is None or origin is None or selection is None:
            return _invalid("A preview needs a `client_id`, a known `origin` and `source_selection`")
        planned: tuple[ExecutionPlan, tuple[InspectedSourceGroup, ...], RebuildRequest | None] | None = self._plan(
            request,
            selection,
        )
        if planned is None:
            return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, _NOT_PLANNABLE)
        plan, groups, rebuild = planned
        preview = _Preview(
            preview_id=f"preview-{token_hex(_ID_BYTES)}",
            client_id=client_id,
            plan=plan,
            groups=groups,
            fingerprints={group.group_id: _group_fingerprint(group) for group in groups},
            products=frozenset(
                product for group in plan.groups for product in group.intent.products.requested_products
            ),
            origin=origin,
            source_selection=selection,
            session_id=request.session_id,
            rebuild=rebuild,
            file_version=version,
            resume_run_id=_text(request.payload, "resume_run_id"),
        )
        with self._previews_lock:
            if request.session_id is not None and request.session_id not in self._sessions:
                return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
            if self._preview_changed(preview):
                return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
            self._previews = {key: value for key, value in self._previews.items() if value.client_id != client_id}
            self._previews[preview.preview_id] = preview
        return ControlResponse.succeeded(
            {
                "preview_id": preview.preview_id,
                "instance_id": self._instance_id,
                "can_execute": plan.can_execute,
                "groups": _product_projection(plan),
                "preview": encode_view(preview_plan(plan, preview.preview_id, self._instance_id)),
            }
        )

    def _plan(
        self,
        request: ControlRequest,
        selection: SourceSelection,
    ) -> tuple[ExecutionPlan, tuple[InspectedSourceGroup, ...], RebuildRequest | None] | None:
        try:
            payload: Mapping[str, object] = request.payload
            workspace: InspectedWorkspace = self._service.discover()
            resume_id: str | None = _text(payload, "resume_run_id")
            if resume_id is not None:
                if self._on_owner(lambda: resume_id in self._service.active_run_ids()):
                    return None
                journal: RunJournal = RunJournal.load(self._store.run_path(resume_id))
                selected: dict[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
                if set(_identifiers(payload, "group_ids") or ()) != {group.group_id for group in journal.plan.groups}:
                    return None
                rebuild: RebuildRequest | None = (
                    decode_intent(RebuildRequest, payload["rebuild"]) if payload.get("rebuild") is not None else None
                )
                return journal.plan, tuple(selected[group.group_id] for group in journal.plan.groups), rebuild
            registrations: tuple[dict[str, object], ...] = _external_sources(payload)
            for entry in registrations:
                registered: ControlResponse = self._register_external(
                    replace(request, payload={**entry, "client_id": payload.get("client_id")})
                )
                if not registered.ok:
                    return None
            if registrations:
                workspace = self._service.discover()
            groups: tuple[InspectedSourceGroup, ...] = _requested_groups(workspace, payload)
            rebuild = decode_intent(RebuildRequest, payload["rebuild"]) if payload.get("rebuild") is not None else None
            plan: ExecutionPlan = self._plan_selection(payload, groups, selection, rebuild)
        except (AniShiftError, OSError, KeyError, TypeError, ValueError) as problem:
            logger.warning("A preview could not be planned", error_class=type(problem).__name__)
            return None
        return plan, groups, rebuild

    def _plan_selection(
        self,
        payload: Mapping[str, object],
        groups: tuple[InspectedSourceGroup, ...],
        selection: SourceSelection,
        rebuild: RebuildRequest | None,
    ) -> ExecutionPlan:
        overrides: object = payload.get("overrides", {})
        if not isinstance(overrides, Mapping):
            msg = "Run setting overrides must be an object"
            raise TypeError(msg)
        if selection is SourceSelection.MANUAL:
            entries: object = payload.get("intents")
            if not isinstance(entries, list) or rebuild is not None:
                msg = "Manual selection requires group intents and cannot carry Auto rebuilds"
                raise ValueError(msg)
            intents: tuple[GroupIntent, ...] = tuple(decode_intent(GroupIntent, item) for item in entries)
            if {intent.group_id for intent in intents} != {group.group_id for group in groups} or any(
                intent.mode is not RunMode.MANUAL for intent in intents
            ):
                msg = "Manual intents must match the selected groups"
                raise ValueError(msg)
            return self._service.plan_manual(intents, overrides=overrides)
        if "intents" in payload:
            msg = "Automatic selection cannot carry manual intents"
            raise ValueError(msg)
        preset_id: str | None = _text(payload, "preset_id")
        preset: AutoPreset = (
            decode_intent(AutoPreset, payload["preset"])
            if "preset" in payload
            else self._service.get_preset(preset_id or self._service.default_preset_id())
        )
        return self._service.plan_auto(
            tuple(group.group_id for group in groups),
            preset,
            rebuild=rebuild,
            overrides=overrides,
            recipes=self._state.recipes,
        )

    def _start(self, request: ControlRequest) -> ControlResponse:
        if self._shutting_down:
            return ControlResponse.refused(ControlErrorCode.REFUSED, _SHUTTING_DOWN)
        client_id: str | None = _text(request.payload, "client_id")
        preview_id: str | None = _text(request.payload, "preview_id")
        if client_id is None or preview_id is None:
            return _invalid("A start needs a `client_id` and a `preview_id`")
        with self._previews_lock:
            preview: _Preview | None = self._previews.get(preview_id)
        if preview is not None and preview.session_id != request.session_id:
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
        refusal: ControlResponse | None = self._unstartable(preview, client_id)
        if refusal is not None or preview is None:
            return refusal if refusal is not None else _invalid(_UNKNOWN_PREVIEW)
        return self._admit(request, preview, tuple(group.group_id for group in preview.groups), client_id)

    def _unstartable(self, preview: _Preview | None, client_id: str) -> ControlResponse | None:
        if preview is None:
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _UNKNOWN_PREVIEW)
        if preview.client_id != client_id:
            return _refuse(RefusalReason.FOREIGN_PREVIEW)
        with self._previews_lock:
            changed: bool = self._preview_changed(preview)
        if not preview.plan.can_execute:
            return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, _NOT_PLANNABLE)
        if changed or any(
            _group_fingerprint(group) != preview.fingerprints[group.group_id] for group in preview.groups
        ):
            with self._previews_lock:
                self._previews.pop(preview.preview_id, None)
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
        return self._conflict(
            tuple(group.group_id for group in preview.groups), client_id, excluding=preview.resume_run_id
        )

    def _preview_changed(self, preview: _Preview) -> bool:
        return self._reconciled_version > preview.file_version or any(
            self._group_versions.get(group.group_id, 0) > preview.file_version for group in preview.groups
        )

    def _admit(
        self,
        request: ControlRequest,
        preview: _Preview,
        group_ids: tuple[str, ...],
        client_id: str,
    ) -> ControlResponse:
        run_id: str = preview.resume_run_id or f"run-{token_hex(_ID_BYTES)}"
        previous: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == run_id), None
        )
        if preview.resume_run_id is not None and (
            previous is None or previous.state is RequestState.SUCCEEDED or run_id in self._service.active_run_ids()
        ):
            return _refuse(RefusalReason.NOT_RESUMABLE)
        journal: RunJournal = (
            RunJournal.load(self._store.run_path(run_id))
            if previous is not None
            else RunJournal.create(
                self._store.run_path(run_id), preview.plan, run_temp_dir(self._service.workspace_root, run_id)
            )
        )
        if journal.plan != preview.plan:
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
        if previous is not None:
            journal.persist()
        accepted = ProcessingRequest(
            request_id=run_id,
            generation=previous.generation + (0 if preview.recovering else 1) if previous is not None else 1,
            group_ids=group_ids,
            fingerprints=dict(preview.fingerprints),
            origin=preview.origin,
            source_selection=preview.source_selection,
            rebuild=preview.rebuild,
            settings=_settings_snapshot(preview.plan.settings),
            state=RequestState.ACCEPTED,
            attempts=previous.attempts + 1 if previous is not None else 1,
            accepted_at=self._now(),
            intents=tuple(group.intent for group in preview.plan.groups),
            automatic=preview.automatic,
        )
        candidate: WatchState = record_request(self._state, accepted)
        for group_id in group_ids:
            candidate = release(candidate, group_id, client_id)
        outcome: dict[str, str | int | bool | None] = {"run_id": run_id, "groups": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        if refusal is not None:
            return refusal
        with self._previews_lock:
            self._previews.pop(preview.preview_id, None)
        self._pending[run_id] = preview.products
        self._run_groups[run_id] = preview.groups
        self._run_results.pop(run_id, None)
        self._run_products[run_id] = {artifact.artifact_id: artifact.kind for artifact in preview.plan.artifacts}
        with self._progress_lock:
            self._run_views[run_id] = RunProgressSnapshot(
                run_id,
                preview_plan(preview.plan, preview.preview_id, self._instance_id),
                {
                    group.group_id: next(
                        (
                            artifact.path.name
                            for artifact in preview.plan.artifacts
                            if artifact.group_id == group.group_id
                            and artifact.path is not None
                            and artifact.kind
                            in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4, ArtifactKind.STANDALONE_TEXT}
                        ),
                        group.group_id,
                    )
                    for group in preview.plan.groups
                },
            )
            self._run_events[run_id] = {}
        submitted: bool = False
        try:
            handle: RunHandle = self._service.submit_plan(
                preview.plan,
                _OwnerSink(self._publish_event),
                origin=preview.origin,
                run_id=run_id,
                automatic=preview.automatic,
                journal=journal,
                resume=previous is not None and run_temp_dir(self._service.workspace_root, run_id).exists(),
            )
            submitted = True
        finally:
            if not submitted:
                self._pending.pop(run_id, None)
                self._run_groups.pop(run_id, None)
                self._save(
                    record_request(
                        self._state,
                        replace(
                            accepted,
                            state=RequestState.FAILED,
                            problem="The accepted plan could not start; review its inputs and settings",
                        ),
                    )
                )
        self._watch_run(run_id, handle)
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _cancel(self, request: ControlRequest) -> ControlResponse:
        run_id: str | None = _text(request.payload, "run_id")
        if run_id is None:
            return _invalid("A cancellation needs a `run_id`")
        cancelled: bool = run_id in self._service.active_run_ids()
        outcome: dict[str, str | int | bool | None] = {"run_id": run_id, "cancelled": cancelled}
        return self._accept_local_command(request, outcome)

    def _watch_run(self, run_id: str, handle: RunHandle) -> None:

        def wait() -> None:
            try:
                result: RunResult | None = handle.result()
            except BaseException as problem:  # noqa: BLE001 - RunHandle forwards every coordinator failure
                logger.warning("A request ended in a terminal fault", error_class=type(problem).__name__)
                result = None
            self._queue.put(_Completion(request_id=run_id, result=result))

        threading.Thread(target=wait, daemon=True).start()

    def _record_completion(self, completion: _Completion) -> None:
        if completion.result is not None:
            self._run_results[completion.request_id] = completion.result
        products: frozenset[ProductKind] = self._pending.pop(completion.request_id, frozenset())
        recorded: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == completion.request_id),
            None,
        )
        if recorded is None:
            return
        finished: ProcessingRequest = replace(recorded, state=_request_state(completion.result))
        candidate: WatchState = record_request(self._state, finished)
        kinds: dict[str, ArtifactKind] = self._run_products.pop(completion.request_id, {})
        if completion.result is not None:
            confirmations: tuple[ProductConfirmation, ...] = tuple(
                ProductConfirmation(
                    group.group_id,
                    kinds[product.artifact_id].value,
                    product.path.relative_to(self._service.workspace_root).as_posix(),
                    finished.generation,
                    finished.request_id,
                    finished.origin,
                )
                for group in completion.result.groups
                for product in group.products
                if product.artifact_id in kinds and product.path.is_relative_to(self._service.workspace_root)
            )
            paths: frozenset[str] = frozenset(item.path for item in confirmations)
            candidate = replace(
                candidate, products=(*(item for item in candidate.products if item.path not in paths), *confirmations)
            )
        if finished.origin is RequestOrigin.USER and finished.state is not RequestState.PAUSED and products:
            candidate = _marked(candidate, finished, products, self._now())
        saved: bool = self._save(candidate)
        self._ledger.mark_finished(recorded.group_ids)
        groups: tuple[InspectedSourceGroup, ...] = self._run_groups.pop(completion.request_id, ())
        if saved and finished.state is RequestState.SUCCEEDED and completion.result is not None:
            self._prepare_ready(completion.result, groups)
        self._publish_state()
        self._publish(
            {"event": "run_finished", "payload": {"run_id": completion.request_id}},
            terminal=True,
        )

    def _run_result(self, request: ControlRequest) -> ControlResponse:
        run_id: str | None = _text(request.payload, "run_id")
        recorded: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == run_id), None
        )
        if recorded is None:
            return _invalid("The resident holds no such run")
        result: RunResult | None = self._run_results.get(recorded.request_id)
        if result is None and recorded.state is RequestState.SUCCEEDED:
            result = self._completed_result(recorded)
        relocating: bool = any(
            group in recorded.group_ids
            for group_id in self._ready_inflight
            for group in (group_id, self._ready_moves[group_id].destination_group_id)
        )
        return ControlResponse.succeeded(
            {
                "state": RequestState.RUNNING.value if relocating else recorded.state.value,
                "result": encode_view(result) if result is not None and not relocating else None,
            }
        )

    def _completed_result(self, request: ProcessingRequest) -> RunResult:
        groups: tuple[GroupResult, ...] = tuple(
            GroupResult(
                group_id,
                GroupStatus.SUCCEEDED,
                products=tuple(
                    ProducedArtifact(item.path, self._service.workspace_root / item.path, {})
                    for item in self._state.products
                    if item.group_id == group_id
                    and item.request_id == request.request_id
                    and item.generation == request.generation
                    and (self._service.workspace_root / item.path).is_file()
                ),
            )
            for group_id in request.group_ids
        )
        return RunResult(request.request_id, groups)

    # ── Settings, subscriptions and shutdown ──────────────────────────────────

    def _reload_settings(self) -> ControlResponse:
        try:
            self._service.reload_preferences()
        except (AniShiftError, OSError) as problem:
            logger.warning("Preferences could not be reloaded", error_class=type(problem).__name__)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return ControlResponse.succeeded({"reloaded": True})

    def _shutdown(self, request: ControlRequest) -> ControlResponse:
        outcome: dict[str, str | int | bool | None] = {"shutting_down": True}
        refusal: ControlResponse | None = self._commit(request, self._state, outcome)
        if refusal is not None:
            return refusal
        self._begin_shutdown()
        return ControlResponse.succeeded(outcome)

    def _begin_shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._settle_at = None
        self._transfers_at = None
        self._subscriptions_at = None
        self._service.set_background_admission(False)
        self._service.drain()
        logger.info("The resident is shutting down", active_runs=len(self._service.active_run_ids()))
        self._publish_state()

    def _subscription_command(self, request: ControlRequest) -> ControlResponse:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            return ControlResponse.refused(ControlErrorCode.REFUSED, _NO_SUBSCRIPTIONS)
        if request.kind == "subscription_add":
            order: SubscriptionOrder = decode_view(SubscriptionOrder, request.payload.get("order"))
            return self._accept_local_command(
                request,
                {
                    "subscription_id": subscription_id(order.series, order.group),
                    "order": json.dumps(encode_view(order)),
                },
            )
        if request.kind == "subscription_get":
            item: Subscription | None = next(
                (item for item in service.list() if item.subscription_id == request.payload.get("subscription_id")),
                None,
            )
            return (
                ControlResponse.succeeded(encode_view(item)) if item is not None else _invalid("Unknown subscription")
            )
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": [_subscription_view(item) for item in service.list()]})
        if request.kind == "subscriptions_check":
            outcomes: tuple[CheckOutcome, ...] = self._check_subscriptions(service, automatic=False)
            return ControlResponse.succeeded(
                {
                    "checked": len(outcomes),
                    "downloaded": sum(outcome.downloaded for outcome in outcomes),
                    "problems": sum(1 for outcome in outcomes if outcome.problem),
                    "outcomes": [encode_view(outcome) for outcome in outcomes],
                }
            )
        return self._subscription_mutation(request, service)

    def _acquisition_command(self, request: ControlRequest) -> ControlResponse:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            return _invalid("No acquisition service is configured")
        payload: Mapping[str, object] = request.payload
        with acquisition.requests("user"):
            if payload.get("operation") == "titles":
                return ControlResponse.succeeded(
                    {"items": [encode_view(item) for item in acquisition.find_titles(str(payload.get("query", "")))]}
                )
            if payload.get("operation") == "search":
                return ControlResponse.succeeded(encode_view(acquisition.search(str(payload.get("query", "")))))
            candidate: TitleCandidate = decode_view(TitleCandidate, payload.get("candidate"))
            if payload.get("operation") == "season":
                return ControlResponse.succeeded(encode_view(acquisition.season_context(candidate)))
            if payload.get("operation") != "releases":
                return _invalid("Unknown acquisition operation")
            episodes: EpisodeRange | None = (
                decode_view(EpisodeRange, payload["episodes"]) if payload.get("episodes") is not None else None
            )
            context: SeasonContext | None = (
                decode_view(SeasonContext, payload["context"]) if payload.get("context") is not None else None
            )
            return ControlResponse.succeeded(
                encode_view(
                    acquisition.search_title(
                        candidate,
                        episodes=episodes,
                        context=context,
                        order=CatalogOrder(str(payload.get("order", "newest"))),
                    )
                )
            )

    def _download_command(self, request: ControlRequest) -> ControlResponse:
        acquisition: AcquisitionService | None = self._service.acquisition
        raw: object = request.payload.get("choices")
        if acquisition is None or not isinstance(raw, list) or not raw:
            return _invalid("A download requires selected releases")
        choices: tuple[ReleaseChoice, ...] = tuple(decode_view(ReleaseChoice, item) for item in raw)
        directory: str | None = _text(request.payload, "directory")
        chosen: tuple[ReleaseChoice, ...]
        response: ControlResponse
        chosen, response = self._on_owner(lambda: self._accept_download(request, acquisition, choices, directory))
        if not response.ok or not chosen:
            return response
        try:
            with acquisition.requests("user_download"):
                for choice in chosen:
                    acquisition.download((choice,), directory_name=directory)
                hashes: frozenset[str] = acquisition.queued_hashes()
                self._on_owner(lambda: self._reconcile_acquisitions(hashes))
        finally:
            self._on_owner(lambda: self._reconcile_acquisitions(frozenset()))
        return response

    def _accept_download(
        self,
        request: ControlRequest,
        acquisition: AcquisitionService,
        choices: tuple[ReleaseChoice, ...],
        directory: str | None,
    ) -> tuple[tuple[ReleaseChoice, ...], ControlResponse]:
        receipt: CommandReceipt | None = self._receipt(request)
        if receipt is not None:
            return (), ControlResponse.succeeded(dict(receipt.outcome))
        if self._shutting_down or not self._finish_pending_commands():
            return (), ControlResponse.refused(ControlErrorCode.REFUSED, _SHUTTING_DOWN)
        existing: set[str] = {
            item.info_hash for item in self._state.acquisitions if item.state is not AcquisitionState.FAILED
        }
        unique: dict[str, ReleaseChoice] = {choice.release.info_hash.casefold(): choice for choice in choices}
        chosen: tuple[ReleaseChoice, ...] = tuple(choice for key, choice in unique.items() if key not in existing)
        confirmations: list[AcquisitionConfirmation] = []
        destination: Path = (
            self._service.workspace_root / series_directory_name(directory)
            if directory is not None
            else acquisition.series_directory(choices[0])
        )
        for choice in chosen:
            folder: Path = destination if directory is not None else acquisition.series_directory(choice)
            confirmations.append(
                AcquisitionConfirmation(
                    token_hex(_ID_BYTES),
                    choice.release.info_hash,
                    folder.relative_to(self._service.workspace_root).as_posix(),
                    (),
                    AcquisitionState.PENDING_SEND,
                    RequestOrigin.USER,
                    None,
                    str(choice.episode) if choice.episode is not None else None,
                    self._now(),
                )
            )
        outcome: CommandOutcome = {"count": len(chosen), "directory": str(destination)}
        replaced_hashes: set[str] = {item.info_hash for item in confirmations}
        failure: ControlResponse | None = self._commit(
            request,
            replace(
                self._state,
                acquisitions=(
                    *(item for item in self._state.acquisitions if item.info_hash not in replaced_hashes),
                    *confirmations,
                ),
            ),
            outcome,
        )
        return chosen, failure or ControlResponse.succeeded(dict(outcome))

    def _check_subscriptions(self, service: SubscriptionService, *, automatic: bool) -> tuple[CheckOutcome, ...]:
        if not automatic:
            self._on_owner(self._retry_subscription_checks)
        self._on_owner(self._reconcile_subscription_sources)
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is not None and self._on_owner(
            lambda: any(
                item.state in {AcquisitionState.PENDING_SEND, AcquisitionState.UNCERTAIN}
                for item in self._state.acquisitions
            )
        ):
            present: frozenset[str] = acquisition.queued_hashes()
            self._on_owner(lambda: self._reconcile_acquisitions(present))
        origin: RequestOrigin = RequestOrigin.BACKGROUND if automatic else RequestOrigin.USER

        def admit(subscription: Subscription, episode: Decimal, choice: ReleaseChoice) -> bool:
            return self._on_owner(
                lambda: self._admit_subscription(service, subscription, episode, choice, origin=origin)
            )

        def record(
            subscription: Subscription,
            confirmed: dict[Decimal, ReleaseChoice],
            offered: dict[Decimal, ReleaseChoice],
            checked: frozenset[Decimal] | None,
        ) -> Subscription | None:
            return self._on_owner(
                lambda: self._record_subscription(service, subscription, confirmed, offered, checked, origin=origin)
            )

        try:
            policy: AutomationPolicy = self._on_owner(lambda: self._state.policy)
            return service.check_due(
                policy,
                admit=admit,
                record=record,
                update=lambda original, updated: self._on_owner(lambda: service.update(original, updated)),
                refresh_calendar=not automatic,
            )
        finally:
            self._on_owner(lambda: self._reconcile_acquisitions(frozenset()))

    def _schedule_subscriptions(self) -> None:
        service: SubscriptionService | None = self._service.subscriptions
        if (
            self._shutting_down
            or service is None
            or self._subscriptions_checking
            or self._subscriptions_problem is not None
            or any(receipt.pending is not None for receipt in self._state.command_receipts)
        ):
            self._subscriptions_at = None
            return
        try:
            deadline: datetime | None = service.next_check_at(self._state.policy)
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Subscription schedule is unavailable", error_class=type(problem).__name__)
            deadline = None
        self._subscriptions_at = (
            time.monotonic() + max(0.0, (deadline - self._clock()).total_seconds()) if deadline is not None else None
        )

    def _poll_subscriptions(self) -> None:
        if self._subscriptions_at is None or self._subscriptions_at > time.monotonic():
            return
        self._subscriptions_at = None
        self._subscriptions_checking = True
        self._active_io += 1
        self._pool.submit(self._check_due_subscriptions)

    def _check_due_subscriptions(self) -> None:
        failure: str | None = None
        try:
            if self._service.subscriptions is not None:
                self._check_subscriptions(self._service.subscriptions, automatic=True)
        except Exception as problem:  # noqa: BLE001
            logger.warning("Scheduled subscription check failed", error_class=type(problem).__name__)
            failure = type(problem).__name__
        finally:
            self._queue.put(lambda: self._finish_subscription_check(failure))

    def _finish_subscription_check(self, failure: str | None) -> None:
        self._subscriptions_checking = False
        self._subscriptions_problem = failure or self._subscriptions_problem
        self._finish_io()
        self._publish_state()

    def _retry_subscription_checks(self) -> None:
        self._subscriptions_problem = None
        self._reconcile_subscription_sources()

    def _restore_provider_locks(self) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None or acquisition.request_control is None:
            return
        acquisition.request_control.restore(
            {item.provider: datetime.fromisoformat(item.until).timestamp() for item in self._state.provider_locks},
            lambda provider, until: self._on_owner(lambda: self._save_provider_lock(provider, until)),
        )

    def _save_provider_lock(self, provider: str, until: float) -> None:
        deadline: ProviderLock = ProviderLock(provider, datetime.fromtimestamp(until, UTC).isoformat(), "rate_limit")
        locks: tuple[ProviderLock, ...] = tuple(
            item for item in self._state.provider_locks if item.provider != provider
        )
        if not self._save(replace(self._state, provider_locks=(*locks, deadline))):
            self._subscriptions_problem = _STATE_NOT_SAVED
            raise OSError(_STATE_NOT_SAVED)
        self._schedule_subscriptions()
        self._publish_state()

    def _admit_subscription(
        self,
        service: SubscriptionService,
        subscription: Subscription,
        episode: Decimal,
        choice: ReleaseChoice,
        *,
        origin: RequestOrigin = RequestOrigin.USER,
    ) -> bool:
        if self._shutting_down or not service.is_current(subscription):
            return False
        if any(receipt.pending is not None for receipt in self._state.command_receipts):
            return False
        info_hash: str = choice.release.info_hash.casefold()
        if any(
            item.info_hash == info_hash
            or (item.subscription_id == subscription.subscription_id and item.episode == str(episode))
            for item in self._state.acquisitions
        ):
            return False
        confirmation: AcquisitionConfirmation = self._new_acquisition(
            subscription, episode, choice, AcquisitionState.PENDING_SEND, origin=origin
        )
        if not self._save(replace(self._state, acquisitions=(*self._state.acquisitions, confirmation))):
            raise OSError(_STATE_NOT_SAVED)
        self._publish_state()
        return True

    def _new_acquisition(
        self,
        subscription: Subscription,
        episode: Decimal,
        choice: ReleaseChoice,
        state: AcquisitionState,
        *,
        origin: RequestOrigin = RequestOrigin.USER,
    ) -> AcquisitionConfirmation:
        return AcquisitionConfirmation(
            operation_id=token_hex(_ID_BYTES),
            info_hash=choice.release.info_hash,
            directory=series_directory_name(subscription.directory or choice.name.series),
            required_files=(),
            state=state,
            origin=origin,
            subscription_id=subscription.subscription_id,
            episode=str(episode),
            updated_at=self._now(),
        )

    def _record_subscription(  # noqa: PLR0913
        self,
        service: SubscriptionService,
        subscription: Subscription,
        confirmed: dict[Decimal, ReleaseChoice],
        offered: dict[Decimal, ReleaseChoice],
        checked: frozenset[Decimal] | None,
        *,
        origin: RequestOrigin = RequestOrigin.USER,
    ) -> Subscription | None:
        hashes: frozenset[str] = frozenset(choice.release.info_hash.casefold() for choice in confirmed.values())
        known: frozenset[str] = frozenset(item.info_hash for item in self._state.acquisitions)
        existing: tuple[AcquisitionConfirmation, ...] = tuple(
            self._new_acquisition(subscription, episode, choice, AcquisitionState.ACCEPTED, origin=origin)
            for episode, choice in confirmed.items()
            if choice.release.info_hash.casefold() not in known
        )
        if existing and not self._save(replace(self._state, acquisitions=(*self._state.acquisitions, *existing))):
            raise OSError(_STATE_NOT_SAVED)
        self._reconcile_acquisitions(hashes)
        self._schedule_transfers()
        return service.record_check(subscription, confirmed, offered, checked)

    def _reconcile_acquisitions(self, present: frozenset[str]) -> None:
        acquisitions: list[AcquisitionConfirmation] = []
        for item in self._state.acquisitions:
            state: AcquisitionState = item.state
            if item.info_hash in present and state in {AcquisitionState.PENDING_SEND, AcquisitionState.UNCERTAIN}:
                state = AcquisitionState.ACCEPTED
            elif state is AcquisitionState.PENDING_SEND:
                state = AcquisitionState.UNCERTAIN
            acquisitions.append(replace(item, state=state, updated_at=self._now()) if state is not item.state else item)
        if tuple(acquisitions) == self._state.acquisitions:
            return
        if not self._save(replace(self._state, acquisitions=tuple(acquisitions))):
            raise OSError(_STATE_NOT_SAVED)
        self._schedule_transfers()
        self._publish_state()

    def _schedule_transfers(self, delay: float = 0.0) -> None:
        if self._shutting_down or self._transfers is None or self._transfers_inspecting:
            return
        active: bool = any(
            item.state is AcquisitionState.ACCEPTED or item.action_pending for item in self._state.acquisitions
        )
        self._transfers_at = time.monotonic() + delay if active else None

    def _poll_transfers(self) -> None:
        if self._transfers_at is None or self._transfers_at > time.monotonic():
            return
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            item for item in self._state.acquisitions if item.state is AcquisitionState.ACCEPTED or item.action_pending
        )
        self._transfers_at = None
        self._transfers_inspecting = True
        self._active_io += 1
        self._pool.submit(self._inspect_transfers, acquisitions)

    def _inspect_transfers(self, acquisitions: tuple[AcquisitionConfirmation, ...]) -> None:
        results: tuple[AcquisitionConfirmation, ...] = ()
        failure: str | None = None
        nature: tuple[str, str] | None = None
        try:
            if self._transfers is not None:
                acquisition: AcquisitionService | None = self._service.acquisition
                if acquisition is not None:
                    with acquisition.requests("transfer"):
                        acquisitions = tuple(self._apply_transfer_action(acquisition, item) for item in acquisitions)
                        results = acquisitions
                        results = self._transfers.inspect(
                            acquisitions, stall_after_s=self._state.policy.transfer_stall_s
                        )
        except Exception as problem:  # noqa: BLE001
            failure = sanitize_event_message(str(problem))
            nature = (type(problem).__name__, failure_code(problem))
            if self._transfers is not None:
                self._transfers.reset_clock()
        finally:
            self._queue.put(lambda: self._record_transfers(results, failure, nature))

    def _record_transfers(
        self,
        results: tuple[AcquisitionConfirmation, ...],
        failure: str | None = None,
        nature: tuple[str, str] | None = None,
    ) -> None:
        self._note_transfers(failure, nature)
        self._transfers_problem = failure
        self._active_io -= 1
        self._transfers_inspecting = False
        updated: dict[str, AcquisitionConfirmation] = {item.operation_id: item for item in results}
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            updated.get(item.operation_id, item)
            if updated.get(item.operation_id, item).action_id == item.action_id
            else item
            for item in self._state.acquisitions
        )
        if acquisitions != self._state.acquisitions and self._save(replace(self._state, acquisitions=acquisitions)):
            self._reconcile_subscription_sources()
            self._publish_state()
            paths: tuple[Path, ...] = tuple(
                self._service.workspace_root / item.directory / name
                for item in results
                if item.state is AcquisitionState.COMPLETE
                for name in item.required_files
            )
            if paths:
                self.files_changed(DirectoryChange(paths=paths, reason="transfer_complete"))
            else:
                self._refresh_automatic()
        self._schedule_transfers(self._transfers_delay)
        self._publish_state()
        completed: frozenset[str] = frozenset(
            item.info_hash for item in self._state.acquisitions if item.state is AcquisitionState.COMPLETE
        )
        if completed and failure is None:
            self._active_io += 1
            self._pool.submit(self._release_completed, completed)

    def _note_transfers(self, failure: str | None, nature: tuple[str, str] | None) -> None:
        previous: tuple[str, str] | None = self._transfers_failure
        self._transfers_failure = nature
        if nature is None:
            self._transfers_delay = TRANSFER_CHECK_INTERVAL_S
            if previous is not None:
                logger.info("Transfer reconciliation recovered")
            return
        self._transfers_delay = min(self._transfers_delay * _TRANSFER_BACKOFF_FACTOR, TRANSFER_BACKOFF_CEILING_S)
        if previous == nature:
            return
        logger.warning(
            "Transfer reconciliation failed",
            error_class=nature[0],
            error_code=nature[1],
            reason=failure,
        )

    def _release_completed(self, hashes: frozenset[str]) -> None:
        problem: str | None = None
        try:
            acquisition: AcquisitionService | None = self._service.acquisition
            if acquisition is not None:
                with acquisition.requests("completed_download"):
                    acquisition.release_completed(hashes)
                    acquisition.finish_transfers()
        except (AniShiftError, OSError, ValueError) as error:
            problem = sanitize_event_message(str(error))
        finally:
            self._queue.put(lambda: self._released_completed(problem))

    def _released_completed(self, problem: str | None) -> None:
        self._active_io -= 1
        if problem is not None:
            self._transfers_problem = problem
        self._publish_state()

    def _restore_runs(self, requests: tuple[ProcessingRequest, ...]) -> None:
        try:
            for request in requests:
                if request.state is RequestState.SUCCEEDED:
                    self._on_owner(partial(self._restore_ready, request))
                    continue
                if request.state not in {RequestState.ACCEPTED, RequestState.RUNNING, RequestState.PAUSED}:
                    continue
                if not self._on_owner(partial(self._can_restore, request)):
                    continue
                try:
                    journal: RunJournal = RunJournal.load(self._store.run_path(request.request_id))
                    self._on_owner(partial(self._resume_restored, request, journal))
                except (AniShiftError, OSError, ValueError) as error:
                    problem: str = sanitize_event_message(str(error)) or "The interrupted run needs manual recovery"
                    self._on_owner(partial(self._failed_recovery, request, problem))
        finally:
            self._queue.put(self._restored_runs)

    def _resume_restored(self, request: ProcessingRequest, journal: RunJournal) -> None:
        if self._shutting_down or self._library is None or not self._can_restore(request):
            return
        if journal.uncertain_remote_work:
            self._failed_recovery(
                request,
                "A remote operation was interrupted without confirmation; "
                "saved products remain and an explicit resume is required",
            )
            return
        if journal.plan.tasks and request.attempts >= self._state.policy.external_retry_budget:
            self._failed_recovery(
                request, "Automatic recovery attempts are exhausted; select the files and explicitly resume"
            )
            return
        groups: tuple[InspectedSourceGroup, ...] = tuple(
            group for group in self._library.groups if group.group_id in request.group_ids
        )
        if len(groups) != len(request.group_ids) or any(
            _group_fingerprint(group) != request.fingerprints.get(group.group_id) for group in groups
        ):
            self._failed_recovery(request, "The sources changed or are missing; inspect the files before resuming")
            return
        preview: _Preview = _Preview(
            preview_id=f"recovery-{request.request_id}",
            client_id=self._instance_id,
            plan=journal.plan,
            groups=groups,
            fingerprints=request.fingerprints,
            products=frozenset(
                product for group in journal.plan.groups for product in group.intent.products.requested_products
            ),
            origin=request.origin,
            source_selection=request.source_selection,
            session_id=None,
            rebuild=request.rebuild,
            automatic=request.automatic,
            resume_run_id=request.request_id,
            recovering=True,
        )
        response: ControlResponse = self._admit(
            ControlRequest(command_id=f"recovery-{request.request_id}-{request.attempts}", kind="start", payload={}),
            preview,
            request.group_ids,
            self._instance_id,
        )
        if not response.ok:
            self._failed_recovery(request, "The saved run could not be admitted; explicitly resume it from Manual")

    def _failed_recovery(self, request: ProcessingRequest, problem: str) -> None:
        if not self._can_restore(request):
            return
        current: ProcessingRequest = next(
            (item for item in self._state.requests if item.request_id == request.request_id), request
        )
        self._save(record_request(self._state, replace(current, state=RequestState.FAILED, problem=problem)))
        self._publish_state()

    def _can_restore(self, request: ProcessingRequest) -> bool:
        return request.request_id not in self._service.active_run_ids() and any(
            item == request for item in self._state.requests
        )

    def _restored_runs(self) -> None:
        self._active_io -= 1
        self._recovering = False
        self._refresh_automatic()
        self._publish_state()

    def _restore_ready(self, request: ProcessingRequest) -> None:
        if self._library is None or not self._can_restore(request):
            return
        sources: tuple[InspectedSourceGroup, ...] = tuple(
            group
            for group in self._library.groups
            if group.group_id in request.group_ids
            and _group_fingerprint(group) == request.fingerprints.get(group.group_id)
            and not self._blocked((group.group_id,), self._instance_id)
        )
        result: RunResult = self._completed_result(request)
        self._run_results[request.request_id] = result
        self._prepare_ready(result, sources)

    def _prepare_ready(self, result: RunResult, sources: Sequence[InspectedSourceGroup] | None = None) -> None:
        if self._ready_store is None:
            return
        if sources is None:
            sources = () if self._library is None else self._library.groups
        groups: dict[str, InspectedSourceGroup] = {group.group_id: group for group in sources}
        for completed in result.groups:
            group: InspectedSourceGroup | None = groups.get(completed.group_id)
            if group is None or completed.status is not GroupStatus.SUCCEEDED:
                continue
            try:
                move: ReadyMove | None = self._ready_store.prepare(
                    group.source, tuple(product.path for product in completed.products)
                )
                if move is not None:
                    self._ready_moves[move.group_id] = move
            except (AniShiftError, OSError, ValueError) as error:
                self._ready_problems[group.group_id] = (
                    sanitize_event_message(str(error)) or "Relocation could not be prepared"
                )
        self._retry_ready()

    def _relocating_groups(self) -> set[str]:
        return self._ready_problems.keys() | {
            group for move in self._ready_moves.values() for group in (move.group_id, move.destination_group_id)
        }

    def _retry_ready(self) -> None:
        if self._shutting_down:
            return
        for group_id, move in self._ready_moves.items():
            if group_id in self._ready_inflight:
                continue
            self._ready_inflight.add(group_id)
            self._active_io += 1
            self._pool.submit(self._move_ready, move, self._state.acquisitions)

    def _move_ready(self, move: ReadyMove, acquisitions: tuple[AcquisitionConfirmation, ...]) -> None:
        problem: str | None = None
        try:
            paths: set[str] = {item.source for item in move.files}
            tracked: tuple[AcquisitionConfirmation, ...] = tuple(
                item
                for item in acquisitions
                if any((Path(item.directory) / name).as_posix() in paths for name in item.required_files)
                or (not item.required_files and any(Path(path).is_relative_to(Path(item.directory)) for path in paths))
            )
            hashes: frozenset[str] = frozenset(item.info_hash for item in tracked)
            acquisition: AcquisitionService | None = self._service.acquisition
            if any(item.state is not AcquisitionState.COMPLETE for item in tracked):
                message: str = "The torrent must be confirmed complete before moving its files"
                raise ExecutionError(message)
            if hashes and (acquisition is None or acquisition.release_completed(hashes) != hashes):
                message = "The torrent client still owns these files; stop its completed job before retrying"
                raise ExecutionError(message)
            if self._ready_store is not None:
                self._ready_store.execute(move)
        except (AniShiftError, OSError, ValueError) as error:
            problem = sanitize_event_message(str(error)) or "Relocation could not finish"
        finally:
            self._queue.put(lambda: self._record_ready(move, problem))

    def _record_ready(self, move: ReadyMove, problem: str | None) -> None:
        self._active_io -= 1
        self._ready_inflight.discard(move.group_id)
        if problem is None and not self._save(move.apply(self._state)):
            problem = "Moved files await a successful state save; retry relocation"
        if problem is not None:
            self._ready_problems[move.group_id] = problem
            self._publish_ready(move)
            return
        self._run_results = {
            run_id: move.apply_result(result, self._service.workspace_root)
            for run_id, result in self._run_results.items()
        }
        try:
            if self._ready_store is not None:
                self._ready_store.acknowledge(move)
        except OSError:
            self._ready_problems[move.group_id] = "Files and state are saved; relocation acknowledgement needs retry"
            self._publish_ready(move)
            return
        self._ready_moves.pop(move.group_id, None)
        self._ready_problems.pop(move.group_id, None)
        self.files_changed(
            DirectoryChange(
                paths=tuple(
                    self._service.workspace_root / name
                    for item in move.files
                    for name in (item.source, item.destination)
                ),
                reason="relocation",
            )
        )
        self._publish_ready(move)

    def _publish_ready(self, move: ReadyMove) -> None:
        self._publish_state()
        for request in self._state.requests:
            if {move.group_id, move.destination_group_id}.intersection(request.group_ids):
                self._publish({"event": "run_finished", "payload": {"run_id": request.request_id}}, terminal=True)

    def _transfer_command(self, request: ControlRequest) -> ControlResponse:
        info_hash: str = str(request.payload.get("info_hash", "")).casefold()
        action: str = str(request.payload.get("action", ""))
        if action not in {"stop", "resume", "cancel"} or not any(
            item.info_hash == info_hash for item in self._state.acquisitions
        ):
            return _invalid("A transfer command needs a known hash and stop, resume or cancel")
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            replace(item, requested_action=action, action_id=request.command_id, action_pending=True, problem=None)
            if item.info_hash == info_hash
            else item
            for item in self._state.acquisitions
        )
        outcome: dict[str, str | bool] = {"info_hash": info_hash, "action": action, "accepted": True}
        refusal: ControlResponse | None = self._commit(
            request, replace(self._state, acquisitions=acquisitions), outcome
        )
        if refusal is not None:
            return refusal
        self._schedule_transfers()
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _apply_transfer_action(
        self, service: AcquisitionService, item: AcquisitionConfirmation
    ) -> AcquisitionConfirmation:
        if not item.action_pending:
            return item
        try:
            service.control_transfer(item.info_hash, str(item.requested_action))
        except (AniShiftError, OSError, ValueError) as problem:
            return replace(item, action_pending=False, problem=sanitize_event_message(str(problem)))
        return replace(
            item,
            action_pending=False,
            problem=None,
            state=AcquisitionState.FAILED if item.requested_action == "cancel" else AcquisitionState.ACCEPTED,
        )

    def _reconcile_subscription_sources(self) -> None:
        if self._service.subscriptions is None or not self._state.acquisitions:
            return
        try:
            self._service.subscriptions.reconcile_sources(self._state.acquisitions)
        except (AniShiftError, OSError) as problem:
            self._subscriptions_problem = type(problem).__name__
            logger.warning("Episode confirmations could not be updated", error_class=type(problem).__name__)

    def _subscription_mutation(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        identifier: str | None = _text(request.payload, "subscription_id")
        if identifier is None:
            return _invalid("A subscription command needs a `subscription_id`")
        outcome: dict[str, str | int | bool | None]
        try:
            present: bool = any(item.subscription_id == identifier for item in service.list())
            if not present and request.kind != "subscription_remove":
                return _invalid("The subscription no longer exists")
            match request.kind:
                case "subscription_enable":
                    outcome = {"subscription_id": identifier, "enabled": True}
                case "subscription_disable":
                    outcome = {"subscription_id": identifier, "enabled": False}
                case "subscription_remove":
                    outcome = {"subscription_id": identifier, "removed": present}
                case _:
                    return ControlResponse.refused(ControlErrorCode.UNKNOWN_COMMAND, _UNKNOWN_COMMAND)
        except (AniShiftError, OSError) as problem:
            logger.warning("A subscription command failed", error_class=type(problem).__name__)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return self._accept_local_command(request, outcome)

    def _accept_local_command(self, request: ControlRequest, outcome: CommandOutcome) -> ControlResponse:
        receipt: CommandReceipt = CommandReceipt(request.command_id, self._now(), outcome, pending=request.kind)
        if not self._save(record_command(self._state, receipt)) or not self._finish_pending_commands():
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return ControlResponse.succeeded(dict(outcome))

    def _finish_pending_commands(self) -> bool:
        for receipt in self._state.command_receipts:
            if receipt.pending is not None and not self._finish_local_command(receipt):
                return False
        return True

    def _finish_local_command(self, receipt: CommandReceipt) -> bool:
        candidate: WatchState = self._state
        try:
            if receipt.pending == "cancel":
                run_id: str = str(receipt.outcome["run_id"])
                self._service.cancel(run_id)
                candidate = replace(
                    candidate,
                    requests=tuple(
                        replace(item, state=RequestState.CANCELLED)
                        if item.request_id == run_id and item.state in _ACTIVE_STATES
                        else item
                        for item in candidate.requests
                    ),
                )
            else:
                service: SubscriptionService | None = self._service.subscriptions
                if service is None:
                    return False
                identifier: str = str(receipt.outcome["subscription_id"])
                if receipt.pending == "subscription_enable":
                    service.enable(identifier)
                elif receipt.pending == "subscription_disable":
                    service.disable(identifier)
                elif receipt.pending == "subscription_add":
                    service.add_order(
                        decode_view(SubscriptionOrder, json.loads(str(receipt.outcome["order"]))),
                        receipt.command_id,
                    )
                else:
                    service.remove(identifier)
        except (AniShiftError, OSError) as problem:
            logger.warning("An accepted local command remains pending", error_class=type(problem).__name__)
            return False
        candidate = replace(
            candidate,
            command_receipts=tuple(
                replace(item, pending=None) if item.command_id == receipt.command_id else item
                for item in candidate.command_receipts
            ),
        )
        saved: bool = self._save(candidate)
        if saved:
            self._schedule_subscriptions()
            self._publish_state()
        return saved

    def _subscription_counts(self) -> dict[str, int]:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            return {"enabled": 0, "disabled": 0}
        try:
            subscriptions: tuple[Subscription, ...] = service.list()
        except AniShiftError, OSError:
            return {"enabled": 0, "disabled": 0}
        enabled: int = sum(1 for item in subscriptions if item.enabled)
        return {"enabled": enabled, "disabled": len(subscriptions) - enabled}

    # ── Persistence and events ────────────────────────────────────────────────

    def _commit(
        self,
        request: ControlRequest,
        candidate: WatchState,
        outcome: CommandOutcome,
    ) -> ControlResponse | None:
        if request.kind not in _MUTATING_KINDS:
            self._state = candidate
            return None
        receipt = CommandReceipt(command_id=request.command_id, accepted_at=self._now(), outcome=outcome)
        if not self._save(record_command(candidate, receipt)):
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return None

    def _save(self, candidate: WatchState) -> bool:
        try:
            self._store.save(candidate)
        except (AniShiftError, OSError) as problem:
            logger.warning("The automation state could not be saved", error_class=type(problem).__name__)
            return False
        self._state = candidate
        return True

    def _receipt(self, request: ControlRequest) -> CommandReceipt | None:
        if request.kind not in _MUTATING_KINDS:
            return None
        return next((item for item in self._state.command_receipts if item.command_id == request.command_id), None)

    def _publish_event(self, event: RunEvent) -> None:
        with self._progress_lock:
            events: dict[tuple[str, str | None, str | None], RunEvent] | None = self._run_events.get(event.run_id)
            if events is not None:
                events[event.kind.value, event.group_id, event.task_id] = event
        if event.kind is RunEventKind.GROUP_FINISHED:
            self._queue.put(lambda: self._notify_group(event))
        self._publish(
            {
                "event": "run_event",
                "payload": {
                    "run_id": event.run_id,
                    "sequence": event.sequence,
                    "kind": event.kind.value,
                    "group_id": event.group_id,
                    "task_id": event.task_id,
                    "state": event.state.value if event.state is not None else None,
                    "progress_percent": event.progress_percent,
                    "message": event.message,
                },
            },
            terminal=event.state in TERMINAL_TASK_STATES,
        )

    def _publish_state(self) -> None:
        self._publish({"event": "state_changed", "payload": self._status()}, terminal=False)

    def _progress_views(self) -> list[dict[str, object]]:
        with self._progress_lock:
            active: set[str] = {item.request_id for item in self._state.requests if item.state in _ACTIVE_STATES}
            finished: list[str] = [run_id for run_id in self._run_views if run_id not in active]
            for run_id in finished[:-_FINISHED_PROGRESS_LIMIT]:
                self._run_views.pop(run_id, None)
                self._run_events.pop(run_id, None)
            return [
                {"run_id": run_id, "preview_id": view.preview.preview_id} for run_id, view in self._run_views.items()
            ]

    def _notify_group(self, event: RunEvent) -> None:
        request: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == event.run_id),
            None,
        )
        if request is None or event.group_id is None:
            return
        with self._progress_lock:
            view: RunProgressSnapshot | None = self._run_views.get(event.run_id)
        if event.state is TaskState.SUCCEEDED and (
            view is None or not any(task.group_id == event.group_id for task in view.preview.tasks)
        ):
            return
        key: tuple[str, str, str] = (event.group_id, f"{request.request_id}:{request.generation}", str(event.state))
        if key in self._state.notified or not self._save(replace(self._state, notified=self._state.notified | {key})):
            return
        with self._progress_lock:
            label: str = view.labels.get(event.group_id, event.group_id) if view is not None else event.group_id
        message: str = "Gotowy odcinek" if event.state is TaskState.SUCCEEDED else "Odcinek wymaga uwagi"
        self._publish(
            {
                "event": "notification",
                "payload": {
                    "title": message,
                    "message": sanitize_event_message(label),
                },
            },
            terminal=True,
        )

    def _publish(self, frame: Mapping[str, object], *, terminal: bool) -> None:
        broadcast: Broadcast | None = self._broadcast
        if broadcast is not None:
            broadcast(frame, terminal)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _blocked(self, group_ids: Sequence[str], client_id: str, *, excluding: str | None = None) -> bool:
        return self._conflict(group_ids, client_id, excluding=excluding) is not None

    def _conflict(
        self, group_ids: Sequence[str], client_id: str, *, excluding: str | None = None
    ) -> ControlResponse | None:
        if self._relocating_groups().intersection(group_ids):
            return _refuse(RefusalReason.GROUP_RELOCATING)
        held: Mapping[str, str] = {item.group_id: item.client_id for item in self._state.reservations}
        if any(held.get(group_id, client_id) != client_id for group_id in group_ids):
            return _refuse(RefusalReason.GROUP_RESERVED)
        active: frozenset[str] = frozenset(
            group_id
            for request in self._state.requests
            if request.state in _ACTIVE_STATES and request.request_id != excluding
            for group_id in request.group_ids
        )
        if active.intersection(group_ids):
            return _refuse(RefusalReason.GROUP_PROCESSING)
        return None

    def _previewed_fingerprint(self, group_id: str) -> SourceFingerprint:
        with self._previews_lock:
            previews: tuple[_Preview, ...] = tuple(self._previews.values())
        for preview in previews:
            known: SourceFingerprint | None = preview.fingerprints.get(group_id)
            if known is not None:
                return known
        return ()

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()


class _OwnerSink:
    """Forwards every run event of the resident to the subscribers of the channel."""

    def __init__(self, publish: Callable[[RunEvent], None]) -> None:
        """Bind one publisher shared by every request this resident admitted."""
        self._publish: Callable[[RunEvent], None] = publish

    def emit(self, event: RunEvent) -> None:
        """Publish one event without owning any workflow state."""
        self._publish(event)


def _marked(
    state: WatchState,
    request: ProcessingRequest,
    products: frozenset[ProductKind],
    moment: str,
) -> WatchState:
    marked: WatchState = state
    selected: dict[str, frozenset[ProductKind]] = {
        intent.group_id: intent.products.requested_products for intent in request.intents
    }
    for group_id in request.group_ids:
        fingerprint: SourceFingerprint | None = request.fingerprints.get(group_id)
        if fingerprint is None:
            continue
        marked = mark_manual_handled(
            marked,
            ManualHandledMarker(
                group_id=group_id,
                fingerprint=fingerprint,
                products=selected.get(group_id, products),
                request_id=request.request_id,
                recorded_at=moment,
            ),
        )
    return marked


def _request_state(result: RunResult | None) -> RequestState:
    if result is None:
        return RequestState.FAILED
    if result.paused:
        return RequestState.PAUSED
    states: frozenset[RequestState] = frozenset(
        _RESULT_STATES.get(group.status, RequestState.FAILED) for group in result.groups
    )
    return next((candidate for candidate in _WORST_FIRST if candidate in states), RequestState.SUCCEEDED)


def _product_projection(plan: ExecutionPlan) -> list[dict[str, object]]:
    preserved: dict[str, set[str]] = {group.group_id: set() for group in plan.groups}
    planned: dict[str, set[str]] = {group.group_id: set() for group in plan.groups}
    for artifact in plan.artifacts:
        if artifact.lifetime is not ArtifactLifetime.DURABLE or artifact.group_id not in preserved:
            continue
        bucket: dict[str, set[str]] = preserved if artifact.state is ArtifactState.READY else planned
        bucket[artifact.group_id].add(artifact.kind.value)
    return [
        {
            "group_id": group.group_id,
            "preserved_products": sorted(preserved[group.group_id]),
            "planned_products": sorted(planned[group.group_id]),
            "problems": [
                {
                    "code": problem.code,
                    "message": sanitize_event_message(problem.message),
                    "is_blocking": problem.is_blocking,
                }
                for problem in group.problems
            ],
        }
        for group in plan.groups
    ]


def _settings_snapshot(settings: RunSettingsSnapshot) -> SettingsSnapshot:
    return cast("SettingsSnapshot", {field.name: getattr(settings, field.name) for field in fields(settings)})


def _group_fingerprint(group: InspectedSourceGroup) -> SourceFingerprint:
    return source_fingerprint(snapshot_sources(group, {}, 0.0))


def _requested_groups(workspace: InspectedWorkspace, payload: Mapping[str, object]) -> tuple[InspectedSourceGroup, ...]:
    requested: tuple[str, ...] | None = _identifiers(payload, "group_ids")
    if "group_ids" in payload and (requested is None or not requested or len(set(requested)) != len(requested)):
        msg = "Selected group IDs must be a nonempty unique list"
        raise ValueError(msg)
    by_id: Mapping[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
    selected: tuple[str, ...] = requested if requested is not None else ready_group_ids(workspace.groups)
    return tuple(by_id[group_id] for group_id in selected)


def _subscription_view(subscription: Subscription) -> dict[str, object]:
    return {
        "subscription_id": subscription.subscription_id,
        "series": subscription.series,
        "group": subscription.group,
        "next_episode": str(subscription.next_episode),
        "enabled": subscription.enabled,
        "end_state": subscription.end_state.value,
        "anilist_id": subscription.anilist_id,
        "episodes": [encode_view(episode) for episode in subscription.episodes],
    }


def _invalid(message: str) -> ControlResponse:
    return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, message)


def _refuse(reason: RefusalReason) -> ControlResponse:
    code, message = _REFUSALS[reason]
    return ControlResponse.refused(code, message, reason.value)


def _reservation_refusal(state: WatchState, group_id: str, client_id: str) -> ControlResponse:
    if any(item.group_id == group_id and item.client_id != client_id for item in state.reservations):
        return _refuse(RefusalReason.GROUP_RESERVED)
    return _refuse(RefusalReason.GROUP_PROCESSING)


def _external_sources(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    registrations: object = payload.get("external_sources", [])
    if not isinstance(registrations, list) or not all(isinstance(entry, dict) for entry in registrations):
        msg = "External registrations must be a list of objects"
        raise TypeError(msg)
    return tuple(cast("dict[str, object]", entry) for entry in registrations)


def _flag(payload: Mapping[str, object], key: str) -> bool | None:
    value: object = payload.get(key)
    return value if isinstance(value, bool) else None


def _text(payload: Mapping[str, object], key: str, *, allow_empty: bool = False) -> str | None:
    value: object = payload.get(key)
    if not isinstance(value, str) or (not value and not allow_empty):
        return None
    return value


def _identifiers(payload: Mapping[str, object], key: str) -> tuple[str, ...] | None:
    value: object = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None
    return tuple(str(item) for item in value)


def _origin(payload: Mapping[str, object]) -> RequestOrigin | None:
    named: object = payload.get("origin", RequestOrigin.USER.value)
    if not isinstance(named, str):
        return None
    try:
        return RequestOrigin(named)
    except ValueError:
        return None


def _selection(payload: Mapping[str, object]) -> SourceSelection | None:
    named: object = payload.get("source_selection", SourceSelection.AUTO.value)
    if not isinstance(named, str):
        return None
    try:
        return SourceSelection(named)
    except ValueError:
        return None
