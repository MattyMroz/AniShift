from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Final, cast

import httpx
import pytest
from conftest import hidden_window_options

from anishift.platform import qbittorrent_process as processes
from anishift.platform.binaries import Binary, bundled_binary_path, external_bin_root
from anishift.platform.qbittorrent_process import ManagedQBittorrent
from anishift.services.torrents import TorrentInfo
from anishift.services.torrents.errors import TorrentClientError

_TIMEOUT_S: Final[float] = 30.0
_START_ATTEMPT: Final[str] = "A closed taken-over client was started again"


def _encode(value: object) -> bytes:
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(_encode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(_encode(key) + _encode(value[key]) for key in sorted(value)) + b"e"
    raise TypeError(type(value).__name__)


def _receipt(
    root: Path, executable: Path, hashes: tuple[str, ...] = ("a" * 40,), released: tuple[str, ...] = ()
) -> None:
    root.mkdir(parents=True)
    document: dict[str, object] = {
        "pid": 123,
        "created": 456,
        "port": 18081,
        "executable": str(executable),
        "hashes": list(hashes),
        "active": True,
        "taken_over": False,
        "released": list(released),
    }
    (root / "process.json").write_text(json.dumps(document), encoding="utf-8")


class _PortSocket:
    def __init__(self, refused: int, opened: list[_PortSocket], family: int, kind: int) -> None:
        del family
        self.refused: int = refused
        self.kind: int = kind
        self.port: int = 0
        self.closed: bool = False
        opened.append(self)

    def __enter__(self) -> _PortSocket:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def bind(self, address: tuple[str, int]) -> None:
        assert address[0] == "0.0.0.0"  # noqa: S104
        if self.kind == socket.SOCK_DGRAM and address[1] == self.refused:
            raise OSError(address[1])
        self.port = address[1]


def _fake_ports(monkeypatch: pytest.MonkeyPatch, draws: list[int], refused: int) -> list[_PortSocket]:
    opened: list[_PortSocket] = []

    def make(family: int, kind: int) -> _PortSocket:
        return _PortSocket(refused, opened, family, kind)

    monkeypatch.setattr(
        processes,
        "socket",
        SimpleNamespace(
            socket=make, AF_INET=socket.AF_INET, SOCK_DGRAM=socket.SOCK_DGRAM, SOCK_STREAM=socket.SOCK_STREAM
        ),
    )
    monkeypatch.setattr(processes, "secrets", SimpleNamespace(randbelow=lambda count: draws.pop(0)))
    return opened


def test_peer_port_skips_a_port_udp_refuses_and_holds_both_sockets_until_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[_PortSocket] = _fake_ports(monkeypatch, [51277 - 49152, 51400 - 49152], 51277)
    with processes._peer_port() as port:
        assert port == 51400
        assert [(item.kind, item.port, item.closed) for item in opened] == [
            (socket.SOCK_DGRAM, 0, True),
            (socket.SOCK_STREAM, 0, True),
            (socket.SOCK_DGRAM, 51400, False),
            (socket.SOCK_STREAM, 51400, False),
        ]
    assert all(item.closed for item in opened)


def test_peer_port_refuses_after_bounded_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[_PortSocket] = _fake_ports(monkeypatch, [51277 - 49152] * processes._PEER_PORT_ATTEMPTS, 51277)
    with pytest.raises(TorrentClientError, match="both TCP and UDP"), processes._peer_port():
        pytest.fail("A refused port was reserved")
    assert len(opened) == processes._PEER_PORT_ATTEMPTS * 2
    assert all(item.closed for item in opened)


def test_peer_port_is_unavailable_to_tcp_and_udp_while_held() -> None:
    refused: list[int] = []
    with processes._peer_port() as port:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as probe:
                try:
                    probe.bind(("0.0.0.0", port))  # noqa: S104
                except OSError:
                    refused.append(kind)
    assert refused == [socket.SOCK_STREAM, socket.SOCK_DGRAM]
    for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
        with socket.socket(socket.AF_INET, kind) as probe:
            probe.bind(("0.0.0.0", port))  # noqa: S104


def test_start_timeout_is_bounded_and_restart_waits_for_explicit_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    children: list[_TimedOutChild] = []

    class _TimedOutChild:
        pid: int = 456

        def __init__(self) -> None:
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 1

        def wait(self, timeout: float) -> int:
            del timeout
            assert self.returncode is not None
            return self.returncode

    def launch(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        del args, kwargs
        child: _TimedOutChild = _TimedOutChild()
        children.append(child)
        return cast("subprocess.Popen[bytes]", child)

    monkeypatch.setattr(processes, "is_windows", lambda: True)
    monkeypatch.setattr(processes, "_START_TIMEOUT_S", 0.0)
    monkeypatch.setattr(processes, "_protect_profile", lambda root: None)
    monkeypatch.setattr(processes, "ensure_authkey", lambda root: b"test-only-key")
    monkeypatch.setattr(processes, "ensure_resource", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "write_managed_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (123, "unused.exe"))
    monkeypatch.setattr(subprocess, "Popen", launch)

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(tmp_path / "profile", http=http)
        try:
            with (
                pytest.raises(TorrentClientError, match="did not become ready"),
                manager.download_scope(frozenset({"a"})),
            ):
                pytest.fail("Unready client accepted a download")
            assert len(children) == processes._START_ATTEMPTS
            assert all(child.returncode == 1 for child in children)
            manager.close()
            manager = ManagedQBittorrent(tmp_path / "profile", http=http)
            with pytest.raises(TorrentClientError, match="explicitly resume"):
                manager.torrents("AniShift")
            assert len(children) == processes._START_ATTEMPTS
            with pytest.raises(TorrentClientError, match="did not become ready"):
                manager.transfer_action("a", "resume")
            assert len(children) == processes._START_ATTEMPTS * 2
        finally:
            manager.close()


@pytest.mark.parametrize("reason", ["pid_reused", "foreign_torrent"])
def test_uncertain_or_taken_over_process_is_never_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    monkeypatch.setattr(
        processes, "_process_identity", lambda pid: (789 if reason == "pid_reused" else 456, str(executable))
    )
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: reason == "visible_window")
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        if request.url.path.endswith("/info"):
            return httpx.Response(200, json=[{"hash": "b" * 40, "progress": 1, "amount_left": 0, "state": "stoppedUP"}])
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.finish_transfers()
            assert not any(path.endswith(("/shutdown", "/stop", "/delete", "/setPreferences")) for path in requests)
        finally:
            manager.close()


@pytest.mark.parametrize("ownership", ["owned", "taken_over", "pid_reused", "closed"])
def test_finalizable_hashes_requires_a_matching_managed_process_or_release_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ownership: str
) -> None:
    executable: Path = bundled_binary_path(Binary.QBITTORRENT, root=tmp_path / "bin")
    monkeypatch.setattr(
        processes,
        "_process_identity",
        lambda pid: None if ownership == "closed" else (789 if ownership == "pid_reused" else 456, str(executable)),
    )
    with httpx.Client() as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(tmp_path / "profile", http=http, bin_root=tmp_path / "bin")
        manager._state = processes._ProcessState(
            pid=123,
            created=456,
            executable=str(executable),
            hashes=frozenset({"a", "b"}),
            taken_over=ownership == "taken_over",
            released=frozenset({"b"}),
        )
        assert manager.finalizable_hashes(frozenset({"a", "b", "foreign"})) == (
            frozenset({"a", "b"}) if ownership == "owned" else frozenset({"b"})
        )


def test_released_hashes_and_a_concurrent_receipt_save_never_block_each_other(tmp_path: Path) -> None:
    root: Path = tmp_path / "profile"
    root.mkdir()
    failures: list[str] = []
    stop: threading.Event = threading.Event()
    with httpx.Client() as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        manager._save(processes._ProcessState(released=frozenset({"a"})))

        def save_repeatedly() -> None:
            port: int = 0
            while not stop.is_set():
                port += 1
                try:
                    with manager._lock:
                        manager._save(processes._ProcessState(port=port, released=frozenset({"a"})))
                except PermissionError:
                    failures.append("save")

        writer: threading.Thread = threading.Thread(target=save_repeatedly)
        writer.start()
        try:
            deadline: float = time.monotonic() + 1.0
            while time.monotonic() < deadline and not failures:
                try:
                    assert manager.released_hashes(frozenset({"a", "b"})) == {"a"}
                except PermissionError:
                    failures.append("read")
        finally:
            stop.set()
            writer.join(_TIMEOUT_S)
    assert failures == []


def test_process_exit_can_outlast_startup_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    elapsed: list[float] = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(time, "sleep", lambda delay: elapsed.__setitem__(0, elapsed[0] + delay))
    monkeypatch.setattr(ManagedQBittorrent, "_matches_process", lambda self, state: elapsed[0] < 30.0)
    with httpx.Client() as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(tmp_path / "profile", http=http)
        manager._wait_for_exit(processes._ProcessState())
    assert elapsed[0] == 30.0
    assert processes._START_TIMEOUT_S == 15.0


def test_an_open_own_window_keeps_ownership_and_blocks_only_the_automatic_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable, released=("a" * 40,))
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)))
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: True)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        if request.url.path.endswith("/info"):
            return httpx.Response(200, json=[{"hash": "a" * 40, "progress": 1, "amount_left": 0, "state": "stalledUP"}])
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.finish_transfers()
            assert len(manager.torrents("AniShift")) == 1
        finally:
            manager.close()

    receipt: dict[str, object] = json.loads((root / "process.json").read_text(encoding="utf-8"))
    assert receipt["taken_over"] is False
    assert receipt["active"] is True
    assert any(path.endswith("/stop") for path in requests)
    assert not any(path.endswith("/shutdown") for path in requests)


