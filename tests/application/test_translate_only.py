from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
)
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.control import RecipePreferences, TextResultFormat, TranslateRecipe
from anishift.application.discovery import discover_groups
from anishift.application.events import RunEvent, WorkerNotification
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    PublishTaskHandler,
    SubtitleTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import (
    VIDEO_PRODUCTS,
    AutoPreset,
    GroupIntent,
    ProductIntent,
    ProductKind,
    RunMode,
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
from anishift.application.results import ArtifactSnapshot, GroupStatus, RunResult, TaskResult
from anishift.application.scheduler import GraphScheduler, ResourceLimits
from anishift.application.selection import ready_group_ids
from anishift.application.sessions import RunSession
from anishift.application.translation_handler import (
    TextDocument,
    TextFragment,
    TranslationExecutor,
    TranslationTaskHandler,
    read_text_document,
    write_text_document,
)
from anishift.application.tts_handler import TtsProgressObserver, TtsTaskHandler
from anishift.errors import ExecutionError
from anishift.services.extraction import ExtractionRequest, ExtractionResult
from anishift.services.media._process import ProcessResult
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.translation.layout_config import LayoutConfig
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SynthesisStatus,
    SynthesizedRequest,
)

_VOICE_TASKS: frozenset[TaskKind] = frozenset(
    {
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.TRANSCODE_AUDIO,
        TaskKind.EXTRACT_AUDIO,
        TaskKind.COMPOSE_MKV,
        TaskKind.COMPOSE_MP4,
    },
)


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
    def run(self, command: tuple[str, ...], *, cancel: CancellationToken, timeout_s: float) -> ProcessResult:
        del command, cancel, timeout_s
        return ProcessResult("out_time_us=1000\nprogress=end\n", "", 0)


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
        subtitle_language_priority=("pol", "eng"),
        audio_language_priority=("jpn",),
    )


def _preset(*products: ProductKind) -> AutoPreset:
    return AutoPreset("translate", "Translate", ProductIntent(frozenset(products)))


def _write_srt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nDzień dobry\n", encoding="utf-8")


