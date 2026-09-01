from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TypedDict, Unpack

import pytest

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
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planner import plan_auto, plan_manual
from anishift.application.planning import (
    ExecutionPlan,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
)
from anishift.application.scheduler import ResourceLimits
from anishift.errors import PlanningError
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


def _settings() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="google",
        translation_max_retries=2,
        translation_concurrency=4,
        llm_profile_id="gemini",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=2,
        tts_group_jobs=4,
        audio_profile_id="default",
        composition_profile_id="balanced",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
        audio_output_profile="eac3",
        subtitle_language_priority=("eng", "fra"),
        audio_language_priority=("jpn", "zho"),
    )


class _PresetKwargs(TypedDict, total=False):
    subtitle_source_policy: SubtitleSourcePolicy
    translation_action: TranslationAction
    source_subtitle_language: str | None
    subtitle_output_format: SubtitleOutputFormat


class _ManualKwargs(_PresetKwargs, total=False):
    preferred_video_artifact_id: str | None
    selected_subtitle_artifact_id: str | None
    selected_audio_artifact_id: str | None
    selected_audio_track_id: int | None
    selected_subtitle_track_id: int | None
    external_audio_role: ExternalAudioRole | None


def _artifact(  # noqa: PLR0913 - artifact fixtures expose only contract fields used by scenarios
    kind: ArtifactKind,
    name: str,
    *,
    group_id: str = "episode-1",
    language: str | None = None,
    subtitle_format: str | None = None,
    audio_codec: str | None = None,
    state: ArtifactState = ArtifactState.READY,
    duration_us: int | None = None,
    lifetime: ArtifactLifetime | None = None,
) -> Artifact:
    path = Path("workspace") / name
    source_kinds = {
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.VIDEO_MP4,
        ArtifactKind.SOURCE_SUBTITLES,
        ArtifactKind.SOURCE_AUDIO,
        ArtifactKind.STANDALONE_TEXT,
    }
    resolved_lifetime = lifetime or (ArtifactLifetime.SOURCE if kind in source_kinds else ArtifactLifetime.DURABLE)
    return Artifact(
        artifact_id=f"{group_id}:{name}",
        group_id=group_id,
        kind=kind,
        path=path,
        state=state,
        lifetime=resolved_lifetime,
        planned_destination=path,
        language=language,
        subtitle_format=subtitle_format,
        audio_codec=audio_codec,
        duration_us=(
            duration_us
            if duration_us is not None
            else 10_000_000
            if kind
            in {
                ArtifactKind.VIDEO_MKV,
                ArtifactKind.VIDEO_MP4,
                ArtifactKind.SOURCE_AUDIO,
                ArtifactKind.NARRATION_AUDIO,
            }
            else None
        ),
    )


def _catalog(video: Artifact) -> MediaCatalog:
    container = ContainerKind.MKV if video.kind is ArtifactKind.VIDEO_MKV else ContainerKind.MP4
    return MediaCatalog(
        path=video.path or Path("missing"),
        container=container,
        duration_us=video.duration_us or 10_000_000,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", "Japanese", True, False),
            MediaTrack(2, MediaTrackKind.SUBTITLES, "ass", "eng", "English", False, False, "ass"),
            MediaTrack(3, MediaTrackKind.SUBTITLES, "subrip", "fra", "French", True, False, "srt"),
        ),
    )


def _group(
    *artifacts: Artifact,
    group_id: str = "episode-1",
    stem: str = "1",
) -> InspectedSourceGroup:
    source = SourceGroup(
        group_id=group_id,
        stem=stem,
        directory=Path("workspace"),
        artifacts=artifacts,
    )
    catalogs = {
        artifact.artifact_id: _catalog(artifact)
        for artifact in artifacts
        if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4} and artifact.state is ArtifactState.READY
    }
    return InspectedSourceGroup(source, artifacts, catalogs, ())


def _preset(products: ProductIntent, **kwargs: Unpack[_PresetKwargs]) -> AutoPreset:
    return AutoPreset("default", "Default", products, **kwargs)


def _manual(
    group: InspectedSourceGroup,
    products: ProductIntent,
    **kwargs: Unpack[_ManualKwargs],
) -> GroupIntent:
    return GroupIntent(group.group_id, RunMode.MANUAL, products, **kwargs)


