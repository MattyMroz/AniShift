from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from tui_fakes import StubService, shell, stub_plan, stub_result

from anishift.application import RunEvent, RunEventEmitter, RunEventKind, RunEventSink, TaskState
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.palette import CommandOption, palette_options
from anishift.tui.lifecycle import begin_planning, begin_run
from anishift.tui.messages import NavigationRequested, RunProgressed
from anishift.tui.screens.execution import (
    CANCEL_COMMAND_NAME,
    CANCEL_KEY,
    DETAILS_COMMAND_NAME,
    DETAILS_KEY,
    EXECUTION_SCOPE,
    FILTER_COMMAND_NAME,
    FILTER_KEY,
    ExecutionView,
    cancel_available,
    execution_body,
    table_available,
)
from anishift.tui.state import RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    EXECUTION_CANCEL_QUESTION,
    EXECUTION_CANCEL_TITLE,
    EXECUTION_CANCELLED_GLYPH,
    EXECUTION_DONE_GLYPH,
    EXECUTION_EMPTY,
    EXECUTION_FAILED_GLYPH,
    EXECUTION_FALLBACK_WORD,
    EXECUTION_FILTER_LABEL,
    EXECUTION_RETRY_WORD,
    EXECUTION_RUNNING_GLYPH,
    EXECUTION_STATE_CANCELLED,
    EXECUTION_STATE_DONE,
    EXECUTION_STATE_FAILED,
    EXECUTION_STATE_RUNNING,
    EXECUTION_STATE_WAITING,
    EXECUTION_SUMMARY,
    EXECUTION_TITLE,
    EXECUTION_WAITING_GLYPH,
    TOOLS_RUN_CANCELLING,
)
from anishift.tui.widgets.progress_table import (
    ProgressFilter,
    ProgressRow,
    RowState,
    listed_rows,
    next_filter,
    progress_body,
    progress_rows,
)

_FULL_SIZE: Final[tuple[int, int]] = (110, 34)

_NARROW_SIZE: Final[tuple[int, int]] = (80, 24)

_PAUSE_LIMIT: Final[int] = 400

_SETTLE_PAUSES: Final[int] = 8

_RUN_GATE_SECONDS: Final[float] = 30.0

_RUN_ID: Final[str] = "run-execution"

_ALPHA: Final[str] = "group-alpha"

_BETA: Final[str] = "group-beta"

_TASK: Final[str] = "task-translate_subtitles-abcdef123456"

_TASK_LABEL: Final[str] = "Translate subtitles"

_OTHER_TASK: Final[str] = "task-compose_mkv-abcdef123456"

_OTHER_TASK_LABEL: Final[str] = "Compose MKV"

_HALF_PERCENT: Final[int] = 42

_FULL_PERCENT: Final[int] = 100

_CATALOG_COMMANDS: Final[int] = 14

_BATCH_EVENTS: Final[int] = 4

_RETRY_MESSAGE: Final[str] = "the engine asked one more time"

_FALLBACK_MESSAGE: Final[str] = "the next engine took the work"

_LOCATED_MESSAGE: Final[str] = "it broke at C:\\secret\\episode.mkv"

_TYPED_TEXT: Final[str] = "watching"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("anishift.tui.ui_state.config_path", lambda: tmp_path / "settings.json")
    return tmp_path


@pytest.fixture
def stub() -> StubService:
    return StubService()


def test_no_event_folds_into_no_row_at_all() -> None:
    assert progress_rows(()) == ()


def test_a_started_task_folds_into_one_running_row_naming_its_operation() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows((_run_started(), _task_started(2)))
    assert rows == (ProgressRow(group_id=_ALPHA, state=RowState.RUNNING, task=_TASK_LABEL),)


def test_the_progress_of_a_task_folds_into_the_percentage_of_its_group() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows((_task_started(1), _task_progress(2, _HALF_PERCENT)))
    assert rows[0].percent == _HALF_PERCENT
    assert rows[0].state is RowState.RUNNING