@pytest.mark.parametrize("released", [("a" * 40,), ("a" * 40, "b" * 40)])
def test_the_idle_close_waits_until_the_owner_released_every_transfer_the_client_still_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, released: tuple[str, ...]
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable, hashes=("a" * 40, "b" * 40), released=released)
    alive: list[bool] = [True]
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)) if alive[0] else None)
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: False)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        if request.url.path.endswith("/info"):
            return httpx.Response(200, json=[{"hash": "b" * 40, "progress": 1, "amount_left": 0, "state": "stoppedUP"}])
        if request.url.path.endswith("/shutdown"):
            alive[0] = False
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.finish_transfers()
        finally:
            manager.close()

    receipt: dict[str, object] = json.loads((root / "process.json").read_text(encoding="utf-8"))
    closed: bool = len(released) == 2
    assert any(path.endswith("/shutdown") for path in requests) is closed
    assert alive[0] is not closed
    assert (receipt["active"], receipt["pid"]) == ((False, 0) if closed else (True, 123))


def test_closed_manual_window_is_not_reported_as_a_start_failure_or_restarted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    _receipt(root, tmp_path / "bin/qbittorrent/qbittorrent.exe")
    path: Path = root / "process.json"
    receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**receipt, "taken_over": True, "start_failed": True}), encoding="utf-8")
    monkeypatch.setattr(processes, "_process_identity", lambda pid: None)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="window was closed"):
                manager.torrents("AniShift")
            assert requests == []
        finally:
            manager.close()


