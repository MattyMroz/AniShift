"""Automation policy and ledger contracts shared by the watcher, the panel and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application.intents import (
    GroupIntent,
    NarrationTimeline,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    TranslationAction,
)
from anishift.application.workflows import WorkflowTarget

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "WATCH_STATE_SCHEMA_VERSION",
    "AcquisitionConfirmation",
    "AcquisitionState",
    "AudiobookRecipe",
    "AutomationPolicy",
    "CommandReceipt",
    "FileReservation",
    "ManualHandledMarker",
    "NarrationTimeline",
    "NotificationKey",
    "PendingDeletion",
    "PreflightFinding",
    "PreflightFindingKind",
    "ProcessingRequest",
    "ProductConfirmation",
    "ProviderLock",
    "ReadyGroup",
    "RecipePreferences",
    "RequestState",
    "Reservation",
    "SourceFingerprint",
    "SourceSelection",
    "TextResultFormat",
    "TranslateRecipe",
    "WatchState",
    "auto_admissible",
    "mark_manual_handled",
    "preflight",
    "record_command",
    "record_request",
    "release",
    "require_relative_paths",
    "reserve",
]

# ── Constants ─────────────────────────────────────────────────────────────────

WATCH_STATE_SCHEMA_VERSION: Final[int] = 2
"""Current schema of the persisted automation state."""

type SourceFingerprint = tuple[tuple[str, int, int], ...]
"""Identity of one group input, exactly what ``watch.source_fingerprint`` returns."""

type NotificationKey = tuple[str, str, str]
"""Group or episode, generation and kind, deduplicating one announcement."""

type SettingValue = str | int | float | bool | None | tuple[SettingValue, ...]
"""Scalar or ordered non-secret configuration values retained by a request."""

type SettingsSnapshot = Mapping[str, SettingValue]
"""Immutable settings a request was accepted under, holding no secret."""

type CommandOutcome = Mapping[str, str | int | bool | None]
"""Result an accepted command produced, replayed instead of running that command twice."""

type FileReservation = tuple[int, str, int]
"""Client file index, the flat path reserved for it and the size its release declares."""

_NO_EXCEPTIONS: Final[Mapping[str, bool]] = MappingProxyType({})
"""Directory table of a policy carrying nothing but the global switch."""

_SECRET_MARKERS: Final[frozenset[str]] = frozenset({"token", "key", "password", "secret"})
"""Name segments marking a settings key whose value must never reach the ledger."""

_DEFAULT_RELEASE_DELAY_S: Final[int] = 3 * 3600
"""Wait after airing before the first release search of an episode without history."""

_DEFAULT_RECHECK_INTERVAL_S: Final[int] = 3600
"""Wait before a due episode without a release is looked for again."""

_DEFAULT_SEARCH_WINDOW_S: Final[int] = 72 * 3600
"""How long one episode is searched for before it becomes a gap needing a decision."""

_DEFAULT_TRANSFER_STALL_S: Final[int] = 30 * 60
"""Active downloading without progress after which a transfer needs attention."""

_DEFAULT_RETRY_BUDGET: Final[int] = 3
"""Attempts one retryable external operation gets in total, the first one included."""

_DEFAULT_RETRY_DELAYS_S: Final[tuple[int, ...]] = (60, 300)
"""Waits between attempts when the server names no delay of its own."""


class TextResultFormat(StrEnum):
    """Result the translate target writes for a plain text input."""

    TEXT = "text"
    SUBTITLES = "subtitles"


class PreflightFindingKind(StrEnum):
    """Pre-existing facts a controlled transition to the task folders has to settle first."""

    AUTOMATION_PAUSED = "automation_paused"
    DIRECTORY_EXCEPTION = "directory_exception"
    UNFINISHED_REQUEST = "unfinished_request"
    RESERVED_NAME_REFUSED = "reserved_name_refused"
    RESERVED_NAME_OCCUPIED = "reserved_name_occupied"


class RefusalReason(StrEnum):
    """Stable identifier of why the resident refused one command, carried beside its message."""

    GROUP_RESERVED = "group_reserved"
    GROUP_PROCESSING = "group_processing"
    GROUP_RELOCATING = "group_relocating"
    SESSION_CLOSED = "session_closed"
    CLIENT_BOUND = "client_bound"
    NOT_RESERVED = "not_reserved"
    FOREIGN_PREVIEW = "foreign_preview"
    NOT_RESUMABLE = "not_resumable"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"


class SourceSelection(StrEnum):
    """How a request picks the sources it works on."""

    AUTO = "auto"
    MANUAL = "manual"


class RequestState(StrEnum):
    """Lifecycle of one accepted processing request."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AcquisitionState(StrEnum):
    """Lifecycle of one release handed to the torrent client."""

    PENDING_SEND = "pending_send"
    UNCERTAIN = "uncertain"
    ACCEPTED = "accepted"
    COMPLETE = "complete"
    FAILED = "failed"


