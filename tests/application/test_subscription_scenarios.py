from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from loguru import logger as loguru_logger
from test_acquisition import _Clock
from test_automation import _INSTANCE, _MOMENT, _TIMEOUT_S, _real_service, _request, _serving
from test_selective_lifecycle import _ENTRY, _PACK, _choice, _SelectiveNetwork, _until
from test_subscription_attempts import _Probe

from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.acquisition_staging import copy_staged
from anishift.application.automation import AutomationOwner
from anishift.application.cancellation import CancellationToken
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AutomationPolicy,
    EpisodeAssignment,
    EpisodeChoice,
    FileStamp,
    LegacyOrder,
    WatchState,
)
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_commands import EpisodeBatch, EpisodeReason, EpisodeResult
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import (
    AniZipMapping,
    EpisodeKey,
    FranchiseGraph,
    ListedEpisode,
    StreamCandidate,
)
from anishift.application.history import HistoryJournal, HistoryKind
from anishift.application.intents import RequestOrigin
from anishift.application.subscription_targets import (
    LEGACY_ORDERED,
    PauseReason,
    SubscriptionRecord,
    SubscriptionTarget,
    TargetState,
    next_check_at,
)
from anishift.application.transfers import TransferInspector, file_map_revision
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.local_control import ControlResponse
from anishift.services.catalog import EpisodeAiring, SeasonAiring, TitleCatalogError, TitleStatus
from anishift.services.catalog.anizip import AniZipCatalog
from anishift.services.catalog.types import PrequelEntry, TitleCandidate
from anishift.services.media.probe import MediaProbe
from anishift.services.torrents import TorrentClientError, TorrentFile, parse_release_name

_WEEK: timedelta = timedelta(days=7)

_AIRED: datetime = _MOMENT - timedelta(hours=1)

_KITSU: int = 500

_OTHER: int = 600

_STALL_S: int = 600

_FIRST: str = "a" * 40

_SECOND: str = "b" * 40

_THIRD: str = "c" * 40

_FOURTH: str = "d" * 40


def _stream(info_hash: str, number: int = 3, *, seeders: int = 99, name: str | None = None) -> StreamCandidate:
    file_name: str = name or f"Neko to Ryuu - {number:02}.mkv"
    return StreamCandidate(info_hash, "1080p", None, file_name, file_name, None, seeders, None, None, (), ())


def _uncertain(info_hash: str = _FIRST) -> StreamCandidate:
    return _stream(info_hash, name="Neko - 03.mkv")


def _refused() -> TorrentClientError:
    return TorrentClientError(context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Busy"))


class _Network(_SelectiveNetwork):
    def __init__(self) -> None:
        super().__init__()
        self.refused_cancel: bool = False
        self.releasing: bool = True
        self.blocked: tuple[str, str] | None = None
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()

    def transfer_action(self, info_hash: str, action: str) -> None:
        if action == "cancel" and self.refused_cancel:
            raise _refused()
        if (info_hash, action) == self.blocked:
            self.blocked = None
            self.entered.set()
            assert self.release.wait(_TIMEOUT_S)
        super().transfer_action(info_hash, action)

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        return super().release_completed(hashes) if self.releasing else frozenset()


class _Season:
    def __init__(self) -> None:
        self.offered: dict[int, tuple[StreamCandidate, ...]] = {3: (_stream(_FIRST),)}
        self.airs: dict[int, datetime] = {number: _AIRED + (number - 3) * _WEEK for number in range(1, 5)}
        self.status: TitleStatus = TitleStatus.RELEASING
        self.count: int = 4
        self.asked: list[int] = []
        self.broken: frozenset[int] = frozenset()
        self.down: bool = False

    def search(self, text: str, *, limit: int = 7) -> tuple[TitleCandidate, ...]:
        raise AssertionError((text, limit))

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        return ()

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        episodes: tuple[EpisodeAiring, ...] = tuple(
            EpisodeAiring(number, moment) for number, moment in self.airs.items()
        )
        return SeasonAiring(anilist_id, self.status, self.count, episodes)

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> FranchiseGraph:
        return FranchiseGraph(
            anilist_id,
            {
                anilist_id: {
                    "id": anilist_id,
                    "title": {"romaji": "Neko to Ryuu", "english": "Neko to Ryuu"},
                    "format": "TV",
                    "status": self.status.value,
                    "episodes": self.count,
                    "synonyms": [],
                    "relations": {"edges": []},
                    "startDate": {"year": 2026, "month": 8, "day": 1},
                }
            },
            frozenset({anilist_id}),
            True,
        )

    def mapping(self, anilist_id: int) -> AniZipMapping:
        if self.down or anilist_id in self.broken:
            raise TitleCatalogError(context=ErrorContext(code=ErrorCode.EPISODE_CATALOG_FAILED, message="down"))
        return _mapping()

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        self.asked.append(number)
        return self.offered.get(number, ())

    def movie_streams(self, kitsu_id: int) -> tuple[StreamCandidate, ...]:
        raise AssertionError(kitsu_id)


def _mapping(*, length: float | None = None) -> AniZipMapping:
    raw: dict[str, dict[str, object]] = {
        str(number): {"episode": str(number), "seasonNumber": 1, "episodeNumber": number} for number in range(1, 5)
    }
    if length is not None:
        raw["3"]["length"] = length
    episodes: tuple[ListedEpisode, ...] = tuple(
        ListedEpisode(number, season=1, episode=number) for number in range(1, 5)
    )
    return AniZipMapping(_KITSU, "TV", 4, episodes, (), None, raw)


def _record(**changes: object) -> SubscriptionRecord:
    record: SubscriptionRecord = SubscriptionRecord(
        "a",
        _ENTRY,
        "Neko to Ryuu",
        (_MOMENT - timedelta(days=2)).isoformat(),
        2,
        kitsu_id=_KITSU,
        mapping=replace(_mapping(), max_age_s=None),
    )
    return replace(record, **changes)  # type: ignore[arg-type]


def _target_row(number: int, state: TargetState, **changes: object) -> SubscriptionTarget:
    fields: dict[str, object] = {
        "due_at": (_AIRED + (number - 3) * _WEEK).isoformat(),
        "started": changes.get("attempts", 0),
        **changes,
    }
    return SubscriptionTarget(number=number, state=state, **fields)  # type: ignore[arg-type]


@dataclass
class _World:
    root: Path
    network: _Network = field(default_factory=_Network)
    season: _Season = field(default_factory=_Season)
    clock: _Clock = field(default_factory=lambda: _Clock(_MOMENT.timestamp()))
    ticks: _Clock = field(default_factory=lambda: _Clock(1000.0))
    probe: _Probe = field(default_factory=_Probe)
    episodes: object = None

    @property
    def store(self) -> WatchStateStore:
        return WatchStateStore(self.root / WATCH_STATE_FILE_NAME)

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock.now, UTC)

    def acquisition(self) -> AcquisitionService:
        return AcquisitionService(
            source=self.network,
            client=cast("TorrentClient", self.network),
            workspace_root=self.root,
            parse_name=parse_release_name,
            torrent_management=cast("TorrentManagement", self.network),
            title_catalog=self.season,
            episode_catalog=cast("_Season", self.episodes) if self.episodes is not None else self.season,
            stream_source=self.season,
            clock=self.clock,
        )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _World:
    built: _World = _World(tmp_path)
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "_CHECK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(
        automation_module,
        "TransferInspector",
        lambda acquisition, root: TransferInspector(acquisition, root, clock=built.ticks),
    )
    return built


