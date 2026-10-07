"""Automation policy and ledger contracts shared by the watcher, the panel and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application.episode_identity import IdentityVerdict
from anishift.application.intents import (
    GroupIntent,
    NarrationTimeline,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    TranslationAction,
)
from anishift.application.release_quality import PolishClass, ResolutionClass, resolution_class
from anishift.application.workflows import WorkflowTarget

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from anishift.application.release_quality import ReleaseTraits
    from anishift.application.subscription_targets import SubscriptionRecord

__all__ = [
    "WATCH_STATE_SCHEMA_VERSION",
    "AcquisitionConfirmation",
    "AcquisitionState",
    "AdmissionConflict",
    "AdmissionSource",
    "AudiobookRecipe",
    "AutomationPolicy",
    "ChoiceTraits",
    "CommandReceipt",
    "EpisodeAssignment",
    "EpisodeChoice",
    "EpisodePublication",
    "FileObjectIdentities",
    "FileReservation",
    "FileStamp",
    "LegacyOrder",
    "LegacyScope",
    "ManualHandledMarker",
    "NarrationTimeline",
    "NotificationKey",
    "PendingDeletion",
    "PreflightFinding",
    "PreflightFindingKind",
    "ProcessingRequest",
    "ProductConfirmation",
    "ProviderLock",
    "PublishedFile",
    "ReadyGroup",
    "RecipePreferences",
    "RequestState",
    "Reservation",
    "SourceFingerprint",
    "SourceSelection",
    "TextResultFormat",
    "TorrentioReference",
    "TranslateRecipe",
    "WatchState",
    "auto_admissible",
    "choice_traits",
    "compact_acquisition",
    "episode_conflict",
    "legacy_conflict",
    "legacy_number",
    "mark_manual_handled",
    "preflight",
    "record_command",
    "record_request",
    "release",
    "require_relative_paths",
    "reserve",
]

# ── Constants ─────────────────────────────────────────────────────────────────

REMOVED_FROM_CLIENT: Final[str] = "removed_from_client"
"""Terminal reason for a previously acknowledged transfer missing from its managed client."""

VERIFICATION_REJECT: Final[str] = "reject:"
"""Prefix of a download check result that rejects the file of a subscription attempt."""

VERIFICATION_SKIPPED: Final[str] = "skipped"
"""Download check result of a check that could not be performed."""

WATCH_STATE_SCHEMA_VERSION: Final[int] = 5
"""Current schema of the persisted automation state."""

type SourceFingerprint = tuple[tuple[str, int, int], ...]
"""Identity of one group input, exactly what ``watch.source_fingerprint`` returns."""

type FileObjectIdentities = tuple[tuple[str, int, int], ...]
"""Relative path, device and inode for every object in one confirmed deletion scope."""

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

type FileStamp = tuple[int, int, int, int]
"""Size, modification time, device and inode proving which file object one name holds."""

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

_DEFAULT_TRANSFER_STALL_S: Final[int] = 10 * 60
"""Active downloading without progress after which a transfer needs attention."""

_DEFAULT_RETRY_BUDGET: Final[int] = 3
"""Attempts one retryable external operation gets in total, the first one included."""

_DEFAULT_RETRY_DELAYS_S: Final[tuple[int, ...]] = (60, 300)
"""Waits between attempts when the server names no delay of its own."""

_UNUSABLE_TRAITS: Final[tuple[str, ...]] = ("dub_only", "hardsub", "raw")
"""Release name and tag facts that exclude a release, in their persisted order."""

_ASSIGNMENT_STOPS: Final[frozenset[str]] = frozenset({"pack", "ambiguous", "no_match", "taken", "recheck"})
"""Reasons a subscription attempt stopped after reading its torrent metadata."""


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
    TRANSFER_METADATA_PENDING = "transfer_metadata_pending"


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

    ADMITTED = "admitted"
    PENDING_SEND = "pending_send"
    UNCERTAIN = "uncertain"
    ACCEPTED = "accepted"
    COMPLETE = "complete"
    FAILED = "failed"


class AdmissionSource(StrEnum):
    """Entry path that admitted one catalogue episode."""

    MANUAL = "manual"
    LEGACY = "legacy"
    SUBSCRIPTION = "subscription"


class AdmissionConflict(StrEnum):
    """Why the owner refuses a new admission of one catalogue episode."""

    ADMITTED = "episode_admitted"
    POSSIBLY_ADMITTED = "episode_possibly_admitted"
    TRANSFER_RECORDED = "transfer_recorded"


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
class TorrentioReference:
    """Stream chosen from Torrentio; its file index and name only hint at the file inside the torrent."""

    info_hash: str
    file_index: int | None = None
    file_name: str | None = None
    release: str = ""
    trackers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.info_hash.strip():
            msg = "A Torrentio reference requires its info hash"
            raise ValueError(msg)
        if not all(isinstance(item, str) and item for item in self.trackers):
            msg = "A Torrentio tracker must be a non-empty address"
            raise ValueError(msg)
        if self.file_index is not None and (type(self.file_index) is not int or self.file_index < 0):
            msg = "A Torrentio file index must be a non-negative whole number"
            raise ValueError(msg)
        object.__setattr__(self, "info_hash", self.info_hash.casefold())


@dataclass(frozen=True, slots=True)
class ChoiceTraits:
    """Quality facts of the admitted release kept after the release details are compacted away."""

    polish: PolishClass
    resolution: ResolutionClass
    unusable: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.polish, PolishClass) or not isinstance(self.resolution, ResolutionClass):
            msg: str = "Choice traits carry a Polish class and a resolution class"
            raise TypeError(msg)
        if self.unusable != tuple(item for item in _UNUSABLE_TRAITS if item in self.unusable):
            msg = "Choice traits name each known unusable fact once, in order"
            raise ValueError(msg)


def choice_traits(traits: ReleaseTraits) -> ChoiceTraits:
    """Return the persisted snapshot of the quality facts of one ranked release."""
    flags: dict[str, bool] = {"dub_only": traits.dub_only, "hardsub": traits.hardsub, "raw": traits.raw}
    return ChoiceTraits(
        polish=traits.polish,
        resolution=resolution_class(traits.resolution)[0],
        unusable=tuple(item for item in _UNUSABLE_TRAITS if flags[item]),
    )


@dataclass(frozen=True, slots=True)
class EpisodeChoice:
    """One catalogue episode, the stream chosen for it and the H1 evidence it was chosen on."""

    anilist_id: int
    number: int
    reference: TorrentioReference
    target: Mapping[str, object]
    verdict: IdentityVerdict
    reason: str
    deviation_confirmed: bool = False
    traits: ChoiceTraits | None = None

    def __post_init__(self) -> None:
        if not _positive(self.anilist_id) or not _positive(self.number):
            msg = "An episode choice requires a positive AniList ID and episode number"
            raise ValueError(msg)
        if self.verdict is IdentityVerdict.MISMATCH and not self.deviation_confirmed:
            msg = "An H1 mismatch requires a confirmed deviation"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PublishedFile:
    """One staged file of an episode set, its reserved flat name and the proof of its verified copy."""

    index: int
    source: str
    name: str
    size: int
    digest: str | None = None
    stamp: FileStamp | None = None

    def __post_init__(self) -> None:
        require_relative_paths((self.source, self.name), "A published episode file")
        if "/" in self.name.replace("\\", "/") or self.index < 0 or self.size < 0:
            msg = "A published episode file needs a flat name, a client index and its declared size"
            raise ValueError(msg)
        if (self.digest is None) != (self.stamp is None):
            msg = "A copied episode file proves both its content and its file object"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class EpisodePublication:
    """Flat set reserved for one episode, copied from staging and handed to Auto as a whole."""

    files: tuple[PublishedFile, ...]
    handed_off: bool = False
    problem: str | None = None

    def __post_init__(self) -> None:
        names: tuple[str, ...] = tuple(item.name.casefold() for item in self.files)
        if not self.files or len(set(names)) != len(names):
            msg = "An episode publication reserves one unique name per file"
            raise ValueError(msg)
        if self.handed_off and not self.copied:
            msg = "Only a set whose every copy is proven can be handed to Auto"
            raise ValueError(msg)

    @property
    def copied(self) -> bool:
        """Whether every file of the set has a recorded, verified copy."""
        return all(item.stamp is not None for item in self.files)


@dataclass(frozen=True, slots=True)
class EpisodeAssignment:
    """One catalogue episode admitted into a selective transfer."""

    admission_id: str
    admitted_at: str
    source: AdmissionSource
    choice: EpisodeChoice
    previous_admission_id: str | None = None
    file_map: str | None = None
    files: tuple[FileReservation, ...] = ()
    conflict: tuple[str, ...] = ()
    replaced: bool = False
    publication: EpisodePublication | None = None
    group_id: str | None = None
    video_path: str | None = None
    subscription_id: str | None = None
    attempt: int | None = None
    verification: str | None = None
    verified_stamp: FileStamp | None = None
    stopped: str | None = None

    def __post_init__(self) -> None:
        if not self.admission_id.strip() or not self.admitted_at.strip():
            msg = "An episode assignment requires its own admission identity and time"
            raise ValueError(msg)
        if self.stopped is not None and self.stopped not in _ASSIGNMENT_STOPS:
            msg = "A stopped episode assignment names a known stop reason"
            raise ValueError(msg)
        self._check_attempt()
        if self.files and self.file_map is None:
            msg = "Episode files require the file map they were bound on"
            raise ValueError(msg)
        indexes: tuple[int, ...] = tuple(index for index, _path, _size in self.files)
        if any(index < 0 for index in indexes) or len(set(indexes)) != len(indexes):
            msg = "An episode file must carry one unique client file index"
            raise ValueError(msg)
        if any(size < 0 for _index, _path, size in self.files):
            msg = "An episode file must carry the size its torrent declares"
            raise ValueError(msg)
        require_relative_paths((path for _index, path, _size in self.files), "An episode file of a torrent")
        if self.video_path is not None:
            require_relative_paths((self.video_path,), "A retained episode video")
        if not all(isinstance(item, str) and item for item in self.conflict):
            msg = "An overridden legacy conflict is named by non-empty references"
            raise ValueError(msg)
        if self.publication is not None and sorted(
            (item.index, item.source, item.size) for item in self.publication.files
        ) != sorted(self.files):
            msg = "An episode publication covers exactly the files of its episode"
            raise ValueError(msg)

    @property
    def mapped(self) -> bool:
        """Whether the episode was bound against the metadata of its torrent, with or without a file."""
        return self.file_map is not None

    @property
    def rejected(self) -> bool:
        """Whether the download check rejected the file of this subscription attempt."""
        return self.verification is not None and self.verification.startswith(VERIFICATION_REJECT)

    def _check_attempt(self) -> None:
        attempt: bool = self.source is AdmissionSource.SUBSCRIPTION
        if attempt != (self.subscription_id is not None) or attempt != (self.attempt is not None):
            msg: str = "Exactly a subscription attempt names its subscription and attempt number"
            raise ValueError(msg)
        if self.attempt is not None and (type(self.attempt) is not int or self.attempt < 1):
            msg = "A subscription attempt is numbered from one"
            raise ValueError(msg)
        if not attempt and self.verification is not None:
            msg = "Only a subscription attempt carries a download check"
            raise ValueError(msg)
        accepted: bool = self.verification is not None and not self.rejected
        if attempt and self.publication is not None and not accepted:
            msg = "A published subscription attempt passed its download check"
            raise ValueError(msg)
        checked: bool = accepted and self.verification != VERIFICATION_SKIPPED
        if self.verified_stamp is not None and not checked:
            msg = "Only a performed, accepted download check binds the checked file"
            raise ValueError(msg)
        if checked and self.publication is not None and self.verified_stamp is None:
            msg = "A published, checked subscription attempt binds the checked file"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class LegacyScope:
    """Catalogue entry, and its local episode when known, that one unkeyed legacy order may cover."""

    anilist_id: int
    number: int | None

    def __post_init__(self) -> None:
        if not _positive(self.anilist_id) or (self.number is not None and not _positive(self.number)):
            msg = "A legacy scope requires a positive AniList ID and, when known, a positive episode"
            raise ValueError(msg)

    def covers(self, anilist_id: int, number: int) -> bool:
        """Whether this order may be the one that already took *number* of *anilist_id*."""
        return self.anilist_id == anilist_id and self.number in {None, number}


@dataclass(frozen=True, slots=True)
class LegacyOrder:
    """One order of the former subscription file, materialized with its conflict reference."""

    anilist_id: int
    number: int | None
    reference: str
    operation_id: str | None
    complete: bool

    def __post_init__(self) -> None:
        if not self.reference or (self.operation_id is not None and not self.operation_id):
            msg = "A legacy order requires its conflict reference and, when recorded, its operation"
            raise ValueError(msg)
        LegacyScope(self.anilist_id, self.number)

    @property
    def scope(self) -> LegacyScope:
        """Catalogue entry and local episode this order may cover."""
        return LegacyScope(self.anilist_id, self.number)


def legacy_number(value: str | Decimal | None) -> int | None:
    """Return a recorded season-local episode as a catalogue number, or nothing when it cannot be one."""
    if value is None:
        return None
    try:
        number: Decimal = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value() or number < 1:
        return None
    return int(number)


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
    nyaa_release_id: int | None = None
    release_title: str | None = None
    previous_operation_id: str | None = None
    assignments: tuple[EpisodeAssignment, ...] = ()
    legacy_scope: LegacyScope | None = None
    selection_revision: int = 0
    applied_revision: int = 0
    manifest: tuple[str, ...] = ()
    cleaned: bool = False

    @property
    def manual(self) -> bool:
        """Whether an explicit user order or explicit reacquire owns this transfer independently of automation."""
        if any(item.source is AdmissionSource.SUBSCRIPTION for item in self.assignments):
            return self.previous_operation_id is not None or any(
                item.source is AdmissionSource.MANUAL for item in self.active_assignments
            )
        return self.origin is RequestOrigin.USER and (
            self.subscription_id is None or self.previous_operation_id is not None
        )

    @property
    def selective(self) -> bool:
        """Whether this transfer was admitted per catalogue episode instead of as a legacy release."""
        return bool(self.assignments)

    @property
    def active_assignments(self) -> tuple[EpisodeAssignment, ...]:
        """Episodes of this transfer that no later explicit repeat replaced."""
        return tuple(item for item in self.protected_assignments if not item.replaced)

    @property
    def protected_assignments(self) -> tuple[EpisodeAssignment, ...]:
        """Admissions retained unless the user ended their transfer before publication."""
        ended: bool = self.state is AcquisitionState.FAILED and (
            self.problem == REMOVED_FROM_CLIENT or self.requested_action == "cancel"
        )
        return tuple(item for item in self.assignments if not ended or item.publication is not None)

    @property
    def client_confirmed(self) -> bool:
        """Whether durable state proves the client previously acknowledged this transfer."""
        return self.content_started or self.applied_revision > 0

    @property
    def wanted_files(self) -> frozenset[int]:
        """Client file indexes every still active episode of this transfer needs."""
        return frozenset(index for item in self.active_assignments for index, _path, _size in item.files)

    def __post_init__(self) -> None:
        if type(self.selection_revision) is not int or type(self.applied_revision) is not int:
            msg = "A selection revision is a whole number"
            raise TypeError(msg)
        if not 0 <= self.applied_revision <= self.selection_revision:
            msg = "A confirmed selection cannot be newer than the recorded one"
            raise ValueError(msg)
        if self.assignments and self.legacy_scope is not None:
            msg = "A selective transfer carries episode assignments, never a legacy scope"
            raise ValueError(msg)
        if not self.assignments and (self.state is AcquisitionState.ADMITTED or self.manifest or self.cleaned):
            msg = "Only a selective transfer can wait as an admission or keep a staging manifest"
            raise ValueError(msg)
        admissions: tuple[str, ...] = tuple(item.admission_id for item in self.assignments)
        if len(set(admissions)) != len(admissions):
            msg = "Every episode assignment requires its own admission identity"
            raise ValueError(msg)
        if any(item.choice.reference.info_hash != self.info_hash.casefold() for item in self.assignments):
            msg = "An episode assignment must reference the transfer that carries it"
            raise ValueError(msg)
        if (self.nyaa_release_id is None) != (self.release_title is None):
            msg = "A retained release requires both its verified Nyaa identifier and original title"
            raise ValueError(msg)
        if self.nyaa_release_id is not None and (
            type(self.nyaa_release_id) is not int or self.nyaa_release_id <= 0 or not self.release_title
        ):
            msg = "A retained Nyaa release requires a positive identifier and original title"
            raise ValueError(msg)
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
        require_relative_paths(self.manifest, "A staged file of a selective transfer")
        object.__setattr__(self, "info_hash", self.info_hash.casefold())


def compact_acquisition(item: AcquisitionConfirmation) -> AcquisitionConfirmation:
    """Discard staging evidence only after a selective transfer's successful cleanup."""
    if not item.selective or not item.cleaned or item.state is not AcquisitionState.COMPLETE:
        return item
    assignments: tuple[EpisodeAssignment, ...] = tuple(
        replace(
            assignment,
            choice=replace(
                assignment.choice,
                target={},
                reference=replace(
                    assignment.choice.reference,
                    trackers=(),
                    release="",
                    file_index=None,
                    file_name=Path(assignment.video_path).name
                    if assignment.video_path is not None
                    else assignment.choice.reference.file_name,
                ),
            ),
            files=(),
            file_map=None,
            publication=None,
        )
        for assignment in item.assignments
    )
    return replace(item, manifest=(), file_layout=(), required_files=(), complete_files=(), assignments=assignments)


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


