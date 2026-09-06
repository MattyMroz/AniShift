from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, cast

import pytest

from anishift.application import AppService
from anishift.cli import watch as cli_watch
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.watch import (
    ERROR_BACKOFF_S,
    LOCK_FILE_NAME,
    PID_FILE_NAME,
    STOP_FILE_NAME,
    WatchStatus,
    batch_command,
    request_stop,
    run_daemon,
    spawn_window,
    watch_state_dir,
    watch_status,
)
from anishift.errors import ExecutionError
from anishift.platform.process_lock import ProcessLock

_SCAN_INTERVAL: Final[float] = 5.0

_PRESET_ID: Final[str] = "default"


class _Ledger:
    def __init__(self, scripted: list[tuple[str, ...]]) -> None:
        self.scripted: list[tuple[str, ...]] = scripted
        self.started: list[tuple[str, ...]] = []
        self.exits: list[tuple[tuple[str, ...], int]] = []
        self.scans: list[float] = []

    def candidates(self, workspace: object, preset: object, now: float) -> tuple[str, ...]:
        del workspace, preset
        self.scans.append(now)
        return self.scripted.pop(0) if self.scripted else ()

    def mark_started(self, group_ids: Sequence[str]) -> None:
        self.started.append(tuple(group_ids))

    def record_exit(self, group_ids: Sequence[str], exit_code: int) -> None:
        self.exits.append((tuple(group_ids), exit_code))


class _Child:
    def __init__(self, polls: list[int | None]) -> None:
        self.polls: list[int | None] = polls

    def poll(self) -> int | None:
        return self.polls.pop(0) if self.polls else 0


class _Spawner:
    def __init__(self, *children: _Child) -> None:
        self.children: list[_Child] = list(children)
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> _Child:
        self.commands.append(list(command))
        return self.children.pop(0) if self.children else _Child([])


class _Sleeper:
    def __init__(self, state_dir: Path, stop_after: int) -> None:
        self.state_dir: Path = state_dir
        self.stop_after: int = stop_after
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)
        if len(self.durations) >= self.stop_after:
            (self.state_dir / STOP_FILE_NAME).touch()


class _Clock:
    def __init__(self) -> None:
        self.now: float = 100.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


class _Subscriptions:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure: Exception | None = failure
        self.checks: int = 0

    def check_all(self) -> tuple[SimpleNamespace, ...]:
        self.checks += 1
        if self.failure is not None:
            raise self.failure
        return (SimpleNamespace(downloaded=2, problem=""),)


class _Service:
    def __init__(self, failure: Exception | None = None, subscriptions: _Subscriptions | None = None) -> None:
        self.subscriptions: _Subscriptions | None = subscriptions
        self.failure: Exception | None = failure
        self.discoveries: int = 0

    def discover(self) -> object:
        self.discoveries += 1
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(groups=())

    def default_preset_id(self) -> str:
        return _PRESET_ID

    def get_preset(self, preset_id: str) -> object:
        del preset_id
        return SimpleNamespace(products=SimpleNamespace(requested_products=()))


class _PopenRecorder:
    def __init__(self) -> None:
        self.command: list[str] = []
        self.creationflags: int | None = None

    def __call__(self, command: Sequence[str], **options: Any) -> object:
        self.command = list(command)
        self.creationflags = options.get("creationflags")
        return SimpleNamespace(poll=lambda: None)


def _as_service(service: _Service) -> AppService:
    return cast("AppService", service)


def _install_ledger(monkeypatch: pytest.MonkeyPatch, ledger: _Ledger) -> None:
    monkeypatch.setattr(cli_watch, "WatchLedger", lambda: ledger)


def test_a_scan_without_candidates_opens_no_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger: _Ledger = _Ledger([()])
    _install_ledger(monkeypatch, ledger)
    spawner: _Spawner = _Spawner()
    service: _Service = _Service()

    code: int = run_daemon(
        _as_service(service),
        state_dir=tmp_path,
        spawner=spawner,
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 1),
    )

    assert code == EXIT_SUCCESS
    assert spawner.commands == []
    assert ledger.started == []


def test_candidates_open_exactly_one_batch_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger: _Ledger = _Ledger([("a", "b")])
    _install_ledger(monkeypatch, ledger)
    spawner: _Spawner = _Spawner(_Child([None]))

    run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=spawner,
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 1),
    )

    assert spawner.commands == [batch_command(("a", "b"))]
    assert ledger.started == [("a", "b")]


def test_a_live_window_blocks_the_next_scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger: _Ledger = _Ledger([("a",), ("b",)])
    _install_ledger(monkeypatch, ledger)
    spawner: _Spawner = _Spawner(_Child([None, None]))
    service: _Service = _Service()

    run_daemon(
        _as_service(service),
        state_dir=tmp_path,
        spawner=spawner,
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 2),
    )

    assert len(spawner.commands) == 1
    assert service.discoveries == 1


def test_a_finished_window_records_its_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger: _Ledger = _Ledger([("a",)])
    _install_ledger(monkeypatch, ledger)
    spawner: _Spawner = _Spawner(_Child([3]))

    run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=spawner,
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 2),
    )

    assert ledger.exits == [(("a",), 3)]
    assert len(spawner.commands) == 1