def test_a_group_that_finished_folds_into_a_done_row_at_the_full_percentage() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (_task_started(1), _task_progress(2, _HALF_PERCENT), _group_finished(3, TaskState.SUCCEEDED)),
    )
    assert rows[0].state is RowState.DONE
    assert rows[0].percent == _FULL_PERCENT


def test_a_group_that_failed_folds_into_a_failed_row_keeping_the_progress_it_reached() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (_task_started(1), _task_progress(2, _HALF_PERCENT), _group_finished(3, TaskState.FAILED)),
    )
    assert rows[0].state is RowState.FAILED
    assert rows[0].percent == _HALF_PERCENT


def test_a_group_that_was_cancelled_folds_into_a_cancelled_row() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows((_task_started(1), _group_finished(2, TaskState.CANCELLED)))
    assert rows[0].state is RowState.CANCELLED


def test_no_later_event_moves_a_group_that_already_ended() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (
            _task_started(1),
            _group_finished(2, TaskState.FAILED),
            _task_progress(3, _FULL_PERCENT),
            _task_started(4),
        ),
    )
    assert rows[0].state is RowState.FAILED
    assert rows[0].percent == 0


def test_a_run_that_finished_leaves_no_group_of_it_in_flight() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (
            _run_started(),
            _task_started(2),
            _task_started(3, group_id=_BETA, task_id=_OTHER_TASK),
            _group_finished(4, TaskState.SUCCEEDED, group_id=_BETA),
            _run_finished(5, TaskState.CANCELLED),
        ),
    )
    assert [row.state for row in rows] == [RowState.CANCELLED, RowState.DONE]


def test_the_same_events_fold_the_same_way_in_every_arrival_order() -> None:
    events: tuple[RunEvent, ...] = (
        _run_started(),
        _task_started(2),
        _task_progress(3, _HALF_PERCENT),
        _task_started(4, group_id=_BETA, task_id=_OTHER_TASK),
        _group_finished(5, TaskState.SUCCEEDED, group_id=_BETA),
    )
    ordered: tuple[ProgressRow, ...] = progress_rows(events)
    assert progress_rows(tuple(reversed(events))) == ordered
    assert progress_rows((*events[3:], *events[:3])) == ordered


def test_folding_the_events_of_a_run_never_changes_the_events_themselves() -> None:
    events: list[RunEvent] = [_run_started(), _task_started(2), _task_progress(3, _HALF_PERCENT)]
    kept: tuple[RunEvent, ...] = tuple(events)
    assert progress_rows(events) == progress_rows(events)
    assert tuple(events) == kept


def test_a_retry_and_a_fallback_fold_into_the_details_of_their_own_group() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (
            _task_started(1),
            _detail(2, RunEventKind.TASK_RETRY, _RETRY_MESSAGE),
            _detail(3, RunEventKind.TASK_FALLBACK, _FALLBACK_MESSAGE),
        ),
    )
    assert rows[0].details == (
        f"{EXECUTION_RETRY_WORD}  {_RETRY_MESSAGE}",
        f"{EXECUTION_FALLBACK_WORD}  {_FALLBACK_MESSAGE}",
    )
    assert rows[0].state is RowState.RUNNING
    assert rows[0].task == _TASK_LABEL


def test_a_retry_without_a_message_folds_into_the_word_alone() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows((_task_started(1), _detail(2, RunEventKind.TASK_RETRY)))
    assert rows[0].details == (EXECUTION_RETRY_WORD,)


def test_no_detail_of_a_group_ever_shows_a_location_an_event_carried() -> None:
    rows: tuple[ProgressRow, ...] = progress_rows(
        (_task_started(1), _detail(2, RunEventKind.TASK_RETRY, _LOCATED_MESSAGE)),
    )
    assert "secret" not in rows[0].details[0]
    assert "<path>" in rows[0].details[0]