def test_unconfirmed_owned_transfers_restore_the_client_and_nothing_else_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    path: Path = root / "process.json"
    receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**receipt, "active": False}), encoding="utf-8")
    children: list[_LiveChild] = []

    class _LiveChild:
        pid: int = 999

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            raise AssertionError(self.pid)

        def wait(self, timeout: float) -> int:
            del timeout
            raise AssertionError(self.pid)

    def launch(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        del args, kwargs
        child: _LiveChild = _LiveChild()
        children.append(child)
        return cast("subprocess.Popen[bytes]", child)

    monkeypatch.setattr(processes, "is_windows", lambda: True)
    monkeypatch.setattr(processes, "_protect_profile", lambda root: None)
    monkeypatch.setattr(processes, "ensure_authkey", lambda root: b"test-only-key")
    monkeypatch.setattr(processes, "ensure_resource", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "write_managed_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: False)
    monkeypatch.setattr(
        processes, "_process_identity", lambda pid: (456, str(executable)) if pid == _LiveChild.pid else None
    )
    monkeypatch.setattr(subprocess, "Popen", launch)

    dead_port: int = cast("int", receipt["port"])

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.port == dead_port:
            raise httpx.ConnectError("the recorded endpoint is gone", request=request)
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.resume_unconfirmed(frozenset())
            manager.resume_unconfirmed(frozenset({"b" * 40}))
            assert children == []
            assert json.loads(path.read_text(encoding="utf-8"))["active"] is False
            manager.resume_unconfirmed(frozenset({"a" * 40}))
            assert len(children) == 1
            stored: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
            assert stored["active"] is True
            assert stored["pid"] == _LiveChild.pid
            manager.resume_unconfirmed(frozenset({"a" * 40}))
            assert len(children) == 1
        finally:
            manager.close()


def test_a_taken_over_client_is_never_restarted_for_unconfirmed_transfers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    _receipt(root, tmp_path / "bin/qbittorrent/qbittorrent.exe")
    path: Path = root / "process.json"
    receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**receipt, "active": False, "taken_over": True}), encoding="utf-8")
    monkeypatch.setattr(processes, "_process_identity", lambda pid: None)
    monkeypatch.setattr(processes, "_protect_profile", lambda root: None)

    def refuse(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        del args, kwargs
        raise AssertionError(_START_ATTEMPT)

    monkeypatch.setattr(subprocess, "Popen", refuse)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match="window was closed"):
                manager.resume_unconfirmed(frozenset({"a" * 40}))
            assert requests == []
        finally:
            manager.close()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="requires real Windows process ownership")
