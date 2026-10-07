"""Versioned, atomic persistence of the automation state under the watch directory."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AudiobookRecipe,
    AutomationPolicy,
    ChoiceTraits,
    CommandReceipt,
    DeletionOutcome,
    DeletionRestore,
    DeletionStatus,
    EpisodeAssignment,
    EpisodeChoice,
    EpisodePublication,
    LegacyOrder,
    LegacyScope,
    ManualHandledMarker,
    NarrationTimeline,
    PendingDeletion,
    PreflightFinding,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    PublishedFile,
    ReadyGroup,
    RecipePreferences,
    RequestState,
    Reservation,
    RestoreOutcome,
    SourceSelection,
    TextResultFormat,
    TorrentioReference,
    TranslateRecipe,
    WatchState,
    preflight,
)
from anishift.application.control_payloads import decode_intent, encode_intent
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import AniZipMapping, ListedEpisode, ListedSpecial
from anishift.application.intents import (
    GroupIntent,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    TranslationAction,
)
from anishift.application.release_quality import PolishClass, ResolutionClass
from anishift.application.subscription_migration import migrate, migrate_to_five
from anishift.application.subscription_targets import (
    PauseReason,
    PolishObservation,
    PolishSkip,
    PolishState,
    ReleaseFailure,
    SubscriptionCheck,
    SubscriptionProblem,
    SubscriptionRecord,
    SubscriptionTarget,
    TargetState,
)
from anishift.application.subscriptions import SUBSCRIPTIONS_FILE_NAME, Subscription, decode_subscriptions
from anishift.application.workflows import WorkflowTarget
from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.paths import run_journal_dir, watch_dir
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from anishift.application.control import (
        CommandOutcome,
        FileObjectIdentities,
        FileReservation,
        FileStamp,
        NotificationKey,
        SettingsSnapshot,
        SettingValue,
        SourceFingerprint,
    )

__all__ = [
    "WATCH_STATE_FILE_NAME",
    "WatchStateStore",
    "watch_state_path",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

WATCH_STATE_FILE_NAME: Final[str] = "state.json"
"""Filename of the automation state, written beside the other watch state files."""

_BACKUP_SUFFIX: Final[str] = ".bak"
"""Ending of the copy kept from the last state that could be read back."""

_SCHEMA_BACKUP_TEMPLATE: Final[str] = ".v{version}.bak"
"""Ending of the copy kept from a document an older schema wrote, before it is rewritten."""

_MIGRATION_BACKUP_SUFFIXES: Final[Mapping[int, str]] = MappingProxyType(
    {3: ".e2-migration.bak", 4: ".e3-migration.bak", 5: ".a1-migration.bak"}
)
"""Ending of the byte-identical copies kept of both owner files before the first write of each schema."""

_SCHEMA_ONE: Final[int] = 1
"""Schema this build still reads and migrates once, filling the sections it never wrote."""

_SCHEMA_TWO: Final[int] = 2
"""Schema this build still reads and migrates once, marking every acquisition as legacy."""

_SCHEMA_THREE: Final[int] = 3
"""Schema this build still reads and migrates once, moving the subscription file into the state."""

_SCHEMA_FOUR: Final[int] = 4
"""Schema this build still reads and migrates once, adding the facts of the release choice."""

_SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[int]] = frozenset(
    {_SCHEMA_ONE, _SCHEMA_TWO, _SCHEMA_THREE, _SCHEMA_FOUR, WATCH_STATE_SCHEMA_VERSION}
)
"""Schema versions of the automation state this build still reads."""

_SCHEMA_FOUR_SECTIONS: Final[tuple[str, ...]] = ("subscriptions", "removed_subscription", "legacy_orders")
"""Root sections schema 4 added, which every schema 4 document must carry and no older one may."""

_SUBSCRIPTION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "subscription_id",
        "anilist_id",
        "kitsu_id",
        "mapping",
        "title",
        "subscribed_at",
        "cut",
        "paused",
        "pause_reason",
        "migrated_at",
        "review_pending",
        "merged_from",
        "problem",
        "catalog_status",
        "episode_count",
        "refreshed_at",
        "checked_at",
        "last_check",
        "targets",
        "migrated_from",
    }
)
"""Keys a serialized subscription must carry."""

_SUBSCRIPTION_KEYS_FIVE: Final[frozenset[str]] = frozenset({"tsukihime_id", "mapping_tvdb_season"})
"""Subscription keys schema 5 added, which every schema 5 document must carry and no older one may."""

_TARGET_KEYS_FIVE: Final[frozenset[str]] = frozenset(
    {"started", "threshold", "failures", "polish", "sources_down_since", "polish_skip"}
)
"""Target keys schema 5 added, which every schema 5 document must carry and no older one may."""

_ASSIGNMENT_KEYS_FIVE: Final[frozenset[str]] = frozenset({"traits", "stopped"})
"""Assignment keys schema 5 added, which every schema 5 document must carry and no older one may."""

_FAILURE_KEYS: Final[frozenset[str]] = frozenset({"hash", "decisive", "transient"})
"""Keys a serialized release failure must carry."""

_POLISH_KEYS: Final[frozenset[str]] = frozenset({"state", "observed_at"})
"""Keys a serialized Polish observation must carry."""

_POLISH_SKIP_KEYS: Final[frozenset[str]] = frozenset({"due", "at", "settled"})
"""Keys a serialized Polish skip must carry."""

_TRAITS_KEYS: Final[frozenset[str]] = frozenset({"polish", "resolution", "unusable"})
"""Keys serialized choice traits must carry."""

_TARGET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "number",
        "due_at",
        "state",
        "attempts",
        "tried",
        "admission_id",
        "reason",
        "notified_late",
        "check_skipped",
    }
)
"""Keys a serialized subscription target must carry."""

_CHECK_KEYS: Final[frozenset[str]] = frozenset(
    {"checked_at", "number", "matching", "uncertain", "mismatched", "outcome"}
)
"""Keys a serialized subscription check must carry."""

_MAPPING_KEYS: Final[frozenset[str]] = frozenset(
    {"kitsu_id", "catalog_type", "episode_count", "episodes", "specials", "raw_episodes"}
)
"""Keys a serialized episode mapping must carry."""

_LISTED_EPISODE_KEYS: Final[frozenset[str]] = frozenset(
    {"number", "title", "airs_at", "season", "episode", "absolute", "aired", "airs_at_fallback"}
)
"""Keys a serialized mapped episode must carry."""

_LISTED_SPECIAL_KEYS: Final[frozenset[str]] = frozenset({"key", "title", "airs_on"})
"""Keys a serialized mapped extra must carry."""

_LEGACY_ORDER_KEYS: Final[frozenset[str]] = frozenset({"anilist_id", "number", "reference", "operation_id", "complete"})
"""Keys a serialized legacy order must carry."""

_SUBSCRIPTIONS_INVALID_MESSAGE: Final[str] = "Subscriptions file is invalid, so the automation state was not migrated"
"""Sentence shown when the former subscription file cannot be read for the migration."""

_SUBSCRIPTIONS_INVALID_SUGGESTION: Final[str] = (
    "Restore config/subscriptions.json.e3-migration.bak or config/subscriptions.json.v<n>.bak "
    "and start the resident again"
)
"""Only recovery a user can perform before the subscription file is migrated."""

_SCHEMA_THREE_ACQUISITION_FIELDS: Final[tuple[str, ...]] = (
    "assignments",
    "legacy_scope",
    "selection_revision",
    "applied_revision",
    "manifest",
    "cleaned",
)
"""Acquisition fields schema 3 added, which every schema 3 document must carry and no older one may."""

_PUBLICATION_DEFAULTS: Final[dict[str, object]] = {"manifest": [], "cleaned": False}
"""Publication fields absent from schema 3 records written before selective publication existed."""

_SCHEMA_TWO_SECTIONS: Final[tuple[str, ...]] = (
    "recipes",
    "ready_groups",
    "pause_owned_transfers",
    "pending_deletions",
)
"""Root sections schema 2 added, which every schema 2 document must carry and no schema 1 one may."""

_TEMPORARY_SUFFIX: Final[str] = ".tmp"
"""Ending of the file a save writes before it replaces the state."""

_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "policy",
        "reservations",
        "markers",
        "requests",
        "acquisitions",
        "products",
        "provider_locks",
        "command_receipts",
        "notified",
    }
)
"""Only root keys accepted from a persisted automation state, beside the sections schema 2 added."""

_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "auto_enabled",
        "directory_exceptions",
        "release_delay_default_s",
        "recheck_interval_s",
        "search_window_s",
        "transfer_stall_s",
        "external_retry_budget",
        "retry_delays_s",
    }
)
"""Keys a serialized automation policy must carry."""

_RESERVATION_KEYS: Final[frozenset[str]] = frozenset({"group_id", "fingerprint", "client_id", "reserved_at"})
"""Keys a serialized reservation must carry."""

_MARKER_KEYS: Final[frozenset[str]] = frozenset({"group_id", "fingerprint", "products", "request_id", "recorded_at"})
"""Keys a serialized manual decision must carry."""

_REQUEST_KEYS: Final[frozenset[str]] = frozenset(
    {
        "request_id",
        "generation",
        "group_ids",
        "fingerprints",
        "origin",
        "source_selection",
        "rebuild",
        "settings",
        "state",
        "attempts",
        "accepted_at",
    }
)
"""Keys a serialized processing request must carry."""

_ACQUISITION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "operation_id",
        "requested_action",
        "action_id",
        "action_pending",
        "problem",
        "info_hash",
        "directory",
        "required_files",
        "state",
        "origin",
        "subscription_id",
        "episode",
        "updated_at",
    }
)
"""Keys a serialized acquisition confirmation must carry beside the completeness schema 2 added."""

_PRODUCT_KEYS: Final[frozenset[str]] = frozenset(
    {"group_id", "artifact_kind", "path", "generation", "request_id", "origin"}
)
"""Keys a serialized product confirmation must carry."""

_PROVIDER_LOCK_KEYS: Final[frozenset[str]] = frozenset({"provider", "until", "reason"})
"""Keys a serialized provider lock must carry."""

_RECIPES_KEYS: Final[frozenset[str]] = frozenset({"translate", "audiobook"})
"""Keys a serialized set of recipe preferences must carry."""

_TRANSLATE_RECIPE_KEYS: Final[frozenset[str]] = frozenset({"text_result", "translation_action"})
"""Keys a serialized translate recipe must carry."""

_AUDIOBOOK_RECIPE_KEYS: Final[frozenset[str]] = frozenset({"translation_action", "timeline"})
"""Keys a serialized audiobook recipe must carry."""

_READY_GROUP_KEYS: Final[frozenset[str]] = frozenset(
    {
        "set_id",
        "group_id",
        "stem",
        "source_directory",
        "source_stem",
        "target",
        "sources",
        "products",
        "main_result",
        "recipe",
    }
)
"""Keys a serialized completed set must carry beside its pending sources."""

_PENDING_DELETION_KEYS: Final[frozenset[str]] = frozenset(
    {"operation_id", "set_id", "requested_at", "files", "recycled"}
)
"""Keys a serialized pending deletion must carry."""

_RECEIPT_KEYS: Final[frozenset[str]] = frozenset({"command_id", "accepted_at", "outcome"})
"""Keys a serialized command receipt must carry."""

_ASSIGNMENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "admission_id",
        "admitted_at",
        "source",
        "previous_admission_id",
        "anilist_id",
        "number",
        "reference",
        "target",
        "verdict",
        "reason",
        "deviation_confirmed",
        "file_map",
        "files",
        "conflict",
        "replaced",
        "publication",
        "group_id",
        "video_path",
        "subscription_id",
        "attempt",
        "verification",
        "verified_stamp",
    }
)
"""Keys a serialized episode assignment must carry."""

_OPTIONAL_ASSIGNMENT_KEYS: Final[tuple[str, ...]] = (
    "publication",
    "group_id",
    "video_path",
    "subscription_id",
    "attempt",
    "verification",
    "verified_stamp",
)
"""Assignment keys a document written before they existed may omit."""

_PUBLICATION_KEYS: Final[frozenset[str]] = frozenset({"files", "handed_off", "problem"})
"""Keys a serialized episode publication must carry."""

_PUBLISHED_FILE_KEYS: Final[frozenset[str]] = frozenset({"index", "source", "name", "size", "digest", "stamp"})
"""Keys a serialized published episode file must carry."""

_STAMP_FIELDS: Final[int] = 4
"""Size, modification time, device and inode of one proven file object."""

_REFERENCE_KEYS: Final[frozenset[str]] = frozenset({"info_hash", "file_index", "file_name", "release", "trackers"})
"""Keys a serialized Torrentio reference must carry."""

_LEGACY_SCOPE_KEYS: Final[frozenset[str]] = frozenset({"anilist_id", "number"})
"""Keys a serialized legacy scope must carry."""

_FINGERPRINT_FIELDS: Final[int] = 3
"""Name, size and modification time of one source file."""

_NOTIFICATION_FIELDS: Final[int] = 3
"""Group or episode, generation and kind of one notification."""

_RESERVATION_FIELDS: Final[int] = 3
"""Client file index, reserved flat path and declared size of one ordered file."""

_INVALID_MESSAGE: Final[str] = "Automation state file is invalid"
"""Sentence shown when the stored automation state cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Restore config/watch/state.json.bak or delete config/watch/state.json"
"""Only recovery a user can perform on a broken automation state."""


