from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, DataTable, Select, Static
from tui_fakes import app_service, inspected_workspace

from anishift.application.results import GroupResult, GroupStatus, ProducedArtifact, RunResult
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import ManualScreen, ResultsScreen


def _result() -> RunResult:
    product = ProducedArtifact("product", Path("workspace/Episode.pl.srt"), {})
    return RunResult(
        "run-1",
        (
            GroupResult("episode-01", GroupStatus.SUCCEEDED, products=(product,)),
            GroupResult("episode-02", GroupStatus.PARTIAL, products=(product,), error_messages=("TTS failed",)),
            GroupResult("episode-03", GroupStatus.FAILED, error_messages=("Translation failed",)),
            GroupResult("episode-04", GroupStatus.CANCELLED, error_messages=("Cancelled",)),
        ),
        ("Cleanup warning",),
    )


async def _assert_results_filter_and_manual_recovery() -> None:
    app = AniShiftApp(app_service())
    app.session.workspace = inspected_workspace(4)
    app.session.run_result = _result()
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("results")
        assert isinstance(app.screen, ResultsScreen)
        table = app.screen.query_one("#results-groups", DataTable)
        assert table.row_count == 4
        assert "Cleanup warning" in str(app.screen.query_one("#results-warnings", Static).render())
        app.screen.query_one("#results-filter", Select).value = GroupStatus.PARTIAL
        await pilot.pause()
        assert table.row_count == 1
        app.screen.query_one("#result-manual", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ManualScreen)
        assert app.session.selected_group_ids == {"episode-02"}


async def _assert_empty_filter_manual_is_safe() -> None:
    app = AniShiftApp(app_service())
    app.session.run_result = RunResult(
        "run-1",
        (GroupResult("episode-01", GroupStatus.SUCCEEDED),),
    )
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("results")
        app.screen.query_one("#results-filter", Select).value = GroupStatus.FAILED
        await pilot.pause()
        app.screen.query_one("#result-manual", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ResultsScreen)


def test_results_render_all_statuses_and_open_non_success_in_manual() -> None:
    asyncio.run(_assert_results_filter_and_manual_recovery())


def test_open_manual_is_safe_when_filter_has_no_rows() -> None:
    asyncio.run(_assert_empty_filter_manual_is_safe())
