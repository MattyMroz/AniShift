"""The one owner of the automation state, its reservations and its processing requests."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum, auto
from functools import partial
from pathlib import Path
from queue import Empty, SimpleQueue
from secrets import token_hex
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from anishift.application.acquisition import (
    AcquisitionService,
    CatalogOrder,
    ReleaseChoice,
    SeasonContext,
)
from anishift.application.artifacts import ArtifactKind, ArtifactLifetime, ArtifactState, create_group_id
from anishift.application.cancellation import EventCancellationToken
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    CommandReceipt,
    DeletionOutcome,
    DeletionStatus,
    ManualHandledMarker,
    PendingDeletion,
    PreflightFinding,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    ReadyGroup,
    RecipePreferences,
    RefusalReason,
    RequestState,
    Reservation,
    SourceSelection,
    WatchState,
    auto_admissible,
    mark_manual_handled,
    preflight,
    record_command,
    record_request,
    release,
    reserve,
)
from anishift.application.control_payloads import decode_intent
from anishift.application.control_views import (
    DeletionPreview,
    LibraryFileIdentity,
    LibrarySet,
    RetryProposal,
    RunProgressSnapshot,
    decode_view,
    encode_view,
    preview_plan,
)
from anishift.application.discovery import ArtifactName, classify_artifact, is_derived_product
from anishift.application.events import RunEventKind, failure_code, sanitize_event_message
from anishift.application.history import HistoryEvent, HistoryJournal, HistoryKind
from anishift.application.inspection import InspectedWorkspace
from anishift.application.intents import (
    AutoPreset,
    ExternalAudioRole,
    GroupIntent,
    RebuildRequest,
    RequestOrigin,
    RunMode,
    SubtitleOutputFormat,
)
from anishift.application.library import file_identity, project_library
from anishift.application.planner import auto_group_products
from anishift.application.planning import ExecutionPlan, TaskState
from anishift.application.products import AUDIO_PRODUCT_PROFILES, main_product, product_suffix
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.recovery import CHECKPOINT_VERSION, RunJournal
from anishift.application.results import GroupResult, GroupStatus, ProducedArtifact, RunResult
from anishift.application.scheduler_runtime import TERMINAL_TASK_STATES
from anishift.application.selection import ready_group_ids, resolve_readiness
from anishift.application.subscriptions import SubscriptionOrder, repeat_of, resolve_subscription_id
from anishift.application.transfers import TransferInspector, flat_layout, reserved_stem
from anishift.application.watch import SCAN_INTERVAL_S, WatchLedger, snapshot_sources, source_fingerprint
from anishift.application.workflows import WorkflowRoute, WorkflowTarget, resolve_route
from anishift.config.workspace import run_temp_dir
from anishift.errors import AniShiftError
from anishift.paths import READY_DIRECTORY
from anishift.platform.directory_watch import DirectoryChange, source_is_available
from anishift.platform.local_control import ControlErrorCode, ControlRequest, ControlResponse
from anishift.platform.recycle import RecycleResult
from anishift.services.catalog import TitleCandidate
from anishift.services.torrents.query import EpisodeRange
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from anishift.application.acquisition import AcquisitionService, ReleaseChoice
    from anishift.application.artifacts import Artifact, SourceGroup
    from anishift.application.control import (
        AutomationPolicy,
        CommandOutcome,
        FileReservation,
        SettingsSnapshot,
        SourceFingerprint,
    )
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
    from anishift.services.torrents import TorrentFile

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

_NOTIFICATION_LIMIT: Final[int] = 128
"""Maximum exact result references retained by this owner, never restored from history."""

_UNIDENTIFIED_NOTIFICATION: Final[str] = "Windows nie wskazał powiadomienia. Otwórz wynik w Bibliotece"
"""Visible refusal when the native callback cannot identify its original notification."""

_UNAVAILABLE_NOTIFICATION: Final[str] = "Wynik powiadomienia jest niedostępny lub zmieniony. Sprawdź Bibliotekę"
"""Visible refusal for an expired reference or a changed result revision."""

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
        RefusalReason.PAUSED: (
            ControlErrorCode.REFUSED,
            "AniShift is paused; choose Resume before starting new work",
        ),
        RefusalReason.SHUTTING_DOWN: (
            ControlErrorCode.REFUSED,
            "The resident is shutting down and admits no new work",
        ),
    }
)
"""Protocol code and English message of every cause this owner refuses a command for."""

_STATE_NOT_SAVED: Final[str] = "The automation state could not be saved, so nothing changed"
"""Reason returned when the command was abandoned instead of applied unrecorded."""

_UNREADABLE_DESTINATION: Final[str] = "The download destination could not be read, so no name was reserved"
"""Problem recorded against one release when its destination cannot be listed before a reservation."""

_OCCUPIED_DESTINATION: Final[str] = "Something took a name reserved for this download; clear that name and retry"
"""Problem recorded against one release when a reserved name stopped being free before its content started."""

_NO_ANSWER: Final[str] = "The resident did not finish the command in time"
"""Reason returned when the owner thread was still busy when the budget ran out."""

_COMMAND_FAILURE_REASON: Final[str] = "command_failed"
"""Fallback reason when a command failure has no domain code."""

_COMMAND_FAILED: Final[str] = "The resident could not complete the command"
"""Reason returned when performing one command raised instead of answering."""


_PAUSE_ACTION: Final[str] = "pause"
"""Action id prefix proving a recorded stop came from the global pause and not from the user."""

_ACTION_ATTEMPTS: Final[int] = 3
"""Attempts one refused transfer action gets before the pause reports it instead of a done stop."""

_STOPPED_TRANSFER_STATES: Final[frozenset[str]] = frozenset(
    {"stoppedDL", "pausedDL", "stoppedUP", "pausedUP", "error", "missingFiles"}
)
"""Client states proving a transfer is not working, whoever or whatever stopped it."""

_NO_SUBSCRIPTIONS: Final[str] = "This resident was composed without a torrent client"
"""Reason returned for a subscription command with no subscription service behind it."""

_NOT_PLANNABLE: Final[str] = "The sources cannot be planned into an executable run"
"""Reason returned when planning fails or the plan carries a blocking problem."""

_MUTATING_KINDS: Final[frozenset[str]] = frozenset(
    {
        "deletion_start",
        "deletion_retry",
        "set_auto",
        "recipe_update",
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
        "reacquire",
        "transfer",
    }
)
"""Commands whose outcome is recorded, so repeating an identifier repeats no effect."""

_SLOW_KINDS: Final[frozenset[str]] = frozenset(
    {
        "discover",
        "register_external",
        "preview",
        "resume_preview",
        "subscriptions_check",
        "acquisition",
        "download",
        "reacquire",
        "retry_prepare",
        "subscription_retry_prepare",
        "library_refresh",
        "library_open",
        "deletion_preview",
        "deletion_validate",
        "deletion_start",
        "deletion_retry",
    }
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


class _ActionRecord(Enum):
    """Outcome of the write that must precede handing one transfer action to the client."""

    SENT = auto()
    SUPERSEDED = auto()
    UNSAVED = auto()


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
    retry: bool = True
    recipe: RecipePreferences = field(default_factory=RecipePreferences)


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


@dataclass(frozen=True, slots=True)
class _NotificationTarget:
    set_id: str
    product: ProductConfirmation
    identity: LibraryFileIdentity
    attempt: tuple[str, int]


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
        open_result: Callable[[Path], None] | None = None,
        ready_store: ReadyStore | None = None,
        scan_interval_s: float = SCAN_INTERVAL_S,
        recycler: Callable[[Path, tuple[int, int, int, int]], RecycleResult] | None = None,
    ) -> None:
        """Load the persisted state and prepare the owner thread and its pool."""
        self._service: AppService = service
        self._store: WatchStateStore = store
        self._instance_id: str = instance_id
        self._clock: Clock = clock
        self._scan_interval_s: float = scan_interval_s
        self._broadcast: Broadcast | None = broadcast
        self._open_panel: Callable[[], None] | None = open_panel
        self._open_result: Callable[[Path], None] | None = open_result
        self._notification_targets: dict[str, _NotificationTarget | None] = {}
        self._notification_problem: str | None = None
        self._panels: set[str] = set()
        self._panel_opening_at: float = 0.0
        self._state: WatchState = store.load()
        self._restart_requests: tuple[ProcessingRequest, ...] = self._state.requests
        self._run_groups: dict[str, tuple[InspectedSourceGroup, ...]] = {}
        self._ready_store: ReadyStore | None = ready_store
        self._recycler: Callable[[Path, tuple[int, int, int, int]], RecycleResult] | None = recycler
        self._deleting: dict[str, str] = {}
        self._deletion_retries: dict[str, int] = {}
        self._deletion_scopes: dict[str, frozenset[Path]] = {}
        self._deletion_dirty: dict[str, set[Path]] = {}
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
        self._completed_groups: dict[tuple[str, int, int, RequestState], frozenset[str]] = {}
        self._progress_lock: threading.Lock = threading.Lock()
        self._run_views: dict[str, RunProgressSnapshot] = {}
        self._run_events: dict[str, dict[tuple[str, str | None, str | None], RunEvent]] = {}
        self._run_products: dict[str, dict[str, Artifact]] = {}
        self._shutting_down: bool = False
        self._serving: bool = False
        self._active_io: int = 0
        self._transfers: TransferInspector | None = (
            TransferInspector(service.acquisition, service.workspace_root) if service.acquisition is not None else None
        )
        self._transfers_at: float | None = None
        self._transfers_inspecting: bool = False
        self._action_attempts: dict[str, tuple[str, int]] = {}
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
        self._ready_library: tuple[LibrarySet, ...] = ()
        self._deletion_previews: dict[str, tuple[DeletionPreview, str | None, int]] = {}
        self._ledger: WatchLedger = WatchLedger()
        self._settle_at: float | None = None
        self._watch_mode: str = "inactive"
        self._fresh_sources: set[Path] = set()
        self._file_version: int = 0
        self._group_versions: dict[str, int] = {}
        self._reconciled_version: int = 0
        self._history: HistoryJournal = HistoryJournal(store.history_path())
        if self._state.reservations:
            self._state = replace(self._state, reservations=())
            self._save(self._state)

    def files_changed(self, change: DirectoryChange) -> None:
        """Coalesce filesystem changes into one bounded owner notification."""
        if change.reason == "resume":
            if self._transfers is not None:
                self._transfers.reset_clock()
            self._queue.put(self._schedule_subscriptions)
        paths: set[Path] = {path for path in change.paths if self._watched_path(path)}
        paths.difference_update(
            set(change.modified_paths) & {self._service.workspace_root, self._service.workspace_root / READY_DIRECTORY}
        )
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
            for operation_id, scope in self._deletion_scopes.items():
                self._deletion_dirty[operation_id].update(
                    scope if reconcile else (item for item in scope if any(item.is_relative_to(path) for path in paths))
                )
            if reconcile or paths.intersection(
                {self._service.workspace_root, self._service.workspace_root / READY_DIRECTORY}
            ):
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

    def _acquisition_groups(self, acquisition: AcquisitionConfirmation) -> list[str]:
        groups: set[str] = set()
        for name in sorted(_assigned_files(acquisition)):
            relative: Path = (Path(acquisition.directory) / name).parent
            candidate: ArtifactName | None = classify_artifact(Path(name), resolve_route(relative))
            if candidate is not None:
                groups.add(create_group_id(relative, candidate.stem))
        return sorted(groups)

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
        if action.startswith("notification:"):
            self._open_notification(action.removeprefix("notification:"))
            return
        if action == "open":
            if self._notification_problem is not None:
                self._notification_problem = None
                self._publish_state()
            self._show_panel()
            return
        if action not in {"pause", "resume", "shutdown"}:
            return
        paused: bool = action in {"pause", "resume"}
        self._perform(
            ControlRequest(
                command_id=f"tray-{token_hex(_ID_BYTES)}",
                kind="set_auto" if paused else "shutdown",
                payload={"enabled": action == "resume"} if paused else {},
            )
        )

    def _show_panel(self, notice: str | None = None) -> None:
        if self._panels:
            payload: dict[str, object] = {} if notice is None else {"notification_problem": notice}
            self._publish({"event": "panel_open", "payload": payload}, terminal=False)
        elif self._open_panel is not None and time.monotonic() - self._panel_opening_at > _PANEL_START_GRACE_S:
            self._panel_opening_at = time.monotonic()
            self._open_panel()

    def serve(self) -> None:
        """Run the owner loop until a shutdown drains every active request."""
        threading.current_thread().name = OWNER_THREAD_NAME
        self._serving = True
        self._history.events(self._clock())
        self._record_history(WatchState(), recovering=True)
        self._restore_provider_locks()
        self._finish_pending_commands()
        self._reconcile_subscription_sources()
        self._report_preflight()
        self._service.set_background_admission(self._state.policy.auto_enabled)
        if not self._state.policy.auto_enabled:
            self._service.pause_runs()
        self._prepare_transfers()
        self._schedule_transfers()
        self._schedule_subscriptions()
        self._retry_ready()
        try:
            self._loop()
        finally:
            self._serving = False
            self._pool.shutdown(wait=True)

    def _report_preflight(self) -> None:
        findings: tuple[PreflightFinding, ...] = preflight(self._state)
        if not findings:
            return
        logger.info(
            "Automation preflight",
            findings=tuple(sorted({finding.kind.value for finding in findings})),
        )

    def _prepare_transfers(self) -> None:
        if self._service.acquisition is None:
            return
        self._active_io += 1
        self._pool.submit(self._prepare_client)

    def _prepare_client(self) -> None:
        problem: str | None = None
        try:
            acquisition: AcquisitionService | None = self._service.acquisition
            if acquisition is not None:
                acquisition.prepare_client()
                self._recover_acquisition_confirmations(acquisition)
        except (AniShiftError, OSError, ValueError) as error:
            problem = sanitize_event_message(str(error))
            logger.warning("The private torrent client was not prepared", error_class=type(error).__name__)
        finally:
            self._queue.put(lambda: self._prepared_client(problem))

    def _recover_acquisition_confirmations(self, acquisition: AcquisitionService) -> None:
        needed: bool = self._on_owner(
            lambda: (
                self._working()
                and any(
                    item.state in {AcquisitionState.PENDING_SEND, AcquisitionState.UNCERTAIN}
                    for item in self._state.acquisitions
                )
            )
        )
        if not needed:
            return
        with acquisition.requests("recovery"):
            present: frozenset[str] = acquisition.queued_hashes()
        self._on_owner(lambda: self._reconcile_acquisitions(present))

    def _prepared_client(self, problem: str | None) -> None:
        self._active_io -= 1
        if problem is not None:
            self._transfers_problem = problem
        self._publish_state()

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
            self._ready_library = project_library(
                self._state, self._service.workspace_root, tuple(group.source for group in workspace.groups)
            )
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
            self._restore_paused()
            self._refresh_automatic()
            self._publish_state()
            if workspace.pending_paths and self._state.policy.auto_enabled:
                self._inspection_at = time.monotonic() + self._scan_interval_s
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
        if not self._state.policy.auto_enabled and not self._files_queued:
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
        if (
            paths
            and all(
                path.relative_to(self._service.workspace_root).parts[0].casefold() == READY_DIRECTORY
                for path in paths
                if path != self._service.workspace_root
            )
            and self._service.workspace_root not in paths
        ):
            self._inspect_ready_changes(paths)
            return
        workspace: InspectedWorkspace | None = None
        try:
            workspace = self._service.discover(changed_paths=paths)
        except (AniShiftError, OSError) as problem:
            logger.warning("Library reconciliation failed", error_class=type(problem).__name__)
        finally:
            self._queue.put(_Inspected(workspace))

    def _inspect_ready_changes(self, paths: tuple[Path, ...]) -> None:
        groups: tuple[SourceGroup, ...] | None = None
        try:
            groups = self._service.library_inventory(paths)
        except (AniShiftError, OSError) as problem:
            logger.warning("Ready inventory reconciliation failed", error_class=type(problem).__name__)
        finally:
            self._queue.put(lambda: self._record_ready_inventory(groups))

    def _record_ready_inventory(self, groups: tuple[SourceGroup, ...] | None) -> None:
        self._inspecting = False
        if groups is not None:
            self._ready_library = project_library(self._state, self._service.workspace_root, groups)
            self._publish_state()
        self._inspect_changes()

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
        succeeded_groups: dict[str, frozenset[str]] = {
            request.request_id: self._succeeded_groups(request)
            for request in self._state.requests
            if request.state in {RequestState.FAILED, RequestState.PARTIAL}
        }
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
                succeeded_groups=succeeded_groups,
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
            recipe=self._state.recipes,
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
            owned: frozenset[str] = frozenset(
                name for name in _assigned_files(acquisition) if directory / name in paths
            )
            if not owned:
                continue
            return acquisition.origin if owned <= frozenset(acquisition.complete_files) else None
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
            if request.kind == "shutdown":
                self._begin_shutdown()
            command.answer(ControlResponse.succeeded(dict(receipt.outcome)))
            return
        if request.kind in _INSTANCE_CHECKED_KINDS and request.instance_id not in {None, self._instance_id}:
            command.answer(ControlResponse.refused(ControlErrorCode.STALE_INSTANCE, _STALE_INSTANCE))
            return
        if request.kind in _SLOW_KINDS:
            if self._shutting_down:
                command.answer(_refuse(RefusalReason.SHUTTING_DOWN))
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
        self._deletion_previews = {
            key: value for key, value in self._deletion_previews.items() if value[1] != session_id
        }
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
        except Exception as problem:  # noqa: BLE001 - the owner must survive any single faulty command
            reason: str = failure_code(problem) or _COMMAND_FAILURE_REASON
            logger.warning(
                "A control command failed",
                command_kind=command.request.kind,
                command_id=command.request.command_id,
                error_class=type(problem).__name__,
                cause_class=type(problem.__cause__).__name__ if problem.__cause__ is not None else None,
                reason=reason,
            )
            receipt: CommandReceipt | None = self._receipt(command.request)
            if command.request.kind == "start" and receipt is not None:
                command.answer(ControlResponse.succeeded(dict(receipt.outcome)))
            else:
                command.answer(ControlResponse.refused(ControlErrorCode.INTERNAL, _COMMAND_FAILED, reason))

    def _perform(self, request: ControlRequest) -> ControlResponse:  # noqa: C901, PLR0911, PLR0912
        match request.kind:
            case "history":
                query: object = request.payload.get("query", "")
                if not isinstance(query, str):
                    return _invalid("History search requires text")
                items: tuple[HistoryEvent, ...] = self._history.materials(self._clock(), query)
                if self._history.problem is not None:
                    return ControlResponse.refused(
                        ControlErrorCode.REFUSED, "Operational history is unavailable", self._history.problem
                    )
                return ControlResponse.succeeded({"items": [encode_view(item) for item in items]})
            case "retry_prepare" | "subscription_retry_prepare":
                inventory: tuple[SourceGroup, ...] = self._service.library_inventory()
                return self._on_owner(lambda: self._history_action(request, inventory))
            case "reacquire":
                return self._reacquire_command(request)
            case "status":
                return ControlResponse.succeeded(self._status())
            case "panel_attach":
                if request.session_id is None:
                    return _invalid("A panel requires a connected session")
                self._panels.add(request.session_id)
                return ControlResponse.succeeded({"attached": True})
            case "ready_retry":
                for request_id, result in tuple(self._run_results.items()):
                    self._prepare_ready(result, None, self._accepted_recipe(request_id))
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
                return ControlResponse.succeeded(encode_view(self._recorded_library(self._service.discover())))
            case (
                "library_refresh"
                | "library_open"
                | "deletion_preview"
                | "deletion_validate"
                | "deletion_start"
                | "deletion_retry"
            ):
                groups: tuple[SourceGroup, ...] = self._service.library_inventory()
                return self._on_owner(lambda: self._library_command(request, groups))
            case "library_details":
                return self._library_details(request)
            case "deletion_get":
                operation: PendingDeletion | None = self._deletion_by_id(_text(request.payload, "operation_id"))
                return (
                    self._library_refusal("library_scope_changed")
                    if operation is None
                    else ControlResponse.succeeded(encode_view(operation))
                )
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
            case "recipes_get":
                return ControlResponse.succeeded(encode_view(self._state.recipes))
            case "recipe_update":
                return self._update_recipe(request)
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
        pausing: bool = self._pausing()
        incomplete: bool = not pausing and self._pause_incomplete()
        materials: list[dict[str, object]] = self._processing_materials()
        return {
            "instance_id": self._instance_id,
            "notification_problem": self._notification_problem,
            "pid": os.getpid(),
            "run_progress": self._progress_views(),
            "materials": materials,
            "material_counts": {
                "downloading": sum(
                    item.get("stage") == "download" and item.get("active") is True for item in materials
                ),
                "processing": sum(
                    item.get("stage") == "processing" and item.get("state") == RequestState.RUNNING.value
                    for item in materials
                ),
                "waiting": sum(
                    item.get("stage") == "waiting"
                    or (item.get("stage") == "processing" and item.get("state") in {"accepted", "paused"})
                    for item in materials
                ),
            },
            "recovery_problems": [
                {"run_id": request.request_id, "group_ids": list(request.group_ids), "problem": request.problem}
                for request in self._state.requests
                if request.problem is not None
            ],
            "auto_enabled": policy.auto_enabled,
            "paused": not policy.auto_enabled and not pausing and not incomplete,
            "pausing": pausing,
            "pause_incomplete": incomplete,
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
                    "name": item.release_title or "Materiał",
                    "stalled": self._transfers is not None and item.info_hash in self._transfers.stalled,
                    "group_ids": self._acquisition_groups(item),
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
            "library": [
                {
                    "group_id": group.group_id,
                    "set_id": group.set_id,
                    "name": group.name,
                    "main_result": group.main_result,
                    "target": None if group.target is None else group.target.value,
                }
                for group in self._ready_library
                if group.available
            ],
            "library_problems": [
                encode_view(group)
                for group in self._ready_library
                if not group.available and any(item.identity is not None for item in group.files)
            ],
            "deletions": [
                {
                    "operation_id": item.operation_id,
                    "set_id": item.set_id,
                    "name": next(
                        (group.stem for group in self._state.ready_groups if group.set_id == item.set_id), item.set_id
                    ),
                    "remaining": len(item.files) - len(item.recycled),
                    "can_confirm": any(
                        file.identity is not None
                        for group in self._ready_library
                        if group.set_id == item.set_id
                        for file in group.files
                    ),
                    "active": item.operation_id in self._deleting,
                    "recycled": len(item.recycled),
                    "total": len(item.files),
                    "uncertain": any(
                        result.status is DeletionStatus.UNCERTAIN
                        or (result.status is DeletionStatus.INFLIGHT and item.operation_id not in self._deleting)
                        for result in item.outcomes
                    ),
                    "retryable": self._deletion_retry_current(item),
                }
                for item in self._state.pending_deletions
            ],
            "shutting_down": self._shutting_down,
            "updated_at": self._now(),
        }

    def _processing_materials(self) -> list[dict[str, object]]:
        materials: dict[str, dict[str, object]] = {}
        for acquisition in self._state.acquisitions:
            materials.update(self._download_materials(acquisition))
        requests: dict[str, ProcessingRequest] = {
            group_id: request for request in self._state.requests for group_id in request.group_ids
        }
        materials = {
            group_id: row
            for group_id, row in materials.items()
            if group_id in requests or not row.get("downloaded") or row.get("source_present")
        }
        completed: dict[str, frozenset[str]] = {}
        for group_id, request in requests.items():
            if request.request_id not in completed:
                completed[request.request_id] = self._succeeded_groups(request)
            row: dict[str, object] = materials.get(group_id, {"material_id": group_id, "group_id": group_id})
            if group_id in completed[request.request_id]:
                materials.pop(group_id, None)
                continue
            row.update(
                name=row.get("name") or self._processing_name(request, group_id),
                stage="processing",
                state=request.state.value,
                run_id=request.request_id,
                group_ids=list(request.group_ids),
                active=request.state in _ACTIVE_STATES,
                problem=request.problem,
            )
            materials[group_id] = row
        for group in () if self._library is None else self._library.groups:
            if group.group_id in requests or group.group_id in materials or group.source.route.target is None:
                continue
            readiness = resolve_readiness(group)
            if readiness.ready:
                continue
            materials[group.group_id] = {
                "material_id": group.group_id,
                "group_id": group.group_id,
                "name": next(
                    (artifact.path.name for artifact in group.artifacts if artifact.path is not None), group.source.stem
                ),
                "stage": "waiting",
                "reason": None if readiness.reason is None else readiness.reason.value,
                "active": False,
            }
        return list(materials.values())

    def _group_succeeded(self, request: ProcessingRequest, group_id: str) -> bool:
        return group_id in self._succeeded_groups(request)

    def _succeeded_groups(self, request: ProcessingRequest) -> frozenset[str]:
        if request.state is RequestState.SUCCEEDED:
            return frozenset(request.group_ids)
        if request.state is RequestState.PAUSED:
            return self._journal_completed_groups(request) or frozenset()
        if request.state in _ACTIVE_STATES:
            with self._progress_lock:
                finished: frozenset[str] = frozenset(
                    event.group_id
                    for event in self._run_events.get(request.request_id, {}).values()
                    if event.kind is RunEventKind.GROUP_FINISHED
                    and event.group_id is not None
                    and event.state is TaskState.SUCCEEDED
                )
            return finished & (self._journal_completed_groups(request) or frozenset()) if finished else frozenset()
        key: tuple[str, int, int, RequestState] = (
            request.request_id,
            request.generation,
            request.attempts,
            request.state,
        )
        if key not in self._completed_groups:
            completed: frozenset[str] | None = self._journal_completed_groups(request)
            if completed is None:
                return frozenset()
            self._completed_groups[key] = completed
        return self._completed_groups[key]

    def _journal_completed_groups(self, request: ProcessingRequest) -> frozenset[str] | None:
        try:
            document: object = json.loads(self._store.run_path(request.request_id).read_bytes())
            if not isinstance(document, dict) or document.get("version") != CHECKPOINT_VERSION:
                return None
            plan: ExecutionPlan = decode_view(ExecutionPlan, document.get("plan"))
        except AniShiftError, OSError, ValueError, TypeError:
            return None
        return frozenset(
            group.group_id
            for group in plan.groups
            if group.intent in request.intents
            and not group.task_ids
            and not any(problem.is_blocking for problem in group.problems)
        )

    def _processing_name(self, request: ProcessingRequest, group_id: str) -> str:
        with self._progress_lock:
            view: RunProgressSnapshot | None = self._run_views.get(request.request_id)
            if view is not None and group_id in view.labels:
                return view.labels[group_id]
        names: tuple[str, ...] = tuple(item[0] for item in request.fingerprints.get(group_id, ()))
        intent: GroupIntent | None = next((item for item in request.intents if item.group_id == group_id), None)
        route: WorkflowRoute = WorkflowRoute(resolve_route(Path()).place, None if intent is None else intent.target)
        primary: str | None = next(
            (
                name
                for name in names
                if (candidate := classify_artifact(Path(name), route)) is not None and candidate.is_primary
            ),
            None,
        )
        return Path(primary or names[0]).name if names else group_id

    def _download_materials(self, acquisition: AcquisitionConfirmation) -> dict[str, dict[str, object]]:
        transfer = next(
            (
                item
                for item in (() if self._transfers is None else self._transfers.snapshot())
                if item.info_hash == acquisition.info_hash
            ),
            None,
        )
        files = () if self._transfers is None else self._transfers.declared(acquisition.info_hash)
        measured: dict[str, float] = {
            item.name.replace("\\", "/"): item.progress for item in files if item.priority > 0
        }
        active: bool = transfer is not None and transfer.state in {
            "downloading",
            "forcedDL",
            "stalledDL",
            "metaDL",
            "forcedMetaDL",
        }
        common: dict[str, object] = {
            "info_hash": acquisition.info_hash,
            "acquisition_id": acquisition.operation_id,
            "acquisition_state": acquisition.state.value,
            "content_started": acquisition.content_started,
            "stage": "download",
            "state": None if transfer is None else transfer.state,
            "active": active and acquisition.state is AcquisitionState.ACCEPTED and not acquisition.problem,
            "problem": acquisition.problem,
        }
        rows: dict[str, dict[str, object]] = {}
        for index, name, _size in acquisition.file_layout:
            relative: Path = (Path(acquisition.directory) / name).parent
            candidate: ArtifactName | None = classify_artifact(Path(name), resolve_route(relative))
            if candidate is None:
                continue
            group_id: str = create_group_id(relative, candidate.stem)
            ready: ReadyGroup | None = next(
                (
                    item
                    for item in self._state.ready_groups
                    if (Path(acquisition.directory) / name).as_posix() in (*item.sources, *item.pending_sources)
                ),
                None,
            )
            if ready is not None:
                group_id = ready.group_id
            fraction: float | None = measured.get(name)
            if name in acquisition.complete_files:
                fraction = 1.0
            previous: dict[str, object] | None = rows.get(group_id)
            if previous is not None:
                previous["progress"] = (
                    min(float(str(previous["progress"])), fraction)
                    if previous["progress"] is not None and fraction is not None
                    else None
                )
                if candidate.is_primary:
                    previous.update(material_id=f"{acquisition.info_hash}:{index}", name=Path(name).name)
                previous["downloaded"] = bool(previous["downloaded"]) and name in acquisition.complete_files
                previous["source_present"] = (
                    bool(previous["source_present"])
                    or (self._service.workspace_root / acquisition.directory / name).is_file()
                )
                continue
            rows[group_id] = {
                **common,
                "material_id": f"{acquisition.info_hash}:{index}",
                "group_id": group_id,
                "name": Path(name).name,
                "progress": fraction,
                "downloaded": name in acquisition.complete_files,
                "source_present": (self._service.workspace_root / acquisition.directory / name).is_file(),
            }
        for row in rows.values():
            if row["downloaded"]:
                row.update(stage="waiting", reason="preparing", active=False)
        if rows or acquisition.file_layout:
            return rows
        if acquisition.state is AcquisitionState.COMPLETE:
            return {}
        return {
            acquisition.operation_id: {
                **common,
                "material_id": acquisition.operation_id,
                "name": (transfer.name if transfer is not None and transfer.name != acquisition.info_hash else None)
                or acquisition.release_title
                or "Materiał",
                "progress": None if transfer is None else transfer.progress,
            }
        }

    def _library_details(self, request: ControlRequest) -> ControlResponse:
        identifier: str | None = _text(request.payload, "set_id")
        group: LibrarySet | None = next((item for item in self._ready_library if item.set_id == identifier), None)
        if group is None:
            return self._library_refusal("library_set_missing")
        return ControlResponse.succeeded(encode_view(group))

    def _library_command(self, request: ControlRequest, groups: tuple[SourceGroup, ...]) -> ControlResponse:
        self._ready_library = project_library(self._state, self._service.workspace_root, groups)
        self._publish_state()
        if request.kind == "library_refresh":
            return ControlResponse.succeeded({"sets": [encode_view(item) for item in self._ready_library]})
        if request.kind == "deletion_retry":
            return self._retry_deletion(request)
        identifier: str | None = _text(request.payload, "set_id")
        group: LibrarySet | None = next((item for item in self._ready_library if item.set_id == identifier), None)
        if group is None:
            return self._library_refusal("library_set_missing")
        if request.kind == "library_open":
            if not group.available:
                return self._library_refusal(group.problem or "library_result_missing")
            return ControlResponse.succeeded({"path": group.main_result})
        return self._deletion_preview(request, group)

    def _deletion_preview(self, request: ControlRequest, group: LibrarySet) -> ControlResponse:
        refusal: ControlResponse | None = self._deletion_conflict(group)
        if refusal is not None:
            return refusal
        files: tuple[LibraryFileIdentity, ...] = tuple(
            item.identity for item in group.files if item.identity is not None
        )
        if not files or any(not source_is_available(self._service.workspace_root / item.path) for item in files):
            return self._library_refusal("library_source_busy" if files else "library_set_missing")
        if request.kind in {"deletion_validate", "deletion_start"}:
            validated: ControlResponse = self._validate_deletion(request, group, files)
            if not validated.ok or request.kind == "deletion_validate":
                return validated
            return self._start_deletion(request, group, files)
        if request.session_id in self._closed_sessions:
            return _refuse(RefusalReason.SESSION_CLOSED)
        preview: DeletionPreview = DeletionPreview(
            f"delete-{token_hex(_ID_BYTES)}", self._instance_id, group.set_id, group.name, files
        )
        self._deletion_previews = {
            key: value for key, value in self._deletion_previews.items() if value[1] != request.session_id
        }
        with self._previews_lock:
            self._deletion_previews[preview.preview_id] = (preview, request.session_id, self._file_version)
        return ControlResponse.succeeded(encode_view(preview))

    def _deletion_conflict(self, group: LibrarySet) -> ControlResponse | None:
        if self._shutting_down:
            return _refuse(RefusalReason.SHUTTING_DOWN)
        record: ReadyGroup | None = next(
            (item for item in self._state.ready_groups if item.set_id == group.set_id), None
        )
        if record is None:
            return self._library_refusal("library_ownership_unknown")
        if record.pending_sources or self._torrent_owns_set(group):
            return self._library_refusal("library_source_held")
        refusal: ControlResponse | None = self._conflict((group.group_id, record.set_id), "")
        if refusal is not None:
            return refusal
        if any(
            item.identity is None
            and (
                (self._service.workspace_root / item.path).exists()
                or (self._service.workspace_root / item.path).is_symlink()
            )
            for item in group.files
        ):
            return self._library_refusal("library_scope_changed")
        return None

    def _torrent_owns_set(self, group: LibrarySet) -> bool:
        paths: set[str] = {item.path for item in group.files}
        return any(
            paths.intersection((Path(item.directory) / name).as_posix() for name in _assigned_files(item))
            for item in self._state.acquisitions
        )

    def _start_deletion(
        self, request: ControlRequest, group: LibrarySet, files: tuple[LibraryFileIdentity, ...]
    ) -> ControlResponse:
        if self._recycler is None:
            return self._library_refusal("recycle_unsupported")
        operation: PendingDeletion = PendingDeletion(
            f"recycle-{token_hex(_ID_BYTES)}",
            group.set_id,
            self._now(),
            tuple((item.path, item.size, item.modified_ns) for item in files),
            identities=tuple((item.path, item.device, item.inode) for item in files),
            instance_id=self._instance_id,
        )
        outcome: CommandOutcome = {"operation_id": operation.operation_id}
        refusal: ControlResponse | None = self._commit(
            request, replace(self._state, pending_deletions=(*self._state.pending_deletions, operation)), outcome
        )
        if refusal is not None:
            return refusal
        self._deletion_previews.pop(str(request.payload.get("preview_id", "")), None)
        with self._previews_lock:
            for previous in self._state.pending_deletions:
                if previous.set_id == group.set_id and previous.operation_id != operation.operation_id:
                    self._deletion_retries.pop(previous.operation_id, None)
                    self._deletion_scopes.pop(previous.operation_id, None)
                    self._deletion_dirty.pop(previous.operation_id, None)
        self._launch_deletion(operation)
        return ControlResponse.succeeded(outcome)

    def _deletion_by_id(self, operation_id: str | None) -> PendingDeletion | None:
        return next((item for item in self._state.pending_deletions if item.operation_id == operation_id), None)

    def _retry_deletion(self, request: ControlRequest) -> ControlResponse:
        operation: PendingDeletion | None = self._deletion_by_id(_text(request.payload, "operation_id"))
        if operation is None or not self._deletion_retry_current(operation):
            return self._library_refusal("library_scope_changed")
        group: LibrarySet | None = next((item for item in self._ready_library if item.set_id == operation.set_id), None)
        if group is None or operation.instance_id != self._instance_id:
            return self._library_refusal("library_scope_changed")
        refusal: ControlResponse | None = self._deletion_conflict(group)
        if refusal is not None:
            return refusal
        if not self._deletion_scope_matches(operation, group):
            return self._library_refusal("library_scope_changed")
        outcome: CommandOutcome = {"operation_id": operation.operation_id}
        refusal = self._commit(request, self._state, outcome)
        if refusal is not None:
            return refusal
        self._launch_deletion(operation)
        return ControlResponse.succeeded(outcome)

    def _deletion_retry_current(self, operation: PendingDeletion) -> bool:
        group: LibrarySet | None = next((item for item in self._ready_library if item.set_id == operation.set_id), None)
        if group is None or operation.instance_id != self._instance_id:
            return False
        with self._previews_lock:
            version: int | None = self._deletion_retries.get(operation.operation_id)
            if version is None or max(self._reconciled_version, self._group_versions.get(group.group_id, 0)) > version:
                return False
        return self._deletion_scope_matches(operation, group, verify_files=False)

    def _launch_deletion(self, operation: PendingDeletion) -> None:
        self._deletion_retries.pop(operation.operation_id, None)
        self._deleting[operation.operation_id] = operation.set_id
        with self._previews_lock:
            self._deletion_scopes.setdefault(
                operation.operation_id,
                frozenset(self._service.workspace_root / name for name, _size, _stamp in operation.files),
            )
            self._deletion_dirty.setdefault(operation.operation_id, set())
        self._active_io += 1
        self._pool.submit(self._recycle_set, operation.operation_id)
        logger.info("Confirmed set recycling admitted", files=len(operation.files))
        self._publish_state()

    def _recycle_set(self, operation_id: str) -> None:
        try:
            while self._recycler is not None:
                groups: tuple[SourceGroup, ...] = self._service.library_inventory()
                item: LibraryFileIdentity | None = self._on_owner(
                    partial(self._begin_deletion_file, operation_id, groups)
                )
                if item is None:
                    break
                result: RecycleResult = self._recycler(
                    self._service.workspace_root / item.path, (item.size, item.modified_ns, item.device, item.inode)
                )
                saved: bool = self._on_owner(partial(self._finish_deletion_file, operation_id, item.path, result))
                if not saved or result.outcome != "recycled":
                    break
        except AniShiftError, OSError, ValueError:
            logger.warning("Set recycling interrupted; durable in-flight evidence retained")
        finally:
            self._queue.put(lambda: self._settle_deletion(operation_id))

    def _deletion_scope_matches(
        self, operation: PendingDeletion, group: LibrarySet, *, verify_files: bool = True
    ) -> bool:
        if not operation.identities or any(
            item.status in {DeletionStatus.INFLIGHT, DeletionStatus.UNCERTAIN} for item in operation.outcomes
        ):
            return False
        identities: dict[str, tuple[int, int]] = {name: (device, inode) for name, device, inode in operation.identities}
        expected: dict[str, LibraryFileIdentity] = {
            name: LibraryFileIdentity(name, size, stamp, *identities[name])
            for name, size, stamp in operation.files
            if name not in operation.recycled
        }
        with self._previews_lock:
            dirty: set[Path] = self._deletion_dirty.get(operation.operation_id, set())
            if any(self._service.workspace_root / name in dirty for name in expected):
                return False
        current: dict[str, LibraryFileIdentity] = {
            item.path: item.identity for item in group.files if item.identity is not None
        }
        return current == expected and (
            not verify_files
            or all(file_identity(self._service.workspace_root, name) == identity for name, identity in expected.items())
        )

    def _begin_deletion_file(self, operation_id: str, groups: tuple[SourceGroup, ...]) -> LibraryFileIdentity | None:
        operation: PendingDeletion | None = self._deletion_by_id(operation_id)
        self._ready_library = project_library(self._state, self._service.workspace_root, groups)
        group: LibrarySet | None = next(
            (item for item in self._ready_library if operation is not None and item.set_id == operation.set_id), None
        )
        if (
            operation is None
            or group is None
            or self._shutting_down
            or not self._deletion_scope_matches(operation, group)
        ):
            return None
        record: ReadyGroup | None = next(
            (item for item in self._state.ready_groups if item.set_id == group.set_id), None
        )
        if record is None or record.pending_sources or self._torrent_owns_set(group):
            return None
        files: tuple[LibraryFileIdentity, ...] = tuple(
            item.identity for item in group.files if item.identity is not None
        )
        if not files or any(not source_is_available(self._service.workspace_root / item.path) for item in files):
            return None
        item: LibraryFileIdentity = files[0]
        started: DeletionOutcome = DeletionOutcome(item.path, DeletionStatus.INFLIGHT, "recycle_inflight")
        if not self._save_deletion_outcome(operation, started):
            return None
        return item

    def _save_deletion_outcome(self, operation: PendingDeletion, outcome: DeletionOutcome) -> bool:
        updated: PendingDeletion = replace(
            operation,
            outcomes=(*(item for item in operation.outcomes if item.path != outcome.path), outcome),
            recycled=(*operation.recycled, outcome.path)
            if outcome.status is DeletionStatus.RECYCLED
            else operation.recycled,
        )
        return self._save(
            replace(
                self._state,
                pending_deletions=tuple(
                    updated if item.operation_id == operation.operation_id else item
                    for item in self._state.pending_deletions
                ),
            )
        )

    def _finish_deletion_file(self, operation_id: str, path: str, result: RecycleResult) -> bool:
        operation: PendingDeletion | None = self._deletion_by_id(operation_id)
        if operation is None:
            return False
        with self._previews_lock:
            if result.outcome == "refused" and self._service.workspace_root / path in self._deletion_dirty.get(
                operation_id, set()
            ):
                result = RecycleResult("uncertain", "library_scope_changed", result.receipt)
        saved: bool = self._save_deletion_outcome(
            operation, DeletionOutcome(path, DeletionStatus(result.outcome), result.reason, result.receipt)
        )
        logger.info("Native recycle file result recorded", outcome=result.outcome, saved=saved)
        self._publish_state()
        return saved

    def _settle_deletion(self, operation_id: str) -> None:
        self._deleting.pop(operation_id, None)
        self._active_io -= 1
        operation: PendingDeletion | None = self._deletion_by_id(operation_id)
        if operation is not None:
            self._record_deletion_history(operation)
        paths: tuple[Path, ...] = tuple(
            self._service.workspace_root / item.path
            for item in (() if operation is None else operation.outcomes)
            if item.status is not DeletionStatus.REFUSED
        )
        if paths:
            self.files_changed(DirectoryChange(paths=paths, reason="recycle_completed"))
        if (
            operation is not None
            and len(operation.recycled) != len(operation.files)
            and not any(
                item.status in {DeletionStatus.INFLIGHT, DeletionStatus.UNCERTAIN} for item in operation.outcomes
            )
        ):
            with self._previews_lock:
                self._deletion_retries[operation_id] = self._file_version
        if operation_id in self._deletion_retries:
            with self._previews_lock:
                if operation is not None and any(
                    self._service.workspace_root / name in self._deletion_dirty.get(operation_id, set())
                    for name, _size, _stamp in operation.files
                    if name not in operation.recycled
                ):
                    self._deletion_retries.pop(operation_id, None)
        if operation_id not in self._deletion_retries:
            with self._previews_lock:
                self._deletion_scopes.pop(operation_id, None)
                self._deletion_dirty.pop(operation_id, None)
        self._publish_state()

    def _validate_deletion(
        self, request: ControlRequest, group: LibrarySet, files: tuple[LibraryFileIdentity, ...]
    ) -> ControlResponse:
        stored: tuple[DeletionPreview, str | None, int] | None = self._deletion_previews.get(
            str(request.payload.get("preview_id", ""))
        )
        if stored is None or stored[1] != request.session_id or request.instance_id != self._instance_id:
            return self._library_refusal("library_scope_changed")
        preview: DeletionPreview = stored[0]
        with self._previews_lock:
            changed: bool = max(self._reconciled_version, self._group_versions.get(group.group_id, 0)) > stored[2]
        if (
            changed
            or preview.set_id != group.set_id
            or preview.files != files
            or any(file_identity(self._service.workspace_root, item.path) != item for item in files)
        ):
            return self._library_refusal("library_scope_changed")
        return ControlResponse.succeeded(encode_view(preview))

    @staticmethod
    def _library_refusal(reason: str) -> ControlResponse:
        return ControlResponse.refused(ControlErrorCode.REFUSED, "The library operation is unavailable", reason=reason)

    def _pausing(self) -> bool:
        return not self._state.policy.auto_enabled and self._settling()

    def _pause_incomplete(self) -> bool:
        """Answer whether this pause reached its boundary leaving a transfer it could not stop."""
        return not self._state.policy.auto_enabled and any(_unstopped_pause(item) for item in self._state.acquisitions)

    def _settling(self) -> bool:
        """Answer whether any started work, accounting or owned I/O has still not reached its boundary."""
        return bool(
            self._pending
            or self._service.active_run_ids()
            or self._inspecting
            or self._active_io
            or self._ready_inflight
            or any(item.action_pending for item in self._state.acquisitions)
        )

    def _set_auto(self, request: ControlRequest) -> ControlResponse:
        enabled: bool | None = _flag(request.payload, "enabled")
        if enabled is None:
            return _invalid("A switch command needs an `enabled` flag")
        if enabled and self._shutting_down:
            return _refuse(RefusalReason.SHUTTING_DOWN)
        changed: bool = enabled != self._state.policy.auto_enabled
        policy = replace(self._state.policy, auto_enabled=enabled)
        candidate: WatchState = replace(self._state, policy=policy)
        if changed:
            candidate = self._resumed_transfers(candidate) if enabled else self._stopped_transfers(candidate)
        outcome: dict[str, str | int | bool | None] = {"auto_enabled": enabled}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        if refusal is not None:
            return refusal
        self._service.set_background_admission(enabled)
        if changed and not enabled:
            self._pause_work()
        elif changed:
            self._resume_work()
        self._refresh_automatic()
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _pause_work(self) -> None:
        """Hold the whole flow: no new admission, no schedule and every own working transfer stopped."""
        self._service.pause_runs()
        self._subscriptions_at = None
        self._settle_at = None
        self._inspection_at = None
        self._schedule_transfers()
        logger.info("Automation paused", transfers=len(self._state.pause_owned_transfers))

    def _resume_work(self) -> None:
        """Take up exactly the work this pause stopped, without reviving separately disabled entries."""
        self._service.resume_runs()
        if self._transfers is not None:
            self._transfers.reset_clock()
        self._prepare_transfers()
        self._schedule_subscriptions()
        self._schedule_transfers()
        if self._library is None:
            self.files_changed(DirectoryChange(reconcile=True, reason="resume"))
        elif self._library.pending_paths:
            self._inspect_changes()
        else:
            self._restore_paused()
        logger.info("Automation resumed")

    def _stopped_transfers(self, state: WatchState) -> WatchState:
        """Record the stop of every own transfer the client last showed working, in one durable state."""
        paused: tuple[str, ...] = self._working_transfers(state)
        if not paused:
            return state
        stopped: frozenset[str] = frozenset(paused)
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            replace(
                item,
                requested_action="stop",
                action_id=f"{_PAUSE_ACTION}-{token_hex(_ID_BYTES)}",
                action_pending=True,
                action_sent=False,
            )
            if item.info_hash in stopped
            else item
            for item in state.acquisitions
        )
        return replace(state, acquisitions=acquisitions, pause_owned_transfers=paused)

    def _resumed_transfers(self, state: WatchState) -> WatchState:
        """Take up only the transfers this pause stopped that still carry an active order."""
        paused: frozenset[str] = frozenset(state.pause_owned_transfers)
        if not paused:
            return state
        enabled: frozenset[str] | None = self._enabled_subscriptions()
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            replace(
                item,
                requested_action="resume",
                action_id=f"resume-{token_hex(_ID_BYTES)}",
                action_pending=True,
                action_sent=False,
            )
            if _resumable(item, paused, enabled)
            else item
            for item in state.acquisitions
        )
        return replace(state, acquisitions=acquisitions, pause_owned_transfers=_unfinished_pause_stops(state))

    def _finish_pause_restore(self) -> None:
        """Take up a transfer whose pause stop only reached the client after the resume had been recorded."""
        if not self._state.pause_owned_transfers or not self._state.policy.auto_enabled:
            return
        candidate: WatchState = self._resumed_transfers(self._state)
        if candidate != self._state:
            self._save(candidate)

    def _working_transfers(self, state: WatchState) -> tuple[str, ...]:
        return tuple(
            item.info_hash
            for item in state.acquisitions
            if (item.state is AcquisitionState.ACCEPTED or (item.action_pending and item.requested_action == "resume"))
            and item.requested_action not in {"stop", "cancel"}
        )

    def _enabled_subscriptions(self) -> frozenset[str] | None:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            return None
        try:
            return frozenset(item.subscription_id for item in service.list() if item.enabled)
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Subscriptions could not be read while resuming", error_class=type(problem).__name__)
            return frozenset()

    def _restore_paused(self) -> None:
        if not self._working() or self._library is None:
            return
        active: frozenset[str] = frozenset(self._service.active_run_ids())
        paused: tuple[ProcessingRequest, ...] = tuple(
            item for item in self._state.requests if item.state is RequestState.PAUSED and item.request_id not in active
        )
        if not paused or self._recovering:
            return
        self._recovering = True
        self._active_io += 1
        self._pool.submit(self._restore_runs, paused)

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
        if self._deleting_groups().intersection(group_ids):
            return self._library_refusal("library_deleting")
        moment: str = self._now()
        candidate: WatchState = self._state
        resumable: frozenset[str] = frozenset(
            item.request_id
            for item in candidate.requests
            if item.state is RequestState.PAUSED
            and set(item.group_ids) == set(group_ids)
            and item.request_id not in self._service.active_run_ids()
        )
        for group_id in group_ids:
            held: WatchState | None = reserve(
                replace(
                    candidate, requests=tuple(item for item in candidate.requests if item.request_id not in resumable)
                ),
                Reservation(
                    group_id=group_id,
                    fingerprint=self._previewed_fingerprint(group_id),
                    client_id=client_id,
                    reserved_at=moment,
                ),
            )
            if held is None:
                return _reservation_refusal(candidate, group_id, client_id)
            candidate = replace(held, requests=candidate.requests)
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
        recipes: RecipePreferences = self._state.recipes
        planned: tuple[ExecutionPlan, tuple[InspectedSourceGroup, ...], RebuildRequest | None] | None = self._plan(
            request,
            selection,
            recipes,
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
            recipe=recipes,
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
        recipes: RecipePreferences,
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
            plan: ExecutionPlan = self._plan_selection(payload, groups, selection, rebuild, recipes)
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
        recipes: RecipePreferences,
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
            return self._service.plan_manual(
                self._recovered_intents(intents),
                overrides=overrides,
                published=self._published_products(),
            )
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
            recipes=recipes,
            targets=self._recorded_targets(),
            published=self._published_products(),
        )

    def _accepted_recipe(self, request_id: str) -> RecipePreferences | None:
        """Return the recipe one accepted order was planned with, never the preferences of a later moment."""
        return next(
            (item.recipe for item in self._state.requests if item.request_id == request_id),
            None,
        )

    def _published_products(self) -> frozenset[Path]:
        """Return the files this program is proven to have published and which still hold the bytes it wrote."""
        root: Path = self._service.workspace_root
        proven: set[Path] = set()
        for item in self._state.products:
            path: Path = root / item.path
            if item.size >= 0 and (item.size, item.modified_ns) == _file_identity(path):
                proven.add(path)
        return frozenset(proven)

    def _recorded_targets(self) -> dict[str, WorkflowTarget]:
        """Return the target every finished set was accepted for, because ``ready`` names no target of its own."""
        return {item.group_id: item.target for item in self._state.ready_groups}

    def _recorded_library(self, workspace: InspectedWorkspace) -> InspectedWorkspace:
        """Return the library where every finished set names the target it was accepted for, not its new folder."""
        recorded: dict[str, WorkflowTarget] = self._recorded_targets()
        if not recorded:
            return workspace
        return replace(
            workspace,
            groups=tuple(_group_with_target(group, recorded.get(group.group_id)) for group in workspace.groups),
        )

    def _recovered_intents(self, intents: tuple[GroupIntent, ...]) -> tuple[GroupIntent, ...]:
        """Restore the target of a finished set from its record, because ``ready`` names no target of its own."""
        recorded: dict[str, WorkflowTarget] = self._recorded_targets()
        return tuple(
            intent
            if intent.target is not None or intent.group_id not in recorded
            else replace(intent, target=recorded[intent.group_id])
            for intent in intents
        )

    def _start(self, request: ControlRequest) -> ControlResponse:
        if self._shutting_down:
            return _refuse(RefusalReason.SHUTTING_DOWN)
        if not self._state.policy.auto_enabled:
            return _refuse(RefusalReason.PAUSED)
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
            attempts=previous.attempts + (1 if preview.retry else 0) if previous is not None else 1,
            accepted_at=self._now(),
            intents=tuple(group.intent for group in preview.plan.groups),
            automatic=preview.automatic,
            recipe=previous.recipe if previous is not None else preview.recipe,
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
        self._run_products[run_id] = {artifact.artifact_id: artifact for artifact in preview.plan.artifacts}
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
                            and artifact.lifetime is ArtifactLifetime.SOURCE
                            and (source_name := classify_artifact(artifact.path, group.source.route)) is not None
                            and source_name.is_primary
                        ),
                        group.source.stem,
                    )
                    for group in preview.groups
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
        artifacts: dict[str, Artifact] = self._run_products.pop(completion.request_id, {})
        if completion.result is not None:
            confirmations: tuple[ProductConfirmation, ...] = tuple(
                ProductConfirmation(
                    group.group_id,
                    artifacts[product.artifact_id].kind.value,
                    product.path.relative_to(self._service.workspace_root).as_posix(),
                    finished.generation,
                    finished.request_id,
                    finished.origin,
                    *_file_identity(product.path),
                )
                for group in completion.result.groups
                for product in group.products
                if product.artifact_id in artifacts and product.path.is_relative_to(self._service.workspace_root)
            )
            paths: frozenset[str] = frozenset(item.path for item in confirmations)
            candidate = replace(
                candidate, products=(*(item for item in candidate.products if item.path not in paths), *confirmations)
            )
            candidate = self._updated_ready_results(candidate, completion.result, finished, tuple(artifacts.values()))
        if finished.origin is RequestOrigin.USER and finished.state is not RequestState.PAUSED and products:
            candidate = _marked(candidate, finished, products, self._now())
        saved: bool = self._save(candidate)
        if saved and self._library is not None:
            self._ready_library = project_library(
                candidate, self._service.workspace_root, tuple(group.source for group in self._library.groups)
            )
        self._ledger.mark_finished(recorded.group_ids)
        groups: tuple[InspectedSourceGroup, ...] = self._run_groups.pop(completion.request_id, ())
        if saved and completion.result is not None:
            self._prepare_ready(completion.result, groups, finished.recipe, tuple(artifacts.values()))
            self._notify_ready_results(finished.group_ids, finished.request_id)
        self._publish_state()
        self._publish(
            {"event": "run_finished", "payload": {"run_id": completion.request_id}},
            terminal=True,
        )
        if finished.state is RequestState.PAUSED:
            self._restore_paused()

    def _updated_ready_results(
        self, state: WatchState, result: RunResult, request: ProcessingRequest, artifacts: tuple[Artifact, ...]
    ) -> WatchState:
        completed: frozenset[str] = frozenset(
            group.group_id for group in result.groups if group.status is GroupStatus.SUCCEEDED
        )
        records: list[ReadyGroup] = []
        for record in state.ready_groups:
            intent: GroupIntent | None = next(
                (item for item in request.intents if item.group_id == record.group_id), None
            )
            if record.group_id not in completed or intent is None:
                records.append(record)
                continue
            requested: frozenset[Path] = _requested_product_paths(
                artifacts, intent, request.settings.get("audio_output_profile")
            )
            selected: tuple[str, ...] = tuple(
                item.path
                for item in state.products
                if item.group_id == record.group_id
                and self._service.workspace_root / item.path in requested
                and (item.size, item.modified_ns) == _file_identity(self._service.workspace_root / item.path)
            )
            headline: str | None = main_product([Path(name).name for name in selected])
            records.append(
                replace(
                    record,
                    products=tuple(sorted(set(record.products) | set(selected))),
                    main_result=next((name for name in selected if Path(name).name == headline), None),
                    target=intent.target or record.target,
                )
            )
        return replace(state, ready_groups=tuple(records))

    def _run_result(self, request: ControlRequest) -> ControlResponse:
        run_id: str | None = _text(request.payload, "run_id")
        recorded: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == run_id), None
        )
        if recorded is None:
            return _invalid("The resident holds no such run")
        result: RunResult | None = self._run_results.get(recorded.request_id)
        if result is None and recorded.state not in {*_ACTIVE_STATES, RequestState.PAUSED}:
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
        completed: frozenset[str] = self._succeeded_groups(request)
        return RunResult(
            request.request_id,
            tuple(
                group
                if group.group_id in completed
                else replace(
                    group,
                    status=GroupStatus.CANCELLED
                    if request.state is RequestState.CANCELLED
                    else (GroupStatus.PARTIAL if group.products else GroupStatus.FAILED),
                    error_messages=(request.problem or "The previous attempt did not complete this group",),
                )
                for group in groups
            ),
        )

    # ── Settings, subscriptions and shutdown ──────────────────────────────────

    def _update_recipe(self, request: ControlRequest) -> ControlResponse:
        from anishift.config.field_access import recipe_with_value  # noqa: PLC0415
        from anishift.config.field_catalog import SettingSpec, recipe_setting_specs  # noqa: PLC0415

        setting_id: str | None = _text(request.payload, "setting_id")
        scope: str | None = _text(request.payload, "reset")
        specs: tuple[SettingSpec, ...] = recipe_setting_specs()
        recipes: RecipePreferences = self._state.recipes
        keys: set[str] = set(request.payload) - {"client_id"}
        if scope in {"translate", "audiobook", "all"} and keys == {"reset"}:
            for spec in specs:
                if scope == "all" or spec.setting_id.startswith(scope + "."):
                    recipes = recipe_with_value(recipes, spec, spec.default)
        elif setting_id is not None and keys == {"setting_id", "value"}:
            selected: SettingSpec | None = next((spec for spec in specs if spec.setting_id == setting_id), None)
            value: str | None = _text(request.payload, "value")
            if selected is None or value is None:
                return _invalid("Unknown recipe setting or value")
            recipes = recipe_with_value(recipes, selected, value)
        else:
            return _invalid("Choose one recipe setting or reset scope")
        outcome: dict[str, str | int | bool | None] = {"updated": recipes != self._state.recipes}
        refusal: ControlResponse | None = self._commit(request, replace(self._state, recipes=recipes), outcome)
        if refusal is not None:
            return refusal
        logger.info("Recipe preferences updated", setting_id=setting_id, reset_scope=scope)
        self._publish_state()
        return ControlResponse.succeeded(outcome)

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
        self._inspection_at = None
        self._service.set_background_admission(False)
        self._service.drain()
        logger.info("The resident is shutting down", active_runs=len(self._service.active_run_ids()))
        self._publish_state()

    def _subscription_command(self, request: ControlRequest) -> ControlResponse:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            if request.kind == "subscriptions_list":
                return ControlResponse.succeeded({"subscriptions": []})
            return ControlResponse.refused(ControlErrorCode.REFUSED, _NO_SUBSCRIPTIONS)
        handlers: Mapping[str, Callable[[ControlRequest, SubscriptionService], ControlResponse]] = {
            "subscription_add": self._subscription_add_command,
            "subscription_get": self._subscription_get_command,
            "subscriptions_list": self._subscriptions_list_command,
            "subscriptions_check": self._subscriptions_check_command,
            "subscription_range": self._subscription_range_command,
            "subscription_repeat": self._subscription_repeat_command,
        }
        return handlers.get(request.kind, self._subscription_mutation)(request, service)

    def _subscription_add_command(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        order: SubscriptionOrder = decode_view(SubscriptionOrder, request.payload.get("order"))
        identifier: str | None = resolve_subscription_id(order, service.list())
        if identifier is None:
            return ControlResponse.refused(
                ControlErrorCode.REFUSED,
                "The order does not identify an unambiguous season; select its catalog entry",
                "subscription_season_ambiguous",
            )
        outcome: dict[str, str | int | bool | None] = {
            "subscription_id": identifier,
            "order": json.dumps(encode_view(order)),
        }
        if "selected" in request.payload:
            selected: tuple[Decimal, ...] | None = _episode_numbers(request.payload, "selected")
            tail: Decimal | None = _episode_number(request.payload, "future_from")
            if selected is None or (request.payload.get("future_from") is not None and tail is None):
                return _invalid("A subscription needs valid selected episode numbers and a future boundary")
            outcome.update(
                selected=json.dumps([str(number) for number in selected]),
                future_from=None if tail is None else str(tail),
            )
        return self._accept_local_command(request, outcome)

    def _subscription_get_command(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        item: Subscription | None = next(
            (item for item in service.list() if item.subscription_id == request.payload.get("subscription_id")),
            None,
        )
        if item is None:
            return _invalid("Unknown subscription")
        return ControlResponse.succeeded({**encode_view(item), "work_states": self._subscription_work_states(item)})

    def _subscriptions_list_command(self, _request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        return ControlResponse.succeeded(
            {
                "subscriptions": [
                    {**_subscription_view(item, self._clock()), "work_states": self._subscription_work_states(item)}
                    for item in service.list()
                ]
            }
        )

    def _subscription_work_states(self, subscription: Subscription) -> dict[str, str]:
        states: dict[str, str] = {}
        acquisitions: dict[str, AcquisitionConfirmation] = {
            item.operation_id: item for item in self._state.acquisitions
        }
        requests: dict[str, ProcessingRequest] = {
            group_id: request for request in self._state.requests for group_id in request.group_ids
        }
        for episode in subscription.episodes:
            acquisition: AcquisitionConfirmation | None = acquisitions.get(episode.acquisition_id or "")
            if acquisition is None or acquisition.repeat_id != episode.repeat_id:
                continue
            materials: dict[str, dict[str, object]] = self._download_materials(acquisition)
            linked: dict[str, ProcessingRequest] = {key: requests[key] for key in materials if key in requests}
            state: str = "downloaded" if episode.state.value == "complete" else "ordered"
            if (
                materials
                and len(linked) == len(materials)
                and all(self._group_succeeded(request, key) for key, request in linked.items())
            ):
                state = "completed"
            elif any(
                request.state in {RequestState.FAILED, RequestState.PARTIAL, RequestState.CANCELLED}
                for request in linked.values()
            ):
                state = "processing_failed"
            elif linked:
                state = "processing"
            states[str(episode.number)] = state
        return states

    def _subscriptions_check_command(self, _request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        if not self._state.policy.auto_enabled:
            return _refuse(RefusalReason.PAUSED)
        outcomes: tuple[CheckOutcome, ...] = self._check_subscriptions(service, automatic=False)
        return ControlResponse.succeeded(
            {
                "checked": len(outcomes),
                "downloaded": sum(outcome.downloaded for outcome in outcomes),
                "problems": sum(1 for outcome in outcomes if outcome.problem),
                "outcomes": [encode_view(outcome) for outcome in outcomes],
            }
        )

    def _subscription_range_command(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        identifier: str | None = self._followed_subscription(request, service)
        selected: tuple[Decimal, ...] | None = _episode_numbers(request.payload, "selected")
        named: str | None = _text(request.payload, "future_from")
        tail: Decimal | None = _episode_number(request.payload, "future_from")
        if identifier is None or selected is None or (named is not None and tail is None):
            return _invalid("A stored range needs a known subscription and the episode numbers it selects")
        return self._accept_local_command(
            request,
            {
                "subscription_id": identifier,
                "selected": json.dumps([str(number) for number in selected]),
                "future_from": None if tail is None else str(tail),
            },
        )

    def _subscription_repeat_command(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        if not self._working():
            return _refuse(RefusalReason.PAUSED)
        identifier: str | None = self._followed_subscription(request, service)
        episodes: tuple[Decimal, ...] | None = _episode_numbers(request.payload, "episodes")
        if identifier is None or not episodes:
            return _invalid("A repeat needs a known subscription and the episode numbers it orders again")
        wanted: frozenset[Decimal] = frozenset(episodes)
        available: list[Decimal] = sorted(
            {
                Decimal(item.episode)
                for item in self._state.acquisitions
                if item.subscription_id == identifier
                and item.episode is not None
                and Decimal(item.episode) in wanted
                and self._subscription_source_present(item)
            }
        )
        if available:
            return ControlResponse.refused(
                ControlErrorCode.REFUSED,
                "A local source is available for the named episodes; use Manual to process it",
                "subscription_source_available",
                details={"episodes": [str(number) for number in available]},
            )
        return self._accept_local_command(
            request,
            {"subscription_id": identifier, "episodes": json.dumps([str(number) for number in episodes])},
        )

    def _subscription_source_present(self, acquisition: AcquisitionConfirmation) -> bool:
        targets: dict[str, WorkflowTarget] = self._recorded_targets()
        names: tuple[str, ...] = (
            acquisition.required_files if acquisition.state is AcquisitionState.COMPLETE else acquisition.complete_files
        )
        for name in names:
            relative: Path = Path(acquisition.directory) / name
            route: WorkflowRoute = resolve_route(relative.parent)
            artifact: ArtifactName | None = classify_artifact(relative, route)
            if artifact is not None:
                target: WorkflowTarget | None = targets.get(create_group_id(relative.parent, artifact.stem))
                artifact = classify_artifact(relative, replace(route, target=target or route.target))
            if artifact is not None and artifact.is_primary and (self._service.workspace_root / relative).is_file():
                return True
        return False

    @staticmethod
    def _followed_subscription(request: ControlRequest, service: SubscriptionService) -> str | None:
        identifier: str | None = _text(request.payload, "subscription_id")
        if identifier is None:
            return None
        return identifier if any(item.subscription_id == identifier for item in service.list()) else None

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
        chosen: tuple[ReleaseChoice, ...]
        response: ControlResponse
        chosen, response = self._on_owner(lambda: self._accept_download(request, choices))
        if not response.ok or not chosen:
            return response
        try:
            with acquisition.requests("user_download"):
                for choice in chosen:
                    acquisition.download((choice,))
                self._confirm_download(acquisition, frozenset(choice.release.info_hash.casefold() for choice in chosen))
        finally:
            self._on_owner(lambda: self._reconcile_acquisitions(frozenset()))
        return self._on_owner(lambda: self._download_summary(choices, chosen, response))

    def _confirm_download(self, acquisition: AcquisitionService, hashes: frozenset[str]) -> None:
        for present in acquisition.observe_added(hashes, may_observe=lambda: self._on_owner(self._working)):
            self._on_owner(partial(self._reconcile_acquisitions, present))

    def _download_summary(
        self,
        choices: tuple[ReleaseChoice, ...],
        sent: tuple[ReleaseChoice, ...],
        response: ControlResponse,
    ) -> ControlResponse:
        sent_hashes: set[str] = {item.release.info_hash.casefold() for item in sent}
        remaining: set[str] = {item.release.info_hash.casefold() for item in choices} - sent_hashes
        if not remaining:
            return response
        accepted: set[str] = {
            item.info_hash
            for item in self._state.acquisitions
            if item.info_hash in remaining and item.state in {AcquisitionState.ACCEPTED, AcquisitionState.COMPLETE}
        }
        if remaining <= accepted:
            return response
        return ControlResponse.refused(
            ControlErrorCode.REFUSED,
            "Some selected releases already have a recorded download intent",
            "download_recorded",
            details={"sent": len(sent_hashes), "accepted": len(accepted), "uncertain": len(remaining - accepted)},
        )

    def _accept_download(
        self,
        request: ControlRequest,
        choices: tuple[ReleaseChoice, ...],
    ) -> tuple[tuple[ReleaseChoice, ...], ControlResponse]:
        receipt: CommandReceipt | None = self._receipt(request)
        if receipt is not None:
            return (), ControlResponse.succeeded(dict(receipt.outcome))
        if self._shutting_down or not self._finish_pending_commands():
            return (), _refuse(RefusalReason.SHUTTING_DOWN)
        if not self._state.policy.auto_enabled:
            return (), _refuse(RefusalReason.PAUSED)
        existing: set[str] = {item.info_hash for item in self._state.acquisitions}
        unique: dict[str, ReleaseChoice] = {choice.release.info_hash.casefold(): choice for choice in choices}
        chosen: tuple[ReleaseChoice, ...] = tuple(choice for key, choice in unique.items() if key not in existing)
        confirmations: list[AcquisitionConfirmation] = [
            AcquisitionConfirmation(
                token_hex(_ID_BYTES),
                choice.release.info_hash,
                "",
                (),
                AcquisitionState.PENDING_SEND,
                RequestOrigin.USER,
                None,
                str(choice.episode) if choice.episode is not None else None,
                self._now(),
                nyaa_release_id=AcquisitionService.retained_reference(choice)[0],
                release_title=AcquisitionService.retained_reference(choice)[1],
            )
            for choice in chosen
        ]
        outcome: CommandOutcome = {"count": len(chosen), "directory": str(self._service.workspace_root)}
        failure: ControlResponse | None = self._commit(
            request,
            replace(
                self._state,
                acquisitions=(*self._state.acquisitions, *confirmations),
            ),
            outcome,
        )
        response: ControlResponse = failure or ControlResponse.succeeded(dict(outcome))
        if failure is not None or chosen:
            return chosen, response
        return (), self._download_summary(choices, (), response)

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
            or not self._state.policy.auto_enabled
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
        if self._shutting_down or not self._state.policy.auto_enabled or not service.is_current(subscription):
            return False
        if any(receipt.pending is not None for receipt in self._state.command_receipts):
            return False
        info_hash: str = choice.release.info_hash.casefold()
        identity: str | None = repeat_of(subscription, episode)
        if any(
            (item.info_hash == info_hash and item.repeat_id == identity)
            or (
                item.subscription_id == subscription.subscription_id
                and item.episode == str(episode)
                and item.repeat_id == identity
            )
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
            directory="",
            required_files=(),
            state=state,
            origin=origin,
            subscription_id=subscription.subscription_id,
            episode=str(episode),
            updated_at=self._now(),
            repeat_id=repeat_of(subscription, episode),
            nyaa_release_id=AcquisitionService.retained_reference(choice)[0],
            release_title=AcquisitionService.retained_reference(choice)[1],
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
        known: frozenset[tuple[str, str | None]] = frozenset(
            (item.info_hash, item.repeat_id) for item in self._state.acquisitions
        )
        existing: tuple[AcquisitionConfirmation, ...] = tuple(
            self._new_acquisition(subscription, episode, choice, AcquisitionState.ACCEPTED, origin=origin)
            for episode, choice in confirmed.items()
            if (choice.release.info_hash.casefold(), repeat_of(subscription, episode)) not in known
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
        working: bool = self._state.policy.auto_enabled
        active: bool = any(
            (item.state is AcquisitionState.ACCEPTED and working) or item.action_pending
            for item in self._state.acquisitions
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
        self._pool.submit(self._inspect_transfers, acquisitions, self._reserved_names())

    def _reserved_names(self) -> frozenset[str] | None:
        try:
            names: set[str] = set(_present_stems(self._service.workspace_root))
        except OSError:
            logger.warning("The download destination could not be read before reserving names")
            return None
        for item in self._state.acquisitions:
            names.update(_reserved_stems(item))
        for group in self._state.ready_groups:
            names.update(reserved_stem(name) for name in (*group.sources, *group.products))
        for deletion in self._state.pending_deletions:
            names.update(reserved_stem(name) for name, _size, _stamp in deletion.files)
        return frozenset(names)

    def _may_settle(self, item: AcquisitionConfirmation) -> bool:
        """Ask the owner, after the slow client read, whether this effect may still be admitted."""
        if not self._serving:
            return self._may_start_content(item)
        return self._on_owner(lambda: self._may_start_content(item))

    def _may_start_content(self, item: AcquisitionConfirmation) -> bool:
        return self._working() and any(
            row.operation_id == item.operation_id and row.action_id == item.action_id
            for row in self._state.acquisitions
        )

    def _working(self) -> bool:
        return self._state.policy.auto_enabled and not self._shutting_down

    def _inspect_transfers(
        self,
        acquisitions: tuple[AcquisitionConfirmation, ...],
        reserved: frozenset[str] | None,
    ) -> None:
        results: tuple[AcquisitionConfirmation, ...] = ()
        failure: str | None = None
        nature: tuple[str, str] | None = None
        try:
            if self._transfers is not None:
                acquisition: AcquisitionService | None = self._service.acquisition
                if acquisition is not None:
                    with acquisition.requests("transfer"):
                        acquisitions = self._apply_transfer_actions(acquisition, acquisitions)
                        results = acquisitions
                        results = self._transfers.inspect(
                            acquisitions, stall_after_s=self._state.policy.transfer_stall_s
                        )
                        results = self._settle_layouts(acquisition, results, reserved)
        except Exception as problem:  # noqa: BLE001
            failure = sanitize_event_message(str(problem))
            nature = (type(problem).__name__, failure_code(problem))
            if self._transfers is not None:
                self._transfers.reset_clock()
        finally:
            self._queue.put(lambda: self._record_transfers(results, failure, nature))

    def _settle_layouts(
        self,
        service: AcquisitionService,
        results: tuple[AcquisitionConfirmation, ...],
        reserved: frozenset[str] | None,
    ) -> tuple[AcquisitionConfirmation, ...]:
        if reserved is None:
            return tuple(self._settle_layout(service, item, None) for item in results)
        taken: set[str] = set(reserved)
        settled: list[AcquisitionConfirmation] = []
        for item in results:
            outcome: AcquisitionConfirmation = self._settle_layout(service, item, frozenset(taken))
            taken.update(_reserved_stems(outcome))
            settled.append(outcome)
        return tuple(settled)

    def _settle_layout(
        self,
        service: AcquisitionService,
        item: AcquisitionConfirmation,
        reserved: frozenset[str] | None,
    ) -> AcquisitionConfirmation:
        if (
            self._transfers is None
            or item.state is not AcquisitionState.ACCEPTED
            or item.problem is not None
            or item.content_started
            or not self._may_settle(item)
        ):
            return item
        if reserved is None:
            return replace(item, problem=_UNREADABLE_DESTINATION)
        if item.file_layout and _occupied(self._service.workspace_root, item.file_layout):
            return replace(item, problem=_OCCUPIED_DESTINATION)
        if item.file_layout:
            return self._start_content(service, item)
        declared: tuple[TorrentFile, ...] = self._transfers.declared(item.info_hash)
        layout: tuple[FileReservation, ...] = flat_layout(declared, reserved)
        if not layout:
            return item
        return self._reserve_names(service, item, declared, layout)

    def _reserve_names(
        self,
        service: AcquisitionService,
        item: AcquisitionConfirmation,
        declared: Sequence[TorrentFile],
        layout: tuple[FileReservation, ...],
    ) -> AcquisitionConfirmation:
        renamed: int = 0
        try:
            for index, path, _size in layout:
                current: str = next(entry.name for entry in declared if entry.index == index)
                if current.replace("\\", "/") != path:
                    service.rename_transfer_file(item.info_hash, current, path)
                    renamed += 1
        except (AniShiftError, OSError, ValueError) as problem:
            return replace(item, problem=sanitize_event_message(str(problem)))
        if renamed and self._transfers is not None:
            self._transfers.forget(item.info_hash)
        logger.info("Transfer destination names reserved", files=len(layout), renamed=renamed)
        return replace(item, file_layout=layout, problem=None)

    def _start_content(self, service: AcquisitionService, item: AcquisitionConfirmation) -> AcquisitionConfirmation:
        """Let a reserved transfer write content unless the user asked for the opposite."""
        if item.content_started or item.requested_action == "stop":
            return item
        try:
            service.start_transfer(item.info_hash)
        except (AniShiftError, OSError, ValueError) as problem:
            return replace(item, problem=sanitize_event_message(str(problem)))
        logger.info("Transfer content started after its names were reserved")
        return replace(item, content_started=True, problem=None)

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
        self._finish_pause_restore()
        pending: dict[str, str | None] = {
            item.info_hash: item.action_id for item in self._state.acquisitions if item.action_pending
        }
        self._action_attempts = {
            key: value for key, value in self._action_attempts.items() if pending.get(key) == value[0]
        }
        self._schedule_transfers(self._transfers_delay)
        self._publish_state()
        self._retry_ready()
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
                if request.state in {
                    RequestState.SUCCEEDED,
                    RequestState.FAILED,
                    RequestState.CANCELLED,
                    RequestState.PARTIAL,
                }:
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
        paused: bool = request.state is RequestState.PAUSED
        if journal.plan.tasks and not paused and request.attempts >= self._state.policy.external_retry_budget:
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
            retry=not paused,
            recipe=request.recipe,
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
        self._restore_paused()
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
        self._prepare_ready(result, sources, request.recipe)
        self._notify_ready_results(request.group_ids, request.request_id)

    def _prepare_ready(
        self,
        result: RunResult,
        sources: Sequence[InspectedSourceGroup] | None = None,
        recipe: RecipePreferences | None = None,
        artifacts: tuple[Artifact, ...] = (),
    ) -> None:
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
                request: ProcessingRequest | None = next(
                    (item for item in self._state.requests if item.request_id == result.run_id), None
                )
                if not artifacts and request is not None and self._store.run_path(request.request_id).is_file():
                    artifacts = RunJournal.load(self._store.run_path(request.request_id)).plan.artifacts
                intent: GroupIntent | None = next(
                    (
                        item
                        for item in (() if request is None else request.intents)
                        if item.group_id == completed.group_id
                    ),
                    None,
                )
                requested: frozenset[Path] = (
                    _requested_product_paths(artifacts, intent, request.settings.get("audio_output_profile"))
                    if intent is not None and request is not None
                    else frozenset()
                )
                reused: tuple[Path, ...] = tuple(
                    self._service.workspace_root / item.path
                    for item in self._state.products
                    if item.group_id == completed.group_id
                    and self._service.workspace_root / item.path in requested
                    and (item.size, item.modified_ns) == _file_identity(self._service.workspace_root / item.path)
                )
                products: tuple[Path, ...] = tuple({*(product.path for product in completed.products), *reused})
                move: ReadyMove | None = self._ready_store.prepare(group.source, products, recipe)
                if move is not None:
                    self._ready_moves[move.group_id] = move
            except (AniShiftError, OSError, ValueError) as error:
                self._ready_problems[group.group_id] = (
                    sanitize_event_message(str(error)) or "Relocation could not be prepared"
                )
        self._retry_ready()

    def _relocated_state(self, move: ReadyMove) -> WatchState:
        """Return the state where one set is renamed and remembered as finished, written in one durable save."""
        completed: set[str] = set()
        for request in self._state.requests:
            if not {move.group_id, move.destination_group_id}.intersection(request.group_ids):
                continue
            path: Path = self._store.run_path(request.request_id)
            if path.is_file() and RunJournal.relocate(path, move, self._service.workspace_root):
                completed.add(request.request_id)
        moved: WatchState = move.apply(self._state, frozenset(completed))
        self._completed_groups.clear()
        group: ReadyGroup | None = self._ready_group(move)
        if group is None:
            return moved
        kept: tuple[ReadyGroup, ...] = tuple(item for item in moved.ready_groups if item.set_id != group.set_id)
        return replace(moved, ready_groups=(*kept, group))

    def _ready_group(self, move: ReadyMove) -> ReadyGroup | None:
        """Build the durable record of one relocated set, so its target survives without reading its new folder."""
        if move.target is None or not move.destination_stem:
            return None
        produced: frozenset[str] = frozenset(move.product_sources)
        sources: tuple[str, ...] = tuple(item.destination for item in move.moved if item.source not in produced)
        products: tuple[str, ...] = tuple(item.destination for item in move.moved if item.source in produced)
        headline: str | None = main_product([Path(name).name for name in products])
        return ReadyGroup(
            set_id=move.group_id,
            group_id=move.destination_group_id,
            stem=move.destination_stem,
            source_directory=move.source_directory,
            source_stem=move.source_stem,
            target=move.target,
            sources=sources,
            products=products,
            main_result=next((name for name in products if Path(name).name == headline), None),
            recipe=move.recipe,
            pending_sources=move.deferred,
        )

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
        staged: ReadyMove = move
        try:
            owners: dict[str, AcquisitionConfirmation] = _file_owners(move, acquisitions)
            complete: frozenset[str] = frozenset(
                item.info_hash for item in owners.values() if item.state is AcquisitionState.COMPLETE
            )
            acquisition: AcquisitionService | None = self._service.acquisition
            released: frozenset[str] = (
                acquisition.release_completed(complete) if complete and acquisition is not None else frozenset()
            )
            held: tuple[str, ...] = tuple(source for source, owner in owners.items() if owner.info_hash not in released)
            if self._ready_store is not None:
                staged = self._ready_store.defer(move, held)
                self._ready_store.execute(staged)
        except (AniShiftError, OSError, ValueError) as error:
            problem = sanitize_event_message(str(error)) or "Relocation could not finish"
        finally:
            self._queue.put(lambda: self._record_ready(staged, problem))

    def _record_ready(self, move: ReadyMove, problem: str | None) -> None:
        self._active_io -= 1
        self._ready_inflight.discard(move.group_id)
        if problem is None:
            try:
                if not self._save(self._relocated_state(move)):
                    problem = "Moved files await a successful state save; retry relocation"
            except (AniShiftError, OSError, ValueError) as error:
                problem = sanitize_event_message(str(error)) or "Relocated checkpoint needs retry"
        if problem is not None:
            self._ready_problems[move.group_id] = problem
            self._publish_ready(move)
            return
        self._run_results = {
            run_id: self._relocated_result(move, result) for run_id, result in self._run_results.items()
        }
        self._notify_ready_results((move.destination_group_id,))
        if move.deferred:
            self._ready_moves[move.group_id] = move
            self._ready_problems.pop(move.group_id, None)
            self._publish_ready(move)
            return
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

    def _relocated_result(self, move: ReadyMove, result: RunResult) -> RunResult:
        if not any(group.group_id in {move.group_id, move.destination_group_id} for group in result.groups):
            return result
        updated: RunResult = move.apply_result(result, self._service.workspace_root)
        request: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == result.run_id), None
        )
        if request is None or move.destination_group_id not in self._succeeded_groups(request):
            return updated
        recovered: GroupResult = next(
            group for group in self._completed_result(request).groups if group.group_id == move.destination_group_id
        )
        return replace(
            updated,
            groups=tuple(
                replace(
                    group,
                    status=GroupStatus.SUCCEEDED,
                    error_messages=(),
                    products=group.products or recovered.products,
                )
                if group.group_id == move.destination_group_id
                else group
                for group in updated.groups
            ),
        )

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
        if self._shutting_down:
            return _refuse(RefusalReason.SHUTTING_DOWN)
        if action == "resume" and not self._state.policy.auto_enabled:
            return _refuse(RefusalReason.PAUSED)
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            replace(
                item,
                requested_action=action,
                action_id=request.command_id,
                action_pending=True,
                action_sent=False,
                problem=None,
            )
            if item.info_hash == info_hash
            else item
            for item in self._state.acquisitions
        )
        remaining: tuple[str, ...] = (
            tuple(item for item in self._state.pause_owned_transfers if item != info_hash)
            if action in {"stop", "cancel"}
            else self._state.pause_owned_transfers
        )
        outcome: dict[str, str | bool] = {"info_hash": info_hash, "action": action, "accepted": True}
        refusal: ControlResponse | None = self._commit(
            request,
            replace(self._state, acquisitions=acquisitions, pause_owned_transfers=remaining),
            outcome,
        )
        if refusal is not None:
            return refusal
        self._schedule_transfers()
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _apply_transfer_actions(
        self, service: AcquisitionService, acquisitions: tuple[AcquisitionConfirmation, ...]
    ) -> tuple[AcquisitionConfirmation, ...]:
        try:
            reported: Mapping[str, str] = _fresh_transfer_states(service, acquisitions)
        except (AniShiftError, OSError, ValueError) as problem:
            return tuple(
                self._refused_action(item, problem) if item.action_pending and _pause_stop(item) else item
                for item in acquisitions
            )
        return tuple(self._apply_transfer_action(service, item, reported) for item in acquisitions)

    def _apply_transfer_action(
        self, service: AcquisitionService, item: AcquisitionConfirmation, reported: Mapping[str, str]
    ) -> AcquisitionConfirmation:
        if not item.action_pending:
            return item
        if item.requested_action == "resume" and not item.file_layout:
            return item
        if _pause_stop(item) and reported.get(item.info_hash) in _STOPPED_TRANSFER_STATES:
            return self._settled_stop(item)
        return self._perform_action(service, item)

    def _perform_action(self, service: AcquisitionService, item: AcquisitionConfirmation) -> AcquisitionConfirmation:
        """Hand one still-current action to the client, only after the write that proves it was recorded."""
        record: _ActionRecord = self._record_sent(item)
        if record is _ActionRecord.SUPERSEDED:
            return item
        if record is _ActionRecord.UNSAVED:
            return replace(item, action_pending=False, problem=_STATE_NOT_SAVED)
        sent: AcquisitionConfirmation = replace(item, action_sent=True)
        try:
            service.control_transfer(sent.info_hash, str(sent.requested_action))
        except (AniShiftError, OSError, ValueError) as problem:
            return self._refused_action(sent, problem)
        self._action_attempts.pop(sent.info_hash, None)
        state: AcquisitionState = sent.state
        if sent.requested_action == "cancel":
            state = AcquisitionState.FAILED
        elif sent.requested_action == "resume":
            state = AcquisitionState.ACCEPTED
        return replace(
            sent,
            action_pending=False,
            problem=None,
            state=state,
        )

    def _settled_stop(self, item: AcquisitionConfirmation) -> AcquisitionConfirmation:
        """Settle a stop the client already shows done, keeping the pause ownership of one we sent ourselves."""
        self._action_attempts.pop(item.info_hash, None)
        if item.action_sent:
            return replace(item, action_pending=False, problem=None)
        return replace(item, requested_action=None, action_pending=False)

    def _refused_action(
        self, item: AcquisitionConfirmation, problem: AniShiftError | OSError | ValueError
    ) -> AcquisitionConfirmation:
        """Hold a refused action in flight for a bounded number of attempts, then report it instead of a done pause."""
        recorded: tuple[str, int] = self._action_attempts.get(item.info_hash, ("", 0))
        attempts: int = recorded[1] + 1 if recorded[0] == item.action_id else 1
        self._action_attempts[item.info_hash] = (str(item.action_id), attempts)
        reason: str | None = sanitize_event_message(str(problem))
        if attempts < _ACTION_ATTEMPTS:
            logger.warning(
                "A transfer action was refused",
                action=str(item.requested_action),
                attempt=attempts,
                attempts=_ACTION_ATTEMPTS,
                error_class=type(problem).__name__,
            )
            return replace(item, problem=reason)
        logger.error(
            "A transfer action stayed unperformed",
            action=str(item.requested_action),
            attempts=attempts,
            error_class=type(problem).__name__,
        )
        return replace(item, action_pending=False, problem=reason)

    def _record_sent(self, item: AcquisitionConfirmation) -> _ActionRecord:
        """Persist on the owner thread that this action is being handed to the client, so a crash cannot lose it."""
        if not self._serving:
            return self._mark_sent(item)
        return self._on_owner(lambda: self._mark_sent(item))

    def _mark_sent(self, item: AcquisitionConfirmation) -> _ActionRecord:
        current: AcquisitionConfirmation | None = next(
            (
                row
                for row in self._state.acquisitions
                if row.operation_id == item.operation_id and row.action_id == item.action_id
            ),
            None,
        )
        if current is None:
            logger.info("A superseded transfer action was dropped", action=str(item.requested_action))
            return _ActionRecord.SUPERSEDED
        if current.action_sent:
            return _ActionRecord.SENT
        acquisitions: tuple[AcquisitionConfirmation, ...] = tuple(
            replace(row, action_sent=True) if row is current else row for row in self._state.acquisitions
        )
        if self._save(replace(self._state, acquisitions=acquisitions)):
            return _ActionRecord.SENT
        return _ActionRecord.UNSAVED

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
                        accepted_id=identifier,
                    )
                    if "selected" in receipt.outcome:
                        tail: object = receipt.outcome["future_from"]
                        service.set_range(
                            identifier,
                            selected=_stored_numbers(receipt.outcome["selected"]),
                            future_from=None if tail is None else Decimal(str(tail)),
                        )
                elif receipt.pending == "subscription_range":
                    stored: object = receipt.outcome["future_from"]
                    service.set_range(
                        identifier,
                        selected=_stored_numbers(receipt.outcome["selected"]),
                        future_from=None if stored is None else Decimal(str(stored)),
                    )
                elif receipt.pending == "subscription_repeat":
                    service.repeat(
                        identifier,
                        _stored_numbers(receipt.outcome["episodes"]),
                        command_id=receipt.command_id,
                        requested_at=receipt.accepted_at,
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
        previous: WatchState = self._state
        self._state = candidate
        self._record_history(previous)
        return True

    def _history_material(self, group_id: str) -> str:
        return next((item.set_id for item in self._state.ready_groups if item.group_id == group_id), group_id)

    def _record_history(self, previous: WatchState, *, recovering: bool = False) -> None:
        try:
            self._append_history(previous, recovering=recovering)
        except AniShiftError, OSError, ValueError, TypeError:
            logger.warning("Operational history observation failed")

    def _append_history(self, previous: WatchState, *, recovering: bool) -> None:
        old_requests: dict[str, ProcessingRequest] = {item.request_id: item for item in previous.requests}
        for request in self._state.requests:
            old: ProcessingRequest | None = old_requests.get(request.request_id)
            if old != request:
                self._record_request_history(request, old, recovering=recovering)
        old_acquisitions: dict[str, AcquisitionConfirmation] = {
            item.operation_id: item for item in previous.acquisitions
        }
        for acquisition in self._state.acquisitions:
            before: AcquisitionConfirmation | None = old_acquisitions.get(acquisition.operation_id)
            if before is None or before.state is not acquisition.state:
                self._record_acquisition_history(acquisition, before)
        for operation in self._state.pending_deletions:
            if not recovering or not operation.outcomes:
                continue
            self._record_deletion_history(operation, recovering=True)

    def _record_request_history(
        self, request: ProcessingRequest, old: ProcessingRequest | None, *, recovering: bool
    ) -> None:
        admitted: bool = old is None or (old.generation, old.attempts) != (request.generation, request.attempts)
        finished: bool = request.state not in {RequestState.ACCEPTED, RequestState.RUNNING}
        if not admitted and (not finished or (old is not None and old.state is request.state)):
            return
        succeeded: frozenset[str] = self._succeeded_groups(request) if finished else frozenset()
        for group_id in request.group_ids:
            material_id: str = self._history_material(group_id)
            name: str = self._processing_name(request, group_id)
            if admitted:
                kind: HistoryKind = HistoryKind.REGENERATION if request.rebuild is not None else HistoryKind.ORDER
                self._history.append(
                    HistoryEvent.create(
                        material_id,
                        request.request_id,
                        request.accepted_at,
                        kind,
                        name,
                        generation=request.generation,
                        attempt=request.attempts,
                    ),
                    self._clock(),
                )
            if not finished:
                continue
            kind = (
                HistoryKind.SUCCESS
                if group_id in succeeded
                else (
                    HistoryKind.INTERRUPTED
                    if request.state in {RequestState.CANCELLED, RequestState.PAUSED}
                    else HistoryKind.ERROR
                )
            )
            self._history.append(
                HistoryEvent.create(
                    material_id,
                    request.request_id,
                    request.accepted_at if recovering else self._now(),
                    kind,
                    name,
                    generation=request.generation,
                    attempt=request.attempts,
                    outcome=request.state.value,
                    recovered_from_admission=recovering,
                ),
                self._clock(),
            )

    def _record_acquisition_history(
        self, item: AcquisitionConfirmation, previous: AcquisitionConfirmation | None
    ) -> None:
        name: str = item.release_title or next((Path(path).name for path in item.required_files), item.info_hash)
        if previous is None:
            self._history.append(
                HistoryEvent.create(
                    item.operation_id,
                    item.operation_id,
                    item.updated_at,
                    HistoryKind.ORDER,
                    name,
                ),
                self._clock(),
            )
        if item.state is AcquisitionState.COMPLETE:
            self._history.append(
                HistoryEvent.create(
                    item.operation_id,
                    item.operation_id,
                    item.updated_at,
                    HistoryKind.DOWNLOAD,
                    name,
                ),
                self._clock(),
            )

    def _record_deletion_history(self, operation: PendingDeletion, *, recovering: bool = False) -> None:
        group: ReadyGroup | None = next(
            (item for item in self._state.ready_groups if item.set_id == operation.set_id), None
        )
        complete: bool = len(operation.recycled) == len(operation.files)
        attempt: int = sum(
            receipt.outcome.get("operation_id") == operation.operation_id for receipt in self._state.command_receipts
        )
        self._history.append(
            HistoryEvent.create(
                operation.set_id,
                operation.operation_id,
                operation.requested_at if recovering else self._now(),
                HistoryKind.DELETE,
                group.stem if group is not None else Path(operation.files[0][0]).name,
                attempt=max(attempt, 1),
                outcome="complete" if complete else "incomplete",
                recovered_from_admission=recovering,
            ),
            self._clock(),
        )

    def _history_action(self, request: ControlRequest, inventory: tuple[SourceGroup, ...]) -> ControlResponse:
        if request.kind == "subscription_retry_prepare":
            return self._subscription_retry_proposal(request, inventory)
        identifier: str | None = _text(request.payload, "material_id")
        if identifier is None:
            return _invalid("Select one material")
        return self._retry_proposal(identifier, inventory)

    def _retry_proposal(self, identifier: str, inventory: tuple[SourceGroup, ...]) -> ControlResponse:
        if not self._working():
            return _refuse(RefusalReason.PAUSED)
        group_id: str = next(
            (item.group_id for item in self._state.ready_groups if item.set_id == identifier), identifier
        )
        current: ProcessingRequest | None = next(
            (item for item in reversed(self._state.requests) if group_id in item.group_ids), None
        )
        group: SourceGroup | None = next((item for item in inventory if item.group_id == group_id), None)
        if current is not None and current.request_id in self._service.active_run_ids():
            return _refuse(RefusalReason.GROUP_PROCESSING)
        conflict: ControlResponse | None = self._conflict(
            (identifier, group_id),
            "",
            excluding=None if current is None else current.request_id,
        )
        if conflict is not None:
            return conflict
        if current is not None and current.state in {RequestState.FAILED, RequestState.PARTIAL, RequestState.PAUSED}:
            try:
                RunJournal.load(self._store.run_path(current.request_id))
            except AniShiftError, OSError, ValueError:
                pass
            else:
                return ControlResponse.succeeded(
                    encode_view(
                        RetryProposal(
                            identifier,
                            "resume",
                            current.group_ids,
                            current.intents,
                            current.request_id,
                        )
                    )
                )
        if group is not None and self._local_primary(group):
            intents: tuple[GroupIntent, ...] = (
                ()
                if current is None
                else tuple(replace(item, mode=RunMode.MANUAL) for item in current.intents if item.group_id == group_id)
            )
            return ControlResponse.succeeded(encode_view(RetryProposal(identifier, "manual", (group_id,), intents)))
        return self._missing_source_retry(identifier, group_id)

    def _missing_source_retry(self, identifier: str, group_id: str) -> ControlResponse:
        acquisition: AcquisitionConfirmation | None = next(
            (
                item
                for item in reversed(self._state.acquisitions)
                if item.operation_id == identifier or group_id in self._acquisition_groups(item)
            ),
            None,
        )
        if acquisition is None:
            return self._retry_refusal("retry_source_missing")
        if acquisition.nyaa_release_id is None:
            return self._retry_refusal("retry_reference_missing")
        return ControlResponse.succeeded(
            encode_view(
                RetryProposal(
                    identifier,
                    "reacquire",
                    operation_id=acquisition.operation_id,
                )
            )
        )

    def _local_primary(self, group: SourceGroup) -> bool:
        target: WorkflowTarget | None = self._recorded_targets().get(group.group_id, group.route.target)
        route: WorkflowRoute = replace(group.route, target=target)
        return any(
            artifact.path is not None
            and artifact.lifetime is ArtifactLifetime.SOURCE
            and (candidate := classify_artifact(artifact.path, route)) is not None
            and candidate.is_primary
            and artifact.path.is_file()
            for artifact in group.artifacts
        )

    @staticmethod
    def _retry_refusal(reason: str) -> ControlResponse:
        return ControlResponse.refused(ControlErrorCode.REFUSED, reason, reason)

    def _subscription_retry_proposal(
        self, request: ControlRequest, inventory: tuple[SourceGroup, ...]
    ) -> ControlResponse:
        if not self._working():
            return _refuse(RefusalReason.PAUSED)
        identifier: str | None = _text(request.payload, "subscription_id")
        episodes: tuple[Decimal, ...] | None = _episode_numbers(request.payload, "episodes")
        if identifier is None or not episodes:
            return _invalid("Select explicit episode numbers")
        selected: tuple[AcquisitionConfirmation, ...] = tuple(
            item
            for item in self._state.acquisitions
            if item.subscription_id == identifier and item.episode is not None and Decimal(item.episode) in episodes
        )
        groups: set[str] = {group_id for item in selected for group_id in self._acquisition_groups(item)}
        local: set[str] = {
            group.group_id for group in inventory if group.group_id in groups and self._local_primary(group)
        }
        if local:
            if len(episodes) != 1 or len(local) != 1:
                return self._retry_refusal("retry_choose_one")
            return self._retry_proposal(next(iter(local)), inventory)
        return ControlResponse.succeeded(
            encode_view(
                RetryProposal(
                    identifier,
                    "subscription",
                    subscription_id=identifier,
                    episodes=episodes,
                )
            )
        )

    def _reacquire_command(self, request: ControlRequest) -> ControlResponse:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            return self._retry_refusal("retry_reference_missing")
        inventory: tuple[SourceGroup, ...] = self._service.library_inventory()
        accepted: tuple[AcquisitionConfirmation | None, ControlResponse] = self._on_owner(
            lambda: self._accept_reacquire(request, inventory)
        )
        item, response = accepted
        if item is None:
            return response
        try:
            with acquisition.requests("user_download"):
                acquisition.reacquire(
                    cast("int", item.nyaa_release_id), cast("str", item.release_title), item.info_hash, item.episode
                )
                self._confirm_download(acquisition, frozenset({item.info_hash.casefold()}))
        finally:
            self._on_owner(lambda: self._reconcile_acquisitions(frozenset()))
        return response

    def _accept_reacquire(
        self, request: ControlRequest, inventory: tuple[SourceGroup, ...]
    ) -> tuple[AcquisitionConfirmation | None, ControlResponse]:
        receipt: CommandReceipt | None = self._receipt(request)
        if receipt is not None:
            return None, ControlResponse.succeeded(dict(receipt.outcome))
        identifier: str | None = _text(request.payload, "operation_id")
        previous: AcquisitionConfirmation | None = next(
            (item for item in self._state.acquisitions if item.operation_id == identifier), None
        )
        if previous is None:
            return None, self._retry_refusal("retry_reference_missing")
        refusal: ControlResponse | None = self._reacquire_refusal(previous, inventory)
        if refusal is not None:
            return None, refusal
        item: AcquisitionConfirmation = replace(
            previous,
            operation_id=f"repeat-{request.command_id}",
            directory="",
            required_files=(),
            complete_files=(),
            file_layout=(),
            content_started=False,
            state=AcquisitionState.PENDING_SEND,
            origin=RequestOrigin.USER,
            requested_action=None,
            action_id=None,
            action_pending=False,
            action_sent=False,
            problem=None,
            updated_at=self._now(),
            repeat_id=request.command_id,
            previous_operation_id=previous.operation_id,
        )
        outcome: CommandOutcome = {"operation_id": item.operation_id}
        refusal = self._commit(
            request,
            replace(
                self._state,
                acquisitions=(*self._state.acquisitions, item),
            ),
            outcome,
        )
        return (None, refusal) if refusal is not None else (item, ControlResponse.succeeded(dict(outcome)))

    def _reacquire_refusal(
        self, previous: AcquisitionConfirmation, inventory: tuple[SourceGroup, ...]
    ) -> ControlResponse | None:
        if not self._working():
            return _refuse(RefusalReason.PAUSED)
        if previous.nyaa_release_id is None:
            return self._retry_refusal("retry_reference_missing")
        groups: set[str] = set(self._acquisition_groups(previous))
        if self._subscription_source_present(previous) or any(
            group.group_id in groups and self._local_primary(group) for group in inventory
        ):
            return self._retry_refusal("retry_source_available")
        conflict: ControlResponse | None = self._conflict(tuple(groups), "")
        if conflict is not None:
            return conflict
        if any(
            item.info_hash == previous.info_hash
            and item.state not in {AcquisitionState.COMPLETE, AcquisitionState.FAILED}
            for item in self._state.acquisitions
        ):
            return self._retry_refusal("retry_acquisition_pending")
        return None

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
        if event.state is TaskState.SUCCEEDED:
            return
        request: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == event.run_id),
            None,
        )
        if request is None or event.group_id is None:
            return
        with self._progress_lock:
            view: RunProgressSnapshot | None = self._run_views.get(event.run_id)
        key: tuple[str, str, str] = (event.group_id, f"{request.request_id}:{request.generation}", str(event.state))
        if key in self._state.notified or not self._save(replace(self._state, notified=self._state.notified | {key})):
            return
        with self._progress_lock:
            label: str = view.labels.get(event.group_id, event.group_id) if view is not None else event.group_id
        self._publish_notification("Materiał wymaga uwagi", sanitize_event_message(label) or "Materiał", None)

    def _notify_ready_results(self, group_ids: Sequence[str], request_id: str | None = None) -> None:
        recorded: set[str] = {item.group_id for item in self._state.ready_groups}
        paths: tuple[Path, ...] = tuple(
            self._service.workspace_root / item.path
            for item in self._state.products
            if item.group_id in group_ids
            and item.group_id not in recorded
            and Path(item.path).parts[0].casefold() == READY_DIRECTORY
        )
        if paths:
            self._active_io += 1
            self._pool.submit(self._refresh_notification_inventory, tuple(group_ids), request_id, paths)
            return
        self._offer_ready_results(group_ids, request_id)

    def _refresh_notification_inventory(
        self, group_ids: tuple[str, ...], request_id: str | None, paths: tuple[Path, ...]
    ) -> None:
        groups: tuple[SourceGroup, ...] | None = None
        try:
            groups = self._service.library_inventory(paths)
        except AniShiftError, OSError:
            logger.warning("The notification result inventory is unavailable")
        finally:
            self._queue.put(lambda: self._record_notification_inventory(groups, group_ids, request_id))

    def _record_notification_inventory(
        self, groups: tuple[SourceGroup, ...] | None, group_ids: tuple[str, ...], request_id: str | None
    ) -> None:
        self._active_io -= 1
        if groups is None:
            return
        self._ready_library = project_library(self._state, self._service.workspace_root, groups)
        self._offer_ready_results(group_ids, request_id)

    def _offer_ready_results(self, group_ids: Sequence[str], request_id: str | None) -> None:
        for record in self._notification_sets(group_ids):
            if record.main_result is None or not record.available:
                continue
            product: ProductConfirmation | None = next(
                (
                    item
                    for item in self._state.products
                    if item.group_id == record.group_id and item.path == record.main_result
                ),
                None,
            )
            request: ProcessingRequest | None = self._notification_request(record, request_id)
            if product is not None and request is not None:
                self._notify_ready_result(record, product, request)

    def _notification_sets(self, group_ids: Sequence[str]) -> tuple[LibrarySet, ...]:
        state: WatchState = replace(
            self._state, ready_groups=tuple(item for item in self._state.ready_groups if item.group_id in group_ids)
        )
        recorded: set[str] = {item.group_id for item in state.ready_groups}
        legacy: tuple[LibrarySet, ...] = tuple(
            item for item in self._ready_library if item.group_id in group_ids and item.group_id not in recorded
        )
        return (*project_library(state, self._service.workspace_root, ()), *legacy)

    def _notification_request(self, record: LibrarySet, request_id: str | None) -> ProcessingRequest | None:
        products: set[str] = {item.path for item in record.files if item.role == "product"}
        attempts: set[tuple[str, int]] = {
            (item.request_id, item.generation)
            for item in self._state.products
            if item.group_id == record.group_id and item.path in products
        }
        return max(
            (
                item
                for item in self._state.requests
                if (request_id is None or item.request_id == request_id)
                and (item.request_id, item.generation) in attempts
                and {record.group_id, record.set_id}.intersection(item.group_ids)
            ),
            key=lambda item: (item.accepted_at, item.generation),
            default=None,
        )

    def _notify_ready_result(
        self, record: LibrarySet, product: ProductConfirmation, request: ProcessingRequest
    ) -> None:
        if request.state in _ACTIVE_STATES:
            return
        key: tuple[str, str, str] = (
            record.group_id,
            f"{request.request_id}:{request.generation}",
            str(TaskState.SUCCEEDED),
        )
        if key in self._state.notified or not self._notification_succeeded(request, record):
            return
        identity: LibraryFileIdentity | None = next(
            (item.identity for item in record.files if item.path == record.main_result), None
        )
        if (
            identity is None
            or (identity.size, identity.modified_ns) != (product.size, product.modified_ns)
            or file_identity(self._service.workspace_root, product.path) != identity
        ):
            return
        if not self._save(replace(self._state, notified=self._state.notified | {key})):
            return
        self._publish_notification(
            "Gotowy materiał",
            sanitize_event_message(record.name) or "Materiał",
            _NotificationTarget(record.set_id, product, identity, (request.request_id, request.generation)),
        )

    def _notification_succeeded(self, request: ProcessingRequest, record: LibrarySet) -> bool:
        identifiers: set[str] = {record.set_id, record.group_id}
        result: RunResult | None = self._run_results.get(request.request_id)
        succeeded: bool = (
            any(group.group_id in identifiers and group.status is GroupStatus.SUCCEEDED for group in result.groups)
            if result is not None
            else bool(identifiers.intersection(self._succeeded_groups(request)))
        )
        if not succeeded:
            return False
        with self._progress_lock:
            view: RunProgressSnapshot | None = self._run_views.get(request.request_id)
        if view is not None:
            return any(task.group_id in identifiers for task in view.preview.tasks)
        try:
            journal: RunJournal = RunJournal.load(self._store.run_path(request.request_id))
        except AniShiftError, OSError, ValueError:
            return False
        return any(journal.products(identifier) for identifier in identifiers)

    def _publish_notification(self, title: str, message: str, target: _NotificationTarget | None) -> None:
        identifier: str = token_hex(_ID_BYTES)
        self._notification_targets[identifier] = target
        if len(self._notification_targets) > _NOTIFICATION_LIMIT:
            self._notification_targets.pop(next(iter(self._notification_targets)))
        self._publish(
            {
                "event": "notification",
                "payload": {
                    "title": title,
                    "message": message,
                    "notification_id": identifier,
                },
            },
            terminal=True,
        )

    def _open_notification(self, identifier: str) -> None:
        known: bool = identifier in self._notification_targets
        target: _NotificationTarget | None = self._notification_targets.pop(identifier, None)
        if known and target is None:
            self._tray_action("open")
            return
        if target is not None and self._notification_current(target) and self._open_result is not None:
            try:
                self._open_result(self._service.workspace_root / target.product.path)
            except OSError, ValueError:
                logger.warning("The notification result could not be opened")
            else:
                self._notification_problem = None
                self._publish_state()
                return
        self._notification_problem = _UNIDENTIFIED_NOTIFICATION if not identifier else _UNAVAILABLE_NOTIFICATION
        self._publish_state()
        self._show_panel(self._notification_problem)

    def _notification_current(self, target: _NotificationTarget) -> bool:
        record: LibrarySet | None = next(
            (item for item in self._notification_sets((target.product.group_id,)) if item.set_id == target.set_id), None
        )
        if record is None or not record.available or record.main_result != target.product.path:
            return False
        if target.product not in self._state.products or record.group_id in self._deleting_groups():
            return False
        request: ProcessingRequest | None = self._notification_request(record, None)
        if request is None or (request.request_id, request.generation) != target.attempt:
            return False
        if any(
            item.state in _ACTIVE_STATES and {record.set_id, record.group_id}.intersection(item.group_ids)
            for item in self._state.requests
        ):
            return False
        return file_identity(self._service.workspace_root, target.product.path) == target.identity

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
        if self._deleting_groups().intersection(group_ids):
            return self._library_refusal("library_deleting")
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

    def _deleting_groups(self) -> set[str]:
        return {
            identifier
            for item in self._state.ready_groups
            if item.set_id in self._deleting.values()
            for identifier in (item.set_id, item.group_id)
        }

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


def _resumable(item: AcquisitionConfirmation, paused: frozenset[str], enabled: frozenset[str] | None) -> bool:
    """Answer whether a globally paused transfer still has an active order to take up again."""
    return (
        item.info_hash in paused
        and item.state is AcquisitionState.ACCEPTED
        and _pause_stop(item)
        and item.action_sent
        and not item.action_pending
        and item.problem is None
        and (item.subscription_id is None or enabled is None or item.subscription_id in enabled)
    )


def _unfinished_pause_stops(state: WatchState) -> tuple[str, ...]:
    """Keep ownership until a pending or failed pause stop has been reconciled."""
    unfinished: frozenset[str] = frozenset(
        item.info_hash
        for item in state.acquisitions
        if _pause_stop(item) and (item.action_pending or item.problem is not None)
    )
    return tuple(item for item in state.pause_owned_transfers if item in unfinished)


def _pause_stop(item: AcquisitionConfirmation) -> bool:
    """Answer whether this recorded stop carries the action id the global pause gives its own stops."""
    return item.requested_action == "stop" and (item.action_id or "").startswith(f"{_PAUSE_ACTION}-")


def _unstopped_pause(item: AcquisitionConfirmation) -> bool:
    """Keep a failed stop visible even when an explicit transfer command replaced the global pause action."""
    return item.requested_action in {"stop", "cancel"} and not item.action_pending and item.problem is not None


def _fresh_transfer_states(
    service: AcquisitionService, acquisitions: tuple[AcquisitionConfirmation, ...]
) -> Mapping[str, str]:
    """Read the client now, only for a pause that has stops to apply, so no decision rests on an old snapshot."""
    if not any(item.action_pending and _pause_stop(item) for item in acquisitions):
        return {}
    return {item.info_hash.casefold(): item.state for item in service.transfers()}


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


def _requested_product_paths(
    artifacts: tuple[Artifact, ...], intent: GroupIntent, audio_profile: object
) -> frozenset[Path]:
    audio_suffix: str | None = (
        product_suffix(ArtifactKind.NARRATION_AUDIO, audio_profile=audio_profile)
        if isinstance(audio_profile, str) and audio_profile in AUDIO_PRODUCT_PROFILES
        else None
    )
    return frozenset(
        artifact.planned_destination
        for artifact in artifacts
        if artifact.group_id == intent.group_id
        and artifact.lifetime is ArtifactLifetime.DURABLE
        and artifact.kind.value.removeprefix("final_") in intent.products.requested_products
        and artifact.planned_destination is not None
        and (
            artifact.kind is not ArtifactKind.NARRATION_AUDIO
            or artifact.planned_destination.suffix.casefold() == audio_suffix
        )
        and (
            artifact.subtitle_format is None
            or intent.subtitle_output_format is SubtitleOutputFormat.PRESERVE
            or artifact.subtitle_format == intent.subtitle_output_format.value
        )
    )


def _settings_snapshot(settings: RunSettingsSnapshot) -> SettingsSnapshot:
    return cast("SettingsSnapshot", {field.name: getattr(settings, field.name) for field in fields(settings)})


def _file_owners(
    move: ReadyMove, acquisitions: Sequence[AcquisitionConfirmation]
) -> dict[str, AcquisitionConfirmation]:
    """Return which transfer owns each relocated source, so only its own files wait for its release."""
    owners: dict[str, AcquisitionConfirmation] = {}
    for item in move.files:
        for acquisition in acquisitions:
            directory: Path = Path(acquisition.directory)
            if any((directory / name).as_posix() == item.source for name in _assigned_files(acquisition)):
                owners[item.source] = acquisition
                break
    return owners


def _assigned_files(acquisition: AcquisitionConfirmation) -> frozenset[str]:
    """Return every workspace name one transfer owns, whether reserved up front or observed later."""
    return frozenset(acquisition.required_files) | frozenset(path for _index, path, _size in acquisition.file_layout)


def _reserved_stems(acquisition: AcquisitionConfirmation) -> frozenset[str]:
    """Return the cores one transfer already reserved, because a name it has not chosen yet holds nothing."""
    return frozenset(reserved_stem(path) for _index, path, _size in acquisition.file_layout)


def _present_stems(root: Path) -> frozenset[str]:
    """Return the cores of every entry but a subfolder in the flat destination, so no transfer writes over one."""
    return frozenset(reserved_stem(entry.name) for entry in root.iterdir() if not entry.is_dir())


def _occupied(root: Path, layout: Sequence[FileReservation]) -> bool:
    """Return whether any name a layout reserved already holds something, counting a name it cannot read as held."""
    return any(_taken_name(root / path) for _index, path, _size in layout)


def _taken_name(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _file_identity(path: Path) -> tuple[int, int]:
    """Return the size and modification time proving which bytes were published, or a pair no file can match."""
    try:
        status: os.stat_result = path.stat()
    except OSError:
        return -1, -1
    return status.st_size, status.st_mtime_ns


def _group_with_target(group: InspectedSourceGroup, target: WorkflowTarget | None) -> InspectedSourceGroup:
    """Return one group whose route names its recorded target, leaving a place that names its own untouched."""
    if target is None or group.source.route.target is not None:
        return group
    route: WorkflowRoute = replace(group.source.route, target=target)
    return replace(group, source=replace(group.source, route=route))


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


def _subscription_view(subscription: Subscription, now: datetime | None = None) -> dict[str, object]:
    current: datetime = now if now is not None else datetime.now(UTC)
    dates: list[tuple[datetime, Decimal]] = []
    for episode in subscription.episodes:
        if not episode.selected or episode.airing_at is None or episode.state.value not in {"pending", "due"}:
            continue
        try:
            moment: datetime = datetime.fromisoformat(episode.airing_at)
        except ValueError:
            continue
        if moment.tzinfo is not None:
            dates.append((moment, episode.number))
    future: list[tuple[datetime, Decimal]] = [item for item in dates if item[0] > current]
    nearest: tuple[datetime, Decimal] | None = min(future) if future else max(dates, default=None)
    return {
        "subscription_id": subscription.subscription_id,
        "series": subscription.series,
        "group": subscription.group,
        "next_episode": str(subscription.next_episode),
        "enabled": subscription.enabled,
        "end_state": subscription.end_state.value,
        "anilist_id": subscription.anilist_id,
        "calendar_problem": subscription.calendar_problem,
        "episodes": [encode_view(episode) for episode in subscription.episodes],
        "airing_at": None if nearest is None else nearest[0].isoformat(),
        "airing_episode": None if nearest is None else str(nearest[1]),
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


def _episode_numbers(payload: Mapping[str, object], key: str) -> tuple[Decimal, ...] | None:
    """Return the episode numbers named under *key*, or nothing when any of them is not one."""
    named: tuple[str, ...] | None = _identifiers(payload, key)
    if named is None:
        return None
    try:
        numbers: tuple[Decimal, ...] = tuple(Decimal(item) for item in named)
    except InvalidOperation:
        return None
    return numbers if all(number.is_finite() and number > 0 for number in numbers) else None


def _stored_numbers(raw: object) -> tuple[Decimal, ...]:
    """Return the episode numbers a receipt recorded, which validation already accepted."""
    return tuple(Decimal(str(item)) for item in json.loads(str(raw)))


def _episode_number(payload: Mapping[str, object], key: str) -> Decimal | None:
    """Return the single episode number named under *key*, or nothing when it is absent or invalid."""
    text: str | None = _text(payload, key)
    if text is None:
        return None
    numbers: tuple[Decimal, ...] | None = _episode_numbers({key: [text]}, key)
    return None if numbers is None else numbers[0]


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