def watch_state_path() -> Path:
    """Return the absolute path of the automation state under the watch directory."""
    return watch_dir() / WATCH_STATE_FILE_NAME


def _fresh_state() -> WatchState:
    """Answer a never-stored configuration, where automation works without anybody switching it on."""
    return WatchState(policy=AutomationPolicy(auto_enabled=True))


class WatchStateStore:
    """Reads and writes the automation state without ever answering with an empty one."""

    def __init__(
        self,
        path: Path,
        *,
        subscriptions_path: Path | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._path: Path = path
        self._readable: bool = False
        self._clock: Callable[[], datetime] = clock
        self._subscriptions_path: Path = (
            subscriptions_path if subscriptions_path is not None else path.parent.parent / SUBSCRIPTIONS_FILE_NAME
        )

    def run_path(self, run_id: str) -> Path:
        """Locate the private checkpoint of one safe run identifier."""
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            msg = "A checkpoint requires a safe run identifier"
            raise ValueError(msg)
        return run_journal_dir(self._path.parent) / f"{run_id}.json"

    def history_path(self) -> Path:
        """Locate the nonauthoritative operational journal beside this owner's state."""
        return self._path.parent / "history.jsonl"

    def load(self) -> WatchState:
        """Read the stored automation state, migrating an older schema once, never answering empty."""
        self._readable = False
        try:
            content: bytes = self._path.read_bytes()
        except FileNotFoundError:
            return self._migrate_without_state()
        except OSError as problem:
            raise _invalid_file() from problem
        try:
            stored: WatchState = _parse(content.decode("utf-8"))
        except UnicodeDecodeError as problem:
            raise _invalid_file() from problem
        self._readable = True
        if stored.schema_version == WATCH_STATE_SCHEMA_VERSION:
            return stored
        return self._upgrade(content, stored)

    def save(self, state: WatchState) -> None:
        """Persist *state*, keeping the last readable version as a backup beside it."""
        if not self._path.exists():
            self._preserve_before_migration(0, {self._path: None, self._subscriptions_path: self._legacy_bytes()})
        self._write(state)

    def _write(self, state: WatchState) -> None:
        payload: str = json.dumps(_encode_state(state), indent=2, ensure_ascii=False) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = self._path.with_name(f"{self._path.name}{_TEMPORARY_SUFFIX}")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._back_up()
        temporary.replace(self._path)
        self._readable = True

    def _upgrade(self, content: bytes, stored: WatchState) -> WatchState:
        legacy_content: bytes | None = self._legacy_bytes()
        migrated: WatchState = self._migrated(stored, legacy_content)
        _keep_backup(
            self._path.with_name(f"{self._path.name}{_SCHEMA_BACKUP_TEMPLATE.format(version=stored.schema_version)}"),
            content,
        )
        self._preserve_before_migration(
            stored.schema_version, {self._path: content, self._subscriptions_path: legacy_content}
        )
        self._write_migrated(migrated)
        findings: tuple[PreflightFinding, ...] = preflight(migrated)
        logger.info(
            "Automation state migrated",
            stored_schema=stored.schema_version,
            schema=WATCH_STATE_SCHEMA_VERSION,
            subscriptions=len(migrated.subscriptions),
            legacy_orders=len(migrated.legacy_orders),
            findings=tuple(sorted({finding.kind.value for finding in findings})),
        )
        return migrated

    def _migrate_without_state(self) -> WatchState:
        legacy_content: bytes | None = self._legacy_bytes()
        if legacy_content is None:
            return _fresh_state()
        migrated: WatchState = self._migrated(_fresh_state(), legacy_content)
        self._preserve_before_migration(0, {self._path: None, self._subscriptions_path: legacy_content})
        self._write_migrated(migrated)
        logger.info(
            "Subscriptions migrated into a new automation state",
            subscriptions=len(migrated.subscriptions),
            legacy_orders=len(migrated.legacy_orders),
        )
        return migrated

    def _migrated(self, stored: WatchState, legacy_content: bytes | None) -> WatchState:
        four: bool = stored.schema_version == _SCHEMA_FOUR
        legacy: tuple[Subscription, ...] = () if four else _decode_legacy(legacy_content)
        try:
            imported: WatchState = stored if four else migrate(stored, legacy, self._clock())
            migrated: WatchState = migrate_to_five(imported)
            return _decode_state(json.loads(json.dumps(_encode_state(migrated))))
        except (KeyError, TypeError, ValueError) as problem:
            raise _subscriptions_invalid() from problem

    def _write_migrated(self, state: WatchState) -> None:
        try:
            self._write(state)
        except OSError as problem:
            raise _migration_blocked() from problem

    def _legacy_bytes(self) -> bytes | None:
        try:
            return self._subscriptions_path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as problem:
            raise _subscriptions_invalid() from problem

    def _preserve_before_migration(self, stored_version: int, sources: Mapping[Path, bytes | None]) -> None:
        pending: tuple[tuple[Path, bytes | None], ...] = tuple(
            (source.with_name(f"{source.name}{suffix}"), content)
            for version, suffix in _MIGRATION_BACKUP_SUFFIXES.items()
            if stored_version < version
            for source, content in sources.items()
        )
        for backup, content in pending:
            if content is None:
                logger.info("No file to preserve before the automation state migration", file=backup.name)
                continue
            _keep_backup(backup, content)

    def _back_up(self) -> None:
        try:
            content: bytes = self._path.read_bytes()
        except OSError:
            return
        if not self._readable:
            try:
                _parse(content.decode("utf-8"))
            except ConfigError, UnicodeDecodeError:
                logger.warning("Kept an unreadable automation state out of the backup")
                return
        self._path.with_name(f"{self._path.name}{_BACKUP_SUFFIX}").write_bytes(content)


def _parse(text: str) -> WatchState:
    try:
        return _decode_state(json.loads(text))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as problem:
        raise _invalid_file() from problem


def _invalid_file() -> ConfigError:
    return ConfigError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=_INVALID_MESSAGE,
            suggestion=_INVALID_SUGGESTION,
        )
    )


