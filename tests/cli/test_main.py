from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Final, NoReturn, cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result

from anishift import bootstrap
from anishift.application import AppService, SubscriptionRow, encode_view
from anishift.cli import control as cli_control
from anishift.cli import interactive as interactive_package
from anishift.cli import watch as cli_watch
from anishift.config.workspace import ENV_WORKSPACE_ROOT, WorkspaceRootNotResolvedError
from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.platform import autostart, qbittorrent_config
from anishift.platform.autostart import AutostartStatus, AutostartUnsupportedError
from anishift.platform.local_control import ControlError

cli_main = importlib.import_module("anishift.cli.main")

_UNSUPPORTED_AUTOSTART_MESSAGE: Final[str] = "Autostart needs the Windows task scheduler"

_UI_MODULE_PREFIXES: Final[tuple[str, ...]] = (
    "textual",
    "questionary",
    "prompt_toolkit",
    "anishift.tui",
    "anishift.cli.interactive",
)

_PROBE_TIMEOUT: Final[int] = 300

_MISSING_WORKSPACE_MESSAGE: Final[str] = "ANISHIFT_WORKSPACE_ROOT not set and no pyproject.toml"

_COLLIDING_WORKSPACE_MESSAGE: Final[str] = "workspace root exists but is not a directory"

_TECHNICAL_PROBE: Final[str] = """
import importlib
import json
import sys

from typer.testing import CliRunner

cli_main = importlib.import_module("anishift.cli.main")
cli_watch = importlib.import_module("anishift.cli.watch")
autostart = importlib.import_module("anishift.platform.autostart")
cli_main.run_setup = lambda *, force=False: []
cli_watch.watch_status = lambda state_dir: cli_watch.WatchStatus(running=False, pid=None)
autostart.status = lambda: autostart.AutostartStatus.MISSING
runner = CliRunner()
codes = [
    runner.invoke(cli_main.app, ["doctor"]).exit_code,
    runner.invoke(cli_main.app, ["setup"]).exit_code,
    runner.invoke(cli_main.app, ["watch", "status"]).exit_code,
    runner.invoke(cli_main.app, ["autostart", "status"]).exit_code,
]
prefixes = tuple(json.loads(sys.argv[1]))
print(json.dumps({"codes": codes, "loaded": sorted(n for n in sys.modules if n.startswith(prefixes))}))
"""


def test_resident_start_failure_is_polish_nonzero_and_closes_service(monkeypatch: pytest.MonkeyPatch) -> None:
    service: Mock = Mock(workspace_root=Path("unused"))
    monkeypatch.setattr(cli_main, "_composed_service", lambda: service)
    monkeypatch.setattr(cli_control, "open_control", Mock(side_effect=ControlError("Resident unavailable")))
    result: Result = CliRunner().invoke(cli_main.app, [])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Nie udało się połączyć z rezydentem" in result.output
    assert "anishift watch status" in result.output
    assert "Traceback" not in result.output
    service.close.assert_called_once()


def test_interactive_control_failure_is_not_misreported_as_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    resident_module = importlib.import_module("anishift.cli.resident")
    service: Mock = Mock(workspace_root=Path("unused"))
    session: Mock = Mock()
    problem: ControlError = ControlError("Interaction failed")
    monkeypatch.setattr(cli_main, "_composed_service", lambda: service)
    monkeypatch.setattr(resident_module, "ResidentSession", Mock(return_value=session))
    monkeypatch.setattr(interactive_package, "run_interactive", Mock(side_effect=problem))
    result: Result = CliRunner().invoke(cli_main.app, [])
    assert result.exception is problem
    assert "Nie udało się połączyć z rezydentem" not in result.output
    session.close.assert_called_once()
    service.close.assert_called_once()


def test_an_unresolved_workspace_reports_the_reason_and_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> AppService:
        raise WorkspaceRootNotResolvedError(
            context=ErrorContext(
                code=ErrorCode.WORKSPACE_NOT_RESOLVED,
                message=_MISSING_WORKSPACE_MESSAGE,
                suggestion="Set ANISHIFT_WORKSPACE_ROOT or run from a repo checkout",
            ),
        )

    monkeypatch.setattr(bootstrap, "production_service", fail)

    result: Result = CliRunner().invoke(cli_main.app, [])

    assert result.exit_code == 1
    assert _MISSING_WORKSPACE_MESSAGE in result.output