def _task_kinds(plan: ExecutionPlan) -> tuple[TaskKind, ...]:
    return tuple(task.kind for task in plan.tasks)


def _task(plan: ExecutionPlan, kind: TaskKind) -> PlanTask:
    return next(task for task in plan.tasks if task.kind is kind)


def test_auto_embedded_subtitles_translate_and_burn_to_mp4() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    group = _group(video)
    products = ProductIntent(
        frozenset({ProductKind.FULL_PL, ProductKind.MP4}),
        burn_subtitle_product=BurnSubtitleProduct.FULL_PL,
    )
    plan = plan_auto((group,), _preset(products), _settings())
    assert plan.can_execute is True
    assert _task_kinds(plan) == (
        TaskKind.EXTRACT_SUBTITLES,
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.PUBLISH_ARTIFACT,
        TaskKind.COMPOSE_MP4,
    )
    extraction = _task(plan, TaskKind.EXTRACT_SUBTITLES)
    assert dict(extraction.parameters)["track_id"] == 2
    assert video.artifact_id in extraction.requires


def test_auto_narration_uses_one_legacy_bulk_extraction_task_per_mkv() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    products = ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO}))

    plan: ExecutionPlan = plan_auto((_group(video),), _preset(products), _settings())

    kinds: tuple[TaskKind, ...] = _task_kinds(plan)
    extraction: PlanTask = _task(plan, TaskKind.EXTRACT_TRACKS)
    produced_kinds: set[ArtifactKind] = {
        artifact.kind for artifact in plan.artifacts if artifact.artifact_id in extraction.produces
    }
    assert kinds == (
        TaskKind.EXTRACT_TRACKS,
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.SPLIT_SUBTITLES,
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.PUBLISH_ARTIFACT,
        TaskKind.PUBLISH_ARTIFACT,
    )
    assert TaskKind.EXTRACT_AUDIO not in kinds
    assert TaskKind.EXTRACT_SUBTITLES not in kinds
    assert produced_kinds == {ArtifactKind.SOURCE_AUDIO, ArtifactKind.SOURCE_SUBTITLES}
    assert dict(extraction.parameters) == {
        "audio_codec": "aac",
        "audio_track_id": 1,
        "subtitle_format": "ass",
        "subtitle_track_id": 2,
    }


def test_auto_groups_and_extraction_tasks_use_legacy_natural_order() -> None:
    episode_10 = _artifact(ArtifactKind.VIDEO_MKV, "Episode 10.mkv", group_id="episode-10")
    episode_2 = _artifact(ArtifactKind.VIDEO_MKV, "Episode 2.mkv", group_id="episode-2")
    groups: tuple[InspectedSourceGroup, ...] = (
        _group(episode_10, group_id="episode-10", stem="Episode 10"),
        _group(episode_2, group_id="episode-2", stem="Episode 2"),
    )
    products = ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO}))

    plan: ExecutionPlan = plan_auto(groups, _preset(products), _settings())

    assert tuple(group.group_id for group in plan.groups) == ("episode-2", "episode-10")
    assert tuple(task.group_id for task in plan.tasks if task.kind is TaskKind.EXTRACT_TRACKS) == (
        "episode-2",
        "episode-10",
    )


def test_auto_can_burn_source_without_translation() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    products = ProductIntent(
        frozenset({ProductKind.MP4}),
        burn_subtitle_product=BurnSubtitleProduct.SOURCE,
    )
    plan = plan_auto((_group(video),), _preset(products), _settings())
    assert TaskKind.EXTRACT_SUBTITLES in _task_kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in _task_kinds(plan)
    assert TaskKind.COMPOSE_MP4 in _task_kinds(plan)


def test_auto_sidecar_translation_narration_and_mkv_share_only_needed_tasks() -> None:
    video = _artifact(ArtifactKind.VIDEO_MP4, "1.mp4")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    products = ProductIntent(
        frozenset({ProductKind.NARRATION_AUDIO, ProductKind.MKV}),
        mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
    )
    plan = plan_auto((_group(video, sidecar),), _preset(products), _settings())
    kinds = _task_kinds(plan)
    assert TaskKind.EXTRACT_SUBTITLES not in kinds
    assert kinds.count(TaskKind.TRANSLATE_SUBTITLES) == 1
    assert kinds.count(TaskKind.SPLIT_SUBTITLES) == 1
    split = next(task for task in plan.tasks if task.kind is TaskKind.SPLIT_SUBTITLES)
    assert split.resource_key == "subtitles"
    assert split.is_network is False
    assert split.is_paid is False
    assert kinds.count(TaskKind.SYNTHESIZE_SPEECH) == 1
    assert kinds.count(TaskKind.MIX_NARRATION) == 1
    assert kinds.count(TaskKind.COMPOSE_MKV) == 1


