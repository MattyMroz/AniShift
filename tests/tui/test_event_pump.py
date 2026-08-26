from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.message import Message
from tui_fakes import RecordingHost, StubService, emit_full_run, shell, stub_plan, stub_result

from anishift.application import RunEvent, RunEventKind, RunEventSink
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.lifecycle import begin_planning, begin_run, finish_run
from anishift.tui.messages import RunProgressed
from anishift.tui.state import RunUiState
from anishift.tui.workers import DRAIN_INTERVAL_SECONDS, STATE_EVENT_LIMIT, RunEventPump, flush

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_PAUSE_LIMIT: Final[int] = 400

_SETTLE_TURNS: Final[int] = 50

_GENERATION: Final[int] = 4

_RUN_ID: Final[str] = "run-a"

_OTHER_RUN_ID: Final[str] = "run-b"

_TASK_ID: Final[str] = "task-1"

_OTHER_TASK_ID: Final[str] = "task-2"

_OVERFLOW_FACTOR: Final[int] = 3

_MIN_DRAIN_SECONDS: Final[float] = 0.05

_MAX_DRAIN_SECONDS: Final[float] = 0.1

_GATE_TIMEOUT_SECONDS: Final[float] = 5.0

_CADENCE_DEADLINE_SECONDS: Final[float] = 3.0

_POLL_SECONDS: Final[float] = 0.005


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    return tmp_path


def test_the_drain_interval_stays_inside_the_specified_window() -> None:
    assert _MIN_DRAIN_SECONDS <= DRAIN_INTERVAL_SECONDS <= _MAX_DRAIN_SECONDS


@pytest.mark.usefixtures("isolated")
def test_the_timer_drains_repeatedly_while_the_run_is_still_working() -> None:
    stub: StubService = StubService()
    stub.result = stub_result(_RUN_ID)
    released: threading.Event = threading.Event()
    finished: threading.Event = threading.Event()

    def emit(sink: RunEventSink) -> None:
        sink.emit(_event(1, RunEventKind.RUN_STARTED))
        assert released.wait(timeout=_GATE_TIMEOUT_SECONDS)
        sink.emit(_progress(2, percent=40))
        assert finished.wait(timeout=_GATE_TIMEOUT_SECONDS)
        sink.emit(_event(3, RunEventKind.RUN_FINISHED))

    stub.emit = emit

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert begin_planning(app.session_state) is not None
            assert app.start_execution(stub_plan()) is True
            await _until_ticking(pilot, lambda: app.session_state.active_run_id == _RUN_ID)
            assert [event.kind for event in app.session_state.events] == [RunEventKind.RUN_STARTED]
            released.set()
            await _until_ticking(pilot, lambda: len(app.session_state.events) == 2)
            assert app.session_state.events[1].kind is RunEventKind.TASK_PROGRESS
            assert app.is_draining is True
            finished.set()
            await _until_ticking(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert [event.kind for event in app.session_state.events] == [
                RunEventKind.RUN_STARTED,
                RunEventKind.TASK_PROGRESS,
                RunEventKind.RUN_FINISHED,
            ]
            assert app.is_draining is False

    _run(scenario())


def test_the_pump_answers_no_run_identity_before_its_first_event() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    assert pump.run_id is None
    assert pump.generation == _GENERATION
    assert pump.drain() == ()


def test_the_pump_takes_the_run_identity_from_its_first_event() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_event(1, RunEventKind.RUN_STARTED))
    pump.emit(_event(2, RunEventKind.TASK_QUEUED, run_id=_OTHER_RUN_ID))
    assert pump.run_id == _RUN_ID


def test_the_pump_keeps_only_the_newest_progress_of_one_task() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    for step in range(50):
        pump.emit(_progress(step + 1, percent=step))
    drained: tuple[RunEvent, ...] = pump.drain()
    assert [event.progress_percent for event in drained] == [49]


def test_the_pump_keeps_the_newest_progress_of_every_task_apart() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_progress(1, percent=10))
    pump.emit(_progress(2, percent=20, task_id=_OTHER_TASK_ID))
    pump.emit(_progress(3, percent=30))
    drained: tuple[RunEvent, ...] = pump.drain()
    assert sorted((event.task_id or "", event.progress_percent or 0) for event in drained) == [
        (_TASK_ID, 30),
        (_OTHER_TASK_ID, 20),
    ]