def test_private_clients_download_concurrently_reconnect_and_stop_independently(  # noqa: C901,PLR0915 - isolated lifecycle
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not (external_bin_root() / "qbittorrent/qbittorrent.exe").is_file():
        pytest.skip("verified bundled qBittorrent is not prepared")
    launch: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []
    occupied: socket.socket = socket.socket()

    def collide_once(command: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        if not any(argument.startswith("--webui-port=") for argument in command):
            return launch(command, **kwargs)
        if not children:
            port: int = int(
                next(argument.split("=", 1)[1] for argument in command if argument.startswith("--webui-port="))
            )
            occupied.bind(("127.0.0.1", port))
            occupied.listen()
            monkeypatch.setattr(processes, "_START_TIMEOUT_S", 1.0)
        else:
            occupied.close()
            monkeypatch.setattr(processes, "_START_TIMEOUT_S", 15.0)
        child: subprocess.Popen[bytes] = launch(command, **kwargs, **hidden_window_options())
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", collide_once)
    data: bytes = b"test data\n" * 200000
    entered: set[str] = set()
    lock: threading.Lock = threading.Lock()
    parallel: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    torrents: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            name: str = self.path.lstrip("/")
            if name in torrents:
                payload: bytes = torrents[name]
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if name == "blocked.bin":
                self.send_error(503)
                return
            with lock:
                entered.add(name)
                if {"one.bin", "two.bin"}.issubset(entered):
                    parallel.set()
            if not release.wait(_TIMEOUT_S):
                self.send_error(503)
                return
            start: int = 0
            end: int = len(data) - 1
            requested: str | None = self.headers.get("Range")
            if requested is not None:
                first, last = requested.removeprefix("bytes=").split("-", 1)
                start, end = int(first), int(last) if last else end
            payload = data[start : end + 1]
            self.send_response(206 if requested else 200)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(payload)

    server: ThreadingHTTPServer = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread: threading.Thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base: str = f"http://127.0.0.1:{server.server_port}/"
    hashes: dict[str, str] = {}
    for name in ("one.bin", "two.bin", "blocked.bin"):
        piece_size: int = 16384
        info: dict[bytes, object] = {
            b"length": len(data),
            b"name": name.encode(),
            b"piece length": piece_size,
            b"pieces": b"".join(
                hashlib.sha1(data[index : index + piece_size], usedforsecurity=False).digest()
                for index in range(0, len(data), piece_size)
            ),
            b"private": 1,
        }
        hashes[name] = hashlib.sha1(_encode(info), usedforsecurity=False).hexdigest()
        torrents[name + ".torrent"] = _encode({b"info": info, b"url-list": [base.encode()]})
    with httpx.Client() as http:
        for name in ("first", "second"):
            profile: Path = tmp_path / name / "qBittorrent/config/qBittorrent.ini"
            profile.parent.mkdir(parents=True)
            profile.write_text(
                "[BitTorrent]\n"
                "Session\\InterfaceAddress=127.0.0.1\n"
                "Session\\DHTEnabled=false\n"
                "Session\\LSDEnabled=false\n"
                "Session\\PeXEnabled=false\n"
                "[Preferences]\n"
                "Connection\\UPnP=false\n"
                "Advanced\\updateCheck=false\n",
                encoding="utf-8",
            )
        first: ManagedQBittorrent = ManagedQBittorrent(tmp_path / "first", http=http)
        second: ManagedQBittorrent = ManagedQBittorrent(tmp_path / "second", http=http)
        first_child = None
        second_child = None
        try:
            with second.download_scope(frozenset({"b" * 40})):
                second_child = second._child
                second_preferences: dict[str, object] = second.preferences()
                assert len(children) == 2
                assert children[0].poll() is not None
                assert second_preferences["current_interface_address"] == "127.0.0.1"
                assert second_preferences["upnp"] is False
            with first.download_scope(frozenset(hashes.values())):
                first_child = first._child
                first.set_preferences(
                    {"ssrf_mitigation": False, "dht": False, "pex": False, "lsd": False, "dl_limit": 0, "up_limit": 0}
                )
                assert first.preferences()["queueing_enabled"] is False
                for name in hashes:
                    first.add_torrent(base + name + ".torrent", save_path=tmp_path / "downloads", category="AniShift")
            assert parallel.wait(_TIMEOUT_S), entered
            release.set()
            deadline: float = time.monotonic() + _TIMEOUT_S
            entries: tuple[TorrentInfo, ...] = ()
            while time.monotonic() < deadline:
                entries = first.torrents("AniShift")
                if sum(item.progress == 1.0 for item in entries) == 2 and all(
                    (tmp_path / "downloads" / name).is_file() for name in ("one.bin", "two.bin")
                ):
                    break
                time.sleep(0.1)
            assert sum(item.progress == 1.0 for item in entries) == 2, entries
            assert (tmp_path / "downloads/one.bin").read_bytes() == data
            assert (tmp_path / "downloads/two.bin").read_bytes() == data
            first.finish_transfers()
            assert first.version() == second.version()
            assert second.torrents("AniShift") == ()
            first.close()
            first = ManagedQBittorrent(tmp_path / "first", http=http)
            assert len(first.torrents("AniShift")) == 3
            first.transfer_action(hashes["blocked.bin"], "cancel")
            deadline = time.monotonic() + _TIMEOUT_S
            while len(first.torrents("AniShift")) > 2 and time.monotonic() < deadline:
                time.sleep(0.1)
            completed_hashes: frozenset[str] = frozenset({hashes["one.bin"], hashes["two.bin"]})
            assert first.release_completed(completed_hashes) == completed_hashes
            assert (tmp_path / "downloads/one.bin").read_bytes() == data
            assert (tmp_path / "downloads/two.bin").read_bytes() == data
            first.finish_transfers()
            assert first_child is not None
            assert first_child.poll() == 0
            assert first.release_completed(completed_hashes) == completed_hashes
            assert second.preferences()["save_path"] == second_preferences["save_path"]
            assert second_child is not None
            assert second_child.poll() is None
            second.finish_transfers()
        finally:
            occupied.close()
            release.set()
            first.close()
            second.close()
            for child in children:
                if child is not None and child.poll() is None:
                    child.terminate()
                    child.wait(timeout=_TIMEOUT_S)
            server.shutdown()
            server.server_close()
            server_thread.join(_TIMEOUT_S)


def test_prepare_reconnects_a_running_own_client_without_starting_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)))
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: False)
    monkeypatch.setattr(processes, "is_windows", lambda: False)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.prepare()
        finally:
            manager.close()

    assert requests != []


