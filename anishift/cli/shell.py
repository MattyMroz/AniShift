"""Interactive shell — the prompt_toolkit REPL that dispatches ``/commands``.

The shell only shows the banner, reads a line, and routes it: an empty line is
the (not-yet-wired) pipeline trigger, a ``/``-line goes to the command
registry. All domain logic lives elsewhere.
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory

from anishift.bootstrap import AppContext
from anishift.cli.banner import show_banner
from anishift.cli.commands import dispatch
from anishift.cli.completer import SlashCompleter
from anishift.config.user_settings import config_path
from utils.rich_console import console

__all__ = ["run_shell"]

# ── Constants ──────────────────────────────────────────────────────────────

_HISTORY_FILE_NAME: str = ".shell_history"
"""History filename kept next to ``config/settings.json`` (never in workspace)."""


def _history_path() -> str:
    """Return the shell-history path beside the panel-preferences file."""
    path = config_path().with_name(_HISTORY_FILE_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _bottom_toolbar() -> HTML:
    """Return the Claude-Code-style hint bar shown under the prompt."""
    return HTML("  Enter = process · /help = commands · Ctrl+C = exit")


def run_shell(context: AppContext) -> None:
    """Run the interactive shell until the user exits.

    Args:
        context: Wired application context used by command handlers.
    """
    show_banner(context)
    session: PromptSession[str] = PromptSession(
        history=FileHistory(_history_path()),
        completer=SlashCompleter(),
        complete_while_typing=True,
        bottom_toolbar=_bottom_toolbar,
    )
    while True:
        try:
            line = session.prompt("anishift > ")
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        stripped = line.strip()
        if not stripped:
            console.print("[warning]Pipeline in progress[/warning] — arrives in stage 3.")
            continue
        if stripped.startswith("/"):
            if not dispatch(stripped, context):
                break
            continue
        console.print("[gray]Type [/gray][info]/help[/info][gray] for commands, or press Enter to process.[/gray]")
    console.print("[gray]Bye.[/gray]")
