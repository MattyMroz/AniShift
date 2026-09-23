"""Private qBittorrent installation, process ownership and transfer lifecycle."""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

import httpx
from pydantic import TypeAdapter, ValidationError

from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.paths import torrent_download_dir
from anishift.platform.binaries import Binary, bundled_binary_path, external_bin_root, is_windows
from anishift.platform.child_processes import independent_child_flags
from anishift.platform.local_control import ensure_authkey
from anishift.platform.process_lock import ProcessLock
from anishift.platform.qbittorrent_config import write_managed_profile
from anishift.services.torrents import QBittorrentClient, TorrentFile, TorrentInfo
from anishift.services.torrents.errors import TorrentClientError
from anishift.setup.installer import ensure_resource
from anishift.utils.logger import get_logger

__all__ = ["ManagedQBittorrent"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_START_ATTEMPTS: Final[int] = 3
"""Bounded process starts when a port is lost between selection and binding."""

_START_TIMEOUT_S: Final[float] = 15.0
"""Readiness deadline for one private process launch."""

_POLL_S: Final[float] = 0.25
"""Delay between readiness checks during process startup and shutdown."""

_MANAGED_PREFERENCES: Final[dict[str, object]] = {
    "queueing_enabled": False,
    "incomplete_files_ext": True,
    "max_ratio_enabled": True,
    "max_ratio": 0,
    "max_ratio_act": 0,
    "max_seeding_time_enabled": True,
    "max_seeding_time": 0,
}
"""Private client policy allowing parallel downloads and stopping completed seeds."""

_QUERY_PROCESS: Final[int] = 0x1000
"""Windows access needed to verify process creation time and executable identity."""

_MAX_IMAGE_PATH: Final[int] = 32768
"""Buffer accommodating a Windows executable path during ownership verification."""


@dataclass(frozen=True, slots=True)
class _ProcessState:
    pid: int = 0
    created: int = 0
    port: int = 0
    executable: str = ""
    hashes: frozenset[str] = frozenset()
    active: bool = False
    taken_over: bool = False
    start_failed: bool = False
    released: frozenset[str] = frozenset()


_STATE: Final[TypeAdapter[_ProcessState]] = TypeAdapter(_ProcessState)
"""Validated process receipt, excluding credentials and torrent payloads."""


class ManagedQBittorrent:
    """Own a private client lazily while keeping the user's client untouched."""

    def __init__(
        self, root: Path, *, http: httpx.Client, bin_root: Path | None = None, previous: QBittorrentClient | None = None
    ) -> None:
        self._root: Path = root.resolve()
        self._bin_root: Path = (bin_root or external_bin_root()).resolve()
        self._http: httpx.Client = http
        self._lock: threading.RLock = threading.RLock()
        self._process_lock: ProcessLock = ProcessLock(self._root / "manager.lock")
        self._state: _ProcessState | None = None
        self._client: QBittorrentClient | None = None
        self._child: subprocess.Popen[bytes] | None = None
        self._previous: QBittorrentClient | None = previous

    @contextmanager
    def download_scope(self, hashes: frozenset[str]) -> Iterator[None]:
        """Persist ownership of the ordered hashes before sending any download."""
        with self._lock:
            state: _ProcessState = self._load()
            self._save(
                replace(
                    state,
                    hashes=state.hashes | hashes,
                    active=True,
                    start_failed=False,
                    released=state.released - hashes,
                )
            )
            self._ensure()
            yield

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        """Restore the private process for owned transfers that were ordered but never confirmed."""
        with self._lock:
            state: _ProcessState = self._load()
            if self._matches_process(state) or not state.hashes & hashes:
                return
            if not state.active:
                self._save(replace(state, active=True))
            self._ensure()

    def prepare(self) -> None:
        """Reconnect or start the private client whenever AniShift runs, without ordering any transfer."""
        with self._lock:
            state: _ProcessState = self._load()
            if state.taken_over:
                return
            if not self._matches_process(state):
                self._save(replace(state, active=True, start_failed=False))
            self._ensure()

    def version(self) -> str:
        """Read an existing client without installing one for a status check."""
        with self._lock:
            return self._required_client().version()

    def preferences(self) -> dict[str, object]:
        """Read preferences of an existing private client."""
        with self._lock:
            return self._required_client().preferences()

    def set_preferences(self, values: Mapping[str, object]) -> None:
        """Update preferences only while process ownership is still confirmed."""
        with self._lock:
            client: QBittorrentClient = self._required_client()
            self._assert_ownership(client)
            client.set_preferences(values)

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str, stopped: bool = False) -> None:
        """Submit an already recorded order to the private client."""
        with self._lock:
            client: QBittorrentClient = self._ensure()
            self._assert_ownership(client)
            client.add_torrent(torrent_url, save_path=save_path, category=category, stopped=stopped)

    def rename_file(self, info_hash: str, old_path: str, new_path: str) -> None:
        """Reserve one destination name in a private transfer that owns the file."""
        with self._lock:
            client: QBittorrentClient = self._required_client()
            self._assert_ownership(client)
            client.rename_file(info_hash, old_path, new_path)

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        """Read managed transfers, restoring a previously active private process if needed."""
        with self._lock:
            state: _ProcessState = self._load()
            own: tuple[TorrentInfo, ...] = (
                self._required_client().torrents(category) if state.active or self._matches_process(state) else ()
            )
            prior: tuple[TorrentInfo, ...] = self._previous_transfers(category)
            return (*own, *(item for item in prior if item.info_hash.casefold() not in state.hashes))

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Read file proofs from the client holding a known transfer."""
        with self._lock:
            if info_hash not in self._load().hashes and self._previous is not None:
                return self._previous.files(info_hash)
            return self._required_client().files(info_hash)

    def _previous_transfers(self, category: str) -> tuple[TorrentInfo, ...]:
        if self._previous is None:
            return ()
        try:
            return self._previous.torrents(category)
        except TorrentClientError:
            return ()

    def resume(self, info_hash: str) -> None:
        """Let a private transfer whose names are reserved write its content."""
        self.transfer_action(info_hash, "resume")

    def transfer_action(self, info_hash: str, action: str) -> None:
        """Stop or resume a known private transfer without deleting data."""
        with self._lock:
            state: _ProcessState = self._load()
            if info_hash not in state.hashes or action not in {"stop", "resume", "cancel"}:
                message: str = "The transfer or action is not managed by AniShift"
                raise _unavailable(message)
            if action == "resume":
                self._save(replace(state, start_failed=False, active=True))
            client: QBittorrentClient = self._ensure()
            self._assert_ownership(client)
            if action == "resume":
                self._save(replace(self._load(), active=True))
                client.resume(info_hash)
            elif action == "cancel":
                client.remove(info_hash)
            else:
                client.stop(info_hash)

    def finish_transfers(self) -> None:
        """Stop completed seeds and close only an idle client with proven ownership."""
        with self._lock:
            state: _ProcessState = self._load()
            if not self._matches_process(state) or state.taken_over:
                return
            client: QBittorrentClient = self._ensure()
            self._assert_ownership(client)
            entries: tuple[TorrentInfo, ...] = client.all_torrents()
            if any(item.info_hash.casefold() not in state.hashes for item in entries):
                self._save(replace(state, taken_over=True))
                logger.warning("Private torrent client contains unowned work; automatic management stopped")
                return
            for item in entries:
                if (
                    item.progress == 1.0
                    and item.amount_left == 0
                    and item.state in {"uploading", "stalledUP", "forcedUP"}
                ):
                    client.stop(item.info_hash)
            if any(item.progress < 1.0 or item.amount_left != 0 for item in entries):
                return
            if _visible_process_window(state.pid):
                logger.info("Kept the private torrent client running while its own window is open")
                return
            self._assert_ownership(client)
            client.shutdown()
            self._wait_for_exit(state)
            self._save(replace(state, active=False, pid=0, created=0))
            self._client = None
            logger.info("Idle private torrent client stopped")

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        """Forget confirmed complete private jobs while preserving their media for relocation."""
        with self._lock:
            state: _ProcessState = self._load()
            released: frozenset[str] = state.released & hashes
            if not hashes - released or not self._matches_process(state) or state.taken_over:
                return released
            client: QBittorrentClient = self._required_client()
            self._assert_ownership(client)
            entries: dict[str, TorrentInfo] = {item.info_hash.casefold(): item for item in client.all_torrents()}
            for info_hash in hashes - released:
                if info_hash not in state.hashes:
                    continue
                entry: TorrentInfo | None = entries.get(info_hash)
                if entry is not None and (
                    entry.progress != 1.0
                    or entry.amount_left != 0
                    or entry.state not in {"uploading", "stalledUP", "queuedUP", "pausedUP", "stoppedUP", "forcedUP"}
                ):
                    continue
                self._assert_ownership(client)
                if entry is not None:
                    client.remove(info_hash)
                released |= {info_hash}
            self._save(replace(self._load(), released=state.released | released))
            return released

    def released_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        """Read only the existing process receipt, without locks, profile setup or client access."""
        try:
            payload: bytes = (self._root / "process.json").read_bytes()
        except FileNotFoundError:
            return frozenset()
        return _STATE.validate_json(payload, strict=True).released & hashes

    def close_owned(self) -> None:
        """Shut the proven private client down on an explicit end, never touching a foreign one."""
        with self._lock:
            state: _ProcessState = self._load()
            if state.taken_over or not self._matches_process(state):
                self._process_lock.release()
                self._client = None
                return
            client: QBittorrentClient = self._required_client()
            self._assert_ownership(client)
            client.shutdown()
            self._wait_for_exit(state)
            self._save(replace(self._load(), pid=0, created=0))
            self._process_lock.release()
            self._client = None
            logger.info("Private torrent client closed on request")

    def close(self) -> None:
        """Release management while leaving active downloads available for recovery."""
        with self._lock:
            self._process_lock.release()
            self._client = None

    def _load(self) -> _ProcessState:
        if self._state is not None:
            return self._state
        if not self._process_lock.acquire():
            message: str = "Another process manages the private torrent profile"
            raise _unavailable(message)
        _protect_profile(self._root)
        path: Path = self._root / "process.json"
        try:
            self._state = _STATE.validate_json(path.read_bytes(), strict=True) if path.exists() else _ProcessState()
        except (OSError, ValidationError) as error:
            message = "Private torrent process state needs repair"
            raise _unavailable(message) from error
        return self._state

    def _save(self, state: _ProcessState) -> None:
        temporary: Path = self._root / "process.tmp"
        with temporary.open("wb") as handle:
            handle.write(_STATE.dump_json(state))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self._root / "process.json")
        self._state = state

    def _required_client(self) -> QBittorrentClient:
        state: _ProcessState = self._load()
        if self._matches_process(state):
            client: QBittorrentClient = self._client or self._make_client(state.port)
            self._assert_profile(client)
            self._client = client
            return client
        if not state.active and not self._matches_process(state):
            message: str = "The private torrent client starts when a download is ordered"
            raise _unavailable(message)
        return self._ensure()

    def _ensure(self) -> QBittorrentClient:
        state: _ProcessState = self._load()
        if state.taken_over:
            message: str = (
                "The private torrent client was taken over; automatic control is disabled"
                if self._matches_process(state)
                else "The private torrent window was closed; downloads remain stopped until explicitly resumed"
            )
            raise _unavailable(message)
        if state.start_failed:
            message = "The private torrent client could not start; resolve the problem and explicitly resume"
            raise _unavailable(message)
        try:
            return self._connect_or_start()
        except AniShiftError, OSError, subprocess.SubprocessError:
            if not self._load().taken_over:
                self._save(replace(self._load(), start_failed=True))
            raise

    def _connect_or_start(self) -> QBittorrentClient:
        state: _ProcessState = self._load()
        if self._matches_process(state):
            client: QBittorrentClient = self._client or self._make_client(state.port)
            self._assert_ownership(client)
            self._client = client
            return client
        if not is_windows():
            message = "Managed torrent installation requires Windows"
            raise _unavailable(message)
        if state.port:
            try:
                self._make_client(state.port).version()
            except TorrentClientError:
                pass
            else:
                self._save(replace(state, taken_over=True))
                message = "An unowned process answers at the private endpoint; automatic start refused"
                raise _unavailable(message)
        ensure_resource("qbittorrent", dest_root=self._bin_root, show_progress=False)
        for _attempt in range(_START_ATTEMPTS):
            started: QBittorrentClient | None = self._start()
            if started is not None:
                self._client = started
                return started
        message = "The private torrent client did not become ready; retry the download"
        raise _unavailable(message)

    def _start(self) -> QBittorrentClient | None:
        state: _ProcessState = self._load()
        executable: Path = bundled_binary_path(Binary.QBITTORRENT, root=self._bin_root)
        with socket.socket() as web_socket, socket.socket() as torrent_socket:
            web_socket.bind(("127.0.0.1", 0))
            torrent_socket.bind(("0.0.0.0", 0))  # noqa: S104 - reserve the torrent peer port, separate from loopback Web UI
            port: int = web_socket.getsockname()[1]
            torrent_port: int = torrent_socket.getsockname()[1]
            write_managed_profile(self._root, web_port=port, torrent_port=torrent_port, password=self._password())
        child: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 - bundled executable and private profile argv
            [
                str(executable),
                f"--profile={self._root}",
                f"--webui-port={port}",
                "--no-splash",
                "--confirm-legal-notice",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | independent_child_flags(),
        )
        self._child = child
        identity: tuple[int, str] | None = _process_identity(child.pid)
        if identity is None:
            child.terminate()
            child.wait(timeout=_START_TIMEOUT_S)
            return None
        state = replace(state, pid=child.pid, created=identity[0], executable=str(executable), port=port)
        try:
            self._save(state)
        except OSError:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=_START_TIMEOUT_S)
            raise
        client: QBittorrentClient = self._make_client(port)
        deadline: float = time.monotonic() + _START_TIMEOUT_S
        while child.poll() is None and time.monotonic() < deadline:
            try:
                self._assert_ownership(client)
                client.set_preferences(_MANAGED_PREFERENCES)
            except TorrentClientError:
                time.sleep(_POLL_S)
            else:
                logger.info("Private torrent client started")
                return client
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=_START_TIMEOUT_S)
        self._save(replace(state, pid=0, created=0))
        logger.warning("Private torrent client start failed; retrying with new ports")
        return None

    def _make_client(self, port: int) -> QBittorrentClient:
        return QBittorrentClient(
            f"http://127.0.0.1:{port}",
            username="admin",
            password=self._password(),
            http=self._http,
            timeout_s=2.0,
        )

    def _password(self) -> str:
        return ensure_authkey(self._root).hex()

    def _matches_process(self, state: _ProcessState) -> bool:
        if state.pid <= 0:
            return False
        identity: tuple[int, str] | None = _process_identity(state.pid)
        return (
            identity is not None
            and identity[0] == state.created
            and Path(identity[1]).resolve() == Path(state.executable).resolve()
            and Path(state.executable).resolve() == bundled_binary_path(Binary.QBITTORRENT, root=self._bin_root)
        )

    def _assert_ownership(self, client: QBittorrentClient) -> None:
        state: _ProcessState = self._load()
        if not self._matches_process(state) or state.taken_over:
            message: str = "Private torrent process ownership could not be confirmed"
            raise _unavailable(message)
        self._assert_profile(client)

    def _assert_profile(self, client: QBittorrentClient) -> None:
        if not self._matches_process(self._load()):
            message: str = "Private torrent process ownership could not be confirmed"
            raise _unavailable(message)
        save_path: object = client.preferences().get("save_path")
        if not isinstance(save_path, str) or Path(save_path).resolve() != torrent_download_dir(self._root):
            message = "The torrent endpoint does not match the private profile"
            raise _unavailable(message)

    def _wait_for_exit(self, state: _ProcessState) -> None:
        deadline: float = time.monotonic() + _START_TIMEOUT_S
        while self._matches_process(state) and time.monotonic() < deadline:
            time.sleep(_POLL_S)
        if self._matches_process(state):
            message: str = "The private torrent client did not finish shutting down"
            raise _unavailable(message)
        if self._child is not None:
            self._child.wait(timeout=_START_TIMEOUT_S)
            self._child = None


def _unavailable(message: str) -> TorrentClientError:
    return TorrentClientError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            message=message,
            suggestion="Open AniShift State and retry after resolving the torrent client problem",
        )
    )


def _protect_profile(root: Path) -> None:
    if not is_windows():
        root.chmod(0o700)
        return
    username: str = os.environ.get("USERNAME", "")
    domain: str = os.environ.get("USERDOMAIN", "")
    if not username:
        message: str = "The current Windows account cannot protect the private torrent profile"
        raise _unavailable(message)
    account: str = f"{domain}\\{username}" if domain else username
    executable: Path = Path(os.environ["SYSTEMROOT"]) / "System32" / "icacls.exe"
    result: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603 - system ACL utility and private root
        [str(executable), str(root), "/inheritance:r", "/grant:r", f"{account}:(OI)(CI)F"],
        capture_output=True,
        check=False,
        timeout=_START_TIMEOUT_S,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        message = "The private torrent profile could not be restricted to the current account"
        raise _unavailable(message)


def _process_identity(pid: int) -> tuple[int, str] | None:
    if sys.platform != "win32":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    handle = kernel.OpenProcess(_QUERY_PROCESS, False, pid)
    if not handle:
        return None
    try:
        created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
        image = ctypes.create_unicode_buffer(_MAX_IMAGE_PATH)
        length = wintypes.DWORD(_MAX_IMAGE_PATH)
        if not kernel.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)
        ):
            return None
        if exited.dwHighDateTime or exited.dwLowDateTime:
            return None
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            return None
        return ((created.dwHighDateTime << 32) | created.dwLowDateTime, image.value)
    finally:
        kernel.CloseHandle(handle)


def _visible_process_window(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    found: bool = False

    def inspect(window: int, _parameter: int) -> bool:
        nonlocal found
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        found = owner.value == pid and bool(user32.IsWindowVisible(window))
        return not found

    user32.EnumWindows(callback_type(inspect), 0)
    return found
