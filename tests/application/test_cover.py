from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
from fakes import write_image_source

from anishift.application.artifacts import COVER_AUDIO_KINDS, Artifact, ArtifactKind, ArtifactLifetime
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.composition_handler import CompositionTaskHandler
from anishift.application.discovery import discover_groups
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import AutoPreset, GroupIntent, ProductIntent, ProductKind, RunMode
from anishift.application.planner import plan_auto, plan_manual
from anishift.application.planning import ExecutionPlan, PlanTask, ProcessingOrderPolicy, RunSettingsSnapshot, TaskKind
from anishift.application.results import RunResult
from anishift.application.runtime import ProductionHandlerFactory
from anishift.application.scheduler import GraphScheduler
from anishift.application.scheduler_contracts import ResourceLimits
from anishift.application.selection import GroupReadiness, ReadinessReason, legal_products, resolve_readiness
from anishift.application.sessions import RunSession
from anishift.application.tts_handler import TtsProgressObserver, TtsTaskHandler
from anishift.application.watch import _PRODUCT_ARTIFACTS
from anishift.application.workflows import WorkflowTarget
from anishift.config.settings import Settings
from anishift.services.composition import (
    CompositionProgressSink,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    CoverCompositionRequest,
    CoverCompositionResult,
)
from anishift.services.extraction import ExtractionRequest, ExtractionResult
from anishift.services.media._process import ProcessResult
from anishift.services.media.types import ContainerKind, MediaCatalog
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.translation import FileTranslation
from anishift.services.tts import SpeechBatch, SpeechBatchResult

_AUDIO_DURATION_US: int = 5_000_000


class _FakeProbe:
    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        return MediaCatalog(path=path, container=ContainerKind.MKV, duration_us=_AUDIO_DURATION_US, tracks=())


class _FakeRunner:
    def run(self, command: tuple[str, ...], *, cancel: CancellationToken, timeout_s: float) -> ProcessResult:
        del command, cancel, timeout_s
        return ProcessResult(f"out_time_us={_AUDIO_DURATION_US}\nprogress=end\n", "", 0)


class _CountingVoice:
    def __init__(self) -> None:
        self.calls: int = 0

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        del batch, callbacks
        self.calls += 1
        raise AssertionError

    def cancel(self) -> None:
        raise AssertionError

    def close(self) -> None:
        pass


class _CountingTranslator:
    def __init__(self) -> None:
        self.calls: int = 0

    def translate_file(  # noqa: PLR0913 - the fake mirrors the domain facade it stands in for
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: object = None,
        observer: object = None,
    ) -> FileTranslation:
        del spoken, displayed, source_lang, target_lang, cancel, observer
        self.calls += 1
        raise AssertionError


class _RefusingExtraction:
    def extract(self, request: ExtractionRequest, *, cancel: CancellationToken, timeout_s: float) -> ExtractionResult:
        del request, cancel, timeout_s
        raise AssertionError