@contextmanager
def _running(world: _World, state: WatchState | None = None) -> Iterator[AutomationOwner]:
    if state is not None:
        world.store.save(state)
    owner: AutomationOwner = AutomationOwner(
        _real_service(world.root, acquisition=world.acquisition()),
        world.store,
        instance_id=_INSTANCE,
        clock=world.now,
        media_probe=cast("MediaProbe", world.probe),
    )
    world.probe.owner = owner
    thread: threading.Thread = _serving(owner)
    try:
        yield owner
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def _following(*records: SubscriptionRecord, auto: bool = True, **changes: object) -> WatchState:
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=auto, transfer_stall_s=_STALL_S), subscriptions=records or (_record(),)
    )
    return replace(state, **changes)  # type: ignore[arg-type]


def _record_of(owner: AutomationOwner, identifier: str = "a") -> SubscriptionRecord | None:
    return next((item for item in owner.state.subscriptions if item.subscription_id == identifier), None)


def _target(owner: AutomationOwner, number: int = 3, identifier: str = "a") -> SubscriptionTarget:
    record: SubscriptionRecord | None = _record_of(owner, identifier)
    assert record is not None
    return next(item for item in record.targets if item.number == number)


def _reaches(owner: AutomationOwner, state: TargetState, number: int = 3, identifier: str = "a") -> None:
    def reached() -> bool:
        record: SubscriptionRecord | None = _record_of(owner, identifier)
        return record is not None and any(item.number == number and item.state is state for item in record.targets)

    _until(reached)


def _idle(owner: AutomationOwner) -> None:
    _until(lambda: owner._on_owner(lambda: not owner._subscription_checks))


def _check(owner: AutomationOwner, command_id: str, identifier: str = "a") -> None:
    _idle(owner)
    answer: ControlResponse = owner.handle(
        _request("subscription_check", {"subscription_id": identifier}, command_id=command_id)
    )
    assert answer.ok
    _until(lambda: owner._on_owner(lambda: identifier not in owner._subscription_requests))
    _idle(owner)


def _command(owner: AutomationOwner, kind: str, command_id: str, **payload: object) -> None:
    answer: ControlResponse = owner.handle(_request(kind, payload, command_id=command_id))
    assert answer.ok, answer


def _order(owner: AutomationOwner, number: int, command_id: str) -> EpisodeResult:
    def batch() -> EpisodeBatch:
        answer: ControlResponse = owner.handle(
            _request(
                "episode_download",
                {"keys": [encode_view(EpisodeKey(_ENTRY, number))]},
                command_id=command_id,
                session_id="panel",
            )
        )
        assert answer.ok, answer
        return decode_view(EpisodeBatch, answer.result)

    _until(lambda: batch().state != "accepted")
    return batch().results[0]


def _status(owner: AutomationOwner, number: int) -> dict[str, object]:
    answer: ControlResponse = owner.handle(
        _request("episode_states", {"anilist_id": _ENTRY, "numbers": [number]}, command_id="states")
    )
    return cast("list[dict[str, object]]", answer.result["items"])[0]


def _choice_on(number: int, info_hash: str) -> EpisodeChoice:
    chosen: EpisodeChoice = _choice(number)
    return replace(chosen, reference=replace(chosen.reference, info_hash=info_hash))


def _transfer(owner: AutomationOwner, info_hash: str) -> AcquisitionConfirmation:
    return next(item for item in reversed(owner.state.acquisitions) if item.info_hash == info_hash)


def _failed(owner: AutomationOwner, info_hash: str) -> Callable[[], bool]:
    return lambda: _transfer(owner, info_hash).state is AcquisitionState.FAILED


def _attempts(state: WatchState, number: int = 3) -> list[EpisodeAssignment]:
    return [
        assignment
        for transfer in state.acquisitions
        for assignment in transfer.assignments
        if assignment.choice.number == number and assignment.source is AdmissionSource.SUBSCRIPTION
    ]


def _hashes(items: list[EpisodeAssignment]) -> list[str]:
    return [item.choice.reference.info_hash for item in items]


def _polls(world: _World, count: int = 3) -> None:
    seen: int = world.network.info_calls
    _until(lambda: world.network.info_calls >= seen + count)


def _files(number: int) -> list[TorrentFile]:
    return [item for item in _PACK if f" - {number:02}." in item.name]


def _started(world: _World, info_hash: str) -> None:
    _until(lambda: any(item[0] == info_hash for item in world.network.metadata_added))
    if info_hash not in world.network.per_hash:
        world.network.deliver(info_hash, _PACK)
    _until(lambda: info_hash in world.network.started)


def _stage(world: _World, owner: AutomationOwner, info_hash: str, number: int = 3) -> None:
    _started(world, info_hash)
    data: Path = world.root / "temp" / ".acquisition" / _transfer(owner, info_hash).operation_id / "data"
    for item in _files(number):
        path: Path = data / item.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"v" * item.size)
    _until(lambda: world.network.tracked[info_hash].state == "downloading")


def _complete(world: _World, info_hash: str, number: int) -> None:
    indexes: frozenset[int] = frozenset(item.index for item in _files(number))
    network: _Network = world.network
    network.per_hash[info_hash] = tuple(
        replace(item, progress=1.0) if item.index in indexes else item for item in network.per_hash[info_hash]
    )
    network.tracked[info_hash] = replace(network.tracked[info_hash], progress=0.5)


def _download(world: _World, owner: AutomationOwner, info_hash: str, number: int = 3) -> None:
    _stage(world, owner, info_hash, number)
    world.network.finish(info_hash)


def _fail(world: _World, owner: AutomationOwner, info_hash: str, how: str) -> None:
    if how == "metadata":
        _until(lambda: any(item[0] == info_hash for item in world.network.metadata_added))
        _polls(world)
        world.ticks.now += automation_module.METADATA_TIMEOUT_S
        return
    if how == "video":
        world.probe.video = False
        _download(world, owner, info_hash)
        return
    _stage(world, owner, info_hash)
    _polls(world)
    world.ticks.now += _STALL_S


def _decisions(world: _World, kind: str | None = None) -> list[dict[str, object]]:
    path: Path = world.store.history_path().with_name("decisions.jsonl")
    if not path.exists():
        return []
    entries: list[dict[str, object]] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [item for item in entries if kind is None or item["kind"] == kind]


def _closures(world: _World) -> list[tuple[object, object]]:
    return [(item["attempt"], item["attempt_result"]) for item in _decisions(world, "attempt")]


def _escalations(world: _World) -> list[object]:
    return [item["reason"] for item in _decisions(world, "escalation")]


def _root_files(world: _World) -> set[str]:
    return {path.name for path in world.root.iterdir() if path.suffix in {".mkv", ".ass"}}


def _stored(owner: AutomationOwner, world: _World) -> WatchState:
    return owner._on_owner(world.store.load)


def _receipts(state: WatchState) -> set[str]:
    return {item.command_id for item in state.command_receipts}


def test_a_due_episode_is_found_downloaded_checked_and_handed_off_once(world: _World) -> None:
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _download(world, owner, _FIRST)
        _reaches(owner, TargetState.SATISFIED)
        saved: WatchState = _stored(owner, world)

    assert _hashes(_attempts(saved)) == [_FIRST]
    assert {"Neko to Ryuu - 03.mkv", "Neko to Ryuu - 03.ass"} <= _root_files(world)
    assert _closures(world) == [(1, "accepted")]


def _checked_at(owner: AutomationOwner) -> str | None:
    record: SubscriptionRecord | None = _record_of(owner)
    return None if record is None else record.checked_at