_UNFINISHED_STATES: Final[frozenset[RequestState]] = frozenset(
    {RequestState.ACCEPTED, RequestState.RUNNING, RequestState.PAUSED}
)
"""States of a request that still owns its groups and has to be settled, never abandoned."""


@dataclass(frozen=True, slots=True)
class AutomationPolicy:
    """Global automatic processing switch, its directory exceptions and the schedule settings."""

    auto_enabled: bool = False
    directory_exceptions: Mapping[str, bool] = _NO_EXCEPTIONS
    release_delay_default_s: int = _DEFAULT_RELEASE_DELAY_S
    recheck_interval_s: int = _DEFAULT_RECHECK_INTERVAL_S
    search_window_s: int = _DEFAULT_SEARCH_WINDOW_S
    transfer_stall_s: int = _DEFAULT_TRANSFER_STALL_S
    external_retry_budget: int = _DEFAULT_RETRY_BUDGET
    retry_delays_s: tuple[int, ...] = _DEFAULT_RETRY_DELAYS_S

    def effective_auto(self, directory: str) -> bool:
        """Whether automatic processing may start in *directory*."""
        if not self.auto_enabled:
            return False
        for candidate in _directory_chain(directory):
            exception: bool | None = self.directory_exceptions.get(candidate)
            if exception is not None:
                return exception
        return self.auto_enabled


@dataclass(frozen=True, slots=True)
class TranslateRecipe:
    """What the translate target adds to the shared content settings, and nothing more."""

    text_result: TextResultFormat = TextResultFormat.TEXT
    translation_action: TranslationAction = TranslationAction.AUTO


@dataclass(frozen=True, slots=True)
class AudiobookRecipe:
    """What the audiobook target adds to the shared content settings, and nothing more."""

    translation_action: TranslationAction = TranslationAction.AUTO
    timeline: NarrationTimeline = NarrationTimeline.CONTINUOUS


@dataclass(frozen=True, slots=True)
class RecipePreferences:
    """Target deltas kept beside the video preset, never a copy of the shared settings."""

    translate: TranslateRecipe = field(default_factory=TranslateRecipe)
    audiobook: AudiobookRecipe = field(default_factory=AudiobookRecipe)


@dataclass(frozen=True, slots=True)
class Reservation:
    """One group held by one client while its manual selection is being edited."""

    group_id: str
    fingerprint: SourceFingerprint
    client_id: str
    reserved_at: str


