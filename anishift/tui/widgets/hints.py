"""The key hint row and the tip row of the start screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.containers import Vertical
from textual.widgets import Static

from anishift.tui.commands.spec import KeyHint
from anishift.tui.strings import (
    GLYPH_GAP,
    HINT_ENTER_KEY,
    HINT_ENTER_LABEL,
    HINT_KEY_GAP,
    HINT_PAIR_GAP,
    TIP_GLYPH,
    TIP_LABEL,
    TIP_TEXT,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.app import ComposeResult

    from anishift.tui.commands.registry import CommandRegistry

__all__ = [
    "HINTS_ID",
    "KEYS_ID",
    "TIP_ID",
    "StartHints",
    "action_hints",
    "hints_row",
    "tip_row",
]

# ── Constants ──────────────────────────────────────────────────────────────

HINTS_ID: Final[str] = "app-hints"
"""Id of the region holding the hint row and the tip row."""

KEYS_ID: Final[str] = "app-keys"
"""Id of the one row of key hints."""

TIP_ID: Final[str] = "app-tip"
"""Id of the one tip row, the first element a small terminal drops."""


def action_hints(registry: CommandRegistry) -> tuple[KeyHint, ...]:
    """Return the ``enter`` hint, then the key of every command *registry* holds."""
    return (
        KeyHint(key=HINT_ENTER_KEY, label=HINT_ENTER_LABEL),
        *(spec.key_hint for spec in registry.commands() if spec.key_hint is not None),
    )


def hints_row(hints: Iterable[KeyHint]) -> str:
    """Render *hints* as one row: keys as the terminal names them, labels lowered."""
    return HINT_PAIR_GAP.join(f"{hint.key}{HINT_KEY_GAP}{hint.label.lower()}" for hint in hints)


def tip_row() -> str:
    """Render the tip line: a bullet, the word marking it, and one sentence."""
    return f"{TIP_GLYPH}{GLYPH_GAP}{TIP_LABEL}{HINT_KEY_GAP}{TIP_TEXT}"


class StartHints(Vertical):
    """The hint row and the tip row of the start screen."""

    def __init__(self) -> None:
        """Build both rows; the shell fills the keys from the live registry."""
        super().__init__(id=HINTS_ID)
        self._keys: Static = Static(id=KEYS_ID)
        self._tip: Static = Static(tip_row(), id=TIP_ID)

    def compose(self) -> ComposeResult:
        """Draw the key hints above the tip."""
        yield self._keys
        yield self._tip

    def show(self, hints: Iterable[KeyHint]) -> None:
        """Render *hints* into the key row."""
        self._keys.update(hints_row(hints))

    def show_tip(self, *, visible: bool) -> None:
        """Show or drop the tip, which no functional element ever waits for."""
        self._tip.display = visible
