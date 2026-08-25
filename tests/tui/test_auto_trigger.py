from __future__ import annotations

from typing import Final

import pytest

from anishift.tui import auto_trigger
from anishift.tui.state import RunUiState, SessionState, UiFeedback

_REASON: Final[str] = "Nie udało się zbudować planu"

_BUSY_STATES: Final[tuple[RunUiState, ...]] = (
    RunUiState.PLANNING,
    RunUiState.RUNNING,
    RunUiState.CANCELLING,
)

_BURST: Final[int] = 12


def test_reserve_hands_out_a_new_generation_from_idle() -> None:
    state: SessionState = SessionState()
    assert auto_trigger.reserve(state) == 1
    assert state.run_state is RunUiState.PLANNING
    assert state.generation == 1


def test_a_second_reserve_hands_out_nothing_and_keeps_the_first_generation() -> None:
    state: SessionState = SessionState()
    first: int | None = auto_trigger.reserve(state)
    second: int | None = auto_trigger.reserve(state)
    assert (first, second) == (1, None)
    assert state.generation == 1
    assert state.run_state is RunUiState.PLANNING


def test_a_burst_of_reserves_creates_exactly_one_generation() -> None:
    state: SessionState = SessionState()
    handed: list[int | None] = [auto_trigger.reserve(state) for _ in range(_BURST)]
    assert handed == [1, *([None] * (_BURST - 1))]
    assert state.generation == 1


@pytest.mark.parametrize("busy", _BUSY_STATES)
def test_reserve_is_refused_in_every_busy_run_state(busy: RunUiState) -> None:
    state: SessionState = SessionState()
    state.run_state = busy
    assert auto_trigger.reserve(state) is None
    assert state.generation == 0
    assert state.run_state is busy


def test_reserve_works_again_after_a_terminal_result() -> None:
    state: SessionState = SessionState()
    assert auto_trigger.reserve(state) == 1
    state.run_state = RunUiState.TERMINAL
    assert auto_trigger.reserve(state) == 2
    assert state.run_state is RunUiState.PLANNING


def test_release_of_the_reserved_generation_opens_the_gate_again() -> None:
    state: SessionState = SessionState()
    generation: int | None = auto_trigger.reserve(state)
    assert generation is not None
    assert auto_trigger.release(state, generation=generation, reason=_REASON) is True
    assert state.run_state is RunUiState.IDLE
    assert state.feedback == UiFeedback.error(_REASON)
    assert auto_trigger.reserve(state) == generation + 1


def test_release_of_a_foreign_generation_changes_nothing() -> None:
    state: SessionState = SessionState()
    generation: int | None = auto_trigger.reserve(state)
    assert generation is not None
    assert auto_trigger.release(state, generation=generation + 1, reason=_REASON) is False
    assert auto_trigger.release(state, generation=generation - 1, reason=_REASON) is False
    assert state.run_state is RunUiState.PLANNING
    assert state.feedback is None
    assert auto_trigger.reserve(state) is None


def test_a_late_release_never_frees_the_reservation_that_replaced_it() -> None:
    state: SessionState = SessionState()
    abandoned: int | None = auto_trigger.reserve(state)
    assert abandoned is not None
    assert auto_trigger.release(state, generation=abandoned, reason=_REASON) is True
    current: int | None = auto_trigger.reserve(state)
    assert current == abandoned + 1
    assert auto_trigger.release(state, generation=abandoned, reason=_REASON) is False
    assert state.run_state is RunUiState.PLANNING
    assert state.generation == current
    assert state.feedback is None
    assert auto_trigger.reserve(state) is None


def test_release_without_a_reservation_starts_nothing_of_its_own() -> None:
    state: SessionState = SessionState()
    assert auto_trigger.release(state, generation=state.generation, reason=_REASON) is False
    assert state.run_state is RunUiState.IDLE
    assert state.generation == 0
    assert state.feedback is None