def test_the_pump_never_reorders_an_older_progress_over_a_newer_one() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_progress(9, percent=90))
    pump.emit(_progress(4, percent=40))
    assert [event.progress_percent for event in pump.drain()] == [90]


def test_the_pump_returns_every_event_in_run_and_sequence_order() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_event(3, RunEventKind.TASK_STARTED))
    pump.emit(_event(1, RunEventKind.RUN_STARTED))
    pump.emit(_progress(4, percent=50))
    pump.emit(_event(2, RunEventKind.TASK_QUEUED))
    pump.emit(_event(5, RunEventKind.RUN_FINISHED))
    assert [event.sequence for event in pump.drain()] == [1, 2, 3, 4, 5]


def test_the_pump_never_lets_a_terminal_event_overtake_its_progress() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_event(2, RunEventKind.RUN_FINISHED))
    pump.emit(_progress(1, percent=99))
    drained: tuple[RunEvent, ...] = pump.drain()
    assert [event.kind for event in drained] == [RunEventKind.TASK_PROGRESS, RunEventKind.RUN_FINISHED]


def test_the_pump_never_grows_past_its_state_bound() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pushed: int = STATE_EVENT_LIMIT * _OVERFLOW_FACTOR
    for sequence in range(1, pushed + 1):
        pump.emit(_event(sequence, RunEventKind.TASK_QUEUED))
    drained: tuple[RunEvent, ...] = pump.drain()
    assert len(drained) == STATE_EVENT_LIMIT
    assert drained[-1].sequence == pushed
    assert drained[0].sequence == pushed - STATE_EVENT_LIMIT + 1


def test_the_pump_keeps_the_terminal_event_and_the_last_progress_past_its_bound() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pushed: int = STATE_EVENT_LIMIT * _OVERFLOW_FACTOR
    pump.emit(_event(1, RunEventKind.RUN_FINISHED))
    for sequence in range(2, pushed + 2):
        pump.emit(_event(sequence, RunEventKind.TASK_QUEUED))
        pump.emit(_progress(sequence, percent=sequence % 100))
    drained: tuple[RunEvent, ...] = pump.drain()
    terminal: list[RunEvent] = [event for event in drained if event.kind is RunEventKind.RUN_FINISHED]
    progress: list[RunEvent] = [event for event in drained if event.kind is RunEventKind.TASK_PROGRESS]
    assert len(terminal) == 1
    assert len(progress) == 1
    assert progress[0].sequence == pushed + 1
    assert len(drained) == STATE_EVENT_LIMIT + 2


def test_a_drained_batch_carries_the_generation_of_its_own_run() -> None:
    host: RecordingHost = RecordingHost()
    pump: RunEventPump = RunEventPump(_GENERATION)
    flush(host, pump)
    assert host.messages == []
    pump.emit(_event(1, RunEventKind.RUN_STARTED))
    flush(host, pump)
    delivered: Message = host.messages[0]
    assert isinstance(delivered, RunProgressed)
    assert delivered.generation == _GENERATION
    assert delivered.run_id == _RUN_ID
    assert len(host.messages) == 1


def test_the_pump_forgets_every_event_it_handed_over() -> None:
    pump: RunEventPump = RunEventPump(_GENERATION)
    pump.emit(_event(1, RunEventKind.RUN_STARTED))
    pump.emit(_progress(2, percent=5))
    pump.emit(_event(3, RunEventKind.RUN_FINISHED))
    assert len(pump.drain()) == 3
    assert pump.drain() == ()
    assert pump.run_id == _RUN_ID