def test_a_missing_release_is_searched_on_the_quarter_hour_hour_and_day_grid_and_reported_once_after_a_week(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks: list[float] = [1000.0]
    monkeypatch.setattr(automation_module, "time", SimpleNamespace(monotonic=lambda: ticks[0]))
    world.season.offered = {}
    world.season.airs[4] = _AIRED + 30 * timedelta(days=1)
    world.clock.now = _AIRED.timestamp()
    ages: tuple[timedelta, ...] = (
        timedelta(0),
        timedelta(days=1, minutes=1),
        timedelta(days=3, minutes=1),
        timedelta(days=7, minutes=1),
        timedelta(days=8, minutes=1),
    )
    delays: list[float] = []
    with _running(world, _following()) as owner:
        for index, age in enumerate(ages):
            moment: str = (_AIRED + age).isoformat()
            world.clock.now = (_AIRED + age).timestamp()
            ticks[0] = 1000.0 + age.total_seconds()
            owner.handle(_request("subscriptions_list", command_id=f"wake-{index}"))
            _until(lambda: _checked_at(owner) == moment)  # noqa: B023
            _idle(owner)
            scheduled: float | None = owner._on_owner(lambda: owner._subscriptions_at)
            assert scheduled is not None
            delays.append(scheduled - ticks[0])
        saved: WatchState = _stored(owner, world)

    assert delays == [15 * 60, 59 * 60, 86400 - 60, 86400 - 60, 86400 - 60]
    assert world.season.asked == [3] * len(ages)
    assert _escalations(world) == ["late"]
    assert ("subscription:a:3", "late", "") in saved.notified
    assert saved.acquisitions == ()


@pytest.mark.parametrize(
    "order", [("metadata", "video", "stall"), ("video", "metadata", "stall")], ids=["metadata-first", "video-first"]
)
def test_three_attempts_on_own_transfers_each_wait_for_the_confirmed_cancel_and_exhaust_the_target_once(
    world: _World, order: tuple[str, str, str]
) -> None:
    world.season.offered[3] = (
        _stream(_FIRST, seeders=300),
        _stream(_SECOND, seeders=200),
        _stream(_THIRD, seeders=100),
        _stream(_FOURTH, seeders=50),
    )
    hashes: tuple[str, ...] = (_FIRST, _SECOND, _THIRD)
    early: int = 0
    with _running(world, _following()) as owner:
        for index, (info_hash, how) in enumerate(zip(hashes, order, strict=True), start=1):
            _reaches(owner, TargetState.ATTEMPTING)
            world.network.refused_cancel = index == 1
            _fail(world, owner, info_hash, how)
            if index == 1:
                _reaches(owner, TargetState.DUE)
                _check(owner, "before-cancel")
                early = len(_attempts(owner.state))
                world.network.refused_cancel = False
            _until(_failed(owner, info_hash))
            world.probe.video = True
            _check(owner, f"after-{index}")
        _reaches(owner, TargetState.EXHAUSTED)
        saved: WatchState = _stored(owner, world)

    attempts: list[EpisodeAssignment] = _attempts(saved)
    assert early == 1
    assert _hashes(attempts) == list(hashes)
    assert [item.previous_admission_id for item in attempts] == [None, None, None]
    assert [item[0] for item in world.network.metadata_added] == list(hashes)
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.state, target.attempts) == (TargetState.EXHAUSTED, 3)
    assert target.tried == tuple(f"{item}:" for item in hashes)
    assert {"sub:a:3:1", "sub:a:3:2", "sub:a:3:3"} <= _receipts(saved)
    assert "sub:a:3:4" not in _receipts(saved)
    results: dict[str, str] = {"metadata": "dead", "video": "rejected", "stall": "dead"}
    assert _closures(world) == [(number, results[how]) for number, how in enumerate(order, start=1)]
    rejected: EpisodeAssignment = attempts[order.index("video")]
    assert (rejected.verification, rejected.publication) == ("reject:no_video_stream", None)
    assert not _root_files(world)
    assert [key for key in saved.notified if key[1] == "exhausted"] == [("subscription:a:3", "exhausted", "")]
    assert _escalations(world) == ["exhausted"]


def test_the_next_attempt_after_a_rejection_on_a_shared_transfer_starts_only_once_that_transfer_dropped_it(
    world: _World,
) -> None:
    world.season.offered[3] = (_stream(_FIRST, seeders=300), _stream(_SECOND, seeders=200))
    world.probe.video = False
    with _running(world, _following(auto=False)) as owner:
        assert owner.admit_episode("manual-4", _choice_on(4, _FIRST)).ok
        _command(owner, "set_auto", "resume", enabled=True)
        _reaches(owner, TargetState.ATTEMPTING)
        _stage(world, owner, _FIRST)
        world.network.stop_ignored = True
        _complete(world, _FIRST, 3)
        _reaches(owner, TargetState.DUE)
        world.probe.video = True
        _check(owner, "second")
        _reaches(owner, TargetState.ATTEMPTING)
        _until(lambda: any(item[0] == _SECOND for item in world.network.metadata_added))
        world.network.deliver(_SECOND, _PACK)
        _until(lambda: _transfer(owner, _SECOND).applied_revision > 0)
        _polls(world)
        waiting: tuple[bool, object] = (_SECOND in world.network.started, _status(owner, 3)["reason"])
        world.network.stop_ignored = False
        world.network.tracked[_FIRST] = replace(world.network.tracked[_FIRST], state="stoppedDL")
        _download(world, owner, _SECOND)
        _reaches(owner, TargetState.SATISFIED)
        saved: WatchState = _stored(owner, world)

    first, second = _attempts(saved)
    assert waiting == (False, EpisodeReason.WAITING_PREVIOUS_TRANSFER)
    assert (first.choice.reference.info_hash, first.verification, first.replaced) == (
        _FIRST,
        "reject:no_video_stream",
        True,
    )
    assert (second.choice.reference.info_hash, second.previous_admission_id) == (_SECOND, first.admission_id)
    assert (_FIRST, "cancel") not in world.network.actions
    shared: AcquisitionConfirmation = next(item for item in saved.acquisitions if item.info_hash == _FIRST)
    assert [item.choice.number for item in shared.active_assignments] == [4]
    assert _closures(world) == [(1, "rejected"), (2, "accepted")]


def test_a_shared_then_an_own_attempt_let_the_third_replace_the_first_across_a_restart(world: _World) -> None:
    world.season.offered[3] = (
        _stream(_FIRST, seeders=300),
        _stream(_SECOND, seeders=200),
        _stream(_THIRD, seeders=100),
        _stream(_FOURTH, seeders=50),
    )
    world.probe.video = False
    with _running(world, _following(auto=False)) as owner:
        assert owner.admit_episode("manual-5", _choice_on(5, _FIRST)).ok
        _command(owner, "set_auto", "resume", enabled=True)
        _reaches(owner, TargetState.ATTEMPTING)
        _stage(world, owner, _FIRST)
        _complete(world, _FIRST, 3)
        _reaches(owner, TargetState.DUE)
        _check(owner, "second")
        _reaches(owner, TargetState.ATTEMPTING)
        _fail(world, owner, _SECOND, "metadata")
        _until(_failed(owner, _SECOND))
    with _running(world) as owner:
        _check(owner, "third")
        _reaches(owner, TargetState.ATTEMPTING)
        _download(world, owner, _THIRD)
        _reaches(owner, TargetState.EXHAUSTED)
        _until(_failed(owner, _THIRD))
        _check(owner, "fourth")
        saved: WatchState = _stored(owner, world)

    first, second, third = _attempts(saved)
    assert _hashes([first, second, third]) == [_FIRST, _SECOND, _THIRD]
    assert (second.previous_admission_id, third.previous_admission_id) == (first.admission_id, first.admission_id)
    assert {"sub:a:3:1", "sub:a:3:2", "sub:a:3:3"} <= _receipts(saved)
    assert _closures(world) == [(1, "rejected"), (2, "dead"), (3, "rejected")]
    assert [key for key in saved.notified if key[1] == "exhausted"] == [("subscription:a:3", "exhausted", "")]
    assert _FOURTH not in {item[0] for item in world.network.metadata_added}


