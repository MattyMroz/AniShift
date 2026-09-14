from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.control import AudiobookRecipe, RecipePreferences
from anishift.application.control_payloads import decode_intent, encode_intent
from anishift.application.discovery import discover_groups
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace, WorkspaceInspector
from anishift.application.intents import (
    AutoPreset,
    GroupIntent,
    NarrationTimeline,
    ProductIntent,
    ProductKind,
    RunMode,
    TranslationAction,
)
from anishift.application.planner import plan_auto, plan_manual
from anishift.application.planning import ExecutionPlan, PlanTask, ProcessingOrderPolicy, RunSettingsSnapshot, TaskKind
from anishift.application.selection import legal_narration_timelines, legal_products, ready_group_ids
from anishift.application.workflows import WorkflowTarget
from anishift.services.media._process import ProcessResult
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


class _FakeProbe:
    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        return MediaCatalog(
            path=path,
            container=ContainerKind.MKV,
            duration_us=1_000_000,
            tracks=(
                MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
                MediaTrack(1, MediaTrackKind.SUBTITLES, "text", "eng", None, False, False, "srt"),
            ),
        )


class _FakeRunner:
    def run(self, *args: object, **kwargs: object) -> ProcessResult:
        del args, kwargs
        return ProcessResult(returncode=0, stdout="", stderr="")


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
    )


def _write_srt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nGood morning\n\n2\n00:00:30,000 --> 00:00:32,000\nGood night\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str = "Good morning. Good night.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _groups(root: Path) -> tuple[InspectedSourceGroup, ...]:
    workspace: InspectedWorkspace = WorkspaceInspector(_FakeProbe(), runner=_FakeRunner()).inspect(
        discover_groups(root),
        cancel=NeverCancelledToken(),
    )
    return workspace.groups


def _ready(root: Path) -> tuple[InspectedSourceGroup, ...]:
    groups: tuple[InspectedSourceGroup, ...] = _groups(root)
    admitted: set[str] = set(ready_group_ids(groups))
    return tuple(group for group in groups if group.group_id in admitted)


def _preset(*products: ProductKind) -> AutoPreset:
    chosen: tuple[ProductKind, ...] = products or (ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO, ProductKind.MKV)
    return AutoPreset("video", "Video", ProductIntent(frozenset(chosen)))


def _plan(root: Path, recipes: RecipePreferences | None = None) -> ExecutionPlan:
    return plan_auto(_ready(root), _preset(), _settings(), recipes=recipes)


def _recipes(
    timeline: NarrationTimeline = NarrationTimeline.CONTINUOUS,
    action: TranslationAction = TranslationAction.AUTO,
) -> RecipePreferences:
    return RecipePreferences(audiobook=AudiobookRecipe(translation_action=action, timeline=timeline))


def _kinds(plan: ExecutionPlan) -> tuple[TaskKind, ...]:
    return tuple(task.kind for task in plan.tasks)


def _codes(plan: ExecutionPlan) -> tuple[str, ...]:
    return tuple(problem.code for problem in plan.problems)


def _task(plan: ExecutionPlan, kind: TaskKind) -> PlanTask:
    return next(task for task in plan.tasks if task.kind is kind)


def _destinations(plan: ExecutionPlan) -> tuple[str, ...]:
    return tuple(
        artifact.planned_destination.name
        for artifact in plan.artifacts
        if artifact.lifetime is ArtifactLifetime.DURABLE and artifact.planned_destination is not None
    )


def test_a_subtitle_in_the_audiobook_place_is_translated_then_read_then_mixed(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())

    assert plan.can_execute
    assert _kinds(plan) == (
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.PUBLISH_ARTIFACT,
    )


def test_the_audiobook_mix_reads_the_manifest_alone_and_never_waits_for_source_audio(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())
    mix: PlanTask = _task(plan, TaskKind.MIX_NARRATION)
    inputs: set[ArtifactKind] = {artifact.kind for artifact in plan.artifacts if artifact.artifact_id in mix.requires}

    assert dict(mix.parameters)["mix_source"] == "standalone"
    assert inputs == {ArtifactKind.TTS_MANIFEST}


def test_an_audiobook_writes_only_the_recording_and_no_video_container(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())

    assert sorted(_destinations(plan)) == ["book.eac3"]


