"""Single-file COM worker whose private desktop is never switched to the user's input desktop."""

from __future__ import annotations

import ctypes
import json
import os
import stat
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import UUID, uuid4

from anishift.platform.recycle import RecycleResult

if TYPE_CHECKING:
    from _ctypes import CFuncPtr, _CData

if sys.platform == "win32":
    import msvcrt

# ── Constants ─────────────────────────────────────────────────────────────────

_RECYCLE_FLAGS: Final[int] = 0x20184404
"""Recycle, record undo, warn before destruction, fail early, suppress progress and error UI; never auto-confirm."""

_FAIL: Final[int] = -2147467259
"""E_FAIL cancels the requested item and subsequent shell operations."""

_DRIVE_FIXED: Final[int] = 3
"""Local fixed media are the supported class for native recycling."""

_SHELL_ITEM: Final[str] = "43826d1e-e718-42ee-bc55-a1e261c37bfe"
"""IShellItem interface identifier."""

_FILE_OPERATION: Final[str] = "947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8"
"""IFileOperation interface identifier."""

_OPERATION_CLASS: Final[str] = "3ad05575-8857-4850-9277-11b85bdb8e09"
"""In-process Shell file operation class."""

_SINK_INTERFACES: Final[frozenset[bytes]] = frozenset(
    UUID(value).bytes_le for value in ("00000000-0000-0000-c000-000000000046", "04b0f1a7-9490-44bc-96e1-4296a31252e2")
)
"""IUnknown and IFileOperationProgressSink interfaces implemented by the retained callback table."""


class _Guid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    def __init__(self, value: str) -> None:
        super().__init__((ctypes.c_ubyte * 16).from_buffer_copy(UUID(value).bytes_le))


class _SinkPointer(ctypes.Structure):
    _fields_ = [("table", ctypes.POINTER(ctypes.c_void_p))]


def _dll(name: str) -> ctypes.CDLL:
    if sys.platform != "win32":
        message: str = "Windows recycling is unavailable"
        raise OSError(message)
    return ctypes.WinDLL(name, use_last_error=True)


def _callback_type(*types: type[_CData]) -> type[CFuncPtr]:
    if sys.platform != "win32":
        message: str = "Windows recycling is unavailable"
        raise OSError(message)
    return ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)