class DeletionStatus(StrEnum):
    """Evidence recorded before or after a single native file operation."""

    INFLIGHT = "inflight"
    RECYCLED = "recycled"
    REFUSED = "refused"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class DeletionOutcome:
    """One file's durable native result, including an opaque exact-item recycle receipt."""

    path: str
    status: DeletionStatus
    reason: str
    receipt: str | None = None

    def __post_init__(self) -> None:
        require_relative_paths((self.path,), "A deletion result")
        if self.status is DeletionStatus.RECYCLED and not self.receipt:
            msg = "A recycled result requires native item evidence"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    """Durable progress for one exact receipt and its reserved staging path."""

    path: str
    staging: str
    status: str = "prepared"
    reason: str = "restore_prepared"
    started: bool = False

    def __post_init__(self) -> None:
        require_relative_paths((self.path, self.staging), "A restored file")
        if self.status not in {"prepared", "inflight", "restored", "refused", "uncertain"}:
            msg = "Unknown restore outcome"
            raise ValueError(msg)
        if not self.staging.startswith("temp/.restore-") or self.staging == self.path:
            msg = "Restore staging must stay in its private workspace temporary directory"
            raise ValueError(msg)
        if type(self.started) is not bool or (self.status in {"inflight", "restored"} and not self.started):
            msg = "Restore effects require a persisted start"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DeletionRestore:
    """One explicit undo intent retained with the original deletion across restarts."""

    operation_id: str
    outcomes: tuple[RestoreOutcome, ...]
    completed: bool = False

    @property
    def unsettled(self) -> bool:
        """Protect only started native effects that have not been proven restored."""
        return any(item.started and item.status != "restored" for item in self.outcomes)

    def __post_init__(self) -> None:
        names: tuple[str, ...] = tuple(item.path for item in self.outcomes)
        staging: tuple[str, ...] = tuple(item.staging for item in self.outcomes)
        if (
            type(self.completed) is not bool
            or not self.operation_id
            or len(set(names)) != len(names)
            or len(set(staging)) != len(staging)
        ):
            msg = "Restore requires one identity and unique file destinations"
            raise ValueError(msg)
        if self.completed and any(item.status != "restored" for item in self.outcomes):
            msg = "Completed restoration requires every file result"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PendingDeletion:
    """One confirmed whole-set deletion, the identity of each file it covers and what already went out."""

    operation_id: str
    set_id: str
    requested_at: str
    files: SourceFingerprint
    recycled: tuple[str, ...] = ()
    identities: FileObjectIdentities = ()
    outcomes: tuple[DeletionOutcome, ...] = ()
    instance_id: str | None = None
    restore: DeletionRestore | None = None

    def __post_init__(self) -> None:
        if not self.files:
            msg = "A pending deletion must name at least one file"
            raise ValueError(msg)
        names: tuple[str, ...] = tuple(name for name, _size, _mtime_ns in self.files)
        require_relative_paths((*names, *self.recycled), "A file of a pending deletion")
        if not frozenset(self.recycled) <= frozenset(names):
            msg = "A recycled file must belong to its confirmed deletion"
            raise ValueError(msg)
        identity_names: tuple[str, ...] = tuple(name for name, _device, _inode in self.identities)
        outcome_names: tuple[str, ...] = tuple(item.path for item in self.outcomes)
        if len(names) != len(set(names)) or len(outcome_names) != len(set(outcome_names)):
            msg = "A deletion cannot contain duplicate files or outcomes"
            raise ValueError(msg)
        if self.identities and (set(identity_names) != set(names) or len(identity_names) != len(names)):
            msg = "Strong deletion identities must cover exactly the confirmed files"
            raise ValueError(msg)
        if not set(outcome_names) <= set(names):
            msg = "A deletion outcome must belong to its confirmed scope"
            raise ValueError(msg)
        if self.identities and set(self.recycled) != {
            item.path for item in self.outcomes if item.status is DeletionStatus.RECYCLED
        }:
            msg = "Recycled files must have matching native results"
            raise ValueError(msg)
        if self.outcomes and not self.identities:
            msg = "Native deletion outcomes require strong file identities"
            raise ValueError(msg)
        if self.restore is not None and (
            not self.identities or {item.path for item in self.restore.outcomes} != set(names)
        ):
            msg = "Restoration must cover exactly the original strongly identified scope"
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
    subscriptions: tuple[SubscriptionRecord, ...] = ()
    removed_subscription: SubscriptionRecord | None = None
    legacy_orders: tuple[LegacyOrder, ...] = ()

    def __post_init__(self) -> None:
        identities: tuple[str, ...] = tuple(item.subscription_id for item in self.subscriptions)
        entries: tuple[int, ...] = tuple(item.anilist_id for item in self.subscriptions if item.anilist_id is not None)
        if len(set(identities)) != len(identities) or len(set(entries)) != len(entries):
            msg = "Every subscription has its own identity and follows its own catalogue entry"
            raise ValueError(msg)


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
    *,
    succeeded_groups: Mapping[str, frozenset[str]] | None = None,
    explicit: bool = False,
) -> bool:
    """Whether Auto may take this source version, with successful groups keyed by request ID."""
    if not explicit and not policy.effective_auto(directory):
        return False
    if _reservation(state, group_id) is not None:
        return False
    if _has_active_request(state, group_id):
        return False
    if any(request.problem and request.fingerprints.get(group_id) == fingerprint for request in state.requests):
        return False
    if _latest_request_blocks(state, group_id, fingerprint, succeeded_groups):
        return False
    return not _manual_blocks(state, group_id, fingerprint, requested_products)


