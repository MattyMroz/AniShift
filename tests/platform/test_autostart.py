from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

import pytest

from anishift.errors import ErrorCode
from anishift.platform import autostart
from anishift.platform.autostart import (
    TASK_NAME,
    AutostartError,
    AutostartStatus,
    AutostartUnsupportedError,
)

_WATCH_ARGV: Final[tuple[str, ...]] = ("C:\\envs\\my env\\Scripts\\pythonw.exe", "-m", "anishift.cli.main", "watch")

_QUOTED_TASK_ARGUMENT: Final[str] = '"C:\\envs\\my env\\Scripts\\pythonw.exe" -m anishift.cli.main watch'

_MISSING_TASK_STDERR: Final[str] = "ERROR: The system cannot find the file specified.\n"

_QUERY_ROW: Final[str] = '"AniShift Watch","N/A","{state}"\n'


class _Runner:
    def __init__(self, *results: subprocess.CompletedProcess[str]) -> None:
        self.results: list[subprocess.CompletedProcess[str]] = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str], **_options: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(command))
        if self.results:
            return self.results.pop(0)
        return _completed(0)


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["schtasks"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "is_windows", lambda: True)


@pytest.fixture
def off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "is_windows", lambda: False)


@pytest.mark.usefixtures("on_windows")
def test_enable_registers_the_logon_task_then_starts_it() -> None:
    runner: _Runner = _Runner()

    autostart.enable(_WATCH_ARGV, run=runner)

    assert runner.calls == [
        [
            "schtasks",
            "/Create",
            "/F",
            "/SC",
            "ONLOGON",
            "/RL",
            "LIMITED",
            "/TN",
            TASK_NAME,
            "/TR",
            _QUOTED_TASK_ARGUMENT,
        ],
        ["schtasks", "/Run", "/TN", TASK_NAME],
    ]


@pytest.mark.usefixtures("on_windows")
def test_enable_quotes_only_the_arguments_holding_a_space() -> None:
    runner: _Runner = _Runner()

    autostart.enable(["python.exe", "-m", "anishift.cli.main", "watch"], run=runner)

    assert runner.calls[0][-1] == "python.exe -m anishift.cli.main watch"


@pytest.mark.usefixtures("on_windows")
def test_enable_reports_a_refusing_scheduler_without_its_full_stderr() -> None:
    runner: _Runner = _Runner(_completed(1, stderr="ERROR: Access is denied.\nsecond line\n"))

    with pytest.raises(AutostartError) as failure:
        autostart.enable(_WATCH_ARGV, run=runner)

    assert failure.value.context.code is ErrorCode.AUTOSTART_FAILED
    assert failure.value.context.suggestion == "ERROR: Access is denied."
    assert "second line" not in str(failure.value)


@pytest.mark.usefixtures("on_windows")
def test_enable_does_not_start_a_task_it_could_not_register() -> None:
    runner: _Runner = _Runner(_completed(1, stderr="ERROR: Access is denied.\n"))

    with pytest.raises(AutostartError):
        autostart.enable(_WATCH_ARGV, run=runner)

    assert len(runner.calls) == 1


@pytest.mark.usefixtures("on_windows")
def test_disable_removes_the_task() -> None:
    runner: _Runner = _Runner()

    autostart.disable(run=runner)

    assert runner.calls == [["schtasks", "/Delete", "/F", "/TN", TASK_NAME]]


@pytest.mark.usefixtures("on_windows")
def test_disable_accepts_a_task_the_scheduler_cannot_find() -> None:
    runner: _Runner = _Runner(_completed(1, stderr=_MISSING_TASK_STDERR))

    autostart.disable(run=runner)

    assert len(runner.calls) == 1


@pytest.mark.usefixtures("on_windows")
def test_disable_reports_every_other_refusal() -> None:
    runner: _Runner = _Runner(_completed(1, stderr="ERROR: Access is denied.\n"))

    with pytest.raises(AutostartError, match="remove"):
        autostart.disable(run=runner)


@pytest.mark.usefixtures("on_windows")
@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("Ready", AutostartStatus.ENABLED),
        ("Running", AutostartStatus.ENABLED),
        ("Disabled", AutostartStatus.DISABLED),
    ],
)
def test_status_reads_the_state_column_of_the_query_row(state: str, expected: AutostartStatus) -> None:
    runner: _Runner = _Runner(_completed(0, stdout=_QUERY_ROW.format(state=state)))

    assert autostart.status(run=runner) is expected
    assert runner.calls == [["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "CSV", "/NH"]]


@pytest.mark.usefixtures("on_windows")
def test_status_reports_a_task_the_scheduler_does_not_hold() -> None:
    runner: _Runner = _Runner(_completed(1, stderr=_MISSING_TASK_STDERR))

    assert autostart.status(run=runner) is AutostartStatus.MISSING


@pytest.mark.usefixtures("on_windows")
def test_status_reports_missing_when_the_query_prints_no_row() -> None:
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
