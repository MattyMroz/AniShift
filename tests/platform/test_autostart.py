from __future__ import annotations

import getpass
import subprocess
import sys
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import pytest

from anishift.cli import watch as watch_module
from anishift.errors import ErrorCode
from anishift.platform import autostart
from anishift.platform.autostart import (
    TASK_NAME,
    AutostartError,
    AutostartStatus,
    AutostartUnsupportedError,
)

_WATCH_ARGV: Final[tuple[str, ...]] = ("C:\\envs\\my env\\Scripts\\pythonw.exe", "-m", "anishift.cli.main", "watch")

_MISSING_TASK_STDERR: Final[str] = "ERROR: Nie można odnaleźć określonego pliku.\n"

_DEFINITION: Final[str] = (
    '<?xml version="1.0" encoding="UTF-16"?>\n'
    '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
    "<Settings>{settings}</Settings></Task>\n"
)


class _Runner:
    def __init__(self, *results: subprocess.CompletedProcess[str]) -> None:
        self.results: list[subprocess.CompletedProcess[str]] = list(results)
        self.calls: list[list[str]] = []
        self.definitions: list[str] = []

    def __call__(self, command: Sequence[str], **_options: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(command))
        if "/Create" in command:
            self.definitions.append(Path(command[command.index("/XML") + 1]).read_text(encoding="utf-16"))
        if self.results:
            return self.results.pop(0)
        return _completed(0)


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["schtasks"], returncode=returncode, stdout=stdout, stderr=stderr)


def _definition(enabled: str | None) -> str:
    settings: str = "" if enabled is None else f"<Enabled>{enabled}</Enabled>"
    return _DEFINITION.format(settings=settings)


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "is_windows", lambda: True)


@pytest.fixture
def off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "is_windows", lambda: False)


@pytest.mark.usefixtures("on_windows")
def test_enable_registers_the_logon_task_from_a_definition_then_starts_it() -> None:
    runner: _Runner = _Runner()

    autostart.enable(_WATCH_ARGV, run=runner)

    assert [call[:4] for call in runner.calls] == [
        ["schtasks", "/Create", "/F", "/XML"],
        ["schtasks", "/Run", "/TN", TASK_NAME],
    ]
    assert runner.calls[0][5:] == ["/TN", TASK_NAME]
    assert not Path(runner.calls[0][4]).exists()
    assert "<Command>C:\\envs\\my env\\Scripts\\pythonw.exe</Command>" in runner.definitions[0]
    assert "<Arguments>-m anishift.cli.main watch</Arguments>" in runner.definitions[0]
    assert "<LogonType>InteractiveToken</LogonType>" in runner.definitions[0]
    assert "<RunLevel>LeastPrivilege</RunLevel>" in runner.definitions[0]


@pytest.mark.usefixtures("on_windows")
def test_enable_quotes_only_the_arguments_holding_a_space() -> None:
    runner: _Runner = _Runner()

    autostart.enable(["python.exe", "--root", "C:\\my lib", "watch"], run=runner)

    assert '<Arguments>--root "C:\\my lib" watch</Arguments>' in runner.definitions[0]


@pytest.mark.usefixtures("on_windows")
def test_enable_registers_the_task_for_the_current_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERDOMAIN", "DESKTOP")
    monkeypatch.setattr(getpass, "getuser", lambda: "matty")
    runner: _Runner = _Runner()

    autostart.enable(_WATCH_ARGV, run=runner)

    assert runner.definitions[0].count("<UserId>DESKTOP\\matty</UserId>") == 2


@pytest.mark.usefixtures("on_windows")
def test_enable_reports_a_refusing_scheduler_without_its_full_stderr() -> None:
    runner: _Runner = _Runner(_completed(1, stderr="ERROR: Odmowa dostępu.\nsecond line\n"))

    with pytest.raises(AutostartError) as failure:
        autostart.enable(_WATCH_ARGV, run=runner)

    assert failure.value.context.code is ErrorCode.AUTOSTART_FAILED
    assert failure.value.context.suggestion == "ERROR: Odmowa dostępu."
    assert "second line" not in str(failure.value)


