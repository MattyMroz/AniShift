from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

import pytest

from anishift.platform import tray as tray_module
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
            user.SendMessageW.restype = ctypes.c_ssize_t
            user.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
            user.LoadIconW.restype = wintypes.HICON
            icon: int = user.SendMessageW(tray._window, 0x007F, 0, 0)
            system_icon: int = user.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))
            assert icon
            assert icon != system_icon
            message: int = user.RegisterWindowMessageW("TaskbarCreated")
            user.SendMessageW(tray._window, message, 0, 0)
            assert calls == []
            user.SendMessageW(tray._window, 0x8001, 0, 0x0202)
        assert opened.wait(5)
        assert calls == ["open"]
        if sys.platform == "win32":
            user.SendMessageW(tray._window, 0x8001, 0, (1 << 16) | 0x0400)
            user.SendMessageW(tray._window, 0x8001, 0, (1 << 16) | 0x0401)
            user.SendMessageW(tray._window, 0x8001, 0, (1 << 16) | 0x0405)
        assert calls == ["open", "open", "open", "open"]
    finally:
        tray.close()
    assert not tray.available


@pytest.mark.parametrize(
    ("enabled", "pausing", "incomplete", "expected"),
    [
        (True, False, False, "Praca"),
        (True, True, False, "Praca"),
        (False, True, False, "Zatrzymywanie"),
        (False, True, True, "Zatrzymywanie"),
        (False, False, False, "Wstrzymano"),
        (False, False, True, "Pauza niepełna"),
    ],
)
def test_the_tray_names_settling_and_an_unfinished_pause_before_it_names_a_full_one(
    enabled: bool, pausing: bool, incomplete: bool, expected: str
) -> None:
    assert tray_module._mode(enabled=enabled, pausing=pausing, incomplete=incomplete) == expected


def test_a_menu_click_acts_on_the_state_its_label_was_built_from() -> None:
    actions: list[str] = []
    tray: TrayIcon = TrayIcon(actions.append)
    try:
        tray.update(auto_enabled=True, busy=False)
        enabled, items = tray._menu_options()
        tray.update(auto_enabled=False, busy=False)
        chosen: str | None = tray._menu_action(2, enabled=enabled)
        reopened: str | None = tray._menu_action(2, enabled=tray._menu_options()[0])
    finally:
        tray.close()

    assert enabled
    assert items == ((1, "Otwórz AniShift"), (2, "Zatrzymaj AniShift"), (3, "Zakończ AniShift"))
    assert chosen == "pause"
    assert reopened == "resume"
    assert actions == []


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows notification area")
def test_an_exit_notification_reaches_the_shell_before_its_icon_is_kept_for_reading_and_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    waits: list[float] = []

    def hold(seconds: float) -> None:
        waits.append(seconds)
        shown.set()
        assert release.wait(5.0)

    monkeypatch.setattr(tray_module, "sleep", hold)
    tray: TrayIcon = TrayIcon(lambda _action: None)
    closing: threading.Thread = threading.Thread(
        target=lambda: tray.close(notification=("AniShift test", "Isolated shutdown notification test")), daemon=True
    )
    try:
        assert tray.available
        closing.start()
        assert shown.wait(5.0)
        assert tray.available
        assert closing.is_alive()
        assert waits == [5.0]
    finally:
        release.set()
        closing.join(5.0)
        tray.close()
    assert not closing.is_alive()
    assert not tray.available
