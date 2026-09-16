from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, cast

import pytest

import anishift.application as application_module
from anishift.application import AppService, InspectedWorkspace
from anishift.cli import control as cli_control
from anishift.cli import watch as watch_module
from anishift.cli.exit_codes import EXIT_INCOMPLETE, EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.watch import RESIDENT_LOCK_FILE_NAME, run_resident, spawn_resident
from anishift.platform import autostart
from anishift.platform import tray as tray_module
from anishift.platform.autostart import AutostartStatus, resident_command
from anishift.platform.local_control import (
    INSTANCE_FILE_NAME,
    KEY_FILE_NAME,
    ControlClient,
    ControlResponse,
    connect,
    control_endpoint,
    read_instance,
)
from anishift.platform.process_lock import ProcessLock
from anishift.services.torrents.errors import TorrentClientError

_TIMEOUT_S: Final[float] = 15.0
_CLOSE_REFUSED: Final[str] = "The private torrent client did not finish shutting down"

_WATCH_STUCK: Final[str] = "The workspace watcher did not finish closing"

_RESIDENT_SCRIPT: Final[str] = """
import sys, time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from anishift.application import AppService, InspectedWorkspace
from anishift.cli.watch import run_resident


class _Service:
    subscriptions = None
    acquisition = None

    def __init__(self, workspace_root):
        self.workspace_root = workspace_root
        workspace_root.mkdir(parents=True, exist_ok=True)

    def discover(self, *, changed_paths=None):
        return InspectedWorkspace((), ())

    def active_run_ids(self):
        return ()

    def set_background_admission(self, enabled):
        del enabled

    def close(self):
        pass

    def drain(self):
        pass

    def retain_runs(self, run_ids):
        del run_ids


state_dir = Path(sys.argv[1])
ready = Path(sys.argv[2])
code = run_resident(
    cast(AppService, _Service(state_dir / "workspace")),
    state_dir=state_dir,
    on_ready=lambda: ready.write_text("ready", encoding="utf-8"),
)
Path(sys.argv[3]).write_text(str(code), encoding="utf-8")
"""


class _Service:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root: Path = workspace_root
        workspace_root.mkdir(parents=True, exist_ok=True)
        self.subscriptions: None = None
        self.acquisition: None = None
        self.admissions: list[bool] = []

    def discover(self, *, changed_paths: Sequence[Path] | None = None) -> InspectedWorkspace:
        del changed_paths
        return InspectedWorkspace((), ())

    def active_run_ids(self) -> tuple[str, ...]:
        return ()

    def set_background_admission(self, enabled: bool) -> None:
        self.admissions.append(enabled)

    def drain(self) -> None:
        pass

    def retain_runs(self, run_ids: Sequence[str]) -> None:
        del run_ids


def _as_service(service: _Service) -> AppService:
    return cast("AppService", service)


def test_a_second_resident_is_refused_and_records_no_instance(tmp_path: Path) -> None:
    lock: ProcessLock = ProcessLock(tmp_path / RESIDENT_LOCK_FILE_NAME)
    assert lock.acquire()
    try:
        code: int = run_resident(_as_service(_Service(tmp_path / "workspace")), state_dir=tmp_path)
    finally:
        lock.release()

    assert code == EXIT_REFUSED
    assert not (tmp_path / INSTANCE_FILE_NAME).exists()


def test_a_resident_serves_commands_and_stops_on_the_shutdown_command(tmp_path: Path) -> None:
    service = _Service(tmp_path / "workspace")
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(_as_service(service), state_dir=tmp_path, on_ready=ready.set),
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        client: ControlClient | None = connect(tmp_path)
        assert client is not None
        try:
            status = client.call("status")
            client.call("shutdown")
        finally:
            client.close()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        if thread.is_alive():
            stopper: ControlClient | None = connect(tmp_path)
            if stopper is not None:
                stopper.call("shutdown", command_id="stop-fallback")
                stopper.close()
            thread.join(timeout=_TIMEOUT_S)

    assert status["pid"] == os.getpid()
    assert codes == [EXIT_SUCCESS]
    assert not (tmp_path / INSTANCE_FILE_NAME).exists()


