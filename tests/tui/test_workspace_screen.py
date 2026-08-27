from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, Final

import pytest
from tui_fakes import (
    StubService,
    emit_full_run,
    inspected_group,
    inspected_workspace,
    shell,
    stub_plan,
    stub_result,
)

from anishift.application import InspectedSourceGroup, InspectedWorkspace, group_is_ready
from anishift.tui import ui_state
from anishift.tui.app import CONTENT_ID, AniShiftApp
from anishift.tui.commands.palette import CommandOption, palette_options, slash_options
from anishift.tui.commands.spec import CommandSpec
from anishift.tui.lifecycle import begin_planning, begin_run, finish_run, request_cancel
from anishift.tui.messages import NavigationRequested, WorkspaceLoaded
from anishift.tui.screens.results import WORKSPACE_COMMAND_NAME as RESULTS_WORKSPACE_COMMAND_NAME
from anishift.tui.screens.workspace import WORKSPACE_ID, GroupState, WorkspaceView, workspace_body
from anishift.tui.state import RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    COMMAND_REFRESH_TITLE,
    GROUP_CONFLICT_GLYPH,
    GROUP_MISSING_GLYPH,
    GROUP_SELECTED_GLYPH,
    GROUP_STATE_CONFLICT,
    GROUP_STATE_NO_SIDECAR,
    GROUP_STATE_READY,
    GROUP_UNSELECTED_GLYPH,
    SELECT_FILTER_PLACEHOLDER,
    SELECT_NO_RESULTS,
    SELECTION_SUMMARY,
    WORKSPACE_EMPTY,
)
from anishift.tui.widgets import group_table
from anishift.tui.widgets.group_table import (
    MIN_WINDOW_ROWS,
    PAGE_ROWS,
    REFRESH_COMMAND_NAME,
    REFRESH_KEY,
    WORKSPACE_SCOPE,
    GroupRow,
    filtered_rows,
    group_rows,
    group_state,
    groups_body,
    listed_top,
    pointed_row,
    refresh_available,
    state_text,
    table_body,
    window_start,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SMALL_SIZE: Final[tuple[int, int]] = (80, 24)

_CRUEL_SIZE: Final[tuple[int, int]] = (80, 13)

_CRUEL_ROWS: Final[int] = 2

_DRAWN_ROWS_FLOOR: Final[int] = 1

_PAUSE_LIMIT: Final[int] = 400

_ALPHA: Final[str] = "alpha-01"

_BETA: Final[str] = "beta-01"

_GAMMA: Final[str] = "gamma-01"

_DELTA: Final[str] = "delta-01"

_MANY: Final[int] = 100

_PROJECTIONS_PER_EVENT: Final[int] = 2

_FILTER_KEYS: Final[str] = "042"

_SCROLL_STEPS: Final[int] = 120

_PARK_STEPS: Final[int] = 30

_POINTER_COLUMN: Final[int] = 4

_POINTER_LINES: Final[tuple[int, ...]] = (0, 1, 3, 6)

_FIXED_POINTER_LINE: Final[int] = 4

_POINTER_REPEATS: Final[int] = 5

_SETTLE_PAUSES: Final[int] = 8

_FULL_WINDOW_ROWS: Final[int] = 17

_SMALL_WINDOW_ROWS: Final[int] = 13

_SHOW_CYCLES: Final[int] = 3

_REFRESH_KEY_LABEL: Final[str] = "Ctrl+R"

_PAINTS_PER_RESIZE: Final[int] = 2

_THEME_COMMAND_NAME: Final[str] = "theme"

_RUN_ID: Final[str] = "run-workspace"

_RUN_GATE_SECONDS: Final[float] = 30.0

_IDLE_SURFACES: Final[tuple[bool, bool, bool]] = (True, True, True)

_BUSY_SURFACES: Final[tuple[bool, bool, bool]] = (False, False, False)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    return tmp_path


@pytest.fixture
def stub() -> StubService:
    return StubService()


def test_an_empty_workspace_keeps_the_base_state_of_the_work_area() -> None:
    assert workspace_body(None) == WORKSPACE_EMPTY
    assert workspace_body(inspected_workspace()) == WORKSPACE_EMPTY


def test_a_group_row_shows_the_selection_the_name_the_source_the_artifacts_and_the_state() -> None:
    rows: tuple[GroupRow, ...] = group_rows(
        inspected_workspace(inspected_group(_ALPHA, sidecar="ass")),
        selected=frozenset({f"group-{_ALPHA}"}),
    )
    assert len(rows) == 1
    assert rows[0].group_id == f"group-{_ALPHA}"
    assert rows[0].name == _ALPHA
    assert rows[0].source == "mkv"
    assert rows[0].artifacts == "mkv, ass"
    assert rows[0].state is GroupState.READY
    assert rows[0].selected is True
    body: str = table_body(rows)
    assert _ALPHA in body
    assert "mkv, ass" in body
    assert state_text(GroupState.READY) in body
    assert GROUP_SELECTED_GLYPH in body


def test_every_group_state_is_named_by_a_word_and_marked_by_a_glyph_of_its_own() -> None:
    words: set[str] = {GROUP_STATE_READY, GROUP_STATE_CONFLICT, GROUP_STATE_NO_SIDECAR}
    glyphs: set[str] = {state_text(state).split()[0] for state in GroupState}
    assert len(glyphs) == len(GroupState)
    assert {state_text(state).split(maxsplit=1)[1] for state in GroupState} == words


def test_a_conflict_is_reported_by_a_word_and_a_glyph_and_never_by_colour_alone() -> None:
    body: str = workspace_body(inspected_workspace(inspected_group(_ALPHA, sidecar="ass", conflict=True)))
    assert GROUP_STATE_CONFLICT in body
    assert GROUP_CONFLICT_GLYPH in body


def test_a_group_without_any_usable_text_is_reported_as_missing_its_sidecar() -> None:
    assert group_state(inspected_group(_ALPHA)) is GroupState.NO_SIDECAR
    assert group_state(inspected_group(_ALPHA, sidecar="ass")) is GroupState.READY
    assert group_state(inspected_group(_ALPHA, embedded=True)) is GroupState.READY
    assert group_state(inspected_group(_ALPHA, sidecar="ass", conflict=True)) is GroupState.CONFLICT


def test_the_table_calls_a_group_ready_exactly_when_the_application_layer_does() -> None:
    shapes: tuple[InspectedSourceGroup, ...] = (
        inspected_group(_ALPHA),
        inspected_group(_ALPHA, sidecar="ass"),
        inspected_group(_ALPHA, sidecar="ass", usable_sidecar=False),
        inspected_group(_ALPHA, embedded=True),
        inspected_group(_ALPHA, sidecar="ass", conflict=True),
        inspected_group(_ALPHA, conflict=True),
    )
    assert [group_state(group) is GroupState.READY for group in shapes] == [group_is_ready(group) for group in shapes]
    assert [group_is_ready(group) for group in shapes] == [False, True, False, True, False, False]


def test_a_warning_about_one_artifact_is_marked_in_the_artifact_column() -> None:
    rows: tuple[GroupRow, ...] = group_rows(
        inspected_workspace(inspected_group(_ALPHA, sidecar="ass", usable_sidecar=False)),
    )
    assert rows[0].artifacts == f"mkv, {GROUP_MISSING_GLYPH}ass"
    assert rows[0].state is GroupState.NO_SIDECAR


def test_no_rendered_row_carries_a_path_of_any_kind() -> None:
    body: str = workspace_body(
        inspected_workspace(inspected_group(_ALPHA, sidecar="ass"), inspected_group(_BETA, embedded=True)),
    )
    assert "\\" not in body
    assert "/" not in body
    assert ":" not in body


def test_the_selection_summary_counts_every_discovered_group() -> None:
    workspace: InspectedWorkspace = inspected_workspace(
        inspected_group(_ALPHA, sidecar="ass"),
        inspected_group(_BETA, sidecar="ass"),
    )
    rows: tuple[GroupRow, ...] = group_rows(workspace, selected=frozenset({f"group-{_ALPHA}"}))
    assert SELECTION_SUMMARY.format(selected=1, total=2) in table_body(rows)


def test_groups_are_listed_in_one_natural_number_order() -> None:
    workspace: InspectedWorkspace = inspected_workspace(
        inspected_group("show-10", sidecar="ass"),
        inspected_group("show-2", sidecar="ass"),
        inspected_group("show-1", sidecar="ass"),
    )
    assert [row.name for row in group_rows(workspace)] == ["show-1", "show-2", "show-10"]
    assert [row.name for row in group_rows(workspace, descending=True)] == ["show-10", "show-2", "show-1"]


def test_the_projection_marks_only_the_group_ids_the_caller_selected() -> None:
    workspace: InspectedWorkspace = inspected_workspace(
        inspected_group(_ALPHA, sidecar="ass"),
        inspected_group(_BETA, sidecar="ass"),
    )
    rows: tuple[GroupRow, ...] = group_rows(workspace, selected=frozenset({f"group-{_BETA}"}))
    assert {row.name: row.selected for row in rows} == {_ALPHA: False, _BETA: True}


def test_a_filter_keeps_only_the_matching_rows_and_says_so_when_none_match() -> None:
    rows: tuple[GroupRow, ...] = group_rows(
        inspected_workspace(inspected_group(_ALPHA, sidecar="ass"), inspected_group(_BETA, sidecar="ass")),
    )
    assert [row.name for row in filtered_rows(rows, "BET")] == [_BETA]
    assert filtered_rows(rows, "   ") == rows
    assert SELECT_NO_RESULTS in table_body(rows, query="nothing")
    assert f"{SELECT_FILTER_PLACEHOLDER} bet" in table_body(rows, query="bet")


def test_the_window_stays_on_its_anchor_while_it_still_holds_the_cursor() -> None:
    assert window_start(0, 3, 10) == 0
    assert window_start(0, 100, 10) == 0
    assert window_start(5, 100, 0) == 0
    assert window_start(45, 100, 10, 45) == 45
    assert window_start(54, 100, 10, 45) == 45
    assert window_start(44, 100, 10, 45) == 44
    assert window_start(55, 100, 10, 45) == 46
    assert window_start(50, 100, 10, 95) == 50
    assert window_start(99, 100, 10) == 90


def test_resolving_the_window_a_second_time_never_moves_it_again() -> None:
    for cursor in (0, 7, 42, 99):
        for anchor in (0, 30, 95):
            once: int = window_start(cursor, 100, 10, anchor)
            assert window_start(cursor, 100, 10, once) == once


def test_no_line_above_the_first_or_below_the_last_listed_row_points_at_a_row() -> None:
    assert pointed_row(2, top=2, start=14, listed=17) == 14
    assert pointed_row(5, top=2, start=14, listed=17) == 17
    assert pointed_row(18, top=2, start=14, listed=17) == 30
    assert pointed_row(1, top=2, start=14, listed=17) is None
    assert pointed_row(19, top=2, start=14, listed=17) is None
    assert pointed_row(2, top=2, start=0, listed=0) is None


def test_the_first_listed_row_sits_below_the_summary_the_status_and_the_filter() -> None:
    rows: tuple[GroupRow, ...] = group_rows(_three_groups())
    assert listed_top(rows) == 2
    assert listed_top(rows, status="praca") == 3
    assert listed_top(rows, query="bet") == 3
    assert listed_top(rows, status="praca", query="bet") == 4
    for status, query in (("", ""), ("praca", ""), ("", "a"), ("praca", "a")):
        body: str = table_body(rows, status=status, query=query)
        assert body.splitlines().index("") + 1 == listed_top(rows, status=status, query=query)


def test_the_simulated_renderer_lists_every_row_without_a_window() -> None:
    rows: tuple[GroupRow, ...] = group_rows(_many_groups())
    assert len(groups_body(rows).splitlines()) == len(rows) + 2
    assert groups_body(()) == WORKSPACE_EMPTY


def test_the_work_area_lists_every_discovered_group_of_the_shell_state() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, inspected_workspace(inspected_group(_ALPHA, sidecar="ass")))
            assert app.query_one(f"#{WORKSPACE_ID}").display is True
            assert _ALPHA in _body(app)

    _run(scenario())


