"""Workspace discovery and group selection screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, LoadingIndicator, Static

from anishift.application.cancellation import EventCancellationToken
from anishift.application.inspection import InspectedWorkspace
from anishift.errors import AniShiftError
from anishift.tui.messages import WorkspaceInspected, WorkspaceInspectionFailed
from anishift.tui.screens.base import MINIMUM_TERMINAL_HEIGHT, MINIMUM_TERMINAL_WIDTH
from anishift.tui.state import SessionState
from anishift.tui.widgets import CommandBar, StatusFooter
from anishift.tui.widgets.group_table import GroupSelectionChanged, GroupTable

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class WorkspaceScreen(Screen[None]):
    """Inspect the workspace outside the UI loop and select source groups."""

    def __init__(self) -> None:
        super().__init__()
        self._inspection_cancel: EventCancellationToken | None = None

    def compose(self) -> ComposeResult:
        """Compose group selection, refresh actions, and persistent shell."""
        with Vertical(classes="route-content"):
            yield Label("Workspace", classes="route-title")
            yield GroupTable(self._session.selected_group_ids)
            with Horizontal(classes="screen-actions"):
                yield Button("Refresh", id="refresh-workspace")
                yield Button("Auto", id="open-auto", variant="primary")
                yield Button("Manual", id="open-manual")
            yield LoadingIndicator(id="workspace-loading")
            yield Static("", id="workspace-error")
        yield Static("Terminal must be at least 100x30", classes="small-terminal")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    @property
    def _session(self) -> SessionState:
        return self._shell.session

    def on_mount(self) -> None:
        """Render cached inspection or start the initial refresh."""
        self._apply_size(self.app.size.width, self.app.size.height)
        if self._session.workspace is None:
            self.refresh_workspace()
            return
        self._apply_workspace(self._session.workspace)

    def on_unmount(self) -> None:
        """Invalidate late inspection results after leaving this screen."""
        if self._inspection_cancel is not None:
            self._inspection_cancel.cancel()

    def on_resize(self, event: events.Resize) -> None:
        """Preserve navigation controls in a small terminal."""
        self._apply_size(event.size.width, event.size.height)

    def on_group_selection_changed(self, message: GroupSelectionChanged) -> None:
        """Persist stable IDs for Auto and Manual routes."""
        self._session.selected_group_ids = set(message.group_ids)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Refresh or navigate without starting a plan."""
        if event.button.id == "refresh-workspace":
            self.refresh_workspace()
        elif event.button.id == "open-auto" and self._session.selected_group_ids:
            await self._shell.open_route("auto")
        elif event.button.id == "open-manual" and self._session.selected_group_ids:
            await self._shell.open_route("manual")

    def refresh_workspace(self) -> None:
        """Cancel a previous inspection and start a newer generation."""
        if self._inspection_cancel is not None:
            self._inspection_cancel.cancel()
        self._session.inspection_generation += 1
        generation: int = self._session.inspection_generation
        token = EventCancellationToken()
        self._inspection_cancel = token
        self.query_one("#workspace-loading", LoadingIndicator).display = True
        self.query_one("#workspace-error", Static).update("")
        self._inspect(generation, token)

    @work(thread=True, exclusive=False, group="workspace-inspection")
    def _inspect(self, generation: int, cancel: EventCancellationToken) -> None:
        try:
            workspace: InspectedWorkspace = self._shell.service.discover(cancel=cancel)
        except AniShiftError as error:
            if not cancel.is_cancelled():
                self.app.call_from_thread(self.post_message, WorkspaceInspectionFailed(generation, str(error)))
            return
        self.app.call_from_thread(self.post_message, WorkspaceInspected(generation, workspace))

    def on_workspace_inspected(self, message: WorkspaceInspected) -> None:
        """Accept only the latest still-mounted inspection generation."""
        if message.generation != self._session.inspection_generation or not self.is_mounted:
            return
        self._session.workspace = message.workspace
        self._apply_workspace(message.workspace)

    def on_workspace_inspection_failed(self, message: WorkspaceInspectionFailed) -> None:
        """Render only the latest sanitized inspection failure."""
        if message.generation != self._session.inspection_generation or not self.is_mounted:
            return
        self.query_one("#workspace-loading", LoadingIndicator).display = False
        self.query_one("#workspace-error", Static).update(message.error)

    def _apply_workspace(self, workspace: InspectedWorkspace) -> None:
        self.query_one("#workspace-loading", LoadingIndicator).display = False
        self.query_one(GroupTable).set_groups(workspace.groups)

    def _apply_size(self, width: int, height: int) -> None:
        is_small: bool = width < MINIMUM_TERMINAL_WIDTH or height < MINIMUM_TERMINAL_HEIGHT
        self.query_one(".route-content", Vertical).display = not is_small
        self.query_one(".small-terminal", Static).display = is_small
