"""Inline autocomplete for ``/commands`` — active only after a leading ``/``."""

from __future__ import annotations

from collections.abc import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from anishift.cli.commands import COMMANDS

__all__ = ["SlashCompleter"]


class SlashCompleter(Completer):
    """Complete ``/commands`` when the current word starts with ``/``.

    Matches are alphabetical prefix matches drawn from
    :data:`anishift.cli.commands.COMMANDS`; the command summary is shown as
    completion meta. Outside a leading ``/`` nothing is suggested.
    """

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        """Yield alphabetical ``/command`` completions for the current word."""
        word = document.text_before_cursor.lstrip()
        if not word.startswith("/"):
            return
        for name in sorted(COMMANDS):
            if name.startswith(word):
                yield Completion(
                    name,
                    start_position=-len(word),
                    display_meta=COMMANDS[name].summary,
                )