@dataclass(frozen=True, slots=True)
class ManualHandledMarker:
    """Products a user deliberately settled for one version of the sources of one group."""

    group_id: str
    fingerprint: SourceFingerprint
    products: frozenset[ProductKind]
    request_id: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ProcessingRequest:
    """One accepted intent to process groups, with the settings it was accepted under."""

    request_id: str
    generation: int
    group_ids: tuple[str, ...]
    fingerprints: Mapping[str, SourceFingerprint]
    origin: RequestOrigin
    source_selection: SourceSelection
    rebuild: RebuildRequest | None
    settings: SettingsSnapshot
    state: RequestState
    attempts: int
    accepted_at: str
    intents: tuple[GroupIntent, ...] = ()
    automatic: bool = False
    problem: str | None = None
    recipe: RecipePreferences = field(default_factory=RecipePreferences)

    def __post_init__(self) -> None:
        for key in self.settings:
            if _SECRET_MARKERS.intersection(key.casefold().split("_")):
                msg = "A request settings snapshot cannot carry a secret"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AcquisitionConfirmation:
    """What is known about one release handed to the torrent client."""

    operation_id: str
    info_hash: str
    directory: str
    required_files: tuple[str, ...]
    state: AcquisitionState
    origin: RequestOrigin
    subscription_id: str | None
    episode: str | None
    updated_at: str
    requested_action: str | None = None
    action_id: str | None = None
    action_pending: bool = False
    action_sent: bool = False
    problem: str | None = None
    complete_files: tuple[str, ...] = ()
    file_layout: tuple[FileReservation, ...] = ()
    content_started: bool = False
    repeat_id: str | None = None

    def __post_init__(self) -> None:
        if self.requested_action not in {None, "stop", "resume", "cancel"}:
            msg = "Unknown transfer action"
            raise ValueError(msg)
        if not frozenset(self.complete_files) <= frozenset(self.required_files):
            msg = "A complete file must be one of the files required from the release"
            raise ValueError(msg)
        indexes: tuple[int, ...] = tuple(index for index, _path, _size in self.file_layout)
        if any(index < 0 for index in indexes) or len(set(indexes)) != len(indexes):
            msg = "A reserved file must carry one unique client file index"
            raise ValueError(msg)
        if any(size < 0 for _index, _path, size in self.file_layout):
            msg = "A reserved file must carry the size its release declares"
            raise ValueError(msg)
        require_relative_paths((path for _index, path, _size in self.file_layout), "A reserved file of a release")
        object.__setattr__(self, "info_hash", self.info_hash.casefold())


@dataclass(frozen=True, slots=True)
class ProductConfirmation:
    """One product proven correct, at a path relative to the library root."""

    group_id: str
    artifact_kind: str
    path: str
    generation: int
    request_id: str
    origin: RequestOrigin
    size: int = -1
    modified_ns: int = -1


@dataclass(frozen=True, slots=True)
class ReadyGroup:
    """Where one completed set came from, so its target survives the move into ``ready``."""

    set_id: str
    group_id: str
    stem: str
    source_directory: str
    source_stem: str
    target: WorkflowTarget
    sources: tuple[str, ...]
    products: tuple[str, ...]
    main_result: str | None = None
    pending_sources: tuple[str, ...] = ()
    recipe: RecipePreferences = field(default_factory=RecipePreferences)

    def __post_init__(self) -> None:
        if not self.set_id.strip() or not self.group_id.strip() or not self.stem.strip():
            msg = "A completed set requires its logical identity and its current name"
            raise ValueError(msg)
        optional: tuple[str, ...] = tuple(value for value in (self.main_result,) if value is not None)
        require_relative_paths(
            (*self.sources, *self.products, *self.pending_sources, *optional), "A file of a completed set"
        )
        if self.main_result is not None and self.main_result not in {*self.products, *self.sources}:
            msg = "The main result of a completed set must be one of its own files"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PendingDeletion:
    """One confirmed whole-set deletion, the identity of each file it covers and what already went out."""

    operation_id: str
    set_id: str
    requested_at: str
    files: SourceFingerprint
    recycled: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.files:
            msg = "A pending deletion must name at least one file"
            raise ValueError(msg)
        names: tuple[str, ...] = tuple(name for name, _size, _mtime_ns in self.files)
        require_relative_paths((*names, *self.recycled), "A file of a pending deletion")
        if not frozenset(self.recycled) <= frozenset(names):
            msg = "A recycled file must belong to its confirmed deletion"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PreflightFinding:
    """One read-only fact of the configuration found before any new role is activated."""

    kind: PreflightFindingKind
    subject: str = ""