@pytest.mark.usefixtures("isolated")
def test_the_shell_records_the_coalesced_events_of_the_run_it_ran() -> None:
    stub: StubService = StubService()
    stub.emit = lambda sink: emit_full_run(sink, _RUN_ID, progress=25)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert begin_planning(app.session_state) is not None
            assert app.start_execution(stub_plan()) is True
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            kinds: list[RunEventKind] = [event.kind for event in app.session_state.events]
            assert kinds == [RunEventKind.RUN_STARTED, RunEventKind.TASK_PROGRESS, RunEventKind.RUN_FINISHED]
            assert app.session_state.active_run_id is None
            assert app.session_state.result is not None
            assert app.session_state.result.run_id == _RUN_ID

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_drain_timer_runs_only_while_a_run_is_active() -> None:
    stub: StubService = StubService()
    stub.emit = lambda sink: emit_full_run(sink, _RUN_ID)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            baseline: int = _running_timers(app)
            assert app.is_draining is False
            assert begin_planning(app.session_state) is not None
            assert app.start_execution(stub_plan()) is True
            assert app.is_draining is True
            assert _running_timers(app) == baseline + 1
            await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
            assert app.is_draining is False
            assert _running_timers(app) == baseline

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_two_consecutive_runs_leave_no_timer_behind() -> None:
    stub: StubService = StubService()
    stub.emit = lambda sink: emit_full_run(sink, _RUN_ID)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            baseline: int = _running_timers(app)
            for _ in range(2):
                assert begin_planning(app.session_state) is not None
                assert app.start_execution(stub_plan()) is True
                await _until(pilot, lambda: app.session_state.run_state is RunUiState.TERMINAL)
                assert _running_timers(app) == baseline
                assert app.is_draining is False
            assert app.session_state.generation == 2

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_a_second_execution_is_refused_while_the_first_one_still_drains() -> None:
    stub: StubService = StubService()
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert begin_planning(app.session_state) is not None
            assert app.start_execution(stub_plan()) is True
            assert app.start_execution(stub_plan()) is False
            await _until(pilot, lambda: app.is_draining is False)
            assert stub.calls == ["execute"]
            assert app.session_state.run_state is RunUiState.TERMINAL

    _run(scenario())


@pytest.mark.parametrize("state", [RunUiState.IDLE, RunUiState.RUNNING, RunUiState.TERMINAL])
@pytest.mark.usefixtures("isolated")
def test_an_execution_asked_for_outside_planning_starts_nothing(state: RunUiState) -> None:
    stub: StubService = StubService()
    stub.emit = lambda sink: emit_full_run(sink, _RUN_ID)
    stub.result = stub_result(_RUN_ID)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _drive_to(app, state)
            baseline: int = _running_timers(app)
            before: tuple[Any, ...] = _snapshot(app)
            assert app.start_execution(stub_plan()) is False
            for _ in range(_SETTLE_TURNS):
                await pilot.pause()
            assert stub.calls == []
            assert list(app.workers) == []
            assert app._pump is None
            assert app._drain_timer is None
            assert _running_timers(app) == baseline
            assert app.is_draining is False
            assert _snapshot(app) == before

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_draining_outside_a_run_delivers_nothing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.drain_run_events()
            await pilot.pause()
            assert app.session_state.events == []
            assert app.is_draining is False

    _run(scenario())


def _event(sequence: int, kind: RunEventKind, run_id: str = _RUN_ID) -> RunEvent:
    return RunEvent(run_id=run_id, sequence=sequence, kind=kind)


def _progress(sequence: int, *, percent: int, task_id: str = _TASK_ID) -> RunEvent:
    return RunEvent(
        run_id=_RUN_ID,
        sequence=sequence,
        kind=RunEventKind.TASK_PROGRESS,
        task_id=task_id,
        progress_percent=percent,
    )


def _drive_to(app: AniShiftApp, state: RunUiState) -> None:
    if state is RunUiState.IDLE:
        return
    assert begin_planning(app.session_state) is not None
    assert begin_run(app.session_state, _RUN_ID) is True
    if state is RunUiState.TERMINAL:
        assert finish_run(app.session_state, stub_result(_RUN_ID)) is True
    assert app.session_state.run_state is state


def _snapshot(app: AniShiftApp) -> tuple[Any, ...]:
    state = app.session_state
    return (
        state.run_state,
        state.generation,
        state.active_run_id,
        tuple(state.events),
        state.plan,
        state.result,
        state.feedback,
    )


def _running_timers(app: AniShiftApp) -> int:
    return len([timer for timer in app._timers if timer._task is not None])


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


async def _until_ticking(pilot: Any, ready: Callable[[], bool]) -> None:
    deadline: float = time.monotonic() + _CADENCE_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if ready():
            return
        await pilot.pause()
        await asyncio.sleep(_POLL_SECONDS)