def test_a_stop_request_ends_the_loop_and_clears_the_state_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_ledger(monkeypatch, _Ledger([]))

    code: int = run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 1),
    )

    assert code == EXIT_SUCCESS
    assert not (tmp_path / STOP_FILE_NAME).exists()
    assert not (tmp_path / PID_FILE_NAME).exists()


def test_a_stop_left_by_a_previous_run_does_not_end_the_new_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ledger: _Ledger = _Ledger([("a",)])
    _install_ledger(monkeypatch, ledger)
    (tmp_path / STOP_FILE_NAME).touch()
    spawner: _Spawner = _Spawner(_Child([None]))

    run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=spawner,
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 1),
    )

    assert len(spawner.commands) == 1


def test_a_second_daemon_refuses_while_the_first_holds_the_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_ledger(monkeypatch, _Ledger([]))
    holder: ProcessLock = ProcessLock(tmp_path / LOCK_FILE_NAME)
    assert holder.acquire() is True

    try:
        code: int = run_daemon(
            _as_service(_Service()),
            state_dir=tmp_path,
            spawner=_Spawner(),
            clock=_Clock(),
            sleep=_Sleeper(tmp_path, 1),
        )
    finally:
        holder.release()

    assert code == EXIT_REFUSED


def test_a_failing_scan_backs_off_and_keeps_watching(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_ledger(monkeypatch, _Ledger([]))
    service: _Service = _Service(ExecutionError("mkvmerge is unavailable"))
    sleeper: _Sleeper = _Sleeper(tmp_path, 2)

    code: int = run_daemon(
        _as_service(service),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=sleeper,
    )

    assert code == EXIT_SUCCESS
    assert sleeper.durations == [ERROR_BACKOFF_S, ERROR_BACKOFF_S]
    assert service.discoveries == 2


def test_an_idle_loop_waits_one_scan_interval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_ledger(monkeypatch, _Ledger([]))
    sleeper: _Sleeper = _Sleeper(tmp_path, 1)

    run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=sleeper,
    )

    assert sleeper.durations == [_SCAN_INTERVAL]


def test_watch_status_reports_a_stopped_watch(tmp_path: Path) -> None:
    assert watch_status(tmp_path) == WatchStatus(running=False, pid=None)


def test_watch_status_reports_the_pid_of_a_running_watch(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / LOCK_FILE_NAME)
    lock.acquire()
    (tmp_path / PID_FILE_NAME).write_text("4321", encoding="utf-8")

    try:
        state: WatchStatus = watch_status(tmp_path)
    finally:
        lock.release()

    assert state == WatchStatus(running=True, pid=4321)


def test_watch_status_reports_a_running_watch_without_a_readable_pid(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / LOCK_FILE_NAME)
    lock.acquire()

    try:
        state: WatchStatus = watch_status(tmp_path)
    finally:
        lock.release()

    assert state == WatchStatus(running=True, pid=None)


def test_request_stop_creates_the_flag_under_a_missing_directory(tmp_path: Path) -> None:
    state_dir: Path = tmp_path / "watch"

    request_stop(state_dir)

    assert (state_dir / STOP_FILE_NAME).is_file()


def test_watch_state_dir_sits_beside_the_panel_preferences() -> None:
    assert watch_state_dir().name == "watch"
    assert watch_state_dir().parent.name == "config"


def test_batch_command_prefers_the_installed_console_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "anishift.exe").write_bytes(b"binary")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    assert batch_command(["a", "b"]) == [str(tmp_path / "anishift.exe"), "watch", "batch", "a", "b"]


def test_batch_command_falls_back_to_the_module_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    interpreter: str = str(tmp_path / "python.exe")
    monkeypatch.setattr(sys, "executable", interpreter)

    assert batch_command(["a"]) == [interpreter, "-m", "anishift.cli.main", "watch", "batch", "a"]


def test_spawn_window_opens_its_own_console_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder: _PopenRecorder = _PopenRecorder()
    monkeypatch.setattr(subprocess, "Popen", recorder)

    spawn_window(["anishift.exe", "watch", "batch", "a"])

    assert recorder.command == ["anishift.exe", "watch", "batch", "a"]
    if sys.platform != "win32":
        assert recorder.creationflags is None
        return
    assert recorder.creationflags == subprocess.CREATE_NEW_CONSOLE


def test_subscriptions_are_checked_at_start_and_again_after_the_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_ledger(monkeypatch, _Ledger([(), (), ()]))
    subscriptions: _Subscriptions = _Subscriptions()
    monkeypatch.setattr(cli_watch, "SUBSCRIPTION_CHECK_INTERVAL_S", 3.0)

    run_daemon(
        _as_service(_Service(subscriptions=subscriptions)),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 3),
    )

    assert subscriptions.checks == 2


def test_a_failing_subscription_check_keeps_the_watch_alive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_ledger(monkeypatch, _Ledger([(), ()]))
    subscriptions: _Subscriptions = _Subscriptions(ExecutionError("index down"))

    code: int = run_daemon(
        _as_service(_Service(subscriptions=subscriptions)),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 2),
    )

    assert code == EXIT_SUCCESS
    assert subscriptions.checks == 1


def test_a_service_without_subscriptions_skips_the_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_ledger(monkeypatch, _Ledger([()]))

    code: int = run_daemon(
        _as_service(_Service()),
        state_dir=tmp_path,
        spawner=_Spawner(),
        clock=_Clock(),
        sleep=_Sleeper(tmp_path, 1),
    )

    assert code == EXIT_SUCCESS