def test_a_workspace_path_collision_reports_the_reason_instead_of_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> AppService:
        raise NotADirectoryError(_COLLIDING_WORKSPACE_MESSAGE)

    monkeypatch.setattr(bootstrap, "production_service", fail)

    result: Result = CliRunner().invoke(cli_main.app, [])

    assert result.exit_code == 1
    assert _COLLIDING_WORKSPACE_MESSAGE in result.output
    assert isinstance(result.exception, SystemExit)


def test_the_entry_point_holds_no_second_construction_path() -> None:
    entry_point: Path = Path(__file__).parents[2] / "anishift" / "cli" / "main.py"
    source: str = entry_point.read_text(encoding="utf-8")

    assert "production_service" in source
    assert "create_app_service" not in source
    assert "prototype" not in source
    assert "PrototypeApp" not in source
    assert "AniShiftApp" not in source


@pytest.mark.parametrize("exit_code", [0, 4])
def test_ctrl_c_during_logger_shutdown_preserves_exit_and_finishes_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
) -> None:
    logger_module = importlib.import_module("anishift.utils.logger")
    completed: list[bool] = []
    previous = signal.getsignal(signal.SIGINT)

    def shutdown() -> None:
        signal.raise_signal(signal.SIGINT)
        completed.append(True)

    monkeypatch.setattr(logger_module, "setup_mode_from_env", Mock())
    monkeypatch.setattr(logger_module, "get_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(logger_module, "shutdown_logger", shutdown)
    monkeypatch.setattr(cli_main, "app", Mock(side_effect=SystemExit(exit_code)))

    try:
        with pytest.raises(SystemExit) as result:
            cli_main.main()
    except KeyboardInterrupt:
        pytest.fail("Ctrl+C interrupted logger cleanup")

    assert result.value.code == exit_code
    assert completed == [True]
    assert signal.getsignal(signal.SIGINT) == previous


def test_the_technical_subcommands_load_no_interactive_toolkit(tmp_path: Path) -> None:
    environment: dict[str, str] = {
        name: value for name, value in os.environ.items() if not name.startswith("ANISHIFT_")
    }
    environment[ENV_WORKSPACE_ROOT] = str(tmp_path / "workspace")
    probe: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _TECHNICAL_PROBE, json.dumps(_UI_MODULE_PREFIXES)],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT,
        check=False,
        env=environment,
    )

    assert probe.returncode == 0, probe.stderr
    report: dict[str, Any] = json.loads(probe.stdout)
    assert report["loaded"] == []
    assert report["codes"][2:] == [0, 0]


def test_doctor_reports_the_watch_and_the_logon_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_main, "run_doctor", lambda **kwargs: [])
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "watch_status", lambda _dir: cli_watch.WatchStatus(running=True, pid=7))
    monkeypatch.setattr(cli_control, "resident_status", lambda _dir: cli_control.ResidentStatus(running=True, pid=7))
    monkeypatch.setattr(autostart, "status", lambda: autostart.AutostartStatus.MISSING)

    result: Result = CliRunner().invoke(cli_main.app, ["doctor"])

    assert result.exit_code == 0
    assert "watch: running (pid 7)" in result.output
    assert "autostart: missing" in result.output
    assert "anishift autostart enable" in result.output


def test_doctor_skips_the_logon_task_where_the_scheduler_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse() -> autostart.AutostartStatus:
        raise autostart.AutostartUnsupportedError(
            context=ErrorContext(
                code=ErrorCode.AUTOSTART_UNSUPPORTED,
                message="Autostart needs the Windows Task Scheduler",
                suggestion="Run the watch by hand",
            )
        )

    monkeypatch.setattr(cli_main, "run_doctor", lambda **kwargs: [])
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(autostart, "status", refuse)

    result: Result = CliRunner().invoke(cli_main.app, ["doctor"])

    assert result.exit_code == 0
    assert "watch: stopped" in result.output
    assert "autostart: Autostart needs the Windows Task Scheduler" in result.output


