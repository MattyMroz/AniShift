"""Application adapter for neutral MKV and MP4 extraction tasks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.extraction import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionTargetFormat,
    LegacyExtractionResult,
    MediaInfo,
    TrackSelection,
    format_extension,
)

__all__ = ["ExtractionTaskHandler", "LegacyExtractionAdapter"]


class ExtractionExecutor(Protocol):
    """Neutral extraction facade required by the application adapter."""

    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ExtractionResult:
        """Extract one selected embedded track."""
        ...


class LegacyBulkExtractor(Protocol):
    """Existing one-process MKV extraction operation used by the REPL pipeline."""

    def __call__(
        self,
        info: MediaInfo,
        selection: TrackSelection,
        dest_dir: Path,
        *,
        on_progress: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> LegacyExtractionResult:
        """Extract the selected legacy track pair without changing its lifecycle."""
        ...


@dataclass(frozen=True, slots=True)
class LegacyExtractionAdapter:
    """Application boundary around the existing identify and bulk extraction operations."""

    identify_operation: Callable[[Path], MediaInfo]
    extract_operation: LegacyBulkExtractor

    def identify(self, source: Path) -> MediaInfo:
        """Identify one media source through the existing domain operation."""
        return self.identify_operation(source)

    def extract(
        self,
        info: MediaInfo,
        selection: TrackSelection,
        destination: Path,
        *,
        on_progress: Callable[[int], None] | None,
        cancel: threading.Event,
    ) -> LegacyExtractionResult:
        """Extract the selected pair through the existing bulk operation."""
        return self.extract_operation(
            info,
            selection,
            destination,
            on_progress=on_progress,
            cancel=cancel,
        )


class ExtractionTaskHandler:
    """Translate extraction plan tasks into one-track service requests."""

    __slots__ = ("_run_root", "_service", "_timeout_s")

    def __init__(self, service: ExtractionExecutor, *, run_root: Path, timeout_s: float) -> None:
        """Bind the neutral service to one scheduler-owned run scope."""
        if timeout_s <= 0:
            msg = "Extraction timeout must be positive"
            raise ValueError(msg)
        self._service: ExtractionExecutor = service
        self._run_root: Path = run_root
        self._timeout_s: float = timeout_s

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Extract one planned audio or subtitle track into group staging."""
        if task.kind not in {TaskKind.EXTRACT_AUDIO, TaskKind.EXTRACT_SUBTITLES}:
            msg = "Extraction handler received a non-extraction task"
            raise ExecutionError(msg)
        if len(task.requires) != 1 or len(task.produces) != 1:
            msg = "Extraction task must have exactly one input and output"
            raise ExecutionError(msg)
        source: Artifact = artifacts.require_ready(task.requires[0])
        if source.kind not in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4} or source.path is None:
            msg = "Extraction task requires one ready MKV or MP4 source"
            raise ExecutionError(msg)
        output: Artifact = artifacts.require_output(task.produces[0])
        parameters: dict[str, str | int | bool] = dict(task.parameters)
        track_id: int = _integer_parameter(parameters, "track_id")
        target_format: ExtractionTargetFormat = ExtractionTargetFormat(_string_parameter(parameters, "target_format"))
        suffix: str = _output_suffix(task, output, parameters, target_format)
        destination: Path = task_staging_path(self._run_root, task, output, suffix)
        request = ExtractionRequest(source.path, track_id, target_format, destination)
        result: ExtractionResult = self._service.extract(
            request,
            cancel=cancel,
            timeout_s=self._timeout_s,
        )
        if result.target_path != destination:
            msg = "Extraction service returned an unexpected target path"
            raise ExecutionError(msg)
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, destination, {}),))


def _output_suffix(
    task: PlanTask,
    output: Artifact,
    parameters: dict[str, str | int | bool],
    target_format: ExtractionTargetFormat,
) -> str:
    if task.kind is TaskKind.EXTRACT_AUDIO:
        if output.kind is not ArtifactKind.SOURCE_AUDIO or target_format is not ExtractionTargetFormat.AUDIO_COPY:
            msg = "Audio extraction task has an incompatible output contract"
            raise ExecutionError(msg)
        return f".{format_extension(_string_parameter(parameters, 'source_codec'))}"
    if output.kind is not ArtifactKind.SOURCE_SUBTITLES or target_format is ExtractionTargetFormat.AUDIO_COPY:
        msg = "Subtitle extraction task has an incompatible output contract"
        raise ExecutionError(msg)
    return f".{target_format.value}"


def _string_parameter(parameters: dict[str, str | int | bool], name: str) -> str:
    value: str | int | bool | None = parameters.get(name)
    if not isinstance(value, str):
        msg = f"Extraction parameter must be a string: {name}"
        raise ExecutionError(msg)
    return value


def _integer_parameter(parameters: dict[str, str | int | bool], name: str) -> int:
    value: str | int | bool | None = parameters.get(name)
    if type(value) is not int:
        msg = f"Extraction parameter must be an integer: {name}"
        raise ExecutionError(msg)
    return value