def test_every_filter_keeps_only_the_rows_it_names() -> None:
    rows: tuple[ProgressRow, ...] = (
        ProgressRow(group_id="a", state=RowState.WAITING),
        ProgressRow(group_id="b", state=RowState.RUNNING),
        ProgressRow(group_id="c", state=RowState.FAILED),
        ProgressRow(group_id="d", state=RowState.DONE),
        ProgressRow(group_id="e", state=RowState.CANCELLED),
    )
    assert listed_rows(rows, ProgressFilter.ALL) == rows
    assert [row.group_id for row in listed_rows(rows, ProgressFilter.RUNNING)] == ["b"]
    assert [row.group_id for row in listed_rows(rows, ProgressFilter.FAILED)] == ["c"]
    assert [row.group_id for row in listed_rows(rows, ProgressFilter.DONE)] == ["c", "d", "e"]


def test_a_filter_hides_a_row_without_ever_changing_the_rows_it_was_given() -> None:
    rows: tuple[ProgressRow, ...] = (
        ProgressRow(group_id="a", state=RowState.RUNNING),
        ProgressRow(group_id="b", state=RowState.DONE),
    )
    assert listed_rows(rows, ProgressFilter.RUNNING) == (rows[0],)
    assert rows == (
        ProgressRow(group_id="a", state=RowState.RUNNING),
        ProgressRow(group_id="b", state=RowState.DONE),
    )


def test_the_filter_walks_every_filter_and_comes_back_to_the_first_one() -> None:
    walked: list[ProgressFilter] = [ProgressFilter.ALL]
    for _ in range(len(ProgressFilter)):
        walked.append(next_filter(walked[-1]))
    assert walked == [
        ProgressFilter.ALL,
        ProgressFilter.RUNNING,
        ProgressFilter.FAILED,
        ProgressFilter.DONE,
        ProgressFilter.ALL,
    ]


def test_a_session_without_one_event_renders_the_base_state() -> None:
    assert progress_body(SessionState()) == EXECUTION_EMPTY
    assert EXECUTION_EMPTY in execution_body(SessionState())


def test_one_row_carries_its_glyph_its_state_word_its_task_and_its_percentage() -> None:
    body: str = progress_body(_session((_task_started(1), _task_progress(2, _HALF_PERCENT))))
    row: str = body.splitlines()[-1]
    assert row.startswith(EXECUTION_RUNNING_GLYPH)
    assert _ALPHA in row
    assert EXECUTION_STATE_RUNNING in row
    assert _TASK_LABEL in row
    assert f"{_HALF_PERCENT}%" in row


def test_every_row_state_carries_its_own_glyph_and_its_own_word() -> None:
    body: str = progress_body(
        _session(
            (
                _task_started(1),
                _task_started(2, group_id=_BETA, task_id=_OTHER_TASK),
                _group_finished(3, TaskState.SUCCEEDED, group_id=_BETA),
                _task_started(4, group_id="group-gamma", task_id=_OTHER_TASK),
                _group_finished(5, TaskState.FAILED, group_id="group-gamma"),
                _task_started(6, group_id="group-delta", task_id=_OTHER_TASK),
                _group_finished(7, TaskState.CANCELLED, group_id="group-delta"),
            ),
        ),
    )
    assert EXECUTION_RUNNING_GLYPH in body
    assert EXECUTION_DONE_GLYPH in body
    assert EXECUTION_FAILED_GLYPH in body
    assert EXECUTION_CANCELLED_GLYPH in body
    assert EXECUTION_STATE_DONE in body
    assert EXECUTION_STATE_FAILED in body
    assert EXECUTION_STATE_CANCELLED in body


def test_a_group_queued_and_never_started_keeps_the_waiting_word() -> None:
    body: str = progress_body(_session((_queued(1),)))
    assert EXECUTION_WAITING_GLYPH in body
    assert EXECUTION_STATE_WAITING in body


