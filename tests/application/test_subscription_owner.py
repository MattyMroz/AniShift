from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from loguru import logger as loguru_logger
from test_acquisition import (
    _S1,
    _S4,
    _Clock,
    _episode_service,
    _EpisodeCatalog,
    _slime_streams,
    _StreamSource,
    _TitleCatalog,
)
from test_automation import _INSTANCE, _MOMENT, _TIMEOUT_S, _await, _library, _owner, _request, _serving
from test_episode_selection import _fixture_graph, _fixture_mapping

from anishift.application import AppService
from anishift.application import automation as automation_module
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AutomationPolicy,
    EpisodeAssignment,
    EpisodeChoice,
    LegacyOrder,
    TorrentioReference,
    WatchState,
)
from anishift.application.control_views import decode_view
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import AniZipMapping, ListedSpecial, StreamCandidate
from anishift.application.intents import RequestOrigin
from anishift.application.subscription_targets import (
    MAX_SUBSCRIPTIONS,
    PauseReason,
    SubscriptionCheck,
    SubscriptionProblem,
    SubscriptionRecord,
    SubscriptionRow,
    SubscriptionTarget,
    TargetState,
)
from anishift.application.subscriptions import Subscription, SubscriptionStore
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.local_control import MAX_FRAME_BYTES, ControlErrorCode, ControlResponse
from anishift.services.catalog import EpisodeAiring, SeasonAiring, TitleCatalogError, TitleStatus
from anishift.services.catalog.anizip import AniZipCatalog
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.torrentio import TorrentioSource

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
        stored_pause: SubscriptionRecord = owner._on_owner(store.load).subscriptions[0]
        resumed: ControlResponse = _ask(owner, "subscription_resume", {"subscription_id": "a"}, "resume-1")
        repeated: ControlResponse = _ask(owner, "subscription_pause", {"subscription_id": "a"}, "pause-1")
        saved: WatchState = owner._on_owner(store.load)

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
        saved: SubscriptionRecord = owner._on_owner(store.load).subscriptions[0]

    assert (saved.paused, saved.pause_reason) == (False, None)


def test_remove_keeps_one_record_for_restore_and_restore_brings_it_back(tmp_path: Path) -> None:
    with _running(tmp_path, WatchState(subscriptions=(_ACTIVE, _PAUSED))) as (owner, store):
        _ask(owner, "subscription_remove", {"subscription_id": "a"}, "remove-a")
        _ask(owner, "subscription_remove", {"subscription_id": "b"}, "remove-b")
        removed: WatchState = owner._on_owner(store.load)
        restored: ControlResponse = _ask(owner, "subscription_restore", command_id="restore-1")
        saved: WatchState = owner._on_owner(store.load)

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
        saved: WatchState = owner._on_owner(store.load)

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
        saved: WatchState = owner._on_owner(store.load)

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == "subscription_limit"
    assert len(saved.subscriptions) == MAX_SUBSCRIPTIONS
    assert saved.removed_subscription == _ACTIVE


@pytest.mark.parametrize(
    "kind", ["subscription_range", "subscription_enable", "subscription_disable", "subscriptions_check"]
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
        saved: WatchState = owner._on_owner(store.load)

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


_NOW: datetime = datetime(2026, 10, 3, 12, tzinfo=UTC)

_KITSU: int = 49235

_WEEK: timedelta = timedelta(days=7)


def _airing(status: TitleStatus = TitleStatus.RELEASING, *, dated: bool = True) -> SeasonAiring:
    episodes: tuple[EpisodeAiring, ...] = tuple(
        EpisodeAiring(number, _NOW - timedelta(hours=1) + (number - 23) * _WEEK) for number in range(1, 25)
    )
    return SeasonAiring(_S4, status, 24, episodes if dated else ())


def _mapping(**changes: object) -> AniZipMapping:
    return replace(_fixture_mapping(_S4), **changes)  # type: ignore[arg-type]


@dataclass
class _World:
    clock: _Clock = field(default_factory=lambda: _Clock(_NOW.timestamp()))
    titles: _TitleCatalog = field(
        default_factory=lambda: _TitleCatalog(graphs={_S4: _fixture_graph(_S1)}, schedules={_S4: _airing()})
    )
    episodes: _EpisodeCatalog = field(default_factory=lambda: _EpisodeCatalog({_S4: _mapping(max_age_s=0)}))
    streams: _StreamSource = field(default_factory=_slime_streams)
    control: RequestControl | None = None
    catalog: object = None

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock.now, UTC)


