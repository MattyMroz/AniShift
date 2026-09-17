from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
from collections.abc import Iterator
from ctypes import wintypes
from pathlib import Path
from unittest.mock import Mock

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
        assert calls == ["open", "open", "open", "notification:"]
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


def test_a_menu_click_acts_on_the_state_its_label_was_built_from(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TrayIcon, "_run", lambda self: self._ready.set())
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


@pytest.fixture
def isolated_tray(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TrayIcon, list[str]]]:
    monkeypatch.setattr(TrayIcon, "_run", lambda self: self._ready.set())
    actions: list[str] = []
    tray: TrayIcon = TrayIcon(actions.append)
    tray._window = 1
    tray._arm_timer = lambda _identifier: 1
    tray._cancel_timer = lambda _identifier: 1
    yield tray, actions
    tray._window = 0
    tray.close()


def test_two_queued_balloons_select_their_own_results_after_clean_clicks(
    isolated_tray: tuple[TrayIcon, list[str]],
) -> None:
    tray, actions = isolated_tray
    submitted: list[tray_module._Balloon] = []

    def submit(balloon: tray_module._Balloon) -> bool:
        submitted.append(balloon)
        return True

    tray.notify("One", "first", "id-1")
    tray.notify("Two", "second", "id-2")
    tray._submit_balloon(submit)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._submit_balloon(submit)
    assert [item.notification_id for item in submitted] == ["id-1"]
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    tray._submit_balloon(submit)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert [item.notification_id for item in submitted] == ["id-1", "id-2"]
    assert actions == ["notification:id-1", "notification:id-2"]


@pytest.mark.parametrize("terminal", [tray_module._Message.BALLOON_TIMEOUT, tray_module._Message.BALLOON_HIDE])
def test_obsolete_click_cannot_target_the_next_shown_balloon_or_restore_identity(
    isolated_tray: tuple[TrayIcon, list[str]],
    terminal: int,
) -> None:
    tray, actions = isolated_tray
    tray.notify("One", "first", "id-1")
    tray.notify("Two", "second", "id-2")
    tray._submit_balloon(lambda _balloon: True)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(terminal, 1)
    tray._submit_balloon(lambda _balloon: True)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    tray.notify("Three", "third", "id-3")
    tray._submit_balloon(lambda _balloon: True)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:", "notification:"]


def test_tooltip_update_neither_clears_nor_retargets_an_active_balloon(
    isolated_tray: tuple[TrayIcon, list[str]],
) -> None:
    tray, actions = isolated_tray
    flags: list[int] = []
    data: tray_module._NotifyIcon = tray_module._NotifyIcon()

    def notify(_operation: int, value: tray_module._NotifyIcon) -> bool:
        flags.append(value.uFlags)
        return True

    tray.notify("One", "first", "id-1")
    tray._update_icon(data, 1, notify)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray.notify("Two", "second", "id-2")
    tray.update(auto_enabled=True, busy=True)
    tray._update_icon(data, 1, notify)
    assert len(flags) == 3
    assert flags[1] & 16
    assert not flags[2] & 16
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:id-1"]


@pytest.mark.parametrize("failure", ["submit", "quiet", "timer", "timer_setup"])
def test_failed_balloon_retires_only_itself_and_future_offers_remain_bounded_and_unidentifiable(
    isolated_tray: tuple[TrayIcon, list[str]],
    failure: str,
) -> None:
    tray, actions = isolated_tray
    for index in range(100):
        tray.notify("Ready", str(index), str(index))
    assert len(tray._notifications) == tray_module._MAX_BALLOONS
    if failure == "timer_setup":
        tray._arm_timer = lambda _identifier: 0
    tray._submit_balloon(lambda _balloon: failure != "submit")
    if failure == "quiet":
        tray._balloon_event(tray_module._Message.BALLOON_HIDE, 1)
    if failure == "timer":
        tray._expire_balloon(tray._timer_id)
    assert tray._active is None
    assert len(tray._notifications) == tray_module._MAX_BALLOONS - 1
    for index in range(100):
        tray.notify("Later", str(index), f"later-{index}")
    assert len(tray._notifications) == tray_module._MAX_BALLOONS
    submitted: list[str | None] = []

    def submit(balloon: tray_module._Balloon) -> bool:
        submitted.append(balloon.notification_id)
        return True

    tray._arm_timer = lambda _identifier: 1
    tray._submit_balloon(submit)
    assert submitted == ["later-68"]
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:"]