def test_prepare_starts_nothing_for_a_client_a_person_took_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    path: Path = root / "process.json"
    receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**receipt, "taken_over": True}), encoding="utf-8")
    monkeypatch.setattr(processes, "_process_identity", lambda pid: None)
    monkeypatch.setattr(processes, "is_windows", lambda: False)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.prepare()
        finally:
            manager.close()

    assert requests == []


def test_prepare_starts_the_client_on_a_clean_install_without_ordering_a_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    children: list[_LiveChild] = []

    class _LiveChild:
        pid: int = 999

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            raise AssertionError(self.pid)

        def wait(self, timeout: float) -> int:
            del timeout
            raise AssertionError(self.pid)

    def launch(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        del args, kwargs
        child: _LiveChild = _LiveChild()
        children.append(child)
        return cast("subprocess.Popen[bytes]", child)

    root: Path = tmp_path / "profile"
    executable: Path = bundled_binary_path(Binary.QBITTORRENT, root=tmp_path / "bin")
    monkeypatch.setattr(processes, "is_windows", lambda: True)
    monkeypatch.setattr(processes, "_protect_profile", lambda root: None)
    monkeypatch.setattr(processes, "ensure_authkey", lambda root: b"test-only-key")
    monkeypatch.setattr(processes, "ensure_resource", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "write_managed_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: False)
    monkeypatch.setattr(
        processes, "_process_identity", lambda pid: (456, str(executable)) if pid == _LiveChild.pid else None
    )
    monkeypatch.setattr(subprocess, "Popen", launch)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            manager.prepare()
            manager.prepare()
        finally:
            manager.close()

    receipt: dict[str, object] = json.loads((root / "process.json").read_text(encoding="utf-8"))
    assert len(children) == 1
    assert receipt["pid"] == _LiveChild.pid
    assert receipt["hashes"] == []
    assert not any("/add" in path for path in requests)


@pytest.mark.parametrize("visible", [False, True])
def test_close_owned_shuts_down_a_proven_client_and_clears_its_recorded_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, visible: bool
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    alive: list[bool] = [True]
    monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)) if alive[0] else None)
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: visible)
    monkeypatch.setattr(processes, "is_windows", lambda: False)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/shutdown"):
            alive[0] = False
            return httpx.Response(200, text="Ok.")
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        manager.close_owned()

    receipt: dict[str, object] = json.loads((root / "process.json").read_text(encoding="utf-8"))
    assert any(path.endswith("/shutdown") for path in requests)
    assert receipt["pid"] == 0
    assert receipt["created"] == 0
    assert receipt["hashes"] == ["a" * 40]
    assert receipt["active"] is True


