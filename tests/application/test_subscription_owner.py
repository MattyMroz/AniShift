from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator, Mapping
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
    _Bridges,
    _Clock,
    _episode_service,
    _EpisodeCatalog,
    _FailingStreams,
    _slime_streams,
    _StreamSource,
    _TitleCatalog,
)
from test_automation import _INSTANCE, _MOMENT, _TIMEOUT_S, _await, _library, _owner, _request, _serving
from test_episode_search import controlled, search_service
from test_episode_search import empty_response as _empty_response
from test_episode_selection import _fixture_graph, _fixture_mapping, _stream

from anishift.application import AppService
from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, ListingRead
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AutomationPolicy,
    ChoiceTraits,
    EpisodeAssignment,
    EpisodeChoice,
    LegacyOrder,
    NotificationKey,
    TorrentioReference,
    WatchState,
    compact_acquisition,
)
from anishift.application.control_views import decode_view
from anishift.application.episode_commands import EpisodeStatus, TargetNotice
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_search import EpisodeSearch, SourceSwitches
from anishift.application.episode_selection import AniZipMapping, EpisodeKey, ListedSpecial, StreamCandidate
from anishift.application.intents import RequestOrigin
from anishift.application.release_quality import PolishClass, ResolutionClass
from anishift.application.subscription_choice import release_hash
from anishift.application.subscription_targets import (
    MAX_SUBSCRIPTIONS,
    Blocker,
    PauseReason,
    PolishObservation,
    PolishSkip,
    PolishState,
    SubscriptionCheck,
    SubscriptionProblem,
    SubscriptionRecord,
    SubscriptionRow,
    SubscriptionTarget,
    TargetState,
    next_check_at,
    next_search_at,
)
from anishift.application.subscriptions import Subscription, SubscriptionStore
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.local_control import MAX_FRAME_BYTES, ControlErrorCode, ControlResponse
from anishift.services.catalog import EpisodeAiring, SeasonAiring, TitleCatalogError, TitleStatus
from anishift.services.catalog.anizip import AniZipCatalog
from anishift.services.catalog.arm import ArmIds
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
    bridges: _Bridges | None = None
    search: EpisodeSearch | None = None
    polish_wait_h: int = 0

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
    service.user_settings = UserSettings(subscription_polish_wait_h=world.polish_wait_h)
    service.acquisition = _episode_service(
        tmp_path,
        world.titles,
        cast("_EpisodeCatalog", world.catalog) if world.catalog is not None else world.episodes,
        world.streams,
        clock=world.clock,
        request_control=world.control,
    )
    if world.bridges is not None:
        service.acquisition._id_catalog = world.bridges
        service.acquisition._anidb_catalog = world.bridges
        service.acquisition._kitsu_catalog = world.bridges
    if world.search is not None:
        service.acquisition._episode_search = world.search
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
        ("polish", None, "shadow"),
        ("proposal", None, "shadow"),
    ]
    assert decisions[0]["mapping_source"] == "live"
    assert decisions[1]["result"] == "match"
    assert (decisions[2]["result"], decisions[2]["reason"]) == ("unknown", "no_polish_after_wait")
    assert decisions[3]["key"] == {"anilist_id": _S4, "number": 23}
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


class _EarlyFailure(_StreamSource):
    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        if number == 22:
            raise OSError(number)
        return super().streams(kitsu_id, number)


def test_a_failing_target_never_stops_the_check_of_the_next_due_one(tmp_path: Path) -> None:
    world: _World = _World()
    world.streams = _EarlyFailure(_slime_streams().answers)
    record: SubscriptionRecord = _followed(subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21)
    with _following(tmp_path, _active(record), world, shadow=True) as (owner, store):
        checked: SubscriptionRecord = _checked(owner, store)

    targets: dict[int, SubscriptionTarget] = {item.number: item for item in checked.targets}
    assert checked.last_check is not None
    assert (checked.last_check.number, checked.last_check.outcome, checked.checked_at) == (22, "source_failed", None)
    assert world.streams.asked == [(_KITSU, 23)]
    assert targets[22].sources_down_since == _NOW.isoformat()
    assert targets[23].sources_down_since is None
    assert [item["key"] for item in _decisions(tmp_path) if item["kind"] == "proposal"] == [
        {"anilist_id": _S4, "number": 23}
    ]