def _migration_blocked() -> ConfigError:
    return ConfigError(
        context=ErrorContext(
            code=ErrorCode.IO_ERROR,
            message="The owner files could not be preserved before the automation state migration",
            suggestion="Free the config directory for writing and start the resident again",
        )
    )


def _subscriptions_invalid() -> ConfigError:
    return ConfigError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=_SUBSCRIPTIONS_INVALID_MESSAGE,
            suggestion=_SUBSCRIPTIONS_INVALID_SUGGESTION,
        )
    )


def _decode_legacy(content: bytes | None) -> tuple[Subscription, ...]:
    if content is None:
        return ()
    try:
        return decode_subscriptions(content.decode("utf-8"))
    except (ConfigError, UnicodeDecodeError) as problem:
        raise _subscriptions_invalid() from problem


def _keep_backup(backup: Path, content: bytes) -> None:
    try:
        present: bool = backup.exists()
    except OSError as problem:
        raise _migration_blocked() from problem
    if not present:
        _write_backup(backup, content)


def _write_backup(backup: Path, content: bytes) -> None:
    temporary: Path = backup.with_name(f"{backup.name}{_TEMPORARY_SUFFIX}")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(backup)
    except OSError as problem:
        raise _migration_blocked() from problem


def _encode_state(state: WatchState) -> dict[str, object]:
    return {
        "schema_version": WATCH_STATE_SCHEMA_VERSION,
        "policy": _encode_policy(state.policy),
        "reservations": [_encode_reservation(item) for item in state.reservations],
        "markers": [_encode_marker(item) for item in state.markers],
        "requests": [_encode_request(item) for item in state.requests],
        "acquisitions": [_encode_acquisition(item) for item in state.acquisitions],
        "products": [_encode_product(item) for item in state.products],
        "provider_locks": [_encode_provider_lock(item) for item in state.provider_locks],
        "command_receipts": [_encode_receipt(item) for item in state.command_receipts],
        "notified": [list(key) for key in sorted(state.notified)],
        "recipes": _encode_recipes(state.recipes),
        "ready_groups": [_encode_ready_group(item) for item in state.ready_groups],
        "pause_owned_transfers": list(state.pause_owned_transfers),
        "pending_deletions": [_encode_pending_deletion(item) for item in state.pending_deletions],
        "subscriptions": [_encode_subscription(item) for item in state.subscriptions],
        "removed_subscription": (
            None if state.removed_subscription is None else _encode_subscription(state.removed_subscription)
        ),
        "legacy_orders": [_encode_legacy_order(item) for item in state.legacy_orders],
    }


def _encode_recipes(recipes: RecipePreferences) -> dict[str, object]:
    return {
        "translate": {
            "text_result": recipes.translate.text_result.value,
            "translation_action": recipes.translate.translation_action.value,
        },
        "audiobook": {
            "translation_action": recipes.audiobook.translation_action.value,
            "timeline": recipes.audiobook.timeline.value,
        },
    }


def _encode_ready_group(group: ReadyGroup) -> dict[str, object]:
    return {
        "set_id": group.set_id,
        "group_id": group.group_id,
        "stem": group.stem,
        "source_directory": group.source_directory,
        "source_stem": group.source_stem,
        "target": group.target.value,
        "sources": list(group.sources),
        "products": list(group.products),
        "main_result": group.main_result,
        "pending_sources": list(group.pending_sources),
        "recipe": _encode_recipes(group.recipe),
    }


def _encode_pending_deletion(deletion: PendingDeletion) -> dict[str, object]:
    return {
        **(
            {
                "restore": {
                    "operation_id": deletion.restore.operation_id,
                    "completed": deletion.restore.completed,
                    "outcomes": [
                        {
                            "path": item.path,
                            "staging": item.staging,
                            "status": item.status,
                            "reason": item.reason,
                            "started": item.started,
                        }
                        for item in deletion.restore.outcomes
                    ],
                }
            }
            if deletion.restore is not None
            else {}
        ),
        "operation_id": deletion.operation_id,
        "set_id": deletion.set_id,
        "requested_at": deletion.requested_at,
        "files": _encode_fingerprint(deletion.files),
        "recycled": list(deletion.recycled),
        "identities": [list(identity) for identity in deletion.identities],
        "outcomes": [
            {"path": item.path, "status": item.status.value, "reason": item.reason, "receipt": item.receipt}
            for item in deletion.outcomes
        ],
        "instance_id": deletion.instance_id,
    }


def _encode_policy(policy: AutomationPolicy) -> dict[str, object]:
    return {
        "auto_enabled": policy.auto_enabled,
        "directory_exceptions": dict(policy.directory_exceptions),
        "release_delay_default_s": policy.release_delay_default_s,
        "recheck_interval_s": policy.recheck_interval_s,
        "search_window_s": policy.search_window_s,
        "transfer_stall_s": policy.transfer_stall_s,
        "external_retry_budget": policy.external_retry_budget,
        "retry_delays_s": list(policy.retry_delays_s),
    }


def _encode_reservation(reservation: Reservation) -> dict[str, object]:
    return {
        "group_id": reservation.group_id,
        "fingerprint": _encode_fingerprint(reservation.fingerprint),
        "client_id": reservation.client_id,
        "reserved_at": reservation.reserved_at,
    }


def _encode_marker(marker: ManualHandledMarker) -> dict[str, object]:
    return {
        "group_id": marker.group_id,
        "fingerprint": _encode_fingerprint(marker.fingerprint),
        "products": sorted(product.value for product in marker.products),
        "request_id": marker.request_id,
        "recorded_at": marker.recorded_at,
    }


def _encode_request(request: ProcessingRequest) -> dict[str, object]:
    return {
        "request_id": request.request_id,
        "generation": request.generation,
        "group_ids": list(request.group_ids),
        "fingerprints": {
            group_id: _encode_fingerprint(fingerprint) for group_id, fingerprint in request.fingerprints.items()
        },
        "origin": request.origin.value,
        "source_selection": request.source_selection.value,
        "rebuild": None if request.rebuild is None else sorted(product.value for product in request.rebuild.products),
        "settings": dict(request.settings),
        "state": request.state.value,
        "attempts": request.attempts,
        "accepted_at": request.accepted_at,
        "intents": [encode_intent(intent) for intent in request.intents],
        "automatic": request.automatic,
        "problem": request.problem,
        "recipe": _encode_recipes(request.recipe),
    }


