from __future__ import annotations

from pathlib import Path
from random import Random

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
)
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
)
from anishift.application.planner import plan_auto
from anishift.application.planning import (
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
    stable_topological_order,
)
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


def _settings() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="translation",
        translation_max_retries=1,
        translation_concurrency=2,
        llm_profile_id="classifier",
        llm_max_concurrency=1,
        tts_profile_id="tts",
        tts_max_retries=1,
        tts_group_jobs=2,
        audio_profile_id="audio",
        composition_profile_id="composition",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )


def _artifact(kind: ArtifactKind, name: str, *, subtitle_format: str | None = None) -> Artifact:
    path = Path("workspace") / name
    lifetime = (
        ArtifactLifetime.SOURCE
        if kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4, ArtifactKind.SOURCE_SUBTITLES}
        else ArtifactLifetime.DURABLE
    )
    return Artifact(
        artifact_id=f"artifact:{name}",
        group_id="episode",
        kind=kind,
        path=path,
        state=ArtifactState.READY,
        lifetime=lifetime,
        planned_destination=path,
        language="pol" if kind is ArtifactKind.FULL_PL else None,
        subtitle_format=subtitle_format,
    )


def _group(artifacts: tuple[Artifact, ...]) -> InspectedSourceGroup:
    video = next(
        artifact for artifact in artifacts if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}
    )
    container = ContainerKind.MKV if video.kind is ArtifactKind.VIDEO_MKV else ContainerKind.MP4
    catalog = MediaCatalog(
        path=video.path or Path("missing"),
        container=container,
        duration_us=1_000_000,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", None, True, False),
            MediaTrack(2, MediaTrackKind.SUBTITLES, "ass", "eng", None, True, False, "ass"),
        ),
    )
    source = SourceGroup("episode", "1", Path("workspace"), artifacts)
    return InspectedSourceGroup(source, artifacts, {video.artifact_id: catalog}, ())


def _products(random: Random) -> ProductIntent:
    all_products = tuple(ProductKind)
    requested = frozenset(product for product in all_products if random.choice((False, True)))
    if not requested:
        requested = frozenset({random.choice(all_products)})
    burn = random.choice(tuple(BurnSubtitleProduct)) if ProductKind.MP4 in requested else BurnSubtitleProduct.NONE
    mkv_tracks = (
        frozenset(track for track in MkvTrackProduct if random.choice((False, True)))
        if ProductKind.MKV in requested
        else frozenset()
    )
    mp4_audio = random.choice(tuple(Mp4AudioSource)) if ProductKind.MP4 in requested else Mp4AudioSource.AUTO
    return ProductIntent(requested, burn, mkv_tracks, mp4_audio)


def test_generated_auto_plans_preserve_graph_invariants() -> None:
    random = Random(9)  # noqa: S311
    settings = _settings()
    for index in range(500):
        video_kind = random.choice((ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4))
        video_suffix = "mkv" if video_kind is ArtifactKind.VIDEO_MKV else "mp4"
        video = _artifact(video_kind, f"1.{video_suffix}")
        previous = _artifact(ArtifactKind.FULL_PL, "1.pl.srt", subtitle_format="srt")
        artifacts: list[Artifact] = [video, previous]
        if random.choice((False, True)):
            suffix = random.choice(("ass", "srt"))
            artifacts.append(_artifact(ArtifactKind.SOURCE_SUBTITLES, f"1.{suffix}", subtitle_format=suffix))
        random.shuffle(artifacts)
        group = _group(tuple(artifacts))
        preset = AutoPreset(f"preset-{index}", "Generated", _products(random))
        first = plan_auto((group,), preset, settings)
        second = plan_auto((_group(tuple(reversed(artifacts))),), preset, settings)
        assert first == second
        assert first.can_execute is True
        assert first.tasks == stable_topological_order(first.tasks)
        produced = [artifact_id for task in first.tasks for artifact_id in task.produces]
        assert len(produced) == len(set(produced))
        producer_by_artifact = {artifact_id: task.task_id for task in first.tasks for artifact_id in task.produces}
        for task in first.tasks:
            assert all(
                producer_by_artifact[artifact_id] in task.depends_on
                for artifact_id in task.requires
                if artifact_id in producer_by_artifact
            )
        missing = {artifact.artifact_id for artifact in first.artifacts if artifact.state is ArtifactState.MISSING}
        assert missing.issubset(producer_by_artifact)
        required = {artifact_id for task in first.tasks for artifact_id in task.requires}
        assert previous.artifact_id not in required
        publish_tasks = tuple(task for task in first.tasks if task.kind is TaskKind.PUBLISH_ARTIFACT)
        assert all(set(task.requires).isdisjoint(task.produces) for task in publish_tasks)
        source_paths = {artifact.path for artifact in group.artifacts if artifact.lifetime is ArtifactLifetime.SOURCE}
        artifact_by_id = {artifact.artifact_id: artifact for artifact in first.artifacts}
        assert all(artifact_by_id[task.produces[0]].planned_destination not in source_paths for task in publish_tasks)
        requested = preset.products.requested_products
        narration_needed = (
            ProductKind.NARRATION_AUDIO in requested
            or MkvTrackProduct.NARRATION_AUDIO in preset.products.mkv_tracks
            or preset.products.mp4_audio_source is Mp4AudioSource.NARRATION
        )
        if not narration_needed:
            assert not {
                TaskKind.EXTRACT_AUDIO,
                TaskKind.SYNTHESIZE_SPEECH,
                TaskKind.MIX_NARRATION,
            } & {task.kind for task in first.tasks}
