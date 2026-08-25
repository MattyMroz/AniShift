"""The single definition of one command the interface can run."""

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
    """One key and the action label a surface renders for it."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """The only definition of one command the interface can run."""

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
