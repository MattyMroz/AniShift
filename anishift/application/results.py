"""Immutable task-result contracts shared by handlers and the scheduler."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from anishift.application.artifacts import Artifact, ArtifactState
from anishift.errors import ExecutionError


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
    """Read-only artifact view given to one task handler."""

    artifacts: Mapping[str, Artifact]

    def __post_init__(self) -> None:
        copied: dict[str, Artifact] = dict(self.artifacts)
        if any(key != artifact.artifact_id for key, artifact in copied.items()):
            msg = "Artifact snapshot keys must match artifact IDs"
            raise ValueError(msg)
        object.__setattr__(self, "artifacts", _FrozenMapping(copied))

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