@pytest.mark.parametrize("reason", ["not_ours", "taken_over"])
def test_close_owned_never_shuts_down_a_client_this_process_does_not_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    if reason == "taken_over":
        path: Path = root / "process.json"
        receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**receipt, "taken_over": True}), encoding="utf-8")
        monkeypatch.setattr(processes, "_process_identity", lambda pid: (456, str(executable)))
    else:
        monkeypatch.setattr(processes, "_process_identity", lambda pid: None)
    monkeypatch.setattr(processes, "is_windows", lambda: False)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        manager.close_owned()

    assert requests == []


@pytest.mark.parametrize(
    ("cause", "refusal"),
    [
        ("live_window", "automatic control is disabled"),
        ("closed_window", "window was closed"),
    ],
)
def test_a_resume_never_reclaims_a_client_that_was_taken_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cause: str, refusal: str
) -> None:
    root: Path = tmp_path / "profile"
    executable: Path = tmp_path / "bin/qbittorrent/qbittorrent.exe"
    _receipt(root, executable)
    path: Path = root / "process.json"
    receipt: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**receipt, "taken_over": True}), encoding="utf-8")
    monkeypatch.setattr(
        processes, "_process_identity", lambda pid: (456, str(executable)) if cause == "live_window" else None
    )
    monkeypatch.setattr(processes, "_visible_process_window", lambda pid: False)
    monkeypatch.setattr(processes, "_protect_profile", lambda root: None)
    monkeypatch.setattr(processes, "is_windows", lambda: True)

    def refuse(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        del args, kwargs
        raise AssertionError(_START_ATTEMPT)

    monkeypatch.setattr(subprocess, "Popen", refuse)
    requests: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("preferences"):
            return httpx.Response(200, json={"save_path": str(root / "qBittorrent/downloads")})
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http, bin_root=tmp_path / "bin")
        try:
            with pytest.raises(TorrentClientError, match=refusal):
                manager.transfer_action("a" * 40, "resume")
        finally:
            manager.close()

    stored: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    assert stored["taken_over"] is True
    assert requests == []
