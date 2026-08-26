"""The reservation gate letting one empty Enter start at most one Auto request."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from anishift.tui import lifecycle
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Collection

    from anishift.application import ExecutionPlan, PlanProblem
    from anishift.tui.state import SessionState

__all__ = ["AutoVerdict", "AutoVerdictKind", "classify", "release", "reserve"]

logger = get_logger(__name__)


class AutoVerdictKind(StrEnum):
    """What one planned Auto request may do next, decided in exactly one place."""

    START = "start"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AutoVerdict:
    """The one answer of whether a planned Auto run may start, with its reasons."""

    kind: AutoVerdictKind
    problems: tuple[str, ...] = ()
    artifact_ids: frozenset[str] = frozenset()

    @property
    def may_start(self) -> bool:
        """Whether this verdict lets the run start without asking anything first."""
        return self.kind is AutoVerdictKind.START


def reserve(state: SessionState) -> int | None:
    """Reserve the generation for one Auto start, or ``None`` while the gate is held."""
    generation: int | None = lifecycle.begin_planning(state)
    if generation is None:
        logger.debug("Auto request refused", run_state=state.run_state.value)
        return None
    logger.info("Auto request reserved", generation=generation)
    return generation


def release(state: SessionState, *, generation: int, reason: str) -> bool:
    """Give the reservation of the current *generation* back, keeping *reason* for the user."""
    if not lifecycle.accepts_message(state, generation=generation):
        logger.debug("Late Auto release dropped", generation=generation)
        return False
    return lifecycle.abandon_planning(state, reason)


def classify(plan: ExecutionPlan, *, accepted: Collection[str] = ()) -> AutoVerdict:
    """Decide once whether *plan* starts, needs a confirmation, or cannot run at all."""
    blocking: tuple[str, ...] = tuple(problem.message for problem in plan.problems if problem.is_blocking)
    if blocking:
        logger.info("Auto plan blocked", problems=len(blocking))
        return AutoVerdict(kind=AutoVerdictKind.BLOCKED, problems=blocking)
    unaccepted: tuple[PlanProblem, ...] = tuple(
        problem for problem in plan.problems if not _is_accepted(problem, accepted)
    )
    if not unaccepted:
        return AutoVerdict(kind=AutoVerdictKind.START)
    logger.info("Auto plan needs a confirmation", problems=len(unaccepted))
    return AutoVerdict(
        kind=AutoVerdictKind.CONFIRM,
        problems=tuple(problem.message for problem in unaccepted),
        artifact_ids=frozenset(artifact_id for problem in unaccepted for artifact_id in problem.artifact_ids),
    )


def _is_accepted(problem: PlanProblem, accepted: Collection[str]) -> bool:
    """Whether the user already accepted this exact irreversible step in this session."""
    if not problem.artifact_ids:
        return False
    return all(artifact_id in accepted for artifact_id in problem.artifact_ids)
