from __future__ import annotations

import asyncio

from textual.widgets import Button, DataTable, Input, Static

from scripts.spikes.textual_stage9 import (
    CANCEL_BUTTON_ID,
    COMMAND_INPUT_ID,
    CONTENT_ID,
    GROUP_COUNT,
    GROUP_TABLE_ID,
    MANUAL_BUTTON_ID,
    MANUAL_FORM_ID,
    MANUAL_VALUE_ID,
    RUN_BUTTON_ID,
    SMALL_TERMINAL_ID,
    STATUS_ID,
    Stage9SpikeApp,
)


async def _assert_workspace_and_manual_form() -> None:
    app = Stage9SpikeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        table = app.query_one(f"#{GROUP_TABLE_ID}", DataTable)
        assert table.row_count == GROUP_COUNT
        await pilot.click(f"#{MANUAL_BUTTON_ID}")
        assert app.screen.query_one(f"#{MANUAL_FORM_ID}")
        manual_value = app.screen.query_one(f"#{MANUAL_VALUE_ID}", Input)
        manual_value.value = "sidecar:fra"
        assert manual_value.value == "sidecar:fra"


def test_spike_renders_workspace_and_edits_manual_form() -> None:
    asyncio.run(_assert_workspace_and_manual_form())


async def _assert_command_refresh() -> None:
    app = Stage9SpikeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        command_input = app.query_one(f"#{COMMAND_INPUT_ID}", Input)
        command_input.focus()
        await pilot.press(*"refresh", "enter")
        assert app.refresh_count == 1
        assert "refreshes: 1" in str(app.query_one(f"#{STATUS_ID}", Static).render())


def test_spike_executes_refresh_from_command_bar() -> None:
    asyncio.run(_assert_command_refresh())


async def _assert_worker_responsiveness_and_cancel() -> None:
    app = Stage9SpikeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click(f"#{RUN_BUTTON_ID}")
        command_input = app.query_one(f"#{COMMAND_INPUT_ID}", Input)
        command_input.focus()
        await pilot.press(*"hello")
        assert command_input.value == "hello"
        await pilot.click(f"#{CANCEL_BUTTON_ID}")
        await pilot.pause(0.05)
        assert app.active_worker_count == 0
        assert app.query_one(f"#{RUN_BUTTON_ID}", Button).disabled is False
        assert app.query_one(f"#{CANCEL_BUTTON_ID}", Button).disabled is True
        assert "cancelled" in str(app.query_one(f"#{STATUS_ID}", Static).render())


def test_spike_keeps_input_responsive_and_cancels_worker() -> None:
    asyncio.run(_assert_worker_responsiveness_and_cancel())


async def _assert_small_terminal_state() -> None:
    app = Stage9SpikeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.resize_terminal(80, 24)
        assert app.query_one(f"#{CONTENT_ID}").display is False
        warning = app.query_one(f"#{SMALL_TERMINAL_ID}", Static)
        assert warning.display is True
        assert "100x30" in str(warning.render())
        assert app.query_one(f"#{COMMAND_INPUT_ID}").display is True
        assert app.query_one(f"#{STATUS_ID}").display is True


def test_spike_preserves_safe_controls_below_minimum_size() -> None:
    asyncio.run(_assert_small_terminal_state())


async def _assert_double_start_is_blocked() -> None:
    app = Stage9SpikeApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.click(f"#{RUN_BUTTON_ID}", times=2)
        assert app.run_start_count == 1
        await pilot.click(f"#{CANCEL_BUTTON_ID}")
        await pilot.pause(0.05)


def test_spike_blocks_double_start() -> None:
    asyncio.run(_assert_double_start_is_blocked())