def test_space_toggles_the_group_under_the_cursor_and_marks_it_in_the_table() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            app.set_focus(_view(app))
            await pilot.press("space")
            await pilot.pause()
            assert app.session_state.selected_group_ids == {f"group-{_ALPHA}"}
            assert _selected_in_body(app, _ALPHA) is True
            assert _selected_in_body(app, _BETA) is False
            await pilot.press("space")
            await pilot.pause()
            assert app.session_state.selected_group_ids == set()
            assert _selected_in_body(app, _ALPHA) is False

    _run(scenario())


def test_the_cursor_keys_move_the_group_that_space_acts_on() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            app.set_focus(_view(app))
            await pilot.press("down")
            await pilot.press("space")
            await pilot.pause()
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert _selected_in_body(app, _BETA) is True

    _run(scenario())


def test_the_selection_is_held_by_group_id_and_never_by_a_row_index() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            _toggle(app, _BETA)
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}

    _run(scenario())


def test_the_selection_survives_a_reversed_order_of_the_same_groups() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            _toggle(app, _BETA)
            assert _order_in_body(app, (_ALPHA, _BETA, _GAMMA)) == [_ALPHA, _BETA, _GAMMA]
            _view(app).action_reverse_order()
            await pilot.pause()
            assert _view(app).descending is True
            assert _order_in_body(app, (_ALPHA, _BETA, _GAMMA)) == [_GAMMA, _BETA, _ALPHA]
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert _selected_in_body(app, _BETA) is True
            assert _selected_in_body(app, _ALPHA) is False
            assert _selected_in_body(app, _GAMMA) is False

    _run(scenario())