def test_the_summary_counts_only_the_groups_that_reached_an_end() -> None:
    body: str = progress_body(
        _session(
            (
                _task_started(1),
                _task_started(2, group_id=_BETA, task_id=_OTHER_TASK),
                _group_finished(3, TaskState.SUCCEEDED, group_id=_BETA),
            ),
        ),
    )
    assert EXECUTION_SUMMARY.format(done=1, total=2) in body


def test_a_run_asked_to_stop_says_so_above_its_rows() -> None:
    state: SessionState = _session((_task_started(1),))
    assert TOOLS_RUN_CANCELLING not in progress_body(state)
    state.run_state = RunUiState.CANCELLING
    body: str = progress_body(state)
    assert TOOLS_RUN_CANCELLING in body.splitlines()[1]


def test_a_narrowed_table_names_the_filter_it_lists_under() -> None:
    state: SessionState = _session((_task_started(1),))
    assert EXECUTION_FILTER_LABEL not in progress_body(state)
    body: str = progress_body(state, listed=ProgressFilter.RUNNING)
    assert f"{EXECUTION_FILTER_LABEL} {EXECUTION_STATE_RUNNING}" in body


def test_a_collapsed_row_shows_its_last_detail_and_an_expanded_row_shows_all_of_them() -> None:
    state: SessionState = _session(
        (
            _task_started(1),
            _detail(2, RunEventKind.TASK_RETRY, _RETRY_MESSAGE),
            _detail(3, RunEventKind.TASK_FALLBACK, _FALLBACK_MESSAGE),
        ),
    )
    collapsed: str = progress_body(state)
    assert _RETRY_MESSAGE not in collapsed
    assert _FALLBACK_MESSAGE in collapsed
    expanded: str = progress_body(state, details=True)
    assert _RETRY_MESSAGE in expanded
    assert _FALLBACK_MESSAGE in expanded


def test_the_execution_body_carries_the_heading_of_the_screen() -> None:
    assert execution_body(_session((_task_started(1),))).startswith(EXECUTION_TITLE)


def test_no_cancel_is_available_outside_a_run_that_is_working() -> None:
    state: SessionState = SessionState()
    state.active_run_id = _RUN_ID
    for run_state in (RunUiState.IDLE, RunUiState.PLANNING, RunUiState.CANCELLING, RunUiState.TERMINAL):
        state.run_state = run_state
        assert cancel_available(state) is False


def test_no_cancel_is_available_while_a_run_announced_no_identity() -> None:
    state: SessionState = SessionState()
    state.run_state = RunUiState.RUNNING
    assert cancel_available(state) is False
    state.active_run_id = _RUN_ID
    assert cancel_available(state) is True


def test_no_cancel_and_no_filter_is_available_while_a_dialog_covers_the_run() -> None:
    state: SessionState = SessionState()
    state.run_state = RunUiState.RUNNING
    state.active_run_id = _RUN_ID
    state.modal_focus_stack.append(None)
    assert cancel_available(state) is False
    assert table_available(state) is False


