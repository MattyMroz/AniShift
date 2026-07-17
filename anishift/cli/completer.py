"""Inline autocomplete for ``/commands`` — active only after a leading ``/``."""

from __future__ import annotations

from collections.abc import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from anishift.cli.commands import COMMANDS, Command

__all__ = ["SlashCompleter"]


class SlashCompleter(Completer):
    """Complete ``/commands`` and their options, Claude-Code style.

    Two levels, both derived from :data:`anishift.cli.commands.COMMANDS`:
    a leading ``/`` completes command names (summary as meta), and a known
    command followed by a space completes that command's option tokens
    (option description as meta). Outside a leading ``/`` nothing is
    suggested.
    """

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        """Yield command or option completions for the text before the cursor."""
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        name, separator, option_prefix = text.partition(" ")
        if not separator:
            yield from _complete_commands(name)
            return
        command = COMMANDS.get(name)
        if command is not None:
            yield from _complete_options(command, option_prefix)


def _complete_commands(prefix: str) -> Iterable[Completion]:
    """Yield alphabetical ``/command`` completions matching *prefix*."""
    for name in sorted(COMMANDS):
        if name.startswith(prefix):
            yield Completion(
                name,
                start_position=-len(prefix),
                display_meta=COMMANDS[name].summary,
            )


def _complete_options(command: Command, prefix: str) -> Iterable[Completion]:
    """Yield alphabetical option completions of *command* matching *prefix*."""
    for option in sorted(command.options):
        if option.startswith(prefix):
            yield Completion(
                option,
                start_position=-len(prefix),
                display_meta=command.options[option],
            )
