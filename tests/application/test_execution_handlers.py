from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.application.cancellation import CancellationToken, NeverCancelledToken
from anishift.application.events import RunEvent, WorkerNotification, WorkerNotificationKind
from anishift.application.extraction_handler import LegacyExtractionAdapter
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.intents import AutoPreset, GroupIntent, ProductIntent, ProductKind, RunMode
from anishift.application.planner import plan_auto
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
)
from anishift.application.results import ArtifactSnapshot, GroupStatus, ProducedArtifact, TaskResult
from anishift.application.scheduler import GraphScheduler, ResourceLimits
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.sessions import RunSession
from anishift.application.subtitle_handler import LegacySubtitleAdapter
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.extraction import (
    ExtractionRequest,
    ExtractionResult,
    LegacyExtractionResult,
    MediaInfo,
    TrackSelection,
)
from anishift.services.subtitles import (
    DisplayedLine,
    SpokenLine,
    load_subtitles,
    split_subtitles,
    write_displayed,
    write_full,
    write_spoken,
)
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine


class _ProgressSink:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _RunEventSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


class _PublishHandler:
    def __init__(self, run_root: Path) -> None:
        self.run_root: Path = run_root

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        cancel.raise_if_cancelled()
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        assert source.path is not None
        destination: Path = task_staging_path(self.run_root, task, output, source.path.suffix)
        destination.write_bytes(source.path.read_bytes())
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, destination, {"validated": True}),))


class _ExtractionService:
    def __init__(self) -> None:
        self.requests: list[ExtractionRequest] = []

    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ExtractionResult:
        assert cancel.is_cancelled() is False
        assert timeout_s == 30.0
        self.requests.append(request)
        if request.target_path.suffix == ".srt":
            _write_srt(request.target_path)
        else:
            request.target_path.write_bytes(b"subtitle")
        return ExtractionResult(
            request.media_path,
            request.track_id,
            request.target_format,
            request.target_path,
            request.target_path.stat().st_size,
        )


class _TranslationService:
    def __init__(self, *, emit_provider_events: bool = False) -> None:
        self.spoken: list[SpokenLine] = []
        self.emit_provider_events: bool = emit_provider_events

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
        assert displayed == []
        assert source_lang == "auto"
        assert target_lang == "pl"
        assert cancel is not None
        assert cancel.is_set() is False
        if observer is not None and self.emit_provider_events:
            observer.retry("deepl", 2, 3)
            observer.fallback("deepl", "google")
        self.spoken = spoken
        translated: tuple[TranslatedLine, ...] = tuple(
            TranslatedLine(
                line.start,
                line.end,
                line.text,
                f"PL {line.text}",
                (f"PL {line.text}",),
                line.style,
            )
            for line in spoken
        )
        return FileTranslation(
            spoken=translated,
            engine_id="fake",
            target_lang="pl",
            unique_lines=len(translated),
            total_lines=len(translated),
            api_calls=1,
        )


def _ready(artifact_id: str, kind: ArtifactKind, path: Path) -> Artifact:
    return Artifact(
        artifact_id,
        "group-1",
        kind,
        path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        path,
    )


def _output(
    artifact_id: str,
    kind: ArtifactKind,
    *,
    subtitle_format: str | None = None,
    audio_codec: str | None = None,
) -> Artifact:
    return Artifact(
        artifact_id,
        "group-1",
        kind,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.INTERMEDIATE,
        subtitle_format=subtitle_format,
        audio_codec=audio_codec,
    )


def _task(
    kind: TaskKind,
    requires: tuple[str, ...],
    produces: tuple[str, ...],
    parameters: tuple[tuple[str, str | int | bool], ...] = (),
) -> PlanTask:
    return PlanTask(
        task_id=f"task-{kind.value}",
        group_id="group-1",
        kind=kind,
        requires=requires,
        produces=produces,
        depends_on=(),
        resource_key="test",
        parameters=parameters,
    )


def _write_srt(path: Path, text: str = "Hello") -> None:
    path.write_text(f"1\n00:00:00,000 --> 00:00:01,000\n{text}\n", encoding="utf-8")


def _write_ass(path: Path) -> None:
    path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,"
        "2,10,10,10,1\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hello\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\p1}m 0 0 l 1 1\n",
        encoding="utf-8",
    )


