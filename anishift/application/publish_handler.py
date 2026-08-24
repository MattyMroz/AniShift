"""Application adapter for validated durable sidecar staging."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Never, Protocol

from anishift.application.artifacts import Artifact, SourceGroup
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.publisher import ArtifactPublisher, PublishRequest
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError

__all__ = ["PublishTaskHandler"]


class ArtifactStager(Protocol):
    """Validate and copy one durable product into private staging."""

    def stage(self, request: PublishRequest, destination: Path, *, cancel: threading.Event) -> Path:
        """Stage one validated sidecar without touching its final destination."""
        ...


class PublishTaskHandler:
    """Stage one planned durable sidecar for coordinator-owned publication."""

    __slots__ = ("_publisher", "_run_root", "_source_groups")

    def __init__(
        self,
        *,
        run_root: Path,
        source_groups: Mapping[str, SourceGroup],
        publisher: ArtifactStager | None = None,
    ) -> None:
        self._run_root: Path = run_root
        self._publisher: ArtifactStager = publisher or ArtifactPublisher()
        self._source_groups: dict[str, SourceGroup] = dict(source_groups)
        if any(group_id != group.group_id for group_id, group in self._source_groups.items()):
            msg = "Publish source-group keys must match group IDs"
            raise ValueError(msg)

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Validate one publish task and return its private staging file."""
        cancel.raise_if_cancelled()
        if task.kind is not TaskKind.PUBLISH_ARTIFACT or len(task.requires) != 1 or len(task.produces) != 1:
            _raise_execution("Publish handler requires exactly one input and output")
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        if source.path is None or output.planned_destination is None or source.kind is not output.kind:
            _raise_execution("Publish task source and target contracts do not match")
        source_group: SourceGroup | None = self._source_groups.get(task.group_id)
        if source_group is None:
            _raise_execution("Publish task group is absent from the run source map")
        try:
            request = PublishRequest(source.path, output, source_group)
        except ValueError as error:
            raise ExecutionError(str(error)) from error
        staging: Path = task_staging_path(
            self._run_root,
            task,
            output,
            output.planned_destination.suffix.casefold(),
        )
        event = threading.Event()
        stop = threading.Event()
        watcher = threading.Thread(target=_mirror_cancel, args=(cancel, event, stop), daemon=True)
        watcher.start()
        try:
            path: Path = self._publisher.stage(request, staging, cancel=event)
        finally:
            stop.set()
            watcher.join()
        cancel.raise_if_cancelled()
        if path != staging or not path.is_file():
            _raise_execution("Artifact publisher returned an invalid staging file")
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, path, {"validated": True}),))


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)


def _mirror_cancel(cancel: CancellationToken, event: threading.Event, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        if cancel.is_cancelled():
            event.set()
            return