def _followed(identifier: str = "a", **changes: object) -> SubscriptionRecord:
    record: SubscriptionRecord = SubscriptionRecord(
        identifier,
        _S4,
        "Slime S4",
        (_NOW - timedelta(days=2)).isoformat(),
        22,
        kitsu_id=_KITSU,
        mapping=_mapping(max_age_s=None),
    )
    return replace(record, **changes)  # type: ignore[arg-type]


def _active(*records: SubscriptionRecord) -> WatchState:
    return WatchState(policy=AutomationPolicy(auto_enabled=True), subscriptions=records)


@contextmanager
def _following(
    tmp_path: Path, state: WatchState, world: _World, *, shadow: bool = False
) -> Iterator[tuple[AutomationOwner, WatchStateStore]]:
    service, _, _ = _library(tmp_path)
    service.acquisition = _episode_service(
        tmp_path,
        world.titles,
        cast("_EpisodeCatalog", world.catalog) if world.catalog is not None else world.episodes,
        world.streams,
        clock=world.clock,
        request_control=world.control,
    )
    store: WatchStateStore = WatchStateStore(
        tmp_path / WATCH_STATE_FILE_NAME, subscriptions_path=tmp_path / "subscriptions.json"
    )
    if not (tmp_path / WATCH_STATE_FILE_NAME).exists():
        store.save(state)
    owner: AutomationOwner = AutomationOwner(
        cast("AppService", service), store, instance_id=_INSTANCE, clock=world.now, subscription_shadow=shadow
    )
    thread: threading.Thread = _serving(owner)
    try:
        yield owner, store
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)


def _settled(owner: AutomationOwner) -> None:
    assert _await(lambda: owner._on_owner(lambda: not owner._subscription_checks))


def _checked(owner: AutomationOwner, store: WatchStateStore, identifier: str = "a") -> SubscriptionRecord:
    assert _await(
        lambda: any(
            item.subscription_id == identifier and item.last_check is not None for item in owner.state.subscriptions
        )
    )
    _settled(owner)
    return next(item for item in owner._on_owner(store.load).subscriptions if item.subscription_id == identifier)


def _decisions(tmp_path: Path) -> list[dict[str, object]]:
    path: Path = tmp_path / "decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_shadow_check_proposes_one_match_and_admits_nothing(tmp_path: Path) -> None:
    world: _World = _World()
    logged: list[dict[str, object]] = []
    handler: int = loguru_logger.add(
        lambda message: logged.append(dict(message.record["extra"])),
        filter=lambda record: record["message"] == "Subscription checked",
    )
    try:
        with _following(tmp_path, _active(_followed()), world, shadow=True) as (owner, store):
            record: SubscriptionRecord = _checked(owner, store)
            saved: WatchState = owner._on_owner(store.load)
            listed: ControlResponse = _ask(owner, "subscriptions_list", command_id="list")
    finally:
        loguru_logger.remove(handler)

    assert record.last_check is not None
    assert (record.last_check.number, record.last_check.outcome) == (23, "proposed")
    assert record.last_check.matching > 0
    assert [(item.number, item.state) for item in record.targets] == [
        (23, TargetState.DUE),
        (24, TargetState.AWAITING_AIRING),
    ]
    assert record.checked_at == _NOW.isoformat()
    assert saved.acquisitions == ()
    assert listed.result["shadow"] is True
    assert (world.episodes.asked, world.titles.scheduled, world.streams.asked) == ([_S4], [_S4], [(_KITSU, 23)])
    decisions: list[dict[str, object]] = _decisions(tmp_path)
    assert [(item["kind"], item.get("source"), item["entry"]) for item in decisions] == [
        ("check", "ani.zip", "shadow"),
        ("check", "torrentio", "shadow"),
        ("proposal", None, "shadow"),
    ]
    assert decisions[0]["mapping_source"] == "live"
    assert decisions[1]["result"] == "match"
    assert decisions[2]["key"] == {"anilist_id": _S4, "number": 23}
    assert logged == [
        {
            "logger_name": "anishift.application.automation",
            "subscription_id": "a",
            "number": 23,
            "match": record.last_check.matching,
            "uncertain": record.last_check.uncertain,
            "mismatch": record.last_check.mismatched,
            "decision": "proposed",
        }
    ]


