from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
    create_artifact_id,
    create_group_id,
)
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.errors import ExecutionError


def _source_artifact(*, state: ArtifactState = ArtifactState.READY) -> Artifact:
    path = Path("workspace/episode.mkv")
    return Artifact(
        artifact_id="video",
        group_id="episode",
        kind=ArtifactKind.VIDEO_MKV,
        path=path,
        state=state,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
    )


def test_artifact_ids_are_stable_and_case_normalized() -> None:
    first_group = create_group_id(Path("Series/Season 1"), "Episode 01")
    second_group = create_group_id(Path("series/season 1"), "episode 01")
    assert first_group == second_group
    first_artifact = create_artifact_id(first_group, ArtifactKind.VIDEO_MKV, Path("Episode.mkv"))
    second_artifact = create_artifact_id(first_group, ArtifactKind.VIDEO_MKV, Path("episode.mkv"))
    assert first_artifact == second_artifact


def test_planned_artifact_variants_do_not_collide() -> None:
    first = create_artifact_id("episode", ArtifactKind.TTS_CLIP, variant="cue-001")
    second = create_artifact_id("episode", ArtifactKind.TTS_CLIP, variant="cue-002")
    assert first != second


@pytest.mark.parametrize("path", [Path("../episode.mkv"), Path.cwd() / "episode.mkv"])
def test_artifact_ids_reject_paths_outside_workspace(path: Path) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        create_artifact_id("episode", ArtifactKind.VIDEO_MKV, path)


def test_planned_durable_artifact_can_lack_runtime_path() -> None:
    destination = Path("workspace/episode.pl.mkv")
    artifact = Artifact(
        artifact_id="final-mkv",
        group_id="episode",
        kind=ArtifactKind.FINAL_MKV,
        path=None,
        state=ArtifactState.MISSING,
        lifetime=ArtifactLifetime.DURABLE,
        planned_destination=destination,
    )
    assert artifact.path is None
    assert artifact.planned_destination == destination


def test_final_container_cannot_be_a_source() -> None:
    path = Path("workspace/episode.pl.mkv")
    with pytest.raises(ValueError, match="never sources"):
        Artifact(
            artifact_id="final-mkv",
            group_id="episode",
            kind=ArtifactKind.FINAL_MKV,
            path=path,
            state=ArtifactState.READY,
            lifetime=ArtifactLifetime.SOURCE,
            planned_destination=path,
        )


def test_candidate_artifact_requires_runtime_path() -> None:
    with pytest.raises(ValueError, match="runtime path"):
        Artifact(
            artifact_id="subtitle",
            group_id="episode",
            kind=ArtifactKind.SOURCE_SUBTITLES,
            path=None,
            state=ArtifactState.CANDIDATE,
            lifetime=ArtifactLifetime.INTERMEDIATE,
        )


def test_source_group_filters_ready_artifacts_without_io() -> None:
    ready = _source_artifact()
    candidate_path = Path("workspace/alternative.mkv")
    candidate = Artifact(
        artifact_id="alternative",
        group_id="episode",
        kind=ArtifactKind.VIDEO_MKV,
        path=candidate_path,
        state=ArtifactState.CANDIDATE,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=candidate_path,
    )
    group = SourceGroup(
        group_id="episode",
        stem="episode",
        directory=Path("workspace"),
        artifacts=(candidate, ready),
    )
    assert group.artifacts_of_kind(ArtifactKind.VIDEO_MKV) == (candidate, ready)
    assert group.ready_artifacts_of_kind(ArtifactKind.VIDEO_MKV) == (ready,)
    assert asdict(group)["group_id"] == "episode"
    with pytest.raises(FrozenInstanceError):
        group.stem = "changed"  # type: ignore[misc]


def test_artifact_snapshot_requires_validated_input() -> None:
    ready = _source_artifact()
    source: dict[str, Artifact] = {ready.artifact_id: ready}
    snapshot = ArtifactSnapshot(source)
    source.clear()
    assert snapshot.require_ready("video") is ready
    assert asdict(snapshot)["artifacts"]["video"].artifact_id == "video"
    with pytest.raises(ExecutionError, match="absent"):
        snapshot.require_ready("missing")


def test_artifact_snapshot_exposes_planned_output_descriptor() -> None:
    ready = _source_artifact()
    destination = Path("workspace/episode.pl.mkv")
    output = Artifact(
        "final-mkv",
        "episode",
        ArtifactKind.FINAL_MKV,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.DURABLE,
        destination,
    )
    snapshot = ArtifactSnapshot({ready.artifact_id: ready}, {output.artifact_id: output})
    assert snapshot.require_output(output.artifact_id).planned_destination == destination
    with pytest.raises(ExecutionError, match="absent"):
        snapshot.require_output("missing")


def test_task_result_copies_read_only_metadata() -> None:
    metadata: dict[str, str | int | bool] = {"published": True}
    output = ProducedArtifact("final-mkv", Path("workspace/episode.pl.mkv"), metadata)
    metadata["published"] = False
    result = TaskResult(task_id="compose", outputs=(output,))
    assert result.outputs[0].metadata["published"] is True
    assert asdict(result)["outputs"][0]["metadata"] == {"published": True}


def test_task_result_rejects_empty_outputs() -> None:
    with pytest.raises(ValueError, match="at least one"):
        TaskResult(task_id="compose", outputs=())
