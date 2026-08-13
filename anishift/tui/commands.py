"""Parsing for the short command-bar vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from enum import StrEnum


class UiCommand(StrEnum):
    """Commands accepted by the persistent TUI command bar."""

    AUTO = "auto"
    MANUAL = "manual"
    SETTINGS = "settings"
    REFRESH = "refresh"
    DOCTOR = "doctor"
    SETUP = "setup"
    HELP = "help"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """A recognized command or one user-facing parse error."""

    command: UiCommand | None
    error: str | None = None


def parse_command(text: str) -> ParsedCommand:
    """Normalize one argument-free command and suggest a nearby spelling."""
    normalized: str = text.strip().casefold()
    if not normalized:
        return ParsedCommand(None)
    try:
        return ParsedCommand(UiCommand(normalized))
    except ValueError:
        choices: tuple[str, ...] = tuple(command.value for command in UiCommand)
        matches: list[str] = get_close_matches(normalized, choices, n=1, cutoff=0.6)
        suffix: str = f" Did you mean '{matches[0]}'?" if matches else ""
        return ParsedCommand(None, f"Unknown command: {normalized}.{suffix}")