def test_only_uncertain_releases_never_start_an_attempt_at_any_age_and_a_later_match_does(world: _World) -> None:
    world.season.offered[3] = (_uncertain(),)
    events: list[dict[str, object]] = []
    with _running(world, _following()) as owner:
        _idle(owner)
        owner._broadcast = lambda frame, terminal: events.append(dict(frame))
        for index, age in enumerate((timedelta(0), timedelta(days=1), timedelta(days=3), timedelta(days=7, minutes=1))):
            world.clock.now = (_AIRED + age).timestamp()
            _check(owner, f"check-{index}")
        before: WatchState = _stored(owner, world)
        world.season.offered[3] = (_uncertain(), _stream(_SECOND))
        _check(owner, "match")
        _reaches(owner, TargetState.ATTEMPTING)
        saved: WatchState = _stored(owner, world)

    assert before.acquisitions == ()
    record: SubscriptionRecord = before.subscriptions[0]
    assert record.last_check is not None
    assert (record.last_check.uncertain, record.last_check.matching, record.last_check.outcome) == (1, 0, "no_match")
    shown: list[object] = [
        cast("dict[str, object]", cast("dict[str, object]", item["payload"])["last_check"])["uncertain"]
        for item in events
        if item.get("event") == "subscription_checked"
    ]
    assert shown == [1, 1, 1, 1, 1]
    assert _escalations(world) == ["late"]
    assert _hashes(_attempts(saved)) == [_SECOND]


@pytest.mark.parametrize("attempting", [False, True], ids=["due", "attempting"])
def test_an_explicit_order_makes_a_target_manual_and_counts_the_attempt_it_replaces(
    world: _World, attempting: bool
) -> None:
    world.season.offered[3] = (_stream(_FIRST),) if attempting else (_uncertain(),)
    with _running(world, _following()) as owner:
        _idle(owner)
        _reaches(owner, TargetState.ATTEMPTING if attempting else TargetState.DUE)
        before: dict[str, object] = _status(owner, 3)
        result: EpisodeResult = _order(owner, 3, "d-3")
        _reaches(owner, TargetState.MANUAL)
        saved: WatchState = _stored(owner, world)

    assert result.reason == EpisodeReason.ADMITTED
    assert before["attempt"] is attempting
    attempts: list[EpisodeAssignment] = _attempts(saved)
    manual: list[EpisodeAssignment] = [
        item
        for transfer in saved.acquisitions
        for item in transfer.assignments
        if item.source is AdmissionSource.MANUAL
    ]
    assert len(manual) == 1
    assert manual[0].previous_admission_id == (attempts[0].admission_id if attempting else None)
    assert manual[0].choice.verdict is (IdentityVerdict.MATCH if attempting else IdentityVerdict.INSUFFICIENT)
    assert [item.replaced for item in attempts] == ([True] if attempting else [])
    assert saved.subscriptions[0].targets[0].attempts == int(attempting)
    assert _closures(world) == ([(1, "replaced")] if attempting else [])


class _Snapshots(_Probe):
    def __init__(self) -> None:
        super().__init__()
        self.hook: Callable[[], None] | None = None

    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> object:  # type: ignore[override]
        if self.hook is not None:
            self.hook()
        return super().identify(path, cancel=cancel, timeout_s=timeout_s)


def _disk(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _rewind(root: Path, snapshot: dict[Path, bytes]) -> None:
    for path in [item for item in root.rglob("*") if item.is_file() and item not in snapshot]:
        path.unlink()
    for path, data in snapshot.items():
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)


@pytest.mark.parametrize("boundary", ["check", "reserved", "published"])
def test_a_restart_at_each_check_and_publication_point_admits_checks_and_publishes_once(
    world: _World, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    probe: _Snapshots = _Snapshots()
    world.probe = probe
    world.network.releasing = False
    snapshots: list[dict[Path, bytes]] = []
    copies: list[FileStamp | None] = []

    def snapshot() -> None:
        if not snapshots:
            snapshots.append(_disk(world.root))

    def copying(source: Path, target: Path, size: int, *, expected: FileStamp | None = None) -> tuple[str, FileStamp]:
        if source.suffix == ".mkv":
            copies.append(expected)
            if boundary == "reserved":
                snapshot()
        return copy_staged(source, target, size, expected=expected)

    monkeypatch.setattr(automation_module, "copy_staged", copying)
    probe.hook = snapshot if boundary == "check" else None
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _download(world, owner, _FIRST)
        _reaches(owner, TargetState.SATISFIED)
    snapshot()
    _rewind(world.root, snapshots[0])
    probe.hook = None
    probe.seen.clear()
    copies.clear()
    with _running(world) as owner:
        _reaches(owner, TargetState.SATISFIED)
        _idle(owner)
        saved: WatchState = _stored(owner, world)

    assignment: EpisodeAssignment = _attempts(saved)[0]
    assert len(saved.acquisitions) == 1
    assert len(saved.acquisitions[0].assignments) == 1
    assert [item[0] for item in world.network.metadata_added] == [_FIRST]
    assert _root_files(world) == {"Neko to Ryuu - 03.mkv", "Neko to Ryuu - 03.ass"}
    assert len(probe.seen) == (1 if boundary == "check" else 0)
    assert copies == ([] if boundary == "published" else [assignment.verified_stamp])
    assert assignment.verified_stamp is not None
    assert _closures(world) == [(1, "accepted")]


def test_a_subscription_without_mapping_keeps_scheduled_targets_and_never_stops_another_from_finishing(
    world: _World,
) -> None:
    world.season.broken = frozenset({_OTHER})
    broken: SubscriptionRecord = SubscriptionRecord("b", _OTHER, "Broken", (_MOMENT - timedelta(days=2)).isoformat(), 2)
    with _running(world, _following(broken, _record())) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _check(owner, "b-again", "b")
        _download(world, owner, _FIRST)
        _reaches(owner, TargetState.SATISFIED)
        failing: SubscriptionRecord | None = _record_of(owner, "b")

    assert failing is not None
    assert failing.last_check is not None
    assert failing.last_check.outcome == "no_candidates"
    assert failing.checked_at == _MOMENT.isoformat()
    assert failing.mapping is None
    assert failing.kitsu_id is None
    assert failing.targets
    assert all(target.attempts == 0 for target in failing.targets)
    assert next_check_at(failing, _MOMENT) is not None


def _finished(*targets: SubscriptionTarget, count: int = 4) -> SubscriptionRecord:
    return _record(catalog_status="FINISHED", episode_count=count, checked_at=_MOMENT.isoformat(), targets=targets)


def _manual_order(number: int, info_hash: str) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        operation_id=f"manual-{number}",
        info_hash=info_hash,
        directory="",
        required_files=(),
        state=AcquisitionState.ADMITTED,
        origin=RequestOrigin.USER,
        subscription_id=None,
        episode=str(number),
        updated_at=_MOMENT.isoformat(),
        assignments=(
            EpisodeAssignment(
                f"manual-{number}", _MOMENT.isoformat(), AdmissionSource.MANUAL, _choice_on(number, info_hash)
            ),
        ),
    )


def _legacy_transfer(state: AcquisitionState) -> AcquisitionConfirmation:
    files: tuple[str, ...] = ("Neko to Ryuu - 04.mkv",)
    return AcquisitionConfirmation(
        operation_id="legacy",
        info_hash=_THIRD,
        directory="Neko",
        required_files=files,
        state=state,
        origin=RequestOrigin.BACKGROUND,
        subscription_id="old",
        episode="4",
        updated_at=_MOMENT.isoformat(),
        complete_files=files if state is AcquisitionState.COMPLETE else (),
    )


