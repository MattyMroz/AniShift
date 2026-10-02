from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from anishift.application.control import (
    WATCH_STATE_SCHEMA_VERSION,
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    CommandReceipt,
    LegacyOrder,
    LegacyScope,
    WatchState,
)
from anishift.application.intents import RequestOrigin
from anishift.application.subscription_migration import legacy_reference, migrate
from anishift.application.subscription_targets import PauseReason, SubscriptionProblem, SubscriptionRecord
from anishift.application.subscriptions import (
    EpisodeOrder,
    EpisodeState,
    Subscription,
    SubscriptionEnd,
    SubscriptionStore,
)
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.errors import ConfigError, ErrorCode

_NOW: datetime = datetime(2026, 10, 2, 12, tzinfo=UTC)

_ADDED: str = "2026-09-01T12:00:00+00:00"


def _legacy(  # noqa: PLR0913
    identifier: str = "neko",
    *,
    anilist_id: int | None = 7,
    enabled: bool = True,
    end: SubscriptionEnd = SubscriptionEnd.ACTIVE,
    added_at: str = _ADDED,
    group: str = "SubsPlease",
) -> Subscription:
    return Subscription(
        subscription_id=identifier,
        query="neko",
        series="Neko to Ryuu",
        group=group,
        next_episode=Decimal(3),
        min_resolution=1080,
        taken=frozenset(),
        added_at=added_at,
        checked_at=None,
        enabled=enabled,
        anilist_id=anilist_id,
        end_state=end,
    )


def _confirmation(operation_id: str, subscription_id: str | None, episode: str | None) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        operation_id=operation_id,
        info_hash=f"{operation_id}hash",
        directory="",
        required_files=(f"{operation_id}.mkv",),
        state=AcquisitionState.ACCEPTED,
        origin=RequestOrigin.BACKGROUND,
        subscription_id=subscription_id,
        episode=episode,
        updated_at=_ADDED,
    )


def _store(tmp_path: Path) -> WatchStateStore:
    return WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME, subscriptions_path=tmp_path / "subscriptions.json")


def _expected_pause(*, enabled: bool, end: SubscriptionEnd) -> PauseReason | None:
    if not enabled:
        return PauseReason.USER
    if end in {SubscriptionEnd.MISSING, SubscriptionEnd.UNCERTAIN}:
        return PauseReason.MIGRATED_MISSING
    return None


@pytest.mark.parametrize("anilist_id", [None, 7])
@pytest.mark.parametrize("end", list(SubscriptionEnd))
@pytest.mark.parametrize("enabled", [False, True])
def test_every_switch_end_and_entry_combination_migrates_to_its_record(
    *, enabled: bool, end: SubscriptionEnd, anilist_id: int | None
) -> None:
    migrated: WatchState = migrate(WatchState(), (_legacy(anilist_id=anilist_id, enabled=enabled, end=end),), _NOW)

    if end is SubscriptionEnd.COMPLETE:
        assert migrated.subscriptions == ()
        return
    reason: PauseReason | None = _expected_pause(enabled=enabled, end=end)
    assert migrated.subscriptions == (
        SubscriptionRecord(
            subscription_id="neko",
            anilist_id=anilist_id,
            title="Neko to Ryuu",
            subscribed_at=_ADDED,
            cut=None,
            paused=reason is not None,
            pause_reason=reason,
            migrated_at=_NOW.isoformat(),
            review_pending=anilist_id is not None,
            merged_from=("neko",),
            problem=None if anilist_id is not None else SubscriptionProblem.SEASON_UNRECOGNIZED,
            migrated_from="subscriptions.json",
        ),
    )
    assert migrated.subscriptions[0].targets == ()
    assert migrated.schema_version == WATCH_STATE_SCHEMA_VERSION


def test_former_subscriptions_of_one_season_merge_into_one_record_without_losing_an_order() -> None:
    older: Subscription = replace(
        _legacy("older", enabled=False, added_at="2026-08-01T12:00:00+00:00", group="DKB"), taken_episodes=("1",)
    )
    newer: Subscription = _legacy("newer", end=SubscriptionEnd.MISSING)
    confirmed: AcquisitionConfirmation = _confirmation("operation-1", "newer", "2")

    migrated: WatchState = migrate(WatchState(acquisitions=(confirmed,)), (newer, older), _NOW)

    assert len(migrated.subscriptions) == 1
    record: SubscriptionRecord = migrated.subscriptions[0]
    assert record.subscription_id == "older"
    assert record.subscribed_at == "2026-08-01T12:00:00+00:00"
    assert record.merged_from == ("older", "newer")
    assert not record.paused
    assert migrated.legacy_orders == (
        LegacyOrder(7, 1, "subscription:older:1", None, complete=False),
        LegacyOrder(7, 2, legacy_reference(confirmed), "operation-1", complete=False),
    )
    assert migrated.acquisitions == (confirmed,)