def test_a_refresh_that_reorders_removes_and_adds_groups_keeps_only_the_survivors() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            _toggle(app, _BETA)
            _toggle(app, _GAMMA)
            assert app.session_state.selected_group_ids == {f"group-{_BETA}", f"group-{_GAMMA}"}
            await _load(
                app,
                pilot,
                inspected_workspace(
                    inspected_group(_GAMMA, sidecar="ass"),
                    inspected_group(_ALPHA, sidecar="ass"),
                    inspected_group(_DELTA, sidecar="ass"),
                ),
            )
            assert app.session_state.selected_group_ids == {f"group-{_GAMMA}"}
            assert _BETA not in _body(app)
            assert _order_in_body(app, (_ALPHA, _DELTA, _GAMMA)) == [_ALPHA, _DELTA, _GAMMA]
            assert _selected_in_body(app, _GAMMA) is True
            assert _selected_in_body(app, _DELTA) is False
            assert _selected_in_body(app, _ALPHA) is False

    _run(scenario())


def test_a_removed_group_leaves_the_selection_without_taking_the_others_with_it() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            _toggle(app, _ALPHA)
            _toggle(app, _BETA)
            await _load(app, pilot, inspected_workspace(inspected_group(_BETA, sidecar="ass")))
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert _selected_in_body(app, _BETA) is True

    _run(scenario())