_DONE: SubscriptionTarget = _target_row(3, TargetState.SATISFIED)

_LEGACY: SubscriptionTarget = _target_row(4, TargetState.MANUAL, reason=LEGACY_ORDERED)


@pytest.mark.parametrize(
    ("target", "changes", "closed"),
    [
        (_target_row(4, TargetState.SATISFIED), {}, True),
        (_target_row(4, TargetState.EXHAUSTED, attempts=3), {}, False),
        (_target_row(4, TargetState.MANUAL), {"acquisitions": (_manual_order(4, _SECOND),)}, False),
        (_LEGACY, {"legacy_orders": (LegacyOrder(_ENTRY, 4, "subscription:old:4", None, complete=False),)}, False),
        (_LEGACY, {"legacy_orders": (LegacyOrder(_ENTRY, 4, "subscription:old:4", None, complete=True),)}, True),
    ],
    ids=["satisfied", "exhausted", "manual-ordered", "legacy-taken", "legacy-complete"],
)
def test_a_finished_season_closes_only_once_every_target_was_really_downloaded(
    world: _World, target: SubscriptionTarget, changes: dict[str, object], closed: bool
) -> None:
    with _running(world, _following(_finished(_DONE, target), auto=False, **changes)) as owner:
        assert owner._on_owner(lambda: owner._save(owner.state))
        saved: WatchState = _stored(owner, world)

    assert (not saved.subscriptions) is closed
    finished: list[str] = [
        item.name
        for item in HistoryJournal(world.store.history_path()).events(_MOMENT)
        if item.kind is HistoryKind.SUBSCRIPTION_FINISHED
    ]
    assert finished == (["Neko to Ryuu"] if closed else [])


def test_an_old_ordered_transfer_completing_after_migration_satisfies_its_target_without_a_new_order(
    world: _World,
) -> None:
    order: LegacyOrder = LegacyOrder(_ENTRY, 4, "subscription:old:4", "legacy", complete=False)
    state: WatchState = _following(
        _finished(_DONE, _LEGACY),
        auto=False,
        legacy_orders=(order,),
        acquisitions=(_legacy_transfer(AcquisitionState.ACCEPTED),),
    )
    with _running(world, state) as owner:
        assert owner._on_owner(lambda: owner._save(owner.state))
        waiting: bool = bool(_stored(owner, world).subscriptions)
        completed: AcquisitionConfirmation = _legacy_transfer(AcquisitionState.COMPLETE)
        assert owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(completed,))))
        saved: WatchState = _stored(owner, world)

    assert waiting
    assert saved.subscriptions == ()
    assert saved.legacy_orders == (order,)


@pytest.mark.parametrize("left", ["due", "exhausted", "attempting", "removed"])
def test_a_target_beyond_a_shrunk_season_blocks_its_close_until_it_is_downloaded_by_hand_or_removed(
    world: _World, left: str
) -> None:
    world.season.status = TitleStatus.FINISHED
    world.season.count = 3
    world.season.airs[4] = _AIRED - timedelta(minutes=30)
    world.season.offered = {4: (_stream(_SECOND, 4),)} if left == "attempting" else {}
    states: dict[str, TargetState] = {"exhausted": TargetState.EXHAUSTED, "attempting": TargetState.DUE}
    beyond: SubscriptionTarget = _target_row(
        4,
        states.get(left, TargetState.DUE),
        due_at=world.season.airs[4].isoformat(),
        attempts=3 if left == "exhausted" else 0,
    )
    with _running(world, _following(_finished(_DONE, beyond, count=3))) as owner:
        _check(owner, "check")
        _reaches(owner, TargetState.ATTEMPTING if left == "attempting" else beyond.state, 4)
        listed: ControlResponse = owner.handle(_request("subscriptions_list", command_id="list"))
        kept: bool = _record_of(owner) is not None
        if left == "removed":
            _command(owner, "subscription_remove", "remove", subscription_id="a")
        else:
            world.season.offered.setdefault(4, (_stream(_FIRST, 4),))
            assert _order(owner, 4, "d-4").reason == EpisodeReason.ADMITTED
            _download(world, owner, _SECOND if left == "attempting" else _FIRST, 4)
        _until(lambda: _record_of(owner) is None)
        saved: WatchState = _stored(owner, world)

    row: dict[str, object] = cast("list[dict[str, object]]", listed.result["subscriptions"])[0]
    assert (row["episode_count"], row["beyond_count"]) == (3, 4)
    assert kept
    assert (saved.removed_subscription is not None) is (left == "removed")
    finished: list[str] = [
        item.name
        for item in HistoryJournal(world.store.history_path()).events(_MOMENT)
        if item.kind is HistoryKind.SUBSCRIPTION_FINISHED
    ]
    assert finished == ([] if left == "removed" else ["Neko to Ryuu"])


def test_a_check_that_closes_the_season_logs_no_next_search(world: _World) -> None:
    world.season.status = TitleStatus.FINISHED
    logged: list[dict[str, object]] = []
    handler: int = loguru_logger.add(
        lambda message: logged.append(dict(message.record["extra"])),
        filter=lambda record: record["message"] == "Subscription next search",
    )
    try:
        record: SubscriptionRecord = _record(targets=(_DONE, _target_row(4, TargetState.SATISFIED)))
        with _running(world, _following(record, auto=False)) as owner:
            _check(owner, "check")
            closed: bool = _record_of(owner) is None
    finally:
        loguru_logger.remove(handler)

    assert closed
    assert [(item["subscription_id"], item["anilist_id"], item["number"], item["at"]) for item in logged] == [
        ("a", _ENTRY, None, None)
    ]


def test_pausing_a_subscription_lets_its_attempt_finish_and_starts_no_new_search(world: _World) -> None:
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _command(owner, "subscription_pause", "pause-a", subscription_id="a")
        asked: int = len(world.season.asked)
        _check(owner, "while-paused")
        _download(world, owner, _FIRST)
        _reaches(owner, TargetState.SATISFIED)
        record: SubscriptionRecord | None = _record_of(owner)

    assert record is not None
    assert record.paused
    assert len(world.season.asked) == asked
    assert (_FIRST, "cancel") not in world.network.actions
    assert _closures(world) == [(1, "accepted")]


def _pause(owner: AutomationOwner, enabled: bool, command_id: str) -> None:
    _command(owner, "set_auto", command_id, enabled=enabled)


@pytest.mark.parametrize("manual", [False, True], ids=["alone", "with-a-manual-download"])
def test_a_global_pause_keeps_the_stall_time_of_a_downloading_attempt_and_adds_none_of_its_own(
    world: _World, manual: bool
) -> None:
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _stage(world, owner, _FIRST)
        if manual:
            assert owner.admit_episode("manual-4", _choice_on(4, _SECOND)).ok
            _stage(world, owner, _SECOND, 4)
        _polls(world)
        world.ticks.now += _STALL_S - 60
        _polls(world)
        _pause(owner, False, "pause")
        _until(lambda: _FIRST in owner.state.pause_owned_transfers and not _transfer(owner, _FIRST).action_pending)
        world.ticks.now += _STALL_S + 100
        if manual:
            _polls(world)
        paused: SubscriptionTarget = _target(owner)
        _pause(owner, True, "resume")
        _until(lambda: world.network.tracked[_FIRST].state == "downloading")
        _polls(world)
        world.ticks.now += 59
        _polls(world)
        before: SubscriptionTarget = _target(owner)
        world.ticks.now += 1
        _reaches(owner, TargetState.DUE)
        closed: SubscriptionTarget = _target(owner)

    assert world.network.actions.count((_FIRST, "stop")) == 1
    assert (paused.state, before.state) == (TargetState.ATTEMPTING, TargetState.ATTEMPTING)
    assert (closed.attempts, closed.reason) == (1, "stalled")