@pytest.mark.parametrize(("answer", "checked_at"), [("empty", _NOW.isoformat()), ("transport", None)])
def test_an_empty_ani_zip_answer_is_a_check_but_a_transport_failure_is_not(
    tmp_path: Path, answer: str, checked_at: str | None
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if answer == "transport":
            message: str = "unreachable"
            raise httpx.ConnectError(message, request=request)
        return httpx.Response(200, json={"episodes": {}, "mappings": {}})

    record: SubscriptionRecord = _followed(kitsu_id=None, mapping=None)
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        world: _World = _World()
        world.catalog = AniZipCatalog(http)
        with _following(tmp_path, _active(record), world, shadow=True) as (owner, store):
            checked: SubscriptionRecord = _checked(owner, store)
            retry: tuple[int, datetime] | None = owner._on_owner(lambda: owner._subscription_retries.get("a"))

    assert checked.checked_at == checked_at
    assert (retry is None) is (checked_at is not None)


def test_an_unavailable_target_never_stops_the_check_of_the_next_due_one(tmp_path: Path) -> None:
    answer: str = (Path(__file__).parents[1] / "fixtures" / "search" / "torrentio__kitsu-49235-23.json").read_text(
        encoding="utf-8"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "torrentio.strem.fun" and request.url.path.endswith(":23.json"):
            return httpx.Response(200, text=answer, headers={"content-type": "application/json"})
        return httpx.Response(500)

    world: _World = _World()
    control: RequestControl = controlled(respond)
    record: SubscriptionRecord = _followed(subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21)
    with httpx.Client(transport=control) as http:
        world.search = search_service(http, control)
        with _following(tmp_path, _active(record), world, shadow=True) as (owner, store):
            checked: SubscriptionRecord = _checked(owner, store)

    targets: dict[int, SubscriptionTarget] = {item.number: item for item in checked.targets}
    assert checked.checked_at == _NOW.isoformat()
    assert (targets[22].state, targets[22].sources_down_since) == (TargetState.DUE, _NOW.isoformat())
    assert (targets[23].state, targets[23].sources_down_since) == (TargetState.DUE, None)
    assert [item["key"] for item in _decisions(tmp_path) if item["kind"] == "proposal"] == [
        {"anilist_id": _S4, "number": 23}
    ]


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
    assert repeated.result == added.result
    record: SubscriptionRecord = saved.subscriptions[0]
    assert added.result == {"subscription_id": record.subscription_id}
    assert (record.subscription_id, record.cut, record.kitsu_id) == (added.result["subscription_id"], 23, _KITSU)
    assert record.mapping == _mapping(max_age_s=None)
    assert [(item.number, item.state) for item in record.targets] == [(24, TargetState.AWAITING_AIRING)]
    assert record.subscribed_at == _NOW.isoformat()
    assert "add" in {item.command_id for item in saved.command_receipts}


def _next_searches() -> tuple[list[dict[str, object]], int]:
    logged: list[dict[str, object]] = []
    handler: int = loguru_logger.add(
        lambda message: logged.append(dict(message.record["extra"])),
        filter=lambda record: record["message"] == "Subscription next search",
    )
    return logged, handler


def test_adding_and_checking_a_subscription_log_its_next_search_once_each(tmp_path: Path) -> None:
    logged, handler = _next_searches()
    try:
        with _following(tmp_path, _active(), _World(), shadow=True) as (owner, store):
            added: ControlResponse = _add(owner)
            _add(owner)
            record: SubscriptionRecord = _checked(owner, store, str(added.result["subscription_id"]))
    finally:
        loguru_logger.remove(handler)

    following: datetime | None = next_check_at(record, _NOW)
    assert following is not None
    assert [(item["number"], item["at"]) for item in logged] == [(24, _NOW.isoformat()), (24, following.isoformat())]
    assert {(item["subscription_id"], item["anilist_id"]) for item in logged} == {(record.subscription_id, _S4)}


def test_adding_an_announced_season_without_dates_targets_every_episode(tmp_path: Path) -> None:
    world: _World = _World()
    world.titles.schedules[_S4] = replace(_airing(TitleStatus.NOT_YET_RELEASED, dated=False), episode_count=None)
    with _following(tmp_path, WatchState(policy=AutomationPolicy(auto_enabled=False)), world) as (owner, store):
        added: ControlResponse = _add(owner)
        record: SubscriptionRecord = owner._on_owner(store.load).subscriptions[0]

    assert added.ok
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


def _renumbered(numbers: Mapping[str, Mapping[str, int | None]]) -> AniZipMapping:
    base: AniZipMapping = _mapping(max_age_s=None)
    raw: dict[str, dict[str, object]] = {key: dict(value) for key, value in base.raw_episodes.items()}
    for key, fields in numbers.items():
        raw[key].update(fields)
    return replace(base, raw_episodes=raw)


def _seasoned(season: int) -> AniZipMapping:
    return _renumbered({str(number): {"seasonNumber": season} for number in range(1, 25)})


def _two_sessions(
    tmp_path: Path, record: SubscriptionRecord, world: _World, *, shadow: bool = False
) -> tuple[SubscriptionRecord, WatchState]:
    with _following(tmp_path, _active(record), world, shadow=shadow) as (owner, store):
        first: SubscriptionRecord = _checked(owner, store)
    with _following(tmp_path, _active(record), world) as (owner, store):
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)
    return first, saved


def test_numbering_conflict_blocks_attempts_after_restart(tmp_path: Path) -> None:
    world: _World = _World()
    stored: AniZipMapping = _renumbered({"23": {"episodeNumber": 99}})

    first, saved = _two_sessions(tmp_path, _followed(mapping=stored), world)

    for record in (first, saved.subscriptions[0]):
        assert (record.problem, record.mapping, record.targets) == (SubscriptionProblem.CATALOG_CONFLICT, stored, ())
    assert saved.acquisitions == ()
    assert world.streams.asked == []


@pytest.mark.parametrize(
    "numbers",
    [
        {"23": {"seasonNumber": None, "episodeNumber": None, "absoluteEpisodeNumber": None}},
        {"23": {"episodeNumber": 22, "absoluteEpisodeNumber": 94}},
    ],
    ids=["filled", "duplicate"],
)
def test_numbering_filled_after_restart_not_conflict(
    tmp_path: Path, numbers: Mapping[str, Mapping[str, int | None]]
) -> None:
    first, saved = _two_sessions(tmp_path, _followed(mapping=_renumbered(numbers)), _World(), shadow=True)

    record: SubscriptionRecord = saved.subscriptions[0]
    assert (first.problem, record.problem, record.mapping) == (None, None, _mapping(max_age_s=None))
    _transfer, assignment = _attempt(saved, 23)
    assert assignment.choice.traits is not None
    target: SubscriptionTarget = record.targets[0]
    assert (target.number, target.state, target.attempts, target.started) == (23, TargetState.ATTEMPTING, 1, 1)


_UNNUMBERED: dict[str, dict[str, int | None]] = {
    "23": {"seasonNumber": None, "episodeNumber": None, "absoluteEpisodeNumber": None}
}


def _named(file_name: str) -> StreamCandidate:
    return _stream(file_name, release=file_name, seeders=20)


def _unnumbered_world(file_name: str) -> _World:
    return _World(
        episodes=_EpisodeCatalog({_S4: replace(_renumbered(_UNNUMBERED), max_age_s=0)}),
        streams=_StreamSource({(_KITSU, 23): (_named(file_name),)}),
    )


@pytest.mark.parametrize(
    ("file_name", "admitted"),
    [
        ("[SubsPlease] Tensei shitara Slime Datta Ken 4th Season - 23 (1080p).mkv", True),
        ("[SubsPlease] Tensei shitara Slime Datta Ken S04E23 (1080p).mkv", False),
    ],
    ids=["entry-title", "sxxexx-only"],
)
def test_no_numbering_decides_on_entry_title(tmp_path: Path, file_name: str, *, admitted: bool) -> None:
    world: _World = _unnumbered_world(file_name)
    record: SubscriptionRecord = _followed(mapping=_renumbered(_UNNUMBERED))
    with _following(tmp_path, _active(record), world) as (owner, store):
        checked: SubscriptionRecord = _checked(owner, store)
        saved: WatchState = owner._on_owner(store.load)

    target: SubscriptionTarget = checked.targets[0]
    assert checked.problem is None
    assert (target.number, target.failures) == (23, ())
    if admitted:
        assert (target.state, target.attempts) == (TargetState.ATTEMPTING, 1)
        assert _attempt(saved, 23)[1].choice.reference.release == file_name
        return
    assert (target.state, target.attempts) == (TargetState.DUE, 0)
    assert saved.acquisitions == ()
    assert next_search_at(target, world.now()) is not None


def test_numbering_appears_on_next_check(tmp_path: Path) -> None:
    file_name: str = "[SubsPlease] Tensei shitara Slime Datta Ken S04E23 (1080p).mkv"
    world: _World = _unnumbered_world(file_name)
    record: SubscriptionRecord = _followed(mapping=_renumbered(_UNNUMBERED))
    with _following(tmp_path, _active(record), world) as (owner, store):
        first: SubscriptionRecord = _checked(owner, store)
        world.episodes.mappings[_S4] = _mapping(max_age_s=0)
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert (first.targets[0].state, first.targets[0].attempts) == (TargetState.DUE, 0)
    record = saved.subscriptions[0]
    assert (record.problem, record.mapping) == (None, _mapping(max_age_s=None))
    assert (record.targets[0].state, record.targets[0].attempts) == (TargetState.ATTEMPTING, 1)
    assert _attempt(saved, 23)[1].choice.reference.release == file_name


@pytest.mark.parametrize(
    ("saved_season", "bridge", "conflict"),
    [(4, None, False), (1, ArmIds(None, 4), True)],
    ids=["A-bridge-down", "B-bridge-season"],
)
def test_bridge_season_scenarios_after_restart(
    tmp_path: Path, saved_season: int, bridge: ArmIds | None, conflict: bool
) -> None:
    world: _World = _World(bridges=_Bridges(bridge))
    stored: SubscriptionRecord = _followed(mapping=_seasoned(1), mapping_tvdb_season=saved_season)

    first, saved = _two_sessions(tmp_path, stored, world, shadow=True)

    record: SubscriptionRecord = saved.subscriptions[0]
    if conflict:
        for checked in (first, record):
            assert (checked.problem, checked.mapping, checked.mapping_tvdb_season) == (
                SubscriptionProblem.CATALOG_CONFLICT,
                _seasoned(1),
                1,
            )
        assert saved.acquisitions == ()
        return
    assert (first.problem, record.problem) == (None, None)
    assert (record.mapping, record.mapping_tvdb_season) == (_mapping(max_age_s=None), None)
    assert _attempt(saved, 23)[1].choice.number == 23


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
    assert target.tried == (assignment.choice.reference.info_hash,)
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
        23,
        (_NOW - timedelta(hours=1)).isoformat(),
        TargetState.DUE,
        1,
        ("0" * 40 + ":0",),
        "attempt-1",
        "replaced",
        started=1,
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


def test_an_admission_numbers_its_command_by_started_attempts_not_counted_ones(tmp_path: Path) -> None:
    due: SubscriptionTarget = SubscriptionTarget(
        23, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE, 0, started=5
    )
    with _following(tmp_path, _active(_followed(targets=(due,))), _World()) as (owner, store):
        _checked(owner, store)
        saved: WatchState = owner._on_owner(store.load)

    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.attempts, target.started) == (TargetState.ATTEMPTING, 1, 6)
    receipts: set[str] = {item.command_id for item in saved.command_receipts}
    assert "sub:a:23:6" in receipts
    assert "sub:a:23:1" not in receipts


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
    assert [(item["key"], item["reason"]) for item in escalations] == [
        ({"anilist_id": _S4, "number": 23}, "late"),
        ({"anilist_id": _S4, "number": 23}, "no_admissible"),
        ({"anilist_id": _S4, "number": 24}, "no_admissible"),
    ]
    assert saved.acquisitions == ()


