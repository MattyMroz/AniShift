from __future__ import annotations

import asyncio
from threading import Event

from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Input
from tui_fakes import app_service

from anishift.setup.doctor import CheckResult, CheckStatus
from anishift.setup.installer import ResourceResult
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import ToolsScreen


async def _submit(app: AniShiftApp, pilot: object, command: str) -> None:
    input_widget = app.screen.query_one("#command-input", Input)
    input_widget.focus()
    await pilot.press(*command, "enter")  # type: ignore[attr-defined]


async def _assert_tools_buttons_and_commands() -> None:
    service = app_service()
    service.doctor.return_value = (CheckResult("python", CheckStatus.OK, "Python ready"),)
    service.setup.return_value = (ResourceResult("ffmpeg", "installed", "verified"),)
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        await _submit(app, pilot, "doctor")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ToolsScreen)
        assert app.screen.query_one("#tools-results", DataTable).row_count == 1
        service.doctor.assert_called_once()
        await _submit(app, pilot, "setup")
        for _ in range(20):
            if service.setup.called:
                break
            await pilot.pause(0.05)
        assert isinstance(app.screen, ToolsScreen)
        service.setup.assert_called_once_with(force=False)
        app.screen.query_one("#tools-force-setup", Button).press()
        await pilot.pause(0.2)
        service.setup.assert_called_with(force=True)


def test_tools_commands_and_buttons_share_nonblocking_facade_actions() -> None:
    asyncio.run(_assert_tools_buttons_and_commands())


async def _assert_late_tool_result_is_ignored() -> None:
    service = app_service()
    release = Event()

    def doctor() -> tuple[CheckResult, ...]:
        release.wait(timeout=5)
        return (CheckResult("old-doctor", CheckStatus.OK, "Old"),)

    service.doctor.side_effect = doctor
    service.setup.return_value = (ResourceResult("ffmpeg", "installed", "verified"),)
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("tools")
        screen = app.screen
        assert isinstance(screen, ToolsScreen)
        screen.run_tool("doctor")
        screen.run_tool("setup")
        await pilot.pause(0.1)
        release.set()
        await pilot.pause(0.2)
        table = app.screen.query_one("#tools-results", DataTable)
        assert str(table.get_cell_at(Coordinate(0, 0))) == "ffmpeg"


def test_tools_ignore_result_from_superseded_worker() -> None:
    asyncio.run(_assert_late_tool_result_is_ignored())