@pytest.mark.parametrize(("ends", "reason"), [((True, True), PauseReason.MIGRATED_MISSING), ((True, False), None)])
def test_a_merged_record_is_closed_by_the_former_version_only_when_every_entry_was(
    ends: tuple[bool, bool], reason: PauseReason | None
) -> None:
    first, second = (SubscriptionEnd.MISSING if missing else SubscriptionEnd.ACTIVE for missing in ends)
    entries: tuple[Subscription, ...] = (
        _legacy("a", end=first),
        _legacy("b", end=second, added_at="2026-09-02T12:00:00+00:00"),
    )

    assert migrate(WatchState(), entries, _NOW).subscriptions[0].pause_reason == reason


def test_legacy_orders_carry_the_former_conflict_references_and_scopes() -> None:
    fractional: EpisodeOrder = EpisodeOrder(
        Decimal("7.5"), state=EpisodeState.ORDERED, info_hash="h", acquisition_id="o"
    )
    complete: EpisodeOrder = EpisodeOrder(Decimal(8), state=EpisodeState.COMPLETE, info_hash="k", acquisition_id="p")
    pending: EpisodeOrder = EpisodeOrder(Decimal(9))
    linked: Subscription = replace(
        _legacy("linked", end=SubscriptionEnd.COMPLETE), taken_episodes=("6",), episodes=(fractional, complete, pending)
    )
    unlinked: Subscription = replace(_legacy("unlinked", anilist_id=None), taken_episodes=("1",))
    unscoped: AcquisitionConfirmation = _confirmation("old", "linked", "5")
    scoped: AcquisitionConfirmation = replace(_confirmation("scoped", "linked", "4"), legacy_scope=LegacyScope(7, 4))
    foreign: AcquisitionConfirmation = _confirmation("foreign", "unlinked", "3")
    state: WatchState = WatchState(acquisitions=(unscoped, scoped, foreign))

    migrated: WatchState = migrate(state, (linked, unlinked), _NOW)

    assert migrated.legacy_orders == (
        LegacyOrder(7, 6, "subscription:linked:6", None, complete=False),
        LegacyOrder(7, None, "subscription:linked:7.5", None, complete=False),
        LegacyOrder(7, 8, "subscription:linked:8", None, complete=True),
        LegacyOrder(7, None, "subscription:linked:7.5:h:o:None", None, complete=False),
        LegacyOrder(7, 8, "subscription:linked:8:k:p:None", None, complete=True),
        LegacyOrder(7, 5, legacy_reference(unscoped), "old", complete=False),
    )
    assert migrated.acquisitions == state.acquisitions


def test_pending_former_commands_settle_by_kind_and_other_receipts_stay_pending() -> None:
    receipts: tuple[CommandReceipt, ...] = (
        CommandReceipt("remove", _ADDED, {"subscription_id": "gone"}, pending="subscription_remove"),
        CommandReceipt("disable", _ADDED, {"subscription_id": "kept"}, pending="subscription_disable"),
        CommandReceipt("add", _ADDED, {"subscription_id": "added"}, pending="subscription_add"),
        CommandReceipt("cancel", _ADDED, {"run_id": "run"}, pending="cancel"),
    )
    entries: tuple[Subscription, ...] = (_legacy("gone"), _legacy("kept", anilist_id=8), _legacy("added", anilist_id=9))

    migrated: WatchState = migrate(WatchState(command_receipts=receipts), entries, _NOW)

    assert [(item.subscription_id, item.pause_reason) for item in migrated.subscriptions] == [
        ("kept", PauseReason.USER),
        ("added", None),
    ]
    assert [item.pending for item in migrated.command_receipts] == [None, None, None, "cancel"]


def _write_listing(tmp_path: Path, version: int) -> bytes:
    path: Path = tmp_path / "subscriptions.json"
    SubscriptionStore(path).save((replace(_legacy(), taken_episodes=("1",)),))
    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = version
    if version == 1:
        document["subscriptions"] = [
            {
                "subscription_id": "neko",
                "query": "neko",
                "series": "Neko to Ryuu",
                "group": "SubsPlease",
                "next_episode": "3",
                "min_resolution": 1080,
                "taken": [],
                "added_at": _ADDED,
                "checked_at": None,
                "taken_episodes": ["1"],
            }
        ]
    path.write_text(json.dumps(document), encoding="utf-8")
    return path.read_bytes()


