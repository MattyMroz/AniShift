"""Typed presentation messages exchanged inside the shell, generation-stamped."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

from anishift.application import RunEventKind

if TYPE_CHECKING:
    from anishift.application import (
        CheckResult,
        ExecutionPlan,
        InspectedSourceGroup,
        InspectedWorkspace,
        ResourceResult,
        RunEvent,
        RunResult,
    )
    from anishift.tui.state import UiRoute

__all__ = [
    "AutoRequested",
    "CommandSubmitted",
    "DoctorReported",
    "GroupRegistered",
    "NavigationRequested",
    "PlanFailed",
    "PlanReady",
    "RunFailed",
    "RunFinished",
    "RunProgressed",
    "SetupReported",
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
class GroupRegistered(Message):
    """One external file was validated and its inspected group replaced."""

    group: InspectedSourceGroup
    generation: int


@dataclass
class DoctorReported(Message):
    """Every technical diagnostic finished for the generation that asked for it."""

    checks: tuple[CheckResult, ...]
    generation: int


@dataclass
class SetupReported(Message):
    """Installation of the configured external resources finished."""

    resources: tuple[ResourceResult, ...]
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

    @property
    def announces_run(self) -> bool:
        """Whether this batch carries the event that opens its own run."""
        return any(event.kind is RunEventKind.RUN_STARTED for event in self.events)


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