@dataclass(frozen=True, slots=True)
class ProviderLock:
    """Moment before which no path may call *provider* again."""

    provider: str
    until: str
    reason: str


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    """Outcome of one accepted command, replayed when its identifier arrives again."""

    command_id: str
    accepted_at: str
    outcome: CommandOutcome
    pending: str | None = None

    def __post_init__(self) -> None:
        if self.pending not in {
            None,
            "cancel",
            "subscription_enable",
            "subscription_disable",
            "subscription_remove",
            "subscription_add",
            "subscription_range",
            "subscription_repeat",
        }:
            msg = "A pending command must identify a supported local operation"
            raise ValueError(msg)
        key: str = "run_id" if self.pending == "cancel" else "subscription_id"
        if self.pending is not None and (not isinstance(self.outcome.get(key), str) or not self.outcome[key]):
            msg = "A pending command requires its target identifier"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class WatchState:
    """Everything the owner of the automation must survive a restart with."""

    schema_version: int = WATCH_STATE_SCHEMA_VERSION
    policy: AutomationPolicy = field(default_factory=AutomationPolicy)
    reservations: tuple[Reservation, ...] = ()
    markers: tuple[ManualHandledMarker, ...] = ()
    requests: tuple[ProcessingRequest, ...] = ()
    acquisitions: tuple[AcquisitionConfirmation, ...] = ()
    products: tuple[ProductConfirmation, ...] = ()
    provider_locks: tuple[ProviderLock, ...] = ()
    command_receipts: tuple[CommandReceipt, ...] = ()
    notified: frozenset[NotificationKey] = frozenset()
    recipes: RecipePreferences = field(default_factory=RecipePreferences)
    ready_groups: tuple[ReadyGroup, ...] = ()
    pause_owned_transfers: tuple[str, ...] = ()
    pending_deletions: tuple[PendingDeletion, ...] = ()


def require_relative_paths(paths: Iterable[str], label: str) -> None:
    """Refuse every persisted path that is not one plain location inside the library."""
    for value in paths:
        candidate: Path = Path(value)
        if not value.strip() or candidate.drive or candidate.root or ".." in candidate.parts:
            msg = f"{label} must stay a relative path inside the library"
            raise ValueError(msg)


def reserve(state: WatchState, reservation: Reservation) -> WatchState | None:
    """Return *state* holding *reservation*, or ``None`` when its group is not free."""
    held: Reservation | None = _reservation(state, reservation.group_id)
    if held is not None and held.client_id != reservation.client_id:
        return None
    if _has_active_request(state, reservation.group_id):
        return None
    remaining: tuple[Reservation, ...] = tuple(
        item for item in state.reservations if item.group_id != reservation.group_id
    )
    return replace(state, reservations=(*remaining, reservation))


def release(state: WatchState, group_id: str, client_id: str) -> WatchState:
    """Return *state* without the reservation *client_id* holds on *group_id*."""
    remaining: tuple[Reservation, ...] = tuple(
        item for item in state.reservations if item.group_id != group_id or item.client_id != client_id
    )
    if len(remaining) == len(state.reservations):
        return state
    return replace(state, reservations=remaining)


def record_request(state: WatchState, request: ProcessingRequest) -> WatchState:
    """Return *state* carrying *request*, replacing an earlier record of the same identifier."""
    remaining: tuple[ProcessingRequest, ...] = tuple(
        item for item in state.requests if item.request_id != request.request_id
    )
    return replace(state, requests=(*remaining, request))


def mark_manual_handled(state: WatchState, marker: ManualHandledMarker) -> WatchState:
    """Return *state* carrying *marker*, replacing an earlier one for the same group and version."""
    remaining: tuple[ManualHandledMarker, ...] = tuple(
        item for item in state.markers if item.group_id != marker.group_id or item.fingerprint != marker.fingerprint
    )
    return replace(state, markers=(*remaining, marker))


