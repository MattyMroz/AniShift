from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anishift.setup.installer import ResourceResult
from anishift.utils.logger import get_logger

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


def test_main_writes_application_log_without_terminal_sink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "anishift.log.jsonl"

    def fake_app() -> None:
        get_logger(__name__).info("pipeline diagnostic")

    monkeypatch.setattr(cli_main, "_log_path", lambda: log_path)
    monkeypatch.setattr(cli_main, "app", fake_app)

    cli_main.main()

    assert log_path.is_file()
    assert "pipeline diagnostic" in log_path.read_text(encoding="utf-8")


def test_main_persists_unhandled_exception_in_error_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "anishift.log.jsonl"

    def failing_app() -> None:
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(cli_main, "_log_path", lambda: log_path)
    monkeypatch.setattr(cli_main, "app", failing_app)

    with pytest.raises(RuntimeError, match="pipeline exploded"):
        cli_main.main()

    error_path = log_path.parent / "errors.log.jsonl"
    assert error_path.is_file()
    assert "pipeline exploded" in error_path.read_text(encoding="utf-8")