def _status(owner: AutomationOwner, number: int = 23) -> EpisodeStatus:
    answer: ControlResponse = _ask(owner, "episode_states", {"anilist_id": _S4, "numbers": [number]}, "states")
    items: object = answer.result["items"]
    assert isinstance(items, list)
    return decode_view(EpisodeStatus, items[0])


def _now(owner: AutomationOwner, command_id: str = "now", number: int = 23) -> ControlResponse:
    return _ask(owner, "subscription_check", {"subscription_id": "a", "number": number}, command_id)


def test_a_due_target_without_polish_waits_and_shows_the_end_of_its_wait(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        record: SubscriptionRecord = _checked(owner, store)
        status: EpisodeStatus = _status(owner)

    assert record.last_check is not None
    assert (record.targets[0].state, record.last_check.outcome) == (TargetState.DUE, "no_match")
    assert record.targets[0].polish_skip is None
    assert (status.polish, status.polish_wait_until, status.polish_skipped) == (
        "unknown",
        (_NOW + timedelta(hours=1)).isoformat(),
        False,
    )
    polish: list[dict[str, object]] = [item for item in _decisions(tmp_path) if item["kind"] == "polish"]
    assert [(item["result"], item["source"], item["reason"]) for item in polish] == [
        ("unknown", None, "waiting_polish")
    ]


def test_download_now_admits_a_waiting_target_once_and_survives_a_restart(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        answer: ControlResponse = _now(owner)
        _settled(owner)
        repeated: ControlResponse = _now(owner)
        _settled(owner)
        status: EpisodeStatus = _status(owner)
        first: WatchState = owner._on_owner(store.load)
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert answer.result == {"subscription_id": "a", "checking": True, "number": 23}
    assert repeated.result == answer.result
    assert status.polish_wait_until is None
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.attempts) == (TargetState.ATTEMPTING, 1)
    assert target.polish_skip is not None
    assert (target.polish_skip.due, target.polish_skip.settled) == ((_NOW - timedelta(hours=1)).isoformat(), True)
    assert len(first.acquisitions) == len(saved.acquisitions) == 1
    skips: list[dict[str, object]] = [item for item in _decisions(tmp_path) if item["kind"] == "skip_polish_wait"]
    assert [(item["key"], item["due_at"], item["entry"]) for item in skips] == [
        ({"anilist_id": _S4, "number": 23}, target.polish_skip.due, "subscription")
    ]


def test_download_now_during_an_ongoing_check_admits_once(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    held: _HeldStreams = _HeldStreams(_slime_streams().answers)
    world.streams = held
    target: SubscriptionTarget = SubscriptionTarget(23, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE, 0)
    with _following(tmp_path, _active(_followed(targets=(target,))), world) as (owner, store):
        assert held.entered.wait(_TIMEOUT_S)
        answer: ControlResponse = _now(owner)
        held.release.set()
        assert _await(
            lambda: owner._on_owner(lambda: not owner._subscription_checks and not owner._subscription_requests)
        )
        saved: WatchState = owner._on_owner(store.load)

    assert answer.ok
    assert (saved.subscriptions[0].targets[0].state, len(saved.acquisitions)) == (TargetState.ATTEMPTING, 1)
    assert len(_attempts(saved)) == 1


def test_download_now_for_another_target_during_a_check_is_served_by_the_next_one(tmp_path: Path) -> None:
    def skip_of_23() -> PolishSkip | None:
        return next(item.polish_skip for item in owner.state.subscriptions[0].targets if item.number == 23)

    world: _World = _World(polish_wait_h=2)
    held: _HeldStreams = _HeldStreams({})
    world.streams = held
    targets: tuple[SubscriptionTarget, ...] = (
        SubscriptionTarget(22, (_NOW - timedelta(hours=1) - _WEEK).isoformat(), TargetState.DUE),
        SubscriptionTarget(23, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE),
    )
    record: SubscriptionRecord = _followed(
        subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21, targets=targets
    )
    with _following(tmp_path, _active(record), world) as (owner, store):
        assert held.entered.wait(_TIMEOUT_S)
        answer: ControlResponse = _now(owner)
        held.release.set()
        assert _await(lambda: owner._on_owner(lambda: (skip := skip_of_23()) is not None and skip.settled))
        _settled(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert answer.ok
    found: dict[int, SubscriptionTarget] = {item.number: item for item in saved.subscriptions[0].targets}
    skip: PolishSkip | None = found[23].polish_skip
    assert skip is not None
    assert (found[23].state, skip.settled, skip.tried) == (TargetState.DUE, True, False)
    assert held.asked.count((_KITSU, 23)) == 2
    assert world.clock.now == _NOW.timestamp()


def test_download_now_failing_its_search_returns_the_target_to_its_grid(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    world.streams = _FailingStreams()
    due: str = (_NOW - timedelta(hours=1)).isoformat()
    asked: str = (_NOW - timedelta(minutes=5)).isoformat()
    target: SubscriptionTarget = SubscriptionTarget(23, due, TargetState.DUE, polish_skip=PolishSkip(due, asked))
    with _following(tmp_path, _active(_followed(targets=(target,))), world) as (owner, store):
        checked: SubscriptionRecord = _checked(owner, store)

    skip: PolishSkip | None = checked.targets[0].polish_skip
    assert skip is not None
    assert (skip.settled, skip.tried) == (False, True)
    moment: datetime | None = next_search_at(checked.targets[0], None)
    assert moment == datetime.fromisoformat(due)


@pytest.mark.parametrize("seen", [None, PolishSkip("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")])
def test_a_check_whose_snapshot_lacks_the_skip_neither_settles_nor_tries_it(seen: PolishSkip | None) -> None:
    due: str = (_NOW - timedelta(hours=1)).isoformat()
    skip: PolishSkip = PolishSkip(due, (_NOW - timedelta(minutes=5)).isoformat())
    record: SubscriptionRecord = _followed(targets=(SubscriptionTarget(23, due, TargetState.DUE, polish_skip=skip),))

    for searched, tried in (([(23, seen)], []), ([], [(23, seen)])):
        assert automation_module._settled_skips(record, searched, tried) == record
    assert automation_module._settled_skips(record, [], [(23, skip)]).targets[0].polish_skip == replace(
        skip, tried=True
    )


def test_download_now_without_a_candidate_keeps_the_target_due_and_stops_its_wait(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    world.streams = _StreamSource({})
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        assert _now(owner).ok
        _settled(owner)
        status: EpisodeStatus = _status(owner)
        saved: WatchState = owner._on_owner(store.load)

    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, saved.acquisitions) == (TargetState.DUE, ())
    assert target.polish_skip is not None
    assert target.polish_skip.settled
    assert next_search_at(target, datetime.fromisoformat(saved.subscriptions[0].checked_at or "")) != _NOW
    assert (status.polish_wait_until, status.polish_skipped) == (None, True)


@pytest.mark.parametrize(("wait_h", "number"), [(0, 23), (2, 24), (2, 99)], ids=["no-wait", "awaiting", "unknown"])
def test_download_now_refuses_a_target_not_waiting_without_a_change(tmp_path: Path, wait_h: int, number: int) -> None:
    world: _World = _World(polish_wait_h=wait_h)
    world.streams = _StreamSource({})
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        before: WatchState = owner._on_owner(store.load)
        answer: ControlResponse = _now(owner, number=number)
        saved: WatchState = owner._on_owner(store.load)

    assert (answer.code, answer.reason) == (ControlErrorCode.REFUSED, "target_not_waiting")
    assert saved.subscriptions == before.subscriptions
    assert "now" not in {item.command_id for item in saved.command_receipts}


def test_download_now_settles_only_targets_searched_with_their_sources_available(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "torrentio.strem.fun" and request.url.path.endswith(":23.json"):
            return httpx.Response(200, json={"streams": []}, headers={"content-type": "application/json"})
        return httpx.Response(500)

    world: _World = _World(polish_wait_h=2)
    control: RequestControl = controlled(respond)
    asked: str = (_NOW - timedelta(minutes=5)).isoformat()
    targets: tuple[SubscriptionTarget, ...] = tuple(
        SubscriptionTarget(number, due, TargetState.DUE, polish_skip=PolishSkip(due, asked))
        for number, due in (
            (22, (_NOW - timedelta(hours=1) - _WEEK).isoformat()),
            (23, (_NOW - timedelta(hours=1)).isoformat()),
        )
    )
    record: SubscriptionRecord = _followed(
        subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21, targets=targets
    )
    with httpx.Client(transport=control) as http:
        world.search = search_service(http, control)
        with _following(tmp_path, _active(record), world) as (owner, store):
            checked: SubscriptionRecord = _checked(owner, store)

    found: dict[int, SubscriptionTarget] = {item.number: item for item in checked.targets}
    assert checked.checked_at == _NOW.isoformat()
    assert found[22].sources_down_since == _NOW.isoformat()
    assert [
        (item.number, item.polish_skip.settled, item.polish_skip.tried)
        for item in checked.targets
        if item.polish_skip is not None
    ] == [(22, False, True), (23, True, False)]
    moment: datetime | None = next_search_at(found[22], _NOW)
    assert moment is not None
    assert moment > _NOW


def test_a_target_check_with_the_polish_history_sends_at_most_14_tsukihime_requests(tmp_path: Path) -> None:
    name: str = "[SubsPlease] Tensei Shitara Slime Datta Ken S4 - 23 (1080p)"
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith(f"/animes/anilist/{_S4}"):
            return httpx.Response(200, json={"id": 77})
        if "/episodes/" in request.url.path:
            start: int = int(request.url.params["offset"])
            rows: list[dict[str, object]] = [
                {"id": number + 1, "btih": f"{number:040x}", "name": name, "filecount": 1, "sublangs": ["en"]}
                for number in range(start, start + 100)
            ]
            return httpx.Response(200, json={"results": rows, "total": 300, "start": start, "limit": 100})
        return httpx.Response(202, json={"id": 5})

    world: _World = _World()
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        acquisition: AcquisitionService = _episode_service(
            tmp_path, world.titles, world.episodes, world.streams, clock=world.clock, request_control=control
        )
        acquisition._episode_search = search_service(http, control)
        read: ListingRead = acquisition.read_listing(_S4)
        counts: list[tuple[int, int]] = []
        for _ in range(2):
            paths.clear()
            acquisition.subscription_check(
                EpisodeKey(_S4, 23),
                read,
                SourceSwitches(True, False, False, False, False),
                failures=(),
                excluded=frozenset(),
                tsukihime_id=None,
                history_at=_NOW,
            )
            counts.append((len(paths), sum(path.endswith("/episodes/22") for path in paths)))

    assert counts == [(14, 1), (14, 2)]


def test_subscription_revision_grows_with_each_subscription_change_only(tmp_path: Path) -> None:
    world: _World = _World(polish_wait_h=2)
    world.streams = _StreamSource({})
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        checked: object = owner._on_owner(owner._status)["subscriptions_revision"]
        owner._on_owner(lambda: owner._save(replace(owner.state, recipes=owner.state.recipes)))
        unchanged: object = owner._on_owner(owner._status)["subscriptions_revision"]
        assert _now(owner).ok
        _settled(owner)
        skipped: object = owner._on_owner(owner._status)["subscriptions_revision"]

    assert isinstance(checked, int)
    assert isinstance(skipped, int)
    assert unchanged == checked
    assert skipped > checked


def test_local_polish_evidence_survives_restart_and_compaction(tmp_path: Path) -> None:
    previous: AcquisitionConfirmation = replace(
        _closed_attempt("previous"),
        operation_id="previous-operation",
        info_hash="1" * 40,
        episode="22",
        state=AcquisitionState.COMPLETE,
        cleaned=True,
        assignments=(
            replace(
                _closed_attempt("previous").assignments[0],
                choice=EpisodeChoice(
                    _S4,
                    22,
                    TorrentioReference("1" * 40, 0, "Slime - 22.mkv", "", ()),
                    {"local_episode": 22},
                    IdentityVerdict.MATCH,
                    "match",
                    traits=ChoiceTraits(PolishClass.POLISH, ResolutionClass.FULL_HD),
                ),
                replaced=False,
            ),
        ),
    )
    compacted: AcquisitionConfirmation = compact_acquisition(previous)
    world: _World = _World(polish_wait_h=6)
    world.streams = _StreamSource({})
    state: WatchState = replace(_active(_followed()), acquisitions=(compacted,))
    with _following(tmp_path, state, world) as (owner, store):
        _checked(owner, store)
    with _following(tmp_path, state, world) as (owner, store):
        _ask(owner, "subscription_check", {"subscription_id": "a"}, "again")
        _settled(owner)
        status: EpisodeStatus = _status(owner)

    assert (compacted.assignments[0].choice.target, compacted.assignments[0].choice.reference.release) == ({}, "")
    assert (status.polish, status.polish_wait_until) == ("present", (_NOW + timedelta(hours=5)).isoformat())
    polish: list[dict[str, object]] = [item for item in _decisions(tmp_path) if item["kind"] == "polish"]
    assert [(item["result"], item["source"]) for item in polish] == [("present", "local")] * 2


def _attempts(state: WatchState) -> list[EpisodeAssignment]:
    return [
        assignment
        for transfer in state.acquisitions
        for assignment in transfer.assignments
        if assignment.source is AdmissionSource.SUBSCRIPTION
    ]


def _published(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    messages: list[str] = []
    original: Callable[..., None] = AutomationOwner._publish_notification

    def record(owner: AutomationOwner, title: str, message: str, target: object) -> None:
        messages.append(message)
        original(owner, title, message, target)

    monkeypatch.setattr(AutomationOwner, "_publish_notification", record)
    return messages


def _escalated(tmp_path: Path) -> list[tuple[object, object, object]]:
    return [
        (cast("dict[str, object]", item["key"])["number"], item["reason"], item.get("attempt"))
        for item in _decisions(tmp_path)
        if item["kind"] == "escalation"
    ]


def _again(owner: AutomationOwner, command_id: str) -> None:
    _ask(owner, "subscription_check", {"subscription_id": "a"}, command_id)
    _settled(owner)


def test_notice_once_per_target_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_StreamSource({}))
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        early: list[str] = list(messages)
        world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
        _again(owner, "deadline")
        _again(owner, "again")
        status: EpisodeStatus = _status(owner)
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _again(owner, "restarted")
        saved: WatchState = owner._on_owner(store.load)

    assert early == []
    assert messages == ["Slime S4 E23: brak pewnego wydania (0 wydań, 0 zgodnych)"]
    assert _escalated(tmp_path) == [(23, "no_admissible", None)]
    assert ("subscription:a:23", "no_admissible", "") in saved.notified
    assert saved.subscriptions[0].targets[0].blocker is Blocker.NO_ADMISSIBLE
    assert status.notices == (TargetNotice("no_admissible"),)


def test_notice_threshold_names_the_wanted_and_available_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = _published(monkeypatch)
    lower: StreamCandidate = _named("[SubsPlease] Tensei shitara Slime Datta Ken 4th Season - 23 (720p).mkv")
    world: _World = _World(streams=_StreamSource({(_KITSU, 23): (lower,)}))
    world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
    dead: SubscriptionTarget = SubscriptionTarget(
        23,
        (_NOW - timedelta(hours=1)).isoformat(),
        TargetState.DUE,
        attempts=1,
        tried=("0" * 40,),
        reason="stalled",
        started=1,
        threshold=ResolutionClass.FULL_HD,
    )
    with _following(tmp_path, _active(_followed(targets=(dead,))), world) as (owner, store):
        checked: SubscriptionRecord = _checked(owner, store)
        _again(owner, "again")
        status: EpisodeStatus = _status(owner)

    assert messages == ["Slime S4 E23: czekam na 1080p (dostępne 720p)"]
    assert _escalated(tmp_path) == [(23, "threshold", None)]
    assert (checked.targets[0].state, checked.targets[0].blocker) == (TargetState.DUE, Blocker.THRESHOLD)
    assert status.notices == (TargetNotice("stalled"), TargetNotice("threshold", "0"))


def test_sources_down_notice_once_across_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_FailingStreams())
    counts: list[int] = []
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        counts.append(len(messages))
    world.clock.now = (_NOW + timedelta(minutes=30)).timestamp()
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        for minutes in (30, 45, 60, 75):
            world.clock.now = (_NOW + timedelta(minutes=minutes)).timestamp()
            _again(owner, f"check-{minutes}")
            counts.append(len(messages))
        status: EpisodeStatus = _status(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert counts == [0, 0, 0, 1, 1]
    assert messages == ["Slime S4 E23: źródła wydań nie odpowiadają od 1 h"]
    assert _escalated(tmp_path) == [(23, "sources_down", None)]
    assert saved.subscriptions[0].targets[0].sources_down_since == _NOW.isoformat()
    assert status.notices == (TargetNotice("sources_down", "1"),)


def test_sources_down_per_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_EarlyFailure(_slime_streams().answers))
    record: SubscriptionRecord = _followed(subscribed_at=(_NOW - timedelta(days=9)).isoformat(), cut=21)
    with _following(tmp_path, _active(record), world, shadow=True) as (owner, store):
        _checked(owner, store)
        world.clock.now = (_NOW + timedelta(minutes=61)).timestamp()
        _again(owner, "later")
        saved: WatchState = owner._on_owner(store.load)

    targets: dict[int, SubscriptionTarget] = {item.number: item for item in saved.subscriptions[0].targets}
    assert (targets[22].sources_down_since, targets[23].sources_down_since) == (_NOW.isoformat(), None)
    assert [item for item in _escalated(tmp_path) if item[1] == "sources_down"] == [(22, "sources_down", None)]
    assert [item for item in messages if "źródła" in item] == ["Slime S4 E22: źródła wydań nie odpowiadają od 1 h"]


def test_sources_down_cleared_when_target_settles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_FailingStreams())
    manual: EpisodeChoice = replace(
        _closed_attempt().assignments[0].choice,
        reference=TorrentioReference("f" * 40, 0, "Slime - 23.mkv", "[Fan] Slime", ()),
    )
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        down: SubscriptionRecord = _checked(owner, store)
        ordered: ControlResponse = owner._on_owner(lambda: owner._admit_episode("manual", manual))
        world.clock.now = (_NOW + timedelta(hours=2)).timestamp()
        _again(owner, "later")
        saved: WatchState = owner._on_owner(store.load)

    assert ordered.ok
    assert down.targets[0].sources_down_since == _NOW.isoformat()
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.sources_down_since, target.blocker) == (TargetState.MANUAL, None, None)
    assert "sources_down" not in [item[1] for item in _escalated(tmp_path)]
    assert messages == []


def test_sources_down_not_reported_for_a_target_awaiting_airing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = _published(monkeypatch)
    waiting: SubscriptionTarget = SubscriptionTarget(
        24,
        (_NOW - timedelta(hours=1) + _WEEK).isoformat(),
        TargetState.AWAITING_AIRING,
        sources_down_since=(_NOW - timedelta(hours=2)).isoformat(),
    )
    with _following(tmp_path, _active(_followed(targets=(waiting,))), _World()) as (owner, store):
        _checked(owner, store)

    assert [item for item in messages if "źródła" in item] == []
    assert "sources_down" not in [item[1] for item in _escalated(tmp_path)]


def test_notice_counts_untried_and_tried_matching_releases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    tried: StreamCandidate = _named("[SubsPlease] Tensei shitara Slime Datta Ken 4th Season - 23 (1080p).mkv")
    dubbed: StreamCandidate = _named("[Grp] Tensei shitara Slime Datta Ken 4th Season - 23 (1080p) [English Dub].mkv")
    uncertain: StreamCandidate = _named("[Grp] Slime - 23.mkv")
    world: _World = _World(streams=_StreamSource({(_KITSU, 23): (tried, dubbed, uncertain)}))
    world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
    dead: SubscriptionTarget = SubscriptionTarget(
        23,
        (_NOW - timedelta(hours=1)).isoformat(),
        TargetState.DUE,
        attempts=1,
        tried=(release_hash(tried.info_hash),),
        reason="stalled",
        started=1,
    )
    with _following(tmp_path, _active(_followed(targets=(dead,))), world) as (owner, store):
        _checked(owner, store)

    assert messages == ["Slime S4 E23: brak pewnego wydania (3 wydania, 1 zgodne, 1 już próbowane)"]


def _pending_world() -> Callable[[httpx.Request], httpx.Response]:
    fixture: dict[str, list[dict[str, object]]] = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "search" / "torrentio__kitsu-49235-23.json").read_text(
            encoding="utf-8"
        )
    )
    erai: dict[str, object] = dict(fixture["streams"][1])
    hints: dict[str, object] = cast("dict[str, object]", erai["behaviorHints"])
    erai["name"] = "Torrentio\n720p"
    erai["title"] = str(erai["title"]).replace("1080", "720")
    erai["behaviorHints"] = {"filename": str(hints["filename"]).replace("1080p", "720p")}
    item: str = (
        "<item><title>[Grp] Slime - 23 (1080p)</title><link>https://nyaa.si/download/1.torrent</link>"
        f"<nyaa:infoHash>{'e' * 40}</nyaa:infoHash><nyaa:seeders>30</nyaa:seeders>"
        "<nyaa:size>1 GiB</nyaa:size></item>"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "torrentio.strem.fun":
            return httpx.Response(200, json={"streams": [erai]})
        if request.url.host == "nyaa.si":
            return httpx.Response(
                200,
                text=f'<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa"><channel>{item}</channel></rss>',
                headers={"content-type": "application/xml"},
            )
        if request.url.path.endswith(f"/animes/anilist/{_S4}"):
            return httpx.Response(200, json={"id": 77})
        if "/episodes/" in request.url.path:
            return httpx.Response(200, json={"results": [], "total": 0, "start": 0, "limit": 100})
        if "tsukihime" in request.url.host:
            return httpx.Response(202, json={"id": 5})
        return _empty_response(request)

    return respond


def test_notice_pending_release_blocks_a_worse_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World()
    world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
    control: RequestControl = controlled(_pending_world())
    with httpx.Client(transport=control) as http:
        world.search = search_service(http, control)
        with _following(tmp_path, _active(_followed()), world) as (owner, store):
            checked: SubscriptionRecord = _checked(owner, store)
            status: EpisodeStatus = _status(owner)

    assert messages == ["Slime S4 E23: czekam na sprawdzenie wydań 1080p"]
    assert _escalated(tmp_path) == [(23, "pending", None)]
    assert (checked.targets[0].state, checked.targets[0].blocker) == (TargetState.DUE, Blocker.PENDING)
    assert status.notices == (TargetNotice("pending"),)


def test_notice_not_published_when_its_state_cannot_be_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_StreamSource({}))
    key: NotificationKey = ("subscription:a:23", "no_admissible", "")
    failing: list[bool] = [True]
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        original: Callable[[WatchState], None] = store.save

        def save(state: WatchState) -> None:
            if failing[0] and key in state.notified:
                message: str = "disk full"
                raise OSError(message)
            original(state)

        monkeypatch.setattr(store, "save", save)
        world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
        _again(owner, "unsaved")
        unsaved: list[str] = list(messages)
        noted: bool = key in owner.state.notified
        failing[0] = False
        _again(owner, "saved")

    assert (unsaved, noted) == ([], False)
    assert messages == ["Slime S4 E23: brak pewnego wydania (0 wydań, 0 zgodnych)"]
    assert _escalated(tmp_path) == [(23, "no_admissible", None)]


