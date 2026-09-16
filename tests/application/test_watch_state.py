from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    AcquisitionState,
    AudiobookRecipe,
    AutomationPolicy,
    CommandReceipt,
    DeletionOutcome,
    DeletionStatus,
    ManualHandledMarker,
    NarrationTimeline,
    PendingDeletion,
    ProcessingRequest,
    ProductConfirmation,
    ProviderLock,
    ReadyGroup,
    RecipePreferences,
    RequestState,
    Reservation,
    SourceFingerprint,
    SourceSelection,
    TextResultFormat,
    TranslateRecipe,
    WatchState,
)
from anishift.application.intents import ProductKind, RebuildRequest, RequestOrigin, TranslationAction
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore, watch_state_path
from anishift.application.workflows import WorkflowTarget
from anishift.errors import ConfigError, ErrorCode

_TIMESTAMP: str = "2026-09-08T12:00:00+00:00"

_FINGERPRINT: SourceFingerprint = (("episode-01.mkv", 1024, 111),)

_SCHEMA_TWO_SECTIONS: tuple[str, ...] = ("recipes", "ready_groups", "pause_owned_transfers", "pending_deletions")


def test_deletion_evidence_round_trips_and_legacy_scope_never_gains_invented_identity(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    deletion: PendingDeletion = PendingDeletion(
        "delete-01",
        "set-01",
        _TIMESTAMP,
        (("ready/01.txt", 10, 20),),
        identities=(("ready/01.txt", 30, 40),),
        outcomes=(DeletionOutcome("ready/01.txt", DeletionStatus.INFLIGHT, "recycle_inflight"),),
        instance_id="original-owner",
    )
    state: WatchState = replace(_state(), pending_deletions=(deletion,))
    store.save(state)
    assert store.load() == state
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = cast("list[dict[str, object]]", document["pending_deletions"])
    for field in ("identities", "outcomes", "instance_id"):
        records[0].pop(field)
    path.write_text(json.dumps(document), encoding="utf-8")
    legacy: PendingDeletion = store.load().pending_deletions[0]
    assert legacy.files == deletion.files
    assert legacy.identities == ()
    assert legacy.outcomes == ()
    assert legacy.instance_id is None


@pytest.mark.parametrize("change", ["foreign_identity", "duplicate_identity", "foreign_outcome", "missing_receipt"])
def test_deletion_loader_rejects_unsafe_native_evidence(tmp_path: Path, change: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    deletion: PendingDeletion = PendingDeletion("delete-01", "set-01", _TIMESTAMP, (("ready/01.txt", 10, 20),))
    store.save(replace(_state(), pending_deletions=(deletion,)))
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    entry: dict[str, object] = cast("list[dict[str, object]]", document["pending_deletions"])[0]
    if change == "foreign_identity":
        entry["identities"] = [["ready/010.txt", 1, 2]]
    elif change == "duplicate_identity":
        entry["identities"] = [["ready/01.txt", 1, 2], ["ready/01.txt", 1, 2]]
    else:
        entry["outcomes"] = [
            {
                "path": "ready/010.txt" if change == "foreign_outcome" else "ready/01.txt",
                "status": "inflight" if change == "foreign_outcome" else "recycled",
                "reason": "test",
                "receipt": None,
            }
        ]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        store.load()


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


def _schema_one_document(tmp_path: Path, state: WatchState) -> dict[str, object]:
    _store(tmp_path).save(state)
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["schema_version"] = 1
    for key in _SCHEMA_TWO_SECTIONS:
        document.pop(key)
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition.pop("complete_files")
    return document


def _write_schema_one(tmp_path: Path, state: WatchState) -> str:
    text: str = json.dumps(_schema_one_document(tmp_path, state))
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(text, encoding="utf-8")
    return text


def test_store_round_trips_every_recorded_fact(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = _state()

    store.save(state)

    assert store.load() == state


@pytest.mark.parametrize("schema", [1, 2])
def test_legacy_transfer_actions_do_not_invent_a_durable_send_record(tmp_path: Path, schema: int) -> None:
    state: WatchState = _state()
    store: WatchStateStore = _store(tmp_path)
    store.save(state)
    document: dict[str, object] = (
        _schema_one_document(tmp_path, state)
        if schema == 1
        else json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    )
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition.pop("action_sent")
    _write(tmp_path, document)

    assert store.load() == state
    assert store.load().acquisitions[0].action_sent is False


def test_legacy_requests_without_group_intents_still_load(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["requests"][0].pop("intents")
    _write(tmp_path, document)

    assert store.load() == _state()


def test_legacy_products_without_the_identity_of_their_bytes_still_load(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["products"][0].pop("size")
    document["products"][0].pop("modified_ns")
    _write(tmp_path, document)

    loaded: WatchState = store.load()

    assert loaded == _state()
    assert loaded.products[0].size == -1


def test_store_lowercases_the_info_hash_of_an_acquisition(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)

    store.save(_state())

    assert store.load().acquisitions[0].info_hash == "aabbcc"


def test_a_never_written_store_answers_with_automation_working_and_nothing_else_recorded(tmp_path: Path) -> None:
    state: WatchState = _store(tmp_path).load()

    assert state == WatchState(policy=AutomationPolicy(auto_enabled=True))
    assert state.policy.auto_enabled is True
    assert state.policy.directory_exceptions == {}


def test_a_stored_pause_stays_a_pause_instead_of_becoming_the_working_default(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))

    assert store.load().policy.auto_enabled is False


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


def test_a_schema_one_state_is_migrated_once_and_keeps_every_recorded_fact(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    original: str = _write_schema_one(tmp_path, _state())

    migrated: WatchState = store.load()

    assert migrated == _state()
    assert migrated.schema_version == WATCH_STATE_SCHEMA_VERSION
    assert (tmp_path / f"{WATCH_STATE_FILE_NAME}.v1.bak").read_text(encoding="utf-8") == original
    after: str = (tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8")
    assert store.load() == migrated
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8") == after


def test_migrating_a_schema_one_state_fills_the_new_facts_with_their_defaults(tmp_path: Path) -> None:
    _write_schema_one(tmp_path, _state())

    migrated: WatchState = _store(tmp_path).load()

    assert migrated.recipes == RecipePreferences()
    assert migrated.recipes.translate.text_result is TextResultFormat.TEXT
    assert migrated.recipes.audiobook.timeline is NarrationTimeline.CONTINUOUS
    assert (migrated.ready_groups, migrated.pause_owned_transfers, migrated.pending_deletions) == ((), (), ())
    assert migrated.acquisitions[0].complete_files == ()


def test_migration_never_overwrites_a_backup_left_by_an_earlier_attempt(tmp_path: Path) -> None:
    _write_schema_one(tmp_path, _state())
    backup: Path = tmp_path / f"{WATCH_STATE_FILE_NAME}.v1.bak"
    backup.write_text("kept", encoding="utf-8")

    _store(tmp_path).load()

    assert backup.read_text(encoding="utf-8") == "kept"


@pytest.mark.parametrize("section", _SCHEMA_TWO_SECTIONS)
def test_a_schema_two_state_missing_a_section_it_must_carry_is_refused(tmp_path: Path, section: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document.pop(section)
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


@pytest.mark.parametrize("section", _SCHEMA_TWO_SECTIONS)
def test_a_schema_two_state_with_a_malformed_section_is_refused(tmp_path: Path, section: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document[section] = "nonsense"
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_a_schema_two_acquisition_without_its_completeness_is_refused(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    document: dict[str, object] = json.loads((tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition.pop("complete_files")
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


@pytest.mark.parametrize("section", _SCHEMA_TWO_SECTIONS)
def test_a_schema_one_state_carrying_a_schema_two_section_is_refused(tmp_path: Path, section: str) -> None:
    store: WatchStateStore = _store(tmp_path)
    document: dict[str, object] = _schema_one_document(tmp_path, _state())
    document[section] = []
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_a_schema_one_acquisition_claiming_completeness_is_refused(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    document: dict[str, object] = _schema_one_document(tmp_path, _state())
    for acquisition in document["acquisitions"]:  # type: ignore[attr-defined]
        acquisition["complete_files"] = []
    _write(tmp_path, document)

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_a_truncated_state_still_raises_instead_of_answering_with_defaults(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    store.save(_state())
    full: str = (tmp_path / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8")
    (tmp_path / WATCH_STATE_FILE_NAME).write_text(full[: len(full) // 2], encoding="utf-8")

    with pytest.raises(ConfigError, match="Automation state file is invalid"):
        store.load()


def test_migrating_a_completed_download_keeps_every_required_file_complete(tmp_path: Path) -> None:
    complete: AcquisitionConfirmation = AcquisitionConfirmation(
        operation_id="operation-2",
        info_hash="ddeeff",
        directory="Solo Leveling",
        required_files=("one.mkv", "two.mkv"),
        state=AcquisitionState.COMPLETE,
        origin=RequestOrigin.BACKGROUND,
        subscription_id=None,
        episode="1",
        updated_at=_TIMESTAMP,
        complete_files=("one.mkv", "two.mkv"),
    )
    _write_schema_one(tmp_path, replace(_state(), acquisitions=(complete,)))

    migrated: WatchState = _store(tmp_path).load()

    assert migrated.acquisitions[0].complete_files == ("one.mkv", "two.mkv")


@pytest.mark.parametrize(
    "state",
    [AcquisitionState.PENDING_SEND, AcquisitionState.UNCERTAIN, AcquisitionState.ACCEPTED, AcquisitionState.FAILED],
)
def test_migrating_an_unfinished_download_invents_no_completeness(tmp_path: Path, state: AcquisitionState) -> None:
    unfinished: AcquisitionConfirmation = replace(
        _state().acquisitions[0], state=state, required_files=("one.mkv", "two.mkv")
    )
    _write_schema_one(tmp_path, replace(_state(), acquisitions=(unfinished,)))

    migrated: WatchState = _store(tmp_path).load()

    assert (migrated.acquisitions[0].state, migrated.acquisitions[0].complete_files) == (state, ())


def test_a_migrated_state_keeps_automatic_work_switched_off(tmp_path: Path) -> None:
    _write_schema_one(tmp_path, replace(_state(), policy=AutomationPolicy(auto_enabled=False)))

    assert _store(tmp_path).load().policy.auto_enabled is False


def test_the_store_round_trips_the_facts_added_by_schema_two(tmp_path: Path) -> None:
    store: WatchStateStore = _store(tmp_path)
    state: WatchState = replace(
        _state(),
        recipes=RecipePreferences(
            translate=TranslateRecipe(TextResultFormat.SUBTITLES, TranslationAction.TRANSLATE),
            audiobook=AudiobookRecipe(TranslationAction.DO_NOT_TRANSLATE, NarrationTimeline.SOURCE_TIMES),
        ),
        ready_groups=(
            ReadyGroup(
                set_id="set-1",
                group_id="ready-episode-01",
                stem="episode-01",
                source_directory="audiobook/Solo Leveling",
                source_stem="episode-01",
                target=WorkflowTarget.AUDIOBOOK,
                sources=("ready/episode-01.mkv",),
                products=("ready/episode-01.m4a",),
                main_result="ready/episode-01.m4a",
                pending_sources=("audiobook/Solo Leveling/episode-01.mkv",),
                recipe=RecipePreferences(audiobook=AudiobookRecipe(timeline=NarrationTimeline.SOURCE_TIMES)),
            ),
        ),
        pause_owned_transfers=("aabbcc",),
        pending_deletions=(
            PendingDeletion(
                operation_id="deletion-1",
                set_id="set-1",
                requested_at=_TIMESTAMP,
                files=(("ready/episode-01.mkv", 1024, 111), ("ready/episode-01.m4a", 2048, 222)),
                recycled=("ready/episode-01.mkv",),
            ),
        ),
        acquisitions=(replace(_state().acquisitions[0], complete_files=("episode-01.mkv",)),),
    )

    store.save(state)

    assert store.load() == state


def test_the_state_lives_beside_the_other_watch_files() -> None:
    path: Path = watch_state_path()

    assert path.name == WATCH_STATE_FILE_NAME
    assert path.parent.name == "watch"
    assert path.parent.parent.name == "config"