@pytest.mark.usefixtures("on_windows")
def test_enable_does_not_start_a_task_it_could_not_register() -> None:
    runner: _Runner = _Runner(_completed(1, stderr="ERROR: Odmowa dostępu.\n"))

    with pytest.raises(AutostartError):
        autostart.enable(_WATCH_ARGV, run=runner)

    assert len(runner.calls) == 1
    assert not Path(runner.calls[0][4]).exists()


@pytest.mark.usefixtures("on_windows")
def test_disable_switches_the_task_off_instead_of_removing_it() -> None:
    runner: _Runner = _Runner()

    autostart.disable(run=runner)

    assert runner.calls == [["schtasks", "/Change", "/TN", TASK_NAME, "/DISABLE"]]


@pytest.mark.usefixtures("on_windows")
def test_disable_creates_a_missing_task_disabled_without_running_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "watch_command", lambda: list(_WATCH_ARGV))
    runner: _Runner = _Runner(_completed(1, stderr=_MISSING_TASK_STDERR), _completed(1, stderr=_MISSING_TASK_STDERR))

    autostart.disable(run=runner)

    assert [call[1] for call in runner.calls] == ["/Change", "/Query", "/Create"]
    assert "<Enabled>false</Enabled>" in runner.definitions[0]
    assert not Path(runner.calls[-1][4]).exists()


@pytest.mark.usefixtures("on_windows")
def test_disable_reports_an_unavailable_scheduler_instead_of_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "watch_command", lambda: list(_WATCH_ARGV))
    runner: _Runner = _Runner(*(_completed(1, stderr="Scheduler unavailable") for _ in range(3)))

    with pytest.raises(AutostartError):
        autostart.disable(run=runner)

    assert [call[1] for call in runner.calls] == ["/Change", "/Query", "/Create"]
    assert not Path(runner.calls[-1][4]).exists()


@pytest.mark.usefixtures("on_windows")
def test_disable_reports_a_refusal_for_a_task_that_still_exists() -> None:
    runner: _Runner = _Runner(
        _completed(1, stderr="ERROR: Odmowa dostępu.\n"),
        _completed(0, stdout=_definition("true")),
    )

    with pytest.raises(AutostartError, match="disable"):
        autostart.disable(run=runner)


@pytest.mark.usefixtures("on_windows")
@pytest.mark.parametrize(
    ("enabled", "expected"),
    [
        ("true", AutostartStatus.ENABLED),
        ("false", AutostartStatus.DISABLED),
        (None, AutostartStatus.ENABLED),
    ],
)
def test_status_reads_the_enabled_flag_of_the_exported_definition(
    enabled: str | None,
    expected: AutostartStatus,
) -> None:
    runner: _Runner = _Runner(_completed(0, stdout=_definition(enabled)))

    assert autostart.status(run=runner) is expected
    assert runner.calls == [["schtasks", "/Query", "/TN", TASK_NAME, "/XML"]]


@pytest.mark.usefixtures("on_windows")
def test_status_reports_a_task_the_scheduler_does_not_hold() -> None:
    runner: _Runner = _Runner(_completed(1, stderr=_MISSING_TASK_STDERR))

    assert autostart.status(run=runner) is AutostartStatus.MISSING


@pytest.mark.usefixtures("on_windows")
def test_status_reports_missing_when_the_export_is_not_a_definition() -> None:
    runner: _Runner = _Runner(_completed(0, stdout="\n"))

    assert autostart.status(run=runner) is AutostartStatus.MISSING