def test_failed_submissions_drain_each_queued_offer_once_and_leave_no_idle_work(
    isolated_tray: tuple[TrayIcon, list[str]],
) -> None:
    tray, actions = isolated_tray
    updates: list[int] = []
    submitted: list[str] = []
    data: tray_module._NotifyIcon = tray_module._NotifyIcon()
    tray._post = lambda _window, message, _parameter, _detail: updates.append(message)

    def reject_balloon(_operation: int, value: tray_module._NotifyIcon) -> bool:
        if value.uFlags & 16:
            submitted.append(value.szInfoTitle)
            return False
        return True

    tray.notify("One", "first", "id-1")
    tray.notify("Two", "second", "id-2")
    processed: int = 0
    while updates:
        assert updates.pop(0) == tray_module._Message.UPDATE
        tray._update_icon(data, 1, reject_balloon)
        processed += 1
        assert processed <= 4
    assert submitted == ["One", "Two"]
    assert not tray._notifications
    assert tray._active is None
    assert tray._timer_id == 0
    assert not actions


@pytest.mark.parametrize("recreate", [False, True])
def test_tooltip_failure_does_not_disable_future_delivery_or_restore_click_identity(
    isolated_tray: tuple[TrayIcon, list[str]],
    recreate: bool,
) -> None:
    tray, actions = isolated_tray
    data: tray_module._NotifyIcon = tray_module._NotifyIcon()
    offered: list[str] = []

    def notify(_operation: int, value: tray_module._NotifyIcon) -> bool:
        if value.uFlags & 16:
            offered.append(value.szInfoTitle)
        return True

    tray.notify("One", "first", "id-1")
    tray._update_icon(data, 1, notify)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._update_icon(data, 1, lambda _mode, _value: False)
    if recreate:
        tray._reset_balloon()
        tray._update_icon(data, 0, notify)
    tray.notify("Two", "second", "id-2")
    tray._update_icon(data, 1, notify)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert offered == ["One", "Two"]
    assert actions == ["notification:"]


def test_taskbar_reset_drops_pending_delivery_and_permanently_revokes_targeting(
    isolated_tray: tuple[TrayIcon, list[str]],
) -> None:
    tray, actions = isolated_tray
    tray.notify("One", "first", "id-1")
    tray.notify("Two", "second", "id-2")
    tray._submit_balloon(lambda _balloon: True)
    tray._reset_balloon()
    assert not tray._notifications
    tray.notify("Three", "third", "id-3")
    tray._submit_balloon(lambda _balloon: True)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:"]