def test_a_failing_subscription_never_stops_the_check_of_the_next_one(tmp_path: Path) -> None:
    class Broken(_EpisodeCatalog):
        def mapping(self, anilist_id: int) -> AniZipMapping:
            if anilist_id == 1:
                raise RuntimeError(anilist_id)
            return super().mapping(anilist_id)

    world: _World = _World()
    world.catalog = Broken({_S4: _mapping(max_age_s=0)})
    broken: SubscriptionRecord = _followed("b", anilist_id=1, title="Broken", kitsu_id=1)
    with _following(tmp_path, _active(broken, _followed()), world) as (owner, store):
        failed: SubscriptionRecord = _checked(owner, store, "b")
        checked: SubscriptionRecord = _checked(owner, store, "a")

    assert failed.last_check is not None
    assert (failed.last_check.outcome, failed.checked_at) == ("source_failed", None)
    assert checked.last_check is not None
    assert checked.last_check.outcome == "proposed"


def test_a_rate_limited_source_blocks_its_provider_and_postpones_the_check_without_consuming_it(
    tmp_path: Path,
) -> None:
    world: _World = _World()
    world.control = RequestControl(
        httpx.MockTransport(lambda request: httpx.Response(429, headers={"retry-after": "600"})),
        clock=world.clock,
        sleep=lambda delay: None,
    )
    with httpx.Client(transport=world.control) as http:
        world.streams = cast("_StreamSource", TorrentioSource(http))
        with _following(tmp_path, _active(_followed()), world) as (owner, store):
            record: SubscriptionRecord = _checked(owner, store)
            retry: datetime | None = owner._on_owner(lambda: owner._subscription_due(record, world.now()))
            saved: WatchState = owner._on_owner(store.load)

    until: datetime = _NOW + timedelta(seconds=600)
    assert record.last_check is not None
    assert (record.last_check.outcome, record.last_check.number, record.checked_at) == ("rate_limited", 23, None)
    assert retry == until
    assert [(item.provider, item.until) for item in saved.provider_locks] == [("torrentio", until.isoformat())]
    assert saved.acquisitions == ()
    assert [(item["source"], item["result"]) for item in _decisions(tmp_path)] == [
        ("ani.zip", "length"),
        ("torrentio", "429"),
    ]


class _LateFailure(_StreamSource):
    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        if number == 23:
            raise OSError(number)
        return super().streams(kitsu_id, number)


def test_a_later_episode_failure_is_the_check_result_and_every_outcome_is_logged(tmp_path: Path) -> None:
    world: _World = _World()
    world.streams = _LateFailure(_slime_streams().answers)
    logged: list[dict[str, object]] = []
    handler: int = loguru_logger.add(
        lambda message: logged.append(dict(message.record["extra"])),
        filter=lambda record: record["message"] == "Subscription checked",
    )
    record: SubscriptionRecord = _followed(subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21)
    try:
        with _following(tmp_path, _active(record), world) as (owner, store):
            checked: SubscriptionRecord = _checked(owner, store)
    finally:
        loguru_logger.remove(handler)

    assert checked.last_check is not None
    assert (checked.last_check.number, checked.last_check.outcome) == (23, "source_failed")
    assert [(item["number"], item["decision"]) for item in logged] == [(22, "no_candidates"), (23, "source_failed")]
    assert all(item["subscription_id"] == "a" for item in logged)


