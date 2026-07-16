"""Tests for the shell command registry and dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli.commands import COMMANDS, dispatch
from anishift.config import user_settings
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppContext:
    monkeypatch.setattr(user_settings, "config_path", lambda: tmp_path / "settings.json")
    return AppContext(
        settings=Settings(),
        user_settings=UserSettings(),
        workspace_root=tmp_path,
    )


def test_registry_has_the_six_commands() -> None:
    assert set(COMMANDS) == {"/help", "/settings", "/auto", "/manual", "/doctor", "/exit"}


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
