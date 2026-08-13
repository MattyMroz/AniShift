"""Live execution progress and cancellation screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from anishift.application.events import RunEvent
from anishift.tui.widgets import CommandBar, StatusFooter
from anishift.tui.widgets.progress_table import ProgressTable

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class ExecutionScreen(Screen[None]):
    """Render the active run without owning its worker or event buffer."""

    def compose(self) -> ComposeResult:
        """Compose progress, idempotent cancellation, and persistent shell."""
        with Vertical(classes="route-content"):
            yield Label("Execution", classes="route-title")
            yield ProgressTable()
            with Horizontal(classes="screen-actions"):
                yield Button("Cancel", id="execution-cancel", variant="error")
            yield Static("", id="execution-feedback")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    def apply_events(self, events: tuple[RunEvent, ...]) -> None:
        """Render the current App-filtered event batch."""
        self.query_one(ProgressTable).apply(events)

    def on_mount(self) -> None:
        """Replay the session projection when returning to an active run."""
        self.apply_events(tuple(self._shell.session.run_events))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Request cancellation without creating a second workflow."""
        if event.button.id != "execution-cancel":
            return
        if self._shell.cancel_active_run():
            event.button.disabled = True
            self.query_one("#execution-feedback", Static).update("Cancellation requested")