def test_a_started_run_opens_the_execution_screen_and_renders_the_groups_it_names(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            assert app.session_state.route is UiRoute.EXECUTION
            assert _view(app).display is True
            body: str = _body(app)
            assert EXECUTION_TITLE in body
            assert _ALPHA in body
            assert _TASK_LABEL in body
            assert f"{_HALF_PERCENT}%" in body

    _finally(scenario(), gate)


def test_the_execution_screen_offers_its_three_actions_only_while_it_is_on_screen(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            assert app.commands.command(CANCEL_COMMAND_NAME) is None
            await _start(app, pilot)
            assert app.commands.command(CANCEL_COMMAND_NAME) is not None
            assert app.commands.command(FILTER_COMMAND_NAME) is not None
            assert app.commands.command(DETAILS_COMMAND_NAME) is not None
            assert _cancel_row(app) is not None
            gate.set()
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert app.commands.command(CANCEL_COMMAND_NAME) is None
            assert app.commands.command(FILTER_COMMAND_NAME) is None
            assert app.commands.command(DETAILS_COMMAND_NAME) is None

    _finally(scenario(), gate)


def test_the_execution_screen_registers_its_own_scope_once(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            _view(app).on_show()
            _view(app).on_show()
            await _settle(pilot)
            assert app.commands.command(CANCEL_COMMAND_NAME) is not None
            app.commands.unregister(EXECUTION_SCOPE)
            assert app.commands.command(CANCEL_COMMAND_NAME) is None

    _finally(scenario(), gate)


def test_the_slash_catalogue_stays_the_same_while_a_run_is_watched(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            assert len(app.commands.slash_names()) == _CATALOG_COMMANDS
            await _start(app, pilot)
            assert len(app.commands.slash_names()) == _CATALOG_COMMANDS

    _finally(scenario(), gate)


def test_the_cancel_key_asks_before_it_stops_anything(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.press(CANCEL_KEY)
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            assert stub.cancelled == []
            assert app.session_state.run_state is RunUiState.RUNNING
            assert EXECUTION_CANCEL_TITLE in _rendered(app)
            assert EXECUTION_CANCEL_QUESTION in _rendered(app)

    _finally(scenario(), gate)


def test_a_confirmed_cancel_stops_the_run_exactly_once(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.press(CANCEL_KEY)
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("enter")
            await _until(pilot, lambda: stub.cancelled == [_RUN_ID])
            assert app.session_state.run_state is RunUiState.CANCELLING
            assert TOOLS_RUN_CANCELLING in _body(app)
            await pilot.press(CANCEL_KEY)
            await _settle(pilot)
            assert app.commands.dispatch(CANCEL_COMMAND_NAME) is False
            assert app.cancel_run() is False
            await _settle(pilot)
            assert stub.cancelled == [_RUN_ID]

    _finally(scenario(), gate)


def test_a_refused_cancel_leaves_the_run_working(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.press(CANCEL_KEY)
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("escape")
            await _settle(pilot)
            assert stub.cancelled == []
            assert app.session_state.run_state is RunUiState.RUNNING
            assert app.session_state.route is UiRoute.EXECUTION

    _finally(scenario(), gate)


def test_the_escape_key_alone_never_stops_a_run(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.press("escape", "escape")
            await _settle(pilot)
            assert stub.cancelled == []
            assert app.session_state.run_state is RunUiState.RUNNING
            assert app.session_state.route is UiRoute.EXECUTION

    _finally(scenario(), gate)


def test_the_cancel_action_and_its_key_ask_the_very_same_question(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            assert app.commands.dispatch(CANCEL_COMMAND_NAME) is True
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")
            await pilot.press("escape")
            await _settle(pilot)
            assert app.commands.dispatch_key(CANCEL_KEY) is True
            await _until(pilot, lambda: _top_dialog(app) == "ConfirmDialog")

    _finally(scenario(), gate)


def test_the_filter_key_narrows_the_listed_groups_without_touching_the_events(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate, finish_beta=True)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await _until(pilot, lambda: _BETA in _body(app))
            events: int = len(app.session_state.events)
            await pilot.press(FILTER_KEY)
            await _settle(pilot)
            assert _view(app).listed is ProgressFilter.RUNNING
            assert _ALPHA in _body(app)
            assert _BETA not in _body(app)
            await pilot.press(FILTER_KEY, FILTER_KEY)
            await _settle(pilot)
            assert _view(app).listed is ProgressFilter.DONE
            assert _BETA in _body(app)
            assert _ALPHA not in _body(app)
            assert len(app.session_state.events) == events

    _finally(scenario(), gate)


def test_the_details_key_opens_every_detail_of_every_row(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate, detailed=True)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await _until(pilot, lambda: _FALLBACK_MESSAGE in _body(app))
            assert _RETRY_MESSAGE not in _body(app)
            await pilot.press(DETAILS_KEY)
            await _settle(pilot)
            assert _view(app).details is True
            assert _RETRY_MESSAGE in _body(app)
            await pilot.press(DETAILS_KEY)
            await _settle(pilot)
            assert _RETRY_MESSAGE not in _body(app)

    _finally(scenario(), gate)


def test_one_drained_batch_of_events_repaints_the_screen_exactly_once(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _watch(app, pilot)
            painted: list[int] = _counted_paints(_view(app))
            app.post_message(_batch(app))
            await _settle(pilot)
            assert painted[0] == 1
            app.post_message(_batch(app, first=_BATCH_EVENTS + 1))
            await _settle(pilot)
            assert painted[0] == 2
            assert len(app.session_state.events) == _BATCH_EVENTS * 2

    asyncio.run(scenario())


def test_a_run_that_ended_paints_its_last_frame_and_then_leaves_the_screen(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate, finish_beta=True)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            gate.set()
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert app.session_state.route is UiRoute.WORKSPACE
            assert _view(app).display is False
            body: str = _body(app)
            assert EXECUTION_STATE_RUNNING not in body
            assert EXECUTION_SUMMARY.format(done=2, total=2) in body

    _finally(scenario(), gate)


def test_the_composer_and_the_palette_stay_usable_while_a_run_is_watched(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.press(*_TYPED_TEXT)
            await _settle(pilot)
            assert _TYPED_TEXT in _rendered(app)
            await pilot.press("ctrl+p")
            await _until(pilot, lambda: _top_dialog(app) == "SelectDialog")
            await pilot.press("escape")
            await _settle(pilot)
            assert app.session_state.route is UiRoute.EXECUTION
            assert _ALPHA in _body(app)

    _finally(scenario(), gate)


def test_a_resize_keeps_the_watched_run_on_screen(stub: StubService) -> None:
    gate: threading.Event = threading.Event()
    _gated(stub, gate)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await _start(app, pilot)
            await pilot.resize_terminal(*_NARROW_SIZE)
            await _settle(pilot)
            assert _ALPHA in _body(app)
            await pilot.resize_terminal(*_FULL_SIZE)
            await _settle(pilot)
            assert _ALPHA in _rendered(app)

    _finally(scenario(), gate)


def _run_started() -> RunEvent:
    return RunEvent(run_id=_RUN_ID, sequence=1, kind=RunEventKind.RUN_STARTED)


def _queued(sequence: int, group_id: str = _ALPHA, task_id: str = _TASK) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=RunEventKind.TASK_QUEUED,
        group_id=group_id,
        task_id=task_id,
        state=TaskState.QUEUED,
    )


def _task_started(sequence: int, group_id: str = _ALPHA, task_id: str = _TASK) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=RunEventKind.TASK_STARTED,
        group_id=group_id,
        task_id=task_id,
        state=TaskState.RUNNING,
    )


def _task_progress(sequence: int, percent: int, group_id: str = _ALPHA, task_id: str = _TASK) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=RunEventKind.TASK_PROGRESS,
        group_id=group_id,
        task_id=task_id,
        progress_percent=percent,
    )


def _group_finished(sequence: int, state: TaskState, group_id: str = _ALPHA) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=RunEventKind.GROUP_FINISHED,
        group_id=group_id,
        state=state,
    )


def _run_finished(sequence: int, state: TaskState) -> RunEvent:
    return RunEvent(run_id=_RUN_ID, sequence=sequence, kind=RunEventKind.RUN_FINISHED, state=state)


def _detail(
    sequence: int,
    kind: RunEventKind,
    message: str | None = None,
    group_id: str = _ALPHA,
) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=kind,
        group_id=group_id,
        task_id=_TASK,
        message=message,
    )


def _session(events: tuple[RunEvent, ...]) -> SessionState:
    state: SessionState = SessionState()
    state.route = UiRoute.EXECUTION
    state.run_state = RunUiState.RUNNING
    state.active_run_id = _RUN_ID
    state.events.extend(events)
    return state


def _batch(app: AniShiftApp, first: int = 1) -> RunProgressed:
    events: tuple[RunEvent, ...] = tuple(
        _task_progress(first + step, min(_FULL_PERCENT, first + step)) for step in range(_BATCH_EVENTS)
    )
    return RunProgressed(events=events, run_id=_RUN_ID, generation=app.session_state.generation)


def _gated(
    stub: StubService,
    gate: threading.Event,
    *,
    finish_beta: bool = False,
    detailed: bool = False,
) -> None:
    def emit(sink: RunEventSink) -> None:
        emitter: RunEventEmitter = RunEventEmitter(_RUN_ID, sink)
        emitter.emit(RunEventKind.RUN_STARTED)
        emitter.emit(RunEventKind.TASK_STARTED, group_id=_ALPHA, task_id=_TASK, state=TaskState.RUNNING)
        emitter.emit(
            RunEventKind.TASK_PROGRESS,
            group_id=_ALPHA,
            task_id=_TASK,
            progress_percent=_HALF_PERCENT,
        )
        if detailed:
            emitter.emit(RunEventKind.TASK_RETRY, group_id=_ALPHA, task_id=_TASK, message=_RETRY_MESSAGE)
            emitter.emit(RunEventKind.TASK_FALLBACK, group_id=_ALPHA, task_id=_TASK, message=_FALLBACK_MESSAGE)
        if finish_beta:
            emitter.emit(
                RunEventKind.TASK_STARTED,
                group_id=_BETA,
                task_id=_OTHER_TASK,
                state=TaskState.RUNNING,
            )
            emitter.emit(RunEventKind.GROUP_FINISHED, group_id=_BETA, state=TaskState.SUCCEEDED)
        gate.wait(_RUN_GATE_SECONDS)
        emitter.emit(RunEventKind.RUN_FINISHED, state=TaskState.SUCCEEDED)

    stub.emit = emit
    stub.result = stub_result(_RUN_ID)


async def _start(app: AniShiftApp, pilot: Any) -> None:
    await pilot.pause()
    assert begin_planning(app.session_state) is not None
    assert app.start_execution(stub_plan()) is True
    await _until(pilot, lambda: app.session_state.run_state is RunUiState.RUNNING)
    await _until(pilot, lambda: _ALPHA in _body(app))


async def _watch(app: AniShiftApp, pilot: Any) -> None:
    await pilot.pause()
    assert begin_planning(app.session_state) is not None
    assert begin_run(app.session_state, _RUN_ID) is True
    app.post_message(NavigationRequested(UiRoute.EXECUTION))
    await _settle(pilot)


def _view(app: AniShiftApp) -> ExecutionView:
    return app.query_one(ExecutionView)


def _body(app: AniShiftApp) -> str:
    return str(_view(app).content)


def _rendered(app: AniShiftApp) -> str:
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


def _top_dialog(app: AniShiftApp) -> str:
    return type(app.screen).__name__


def _cancel_row(app: AniShiftApp) -> CommandOption | None:
    return next((row for row in palette_options(app.commands) if row.label == EXECUTION_CANCEL_TITLE), None)


def _counted_paints(view: ExecutionView) -> list[int]:
    counted: list[int] = [0]
    paint: Callable[[SessionState], None] = view.show

    def counting(state: SessionState) -> None:
        counted[0] += 1
        paint(state)

    view.show = counting  # type: ignore[method-assign]
    return counted


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


def _finally(scenario: Coroutine[Any, Any, None], gate: threading.Event) -> None:
    try:
        asyncio.run(scenario)
    finally:
        gate.set()
