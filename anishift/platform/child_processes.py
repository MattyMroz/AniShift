"""Windows child-process lifetime tied to the resident, with explicit independent clients."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from typing import Final

from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_JOB_HANDLES: Final[list[int]] = []
"""Non-inherited job handles retained until Windows closes them at process exit."""

_JOB_FLAGS: Final[int] = 0x2000 | 0x0800
"""Kill inherited children on owner death while allowing explicit breakaway clients."""

_EXTENDED_LIMITS: Final[int] = 9
"""Windows information class for extended job limits."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


def contain_children() -> None:
    """Ensure inherited media workers cannot outlive this Windows resident process."""
    if sys.platform != "win32" or _JOB_HANDLES:
        return
    kernel: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle: int = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits: _ExtendedLimits = _ExtendedLimits()
    limits.basic.flags = _JOB_FLAGS
    try:
        if not kernel.SetInformationJobObject(handle, _EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    except OSError:
        kernel.CloseHandle(handle)
        raise
    _JOB_HANDLES.append(handle)
    logger.info("Resident child-process lifetime protected")


def independent_child_flags() -> int:
    """Let a separately owned torrent client or panel survive the resident's exit."""
    return getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0) if _JOB_HANDLES else 0
