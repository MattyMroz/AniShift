"""Versioned, atomic persistence of the automation state under the watch directory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    CommandReceipt,
    ManualHandledMarker,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    RequestState,
    Reservation,
    SourceSelection,
    WatchState,
)
from anishift.application.control_payloads import decode_intent, encode_intent
from anishift.application.intents import GroupIntent, ProductKind, RebuildRequest, RequestOrigin
from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.paths import config_path
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from anishift.application.control import (
        CommandOutcome,
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

_STATE_DIR_NAME: Final[str] = "watch"
"""Directory under the panel configuration holding every watch state file."""

_BACKUP_SUFFIX: Final[str] = ".bak"
"""Ending of the copy kept from the last state that could be read back."""

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
"""Only root keys accepted from a persisted automation state."""

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
"""Keys a serialized acquisition confirmation must carry."""

_PRODUCT_KEYS: Final[frozenset[str]] = frozenset(
    {"group_id", "artifact_kind", "path", "generation", "request_id", "origin"}
)
"""Keys a serialized product confirmation must carry."""

_PROVIDER_LOCK_KEYS: Final[frozenset[str]] = frozenset({"provider", "until", "reason"})
"""Keys a serialized provider lock must carry."""

_RECEIPT_KEYS: Final[frozenset[str]] = frozenset({"command_id", "accepted_at", "outcome"})
"""Keys a serialized command receipt must carry."""

_FINGERPRINT_FIELDS: Final[int] = 3
"""Name, size and modification time of one source file."""

_NOTIFICATION_FIELDS: Final[int] = 3
"""Group or episode, generation and kind of one notification."""

_INVALID_MESSAGE: Final[str] = "Automation state file is invalid"
"""Sentence shown when the stored automation state cannot be trusted."""

_INVALID_SUGGESTION: Final[str] = "Restore config/watch/state.json.bak or delete config/watch/state.json"
"""Only recovery a user can perform on a broken automation state."""


def watch_state_path() -> Path:
    """Return the absolute path of the automation state under the watch directory."""
    return config_path().parent / _STATE_DIR_NAME / WATCH_STATE_FILE_NAME


class WatchStateStore:
    """Reads and writes the automation state without ever answering with an empty one."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path

    def run_path(self, run_id: str) -> Path:
        """Locate the private checkpoint of one safe run identifier."""
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            msg = "A checkpoint requires a safe run identifier"
            raise ValueError(msg)
        return self._path.parent / "runs" / f"{run_id}.json"

    def load(self) -> WatchState:
        """Read the stored automation state, or the default one when nothing was written yet."""
        try:
            text: str = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return WatchState()
        except (OSError, UnicodeDecodeError) as problem:
            raise _invalid_file() from problem
        return _parse(text)

    def save(self, state: WatchState) -> None:
        """Persist *state*, keeping the last readable version as a backup beside it."""
        payload: str = json.dumps(_encode_state(state), indent=2, ensure_ascii=False) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = self._path.with_name(f"{self._path.name}{_TEMPORARY_SUFFIX}")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._back_up()
        temporary.replace(self._path)

    def _back_up(self) -> None:
        try:
            text: str = self._path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            return
        try:
            _parse(text)
        except ConfigError:
            logger.warning("Kept an unreadable automation state out of the backup")
            return
        self._path.with_name(f"{self._path.name}{_BACKUP_SUFFIX}").write_text(text, encoding="utf-8", newline="\n")


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
        "problem": confirmation.problem,
    }


def _encode_product(confirmation: ProductConfirmation) -> dict[str, object]:
    return {
        "group_id": confirmation.group_id,
        "artifact_kind": confirmation.artifact_kind,
        "path": confirmation.path,
        "generation": confirmation.generation,
        "request_id": confirmation.request_id,
        "origin": confirmation.origin.value,
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


def _decode_state(raw: object) -> WatchState:
    document: dict[str, object] = _strict_object(raw, _ROOT_KEYS, "automation state")
    schema_version: object = document["schema_version"]
    if type(schema_version) is not int or schema_version != WATCH_STATE_SCHEMA_VERSION:
        msg = "Unsupported automation state schema version"
        raise ValueError(msg)
    return WatchState(
        schema_version=schema_version,
        policy=_decode_policy(document["policy"]),
        reservations=tuple(_decode_reservation(item) for item in _list(document["reservations"], "reservations")),
        markers=tuple(_decode_marker(item) for item in _list(document["markers"], "markers")),
        requests=tuple(_decode_request(item) for item in _list(document["requests"], "requests")),
        acquisitions=tuple(_decode_acquisition(item) for item in _list(document["acquisitions"], "acquisitions")),
        products=tuple(_decode_product(item) for item in _list(document["products"], "products")),
        provider_locks=tuple(
            _decode_provider_lock(item) for item in _list(document["provider_locks"], "provider_locks")
        ),
        command_receipts=tuple(
            _decode_receipt(item) for item in _list(document["command_receipts"], "command_receipts")
        ),
        notified=frozenset(_decode_notification(item) for item in _list(document["notified"], "notified")),
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
    automatic: bool = _flag({"automatic": document.pop("automatic", False)}, "automatic")
    intents: tuple[GroupIntent, ...] = tuple(
        decode_intent(GroupIntent, item) for item in _list(document.pop("intents", []), "group intents")
    )
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
    )


def _decode_acquisition(raw: object) -> AcquisitionConfirmation:
    raw = {
        "requested_action": None,
        "action_id": None,
        "action_pending": False,
        "problem": None,
        **_strict_mapping(raw, "acquisition confirmation"),
    }
    document: dict[str, object] = _strict_object(raw, _ACQUISITION_KEYS, "acquisition confirmation")
    return AcquisitionConfirmation(
        operation_id=_text(document, "operation_id"),
        info_hash=_text(document, "info_hash"),
        directory=_text(document, "directory"),
        required_files=_decode_texts(document["required_files"], "required files"),
        state=AcquisitionState(_text(document, "state")),
        origin=RequestOrigin(_text(document, "origin")),
        subscription_id=_optional_text(document, "subscription_id"),
        episode=_optional_text(document, "episode"),
        updated_at=_text(document, "updated_at"),
        requested_action=_optional_text(document, "requested_action"),
        action_id=_optional_text(document, "action_id"),
        action_pending=_flag(document, "action_pending"),
        problem=_optional_text(document, "problem"),
    )


def _decode_product(raw: object) -> ProductConfirmation:
    document: dict[str, object] = _strict_object(raw, _PRODUCT_KEYS, "product confirmation")
    return ProductConfirmation(
        group_id=_text(document, "group_id"),
        artifact_kind=_text(document, "artifact_kind"),
        path=_text(document, "path"),
        generation=_whole(document, "generation"),
        request_id=_text(document, "request_id"),
        origin=RequestOrigin(_text(document, "origin")),
    )


def _decode_provider_lock(raw: object) -> ProviderLock:
    document: dict[str, object] = _strict_object(raw, _PROVIDER_LOCK_KEYS, "provider lock")
    return ProviderLock(
        provider=_text(document, "provider"),
        until=_text(document, "until"),
        reason=_text(document, "reason"),
    )


def _decode_receipt(raw: object) -> CommandReceipt:
    document: dict[str, object] = dict(_strict_mapping(raw, "command receipt"))
    pending: object = document.pop("pending", None)
    document = _strict_object(document, _RECEIPT_KEYS, "command receipt")
    if pending is not None and not isinstance(pending, str):
        msg = "A pending command kind must be text"
        raise TypeError(msg)
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
