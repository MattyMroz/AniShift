from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, Final, cast

from textual.message import Message

from anishift.application import (
    AppService,
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    ExecutionPlan,
    GroupConflict,
    GroupConflictKind,
    GroupResult,
    GroupStatus,
    InspectedSourceGroup,
    InspectedWorkspace,
    ProducedArtifact,
    RunEventEmitter,
    RunEventKind,
    RunEventSink,
    RunResult,
    SourceGroup,
)
from anishift.application.artifacts import create_group_id
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
)
from anishift.application.inspection import WorkspaceInspector
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.scheduler_contracts import TaskHandler, TaskProgressSink
from anishift.config import Settings, UserSettings
from anishift.config.model_catalog import ModelCatalog, parse_model_catalog
from anishift.config.presets import AutoPresetFile, default_preset_file
from anishift.errors import ExecutionError
from anishift.services.extraction import ExtractionRequest, ExtractionResult
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.setup.doctor import CheckResult, CheckStatus
from anishift.tui.app import AniShiftApp

OFFLINE_ROOT: Final[Path] = Path(__file__).parent / "_offline_never_created"

STUB_RUN_ID: Final[str] = "run-stub"

STUB_TASK_ID: Final[str] = "task-1"

STUB_GROUP_ID: Final[str] = "group-1"

PILOT_CATALOG_ALIAS: Final[str] = "foundry/gpt-main"

_PILOT_CATALOG_SOURCE: Final[str] = """
{
  "schema_version": 1,
  "providers": { "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" } },
  "models": { "foundry/gpt-main": { "provider": "foundry-openai", "model": "id-1" } }
}
"""

_PILOT_SUBTITLE: Final[str] = "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n"

_PILOT_GATE_SECONDS: Final[float] = 30.0


def offline_service(root: Path | None = None) -> AppService:
    home: Path = OFFLINE_ROOT if root is None else root
    env_file: Path = home / ".env"
    return AppService(
        workspace_root=home,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        preset_saver=lambda file: None,
        settings_saver=lambda draft: None,
        env_file=env_file,
    )


def shell(service: AppService | None = None) -> AniShiftApp:
    return AniShiftApp(service=offline_service() if service is None else service)


def empty_workspace() -> InspectedWorkspace:
    return InspectedWorkspace(groups=(), warnings=())


def stub_plan() -> ExecutionPlan:
    return cast("ExecutionPlan", object())


def stub_group() -> InspectedSourceGroup:
    return cast("InspectedSourceGroup", object())


def source_artifact(
    group_id: str,
    kind: ArtifactKind,
    path: Path,
    *,
    state: ArtifactState = ArtifactState.READY,
) -> Artifact:
    return Artifact(
        artifact_id=f"artifact-{group_id}-{kind.value}",
        group_id=group_id,
        kind=kind,
        path=path,
        state=state,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
    )


def subtitled_catalog(path: Path) -> MediaCatalog:
    return MediaCatalog(
        path=path,
        container=ContainerKind.MKV,
        duration_us=1,
        tracks=(
            MediaTrack(
                track_id=0,
                kind=MediaTrackKind.VIDEO,
                codec_id="V_MPEG4/ISO/AVC",
                language=None,
                name=None,
                is_default=True,
                is_forced=False,
            ),
            MediaTrack(
                track_id=1,
                kind=MediaTrackKind.SUBTITLES,
                codec_id="S_TEXT/ASS",
                language="eng",
                name=None,
                is_default=True,
                is_forced=False,
                subtitle_format="ass",
            ),
        ),
    )


def inspected_group(
    stem: str,
    *,
    sidecar: str | None = None,
    usable_sidecar: bool = True,
    embedded: bool = False,
    conflict: bool = False,
) -> InspectedSourceGroup:
    group_id: str = f"group-{stem}"
    container: Path = Path(f"{stem}.mkv")
    artifacts: list[Artifact] = [source_artifact(group_id, ArtifactKind.VIDEO_MKV, container)]
    if sidecar is not None:
        artifacts.append(
            source_artifact(
                group_id,
                ArtifactKind.SOURCE_SUBTITLES,
                Path(f"{stem}.{sidecar}"),
                state=ArtifactState.READY if usable_sidecar else ArtifactState.INVALID,
            ),
        )
    catalogs: dict[str, MediaCatalog] = {}
    if embedded:
        catalogs[artifacts[0].artifact_id] = subtitled_catalog(container)
    conflicts: tuple[GroupConflict, ...] = ()
    if conflict:
        conflicts = (
            GroupConflict(
                kind=GroupConflictKind.AMBIGUOUS_PRIMARY,
                message="Two candidate videos share one stem",
                paths=(container,),
            ),
        )
    return InspectedSourceGroup(
        source=SourceGroup(
            group_id=group_id,
            stem=stem,
            directory=Path(),
            artifacts=tuple(artifacts),
            conflicts=conflicts,
        ),
        artifacts=tuple(artifacts),
        media_catalogs=catalogs,
        conflicts=conflicts,
    )


