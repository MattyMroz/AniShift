"""Shared shell for temporary Stage 9 route placeholders."""

from __future__ import annotations

from typing import Final

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from anishift.tui.widgets import CommandBar, StatusFooter

# ── Constants ────────────────────────────────────────────────────────────────

MINIMUM_TERMINAL_WIDTH: Final[int] = 100
"""Smallest width that displays full route content."""

MINIMUM_TERMINAL_HEIGHT: Final[int] = 30
"""Smallest height that displays full route content."""


class PlaceholderScreen(Screen[None]):
    """Importable route shell replaced by a use-case screen in later steps."""

    route_id: str = "placeholder"
    route_title: str = "AniShift"

    def compose(self) -> ComposeResult:
        """Keep navigation and safe controls available at every size."""
        with Vertical(classes="route-content"):
            yield Label(self.route_title, classes="route-title")
            yield Static("This workflow arrives in the next implementation step.", classes="placeholder-copy")
            yield Button("Back", id="back", disabled=self.route_id == "workspace")
        yield Static("Terminal must be at least 100x30", classes="small-terminal")
        yield CommandBar()
        yield StatusFooter()

    def on_mount(self) -> None:
        """Apply the initial terminal-size guard."""
        self.apply_terminal_size(self.app.size.width, self.app.size.height)

    def on_resize(self, event: events.Resize) -> None:
        """Replace route content while preserving safe controls below 100x30."""
        self.apply_terminal_size(event.size.width, event.size.height)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Return every non-workspace placeholder to the workspace route."""
        if event.button.id == "back" and self.route_id != "workspace":
            await self.app.switch_screen("workspace")

    def apply_terminal_size(self, width: int, height: int) -> None:
        """Toggle only the central content for terminals smaller than 100x30."""
        is_small: bool = width < MINIMUM_TERMINAL_WIDTH or height < MINIMUM_TERMINAL_HEIGHT
        self.query_one(".route-content", Vertical).display = not is_small
        self.query_one(".small-terminal", Static).display = is_small