def record_command(state: WatchState, receipt: CommandReceipt) -> WatchState:
    """Return *state* carrying *receipt*; a command identifier already accepted changes nothing."""
    if any(item.command_id == receipt.command_id for item in state.command_receipts):
        return state
    return replace(state, command_receipts=(*state.command_receipts, receipt))


def preflight(
    state: WatchState,
    *,
    refused_names: Sequence[str] = (),
    occupied_names: Sequence[str] = (),
) -> tuple[PreflightFinding, ...]:
    """Report every pre-existing fact a controlled transition has to settle, changing nothing.

    *refused_names* are the reserved workspace names left untouched, *occupied_names* the ones
    that already hold content; both come from the caller that may read the filesystem.
    """
    paused: tuple[PreflightFinding, ...] = (
        () if state.policy.auto_enabled else (PreflightFinding(PreflightFindingKind.AUTOMATION_PAUSED),)
    )
    return (
        *paused,
        *(
            PreflightFinding(PreflightFindingKind.DIRECTORY_EXCEPTION, directory)
            for directory in sorted(state.policy.directory_exceptions)
        ),
        *(
            PreflightFinding(PreflightFindingKind.UNFINISHED_REQUEST, request.request_id)
            for request in state.requests
            if request.state in _UNFINISHED_STATES
        ),
        *(PreflightFinding(PreflightFindingKind.RESERVED_NAME_REFUSED, name) for name in refused_names),
        *(PreflightFinding(PreflightFindingKind.RESERVED_NAME_OCCUPIED, name) for name in occupied_names),
    )


def auto_admissible(  # noqa: PLR0913 - every admission condition stays an explicit call-site value
    state: WatchState,
    policy: AutomationPolicy,
    group_id: str,
    directory: str,
    fingerprint: SourceFingerprint,
    requested_products: frozenset[ProductKind],
) -> bool:
    """Whether automatic processing may take *group_id* for that version of its sources."""
    if not policy.effective_auto(directory):
        return False
    if _reservation(state, group_id) is not None:
        return False
    if _has_active_request(state, group_id):
        return False
    if any(request.problem and request.fingerprints.get(group_id) == fingerprint for request in state.requests):
        return False
    if _manual_blocks(state, group_id, fingerprint, requested_products):
        return False
    return not _retries_exhausted(state, policy, group_id, fingerprint)


def _directory_chain(directory: str) -> tuple[str, ...]:
    parts: list[str] = [part for part in directory.replace("\\", "/").split("/") if part]
    return (*("/".join(parts[:index]) for index in range(len(parts), 0, -1)), "")


def _reservation(state: WatchState, group_id: str) -> Reservation | None:
    return next((item for item in state.reservations if item.group_id == group_id), None)


def _has_active_request(state: WatchState, group_id: str) -> bool:
    return any(group_id in request.group_ids and request.state in _UNFINISHED_STATES for request in state.requests)


def _manual_blocks(
    state: WatchState,
    group_id: str,
    fingerprint: SourceFingerprint,
    requested_products: frozenset[ProductKind],
) -> bool:
    marker: ManualHandledMarker | None = next(
        (item for item in state.markers if item.group_id == group_id and item.fingerprint == fingerprint),
        None,
    )
    return marker is not None and bool(requested_products - marker.products)


def _retries_exhausted(
    state: WatchState,
    policy: AutomationPolicy,
    group_id: str,
    fingerprint: SourceFingerprint,
) -> bool:
    failed: tuple[ProcessingRequest, ...] = tuple(
        request
        for request in state.requests
        if request.state is RequestState.FAILED and request.fingerprints.get(group_id) == fingerprint
    )
    return bool(failed) and failed[-1].attempts >= policy.external_retry_budget
