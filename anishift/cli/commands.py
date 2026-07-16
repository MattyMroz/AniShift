"""Shell command registry — single source of truth for ``/commands``.

The completer, ``/help``, option suggestions and option validation all derive
from :data:`COMMANDS`; nothing lists the commands or their options twice.
Handlers take the :class:`AppContext` plus the set of enabled option tokens
and return ``True`` to keep the REPL running or ``False`` to exit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from anishift.bootstrap import AppContext
from anishift.config.user_settings import Mode, save_user_settings
from anishift.setup.doctor import CheckStatus, run_doctor
from utils.rich_console import StatusType, console, get_status_icon

if TYPE_CHECKING:
    from anishift.setup.installer import ResourceResult

__all__ = ["COMMANDS", "Command", "dispatch", "print_setup_report"]

# ── Constants ──────────────────────────────────────────────────────────────

_STATUS_ICON: dict[CheckStatus, StatusType] = {
    CheckStatus.OK: "success",
    CheckStatus.WARN: "warning",
    CheckStatus.FAIL: "error",
    CheckStatus.SKIP: "stopped",
}
"""Maps a doctor check outcome to a ``rich_console`` status-icon name."""

_OUTCOME_ICON: dict[str, StatusType] = {
    "installed": "success",
    "skipped": "info",
    "unavailable": "warning",
    "cancelled": "warning",
    "failed": "error",
}
"""Maps a setup outcome to a ``rich_console`` status-icon name."""

_FORCE: Final[str] = "force"
"""Option token of ``/setup`` that re-downloads everything."""


@dataclass(frozen=True, slots=True)
class Command:
    """A shell command.

    Attributes:
        name: The slash-prefixed command token (``"/help"``).
        summary: One-line description shown in completion and ``/help``.
        handler: Runs the command with the enabled option tokens; returns
            ``False`` to exit the REPL.
        options: Option token to description — the single source of truth
            both the completer (suggestions after the command name) and
            :func:`dispatch` (validation) derive from. Empty for commands
            without options.
    """

    name: str
    summary: str
    handler: Callable[[AppContext, frozenset[str]], bool]
    options: dict[str, str] = field(default_factory=dict)


def print_setup_report(results: list[ResourceResult]) -> None:
    """Render setup results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_OUTCOME_ICON.get(result.outcome, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.detail}")


def _set_mode(context: AppContext, mode: Mode) -> bool:
    """Switch the processing mode and persist it."""
    context.user_settings.mode = mode
    save_user_settings(context.user_settings)
    console.print(f"[success]Mode set to[/success] [info]{mode}[/info].")
    return True


def _handle_help(context: AppContext, options: frozenset[str]) -> bool:
    """Print the command table."""
    for command in COMMANDS.values():
        console.print(f"  [info]{command.name}[/info]  [gray]{command.summary}[/gray]")
    return True


def _handle_settings(context: AppContext, options: frozenset[str]) -> bool:
    """Open the settings panel (imported lazily to defer prompt_toolkit)."""
    from anishift.cli.settings_panel import open_settings_panel  # noqa: PLC0415

    context.user_settings = open_settings_panel(context)
    return True


def _handle_auto(context: AppContext, options: frozenset[str]) -> bool:
    """Switch to auto mode."""
    return _set_mode(context, "auto")


def _handle_manual(context: AppContext, options: frozenset[str]) -> bool:
    """Switch to manual mode."""
    return _set_mode(context, "manual")


def _handle_doctor(context: AppContext, options: frozenset[str]) -> bool:
    """Run diagnostics and render the report."""
    for result in run_doctor(context.settings):
        icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
        if result.suggestion and result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            console.print(f"   [gray]-> {result.suggestion}[/gray]")
    return True


def _handle_setup(context: AppContext, options: frozenset[str]) -> bool:
    """Install missing external tools (``force`` re-downloads everything)."""
    from anishift.errors import AniShiftError  # noqa: PLC0415
    from anishift.setup.installer import run_setup  # noqa: PLC0415

    try:
        results = run_setup(force=_FORCE in options)
    except AniShiftError as exc:
        console.print(f"[error]{exc}[/error]")
        return True
    print_setup_report(results)
    return True


def _handle_exit(context: AppContext, options: frozenset[str]) -> bool:
    """Leave the REPL."""
    return False


COMMANDS: dict[str, Command] = {
    "/auto": Command("/auto", "Switch to auto mode (Enter processes everything)", _handle_auto),
    "/doctor": Command("/doctor", "Run diagnostics and report your setup", _handle_doctor),
    "/exit": Command("/exit", "Leave AniShift", _handle_exit),
    "/help": Command("/help", "Show available commands", _handle_help),
    "/manual": Command("/manual", "Switch to manual mode (prompt per track)", _handle_manual),
    "/settings": Command("/settings", "Open the settings panel", _handle_settings),
    "/setup": Command(
        "/setup",
        "Download missing external tools",
        _handle_setup,
        options={_FORCE: "re-download everything, even if already present"},
    ),
}
"""Single source of truth for every shell command, keyed by name."""


def dispatch(text: str, context: AppContext) -> bool:
    """Route a ``/``-prefixed line to its handler.

    The first token selects the command; every following token must be an
    option declared in that command's :attr:`Command.options` (Claude-Code
    style: ``/setup force``, never unix flags).

    Args:
        text: The raw command line (leading/trailing spaces tolerated).
        context: The wired application context passed to the handler.

    Returns:
        ``True`` to keep the REPL running, ``False`` to exit. A blank line,
        an unknown command or an unknown option keeps the loop running.
    """
    parts = text.strip().split()
    if not parts:
        return True
    name = parts[0]
    command = COMMANDS.get(name)
    if command is None:
        console.print(f"[warning]Unknown command[/warning] [info]{name}[/info]. Type [info]/help[/info].")
        return True
    options = frozenset(parts[1:])
    unknown = options - command.options.keys()
    if unknown:
        known = ", ".join(sorted(command.options)) if command.options else "none"
        console.print(
            f"[warning]Unknown option[/warning] [info]{', '.join(sorted(unknown))}[/info]"
            f" for [info]{name}[/info]. Available: [info]{known}[/info].",
        )
        return True
    return command.handler(context, options)