def test_watch_status_reports_a_stopped_watch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)

    result: Result = CliRunner().invoke(cli_main.app, ["watch", "status"])

    assert result.exit_code == 0
    assert result.output.splitlines() == ["stopped", "resident: stopped"]


def test_watch_status_names_the_running_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "watch_status", lambda _dir: cli_watch.WatchStatus(running=True, pid=99))

    result: Result = CliRunner().invoke(cli_main.app, ["watch", "status"])

    assert result.exit_code == 0
    assert result.output.splitlines() == ["running (pid 99)", "resident: stopped"]


def test_watch_stop_records_the_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requested: list[Path] = []
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "request_stop", requested.append)

    result: Result = CliRunner().invoke(cli_main.app, ["watch", "stop"])

    assert result.exit_code == 0
    assert requested == [tmp_path]


def test_watch_runs_the_daemon_on_the_composed_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service: AppService = cast("AppService", object())
    seen: list[tuple[object, Path]] = []

    def daemon(passed: AppService, *, state_dir: Path, enable_tray: bool) -> int:
        assert enable_tray
        seen.append((passed, state_dir))
        return 3

    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: service)
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "run_resident", daemon)

    result: Result = CliRunner().invoke(cli_main.app, ["watch"])

    assert result.exit_code == 3
    assert seen == [(service, tmp_path)]


def test_watch_refuses_a_second_process_with_one_sentence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started: list[Path] = []

    def daemon(service: AppService, *, state_dir: Path, enable_tray: bool) -> int:
        assert enable_tray
        del service
        started.append(state_dir)
        return 0

    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: cast("AppService", object()))
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "watch_status", lambda _dir: cli_watch.WatchStatus(running=True, pid=7))
    monkeypatch.setattr(cli_watch, "run_resident", daemon)

    result: Result = CliRunner().invoke(cli_main.app, ["watch"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert result.output.strip() == "Another watch process is already running; see `anishift watch status`"
    assert started == []


def test_watch_says_it_is_watching_before_the_loop_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: cast("AppService", object()))
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "watch_status", lambda _dir: cli_watch.WatchStatus(running=False, pid=None))
    monkeypatch.setattr(cli_watch, "run_resident", lambda service, *, state_dir, enable_tray: 0)

    result: Result = CliRunner().invoke(cli_main.app, ["watch"])

    assert result.exit_code == 0
    assert result.output.strip() == "Watching the library; Ctrl+C or `anishift watch stop` ends it"