def _encode_acquisition(confirmation: AcquisitionConfirmation) -> dict[str, object]:
    return {
        "operation_id": confirmation.operation_id,
        "info_hash": confirmation.info_hash,
        "directory": confirmation.directory,
        "required_files": list(confirmation.required_files),
        "state": confirmation.state.value,
        "origin": confirmation.origin.value,
        "subscription_id": confirmation.subscription_id,
        "episode": confirmation.episode,
        "updated_at": confirmation.updated_at,
        "requested_action": confirmation.requested_action,
        "action_id": confirmation.action_id,
        "action_pending": confirmation.action_pending,
        "action_sent": confirmation.action_sent,
        "problem": confirmation.problem,
        "complete_files": list(confirmation.complete_files),
        "file_layout": [[index, path, size] for index, path, size in confirmation.file_layout],
        "content_started": confirmation.content_started,
        "repeat_id": confirmation.repeat_id,
        "nyaa_release_id": confirmation.nyaa_release_id,
        "release_title": confirmation.release_title,
        "previous_operation_id": confirmation.previous_operation_id,
        "assignments": [_encode_assignment(item) for item in confirmation.assignments],
        "legacy_scope": (
            None
            if confirmation.legacy_scope is None
            else {"anilist_id": confirmation.legacy_scope.anilist_id, "number": confirmation.legacy_scope.number}
        ),
        "selection_revision": confirmation.selection_revision,
        "applied_revision": confirmation.applied_revision,
        "manifest": list(confirmation.manifest),
        "cleaned": confirmation.cleaned,
    }


def _encode_assignment(assignment: EpisodeAssignment) -> dict[str, object]:
    choice: EpisodeChoice = assignment.choice
    return {
        "admission_id": assignment.admission_id,
        "admitted_at": assignment.admitted_at,
        "source": assignment.source.value,
        "previous_admission_id": assignment.previous_admission_id,
        "anilist_id": choice.anilist_id,
        "number": choice.number,
        "reference": {
            "info_hash": choice.reference.info_hash,
            "file_index": choice.reference.file_index,
            "file_name": choice.reference.file_name,
            "release": choice.reference.release,
            "trackers": list(choice.reference.trackers),
        },
        "target": dict(choice.target),
        "verdict": choice.verdict.value,
        "reason": choice.reason,
        "deviation_confirmed": choice.deviation_confirmed,
        "file_map": assignment.file_map,
        "files": [[index, path, size] for index, path, size in assignment.files],
        "conflict": list(assignment.conflict),
        "replaced": assignment.replaced,
        "publication": None if assignment.publication is None else _encode_publication(assignment.publication),
        "group_id": assignment.group_id,
        "video_path": assignment.video_path,
        "subscription_id": assignment.subscription_id,
        "attempt": assignment.attempt,
        "verification": assignment.verification,
        "verified_stamp": None if assignment.verified_stamp is None else list(assignment.verified_stamp),
        "traits": None
        if choice.traits is None
        else {
            "polish": choice.traits.polish.name.casefold(),
            "resolution": int(choice.traits.resolution),
            "unusable": list(choice.traits.unusable),
        },
        "stopped": assignment.stopped,
    }


def _encode_publication(publication: EpisodePublication) -> dict[str, object]:
    return {
        "files": [
            {
                "index": item.index,
                "source": item.source,
                "name": item.name,
                "size": item.size,
                "digest": item.digest,
                "stamp": None if item.stamp is None else list(item.stamp),
            }
            for item in publication.files
        ],
        "handed_off": publication.handed_off,
        "problem": publication.problem,
    }


def _encode_product(confirmation: ProductConfirmation) -> dict[str, object]:
    return {
        "group_id": confirmation.group_id,
        "artifact_kind": confirmation.artifact_kind,
        "path": confirmation.path,
        "generation": confirmation.generation,
        "request_id": confirmation.request_id,
        "origin": confirmation.origin.value,
        "size": confirmation.size,
        "modified_ns": confirmation.modified_ns,
    }


def _encode_provider_lock(lock: ProviderLock) -> dict[str, object]:
    return {"provider": lock.provider, "until": lock.until, "reason": lock.reason}


def _encode_receipt(receipt: CommandReceipt) -> dict[str, object]:
    return {
        "command_id": receipt.command_id,
        "accepted_at": receipt.accepted_at,
        "outcome": dict(receipt.outcome),
        **({"pending": receipt.pending} if receipt.pending is not None else {}),
    }


def _encode_fingerprint(fingerprint: SourceFingerprint) -> list[list[object]]:
    return [[name, size, mtime_ns] for name, size, mtime_ns in fingerprint]


@dataclass(frozen=True, slots=True)
class _SchemaTwoFacts:
    """Sections schema 2 added, either read from the document or defaulted for a schema 1 one."""

    recipes: RecipePreferences = field(default_factory=RecipePreferences)
    ready_groups: tuple[ReadyGroup, ...] = ()
    pause_owned_transfers: tuple[str, ...] = ()
    pending_deletions: tuple[PendingDeletion, ...] = ()


def _decode_state(raw: object) -> WatchState:
    stored: dict[str, object] = dict(_strict_mapping(raw, "automation state"))
    schema_version: int = _schema_version(stored)
    added: _SchemaTwoFacts = _schema_two_facts(stored, schema_version)
    subscriptions: _SchemaFourFacts = _schema_four_facts(stored, schema_version)
    document: dict[str, object] = _strict_object(stored, _ROOT_KEYS, "automation state")
    return WatchState(
        schema_version=schema_version,
        recipes=added.recipes,
        ready_groups=added.ready_groups,
        pause_owned_transfers=added.pause_owned_transfers,
        pending_deletions=added.pending_deletions,
        subscriptions=subscriptions.subscriptions,
        removed_subscription=subscriptions.removed_subscription,
        legacy_orders=subscriptions.legacy_orders,
        policy=_decode_policy(document["policy"]),
        reservations=tuple(_decode_reservation(item) for item in _list(document["reservations"], "reservations")),
        markers=tuple(_decode_marker(item) for item in _list(document["markers"], "markers")),
        requests=tuple(_decode_request(item) for item in _list(document["requests"], "requests")),
        acquisitions=tuple(
            _decode_acquisition(item, schema_version) for item in _list(document["acquisitions"], "acquisitions")
        ),
        products=tuple(_decode_product(item) for item in _list(document["products"], "products")),
        provider_locks=tuple(
            _decode_provider_lock(item) for item in _list(document["provider_locks"], "provider_locks")
        ),
        command_receipts=tuple(
            _decode_receipt(item, schema_version) for item in _list(document["command_receipts"], "command_receipts")
        ),
        notified=frozenset(_decode_notification(item) for item in _list(document["notified"], "notified")),
    )


def _schema_version(document: Mapping[str, object]) -> int:
    version: object = document.get("schema_version")
    if type(version) is not int or version not in _SUPPORTED_SCHEMA_VERSIONS:
        msg = "Unsupported automation state schema version"
        raise ValueError(msg)
    return version


def _schema_two_facts(document: dict[str, object], schema_version: int) -> _SchemaTwoFacts:
    sections: dict[str, object] = {key: document.pop(key) for key in _SCHEMA_TWO_SECTIONS if key in document}
    if schema_version == _SCHEMA_ONE:
        if sections:
            msg = "A schema 1 automation state cannot carry the sections schema 2 added"
            raise ValueError(msg)
        return _SchemaTwoFacts()
    if frozenset(sections) != frozenset(_SCHEMA_TWO_SECTIONS):
        msg = "A schema 2 automation state is missing a section it must carry"
        raise ValueError(msg)
    return _SchemaTwoFacts(
        recipes=_decode_recipes(sections["recipes"]),
        ready_groups=tuple(_decode_ready_group(item) for item in _list(sections["ready_groups"], "ready groups")),
        pause_owned_transfers=_decode_texts(sections["pause_owned_transfers"], "transfers owned by a pause"),
        pending_deletions=tuple(
            _decode_pending_deletion(item) for item in _list(sections["pending_deletions"], "pending deletions")
        ),
    )


@dataclass(frozen=True, slots=True)
class _SchemaFourFacts:
    """Sections schema 4 added, either read from the document or empty for an older one."""

    subscriptions: tuple[SubscriptionRecord, ...] = ()
    removed_subscription: SubscriptionRecord | None = None
    legacy_orders: tuple[LegacyOrder, ...] = ()