def test_a_started_resident_records_itself_and_answers_on_its_endpoint(tmp_path: Path) -> None:
    service = _Service(tmp_path / "workspace")
    ready = threading.Event()
    thread = threading.Thread(
        target=lambda: run_resident(_as_service(service), state_dir=tmp_path, on_ready=ready.set),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        recorded = read_instance(tmp_path)
        reported = cli_control.resident_status(tmp_path)
    finally:
        stopper: ControlClient | None = connect(tmp_path)
        if stopper is not None:
            stopper.call("shutdown")
            stopper.close()
        thread.join(timeout=_TIMEOUT_S)

    assert recorded is not None
    assert recorded.pid == os.getpid()
    assert recorded.endpoint == control_endpoint(tmp_path)
    assert (tmp_path / KEY_FILE_NAME).is_file()
    assert reported == cli_control.ResidentStatus(running=True, pid=os.getpid())


def test_no_resident_answers_before_one_is_started(tmp_path: Path) -> None:
    assert cli_control.resident_status(tmp_path) == cli_control.ResidentStatus(running=False, pid=None)


@pytest.mark.integration
def test_two_racing_residents_leave_exactly_one_owner(tmp_path: Path) -> None:
    state_dir: Path = tmp_path / "watch"
    state_dir.mkdir()
    environment: dict[str, str] = {
        **os.environ,
        "ANISHIFT_CONFIG_DIR": str(tmp_path / "config"),
        "ANISHIFT_WORKSPACE_ROOT": str(tmp_path / "workspace"),
    }
    children: list[subprocess.Popen[str]] = [
        subprocess.Popen(  # noqa: S603 - fixed probe on this interpreter
            [
                sys.executable,
                "-c",
                _RESIDENT_SCRIPT,
                str(state_dir),
                str(tmp_path / f"ready-{index}"),
                str(tmp_path / f"code-{index}"),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(2)
    ]
    try:
        owner_client: ControlClient | None = _awaited_client(state_dir)
        assert owner_client is not None
        try:
            owner_client.call("status")
            ready_indices: list[int] = [index for index in range(2) if (tmp_path / f"ready-{index}").is_file()]
            assert len(ready_indices) == 1
            loser_index: int = 1 - ready_indices[0]
            stdout: str
            stderr: str
            stdout, stderr = children[loser_index].communicate(timeout=30)
            assert children[loser_index].returncode == 0, (stdout, stderr)
            assert int((tmp_path / f"code-{loser_index}").read_text(encoding="utf-8")) == EXIT_REFUSED
            owner_client.call("shutdown")
        finally:
            owner_client.close()
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, (stdout, stderr)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)

    codes: list[int] = [int((tmp_path / f"code-{index}").read_text(encoding="utf-8")) for index in range(2)]
    assert sorted(codes) == sorted((EXIT_SUCCESS, EXIT_REFUSED))
    assert not (state_dir / INSTANCE_FILE_NAME).exists()


def test_the_resident_argv_uses_the_windowless_interpreter() -> None:
    launcher: Path = Path(sys.executable).with_name("pythonw.exe")
    if not launcher.is_file():
        pytest.skip("this interpreter ships no windowless launcher")

    argv: list[str] = resident_command()

    assert argv == [str(launcher), "-m", "anishift.cli.main", "watch", "resident"]


def test_spawning_a_resident_detaches_it_from_this_process(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    def popen(command: object, **options: Any) -> object:
        recorded["command"] = command
        recorded.update(options)
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr("anishift.cli.watch.subprocess.Popen", popen)
    monkeypatch.setattr("anishift.platform.autostart.resident_command", lambda: ["python", "-m", "anishift.cli.main"])

    spawn_resident()

    assert recorded["stdin"] == subprocess.DEVNULL
    assert recorded["stdout"] == subprocess.DEVNULL
    assert recorded["stderr"] == subprocess.DEVNULL
    if sys.platform == "win32":
        assert recorded["creationflags"] == subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    else:
        assert recorded["start_new_session"] is True


def _awaited_client(state_dir: Path) -> ControlClient | None:
    deadline: float = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        client: ControlClient | None = connect(state_dir)
        if client is not None:
            return client
        time.sleep(0.05)
    return None


class _Acquisition:
    def __init__(self, *, refusing: bool = False) -> None:
        self.events: list[str] = []
        self.request_control: None = None
        self.refusing: bool = refusing

    def prepare_client(self) -> None:
        self.events.append("prepare")

    def close_client(self) -> None:
        self.events.append("close_client")
        if self.refusing:
            raise TorrentClientError(_CLOSE_REFUSED)

    def close(self) -> None:
        self.events.append("close")


class _ClientService(_Service):
    def __init__(self, workspace_root: Path, acquisition: _Acquisition) -> None:
        super().__init__(workspace_root)
        self.acquisition: Any = acquisition

    def pause_runs(self) -> None:
        pass

    def resume_runs(self) -> None:
        pass


def test_three_panels_share_one_client_and_closing_one_leaves_the_resident_until_a_full_end(tmp_path: Path) -> None:
    acquisition = _Acquisition()
    service = _ClientService(tmp_path / "workspace", acquisition)
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(_as_service(cast("_Service", service)), state_dir=tmp_path, on_ready=ready.set)
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        client: ControlClient | None = connect(tmp_path)
        assert client is not None
        try:
            _assert_shared_panels(client, tmp_path)
            assert thread.is_alive()
            client.call("shutdown")
        finally:
            client.close()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        if thread.is_alive():
            stopper: ControlClient | None = connect(tmp_path)
            if stopper is not None:
                stopper.call("shutdown", command_id="stop-fallback")
                stopper.close()
            thread.join(timeout=_TIMEOUT_S)

    assert not thread.is_alive()
    assert codes == [EXIT_SUCCESS]
    assert acquisition.events == ["prepare", "close_client", "close"]
    assert not (tmp_path / INSTANCE_FILE_NAME).exists()


def _assert_shared_panels(first: ControlClient, state_dir: Path) -> None:
    with ExitStack() as stack:
        second: ControlClient | None = connect(state_dir)
        assert second is not None
        stack.callback(second.close)
        third: ControlClient | None = connect(state_dir)
        assert third is not None
        stack.callback(third.close)
        identity: object = first.call("status")["instance_id"]
        assert second.call("status")["instance_id"] == identity
        assert third.call("status")["instance_id"] == identity
        second.close()
        assert third.call("status")["shutting_down"] is False


@pytest.mark.parametrize(
    ("reported", "registrations"),
    [(AutostartStatus.MISSING, 1), (AutostartStatus.DISABLED, 0), (AutostartStatus.ENABLED, 0)],
)
def test_only_a_missing_logon_task_is_registered_when_the_resident_starts(
    monkeypatch: pytest.MonkeyPatch, reported: AutostartStatus, registrations: int
) -> None:
    registered: list[Sequence[str]] = []
    monkeypatch.setattr(autostart, "status", lambda **_options: reported)
    monkeypatch.setattr(autostart, "register", lambda command, **_options: registered.append(command))
    monkeypatch.setattr(autostart, "watch_command", lambda: ["pythonw.exe", "-m", "anishift.cli.main", "watch"])

    watch_module._ensure_autostart()

    assert len(registered) == registrations


def test_an_unavailable_task_scheduler_never_stops_the_resident_from_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**_options: object) -> AutostartStatus:
        raise autostart.AutostartUnsupportedError

    monkeypatch.setattr(autostart, "status", refuse)

    watch_module._ensure_autostart()


class _Tray:
    def __init__(self, action: Callable[[str], None]) -> None:
        self.action: Callable[[str], None] = action
        self.states: list[tuple[bool, bool]] = []
        self.busy_states: list[bool] = []
        self.incomplete_states: list[bool] = []
        self.notifications: list[tuple[str, str]] = []
        self.closed: int = 0

    @property
    def available(self) -> bool:
        return True

    def update(
        self,
        *,
        auto_enabled: bool,
        busy: bool,
        problem: bool = False,
        pausing: bool = False,
        incomplete: bool = False,
    ) -> None:
        del problem
        self.busy_states.append(busy)
        self.states.append((auto_enabled, pausing))
        self.incomplete_states.append(incomplete)

    def notify(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def close(self, *, notification: tuple[str, str] | None = None) -> None:
        if notification is not None:
            self.notifications.append(notification)
        self.closed += 1


class _RunningService(_ClientService):
    def __init__(self, workspace_root: Path, acquisition: _Acquisition) -> None:
        super().__init__(workspace_root, acquisition)
        self.running: bool = True

    def active_run_ids(self) -> tuple[str, ...]:
        return ("run-1",) if self.running else ()


def test_the_tray_shows_settling_until_the_started_work_reaches_its_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _RunningService(tmp_path / "workspace", _Acquisition())
    trays: list[_Tray] = []
    monkeypatch.setattr(watch_module, "contain_children", lambda: None)
    monkeypatch.setattr(autostart, "status", lambda **_options: AutostartStatus.ENABLED)
    monkeypatch.setattr(tray_module, "TrayIcon", _recording_tray(trays))
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(
                _as_service(cast("_Service", service)),
                state_dir=tmp_path,
                on_ready=ready.set,
                enable_tray=True,
            )
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        client: ControlClient | None = connect(tmp_path)
        assert client is not None
        try:
            client.call("set_auto", {"enabled": False}, command_id="pause-1")
            settling: list[tuple[bool, bool]] = list(trays[0].states)
            service.running = False
            client.call("set_auto", {"enabled": True}, command_id="resume-1")
            client.call("set_auto", {"enabled": False}, command_id="pause-2")
            client.call("shutdown", command_id="end-1")
        finally:
            client.close()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        if thread.is_alive():
            stopper: ControlClient | None = connect(tmp_path)
            if stopper is not None:
                service.running = False
                stopper.call("shutdown", command_id="stop-fallback")
                stopper.close()
            thread.join(timeout=_TIMEOUT_S)

    assert codes == [EXIT_SUCCESS]
    assert (False, True) in settling
    assert (False, False) not in settling
    assert trays[0].states[-1] == (False, False)
    assert trays[0].closed == 1


def _recording_tray(trays: list[_Tray]) -> Callable[[Callable[[str], None]], _Tray]:
    def build(action: Callable[[str], None]) -> _Tray:
        tray = _Tray(action)
        trays.append(tray)
        return tray

    return build


class _CapturedOwner:
    def __init__(self, service: AppService, store: object, **_options: object) -> None:
        del service, store
        self.broadcasts: list[Callable[[Mapping[str, object], bool], None]] = []
        self.finished: threading.Event = threading.Event()

    def attach_broadcast(self, broadcast: Callable[[Mapping[str, object], bool], None]) -> None:
        self.broadcasts.append(broadcast)

    def files_changed(self, change: object) -> None:
        del change

    def handle(self, request: object) -> ControlResponse:
        del request
        return ControlResponse.succeeded({})

    def disconnect(self, client_id: str) -> None:
        del client_id

    def tray_action(self, action: str) -> None:
        del action

    def request_shutdown(self) -> None:
        self.finished.set()

    def serve(self) -> None:
        self.finished.wait(_TIMEOUT_S)


def _recording_owner(owners: list[_CapturedOwner]) -> Callable[..., _CapturedOwner]:
    def build(service: AppService, store: object, **options: object) -> _CapturedOwner:
        owner = _CapturedOwner(service, store, **options)
        owners.append(owner)
        return owner

    return build


def _state_frame(request_state: str) -> dict[str, object]:
    return {
        "event": "state_changed",
        "payload": {
            "auto_enabled": request_state == "running",
            "requests": [
                {
                    "request_id": "request-1",
                    "origin": "user",
                    "source_selection": "auto",
                    "state": request_state,
                    "group_ids": ["episode-01"],
                }
            ],
        },
    }


def test_the_tray_reports_no_work_for_a_request_that_only_waits_for_the_pause_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _ClientService(tmp_path / "workspace", _Acquisition())
    owners: list[_CapturedOwner] = []
    trays: list[_Tray] = []
    monkeypatch.setattr(watch_module, "contain_children", lambda: None)
    monkeypatch.setattr(application_module, "AutomationOwner", _recording_owner(owners))
    monkeypatch.setattr(autostart, "status", lambda **_options: AutostartStatus.ENABLED)
    monkeypatch.setattr(tray_module, "TrayIcon", _recording_tray(trays))
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(_as_service(service), state_dir=tmp_path, on_ready=ready.set, enable_tray=True)
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        broadcast: Callable[[Mapping[str, object], bool], None] = owners[0].broadcasts[0]
        broadcast(_state_frame("paused"), False)
        broadcast(_state_frame("running"), False)
    finally:
        owners[0].request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert codes == [EXIT_SUCCESS]
    assert trays[0].busy_states == [False, True]


@pytest.mark.parametrize(
    ("refusing", "expected"),
    [(False, (1, EXIT_SUCCESS, 0)), (True, (3, EXIT_INCOMPLETE, 1))],
)
def test_a_private_client_that_will_not_close_is_retried_and_then_reported_by_the_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusing: bool, expected: tuple[int, int, int]
) -> None:
    attempts, code, notifications = expected
    monkeypatch.setattr(watch_module, "contain_children", lambda: None)
    monkeypatch.setattr(watch_module, "_CLOSE_RETRY_S", 0.0)
    monkeypatch.setattr(autostart, "status", lambda **_options: AutostartStatus.ENABLED)
    trays: list[_Tray] = []
    monkeypatch.setattr(tray_module, "TrayIcon", _recording_tray(trays))
    acquisition = _Acquisition(refusing=refusing)
    service = _ClientService(tmp_path / "workspace", acquisition)
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(_as_service(service), state_dir=tmp_path, on_ready=ready.set, enable_tray=True)
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        client: ControlClient | None = connect(tmp_path)
        assert client is not None
        try:
            client.call("shutdown", command_id="end-1")
        finally:
            client.close()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        if thread.is_alive():
            stopper: ControlClient | None = connect(tmp_path)
            if stopper is not None:
                stopper.call("shutdown", command_id="stop-fallback")
                stopper.close()
            thread.join(timeout=_TIMEOUT_S)

    assert not thread.is_alive()
    assert codes == [code]
    assert acquisition.events.count("close_client") == attempts
    assert acquisition.events[-1] == "close"
    assert len(trays[0].notifications) == notifications
    assert trays[0].closed == 1
    assert not (tmp_path / INSTANCE_FILE_NAME).exists()


class _FailingWatch:
    def __init__(self, root: Path, on_change: Callable[[object], None]) -> None:
        del root, on_change
        self.mode: str = "native"
        self.closes: int = 0

    def close(self) -> None:
        self.closes += 1
        raise TimeoutError(_WATCH_STUCK)


def test_a_watcher_that_will_not_close_still_lets_the_end_release_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watches: list[_FailingWatch] = []

    def build(root: Path, on_change: Callable[[object], None]) -> _FailingWatch:
        watch = _FailingWatch(root, on_change)
        watches.append(watch)
        return watch

    monkeypatch.setattr(watch_module, "contain_children", lambda: None)
    monkeypatch.setattr(autostart, "status", lambda **_options: AutostartStatus.ENABLED)
    monkeypatch.setattr(watch_module, "DirectoryWatch", build)
    trays: list[_Tray] = []
    monkeypatch.setattr(tray_module, "TrayIcon", _recording_tray(trays))
    acquisition = _Acquisition()
    service = _ClientService(tmp_path / "workspace", acquisition)
    ready = threading.Event()
    codes: list[int] = []
    thread = threading.Thread(
        target=lambda: codes.append(
            run_resident(_as_service(service), state_dir=tmp_path, on_ready=ready.set, enable_tray=True)
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert ready.wait(timeout=_TIMEOUT_S)
        client: ControlClient | None = connect(tmp_path)
        assert client is not None
        try:
            client.call("shutdown", command_id="end-1")
        finally:
            client.close()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        if thread.is_alive():
            stopper: ControlClient | None = connect(tmp_path)
            if stopper is not None:
                stopper.call("shutdown", command_id="stop-fallback")
                stopper.close()
            thread.join(timeout=_TIMEOUT_S)

    assert not thread.is_alive()
    assert codes == [EXIT_INCOMPLETE]
    assert watches[0].closes == 1
    assert acquisition.events == ["prepare", "close_client", "close"]
    assert trays[0].closed == 1
    assert not (tmp_path / INSTANCE_FILE_NAME).exists()
    assert connect(tmp_path) is None