def inspected_workspace(*groups: InspectedSourceGroup) -> InspectedWorkspace:
    return InspectedWorkspace(groups=groups, warnings=())


def stub_result(run_id: str = STUB_RUN_ID) -> RunResult:
    return RunResult(
        run_id=run_id,
        groups=(GroupResult(group_id=STUB_GROUP_ID, status=GroupStatus.SUCCEEDED),),
    )


def produced_artifact(artifact_id: str, path: Path) -> ProducedArtifact:
    return ProducedArtifact(artifact_id=artifact_id, path=path, metadata={})


def group_result(
    group_id: str,
    status: GroupStatus,
    *,
    products: tuple[ProducedArtifact, ...] = (),
    preserved: tuple[ProducedArtifact, ...] = (),
    errors: tuple[str, ...] = (),
) -> GroupResult:
    return GroupResult(
        group_id=group_id,
        status=status,
        products=products,
        preserved_products=preserved,
        error_messages=errors,
    )


def mixed_result(*groups: GroupResult, run_id: str = STUB_RUN_ID, warnings: tuple[str, ...] = ()) -> RunResult:
    return RunResult(run_id=run_id, groups=groups, warnings=warnings)


def emit_full_run(sink: RunEventSink, run_id: str = STUB_RUN_ID, progress: int = 3) -> None:
    emitter: RunEventEmitter = RunEventEmitter(run_id, sink)
    emitter.emit(RunEventKind.RUN_STARTED)
    for step in range(progress):
        emitter.emit(RunEventKind.TASK_PROGRESS, task_id=STUB_TASK_ID, progress_percent=step)
    emitter.emit(RunEventKind.RUN_FINISHED)


