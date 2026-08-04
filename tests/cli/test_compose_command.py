from __future__ import annotations

from anishift.cli.commands import COMMANDS


def test_compose_command_is_registered() -> None:
    assert "/compose" in COMMANDS
    assert "translation" in COMMANDS["/compose"].summary.casefold()


def test_compose_command_takes_no_options() -> None:
    assert COMMANDS["/compose"].options == {}
