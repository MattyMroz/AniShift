from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from episode_download_support import Catalog, make_pack, private_client, resident, wait_for

from anishift.application import automation as automation_module
from anishift.application import watch as watch_module
from anishift.application.automation import AutomationOwner
from anishift.application.control import AutomationPolicy, EpisodeAssignment, WatchState
from anishift.application.episode_selection import AniZipMapping, StreamCandidate
from anishift.application.history import HistoryJournal, HistoryKind
from anishift.application.subscription_targets import SubscriptionRecord, SubscriptionTarget, TargetState
from anishift.application.watch_state import WatchStateStore
from anishift.platform.qbittorrent_process import ManagedQBittorrent
from anishift.services.catalog import EpisodeAiring, SeasonAiring, TitleStatus
from anishift.services.media import DefaultMediaProbe
from anishift.services.torrents import TorrentFile, TorrentInfo
from anishift.services.torrents.errors import TorrentClientError

_NOW: datetime = datetime.now(UTC)

_SELECTED: list[int] = [0, 0, 0, 0, 1, 1]


class _AiredCatalog(Catalog):
    def __init__(self, info_hash: str, rejected: str | None = None) -> None:
        super().__init__(info_hash)
        self.rejected: str | None = rejected

    def mapping(self, anilist_id: int) -> AniZipMapping:
        listed: AniZipMapping = super().mapping(anilist_id)
        episodes: dict[str, dict[str, object]] = {key: dict(value) for key, value in listed.raw_episodes.items()}
        episodes["3"]["length"] = 2 / 60
        return replace(listed, raw_episodes=episodes)

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        return SeasonAiring(
            anilist_id,
            TitleStatus.FINISHED,
            3,
            (
                EpisodeAiring(1, _NOW - timedelta(days=10)),
                EpisodeAiring(2, _NOW - timedelta(days=3)),
                EpisodeAiring(3, _NOW - timedelta(hours=1)),
            ),
        )

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        found: tuple[StreamCandidate, ...] = super().streams(kitsu_id, number)
        if self.rejected is None:
            return found
        return (replace(found[0], info_hash=self.rejected, seeders=200), *found)


@pytest.fixture
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.1)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.1)
    monkeypatch.setattr(watch_module, "QUIET_S", 0.1)


