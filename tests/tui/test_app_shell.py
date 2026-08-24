from __future__ import annotations

import ast
import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.widgets import Static

import anishift.tui
from anishift.application import RunEvent, RunEventKind
from anishift.tui.app import (
    FULL_LAYOUT_MIN_HEIGHT,
    FULL_LAYOUT_MIN_WIDTH,
    AniShiftApp,
    is_compact,
)
from anishift.tui.brand import WORDMARK
from anishift.tui.lifecycle import begin_planning, begin_run
from anishift.tui.messages import (
    NavigationRequested,
    PlanFailed,
    RunFailed,
    RunProgressed,
    WorkspaceFailed,
)
from anishift.tui.screens.workspace import EMPTY_WORKSPACE_TEXT, WorkspaceView, workspace_body
from anishift.tui.state import GroupIntentDraft, RunUiState, SessionState, UiRoute
from anishift.tui.widgets.footer import footer_text

_FRAME_IDS: Final[tuple[str, ...]] = (
    "#app-brand",
    "#app-header",
    "#app-content",
    "#app-composer",
    "#app-footer",
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SMALL_SIZE: Final[tuple[int, int]] = (80, 24)

_FORBIDDEN_IMPORTS: Final[tuple[str, ...]] = (
    "anishift.services",
    "anishift.pipeline",
    "anishift.application.service",
    "anishift.application.runtime",
)


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _event(sequence: int) -> RunEvent:
    return RunEvent(run_id="run-1", sequence=sequence, kind=RunEventKind.TASK_QUEUED)


def _imported_modules(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def _shell_sources() -> list[Path]:
    root: Path = Path(anishift.tui.__file__).parent
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def test_layout_threshold_matches_the_full_terminal_size() -> None:
    assert (FULL_LAYOUT_MIN_WIDTH, FULL_LAYOUT_MIN_HEIGHT) == _FULL_SIZE
    assert is_compact(width=100, height=30) is False
    assert is_compact(width=99, height=30) is True
    assert is_compact(width=100, height=29) is True


def test_footer_projects_only_counts_and_the_run_state() -> None:
    state: SessionState = SessionState()
    state.selected_group_ids = {"ep01", "ep02"}
    assert footer_text(state) == "workspace: 0 · selected: 2 · run: idle"


def test_footer_projection_never_leaks_a_path() -> None:
    state: SessionState = SessionState()
    state.error_message = "C:/Users/secret/workspace/ep01.mkv"
    assert "secret" not in footer_text(state)


def test_workspace_body_shows_the_base_state_without_sources() -> None:
    assert workspace_body(None) == EMPTY_WORKSPACE_TEXT


def test_shell_modules_import_no_backend_module() -> None:
    offenders: list[str] = [
        f"{path.name}:{module}"
        for path in _shell_sources()
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if module.startswith(_FORBIDDEN_IMPORTS)
    ]
    assert offenders == []


def test_the_import_guard_flags_a_backend_import() -> None:
    assert [
        module
        for module in _imported_modules("from anishift.application.service import AppService\n")
        if module.startswith(_FORBIDDEN_IMPORTS)
    ] == ["anishift.application.service"]


def test_shell_mounts_the_fixed_frame_without_a_backend() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for frame_id in _FRAME_IDS:
                assert app.query_one(frame_id) is not None
            assert app.session_state.route is UiRoute.WORKSPACE
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_shell_shows_the_workspace_base_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view: WorkspaceView = app.query_one(WorkspaceView)
            assert view.content == EMPTY_WORKSPACE_TEXT
            assert view.display is True

    _run(scenario())


def test_shell_shows_the_full_wordmark_and_footer_projection() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact") is False
            assert app.query_one("#app-brand", Static).display is True
            assert app.query_one("#app-footer", Static).content == footer_text(app.session_state)
            assert app.query_one("#app-header", Static).content == "workspace"

    _run(scenario())


def test_shrinking_the_terminal_keeps_every_fixed_region_mounted() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            regions: dict[str, object] = {frame_id: app.query_one(frame_id) for frame_id in _FRAME_IDS}
            state: SessionState = app.session_state
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert app.screen.has_class("compact") is True
            assert all(app.query_one(frame_id) is regions[frame_id] for frame_id in _FRAME_IDS)
            assert app.session_state is state

    _run(scenario())


def test_shrinking_the_terminal_switches_to_the_compact_wordmark() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            brand: Static = app.query_one("#app-brand", Static)
            assert str(brand.content) == WORDMARK

    _run(scenario())


def test_growing_the_terminal_restores_the_full_layout() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_SMALL_SIZE) as pilot:
            await pilot.pause()
            assert app.screen.has_class("compact") is True
            await pilot.resize_terminal(*_FULL_SIZE)
            await pilot.pause()
            assert app.screen.has_class("compact") is False

    _run(scenario())


def test_navigation_moves_the_route_and_hides_the_workspace_view() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(NavigationRequested(UiRoute.AUTO))
            await pilot.pause()
            assert app.session_state.route is UiRoute.AUTO
            assert app.query_one("#app-header", Static).content == "auto"
            assert app.query_one(WorkspaceView).display is False

    _run(scenario())


def test_navigation_keeps_the_drafts_of_the_session() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            draft: GroupIntentDraft = GroupIntentDraft(group_id="ep01", products=set())
            app.session_state.manual_drafts["ep01"] = draft
            app.post_message(NavigationRequested(UiRoute.MANUAL))
            await pilot.pause()
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert app.session_state.manual_drafts["ep01"] is draft

    _run(scenario())


def test_a_late_run_event_of_an_old_generation_changes_nothing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            assert begin_run(app.session_state, "run-1") is True
            app.post_message(RunProgressed(events=(_event(1),), run_id="run-1", generation=generation - 1))
            await pilot.pause()
            assert app.session_state.run_events == []
            app.post_message(RunProgressed(events=(_event(2),), run_id="run-1", generation=generation))
            await pilot.pause()
            assert [event.sequence for event in app.session_state.run_events] == [2]

    _run(scenario())


def test_a_run_event_of_another_run_changes_nothing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            assert begin_run(app.session_state, "run-1") is True
            app.post_message(RunProgressed(events=(_event(1),), run_id="run-2", generation=generation))
            await pilot.pause()
            assert app.session_state.run_events == []

    _run(scenario())


def test_a_late_failure_of_an_old_generation_never_reaches_the_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.post_message(WorkspaceFailed(reason="Skanowanie nie powiodło się", generation=-1))
            app.post_message(PlanFailed(reason="Nie ukończono", generation=-1))
            app.post_message(RunFailed(reason="Nie ukończono", run_id="run-1", generation=-1))
            await pilot.pause()
            assert app.session_state.error_message is None
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_a_failure_of_the_current_generation_reaches_the_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int = app.session_state.generation
            app.post_message(WorkspaceFailed(reason="Skanowanie nie powiodło się", generation=generation))
            await pilot.pause()
            assert app.session_state.error_message == "Skanowanie nie powiodło się"

    _run(scenario())


@pytest.mark.parametrize("size", [_FULL_SIZE, _SMALL_SIZE])
def test_shell_mounts_at_both_canonical_sizes(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#app-composer") is not None
            assert app.query_one("#app-footer", Static).content == footer_text(app.session_state)

    _run(scenario())