def test_watch_batch_explains_migration_without_opening_another_window(monkeypatch: pytest.MonkeyPatch) -> None:
    service: AppService = cast("AppService", object())
    batches: list[list[str]] = []

    def interactive(passed: AppService, *, batch: list[str] | None = None) -> int:
        assert passed is service
        batches.append(list(batch or []))
        return 4

    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: service)
    monkeypatch.setattr(interactive_package, "run_interactive", interactive)

    result: Result = CliRunner().invoke(cli_main.app, ["watch", "batch", "a", "b"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert batches == []
    assert "Batch windows were replaced" in result.output


def test_autostart_enable_registers_the_watch_command(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[list[str]] = []
    monkeypatch.setattr(autostart, "watch_command", lambda: ["pythonw.exe", "-m", "anishift.cli.main", "watch"])
    monkeypatch.setattr(autostart, "enable", lambda command: registered.append(list(command)))

    result: Result = CliRunner().invoke(cli_main.app, ["autostart", "enable"])

    assert result.exit_code == 0
    assert registered == [["pythonw.exe", "-m", "anishift.cli.main", "watch"]]


def test_autostart_enable_states_a_refusal_without_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> list[str]:
        raise AutostartUnsupportedError(
            context=ErrorContext(
                code=ErrorCode.AUTOSTART_UNSUPPORTED,
                message=_UNSUPPORTED_AUTOSTART_MESSAGE,
                suggestion="Start `anishift watch` yourself on this system",
            ),
        )

    monkeypatch.setattr(autostart, "watch_command", refuse)

    result: Result = CliRunner().invoke(cli_main.app, ["autostart", "enable"])

    assert result.exit_code == 1
    assert _UNSUPPORTED_AUTOSTART_MESSAGE in result.output
    assert isinstance(result.exception, SystemExit)


def test_autostart_disable_switches_the_task_off_and_stops_the_watch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    switched: list[bool] = []
    requested: list[Path] = []
    monkeypatch.setattr(autostart, "disable", lambda: switched.append(True))
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "request_stop", requested.append)

    result: Result = CliRunner().invoke(cli_main.app, ["autostart", "disable"])

    assert result.exit_code == 0
    assert switched == [True]
    assert requested == [tmp_path]


def test_autostart_status_prints_the_scheduler_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "status", lambda: AutostartStatus.ENABLED)

    result: Result = CliRunner().invoke(cli_main.app, ["autostart", "status"])

    assert result.exit_code == 0
    assert result.output.strip() == "enabled"


def test_qbit_status_checks_private_readiness_without_composing_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    doctor = importlib.import_module("anishift.setup.doctor")
    monkeypatch.setattr(bootstrap, "production_service", Mock(side_effect=AssertionError("no client startup")))
    monkeypatch.setattr(
        doctor,
        "check_managed_torrent_client",
        lambda: doctor.CheckResult("torrent_client", doctor.CheckStatus.OK, "Private binary ready"),
    )
    result: Result = CliRunner().invoke(cli_main.app, ["qbit", "status"])
    assert result.exit_code == 0
    assert "Private binary ready" in result.output


def test_qbit_setup_prepares_only_the_private_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    installer = importlib.import_module("anishift.setup.installer")
    calls: list[str] = []
    monkeypatch.setattr(installer, "ensure_resource", lambda name, **kwargs: calls.append(name))
    monkeypatch.setattr(
        qbittorrent_config, "enable_web_ui", Mock(side_effect=AssertionError("personal profile changed"))
    )
    result: Result = CliRunner().invoke(cli_main.app, ["qbit", "setup"])
    assert result.exit_code == 0
    assert calls == ["qbittorrent"]
    assert "password" not in result.output


def test_qbit_setup_reports_an_install_failure_without_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    installer = importlib.import_module("anishift.setup.installer")
    failure = installer.InstallerError(
        context=ErrorContext(code=ErrorCode.IO_ERROR, message="Archive integrity check failed")
    )
    monkeypatch.setattr(installer, "ensure_resource", Mock(side_effect=failure))
    result: Result = CliRunner().invoke(cli_main.app, ["qbit", "setup"])
    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "Archive integrity check failed" in result.output
    assert "Traceback" not in result.output


class _Resident:
    def __init__(self, answer: object) -> None:
        self.answer: object = answer
        self.calls: list[tuple[str, object]] = []
        self.closed: bool = False

    def call(self, kind: str, payload: object = None) -> object:
        self.calls.append((kind, payload))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer

    def close(self) -> None:
        self.closed = True


def _resident(monkeypatch: pytest.MonkeyPatch, answer: object) -> _Resident:
    resident: _Resident = _Resident(answer)
    monkeypatch.setattr(cli_control, "open_control", lambda _state_dir: resident)
    return resident


def test_subs_list_prints_one_row_per_followed_season_from_the_resident(monkeypatch: pytest.MonkeyPatch) -> None:
    row: SubscriptionRow = SubscriptionRow(
        subscription_id="ab12cd34ef56",
        anilist_id=500,
        title="Neko to Ryuu",
        on_disk=2,
        ready=1,
        due_at=None,
        paused=False,
        pause_reason=None,
        problem=None,
        review_pending=True,
    )
    rows: tuple[SubscriptionRow, ...] = (
        row,
        replace(row, subscription_id="cd34", title="Oshi no Ko", episode_count=12, review_pending=False),
        replace(row, subscription_id="ef56", paused=True, pause_reason="migrated_missing"),
    )
    resident: _Resident = _resident(monkeypatch, {"subscriptions": [encode_view(row) for row in rows]})

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "list"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "ab12cd34ef56 Neko to Ryuu · episodes: 2/? · ready: 1 · migrated, review pending",
        "cd34 Oshi no Ko · episodes: 2/12 · ready: 1 · active",
        "ef56 Neko to Ryuu · episodes: 2/? · ready: 1 · paused (migrated_missing)",
    ]
    assert resident.calls == [("subscriptions_list", None)]
    assert resident.closed


def test_subs_list_states_when_nothing_is_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    _resident(monkeypatch, {"subscriptions": []})

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "list"])

    assert result.exit_code == 0
    assert result.output.strip() == "No followed series."


