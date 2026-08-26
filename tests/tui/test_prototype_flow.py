from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.widgets import Static

from anishift.tui import ui_state
from anishift.tui.app import THEME_ROWS, AniShiftApp
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.prototype import PrototypeApp, demo_rows, working_status
from anishift.tui.screens.workspace import WORKSPACE_ID, GroupState, group_line, groups_body, state_text
from anishift.tui.state import RunUiState
from anishift.tui.strings import (
    CONTEXT_MODE_DEMO,
    DEMO_TITLE,
    RUN_DONE,
    RUN_PLANNING,
    WORKSPACE_EMPTY,
)
from anishift.tui.theme import DARK_THEME_ID, THEME_IDS
from anishift.tui.ui_state import load_ui_state
from anishift.tui.widgets.composer import CONTEXT_ID

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SMALL_SIZE: Final[tuple[int, int]] = (80, 24)

_BOTH_SIZES: Final[tuple[tuple[int, int], ...]] = (_FULL_SIZE, _SMALL_SIZE)

_FAST_STEP: Final[float] = 0.01

_HELD_STEP: Final[float] = 60.0

_PAUSE_LIMIT: Final[int] = 400

_SETTLE_PAUSES: Final[int] = 30

_ON_SCREEN_IDS: Final[tuple[str, ...]] = ("#app-body", "#app-content", "#app-composer", "#app-footer")


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target: Path = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


def test_the_launcher_injects_the_simulated_sequence() -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_HELD_STEP)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.title == DEMO_TITLE
            assert CONTEXT_MODE_DEMO in _text(app, f"#{CONTEXT_ID}")

    _run(scenario())


@pytest.mark.parametrize("size", _BOTH_SIZES)
def test_the_prototype_opens_on_the_start_screen(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_HELD_STEP)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.query_one("#app-brand").display
            assert not app.query_one(f"#{WORKSPACE_ID}").display
            _assert_on_screen(app, size)

    _run(scenario())


@pytest.mark.parametrize("size", _BOTH_SIZES)
def test_one_empty_enter_walks_the_work_screen_to_a_result(size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_FAST_STEP)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert app.session_state.generation == 1
            assert app.session_state.run_state is RunUiState.TERMINAL
            assert not app.query_one("#app-brand").display
            assert app.query_one(f"#{WORKSPACE_ID}").display
            assert RUN_DONE in _text(app, f"#{WORKSPACE_ID}")
            _assert_on_screen(app, size)

    _run(scenario())


def test_the_result_covers_every_selected_group() -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_FAST_STEP)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.result is not None)
            result = app.session_state.result
            assert result is not None
            assert [group.group_id for group in result.groups] == [row.name for row in demo_rows() if row.selected]

    _run(scenario())


def test_a_second_enter_during_the_sequence_starts_no_second_run() -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_HELD_STEP)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for _ in range(4):
                await pilot.press("enter")
                await pilot.pause()
            assert app.session_state.generation == 1
            assert app.session_state.run_state is RunUiState.PLANNING
            assert app.session_state.result is None
            assert RUN_PLANNING in _text(app, f"#{WORKSPACE_ID}")

    _run(scenario())


def test_the_work_area_names_every_group_state_in_words() -> None:
    body: str = groups_body(demo_rows())
    for state in GroupState:
        assert state_text(state) in body


def test_every_group_state_carries_a_glyph_of_its_own() -> None:
    glyphs: set[str] = {state_text(state).split()[0] for state in GroupState}
    assert len(glyphs) == len(GroupState)


def test_a_row_marks_whether_the_next_workflow_acts_on_it() -> None:
    rows = demo_rows()
    picked: str = group_line(next(row for row in rows if row.selected), name_width=1)
    passed: str = group_line(next(row for row in rows if not row.selected), name_width=1)
    assert picked[0] != passed[0]


def test_an_empty_group_list_keeps_the_base_message() -> None:
    assert groups_body(()) == WORKSPACE_EMPTY


def test_the_status_line_names_the_operation_the_run_is_on() -> None:
    body: str = groups_body(demo_rows(), status=working_status())
    assert working_status() in body


def test_every_registered_theme_has_a_row_of_its_own() -> None:
    assert tuple(theme_id for theme_id, _, _ in THEME_ROWS) == THEME_IDS
    assert len({title for _, title, _ in THEME_ROWS}) == len(THEME_ROWS)


@pytest.mark.usefixtures("state_file")
def test_the_theme_surface_previews_the_highlighted_theme_and_reverts() -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_HELD_STEP)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.theme == DARK_THEME_ID
            app.commands.dispatch("theme")
            await _settle(pilot)
            await pilot.press("down")
            await pilot.pause()
            assert app.theme != DARK_THEME_ID
            await pilot.press("escape")
            await _settle(pilot)
            assert app.theme == DARK_THEME_ID
            assert load_ui_state().theme == DARK_THEME_ID

    _run(scenario())


@pytest.mark.usefixtures("state_file")
def test_the_theme_surface_keeps_and_stores_a_confirmed_theme() -> None:
    async def scenario() -> None:
        app: PrototypeApp = PrototypeApp(step=_HELD_STEP)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("theme")
            await _settle(pilot)
            await pilot.press("down")
            await pilot.pause()
            previewed: str = app.theme
            await pilot.press("enter")
            await _settle(pilot)
            assert previewed != DARK_THEME_ID
            assert app.theme == previewed
            assert load_ui_state().theme == previewed
            assert _dialogs(app) == []

    _run(scenario())


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


def _text(app: AniShiftApp, selector: str) -> str:
    return str(app.query_one(selector, Static).content)


def _dialogs(app: AniShiftApp) -> list[str]:
    return [type(screen).__name__ for screen in app.screen_stack if isinstance(screen, DialogScreen)]


def _assert_on_screen(app: AniShiftApp, size: tuple[int, int]) -> None:
    height: int = size[1]
    for selector in _ON_SCREEN_IDS:
        region = app.query_one(selector).region
        assert region.y >= 0
        assert region.y + region.height <= height