def _schema_four_facts(document: dict[str, object], schema_version: int) -> _SchemaFourFacts:
    sections: dict[str, object] = {key: document.pop(key) for key in _SCHEMA_FOUR_SECTIONS if key in document}
    if schema_version < _SCHEMA_FOUR:
        if sections:
            msg = "An automation state older than schema 4 cannot carry the sections schema 4 added"
            raise ValueError(msg)
        return _SchemaFourFacts()
    if frozenset(sections) != frozenset(_SCHEMA_FOUR_SECTIONS):
        msg = "A schema 4 automation state is missing a section it must carry"
        raise ValueError(msg)
    removed: object = sections["removed_subscription"]
    return _SchemaFourFacts(
        subscriptions=tuple(
            _decode_subscription(item, schema_version) for item in _list(sections["subscriptions"], "subscriptions")
        ),
        removed_subscription=None if removed is None else _decode_subscription(removed, schema_version),
        legacy_orders=tuple(_decode_legacy_order(item) for item in _list(sections["legacy_orders"], "legacy orders")),
    )


def _encode_subscription(record: SubscriptionRecord) -> dict[str, object]:
    check: SubscriptionCheck | None = record.last_check
    return {
        "subscription_id": record.subscription_id,
        "anilist_id": record.anilist_id,
        "kitsu_id": record.kitsu_id,
        "mapping": None if record.mapping is None else _encode_mapping(record.mapping),
        "title": record.title,
        "subscribed_at": record.subscribed_at,
        "cut": record.cut,
        "paused": record.paused,
        "pause_reason": None if record.pause_reason is None else record.pause_reason.value,
        "migrated_at": record.migrated_at,
        "review_pending": record.review_pending,
        "merged_from": list(record.merged_from),
        "problem": None if record.problem is None else record.problem.value,
        "catalog_status": record.catalog_status,
        "episode_count": record.episode_count,
        "refreshed_at": record.refreshed_at,
        "checked_at": record.checked_at,
        "last_check": None
        if check is None
        else {
            "checked_at": check.checked_at,
            "number": check.number,
            "matching": check.matching,
            "uncertain": check.uncertain,
            "mismatched": check.mismatched,
            "outcome": check.outcome,
        },
        "targets": [
            {
                "number": item.number,
                "due_at": item.due_at,
                "state": item.state.value,
                "attempts": item.attempts,
                "tried": list(item.tried),
                "admission_id": item.admission_id,
                "reason": item.reason,
                "notified_late": item.notified_late,
                "check_skipped": item.check_skipped,
                "started": item.started,
                "threshold": None if item.threshold is None else int(item.threshold),
                "failures": [
                    {"hash": failure.info_hash, "decisive": failure.decisive, "transient": failure.transient}
                    for failure in item.failures
                ],
                "polish": None
                if item.polish is None
                else {"state": item.polish.state.value, "observed_at": item.polish.observed_at},
                "sources_down_since": item.sources_down_since,
                "polish_skip": None
                if item.polish_skip is None
                else {"due": item.polish_skip.due, "at": item.polish_skip.at, "settled": item.polish_skip.settled},
            }
            for item in record.targets
        ],
        "migrated_from": record.migrated_from,
        "tsukihime_id": record.tsukihime_id,
        "mapping_tvdb_season": record.mapping_tvdb_season,
    }


def _encode_mapping(mapping: AniZipMapping) -> dict[str, object]:
    return {
        "kitsu_id": mapping.kitsu_id,
        "catalog_type": mapping.catalog_type,
        "episode_count": mapping.episode_count,
        "episodes": [
            {
                "number": item.number,
                "title": item.title,
                "airs_at": None if item.airs_at is None else item.airs_at.isoformat(),
                "season": item.season,
                "episode": item.episode,
                "absolute": item.absolute,
                "aired": item.aired,
                "airs_at_fallback": item.airs_at_fallback,
            }
            for item in mapping.episodes
        ],
        "specials": [
            {
                "key": item.key,
                "title": item.title,
                "airs_on": None if item.airs_on is None else item.airs_on.isoformat(),
            }
            for item in mapping.specials
        ],
        "raw_episodes": {key: dict(value) for key, value in mapping.raw_episodes.items()},
    }


def _encode_legacy_order(order: LegacyOrder) -> dict[str, object]:
    return {
        "anilist_id": order.anilist_id,
        "number": order.number,
        "reference": order.reference,
        "operation_id": order.operation_id,
        "complete": order.complete,
    }


def _decode_subscription(raw: object, schema_version: int) -> SubscriptionRecord:
    five: bool = schema_version > _SCHEMA_FOUR
    document: dict[str, object] = _strict_object(
        raw, _SUBSCRIPTION_KEYS | _SUBSCRIPTION_KEYS_FIVE if five else _SUBSCRIPTION_KEYS, "subscription"
    )
    reason: str | None = _optional_text(document, "pause_reason")
    problem: str | None = _optional_text(document, "problem")
    mapping: object = document["mapping"]
    check: object = document["last_check"]
    return SubscriptionRecord(
        subscription_id=_text(document, "subscription_id"),
        anilist_id=_optional_whole(document, "anilist_id"),
        kitsu_id=_optional_whole(document, "kitsu_id"),
        mapping=None if mapping is None else _decode_mapping(mapping),
        title=_text(document, "title"),
        subscribed_at=_text(document, "subscribed_at"),
        cut=_optional_whole(document, "cut"),
        paused=_flag(document, "paused"),
        pause_reason=None if reason is None else PauseReason(reason),
        migrated_at=_optional_text(document, "migrated_at"),
        review_pending=_flag(document, "review_pending"),
        merged_from=_decode_texts(document["merged_from"], "merged subscriptions"),
        problem=None if problem is None else SubscriptionProblem(problem),
        catalog_status=_optional_text(document, "catalog_status"),
        episode_count=_optional_whole(document, "episode_count"),
        refreshed_at=_optional_text(document, "refreshed_at"),
        checked_at=_optional_text(document, "checked_at"),
        last_check=None if check is None else _decode_check(check),
        targets=tuple(_decode_target(item, five=five) for item in _list(document["targets"], "subscription targets")),
        migrated_from=_optional_text(document, "migrated_from"),
        tsukihime_id=_optional_whole(document, "tsukihime_id") if five else None,
        mapping_tvdb_season=_optional_whole(document, "mapping_tvdb_season") if five else None,
    )


def _decode_check(raw: object) -> SubscriptionCheck:
    document: dict[str, object] = _strict_object(raw, _CHECK_KEYS, "subscription check")
    return SubscriptionCheck(
        checked_at=_text(document, "checked_at"),
        number=_optional_whole(document, "number"),
        matching=_whole(document, "matching"),
        uncertain=_whole(document, "uncertain"),
        mismatched=_whole(document, "mismatched"),
        outcome=_text(document, "outcome"),
    )


def _decode_target(raw: object, *, five: bool) -> SubscriptionTarget:
    document: dict[str, object] = _strict_object(
        raw, _TARGET_KEYS | _TARGET_KEYS_FIVE if five else _TARGET_KEYS, "subscription target"
    )
    attempts: int = _whole(document, "attempts")
    target: SubscriptionTarget = SubscriptionTarget(
        number=_whole(document, "number"),
        due_at=_optional_text(document, "due_at"),
        state=TargetState(_text(document, "state")),
        attempts=attempts,
        tried=_decode_texts(document["tried"], "tried release files"),
        admission_id=_optional_text(document, "admission_id"),
        reason=_optional_text(document, "reason"),
        notified_late=_flag(document, "notified_late"),
        check_skipped=_flag(document, "check_skipped"),
        started=attempts,
    )
    return _schema_five_target(target, document) if five else target


def _schema_five_target(target: SubscriptionTarget, document: dict[str, object]) -> SubscriptionTarget:
    threshold: int | None = _optional_whole(document, "threshold")
    polish: object = document["polish"]
    skip: object = document["polish_skip"]
    return replace(
        target,
        started=_whole(document, "started"),
        threshold=None if threshold is None else ResolutionClass(threshold),
        failures=tuple(_decode_failure(item) for item in _list(document["failures"], "release failures")),
        polish=None if polish is None else _decode_polish(polish),
        sources_down_since=_optional_text(document, "sources_down_since"),
        polish_skip=None if skip is None else _decode_polish_skip(skip),
    )


def _decode_failure(raw: object) -> ReleaseFailure:
    document: dict[str, object] = _strict_object(raw, _FAILURE_KEYS, "release failure")
    return ReleaseFailure(
        info_hash=_text(document, "hash"),
        decisive=_flag(document, "decisive"),
        transient=_whole(document, "transient"),
    )


def _decode_polish(raw: object) -> PolishObservation:
    document: dict[str, object] = _strict_object(raw, _POLISH_KEYS, "Polish observation")
    return PolishObservation(PolishState(_text(document, "state")), _text(document, "observed_at"))