def test_the_only_published_product_of_an_audiobook_is_the_recording_the_mix_made(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())
    mix: PlanTask = _task(plan, TaskKind.MIX_NARRATION)
    produced: set[ArtifactKind] = {
        next(artifact for artifact in plan.artifacts if artifact.artifact_id == artifact_id).kind
        for artifact_id in mix.produces
    }
    published: tuple[PlanTask, ...] = tuple(task for task in plan.tasks if task.kind is TaskKind.PUBLISH_ARTIFACT)

    assert produced == {ArtifactKind.NARRATION_AUDIO}
    assert len(published) == 1
    assert set(published[0].requires) == set(mix.produces)


def test_a_text_in_the_audiobook_place_never_publishes_the_draft_the_translator_made(tmp_path: Path) -> None:
    _write_text(tmp_path / "audiobook" / "book.txt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())
    translation: PlanTask = _task(plan, TaskKind.TRANSLATE_SUBTITLES)
    drafts: set[ArtifactLifetime] = {
        next(artifact for artifact in plan.artifacts if artifact.artifact_id == artifact_id).lifetime
        for artifact_id in translation.produces
    }

    assert plan.can_execute
    assert drafts == {ArtifactLifetime.INTERMEDIATE}
    assert sorted(_destinations(plan)) == ["book.eac3"]


def test_a_refused_translation_reads_the_source_and_plans_no_translation_at_all(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes(action=TranslationAction.DO_NOT_TRANSLATE))
    speech: PlanTask = _task(plan, TaskKind.SYNTHESIZE_SPEECH)
    script: Artifact = next(artifact for artifact in plan.artifacts if artifact.artifact_id == speech.requires[0])

    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert script.kind is ArtifactKind.SOURCE_SUBTITLES
    assert script.lifetime is ArtifactLifetime.SOURCE


def test_a_refused_translation_of_a_text_cannot_keep_times_that_do_not_exist(tmp_path: Path) -> None:
    _write_text(tmp_path / "audiobook" / "book.txt")

    plan: ExecutionPlan = _plan(
        tmp_path,
        _recipes(timeline=NarrationTimeline.SOURCE_TIMES, action=TranslationAction.DO_NOT_TRANSLATE),
    )

    assert not plan.can_execute
    assert "narration_times_unavailable" in _codes(plan)


def test_an_audiobook_place_never_inherits_the_container_products_of_the_video_preset(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes())
    requested: frozenset[ProductKind] = plan.groups[0].intent.products.requested_products

    assert requested == frozenset({ProductKind.NARRATION_AUDIO})


def test_a_manual_audiobook_asking_for_a_film_is_refused_with_its_own_reason(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")
    groups: tuple[InspectedSourceGroup, ...] = _ready(tmp_path)
    intent: GroupIntent = GroupIntent(
        group_id=groups[0].group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.MKV})),
    )

    plan: ExecutionPlan = plan_manual(groups, {groups[0].group_id: intent}, _settings())

    assert not plan.can_execute
    assert "audiobook_products_unsupported" in _codes(plan)