@pytest.mark.parametrize("manual", [False, True], ids=["alone", "with-a-manual-download"])
def test_a_global_pause_neither_stops_nor_times_out_an_attempt_waiting_for_its_file_list(
    world: _World, manual: bool
) -> None:
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _until(lambda: any(item[0] == _FIRST for item in world.network.metadata_added))
        if manual:
            assert owner.admit_episode("manual-4", _choice_on(4, _SECOND)).ok
            _stage(world, owner, _SECOND, 4)
        _polls(world)
        world.ticks.now += automation_module.METADATA_TIMEOUT_S - 60
        _polls(world)
        _pause(owner, False, "pause")
        world.ticks.now += automation_module.METADATA_TIMEOUT_S + 100
        if manual:
            _polls(world)
        paused: tuple[str | None, tuple[str, ...]] = (
            _transfer(owner, _FIRST).problem,
            owner.state.pause_owned_transfers,
        )
        _pause(owner, True, "resume")
        _polls(world)
        world.ticks.now += 59
        _polls(world)
        before: str | None = _transfer(owner, _FIRST).problem
        world.ticks.now += 1
        _reaches(owner, TargetState.DUE)

    assert paused == (None, ())
    assert (_FIRST, "stop") not in world.network.actions
    assert before is None
    assert _closures(world) == [(1, "dead")]


def test_a_file_list_arriving_in_a_global_pause_is_selected_and_started_only_after_it(world: _World) -> None:
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _until(lambda: any(item[0] == _FIRST for item in world.network.metadata_added))
        assert owner.admit_episode("manual-4", _choice_on(4, _SECOND)).ok
        _stage(world, owner, _SECOND, 4)
        _pause(owner, False, "pause")
        world.network.deliver(_FIRST, _PACK)
        _polls(world)
        asked: int = len(world.season.asked)
        _check(owner, "while-paused")
        during: tuple[bool, bool, int] = (
            _FIRST in world.network.selected,
            _FIRST in world.network.started,
            len(world.season.asked) - asked,
        )
        _pause(owner, True, "resume")
        _until(lambda: _FIRST in world.network.started)

    assert during == (False, False, 0)
    assert world.network.selected[_FIRST] == frozenset(item.index for item in _files(3))
    assert world.network.unapproved_starts == []


def test_a_removed_subscription_rejected_by_its_check_tries_nothing_more_and_undo_keeps_its_attempts(
    world: _World,
) -> None:
    world.season.offered[3] = (_stream(_FIRST, seeders=300), _stream(_SECOND, seeders=200))
    world.probe.video = False
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _command(owner, "subscription_remove", "remove", subscription_id="a")
        _download(world, owner, _FIRST)
        _until(_failed(owner, _FIRST))
        removed: SubscriptionRecord | None = owner.state.removed_subscription
        _idle(owner)
        tried: list[str] = [item[0] for item in world.network.metadata_added]
        _command(owner, "subscription_restore", "undo")
        restored: SubscriptionTarget = _target(owner)
        world.probe.video = True
        _check(owner, "after-undo")
        saved: WatchState = _stored(owner, world)

    assert removed is not None
    assert (removed.targets[0].state, removed.targets[0].attempts, removed.targets[0].reason) == (
        TargetState.DUE,
        1,
        "rejected",
    )
    assert tried == [_FIRST]
    assert (restored.state, restored.attempts, restored.tried) == (TargetState.DUE, 1, (f"{_FIRST}:",))
    assert _hashes(_attempts(saved)) == [_FIRST, _SECOND]
    assert "sub:a:3:2" in _receipts(saved)


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
@pytest.mark.parametrize("stop", ["settled", "in-flight"])
def test_an_order_joining_a_transfer_stopped_by_the_pause_resumes_only_that_one(
    world: _World, stop: str, restart: bool
) -> None:
    world.season.airs[4] = _AIRED - timedelta(minutes=30)
    world.season.offered[4] = (_stream(_SECOND, 4),)
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _reaches(owner, TargetState.ATTEMPTING, 4)
        _started(world, _FIRST)
        _started(world, _SECOND)
        world.network.blocked = (_FIRST, "stop") if stop == "in-flight" else None
        _pause(owner, False, "pause")
        _until(lambda: set(owner.state.pause_owned_transfers) == {_FIRST, _SECOND})
        if stop == "in-flight":
            assert world.network.entered.wait(_TIMEOUT_S)
        else:
            _until(lambda: not _transfer(owner, _FIRST).action_pending)
        assert owner.admit_episode("manual-5", _choice_on(5, _FIRST)).ok
        world.network.release.set()
        _until(lambda: (_FIRST, "resume") in world.network.actions)
        joined: tuple[str, ...] = owner.state.pause_owned_transfers
    if restart:
        with _running(world) as owner:
            _polls(world)
            joined = owner.state.pause_owned_transfers

    assert joined == (_SECOND,)
    assert world.network.actions.index((_FIRST, "stop")) < world.network.actions.index((_FIRST, "resume"))
    assert (_SECOND, "resume") not in world.network.actions
    assert world.network.tracked[_FIRST].state == "downloading"


def test_an_attempt_joining_a_manual_transfer_keeps_working_through_a_pause_and_a_restart(world: _World) -> None:
    with _running(world, _following(auto=False)) as owner:
        assert owner.admit_episode("manual-4", _choice_on(4, _FIRST)).ok
        _command(owner, "set_auto", "resume", enabled=True)
        _reaches(owner, TargetState.ATTEMPTING)
        _started(world, _FIRST)
        _pause(owner, False, "pause")
        _polls(world)
    with _running(world) as owner:
        _polls(world)
        owned: tuple[str, ...] = owner.state.pause_owned_transfers
        target: SubscriptionTarget = _target(owner)

    assert owned == ()
    assert (_FIRST, "stop") not in world.network.actions
    assert world.network.tracked[_FIRST].state == "downloading"
    assert target.state is TargetState.ATTEMPTING


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
def test_replacing_the_only_manual_order_of_a_mixed_transfer_in_a_pause_stops_it_for_the_pause(
    world: _World, restart: bool
) -> None:
    with _running(world, _following(auto=False)) as owner:
        assert owner.admit_episode("manual-4", _choice_on(4, _FIRST)).ok
        _command(owner, "set_auto", "resume", enabled=True)
        _reaches(owner, TargetState.ATTEMPTING)
        _started(world, _FIRST)
        _pause(owner, False, "pause")
        manual: str = next(
            item.admission_id for item in _transfer(owner, _FIRST).assignments if item.source is AdmissionSource.MANUAL
        )
        replaced: ControlResponse = owner._on_owner(
            lambda: owner._admit_episode("replace-4", _choice_on(4, _THIRD), previous=manual)
        )
        stored: WatchState = _stored(owner, world)
        if not restart:
            _until(lambda: (_FIRST, "stop") in world.network.actions)
    with _running(world) as owner:
        _until(lambda: (_FIRST, "stop") in world.network.actions)
        _until(lambda: not _transfer(owner, _FIRST).action_pending)
        _pause(owner, True, "unpause")
        _until(lambda: (_FIRST, "resume") in world.network.actions)

    assert replaced.ok
    shared: AcquisitionConfirmation = next(item for item in stored.acquisitions if item.info_hash == _FIRST)
    assert (shared.requested_action, stored.pause_owned_transfers) == ("stop", (_FIRST,))
    assert world.network.actions.count((_FIRST, "stop")) == 1


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize("failure", ["exception", "timeout", "404"])
def test_an_ani_zip_outage_checks_admits_and_verifies_from_the_saved_mapping_also_after_a_restart(
    world: _World, failure: str
) -> None:
    refreshed: str = (_MOMENT - timedelta(days=1)).isoformat()
    record: SubscriptionRecord = _record(mapping=replace(_mapping(length=24), max_age_s=None), refreshed_at=refreshed)
    handlers: dict[str, Callable[[httpx.Request], httpx.Response]] = {
        "timeout": _timeout,
        "404": lambda request: httpx.Response(404),
    }
    world.season.down = failure == "exception"
    with httpx.Client(transport=httpx.MockTransport(handlers.get(failure, _timeout))) as http:
        world.episodes = None if failure == "exception" else AniZipCatalog(http)
        with _running(world, _following(record)) as owner:
            _reaches(owner, TargetState.ATTEMPTING)
        with _running(world) as owner:
            _download(world, owner, _FIRST)
            _reaches(owner, TargetState.SATISFIED)
    saved: WatchState = world.store.load()

    assert _attempts(saved)[0].verification == "no_contradiction"
    kept: SubscriptionRecord = saved.subscriptions[0]
    assert (kept.mapping, kept.refreshed_at, kept.problem) == (record.mapping, refreshed, None)
    sources: set[object] = {item.get("mapping_source") for item in _decisions(world) if item.get("source") == "ani.zip"}
    assert sources == {"snapshot"}