def _decode_polish_skip(raw: object) -> PolishSkip:
    document: dict[str, object] = _strict_object(raw, _POLISH_SKIP_KEYS, "Polish skip")
    return PolishSkip(_text(document, "due"), _text(document, "at"), settled=_flag(document, "settled"))


def _decode_mapping(raw: object) -> AniZipMapping:
    document: dict[str, object] = _strict_object(raw, _MAPPING_KEYS, "episode mapping")
    episodes: list[ListedEpisode] = []
    for entry in _list(document["episodes"], "mapped episodes"):
        item: dict[str, object] = _strict_object(entry, _LISTED_EPISODE_KEYS, "mapped episode")
        airs_at: str | None = _optional_text(item, "airs_at")
        episodes.append(
            ListedEpisode(
                number=_whole(item, "number"),
                title=_optional_text(item, "title"),
                airs_at=None if airs_at is None else datetime.fromisoformat(airs_at),
                season=_optional_whole(item, "season"),
                episode=_optional_whole(item, "episode"),
                absolute=_optional_whole(item, "absolute"),
                aired=_flag(item, "aired"),
                airs_at_fallback=_flag(item, "airs_at_fallback"),
            )
        )
    specials: list[ListedSpecial] = []
    for entry in _list(document["specials"], "mapped extras"):
        item = _strict_object(entry, _LISTED_SPECIAL_KEYS, "mapped extra")
        airs_on: str | None = _optional_text(item, "airs_on")
        specials.append(
            ListedSpecial(
                key=_text(item, "key"),
                title=_optional_text(item, "title"),
                airs_on=None if airs_on is None else date.fromisoformat(airs_on),
            )
        )
    raw_episodes: dict[str, object] = _strict_mapping(document["raw_episodes"], "raw mapped episodes")
    return AniZipMapping(
        kitsu_id=_optional_whole(document, "kitsu_id"),
        catalog_type=_optional_text(document, "catalog_type"),
        episode_count=_optional_whole(document, "episode_count"),
        episodes=tuple(episodes),
        specials=tuple(specials),
        max_age_s=None,
        raw_episodes={key: _strict_mapping(value, "raw mapped episode") for key, value in raw_episodes.items()},
    )


def _decode_legacy_order(raw: object) -> LegacyOrder:
    document: dict[str, object] = _strict_object(raw, _LEGACY_ORDER_KEYS, "legacy order")
    return LegacyOrder(
        anilist_id=_whole(document, "anilist_id"),
        number=_optional_whole(document, "number"),
        reference=_text(document, "reference"),
        operation_id=_optional_text(document, "operation_id"),
        complete=_flag(document, "complete"),
    )


def _decode_recipes(raw: object) -> RecipePreferences:
    document: dict[str, object] = _strict_object(raw, _RECIPES_KEYS, "recipe preferences")
    translate: dict[str, object] = _strict_object(document["translate"], _TRANSLATE_RECIPE_KEYS, "translate recipe")
    audiobook: dict[str, object] = _strict_object(document["audiobook"], _AUDIOBOOK_RECIPE_KEYS, "audiobook recipe")
    return RecipePreferences(
        translate=TranslateRecipe(
            text_result=TextResultFormat(_text(translate, "text_result")),
            translation_action=TranslationAction(_text(translate, "translation_action")),
        ),
        audiobook=AudiobookRecipe(
            translation_action=TranslationAction(_text(audiobook, "translation_action")),
            timeline=NarrationTimeline(_text(audiobook, "timeline")),
        ),
    )


def _decode_ready_group(raw: object) -> ReadyGroup:
    stored: dict[str, object] = dict(_strict_mapping(raw, "completed set"))
    single: object = stored.pop("pending_source", None)
    pending: object = stored.pop("pending_sources", None)
    document: dict[str, object] = _strict_object(stored, _READY_GROUP_KEYS, "completed set")
    return ReadyGroup(
        set_id=_text(document, "set_id"),
        group_id=_text(document, "group_id"),
        stem=_text(document, "stem"),
        source_directory=_text(document, "source_directory"),
        source_stem=_text(document, "source_stem"),
        target=WorkflowTarget(_text(document, "target")),
        sources=_decode_texts(document["sources"], "sources of a completed set"),
        products=_decode_texts(document["products"], "products of a completed set"),
        main_result=_optional_text(document, "main_result"),
        pending_sources=_pending_sources(single, pending),
        recipe=_decode_recipes(document["recipe"]),
    )


def _pending_sources(single: object, pending: object) -> tuple[str, ...]:
    if pending is not None:
        return _decode_texts(pending, "pending sources of a completed set")
    return () if single is None else (_as_text(single, "pending source of a completed set"),)


def _decode_pending_deletion(raw: object) -> PendingDeletion:
    document: dict[str, object] = dict(_strict_mapping(raw, "pending deletion"))
    restore: DeletionRestore | None = _decode_restore(document.pop("restore")) if "restore" in document else None
    identities: FileObjectIdentities = _decode_object_identities(document.pop("identities", []))
    outcomes: tuple[DeletionOutcome, ...] = tuple(
        _decode_deletion_outcome(item) for item in _list(document.pop("outcomes", []), "deletion outcomes")
    )
    instance_id: str | None = _optional_text({"instance_id": document.pop("instance_id", None)}, "instance_id")
    _strict_object(document, _PENDING_DELETION_KEYS, "pending deletion")
    return PendingDeletion(
        operation_id=_text(document, "operation_id"),
        set_id=_text(document, "set_id"),
        requested_at=_text(document, "requested_at"),
        files=_decode_fingerprint(document["files"]),
        recycled=_decode_texts(document["recycled"], "recycled files of a pending deletion"),
        identities=identities,
        outcomes=outcomes,
        instance_id=instance_id,
        restore=restore,
    )


def _decode_restore(raw: object) -> DeletionRestore:
    document: dict[str, object] = _strict_object(
        raw, frozenset({"operation_id", "completed", "outcomes"}), "deletion restore"
    )
    outcomes: list[RestoreOutcome] = []
    for entry in _list(document["outcomes"], "restore outcomes"):
        item: dict[str, object] = _strict_object(
            entry, frozenset({"path", "staging", "status", "reason", "started"}), "restore outcome"
        )
        outcomes.append(
            RestoreOutcome(
                _text(item, "path"),
                _text(item, "staging"),
                _text(item, "status"),
                _text(item, "reason"),
                _flag(item, "started"),
            )
        )
    return DeletionRestore(_text(document, "operation_id"), tuple(outcomes), _flag(document, "completed"))


def _decode_object_identities(raw: object) -> FileObjectIdentities:
    entries: list[tuple[str, int, int]] = []
    for item in _list(raw, "file object identities"):
        name, device, inode = _list(item, "file object identity")
        entries.append((_as_text(name, "file path"), _as_whole(device, "file device"), _as_whole(inode, "file inode")))
    return tuple(entries)


def _decode_deletion_outcome(raw: object) -> DeletionOutcome:
    document: dict[str, object] = _strict_object(
        raw, frozenset({"path", "status", "reason", "receipt"}), "deletion outcome"
    )
    return DeletionOutcome(
        _text(document, "path"),
        DeletionStatus(_text(document, "status")),
        _text(document, "reason"),
        _optional_text(document, "receipt"),
    )


def _decode_policy(raw: object) -> AutomationPolicy:
    document: dict[str, object] = _strict_object(raw, _POLICY_KEYS, "automation policy")
    exceptions: dict[str, object] = _strict_mapping(document["directory_exceptions"], "directory exceptions")
    return AutomationPolicy(
        auto_enabled=_flag(document, "auto_enabled"),
        directory_exceptions={key: _flag(exceptions, key) for key in exceptions},
        release_delay_default_s=_whole(document, "release_delay_default_s"),
        recheck_interval_s=_whole(document, "recheck_interval_s"),
        search_window_s=_whole(document, "search_window_s"),
        transfer_stall_s=_whole(document, "transfer_stall_s"),
        external_retry_budget=_whole(document, "external_retry_budget"),
        retry_delays_s=_decode_whole_numbers(document["retry_delays_s"], "retry delays"),
    )


def _decode_reservation(raw: object) -> Reservation:
    document: dict[str, object] = _strict_object(raw, _RESERVATION_KEYS, "reservation")
    return Reservation(
        group_id=_text(document, "group_id"),
        fingerprint=_decode_fingerprint(document["fingerprint"]),
        client_id=_text(document, "client_id"),
        reserved_at=_text(document, "reserved_at"),
    )


def _decode_marker(raw: object) -> ManualHandledMarker:
    document: dict[str, object] = _strict_object(raw, _MARKER_KEYS, "manual decision")
    return ManualHandledMarker(
        group_id=_text(document, "group_id"),
        fingerprint=_decode_fingerprint(document["fingerprint"]),
        products=_decode_products(document["products"]),
        request_id=_text(document, "request_id"),
        recorded_at=_text(document, "recorded_at"),
    )