def _write_ass(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name\n"
        "Style: Default\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\\i1}Zażółć{\\i0} gęślą jaźń\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\p1}m 0 0 l 10 0 10 10{\\p0}\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str = "Zażółć gęślą jaźń.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _groups(root: Path) -> tuple[InspectedSourceGroup, ...]:
    discovery = discover_groups(root)
    workspace = WorkspaceInspector(_FakeProbe(), runner=_FakeRunner()).inspect(
        discovery,
        cancel=NeverCancelledToken(),
    )
    return workspace.groups


def _ready(root: Path) -> tuple[InspectedSourceGroup, ...]:
    groups = _groups(root)
    admitted = set(ready_group_ids(groups))
    return tuple(group for group in groups if group.group_id in admitted)


def _plan(root: Path, *products: ProductKind, recipes: RecipePreferences | None = None) -> ExecutionPlan:
    preset = _preset(*products) if products else _preset(ProductKind.FULL_PL)
    return plan_auto(_ready(root), preset, _settings(), recipes=recipes)


def _kinds(plan: ExecutionPlan) -> tuple[TaskKind, ...]:
    return tuple(task.kind for task in plan.tasks)


def _destinations(plan: ExecutionPlan) -> tuple[Path, ...]:
    return tuple(
        artifact.planned_destination
        for artifact in plan.artifacts
        if artifact.lifetime is ArtifactLifetime.DURABLE and artifact.planned_destination is not None
    )


def _codes(plan: ExecutionPlan) -> tuple[str, ...]:
    return tuple(problem.code for problem in plan.problems)


def test_a_plain_text_document_is_translated_into_a_polish_text_document(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")

    plan: ExecutionPlan = _plan(tmp_path)

    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.TRANSLATE_SUBTITLES, TaskKind.PUBLISH_ARTIFACT)
    assert _destinations(plan) == (tmp_path / "translate" / "Book.pl.txt",)


def test_a_translate_only_run_never_reaches_the_voice_or_container_services(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    _write_srt(tmp_path / "translate" / "Film.srt")
    _write_ass(tmp_path / "translate" / "Signs.ass")
    groups: tuple[InspectedSourceGroup, ...] = _ready(tmp_path)
    plan: ExecutionPlan = plan_auto(groups, _preset(*VIDEO_PRODUCTS), _settings())
    words: _PrefixTranslation = _PrefixTranslation()
    voice: _CountingTts = _CountingTts(tmp_path / "clips")

    result: RunResult = _run(plan, groups, tmp_path / "temp" / "run-translate", words, voice)

    assert plan.can_execute
    assert not _VOICE_TASKS.intersection(_kinds(plan))
    assert [group.status for group in result.groups] == [GroupStatus.SUCCEEDED] * 3
    assert words.calls == 3
    assert voice.calls == 0


def test_a_lone_subtitle_file_in_the_root_is_never_translated_or_spoken(tmp_path: Path) -> None:
    _write_srt(tmp_path / "Film.srt")
    _write_text(tmp_path / "translate" / "Book.txt")
    groups: tuple[InspectedSourceGroup, ...] = _ready(tmp_path)
    plan: ExecutionPlan = plan_auto(groups, _preset(ProductKind.FULL_PL), _settings())
    words: _PrefixTranslation = _PrefixTranslation()
    voice: _CountingTts = _CountingTts(tmp_path / "clips")

    result: RunResult = _run(plan, groups, tmp_path / "temp" / "run-root", words, voice)

    assert [group.source.stem for group in groups] == ["Book"]
    assert [group.status for group in result.groups] == [GroupStatus.SUCCEEDED]
    assert (words.calls, voice.calls) == (1, 0)
    assert (tmp_path / "translate" / "Book.pl.txt").is_file()
    assert not (tmp_path / "Film.pl.srt").exists()


def test_the_voice_boundary_counts_a_synthesis_the_same_handlers_dispatch(tmp_path: Path) -> None:
    spoken_path: Path = tmp_path / "Film.spoken.pl.srt"
    spoken_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nCześć\n", encoding="utf-8")
    spoken: Artifact = Artifact(
        "spoken",
        "group-1",
        ArtifactKind.SPOKEN_PL,
        spoken_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        spoken_path,
    )
    manifest: Artifact = Artifact(
        "manifest",
        "group-1",
        ArtifactKind.TTS_MANIFEST,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.INTERMEDIATE,
    )
    task: PlanTask = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken",),
        ("manifest",),
        (),
        "tts:edge",
        (("narration_timeline", "source_times"), ("script_kind", "spoken_pl")),
    )
    voice: _CountingTts = _CountingTts(tmp_path / "clips")
    handlers: ExecutionHandlers = _handlers(
        tmp_path / "temp" / "run-voice", _PrefixTranslation(), voice, {}, {"group-1": 0}
    )

    handlers.execute(
        task,
        ArtifactSnapshot({"spoken": spoken}, {"manifest": manifest}),
        NeverCancelledToken(),
        _ProgressSink(),
    )

    assert voice.calls == 1


def test_a_film_in_subs_waits_for_its_sidecar_before_any_task_is_planned(tmp_path: Path) -> None:
    (tmp_path / "subs").mkdir()
    (tmp_path / "subs" / "Film.mkv").write_bytes(b"video")

    plan: ExecutionPlan = _plan(tmp_path)

    assert plan.tasks == ()
    assert plan.groups == ()


def test_a_subtitle_product_beside_its_own_film_is_never_produced_again(tmp_path: Path) -> None:
    (tmp_path / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "Film.pl.srt")

    plan: ExecutionPlan = _plan(tmp_path, ProductKind.FULL_PL)

    assert [group.source.stem for group in _ready(tmp_path)] == ["Film"]
    assert len(plan.groups) == 1
    assert plan.tasks == ()


def test_a_container_product_beside_its_own_film_stays_one_group(tmp_path: Path) -> None:
    (tmp_path / "Film.mkv").write_bytes(b"video")
    (tmp_path / "Film.pl.mkv").write_bytes(b"video")

    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)

    assert [group.source.stem for group in groups] == ["Film"]
    assert {artifact.kind for artifact in groups[0].artifacts} == {
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.FINAL_MKV,
    }


