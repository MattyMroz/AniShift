"""Blocking Windows directory notifications with an explicit polling fallback."""

from __future__ import annotations

import ctypes
import struct
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BUFFER_BYTES: Final[int] = 64 * 1024
"""Maximum notification buffer also accepted by Windows network redirectors."""

FALLBACK_INTERVAL_S: Final[float] = 30.0
"""Reconciliation interval when the filesystem cannot provide native notifications."""

_FILE_LIST_DIRECTORY: Final[int] = 0x0001
"""Directory access required for change notifications."""

_GENERIC_READ: Final[int] = 0x80000000
"""Read access used to admit complete sources, including read-only files."""

_SHARE_READ: Final[int] = 0x0001
"""Allow players to read a source while refusing existing writers."""

_SHARE_ALL: Final[int] = 0x0007
"""Keep read, write and deletion available to other directory users."""

_OPEN_EXISTING: Final[int] = 3
"""Open a directory without creating or replacing it."""

_DIRECTORY_FLAGS: Final[int] = 0x42000000
"""Backup semantics and overlapped I/O for a directory handle."""

_NOTIFY_FILTER: Final[int] = 0x0000001F
"""Watch names, directories, attributes, size and last-write changes."""

_INFINITE: Final[int] = 0xFFFFFFFF
"""Wait for an event without periodic wakeups."""

_ERROR_IO_PENDING: Final[int] = 997
"""An asynchronous directory read was accepted and is still pending."""

_ERROR_NOTIFY_ENUM_DIR: Final[int] = 1022
"""Windows could not retain every change and requires reconciliation."""

_CLOSE_TIMEOUT_S: Final[float] = 5.0
"""Time allowed for the notification thread to acknowledge cancellation."""


@dataclass(frozen=True, slots=True)
class DirectoryChange:
    """Changed paths or a request to reconcile the complete directory."""

    paths: tuple[Path, ...] = ()
    reconcile: bool = False
    reason: str = "change"


def source_is_available(path: Path) -> bool:
    """Check source readability and reject open writers on Windows."""
    if sys.platform != "win32":
        try:
            with path.open("rb"):
                return True
        except OSError:
            return False
    api: ctypes.CDLL = _kernel32()
    handle: int = int(api.CreateFileW(str(path), _GENERIC_READ, _SHARE_READ, None, _OPEN_EXISTING, 0, None))
    if handle == ctypes.c_void_p(-1).value:
        return False
    api.CloseHandle(handle)
    return True


