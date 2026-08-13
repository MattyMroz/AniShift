"""Non-blocking doctor and external-resource setup tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Static

from anishift.setup.doctor import CheckResult
from anishift.setup.installer import ResourceResult
from anishift.tui.widgets import CommandBar, StatusFooter

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class ToolsScreen(Screen[None]):
    """Run diagnostics and setup through the shared application facade."""

    def __init__(self) -> None:
        super().__init__()
        self._generation: int = 0

    def compose(self) -> ComposeResult:
        """Compose explicit actions and one ordered result table."""
        with Vertical(classes="route-content"):
            yield Label("Tools", classes="route-title")
            with Horizontal(classes="screen-actions"):
                yield Button("Doctor", id="tools-doctor", variant="primary")
                yield Button("Setup", id="tools-setup")
                yield Button("Force setup", id="tools-force-setup", variant="warning")
                yield Button("Back", id="back")
            yield DataTable(id="tools-results", zebra_stripes=True)
            yield Static("", id="tools-feedback")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    def on_mount(self) -> None:
        """Create result columns and consume a command-routed tool action once."""
        self.query_one("#tools-results", DataTable).add_columns("Name", "Status", "Message", "Suggestion")
        action: str | None = self._shell.session.pending_tool_action
        self._shell.session.pending_tool_action = None
        if action is not None:
            self.run_tool(action)

    def run_tool(self, action: str) -> None:
        """Run a command-routed action through the same worker as buttons."""
        self._generation += 1
        generation: int = self._generation
        if action == "doctor":
            self._run_doctor(generation)
        elif action == "setup":
            self._run_setup(False, generation)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Run one explicit tool action without blocking the UI loop."""
        if event.button.id == "back":
            await self._shell.open_route("workspace")
        elif event.button.id == "tools-doctor":
            self.run_tool("doctor")
        elif event.button.id in {"tools-setup", "tools-force-setup"}:
            self._generation += 1
            self._run_setup(event.button.id == "tools-force-setup", self._generation)

    @work(thread=True, exclusive=True, group="technical-tools")
    def _run_doctor(self, generation: int) -> None:
        results: tuple[CheckResult, ...] = self._shell.service.doctor()
        self.app.call_from_thread(self._show_doctor, generation, results)

    @work(thread=True, exclusive=True, group="technical-tools")
    def _run_setup(self, force: bool, generation: int) -> None:
        results: tuple[ResourceResult, ...] = self._shell.service.setup(force=force)
        self.app.call_from_thread(self._show_setup, generation, results)

    def _show_doctor(self, generation: int, results: tuple[CheckResult, ...]) -> None:
        if generation != self._generation or not self.is_mounted:
            return
        table = self.query_one("#tools-results", DataTable)
        table.clear()
        for result in results:
            table.add_row(result.name, result.status.value, result.message, result.suggestion)
        self.query_one("#tools-feedback", Static).update("Doctor completed")

    def _show_setup(self, generation: int, results: tuple[ResourceResult, ...]) -> None:
        if generation != self._generation or not self.is_mounted:
            return
        table = self.query_one("#tools-results", DataTable)
        table.clear()
        for result in results:
            table.add_row(result.name, result.outcome, result.detail, "")
        self.query_one("#tools-feedback", Static).update("Setup completed")