def test_a_finished_set_waiting_in_ready_starts_no_work(tmp_path: Path) -> None:
    (tmp_path / "ready").mkdir()
    (tmp_path / "ready" / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "ready" / "Film.srt")
    (tmp_path / "ready" / "Film.pl.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "ready" / "Film.pl.srt")

    plan: ExecutionPlan = _plan(tmp_path, *VIDEO_PRODUCTS)

    assert _ready(tmp_path) == ()
    assert plan.groups == ()
    assert plan.tasks == ()
    kinds: set[ArtifactKind] = {artifact.kind for group in _groups(tmp_path) for artifact in group.artifacts}
    assert ArtifactKind.FINAL_MKV in kinds
    assert ArtifactKind.FULL_PL in kinds


def test_a_film_in_subs_translates_the_sidecar_even_when_the_preset_prefers_embedded(tmp_path: Path) -> None:
    (tmp_path / "subs").mkdir()
    (tmp_path / "subs" / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "subs" / "Film.srt")
    preset: AutoPreset = AutoPreset(
        "video",
        "Video",
        ProductIntent(frozenset({ProductKind.FULL_PL})),
        subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
    )

    plan: ExecutionPlan = plan_auto(_ready(tmp_path), preset, _settings())

    assert plan.can_execute
    assert TaskKind.EXTRACT_SUBTITLES not in _kinds(plan)
    assert _sources(plan, TaskKind.TRANSLATE_SUBTITLES) == (tmp_path / "subs" / "Film.srt",)


def test_a_manual_run_in_subs_cannot_waive_the_mandatory_pair(tmp_path: Path) -> None:
    (tmp_path / "subs").mkdir()
    (tmp_path / "subs" / "Film.mkv").write_bytes(b"video")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    intents: dict[str, GroupIntent] = {
        groups[0].group_id: GroupIntent(
            group_id=groups[0].group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(frozenset({ProductKind.FULL_PL})),
            subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
            selected_subtitle_track_id=1,
        )
    }

    plan: ExecutionPlan = plan_manual(groups, intents, _settings())

    assert not plan.can_execute
    assert plan.tasks == ()
    assert "sidecar_required" in _codes(plan)


def test_a_manual_run_in_subs_may_read_the_embedded_track_once_the_pair_exists(tmp_path: Path) -> None:
    (tmp_path / "subs").mkdir()
    (tmp_path / "subs" / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "subs" / "Film.srt")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    intents: dict[str, GroupIntent] = {
        groups[0].group_id: GroupIntent(
            group_id=groups[0].group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(frozenset({ProductKind.FULL_PL})),
            subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
            selected_subtitle_track_id=1,
        )
    }

    plan: ExecutionPlan = plan_manual(groups, intents, _settings())

    assert plan.can_execute
    assert _codes(plan) == ()
    assert TaskKind.EXTRACT_SUBTITLES in _kinds(plan)


def test_a_film_in_the_root_still_follows_the_embedded_policy_of_the_preset(tmp_path: Path) -> None:
    (tmp_path / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "Film.srt")
    preset: AutoPreset = AutoPreset(
        "video",
        "Video",
        ProductIntent(frozenset({ProductKind.FULL_PL})),
        subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
    )

    plan: ExecutionPlan = plan_auto(_ready(tmp_path), preset, _settings())

    assert plan.can_execute
    assert TaskKind.EXTRACT_SUBTITLES in _kinds(plan)


def _sources(plan: ExecutionPlan, kind: TaskKind) -> tuple[Path | None, ...]:
    by_id: dict[str, Artifact] = {artifact.artifact_id: artifact for artifact in plan.artifacts}
    task: PlanTask = next(item for item in plan.tasks if item.kind is kind)
    return tuple(by_id[artifact_id].path for artifact_id in task.requires)


@pytest.mark.parametrize(("name", "product"), [("Film.srt", "srt"), ("Signs.ass", "ass"), ("Signs.ssa", "ass")])
def test_a_subtitle_document_keeps_its_own_format(tmp_path: Path, name: str, product: str) -> None:
    if name.endswith(".srt"):
        _write_srt(tmp_path / "translate" / name)
    else:
        _write_ass(tmp_path / "translate" / name)

    plan: ExecutionPlan = _plan(tmp_path)

    stem: str = Path(name).stem
    assert plan.can_execute
    assert _kinds(plan) == (TaskKind.TRANSLATE_SUBTITLES, TaskKind.PUBLISH_ARTIFACT)
    assert _destinations(plan) == (tmp_path / "translate" / f"{stem}.pl.{product}",)


def test_the_subtitle_result_of_a_text_document_is_declared_a_draft(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    recipes = RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.SUBTITLES))

    plan: ExecutionPlan = _plan(tmp_path, recipes=recipes)

    assert plan.can_execute
    assert _destinations(plan) == (tmp_path / "translate" / "Book.pl.srt",)
    draft = next(problem for problem in plan.problems if problem.code == "draft_subtitle_timings")
    assert draft.is_blocking is False