def _method(pointer: ctypes.c_void_p, index: int, *types: type[_CData]) -> CFuncPtr:
    table: ctypes._Pointer[ctypes.c_void_p] = ctypes.cast(
        pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    return _callback_type(*types)(table[index])


def _check(hr: int) -> None:
    if hr < 0:
        raise OSError(hr & 0xFFFFFFFF)


def _identity(path: Path) -> tuple[int, int, int, int] | None:
    try:
        if not path.is_absolute() or any(item.is_symlink() or item.is_junction() for item in (path, *path.parents)):
            return None
        info: os.stat_result = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino


def _supported_path(path: Path) -> bool:
    if path.drive.startswith("\\") or ":" in path.name or _identity(path) is None:
        return False
    kernel: ctypes.CDLL = _dll("kernel32")
    kernel.GetVolumePathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
    kernel.GetVolumeInformationW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    volume: ctypes.Array[ctypes.c_wchar] = ctypes.create_unicode_buffer(32768)
    filesystem: ctypes.Array[ctypes.c_wchar] = ctypes.create_unicode_buffer(64)
    return bool(
        kernel.GetVolumePathNameW(str(path), volume, len(volume))
        and kernel.GetDriveTypeW(volume.value) == _DRIVE_FIXED
        and kernel.GetVolumeInformationW(volume.value, None, 0, None, None, None, filesystem, len(filesystem))
        and filesystem.value == "NTFS"
    )


def _private_desktop() -> int:
    user: ctypes.CDLL = _dll("user32")
    user.CreateDesktopW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    user.CreateDesktopW.restype = ctypes.c_void_p
    user.SetThreadDesktop.argtypes = [ctypes.c_void_p]
    handle: int = user.CreateDesktopW(f"anishift-recycle-{uuid4().hex}", None, None, 0, 0x0083, None)
    if not handle or not user.SetThreadDesktop(handle):
        message: str = "A private recycle desktop could not be assigned"
        raise OSError(message)
    return handle


@contextmanager
def _locked_source(path: Path, identity: tuple[int, int, int, int]) -> Iterator[None]:
    if sys.platform != "win32":
        message: str = "Windows recycling is unavailable"
        raise OSError(message)
    kernel: ctypes.CDLL = _dll("kernel32")
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    handle: int = kernel.CreateFileW(str(path), 0x80000000, 0x5, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    descriptor: int
    if sys.platform == "win32":
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    try:
        info: os.stat_result = os.fstat(descriptor)
        if (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino) != identity or _identity(path) != identity:
            message = "The confirmed file changed"
            raise OSError(message)
        yield
    finally:
        os.close(descriptor)


class _ProgressSink:
    def __init__(self, path: Path, identity: tuple[int, int, int, int], ole: ctypes.CDLL) -> None:
        self.path: Path = path
        self.identity: tuple[int, int, int, int] = identity
        self.ole: ctypes.CDLL = ole
        self.pointer: _SinkPointer = _SinkPointer()
        self.references: int = 1
        self.allowed: bool = False
        self.failed: bool = False
        self.post_hr: int | None = None
        self.receipt: str | None = None
        signatures: list[tuple[type[_CData], ...]] = [
            (ctypes.c_void_p, ctypes.c_void_p),
            (),
            (),
            (),
            (ctypes.c_int32,),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_wchar_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int32, ctypes.c_void_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int32, ctypes.c_void_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int32, ctypes.c_void_p),
            (ctypes.c_uint32, ctypes.c_void_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p),
            (ctypes.c_uint32, ctypes.c_void_p, ctypes.c_wchar_p),
            (
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                ctypes.c_uint32,
                ctypes.c_int32,
                ctypes.c_void_p,
            ),
            (ctypes.c_uint32, ctypes.c_uint32),
            (),
            (),
            (),
        ]
        actions: dict[int, Callable[..., int]] = {
            0: self._query,
            1: self._add_ref,
            2: self._release,
            11: self._pre,
            12: self._post,
        }
        self.callbacks: list[CFuncPtr] = [
            _callback_type(*signature)(self._guard(actions.get(index, self._noop)))
            for index, signature in enumerate(signatures)
        ]
        self.table: ctypes.Array[ctypes.c_void_p] = (ctypes.c_void_p * len(self.callbacks))(
            *(ctypes.cast(callback, ctypes.c_void_p).value for callback in self.callbacks)
        )
        self.pointer.table = self.table

    def _guard(self, action: Callable[..., int]) -> Callable[..., int]:
        def call(*args: object) -> int:
            try:
                return action(*args)
            except BaseException:  # noqa: BLE001
                self.failed = True
                return _FAIL

        return call

    def _query(self, this: int, iid: int, output: int) -> int:
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = None
        if ctypes.string_at(iid, 16) not in _SINK_INTERFACES:
            return -2147467262
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(self.pointer)
        self._add_ref(this)
        return 0

    def _add_ref(self, this: int) -> int:
        del this
        self.references += 1
        return self.references

    def _release(self, this: int) -> int:
        del this
        self.references -= 1
        return self.references

    @staticmethod
    def _noop(*args: object) -> int:
        return 0

    def _pre(self, this: int, flags: int, source: int) -> int:
        del this, source
        self.allowed = bool(flags & 0x80) and not self.failed and _identity(self.path) == self.identity
        if not self.allowed:
            self.failed = True
        return 0 if self.allowed else _FAIL

    def _post(self, this: int, flags: int, source: int, hr: int, destination: int) -> int:
        del this, flags, source
        self.post_hr = hr
        if hr < 0 or not destination or not self.allowed:
            return _FAIL
        value: ctypes.c_void_p = ctypes.c_void_p()
        item: ctypes.c_void_p = ctypes.c_void_p(destination)
        _check(
            _method(item, 5, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(item, 0x80028000, ctypes.byref(value))
        )
        try:
            self.receipt = ctypes.wstring_at(value) if value.value else None
        finally:
            self.ole.CoTaskMemFree(value)
        return 0 if self.receipt else _FAIL


def _native_recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
    ole: ctypes.CDLL = _dll("ole32")
    shell: ctypes.CDLL = _dll("shell32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoCreateInstance.argtypes = [
        ctypes.POINTER(_Guid),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell.SHCreateItemFromParsingName.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _check(ole.CoInitializeEx(None, 2))
    item: ctypes.c_void_p = ctypes.c_void_p()
    operation: ctypes.c_void_p = ctypes.c_void_p()
    sink: _ProgressSink = _ProgressSink(path, identity, ole)
    try:
        _check(shell.SHCreateItemFromParsingName(str(path), None, ctypes.byref(_Guid(_SHELL_ITEM)), ctypes.byref(item)))
        _check(
            ole.CoCreateInstance(
                ctypes.byref(_Guid(_OPERATION_CLASS)),
                None,
                1,
                ctypes.byref(_Guid(_FILE_OPERATION)),
                ctypes.byref(operation),
            )
        )
        _check(_method(operation, 5, ctypes.c_uint32)(operation, _RECYCLE_FLAGS))
        _check(_method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, item, ctypes.byref(sink.pointer)))
        result: int = _method(operation, 21)(operation)
        aborted: ctypes.c_int32 = ctypes.c_int32(1)
        aborted_result: int = _method(operation, 22, ctypes.POINTER(ctypes.c_int32))(operation, ctypes.byref(aborted))
        if (
            result >= 0
            and aborted_result >= 0
            and not aborted.value
            and not sink.failed
            and sink.allowed
            and sink.post_hr is not None
            and sink.post_hr >= 0
            and sink.receipt
            and not path.exists()
        ):
            return RecycleResult("recycled", "recycle_completed", sink.receipt)
        if (
            sink.receipt
            or _identity(path) != identity
            or sink.post_hr is None
            or aborted_result < 0
            or (sink.allowed and (sink.failed or aborted.value))
        ):
            return RecycleResult("uncertain", "recycle_incomplete", sink.receipt)
        return RecycleResult("refused", "recycle_refused")
    finally:
        for pointer in (item, operation):
            if pointer.value:
                _method(pointer, 2)(pointer)
        ole.CoUninitialize()


def _read_request(payload: dict[str, object]) -> tuple[Path, tuple[int, int, int, int]]:
    values: object = payload["identity"]
    path: object = payload["path"]
    parent_pid: object = payload["parent_pid"]
    if not isinstance(values, list) or not isinstance(path, str) or type(parent_pid) is not int:
        message: str = "Invalid recycle request"
        raise ValueError(message)
    size: int
    stamp: int
    device: int
    inode: int
    size, stamp, device, inode = values
    identity: tuple[int, int, int, int] = (size, stamp, device, inode)
    if any(type(value) is not int for value in identity):
        message = "Invalid file identity"
        raise ValueError(message)
    _watch_parent(parent_pid)
    return Path(path), identity


def _watch_parent(pid: int) -> None:
    if pid != os.getppid():
        message: str = "The recycle helper parent changed"
        raise OSError(message)
    kernel: ctypes.CDLL = _dll("kernel32")
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    handle: int = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        message = "The recycle helper parent is unavailable"
        raise OSError(message)

    def wait() -> None:
        kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        os._exit(125)

    threading.Thread(target=wait, daemon=True).start()


def main() -> None:
    """Execute one request only after desktop isolation and supported-file validation succeed."""
    result: RecycleResult = RecycleResult("refused", "recycle_unsupported")
    started: bool = False
    try:
        payload: dict[str, object] = json.loads(sys.stdin.read())
        if payload.get("operation") == "restore":
            from anishift.platform.restore_worker import restore_request  # noqa: PLC0415

            result = restore_request(payload)
            sys.stdout.write(json.dumps(asdict(result)))
            sys.stdout.flush()
            return
        path, identity = _read_request(payload)
        if sys.platform == "win32" and _supported_path(path) and _identity(path) == identity:
            _private_desktop()
            with _locked_source(path, identity):
                started = True
                result = _native_recycle(path, identity)
    except OSError, ValueError, KeyError, TypeError:
        result = RecycleResult("uncertain" if started else "refused", "recycle_unavailable")
    sys.stdout.write(json.dumps(asdict(result)))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
