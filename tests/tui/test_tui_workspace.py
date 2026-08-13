from __future__ import annotations

import asyncio
from threading import Event, Lock
from unittest.mock import Mock

from textual.widgets import Button, Input, SelectionList
from tui_fakes import app_service, inspected_workspace

from anishift.application.inspection import InspectedWorkspace
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import WorkspaceScreen


async def _assert_workspace_selection_refresh_filter(service: Mock) -> None:
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, WorkspaceScreen)
        selection = app.screen.query_one("#group-selection", SelectionList)
        assert selection.option_count == 20
        assert len(selection.selected) == 20
        selection.deselect_all()
        selection.select("episode-01")
        selection.select("episode-02")
        await pilot.pause()
        assert app.session.selected_group_ids == {"episode-01", "episode-02"}
        filter_input = app.screen.query_one("#group-filter", Input)
        filter_input.value = "20"
        await pilot.pause()
        assert selection.option_count == 1
        assert app.session.selected_group_ids == {"episode-01", "episode-02"}
        selection.select("episode-20")
        await pilot.pause()
        assert app.session.selected_group_ids == {"episode-01", "episode-02", "episode-20"}
        app.screen.refresh_workspace()
        await pilot.pause(0.2)
        assert app.session.selected_group_ids == {"episode-01", "episode-02", "episode-20"}
        assert service.discover.call_count == 2


def test_workspace_handles_twenty_groups_and_preserves_selection() -> None:
    asyncio.run(_assert_workspace_selection_refresh_filter(app_service()))


async def _assert_inspection_does_not_block_input(service: Mock) -> None:
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        input_widget = app.screen.query_one("#command-input", Input)
        input_widget.focus()
        await pilot.press(*"hello")
        assert input_widget.value == "hello"


def test_workspace_inspection_keeps_command_input_responsive() -> None:
    asyncio.run(_assert_inspection_does_not_block_input(app_service()))


async def _assert_stale_inspection_is_ignored() -> None:
    service = app_service()
    old_workspace = inspected_workspace(1)
    new_workspace = inspected_workspace(2)
    entered = Event()
    release = Event()
    call_lock = Lock()
    call_number = 0

    def discover(*, cancel: object) -> InspectedWorkspace:
        del cancel
        nonlocal call_number
        with call_lock:
            call_number += 1
            current = call_number
        if current == 1:
            entered.set()
            release.wait(timeout=2)
            return old_workspace
        return new_workspace

    service.discover.side_effect = discover
    app = AniShiftApp(service)
    async with app.run_test(size=(120, 36)) as pilot:
        for _ in range(20):
            if entered.is_set():
                break
            await pilot.pause(0.01)
        assert entered.is_set()
        app.screen.query_one("#refresh-workspace", Button).press()
        await pilot.pause(0.1)
        release.set()
        await pilot.pause(0.1)
        assert app.session.workspace is new_workspace
        assert app.screen.query_one("#group-selection", SelectionList).option_count == 2


def test_workspace_ignores_an_older_refresh_result() -> None:
    asyncio.run(_assert_stale_inspection_is_ignored())
