from __future__ import annotations

import asyncio

from textual.widgets import Button, DataTable, Input, Static
from tui_fakes import app_service

from anishift.application.events import RunEvent, RunEventKind
from anishift.application.planning import TaskState
from anishift.tui.app import AniShiftApp
from anishift.tui.messages import RunEventsReceived
from anishift.tui.screens import ExecutionScreen


async def _assert_progress_retry_and_cancel() -> None:
    service = app_service()
    service.cancel.return_value = True
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        app.session.begin_run()
        app.session.active_run_id = "run-1"
        await app.open_route("execution")
        assert isinstance(app.screen, ExecutionScreen)
        app.post_message(
            RunEventsReceived(
                app.session.generation,
                (
                    RunEvent("run-1", 1, RunEventKind.TASK_STARTED, "episode", "translate", TaskState.RUNNING),
                    RunEvent(
                        "run-1",
                        2,
                        RunEventKind.TASK_PROGRESS,
                        "episode",
                        "translate",
                        progress_percent=40,
                    ),
                    RunEvent(
                        "run-1",
                        3,
                        RunEventKind.TASK_RETRY,
                        "episode",
                        "translate",
                        message="retrying provider",
                    ),
                    RunEvent("run-1", 4, RunEventKind.GROUP_FINISHED, "episode", state=TaskState.SUCCEEDED),
                ),
            )
        )
        input_widget = app.screen.query_one("#command-input", Input)
        input_widget.focus()
        await pilot.press(*"hello")
        await pilot.pause()
        assert input_widget.value == "hello"
        assert app.screen.query_one("#task-progress", DataTable).row_count == 1
        assert "retrying provider" in str(app.screen.query_one("#execution-notifications", Static).render())
        await app.open_route("settings")
        await app.open_route("execution")
        assert app.screen.query_one("#task-progress", DataTable).row_count == 1
        assert "retrying provider" in str(app.screen.query_one("#execution-notifications", Static).render())
        app.screen.query_one("#execution-cancel", Button).press()
        await pilot.pause()
        app.screen.query_one("#execution-cancel", Button).press()
        assert service.cancel.call_count == 1


def test_execution_renders_events_without_blocking_input_and_cancels_once() -> None:
    asyncio.run(_assert_progress_retry_and_cancel())
