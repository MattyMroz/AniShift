"""State transitions of one session, free of domain logic and of I/O."""

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
"""The only accepted run-state edges, keyed by the current state."""


def run_transition_allowed(current: RunUiState, target: RunUiState) -> bool:
    """Whether moving from *current* to *target* is an accepted run edge."""
    return target in ALLOWED_RUN_TRANSITIONS[current]


def accepts_message(state: SessionState, *, generation: int, run_id: str | None = None) -> bool:
    """Whether a message of *generation*, and of *run_id* when given, is still current."""
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
    """Move the active run into the cancelling state, keeping it tracked."""
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