class _HeldStreams(_StreamSource):
    def __init__(self, answers: Mapping[tuple[int, int | None], tuple[StreamCandidate, ...]]) -> None:
        super().__init__(answers)
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        self.entered.set()
        assert self.release.wait(_TIMEOUT_S)
        return super().streams(kitsu_id, number)


def test_a_requested_check_during_a_scheduled_one_gets_its_result_without_a_second_query(tmp_path: Path) -> None:
    world: _World = _World()
    held: _HeldStreams = _HeldStreams(_slime_streams().answers)
    world.streams = held
    events: list[Mapping[str, object]] = []
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        assert held.entered.wait(_TIMEOUT_S)
        owner._broadcast = lambda frame, terminal: events.append(frame)
        answer: ControlResponse = _ask(owner, "subscription_check", {"subscription_id": "a"}, "f")
        held.release.set()
        _checked(owner, store)

    assert answer.result == {"subscription_id": "a", "checking": True}
    checks: list[Mapping[str, object]] = [item for item in events if item.get("event") == "subscription_checked"]
    assert len(checks) == 1
    payload: object = checks[0]["payload"]
    assert isinstance(payload, Mapping)
    assert payload["subscription_id"] == "a"
    assert cast("Mapping[str, object]", payload["last_check"])["number"] == 23
    assert held.asked == [(_KITSU, 23)]


class _DownEpisodes(_EpisodeCatalog):
    def mapping(self, anilist_id: int) -> AniZipMapping:
        self.asked.append(anilist_id)
        raise TitleCatalogError(context=ErrorContext(code=ErrorCode.EPISODE_CATALOG_FAILED, message="down"))


@pytest.mark.parametrize("failure", ["exception", "404"])
def test_an_ani_zip_outage_checks_from_the_saved_mapping_also_after_a_restart(tmp_path: Path, failure: str) -> None:
    refreshed: str = (_NOW - timedelta(days=1)).isoformat()
    state: WatchState = _active(_followed(refreshed_at=refreshed))
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as http:
        world: _World = _World()
        world.catalog = AniZipCatalog(http) if failure == "404" else _DownEpisodes({})
        records: list[SubscriptionRecord] = []
        for _ in range(2):
            with _following(tmp_path, state, world, shadow=True) as (owner, store):
                _ask(owner, "subscription_check", {"subscription_id": "a"}, f"check-{len(records)}")
                _settled(owner)
                records.append(owner._on_owner(store.load).subscriptions[0])

    for record in records:
        assert record.last_check is not None
        assert record.last_check.outcome == "proposed"
        assert (record.mapping, record.refreshed_at, record.problem) == (_mapping(max_age_s=None), refreshed, None)
    sources: list[object] = [
        item.get("mapping_source") for item in _decisions(tmp_path) if item.get("source") == "ani.zip"
    ]
    assert sources
    assert set(sources) == {"snapshot"}


def _add(owner: AutomationOwner, command_id: str = "add", anilist_id: int = _S4) -> ControlResponse:
    return _ask(owner, "subscription_add", {"anilist_id": anilist_id}, command_id)


