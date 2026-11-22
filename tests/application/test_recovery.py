from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from test_planner import _artifact, _group, _preset, _settings

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactState
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.intents import ProductIntent, ProductKind
from anishift.application.planner import plan_auto, replan
from anishift.application.planning import ExecutionPlan, PlanTask, RunSettingsSnapshot, TaskKind
from anishift.application.recovery import _remaining, rebase_plan
from anishift.application.results import ProducedArtifact, TaskResult

_NARRATION: ProductIntent = ProductIntent(frozenset({ProductKind.NARRATION_AUDIO}))


def _episode() -> InspectedSourceGroup:
    return _group(_artifact(ArtifactKind.VIDEO_MKV, "1.mkv"))


def _finished(plan: ExecutionPlan, kinds: frozenset[TaskKind]) -> tuple[ExecutionPlan, tuple[PlanTask, ...]]:
    remaining: ExecutionPlan = plan
    done: list[PlanTask] = []
    for task in plan.tasks:
        if task.kind not in kinds:
            continue
        outputs: tuple[ProducedArtifact, ...] = tuple(
            ProducedArtifact(artifact_id, Path("run") / artifact_id, {}) for artifact_id in task.produces
        )
        remaining = _remaining(remaining, TaskResult(task.task_id, outputs))
        done.append(replace(task, depends_on=()))
    return remaining, tuple(done)


def _accepted(kinds: frozenset[TaskKind]) -> tuple[ExecutionPlan, tuple[PlanTask, ...]]:
    return _finished(plan_auto((_episode(),), _preset(_NARRATION), _settings()), kinds)


def _fresh(saved: ExecutionPlan, settings: RunSettingsSnapshot) -> ExecutionPlan:
    return replan((_episode(),), saved, settings)


_BEFORE_MIX: frozenset[TaskKind] = frozenset(
    {TaskKind.EXTRACT_TRACKS, TaskKind.TRANSLATE_SUBTITLES, TaskKind.SPLIT_SUBTITLES, TaskKind.SYNTHESIZE_SPEECH}
)


def test_rebasing_onto_unchanged_settings_keeps_the_saved_remaining_graph() -> None:
    saved, done = _accepted(_BEFORE_MIX)

    rebased, kept = rebase_plan(saved, done, _fresh(saved, _settings()))

    assert rebased == saved
    assert kept == done


def test_a_new_model_or_engine_invalidates_nothing_already_made() -> None:
    saved, done = _accepted(_BEFORE_MIX)
    changed: RunSettingsSnapshot = replace(_settings(), translation_profile_id="llm", tts_profile_id="elevenreader")

    rebased, kept = rebase_plan(saved, done, _fresh(saved, changed))

    assert rebased == saved
    assert kept == done


def test_a_new_audio_profile_mixes_again_without_recording_the_voice_again() -> None:
    saved, done = _accepted(_BEFORE_MIX)

    rebased, kept = rebase_plan(saved, done, _fresh(saved, replace(_settings(), audio_output_profile="aac")))

    kinds: tuple[TaskKind, ...] = tuple(task.kind for task in rebased.tasks)
    assert TaskKind.SYNTHESIZE_SPEECH not in kinds
    assert TaskKind.MIX_NARRATION in kinds
    assert TaskKind.PUBLISH_ARTIFACT in kinds
    assert {task.kind for task in kept} == _BEFORE_MIX
    published: Artifact = next(
        artifact
        for artifact in rebased.artifacts
        if artifact.planned_destination is not None
        and artifact.kind is ArtifactKind.NARRATION_AUDIO
        and artifact.state is ArtifactState.MISSING
    )
    assert published.planned_destination is not None
    assert published.planned_destination.suffix == ".m4a"


def test_a_new_subtitle_language_extracts_again_and_redoes_everything_after_it() -> None:
    saved, done = _accepted(_BEFORE_MIX)

    rebased, kept = rebase_plan(
        saved, done, _fresh(saved, replace(_settings(), subtitle_language_priority=("fra", "eng")))
    )

    kinds: frozenset[TaskKind] = frozenset(task.kind for task in rebased.tasks)
    assert {TaskKind.EXTRACT_TRACKS, TaskKind.SYNTHESIZE_SPEECH, TaskKind.MIX_NARRATION} <= kinds
    assert kept == ()


def test_a_step_whose_input_is_made_again_is_made_again_too() -> None:
    saved, done = _accepted(frozenset({TaskKind.EXTRACT_TRACKS, TaskKind.TRANSLATE_SUBTITLES}))
    extract: PlanTask = next(task for task in done if task.kind is TaskKind.EXTRACT_TRACKS)

    rebased, kept = rebase_plan(saved, tuple(task for task in done if task != extract), _fresh(saved, _settings()))

    kinds: frozenset[TaskKind] = frozenset(task.kind for task in rebased.tasks)
    assert {TaskKind.EXTRACT_TRACKS, TaskKind.TRANSLATE_SUBTITLES} <= kinds
    assert kept == ()
