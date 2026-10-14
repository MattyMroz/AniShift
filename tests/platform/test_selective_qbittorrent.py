from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from test_qbittorrent_process import _receipt

from anishift.platform import qbittorrent_process as processes
from anishift.platform.qbittorrent_process import ManagedQBittorrent
from anishift.services.torrents import TorrentFile
from anishift.services.torrents.errors import TorrentClientError

pytestmark = pytest.mark.unit


class _Api:
    def __init__(self, root: Path) -> None:
        self.root: Path = root
        self.files: tuple[TorrentFile, ...] = (
            TorrentFile(0, "Pack/E01.mkv", 100, 0.0, 1),
            TorrentFile(3, "Pack/E02.mkv", 100, 0.0, 1),
            TorrentFile(8, "Pack/E03.mkv", 100, 0.0, 1),
        )
        self.state: str = "stoppedDL"
        self.hash: str = "a" * 40
        self.present: bool = True
        self.ignore_priority: int | None = None
        self.wrong_path: bool = False
        self.wrong_profile: bool = False
        self.start_on_selection: bool = False
        self.mutations: list[tuple[str, dict[str, list[str]]]] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        route: str = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            form: dict[str, list[str]] = parse_qs(request.content.decode())
            self.mutations.append((route, form))
            if route == "filePrio":
                indexes: set[int] = {int(value) for value in form["id"][0].split("|")}
                priority: int = int(form["priority"][0])
                if priority == 1 and self.start_on_selection:
                    self.state = "downloading"
                if priority != self.ignore_priority:
                    self.files = tuple(
                        replace(item, priority=priority) if item.index in indexes else item for item in self.files
                    )
            return httpx.Response(200, text="Ok.")
        if route == "preferences":
            return httpx.Response(
                200, json={"save_path": str(self.root / ("foreign" if self.wrong_profile else "qBittorrent/downloads"))}
            )
        if route == "info":
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": self.hash,
                        "state": self.state,
                        "save_path": str(self.root / ("foreign" if self.wrong_path else "data")),
                    }
                ]
                if self.present
                else [],
            )
        if route == "files":
            return httpx.Response(200, json=[asdict(item) for item in self.files])
        return httpx.Response(200, text="v5.2.3")


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Api:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)))
    return _Api(root)


def test_stopped_selection_verifies_zero_then_union_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    expected: tuple[TorrentFile, ...] = api.files
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            for selected in (frozenset({0}), frozenset({0, 8}), frozenset({0, 8})):
                result: tuple[TorrentFile, ...] = manager.select_files(
                    api.hash, expected, selected, save_path=api.root / "data"
                )
                assert {item.index for item in result if item.priority == 1} == selected
        finally:
            manager.close()
    assert [form["priority"] for route, form in api.mutations] == [["0"], ["1"]] * 3
    assert all(route == "filePrio" for route, _form in api.mutations)
    assert api.mutations[-1][1]["id"] == ["0|8"]


@pytest.mark.parametrize(
    "reason",
    [
        "unowned",
        "profile",
        "path",
        "map",
        "index",
        "zero_readback",
        "selected_readback",
        "checkingResumeData",
        "downloading",
    ],
)
def test_negative_selection_never_starts_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    files: tuple[TorrentFile, ...] = api.files
    selected: frozenset[int] = frozenset({0, 8})
    info_hash: str = "b" * 40 if reason == "unowned" else api.hash
    if reason == "unowned":
        api.hash = info_hash
    api.wrong_profile = reason == "profile"
    api.wrong_path = reason == "path"
    if reason == "map":
        files = (replace(files[0], size=101), *files[1:])
    if reason == "index":
        selected = frozenset({1})
    if reason in {"zero_readback", "selected_readback"}:
        api.ignore_priority = 0 if reason == "zero_readback" else 1
    if reason in {"checkingResumeData", "downloading"}:
        api.state = reason
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError):
                manager.select_files(info_hash, files, selected, save_path=api.root / "data")
        finally:
            manager.close()
    assert all(route not in {"start", "add", "delete"} for route, _form in api.mutations)
    if reason in {"unowned", "profile", "path", "map", "index"}:
        assert api.mutations == []
    if reason in {"checkingResumeData", "downloading"}:
        assert [route for route, _form in api.mutations] == ["stop"]


@pytest.mark.parametrize("reason", ["unowned", "existing", "profile"])
def test_metadata_admission_refuses_foreign_or_existing_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.wrong_profile = reason == "profile"
    info_hash: str = "b" * 40 if reason == "unowned" else api.hash
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError):
                manager.add_metadata(info_hash, save_path=api.root / "data", category="AniShift")
        finally:
            manager.close()
    assert api.mutations == []


def test_download_scope_does_not_claim_an_existing_foreign_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.hash = "b" * 40
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError), manager.download_scope(frozenset({api.hash})):
                pytest.fail("A foreign torrent was claimed")
        finally:
            manager.close()
    assert api.hash not in json.loads((api.root / "process.json").read_text())["hashes"]
    assert api.mutations == []


def test_metadata_add_requires_persisted_hash_and_uses_only_metadata_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.present = False
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.add_metadata(api.hash, save_path=api.root / "data", category="AniShift")
        finally:
            manager.close()
    assert len(api.mutations) == 1
    assert api.mutations[0][0] == "add"
    assert api.mutations[0][1]["stopCondition"] == ["MetadataReceived"]


@pytest.mark.parametrize("expected_map", ["empty", "stale"])
def test_premature_selection_does_not_stop_metadata_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expected_map: str
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    files: tuple[TorrentFile, ...] = api.files if expected_map == "stale" else ()
    api.files = ()
    api.state = "metaDL"
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="file map changed"):
                manager.select_files(api.hash, files, frozenset(), save_path=api.root / "data")
        finally:
            manager.close()
    assert api.mutations == []


def test_rename_refuses_a_hash_outside_the_persisted_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.hash = "b" * 40
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="not managed"):
                manager.rename_file(api.hash, "Pack/E01.mkv", "E01.mkv")
        finally:
            manager.close()
    assert api.mutations == []


def test_download_scope_accepts_a_present_hash_already_owned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with manager.download_scope(frozenset({api.hash})):
                assert json.loads((api.root / "process.json").read_text())["hashes"] == [api.hash]
        finally:
            manager.close()
    assert api.mutations == []


def test_selection_refuses_a_client_that_starts_before_final_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.start_on_selection = True
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="confirmed stopped"):
                manager.select_files(api.hash, api.files, frozenset({0}), save_path=api.root / "data")
        finally:
            manager.close()
    assert [route for route, _form in api.mutations] == ["filePrio", "filePrio", "stop"]


def test_unconfirmed_zero_priorities_block_selection_even_when_final_scope_would_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api: _Api = _setup(tmp_path, monkeypatch)
    api.ignore_priority = 0
    with httpx.Client(transport=httpx.MockTransport(api.respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(api.root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="omitted file priorities"):
                manager.select_files(api.hash, api.files, frozenset({0, 3, 8}), save_path=api.root / "data")
        finally:
            manager.close()
    assert [(route, form["priority"]) for route, form in api.mutations] == [("filePrio", ["0"])]