def test_subs_remove_asks_the_resident_and_names_the_restore_key(monkeypatch: pytest.MonkeyPatch) -> None:
    resident: _Resident = _resident(monkeypatch, {"removed": True})

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "remove", "ab12cd34ef56"])

    assert result.exit_code == 0
    assert resident.calls == [("subscription_remove", {"subscription_id": "ab12cd34ef56"})]
    assert "Ctrl+Z" in result.output


def test_subs_remove_reports_an_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _resident(
        monkeypatch,
        ControlError("The subscription no longer exists", reason="subscription_missing", answered=True),
    )

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "remove", "zzz"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "The subscription no longer exists" in result.output
    assert "Traceback" not in result.output


class _Answers(_Resident):
    def __init__(self, answers: list[object]) -> None:
        super().__init__(None)
        self.answers: list[object] = answers

    def call(self, kind: str, payload: object = None) -> object:
        self.calls.append((kind, payload))
        return self.answers.pop(0)


_OLD_CHECK: dict[str, object] = {
    "checked_at": "2026-10-03T10:00:00+00:00",
    "number": 22,
    "matching": 1,
    "uncertain": 0,
    "mismatched": 0,
    "outcome": "proposed",
}


def test_subs_check_waits_for_the_new_result_and_prints_it(monkeypatch: pytest.MonkeyPatch) -> None:
    new: dict[str, object] = {**_OLD_CHECK, "checked_at": "2026-10-03T12:00:00+00:00", "number": 23, "matching": 0}
    new["outcome"] = "no_match"
    resident: _Answers = _Answers(
        [{"last_check": _OLD_CHECK}, {"checking": True}, {"last_check": _OLD_CHECK}, {"last_check": new}]
    )
    monkeypatch.setattr(cli_control, "open_control", lambda _state_dir: resident)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "check", "ab12cd34ef56"])

    payload: dict[str, object] = {"subscription_id": "ab12cd34ef56"}
    assert result.exit_code == 0
    assert result.output.strip() == "Checked E23: 0 matching, 0 uncertain, 0 mismatched · no match"
    assert [call for call, _ in resident.calls] == [
        "subscription_get",
        "subscription_check",
        "subscription_get",
        "subscription_get",
    ]
    assert all(sent == payload for _, sent in resident.calls)


def test_subs_check_names_a_list_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    refreshed: dict[str, object] = {**_OLD_CHECK, "number": None, "matching": 0, "outcome": "refreshed"}
    resident: _Answers = _Answers([{"last_check": None}, {"checking": True}, {"last_check": refreshed}])
    monkeypatch.setattr(cli_control, "open_control", lambda _state_dir: resident)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "check", "ab12"])

    assert result.output.strip() == "Checked the list: 0 matching, 0 uncertain, 0 mismatched · refreshed"


def test_subs_check_states_a_check_still_running(monkeypatch: pytest.MonkeyPatch) -> None:
    resident: _Answers = _Answers([{"last_check": None}, {"checking": True}])
    monkeypatch.setattr(cli_control, "open_control", lambda _state_dir: resident)
    monkeypatch.setattr(cli_main, "_SUBS_CHECK_WAIT_S", 0.0)

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "check", "ab12"])

    assert result.exit_code == cli_main.EXIT_INCOMPLETE
    assert "still running" in result.output


def test_subs_check_reports_an_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _resident(
        monkeypatch,
        ControlError("The subscription no longer exists", reason="subscription_missing", answered=True),
    )

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "check", "zzz"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "The subscription no longer exists" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", [["subs", "list"], ["subs", "remove", "ab12cd34ef56"]])
def test_subs_states_a_broken_store_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
) -> None:
    def refuse(*_arguments: object) -> NoReturn:
        raise ConfigError(
            context=ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message="Subscriptions file is invalid",
                suggestion="Fix or delete config/subscriptions.json",
            ),
        )

    monkeypatch.setattr(cli_control, "open_control", refuse)

    result: Result = CliRunner().invoke(cli_main.app, command)

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "Subscriptions file is invalid" in result.output
    assert "Fix or delete config/subscriptions.json" in result.output
    assert "Traceback" not in result.output
