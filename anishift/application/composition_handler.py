"""Application adapter for independently planned container products."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Never, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.intents import BurnSubtitleProduct, MkvTrackProduct
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.composition import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionProgressSink,
    CompositionResult,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    ContainerTarget,
    SubtitleRole,
)

__all__ = ["CompositionTaskHandler", "LegacyCompositionAdapter", "build_composition_request"]

# ── Constants ────────────────────────────────────────────────────────────────

_IN_PROGRESS_PERCENT: Final[int] = 99
"""Highest reported percentage before output validation succeeds."""


class ContainerComposer(Protocol):
    """Configured service producing one validated container at a time."""

    def compose_container(
        self,
        request: ContainerCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> ContainerCompositionResult:
        """Compose one exact MKV or MP4 request."""
        ...


class LegacyComposer(Protocol):
    """Existing multi-variant composition operation used by the REPL."""

    def compose(
        self,
        plan: CompositionPlan,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CompositionResult:
        """Compose one legacy output variant."""
        ...


@dataclass(frozen=True, slots=True)
class LegacyCompositionAdapter:
    """Application boundary retaining the legacy composition operation."""

    service: LegacyComposer

    def compose(
        self,
        plan: CompositionPlan,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CompositionResult:
        """Delegate one legacy plan without changing its product policy."""
        return self.service.compose(plan, callbacks=callbacks, cancel=cancel)


class CompositionTaskHandler:
    """Execute one composition task inside its run-owned staging scope."""

    __slots__ = ("_run_root", "_service")

    def __init__(self, service: ContainerComposer, *, run_root: Path) -> None:
        self._service: ContainerComposer = service
        self._run_root: Path = run_root

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Compose and validate one planned durable container staging file."""
        cancel.raise_if_cancelled()
        planned: ContainerCompositionRequest = build_composition_request(task, artifacts)
        output: Artifact = artifacts.require_output(task.produces[0])
        staging: Path = task_staging_path(self._run_root, task, output, f".{planned.target.value}")
        request: ContainerCompositionRequest = replace(planned, destination=staging)
        event = threading.Event()
        stop = threading.Event()
        watcher = threading.Thread(target=_mirror_cancel, args=(cancel, event, stop), daemon=True)
        watcher.start()
        try:
            result: ContainerCompositionResult = self._service.compose_container(
                request,
                callbacks=_ProgressObserver(task.task_id, progress),
                cancel=event,
            )
        finally:
            stop.set()
            watcher.join()
        cancel.raise_if_cancelled()
        _validate_result(result, request)
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        metadata: dict[str, str | int | bool] = {
            "validated": True,
            "output_size_bytes": result.output_size_bytes,
            "source_size_bytes": result.source_size_bytes,
            "warning_count": len(result.warnings),
        }
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, staging, metadata),))


