from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.handlers import build_composition_request
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot
from anishift.errors import ExecutionError
from anishift.services.composition.types import ContainerTarget, SubtitleRole


def _ready(artifact_id: str, kind: ArtifactKind, path: Path, *, language: str | None = None) -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        group_id="group-1",
        kind=kind,
        path=path,
        state=ArtifactState.READY,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
        language=language,
    )


def _output(artifact_id: str, kind: ArtifactKind, destination: Path) -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        group_id="group-1",
        kind=kind,
        path=None,
        state=ArtifactState.MISSING,
        lifetime=ArtifactLifetime.DURABLE,
        planned_destination=destination,
    )


def _task(
    kind: TaskKind,
    requires: tuple[str, ...],
    produces: str,
    parameters: tuple[tuple[str, str | int | bool], ...],
) -> PlanTask:
    return PlanTask(
        task_id=f"task-{kind.value}",
        group_id="group-1",
        kind=kind,
        requires=requires,
        produces=(produces,),
        depends_on=(),
        resource_key="composition:balanced",
        parameters=parameters,
    )


def test_build_mkv_request_uses_only_planned_tracks(tmp_path: Path) -> None:
    video = _ready("video", ArtifactKind.VIDEO_MKV, tmp_path / "Episode.mkv")
    full = _ready("full", ArtifactKind.FULL_PL, tmp_path / "Episode.pl.ass", language="pol")
    narration = _ready("audio", ArtifactKind.NARRATION_AUDIO, tmp_path / "Episode.eac3")
    output = _output("mkv", ArtifactKind.FINAL_MKV, tmp_path / "Episode.pl.mkv")
    snapshot = ArtifactSnapshot(
        {artifact.artifact_id: artifact for artifact in (video, full, narration)},
        {output.artifact_id: output},
    )
    task = _task(
        TaskKind.COMPOSE_MKV,
        ("video", "full", "audio"),
        "mkv",
        (("mkv_tracks", "full_pl_subtitles,narration_audio"),),
    )

    request = build_composition_request(task, snapshot)

    assert request.target is ContainerTarget.MKV
    assert request.narration_audio == narration.path
    assert request.keep_original_audio is True
    assert tuple(subtitle.path for subtitle in request.attached_subtitles) == (full.path,)
    assert request.attached_subtitles[0].role is SubtitleRole.FULL


def test_build_mp4_request_uses_explicit_burn_and_audio_products(tmp_path: Path) -> None:
    video = _ready("video", ArtifactKind.VIDEO_MKV, tmp_path / "Episode.mkv")
    displayed = _ready("displayed", ArtifactKind.DISPLAYED_PL, tmp_path / "Episode.displayed.pl.ass")
    narration = _ready("audio", ArtifactKind.NARRATION_AUDIO, tmp_path / "Episode.eac3")
    output = _output("mp4", ArtifactKind.FINAL_MP4, tmp_path / "Episode.pl.mp4")
    snapshot = ArtifactSnapshot(
        {artifact.artifact_id: artifact for artifact in (video, displayed, narration)},
        {output.artifact_id: output},
    )
    task = _task(
        TaskKind.COMPOSE_MP4,
        ("video", "displayed", "audio"),
        "mp4",
        (("audio_source", "narration"), ("burn_subtitles", "displayed_pl")),
    )

    request = build_composition_request(task, snapshot)

    assert request.target is ContainerTarget.MP4
    assert request.burn_subtitle == displayed.path
    assert request.narration_audio == narration.path
    assert request.keep_original_audio is False


def test_build_composition_request_rejects_output_away_from_source(tmp_path: Path) -> None:
    video = _ready("video", ArtifactKind.VIDEO_MKV, tmp_path / "Episode.mkv")
    destination = tmp_path / "output" / "Episode.pl.mp4"
    output = _output("mp4", ArtifactKind.FINAL_MP4, destination)
    snapshot = ArtifactSnapshot({video.artifact_id: video}, {output.artifact_id: output})
    task = _task(
        TaskKind.COMPOSE_MP4,
        ("video",),
        "mp4",
        (("audio_source", "original"), ("burn_subtitles", "none")),
    )

    with pytest.raises(ExecutionError, match="next to"):
        build_composition_request(task, snapshot)


def test_build_composition_request_rejects_output_kind_mismatch(tmp_path: Path) -> None:
    video = _ready("video", ArtifactKind.VIDEO_MKV, tmp_path / "Episode.mkv")
    output = _output("wrong", ArtifactKind.FINAL_MKV, tmp_path / "Episode.pl.mp4")
    snapshot = ArtifactSnapshot({video.artifact_id: video}, {output.artifact_id: output})
    task = _task(
        TaskKind.COMPOSE_MP4,
        ("video",),
        "wrong",
        (("audio_source", "original"), ("burn_subtitles", "none")),
    )

    with pytest.raises(ExecutionError, match="final_mp4"):
        build_composition_request(task, snapshot)
