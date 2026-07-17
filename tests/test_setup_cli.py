"""Tests for the `anishift setup` CLI command."""

from __future__ import annotations

import importlib

import pytest
from typer.testing import CliRunner

from anishift.setup.installer import ResourceResult

cli_main = importlib.import_module("anishift.cli.main")


def test_setup_command_prints_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        return [ResourceResult("ffmpeg", "installed", "downloaded and verified")]

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup"])
    assert result.exit_code == 0
    assert "ffmpeg" in result.output


def test_setup_command_exits_1_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        return [ResourceResult("ffmpeg", "failed", "download failed")]

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup"])
    assert result.exit_code == 1


def test_setup_command_passes_force(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return []

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup", "--force"])
    assert result.exit_code == 0
    assert seen["force"] is True
