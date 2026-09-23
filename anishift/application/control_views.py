"""Read-only planning views sent by the resident without an execution graph."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter

from anishift.application.artifacts import ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.events import RunEvent
from anishift.application.intents import GroupIntent
from anishift.application.planning import PlanProblem, TaskKind
from anishift.application.workflows import WorkflowTarget
from anishift.services.torrents import Release, ReleaseName

if TYPE_CHECKING:
    from anishift.application.planning import ExecutionPlan


@dataclass(frozen=True, slots=True)
class PreviewTask:
    """Identify a progress row without inputs, parameters or executable dependencies."""

    task_id: str
    group_id: str
    kind: TaskKind


@dataclass(frozen=True, slots=True)
class PreviewGroup:
    """Describe the selected products and their reuse for one group."""

    group_id: str
    intent: GroupIntent
    preserved_products: tuple[ArtifactKind, ...]
    planned_products: tuple[ArtifactKind, ...]


@dataclass(frozen=True, slots=True)
class PlanPreview:
    """Present a resident-owned plan that can only be started by its preview ID."""

    preview_id: str
    instance_id: str
    groups: tuple[PreviewGroup, ...]
    tasks: tuple[PreviewTask, ...]
    problems: tuple[PlanProblem, ...]

    @property
    def can_execute(self) -> bool:
        """Whether every selected group can be accepted for execution."""
        return not any(problem.is_blocking for problem in self.problems)


@dataclass(frozen=True, slots=True)
class RunProgressSnapshot:
    """Reconstruct progress from public task identities and coalesced events."""

    run_id: str
    preview: PlanPreview
    labels: dict[str, str]
    events: tuple[RunEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class LibraryFileIdentity:
    """Identify one regular workspace file independently of its name and modification stamp."""

    path: str
    size: int
    modified_ns: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class LibraryFile:
    """Describe a member of a completed set using the owner's current file inventory."""

    path: str
    role: str
    format: str
    identity: LibraryFileIdentity | None


@dataclass(frozen=True, slots=True)
class LibrarySet:
    """Present a completed set and its selected result without substituting another file."""

    set_id: str
    group_id: str
    name: str
    target: WorkflowTarget | None
    main_result: str | None
    files: tuple[LibraryFile, ...]
    available: bool
    problem: str | None = None
    provisional_timing: bool = False


@dataclass(frozen=True, slots=True)
class RetryProposal:
    """Describe the current retry route without granting execution authority to UI paths."""

    material_id: str
    action: str
    group_ids: tuple[str, ...] = ()
    intents: tuple[GroupIntent, ...] = ()
    operation_id: str | None = None
    subscription_id: str | None = None
    episodes: tuple[Decimal, ...] = ()


@dataclass(frozen=True, slots=True)
class DeletionPreview:
    """Bind one confirmation to an exact set of original files in one resident instance."""

    preview_id: str
    instance_id: str
    set_id: str
    name: str
    files: tuple[LibraryFileIdentity, ...]

    @property
    def total_size(self) -> int:
        """Return the size of the exact files covered by this confirmation."""
        return sum(item.size for item in self.files)


def preview_plan(plan: ExecutionPlan, preview_id: str, instance_id: str) -> PlanPreview:
    """Project products and progress identities without exposing an executable plan."""
    groups: list[PreviewGroup] = []
    for group in plan.groups:
        preserved: set[ArtifactKind] = set()
        planned: set[ArtifactKind] = set()
        for artifact in plan.artifacts:
            if artifact.group_id == group.group_id and artifact.lifetime is ArtifactLifetime.DURABLE:
                (preserved if artifact.state is ArtifactState.READY else planned).add(artifact.kind)
        groups.append(PreviewGroup(group.group_id, group.intent, tuple(sorted(preserved)), tuple(sorted(planned))))
    return PlanPreview(
        preview_id,
        instance_id,
        tuple(groups),
        tuple(PreviewTask(task.task_id, task.group_id, task.kind) for task in plan.tasks),
        plan.problems,
    )


def encode_view[T](value: T) -> dict[str, object]:
    """Encode a read-only dataclass view as JSON-compatible fields."""
    return cast("dict[str, object]", json.loads(_adapter(type(value)).dump_json(value, fallback=dict, warnings=False)))


def decode_view[T](model: type[T], payload: object) -> T:
    """Validate one JSON view received over the authenticated local connection."""
    return _adapter(model).validate_json(json.dumps(payload), strict=True)


def _adapter[T](model: type[T]) -> TypeAdapter[T]:
    adapter: TypeAdapter[T] = TypeAdapter(model)
    adapter.rebuild(_types_namespace={"Release": Release, "ReleaseName": ReleaseName})
    return adapter