class DirectoryWatch:
    """Observe a library without polling while native notifications are available."""

    def __init__(self, root: Path, changed: Callable[[DirectoryChange], None]) -> None:
        self._root: Path = root
        self._changed: Callable[[DirectoryChange], None] = changed
        self._stopped: threading.Event = threading.Event()
        self._native: _WindowsChanges | None = None
        self.mode: str = "native"
        try:
            self._native = _WindowsChanges(root)
        except OSError:
            self.mode = "polling"
        self._thread: threading.Thread = threading.Thread(target=self._run, name="anishift-files", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Cancel the outstanding wait and release directory and event handles."""
        self._stopped.set()
        native: _WindowsChanges | None = self._native
        if native is not None:
            native.stop()
        self._thread.join(_CLOSE_TIMEOUT_S)
        if self._thread.is_alive():
            msg = "The directory watcher did not acknowledge cancellation"
            raise TimeoutError(msg)

    def _run(self) -> None:
        native: _WindowsChanges | None = self._native
        if native is not None:
            try:
                self._run_native(native)
            except OSError:
                self.mode = "polling"
                logger.warning("Native directory notifications failed; using periodic reconciliation")
            finally:
                native.close()
                self._native = None
        if self._stopped.is_set():
            return
        self._changed(DirectoryChange(reconcile=True, reason="polling_fallback"))
        while not self._stopped.wait(FALLBACK_INTERVAL_S):
            self._changed(DirectoryChange(reconcile=True, reason="polling_fallback"))

    def _run_native(self, native: _WindowsChanges) -> None:
        while not self._stopped.is_set():
            change: DirectoryChange | None = native.read()
            if change is None:
                return
            self._changed(change)


class _Overlapped(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class _WindowsChanges:
    def __init__(self, root: Path) -> None:
        self._api: ctypes.CDLL = _kernel32()
        self._root: Path = root
        self._lock: threading.Lock = threading.Lock()
        self._closed: bool = False
        self._directory: int = int(
            self._api.CreateFileW(
                str(root),
                _FILE_LIST_DIRECTORY,
                _SHARE_ALL,
                None,
                _OPEN_EXISTING,
                _DIRECTORY_FLAGS,
                None,
            )
        )
        if self._directory == ctypes.c_void_p(-1).value:
            raise OSError(_last_error(), "Could not watch the library directory")
        self._stop: int = 0
        self._event: int = 0
        self._buffer: ctypes.Array[wintypes.DWORD] = (
            wintypes.DWORD * (BUFFER_BYTES // ctypes.sizeof(wintypes.DWORD))
        )()
        self._overlapped: _Overlapped = _Overlapped()
        try:
            self._stop = self._create_event()
            self._event = self._create_event()
            self._overlapped.hEvent = self._event
            self._arm()
        except OSError:
            self.close()
            raise

    def _arm(self) -> None:
        self._api.ResetEvent(self._event)
        accepted: bool = bool(
            self._api.ReadDirectoryChangesW(
                self._directory,
                self._buffer,
                BUFFER_BYTES,
                True,
                _NOTIFY_FILTER,
                None,
                ctypes.byref(self._overlapped),
                None,
            )
        )
        if not accepted and _last_error() != _ERROR_IO_PENDING:
            raise OSError(_last_error(), "Could not start directory notifications")

    def _create_event(self) -> int:
        handle: int = int(self._api.CreateEventW(None, True, False, None) or 0)
        if not handle:
            raise OSError(_last_error(), "Could not create directory notification events")
        return handle

    def read(self) -> DirectoryChange | None:
        handles: ctypes.Array[wintypes.HANDLE] = (wintypes.HANDLE * 2)(self._stop, self._event)
        signalled: int = int(self._api.WaitForMultipleObjects(2, handles, False, _INFINITE))
        if signalled == 0:
            return None
        if signalled != 1:
            raise OSError(_last_error(), "Directory notification wait failed")
        count: wintypes.DWORD = wintypes.DWORD()
        complete: bool = bool(
            self._api.GetOverlappedResult(
                self._directory,
                ctypes.byref(self._overlapped),
                ctypes.byref(count),
                False,
            )
        )
        if not complete and _last_error() != _ERROR_NOTIFY_ENUM_DIR:
            raise OSError(_last_error(), "Directory notification read failed")
        payload: bytes = ctypes.string_at(self._buffer, count.value) if complete else b""
        self._arm()
        return _decode_changes(self._root, payload)

    def stop(self) -> None:
        with self._lock:
            if not self._closed:
                self._api.SetEvent(self._stop)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._api.CancelIoEx(self._directory, ctypes.byref(self._overlapped))
            count: wintypes.DWORD = wintypes.DWORD()
            self._api.GetOverlappedResult(self._directory, ctypes.byref(self._overlapped), ctypes.byref(count), True)
            for handle in (self._directory, self._stop, self._event):
                if handle:
                    self._api.CloseHandle(handle)


def _decode_changes(root: Path, payload: bytes) -> DirectoryChange:  # noqa: PLR0911
    if not payload:
        return DirectoryChange(reconcile=True, reason="overflow")
    paths: dict[Path, None] = {}
    offset: int = 0
    while True:
        if offset + 12 > len(payload):
            return DirectoryChange(reconcile=True, reason="invalid_notification")
        following: int
        length: int
        following, _, length = struct.unpack_from("<III", payload, offset)
        end: int = offset + 12 + length
        if end > len(payload) or length % 2:
            return DirectoryChange(reconcile=True, reason="invalid_notification")
        try:
            relative: Path = Path(payload[offset + 12 : end].decode("utf-16-le"))
        except UnicodeDecodeError:
            return DirectoryChange(reconcile=True, reason="invalid_notification")
        if relative.is_absolute() or ".." in relative.parts:
            return DirectoryChange(reconcile=True, reason="invalid_notification")
        paths[root / relative] = None
        if not following:
            return DirectoryChange(paths=tuple(paths))
        if following < 12 + length or following % 4:
            return DirectoryChange(reconcile=True, reason="invalid_notification")
        offset += following


def _last_error() -> int:
    if sys.platform == "win32":
        return ctypes.get_last_error()
    msg = "Windows error state is unavailable on this platform"
    raise OSError(msg)


@cache
def _kernel32() -> ctypes.CDLL:
    if sys.platform != "win32":
        msg = "Native directory notifications require Windows"
        raise OSError(msg)
    api: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateEventW.restype = wintypes.HANDLE
    api.ReadDirectoryChangesW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    api.ReadDirectoryChangesW.restype = wintypes.BOOL
    api.GetOverlappedResult.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID, wintypes.BOOL]
    api.GetOverlappedResult.restype = wintypes.BOOL
    api.WaitForMultipleObjects.argtypes = [wintypes.DWORD, wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD]
    api.WaitForMultipleObjects.restype = wintypes.DWORD
    api.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    api.CancelIoEx.restype = wintypes.BOOL
    api.ResetEvent.argtypes = [wintypes.HANDLE]
    api.ResetEvent.restype = wintypes.BOOL
    api.SetEvent.argtypes = [wintypes.HANDLE]
    api.SetEvent.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api