class StubService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.cancelled: list[str] = []
        self.error: Exception | None = None
        self.user_settings: UserSettings = UserSettings()
        self.workspace_root: Path = OFFLINE_ROOT
        self.workspace: InspectedWorkspace = empty_workspace()
        self.group: InspectedSourceGroup = stub_group()
        self.plan: ExecutionPlan = stub_plan()
        self.result: RunResult = stub_result()
        self.checks: tuple[Any, ...] = ()
        self.resources: tuple[Any, ...] = ()
        self.emit: Callable[[RunEventSink], None] | None = None

    def discover(self, *, cancel: Any = None) -> InspectedWorkspace:
        return self._answer("discover", self.workspace)

    def register_external_subtitle(
        self,
        group_id: str,
        path: Path,
        declared_language: str | None,
        *,
        cancel: Any = None,
    ) -> InspectedSourceGroup:
        return self._answer("register_external_subtitle", self.group)

    def register_external_audio(
        self,
        group_id: str,
        path: Path,
        role: Any,
        *,
        cancel: Any = None,
    ) -> InspectedSourceGroup:
        return self._answer("register_external_audio", self.group)

    def plan_auto(self, group_ids: Sequence[str], preset: Any) -> ExecutionPlan:
        return self._answer("plan_auto", self.plan)

    def plan_manual(self, intents: Sequence[Any]) -> ExecutionPlan:
        return self._answer("plan_manual", self.plan)

    def doctor(self) -> tuple[Any, ...]:
        return self._answer("doctor", self.checks)

    def setup(self, *, force: bool = False) -> tuple[Any, ...]:
        return self._answer("setup", self.resources)

    def execute(self, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        self.calls.append("execute")
        if self.emit is not None:
            self.emit(sink)
        if self.error is not None:
            raise self.error
        return self.result

    def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True

    def settings_snapshot(self) -> UserSettings:
        return deepcopy(self.user_settings)

    def as_service(self) -> AppService:
        return cast("AppService", self)

    def _answer[T](self, name: str, value: T) -> T:
        self.calls.append(name)
        if self.error is not None:
            raise self.error
        return value


class RecordingHost:
    def __init__(self) -> None:
        self.launched: list[Mapping[str, Any]] = []
        self.messages: list[Message] = []

    def run_worker(
        self,
        work: Callable[[], None],
        *,
        name: str = "",
        group: str = "default",
        exit_on_error: bool = True,
        thread: bool = False,
    ) -> object:
        self.launched.append(
            {"work": work, "name": name, "group": group, "exit_on_error": exit_on_error, "thread": thread},
        )
        return None

    def post_message(self, message: Message) -> bool:
        self.messages.append(message)
        return True

    def run_all(self) -> None:
        for launch in tuple(self.launched):
            cast("Callable[[], None]", launch["work"])()


def write_source_group(root: Path, stem: str) -> Path:
    container: Path = root / f"{stem}.mkv"
    container.write_bytes(b"fake media")
    container.with_suffix(".srt").write_text(_PILOT_SUBTITLE, encoding="utf-8")
    return container


def pilot_catalog() -> ModelCatalog:
    return parse_model_catalog(_PILOT_CATALOG_SOURCE)


def pilot_checks() -> tuple[CheckResult, ...]:
    return (
        CheckResult(name="python_version", status=CheckStatus.OK, message="Python is recent enough"),
        CheckResult(
            name="binaries",
            status=CheckStatus.WARN,
            message="One external tool is missing",
            suggestion="Install the external tools",
        ),
    )


class PilotMediaProbe:
    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        return MediaCatalog(
            path=path,
            container=ContainerKind(path.suffix.casefold().lstrip(".")),
            duration_us=10_000_000,
            tracks=(
                MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
                MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", None, True, False),
            ),
        )


class RefusedExtraction:
    def extract(self, request: ExtractionRequest, *, cancel: object, timeout_s: float) -> ExtractionResult:
        del request, cancel, timeout_s
        message: str = "A usable sidecar must never be extracted from the container"
        raise AssertionError(message)


class PilotTranslation:
    def __init__(self) -> None:
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.holds: bool = False

    def translate_file(  # noqa: PLR0913 - mirrors the translation service signature
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        del displayed, source_lang, target_lang, observer
        self.entered.set()
        if self.holds:
            assert self.release.wait(timeout=_PILOT_GATE_SECONDS)
        if cancel is not None and cancel.is_set():
            return FileTranslation(engine_id="pilot", error="cancelled")
        translated: tuple[TranslatedLine, ...] = tuple(
            TranslatedLine(line.start, line.end, line.text, f"PL {line.text}", (f"PL {line.text}",), line.style)
            for line in spoken
        )
        return FileTranslation(
            spoken=translated,
            engine_id="pilot",
            unique_lines=len(translated),
            total_lines=len(translated),
            api_calls=1,
        )


class PilotHandler:
    def __init__(self, delegate: TaskHandler, *, failing_group_id: str | None, progress_updates: int) -> None:
        self._delegate: TaskHandler = delegate
        self._failing_group_id: str | None = failing_group_id
        self._progress_updates: int = progress_updates

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        for step in range(self._progress_updates):
            percent: int = 1 + step * 99 // max(self._progress_updates, 1)
            progress.emit(
                WorkerNotification(
                    kind=WorkerNotificationKind.PROGRESS,
                    task_id=task.task_id,
                    progress_percent=min(percent, 99),
                )
            )
        if task.group_id == self._failing_group_id and task.kind is TaskKind.TRANSLATE_SUBTITLES:
            message: str = "Pilot translation failure"
            raise ExecutionError(message)
        return self._delegate.execute(task, artifacts, cancel, progress)

    def close(self) -> None:
        close: object = getattr(self._delegate, "close", None)
        if callable(close):
            close()


def pilot_service(  # noqa: PLR0913 - one knob per boundary the pilot replaces
    root: Path,
    *,
    translation: PilotTranslation | None = None,
    failing_stem: str | None = None,
    checks: tuple[CheckResult, ...] = (),
    prober: Callable[[Any], None] | None = None,
    progress_updates: int = 0,
) -> AppService:
    engine: PilotTranslation = translation if translation is not None else PilotTranslation()
    failing_group_id: str | None = None if failing_stem is None else create_group_id(Path(), failing_stem)
    stored: list[AutoPresetFile] = [default_preset_file()]
    env_file: Path = root / ".env"

    def handlers(
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> TaskHandler:
        del plan
        delegate: ExecutionHandlers = ExecutionHandlers(
            ExtractionTaskHandler(RefusedExtraction(), run_root=run_root, timeout_s=30.0),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(engine, run_root=run_root),
            publish=PublishTaskHandler(
                run_root=run_root,
                source_groups={group_id: group.source for group_id, group in source_groups.items()},
            ),
        )
        return PilotHandler(
            delegate,
            failing_group_id=failing_group_id,
            progress_updates=progress_updates,
        )

    return AppService(
        workspace_root=root,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(PilotMediaProbe()),
        handler_factory=handlers,
        preset_loader=lambda: stored[0],
        preset_saver=lambda value: stored.__setitem__(0, value),
        settings_saver=lambda draft: None,
        doctor_runner=lambda settings: checks,
        setup_runner=lambda **kwargs: (),
        catalog_loader=pilot_catalog,
        model_prober=cast("Any", prober),
        env_file=env_file,
    )