def test_adding_a_releasing_season_saves_its_cut_mapping_and_future_targets_once(tmp_path: Path) -> None:
    world: _World = _World()
    world.titles.schedules[_S4] = _airing()
    with _following(tmp_path, WatchState(policy=AutomationPolicy(auto_enabled=False)), world) as (owner, store):
        added: ControlResponse = _add(owner)
        repeated: ControlResponse = _add(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert added.ok
    assert added.result["from_number"] == 24
    assert repeated.result == added.result
    record: SubscriptionRecord = saved.subscriptions[0]
    assert (record.subscription_id, record.cut, record.kitsu_id) == (added.result["subscription_id"], 23, _KITSU)
    assert record.mapping == _mapping(max_age_s=None)
    assert [(item.number, item.state) for item in record.targets] == [(24, TargetState.AWAITING_AIRING)]
    assert record.subscribed_at == _NOW.isoformat()
    assert "add" in {item.command_id for item in saved.command_receipts}


def test_adding_an_announced_season_without_dates_targets_every_episode(tmp_path: Path) -> None:
    world: _World = _World()
    world.titles.schedules[_S4] = replace(_airing(TitleStatus.NOT_YET_RELEASED, dated=False), episode_count=None)
    with _following(tmp_path, WatchState(policy=AutomationPolicy(auto_enabled=False)), world) as (owner, store):
        added: ControlResponse = _add(owner)
        record: SubscriptionRecord = owner._on_owner(store.load).subscriptions[0]

    assert added.result["from_number"] == 1
    assert record.targets
    assert {item.state for item in record.targets} == {TargetState.AWAITING_AIRING}
    assert record.targets[0].number == 1


@pytest.mark.parametrize(
    ("schedule", "state", "catalog", "reason"),
    [
        (_airing(TitleStatus.FINISHED), WatchState(), None, "subscription_not_airing"),
        (_airing(TitleStatus.HIATUS, dated=False), WatchState(), None, "subscription_cut_unknown"),
        (_airing(), WatchState(subscriptions=(_followed(),)), None, "subscription_exists"),
        (
            _airing(),
            WatchState(
                subscriptions=tuple(
                    _followed(f"s{index}", anilist_id=1000 + index) for index in range(MAX_SUBSCRIPTIONS)
                )
            ),
            None,
            "subscription_limit",
        ),
        (_airing(), WatchState(), "down", "source_failed"),
    ],
    ids=["finished", "hiatus-undated", "duplicate", "limit", "new-title-without-ani-zip"],
)
def test_an_impossible_addition_is_refused_without_a_write(
    tmp_path: Path, schedule: SeasonAiring, state: WatchState, catalog: str | None, reason: str
) -> None:
    world: _World = _World()
    world.titles.schedules[_S4] = schedule
    world.catalog = _DownEpisodes({}) if catalog == "down" else None
    paused: WatchState = replace(state, policy=AutomationPolicy(auto_enabled=False))
    with _following(tmp_path, paused, world) as (owner, store):
        answer: ControlResponse = _add(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == reason
    assert saved.subscriptions == paused.subscriptions
    assert "add" not in {item.command_id for item in saved.command_receipts}


def _migrated(**changes: object) -> SubscriptionRecord:
    return replace(
        _followed(
            cut=None,
            kitsu_id=None,
            mapping=None,
            subscribed_at=(_NOW - 10 * _WEEK).isoformat(),
            migrated_at=(_NOW - _WEEK).isoformat(),
            review_pending=True,
        ),
        **changes,  # type: ignore[arg-type]
    )


def test_a_paused_migrated_record_is_refreshed_and_its_review_finishes_on_complete_live_data(tmp_path: Path) -> None:
    record: SubscriptionRecord = _migrated(paused=True, pause_reason=PauseReason.USER)
    with _following(tmp_path, _active(record), _World()) as (owner, store):
        reviewed: SubscriptionRecord = _checked(owner, store)

    assert (reviewed.review_pending, reviewed.paused, reviewed.pause_reason) == (False, True, PauseReason.USER)
    assert (reviewed.kitsu_id, reviewed.mapping) == (_KITSU, _mapping(max_age_s=None))
    assert reviewed.last_check is not None
    assert reviewed.last_check.outcome == "refreshed"
    assert [item.number for item in reviewed.targets] == list(range(14, 25))


def test_a_late_review_keeps_a_target_aired_after_migration_unpaused(tmp_path: Path) -> None:
    record: SubscriptionRecord = _migrated(migrated_at=(_NOW - timedelta(hours=2)).isoformat())
    with _following(tmp_path, _active(record), _World()) as (owner, store):
        reviewed: SubscriptionRecord = _checked(owner, store)

    assert (reviewed.review_pending, reviewed.paused) == (False, True)
    assert reviewed.pause_reason is PauseReason.MIGRATED_DUE
    late: SubscriptionRecord = _migrated(
        subscribed_at=(_NOW - timedelta(hours=3)).isoformat(), migrated_at=(_NOW - timedelta(hours=2)).isoformat()
    )
    with _following(tmp_path / "late", _active(late), _World(), shadow=True) as (owner, store):
        kept: SubscriptionRecord = _checked(owner, store)

    assert (kept.review_pending, kept.paused) == (False, False)
    assert [(item.number, item.state) for item in kept.targets] == [
        (23, TargetState.DUE),
        (24, TargetState.AWAITING_AIRING),
    ]


@pytest.mark.parametrize("failure", ["schedule", "snapshot"])
def test_an_incomplete_review_read_keeps_the_review_and_retries_it_after_a_restart(
    tmp_path: Path, failure: str
) -> None:
    world: _World = _World()
    down: _DownEpisodes = _DownEpisodes({})
    record: SubscriptionRecord = _migrated()
    if failure == "schedule":
        world.titles.schedule_fails = True
    else:
        world.catalog = down
        record = replace(record, kitsu_id=_KITSU, mapping=_mapping(max_age_s=None))
    reads: list[int] = world.titles.scheduled if failure == "schedule" else down.asked
    for attempt in range(1, 3):
        with _following(tmp_path, _active(record), world) as (owner, store):
            assert _await(lambda: len(reads) >= attempt)  # noqa: B023
            _settled(owner)
            retry: tuple[int, datetime] | None = owner._on_owner(lambda: owner._subscription_retries.get("a"))
            saved: SubscriptionRecord = owner._on_owner(store.load).subscriptions[0]
        assert (saved.review_pending, saved.targets, saved.migrated_at) == (True, (), record.migrated_at)
        assert retry == (1, _NOW + timedelta(seconds=60))
    assert len(reads) == 2


def test_a_catalog_conflict_has_a_repair_deadline_and_a_consistent_live_read_clears_it(tmp_path: Path) -> None:
    other: SubscriptionRecord = _followed(kitsu_id=1, mapping=_mapping(kitsu_id=1, max_age_s=None))
    with _following(tmp_path, _active(other), _World()) as (owner, store):
        conflicted: SubscriptionRecord = _checked(owner, store)
        retry: tuple[int, datetime] | None = owner._on_owner(lambda: owner._subscription_retries.get("a"))
        deadline: datetime | None = owner._on_owner(lambda: owner._subscription_due(conflicted, _NOW))

    assert conflicted.problem is SubscriptionProblem.CATALOG_CONFLICT
    assert conflicted.targets == ()
    assert retry == (1, _NOW + timedelta(seconds=60))
    assert deadline == _NOW + timedelta(seconds=60)
    repaired: SubscriptionRecord = _followed(problem=SubscriptionProblem.CATALOG_CONFLICT)
    with _following(tmp_path / "repaired", _active(repaired), _World()) as (owner, store):
        cleared: SubscriptionRecord = _checked(owner, store)

    assert cleared.problem is None


def test_the_owner_schedules_the_next_check_and_runs_it_once_the_clocks_reach_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks: list[float] = [1000.0]
    monkeypatch.setattr(automation_module, "time", SimpleNamespace(monotonic=lambda: ticks[0]))
    world: _World = _World()
    checked: SubscriptionRecord = _followed(
        checked_at=_NOW.isoformat(),
        targets=(SubscriptionTarget(24, (_NOW + timedelta(hours=2)).isoformat(), TargetState.AWAITING_AIRING),),
    )
    with _following(tmp_path, _active(checked), world) as (owner, store):
        scheduled: float | None = owner._on_owner(lambda: owner._subscriptions_at)
        world.clock.now += 2 * 3600
        ticks[0] += 2 * 3600
        _ask(owner, "subscriptions_list", command_id="wake")
        record: SubscriptionRecord = _checked(owner, store)
        paused: ControlResponse = _ask(owner, "set_auto", {"enabled": False}, "pause")
        idle: float | None = owner._on_owner(lambda: owner._subscriptions_at)

    assert scheduled == 1000.0 + 2 * 3600
    assert record.checked_at == (_NOW + timedelta(hours=2)).isoformat()
    assert world.titles.scheduled == [_S4]
    assert paused.ok
    assert idle is None


def test_a_globally_paused_owner_checks_nothing_on_its_own(tmp_path: Path) -> None:
    world: _World = _World()
    state: WatchState = WatchState(policy=AutomationPolicy(auto_enabled=False), subscriptions=(_followed(),))
    with _following(tmp_path, state, world) as (owner, store):
        scheduled: float | None = owner._on_owner(lambda: owner._subscriptions_at)
        manual: ControlResponse = _ask(owner, "subscription_check", {"subscription_id": "a"}, "check")
        record: SubscriptionRecord = _checked(owner, store)

    assert scheduled is None
    assert manual.result == {"subscription_id": "a", "checking": True}
    assert record.last_check is not None
    assert record.last_check.outcome == "refreshed"
    assert world.streams.asked == []


def test_the_list_and_details_of_the_largest_subscriptions_fit_in_one_frame(tmp_path: Path) -> None:
    title: str = "Ż" * 200
    specials: tuple[ListedSpecial, ...] = tuple(ListedSpecial(f"S{index}", "Ś" * 120, None) for index in range(300))
    huge: SubscriptionRecord = _followed(
        "huge",
        title=title,
        cut=0,
        mapping=_mapping(max_age_s=None, specials=specials),
        targets=tuple(
            SubscriptionTarget(number, (_NOW + number * _WEEK).isoformat(), TargetState.AWAITING_AIRING)
            for number in range(1, 2001)
        ),
        last_check=SubscriptionCheck(_NOW.isoformat(), 2000, 999, 999, 999, "no_match"),
    )
    rows: tuple[SubscriptionRecord, ...] = tuple(
        replace(huge, subscription_id=f"s{index:03}", anilist_id=5000 + index, problem=None)
        for index in range(MAX_SUBSCRIPTIONS - 1)
    )
    state: WatchState = WatchState(policy=AutomationPolicy(auto_enabled=False), subscriptions=(*rows, huge))
    with _following(tmp_path, state, _World()) as (owner, _):
        listed: ControlResponse = _ask(owner, "subscriptions_list", command_id="list")
        details: ControlResponse = _ask(owner, "subscription_get", {"subscription_id": "huge"}, "get")

    for answer in (listed, details):
        assert answer.ok
        assert len(json.dumps(answer.result, ensure_ascii=False).encode()) < MAX_FRAME_BYTES // 2
    assert len(details.result["specials"]) == 300  # type: ignore[arg-type]


def _attempt(state: WatchState, number: int) -> tuple[AcquisitionConfirmation, EpisodeAssignment]:
    return next(
        (transfer, assignment)
        for transfer in state.acquisitions
        for assignment in transfer.assignments
        if assignment.choice.number == number and assignment.source is AdmissionSource.SUBSCRIPTION
    )


def test_a_due_check_admits_one_attempt_and_a_restarted_check_admits_no_second(tmp_path: Path) -> None:
    world: _World = _World()
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        listed: ControlResponse = _ask(owner, "subscriptions_list", command_id="list")
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert listed.result["shadow"] is False
    transfer, assignment = _attempt(saved, 23)
    assert len(saved.acquisitions) == 1
    assert (assignment.subscription_id, assignment.attempt, assignment.previous_admission_id) == ("a", 1, None)
    assert transfer.origin is RequestOrigin.BACKGROUND
    assert not transfer.manual
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.number, target.state, target.attempts) == (23, TargetState.ATTEMPTING, 1)
    assert target.admission_id == assignment.admission_id
    assert target.tried == (f"{assignment.choice.reference.info_hash}:{assignment.choice.reference.file_index}",)
    assert "sub:a:23:1" in {item.command_id for item in saved.command_receipts}
    assert world.streams.asked == [(_KITSU, 23)]
    entries: list[tuple[object, object]] = [(item["kind"], item["entry"]) for item in _decisions(tmp_path)]
    assert entries.count(("selection", "subscription")) == 1
    assert ("proposal", "shadow") not in entries


def _closed_attempt(admission_id: str = "attempt-1") -> AcquisitionConfirmation:
    choice: EpisodeChoice = EpisodeChoice(
        _S4,
        23,
        TorrentioReference("0" * 40, 0, "Old - 23.mkv", "[Old] Slime", ()),
        {"local_episode": 23},
        IdentityVerdict.MATCH,
        "match",
    )
    assignment: EpisodeAssignment = EpisodeAssignment(
        admission_id,
        _NOW.isoformat(),
        AdmissionSource.SUBSCRIPTION,
        choice,
        replaced=True,
        subscription_id="a",
        attempt=1,
    )
    return AcquisitionConfirmation(
        operation_id="old-operation",
        info_hash="0" * 40,
        directory="",
        required_files=(),
        state=AcquisitionState.ACCEPTED,
        origin=RequestOrigin.BACKGROUND,
        subscription_id=None,
        episode="23",
        updated_at=_NOW.isoformat(),
        assignments=(assignment,),
        selection_revision=2,
    )


def test_the_next_attempt_replaces_the_closed_one_still_held_by_a_shared_transfer(tmp_path: Path) -> None:
    closed: SubscriptionTarget = SubscriptionTarget(
        23, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE, 1, ("0" * 40 + ":0",), "attempt-1", "replaced"
    )
    state: WatchState = replace(_active(_followed(targets=(closed,))), acquisitions=(_closed_attempt(),))
    with _following(tmp_path, state, _World()) as (owner, store):
        _checked(owner, store)
        saved: WatchState = owner._on_owner(store.load)

    _transfer, assignment = _latest(saved)
    assert (assignment.attempt, assignment.previous_admission_id) == (2, "attempt-1")
    old: AcquisitionConfirmation = next(item for item in saved.acquisitions if item.operation_id == "old-operation")
    assert old.selection_revision == 2
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.attempts, target.admission_id) == (
        TargetState.ATTEMPTING,
        2,
        assignment.admission_id,
    )
    assert "sub:a:23:2" in {item.command_id for item in saved.command_receipts}