def _write_old_state(tmp_path: Path) -> bytes:
    staging: Path = tmp_path / "staging"
    store: WatchStateStore = WatchStateStore(
        staging / WATCH_STATE_FILE_NAME, subscriptions_path=staging / "subscriptions.json"
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    document: dict[str, object] = json.loads((tmp_path / "staging" / WATCH_STATE_FILE_NAME).read_text(encoding="utf-8"))
    document["schema_version"] = 3
    for key in ("subscriptions", "removed_subscription", "legacy_orders"):
        document.pop(key)
    path: Path = tmp_path / WATCH_STATE_FILE_NAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path.read_bytes()


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_migration_never_writes_the_former_subscription_file_of_any_version(tmp_path: Path, version: int) -> None:
    listing: bytes = _write_listing(tmp_path, version)
    state: bytes = _write_old_state(tmp_path)
    store: WatchStateStore = _store(tmp_path)

    migrated: WatchState = store.load()
    written: bytes = (tmp_path / WATCH_STATE_FILE_NAME).read_bytes()

    assert store.load() == migrated
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == written
    assert (tmp_path / "subscriptions.json").read_bytes() == listing
    assert not list(tmp_path.glob("subscriptions.json.v*.bak"))
    assert (tmp_path / "subscriptions.json.e3-migration.bak").read_bytes() == listing
    assert (tmp_path / f"{WATCH_STATE_FILE_NAME}.e3-migration.bak").read_bytes() == state
    assert [item.subscription_id for item in migrated.subscriptions] == ["neko"]


def test_a_missing_state_with_a_former_listing_migrates_and_saves(tmp_path: Path) -> None:
    listing: bytes = _write_listing(tmp_path, 4)

    migrated: WatchState = _store(tmp_path).load()

    assert [item.subscription_id for item in migrated.subscriptions] == ["neko"]
    assert migrated.legacy_orders == (LegacyOrder(7, 1, "subscription:neko:1", None, complete=False),)
    assert _store(tmp_path).load() == migrated
    assert (tmp_path / "subscriptions.json").read_bytes() == listing
    assert (tmp_path / "subscriptions.json.e3-migration.bak").read_bytes() == listing


def test_neither_file_answers_the_default_state_without_writing(tmp_path: Path) -> None:
    assert _store(tmp_path).load().subscriptions == ()
    assert list(tmp_path.iterdir()) == []


def test_a_failed_migration_write_changes_no_input_and_the_next_load_completes(tmp_path: Path) -> None:
    listing: bytes = _write_listing(tmp_path, 4)
    state: bytes = _write_old_state(tmp_path)
    blocker: Path = tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp"
    blocker.mkdir()

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.IO_ERROR
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state
    assert (tmp_path / "subscriptions.json").read_bytes() == listing
    blocker.rmdir()
    assert [item.subscription_id for item in _store(tmp_path).load().subscriptions] == ["neko"]
    assert (tmp_path / f"{WATCH_STATE_FILE_NAME}.e3-migration.bak").read_bytes() == state


def test_a_corrupt_former_listing_refuses_the_migration_and_keeps_both_files(tmp_path: Path) -> None:
    (tmp_path / "subscriptions.json").write_bytes(b"{broken")
    state: bytes = _write_old_state(tmp_path)

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert "e3-migration.bak" in failure.value.context.suggestion
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state
    assert (tmp_path / "subscriptions.json").read_bytes() == b"{broken"


def test_a_listing_that_cannot_migrate_refuses_before_any_copy_and_keeps_both_files(tmp_path: Path) -> None:
    listing_path: Path = tmp_path / "subscriptions.json"
    SubscriptionStore(listing_path).save((_legacy(added_at="not-a-date"),))
    listing: bytes = listing_path.read_bytes()
    state: bytes = _write_old_state(tmp_path)

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert "e3-migration.bak" in failure.value.context.suggestion
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state
    assert listing_path.read_bytes() == listing
    assert not list(tmp_path.glob("*.bak"))


def test_an_unreadable_former_listing_refuses_with_the_restore_hint(tmp_path: Path) -> None:
    (tmp_path / "subscriptions.json").mkdir()
    state: bytes = _write_old_state(tmp_path)

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert "e3-migration.bak" in failure.value.context.suggestion
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state


def test_a_schema_copy_that_cannot_be_made_blocks_the_migration(tmp_path: Path) -> None:
    listing: bytes = _write_listing(tmp_path, 4)
    state: bytes = _write_old_state(tmp_path)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.v3.bak.tmp").mkdir()

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.IO_ERROR
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state
    assert (tmp_path / "subscriptions.json").read_bytes() == listing


def test_an_existing_migration_copy_is_never_overwritten(tmp_path: Path) -> None:
    _write_listing(tmp_path, 4)
    _write_old_state(tmp_path)
    copy: Path = tmp_path / "subscriptions.json.e3-migration.bak"
    copy.write_bytes(b"kept")

    _store(tmp_path).load()

    assert copy.read_bytes() == b"kept"


def test_a_migration_copy_that_cannot_be_made_blocks_the_write(tmp_path: Path) -> None:
    _write_listing(tmp_path, 4)
    state: bytes = _write_old_state(tmp_path)
    (tmp_path / f"{WATCH_STATE_FILE_NAME}.e3-migration.bak.tmp").mkdir()

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.IO_ERROR
    assert (tmp_path / WATCH_STATE_FILE_NAME).read_bytes() == state
