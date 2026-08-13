from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from anishift.application.inspection import InspectedWorkspace
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings

cli_main: ModuleType = import_module("anishift.cli.main")


def test_default_entrypoint_launches_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    launch = Mock()
    monkeypatch.setattr(cli_main, "launch_tui", launch)

    result = CliRunner().invoke(cli_main.app)

    assert result.exit_code == 0
    launch.assert_called_once_with()


def test_run_preset_uses_shared_application_service(monkeypatch: pytest.MonkeyPatch) -> None:
    context = AppContext(Settings(_env_file=None), UserSettings(), Path("workspace"))
    service = Mock()
    group = Mock()
    group.group_id = "episode-01"
    service.discover.return_value = InspectedWorkspace((group,), ())
    service.get_preset.return_value = Mock()
    service.plan_auto.return_value = Mock()
    service.execute.return_value = RunResult(
        "run-1",
        (GroupResult("episode-01", GroupStatus.SUCCEEDED),),
    )
    monkeypatch.setattr(cli_main, "bootstrap", lambda: context)
    monkeypatch.setattr(cli_main, "create_app_service", lambda _context: service)

    result = CliRunner().invoke(cli_main.app, ["run", "--preset", "default"])

    assert result.exit_code == 0
    service.get_preset.assert_called_once_with("default")
    service.plan_auto.assert_called_once_with(("episode-01",), service.get_preset.return_value)
    service.execute.assert_called_once()
