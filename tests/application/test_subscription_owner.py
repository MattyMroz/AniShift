from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_automation import _MOMENT, _TIMEOUT_S, _library, _owner, _request, _serving

from anishift.application.automation import AutomationOwner
from anishift.application.control import LegacyOrder, WatchState
from anishift.application.control_views import decode_view
from anishift.application.subscription_targets import (
    MAX_SUBSCRIPTIONS,
    PauseReason,
    SubscriptionRecord,
    SubscriptionRow,
)
from anishift.application.subscriptions import Subscription, SubscriptionStore
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.platform.local_control import ControlErrorCode, ControlResponse

_ACTIVE: SubscriptionRecord = SubscriptionRecord(
    subscription_id="a",
    anilist_id=1,
    title="Alpha",
    subscribed_at=_MOMENT.isoformat(),
    cut=0,
)

_PAUSED: SubscriptionRecord = replace(
    _ACTIVE, subscription_id="b", anilist_id=2, title="Beta", paused=True, pause_reason=PauseReason.USER
)


@contextmanager
def _running(tmp_path: Path, state: WatchState) -> Iterator[tuple[AutomationOwner, WatchStateStore]]:
    service, _, _ = _library(tmp_path)
    store: WatchStateStore = WatchStateStore(
        tmp_path / WATCH_STATE_FILE_NAME, subscriptions_path=tmp_path / "subscriptions.json"
    )
    store.save(state)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        yield owner, store
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)


def _ask(
    owner: AutomationOwner, kind: str, payload: Mapping[str, object] | None = None, command_id: str = "c"
) -> ControlResponse:
    return owner.handle(_request(kind, payload, command_id=command_id))


def _rows(response: ControlResponse) -> list[SubscriptionRow]:
    rows: object = response.result["subscriptions"]
    assert isinstance(rows, list)
    return [decode_view(SubscriptionRow, item) for item in rows]


def test_the_list_answers_rows_in_display_order_without_target_lists(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_PAUSED, _ACTIVE))) as (owner, _):
        answer: ControlResponse = _ask(owner, "subscriptions_list")

    assert answer.ok
    assert [row.subscription_id for row in _rows(answer)] == ["a", "b"]
    assert answer.result["problem"] is None
    assert all("targets" not in item for item in answer.result["subscriptions"])  # type: ignore[attr-defined]


def test_details_answer_the_row_and_counts_of_one_subscription(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE,))) as (owner, _):
        answer: ControlResponse = _ask(owner, "subscription_get", {"subscription_id": "a"})

    assert answer.ok
    assert decode_view(SubscriptionRow, answer.result["row"]).title == "Alpha"
    assert answer.result["first_target"] is None


def test_pause_and_resume_persist_with_a_receipt_and_repeat_no_effect(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE,))) as (owner, store):
        paused: ControlResponse = _ask(owner, "subscription_pause", {"subscription_id": "a"}, "pause-1")
        stored_pause: SubscriptionRecord = store.load().subscriptions[0]
        resumed: ControlResponse = _ask(owner, "subscription_resume", {"subscription_id": "a"}, "resume-1")
        repeated: ControlResponse = _ask(owner, "subscription_pause", {"subscription_id": "a"}, "pause-1")
        saved: WatchState = store.load()

    assert paused.result == {"subscription_id": "a", "paused": True}
    assert (stored_pause.paused, stored_pause.pause_reason) == (True, PauseReason.USER)
    assert resumed.result == {"subscription_id": "a", "paused": False}
    assert repeated.result == paused.result
    assert (saved.subscriptions[0].paused, saved.subscriptions[0].pause_reason) == (False, None)
    assert {"pause-1", "resume-1"} <= {item.command_id for item in saved.command_receipts}


def test_resuming_a_migrated_pause_clears_its_reason(tmp_path: Path) -> None:
    missing: SubscriptionRecord = replace(_ACTIVE, paused=True, pause_reason=PauseReason.MIGRATED_MISSING)
    with _running(tmp_path, WatchState(subscriptions=(missing,))) as (owner, store):
        assert _ask(owner, "subscription_resume", {"subscription_id": "a"}).ok
        saved: SubscriptionRecord = store.load().subscriptions[0]

    assert (saved.paused, saved.pause_reason) == (False, None)


