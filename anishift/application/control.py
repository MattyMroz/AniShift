"""Automation policy and ledger contracts shared by the watcher, the panel and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application.intents import GroupIntent, ProductKind, RebuildRequest, RequestOrigin

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "WATCH_STATE_SCHEMA_VERSION",
    "AcquisitionConfirmation",
    "AcquisitionState",
    "AutomationPolicy",
    "CommandReceipt",
    "ManualHandledMarker",
    "NotificationKey",
    "ProcessingRequest",
    "ProductConfirmation",
    "ProviderLock",
    "RequestState",
    "Reservation",
    "SourceFingerprint",
    "SourceSelection",
    "WatchState",
    "auto_admissible",
    "mark_manual_handled",
    "record_command",
    "record_request",
    "release",
    "reserve",
]

# ── Constants ─────────────────────────────────────────────────────────────────

WATCH_STATE_SCHEMA_VERSION: Final[int] = 1
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

    def __post_init__(self) -> None:
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
    if _manual_blocks(state, group_id, fingerprint, requested_products):
        return False
    return not _retries_exhausted(state, policy, group_id, fingerprint)


def _directory_chain(directory: str) -> tuple[str, ...]:
    parts: list[str] = [part for part in directory.replace("\\", "/").split("/") if part]
    return (*("/".join(parts[:index]) for index in range(len(parts), 0, -1)), "")


def _reservation(state: WatchState, group_id: str) -> Reservation | None:
    return next((item for item in state.reservations if item.group_id == group_id), None)


def _has_active_request(state: WatchState, group_id: str) -> bool:
    return any(
        group_id in request.group_ids
        and request.state in {RequestState.ACCEPTED, RequestState.RUNNING, RequestState.PAUSED}
        for request in state.requests
    )


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
