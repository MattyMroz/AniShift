"""Production Textual shell and route-level command handling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Final

from textual import work
from textual.app import App
from textual.screen import Screen
from textual.timer import Timer

from anishift.application.events import EventBuffer, RunEvent, RunEventKind
from anishift.application.planning import ExecutionPlan
from anishift.application.results import RunResult
from anishift.application.service import AppService
from anishift.tui.commands import ParsedCommand, UiCommand, parse_command
from anishift.tui.messages import CommandSubmitted, RunCompleted, RunEventsReceived
from anishift.tui.screens import (
    AutoScreen,
    ExecutionScreen,
    ManualScreen,
    PreviewScreen,
    ResultsScreen,
    SettingsScreen,
    ToolsScreen,
    WorkspaceScreen,
)
from anishift.tui.state import SessionState
from anishift.tui.widgets import CommandBar, StatusFooter

# ── Constants ────────────────────────────────────────────────────────────────

EVENT_POLL_SECONDS: Final[float] = 0.075
"""UI-thread interval for draining bounded application events."""

FOOTER_REFRESH_SECONDS: Final[float] = 0.25
"""UI refresh interval for the elapsed-time footer segment."""

HELP_TEXT: Final[str] = "Commands: auto, manual, settings, refresh, doctor, setup, help"
"""Stable command vocabulary shown by the help action."""


class AniShiftApp(App[None]):
    """Full-screen presentation shell over one shared application facade."""

    CSS_PATH = "theme.tcss"
    SCREENS: ClassVar[dict[str, Callable[[], Screen[Any]]]] = {
        "workspace": WorkspaceScreen,
        "auto": AutoScreen,
        "manual": ManualScreen,
        "settings": SettingsScreen,
        "preview": PreviewScreen,
        "execution": ExecutionScreen,
        "results": ResultsScreen,
        "tools": ToolsScreen,
    }

    def __init__(self, service: AppService, *, workspace_label: str = "workspace") -> None:
        super().__init__()
        self.service: AppService = service
        self.session: SessionState = SessionState(workspace_label=workspace_label)
        self._event_buffer: EventBuffer | None = None
        self._event_timer: Timer | None = None
        self._footer_timer: Timer | None = None

    async def on_mount(self) -> None:
        """Open the workspace route and install UI-owned timers."""
        await self.push_screen("workspace")
        self._event_timer = self.set_interval(EVENT_POLL_SECONDS, self._drain_events, pause=True)
        self._footer_timer = self.set_interval(FOOTER_REFRESH_SECONDS, self._refresh_footer)
        self._refresh_footer()

    def on_unmount(self) -> None:
        """Stop presentation timers before Textual removes the screen stack."""
        for timer in (self._event_timer, self._footer_timer):
            if timer is not None:
                timer.stop()

    async def on_command_submitted(self, message: CommandSubmitted) -> None:
        """Parse and route one command without leaking behavior into the widget."""
        parsed: ParsedCommand = parse_command(message.value)
        if parsed.error is not None:
            self._set_feedback(parsed.error)
            return
        if parsed.command is None:
            self._set_feedback("")
            return
        await self._dispatch_command(parsed.command)

    def on_run_events_received(self, message: RunEventsReceived) -> None:
        """Accept only events from the active UI generation and run identity."""
        if message.generation != self.session.generation:
            return
        accepted: list[RunEvent] = []
        for event in message.events:
            if self.session.active_run_id is None and event.kind is RunEventKind.RUN_STARTED:
                self.session.active_run_id = event.run_id
            if event.run_id == self.session.active_run_id:
                accepted.append(event)
        if accepted:
            self._refresh_footer()

    def on_run_completed(self, message: RunCompleted) -> None:
        """Close one matching event subscription and expose its terminal state."""
        if message.generation != self.session.generation:
            return
        state: str = "cancelled" if message.result.cancelled else "completed"
        self.session.finish_run(state)
        self._event_buffer = None
        if self._event_timer is not None:
            self._event_timer.pause()
        self._refresh_footer()

    async def start_execution(self, plan: ExecutionPlan) -> bool:
        """Start exactly one blocking application run outside the UI loop."""
        if self.session.run_state in {"running", "cancelling"}:
            return False
        generation: int = self.session.begin_run()
        buffer = EventBuffer()
        self._event_buffer = buffer
        if self._event_timer is not None:
            self._event_timer.resume()
        await self.switch_screen("execution")
        self._refresh_footer()
        self._execute_plan(plan, generation, buffer)
        return True

    def cancel_active_run(self) -> bool:
        """Request cancellation only after the current run ID has been observed."""
        run_id: str | None = self.session.active_run_id
        if run_id is None:
            return False
        cancelled: bool = self.service.cancel(run_id)
        if cancelled:
            self.session.run_state = "cancelling"
            self._refresh_footer()
        return cancelled

    @work(thread=True, exclusive=True, group="application-execution")
    def _execute_plan(self, plan: ExecutionPlan, generation: int, buffer: EventBuffer) -> None:
        result: RunResult = self.service.execute(plan, buffer)
        self.call_from_thread(self._post_completion, generation, result, buffer)

    def _post_completion(self, generation: int, result: RunResult, buffer: EventBuffer) -> None:
        events: tuple[RunEvent, ...] = buffer.drain()
        if events:
            self.post_message(RunEventsReceived(generation, events))
        self.post_message(RunCompleted(generation, result))

    def _drain_events(self) -> None:
        buffer: EventBuffer | None = self._event_buffer
        if buffer is None:
            return
        events: tuple[RunEvent, ...] = buffer.drain()
        if events:
            self.post_message(RunEventsReceived(self.session.generation, events))

    async def _dispatch_command(self, command: UiCommand) -> None:
        routes: dict[UiCommand, str] = {
            UiCommand.AUTO: "auto",
            UiCommand.MANUAL: "manual",
            UiCommand.SETTINGS: "settings",
            UiCommand.DOCTOR: "tools",
            UiCommand.SETUP: "tools",
        }
        if command is UiCommand.HELP:
            self._set_feedback(HELP_TEXT)
            return
        if command is UiCommand.REFRESH:
            await self._switch_route("workspace", "Workspace refresh is available on the Workspace screen.")
            self.session.route = "workspace"
            return
        route: str = routes[command]
        self.session.route = route
        if command is UiCommand.AUTO:
            self.session.mode = "auto"
        elif command is UiCommand.MANUAL:
            self.session.mode = "manual"
        await self._switch_route(route, "")

    async def _switch_route(self, route: str, feedback: str) -> None:
        await self.switch_screen(route)
        self._set_feedback(feedback)
        self._refresh_footer()

    def _set_feedback(self, text: str) -> None:
        self.screen.query_one(CommandBar).set_feedback(text)

    def _refresh_footer(self) -> None:
        self.screen.query_one(StatusFooter).refresh_from_state(self.session)
