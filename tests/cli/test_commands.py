from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli.commands import COMMANDS, dispatch
from anishift.config import user_settings
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.setup.installer import ResourceResult


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppContext:
    monkeypatch.setattr(user_settings, "config_path", lambda: tmp_path / "settings.json")
    return AppContext(
        settings=Settings(),
        user_settings=UserSettings(),
        workspace_root=tmp_path,
    )


def test_registry_has_the_seven_commands() -> None:
    assert set(COMMANDS) == {"/help", "/settings", "/auto", "/manual", "/doctor", "/exit", "/setup"}


def test_setup_defaults_to_no_force(context: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return [ResourceResult("ffmpeg", "installed", "downloaded and verified")]

    monkeypatch.setattr("anishift.setup.installer.run_setup", _fake_run_setup)
    assert dispatch("/setup", context) is True
    assert seen["force"] is False


def test_setup_force_token_forces_reinstall(context: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return []

    monkeypatch.setattr("anishift.setup.installer.run_setup", _fake_run_setup)
    assert dispatch("/setup force", context) is True
    assert seen["force"] is True


def test_setup_unknown_option_reports_without_running(
    context: AppContext, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _never(**_kwargs: object) -> list[ResourceResult]:
        raise AssertionError("run_setup must not run for an unknown option")

    monkeypatch.setattr("anishift.setup.installer.run_setup", _never)
    assert dispatch("/setup blah", context) is True
    assert "Unknown option" in capsys.readouterr().out


def test_option_on_optionless_command_reports(context: AppContext, capsys: pytest.CaptureFixture[str]) -> None:
    assert dispatch("/help force", context) is True
    assert "Unknown option" in capsys.readouterr().out


def test_exit_handler_returns_false(context: AppContext) -> None:
    assert dispatch("/exit", context) is False


def test_help_returns_true(context: AppContext) -> None:
    assert dispatch("/help", context) is True


def test_auto_sets_mode_and_persists(context: AppContext) -> None:
    context.user_settings = UserSettings(mode="manual")
    assert dispatch("/auto", context) is True
    assert context.user_settings.mode == "auto"
    assert user_settings.load_user_settings().mode == "auto"


def test_manual_sets_mode_and_persists(context: AppContext) -> None:
    assert dispatch("/manual", context) is True
    assert context.user_settings.mode == "manual"
    assert user_settings.load_user_settings().mode == "manual"


def test_unknown_command_returns_true(context: AppContext) -> None:
    assert dispatch("/nope", context) is True


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_blank_input_returns_true_without_raising(text: str, context: AppContext) -> None:
    assert dispatch(text, context) is True
