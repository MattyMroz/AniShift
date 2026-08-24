"""Immutable task-result contracts shared by handlers and the scheduler."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from anishift.application.artifacts import Artifact, ArtifactLifetime, ArtifactState
from anishift.application.events import sanitize_event_message
from anishift.errors import ExecutionError

__all__ = [
    "ArtifactSnapshot",
    "GroupResult",
    "GroupStatus",
    "ProducedArtifact",
    "RunResult",
    "TaskResult",
]


class _FrozenMapping[K, V](Mapping[K, V]):
    """Read-only copied mapping that remains compatible with dataclass serialization."""

    def __init__(self, values: Mapping[K, V]) -> None:
        self._values: dict[K, V] = dict(values)

    def __getitem__(self, key: K) -> V:
        return self._values[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, object]) -> dict[K, V]:
        return deepcopy(self._values, memo)


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    """Read-only task inputs and planned output descriptors given to one handler."""

    artifacts: Mapping[str, Artifact]
    planned_outputs: Mapping[str, Artifact] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied: dict[str, Artifact] = dict(self.artifacts)
        if any(key != artifact.artifact_id for key, artifact in copied.items()):
            msg = "Artifact snapshot keys must match artifact IDs"
            raise ValueError(msg)
        outputs: dict[str, Artifact] = dict(self.planned_outputs)
        if any(key != artifact.artifact_id for key, artifact in outputs.items()):
            msg = "Planned output keys must match artifact IDs"
            raise ValueError(msg)
        if set(copied) & set(outputs):
            msg = "Task inputs and outputs must be disjoint"
            raise ValueError(msg)
        if any(
            artifact.state is not ArtifactState.MISSING or artifact.lifetime is ArtifactLifetime.SOURCE
            for artifact in outputs.values()
        ):
            msg = "Planned outputs must be missing intermediate or durable artifacts"
            raise ValueError(msg)
        object.__setattr__(self, "artifacts", _FrozenMapping(copied))
        object.__setattr__(self, "planned_outputs", _FrozenMapping(outputs))

    def require_ready(self, artifact_id: str) -> Artifact:
        """Return a ready artifact or reject an invalid handler input."""
        artifact: Artifact | None = self.artifacts.get(artifact_id)
        if artifact is None:
            msg = f"Required artifact is absent from snapshot: {artifact_id}"
            raise ExecutionError(msg)
        if artifact.state is not ArtifactState.READY:
            msg = f"Required artifact is not ready: {artifact_id}"
            raise ExecutionError(msg)
        return artifact

    def require_output(self, artifact_id: str) -> Artifact:
        """Return one immutable planned output descriptor for a task handler."""
        artifact: Artifact | None = self.planned_outputs.get(artifact_id)
        if artifact is None:
            msg = f"Planned output is absent from snapshot: {artifact_id}"
            raise ExecutionError(msg)
        return artifact


@dataclass(frozen=True, slots=True)
class ProducedArtifact:
    """Filesystem result declared by a completed task handler."""

    artifact_id: str
    path: Path
    metadata: Mapping[str, str | int | bool]

    def __post_init__(self) -> None:
        if not self.artifact_id.strip():
            msg = "Produced artifact ID cannot be empty"
            raise ValueError(msg)
        object.__setattr__(self, "metadata", _FrozenMapping(self.metadata))


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Validated outputs returned by exactly one completed plan task."""

    task_id: str
    outputs: tuple[ProducedArtifact, ...]

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            msg = "Task result ID cannot be empty"
            raise ValueError(msg)
        if not self.outputs:
            msg = "Task result must contain at least one produced artifact"
            raise ValueError(msg)
        output_ids: tuple[str, ...] = tuple(output.artifact_id for output in self.outputs)
        if len(output_ids) != len(set(output_ids)):
            msg = "Task result output IDs must be unique"
            raise ValueError(msg)


class GroupStatus(StrEnum):
    """Terminal outcome of one independently executable source group."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GroupResult:
    """Terminal group outcome preserving every product completed before failure."""

    group_id: str
    status: GroupStatus
    task_results: tuple[TaskResult, ...] = ()
    products: tuple[ProducedArtifact, ...] = ()
    error_messages: tuple[str, ...] = ()
    preserved_products: tuple[ProducedArtifact, ...] = ()

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            msg = "Group result requires a group ID"
            raise ValueError(msg)
        task_ids: tuple[str, ...] = tuple(result.task_id for result in self.task_results)
        product_ids: tuple[str, ...] = tuple(product.artifact_id for product in self.products)
        preserved_ids: tuple[str, ...] = tuple(product.artifact_id for product in self.preserved_products)
        _require_unique_result_ids(task_ids, "task result IDs")
        _require_unique_result_ids(product_ids, "product artifact IDs")
        _require_unique_result_ids(preserved_ids, "preserved product artifact IDs")
        if set(product_ids) & set(preserved_ids):
            msg = "New and preserved products must be disjoint"
            raise ValueError(msg)
        safe_messages: tuple[str, ...] = tuple(sanitize_event_message(message) or "" for message in self.error_messages)
        object.__setattr__(self, "error_messages", safe_messages)
        if any(not message.strip() for message in safe_messages):
            msg = "Group result errors cannot be blank"
            raise ValueError(msg)
        if self.status is GroupStatus.SUCCEEDED and safe_messages:
            msg = "Successful group result cannot contain errors"
            raise ValueError(msg)
        if self.status is GroupStatus.PARTIAL and (not self.products or not safe_messages):
            msg = "Partial group result requires completed products and errors"
            raise ValueError(msg)
        if self.status is GroupStatus.FAILED:
            if self.products:
                msg = "Group result with completed products must be partial, not failed"
                raise ValueError(msg)
            if not safe_messages:
                msg = "Failed group result requires at least one error"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RunResult:
    """Immutable terminal results for every group admitted to one run."""

    run_id: str
    groups: tuple[GroupResult, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.groups:
            msg = "Run result requires a run ID and at least one group result"
            raise ValueError(msg)
        group_ids: tuple[str, ...] = tuple(group.group_id for group in self.groups)
        _require_unique_result_ids(group_ids, "run group IDs")
        safe_warnings: tuple[str, ...] = tuple(sanitize_event_message(warning) or "" for warning in self.warnings)
        if any(not warning.strip() for warning in safe_warnings):
            msg = "Run result warnings cannot be blank"
            raise ValueError(msg)
        object.__setattr__(self, "warnings", safe_warnings)

    @property
    def succeeded(self) -> bool:
        """Return whether every group completed successfully."""
        return all(group.status is GroupStatus.SUCCEEDED for group in self.groups)

    @property
    def cancelled(self) -> bool:
        """Return whether cancellation affected at least one group."""
        return any(group.status is GroupStatus.CANCELLED for group in self.groups)


def _require_unique_result_ids(values: tuple[str, ...], label: str) -> None:
    if any(not value.strip() for value in values) or len(values) != len(set(values)):
        msg = f"{label.capitalize()} must be non-empty and unique"
        raise ValueError(msg)