def test_exit_error_supersedes_pending_balloons_and_keeps_its_bounded_reading_opportunity(
    isolated_tray: tuple[TrayIcon, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray, _actions = isolated_tray
    submitted: list[tuple[str, str]] = []
    waits: list[float] = []
    data: tray_module._NotifyIcon = tray_module._NotifyIcon()

    def submit(_operation: int, value: tray_module._NotifyIcon) -> bool:
        if value.uFlags & 16:
            submitted.append((value.szInfoTitle, value.szInfo))
        return True

    def post(_window: int, message: int, _parameter: int, _detail: int) -> None:
        if message == tray_module._Message.UPDATE:
            tray._update_icon(data, 1, submit)
        elif message == tray_module._Message.CLOSE:
            tray._reset_balloon()

    tray.notify("One", "first", "id-1")
    tray._submit_balloon(lambda _balloon: True)
    tray.notify("Two", "second", "id-2")
    tray._post = post
    monkeypatch.setattr(tray_module, "sleep", waits.append)
    tray.close(notification=("End", "Client remains open"))
    assert submitted == [("", ""), ("End", "Client remains open")]
    assert waits == [tray_module._EXIT_NOTIFICATION_S]
    assert tray._active is None
    assert not tray._notifications


def test_unsupported_tray_does_not_retain_notifications(isolated_tray: tuple[TrayIcon, list[str]]) -> None:
    tray, actions = isolated_tray
    tray._window = 0
    tray.notify("Ready", "first", "id-1")
    assert not tray._notifications
    assert not actions


def test_result_folder_selection_uses_the_shared_desktop_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launch: Mock = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    tray_module.open_path(tmp_path / "ready" / "Episode.pl.mkv", show_folder=True)
    arguments: list[str] = launch.call_args.args[0]
    if sys.platform == "win32":
        assert arguments[1:] == ["/select,", str(tmp_path / "ready" / "Episode.pl.mkv")]
    else:
        assert arguments[1:] == [str(tmp_path / "ready")]


@pytest.mark.parametrize("missing", [False, True])
def test_missing_windows_directory_refuses_explorer_without_falling_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing: bool,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("SYSTEMROOT", "")
    if missing:
        monkeypatch.delenv("SYSTEMROOT")
    launch: Mock = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(OSError, match="Windows system directory is unavailable"):
        tray_module.open_path(tmp_path / "ready" / "Episode.pl.mkv", show_folder=True)
    launch.assert_not_called()


def test_v4_callback_decodes_icon_identity_and_keeps_icon_activation_as_home(
    isolated_tray: tuple[TrayIcon, list[str]],
) -> None:
    tray, actions = isolated_tray
    tray.notify("One", "first", "id-1")
    tray._submit_balloon(lambda _balloon: True)
    for event in (tray_module._Message.SELECT, tray_module._Message.KEY_SELECT, tray_module._Message.LEFT_UP):
        tray._tray_event(1, (1 << 16) | event)
    tray._tray_event(1, (1 << 16) | tray_module._Message.BALLOON_SHOW)
    tray._tray_event(1, (2 << 16) | tray_module._Message.BALLOON_CLICK)
    tray._tray_event(1, (1 << 16) | tray_module._Message.BALLOON_CLICK)
    assert actions == ["open", "open", "open", "notification:", "notification:id-1"]


def test_a_queued_old_timer_cannot_expire_the_next_balloon(isolated_tray: tuple[TrayIcon, list[str]]) -> None:
    tray, actions = isolated_tray
    tray.notify("One", "first", "id-1")
    tray.notify("Two", "second", "id-2")
    tray._submit_balloon(lambda _balloon: True)
    old_timer: int = tray._timer_id
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    tray._submit_balloon(lambda _balloon: True)
    tray._expire_balloon(old_timer)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:id-1", "notification:id-2"]


def test_failed_exit_notification_has_bounded_wait_and_shutdown_revokes_active_clicks(
    isolated_tray: tuple[TrayIcon, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray, actions = isolated_tray
    waits: list[float | None] = []
    sleeps: list[float] = []
    data: tray_module._NotifyIcon = tray_module._NotifyIcon()

    def wait(timeout: float | None = None) -> bool:
        waits.append(timeout)
        return False

    def post(_window: int, message: int, _parameter: int, _detail: int) -> None:
        if message == tray_module._Message.UPDATE:
            tray._update_icon(data, 1, lambda _mode, _value: False)
        elif message == tray_module._Message.CLOSE:
            tray._reset_balloon()

    tray.notify("One", "first", "id-1")
    tray._submit_balloon(lambda _balloon: True)
    tray._balloon_event(tray_module._Message.BALLOON_SHOW, 1)
    tray.close()
    tray._balloon_event(tray_module._Message.BALLOON_CLICK, 1)
    assert actions == ["notification:"]
    tray._post = post
    monkeypatch.setattr(tray._notification_submitted, "wait", wait)
    monkeypatch.setattr(tray_module, "sleep", sleeps.append)
    tray.close(notification=("End", "Client remains open"))
    tray.notify("Later", "ignored", "id-2")
    assert waits == [tray_module._START_TIMEOUT_S]
    assert not sleeps
    assert not tray._notifications
    assert tray._active is None