class _RecordingComposer:
    def __init__(self) -> None:
        self.requests: list[CoverCompositionRequest] = []

    def compose_cover(
        self,
        request: CoverCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CoverCompositionResult:
        del callbacks, cancel
        self.requests.append(request)
        request.destination.write_bytes(b"cover")
        return CoverCompositionResult(
            request.still_image,
            request.audio,
            request.destination,
            request.destination.stat().st_size,
            _AUDIO_DURATION_US,
            1.0,
        )

    def compose_container(
        self,
        request: ContainerCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> ContainerCompositionResult:
        del request, callbacks, cancel
        raise AssertionError


class _CollectingEvents:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def _settings(profile: str = "eac3") -> RunSettingsSnapshot:
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
        audio_output_profile=profile,
    )


def _preset() -> AutoPreset:
    return AutoPreset("video", "Video", ProductIntent(frozenset({ProductKind.MKV})))


def _write_text(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Zażółć gęślą jaźń.\n", encoding="utf-8")


def _write_srt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n00:00:00,000 --> 00:00:02,000\nDzień dobry\n", encoding="utf-8")


def _write_audio(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio bytes")


def _groups(root: Path) -> tuple[InspectedSourceGroup, ...]:
    return (
        WorkspaceInspector(_FakeProbe(), runner=_FakeRunner())
        .inspect(discover_groups(root), cancel=NeverCancelledToken())
        .groups
    )


def _only(root: Path) -> InspectedSourceGroup:
    groups: tuple[InspectedSourceGroup, ...] = _groups(root)
    assert len(groups) == 1
    return groups[0]


def _auto(root: Path, published: frozenset[Path] | None = None, profile: str = "eac3") -> ExecutionPlan:
    return plan_auto(_groups(root), _preset(), _settings(profile), published=published)


def _either_mode(root: Path, mode: RunMode, profile: str) -> ExecutionPlan:
    if mode is RunMode.AUTO:
        return _auto(root, profile=profile)
    group: InspectedSourceGroup = _only(root)
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
    )
    return plan_manual((group,), {group.group_id: intent}, _settings(profile))


def _published(root: Path) -> frozenset[Path]:
    return frozenset({root / "cover" / "Book.eac3"})


def _kinds(plan: ExecutionPlan) -> tuple[TaskKind, ...]:
    return tuple(task.kind for task in plan.tasks)


def _codes(plan: ExecutionPlan) -> tuple[str, ...]:
    return tuple(problem.code for problem in plan.problems)


@dataclass(frozen=True, slots=True)
class _Executed:
    result: RunResult
    composer: _RecordingComposer
    voice: _CountingVoice
    words: _CountingTranslator


def _execute(plan: ExecutionPlan, groups: tuple[InspectedSourceGroup, ...], run_root: Path) -> _Executed:
    voice: _CountingVoice = _CountingVoice()
    words: _CountingTranslator = _CountingTranslator()
    composer: _RecordingComposer = _RecordingComposer()
    with RunSession(run_root) as session:
        result: RunResult = GraphScheduler(
            ExecutionHandlers(
                ExtractionTaskHandler(_RefusingExtraction(), run_root=run_root, timeout_s=30.0),
                SubtitleTaskHandler(run_root=run_root),
                TranslationTaskHandler(words, run_root=run_root),
                tts=TtsTaskHandler(voice, run_root=run_root, group_ranks={groups[0].group_id: 0}),
                composition=CompositionTaskHandler(composer, run_root=run_root),
                publish=PublishTaskHandler(
                    run_root=run_root,
                    source_groups={group.group_id: group.source for group in groups},
                ),
            ),
            limits=ResourceLimits.from_settings(plan.settings),
            run_id=run_root.name,
            session=session,
        ).run(plan, cancel=NeverCancelledToken(), events=_CollectingEvents())
    return _Executed(result, composer, voice, words)


def _products(result: RunResult) -> list[str]:
    return [product.path.name for group in result.groups for product in group.products]


def _plays(plan: ExecutionPlan, task: PlanTask) -> str | None:
    audio: Artifact = next(
        artifact
        for artifact in plan.artifacts
        if artifact.artifact_id in task.requires and artifact.kind in COVER_AUDIO_KINDS
    )
    return audio.path.name if audio.path is not None else None


def _durable(plan: ExecutionPlan) -> tuple[str, ...]:
    produced: set[str] = {artifact_id for task in plan.tasks for artifact_id in task.produces}
    return tuple(
        sorted(
            artifact.planned_destination.name
            for artifact in plan.artifacts
            if artifact.artifact_id in produced
            and artifact.lifetime is ArtifactLifetime.DURABLE
            and artifact.planned_destination is not None
        )
    )


def test_the_production_factory_really_builds_a_handler_for_a_cover_only_plan(tmp_path: Path) -> None:
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")
    plan: ExecutionPlan = _auto(tmp_path)
    factory: ProductionHandlerFactory = ProductionHandlerFactory(lambda: Settings(_env_file=None))

    handlers: ExecutionHandlers = factory(tmp_path / "run", plan, {})

    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert handlers.composition is not None


def test_every_public_product_names_the_artifact_that_proves_it_exists() -> None:
    assert set(_PRODUCT_ARTIFACTS) == set(ProductKind)


@pytest.mark.parametrize("content_first", [True, False])
def test_a_cover_becomes_one_film_only_once_both_of_its_halves_arrived(tmp_path: Path, *, content_first: bool) -> None:
    cover: Path = tmp_path / "cover"
    if content_first:
        _write_text(cover / "Book.txt")
        assert resolve_readiness(_only(tmp_path)).reason is ReadinessReason.IMAGE_MISSING
        write_image_source(cover / "Book.png")
    else:
        write_image_source(cover / "Book.png")
        assert resolve_readiness(_only(tmp_path)).reason is ReadinessReason.CONTENT_SOURCE_MISSING
        _write_text(cover / "Book.txt")

    plan: ExecutionPlan = _auto(tmp_path)

    assert resolve_readiness(_only(tmp_path)) == GroupReadiness(ready=True)
    assert plan.can_execute
    assert _kinds(plan) == (
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.PUBLISH_ARTIFACT,
        TaskKind.COMPOSE_COVER,
    )
    assert _durable(plan) == ("Book.cover.mp4", "Book.eac3")


def test_replacing_only_the_picture_of_a_finished_cover_neither_translates_nor_synthesises(tmp_path: Path) -> None:
    cover: Path = tmp_path / "cover"
    _write_text(cover / "Book.txt")
    write_image_source(cover / "Book.png")
    assert _durable(_auto(tmp_path)) == ("Book.cover.mp4", "Book.eac3")
    _write_audio(cover / "Book.eac3")
    (cover / "Book.cover.mp4").write_bytes(b"previous film")
    write_image_source(cover / "Book.png", width=640, height=480)

    plan: ExecutionPlan = _auto(tmp_path, _published(tmp_path))
    renamed_profile: ExecutionPlan = _auto(tmp_path, _published(tmp_path), profile="mp3")

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)
    assert TaskKind.MIX_NARRATION not in _kinds(plan)
    assert renamed_profile.can_execute
    assert _kinds(renamed_profile) == (TaskKind.COMPOSE_COVER,)


@pytest.mark.parametrize("recording", ["Book.mp3", "Book.eac3", "Book.m4a"])
def test_a_cover_given_finished_audio_never_synthesises_a_second_voice(tmp_path: Path, recording: str) -> None:
    _write_audio(tmp_path / "cover" / recording)
    write_image_source(tmp_path / "cover" / "Book.jpg")

    plan: ExecutionPlan = _auto(tmp_path)

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert _durable(plan) == ("Book.cover.mp4",)


def test_executing_a_cover_from_finished_audio_calls_no_voice_and_no_translator(tmp_path: Path) -> None:
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    plan: ExecutionPlan = plan_auto(groups, _preset(), _settings())

    executed: _Executed = _execute(plan, groups, tmp_path / "temp" / "run-cover")

    assert executed.result.succeeded
    assert executed.voice.calls == 0
    assert executed.words.calls == 0
    assert len(executed.composer.requests) == 1
    assert _products(executed.result) == ["Book.cover.mp4"]


def test_a_cover_reading_a_subtitle_document_keeps_using_the_audiobook_voice(tmp_path: Path) -> None:
    _write_srt(tmp_path / "cover" / "Book.srt")
    write_image_source(tmp_path / "cover" / "Book.png")

    plan: ExecutionPlan = _auto(tmp_path)

    assert plan.can_execute
    assert TaskKind.SYNTHESIZE_SPEECH in _kinds(plan)
    assert _kinds(plan)[-1] is TaskKind.COMPOSE_COVER


def test_the_cover_task_carries_the_picture_and_the_recording_it_was_planned_for(tmp_path: Path) -> None:
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")

    plan: ExecutionPlan = _auto(tmp_path)
    compose: PlanTask = next(task for task in plan.tasks if task.kind is TaskKind.COMPOSE_COVER)
    inputs: set[ArtifactKind] = {
        artifact.kind for artifact in plan.artifacts if artifact.artifact_id in compose.requires
    }

    assert compose.parameters == ()
    assert inputs == {ArtifactKind.SOURCE_IMAGE, ArtifactKind.SOURCE_AUDIO}


def test_two_competing_pictures_refuse_to_be_guessed_between(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    write_image_source(tmp_path / "cover" / "Book.png")
    write_image_source(tmp_path / "cover" / "Book.jpeg")

    plan: ExecutionPlan = _auto(tmp_path)

    assert not plan.can_execute
    assert "cover_image_ambiguous" in _codes(plan)


def test_choosing_one_of_two_competing_pictures_lets_the_refused_cover_proceed(tmp_path: Path) -> None:
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")
    write_image_source(tmp_path / "cover" / "Book.jpeg")
    group: InspectedSourceGroup = _only(tmp_path)
    images: list[Artifact] = sorted(
        (artifact for artifact in group.artifacts if artifact.kind is ArtifactKind.SOURCE_IMAGE),
        key=lambda artifact: artifact.artifact_id,
    )
    assert len(images) == 2
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
        selected_image_artifact_id=images[1].artifact_id,
    )

    plan: ExecutionPlan = plan_manual((group,), {group.group_id: intent}, _settings())

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert images[1].artifact_id in plan.tasks[0].requires
    assert images[0].artifact_id not in plan.tasks[0].requires


@pytest.mark.parametrize("mode", [RunMode.AUTO, RunMode.MANUAL])
@pytest.mark.parametrize("recording", ["Book.mp3", "Book.eac3"])
@pytest.mark.parametrize("profile", ["eac3", "mp3"])
def test_a_text_beside_an_independent_recording_is_never_guessed_between(
    tmp_path: Path,
    recording: str,
    profile: str,
    mode: RunMode,
) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_audio(tmp_path / "cover" / recording)
    write_image_source(tmp_path / "cover" / "Book.png")

    plan: ExecutionPlan = _either_mode(tmp_path, mode, profile)

    assert plan.groups[0].intent.mode is mode
    assert not plan.can_execute
    assert "cover_source_ambiguous" in _codes(plan)
    assert _kinds(plan) == ()


def test_choosing_the_recording_settles_the_conflict_a_guess_was_refused_for(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")
    group: InspectedSourceGroup = _only(tmp_path)
    recording: Artifact = next(artifact for artifact in group.artifacts if artifact.kind is ArtifactKind.SOURCE_AUDIO)
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
        selected_audio_artifact_id=recording.artifact_id,
    )

    plan: ExecutionPlan = plan_manual((group,), {group.group_id: intent}, _settings())

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert recording.artifact_id in plan.tasks[0].requires
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)


