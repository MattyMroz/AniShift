from __future__ import annotations

import asyncio
from threading import Event
from typing import cast
from unittest.mock import Mock

from textual.widgets import Input, Static

from anishift.application.events import RunEvent, RunEventKind, RunEventSink
from anishift.application.inspection import InspectedWorkspace
from anishift.application.intents import AutoPreset, ProductIntent, ProductKind
from anishift.application.planning import ExecutionPlan
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.application.service import AppService, EngineAvailability
from anishift.config.field_catalog import setting_catalog
from anishift.config.user_settings import UserSettings
from anishift.tui.app import AniShiftApp
from anishift.tui.messages import RunEventsReceived
from anishift.tui.screens import AutoScreen, ManualScreen, ResultsScreen, SettingsScreen, ToolsScreen, WorkspaceScreen
from anishift.tui.widgets.command_bar import (
    COMMAND_FEEDBACK_ID,
    COMMAND_INPUT_ID,
    COMMAND_PROMPT,
    STATUS_FOOTER_ID,
)


def _service() -> Mock:
    service = Mock(spec=AppService)
    service.discover.return_value = InspectedWorkspace((), ())
    preset = AutoPreset("default", "Default", ProductIntent(frozenset({ProductKind.FULL_PL})))
    service.list_presets.return_value = (preset,)
    service.get_preset.return_value = preset
    service.settings_snapshot.return_value = UserSettings()
    service.settings_catalog.return_value = setting_catalog()
    service.environment_statuses.return_value = {}
    service.engine_availability.return_value = (EngineAvailability("translation", "google", True, "ready"),)
    service.doctor.return_value = ()
    service.setup.return_value = ()
    return service


def _rendered(widget: Static) -> str:
    return str(widget.render())


class _RecordingApp(AniShiftApp):
    CSS_PATH = "../../anishift/tui/theme.tcss"

    def __init__(self, service: AppService) -> None:
        super().__init__(service)
        self.accepted_event_batches: list[tuple[RunEvent, ...]] = []

    def on_run_events_received(self, message: RunEventsReceived) -> None:
        self.accepted_event_batches.append(message.events)
        super().on_run_events_received(message)


async def _submit(app: AniShiftApp, pilot: object, command: str) -> None:
    input_widget = app.screen.query_one(f"#{COMMAND_INPUT_ID}", Input)
    input_widget.focus()
    await pilot.press(*command, "enter")  # type: ignore[attr-defined]


async def _assert_routes_and_persistent_shell() -> None:
    service = _service()
    app = AniShiftApp(service, workspace_label="episodes")
    async with app.run_test(size=(100, 30)) as pilot:
        assert isinstance(app.screen, WorkspaceScreen)
        assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
        assert "workspace: episodes" in _rendered(app.screen.query_one(f"#{STATUS_FOOTER_ID}", Static))
        await _submit(app, pilot, "auto")
        assert isinstance(app.screen, AutoScreen)
        assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
        assert "mode: auto" in _rendered(app.screen.query_one(f"#{STATUS_FOOTER_ID}", Static))
        await _submit(app, pilot, "manual")
        assert isinstance(app.screen, ManualScreen)
        assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
        assert "mode: manual" in _rendered(app.screen.query_one(f"#{STATUS_FOOTER_ID}", Static))
        await _submit(app, pilot, "settings")
        assert isinstance(app.screen, SettingsScreen)
        assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
        await _submit(app, pilot, "doctor")
        assert isinstance(app.screen, ToolsScreen)
        assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
        await _submit(app, pilot, "setup")
        assert isinstance(app.screen, ToolsScreen)
        await _submit(app, pilot, "refresh")
        assert isinstance(app.screen, WorkspaceScreen)
        await pilot.pause()
        assert service.discover.call_count == 2
        await _submit(app, pilot, "help")
        feedback = app.screen.query_one(f"#{COMMAND_FEEDBACK_ID}", Static)
        assert "Commands: auto, manual" in _rendered(feedback)
        service.doctor.assert_called_once()
        service.setup.assert_called_once_with(force=False)


def test_commands_route_without_calling_application_workflows() -> None:
    asyncio.run(_assert_routes_and_persistent_shell())


async def _assert_every_route_keeps_the_shell() -> None:
    service = _service()
    app = AniShiftApp(service)
    async with app.run_test(size=(100, 30)):
        for route in ("settings", "execution", "results", "tools"):
            await app.switch_screen(route)
            assert COMMAND_PROMPT in _rendered(app.screen.query_one("#command-prompt", Static))
            assert app.screen.query_one(f"#{STATUS_FOOTER_ID}", Static).display is True


def test_every_route_keeps_command_bar_and_footer() -> None:
    asyncio.run(_assert_every_route_keeps_the_shell())