def test_the_refresh_key_reads_the_workspace_again_off_the_ui_thread(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            _toggle(app, _BETA)
            stub.calls.clear()
            stub.workspace = inspected_workspace(
                inspected_group(_BETA, sidecar="ass"),
                inspected_group(_DELTA, sidecar="ass"),
            )
            app.set_focus(_view(app))
            await pilot.press("ctrl+r")
            await _until(pilot, lambda: stub.calls == ["discover"])
            await _until(pilot, lambda: _DELTA in _body(app))
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.plan is None

    _run(scenario())


def test_a_refresh_of_an_earlier_generation_never_replaces_the_newer_workspace() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            stale: InspectedWorkspace = _three_groups()
            await _load(app, pilot, stale)
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            app.post_message(WorkspaceLoaded(workspace=_one_group(_DELTA), generation=generation))
            await pilot.pause()
            assert _DELTA in _body(app)
            app.post_message(WorkspaceLoaded(workspace=stale, generation=generation - 1))
            await pilot.pause()
            assert _DELTA in _body(app)
            assert _ALPHA not in _body(app)

    _run(scenario())


def test_neither_the_selection_nor_a_refresh_ever_starts_planning_or_a_run(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            stub.calls.clear()
            app.set_focus(_view(app))
            await pilot.press("space")
            await pilot.press("ctrl+r")
            await _until(pilot, lambda: stub.calls == ["discover"])
            assert stub.calls == ["discover"]
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.plan is None
            assert app.session_state.active_run_id is None

    _run(scenario())


def test_no_slash_command_of_the_registry_offers_a_refresh() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert REFRESH_COMMAND_NAME not in app.commands.slash_names()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            action: CommandSpec | None = app.commands.command(REFRESH_COMMAND_NAME)
            assert action is not None
            assert action.slash_name is None
            assert action.slash_forms == ()
            assert REFRESH_COMMAND_NAME not in app.commands.slash_names()
            assert slash_options(app.commands, REFRESH_COMMAND_NAME) == ()

    _run(scenario())


def test_the_workspace_on_screen_offers_refresh_as_a_palette_row_of_its_own() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert _refresh_row(app) is None
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            row: CommandOption | None = _refresh_row(app)
            assert row is not None
            assert row.name == REFRESH_COMMAND_NAME
            assert row.keys == _REFRESH_KEY_LABEL

    _run(scenario())


def test_the_refresh_key_and_the_refresh_palette_row_reach_the_one_action() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            action: CommandSpec | None = app.commands.command(REFRESH_COMMAND_NAME)
            assert action is not None
            assert action.run == _view(app).action_refresh
            assert REFRESH_KEY in action.keys

    _run(scenario())


def test_the_refresh_palette_row_reads_the_workspace_again_off_the_ui_thread(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            stub.calls.clear()
            stub.workspace = _one_group(_DELTA)
            row: CommandOption | None = _refresh_row(app)
            assert row is not None
            assert app.commands.dispatch(row.name) is True
            await _until(pilot, lambda: stub.calls == ["discover"])
            await _until(pilot, lambda: _DELTA in _body(app))
            assert stub.calls == ["discover"]
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_the_refresh_action_leaves_the_registry_with_the_workspace_view() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            assert app.commands.command(REFRESH_COMMAND_NAME) is not None
            app.post_message(NavigationRequested(UiRoute.AUTO))
            await _settle(pilot)
            assert app.query_one(f"#{WORKSPACE_ID}").display is False
            assert app.commands.command(REFRESH_COMMAND_NAME) is None
            assert _refresh_row(app) is None
            assert app.commands.dispatch_key(REFRESH_KEY) is False

    _run(scenario())


def test_showing_the_workspace_again_registers_the_refresh_action_exactly_once() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            for _ in range(_SHOW_CYCLES):
                app.post_message(NavigationRequested(UiRoute.AUTO))
                await _settle(pilot)
                app.post_message(NavigationRequested(UiRoute.WORKSPACE))
                await _settle(pilot)
            assert [spec.name for spec in app.commands.commands() if spec.name == REFRESH_COMMAND_NAME] == [
                REFRESH_COMMAND_NAME,
            ]
            assert len([row for row in palette_options(app.commands) if row.label == COMMAND_REFRESH_TITLE]) == 1
            app.commands.unregister(WORKSPACE_SCOPE)
            assert app.commands.command(REFRESH_COMMAND_NAME) is None

    _run(scenario())


def test_a_refresh_is_permitted_only_by_a_session_that_runs_nothing_and_holds_no_dialog() -> None:
    state: SessionState = SessionState()
    for run_state in RunUiState:
        state.run_state = run_state
        assert refresh_available(state) is (run_state in {RunUiState.IDLE, RunUiState.TERMINAL})
    state.run_state = RunUiState.IDLE
    state.modal_focus_stack.append(None)
    assert refresh_available(state) is False
    state.modal_focus_stack.clear()
    assert refresh_available(state) is True


def test_no_refresh_reads_the_workspace_again_while_a_dialog_covers_it(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            stub.calls.clear()
            stub.workspace = _one_group(_DELTA)
            assert app.commands.dispatch(_THEME_COMMAND_NAME) is True
            await _settle(pilot)
            assert app.session_state.modal_focus_stack != []
            assert app.commands.command(REFRESH_COMMAND_NAME) is not None
            await pilot.press(REFRESH_KEY)
            await _settle(pilot)
            assert stub.calls == []
            assert app.commands.dispatch_key(REFRESH_KEY) is False
            assert app.commands.dispatch(REFRESH_COMMAND_NAME) is False
            assert _refresh_row(app) is None
            assert _DELTA not in _body(app)
            await pilot.press("escape")
            await _settle(pilot)
            assert app.session_state.modal_focus_stack == []
            assert _refresh_row(app) is not None
            assert app.commands.dispatch_key(REFRESH_KEY) is True
            await _until(pilot, lambda: _DELTA in _body(app))

    _run(scenario())


def test_no_refresh_reads_the_workspace_again_while_planning_is_in_flight(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            _toggle(app, _BETA)
            stub.calls.clear()
            stub.workspace = _one_group(_DELTA)
            assert begin_planning(app.session_state) is not None
            app.set_focus(_view(app))
            await pilot.press(REFRESH_KEY)
            await _settle(pilot)
            assert stub.calls == []
            assert app.commands.dispatch(REFRESH_COMMAND_NAME) is False
            assert _refresh_row(app) is None
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert _DELTA not in _body(app)

    _run(scenario())


def test_no_refresh_replaces_the_projection_while_the_run_the_user_watches_is_active(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    stub.emit = lambda sink: _emit_then_hold(sink, gate)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            _toggle(app, _BETA)
            assert begin_planning(app.session_state) is not None
            assert app.start_execution(stub_plan()) is True
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.RUNNING)
            stub.calls.clear()
            stub.workspace = _one_group(_DELTA)
            app.set_focus(_view(app))
            await pilot.press(REFRESH_KEY)
            await _settle(pilot)
            assert stub.calls == []
            assert app.commands.dispatch(REFRESH_COMMAND_NAME) is False
            assert _refresh_row(app) is None
            assert app.session_state.selected_group_ids == {f"group-{_BETA}"}
            assert app.session_state.active_run_id == _RUN_ID
            assert _DELTA not in _body(app)
            gate.set()
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert app.commands.dispatch(RESULTS_WORKSPACE_COMMAND_NAME) is True
            await _settle(pilot)
            assert _refresh_row(app) is not None
            assert app.commands.dispatch_key(REFRESH_KEY) is True
            await _until(pilot, lambda: _DELTA in _body(app))

    try:
        _run(scenario())
    finally:
        gate.set()


def test_the_refresh_key_and_its_palette_row_answer_as_one_through_every_run_state(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _three_groups())
            await _settle(pilot)
            stub.workspace = _three_groups()
            states: list[RunUiState] = []
            surfaces: list[tuple[bool, bool, bool]] = []

            async def record() -> None:
                states.append(app.session_state.run_state)
                surfaces.append(
                    (
                        _refresh_row(app) is not None,
                        app.commands.dispatch_key(REFRESH_KEY),
                        app.commands.dispatch(REFRESH_COMMAND_NAME),
                    ),
                )
                await _settle(pilot)

            await record()
            assert begin_planning(app.session_state) is not None
            await record()
            assert begin_run(app.session_state, _RUN_ID) is True
            await record()
            assert request_cancel(app.session_state) is True
            await record()
            assert finish_run(app.session_state, stub_result(_RUN_ID)) is True
            await record()
            assert states == [
                RunUiState.IDLE,
                RunUiState.PLANNING,
                RunUiState.RUNNING,
                RunUiState.CANCELLING,
                RunUiState.TERMINAL,
            ]
            assert surfaces == [
                _IDLE_SURFACES,
                _BUSY_SURFACES,
                _BUSY_SURFACES,
                _BUSY_SURFACES,
                _IDLE_SURFACES,
            ]

    _run(scenario())


def test_scrolling_and_filtering_a_hundred_groups_ask_the_service_for_nothing(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            stub.calls.clear()
            view: WorkspaceView = _view(app)
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_up()
            view.action_page_down()
            view.action_page_up()
            app.set_focus(view)
            for character in "042":
                await pilot.press(character)
            await pilot.pause()
            assert view.filter_query == "042"
            assert "show-042" in _body(app)
            assert "show-041" not in _body(app)
            await pilot.press("backspace")
            await pilot.pause()
            assert view.filter_query == "04"
            await pilot.press("escape")
            await pilot.pause()
            assert view.filter_query == ""
            assert stub.calls == []

    _run(scenario())


def test_every_scroll_and_filter_event_projects_a_hundred_groups_a_bounded_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = _view(app)
            app.set_focus(view)
            projections: list[int] = _counted_projections(monkeypatch)
            events: int = 0
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
                events += 1
            view.action_page_up()
            events += 1
            await pilot.pause()
            for character in _FILTER_KEYS:
                await pilot.press(character)
                events += 1
            await pilot.press("backspace")
            events += 1
            await pilot.pause()
            assert view.filter_query == _FILTER_KEYS[:-1]
            assert len(_current_rows(app)) == _MANY
            assert events <= projections[0] <= events * _PROJECTIONS_PER_EVENT

    _run(scenario())


def test_the_small_terminal_layout_lists_only_the_rows_its_work_area_draws() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_SMALL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = _view(app)
            await _repaint(pilot, view)
            assert len(_listed_rows(app)) >= _DRAWN_ROWS_FLOOR
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
            await pilot.pause()
            assert view.cursor == _MANY - 1
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True

    _run(scenario())


def test_a_work_area_shorter_than_the_window_floor_still_draws_the_row_the_cursor_sits_on() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_CRUEL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = _view(app)
            await _repaint(pilot, view)
            assert _DRAWN_ROWS_FLOOR <= len(_listed_rows(app)) <= _CRUEL_ROWS
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
            await pilot.pause()
            assert view.cursor == _MANY - 1
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True
            view.action_page_up()
            await pilot.pause()
            assert view.cursor == _MANY - 1 - PAGE_ROWS
            assert _cursor_is_drawn(app) is True

    _run(scenario())


def test_no_pointer_below_the_last_drawn_row_of_a_short_work_area_moves_the_cursor() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_CRUEL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = _view(app)
            await _repaint(pilot, view)
            drawn: int = len(_listed_rows(app))
            assert drawn == _CRUEL_ROWS
            last: int = _top_line(app) + drawn - 1
            await _hover_line(pilot, view, last)
            assert view.cursor == view.window_top + drawn - 1
            cursor: int = view.cursor
            top: int = view.window_top
            await _hover_line(pilot, view, last + 1)
            assert (view.cursor, view.window_top) == (cursor, top)
            assert len(_listed_rows(app)) == drawn

    _run(scenario())


def test_a_terminal_shrinking_under_the_window_floor_brings_the_cursor_back_into_view() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = await _park(app, pilot)
            assert view.window_top > 0
            await pilot.resize_terminal(*_CRUEL_SIZE)
            await pilot.pause()
            await _repaint(pilot, view)
            assert view.cursor == _PARK_STEPS
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True

    _run(scenario())


def test_the_table_lists_only_the_window_its_container_offers() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            listed: list[str] = _listed_rows(app)
            assert MIN_WINDOW_ROWS <= len(listed) < _MANY
            assert "show-000" in _body(app)
            assert "show-099" not in _body(app)
            view: WorkspaceView = _view(app)
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
            await pilot.pause()
            assert view.cursor == _MANY - 1
            assert "show-099" in _body(app)
            assert "show-000" not in _body(app)

    _run(scenario())


@pytest.mark.parametrize(("size", "rows"), [(_FULL_SIZE, _FULL_WINDOW_ROWS), (_CRUEL_SIZE, _CRUEL_ROWS)])
def test_the_first_paint_after_a_workspace_fills_the_work_area_it_was_given(
    size: tuple[int, int],
    rows: int,
) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            await _settle(pilot)
            assert len(_listed_rows(app)) == rows
            assert _drawn_lines(app) <= _work_area_height(app)
            assert _cursor_is_drawn(app) is True

    _run(scenario())


def test_a_resize_alone_redraws_the_window_the_new_work_area_offers() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            await _settle(pilot)
            assert len(_listed_rows(app)) == _FULL_WINDOW_ROWS
            await pilot.resize_terminal(*_SMALL_SIZE)
            await _settle(pilot)
            assert len(_listed_rows(app)) == _SMALL_WINDOW_ROWS
            assert _drawn_lines(app) <= _work_area_height(app)
            await pilot.resize_terminal(*_CRUEL_SIZE)
            await _settle(pilot)
            assert len(_listed_rows(app)) == _CRUEL_ROWS
            assert _drawn_lines(app) <= _work_area_height(app)
            await pilot.resize_terminal(*_FULL_SIZE)
            await _settle(pilot)
            assert len(_listed_rows(app)) == _FULL_WINDOW_ROWS
            assert _drawn_lines(app) <= _work_area_height(app)

    _run(scenario())


def test_a_settled_work_area_repaints_the_table_no_further() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            await _settle(pilot)
            view: WorkspaceView = _view(app)
            painted: list[int] = _counted_paints(view)
            await _settle(pilot)
            assert painted[0] == 0
            await pilot.resize_terminal(*_SMALL_SIZE)
            await _settle(pilot)
            resized: int = painted[0]
            assert 1 <= resized <= _PAINTS_PER_RESIZE
            await _settle(pilot)
            assert painted[0] == resized

    _run(scenario())


def test_a_resize_moves_neither_the_cursor_nor_the_selection_of_the_table() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            await _settle(pilot)
            view: WorkspaceView = await _park(app, pilot)
            view.action_toggle_group()
            await _settle(pilot)
            selected: set[str] = set(app.session_state.selected_group_ids)
            assert len(selected) == 1
            for size in (_SMALL_SIZE, _CRUEL_SIZE, _FULL_SIZE):
                await pilot.resize_terminal(*size)
                await _settle(pilot)
                assert view.cursor == _PARK_STEPS
                assert set(app.session_state.selected_group_ids) == selected
                assert _cursor_is_drawn(app) is True
                assert _drawn_lines(app) <= _work_area_height(app)

    _run(scenario())


def test_the_pointer_moves_the_table_cursor_to_the_row_it_rests_on() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = await _park(app, pilot)
            parked: int = view.window_top
            assert parked > 0
            top: int = _top_line(app)
            for line in _POINTER_LINES:
                await _hover_line(pilot, view, top + line)
                assert view.cursor == parked + line
                assert view.window_top == parked

    _run(scenario())


def test_repeated_pointer_moves_at_one_line_leave_the_table_window_exactly_where_it_was() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = await _park(app, pilot)
            parked: int = view.window_top
            assert parked > 0
            first: str = _listed_rows(app)[0]
            seen: list[tuple[int, int, str]] = []
            for _ in range(_POINTER_REPEATS):
                await _hover_line(pilot, view, _top_line(app) + _FIXED_POINTER_LINE)
                seen.append((view.cursor, view.window_top, _listed_rows(app)[0]))
            assert seen == [(parked + _FIXED_POINTER_LINE, parked, first)] * _POINTER_REPEATS

    _run(scenario())


def test_the_pointer_never_changes_the_selection_of_the_table() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = await _park(app, pilot)
            await _hover_line(pilot, view, _top_line(app) + _FIXED_POINTER_LINE)
            view.action_toggle_group()
            await pilot.pause()
            selected: set[str] = set(app.session_state.selected_group_ids)
            assert len(selected) == 1
            on_selected: int = _FIXED_POINTER_LINE
            for line in (on_selected, on_selected + 2, on_selected, on_selected - 3):
                await _hover_line(pilot, view, _top_line(app) + line)
                assert set(app.session_state.selected_group_ids) == selected
            assert _selected_row_count(app) == 1

    _run(scenario())


def test_the_keyboard_still_brings_an_off_window_row_of_the_table_into_view() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = _view(app)
            assert view.window_top == 0
            assert "show-000" in _body(app)
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_down()
            await pilot.pause()
            assert view.cursor == _MANY - 1
            assert view.window_top > 0
            assert "show-099" in _body(app)
            assert "show-000" not in _body(app)
            for _ in range(_SCROLL_STEPS):
                view.action_cursor_up()
            await pilot.pause()
            assert (view.cursor, view.window_top) == (0, 0)
            assert "show-000" in _body(app)

    _run(scenario())


def test_a_click_on_the_table_focuses_it_and_moves_neither_the_cursor_nor_the_selection() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _load(app, pilot, _many_groups())
            view: WorkspaceView = await _park(app, pilot)
            view.action_toggle_group()
            await pilot.pause()
            selected: set[str] = set(app.session_state.selected_group_ids)
            cursor: int = view.cursor
            window: int = view.window_top
            app.set_focus(None)
            await pilot.click(view, offset=(_POINTER_COLUMN, _top_line(app) + 1))
            await pilot.pause()
            assert app.focused is view
            assert (view.cursor, view.window_top) == (cursor, window)
            assert set(app.session_state.selected_group_ids) == selected

    _run(scenario())


def test_the_table_takes_no_key_while_the_shell_holds_no_workspace() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            view: WorkspaceView = _view(app)
            assert view.can_focus is False
            view.action_toggle_group()
            view.action_cursor_down()
            assert app.session_state.selected_group_ids == set()
            assert view.cursor == 0
            assert view.filter_query == ""

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


def _emit_then_hold(sink: Any, gate: threading.Event) -> None:
    emit_full_run(sink, _RUN_ID, progress=1)
    gate.wait(_RUN_GATE_SECONDS)


def _refresh_row(app: AniShiftApp) -> CommandOption | None:
    return next((row for row in palette_options(app.commands) if row.label == COMMAND_REFRESH_TITLE), None)


def _counted_paints(view: WorkspaceView) -> list[int]:
    counted: list[int] = [0]
    paint: Callable[..., None] = view.show_rows

    def counting(rows: Sequence[GroupRow], *, status: str = "") -> None:
        counted[0] += 1
        paint(rows, status=status)

    view.show_rows = counting  # type: ignore[method-assign]
    return counted


async def _load(app: AniShiftApp, pilot: Any, workspace: InspectedWorkspace) -> None:
    app.post_message(WorkspaceLoaded(workspace=workspace, generation=app.session_state.generation))
    await pilot.pause()


def _view(app: AniShiftApp) -> WorkspaceView:
    return app.query_one(WorkspaceView)


def _body(app: AniShiftApp) -> str:
    return str(_view(app).content)


def _listed_rows(app: AniShiftApp) -> list[str]:
    lines: list[str] = _body(app).splitlines()
    return lines[lines.index("") + 1 :]


def _top_line(app: AniShiftApp) -> int:
    return _body(app).splitlines().index("") + 1


async def _park(app: AniShiftApp, pilot: Any) -> WorkspaceView:
    view: WorkspaceView = _view(app)
    for _ in range(_PARK_STEPS):
        view.action_cursor_down()
    await pilot.pause()
    return view


async def _hover_line(pilot: Any, view: WorkspaceView, line: int) -> None:
    await pilot.hover(view, offset=(_POINTER_COLUMN, line))
    await pilot.pause()


async def _repaint(pilot: Any, view: WorkspaceView) -> None:
    view.action_cursor_down()
    view.action_cursor_up()
    await pilot.pause()


def _work_area_height(app: AniShiftApp) -> int:
    return app.query_one(f"#{CONTENT_ID}").content_size.height


def _drawn_lines(app: AniShiftApp) -> int:
    return len(_body(app).splitlines())


def _cursor_is_drawn(app: AniShiftApp) -> bool:
    view: WorkspaceView = _view(app)
    return 0 <= view.cursor - view.window_top < len(_listed_rows(app))


def _counted_projections(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    counted: list[int] = [0]
    project: Callable[..., tuple[GroupRow, ...]] = group_table.group_rows

    def counting(*args: Any, **kwargs: Any) -> tuple[GroupRow, ...]:
        counted[0] += 1
        return project(*args, **kwargs)

    monkeypatch.setattr(group_table, "group_rows", counting)
    return counted


def _selected_row_count(app: AniShiftApp) -> int:
    return sum(1 for line in _listed_rows(app) if line[1] == GROUP_SELECTED_GLYPH)


def _row_of(app: AniShiftApp, stem: str) -> str:
    return next(line for line in _listed_rows(app) if stem in line)


def _selected_in_body(app: AniShiftApp, stem: str) -> bool:
    marker: str = _row_of(app, stem)[1]
    assert marker in {GROUP_SELECTED_GLYPH, GROUP_UNSELECTED_GLYPH}
    return marker == GROUP_SELECTED_GLYPH


def _order_in_body(app: AniShiftApp, stems: tuple[str, ...]) -> list[str]:
    body: str = _body(app)
    return sorted(stems, key=body.index)


def _toggle(app: AniShiftApp, stem: str) -> None:
    view: WorkspaceView = _view(app)
    target: int = next(index for index, row in enumerate(_current_rows(app)) if row.name == stem)
    while view.cursor > target:
        view.action_cursor_up()
    while view.cursor < target:
        view.action_cursor_down()
    view.action_toggle_group()


def _current_rows(app: AniShiftApp) -> tuple[GroupRow, ...]:
    return group_rows(app.session_state.workspace, descending=_view(app).descending)


def _one_group(stem: str) -> InspectedWorkspace:
    return inspected_workspace(inspected_group(stem, sidecar="ass"))


def _three_groups() -> InspectedWorkspace:
    return inspected_workspace(
        inspected_group(_GAMMA, sidecar="ass"),
        inspected_group(_ALPHA, sidecar="ass"),
        inspected_group(_BETA, sidecar="ass"),
    )


def _many_groups() -> InspectedWorkspace:
    return inspected_workspace(*(inspected_group(f"show-{index:03d}", sidecar="ass") for index in range(_MANY)))