def _held_check(world: _World) -> tuple[threading.Event, threading.Event]:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    probe: _Snapshots = _Snapshots()

    def hold() -> None:
        entered.set()
        assert release.wait(_TIMEOUT_S)

    probe.hook = hold
    world.probe = probe
    return entered, release


def _rows(owner: AutomationOwner) -> list[dict[str, object]]:
    answer: ControlResponse = owner.handle(_request("subscriptions_list", command_id="list"))
    return cast("list[dict[str, object]]", answer.result["subscriptions"])


def test_an_ambiguous_pack_keeps_the_attempt_until_the_user_picks_its_file(world: _World) -> None:
    pack: tuple[TorrentFile, ...] = (TorrentFile(0, "Pack/unknown.mkv", 400, 0.0, 1),)
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _until(lambda: any(item[0] == _FIRST for item in world.network.metadata_added))
        world.network.deliver(_FIRST, pack)
        _until(lambda: _transfer(owner, _FIRST).assignments[0].mapped)
        _polls(world)
        waiting: tuple[TargetState, object] = (_target(owner).state, _status(owner, 3)["reason"])
        _command(
            owner,
            "episode_file_choose",
            "choose",
            admission_id=_transfer(owner, _FIRST).assignments[0].admission_id,
            revision=file_map_revision(pack),
            file={"index": 0, "path": "Pack/unknown.mkv", "size": 400},
        )
        _until(lambda: _FIRST in world.network.started)
        chosen: tuple[object, ...] = _transfer(owner, _FIRST).assignments[0].files
        target: SubscriptionTarget = _target(owner)

    assert waiting == (TargetState.ATTEMPTING, EpisodeReason.EPISODE_FILE_UNRESOLVED)
    assert chosen == ((0, "Pack/unknown.mkv", 400),)
    assert (target.state, target.attempts) == (TargetState.ATTEMPTING, 1)
    assert (_FIRST, "cancel") not in world.network.actions


def test_an_order_taking_over_an_attempt_in_its_check_on_the_same_release_keeps_its_video(world: _World) -> None:
    entered, release = _held_check(world)
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _download(world, owner, _FIRST)
        assert entered.wait(_TIMEOUT_S)
        try:
            result: EpisodeResult = _order(owner, 3, "d-3")
        finally:
            release.set()
        _reaches(owner, TargetState.SATISFIED)
        saved: WatchState = _stored(owner, world)

    attempt, manual = next(item for item in saved.acquisitions if item.info_hash == _FIRST).assignments
    assert result.reason == EpisodeReason.ADMITTED
    assert (attempt.replaced, attempt.publication) == (True, None)
    assert (manual.source, manual.previous_admission_id) == (AdmissionSource.MANUAL, attempt.admission_id)
    assert manual.files == attempt.files
    assert {"Neko to Ryuu - 03.mkv", "Neko to Ryuu - 03.ass"} <= _root_files(world)


def test_a_rejected_attempt_of_a_subscription_pushed_out_of_the_undo_slot_still_cancels_its_transfer(
    world: _World,
) -> None:
    second: SubscriptionRecord = _record(
        subscription_id="b", anilist_id=_OTHER, paused=True, pause_reason=PauseReason.USER
    )
    world.probe.video = False
    with _running(world, _following(_record(), second)) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _command(owner, "subscription_remove", "remove-a", subscription_id="a")
        _command(owner, "subscription_remove", "remove-b", subscription_id="b")
        _download(world, owner, _FIRST)
        _until(_failed(owner, _FIRST))
        saved: WatchState = _stored(owner, world)

    assert [item.verification for item in _attempts(saved)] == ["reject:no_video_stream"]
    assert (_FIRST, "cancel") in world.network.actions
    assert saved.removed_subscription is not None
    assert (saved.subscriptions, saved.removed_subscription.subscription_id) == ((), "b")
    assert not _root_files(world)


@pytest.mark.parametrize("shared", [False, True], ids=["own", "shared"])
def test_a_manual_order_that_succeeds_satisfies_its_target_and_finishes_normally(world: _World, shared: bool) -> None:
    with _running(world, _following(auto=False)) as owner:
        assert _order(owner, 3, "d-3").reason == EpisodeReason.ADMITTED
        if shared:
            assert owner.admit_episode("manual-5", _choice_on(5, _FIRST)).ok
        _pause(owner, True, "resume")
        _reaches(owner, TargetState.MANUAL)
        _stage(world, owner, _FIRST)
        if shared:
            _complete(world, _FIRST, 3)
        else:
            world.network.finish(_FIRST)
        _reaches(owner, TargetState.SATISFIED)
        if shared:
            _polls(world)
        else:
            _until(lambda: _transfer(owner, _FIRST).cleaned)
    saved: WatchState = world.store.load()

    transfer: AcquisitionConfirmation = next(item for item in saved.acquisitions if item.info_hash == _FIRST)
    manual: EpisodeAssignment = next(item for item in transfer.assignments if item.choice.number == 3)
    assert (manual.replaced, automation_module._handed_off(manual)) == (False, True)
    assert transfer.requested_action is None
    assert (_FIRST, "cancel") not in world.network.actions
    assert [item.choice.number for item in transfer.active_assignments] == ([3, 5] if shared else [3])
    assert transfer.state is (AcquisitionState.ACCEPTED if shared else AcquisitionState.COMPLETE)
    assert {"Neko to Ryuu - 03.mkv", "Neko to Ryuu - 03.ass"} <= _root_files(world)


@pytest.mark.parametrize("how", ["metadata", "stall"])
def test_a_manual_order_that_dies_hands_its_target_back_to_the_next_automatic_attempt(world: _World, how: str) -> None:
    with _running(world, _following(auto=False)) as owner:
        assert _order(owner, 3, "d-3").reason == EpisodeReason.ADMITTED
        _pause(owner, True, "resume")
        _reaches(owner, TargetState.MANUAL)
        _fail(world, owner, _FIRST, how)
        _until(_failed(owner, _FIRST))
        released: SubscriptionTarget = _target(owner)
        world.season.offered[3] = (_stream(_SECOND),)
        _check(owner, "after-manual")
        _reaches(owner, TargetState.ATTEMPTING)
        saved: WatchState = _stored(owner, world)

    assert (released.state, released.attempts) == (TargetState.DUE, 0)
    assert (_FIRST, "cancel") in world.network.actions
    assert [(item.choice.reference.info_hash, item.previous_admission_id) for item in _attempts(saved)] == [
        (_SECOND, None)
    ]


