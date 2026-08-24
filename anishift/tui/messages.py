"""Typed presentation messages exchanged inside the shell.

Every message a worker can deliver late carries the generation it was created
for, and every run message also carries its ``run_id``, so the shell can drop
the answer of an interaction the user already abandoned.

Public API:
    NavigationRequested: Ask the host to show another route.
    CommandSubmitted: Composer submission that is not an empty Auto request.
    AutoRequested: Empty composer submission asking for the Auto workflow.
    WorkspaceLoaded: Inspection finished for one generation.
    WorkspaceFailed: Inspection failed for one generation.
    PlanReady: Plan built for one generation.
    PlanFailed: Planning failed for one generation.
    RunProgressed: Batch of events belonging to one run.
    RunFinished: Terminal result of one run.
    RunFailed: One run ended without a result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from anishift.application import ExecutionPlan, InspectedWorkspace, RunEvent, RunResult
    from anishift.tui.state import UiRoute

__all__ = [
    "AutoRequested",
    "CommandSubmitted",
    "NavigationRequested",
    "PlanFailed",
    "PlanReady",
    "RunFailed",
    "RunFinished",
    "RunProgressed",
    "WorkspaceFailed",
    "WorkspaceLoaded",
]


@dataclass
class NavigationRequested(Message):
    """Ask the host to show another route."""

    route: UiRoute


@dataclass
class CommandSubmitted(Message):
    """Composer submission that is not an empty Auto request."""

    text: str


@dataclass
class AutoRequested(Message):
    """Empty composer submission asking for the automatic workflow."""

    generation: int


@dataclass
class WorkspaceLoaded(Message):
    """Inspection finished for the generation that asked for it."""

    workspace: InspectedWorkspace
    generation: int


@dataclass
class WorkspaceFailed(Message):
    """Inspection failed; the reason is already redacted."""

    reason: str
    generation: int


@dataclass
class PlanReady(Message):
    """Plan built for the generation that asked for it."""

    plan: ExecutionPlan
    generation: int


@dataclass
class PlanFailed(Message):
    """Planning failed; the reason is already redacted."""

    reason: str
    generation: int


@dataclass
class RunProgressed(Message):
    """Batch of events belonging to one run of one generation."""

    events: tuple[RunEvent, ...]
    run_id: str
    generation: int


@dataclass
class RunFinished(Message):
    """Terminal result of one run of one generation."""

    result: RunResult
    run_id: str
    generation: int


@dataclass
class RunFailed(Message):
    """One run ended without a result; the reason is already redacted."""

    reason: str
    run_id: str
    generation: int
