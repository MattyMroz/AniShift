"""UI-neutral preparation and execution of automatic runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from anishift.application import (
    AppService,
    AutoPreset,
    ExecutionPlan,
    InspectedWorkspace,
    RunEventSink,
    RunResult,
    ready_group_ids,
)
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.utils.logger import get_logger

__all__ = [
    "AutoRunBlocker",
    "AutoRunRefusal",
    "PreparedAutoRun",
    "execute_auto_run",
    "execute_plan",
    "prepare_auto_run",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_NO_SOURCES: Final[str] = "The workspace holds no source group to run."
"""Refusal returned when discovery finds no source group."""

_NO_SOURCES_HINT: Final[str] = "Put a video or a subtitle file in the workspace and run the preset again."
"""Suggestion returned beside an empty workspace."""

_NO_READY_SOURCES: Final[str] = "No discovered source group is ready to run."
"""Refusal returned when every discovered group is unready."""

_NO_READY_SOURCES_HINT: Final[str] = "Give every group usable text, resolve its conflict, then run the preset again."
"""Suggestion returned when no discovered group is ready."""

_PLAN_BLOCKED: Final[str] = "The plan cannot run because of a blocking problem."
"""Refusal returned when planning reports a blocking problem."""

_PLAN_SCOPE: Final[str] = "plan"
"""Fallback scope assigned to a blocker without a group."""

_SELECTION_BLOCKED: Final[str] = "The run cannot take every requested source group."
"""Refusal returned when a requested group is unknown or unready."""

_SELECTION_HINT: Final[str] = "Request only groups the workspace holds and reports ready, then run the preset again."
"""Suggestion returned beside a rejected group selection."""

_UNKNOWN_GROUP: Final[str] = "The workspace holds no such source group."
"""Blocker message assigned to a requested group discovery never reported."""

_UNREADY_GROUP: Final[str] = "This source group is not ready to run."
"""Blocker message assigned to a requested group discovery reports unready."""


@dataclass(frozen=True, slots=True)
class AutoRunBlocker:
    """Describe one blocking plan problem without presentation concerns."""

    scope: str
    message: str


@dataclass(frozen=True, slots=True)
class AutoRunRefusal:
    """Describe why an automatic run cannot start."""

    message: str
    suggestion: str = ""
    blockers: tuple[AutoRunBlocker, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedAutoRun:
    """Carry the inspected workspace and accepted automatic plan."""

    preset_id: str
    workspace: InspectedWorkspace
    group_ids: tuple[str, ...]
    plan: ExecutionPlan


def prepare_auto_run(
    service: AppService,
    preset_id: str,
    *,
    cancel: CancellationToken | None = None,
    group_ids: Sequence[str] | None = None,
) -> PreparedAutoRun | AutoRunRefusal:
    """Discover, validate and plan one automatic run without rendering UI."""
    token: CancellationToken = cancel or NeverCancelledToken()
    workspace: InspectedWorkspace = service.discover(cancel=token)
    token.raise_if_cancelled()
    if not workspace.groups:
        return AutoRunRefusal(_NO_SOURCES, _NO_SOURCES_HINT)
    preset: AutoPreset = service.get_preset(preset_id)
    token.raise_if_cancelled()
    selection: tuple[str, ...] | AutoRunRefusal = _select_groups(workspace, group_ids)
    if isinstance(selection, AutoRunRefusal):
        return selection
    plan: ExecutionPlan = service.plan_auto(selection, preset)
    token.raise_if_cancelled()
    blockers: tuple[AutoRunBlocker, ...] = tuple(
        AutoRunBlocker(problem.group_id or _PLAN_SCOPE, problem.message)
        for problem in plan.problems
        if problem.is_blocking
    )
    if blockers:
        return AutoRunRefusal(_PLAN_BLOCKED, blockers=blockers)
    logger.info("Automatic run planned", preset_id=preset_id, groups=len(selection), tasks=len(plan.tasks))
    return PreparedAutoRun(preset_id, workspace, selection, plan)


def _select_groups(
    workspace: InspectedWorkspace,
    requested: Sequence[str] | None,
) -> tuple[str, ...] | AutoRunRefusal:
    """Resolve the requested group IDs against the workspace, keeping its ready order."""
    ready: tuple[str, ...] = ready_group_ids(workspace.groups)
    if requested is None:
        if not ready:
            return AutoRunRefusal(_NO_READY_SOURCES, _NO_READY_SOURCES_HINT)
        return ready
    known: frozenset[str] = frozenset(group.group_id for group in workspace.groups)
    runnable: frozenset[str] = frozenset(ready)
    rejected: tuple[AutoRunBlocker, ...] = tuple(
        AutoRunBlocker(group_id, _UNREADY_GROUP if group_id in known else _UNKNOWN_GROUP)
        for group_id in requested
        if group_id not in runnable
    )
    if rejected:
        return AutoRunRefusal(_SELECTION_BLOCKED, _SELECTION_HINT, rejected)
    wanted: frozenset[str] = frozenset(requested)
    selected: tuple[str, ...] = tuple(group_id for group_id in ready if group_id in wanted)
    if not selected:
        return AutoRunRefusal(_NO_READY_SOURCES, _NO_READY_SOURCES_HINT)
    return selected


def execute_auto_run(service: AppService, prepared: PreparedAutoRun, sink: RunEventSink) -> RunResult:
    """Execute one accepted automatic plan through the application facade."""
    return execute_plan(service, prepared.plan, sink)


def execute_plan(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
    """Execute one accepted plan through the shared application facade."""
    return service.execute(plan, sink)