def episode_conflict(state: WatchState, anilist_id: int, number: int) -> AdmissionConflict | None:
    """Why admitting *number* of *anilist_id* would repeat an order recorded in *state*."""
    if any(
        item.choice.anilist_id == anilist_id and item.choice.number == number
        for acquisition in state.acquisitions
        for item in acquisition.protected_assignments
    ):
        return AdmissionConflict.ADMITTED
    recorded: tuple[LegacyScope, ...] = (
        *(item.legacy_scope for item in state.acquisitions if item.legacy_scope is not None),
        *(item.scope for item in state.legacy_orders),
    )
    if any(scope.covers(anilist_id, number) for scope in recorded):
        return AdmissionConflict.POSSIBLY_ADMITTED
    return None


def legacy_conflict(state: WatchState, scope: LegacyScope) -> bool:
    """Whether an unkeyed legacy order in *scope* may repeat an episode admitted per catalogue key."""
    return any(
        scope.covers(item.choice.anilist_id, item.choice.number)
        for acquisition in state.acquisitions
        for item in acquisition.protected_assignments
    )


def _positive(value: object) -> bool:
    return type(value) is int and value >= 1


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


def _latest_request_blocks(
    state: WatchState,
    group_id: str,
    fingerprint: SourceFingerprint,
    succeeded_groups: Mapping[str, frozenset[str]] | None,
) -> bool:
    latest: ProcessingRequest | None = max(
        (
            request
            for request in reversed(state.requests)
            if group_id in request.group_ids and request.fingerprints.get(group_id) == fingerprint
        ),
        key=lambda request: request.accepted_at,
        default=None,
    )
    if latest is None:
        return False
    return latest.state in {RequestState.FAILED, RequestState.PARTIAL} and group_id not in (
        () if succeeded_groups is None else succeeded_groups.get(latest.request_id, ())
    )
