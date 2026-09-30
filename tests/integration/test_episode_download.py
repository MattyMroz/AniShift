from __future__ import annotations

import json
import time
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from episode_download_support import Catalog, make_pack, private_client, resident, seed_ready, wait_for

from anishift.application import automation as automation_module
from anishift.application import watch as watch_module
from anishift.application.control import AcquisitionConfirmation, RequestState, WatchState
from anishift.application.watch_state import WatchStateStore
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import ControlClient
from anishift.services.torrents import TorrentFile
from anishift.services.torrents.errors import TorrentClientError


def _download(client: ControlClient, number: int) -> None:
    client.call(
        "episode_download",
        {"keys": [{"anilist_id": 500, "number": number}]},
        command_id=f"download-{number}",
        instance_id="f7",
    )


def _record(state: WatchState, times: dict[str, float], start: float) -> None:
    elapsed: float = round(time.monotonic() - start, 4)
    for transfer in state.acquisitions:
        for item in transfer.assignments:
            prefix: str = f"E{item.choice.number}"
            times.setdefault(f"{prefix}:admitted", elapsed)
            if item.files:
                times.setdefault(f"{prefix}:metadata", elapsed)
            if transfer.content_started:
                times.setdefault(f"{prefix}:started", elapsed)
            if item.publication is not None and item.publication.handed_off:
                times.setdefault(f"{prefix}:handoff", elapsed)
    for group in state.ready_groups:
        for number in (1, 3):
            if f" - {number:02}" in group.stem:
                times.setdefault(f"E{number}:ready", elapsed)


