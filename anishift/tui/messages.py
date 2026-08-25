"""Typed presentation messages exchanged inside the shell, generation-stamped."""

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