def _decode_request(raw: object) -> ProcessingRequest:
    document: dict[str, object] = _strict_mapping(raw, "processing request")
    problem: str | None = _optional_text({"problem": document.pop("problem", None)}, "problem")
    automatic: bool = _flag({"automatic": document.pop("automatic", False)}, "automatic")
    intents: tuple[GroupIntent, ...] = tuple(
        decode_intent(GroupIntent, item) for item in _list(document.pop("intents", []), "group intents")
    )
    stored_recipe: object = document.pop("recipe", None)
    recipe: RecipePreferences = RecipePreferences() if stored_recipe is None else _decode_recipes(stored_recipe)
    document = _strict_object(document, _REQUEST_KEYS, "processing request")
    fingerprints: dict[str, object] = _strict_mapping(document["fingerprints"], "request fingerprints")
    rebuild: object = document["rebuild"]
    return ProcessingRequest(
        request_id=_text(document, "request_id"),
        generation=_whole(document, "generation"),
        group_ids=_decode_texts(document["group_ids"], "group identifiers"),
        fingerprints={group_id: _decode_fingerprint(value) for group_id, value in fingerprints.items()},
        origin=RequestOrigin(_text(document, "origin")),
        source_selection=SourceSelection(_text(document, "source_selection")),
        rebuild=None if rebuild is None else RebuildRequest(_decode_products(rebuild)),
        settings=_decode_settings(document["settings"]),
        state=RequestState(_text(document, "state")),
        attempts=_whole(document, "attempts"),
        accepted_at=_text(document, "accepted_at"),
        intents=intents,
        automatic=automatic,
        problem=problem,
        recipe=recipe,
    )


def _decode_acquisition(raw: object, schema_version: int) -> AcquisitionConfirmation:
    stored: dict[str, object] = dict(_strict_mapping(raw, "acquisition confirmation"))
    stated: bool = "complete_files" in stored
    complete: object = stored.pop("complete_files", [])
    layout: object = stored.pop("file_layout", [])
    started: bool = _flag({"content_started": stored.pop("content_started", False)}, "content_started")
    sent: bool = _flag({"action_sent": stored.pop("action_sent", False)}, "action_sent")
    repeat: str | None = _optional_text({"repeat_id": stored.pop("repeat_id", None)}, "repeat_id")
    release_id: object = stored.pop("nyaa_release_id", None)
    if release_id is not None and (type(release_id) is not int or release_id <= 0):
        msg = "Invalid retained Nyaa release identifier"
        raise ValueError(msg)
    title: str | None = _optional_text({"release_title": stored.pop("release_title", None)}, "release_title")
    previous: str | None = _optional_text(
        {"previous_operation_id": stored.pop("previous_operation_id", None)}, "previous_operation_id"
    )
    assignments, scope, revisions, staging = _schema_three_identity(stored, schema_version)
    document: dict[str, object] = _strict_object(
        {
            "requested_action": None,
            "action_id": None,
            "action_pending": False,
            "problem": None,
            **stored,
        },
        _ACQUISITION_KEYS,
        "acquisition confirmation",
    )
    state: AcquisitionState = AcquisitionState(_text(document, "state"))
    required_files: tuple[str, ...] = _decode_texts(document["required_files"], "required files")
    return AcquisitionConfirmation(
        operation_id=_text(document, "operation_id"),
        info_hash=_text(document, "info_hash"),
        directory=_text(document, "directory"),
        required_files=required_files,
        state=state,
        origin=RequestOrigin(_text(document, "origin")),
        subscription_id=_optional_text(document, "subscription_id"),
        episode=_optional_text(document, "episode"),
        updated_at=_text(document, "updated_at"),
        requested_action=_optional_text(document, "requested_action"),
        action_id=_optional_text(document, "action_id"),
        action_pending=_flag(document, "action_pending"),
        problem=_optional_text(document, "problem"),
        complete_files=_complete_files(
            complete,
            stated=stated,
            schema_version=schema_version,
            state=state,
            required_files=required_files,
        ),
        file_layout=_decode_layout(layout),
        content_started=started,
        repeat_id=repeat,
        nyaa_release_id=release_id,
        release_title=title,
        previous_operation_id=previous,
        action_sent=sent,
        assignments=assignments,
        legacy_scope=scope,
        selection_revision=revisions[0],
        applied_revision=revisions[1],
        manifest=staging[0],
        cleaned=staging[1],
    )


def _schema_three_identity(
    document: dict[str, object], schema_version: int
) -> tuple[tuple[EpisodeAssignment, ...], LegacyScope | None, tuple[int, int], tuple[tuple[str, ...], bool]]:
    fields: dict[str, object] = {key: document.pop(key) for key in _SCHEMA_THREE_ACQUISITION_FIELDS if key in document}
    if schema_version < _SCHEMA_THREE:
        if fields:
            msg = "An acquisition confirmation older than schema 3 cannot carry episode identity"
            raise ValueError(msg)
        return (), None, (0, 0), ((), False)
    if not fields.keys() & _PUBLICATION_DEFAULTS.keys():
        fields.update(_PUBLICATION_DEFAULTS)
    if frozenset(fields) != frozenset(_SCHEMA_THREE_ACQUISITION_FIELDS):
        msg = "A schema 3 acquisition confirmation must state its episode identity"
        raise ValueError(msg)
    raw_scope: object = fields["legacy_scope"]
    scope: LegacyScope | None = None
    if raw_scope is not None:
        stored: dict[str, object] = _strict_object(raw_scope, _LEGACY_SCOPE_KEYS, "legacy scope")
        number: object = stored["number"]
        scope = LegacyScope(
            _whole(stored, "anilist_id"), None if number is None else _as_whole(number, "legacy scope episode")
        )
    revisions: tuple[int, int] = (
        _as_whole(fields["selection_revision"], "selection revision"),
        _as_whole(fields["applied_revision"], "confirmed selection revision"),
    )
    return (
        tuple(
            _decode_assignment(item, five=schema_version > _SCHEMA_FOUR)
            for item in _list(fields["assignments"], "episode assignments")
        ),
        scope,
        revisions,
        (_decode_texts(fields["manifest"], "staging manifest"), _flag(fields, "cleaned")),
    )


def _decode_assignment(raw: object, *, five: bool) -> EpisodeAssignment:
    stored: dict[str, object] = _strict_mapping(raw, "episode assignment")
    document: dict[str, object] = _strict_object(
        {**dict.fromkeys(_OPTIONAL_ASSIGNMENT_KEYS), **stored},
        _ASSIGNMENT_KEYS | _ASSIGNMENT_KEYS_FIVE if five else _ASSIGNMENT_KEYS,
        "episode assignment",
    )
    reference: dict[str, object] = _strict_object(document["reference"], _REFERENCE_KEYS, "Torrentio reference")
    index: object = reference["file_index"]
    attempt: object = document["attempt"]
    stamp: object = document["verified_stamp"]
    traits: object = document.get("traits")
    return EpisodeAssignment(
        stopped=_optional_text(document, "stopped") if five else None,
        subscription_id=_optional_text(document, "subscription_id"),
        attempt=None if attempt is None else _as_whole(attempt, "subscription attempt"),
        verification=_optional_text(document, "verification"),
        verified_stamp=None if stamp is None else _decode_stamp(stamp),
        admission_id=_text(document, "admission_id"),
        admitted_at=_text(document, "admitted_at"),
        source=AdmissionSource(_text(document, "source")),
        previous_admission_id=_optional_text(document, "previous_admission_id"),
        file_map=_optional_text(document, "file_map"),
        files=_decode_layout(document["files"]),
        conflict=_decode_texts(document["conflict"], "overridden legacy conflict"),
        replaced=_flag(document, "replaced"),
        publication=None if document["publication"] is None else _decode_publication(document["publication"]),
        group_id=_optional_text(document, "group_id"),
        video_path=_optional_text(document, "video_path"),
        choice=EpisodeChoice(
            anilist_id=_whole(document, "anilist_id"),
            number=_whole(document, "number"),
            reference=TorrentioReference(
                _text(reference, "info_hash"),
                None if index is None else _as_whole(index, "Torrentio file index"),
                _optional_text(reference, "file_name"),
                _as_text(reference["release"], "Torrentio release"),
                _decode_texts(reference["trackers"], "Torrentio trackers"),
            ),
            target=_strict_mapping(document["target"], "H1 target"),
            verdict=IdentityVerdict(_text(document, "verdict")),
            reason=_text(document, "reason"),
            deviation_confirmed=_flag(document, "deviation_confirmed"),
            traits=None if traits is None else _decode_traits(traits),
        ),
    )


