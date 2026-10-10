"""Screen actions shared by panel footers and the ? help."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from anishift.cli.interactive.menu import pack_keys

# ── Constants ─────────────────────────────────────────────────────────────────

type Action = tuple[str, str]
"""One key and its Polish label, as shown in a footer or help."""

EVERYWHERE: Final[tuple[Action, ...]] = (
    ("↑↓", "wybierz"),
    ("←→", "zakładki"),
    ("Tab", "zakładki"),
    ("O", "automat"),
    ("Esc", "wróć"),
)
"""Keys working on every panel screen, listed at the end of each help."""

MORE: Final[str] = "? więcej"
"""Footer hint opening the help of the current screen."""

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
    """Build footer hints: footer actions, then ? więcej and Esc wróć, merged with an Enter that also goes back."""
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
    """List the actions of this screen and of every screen, wrapped only between hints."""
    listed: tuple[str, ...] = tuple(f"{key} {label}" for key, label in actions)
    everywhere: tuple[str, ...] = tuple(f"{key} {label}" for key, label in EVERYWHERE)
    return (
        *intro,
        *(("Ten ekran", *pack_keys(listed, width, limit=len(listed))) if listed else ()),
        "Wszędzie",
        *pack_keys(everywhere, width, limit=len(everywhere)),
    )