def _settings() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="google",
        translation_fallback_chain=("deepl",),
        translation_max_retries=3,
        translation_concurrency=2,
        llm_profile_id="gemini",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=3,
        tts_group_jobs=2,
        audio_profile_id="eac3",
        composition_profile_id="default",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )


def test_extraction_handler_builds_one_track_request_in_group_scope(tmp_path: Path) -> None:
    media = tmp_path / "episode.mkv"
    media.write_bytes(b"mkv")
    source = _ready("video", ArtifactKind.VIDEO_MKV, media)
    output = _output("source-subtitles", ArtifactKind.SOURCE_SUBTITLES, subtitle_format="ass")
    task = _task(
        TaskKind.EXTRACT_SUBTITLES,
        (source.artifact_id,),
        (output.artifact_id,),
        (("track_id", 2), ("target_format", "ass")),
    )
    service = _ExtractionService()
    progress = _ProgressSink()
    handler = ExtractionTaskHandler(service, run_root=tmp_path / "run", timeout_s=30.0)

    result: TaskResult = handler.execute(
        task,
        ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
        NeverCancelledToken(),
        progress,
    )

    assert service.requests[0].track_id == 2
    assert result.outputs[0].path.parent == tmp_path / "run" / "group-1"
    assert result.outputs[0].path.suffix == ".ass"
    assert progress.notifications[0].progress_percent == 100