def _decode_traits(raw: object) -> ChoiceTraits:
    document: dict[str, object] = _strict_object(raw, _TRAITS_KEYS, "choice traits")
    return ChoiceTraits(
        polish={item.name.casefold(): item for item in PolishClass}[_text(document, "polish")],
        resolution=ResolutionClass(_whole(document, "resolution")),
        unusable=_decode_texts(document["unusable"], "unusable release facts"),
    )


def _decode_publication(raw: object) -> EpisodePublication:
    document: dict[str, object] = _strict_object(raw, _PUBLICATION_KEYS, "episode publication")
    files: list[PublishedFile] = []
    for item in _list(document["files"], "published episode files"):
        stored: dict[str, object] = _strict_object(item, _PUBLISHED_FILE_KEYS, "published episode file")
        stamp: object = stored["stamp"]
        files.append(
            PublishedFile(
                index=_whole(stored, "index"),
                source=_text(stored, "source"),
                name=_text(stored, "name"),
                size=_whole(stored, "size"),
                digest=_optional_text(stored, "digest"),
                stamp=None if stamp is None else _decode_stamp(stamp),
            )
        )
    return EpisodePublication(
        files=tuple(files), handed_off=_flag(document, "handed_off"), problem=_optional_text(document, "problem")
    )


def _decode_stamp(raw: object) -> FileStamp:
    values: tuple[int, ...] = _decode_whole_numbers(raw, "published file stamp")
    if len(values) != _STAMP_FIELDS:
        msg = "A published file stamp carries a size, a modification time, a device and an inode"
        raise TypeError(msg)
    return values[0], values[1], values[2], values[3]


def _decode_layout(raw: object) -> tuple[FileReservation, ...]:
    entries: list[FileReservation] = []
    for item in _list(raw, "reserved files"):
        fields: list[object] = _list(item, "reserved file")
        if len(fields) != _RESERVATION_FIELDS:
            msg = "A reserved file carries a client index, a flat path and a size"
            raise TypeError(msg)
        index, path, size = fields
        entries.append(
            (
                _as_whole(index, "reserved file index"),
                _as_text(path, "reserved file path"),
                _as_whole(size, "reserved file size"),
            )
        )
    return tuple(entries)


def _complete_files(
    raw: object,
    *,
    stated: bool,
    schema_version: int,
    state: AcquisitionState,
    required_files: tuple[str, ...],
) -> tuple[str, ...]:
    if schema_version != _SCHEMA_ONE:
        if not stated:
            msg = "A schema 2 acquisition confirmation must state which required files are complete"
            raise ValueError(msg)
        return _decode_texts(raw, "complete files")
    if stated:
        msg = "A schema 1 acquisition confirmation cannot state which required files are complete"
        raise ValueError(msg)
    return required_files if state is AcquisitionState.COMPLETE else ()


def _decode_product(raw: object) -> ProductConfirmation:
    stored: dict[str, object] = dict(_strict_mapping(raw, "product confirmation"))
    size: int = _as_whole(stored.pop("size", -1), "product size")
    modified_ns: int = _as_whole(stored.pop("modified_ns", -1), "product modification time")
    document: dict[str, object] = _strict_object(stored, _PRODUCT_KEYS, "product confirmation")
    return ProductConfirmation(
        group_id=_text(document, "group_id"),
        artifact_kind=_text(document, "artifact_kind"),
        path=_text(document, "path"),
        generation=_whole(document, "generation"),
        request_id=_text(document, "request_id"),
        origin=RequestOrigin(_text(document, "origin")),
        size=size,
        modified_ns=modified_ns,
    )


def _decode_provider_lock(raw: object) -> ProviderLock:
    document: dict[str, object] = _strict_object(raw, _PROVIDER_LOCK_KEYS, "provider lock")
    return ProviderLock(
        provider=_text(document, "provider"),
        until=_text(document, "until"),
        reason=_text(document, "reason"),
    )


def _decode_receipt(raw: object, schema_version: int) -> CommandReceipt:
    document: dict[str, object] = dict(_strict_mapping(raw, "command receipt"))
    pending: object = document.pop("pending", None)
    document = _strict_object(document, _RECEIPT_KEYS, "command receipt")
    if pending is not None and not isinstance(pending, str):
        msg = "A pending command kind must be text"
        raise TypeError(msg)
    if schema_version >= _SCHEMA_FOUR and pending not in {None, "cancel"}:
        msg = "A schema 4 command receipt can only wait for a cancellation"
        raise ValueError(msg)
    return CommandReceipt(
        command_id=_text(document, "command_id"),
        accepted_at=_text(document, "accepted_at"),
        outcome=_decode_outcome(document["outcome"]),
        pending=pending,
    )


def _decode_fingerprint(raw: object) -> SourceFingerprint:
    entries: list[tuple[str, int, int]] = []
    for item in _list(raw, "source fingerprint"):
        fields: list[object] = _list(item, "source fingerprint entry")
        if len(fields) != _FINGERPRINT_FIELDS:
            msg = "A source fingerprint entry carries a name, a size and a modification time"
            raise TypeError(msg)
        name, size, mtime_ns = fields
        entries.append(
            (_as_text(name, "source name"), _as_whole(size, "source size"), _as_whole(mtime_ns, "source time"))
        )
    return tuple(entries)


def _decode_notification(raw: object) -> NotificationKey:
    fields: list[object] = _list(raw, "notification key")
    if len(fields) != _NOTIFICATION_FIELDS:
        msg = "A notification key carries a subject, a generation and a kind"
        raise TypeError(msg)
    subject, generation, kind = fields
    return (
        _as_text(subject, "notification subject"),
        _as_text(generation, "notification generation"),
        _as_text(kind, "notification kind"),
    )


def _decode_products(raw: object) -> frozenset[ProductKind]:
    return frozenset(ProductKind(value) for value in _decode_texts(raw, "products"))


def _decode_texts(raw: object, label: str) -> tuple[str, ...]:
    return tuple(_as_text(value, label) for value in _list(raw, label))


def _decode_whole_numbers(raw: object, label: str) -> tuple[int, ...]:
    return tuple(_as_whole(value, label) for value in _list(raw, label))


def _decode_settings(raw: object) -> SettingsSnapshot:
    document: dict[str, object] = _strict_mapping(raw, "request settings")
    return {key: _setting_value(value) for key, value in document.items()}


def _setting_value(value: object) -> SettingValue:
    if isinstance(value, list):
        return tuple(_setting_value(item) for item in value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    msg = "A request setting must be a scalar or an ordered collection"
    raise TypeError(msg)


def _decode_outcome(raw: object) -> CommandOutcome:
    document: dict[str, object] = _strict_mapping(raw, "command outcome")
    outcome: dict[str, str | int | bool | None] = {}
    for key, value in document.items():
        if value is not None and not isinstance(value, str | int | bool):
            msg = "A command outcome value must be text, a whole number, a flag or null"
            raise TypeError(msg)
        outcome[key] = value
    return outcome


def _strict_object(raw: object, expected_keys: frozenset[str], label: str) -> dict[str, object]:
    document: dict[str, object] = _strict_mapping(raw, label)
    if frozenset(document) != expected_keys:
        msg = f"Serialized {label} has missing or unknown fields"
        raise ValueError(msg)
    return document


def _strict_mapping(raw: object, label: str) -> dict[str, object]:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        msg = f"Serialized {label} must be an object with text keys"
        raise TypeError(msg)
    document: dict[str, object] = raw
    return document


def _list(raw: object, label: str) -> list[object]:
    if not isinstance(raw, list):
        msg = f"Serialized {label} must be a list"
        raise TypeError(msg)
    values: list[object] = raw
    return values


def _text(document: Mapping[str, object], key: str) -> str:
    return _as_text(document[key], key)


def _optional_text(document: Mapping[str, object], key: str) -> str | None:
    value: object = document[key]
    return None if value is None else _as_text(value, key)


def _whole(document: Mapping[str, object], key: str) -> int:
    return _as_whole(document[key], key)


def _optional_whole(document: Mapping[str, object], key: str) -> int | None:
    value: object = document[key]
    return None if value is None else _as_whole(value, key)


def _flag(document: Mapping[str, object], key: str) -> bool:
    value: object = document[key]
    if not isinstance(value, bool):
        msg = f"Automation state field {key!r} must be a flag"
        raise TypeError(msg)
    return value


def _as_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        msg = f"Automation state field {label!r} must be text"
        raise TypeError(msg)
    return value


def _as_whole(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"Automation state field {label!r} must be a whole number"
        raise TypeError(msg)
    return value