def test_a_cover_whose_text_was_deleted_still_composes_its_film_from_the_recording_it_published(
    tmp_path: Path,
) -> None:
    cover: Path = tmp_path / "cover"
    write_image_source(cover / "Book.png")
    _write_audio(cover / "Book.eac3")

    plan: ExecutionPlan = _auto(tmp_path, _published(tmp_path))
    compose: PlanTask = next(task for task in plan.tasks if task.kind is TaskKind.COMPOSE_COVER)

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert "cover_source_missing" not in _codes(plan)
    assert _plays(plan, compose) == "Book.eac3"
    assert _durable(plan) == ("Book.cover.mp4",)


def test_executing_a_cover_from_the_recording_it_published_really_writes_the_film(tmp_path: Path) -> None:
    cover: Path = tmp_path / "cover"
    write_image_source(cover / "Book.png")
    _write_audio(cover / "Book.eac3")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    plan: ExecutionPlan = plan_auto(groups, _preset(), _settings(), published=_published(tmp_path))

    executed: _Executed = _execute(plan, groups, tmp_path / "temp" / "run-own")

    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert executed.result.succeeded
    assert executed.composer.requests[0].audio == cover / "Book.eac3"
    assert executed.voice.calls == 0
    assert _products(executed.result) == ["Book.cover.mp4"]


