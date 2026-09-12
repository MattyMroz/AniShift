from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

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
    SourceFingerprint,
    SourceSelection,
    WatchState,
)
from anishift.application.intents import ProductKind, RebuildRequest, RequestOrigin
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore, watch_state_path
from anishift.errors import ConfigError, ErrorCode

_TIMESTAMP: str = "2026-09-08T12:00:00+00:00"

_FINGERPRINT: SourceFingerprint = (("episode-01.mkv", 1024, 111),)


def _store(tmp_path: Path) -> WatchStateStore:
    return WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME)


def _state() -> WatchState:
    return WatchState(
        policy=AutomationPolicy(auto_enabled=True, directory_exceptions={"Solo Leveling": False}),
        reservations=(Reservation("episode-01", _FINGERPRINT, "panel", _TIMESTAMP),),
        markers=(
            ManualHandledMarker(
                group_id="episode-01",
                fingerprint=_FINGERPRINT,
                products=frozenset({ProductKind.FULL_PL}),
                request_id="request-1",
                recorded_at=_TIMESTAMP,
            ),
        ),
        requests=(
            ProcessingRequest(
                request_id="request-1",
                generation=2,
                group_ids=("episode-01",),
                fingerprints={"episode-01": _FINGERPRINT},
                origin=RequestOrigin.BACKGROUND,
                source_selection=SourceSelection.MANUAL,
                rebuild=RebuildRequest(frozenset({ProductKind.NARRATION_AUDIO})),
                settings={"llm_max_concurrency": 4, "tts_speed": 1.25, "burn": False, "voice": None},
                state=RequestState.RUNNING,
                attempts=1,
                accepted_at=_TIMESTAMP,
            ),
        ),
        acquisitions=(
            AcquisitionConfirmation(
                operation_id="operation-1",
                info_hash="AABBCC",
                directory="Solo Leveling",
                required_files=("episode-01.mkv",),
                state=AcquisitionState.ACCEPTED,
                origin=RequestOrigin.BACKGROUND,
                subscription_id="63b5bd67f700",
                episode="7.5",
                updated_at=_TIMESTAMP,
            ),
        ),
        products=(
            ProductConfirmation(
                group_id="episode-01",
                artifact_kind="final_mkv",
                path="Solo Leveling/episode-01.mkv",
                generation=2,
                request_id="request-1",
                origin=RequestOrigin.USER,
            ),
        ),
        provider_locks=(ProviderLock("nyaa", _TIMESTAMP, "rate limited"),),
        command_receipts=(CommandReceipt("command-1", _TIMESTAMP, {"accepted": True, "queued": 2, "note": None}),),
        notified=frozenset({("episode-01", "2", "ready")}),
    )


def _write(tmp_path: Path, document: object) -> None:
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(json.dumps(document), encoding="utf-8")


def test_store_round_trips_every_recorded_fact(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _state()

    store.save(state)

    assert store.load() == state


def test_legacy_requests_without_group_intents_still_load(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["requests"][0].pop("intents")
    _write(tmp_path, document)

    assert store.load() == _state()


def test_store_lowercases_the_info_hash_of_an_acquisition(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)

    store.save(_state())

    assert store.load().acquisitions[0].info_hash == "aabbcc"


def test_store_answers_with_automatic_work_switched_off_when_nothing_was_written(tmp_path: Path) -> None:
    state: WatchState = _store(tmp_path).load()

    assert state == WatchState()
    assert state.policy.auto_enabled is False
    assert state.policy.directory_exceptions == {}


def test_store_rejects_a_corrupt_document(tmp_path: Path) -> None:
    (tmp_path / WATCH_STATE_FILE_NAME).write_text('{"schema_version": 1, "policy"', encoding="utf-8")

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID


def test_store_rejects_an_unknown_field(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(WatchState())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["surprise"] = []
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_store_rejects_another_schema_version(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(WatchState())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["schema_version"] = WATCH_STATE_SCHEMA_VERSION + 1
    _write(tmp_path, document)

    with pytest.raises(ConfigError):
        store.load()


def test_saving_keeps_the_previous_version_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    first: WatchState = _state()
    store.save(first)

    store.save(replace(first, policy=AutomationPolicy(auto_enabled=False)))

    backup: WatchStateStore = WatchStateStore(tmp_path / f"{WATCH_STATE_FILE_NAME}.bak")
    assert backup.load() == first
    assert store.load().policy.auto_enabled is False
    assert not (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").exists()


def test_a_temporary_file_left_by_a_crash_changes_nothing(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _state()
    store.save(state)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").write_text("{ not json", encoding="utf-8")

    assert store.load() == state


def test_saving_overwrites_a_temporary_file_left_by_a_crash(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").write_text("{ not json", encoding="utf-8")

    store.save(_state())

    assert not (tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp").exists()
    assert store.load() == _state()


def test_store_rejects_a_file_that_is_not_valid_text_and_can_still_save(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    (tmp_path / WATCH_STATE_FILE_NAME).write_bytes(b'{"schema_version": 1, "policy": "\xff\xfe')

    with pytest.raises(ConfigError) as failure:
        store.load()
    store.save(_state())

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert store.load() == _state()


def test_saving_always_writes_the_current_schema_version(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)

    store.save(replace(_state(), schema_version=99))

    assert json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))["schema_version"] == (
        WATCH_STATE_SCHEMA_VERSION
    )
    assert store.load().schema_version == WATCH_STATE_SCHEMA_VERSION


def test_the_state_lives_beside_the_other_watch_files() -> None:
    path: Path = watch_state_path()

    assert path.name == WATCH_STATE_FILE_NAME
    assert path.parent.name == "watch"
    assert path.parent.parent.name == "config"
