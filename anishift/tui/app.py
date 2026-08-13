"""Production Textual shell and route-level command handling."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Final

from textual import work
from textual.app import App
from textual.screen import Screen
from textual.timer import Timer

from anishift.application.events import EventBuffer, RunEvent, RunEventKind, sanitize_event_message
from anishift.application.planning import ExecutionPlan
from anishift.application.results import RunResult
from anishift.application.service import AppService
from anishift.tui.commands import ParsedCommand, UiCommand, parse_command
from anishift.tui.messages import CommandSubmitted, RunCompleted, RunEventsReceived, RunFailed
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
            self.session.run_events.extend(accepted)
            if isinstance(self.screen, ExecutionScreen):
                self.screen.apply_events(tuple(accepted))
            self._refresh_footer()

    def on_run_completed(self, message: RunCompleted) -> None:
        """Close one matching event subscription and expose its terminal state."""
        if message.generation != self.session.generation:
            return
        state: str = "cancelled" if message.result.cancelled else "completed"
        self.session.run_result = message.result
        self.session.finish_run(state)
        self._event_buffer = None
        if self._event_timer is not None:
            self._event_timer.pause()
        self._refresh_footer()
        if self.screen_stack:
            self.call_later(self.open_route, "results")

    def on_run_failed(self, message: RunFailed) -> None:
        """Recover the shell when execution fails before producing a RunResult."""
        if message.generation != self.session.generation:
            return
        self.session.run_error = message.error
        self.session.finish_run("failed")
        self._event_buffer = None
        if self._event_timer is not None:
            self._event_timer.pause()
        self.call_later(self.open_route, "results")
        self.notify(message.error, severity="error")

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
        try:
            result: RunResult = self.service.execute(plan, buffer)
        except Exception as error:  # noqa: BLE001 - process boundary must recover the interactive shell
            message: str = sanitize_event_message(str(error)) or type(error).__name__
            self.call_from_thread(self._post_failure, generation, message, buffer)
            return
        self.call_from_thread(self._post_completion, generation, result, buffer)

    def _post_completion(self, generation: int, result: RunResult, buffer: EventBuffer) -> None:
        events: tuple[RunEvent, ...] = buffer.drain()
        if events:
            self.post_message(RunEventsReceived(generation, events))
        self.post_message(RunCompleted(generation, result))

    def _post_failure(self, generation: int, error: str, buffer: EventBuffer) -> None:
        events: tuple[RunEvent, ...] = buffer.drain()
        if events:
            self.post_message(RunEventsReceived(generation, events))
        self.post_message(RunFailed(generation, error))

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
            had_workspace: bool = self.session.workspace is not None
            await self._switch_route("workspace", "")
            if had_workspace and isinstance(self.screen, WorkspaceScreen):
                self.screen.refresh_workspace()
            self.session.route = "workspace"
            return
        if command in {UiCommand.DOCTOR, UiCommand.SETUP}:
            if isinstance(self.screen, ToolsScreen):
                self.screen.run_tool(command.value)
                return
            self.session.pending_tool_action = command.value
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

    async def open_route(self, route: str) -> None:
        """Navigate from a screen action through the same route state as commands."""
        self.session.route = route
        if route in {"auto", "manual"}:
            self.session.mode = route
        await self._switch_route(route, "")

    def _set_feedback(self, text: str) -> None:
        self.screen.query_one(CommandBar).set_feedback(text)

    def _refresh_footer(self) -> None:
        if self.screen_stack:
            footer = self.screen.query_one_optional(StatusFooter)
            if footer is not None:
                footer.refresh_from_state(self.session)