@dataclass(frozen=True, slots=True)
class _ProgressObserver:
    task_id: str
    progress: TaskProgressSink

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Forward measured progress while reserving completion for validated output."""
        del scope_id
        self.progress.emit(
            WorkerNotification(
                WorkerNotificationKind.PROGRESS,
                self.task_id,
                min(percent, _IN_PROGRESS_PERCENT),
                phase,
            )
        )


def build_composition_request(task: PlanTask, artifacts: ArtifactSnapshot) -> ContainerCompositionRequest:
    """Translate one composition task into an exact single-container request."""
    if task.kind not in {TaskKind.COMPOSE_MKV, TaskKind.COMPOSE_MP4}:
        _raise_execution("Only composition tasks can build a container request")
    if len(task.produces) != 1:
        _raise_execution("A composition task must produce exactly one container")
    inputs: tuple[Artifact, ...] = tuple(artifacts.require_ready(artifact_id) for artifact_id in task.requires)
    video: Artifact = _require_one(inputs, {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}, "source video")
    source_video: Path = _runtime_path(video)
    output: Artifact = artifacts.require_output(task.produces[0])
    expected_output_kind: ArtifactKind = (
        ArtifactKind.FINAL_MKV if task.kind is TaskKind.COMPOSE_MKV else ArtifactKind.FINAL_MP4
    )
    if output.kind is not expected_output_kind:
        _raise_execution(f"{task.kind.value} must produce {expected_output_kind.value}")
    destination: Path | None = output.planned_destination
    if destination is None or destination.parent != source_video.parent:
        _raise_execution("Container destination must be planned next to its selected source")
    parameters: dict[str, str | int | bool] = dict(task.parameters)
    if task.kind is TaskKind.COMPOSE_MKV:
        return _build_mkv_request(inputs, source_video=source_video, destination=destination, parameters=parameters)
    return _build_mp4_request(inputs, source_video=source_video, destination=destination, parameters=parameters)


def _build_mkv_request(
    inputs: tuple[Artifact, ...],
    *,
    source_video: Path,
    destination: Path,
    parameters: dict[str, str | int | bool],
) -> ContainerCompositionRequest:
    raw_tracks: str = _string_parameter(parameters, "mkv_tracks")
    requested_tracks: tuple[MkvTrackProduct, ...] = tuple(
        MkvTrackProduct(value) for value in raw_tracks.split(",") if value
    )
    subtitle_specs: dict[MkvTrackProduct, tuple[ArtifactKind, SubtitleRole, str]] = {
        MkvTrackProduct.SOURCE_SUBTITLES: (ArtifactKind.SOURCE_SUBTITLES, SubtitleRole.FULL, "Source subtitles"),
        MkvTrackProduct.FULL_PL_SUBTITLES: (ArtifactKind.FULL_PL, SubtitleRole.FULL, "Polish subtitles"),
        MkvTrackProduct.DISPLAYED_PL_SUBTITLES: (
            ArtifactKind.DISPLAYED_PL,
            SubtitleRole.DISPLAYED,
            "Polish signs",
        ),
    }
    attached: list[AttachedSubtitle] = []
    for track in requested_tracks:
        spec: tuple[ArtifactKind, SubtitleRole, str] | None = subtitle_specs.get(track)
        if spec is None:
            continue
        kind, role, track_name = spec
        artifact: Artifact = _require_one(inputs, {kind}, track.value)
        attached.append(
            AttachedSubtitle(
                path=_runtime_path(artifact),
                role=role,
                language=artifact.language or ("pol" if kind is not ArtifactKind.SOURCE_SUBTITLES else "und"),
                track_name=track_name,
            )
        )
    narration: Artifact | None = None
    if MkvTrackProduct.NARRATION_AUDIO in requested_tracks:
        narration = _require_one(inputs, {ArtifactKind.NARRATION_AUDIO}, "narration audio")
    return ContainerCompositionRequest(
        source_video=source_video,
        destination=destination,
        target=ContainerTarget.MKV,
        burn_subtitle=None,
        attached_subtitles=tuple(attached),
        narration_audio=_runtime_path(narration) if narration is not None else None,
        keep_original_audio=True,
    )


def _build_mp4_request(
    inputs: tuple[Artifact, ...],
    *,
    source_video: Path,
    destination: Path,
    parameters: dict[str, str | int | bool],
) -> ContainerCompositionRequest:
    burn_product: BurnSubtitleProduct = BurnSubtitleProduct(_string_parameter(parameters, "burn_subtitles"))
    burn_kind: ArtifactKind | None = {
        BurnSubtitleProduct.NONE: None,
        BurnSubtitleProduct.SOURCE: ArtifactKind.SOURCE_SUBTITLES,
        BurnSubtitleProduct.FULL_PL: ArtifactKind.FULL_PL,
        BurnSubtitleProduct.DISPLAYED_PL: ArtifactKind.DISPLAYED_PL,
    }[burn_product]
    burn_subtitle: Path | None = None
    if burn_kind is not None:
        burn_subtitle = _runtime_path(_require_one(inputs, {burn_kind}, "burn subtitle"))
    audio_source: str = _string_parameter(parameters, "audio_source")
    narration_audio: Path | None = None
    if audio_source == "narration":
        narration_audio = _runtime_path(_require_one(inputs, {ArtifactKind.NARRATION_AUDIO}, "narration audio"))
    elif audio_source != "original":
        _raise_execution("MP4 audio source must be original or narration")
    return ContainerCompositionRequest(
        source_video=source_video,
        destination=destination,
        target=ContainerTarget.MP4,
        burn_subtitle=burn_subtitle,
        attached_subtitles=(),
        narration_audio=narration_audio,
        keep_original_audio=audio_source == "original",
    )


def _validate_result(result: ContainerCompositionResult, request: ContainerCompositionRequest) -> None:
    valid: bool = (
        result.source_path == request.source_video
        and result.target is request.target
        and result.output_path == request.destination
        and result.output_size_bytes > 0
        and result.source_size_bytes > 0
        and result.output_path.is_file()
        and result.output_path.stat().st_size == result.output_size_bytes
    )
    if not valid:
        _raise_execution("Composition service returned an invalid container result")


def _require_one(inputs: tuple[Artifact, ...], kinds: set[ArtifactKind], label: str) -> Artifact:
    matches: tuple[Artifact, ...] = tuple(artifact for artifact in inputs if artifact.kind in kinds)
    if len(matches) != 1:
        _raise_execution(f"Composition task requires exactly one {label} artifact")
    return matches[0]


def _runtime_path(artifact: Artifact) -> Path:
    if artifact.path is None:
        _raise_execution(f"Ready artifact has no runtime path: {artifact.artifact_id}")
    return artifact.path


def _string_parameter(parameters: dict[str, str | int | bool], name: str) -> str:
    value: str | int | bool | None = parameters.get(name)
    if not isinstance(value, str):
        _raise_execution(f"Composition parameter must be a string: {name}")
    return value


def _mirror_cancel(cancel: CancellationToken, event: threading.Event, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        if cancel.is_cancelled():
            event.set()
            return


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)