def test_a_manual_order_that_dies_in_a_shared_pack_is_withdrawn_and_replaced_by_the_next_attempt(
    world: _World,
) -> None:
    world.season.airs[3] = _AIRED - 3 * timedelta(days=1)
    world.season.airs[4] = _AIRED
    world.season.offered[4] = (_stream(_FIRST, 4),)
    with _running(world, _following(auto=False)) as owner:
        assert _order(owner, 3, "d-3").reason == EpisodeReason.ADMITTED
        assert _order(owner, 4, "d-4").reason == EpisodeReason.ADMITTED
        _pause(owner, True, "resume")
        _reaches(owner, TargetState.MANUAL, 4)
        _fail(world, owner, _FIRST, "stall")
        _reaches(owner, TargetState.DUE, 4)
        withdrawn: AcquisitionConfirmation = _transfer(owner, _FIRST)
        world.season.offered[4] = (_stream(_SECOND, 4),)
        _check(owner, "after-manual")
        _reaches(owner, TargetState.ATTEMPTING, 4)
    saved: WatchState = world.store.load()

    manual: str = next(item.admission_id for item in withdrawn.assignments if item.choice.number == 4)
    assert [item.choice.number for item in withdrawn.active_assignments] == [3]
    assert (_FIRST, "cancel") not in world.network.actions
    assert [(item.choice.reference.info_hash, item.previous_admission_id) for item in _attempts(saved, 4)] == [
        (_SECOND, manual)
    ]


def test_a_manual_order_that_dies_in_a_global_pause_keeps_its_target_manual(world: _World) -> None:
    world.season.offered[3] = (_uncertain(),)
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.DUE)
        _pause(owner, False, "pause")
        assert _order(owner, 3, "d-3").reason == EpisodeReason.ADMITTED
        _reaches(owner, TargetState.MANUAL)
        _fail(world, owner, _FIRST, "metadata")
        _until(lambda: _transfer(owner, _FIRST).problem is not None)
        _polls(world)
        target: SubscriptionTarget = _target(owner)

    assert target.state is TargetState.MANUAL
    assert (_FIRST, "cancel") not in world.network.actions


def test_one_check_never_admits_one_release_file_for_two_targets(world: _World) -> None:
    world.season.airs[4] = _AIRED
    world.season.offered[3] = (replace(_stream(_FIRST, 3), file_index=0),)
    world.season.offered[4] = (replace(_stream(_FIRST, 4, seeders=300), file_index=0), _stream(_SECOND, 4))
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _reaches(owner, TargetState.ATTEMPTING, 4)
        saved: WatchState = _stored(owner, world)

    admitted: list[tuple[int, str, int | None]] = [
        (item.choice.number, item.choice.reference.info_hash, item.choice.reference.file_index)
        for item in (*_attempts(saved, 3), *_attempts(saved, 4))
    ]
    assert admitted == [(3, _FIRST, 0), (4, _SECOND, None)]


def test_a_later_check_never_admits_a_file_held_by_another_target_of_the_subscription(world: _World) -> None:
    world.season.airs[4] = _AIRED
    world.season.offered[3] = (replace(_stream(_FIRST, 3), file_index=0),)
    world.season.offered[4] = ()
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        world.season.offered[4] = (replace(_stream(_FIRST, 4, seeders=300), file_index=0), _stream(_SECOND, 4))
        _check(owner, "check-4")
        _reaches(owner, TargetState.ATTEMPTING, 4)
    saved: WatchState = world.store.load()

    admitted: list[tuple[int, str, int | None]] = [
        (item.choice.number, item.choice.reference.info_hash, item.choice.reference.file_index)
        for item in (*_attempts(saved, 3), *_attempts(saved, 4))
    ]
    assert admitted == [(3, _FIRST, 0), (4, _SECOND, None)]


def test_a_check_never_admits_a_file_a_manual_order_of_another_target_holds(world: _World) -> None:
    world.season.airs[4] = _AIRED
    world.season.offered[3] = (replace(_stream(_FIRST, 3), file_index=0),)
    world.season.offered[4] = (replace(_stream(_FIRST, 4), file_index=0),)
    with _running(world, _following(auto=False)) as owner:
        assert _order(owner, 3, "d-3").reason == EpisodeReason.ADMITTED
        _pause(owner, True, "resume")
        _reaches(owner, TargetState.MANUAL)
        _check(owner, "check-4")
        target: SubscriptionTarget = _target(owner, 4)
    saved: WatchState = world.store.load()

    assert (target.state, target.attempts) == (TargetState.DUE, 0)
    assert _attempts(saved, 4) == []
    assert [(item.choice.number, item.source) for item in saved.acquisitions[0].assignments] == [
        (3, AdmissionSource.MANUAL)
    ]


def test_two_subscriptions_of_different_entries_never_admit_the_same_file(world: _World) -> None:
    second: SubscriptionRecord = replace(_record(), subscription_id="b", anilist_id=_OTHER)
    world.season.offered[3] = (replace(_stream(_FIRST, 3), file_index=0),)
    with _running(world, _following(_record(), second)) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        _idle(owner)
        stored: WatchState = _stored(owner, world)

    pairs: list[tuple[str, int | None]] = [
        (item.choice.reference.info_hash, item.choice.reference.file_index)
        for transfer in stored.acquisitions
        for item in transfer.assignments
    ]
    assert pairs == [(_FIRST, 0)]


def test_the_list_names_the_episode_whose_download_is_being_checked(world: _World) -> None:
    entered, release = _held_check(world)
    with _running(world, _following()) as owner:
        _reaches(owner, TargetState.ATTEMPTING)
        before: object = _rows(owner)[0]["checking_number"]
        _download(world, owner, _FIRST)
        assert entered.wait(_TIMEOUT_S)
        try:
            during: object = _rows(owner)[0]["checking_number"]
        finally:
            release.set()
        _reaches(owner, TargetState.SATISFIED)
        after: object = _rows(owner)[0]["checking_number"]

    assert (before, during, after) == (None, 3, None)


@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
def test_cancelling_the_only_manual_transfer_of_a_mixed_pack_in_a_pause_closes_its_attempt_after_the_pause(
    world: _World, restart: bool
) -> None:
    with _running(world, _following(auto=False)) as owner:
        assert owner.admit_episode("manual-4", _choice_on(4, _FIRST)).ok
        _command(owner, "set_auto", "resume", enabled=True)
        _reaches(owner, TargetState.ATTEMPTING)
        _started(world, _FIRST)
        _pause(owner, False, "pause")
        _command(owner, "transfer", "cancel-pack", info_hash=_FIRST, action="cancel")
        _until(_failed(owner, _FIRST))
        paused: tuple[TargetState, tuple[str, ...]] = (_target(owner).state, owner.state.pause_owned_transfers)
        if not restart:
            _pause(owner, True, "unpause")
            _reaches(owner, TargetState.DUE)
    if restart:
        with _running(world) as owner:
            _pause(owner, True, "unpause")
            _reaches(owner, TargetState.DUE)
    saved: WatchState = world.store.load()

    assert paused == (TargetState.ATTEMPTING, ())
    assert world.network.actions.count((_FIRST, "cancel")) == 1
    assert (_FIRST, "stop") not in world.network.actions
    target: SubscriptionTarget = saved.subscriptions[0].targets[0]
    assert (target.attempts, target.reason) == (1, "failed")
    assert _closures(world) == [(1, "dead")]