async def _assert_invalid_empty_and_double_submit() -> None:
    service = _service()
    app = AniShiftApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        await _submit(app, pilot, "setings")
        feedback = app.screen.query_one(f"#{COMMAND_FEEDBACK_ID}", Static)
        assert "Did you mean 'settings'?" in _rendered(feedback)
        await _submit(app, pilot, "")
        assert _rendered(feedback) == ""
        await _submit(app, pilot, "auto")
        await _submit(app, pilot, "")
        assert isinstance(app.screen, AutoScreen)
        service.plan_auto.assert_not_called()
        service.plan_manual.assert_not_called()


def test_invalid_empty_and_repeated_submit_remain_safe() -> None:
    asyncio.run(_assert_invalid_empty_and_double_submit())


async def _assert_small_terminal_keeps_command_and_footer() -> None:
    app = AniShiftApp(_service())
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.resize_terminal(80, 24)
        assert app.screen.query_one(".route-content").display is False
        warning = app.screen.query_one(".small-terminal", Static)
        assert warning.display is True
        assert "100x30" in _rendered(warning)
        assert app.screen.query_one(f"#{COMMAND_INPUT_ID}", Input).display is True
        footer = app.screen.query_one(f"#{STATUS_FOOTER_ID}", Static)
        assert footer.display is True
        assert "run: idle" in _rendered(footer)
        await _submit(app, pilot, "help")
        assert "Commands:" in _rendered(app.screen.query_one(f"#{COMMAND_FEEDBACK_ID}", Static))


def test_small_terminal_preserves_safe_controls() -> None:
    asyncio.run(_assert_small_terminal_keeps_command_and_footer())


async def _assert_execution_is_single_and_input_remains_responsive() -> None:
    service = _service()
    release = Event()

    def execute(_plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        sink.emit(RunEvent("run-1", 1, RunEventKind.RUN_STARTED))
        release.wait(timeout=5)
        return RunResult("run-1", (GroupResult("episode", GroupStatus.SUCCEEDED),))

    service.execute.side_effect = execute
    service.cancel.return_value = True
    app = AniShiftApp(service)
    plan = cast(ExecutionPlan, Mock(spec=ExecutionPlan))
    async with app.run_test(size=(100, 30)) as pilot:
        assert await app.start_execution(plan) is True
        assert await app.start_execution(plan) is False
        command_input = app.screen.query_one(f"#{COMMAND_INPUT_ID}", Input)
        command_input.focus()
        await pilot.press(*"hello")
        assert command_input.value == "hello"
        app.session.active_run_id = "run-1"
        assert app.cancel_active_run() is True
        assert await app.start_execution(plan) is False
        release.set()
        await pilot.pause(0.2)
        assert app.session.run_state == "completed"
        assert service.execute.call_count == 1


def test_execution_blocks_double_start_without_blocking_input() -> None:
    asyncio.run(_assert_execution_is_single_and_input_remains_responsive())


async def _assert_fast_run_drains_state_events_before_completion() -> None:
    service = _service()

    def execute(_plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        sink.emit(RunEvent("run-fast", 1, RunEventKind.RUN_STARTED))
        sink.emit(RunEvent("run-fast", 2, RunEventKind.RUN_FINISHED))
        return RunResult("run-fast", (GroupResult("episode", GroupStatus.SUCCEEDED),))

    service.execute.side_effect = execute
    app = _RecordingApp(service)
    plan = cast(ExecutionPlan, Mock(spec=ExecutionPlan))
    async with app.run_test(size=(100, 30)) as pilot:
        assert await app.start_execution(plan) is True
        await pilot.pause(0.2)
        assert tuple(event.kind for batch in app.accepted_event_batches for event in batch) == (
            RunEventKind.RUN_STARTED,
            RunEventKind.RUN_FINISHED,
        )
        assert app.session.run_state == "completed"


def test_fast_run_drains_state_events_before_completion() -> None:
    asyncio.run(_assert_fast_run_drains_state_events_before_completion())


async def _assert_worker_failure_recovers_shell() -> None:
    service = _service()

    def fail(_plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        sink.emit(RunEvent("run-failed", 1, RunEventKind.RUN_STARTED))
        raise RuntimeError(r'failed C:\Users\name\Episode.mkv token="secret"')

    service.execute.side_effect = fail
    app = AniShiftApp(service)
    app.session.run_result = RunResult("old", (GroupResult("old-group", GroupStatus.SUCCEEDED),))
    plan = cast(ExecutionPlan, Mock(spec=ExecutionPlan))
    async with app.run_test(size=(100, 30)) as pilot:
        assert await app.start_execution(plan) is True
        await pilot.pause(0.2)
        assert app.session.run_state == "failed"
        assert app.session.run_result is None
        assert app.session.run_error == "failed <path> token=<redacted>"
        assert isinstance(app.screen, ResultsScreen)
        assert "failed <path> token=<redacted>" in _rendered(app.screen.query_one("#result-details", Static))


def test_unexpected_worker_failure_returns_to_results_safely() -> None:
    asyncio.run(_assert_worker_failure_recovers_shell())