def test_llm_translation_uses_the_llm_worker_limit() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    settings = replace(
        _settings(),
        translation_profile_id="llm",
        translation_concurrency=16,
        llm_profile_id="gemini",
        llm_max_concurrency=1,
    )
    plan = plan_auto((_group(video),), _preset(products), settings)
    task = _task(plan, TaskKind.TRANSLATE_SUBTITLES)
    limits = ResourceLimits.from_settings(settings)
    assert task.resource_key == "llm:gemini"
    assert limits.worker_limit(task.resource_key, settings) == 1


def test_manual_ready_polish_builds_narration_without_translation() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    polish = _artifact(ArtifactKind.FULL_PL, "1.pl.srt", language="pol", subtitle_format="srt")
    group = _group(video, polish)
    products = ProductIntent(frozenset({ProductKind.NARRATION_AUDIO}))
    intent = _manual(
        group,
        products,
        subtitle_source_policy=SubtitleSourcePolicy.READY_POLISH,
        selected_subtitle_artifact_id=polish.artifact_id,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    kinds = _task_kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in kinds
    assert TaskKind.EXTRACT_SUBTITLES not in kinds
    assert TaskKind.SPLIT_SUBTITLES in kinds
    assert TaskKind.SYNTHESIZE_SPEECH in kinds


def test_manual_ready_polish_policy_requires_explicit_artifact() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    first = _artifact(ArtifactKind.FULL_PL, "1.pl.ass", language="pol", subtitle_format="ass")
    second = _artifact(ArtifactKind.FULL_PL, "1.pl.srt", language="pol", subtitle_format="srt")
    group = _group(video, first, second)
    products = ProductIntent(frozenset({ProductKind.NARRATION_AUDIO}))
    intent = _manual(group, products, subtitle_source_policy=SubtitleSourcePolicy.READY_POLISH)
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"subtitle_selection_missing"}


def test_manual_ready_polish_policy_rejects_source_subtitle_id() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    source = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    group = _group(video, source)
    intent = _manual(
        group,
        ProductIntent(frozenset({ProductKind.FULL_PL})),
        subtitle_source_policy=SubtitleSourcePolicy.READY_POLISH,
        selected_subtitle_artifact_id=source.artifact_id,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"subtitle_policy_mismatch"}


def test_manual_ready_spoken_skips_translation_and_split() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    spoken = _artifact(ArtifactKind.SPOKEN_PL, "1.spoken.pl.srt", language="pol", subtitle_format="srt")
    group = _group(video, spoken)
    products = ProductIntent(
        frozenset({ProductKind.NARRATION_AUDIO, ProductKind.MKV, ProductKind.MP4}),
        mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
        mp4_audio_source=Mp4AudioSource.NARRATION,
    )
    intent = _manual(group, products, selected_subtitle_artifact_id=spoken.artifact_id)
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    kinds = _task_kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in kinds
    assert TaskKind.SPLIT_SUBTITLES not in kinds
    assert TaskKind.SYNTHESIZE_SPEECH in kinds
    assert TaskKind.COMPOSE_MKV in kinds
    assert TaskKind.COMPOSE_MP4 in kinds


