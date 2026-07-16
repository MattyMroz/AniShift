"""Shell command registry — single source of truth for ``/commands``.

The completer and ``/help`` both derive from :data:`COMMANDS`; nothing lists
the commands twice. Handlers take the :class:`AppContext` and return ``True``
to keep the REPL running or ``False`` to exit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from anishift.bootstrap import AppContext
from anishift.config.user_settings import Mode, save_user_settings
from anishift.setup.doctor import CheckStatus, run_doctor
from utils.rich_console import StatusType, console, get_status_icon

__all__ = ["COMMANDS", "Command", "dispatch"]

# ── Constants ──────────────────────────────────────────────────────────────

_STATUS_ICON: dict[CheckStatus, StatusType] = {
    CheckStatus.OK: "success",
    CheckStatus.WARN: "warning",
    CheckStatus.FAIL: "error",
    CheckStatus.SKIP: "stopped",
}
"""Maps a doctor check outcome to a ``rich_console`` status-icon name."""


@dataclass(frozen=True, slots=True)
class Command:
    """A shell command.

    Attributes:
        name: The slash-prefixed command token (``"/help"``).
        summary: One-line description shown in completion and ``/help``.
        handler: Runs the command; returns ``False`` to exit the REPL.
    """

    name: str
    summary: str
    handler: Callable[[AppContext], bool]


def _set_mode(context: AppContext, mode: Mode) -> bool:
    """Switch the processing mode and persist it."""
    context.user_settings.mode = mode
    save_user_settings(context.user_settings)
    console.print(f"[success]Mode set to[/success] [info]{mode}[/info].")
    return True


def _handle_help(context: AppContext) -> bool:
    """Print the command table."""
    for command in COMMANDS.values():
        console.print(f"  [info]{command.name}[/info]  [gray]{command.summary}[/gray]")
    return True


def _handle_settings(context: AppContext) -> bool:
    """Open the settings panel (imported lazily to defer prompt_toolkit)."""
    from anishift.cli.settings_panel import open_settings_panel  # noqa: PLC0415

    context.user_settings = open_settings_panel(context)
    return True


def _handle_auto(context: AppContext) -> bool:
    """Switch to auto mode."""
    return _set_mode(context, "auto")


def _handle_manual(context: AppContext) -> bool:
    """Switch to manual mode."""
    return _set_mode(context, "manual")


def _handle_doctor(context: AppContext) -> bool:
    """Run diagnostics and render the report."""
    for result in run_doctor(context.settings):
        icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
        if result.suggestion and result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            console.print(f"   [gray]-> {result.suggestion}[/gray]")
    return True


def _handle_exit(context: AppContext) -> bool:
    """Leave the REPL."""
    return False


COMMANDS: dict[str, Command] = {
    "/auto": Command("/auto", "Switch to auto mode (Enter processes everything)", _handle_auto),
    "/doctor": Command("/doctor", "Run diagnostics and report your setup", _handle_doctor),
    "/exit": Command("/exit", "Leave AniShift", _handle_exit),
    "/help": Command("/help", "Show available commands", _handle_help),
    "/manual": Command("/manual", "Switch to manual mode (prompt per track)", _handle_manual),
    "/settings": Command("/settings", "Open the settings panel", _handle_settings),
}
"""Single source of truth for every shell command, keyed by name."""


def dispatch(text: str, context: AppContext) -> bool:
    """Route a ``/``-prefixed line to its handler.

    Args:
        text: The raw command line (leading/trailing spaces tolerated).
        context: The wired application context passed to the handler.

    Returns:
        ``True`` to keep the REPL running, ``False`` to exit. A blank line or
        an unknown command keeps the loop running.
    """
    parts = text.strip().split()
    if not parts:
        return True
    name = parts[0]
    command = COMMANDS.get(name)
    if command is None:
        console.print(f"[warning]Unknown command[/warning] [info]{name}[/info]. Type [info]/help[/info].")
        return True
    return command.handler(context)