@pytest.mark.integration
def test_selected_pack_survives_owner_and_qb_restart_to_two_library_results_without_unordered_episode(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.1)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.1)
    monkeypatch.setattr(watch_module, "QUIET_S", 0.1)
    torrent, info_hash = make_pack(tmp_path / "seed-data")
    seed_requests: list[httpx.Request] = []
    receiver_requests: list[httpx.Request] = []
    times: dict[str, float] = {}
    priorities: list[list[int]] = []
    peer_attempts: int = 0
    catalog: Catalog = Catalog(info_hash)
    with (
        private_client(tmp_path / "seed", monkeypatch, seed_requests) as (seed, seed_api, peer),
        private_client(tmp_path / "receiver", monkeypatch, receiver_requests) as (receiver, api, receiver_peer),
    ):
        version: str = receiver.version()
        seed.set_preferences({"max_ratio": -1, "max_seeding_time": -1, "max_inactive_seeding_time": -1})
        seed_api.post(
            "torrents/add",
            files={"torrents": ("fixture.torrent", torrent)},
            data={
                "savepath": str(tmp_path / "seed-data"),
                "category": "AniShift",
                "stopped": "false",
                "autoTMM": "false",
                "contentLayout": "Original",
            },
        ).raise_for_status()
        wait_for(lambda: seed_ready(seed), "local seeder")
        seed.set_preferences({"up_limit": 1024})
        start: float = time.monotonic()
        times["E1:D"] = 0.0
        with resident(tmp_path, receiver, catalog) as (owner, service, client):
            _download(client, 1)
            wait_for(lambda: bool(receiver.torrents("AniShift")), "one magnet admitted")
            _record(owner.state, times, start)
            times["E3:D"] = round(time.monotonic() - start, 4)
            _download(client, 3)
            wait_for(lambda: len(owner.state.acquisitions[0].assignments) == 2, "joined E3")
            _record(owner.state, times, start)
            assert len(receiver.torrents("AniShift")) == 1
            operation: str = owner.state.acquisitions[0].operation_id
            unordered: Path = (
                tmp_path / "workspace/temp/.acquisition" / operation / "data/F7-pack/Neko to Ryuu - 02.mkv"
            )
            unordered.parent.mkdir(parents=True, exist_ok=True)
            unordered.write_bytes(b"unrequested-fragment")
            assert service.discover().groups == ()
            assert service.discover(changed_paths=(unordered,)).groups == ()
            deadline: float = time.monotonic() + 45
            while not owner.state.acquisitions[0].content_started:
                assert time.monotonic() < deadline, "content start before restart"
                _record(owner.state, times, start)
                api.post(
                    "torrents/addPeers", data={"hashes": info_hash, "peers": f"127.0.0.1:{peer}"}
                ).raise_for_status()
                seed_api.post(
                    "torrents/addPeers", data={"hashes": info_hash, "peers": f"127.0.0.1:{receiver_peer}"}
                ).raise_for_status()
                peer_attempts += 1
                time.sleep(0.1)
            _record(owner.state, times, start)
            assert receiver.torrents("AniShift")[0].progress < 1
        previous_child = receiver._child
        assert previous_child is not None
        receiver.close_owned()
        assert previous_child.poll() is not None
        receiver.prepare()
        assert receiver._child is not None
        assert receiver._child.pid != previous_child.pid
        assert receiver._state is not None
        api.base_url = httpx.URL(f"http://127.0.0.1:{receiver._state.port}/api/v2/")
        api.post("auth/login", data={"username": "admin", "password": receiver._password()}).raise_for_status()
        receiver.set_preferences({"listen_port": receiver_peer})
        assert receiver.preferences()["resolve_peer_countries"] is False
        times["qb_restarted"] = round(time.monotonic() - start, 4)
        seed.set_preferences({"up_limit": 0})
        with resident(tmp_path, receiver, catalog) as (owner, service, client):
            _download(client, 1)
            _download(client, 3)
            assert service.discover().groups == ()
            assert service.discover(changed_paths=(unordered,)).groups == ()
            deadline = time.monotonic() + 150
            next_peer: float = 0.0
            while time.monotonic() < deadline:
                _record(owner.state, times, start)
                transfer: AcquisitionConfirmation = owner.state.acquisitions[0]
                if len(owner.state.ready_groups) == 2 and transfer.cleaned:
                    break
                assert not any(item.state is RequestState.FAILED for item in owner.state.requests), [
                    item.problem for item in owner.state.requests
                ]
                files: tuple[TorrentFile, ...] = ()
                try:
                    if not receiver.released_hashes(frozenset({info_hash})):
                        files = receiver.files(info_hash)
                except TorrentClientError:
                    assert receiver.released_hashes(frozenset({info_hash}))
                if files:
                    priorities.append([item.priority for item in files])
                for number in (1, 3):
                    selected: list[TorrentFile] = [item for item in files if f" - {number:02}." in item.name]
                    if len(selected) == 2 and all(item.progress == 1 for item in selected):
                        times.setdefault(f"E{number}:complete", round(time.monotonic() - start, 4))
                if time.monotonic() >= next_peer and not receiver.released_hashes(frozenset({info_hash})):
                    api.post(
                        "torrents/addPeers", data={"hashes": info_hash, "peers": f"127.0.0.1:{peer}"}
                    ).raise_for_status()
                    seed_api.post(
                        "torrents/addPeers", data={"hashes": info_hash, "peers": f"127.0.0.1:{receiver_peer}"}
                    ).raise_for_status()
                    peer_attempts += 1
                    next_peer = time.monotonic() + 0.5
                time.sleep(0.05)
            else:
                pytest.fail(
                    json.dumps(
                        {
                            "times": times,
                            "transfer": str(owner.state.acquisitions),
                            "requests": str(owner.state.requests),
                            "receiver": api.get("torrents/info").json(),
                            "seed": seed_api.get("torrents/info").json(),
                            "peers": api.get("sync/torrentPeers", params={"hash": info_hash}).json(),
                        }
                    )
                )
            workspace: Path = tmp_path / "workspace"
            data: Path = workspace / "temp/.acquisition" / operation / "data"
            owner.files_changed(DirectoryChange(reconcile=True))
            owner.files_changed(DirectoryChange(paths=(data / "F7-pack/Neko to Ryuu - 02.mkv",)))
            groups: set[str] = {group.source.stem for group in service.discover().groups}
            assert groups == {"Neko to Ryuu - 01", "Neko to Ryuu - 03"}
            assert {group.source.stem for group in service.discover(changed_paths=(data,)).groups} == groups
            state: WatchState = owner.state
            assert len(state.acquisitions) == 1
            assert {item.choice.number for item in state.acquisitions[0].assignments} == {1, 3}
            assert len({item.admission_id for item in state.acquisitions[0].assignments}) == 2
            assert len(state.requests) == 2
            assert all(item.state is RequestState.SUCCEEDED and item.attempts == 1 for item in state.requests)
            assert len({group for item in state.requests for group in item.group_ids}) == 2
            assert len(state.ready_groups) == 2
            for group in state.ready_groups:
                assert group.main_result is not None
                assert len(group.products) == 2
                assert {Path(name).suffix for name in group.products} == {".srt", ".eac3"}
                assert (workspace / group.main_result).is_file()
                assert all((workspace / name).is_file() for name in (*group.sources, *group.products))
                assert all(name.startswith("ready/") for name in (*group.sources, *group.products))
            assert not data.parent.exists()
            assert receiver.released_hashes(frozenset({info_hash})) == frozenset({info_hash})
            states = client.call("episode_states", {"anilist_id": 500, "numbers": [1, 2, 3]})
            assert [item["state"] for item in cast("list[dict[str, object]]", states["items"])] == [
                "ready",
                "not_ordered",
                "ready",
            ]
            wait_for(
                lambda: len(cast("list[object]", client.call("status")["library"])) == 2,
                "two library results",
            )
            status = client.call("status")
            assert len(cast("list[object]", status["library"])) == 2
            assert WatchStateStore(tmp_path / "watch/state.json").load().acquisitions == state.acquisitions
        adds: list[httpx.Request] = [item for item in receiver_requests if item.url.path.endswith("/torrents/add")]
        assert len(adds) == 1
        magnet: str = parse_qs(adds[0].content.decode())["urls"][0]
        assert urlsplit(magnet).scheme == "magnet"
        assert parse_qs(urlsplit(magnet).query) == {"xt": [f"urn:btih:{info_hash}"]}
        assert catalog.asked == [1, 3]
        assert [1, 1, 0, 0, 1, 1] in priorities
        assert all(
            f"E{number}:{phase}" in times
            for number in (1, 3)
            for phase in ("D", "admitted", "metadata", "started", "complete", "handoff", "ready")
        )
        print(  # noqa: T201
            json.dumps(
                {
                    "q05_seconds_from_first_D": times,
                    "peer_attempts": peer_attempts,
                    "version": version,
                    "metadata_adds": len(adds),
                    "ipc_status_bytes": len(json.dumps(status).encode()),
                }
            )
        )
