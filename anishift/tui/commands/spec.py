"""The single definition of one command the interface can run.

The name, title, description, category, slash form, aliases, keys and
availability predicates of a command live in exactly one ``CommandSpec``. The
palette, the slash suggestions, the key hints and the buttons only project this
definition, so a surface can never disagree with the command it runs.

A predicate receives the session state and answers about it; a spec never keeps
a copy of that state.

Public API:
    CommandRun: Callback one command runs when it is dispatched.
    CommandPredicate: Answer of one command about the session state it reads.
    StateReader: Read-only access to the session state the shell owns.
    CommandCategory: Group one command belongs to when a surface lists it.
    KeyHint: One key and the action label a surface renders for it.
    CommandSpec: The only definition of one command.
    key_display: Human form of one Textual key name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from anishift.tui.state import SessionState

__all__ = [
    "CommandCategory",
    "CommandPredicate",
    "CommandRun",
    "CommandSpec",
    "KeyHint",
    "StateReader",
    "key_display",
]

# ── Constants ──────────────────────────────────────────────────────────────

CommandRun = Callable[[], None]
"""Callback one command runs when the registry dispatches it."""

CommandPredicate = Callable[[SessionState], bool]
"""Answer of one command about the session state it is allowed to read."""

StateReader = Callable[[], SessionState]
"""Read-only access to the one session state the application shell owns."""

_KEY_SEPARATOR: Final[str] = "+"
"""Separator Textual puts between the modifiers and the key itself."""


def key_display(key: str) -> str:
    """Return the human form of the Textual key name *key*."""
    return _KEY_SEPARATOR.join(part.capitalize() for part in key.split(_KEY_SEPARATOR))


class CommandCategory(StrEnum):
    """Group one command belongs to when a surface lists commands.

    ``ACTION`` marks a contextual action: it may own keys and a palette row,
    but it never owns a slash name.
    """

    SESSION = "session"
    WORKFLOW = "workflow"
    SETTINGS = "settings"
    DIAGNOSTICS = "diagnostics"
    ACTION = "action"


@dataclass(frozen=True, slots=True)
class KeyHint:
    """One key and the action label a surface renders for it.

    Attributes:
        key: Textual key name the command answers to.
        label: Title of the command the key runs.
    """

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """The only definition of one command the interface can run.

    Attributes:
        name: Identity the registry stores and ``dispatch`` accepts.
        title: Short label a palette row, a key hint or a button shows.
        description: One sentence explaining what the command does.
        category: Group a surface uses to order and to label the command.
        run: Callback that performs the command; the catalog never writes one.
        hidden: Whether surfaces list the command; it stays runnable by key.
        enabled: Whether the session allows the command; ``None`` means always.
        suggested: Whether the session makes it the likely next step.
        slash_name: Slash form of the command, or ``None`` for an action.
        slash_aliases: Extra forms one query may match, without an extra row.
        keys: Textual key names that run the command through the registry.
    """

    name: str
    title: str
    description: str
    category: CommandCategory
    run: CommandRun
    hidden: bool = False
    enabled: CommandPredicate | None = None
    suggested: CommandPredicate | None = None
    slash_name: str | None = None
    slash_aliases: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a definition no surface could project consistently."""
        if not self.name:
            msg = "A command needs a name"
            raise ValueError(msg)
        if self.category is CommandCategory.ACTION and self.slash_name is not None:
            msg = f"Contextual action {self.name!r} cannot own a slash name"
            raise ValueError(msg)
        if self.slash_name is None and self.slash_aliases:
            msg = f"Command {self.name!r} owns aliases without a slash name"
            raise ValueError(msg)

    @property
    def slash_forms(self) -> tuple[str, ...]:
        """Slash name and aliases one query may match, as one command."""
        return () if self.slash_name is None else (self.slash_name, *self.slash_aliases)

    @property
    def key_hint(self) -> KeyHint | None:
        """Label of the first key this command answers to, if it owns one."""
        return KeyHint(key=self.keys[0], label=self.title) if self.keys else None

    def is_enabled(self, state: SessionState) -> bool:
        """Whether *state* lets this command run right now."""
        return True if self.enabled is None else self.enabled(state)

    def is_suggested(self, state: SessionState) -> bool:
        """Whether *state* makes this command the likely next step."""
        return False if self.suggested is None else self.suggested(state)
