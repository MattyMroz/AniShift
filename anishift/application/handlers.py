"""Typed adapters from planned tasks to domain-service requests."""

from __future__ import annotations

from pathlib import Path

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.intents import BurnSubtitleProduct, MkvTrackProduct
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot
from anishift.errors import ExecutionError
from anishift.services.composition.types import (
    AttachedSubtitle,
    ContainerCompositionRequest,
    ContainerTarget,
    SubtitleRole,
)

__all__ = ["build_composition_request"]


def build_composition_request(task: PlanTask, artifacts: ArtifactSnapshot) -> ContainerCompositionRequest:
    """Translate one composition task into an exact single-container request."""
    if task.kind not in {TaskKind.COMPOSE_MKV, TaskKind.COMPOSE_MP4}:
        msg = "Only composition tasks can build a container request"
        raise ExecutionError(msg)
    if len(task.produces) != 1:
        msg = "A composition task must produce exactly one container"
        raise ExecutionError(msg)
    inputs: tuple[Artifact, ...] = tuple(artifacts.require_ready(artifact_id) for artifact_id in task.requires)
    video: Artifact = _require_one(inputs, {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}, "source video")
    source_video: Path = _runtime_path(video)
    output: Artifact = artifacts.require_output(task.produces[0])
    expected_output_kind: ArtifactKind = (
        ArtifactKind.FINAL_MKV if task.kind is TaskKind.COMPOSE_MKV else ArtifactKind.FINAL_MP4
    )
    if output.kind is not expected_output_kind:
        msg = f"{task.kind.value} must produce {expected_output_kind.value}"
        raise ExecutionError(msg)
    destination: Path | None = output.planned_destination
    if destination is None or destination.parent != source_video.parent:
        msg = "Container destination must be planned next to its selected source"
        raise ExecutionError(msg)
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
        msg = "MP4 audio source must be original or narration"
        raise ExecutionError(msg)
    return ContainerCompositionRequest(
        source_video=source_video,
        destination=destination,
        target=ContainerTarget.MP4,
        burn_subtitle=burn_subtitle,
        attached_subtitles=(),
        narration_audio=narration_audio,
        keep_original_audio=audio_source == "original",
    )


def _require_one(inputs: tuple[Artifact, ...], kinds: set[ArtifactKind], label: str) -> Artifact:
    matches: tuple[Artifact, ...] = tuple(artifact for artifact in inputs if artifact.kind in kinds)
    if len(matches) != 1:
        msg = f"Composition task requires exactly one {label} artifact"
        raise ExecutionError(msg)
    return matches[0]


def _runtime_path(artifact: Artifact) -> Path:
    if artifact.path is None:
        msg = f"Ready artifact has no runtime path: {artifact.artifact_id}"
        raise ExecutionError(msg)
    return artifact.path


def _string_parameter(parameters: dict[str, str | int | bool], name: str) -> str:
    value: str | int | bool | None = parameters.get(name)
    if not isinstance(value, str):
        msg = f"Composition parameter must be a string: {name}"
        raise ExecutionError(msg)
    return value
