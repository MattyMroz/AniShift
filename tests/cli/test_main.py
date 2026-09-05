from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Final
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner, Result

from anishift import bootstrap
from anishift.application import AppService
from anishift.config.workspace import ENV_WORKSPACE_ROOT, WorkspaceRootNotResolvedError
from anishift.errors import ErrorCode, ErrorContext

cli_main = importlib.import_module("anishift.cli.main")

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
cli_main.run_setup = lambda *, force=False: []
runner = CliRunner()
codes = [
    runner.invoke(cli_main.app, ["doctor"]).exit_code,
    runner.invoke(cli_main.app, ["setup"]).exit_code,
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
