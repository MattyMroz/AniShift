from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

import pytest

from anishift.platform.tray import TrayIcon


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows notification area")
def test_tray_recreates_its_icon_without_starting_work_and_removes_its_window() -> None:
    calls: list[str] = []
    opened: threading.Event = threading.Event()

    def action(value: str) -> None:
        calls.append(value)
        opened.set()

    tray: TrayIcon = TrayIcon(action)
    try:
        assert tray.available
        tray.update(auto_enabled=True, busy=True)
        if sys.platform == "win32":
            user = ctypes.WinDLL("user32")
            user.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
            user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            message: int = user.RegisterWindowMessageW("TaskbarCreated")
            user.SendMessageW(tray._window, message, 0, 0)
            assert calls == []
            user.SendMessageW(tray._window, 0x8001, 0, 0x0202)
        assert opened.wait(5)
        assert calls == ["open"]
    finally:
        tray.close()
    assert not tray.available
