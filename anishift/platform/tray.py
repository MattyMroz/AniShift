"""Windows notification icon backed by one hidden message window."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from contextlib import ExitStack
from ctypes import wintypes
from dataclasses import dataclass
from enum import IntEnum
from importlib.resources import as_file, files
from pathlib import Path
from secrets import token_hex
from shutil import which
from time import monotonic, sleep
from typing import Final

from anishift.utils.logger import get_logger

__all__ = ["TrayIcon", "open_path", "raise_panel"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_START_TIMEOUT_S: Final[float] = 5.0
"""Maximum wait for the hidden tray window to be created or closed."""

_EXIT_NOTIFICATION_S: Final[float] = 5.0
"""Reading opportunity after the shell accepts a final error notification, before its icon is removed."""

_ICON_PARTS: Final[tuple[str, ...]] = ("cli", "interactive", "assets", "mascot", "app.ico")
"""Packaged mascot icon loaded without importing the interactive frontend."""

_APP_ID: Final[str] = "AniShift.Desktop"
"""Stable Windows identity shared by resident windows and their notifications."""

_MAX_BALLOONS: Final[int] = 32
"""Maximum pending notifications retained by the desktop adapter."""

_BALLOON_EXPIRY_S: Final[float] = 300.0
"""Delivery budget; expiry revokes identity and never proves which notification was clicked."""


class _Message(IntEnum):
    DESTROY = 0x0002
    CLOSE = 0x0010
    LEFT_UP = 0x0202
    RIGHT_UP = 0x0205
    CONTEXT_MENU = 0x007B
    SELECT = 0x0400
    KEY_SELECT = 0x0401
    BALLOON_SHOW = 0x0402
    BALLOON_HIDE = 0x0403
    BALLOON_TIMEOUT = 0x0404
    BALLOON_CLICK = 0x0405
    TIMER = 0x0113
    TRAY = 0x8001
    UPDATE = 0x8002


def open_path(path: Path, *, show_folder: bool = False) -> None:
    """Open an already validated desktop result or select it in its containing folder."""
    if sys.platform == "win32":
        if show_folder:
            system_root: str | None = os.environ.get("SYSTEMROOT")
            if not system_root:
                message: str = "The Windows system directory is unavailable"
                raise OSError(message)
            explorer: Path = Path(system_root) / "explorer.exe"
            subprocess.Popen([str(explorer), "/select,", str(path)])  # noqa: S603 - validated workspace file
        else:
            os.startfile(path)  # noqa: S606 - validated workspace file
    else:
        target: Path = path.parent if show_folder else path
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])  # noqa: S603


@dataclass(frozen=True, slots=True)
class _Balloon:
    title: str
    message: str
    notification_id: str | None
    queued_at: float
    final: bool = False


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
        self._pausing: bool = False
        self._incomplete: bool = False
        self._notifications: deque[_Balloon] = deque(maxlen=_MAX_BALLOONS)
        self._active: _Balloon | None = None
        self._shown: bool = False
        self._ambiguous: bool = False
        self._closing: bool = False
        self._timer_id: int = 0
        self._arm_timer: Callable[[int], object] | None = None
        self._cancel_timer: Callable[[int], object] | None = None
        self._notification_submitted: threading.Event = threading.Event()
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

    def update(
        self,
        *,
        auto_enabled: bool,
        busy: bool,
        problem: bool = False,
        pausing: bool = False,
        incomplete: bool = False,
    ) -> None:
        """Replace the tooltip state without touching the application or network."""
        with self._lock:
            self._auto, self._busy = auto_enabled, busy
            self._problem, self._pausing = problem, pausing
            self._incomplete = incomplete
        self._send(_Message.UPDATE)

    def notify(self, title: str, message: str, notification_id: str | None = None) -> None:
        """Offer one result notification without making delivery a success condition."""
        with self._lock:
            if not self.available or self._closing:
                return
            self._notifications.append(_Balloon(title, message, notification_id, monotonic()))
        self._send(_Message.UPDATE)

    def close(self, *, notification: tuple[str, str] | None = None) -> None:
        """Offer a final error time on screen before removing the icon and joining its message thread."""
        with self._lock:
            self._closing = True
            self._notifications.clear()
            if notification is not None and self.available:
                self._notification_submitted.clear()
                self._notifications.append(_Balloon(*notification, None, monotonic(), final=True))
        if notification is not None and self.available:
            self._send(_Message.UPDATE)
            if self._notification_submitted.wait(_START_TIMEOUT_S):
                sleep(_EXIT_NOTIFICATION_S)
        self._send(_Message.CLOSE)
        if self._thread is not None:
            self._thread.join(_START_TIMEOUT_S)

    def _send(self, message: _Message) -> None:
        if self._post is not None and self._window:
            self._post(self._window, message, 0, 0)

    def _retire_balloon(self, *, ambiguous: bool) -> None:
        self._ambiguous |= ambiguous
        self._active = None
        self._shown = False
        if self._cancel_timer is not None:
            self._cancel_timer(self._timer_id)

    def _balloon_event(self, event: int, icon_id: int) -> None:
        if icon_id != 1:
            if event == _Message.BALLOON_CLICK:
                self._action("notification:")
            return
        if event == _Message.BALLOON_SHOW:
            if self._active is None or self._shown:
                self._ambiguous = True
            else:
                self._shown = True
            return
        if event == _Message.BALLOON_CLICK:
            target: str = ""
            if self._active is not None and self._shown and not self._ambiguous and not self._closing:
                target = self._active.notification_id or ""
            self._action(f"notification:{target}")
            self._retire_balloon(ambiguous=not bool(target))
        elif event in {_Message.BALLOON_HIDE, _Message.BALLOON_TIMEOUT}:
            self._retire_balloon(ambiguous=True)
        self._send(_Message.UPDATE)

    def _tray_event(self, window: int, detail: int) -> None:
        event: int = detail & 0xFFFF
        if event in {_Message.LEFT_UP, _Message.SELECT, _Message.KEY_SELECT}:
            self._action("open")
        elif event in {_Message.BALLOON_SHOW, _Message.BALLOON_HIDE, _Message.BALLOON_TIMEOUT, _Message.BALLOON_CLICK}:
            self._balloon_event(event, (detail >> 16) & 0xFFFF)
        elif event in {_Message.RIGHT_UP, _Message.CONTEXT_MENU}:
            self._menu(window)

    def _expire_balloon(self, timer_id: int) -> None:
        if self._active is None or timer_id != self._timer_id:
            return
        self._retire_balloon(ambiguous=True)
        self._send(_Message.UPDATE)

    def _submit_balloon(self, submit: Callable[[_Balloon], bool]) -> None:
        with self._lock:
            if self._closing and self._notifications:
                self._retire_balloon(ambiguous=True)
            if self._active is not None:
                return
            while self._notifications and monotonic() - self._notifications[0].queued_at >= _BALLOON_EXPIRY_S:
                self._notifications.popleft()
            if not self._notifications:
                return
            balloon: _Balloon = self._notifications.popleft()
            self._active = balloon
        if not submit(balloon):
            self._retire_balloon(ambiguous=True)
            self._send(_Message.UPDATE)
            return
        if balloon.final:
            self._notification_submitted.set()
        if self._active is not balloon:
            return
        self._timer_id += 1
        if self._arm_timer is None or not self._arm_timer(self._timer_id):
            self._expire_balloon(self._timer_id)

    def _reset_balloon(self) -> None:
        self._retire_balloon(ambiguous=True)
        with self._lock:
            self._notifications.clear()

    def _update_icon(self, data: _NotifyIcon, operation: int, notify: Callable[[int, _NotifyIcon], bool]) -> None:
        with self._lock:
            enabled: bool = self._auto
            busy: bool = self._busy
            problem: bool = self._problem
            pausing: bool = self._pausing
            incomplete: bool = self._incomplete
        data.uFlags = 1 | 2 | 4 | 128
        activity: str = "wymaga uwagi" if problem else ("praca trwa" if busy else "czuwanie")
        data.szTip = f"AniShift · {_mode(enabled=enabled, pausing=pausing, incomplete=incomplete)} · {activity}"
        if not notify(operation, data):
            self._retire_balloon(ambiguous=True)
            return
        if operation == 0:
            data.uTimeoutOrVersion = 4
            if not notify(4, data):
                self._ambiguous = True

        def submit(balloon: _Balloon) -> bool:
            if balloon.final:
                data.uFlags = 16
                data.szInfo = ""
                notify(1, data)
            data.uFlags = 16 if balloon.final else 16 | 64
            data.szInfoTitle, data.szInfo = balloon.title[:63], balloon.message[:255]
            data.dwInfoFlags = 4 | 32 | 128
            return notify(1, data)

        self._submit_balloon(submit)

    def _run(self) -> None:
        try:
            with ExitStack() as resources:
                self._message_loop(resources)
        except (OSError, ValueError) as error:
            logger.warning("Windows tray unavailable", error_class=type(error).__name__)
        finally:
            self._reset_balloon()
            self._window = 0
            self._ready.set()

    def _message_loop(self, resources: ExitStack) -> None:  # noqa: PLR0915
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
        user.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user.LoadImageW.restype = wintypes.HICON
        user.DestroyIcon.argtypes = [wintypes.HICON]
        user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.SendMessageW.restype = ctypes.c_ssize_t
        user.DestroyWindow.argtypes = [wintypes.HWND]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = ctypes.c_ssize_t
        user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
        user.SetTimer.restype = ctypes.c_size_t
        user.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        shell.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_NotifyIcon)]
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
        shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self._post = user.PostMessageW
        taskbar_created: int = user.RegisterWindowMessageW("TaskbarCreated")
        data: _NotifyIcon = _NotifyIcon()
        data.cbSize, data.uID = ctypes.sizeof(data), 1
        data.uCallbackMessage = _Message.TRAY
        data.hIcon = _load_mascot_icon(user, resources, user.GetSystemMetrics(49), user.GetSystemMetrics(50))
        data.hBalloonIcon = _load_mascot_icon(user, resources, user.GetSystemMetrics(11), user.GetSystemMetrics(12))

        def update(operation: int) -> None:
            self._update_icon(
                data, operation, lambda mode, value: bool(shell.Shell_NotifyIconW(mode, ctypes.byref(value)))
            )

        def procedure(window: int, message: int, parameter: int, detail: int) -> int:
            if message == taskbar_created:
                self._reset_balloon()
                update(0)
            elif message == _Message.UPDATE:
                update(1)
            elif message == _Message.TRAY:
                self._tray_event(window, detail)
            elif message == _Message.TIMER:
                self._expire_balloon(parameter)
            elif message == _Message.CLOSE:
                self._reset_balloon()
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
        definition.icon = data.hBalloonIcon
        if not user.RegisterClassW(ctypes.byref(definition)):
            raise ctypes.WinError(ctypes.get_last_error())
        window: int = user.CreateWindowExW(0, name, "AniShift", 0, 0, 0, 0, 0, None, None, instance, None)
        if not window:
            user.UnregisterClassW(name, instance)
            raise ctypes.WinError(ctypes.get_last_error())
        self._window, data.hWnd = window, window
        self._arm_timer = lambda identifier: user.SetTimer(window, identifier, int(_BALLOON_EXPIRY_S * 1000), None)
        self._cancel_timer = lambda identifier: user.KillTimer(window, identifier)
        user.SendMessageW(window, 0x0080, 0, data.hIcon)
        user.SendMessageW(window, 0x0080, 1, data.hBalloonIcon)
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
            enabled, items = self._menu_options()
            for identifier, label in items:
                user.AppendMenuW(menu, 0, identifier, label)
            point = wintypes.POINT()
            user.GetCursorPos(ctypes.byref(point))
            user.SetForegroundWindow(window)
            selected: int = user.TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, window, None)
            action: str | None = self._menu_action(selected, enabled=enabled)
            if action is not None:
                self._action(action)
        finally:
            user.DestroyMenu(menu)

    def _menu_options(self) -> tuple[bool, tuple[tuple[int, str], ...]]:
        """Read the flow state once and label every menu item from that single observation."""
        with self._lock:
            enabled: bool = self._auto
        return enabled, (
            (1, "Otwórz AniShift"),
            (2, "Zatrzymaj AniShift" if enabled else "Wznów AniShift"),
            (3, "Zakończ AniShift"),
        )

    def _menu_action(self, selected: int, *, enabled: bool) -> str | None:
        """Name the action of one selection from the observation its label was built from."""
        return {1: "open", 2: "pause" if enabled else "resume", 3: "shutdown"}.get(selected)


def _mode(*, enabled: bool, pausing: bool, incomplete: bool) -> str:
    """Name the four real flow states, including the settling one and a pause that left a transfer working."""
    if enabled:
        return "Praca"
    if pausing:
        return "Zatrzymywanie"
    return "Pauza niepełna" if incomplete else "Wstrzymano"


def _load_mascot_icon(user: ctypes.CDLL, resources: ExitStack, width: int, height: int) -> int:
    if sys.platform != "win32":
        message: str = "Notification icons require Windows"
        raise OSError(message)
    with as_file(files("anishift").joinpath(*_ICON_PARTS)) as path:
        icon: int = user.LoadImageW(None, str(path), 1, width, height, 16)
    if not icon:
        raise ctypes.WinError(ctypes.get_last_error())
    resources.callback(user.DestroyIcon, icon)
    return icon