def test_sources_down_notice_waits_a_full_hour(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(streams=_FailingStreams())
    counts: list[int] = []
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        _checked(owner, store)
        for moment in (timedelta(minutes=59, seconds=59), timedelta(hours=1)):
            world.clock.now = (_NOW + moment).timestamp()
            _again(owner, f"check-{moment.total_seconds()}")
            counts.append(len(messages))

    assert counts == [0, 1]


def test_no_polish_after_buffer_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    world: _World = _World(polish_wait_h=2)
    with _following(tmp_path, _active(_followed()), world) as (owner, store):
        waiting: SubscriptionRecord = _checked(owner, store)
        world.clock.now = (_NOW + timedelta(hours=1)).timestamp()
        _again(owner, "after-buffer")
        status: EpisodeStatus = _status(owner)
        saved: WatchState = owner._on_owner(store.load)

    assert waiting.targets[0].state is TargetState.DUE
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.polish_buffer_min) == (TargetState.ATTEMPTING, 120)
    assert status.notices == (TargetNotice("no_polish_after_wait", "120"),)
    assert (messages, _escalated(tmp_path)) == ([], [])


@pytest.mark.parametrize("case", ["absent", "no-wait", "download-now"])
def test_no_polish_reason_only_after_an_actual_wait(tmp_path: Path, case: str) -> None:
    world: _World = _World(polish_wait_h=0 if case == "no-wait" else 2)
    absent: PolishObservation = PolishObservation(PolishState.ABSENT, _NOW.isoformat())
    due: SubscriptionTarget = SubscriptionTarget(
        23, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE, polish=absent if case == "absent" else None
    )
    with _following(tmp_path, _active(_followed(targets=(due,))), world) as (owner, store):
        _checked(owner, store)
        if case == "download-now":
            assert _now(owner).ok
            _settled(owner)
        status: EpisodeStatus = _status(owner)
        saved: WatchState = owner._on_owner(store.load)

    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.polish_buffer_min) == (TargetState.ATTEMPTING, None)
    assert status.notices == ()


def test_replaced_attempt_closes_without_a_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = _published(monkeypatch)
    attempting: SubscriptionTarget = SubscriptionTarget(
        23,
        (_NOW - timedelta(hours=1)).isoformat(),
        TargetState.ATTEMPTING,
        attempts=1,
        started=1,
        tried=("0" * 40,),
        admission_id="attempt-1",
    )
    state: WatchState = replace(_active(_followed(targets=(attempting,))), acquisitions=(_closed_attempt(),))
    with _following(tmp_path, state, _World(streams=_StreamSource({}))) as (owner, store):
        _checked(owner, store)

    closures: list[object] = [item.get("attempt_result") for item in _decisions(tmp_path) if item["kind"] == "attempt"]
    assert closures == ["replaced"]
    assert [item for item in _escalated(tmp_path) if item[1] == "replaced"] == []
    assert [item for item in messages if "szukam" in item] == []
