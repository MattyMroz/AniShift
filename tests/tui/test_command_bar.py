from __future__ import annotations

from anishift.tui.commands import UiCommand, parse_command
from anishift.tui.state import SessionState


def test_command_parser_accepts_exact_casefolded_commands() -> None:
    assert parse_command("  AuTo  ").command is UiCommand.AUTO
    assert parse_command("manual").command is UiCommand.MANUAL
    assert parse_command("settings").command is UiCommand.SETTINGS
    assert parse_command("refresh").command is UiCommand.REFRESH
    assert parse_command("doctor").command is UiCommand.DOCTOR
    assert parse_command("setup").command is UiCommand.SETUP
    assert parse_command("help").command is UiCommand.HELP


def test_command_parser_keeps_empty_input_inert_and_suggests_typo() -> None:
    assert parse_command("   ").command is None
    assert parse_command("   ").error is None
    parsed = parse_command("setings")
    assert parsed.command is None
    assert parsed.error == "Unknown command: setings. Did you mean 'settings'?"


def test_session_elapsed_changes_only_while_running() -> None:
    now: list[float] = [10.0]
    state = SessionState("workspace", _clock=lambda: now[0])
    assert state.elapsed_seconds == 0
    assert state.begin_run() == 1
    now[0] = 12.9
    assert state.elapsed_seconds == 2
    state.finish_run("completed")
    now[0] = 20.0
    assert state.elapsed_seconds == 0