def test_manual_ready_spoken_honors_explicit_output_format() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    spoken = _artifact(ArtifactKind.SPOKEN_PL, "1.spoken.pl.srt", language="pol", subtitle_format="srt")
    group = _group(video, spoken)
    products = ProductIntent(frozenset({ProductKind.SPOKEN_PL}))
    intent = _manual(
        group,
        products,
        selected_subtitle_artifact_id=spoken.artifact_id,
        subtitle_output_format=SubtitleOutputFormat.ASS,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert _task_kinds(plan) == (TaskKind.NORMALIZE_SUBTITLES, TaskKind.PUBLISH_ARTIFACT)
    target = next(
        artifact
        for artifact in plan.artifacts
        if artifact.kind is ArtifactKind.SPOKEN_PL
        and artifact.state is ArtifactState.MISSING
        and artifact.lifetime is ArtifactLifetime.DURABLE
    )
    assert target.planned_destination == Path("workspace/1.spoken.pl.ass")


def test_manual_displayed_cannot_duplicate_format_conversion_when_narration_is_requested() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    displayed = _artifact(
        ArtifactKind.DISPLAYED_PL,
        "1.displayed.pl.srt",
        language="pol",
        subtitle_format="srt",
    )
    group = _group(video, displayed)
    products = ProductIntent(frozenset({ProductKind.DISPLAYED_PL, ProductKind.NARRATION_AUDIO}))
    intent = _manual(
        group,
        products,
        selected_subtitle_artifact_id=displayed.artifact_id,
        subtitle_output_format=SubtitleOutputFormat.ASS,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"spoken_polish_unavailable"}


def test_manual_ready_narration_composes_without_tts_or_subtitles() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    narration = _artifact(ArtifactKind.NARRATION_AUDIO, "1.eac3", audio_codec="eac3")
    group = _group(video, narration)
    products = ProductIntent(
        frozenset({ProductKind.MKV, ProductKind.MP4}),
        mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
        mp4_audio_source=Mp4AudioSource.NARRATION,
    )
    intent = _manual(group, products, selected_audio_artifact_id=narration.artifact_id)
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert _task_kinds(plan) == (TaskKind.COMPOSE_MKV, TaskKind.COMPOSE_MP4)


def test_manual_external_narration_uses_configured_product_codec() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    narration = _artifact(
        ArtifactKind.NARRATION_AUDIO,
        "outside.aac",
        audio_codec=None,
        lifetime=ArtifactLifetime.SOURCE,
    )
    group = _group(video, narration)
    products = ProductIntent(frozenset({ProductKind.NARRATION_AUDIO}))
    intent = _manual(
        group,
        products,
        selected_audio_artifact_id=narration.artifact_id,
        external_audio_role=ExternalAudioRole.NARRATION_MIX,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert _task_kinds(plan) == (TaskKind.TRANSCODE_AUDIO, TaskKind.PUBLISH_ARTIFACT)
    target = next(
        artifact
        for artifact in plan.artifacts
        if artifact.kind is ArtifactKind.NARRATION_AUDIO
        and artifact.lifetime is ArtifactLifetime.DURABLE
        and artifact.state is ArtifactState.MISSING
    )
    assert target.planned_destination == Path("workspace/1.eac3")


def test_aac_audio_profile_publishes_m4a_extension() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    narration = _artifact(
        ArtifactKind.NARRATION_AUDIO,
        "outside.eac3",
        audio_codec=None,
        lifetime=ArtifactLifetime.SOURCE,
    )
    group = _group(video, narration)
    intent = _manual(
        group,
        ProductIntent(frozenset({ProductKind.NARRATION_AUDIO})),
        selected_audio_artifact_id=narration.artifact_id,
        external_audio_role=ExternalAudioRole.NARRATION_MIX,
    )
    settings = replace(_settings(), audio_output_profile="aac")
    plan = plan_manual((group,), {group.group_id: intent}, settings)
    target = next(
        artifact
        for artifact in plan.artifacts
        if artifact.kind is ArtifactKind.NARRATION_AUDIO
        and artifact.lifetime is ArtifactLifetime.DURABLE
        and artifact.state is ArtifactState.MISSING
    )
    assert target.planned_destination == Path("workspace/1.m4a")


def test_manual_external_source_audio_replaces_embedded_audio_for_mix() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    polish = _artifact(ArtifactKind.FULL_PL, "1.pl.srt", language="pol", subtitle_format="srt")
    external_audio = _artifact(ArtifactKind.SOURCE_AUDIO, "outside.flac", audio_codec="flac")
    group = _group(video, polish, external_audio)
    products = ProductIntent(frozenset({ProductKind.NARRATION_AUDIO}))
    intent = _manual(
        group,
        products,
        selected_subtitle_artifact_id=polish.artifact_id,
        selected_audio_artifact_id=external_audio.artifact_id,
        external_audio_role=ExternalAudioRole.SOURCE_AUDIO,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    kinds = _task_kinds(plan)
    assert TaskKind.EXTRACT_AUDIO not in kinds
    assert external_audio.artifact_id in _task(plan, TaskKind.MIX_NARRATION).requires


def test_manual_audio_is_revalidated_against_preferred_video_duration() -> None:
    mkv = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv", duration_us=10_000_000)
    mp4 = _artifact(ArtifactKind.VIDEO_MP4, "1.mp4", duration_us=12_000_001)
    narration = _artifact(ArtifactKind.NARRATION_AUDIO, "1.eac3", audio_codec="eac3", duration_us=10_000_000)
    group = _group(mkv, mp4, narration)
    products = ProductIntent(
        frozenset({ProductKind.MP4}),
        mp4_audio_source=Mp4AudioSource.NARRATION,
    )
    intent = _manual(
        group,
        products,
        preferred_video_artifact_id=mp4.artifact_id,
        selected_audio_artifact_id=narration.artifact_id,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"audio_duration_mismatch"}


def test_audio_duration_tolerance_comes_from_run_snapshot() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv", duration_us=10_000_000)
    narration = _artifact(ArtifactKind.NARRATION_AUDIO, "1.eac3", audio_codec="eac3", duration_us=12_000_000)
    group = _group(video, narration)
    products = ProductIntent(frozenset({ProductKind.MP4}), mp4_audio_source=Mp4AudioSource.NARRATION)
    intent = _manual(group, products, selected_audio_artifact_id=narration.artifact_id)
    settings = replace(_settings(), audio_duration_tolerance_us=2_000_000)
    plan = plan_manual((group,), {group.group_id: intent}, settings)
    assert plan.can_execute is True


def test_task_cost_flags_come_from_run_snapshot() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    settings = replace(_settings(), translation_is_network=False, translation_is_paid=False)
    plan = plan_auto(
        (_group(video, sidecar),),
        _preset(ProductIntent(frozenset({ProductKind.FULL_PL}))),
        settings,
    )
    translation = _task(plan, TaskKind.TRANSLATE_SUBTITLES)
    assert translation.is_network is False
    assert translation.is_paid is False


def test_manual_external_subtitle_products_keep_video_stem() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    external = _artifact(
        ArtifactKind.SOURCE_SUBTITLES,
        "unrelated-name.ass",
        language="fra",
        subtitle_format="ass",
    )
    group = _group(video, external)
    products = ProductIntent(frozenset({ProductKind.SOURCE_SUBTITLES, ProductKind.FULL_PL}))
    intent = _manual(
        group,
        products,
        subtitle_source_policy=SubtitleSourcePolicy.EXTERNAL,
        selected_subtitle_artifact_id=external.artifact_id,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    destinations = {
        artifact.planned_destination.name
        for artifact in plan.artifacts
        if artifact.state is ArtifactState.MISSING and artifact.planned_destination is not None
    }
    assert {"1.ass", "1.pl.ass"}.issubset(destinations)
    assert external.path in {artifact.path for artifact in plan.artifacts}


def test_video_without_subtitles_can_repackage_to_mp4() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    products = ProductIntent(frozenset({ProductKind.MP4}))
    plan = plan_auto((_group(video),), _preset(products), _settings())
    assert _task_kinds(plan) == (TaskKind.COMPOSE_MP4,)


def test_standalone_txt_produces_only_polish_srt() -> None:
    text = _artifact(ArtifactKind.STANDALONE_TEXT, "1.txt")
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    plan = plan_auto((_group(text),), _preset(products), _settings())
    assert _task_kinds(plan) == (TaskKind.TRANSLATE_SUBTITLES, TaskKind.PUBLISH_ARTIFACT)
    target = next(artifact for artifact in plan.artifacts if artifact.lifetime is ArtifactLifetime.DURABLE)
    assert target.planned_destination == Path("workspace/1.pl.srt")


def test_auto_chooses_mkv_and_ass_regardless_of_input_order() -> None:
    mkv = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    mp4 = _artifact(ArtifactKind.VIDEO_MP4, "1.mp4")
    ass = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    srt = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.srt", subtitle_format="srt")
    products = ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.MP4}))
    plan = plan_auto((_group(srt, mp4, ass, mkv),), _preset(products), _settings())
    translate = _task(plan, TaskKind.TRANSLATE_SUBTITLES)
    compose = _task(plan, TaskKind.COMPOSE_MP4)
    assert ass.artifact_id in translate.requires
    assert srt.artifact_id not in translate.requires
    assert mkv.artifact_id in compose.requires
    assert mp4.artifact_id not in compose.requires


def test_auto_never_uses_existing_derived_product_as_input() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    previous = _artifact(ArtifactKind.FULL_PL, "1.pl.ass", language="pol", subtitle_format="ass")
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    plan = plan_auto((_group(video, previous),), _preset(products), _settings())
    required = {artifact_id for task in plan.tasks for artifact_id in task.requires}
    assert previous.artifact_id not in required
    assert TaskKind.EXTRACT_SUBTITLES in _task_kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES in _task_kinds(plan)
    assert any(problem.code == "product_overwrite" and not problem.is_blocking for problem in plan.problems)
    target = next(
        artifact
        for artifact in plan.artifacts
        if artifact.kind is ArtifactKind.FULL_PL
        and artifact.state is ArtifactState.MISSING
        and artifact.lifetime is ArtifactLifetime.DURABLE
    )
    assert target.preserved_path == previous.path


def test_forced_translation_translates_declared_polish_source() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(
        ArtifactKind.SOURCE_SUBTITLES,
        "1.srt",
        language="pol",
        subtitle_format="srt",
    )
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    preset = _preset(products, translation_action=TranslationAction.TRANSLATE)
    plan = plan_auto((_group(video, sidecar),), preset, _settings())
    assert TaskKind.TRANSLATE_SUBTITLES in _task_kinds(plan)


def test_do_not_translate_unknown_source_blocks_false_polish_product() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.srt", subtitle_format="srt")
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    preset = _preset(products, translation_action=TranslationAction.DO_NOT_TRANSLATE)
    plan = plan_auto((_group(video, sidecar),), preset, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert plan.problems[0].code == "false_polish_product"


def test_exact_stem_source_product_requires_no_task() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    products = ProductIntent(frozenset({ProductKind.SOURCE_SUBTITLES}))
    plan = plan_auto((_group(video, sidecar),), _preset(products), _settings())
    assert plan.can_execute is True
    assert plan.tasks == ()


def test_manual_embedded_source_cannot_replace_existing_sidecar() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    group = _group(video, sidecar)
    products = ProductIntent(frozenset({ProductKind.SOURCE_SUBTITLES}))
    intent = _manual(
        group,
        products,
        subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
        selected_subtitle_track_id=2,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"source_path_collision"}


def test_manual_selected_srt_overrides_automatic_ass_preference() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    ass = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    srt = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.srt", subtitle_format="srt")
    group = _group(video, ass, srt)
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    intent = _manual(group, products, selected_subtitle_artifact_id=srt.artifact_id)
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    translate = _task(plan, TaskKind.TRANSLATE_SUBTITLES)
    assert srt.artifact_id in translate.requires
    assert ass.artifact_id not in translate.requires


def test_manual_declared_source_language_reaches_mkv_track() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    group = _group(video, sidecar)
    products = ProductIntent(
        frozenset({ProductKind.MKV}),
        mkv_tracks=frozenset({MkvTrackProduct.SOURCE_SUBTITLES}),
    )
    intent = _manual(
        group,
        products,
        selected_subtitle_artifact_id=sidecar.artifact_id,
        source_subtitle_language="fra",
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    selected = next(artifact for artifact in plan.artifacts if artifact.artifact_id == sidecar.artifact_id)
    assert selected.language == "fra"
    assert selected.artifact_id in _task(plan, TaskKind.COMPOSE_MKV).requires


def test_manual_selected_embedded_track_overrides_sidecar() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    group = _group(video, sidecar)
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    intent = _manual(group, products, selected_subtitle_track_id=3)
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    extraction = _task(plan, TaskKind.EXTRACT_SUBTITLES)
    assert dict(extraction.parameters)["track_id"] == 3
    assert sidecar.artifact_id not in _task(plan, TaskKind.TRANSLATE_SUBTITLES).requires


def test_polish_pl_language_alias_bypasses_translation() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(
        ArtifactKind.SOURCE_SUBTITLES,
        "1.srt",
        language="pl",
        subtitle_format="srt",
    )
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    plan = plan_auto((_group(video, sidecar),), _preset(products), _settings())
    assert TaskKind.TRANSLATE_SUBTITLES not in _task_kinds(plan)
    assert TaskKind.NORMALIZE_SUBTITLES in _task_kinds(plan)


@pytest.mark.parametrize("kind", [ArtifactKind.SPOKEN_PL, ArtifactKind.DISPLAYED_PL])
def test_manual_cannot_force_translate_a_derived_polish_product(kind: ArtifactKind) -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    suffix = "spoken.pl.srt" if kind is ArtifactKind.SPOKEN_PL else "displayed.pl.srt"
    polish = _artifact(kind, f"1.{suffix}", language="pol", subtitle_format="srt")
    group = _group(video, polish)
    requested = ProductKind.SPOKEN_PL if kind is ArtifactKind.SPOKEN_PL else ProductKind.DISPLAYED_PL
    intent = _manual(
        group,
        ProductIntent(frozenset({requested})),
        selected_subtitle_artifact_id=polish.artifact_id,
        translation_action=TranslationAction.TRANSLATE,
    )
    plan = plan_manual((group,), {group.group_id: intent}, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert {problem.code for problem in plan.problems} == {"polish_product_not_translatable"}


def test_mkv_and_mp4_share_one_generated_narration_artifact() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    sidecar = _artifact(ArtifactKind.SOURCE_SUBTITLES, "1.ass", subtitle_format="ass")
    products = ProductIntent(
        frozenset({ProductKind.MKV, ProductKind.MP4}),
        mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
        mp4_audio_source=Mp4AudioSource.NARRATION,
    )
    plan = plan_auto((_group(video, sidecar),), _preset(products), _settings())
    mix_output = _task(plan, TaskKind.MIX_NARRATION).produces[0]
    assert mix_output in _task(plan, TaskKind.COMPOSE_MKV).requires
    assert mix_output in _task(plan, TaskKind.COMPOSE_MP4).requires


def test_three_manual_groups_keep_independent_products_and_sources() -> None:
    groups: list[InspectedSourceGroup] = []
    intents: dict[str, GroupIntent] = {}
    for number, product in enumerate((ProductKind.FULL_PL, ProductKind.MKV, ProductKind.MP4), start=1):
        group_id = f"episode-{number}"
        video = _artifact(ArtifactKind.VIDEO_MKV, f"{number}.mkv", group_id=group_id)
        sidecar = _artifact(
            ArtifactKind.SOURCE_SUBTITLES,
            f"{number}.srt",
            group_id=group_id,
            subtitle_format="srt",
        )
        group = _group(video, sidecar, group_id=group_id, stem=str(number))
        groups.append(group)
        intents[group_id] = _manual(
            group,
            ProductIntent(frozenset({product})),
            selected_subtitle_artifact_id=sidecar.artifact_id,
        )
    plan = plan_manual(tuple(reversed(groups)), intents, _settings())
    assert tuple(group.group_id for group in plan.groups) == ("episode-1", "episode-2", "episode-3")
    assert {task.group_id for task in plan.tasks} == {"episode-1", "episode-2", "episode-3"}


def test_one_blocked_group_makes_the_whole_batch_non_executable() -> None:
    first_id = "episode-1"
    first_video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv", group_id=first_id)
    first_sidecar = _artifact(
        ArtifactKind.SOURCE_SUBTITLES,
        "1.ass",
        group_id=first_id,
        subtitle_format="ass",
    )
    first = _group(first_video, first_sidecar, group_id=first_id, stem="1")
    second_id = "episode-2"
    second_video = _artifact(ArtifactKind.VIDEO_MKV, "2.mkv", group_id=second_id)
    second = _group(second_video, group_id=second_id, stem="2")
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    preset = _preset(products, subtitle_source_policy=SubtitleSourcePolicy.SIDECAR)
    plan = plan_auto((first, second), preset, _settings())
    assert plan.can_execute is False
    assert plan.tasks == ()
    assert all(artifact.state is not ArtifactState.MISSING for artifact in plan.artifacts)


def test_manual_planning_requires_exact_intent_map() -> None:
    video = _artifact(ArtifactKind.VIDEO_MKV, "1.mkv")
    group = _group(video)
    with pytest.raises(PlanningError, match="exactly one intent"):
        plan_manual((group,), {}, _settings())