def _subscribed(root: Path) -> WatchStateStore:
    record: SubscriptionRecord = SubscriptionRecord(
        "neko",
        500,
        "Neko to Ryuu",
        (_NOW - timedelta(days=1)).isoformat(),
        2,
        kitsu_id=500,
        mapping=_AiredCatalog("").mapping(500),
        catalog_status="FINISHED",
        episode_count=3,
        targets=(SubscriptionTarget(3, (_NOW - timedelta(hours=1)).isoformat(), TargetState.DUE, 0),),
    )
    store: WatchStateStore = WatchStateStore(root / "watch/state.json", subscriptions_path=root / "absent.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), subscriptions=(record,)))
    return store


def _seed(seed: ManagedQBittorrent, api: httpx.Client, root: Path, torrents: tuple[bytes, ...]) -> None:
    seed.set_preferences({"max_ratio": -1, "max_seeding_time": -1, "max_inactive_seeding_time": -1})
    for torrent in torrents:
        api.post(
            "torrents/add",
            files={"torrents": ("fixture.torrent", torrent)},
            data={
                "savepath": str(root),
                "category": "AniShift",
                "stopped": "false",
                "autoTMM": "false",
                "contentLayout": "Original",
            },
        ).raise_for_status()

    def seeding() -> bool:
        entries = seed.torrents("AniShift")
        return len(entries) == len(torrents) and all(
            item.progress == 1 and item.state in {"stalledUP", "uploading"} for item in entries
        )

    wait_for(seeding, "local seeder")


def _follow(  # noqa: PLR0913
    owner: AutomationOwner,
    receiver: ManagedQBittorrent,
    apis: tuple[httpx.Client, httpx.Client],
    peers: tuple[int, int],
    done: Callable[[WatchState], bool],
    priorities: list[list[int]],
) -> None:
    api, seed_api = apis
    deadline: float = time.monotonic() + 150
    next_peer: float = 0.0
    while time.monotonic() < deadline:
        if done(owner.state):
            return
        try:
            listed: tuple[TorrentInfo, ...] = receiver.torrents("AniShift")
        except TorrentClientError:
            listed = ()
        for transfer in listed:
            if receiver.released_hashes(frozenset({transfer.info_hash})):
                continue
            try:
                files: tuple[TorrentFile, ...] = receiver.files(transfer.info_hash)
            except TorrentClientError:
                continue
            if files:
                priorities.append([item.priority for item in files])
            if time.monotonic() >= next_peer:
                api.post(
                    "torrents/addPeers", data={"hashes": transfer.info_hash, "peers": f"127.0.0.1:{peers[0]}"}
                ).raise_for_status()
                seed_api.post(
                    "torrents/addPeers", data={"hashes": transfer.info_hash, "peers": f"127.0.0.1:{peers[1]}"}
                ).raise_for_status()
        if time.monotonic() >= next_peer:
            next_peer = time.monotonic() + 0.5
        time.sleep(0.05)
    pytest.fail(json.dumps({"state": str(owner.state), "receiver": api.get("torrents/info").json()}))


def _finished(state: WatchState) -> bool:
    return not state.subscriptions and bool(state.ready_groups) and state.acquisitions[-1].cleaned


def _decisions(store: WatchStateStore) -> list[dict[str, object]]:
    path: Path = store.history_path().with_name("decisions.jsonl")
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _assert_finished_season(store: WatchStateStore, final: WatchState, workspace: Path) -> EpisodeAssignment:
    assert len(final.ready_groups) == 1
    group = final.ready_groups[0]
    assert group.main_result is not None
    assert (workspace / group.main_result).is_file()
    assert "Neko to Ryuu - 03" in group.main_result
    assert not (workspace / "temp/.acquisition" / final.acquisitions[-1].operation_id).exists()
    history: list[str] = [
        item.name
        for item in HistoryJournal(store.history_path()).events(_NOW - timedelta(days=1))
        if item.kind is HistoryKind.SUBSCRIPTION_FINISHED
    ]
    assert history == ["Neko to Ryuu"]
    satisfied: EpisodeAssignment = final.acquisitions[-1].assignments[0]
    assert satisfied.group_id is not None
    return satisfied


def _adds(requests: list[httpx.Request]) -> list[str]:
    magnets: list[str] = [
        parse_qs(item.content.decode())["urls"][0] for item in requests if item.url.path.endswith("/torrents/add")
    ]
    return [parse_qs(urlsplit(item).query)["xt"][0].removeprefix("urn:btih:").casefold() for item in magnets]


def _started(state: WatchState) -> bool:
    return any(item.content_started for item in state.acquisitions)


@pytest.mark.integration
@pytest.mark.usefixtures("quick")
def test_a_due_target_downloads_only_its_episode_across_an_owner_restart_and_finishes_the_season(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torrent, info_hash = make_pack(tmp_path / "seed-data")
    seed_requests: list[httpx.Request] = []
    receiver_requests: list[httpx.Request] = []
    priorities: list[list[int]] = []
    catalog: _AiredCatalog = _AiredCatalog(info_hash)
    store: WatchStateStore = _subscribed(tmp_path)
    with (
        private_client(tmp_path / "seed", monkeypatch, seed_requests) as (seed, seed_api, peer),
        private_client(tmp_path / "receiver", monkeypatch, receiver_requests) as (receiver, api, receiver_peer),
    ):
        _seed(seed, seed_api, tmp_path / "seed-data", (torrent,))
        seed.set_preferences({"up_limit": 1024})
        links: tuple[tuple[httpx.Client, httpx.Client], tuple[int, int]] = ((api, seed_api), (peer, receiver_peer))
        with resident(tmp_path, receiver, catalog, DefaultMediaProbe()) as (owner, _service, _client):
            _follow(owner, receiver, *links, _started, priorities)
            assert not owner.state.ready_groups
        seed.set_preferences({"up_limit": 0})
        with resident(tmp_path, receiver, catalog, DefaultMediaProbe()) as (owner, _service, client):
            _follow(owner, receiver, *links, _finished, priorities)
            final: WatchState = owner.state
            listed: Mapping[str, object] = client.call("subscriptions_list")

    assert _adds(receiver_requests) == [info_hash]
    assert catalog.asked == [3]
    assert priorities[-1] == _SELECTED
    assert {tuple(item) for item in priorities} <= {(1, 1, 1, 1, 1, 1), tuple(_SELECTED)}
    assert len(final.acquisitions) == 1
    satisfied: EpisodeAssignment = _assert_finished_season(store, final, tmp_path / "workspace")
    assert (satisfied.subscription_id, satisfied.attempt, satisfied.verification) == ("neko", 1, "no_contradiction")
    assert listed["subscriptions"] == []
    decisions: list[dict[str, object]] = _decisions(store)
    assert [(item["verdict"], item["entry"]) for item in decisions if item.get("source") == "h2"] == [
        ("no_contradiction", "subscription")
    ]
    assert [item["entry"] for item in decisions if item["kind"] == "selection"] == ["subscription"]


@pytest.mark.integration
@pytest.mark.usefixtures("quick")
def test_a_release_without_video_is_rejected_cancelled_and_replaced_by_the_next_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad, bad_hash = make_pack(tmp_path / "seed-data", name="F7-silent", video=False)
    good, good_hash = make_pack(tmp_path / "seed-data")
    seed_requests: list[httpx.Request] = []
    receiver_requests: list[httpx.Request] = []
    priorities: list[list[int]] = []
    catalog: _AiredCatalog = _AiredCatalog(good_hash, bad_hash)
    store: WatchStateStore = _subscribed(tmp_path)
    workspace: Path = tmp_path / "workspace"
    with (
        private_client(tmp_path / "seed", monkeypatch, seed_requests) as (seed, seed_api, peer),
        private_client(tmp_path / "receiver", monkeypatch, receiver_requests) as (receiver, api, receiver_peer),
    ):
        _seed(seed, seed_api, tmp_path / "seed-data", (bad, good))
        links: tuple[tuple[httpx.Client, httpx.Client], tuple[int, int]] = ((api, seed_api), (peer, receiver_peer))
        with resident(tmp_path, receiver, catalog, DefaultMediaProbe()) as (owner, _service, client):

            def cancelled(state: WatchState) -> bool:
                target: SubscriptionTarget = state.subscriptions[0].targets[0]
                return target.state is TargetState.DUE and target.attempts == 1 and not receiver.torrents("AniShift")

            _follow(owner, receiver, *links, cancelled, priorities)
            assert not list(workspace.glob("*.mkv"))
            client.call("subscription_check", {"subscription_id": "neko"}, command_id="check-again")
            _follow(owner, receiver, *links, _finished, priorities)
            final: WatchState = owner.state

    assert _adds(receiver_requests) == [bad_hash, good_hash]
    satisfied: EpisodeAssignment = _assert_finished_season(store, final, workspace)
    assert (satisfied.attempt, satisfied.previous_admission_id, satisfied.choice.reference.info_hash) == (
        2,
        None,
        good_hash,
    )
    rejected: EpisodeAssignment = final.acquisitions[0].assignments[0]
    assert (rejected.choice.reference.info_hash, rejected.publication) == (bad_hash, None)
    assert not any("F7-silent" in name for group in final.ready_groups for name in group.sources)
    checks: list[tuple[object, object]] = [
        (item["verdict"], item["reason"]) for item in _decisions(store) if item.get("source") == "h2"
    ]
    assert checks == [("reject", "no_video_stream"), ("no_contradiction", "duration_within_tolerance")]
