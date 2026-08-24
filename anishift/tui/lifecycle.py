"""State transitions of one session, free of domain logic and I/O.

Every function moves ``SessionState`` forward or decides whether a late message
still belongs to the current view. Nothing here plans, executes, reads files or
talks to a provider: the shell calls these operations, the application layer
owns the work itself.

Public API:
    ALLOWED_RUN_TRANSITIONS: The only accepted run-state edges.
    run_transition_allowed: Whether one run-state edge is accepted.
    accepts_message: Whether a late message may still change the view.
    navigate: Show another route without disturbing run or drafts.
    set_workspace: Store an inspection and keep the surviving selection.
    report_error: Keep redacted failure feedback that no run owns.
    begin_planning: Reserve a new generation and start planning.
    plan_ready: Store a plan awaiting preview or start.
    abandon_planning: Drop planning and keep its reason.
    begin_run: Enter the run the planner produced.
    record_run_events: Append accepted events of the active run.
    request_cancel: Ask the active run to stop.
    finish_run: Store the terminal result of the active run.
    fail_run: End the active run without a result.
    open_modal: Remember the focus a modal layer must restore.
    close_modal: Restore the focus of the closing modal layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.tui.state import RunUiState, UiFeedback

if TYPE_CHECKING:
    from collections.abc import Iterable

    from anishift.application import ExecutionPlan, InspectedWorkspace, RunEvent, RunResult
    from anishift.tui.state import SessionState, UiRoute

__all__ = [
    "ALLOWED_RUN_TRANSITIONS",
    "abandon_planning",
    "accepts_message",
    "begin_planning",
    "begin_run",
    "close_modal",
    "fail_run",
    "finish_run",
    "navigate",
    "open_modal",
    "plan_ready",
    "record_run_events",
    "report_error",
    "request_cancel",
    "run_transition_allowed",
    "set_workspace",
]

# ── Constants ──────────────────────────────────────────────────────────────

ALLOWED_RUN_TRANSITIONS: Final[Mapping[RunUiState, frozenset[RunUiState]]] = MappingProxyType(
    {
        RunUiState.IDLE: frozenset({RunUiState.PLANNING}),
        RunUiState.PLANNING: frozenset({RunUiState.IDLE, RunUiState.RUNNING}),
        RunUiState.RUNNING: frozenset({RunUiState.CANCELLING, RunUiState.TERMINAL}),
        RunUiState.CANCELLING: frozenset({RunUiState.TERMINAL}),
        RunUiState.TERMINAL: frozenset({RunUiState.PLANNING}),
    },
)
"""The only accepted run-state edges; every other move is a shell defect."""


def run_transition_allowed(current: RunUiState, target: RunUiState) -> bool:
    """Whether moving from *current* to *target* is an accepted run edge."""
    return target in ALLOWED_RUN_TRANSITIONS[current]


def accepts_message(state: SessionState, *, generation: int, run_id: str | None = None) -> bool:
    """Whether a message of *generation* may still change the current view.

    A message from any other generation, or from a run the session no longer
    tracks, is late and must be dropped.
    """
    if generation != state.generation:
        return False
    if run_id is None:
        return True
    return run_id == state.active_run_id


def navigate(state: SessionState, route: UiRoute) -> bool:
    """Show *route* without touching the active run, the plan or any draft."""
    if state.route is route:
        return False
    state.route = route
    return True


def set_workspace(state: SessionState, workspace: InspectedWorkspace) -> None:
    """Store an inspection, keeping only selection and drafts that survive it."""
    state.workspace = workspace
    known: set[str] = {group.group_id for group in workspace.groups}
    state.selected_group_ids &= known
    state.manual_drafts = {group_id: draft for group_id, draft in state.manual_drafts.items() if group_id in known}


def report_error(state: SessionState, reason: str) -> None:
    """Keep failure feedback no run owns, such as a failed inspection."""
    state.feedback = UiFeedback.error(reason)


def begin_planning(state: SessionState) -> int | None:
    """Reserve a new generation for planning, or refuse an illegal moment."""
    if not _enter(state, RunUiState.PLANNING):
        return None
    state.generation += 1
    state.plan = None
    state.result = None
    state.feedback = None
    state.active_run_id = None
    state.events.clear()
    return state.generation


def plan_ready(state: SessionState, plan: ExecutionPlan) -> None:
    """Store the plan the session may preview and start."""
    state.plan = plan


def abandon_planning(state: SessionState, reason: str) -> bool:
    """Leave planning without a run and keep its redacted reason."""
    if not _enter(state, RunUiState.IDLE):
        return False
    state.plan = None
    state.feedback = UiFeedback.error(reason)
    return True


def begin_run(state: SessionState, run_id: str) -> bool:
    """Enter the run the planner produced, or refuse an illegal moment."""
    if not _enter(state, RunUiState.RUNNING):
        return False
    state.active_run_id = run_id
    return True


def record_run_events(state: SessionState, events: Iterable[RunEvent]) -> None:
    """Append events the shell already accepted for the active run."""
    state.events.extend(events)


def request_cancel(state: SessionState) -> bool:
    """Ask the active run to stop; the run stays until it is terminal."""
    return _enter(state, RunUiState.CANCELLING)


def finish_run(state: SessionState, result: RunResult) -> bool:
    """Store the terminal result and release the active run."""
    if not _enter(state, RunUiState.TERMINAL):
        return False
    state.result = result
    state.active_run_id = None
    return True


def fail_run(state: SessionState, reason: str) -> bool:
    """End the active run without a result, keeping its redacted reason."""
    if not _enter(state, RunUiState.TERMINAL):
        return False
    state.feedback = UiFeedback.error(reason)
    state.active_run_id = None
    return True


def open_modal(state: SessionState, focus_id: str | None) -> None:
    """Remember the focus the closing modal layer will have to restore."""
    state.modal_focus_stack.append(focus_id)


def close_modal(state: SessionState) -> str | None:
    """Restore and return the focus the closing modal layer remembered."""
    if not state.modal_focus_stack:
        return None
    state.focus_id = state.modal_focus_stack.pop()
    return state.focus_id


def _enter(state: SessionState, target: RunUiState) -> bool:
    """Apply one run-state edge, refusing every move outside the contract."""
    if not run_transition_allowed(state.run_state, target):
        return False
    state.run_state = target
    return True