def _latest(state: WatchState) -> tuple[AcquisitionConfirmation, EpisodeAssignment]:
    return next(
        (transfer, assignment)
        for transfer in reversed(state.acquisitions)
        for assignment in transfer.assignments
        if assignment.choice.number == 23
    )


def test_a_manual_order_replaces_an_active_attempt_and_its_target_follows_the_order(tmp_path: Path) -> None:
    world: _World = _World()
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        attempt: EpisodeAssignment = _attempt(owner.state, 23)[1]
        manual: EpisodeChoice = replace(
            attempt.choice, reference=replace(attempt.choice.reference, info_hash="f" * 40, file_index=7)
        )
        replaced: ControlResponse = owner._on_owner(
            lambda: owner._admit_episode("manual", manual, previous=attempt.admission_id)
        )
        saved: WatchState = owner._on_owner(store.load)

    assert replaced.ok
    assert _attempt(saved, 23)[1].replaced
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.attempts) == (TargetState.MANUAL, 1)
    closures: list[object] = [item.get("attempt_result") for item in _decisions(tmp_path) if item["kind"] == "attempt"]
    assert closures == ["replaced"]


def test_a_target_unreleased_a_week_after_airing_is_reported_once(tmp_path: Path) -> None:
    world: _World = _World()
    world.streams = _StreamSource({})
    week_late: SeasonAiring = replace(
        _airing(),
        episodes=tuple(
            EpisodeAiring(number, _NOW - 8 * timedelta(days=1) + (number - 23) * _WEEK) for number in range(1, 25)
        ),
    )
    world.titles.schedules[_S4] = week_late
    record: SubscriptionRecord = _followed(subscribed_at=(_NOW - timedelta(days=10)).isoformat())
    with _following(tmp_path, _active(record), world) as (owner, store):
        first: SubscriptionRecord = _checked(owner, store)
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert [(item.number, item.notified_late) for item in first.targets] == [(23, True), (24, False)]
    assert ("subscription:a:23", "late", "") in saved.notified
    escalations: list[dict[str, object]] = [item for item in _decisions(tmp_path) if item["kind"] == "escalation"]
    assert [(item["key"], item["reason"]) for item in escalations] == [({"anilist_id": _S4, "number": 23}, "late")]
    assert saved.acquisitions == ()