@pytest.mark.usefixtures("off_windows")
@pytest.mark.parametrize(
    "ask_scheduler",
    [
        lambda runner: autostart.enable(_WATCH_ARGV, run=runner),
        lambda runner: autostart.disable(run=runner),
        lambda runner: autostart.status(run=runner),
    ],
)
def test_the_scheduler_is_refused_outside_windows(ask_scheduler: Callable[[_Runner], object]) -> None:
    runner: _Runner = _Runner()

    with pytest.raises(AutostartUnsupportedError) as failure:
        ask_scheduler(runner)

    assert failure.value.context.code is ErrorCode.AUTOSTART_UNSUPPORTED
    assert runner.calls == []


def test_watch_command_points_at_the_windowless_interpreter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "pythonw.exe").write_bytes(b"binary")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    assert autostart.watch_command() == [str(tmp_path / "pythonw.exe"), "-m", "anishift.cli.main", "watch"]


def test_watch_command_refuses_an_environment_without_pythonw(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    with pytest.raises(AutostartError, match="pythonw"):
        autostart.watch_command()


@pytest.mark.usefixtures("on_windows")
def test_register_creates_the_logon_task_without_starting_the_watch_now() -> None:
    runner: _Runner = _Runner()

    autostart.register(_WATCH_ARGV, run=runner)

    assert [call[:4] for call in runner.calls] == [["schtasks", "/Create", "/F", "/XML"]]
    assert runner.calls[0][5:] == ["/TN", TASK_NAME]
    assert not Path(runner.calls[0][4]).exists()
    assert "<Arguments>-m anishift.cli.main watch</Arguments>" in runner.definitions[0]


@pytest.mark.usefixtures("off_windows")
def test_register_refuses_outside_windows_without_touching_a_process() -> None:
    runner: _Runner = _Runner()

    with pytest.raises(autostart.AutostartUnsupportedError):
        autostart.register(_WATCH_ARGV, run=runner)

    assert runner.calls == []


class _Scheduler:
    def __init__(self) -> None:
        self.enabled: bool | None = None
        self.created: list[bool] = []
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str], **_options: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(command))
        if "/Create" in command:
            definition: str = Path(command[command.index("/XML") + 1]).read_text(encoding="utf-16")
            root: ElementTree.Element = ElementTree.fromstring(definition)  # noqa: S314 - generated task definition
            enabled: ElementTree.Element | None = root.find(
                "task:Settings/task:Enabled", {"task": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            )
            assert enabled is not None
            self.enabled = enabled.text == "true"
            self.created.append(self.enabled)
            return _completed(0)
        if "/DISABLE" in command or "/Delete" in command:
            if self.enabled is None:
                return _completed(1, stderr=_MISSING_TASK_STDERR)
            self.enabled = False if "/DISABLE" in command else None
            return _completed(0)
        if "/Query" in command:
            if self.enabled is None:
                return _completed(1, stderr=_MISSING_TASK_STDERR)
            return _completed(0, stdout=_definition("true" if self.enabled else "false"))
        return _completed(0)


@pytest.mark.usefixtures("on_windows")
@pytest.mark.parametrize("existing", [False, True])
def test_explicit_off_survives_normal_startup_and_only_explicit_enable_starts_the_task(
    monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    scheduler: _Scheduler = _Scheduler()
    monkeypatch.setattr(autostart, "watch_command", lambda: list(_WATCH_ARGV))
    monkeypatch.setattr(autostart, "status", partial(autostart.status, run=scheduler))
    monkeypatch.setattr(autostart, "register", partial(autostart.register, run=scheduler))

    if existing:
        autostart.register(_WATCH_ARGV)
        assert autostart.status() is AutostartStatus.ENABLED

    autostart.disable(run=scheduler)
    watch_module._ensure_autostart()

    assert autostart.status() is AutostartStatus.DISABLED
    assert scheduler.created == [existing]
    assert not any("/Run" in command for command in scheduler.calls)

    autostart.enable(_WATCH_ARGV, run=scheduler)

    assert autostart.status() is AutostartStatus.ENABLED
    assert scheduler.created == [existing, True]
    assert scheduler.calls[-2] == ["schtasks", "/Run", "/TN", TASK_NAME]