def test_a_translate_group_never_inherits_the_products_of_the_video_preset(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")

    plan: ExecutionPlan = _plan(tmp_path, *VIDEO_PRODUCTS)

    assert plan.can_execute
    assert plan.groups[0].intent.products.requested_products == frozenset({ProductKind.TRANSLATED_TEXT})


def test_a_source_document_is_never_published_over_itself(tmp_path: Path) -> None:
    source: Path = tmp_path / "translate" / "Book.txt"
    _write_text(source)

    plan: ExecutionPlan = _plan(tmp_path)

    assert source not in _destinations(plan)
    publish: PlanTask = next(task for task in plan.tasks if task.kind is TaskKind.PUBLISH_ARTIFACT)
    assert len(publish.requires) == 1
    assert plan.groups[0].intent.products.requested_products == frozenset({ProductKind.TRANSLATED_TEXT})


def test_a_subtitle_source_refuses_to_become_a_plain_text_document(tmp_path: Path) -> None:
    _write_srt(tmp_path / "translate" / "Film.srt")
    groups: tuple[InspectedSourceGroup, ...] = _ready(tmp_path)
    intents = {
        groups[0].group_id: GroupIntent(
            group_id=groups[0].group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(frozenset({ProductKind.TRANSLATED_TEXT})),
        )
    }

    plan: ExecutionPlan = plan_manual(groups, intents, _settings())

    assert not plan.can_execute
    assert _codes(plan) == ("translated_text_unsupported",)


def test_only_a_translate_place_writes_a_plain_text_document(tmp_path: Path) -> None:
    (tmp_path / "Film.mkv").write_bytes(b"video")
    _write_srt(tmp_path / "Film.srt")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    intents = {
        groups[0].group_id: GroupIntent(
            group_id=groups[0].group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(frozenset({ProductKind.TRANSLATED_TEXT})),
        )
    }

    plan: ExecutionPlan = plan_manual(groups, intents, _settings())

    assert not plan.can_execute
    assert _codes(plan) == ("translated_text_unsupported",)


def test_a_translate_place_refuses_to_write_a_polish_name_without_translating(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    recipes = RecipePreferences(
        translate=TranslateRecipe(translation_action=TranslationAction.DO_NOT_TRANSLATE),
    )

    plan: ExecutionPlan = _plan(tmp_path, recipes=recipes)

    assert not plan.can_execute
    assert _codes(plan) == ("translate_translation_required",)


def test_two_independent_documents_of_one_name_are_never_picked_at_random(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    _write_srt(tmp_path / "translate" / "Book.srt")
    groups: tuple[InspectedSourceGroup, ...] = _groups(tmp_path)
    intents = {
        groups[0].group_id: GroupIntent(
            group_id=groups[0].group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(frozenset({ProductKind.FULL_PL})),
        )
    }

    plan: ExecutionPlan = plan_manual(groups, intents, _settings())

    assert not plan.can_execute
    assert "translate_source_ambiguous" in _codes(plan)


def test_a_finished_translate_group_is_not_translated_again(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt")
    _write_text(tmp_path / "translate" / "Book.pl.txt", "Polski tekst.\n")

    plan: ExecutionPlan = _plan(tmp_path)

    assert len(plan.groups) == 1
    assert plan.tasks == ()


class _ProgressSink:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _PrefixTranslation:
    def __init__(self) -> None:
        self.calls: int = 0

    def translate_file(  # noqa: PLR0913 - test fake mirrors the domain facade
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        del source_lang, target_lang, cancel, observer
        self.calls += 1
        return FileTranslation(
            spoken=tuple(
                TranslatedLine(line.start, line.end, line.text, f"PL {line.text}", (f"PL {line.text}",), line.style)
                for line in spoken
            ),
            displayed=tuple(f"PL {line.text}" for line in displayed),
            engine_id="fake",
            target_lang="pl",
            unique_lines=len(spoken) + len(displayed),
            total_lines=len(spoken) + len(displayed),
            api_calls=1,
        )


class _RefusingExtraction:
    def extract(self, request: ExtractionRequest, *, cancel: CancellationToken, timeout_s: float) -> ExtractionResult:
        del request, cancel, timeout_s
        raise AssertionError


class _CountingTts:
    def __init__(self, root: Path) -> None:
        self.root: Path = root
        self.calls: int = 0

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        del callbacks
        self.calls += 1
        self.root.mkdir(parents=True, exist_ok=True)
        executions: list[SynthesizedRequest] = []
        for request in batch.requests:
            path: Path = self.root / f"{request.request_id}.mp3"
            path.write_bytes(b"audio")
            clip = SpeechClip(
                request.request_id,
                path,
                AudioFormat.MP3,
                24_000,
                1,
                500,
                "edge",
                "edge-default",
                "voice",
                1,
                10.0,
                False,
            )
            executions.append(SynthesizedRequest(request, SynthesisStatus.SYNTHESIZED, clip, "", 0))
        stats = SpeechBatchStats(
            len(executions), len(executions), 0, 0, 0, len(executions), 0, 10.0, "edge", "edge-default", "voice"
        )
        return SpeechBatchResult(batch.scope_id, SpeechBatchStatus.COMPLETED, tuple(executions), stats, None)

    def cancel(self) -> None:
        raise AssertionError

    def close(self) -> None:
        pass


def _handlers(
    run_root: Path,
    words: TranslationExecutor,
    voice: _CountingTts,
    source_groups: dict[str, SourceGroup],
    group_ranks: dict[str, int],
) -> ExecutionHandlers:
    return ExecutionHandlers(
        ExtractionTaskHandler(_RefusingExtraction(), run_root=run_root, timeout_s=30.0),
        SubtitleTaskHandler(run_root=run_root),
        TranslationTaskHandler(words, run_root=run_root),
        tts=TtsTaskHandler(voice, run_root=run_root, group_ranks=group_ranks),
        publish=PublishTaskHandler(run_root=run_root, source_groups=source_groups),
    )


def _run(
    plan: ExecutionPlan,
    groups: tuple[InspectedSourceGroup, ...],
    run_root: Path,
    words: TranslationExecutor,
    voice: _CountingTts,
) -> RunResult:
    source_groups: dict[str, SourceGroup] = {group.group_id: group.source for group in groups}
    ranks: dict[str, int] = {group.group_id: rank for rank, group in enumerate(groups)}
    with RunSession(run_root) as session:
        handlers: ExecutionHandlers = _handlers(run_root, words, voice, source_groups, ranks)
        return GraphScheduler(
            handlers,
            limits=ResourceLimits.from_settings(plan.settings),
            run_id=run_root.name,
            session=session,
        ).run(plan, cancel=NeverCancelledToken(), events=_RunEventSink())


class _RunEventSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


class _ShuffledTranslation:
    def translate_file(  # noqa: PLR0913 - test fake mirrors the domain facade
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        del displayed, source_lang, target_lang, cancel, observer
        return FileTranslation(
            spoken=tuple(
                TranslatedLine(line.start, line.end, line.text, f"PL {index}", (f"PL {index}",), line.style)
                for index, line in enumerate(reversed(spoken))
            ),
            displayed=(),
            engine_id="fake",
            target_lang="pl",
            unique_lines=len(spoken),
            total_lines=len(spoken),
            api_calls=1,
        )


def _execute(plan: ExecutionPlan, run_root: Path, service: TranslationExecutor | None = None) -> Path:
    by_id = {artifact.artifact_id: artifact for artifact in plan.artifacts}
    task: PlanTask = next(item for item in plan.tasks if item.kind is TaskKind.TRANSLATE_SUBTITLES)
    snapshot = ArtifactSnapshot(
        {artifact_id: by_id[artifact_id] for artifact_id in task.requires},
        {artifact_id: by_id[artifact_id] for artifact_id in task.produces},
    )
    executor: TranslationExecutor = service if service is not None else _PrefixTranslation()
    result: TaskResult = TranslationTaskHandler(executor, run_root=run_root).execute(
        task,
        snapshot,
        NeverCancelledToken(),
        _ProgressSink(),
    )
    return result.outputs[0].path


def test_equal_paragraphs_returned_out_of_their_places_are_refused(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt", "Tak.\n\nTak.\n")
    run_root: Path = tmp_path / "run"

    with pytest.raises(ExecutionError, match="incomplete"):
        _execute(_plan(tmp_path), run_root, _ShuffledTranslation())

    assert not list(run_root.rglob("*.txt"))


@pytest.mark.parametrize("name", ["Signs.ass", "Signs.ssa"])
def test_styled_subtitles_keep_their_tags_drawings_and_styles(tmp_path: Path, name: str) -> None:
    _write_ass(tmp_path / "translate" / name)

    written: Path = _execute(_plan(tmp_path), tmp_path / "run")

    body: str = written.read_text(encoding="utf-8")
    assert "Style: Default" in body
    assert "{\\p1}m 0 0 l 10 0 10 10{\\p0}" in body
    assert "{\\i1}" in body
    assert "PL " in body


def test_a_plain_text_document_is_translated_paragraph_by_paragraph(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Book.txt", "Pierwszy akapit.\n\nDrugi akapit.\n")

    written: Path = _execute(_plan(tmp_path), tmp_path / "run")

    assert written.suffix == ".txt"
    assert written.read_text(encoding="utf-8") == "PL Pierwszy akapit.\n\nPL Drugi akapit.\n"


def _document(text: str) -> TextDocument:
    return read_text_document(text, LayoutConfig())


def test_every_paragraph_keeps_its_own_identifier_and_order() -> None:
    document: TextDocument = _document("Pierwszy akapit.\n\nDrugi akapit.\n")

    assert [(fragment.paragraph, fragment.position) for fragment in document.fragments] == [(0, 0), (1, 0)]
    assert [fragment.text for fragment in document.fragments] == ["Pierwszy akapit.", "Drugi akapit."]


def test_blank_lines_between_paragraphs_survive_translation(tmp_path: Path) -> None:
    text: str = "Pierwszy akapit.\n\n\nDrugi akapit.\n\nTrzeci akapit.\n"
    document: TextDocument = _document(text)
    translated = tuple(f"PL {fragment.text}" for fragment in document.fragments)

    written: Path | None = write_text_document(document, translated, tmp_path / "out.txt")

    assert written is not None
    assert written.read_text(encoding="utf-8") == ("PL Pierwszy akapit.\n\n\nPL Drugi akapit.\n\nPL Trzeci akapit.\n")


def test_a_long_paragraph_is_split_for_the_translator_and_rejoined_as_one_paragraph(tmp_path: Path) -> None:
    sentence: str = "Zażółć gęślą jaźń raz jeszcze. "
    text: str = f"{sentence * 60}\n\nKrótki akapit.\n"
    document: TextDocument = _document(text)
    first: tuple[TextFragment, ...] = tuple(item for item in document.fragments if item.paragraph == 0)
    translated = tuple(fragment.text for fragment in document.fragments)

    written: Path | None = write_text_document(document, translated, tmp_path / "out.txt")

    assert len(first) > 1
    assert written is not None
    lines: list[str] = written.read_text(encoding="utf-8").split("\n")
    assert lines[1] == ""
    assert lines[2] == "Krótki akapit."
    assert "Zażółć gęślą jaźń raz jeszcze." in lines[0]


def test_polish_characters_pass_through_the_document_unchanged(tmp_path: Path) -> None:
    text: str = "Zażółć gęślą jaźń.\n\nĄĆĘŁŃÓŚŹŻ ąćęłńóśźż.\n"
    document: TextDocument = _document(text)

    written: Path | None = write_text_document(
        document,
        tuple(fragment.text for fragment in document.fragments),
        tmp_path / "out.txt",
    )

    assert written is not None
    assert written.read_text(encoding="utf-8") == text


def test_fragments_are_composed_by_identifier_not_by_arrival_order(tmp_path: Path) -> None:
    document: TextDocument = TextDocument(
        fragments=(TextFragment(0, 1, "drugi"), TextFragment(0, 0, "pierwszy")),
        breaks=("\n",),
    )

    written: Path | None = write_text_document(document, ("drugi", "pierwszy"), tmp_path / "out.txt")

    assert written is not None
    assert written.read_text(encoding="utf-8") == "pierwszy drugi\n"


def test_a_missing_fragment_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    document: TextDocument = _document("Pierwszy akapit.\n\nDrugi akapit.\n")
    destination: Path = tmp_path / "out.txt"

    with pytest.raises(ExecutionError, match="every fragment"):
        write_text_document(document, ("PL Pierwszy akapit.",), destination)

    assert not destination.exists()


def test_a_document_without_any_content_is_never_written(tmp_path: Path) -> None:
    document: TextDocument = _document("   \n\n   \n")
    destination: Path = tmp_path / "out.txt"

    written: Path | None = write_text_document(
        document,
        tuple(fragment.text for fragment in document.fragments),
        destination,
    )

    assert written is None
    assert not destination.exists()


def test_a_fragment_of_an_unknown_paragraph_is_refused() -> None:
    with pytest.raises(ValueError, match="paragraph the document does not have"):
        TextDocument(fragments=(TextFragment(2, 0, "tekst"),), breaks=("\n",))


def test_the_published_text_product_is_named_after_the_source_stem(tmp_path: Path) -> None:
    _write_text(tmp_path / "translate" / "Zażółć gęślą jaźń.txt")

    plan: ExecutionPlan = _plan(tmp_path)

    assert _destinations(plan) == (tmp_path / "translate" / "Zażółć gęślą jaźń.pl.txt",)
    target = next(artifact for artifact in plan.artifacts if artifact.kind is ArtifactKind.TRANSLATED_TEXT)
    assert target.language == "pol"
