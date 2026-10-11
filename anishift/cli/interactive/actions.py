"""Screen actions shared by panel footers and the ? help."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from rich.cells import cell_len
from rich.text import Text

from anishift.cli.interactive.menu import pack_keys

# ── Constants ─────────────────────────────────────────────────────────────────

type Action = tuple[str, str]
"""One key and its Polish label, as shown in a footer or help."""

EVERYWHERE: Final[tuple[Action, ...]] = (
    ("↑↓", "wybierz"),
    ("←→ Tab", "zakładki"),
    ("O", "automat"),
    ("Esc", "wróć"),
)
"""Keys working on every panel screen, listed at the end of each help."""

MORE: Final[str] = "? klawisze"
"""Footer hint opening the help of the current screen."""

ACTION_NOTICES: Final[frozenset[str]] = frozenset({"Ctrl+Z cofnij", "P pobierz ponownie"})
"""Key hints a notice may end with, clickable like the footer."""

PANEL_ACTIONS: Final[tuple[Action, ...]] = (("M", "ręczny"), ("U", "ustawienia"))
"""Mode switches listed under ? on every list outside Anime."""


@dataclass(frozen=True, slots=True)
class ScreenActions:
    """Name a screen's footer actions in priority order and the actions listed only in its help."""

    footer: tuple[Action, ...] = ()
    more: tuple[Action, ...] = ()

    @property
    def listed(self) -> tuple[Action, ...]:
        """Return every action of the screen in priority order."""
        return (*self.footer, *self.more)


def footer_segments(actions: ScreenActions, *, more: bool = True) -> tuple[str, ...]:
    """Build footer hints: footer actions, then ? klawisze and Esc wróć, merged with an Enter that also goes back."""
    shown: list[str] = [f"{key} {label}" for key, label in actions.footer]
    escape: tuple[str, ...] = ("Esc wróć",)
    if shown and shown[0] == "Enter wróć":
        shown[0], escape = "Enter/Esc wróć", ()
    return (*shown, *((MORE,) if more else ()), *escape)


def pack_footer(segments: Sequence[str], width: int) -> tuple[str, ...]:
    """Pack footer hints into two lines, dropping actions from the end but never ? or Esc."""
    optional: tuple[str, ...] = tuple(
        segment for segment in reversed(segments) if not segment.startswith(("?", "Esc", "Enter/Esc"))
    )
    return pack_keys(segments, width, optional=optional)


def help_lines(actions: Sequence[Action], width: int, *, intro: Sequence[str] = ()) -> tuple[str, ...]:
    """List the actions of this screen and of every screen as a table of keys and what they do."""
    sections: tuple[tuple[str, Sequence[Action]], ...] = (("Ten ekran", actions), ("Wszędzie", EVERYWHERE))
    column: int = max(cell_len(key) for _title, rows in sections for key, _label in rows)
    lines: list[str] = list(intro)
    for title, rows in sections:
        if not rows:
            continue
        lines.append(title)
        lines.extend(_cropped(f"  {key}{' ' * (column - cell_len(key))}  {label}", width) for key, label in rows)
    return tuple(lines)


def _cropped(line: str, width: int) -> str:
    shown: Text = Text(line)
    shown.truncate(max(width, 1), overflow="crop")
    return shown.plain