def test_executing_a_cover_in_ready_whose_recording_a_person_overwrote_uses_their_bytes(tmp_path: Path) -> None:
    ready: Path = tmp_path / "ready"
    write_image_source(ready / "Book.png")
    (ready / "Book.cover.mp4").write_bytes(b"previous film")
    _write_audio(ready / "Book.eac3")
    group: InspectedSourceGroup = _only(tmp_path)
    plan: ExecutionPlan = _regenerated(group)

    executed: _Executed = _execute(plan, (group,), tmp_path / "temp" / "run-ready")

    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert executed.result.succeeded
    assert executed.composer.requests[0].audio == ready / "Book.eac3"
    assert executed.voice.calls == 0
    assert _products(executed.result) == ["Book.cover.mp4"]


def test_a_manual_cover_whose_text_was_deleted_also_composes_from_the_recording_it_published(
    tmp_path: Path,
) -> None:
    cover: Path = tmp_path / "cover"
    write_image_source(cover / "Book.png")
    _write_audio(cover / "Book.eac3")
    group: InspectedSourceGroup = _only(tmp_path)
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
    )

    plan: ExecutionPlan = plan_manual((group,), {group.group_id: intent}, _settings(), published=_published(tmp_path))
    delivered: ExecutionPlan = plan_manual((group,), {group.group_id: intent}, _settings())
    compose: PlanTask = next(task for task in plan.tasks if task.kind is TaskKind.COMPOSE_COVER)

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert "cover_source_missing" not in _codes(plan)
    assert _plays(plan, compose) == "Book.eac3"
    assert _durable(plan) == ("Book.cover.mp4",)
    assert _plays(delivered, delivered.tasks[0]) == "Book.eac3"


