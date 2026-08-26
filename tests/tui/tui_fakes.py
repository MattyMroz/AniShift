from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
    RunEventEmitter,
    RunEventKind,
    RunEventSink,
    RunResult,
    SourceGroup,
)
from anishift.config import Settings, UserSettings
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.tui.app import AniShiftApp

OFFLINE_ROOT: Final[Path] = Path(__file__).parent / "_offline_never_created"

STUB_RUN_ID: Final[str] = "run-stub"

STUB_TASK_ID: Final[str] = "task-1"

STUB_GROUP_ID: Final[str] = "group-1"


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


def emit_full_run(sink: RunEventSink, run_id: str = STUB_RUN_ID, progress: int = 3) -> None:
    emitter: RunEventEmitter = RunEventEmitter(run_id, sink)
    emitter.emit(RunEventKind.RUN_STARTED)
    for step in range(progress):
        emitter.emit(RunEventKind.TASK_PROGRESS, task_id=STUB_TASK_ID, progress_percent=step)
    emitter.emit(RunEventKind.RUN_FINISHED)


class StubService:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None
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
