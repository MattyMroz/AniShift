"""Application adapter for neutral MKV and MP4 extraction tasks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

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

# ── Constants ─────────────────────────────────────────────────────────────────

_CANCEL_POLL_SECONDS: Final[float] = 0.05
"""Maximum delay before legacy MKV extraction observes cancellation."""


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

    def __call__(  # noqa: PLR0913 - preserve the bulk extraction boundary
        self,
        info: MediaInfo,
        selection: TrackSelection,
        dest_dir: Path,
        *,
        on_progress: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
        timeout_s: float = 3600.0,
    ) -> LegacyExtractionResult:
        """Extract the selected track pair with live progress and a deadline."""
        ...


@dataclass(frozen=True, slots=True)
class LegacyExtractionAdapter:
    """Application boundary around the existing identify and bulk extraction operations."""

    identify_operation: Callable[[Path], MediaInfo]
    extract_operation: LegacyBulkExtractor

    def identify(self, source: Path) -> MediaInfo:
        """Identify one media source through the existing domain operation."""
        return self.identify_operation(source)

    def extract(  # noqa: PLR0913 - preserve the bulk extraction boundary
        self,
        info: MediaInfo,
        selection: TrackSelection,
        destination: Path,
        *,
        on_progress: Callable[[int], None] | None,
        cancel: threading.Event,
        timeout_s: float,
    ) -> LegacyExtractionResult:
        """Extract the selected pair through the existing bulk operation."""
        return self.extract_operation(
            info,
            selection,
            destination,
            on_progress=on_progress,
            cancel=cancel,
            timeout_s=timeout_s,
        )


class ExtractionTaskHandler:
    """Execute neutral MP4 tasks and legacy-compatible MKV extraction."""

    __slots__ = ("_legacy", "_run_root", "_service", "_timeout_s")

    def __init__(
        self,
        service: ExtractionExecutor,
        *,
        run_root: Path,
        timeout_s: float,
        legacy: LegacyExtractionAdapter | None = None,
    ) -> None:
        """Bind extraction facades to one scheduler-owned run scope."""
        if timeout_s <= 0:
            msg = "Extraction timeout must be positive"
            raise ValueError(msg)
        self._service: ExtractionExecutor = service
        self._legacy: LegacyExtractionAdapter | None = legacy
        self._run_root: Path = run_root
        self._timeout_s: float = timeout_s

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Extract one planned MKV track set or one neutral container track."""
        supported: frozenset[TaskKind] = frozenset(
            {TaskKind.EXTRACT_AUDIO, TaskKind.EXTRACT_SUBTITLES, TaskKind.EXTRACT_TRACKS}
        )
        if task.kind not in supported:
            msg = "Extraction handler received a non-extraction task"
            raise ExecutionError(msg)
        expected_outputs: int = 2 if task.kind is TaskKind.EXTRACT_TRACKS else 1
        if len(task.requires) != 1 or len(task.produces) != expected_outputs:
            msg = "Extraction task has an incompatible input or output count"
            raise ExecutionError(msg)
        source: Artifact = artifacts.require_ready(task.requires[0])
        if source.kind not in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4} or source.path is None:
            msg = "Extraction task requires one ready MKV or MP4 source"
            raise ExecutionError(msg)
        if source.kind is ArtifactKind.VIDEO_MKV and self._legacy is not None:
            return self._extract_legacy_mkv(task, artifacts, source, cancel, progress)
        if task.kind is TaskKind.EXTRACT_TRACKS:
            msg = "Bulk track extraction requires an MKV source"
            raise ExecutionError(msg)
        return self._extract_neutral(task, artifacts, source, cancel, progress)

    def _extract_neutral(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        source: Artifact,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Extract one MP4 track through the neutral adapter."""
        if source.path is None:
            msg = "Extraction source requires a runtime path"
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

    def _extract_legacy_mkv(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        source: Artifact,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Run one legacy gui-mode process for the selected MKV track set."""
        if self._legacy is None or source.path is None:
            msg = "Legacy MKV extraction is unavailable"
            raise ExecutionError(msg)
        parameters: dict[str, str | int | bool] = dict(task.parameters)
        if task.kind is TaskKind.EXTRACT_TRACKS:
            selection = TrackSelection(
                _integer_parameter(parameters, "audio_track_id"),
                _integer_parameter(parameters, "subtitle_track_id"),
                False,
            )
        elif task.kind is TaskKind.EXTRACT_AUDIO:
            selection = TrackSelection(_integer_parameter(parameters, "track_id"), None, False)
        else:
            selection = TrackSelection(None, _integer_parameter(parameters, "track_id"), False)
        outputs: tuple[Artifact, ...] = tuple(artifacts.require_output(item) for item in task.produces)
        destination: Path = task_staging_path(self._run_root, task, outputs[0], ".tmp").parent
        extraction_cancel = threading.Event()
        stop = threading.Event()
        watcher = threading.Thread(
            target=_mirror_cancel,
            args=(cancel, extraction_cancel, stop),
            daemon=True,
        )
        watcher.start()

        def report(percent: int) -> None:
            progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, percent))

        try:
            cancel.raise_if_cancelled()
            info: MediaInfo = self._legacy.identify(source.path)
            result: LegacyExtractionResult = self._legacy.extract(
                info,
                selection,
                destination,
                on_progress=report,
                cancel=extraction_cancel,
                timeout_s=self._timeout_s,
            )
            cancel.raise_if_cancelled()
        finally:
            stop.set()
            watcher.join()
        path_by_kind: dict[ArtifactKind, Path | None] = {
            ArtifactKind.SOURCE_AUDIO: result.audio_path,
            ArtifactKind.SOURCE_SUBTITLES: result.subtitle_path,
        }
        produced: list[ProducedArtifact] = []
        for output in outputs:
            output_path: Path | None = path_by_kind.get(output.kind)
            if output_path is None:
                msg = "Legacy MKV extraction omitted a planned output"
                raise ExecutionError(msg)
            produced.append(ProducedArtifact(output.artifact_id, output_path, {}))
        return TaskResult(task.task_id, tuple(produced))


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


def _mirror_cancel(cancel: CancellationToken, target: threading.Event, stop: threading.Event) -> None:
    """Mirror scheduler cancellation into the legacy extraction event."""
    while not stop.wait(_CANCEL_POLL_SECONDS):
        if cancel.is_cancelled():
            target.set()
            return