def test_one_unrenamed_recording_is_this_programs_product_only_while_a_record_proves_it(tmp_path: Path) -> None:
    cover: Path = tmp_path / "cover"
    _write_text(cover / "Book.txt")
    write_image_source(cover / "Book.png")
    _write_audio(cover / "Book.eac3")

    recorded: ExecutionPlan = _auto(tmp_path, _published(tmp_path))
    delivered: ExecutionPlan = _auto(tmp_path)

    assert recorded.can_execute
    assert "cover_source_ambiguous" not in _codes(recorded)
    assert _kinds(recorded) == (TaskKind.COMPOSE_COVER,)
    assert not delivered.can_execute
    assert "cover_source_ambiguous" in _codes(delivered)
    assert _kinds(delivered) == ()


def test_two_competing_documents_are_never_picked_between_without_being_asked(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_srt(tmp_path / "cover" / "Book.srt")
    write_image_source(tmp_path / "cover" / "Book.png")

    plan: ExecutionPlan = _auto(tmp_path)

    assert not plan.can_execute
    assert "cover_source_ambiguous" in _codes(plan)


def test_choosing_the_text_makes_a_cover_read_it_aloud_beside_an_existing_recording(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    _write_audio(tmp_path / "cover" / "Book.mp3")
    write_image_source(tmp_path / "cover" / "Book.png")
    group: InspectedSourceGroup = _only(tmp_path)
    document: Artifact = next(artifact for artifact in group.artifacts if artifact.kind is ArtifactKind.STANDALONE_TEXT)
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
        selected_subtitle_artifact_id=document.artifact_id,
    )

    plan: ExecutionPlan = plan_manual((group,), {group.group_id: intent}, _settings())

    assert plan.can_execute
    assert TaskKind.SYNTHESIZE_SPEECH in _kinds(plan)


def test_a_broken_picture_stops_the_cover_before_any_voice_is_paid_for(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    (tmp_path / "cover" / "Book.png").write_bytes(b"not a picture at all")

    plan: ExecutionPlan = _auto(tmp_path)

    assert not plan.can_execute
    assert "cover_image_missing" in _codes(plan)
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)


def test_a_cover_place_is_only_ever_offered_the_film_it_can_really_write(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    write_image_source(tmp_path / "cover" / "Book.png")

    assert legal_products(_only(tmp_path)) == frozenset({ProductKind.COVER_MP4})


def test_a_cover_never_writes_the_polish_subtitles_a_plain_text_place_would(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    write_image_source(tmp_path / "cover" / "Book.png")

    plan: ExecutionPlan = _auto(tmp_path)

    assert _durable(plan) == ("Book.cover.mp4", "Book.eac3")
    assert plan.groups[0].intent.products.requested_products == frozenset({ProductKind.COVER_MP4})
    assert not any(name.endswith(".pl.srt") for name in _durable(plan))


def _ready_cover(root: Path, *, with_audio: bool) -> InspectedSourceGroup:
    ready: Path = root / "ready"
    write_image_source(ready / "Book.png")
    (ready / "Book.cover.mp4").write_bytes(b"previous film")
    if with_audio:
        _write_audio(ready / "Book.mp3")
    else:
        _write_text(ready / "Book.txt")
    return _only(root)


def _regenerated(group: InspectedSourceGroup) -> ExecutionPlan:
    intent: GroupIntent = GroupIntent(
        group_id=group.group_id,
        mode=RunMode.MANUAL,
        products=ProductIntent(frozenset({ProductKind.COVER_MP4})),
        target=WorkflowTarget.COVER,
    )
    return plan_manual((group,), {group.group_id: intent}, _settings())


def test_a_finished_cover_waiting_in_ready_never_starts_work_by_itself(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _ready_cover(tmp_path, with_audio=True)

    assert group.source.route.target is None
    assert group.source.route.starts_automatic_work is False
    assert resolve_readiness(group) == GroupReadiness(ready=False, reason=ReadinessReason.PLACE_STARTS_NO_WORK)


def test_regenerating_a_cover_in_ready_recovers_its_target_instead_of_reading_the_folder(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _ready_cover(tmp_path, with_audio=True)

    plan: ExecutionPlan = _regenerated(group)

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.COMPOSE_COVER,)
    assert _durable(plan) == ("Book.cover.mp4",)
    assert legal_products(group, WorkflowTarget.COVER) == frozenset({ProductKind.COVER_MP4})


def test_fixing_only_the_picture_of_a_cover_neither_translates_nor_synthesises_again(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _ready_cover(tmp_path, with_audio=True)

    plan: ExecutionPlan = _regenerated(group)

    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)
    assert TaskKind.MIX_NARRATION not in _kinds(plan)


def test_a_cover_whose_recording_does_not_exist_shows_the_work_it_really_needs(tmp_path: Path) -> None:
    group: InspectedSourceGroup = _ready_cover(tmp_path, with_audio=False)

    plan: ExecutionPlan = _regenerated(group)

    assert plan.can_execute
    assert _kinds(plan) == (
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.PUBLISH_ARTIFACT,
        TaskKind.COMPOSE_COVER,
    )


def test_two_covers_of_the_same_name_from_different_places_stay_two_groups(tmp_path: Path) -> None:
    _write_text(tmp_path / "cover" / "Book.txt")
    write_image_source(tmp_path / "cover" / "Book.png")
    _write_text(tmp_path / "cover" / "second" / "Book.txt")
    write_image_source(tmp_path / "cover" / "second" / "Book.png")

    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    plan: ExecutionPlan = plan_auto(groups, _preset(), _settings())

    assert len({group.group_id for group in groups}) == 2
    assert _kinds(plan).count(TaskKind.COMPOSE_COVER) == 2
    assert {
        artifact.planned_destination.parent.name
        for artifact in plan.artifacts
        if artifact.lifetime is ArtifactLifetime.DURABLE and artifact.planned_destination is not None
    } == {"cover", "second"}