def test_legacy_extraction_adapter_preserves_bulk_operation_contract(tmp_path: Path) -> None:
    media = tmp_path / "episode.mkv"
    media.write_bytes(b"mkv")
    media_info = MediaInfo(media, ())
    cancel = threading.Event()
    observed: list[object] = []

    def identify(path: Path) -> MediaInfo:
        observed.append(path)
        return media_info

    def extract(
        info: MediaInfo,
        selection: TrackSelection,
        dest_dir: Path,
        *,
        on_progress: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> LegacyExtractionResult:
        observed.extend((info, selection, dest_dir, cancel))
        if on_progress is not None:
            on_progress(100)
        return LegacyExtractionResult(None, None)

    adapter = LegacyExtractionAdapter(identify, extract)
    selection = TrackSelection(None, None, False)
    progress: list[int] = []

    assert adapter.identify(media) is media_info
    assert adapter.extract(media_info, selection, tmp_path, on_progress=progress.append, cancel=cancel) == (
        LegacyExtractionResult(None, None)
    )
    assert observed == [media, media_info, selection, tmp_path, cancel]
    assert progress == [100]


def test_subtitle_handler_normalizes_srt_to_ass(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.srt"
    _write_srt(source_path)
    source = _ready("source", ArtifactKind.SOURCE_SUBTITLES, source_path)
    output = _output("full", ArtifactKind.FULL_PL, subtitle_format="ass")
    task = _task(
        TaskKind.NORMALIZE_SUBTITLES,
        (source.artifact_id,),
        (output.artifact_id,),
        (("output_format", "ass"),),
    )

    result: TaskResult = SubtitleTaskHandler(run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
        NeverCancelledToken(),
        _ProgressSink(),
    )

    assert result.outputs[0].path.suffix == ".ass"
    assert "[Events]" in result.outputs[0].path.read_text(encoding="utf-8")


def test_subtitle_handler_splits_spoken_and_displayed_outputs(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.ass"
    _write_ass(source_path)
    source = _ready("full", ArtifactKind.FULL_PL, source_path)
    spoken = _output("spoken", ArtifactKind.SPOKEN_PL, subtitle_format="ass")
    displayed = _output("displayed", ArtifactKind.DISPLAYED_PL, subtitle_format="ass")
    task = _task(
        TaskKind.SPLIT_SUBTITLES,
        (source.artifact_id,),
        (spoken.artifact_id, displayed.artifact_id),
    )

    result: TaskResult = SubtitleTaskHandler(run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot(
            {source.artifact_id: source},
            {spoken.artifact_id: spoken, displayed.artifact_id: displayed},
        ),
        NeverCancelledToken(),
        _ProgressSink(),
    )

    assert tuple(output.artifact_id for output in result.outputs) == ("spoken", "displayed")
    assert all(output.path.is_file() for output in result.outputs)


def test_legacy_subtitle_adapter_keeps_split_and_product_parity(tmp_path: Path) -> None:
    source = tmp_path / "episode.ass"
    _write_ass(source)
    adapter = LegacySubtitleAdapter()
    adapted_split = adapter.split(adapter.load(source), kind="ass")
    direct_split = split_subtitles(load_subtitles(source), kind="ass")
    assert adapted_split.decisions == direct_split.decisions
    assert adapted_split.spoken == direct_split.spoken

    adapted_root = tmp_path / "adapted"
    direct_root = tmp_path / "direct"
    adapted_root.mkdir()
    direct_root.mkdir()
    adapted = adapter.write_polish(adapted_split, adapted_root / "episode", "ass")
    direct = (
        write_full(direct_split, direct_root / "episode.pl.ass"),
        write_spoken(direct_split, direct_root / "episode.spoken.pl.ass"),
        write_displayed(direct_split, direct_root / "episode.displayed.pl.ass"),
    )

    adapted_paths = (adapted.full, adapted.spoken, adapted.displayed)
    assert tuple(path.read_text(encoding="utf-8") if path is not None else None for path in adapted_paths) == tuple(
        path.read_text(encoding="utf-8") if path is not None else None for path in direct
    )


def test_translation_handler_writes_complete_polish_staging(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.srt"
    _write_srt(source_path)
    source = _ready("source", ArtifactKind.SOURCE_SUBTITLES, source_path)
    output = _output("full", ArtifactKind.FULL_PL, subtitle_format="srt")
    task = _task(
        TaskKind.TRANSLATE_SUBTITLES,
        (source.artifact_id,),
        (output.artifact_id,),
        (("output_format", "srt"),),
    )
    service = _TranslationService()

    result: TaskResult = TranslationTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
        NeverCancelledToken(),
        _ProgressSink(),
    )

    assert service.spoken[0].text == "Hello"
    assert "PL Hello" in result.outputs[0].path.read_text(encoding="utf-8")
    assert result.outputs[0].metadata["engine_id"] == "fake"


def test_translation_handler_translates_standalone_text_to_srt(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.txt"
    source_path.write_text("First sentence. Second sentence.", encoding="utf-8")
    source = _ready("source", ArtifactKind.STANDALONE_TEXT, source_path)
    output = _output("full", ArtifactKind.FULL_PL, subtitle_format="srt")
    task = _task(
        TaskKind.TRANSLATE_SUBTITLES,
        (source.artifact_id,),
        (output.artifact_id,),
        (("source_kind", "txt"), ("output_format", "srt")),
    )

    result: TaskResult = TranslationTaskHandler(_TranslationService(), run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
        NeverCancelledToken(),
        _ProgressSink(),
    )

    translated: str = result.outputs[0].path.read_text(encoding="utf-8")
    assert "PL First sentence. Second sentence." in translated


def test_translation_handler_maps_provider_events_to_worker_notifications(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.srt"
    _write_srt(source_path)
    source = _ready("source", ArtifactKind.SOURCE_SUBTITLES, source_path)
    output = _output("full", ArtifactKind.FULL_PL, subtitle_format="srt")
    task = _task(
        TaskKind.TRANSLATE_SUBTITLES,
        (source.artifact_id,),
        (output.artifact_id,),
        (("output_format", "srt"),),
    )
    progress = _ProgressSink()

    TranslationTaskHandler(
        _TranslationService(emit_provider_events=True),
        run_root=tmp_path / "run",
    ).execute(
        task,
        ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
        NeverCancelledToken(),
        progress,
    )

    assert tuple(notification.kind.value for notification in progress.notifications) == (
        "retry",
        "fallback",
        "progress",
    )


def test_execution_handlers_rejects_family_not_available_in_increment_10a(tmp_path: Path) -> None:
    extraction = ExtractionTaskHandler(_ExtractionService(), run_root=tmp_path / "run", timeout_s=30.0)
    handlers = ExecutionHandlers(
        extraction,
        SubtitleTaskHandler(run_root=tmp_path / "run"),
        TranslationTaskHandler(_TranslationService(), run_root=tmp_path / "run"),
    )
    task = _task(TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",))

    with pytest.raises(ExecutionError, match="unavailable"):
        handlers.execute(task, ArtifactSnapshot({}), NeverCancelledToken(), _ProgressSink())


@pytest.mark.parametrize("unsafe_id", ["..", "nested/group", r"nested\group", "C:escape"])
def test_task_staging_path_rejects_unsafe_identifiers(tmp_path: Path, unsafe_id: str) -> None:
    output = _output("spoken", ArtifactKind.SPOKEN_PL, subtitle_format="srt")
    task = _task(TaskKind.SPLIT_SUBTITLES, ("full",), (output.artifact_id,))
    object.__setattr__(task, "group_id", unsafe_id)

    with pytest.raises(ExecutionError, match="safe staging path"):
        task_staging_path(tmp_path, task, output, ".srt")


def test_scheduler_executes_real_increment_10a_handlers(tmp_path: Path) -> None:
    media_path = tmp_path / "episode.mkv"
    media_path.write_bytes(b"mkv")
    video = _ready("video", ArtifactKind.VIDEO_MKV, media_path)
    source = _output("source", ArtifactKind.SOURCE_SUBTITLES, subtitle_format="srt")
    full = _output("full", ArtifactKind.FULL_PL, subtitle_format="srt")
    spoken = _output("spoken", ArtifactKind.SPOKEN_PL, subtitle_format="srt")
    extract = PlanTask(
        "extract",
        "group-1",
        TaskKind.EXTRACT_SUBTITLES,
        (video.artifact_id,),
        (source.artifact_id,),
        (),
        "extraction",
        (("track_id", 2), ("target_format", "srt")),
    )
    translate = PlanTask(
        "translate",
        "group-1",
        TaskKind.TRANSLATE_SUBTITLES,
        (source.artifact_id,),
        (full.artifact_id,),
        (extract.task_id,),
        "translation:google",
        (("output_format", "srt"),),
    )
    split = PlanTask(
        "split",
        "group-1",
        TaskKind.SPLIT_SUBTITLES,
        (full.artifact_id,),
        (spoken.artifact_id,),
        (translate.task_id,),
        "llm:gemini",
    )
    intent = GroupIntent(
        "group-1",
        RunMode.AUTO,
        ProductIntent(requested_products=frozenset({ProductKind.SPOKEN_PL})),
    )
    group = GroupPlan(
        "group-1",
        intent,
        tuple(artifact.artifact_id for artifact in (video, source, full, spoken)),
        (extract.task_id, translate.task_id, split.task_id),
    )
    settings: RunSettingsSnapshot = _settings()
    plan = ExecutionPlan((group,), (video, source, full, spoken), (extract, translate, split), settings, ())
    run_root = tmp_path / "temp" / "run-1"
    sink = _RunEventSink()

    with RunSession(run_root) as session:
        handlers = ExecutionHandlers(
            ExtractionTaskHandler(_ExtractionService(), run_root=run_root, timeout_s=30.0),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(_TranslationService(), run_root=run_root),
        )
        scheduler = GraphScheduler(
            handlers,
            limits=ResourceLimits.from_settings(settings),
            run_id="run-1",
            session=session,
        )
        result = scheduler.run(plan, cancel=NeverCancelledToken(), events=sink)
        final_path: Path = result.groups[0].task_results[-1].outputs[0].path
        assert "PL Hello" in final_path.read_text(encoding="utf-8")

    assert result.groups[0].status is GroupStatus.SUCCEEDED
    assert run_root.exists() is False


def test_planner_to_scheduler_executes_standalone_text_plan(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.txt"
    source_path.write_text("Hello from a standalone file.", encoding="utf-8")
    source = _ready("text-source", ArtifactKind.STANDALONE_TEXT, source_path)
    source_group = SourceGroup("group-1", "episode", tmp_path, (source,))
    inspected = InspectedSourceGroup(source_group, (source,), {}, ())
    products = ProductIntent(frozenset({ProductKind.FULL_PL}))
    plan: ExecutionPlan = plan_auto(
        (inspected,),
        AutoPreset("default", "Default", products),
        _settings(),
    )
    run_root = tmp_path / "temp" / "run-txt"
    published = tmp_path / "episode.pl.srt"

    with RunSession(run_root) as session:
        handlers = ExecutionHandlers(
            ExtractionTaskHandler(_ExtractionService(), run_root=run_root, timeout_s=30.0),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(_TranslationService(), run_root=run_root),
            publish=_PublishHandler(run_root),
        )
        result = GraphScheduler(
            handlers,
            limits=ResourceLimits.from_settings(plan.settings),
            run_id="run-txt",
            session=session,
        ).run(plan, cancel=NeverCancelledToken(), events=_RunEventSink())

    assert result.groups[0].status is GroupStatus.SUCCEEDED
    assert "PL Hello from a standalone file." in published.read_text(encoding="utf-8")
