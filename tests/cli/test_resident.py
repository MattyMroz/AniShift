from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, cast

import pytest

from anishift.application import AppService, InspectedWorkspace
from anishift.cli import control as cli_control
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.watch import RESIDENT_LOCK_FILE_NAME, run_resident, spawn_resident
from anishift.platform.autostart import resident_command
from anishift.platform.local_control import (
    INSTANCE_FILE_NAME,
    KEY_FILE_NAME,
    ControlClient,
    connect,
    control_endpoint,
    read_instance,
)
from anishift.platform.process_lock import ProcessLock

_TIMEOUT_S: Final[float] = 15.0

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
        owner_client.call("shutdown")
        owner_client.close()
        for child in children:
            child.wait(timeout=30)
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
