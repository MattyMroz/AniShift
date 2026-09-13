"""Windows notification icon backed by one hidden message window."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from enum import IntEnum
from secrets import token_hex
from shutil import which
from typing import Final

from anishift.utils.logger import get_logger

__all__ = ["TrayIcon", "raise_panel"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_START_TIMEOUT_S: Final[float] = 5.0
"""Maximum wait for the hidden tray window to be created or closed."""


class _Message(IntEnum):
    DESTROY = 0x0002
    CLOSE = 0x0010
    LEFT_UP = 0x0202
    RIGHT_UP = 0x0205
    TRAY = 0x8001
    UPDATE = 0x8002


def raise_panel(window_name: str | None) -> None:
    """Raise the explicitly requested panel in its owned terminal window when available."""
    if sys.platform != "win32":
        return
    terminal: str | None = which("wt.exe") if window_name is not None else None
    if terminal is not None:
        try:
            subprocess.Popen(  # noqa: S603 - focus the named window that launched this panel
                [terminal, "-w", str(window_name), "focus-tab", "-t", "0"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as error:
            logger.warning("Could not raise the panel", error_class=type(error).__name__)
        return
    kernel: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)
    user: ctypes.CDLL = ctypes.WinDLL("user32", use_last_error=True)
    kernel.GetConsoleWindow.restype = wintypes.HWND
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    window: int = kernel.GetConsoleWindow()
    if not window or not user.IsWindowVisible(window):
        return
    if user.IsIconic(window):
        user.ShowWindow(window, 9)
    user.SetForegroundWindow(window)


class _NotifyIcon(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class TrayIcon:
    """Forward tray actions without doing application work on the Windows message thread."""

    def __init__(self, action: Callable[[str], None]) -> None:
        self._action: Callable[[str], None] = action
        self._lock: threading.Lock = threading.Lock()
        self._ready: threading.Event = threading.Event()
        self._window: int = 0
        self._auto: bool = False
        self._busy: bool = False
        self._problem: bool = False
        self._notification: tuple[str, str] | None = None
        self._post: Callable[[int, int, int, int], object] | None = None
        self._thread: threading.Thread | None = None
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._run, name="anishift-tray", daemon=True)
            self._thread.start()
            self._ready.wait(_START_TIMEOUT_S)

    @property
    def available(self) -> bool:
        """Whether the Windows tray message window was created."""
        return self._window != 0

    def update(self, *, auto_enabled: bool, busy: bool, problem: bool = False) -> None:
        """Replace the tooltip state without touching the application or network."""
        with self._lock:
            self._auto, self._busy = auto_enabled, busy
            self._problem = problem
        self._send(_Message.UPDATE)

    def notify(self, title: str, message: str) -> None:
        """Offer one result notification without making delivery a success condition."""
        with self._lock:
            self._notification = (title, message)
        self._send(_Message.UPDATE)

    def close(self) -> None:
        """Remove the icon and join its message thread."""
        self._send(_Message.CLOSE)
        if self._thread is not None:
            self._thread.join(_START_TIMEOUT_S)

    def _send(self, message: _Message) -> None:
        if self._post is not None and self._window:
            self._post(self._window, message, 0, 0)

    def _run(self) -> None:
        try:
            self._message_loop()
        except (OSError, ValueError) as error:
            logger.warning("Windows tray unavailable", error_class=type(error).__name__)
        finally:
            self._window = 0
            self._ready.set()

    def _message_loop(self) -> None:  # noqa: PLR0915 - native signatures and callbacks share one window lifetime
        if sys.platform != "win32":
            return
        user = ctypes.WinDLL("user32", use_last_error=True)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        class WindowClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("procedure", callback_type),
                ("class_extra", ctypes.c_int),
                ("window_extra", ctypes.c_int),
                ("instance", wintypes.HINSTANCE),
                ("icon", wintypes.HICON),
                ("cursor", wintypes.HANDLE),
                ("background", wintypes.HBRUSH),
                ("menu", wintypes.LPCWSTR),
                ("name", wintypes.LPCWSTR),
            ]

        user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
        user.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user.CreateWindowExW.restype = wintypes.HWND
        user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.DefWindowProcW.restype = ctypes.c_ssize_t
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user.LoadIconW.restype = wintypes.HICON
        user.DestroyWindow.argtypes = [wintypes.HWND]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = ctypes.c_ssize_t
        user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        shell.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NotifyIcon)]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self._post = user.PostMessageW
        taskbar_created: int = user.RegisterWindowMessageW("TaskbarCreated")
        data: _NotifyIcon = _NotifyIcon()
        data.cbSize, data.uID = ctypes.sizeof(data), 1
        data.uCallbackMessage = _Message.TRAY
        data.hIcon = user.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))

        def update(operation: int) -> None:
            with self._lock:
                enabled: bool = self._auto
                busy: bool = self._busy
                problem: bool = self._problem
                notification: tuple[str, str] | None = self._notification
                self._notification = None
            data.uFlags = 1 | 2 | 4
            activity: str = "wymaga uwagi" if problem else ("praca trwa" if busy else "czuwanie")
            data.szTip = f"AniShift · Auto {'włączone' if enabled else 'wyłączone'} · {activity}"
            data.szInfo, data.szInfoTitle = "", ""
            if notification is not None:
                data.uFlags |= 16
                data.szInfoTitle, data.szInfo = notification[0][:63], notification[1][:255]
                data.dwInfoFlags = 1
            shell.Shell_NotifyIconW(operation, ctypes.byref(data))

        def procedure(window: int, message: int, parameter: int, detail: int) -> int:
            if message == taskbar_created:
                update(0)
            elif message == _Message.UPDATE:
                update(1)
            elif message == _Message.TRAY and detail == _Message.LEFT_UP:
                self._action("open")
            elif message == _Message.TRAY and detail == _Message.RIGHT_UP:
                self._menu(window)
            elif message == _Message.CLOSE:
                shell.Shell_NotifyIconW(2, ctypes.byref(data))
                user.DestroyWindow(window)
            elif message == _Message.DESTROY:
                user.PostQuitMessage(0)
            else:
                return int(user.DefWindowProcW(window, message, parameter, detail))
            return 0

        callback = callback_type(procedure)
        instance = kernel.GetModuleHandleW(None)
        name: str = f"AniShiftTray-{token_hex(8)}"
        definition: WindowClass = WindowClass()
        definition.procedure, definition.instance, definition.name = callback, instance, name
        if not user.RegisterClassW(ctypes.byref(definition)):
            raise ctypes.WinError(ctypes.get_last_error())
        window: int = user.CreateWindowExW(0, name, "AniShift", 0, 0, 0, 0, 0, None, None, instance, None)
        if not window:
            user.UnregisterClassW(name, instance)
            raise ctypes.WinError(ctypes.get_last_error())
        self._window, data.hWnd = window, window
        try:
            update(0)
            self._ready.set()
            message = wintypes.MSG()
            while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        finally:
            shell.Shell_NotifyIconW(2, ctypes.byref(data))
            user.UnregisterClassW(name, instance)

    def _menu(self, window: int) -> None:
        if sys.platform != "win32":
            return
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.CreatePopupMenu.restype = wintypes.HMENU
        user.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.LPVOID,
        ]
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.DestroyMenu.argtypes = [wintypes.HMENU]
        menu = user.CreatePopupMenu()
        try:
            user.AppendMenuW(menu, 0, 1, "Otwórz AniShift")
            user.AppendMenuW(menu, 0, 2, "Wyłącz Auto" if self._auto else "Włącz Auto")
            user.AppendMenuW(menu, 0, 3, "Zakończ AniShift")
            point = wintypes.POINT()
            user.GetCursorPos(ctypes.byref(point))
            user.SetForegroundWindow(window)
            selected: int = user.TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, window, None)
            action: str | None = {1: "open", 2: "toggle_auto", 3: "shutdown"}.get(selected)
            if action is not None:
                self._action(action)
        finally:
            user.DestroyMenu(menu)
