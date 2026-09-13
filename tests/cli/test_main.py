from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, NoReturn, cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result

from anishift import bootstrap
from anishift.application import AppService, CheckOutcome, Subscription, encode_view
from anishift.cli import control as cli_control
from anishift.cli import interactive as interactive_package
from anishift.cli import watch as cli_watch
from anishift.config.workspace import ENV_WORKSPACE_ROOT, WorkspaceRootNotResolvedError
from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.platform import autostart, qbittorrent_config
from anishift.platform.autostart import AutostartStatus, AutostartUnsupportedError

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


def test_autostart_disable_removes_the_task_and_stops_the_watch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    removed: list[bool] = []
    requested: list[Path] = []
    monkeypatch.setattr(autostart, "disable", lambda: removed.append(True))
    monkeypatch.setattr(cli_watch, "watch_state_dir", lambda: tmp_path)
    monkeypatch.setattr(cli_watch, "request_stop", requested.append)

    result: Result = CliRunner().invoke(cli_main.app, ["autostart", "disable"])

    assert result.exit_code == 0
    assert removed == [True]
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


def _service_with_subscriptions(subscriptions: object) -> AppService:
    return cast("AppService", SimpleNamespace(subscriptions=subscriptions))


def _followed(series: str, group: str, episode: int, checked: str | None) -> Subscription:
    return Subscription(
        subscription_id="ab12cd34ef56",
        series=series,
        group=group,
        next_episode=Decimal(episode),
        checked_at=checked,
        query=series,
        min_resolution=1080,
        taken=frozenset(),
        added_at="2026-09-13T00:00:00+00:00",
    )


def test_subs_list_prints_one_row_per_followed_series(monkeypatch: pytest.MonkeyPatch) -> None:
    followed: tuple[Subscription, ...] = (_followed("Neko to Ryuu", "SubsPlease", 12, None),)
    service: AppService = _service_with_subscriptions(SimpleNamespace(list=lambda: followed))
    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: service)

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "list"])

    assert result.exit_code == 0
    assert result.output.strip() == "ab12cd34ef56 [SubsPlease] Neko to Ryuu · next: 12 · checked: never"


def test_subs_list_states_when_nothing_is_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap, "production_service", lambda: _service_with_subscriptions(SimpleNamespace(list=lambda: ()))
    )

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "list"])

    assert result.exit_code == 0
    assert result.output.strip() == "No followed series."


def test_subs_remove_reports_an_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    removed: list[str] = []

    def remove(subscription_id: str) -> bool:
        removed.append(subscription_id)
        return False

    monkeypatch.setattr(
        cli_main, "_resident_call", lambda kind, payload: {"removed": remove(payload["subscription_id"])}
    )

    monkeypatch.setattr(
        bootstrap, "production_service", lambda: _service_with_subscriptions(SimpleNamespace(remove=remove))
    )

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "remove", "zzz"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert removed == ["zzz"]
    assert "No followed series has that id." in result.output


def test_subs_check_prints_downloads_and_problems_per_series(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: tuple[CheckOutcome, ...] = (
        CheckOutcome(subscription=_followed("Neko to Ryuu", "SubsPlease", 12, "x"), downloaded=2, problem=""),
        CheckOutcome(subscription=_followed("Oshi no Ko", "DKB", 3, "x"), downloaded=0, problem="Nyaa timed out"),
    )
    service: AppService = _service_with_subscriptions(SimpleNamespace(check_all=lambda: outcomes))
    monkeypatch.setattr(cli_main, "_resident_call", lambda kind: {"outcomes": [encode_view(item) for item in outcomes]})
    monkeypatch.setattr(bootstrap, "production_service", lambda **kwargs: service)

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "check"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "[SubsPlease] Neko to Ryuu: downloaded 2",
        "[DKB] Oshi no Ko: Nyaa timed out",
    ]


@pytest.mark.parametrize("command", [["subs", "list"], ["subs", "check"], ["subs", "remove", "ab12cd34ef56"]])
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

    store: SimpleNamespace = SimpleNamespace(list=refuse, check_all=refuse, remove=refuse)
    monkeypatch.setattr(cli_control, "open_control", refuse)
    monkeypatch.setattr(bootstrap, "production_service", lambda: _service_with_subscriptions(store))

    result: Result = CliRunner().invoke(cli_main.app, command)

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "Subscriptions file is invalid" in result.output
    assert "Fix or delete config/subscriptions.json" in result.output
    assert "Traceback" not in result.output


def test_subs_refuses_a_session_without_subscriptions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap, "production_service", lambda: _service_with_subscriptions(None))

    result: Result = CliRunner().invoke(cli_main.app, ["subs", "list"])

    assert result.exit_code == cli_main.EXIT_REFUSED
