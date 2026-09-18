"""Restore one exact virtual Recycle Bin item without replacing an occupied destination."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from anishift.platform.recycle import RecycleResult
from anishift.platform.recycle_worker import (
    _FAIL,
    _FILE_OPERATION,
    _OPERATION_CLASS,
    _SHELL_ITEM,
    _callback_type,
    _check,
    _dll,
    _Guid,
    _identity,
    _locked_source,
    _method,
    _private_desktop,
    _ProgressSink,
    _supported_path,
    _watch_parent,
)

if sys.platform == "win32":
    import msvcrt

# ── Constants ─────────────────────────────────────────────────────────────────

_MOVE_FLAGS: Final[int] = 0x00100404
"""Fail early and suppress progress/error UI without consenting to replacement."""

_IDENTITY_FIELDS: Final[int] = 4
"""Size, modification time, device and inode form a complete file identity."""


def _safe_parents(path: Path) -> bool:
    return path.is_absolute() and all(
        not item.is_symlink() and not item.is_junction() for item in (path, *path.parents)
    )


def _occupied(path: Path) -> bool:
    return os.path.lexists(path)


@contextmanager
def _held_parents(path: Path) -> Iterator[None]:
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
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handles: list[int] = []
    try:
        for parent in reversed(path.parents):
            handle: int = kernel.CreateFileW(str(parent), 0x80, 0x3, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise OSError("restore_unsafe_path")
            handles.append(handle)
        if not _safe_parents(path):
            raise OSError("restore_unsafe_path")
        yield
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def _publish_file(staging: Path, path: Path, identity: tuple[int, int, int, int]) -> None:
    if sys.platform != "win32":
        raise OSError("restore_unsupported")
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
    kernel.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    with _held_parents(path), _held_parents(staging):
        handle: int = kernel.CreateFileW(str(staging), 0x80010000, 0x1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError("restore_source_busy")
        descriptor: int
        if sys.platform == "win32":
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        try:
            info: os.stat_result = os.fstat(descriptor)
            if (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino) != identity:
                raise OSError("restore_scope_changed")
            _rename_handle(kernel, handle, path)
        finally:
            os.close(descriptor)


def _rename_handle(kernel: ctypes.CDLL, handle: int, path: Path) -> None:
    encoded: bytes = str(path).encode("utf-16-le")
    terminated: bytes = encoded + b"\x00\x00"

    class RenameInfo(ctypes.Structure):
        _fields_ = [
            ("replace", ctypes.c_uint32),
            ("root", ctypes.c_void_p),
            ("length", ctypes.c_uint32),
            ("name", ctypes.c_ubyte * len(terminated)),
        ]

    request: RenameInfo = RenameInfo(
        0, None, len(encoded), (ctypes.c_ubyte * len(terminated)).from_buffer_copy(terminated)
    )
    if not kernel.SetFileInformationByHandle(handle, 3, ctypes.byref(request), ctypes.sizeof(request)):
        if _occupied(path):
            raise FileExistsError("restore_destination_occupied")
        raise OSError("restore_publish_failed")


def _display(item: ctypes.c_void_p, ole: ctypes.CDLL) -> str | None:
    value: ctypes.c_void_p = ctypes.c_void_p()
    hr: int = _method(item, 5, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p))(item, 0x80058000, ctypes.byref(value))
    try:
        return ctypes.wstring_at(value) if hr >= 0 and value.value else None
    finally:
        if value.value:
            ole.CoTaskMemFree(value)


class _BinItem:
    def __init__(self, receipt: Path) -> None:
        self.ole: ctypes.CDLL = _dll("ole32")
        self.shell: ctypes.CDLL = _dll("shell32")
        self.item: ctypes.c_void_p = ctypes.c_void_p()
        self.folder: ctypes.c_void_p = ctypes.c_void_p()
        self.root: ctypes.c_void_p = ctypes.c_void_p()
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.shell.SHGetKnownFolderItem.argtypes = [
            ctypes.POINTER(_Guid),
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.shell.SHCreateItemWithParent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        _check(self.ole.CoInitializeEx(None, 2))
        try:
            self._bind(receipt)
        except OSError:
            self.close()
            raise

    def _bind(self, receipt: Path) -> None:
        iid: _Guid = _Guid(_SHELL_ITEM)
        _check(
            self.shell.SHGetKnownFolderItem(
                ctypes.byref(_Guid("b7534046-3ecb-4c18-be4e-64cd4cb7d6ac")),
                0,
                None,
                ctypes.byref(iid),
                ctypes.byref(self.root),
            )
        )
        _check(
            _method(
                self.root,
                3,
                ctypes.c_void_p,
                ctypes.POINTER(_Guid),
                ctypes.POINTER(_Guid),
                ctypes.POINTER(ctypes.c_void_p),
            )(
                self.root,
                None,
                ctypes.byref(_Guid("3981e224-f559-11d3-8e3a-00c04f6837d5")),
                ctypes.byref(_Guid("000214e6-0000-0000-c000-000000000046")),
                ctypes.byref(self.folder),
            )
        )
        pidl: ctypes.c_void_p = ctypes.c_void_p()
        eaten: ctypes.c_uint32 = ctypes.c_uint32()
        attrs: ctypes.c_uint32 = ctypes.c_uint32()
        try:
            _check(
                _method(
                    self.folder,
                    3,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_uint32),
                )(self.folder, None, None, str(receipt), ctypes.byref(eaten), ctypes.byref(pidl), ctypes.byref(attrs))
            )
            _check(
                self.shell.SHCreateItemWithParent(None, self.folder, pidl, ctypes.byref(iid), ctypes.byref(self.item))
            )
        finally:
            if pidl.value:
                self.ole.CoTaskMemFree(pidl)
        if _display(self.item, self.ole) != str(receipt):
            raise OSError("restore_receipt_mismatch")

    def close(self) -> None:
        """Release only this exact item and its namespace bindings."""
        for pointer in (self.item, self.folder, self.root):
            if pointer.value:
                _method(pointer, 2)(pointer)
        self.ole.CoUninitialize()


class _MoveSink(_ProgressSink):
    def __init__(self, receipt: Path, staging: Path, identity: tuple[int, int, int, int], ole: ctypes.CDLL) -> None:
        super().__init__(receipt, identity, ole)
        self.staging: Path = staging
        self.callbacks[7] = _callback_type(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p)(
            self._guard(self._pre_move)
        )
        self.callbacks[8] = _callback_type(
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int32, ctypes.c_void_p
        )(self._guard(self._post_move))
        for index in (7, 8):
            self.table[index] = ctypes.cast(self.callbacks[index], ctypes.c_void_p).value

    def _pre_move(self, this: int, flags: int, source: int, parent: int, name: str) -> int:
        del this, flags
        self.allowed = (
            not self.failed
            and _display(ctypes.c_void_p(source), self.ole) == str(self.path)
            and _display(ctypes.c_void_p(parent), self.ole) == str(self.staging.parent)
            and name == self.staging.name
            and not _occupied(self.staging)
            and _safe_parents(self.staging)
            and _identity(self.path) == self.identity
        )
        return 0 if self.allowed else _FAIL

    def _post_move(self, this: int, flags: int, source: int, parent: int, name: str, hr: int, created: int) -> int:  # noqa: PLR0913 - native callback ABI
        del this, flags, source, parent, name
        self.post_hr = hr
        self.allowed = (
            self.allowed
            and hr >= 0
            and bool(created)
            and _display(ctypes.c_void_p(created), self.ole) == str(self.staging)
            and _identity(self.staging) == self.identity
        )
        return 0 if self.allowed else _FAIL


def _move(item: _BinItem, receipt: Path, staging: Path, identity: tuple[int, int, int, int]) -> bool:
    target: ctypes.c_void_p = ctypes.c_void_p()
    operation: ctypes.c_void_p = ctypes.c_void_p()
    item.shell.SHCreateItemFromParsingName.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    item.ole.CoCreateInstance.argtypes = [
        ctypes.POINTER(_Guid),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    sink: _MoveSink = _MoveSink(receipt, staging, identity, item.ole)
    try:
        _check(
            item.shell.SHCreateItemFromParsingName(
                str(staging.parent), None, ctypes.byref(_Guid(_SHELL_ITEM)), ctypes.byref(target)
            )
        )
        _check(
            item.ole.CoCreateInstance(
                ctypes.byref(_Guid(_OPERATION_CLASS)),
                None,
                1,
                ctypes.byref(_Guid(_FILE_OPERATION)),
                ctypes.byref(operation),
            )
        )
        _check(_method(operation, 5, ctypes.c_uint32)(operation, _MOVE_FLAGS))
        _check(
            _method(operation, 14, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p)(
                operation, item.item, target, staging.name, ctypes.byref(sink.pointer)
            )
        )
        with _locked_source(receipt, identity):
            hr: int = _method(operation, 21)(operation)
        aborted: ctypes.c_int32 = ctypes.c_int32(1)
        aborted_hr: int = _method(operation, 22, ctypes.POINTER(ctypes.c_int32))(operation, ctypes.byref(aborted))
        return (
            hr >= 0
            and aborted_hr >= 0
            and not aborted.value
            and sink.allowed
            and not sink.failed
            and sink.post_hr is not None
            and sink.post_hr >= 0
            and not _occupied(receipt)
            and _identity(staging) == identity
        )
    finally:
        for pointer in (operation, target):
            if pointer.value:
                _method(pointer, 2)(pointer)


def restore_request(payload: dict[str, object]) -> RecycleResult:
    """Inspect recorded locations in check-only mode, otherwise restore and publish the exact item."""
    try:
        return _restore(payload)
    except OSError, ValueError, TypeError, KeyError:
        return RecycleResult("uncertain", "restore_interrupted")


def _restore(payload: dict[str, object]) -> RecycleResult:  # noqa: C901, PLR0911, PLR0912 - reconcile mutually exclusive persisted locations before mutation
    parent: object = payload["parent_pid"]
    if type(parent) is not int:
        raise ValueError("restore_invalid_request")
    _watch_parent(parent)
    _private_desktop()
    root: Path = Path(str(payload["workspace"]))
    relative: Path = Path(str(payload["path"]))
    staged: Path = Path(str(payload["staging"]))
    if (
        relative.is_absolute()
        or staged.is_absolute()
        or relative.drive
        or staged.drive
        or ".." in (*relative.parts, *staged.parts)
        or ":" in str(relative)
        or ":" in str(staged)
    ):
        raise ValueError("restore_invalid_path")
    path: Path = root / relative
    staging: Path = root / staged
    if not staged.as_posix().startswith("temp/.restore-") or not all(map(_safe_parents, (path, staging))):
        return RecycleResult("refused", "restore_unsafe_path")
    values: object = payload["identity"]
    if (
        not isinstance(values, list)
        or len(values) != _IDENTITY_FIELDS
        or any(type(value) is not int for value in values)
    ):
        raise ValueError("restore_invalid_identity")
    identity: tuple[int, int, int, int] = (values[0], values[1], values[2], values[3])
    receipt: Path | None = Path(str(payload["receipt"])) if payload.get("receipt") else None
    if _occupied(path):
        if not _occupied(staging) and _identity(path) == identity and (receipt is None or not _occupied(receipt)):
            return RecycleResult("restored", "restore_completed")
        return RecycleResult("refused", "restore_destination_occupied")
    if not path.parent.is_dir() or path.parent.stat().st_dev != identity[2]:
        return RecycleResult("refused", "restore_unsupported_destination")
    ancestor: Path = next(parent for parent in staging.parents if parent.exists())
    if not ancestor.is_dir() or ancestor.stat().st_dev != identity[2]:
        return RecycleResult("refused", "restore_unsupported_destination")
    if _occupied(staging):
        if not payload.get("started") or _identity(staging) != identity or (receipt is not None and _occupied(receipt)):
            return RecycleResult("uncertain", "restore_scope_changed")
    elif receipt is None or _identity(receipt) != identity or not _supported_path(receipt):
        return RecycleResult("refused", "restore_receipt_missing")
    elif payload.get("check_only"):
        item: _BinItem = _BinItem(receipt)
        item.close()
        return RecycleResult("ready", "restore_ready_bin")
    elif not _stage_item(root, receipt, staging, identity):
        return RecycleResult("uncertain", "restore_incomplete")
    if payload.get("check_only"):
        return RecycleResult("ready", "restore_ready")
    try:
        _publish_file(staging, path, identity)
    except FileExistsError:
        return RecycleResult("refused", "restore_destination_occupied")
    return (
        RecycleResult("restored", "restore_completed")
        if _identity(path) == identity
        else RecycleResult("uncertain", "restore_incomplete")
    )


def _stage_item(root: Path, receipt: Path, staging: Path, identity: tuple[int, int, int, int]) -> bool:
    temporary: Path = root / "temp"
    with _held_parents(temporary):
        temporary.mkdir(exist_ok=True)
    with _held_parents(staging.parent):
        staging.parent.mkdir(exist_ok=True)
    with _held_parents(staging):
        if staging.parent.stat().st_dev != identity[2]:
            raise OSError("restore_unsupported_destination")
        item: _BinItem = _BinItem(receipt)
        try:
            return _move(item, receipt, staging, identity)
        finally:
            item.close()