def test_remove_keeps_one_record_for_restore_and_restore_brings_it_back(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE, _PAUSED))) as (owner, store):
        _ask(owner, "subscription_remove", {"subscription_id": "a"}, "remove-a")
        _ask(owner, "subscription_remove", {"subscription_id": "b"}, "remove-b")
        removed: WatchState = store.load()
        restored: ControlResponse = _ask(owner, "subscription_restore", command_id="restore-1")
        saved: WatchState = store.load()

    assert removed.subscriptions == ()
    assert removed.removed_subscription == _PAUSED
    assert restored.result == {"subscription_id": "b", "restored": True}
    assert saved.subscriptions == (_PAUSED,)
    assert saved.removed_subscription is None


@pytest.mark.parametrize(
    ("state", "kind", "reason"),
    [
        (WatchState(), "subscription_restore", "nothing_to_restore"),
        (
            WatchState(subscriptions=(_ACTIVE,), removed_subscription=_ACTIVE),
            "subscription_restore",
            "subscription_exists",
        ),
        (
            WatchState(subscriptions=(_PAUSED,), removed_subscription=replace(_ACTIVE, anilist_id=2)),
            "subscription_restore",
            "subscription_exists",
        ),
        (WatchState(), "subscription_get", "subscription_missing"),
        (WatchState(), "subscription_pause", "subscription_missing"),
        (WatchState(), "subscription_resume", "subscription_missing"),
        (WatchState(), "subscription_remove", "subscription_missing"),
    ],
)
def test_impossible_subscription_commands_are_refused_without_a_change(
    tmp_path: Path, state: WatchState, kind: str, reason: str
) -> None:
    with _running(tmp_path, state) as (owner, store):
        answer: ControlResponse = _ask(owner, kind, {"subscription_id": "a"})
        saved: WatchState = store.load()

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == reason
    assert (saved.subscriptions, saved.removed_subscription) == (state.subscriptions, state.removed_subscription)


def test_restore_at_the_subscription_limit_is_refused_and_keeps_the_undo(tmp_path: Path) -> None:
    full: tuple[SubscriptionRecord, ...] = tuple(
        replace(_ACTIVE, subscription_id=f"s{index}", anilist_id=100 + index, title=f"S{index}")
        for index in range(MAX_SUBSCRIPTIONS)
    )
    state: WatchState = WatchState(subscriptions=full, removed_subscription=_ACTIVE)
    with _running(tmp_path, state) as (owner, store):
        answer: ControlResponse = _ask(owner, "subscription_restore", command_id="restore")
        saved: WatchState = store.load()

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == "subscription_limit"
    assert len(saved.subscriptions) == MAX_SUBSCRIPTIONS
    assert saved.removed_subscription == _ACTIVE


@pytest.mark.parametrize(
    "kind", ["subscription_add", "subscription_enable", "subscription_disable", "subscriptions_check"]
)
def test_former_subscription_commands_are_unknown(tmp_path: Path, kind: str) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE,))) as (owner, _):
        answer: ControlResponse = _ask(owner, kind, {"subscription_id": "a"})

    assert answer.code is ControlErrorCode.UNKNOWN_COMMAND


def test_a_change_that_cannot_be_saved_is_refused_and_keeps_the_state(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE,))) as (owner, store):
        blocker: Path = tmp_path / f"{WATCH_STATE_FILE_NAME}.tmp"
        blocker.mkdir()
        answer: ControlResponse = _ask(owner, "subscription_pause", {"subscription_id": "a"})
        listed: ControlResponse = _ask(owner, "subscriptions_list", command_id="list")
        blocker.rmdir()
        saved: WatchState = store.load()

    assert answer.code is ControlErrorCode.INTERNAL
    assert not _rows(listed)[0].paused
    assert not saved.subscriptions[0].paused


def test_the_owner_never_writes_the_frozen_subscription_file(tmp_path: Path) -> None:
    listing: Path = tmp_path / "subscriptions.json"
    SubscriptionStore(listing).save(
        (
            Subscription(
                subscription_id="a",
                query="alpha",
                series="Alpha",
                group="SubsPlease",
                next_episode=Decimal(2),
                min_resolution=1080,
                taken=frozenset(),
                added_at=_MOMENT.isoformat(),
                checked_at=None,
                anilist_id=1,
                taken_episodes=("1",),
            ),
        )
    )
    frozen: bytes = listing.read_bytes()
    service, _, _ = _library(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME, subscriptions_path=listing)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        _ask(owner, "subscription_pause", {"subscription_id": "a"}, "pause")
        _ask(owner, "subscription_remove", {"subscription_id": "a"}, "remove")
        _ask(owner, "subscription_restore", command_id="restore")
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    saved: WatchState = store.load()
    assert listing.read_bytes() == frozen
    assert [item.subscription_id for item in saved.subscriptions] == ["a"]
    assert saved.legacy_orders == (LegacyOrder(1, 1, "subscription:a:1", None, complete=False),)