def test_the_two_readings_of_one_book_never_share_a_task_or_an_artifact(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    continuous: ExecutionPlan = _plan(tmp_path, _recipes(NarrationTimeline.CONTINUOUS))
    source_times: ExecutionPlan = _plan(tmp_path, _recipes(NarrationTimeline.SOURCE_TIMES))
    voice_tasks: set[TaskKind] = {TaskKind.SYNTHESIZE_SPEECH, TaskKind.MIX_NARRATION}
    continuous_ids: set[str] = {task.task_id for task in continuous.tasks if task.kind in voice_tasks}
    source_ids: set[str] = {task.task_id for task in source_times.tasks if task.kind in voice_tasks}
    continuous_manifest: set[str] = {
        artifact.artifact_id for artifact in continuous.artifacts if artifact.kind is ArtifactKind.TTS_MANIFEST
    }
    source_manifest: set[str] = {
        artifact.artifact_id for artifact in source_times.artifacts if artifact.kind is ArtifactKind.TTS_MANIFEST
    }

    assert continuous_ids.isdisjoint(source_ids)
    assert continuous_manifest.isdisjoint(source_manifest)


def test_the_reading_a_run_was_accepted_with_survives_being_stored(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")
    plan: ExecutionPlan = _plan(tmp_path, _recipes(NarrationTimeline.SOURCE_TIMES))
    stored: GroupIntent = plan.groups[0].intent

    restored: GroupIntent = decode_intent(GroupIntent, encode_intent(stored))

    assert restored.narration_timeline is NarrationTimeline.SOURCE_TIMES
    assert restored == stored


def test_an_intent_stored_before_readings_existed_still_loads_as_the_continuous_one() -> None:
    payload: dict[str, object] = {
        "group_id": "group-1",
        "mode": "auto",
        "products": {"requested_products": ["narration_audio"]},
    }

    restored: GroupIntent = decode_intent(GroupIntent, payload)

    assert restored.narration_timeline is NarrationTimeline.CONTINUOUS


def test_the_speech_task_carries_the_reading_and_the_document_it_was_planned_for(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    plan: ExecutionPlan = _plan(tmp_path, _recipes(NarrationTimeline.SOURCE_TIMES, TranslationAction.TRANSLATE))
    speech: PlanTask = _task(plan, TaskKind.SYNTHESIZE_SPEECH)

    assert dict(speech.parameters) == {"narration_timeline": "source_times", "script_kind": "full_pl"}


@pytest.mark.parametrize(
    ("place", "name", "expected"),
    [
        ("audiobook", "book.srt", frozenset({ProductKind.NARRATION_AUDIO})),
        ("translate", "doc.srt", frozenset({ProductKind.FULL_PL, ProductKind.TRANSLATED_TEXT})),
        (".", "story.txt", frozenset({ProductKind.FULL_PL})),
    ],
)
def test_a_place_offers_only_the_products_it_can_really_write(
    tmp_path: Path,
    place: str,
    name: str,
    expected: frozenset[ProductKind],
) -> None:
    if name.endswith(".txt"):
        _write_text(tmp_path / place / name)
    else:
        _write_srt(tmp_path / place / name)

    group: InspectedSourceGroup = _groups(tmp_path)[0]

    assert legal_products(group) == expected


def test_a_group_whose_only_film_failed_validation_is_never_offered_a_film(tmp_path: Path) -> None:
    video: Artifact = Artifact(
        artifact_id="artifact-video",
        group_id="group-1",
        kind=ArtifactKind.VIDEO_MKV,
        path=tmp_path / "episode.mkv",
        state=ArtifactState.INVALID,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=tmp_path / "episode.mkv",
    )
    group: InspectedSourceGroup = InspectedSourceGroup(
        source=SourceGroup("group-1", "episode", tmp_path, (video,)),
        artifacts=(video,),
        media_catalogs={},
        conflicts=(),
    )

    offered: frozenset[ProductKind] = legal_products(group)

    assert ProductKind.MKV not in offered
    assert ProductKind.MP4 not in offered
    assert ProductKind.NARRATION_AUDIO in offered


def test_the_place_a_run_was_accepted_for_survives_being_stored(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")
    plan: ExecutionPlan = _plan(tmp_path, _recipes())
    stored: GroupIntent = plan.groups[0].intent

    restored: GroupIntent = decode_intent(GroupIntent, encode_intent(stored))

    assert restored.target is WorkflowTarget.AUDIOBOOK
    assert restored == stored


def test_an_intent_stored_before_places_were_recorded_still_loads_without_one() -> None:
    payload: dict[str, object] = {
        "group_id": "group-1",
        "mode": "auto",
        "products": {"requested_products": ["narration_audio"]},
    }

    restored: GroupIntent = decode_intent(GroupIntent, payload)

    assert restored.target is None


def test_work_accepted_for_another_place_than_its_files_sit_in_now_is_refused(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")
    groups: tuple[InspectedSourceGroup, ...] = _ready(tmp_path)
    intent: GroupIntent = GroupIntent(
        group_id=groups[0].group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.NARRATION_AUDIO})),
        target=WorkflowTarget.TRANSLATE,
    )

    plan: ExecutionPlan = plan_manual(groups, {groups[0].group_id: intent}, _settings())

    assert not plan.can_execute
    assert "intent_target_changed" in _codes(plan)


def test_a_text_is_only_ever_offered_the_reading_it_can_really_be_given(tmp_path: Path) -> None:
    _write_text(tmp_path / "audiobook" / "book.txt")

    group: InspectedSourceGroup = _groups(tmp_path)[0]

    assert legal_narration_timelines(group) == frozenset({NarrationTimeline.CONTINUOUS})


def test_a_document_with_real_times_keeps_both_readings(tmp_path: Path) -> None:
    _write_srt(tmp_path / "audiobook" / "book.srt")

    group: InspectedSourceGroup = _groups(tmp_path)[0]

    assert legal_narration_timelines(group) == frozenset(NarrationTimeline)


def test_a_translated_text_cannot_keep_times_its_translation_only_invented(tmp_path: Path) -> None:
    _write_text(tmp_path / "audiobook" / "book.txt")

    plan: ExecutionPlan = _plan(
        tmp_path,
        _recipes(timeline=NarrationTimeline.SOURCE_TIMES, action=TranslationAction.TRANSLATE),
    )

    assert not plan.can_execute
    assert "narration_times_unavailable" in _codes(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
