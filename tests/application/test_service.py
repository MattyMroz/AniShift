from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fakes import (
    CollectingRunSink,
    FailingGroupHandler,
    FakeMediaProbe,
    FakeTranslationService,
    write_media_source,
    write_text_source,
)

import anishift.application.service as service_module
import anishift.application.watch as watch_module
from anishift.application.automation import AutomationOwner
from anishift.application.cancellation import CancellationToken, EventCancellationToken
from anishift.application.control import ProcessingRequest, ReadyGroup, RequestState
from anishift.application.control_views import PlanPreview
from anishift.application.discovery import DiscoveryResult
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace, WorkspaceInspector
from anishift.application.intents import (
    AutoPreset,
    ExternalAudioRole,
    GroupIntent,
    ProductIntent,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    RunMode,
    SubtitleSourcePolicy,
)
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, TaskKind
from anishift.application.ready import ReadyStore
from anishift.application.results import GroupStatus, RunResult
from anishift.application.scheduler import RunHandle
from anishift.application.scheduler_contracts import ResourceLimits, TaskHandler, extraction_worker_count
from anishift.application.scheduler_runtime import extraction_group_ids
from anishift.application.service import AppService, AutoPresetDraft
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.bootstrap import AppContext, bootstrap, create_app_service
from anishift.cli.interactive.manual import ManualController, ManualResult, ManualRun
from anishift.cli.resident import ResidentSession
from anishift.cli.watch import run_resident
from anishift.config.model_catalog import ModelCatalog, parse_model_catalog
from anishift.config.presets import AutoPresetFile, default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.config.workspace import cleanup_orphaned_temp
from anishift.errors import ErrorCode, ExecutionError, RunConflictError
from anishift.paths import TRANSLATE_DIRECTORY, relocation_journal_dir
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlServer,
    connect,
    control_endpoint,
)
from anishift.services.extraction import ExtractionRequest, ExtractionResult
from anishift.services.media import DefaultMediaProbe
from anishift.services.media._process import ProcessResult
from anishift.services.media.types import MediaCatalog

_PALANTIR_TOKEN = "palantir-token-sentinel-deadbeef"  # noqa: S105


class _UnusedExtraction:
    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: object,
        timeout_s: float,
    ) -> ExtractionResult:
        del request, cancel, timeout_s
        raise AssertionError("TXT flow must not extract media tracks")


def _service(  # noqa: PLR0913 - one builder for every service variant the tests need
    tmp_path: Path,
    translation: FakeTranslationService,
    *,
    fail_group_id: str | None = None,
    preset_store: list[AutoPresetFile] | None = None,
    inspector: WorkspaceInspector | None = None,
    settings: Settings | None = None,
    user_settings: UserSettings | None = None,
    catalog_loader: Callable[[], ModelCatalog] | None = None,
    prepare_workspace: Callable[[DiscoveryResult, CancellationToken], None] | None = None,
) -> AppService:
    stored: list[AutoPresetFile] = preset_store if preset_store is not None else [default_preset_file()]

    def handlers(
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> TaskHandler:
        del plan
        discovered_groups = {group_id: group.source for group_id, group in source_groups.items()}
        delegate = ExecutionHandlers(
            ExtractionTaskHandler(_UnusedExtraction(), run_root=run_root, timeout_s=30.0),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(translation, run_root=run_root),
            publish=PublishTaskHandler(run_root=run_root, source_groups=discovered_groups),
        )
        return FailingGroupHandler(delegate, group_id=fail_group_id)

    return AppService(
        workspace_root=tmp_path,
        settings=settings or Settings(_env_file=None),
        user_settings=user_settings or UserSettings(),
        inspector=inspector or WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=handlers,
        preset_loader=lambda: stored[0],
        preset_saver=lambda value: stored.__setitem__(0, value),
        settings_saver=lambda value: None,
        catalog_loader=catalog_loader or _catalog,
        prepare_workspace=prepare_workspace,
    )


def _catalog() -> ModelCatalog:
    source = """
    {
      "schema_version": 1,
      "providers": { "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" } },
      "models": { "foundry/gpt-main": { "provider": "foundry-openai", "model": "id-1" } }
    }
    """
    return parse_model_catalog(source)


@contextmanager
def _panel_owner(
    service: AppService, tmp_path: Path, *, ready: bool = False
) -> Iterator[tuple[ResidentSession, WatchStateStore]]:
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = AutomationOwner(
        service,
        store,
        instance_id="panel-test",
        ready_store=ReadyStore(relocation_journal_dir(tmp_path / ".control"), tmp_path) if ready else None,
    )
    thread: threading.Thread = threading.Thread(target=owner.serve, daemon=True)
    thread.start()
    endpoint: str = control_endpoint(tmp_path / ".control")
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
    owner.attach_broadcast(server.broadcast)
    session: ResidentSession = ResidentSession(
        service.workspace_root, lambda: ControlClient(endpoint, key, timeout_s=5.0)
    )
    try:
        yield session, store
    finally:
        session.close()
        server.close()
        owner.request_shutdown()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize("regenerate", [False, True])
def test_panel_executes_only_selected_episodes_through_the_resident(tmp_path: Path, *, regenerate: bool) -> None:
    for number in (1, 3, 8):
        write_text_source(tmp_path / f"{number:02d}.txt", f"Episode {number}")
    previous: str = "1\n00:00:00,000 --> 00:00:01,000\nPrevious translation\n"
    (tmp_path / "03.pl.srt").write_text(previous, encoding="utf-8")
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation)
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    rendered: threading.Event = threading.Event()
    with _panel_owner(service, tmp_path) as (session, store):
        controller: ManualController = ManualController(session, session.discover(), preset, rendered.set)
        keys: tuple[str, ...] = ("down", "space", "down", "space", "end")
        for key in (*keys, *(("down",) * 3 if regenerate else ()), "enter"):
            assert controller.handle_key(key) is ManualResult.STAY
        assert rendered.wait(5.0)
        assert "2 odcinków" in controller.render(120, 40).plain
        assert translation.calls == []
        assert len(store.load().reservations) == 2
        assert controller.handle_key("enter") is ManualResult.START_RUN
        prepared: ManualRun | None = controller.take_ready_run()
        assert prepared is not None
        assert isinstance(prepared.plan, PlanPreview)
        sink: CollectingRunSink = CollectingRunSink()
        result: RunResult = session.execute(prepared.plan, sink)
        assert result.succeeded
        assert sink.events
        assert {group.group_id for group in result.groups} == {group.group_id for group in prepared.plan.groups}
        assert store.load().requests[0].state is RequestState.SUCCEEDED
        assert len(store.load().markers) == 2
        assert store.load().reservations == ()
        assert not (tmp_path / "01.pl.srt").exists()
        assert "PL Episode 8" in (tmp_path / "08.pl.srt").read_text(encoding="utf-8")
        assert ("PL Episode 3" if regenerate else "Previous translation") in (tmp_path / "03.pl.srt").read_text(
            encoding="utf-8"
        )
        assert len(translation.calls) == (2 if regenerate else 1)


@pytest.mark.integration
@pytest.mark.parametrize("early", [False, True])
def test_global_resume_finishes_the_same_real_graph_without_repeating_its_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, early: bool
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    write_media_source(tmp_path / "03.mkv")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    translation: FakeTranslationService = FakeTranslationService(entered=entered, release=release)
    service: AppService = _service(tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()))
    preset: AutoPreset = AutoPreset(
        "once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
    )
    try:
        with _panel_owner(service, tmp_path) as (session, store):
            group_ids: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
            session.reserve(group_ids)
            preview: PlanPreview = session.plan_auto(group_ids, preset)
            run_id: str = session.start(preview)
            assert entered.wait(1.0)
            session.command("set_auto", {"enabled": False})
            assert session.command("status")["pausing"] is True
            if early:
                time.sleep(0.1)
                session.command("set_auto", {"enabled": True})
            release.set()
            if not early:
                assert _wait_for_resident(session, lambda state: state["paused"] is True)
                assert store.load().requests[0].state is RequestState.PAUSED
                assert store.load().markers == ()
                session.command("set_auto", {"enabled": True})
            assert _wait_for_resident(
                session,
                lambda _state: session.command("run_result", {"run_id": run_id})["state"] == "succeeded",
            )
            assert len(translation.calls) == 1
            assert len(store.load().requests) == 1
            assert store.load().requests[0].attempts == 1
            assert len(store.load().products) == 2
    finally:
        release.set()
        service.close()


def _wait_for_resident(session: ResidentSession, condition: Callable[[Mapping[str, object]], bool]) -> bool:
    deadline: float = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if condition(session.command("status")):
            return True
        time.sleep(0.01)
    return False


@pytest.mark.integration
def test_restarting_a_paused_owner_preserves_the_graph_and_only_resume_finishes_its_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    write_media_source(tmp_path / "03.mkv")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    translation: FakeTranslationService = FakeTranslationService(entered=entered, release=release)
    service: AppService = _service(tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()))
    preset: AutoPreset = AutoPreset(
        "once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
    )
    try:
        with _panel_owner(service, tmp_path) as (session, store):
            group_ids: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
            session.reserve(group_ids)
            run_id: str = session.start(session.plan_auto(group_ids, preset))
            assert entered.wait(1.0)
            session.command("set_auto", {"enabled": False})
            release.set()
            assert _wait_for_resident(session, lambda state: state["paused"] is True)
            assert store.load().requests[0].state is RequestState.PAUSED
    finally:
        release.set()
        service.close()
    restarted: AppService = _service(tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()))
    try:
        with _panel_owner(restarted, tmp_path) as (session, store):
            assert session.command("status")["paused"] is True
            assert restarted.active_run_ids() == ()
            assert store.load().products == ()
            session.command("set_auto", {"enabled": True})
            assert _wait_for_resident(
                session,
                lambda _state: session.command("run_result", {"run_id": run_id})["state"] == "succeeded",
            )
            assert len(translation.calls) == 1
            assert len(store.load().requests) == 1
            assert store.load().requests[0].attempts == 1
            assert len(store.load().products) == 2
    finally:
        restarted.close()


@pytest.mark.integration
def test_panel_escape_releases_the_scope_for_another_session(tmp_path: Path) -> None:
    write_text_source(tmp_path / "03.txt", "Original")
    service: AppService = _service(tmp_path, FakeTranslationService())
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    rendered: threading.Event = threading.Event()
    with _panel_owner(service, tmp_path) as (session, store):
        workspace: InspectedWorkspace = session.discover()
        controller: ManualController = ManualController(session, workspace, preset, rendered.set)
        for key in ("space", "end", "enter"):
            controller.handle_key(key)
        assert rendered.wait(5.0)
        second: ResidentSession = session.new_session()
        try:
            with pytest.raises(ControlError) as held:
                second.reserve((workspace.groups[0].group_id,))
            assert held.value.code is ControlErrorCode.CONFLICT
            assert controller.handle_key("escape") is ManualResult.STAY
            assert store.load().reservations == ()
            second.reserve((workspace.groups[0].group_id,))
        finally:
            second.close()


@pytest.mark.integration
def test_panel_start_rejects_a_source_changed_after_preview(tmp_path: Path) -> None:
    source: Path = tmp_path / "03.txt"
    write_text_source(source, "Original")
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation)
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    with _panel_owner(service, tmp_path) as (session, store):
        group_id: str = session.discover().groups[0].group_id
        session.reserve((group_id,))
        preview: PlanPreview = session.plan_auto((group_id,), preset)
        source.write_text("A different source", encoding="utf-8")
        with pytest.raises(ControlError) as changed:
            session.execute(preview, CollectingRunSink())
        assert changed.value.code is ControlErrorCode.STALE_PREVIEW
        assert translation.calls == []
        assert store.load().requests == ()


class _AudioDecode:
    def __init__(self, entered: threading.Event | None = None, release: threading.Event | None = None) -> None:
        self.entered: threading.Event | None = entered
        self.release: threading.Event | None = release

    def run(self, command: Sequence[str], *, cancel: CancellationToken, timeout_s: float) -> ProcessResult:
        del command, timeout_s
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(5.0)
        cancel.raise_if_cancelled()
        return ProcessResult("out_time_us=10000000\nprogress=end\n", "", 0)


@pytest.mark.integration
def test_panel_preserves_external_sources_when_another_group_changes(tmp_path: Path) -> None:
    write_media_source(tmp_path / "03.mkv")
    outside: Path = tmp_path / ".external"
    outside.mkdir()
    subtitle: Path = outside / "translated.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nExternal text\n", encoding="utf-8")
    audio: Path = outside / "audio.wav"
    audio.write_bytes(b"audio")
    translation: FakeTranslationService = FakeTranslationService()
    inspector: WorkspaceInspector = WorkspaceInspector(FakeMediaProbe(), runner=_AudioDecode(), ffmpeg=Path("ffmpeg"))
    service: AppService = _service(tmp_path, translation, inspector=inspector)
    with _panel_owner(service, tmp_path) as (session, _):
        group_id: str = session.discover().groups[0].group_id
        session.reserve((group_id,))
        subtitles: InspectedSourceGroup = session.register_external_subtitle(group_id, subtitle, "en")
        sources: InspectedSourceGroup = session.register_external_audio(group_id, audio, ExternalAudioRole.SOURCE_AUDIO)
        intent: GroupIntent = GroupIntent(
            group_id,
            RunMode.MANUAL,
            ProductIntent(frozenset({ProductKind.FULL_PL})),
            subtitle_source_policy=SubtitleSourcePolicy.EXTERNAL,
            selected_subtitle_artifact_id=subtitles.artifacts[-1].artifact_id,
            selected_audio_artifact_id=sources.artifacts[-1].artifact_id,
            external_audio_role=ExternalAudioRole.SOURCE_AUDIO,
        )
        write_text_source(tmp_path / "08.txt", "Another episode")
        preview: PlanPreview = session.plan_manual((intent,))
        assert preview.can_execute
        assert preview.groups[0].intent == intent
        result: RunResult = session.execute(preview, CollectingRunSink())
        assert result.succeeded
        assert translation.calls == [("External text",)]
        assert audio.read_bytes() == b"audio"
        assert "External text" in subtitle.read_text(encoding="utf-8")


@pytest.mark.integration
def test_closed_panel_cannot_register_a_late_external_source(tmp_path: Path) -> None:
    write_media_source(tmp_path / "03.mkv")
    audio: Path = tmp_path / ".external.wav"
    audio.write_bytes(b"audio")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    inspector: WorkspaceInspector = WorkspaceInspector(
        FakeMediaProbe(), runner=_AudioDecode(entered, release), ffmpeg=Path("ffmpeg")
    )
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=inspector)
    with _panel_owner(service, tmp_path) as (session, _):
        group_id: str = session.discover().groups[0].group_id
        session.reserve((group_id,))
        errors: list[ControlError | OSError] = []

        def register() -> None:
            try:
                session.register_external_audio(group_id, audio, ExternalAudioRole.SOURCE_AUDIO)
            except (ControlError, OSError) as error:
                errors.append(error)

        worker: threading.Thread = threading.Thread(target=register, daemon=True)
        worker.start()
        second: ResidentSession = session.new_session()
        try:
            assert entered.wait(5.0)
            session.close()
            deadline: float = time.monotonic() + 5.0
            while True:
                try:
                    second.reserve((group_id,))
                    break
                except ControlError as error:
                    if error.code is not ControlErrorCode.CONFLICT:
                        raise
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
        finally:
            release.set()
            worker.join(timeout=5.0)
            second.close()
        assert not worker.is_alive()
        assert errors
        assert all(artifact.path != audio for artifact in service.discover().groups[0].artifacts)


@pytest.mark.integration
@pytest.mark.parametrize("changed_file", ["03.txt", "03.pl.srt"])
def test_resident_preserves_user_edits_made_during_translation(tmp_path: Path, changed_file: str) -> None:
    write_text_source(tmp_path / "03.txt", "Original text")
    write_text_source(tmp_path / "08.txt", "Unaffected episode")
    product: Path = tmp_path / "03.pl.srt"
    previous: str = "1\n00:00:00,000 --> 00:00:01,000\nPrevious translation\n"
    product.write_text(previous, encoding="utf-8")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    translation: FakeTranslationService = FakeTranslationService(entered=entered, release=release)
    service: AppService = _service(tmp_path, translation)
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    edited: str = "1\n00:00:00,000 --> 00:00:01,000\nUser correction during translation\n"
    with _panel_owner(service, tmp_path) as (session, store), ThreadPoolExecutor(max_workers=1) as pool:
        group_ids: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(group_ids)
        preview: PlanPreview = session.plan_auto(
            group_ids, preset, rebuild=RebuildRequest(frozenset({ProductKind.FULL_PL}))
        )
        pending: Future[RunResult] = pool.submit(session.execute, preview, CollectingRunSink())
        try:
            assert entered.wait(2.0)
            (tmp_path / changed_file).write_text(edited, encoding="utf-8")
        finally:
            release.set()
        result: RunResult = pending.result(timeout=5.0)
        assert not result.succeeded
        assert result.groups[0].products == ()
        assert result.groups[1].status is GroupStatus.SUCCEEDED
        assert "PL Unaffected episode" in (tmp_path / "08.pl.srt").read_text(encoding="utf-8")
        assert len(store.load().products) == 1
        assert product.read_text(encoding="utf-8") == (edited if changed_file == product.name else previous)
        assert len(translation.calls) == 2
        session.reserve(group_ids)
        with pytest.raises(ControlError):
            session.plan_resume(group_ids)


@pytest.mark.integration
@pytest.mark.parametrize("failure_at", ["before_replace", "after_replace", "checkpoint", "after_replace_other_group"])
def test_resident_resumes_partial_publication_without_translating_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str
) -> None:
    write_media_source(tmp_path / "03.mkv")
    write_text_source(tmp_path / "03.srt", "1\n00:00:00,000 --> 00:00:01,000\nOriginal text\n")
    previous: str = "1\n00:00:00,000 --> 00:00:01,000\nPrevious translation\n"
    for name in ("03.pl.srt", "03.spoken.pl.srt"):
        (tmp_path / name).write_text(previous, encoding="utf-8")
    if failure_at == "after_replace_other_group":
        write_media_source(tmp_path / "08.mkv")
        write_text_source(tmp_path / "08.srt", "1\n00:00:00,000 --> 00:00:01,000\nAnother episode\n")
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()))
    preset: AutoPreset = AutoPreset(
        "once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
    )
    original_replace: Callable[[Path, Path], Path] = Path.replace
    published: list[Path] = []

    def replace_product(source: Path, destination: Path) -> Path:
        if failure_at == "checkpoint" and published and destination.parent.name == "runs":
            raise OSError(errno.ENOSPC, "Injected checkpoint failure")
        if (
            destination.parent == tmp_path
            and destination.name.startswith("03.")
            and destination.name.endswith(".pl.srt")
        ):
            if published:
                if failure_at.startswith("after_replace"):
                    original_replace(source, destination)
                raise OSError(errno.EIO, "Injected publication failure")
            published.append(destination)
        return original_replace(source, destination)

    with _panel_owner(service, tmp_path) as (session, store):
        group_ids: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(group_ids)
        preview: PlanPreview = session.plan_auto(
            group_ids, preset, rebuild=RebuildRequest(frozenset({ProductKind.FULL_PL}))
        )
        with monkeypatch.context() as failure:
            assert preview.can_execute, preview.problems
            failure.setattr(Path, "replace", replace_product)
            result: RunResult = session.execute(preview, CollectingRunSink())
        assert result.groups[0].status is GroupStatus.PARTIAL
        assert len(result.groups[0].error_messages) == 1, result.groups[0].error_messages
        assert len(published) == 1
        assert len(translation.calls) == len(group_ids)
        if len(group_ids) == 2:
            assert result.groups[1].status is GroupStatus.SUCCEEDED
        assert store.load().requests[0].state is RequestState.PARTIAL
        preserved: bytes = published[0].read_bytes()
        identity: tuple[int, int] = (published[0].stat().st_ino, published[0].stat().st_mtime_ns)
        untouched: Path = next(
            tmp_path / name for name in ("03.pl.srt", "03.spoken.pl.srt") if tmp_path / name not in published
        )
        assert (
            "PL Original text" if failure_at.startswith("after_replace") else "Previous translation"
        ) in untouched.read_text(encoding="utf-8")
    script: str = """
import json
import sys
from pathlib import Path
from fakes import CollectingRunSink, FakeMediaProbe, FakeTranslationService
from test_service import _panel_owner, _service
from anishift.application.inspection import WorkspaceInspector
from anishift.application.planning import TaskKind

root = Path(sys.argv[1])
translation = FakeTranslationService()
service = _service(root, translation, inspector=WorkspaceInspector(FakeMediaProbe()))
with _panel_owner(service, root) as (session, store):
    group_ids = tuple(group.group_id for group in session.discover().groups)
    session.reserve(group_ids)
    remaining = session.plan_resume(group_ids)
    assert TaskKind.TRANSLATE_SUBTITLES not in {task.kind for task in remaining.tasks}
    result = session.execute(remaining, CollectingRunSink())
    print(json.dumps({
        "succeeded": result.succeeded,
        "products": sum(len(group.products) for group in result.groups),
        "run_id": result.run_id,
        "translations": len(translation.calls),
        "generation": store.load().requests[0].generation,
    }))
"""
    completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
    )
    assert completed.returncode == 0, completed.stderr
    outcome: dict[str, object] = json.loads(completed.stdout)
    assert outcome == {
        "succeeded": True,
        "products": 2 * len(group_ids),
        "run_id": result.run_id,
        "translations": 0,
        "generation": 2,
    }
    assert published[0].read_bytes() == preserved
    assert (published[0].stat().st_ino, published[0].stat().st_mtime_ns) == identity
    assert "PL Original text" in untouched.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.parametrize(
    "failure_at",
    [
        "before_accept",
        "after_accept",
        "remote",
        "before_replace",
        "after_replace",
        "after_cleanup",
        "before_ready",
        "after_link",
    ],
)
def test_resident_recovers_after_process_death_without_repeating_confirmed_translation(
    tmp_path: Path, failure_at: str
) -> None:
    source: Path = tmp_path / "03.txt"
    write_text_source(source, "Original text")
    identity: int = source.stat().st_ino
    script: str = """
import json
import os
import sys
from pathlib import Path
from fakes import CollectingRunSink, FakeTranslationService
from test_service import _panel_owner, _service
from anishift.application.automation import AutomationOwner
from anishift.application.intents import AutoPreset, ProductIntent, ProductKind
from anishift.application.ready import ReadyStore
from anishift.cli.watch import run_resident

root = Path(sys.argv[1])
phase = sys.argv[2]
translation = FakeTranslationService()
service = _service(root, translation)
if phase == "restart":
    code = run_resident(service, state_dir=root / ".control")
    print(json.dumps({"translations": len(translation.calls), "code": code}))
    service.close()
    sys.exit(code)
original_commit = AutomationOwner._commit
def commit(self, request, *args):
    if request.kind == "start" and phase == "before_accept":
        os._exit(73)
    result = original_commit(self, request, *args)
    if request.kind == "start" and phase == "after_accept":
        os._exit(73)
    return result
AutomationOwner._commit = commit
original_translation = translation.translate_file
def translate(*args, **kwargs):
    result = original_translation(*args, **kwargs)
    if phase == "remote":
        os._exit(73)
    return result
translation.translate_file = translate
original_replace = Path.replace
def replace_file(self, destination):
    if destination == root / "03.pl.srt" and phase == "before_replace":
        os._exit(73)
    result = original_replace(self, destination)
    if destination == root / "03.pl.srt" and phase == "after_replace":
        os._exit(73)
    return result
Path.replace = replace_file
if phase == "after_cleanup":
    AutomationOwner._record_completion = lambda *args: os._exit(73)
if phase == "before_ready":
    ReadyStore.prepare = lambda *args: os._exit(73)
original_link = os.link
def link(*args, **kwargs):
    original_link(*args, **kwargs)
    if phase == "after_link":
        os._exit(73)
os.link = link
with _panel_owner(service, root, ready=True) as (session, store):
    groups = tuple(group.group_id for group in session.discover().groups)
    session.reserve(groups)
    preset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    session.execute(session.plan_auto(groups, preset), CollectingRunSink())
raise AssertionError("The selected crash boundary was not reached")
"""
    environment: dict[str, str] = {**os.environ, "PYTHONPATH": str(Path(__file__).parent)}
    crashed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(tmp_path), failure_at],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert crashed.returncode == 73, crashed.stderr
    client: ControlClient | None = None
    with subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", script, str(tmp_path), "restart"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as process:
        try:
            deadline: float = time.monotonic() + 15.0
            while client is None and time.monotonic() < deadline and process.poll() is None:
                client = connect(tmp_path / ".control")
                time.sleep(0.01)
            assert client is not None
            while time.monotonic() < deadline:
                status: Mapping[str, object] = client.call("status")
                if failure_at in {"before_accept", "remote"}:
                    if status["library_groups"] and not status["requests"]:
                        break
                elif (tmp_path / "ready/03.pl.srt").is_file() and not status["relocations"]:
                    break
                time.sleep(0.01)
            if failure_at in {"before_accept", "remote"}:
                assert source.stat().st_ino == identity
                assert not (tmp_path / "ready/03.pl.srt").exists()
                assert bool(status["recovery_problems"]) == (failure_at == "remote")
            else:
                assert (tmp_path / "ready/03.txt").stat().st_ino == identity
                assert "PL Original text" in (tmp_path / "ready/03.pl.srt").read_text(encoding="utf-8")
                assert not source.exists()
                assert not status["requests"]
                assert not status["relocations"]
            client.call("shutdown")
            stdout: str
            stderr: str
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stderr
            assert json.loads(stdout) == {"translations": int(failure_at == "after_accept"), "code": 0}
        finally:
            if client is not None:
                client.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


@pytest.mark.integration
def test_resident_moves_sources_and_products_then_regenerates_in_ready(tmp_path: Path) -> None:
    source: Path = tmp_path / "03.txt"
    write_text_source(source, "Original text")
    identity: int = source.stat().st_ino
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation)
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    with _panel_owner(service, tmp_path, ready=True) as (session, store):
        groups: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(groups)
        result: RunResult = session.execute(session.plan_auto(groups, preset), CollectingRunSink())
        assert result.succeeded
        assert all(product.path.parent == tmp_path / "ready" for group in result.groups for product in group.products)
        deadline: float = time.monotonic() + 5.0
        while not (tmp_path / "ready/03.txt").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        moved: Path = tmp_path / "ready/03.txt"
        assert moved.stat().st_ino == identity
        assert (tmp_path / "ready/03.pl.srt").is_file()
        assert not source.exists()
        groups = tuple(group.group_id for group in session.discover().groups)
        session.reserve(groups)
        rebuilt: RunResult = session.execute(
            session.plan_auto(groups, preset, rebuild=RebuildRequest(frozenset({ProductKind.FULL_PL}))),
            CollectingRunSink(),
        )
        assert rebuilt.succeeded
        assert len(translation.calls) == 2
        assert moved.stat().st_ino == identity
        assert len(session.discover().groups) == 1
        assert all(product.path.startswith("ready/") for product in store.load().products)
        recorded: tuple[ReadyGroup, ...] = store.load().ready_groups
        assert len(recorded) == 1
        assert recorded[0].stem == "03"
        assert recorded[0].target is WorkflowTarget.VIDEO
        assert recorded[0].source_directory == "."
        assert recorded[0].source_stem == "03"
        assert recorded[0].sources == ("ready/03.txt",)
        assert recorded[0].products == ("ready/03.pl.srt",)
        assert recorded[0].main_result == "ready/03.pl.srt"


@pytest.mark.integration
def test_two_sets_named_alike_from_different_places_share_one_ready_without_mixing(tmp_path: Path) -> None:
    for folder in ("A", "B"):
        directory: Path = tmp_path / "translate" / folder
        directory.mkdir(parents=True)
        write_text_source(directory / "Book.txt", f"Text of {folder}")
    service: AppService = _service(tmp_path, FakeTranslationService())
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    with _panel_owner(service, tmp_path, ready=True) as (session, store):
        groups: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        assert len(groups) == 2
        session.reserve(groups)
        assert session.execute(session.plan_auto(groups, preset), CollectingRunSink()).succeeded
        deadline: float = time.monotonic() + 5.0
        while len(list((tmp_path / "ready").glob("*"))) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        names: list[str] = sorted(path.name for path in (tmp_path / "ready").iterdir())

    recorded: tuple[ReadyGroup, ...] = store.load().ready_groups
    assert names == ["Book [2].pl.txt", "Book [2].txt", "Book.pl.txt", "Book.txt"]
    assert len(recorded) == 2
    assert {item.source_directory for item in recorded} == {"translate/A", "translate/B"}
    assert {item.stem for item in recorded} == {"Book", "Book [2]"}
    assert all(item.source_stem == "Book" for item in recorded)
    for item in recorded:
        assert {Path(name).name.split(".")[0] for name in (*item.sources, *item.products)} == {item.stem}


def test_real_service_flows_from_discovery_through_partial_execution(tmp_path: Path) -> None:
    for name in ("Episode 1", "Episode 2", "Episode 3"):
        write_media_source(tmp_path / f"{name}.mkv")
    preset_store: list[AutoPresetFile] = [default_preset_file()]
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        preset_store=preset_store,
        inspector=WorkspaceInspector(FakeMediaProbe()),
    )
    workspace = service.discover()
    selected = workspace.groups[:2]
    draft = AutoPresetDraft(
        "preview",
        "Preview once",
        ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL})),
    )
    fail_group_id: str = selected[1].group_id
    service = _service(
        tmp_path,
        FakeTranslationService(),
        fail_group_id=fail_group_id,
        preset_store=preset_store,
        inspector=WorkspaceInspector(FakeMediaProbe()),
    )
    workspace = service.discover()
    selected = workspace.groups[:2]

    plan: ExecutionPlan = service.plan_auto(tuple(group.group_id for group in selected), draft)
    sink = CollectingRunSink()
    result: RunResult = service.execute(plan, sink)

    assert tuple(group.status for group in result.groups) == (GroupStatus.SUCCEEDED, GroupStatus.PARTIAL)
    assert (tmp_path / "Episode 1.pl.srt").is_file()
    assert (tmp_path / "Episode 1.spoken.pl.srt").is_file()
    assert (tmp_path / "Episode 2.pl.srt").is_file()
    assert not (tmp_path / "Episode 2.spoken.pl.srt").exists()
    assert not any((tmp_path / "temp").iterdir())
    assert service.list_presets() == default_preset_file().presets
    assert sink.events[0].kind.value == "run_started"
    assert sink.events[-1].kind.value == "run_finished"


def test_preview_draft_does_not_save_and_explicit_save_replaces_preset(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    store: list[AutoPresetFile] = [default_preset_file()]
    service: AppService = _service(tmp_path, FakeTranslationService(), preset_store=store)
    group_id: str = service.discover().groups[0].group_id
    draft = AutoPresetDraft("default", "Changed", ProductIntent(frozenset({ProductKind.SPOKEN_PL})))

    service.plan_auto((group_id,), draft)
    assert store[0] == default_preset_file()

    saved = service.save_preset(draft)
    assert store[0].presets == (saved,)


def test_active_run_rejects_a_second_execute_before_creating_another_scope(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    entered = threading.Event()
    release = threading.Event()
    service: AppService = _service(tmp_path, FakeTranslationService(entered=entered, release=release))
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    sink = CollectingRunSink()
    results: list[RunResult] = []
    thread = threading.Thread(target=lambda: results.append(service.execute(plan, sink)))
    thread.start()
    assert entered.wait(timeout=1.0)

    with pytest.raises(RunConflictError, match="already active"):
        service.execute(plan, CollectingRunSink())

    assert len(tuple((tmp_path / "temp").iterdir())) == 1
    assert service.cancel(sink.events[0].run_id)
    assert not service.cancel("another-run")
    release.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert len(results) == 1
    assert results[0].cancelled
    assert not any((tmp_path / "temp").iterdir())


def test_draining_retains_staging_and_protects_it_from_the_next_runs_cleanup(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    service: AppService = _service(tmp_path, FakeTranslationService(entered=entered, release=release))
    group_id: str = service.discover().groups[0].group_id
    preset: AutoPresetDraft = AutoPresetDraft(
        "preview",
        "Preview",
        ProductIntent(frozenset({ProductKind.FULL_PL})),
    )
    handle: RunHandle = service.submit_plan(
        service.plan_auto((group_id,), preset),
        CollectingRunSink(),
        origin=RequestOrigin.USER,
    )
    try:
        assert entered.wait(timeout=2.0)
        service.drain()
    finally:
        release.set()
    result: RunResult = handle.result(timeout=5.0)
    retained: Path = tmp_path / "temp" / handle.run_id
    staged: dict[Path, bytes] = {path: path.read_bytes() for path in retained.rglob("*") if path.is_file()}
    service.close()

    assert result.paused
    assert staged
    assert not service.active_run_ids()
    assert not (tmp_path / "Episode.pl.srt").exists()

    write_text_source(tmp_path / "Another.txt", "Other text")
    restarted: AppService = _service(tmp_path, FakeTranslationService())
    restarted.retain_runs((handle.run_id,))
    other_id: str = next(group.group_id for group in restarted.discover().groups if group.group_id != group_id)
    try:
        completed: RunResult = restarted.execute(restarted.plan_auto((other_id,), preset), CollectingRunSink())
    finally:
        restarted.close()

    assert completed.succeeded
    assert {path: path.read_bytes() for path in staged} == staged


def test_an_interrupted_execute_cancels_its_run_and_leaves_no_temporary_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    entered = threading.Event()
    release = threading.Event()
    service: AppService = _service(tmp_path, FakeTranslationService(entered=entered, release=release))
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    original: Callable[..., RunResult] = RunHandle.result
    interrupted: list[str] = []
    raised: list[BaseException] = []

    def once(self: RunHandle, timeout: float | None = None) -> RunResult:
        if threading.current_thread() is thread and not interrupted:
            assert entered.wait(timeout=5.0)
            interrupted.append(self.run_id)
            raise KeyboardInterrupt
        return original(self, timeout)

    def run() -> None:
        try:
            service.execute(plan, CollectingRunSink())
        except KeyboardInterrupt as interrupt:
            raised.append(interrupt)

    monkeypatch.setattr(RunHandle, "result", once)
    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(timeout=5.0)
    thread.join(timeout=0.5)
    waiting: bool = thread.is_alive()
    release.set()
    thread.join(timeout=10.0)

    assert waiting
    assert not thread.is_alive()
    assert len(raised) == 1
    assert service.active_run_ids() == ()
    assert not any((tmp_path / "temp").iterdir())


def test_two_submitted_plans_stay_independent_and_share_one_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_text_source(tmp_path / "Episode 1.txt", "Text")
    write_text_source(tmp_path / "Episode 2.txt", "Text")
    entered = threading.Event()
    release = threading.Event()
    service: AppService = _service(tmp_path, FakeTranslationService(entered=entered, release=release))
    groups = service.discover().groups
    draft = AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL})))
    first_plan: ExecutionPlan = service.plan_auto((groups[0].group_id,), draft)
    second_plan: ExecutionPlan = service.plan_auto((groups[1].group_id,), draft)
    cleaned: list[tuple[str, ...]] = []

    def spy(root: Path, *, active_run_ids: Collection[str]) -> tuple[Path, ...]:
        cleaned.append(tuple(active_run_ids))
        return cleanup_orphaned_temp(root, active_run_ids=active_run_ids)

    monkeypatch.setattr(service_module, "cleanup_orphaned_temp", spy)

    first: RunHandle = service.submit_plan(first_plan, CollectingRunSink(), origin=RequestOrigin.USER)
    assert entered.wait(timeout=2.0)
    second: RunHandle = service.submit_plan(second_plan, CollectingRunSink(), origin=RequestOrigin.BACKGROUND)
    try:
        assert set(cleaned[-1]) == {first.run_id, second.run_id}
        assert service.cancel(second.run_id)
        release.set()

        assert first.result(timeout=10.0).succeeded
        assert second.result(timeout=10.0).cancelled
        assert (tmp_path / "Episode 1.pl.srt").is_file()
        assert not (tmp_path / "Episode 2.pl.srt").exists()
        assert not any((tmp_path / "temp").iterdir())

        replayed: RunResult = service.execute(second_plan, CollectingRunSink())
        assert replayed.succeeded
        assert (tmp_path / "Episode 2.pl.srt").is_file()
    finally:
        service.close()


def test_settings_draft_and_plan_snapshot_are_detached(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    group_id: str = service.discover().groups[0].group_id
    draft = service.settings_snapshot()
    draft.translation_concurrency = 3
    draft.tts_voice_profiles = {
        key: replace(profile, postprocess_tempo=1.5) for key, profile in draft.tts_voice_profiles.items()
    }
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )

    service.save_settings(draft)

    assert plan.settings.translation_concurrency == 1
    assert plan.settings.llm_max_concurrency == 4
    assert plan.settings.tts_postprocess_tempo == 1.25
    assert plan.settings.tts_voice_label == "Dallin"
    assert plan.settings.tts_group_jobs == 1
    assert plan.settings.tts_request_concurrency == 85
    assert plan.settings.processing_order_policy is ProcessingOrderPolicy.READY_FIRST
    assert service.settings_snapshot().translation_concurrency == 3


def test_service_rebuild_preview_preserves_files_and_run_only_settings(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    target: Path = tmp_path / "Episode.pl.srt"
    previous: bytes = b"1\n00:00:00,000 --> 00:00:01,000\nPrevious Polish text\n"
    target.write_bytes(previous)
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation)
    group_id: str = service.discover().groups[0].group_id
    preset: AutoPresetDraft = AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL})))
    preferences: UserSettings = service.settings_snapshot()
    stored_presets: tuple[AutoPreset, ...] = service.list_presets()

    ordinary: ExecutionPlan = service.plan_auto((group_id,), preset)
    forced: ExecutionPlan = service.plan_auto(
        (group_id,),
        preset,
        rebuild=RebuildRequest(frozenset({ProductKind.FULL_PL})),
        overrides={"tts_voice_id": "one-run-voice", "tts_postprocess_tempo": 1.5},
    )

    assert ordinary.tasks == ()
    assert forced.can_execute
    assert TaskKind.TRANSLATE_SUBTITLES in {task.kind for task in forced.tasks}
    assert forced.settings.tts_voice_id == "one-run-voice"
    assert forced.settings.tts_postprocess_tempo == 1.5
    assert target.read_bytes() == previous
    assert translation.calls == []
    assert service.settings_snapshot() == preferences
    assert service.list_presets() == stored_presets
    assert service.plan_auto((group_id,), preset).settings == ordinary.settings

    try:
        result: RunResult = service.execute(forced, CollectingRunSink())
        assert result.succeeded
        assert target.read_bytes() != previous
        assert len(translation.calls) == 1
    finally:
        service.close()


def test_failed_rebuild_preserves_previous_product(tmp_path: Path) -> None:
    write_media_source(tmp_path / "Episode.mkv")
    previous: bytes = b"1\n00:00:00,000 --> 00:00:01,000\nPrevious Polish text\n"
    (tmp_path / "Episode.pl.srt").write_bytes(previous)
    target: Path = tmp_path / "Episode.spoken.pl.srt"
    target.write_bytes(previous)
    inspector: WorkspaceInspector = WorkspaceInspector(FakeMediaProbe())
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=inspector)
    group_id: str = service.discover().groups[0].group_id
    service = _service(tmp_path, FakeTranslationService(), fail_group_id=group_id, inspector=inspector)
    service.discover()
    preset: AutoPresetDraft = AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.SPOKEN_PL})))
    plan: ExecutionPlan = service.plan_auto(
        (group_id,), preset, rebuild=RebuildRequest(frozenset({ProductKind.SPOKEN_PL}))
    )

    try:
        result: RunResult = service.execute(plan, CollectingRunSink())
        assert not result.succeeded
        assert target.read_bytes() == previous
        assert (tmp_path / "Episode.pl.srt").read_bytes() == previous
    finally:
        service.close()


def test_auto_plan_preserves_ready_first_four_file_llm_queue(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    preferences = UserSettings(
        translation_engine="llm",
        llm_max_concurrency=4,
        processing_order_policy="ready_first",
    )
    service: AppService = _service(tmp_path, FakeTranslationService(), user_settings=preferences)
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    limits: ResourceLimits = ResourceLimits.from_settings(plan.settings)

    assert plan.settings.processing_order_policy is ProcessingOrderPolicy.READY_FIRST
    assert limits.worker_limit("llm:gemini", plan.settings) == 4


def test_auto_keeps_legacy_single_episode_tts_with_provider_request_concurrency(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    group_id: str = service.discover().groups[0].group_id

    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    limits: ResourceLimits = ResourceLimits.from_settings(plan.settings)

    assert limits.worker_limit(f"tts:{plan.settings.tts_profile_id}", plan.settings) == 1
    assert plan.settings.tts_request_concurrency == 85


def test_auto_uses_the_legacy_extraction_pool_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(group_id=f"group-{index}", kind=TaskKind.EXTRACT_TRACKS) for index in range(6)
    )
    plan: ExecutionPlan = cast("ExecutionPlan", SimpleNamespace(tasks=tasks))
    monkeypatch.setattr(os, "cpu_count", lambda: 16)

    assert extraction_worker_count(len(extraction_group_ids(plan))) == 6


def test_engine_availability_exposes_reasons_without_secret_values(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, FakeTranslationService())

    statuses = {(item.domain, item.engine_id): item for item in service.engine_availability()}

    assert statuses["translation", "google"].is_available
    assert not statuses["translation", "deepl"].is_available
    assert statuses["translation", "deepl"].reason == "missing deepl_api_key; configure environment or open Tools"


def test_engine_availability_reports_the_palantir_token_in_both_directions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    connected: UserSettings = UserSettings(palantir_enrollment_base_url="https://example.palantirfoundry.com")
    without_token: AppService = _service(tmp_path, FakeTranslationService(), user_settings=connected)
    with_token: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        settings=Settings(_env_file=None, palantir_token=_PALANTIR_TOKEN),
        user_settings=connected,
    )

    missing = {(item.domain, item.engine_id): item for item in without_token.engine_availability()}
    ready = {(item.domain, item.engine_id): item for item in with_token.engine_availability()}

    assert not missing["llm", "palantir"].is_available
    assert missing["llm", "palantir"].reason == "missing palantir_token; configure environment or open Tools"
    assert ready["llm", "palantir"].is_available
    assert ready["llm", "palantir"].reason == "ready"
    assert _PALANTIR_TOKEN not in str(ready["llm", "palantir"])


def test_bootstrap_builds_the_shared_service_without_creating_provider_clients(tmp_path: Path) -> None:
    workspace_root: Path = tmp_path / "workspace"
    context: AppContext = bootstrap(
        settings=Settings(workspace_root=str(workspace_root), _env_file=None),
        create_dirs=False,
    )

    service: AppService = create_app_service(context)

    assert isinstance(service, AppService)
    assert not workspace_root.exists()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows writer sharing")
def test_inspection_waits_for_writers_and_reuses_video_after_subtitle_copy(tmp_path: Path) -> None:
    source: Path = tmp_path / "03.mkv"
    write_media_source(source)
    probe: _CountingProbe = _CountingProbe()
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(probe))
    with source.open("r+b"):
        for _ in range(3):
            assert service.discover(changed_paths=(source,)).pending_paths == (source,)
        assert probe.calls == 0
    assert service.discover(changed_paths=(source,)).pending_paths == ()
    assert probe.calls == 1
    subtitles: Path = tmp_path / "03.srt"
    write_text_source(subtitles, "1\n00:00:00,000 --> 00:00:01,000\nNew subtitles\n")
    with subtitles.open("r+b"):
        assert service.discover(changed_paths=(subtitles,)).pending_paths == (subtitles,)
        assert probe.calls == 1
    assert service.discover(changed_paths=(subtitles,)).pending_paths == ()
    assert probe.calls == 1


class _CountingProbe(FakeMediaProbe):
    def __init__(self) -> None:
        self.calls: int = 0

    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        self.calls += 1
        return super().identify(path, cancel=cancel, timeout_s=timeout_s)


def test_discovery_of_unchanged_files_reuses_the_previous_inspection(tmp_path: Path) -> None:
    write_media_source(tmp_path / "Episode 1.mkv")
    probe = _CountingProbe()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        inspector=WorkspaceInspector(cast("DefaultMediaProbe", probe)),
    )

    first = service.discover()
    second = service.discover()

    assert probe.calls == 1
    assert second is first


def test_a_changed_workspace_file_forces_a_new_inspection(tmp_path: Path) -> None:
    source: Path = tmp_path / "Episode 1.mkv"
    write_media_source(source)
    probe = _CountingProbe()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        inspector=WorkspaceInspector(cast("DefaultMediaProbe", probe)),
    )
    service.discover()

    source.write_bytes(b"fake media with a different size")
    service.discover()

    assert probe.calls == 2


def test_a_new_episode_is_inspected_without_probing_unchanged_episodes(tmp_path: Path) -> None:
    write_media_source(tmp_path / "Episode 1.mkv")
    probe = _CountingProbe()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        inspector=WorkspaceInspector(cast("DefaultMediaProbe", probe)),
    )
    service.discover()

    write_media_source(tmp_path / "Episode 2.mkv")
    workspace = service.discover()

    assert probe.calls == 2
    assert len(workspace.groups) == 2


def test_later_subtitles_are_inspected_without_probing_the_same_media_again(tmp_path: Path) -> None:
    write_media_source(tmp_path / "Episode 1.mkv")
    probe = _CountingProbe()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        inspector=WorkspaceInspector(cast("DefaultMediaProbe", probe)),
    )
    service.discover()
    subtitle: Path = tmp_path / "Episode 1.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

    updated = service.discover()
    assert probe.calls == 1
    assert any(artifact.path == subtitle for artifact in updated.groups[0].artifacts)

    subtitle.unlink()
    removed = service.discover()
    assert probe.calls == 1
    assert all(artifact.path != subtitle for artifact in removed.groups[0].artifacts)


def test_replacing_one_episode_only_invalidates_its_own_inspection(tmp_path: Path) -> None:
    for number in (1, 2, 3):
        write_media_source(tmp_path / f"Episode {number}.mkv")
    probe = _CountingProbe()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        inspector=WorkspaceInspector(cast("DefaultMediaProbe", probe)),
    )
    first = service.discover()
    (tmp_path / "Episode 2.mkv").write_bytes(b"a different complete file")

    changed = service.discover()

    assert probe.calls == 4
    assert changed.groups[0] is first.groups[0]
    assert changed.groups[1] is not first.groups[1]
    assert changed.groups[2] is first.groups[2]


def test_discovery_can_cancel_while_prewarm_prepares_tools(tmp_path: Path) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    errors: list[ExecutionError] = []

    def prepare(discovery: DiscoveryResult, cancel: CancellationToken) -> None:
        entered.set()
        assert release.wait(timeout=2.0)

    service: AppService = _service(tmp_path, FakeTranslationService(), prepare_workspace=prepare)
    token: EventCancellationToken = EventCancellationToken()

    def discover_cancelled() -> None:
        try:
            service.discover(cancel=token)
        except ExecutionError as error:
            errors.append(error)

    prewarm: threading.Thread = threading.Thread(target=service.discover)
    waiting: threading.Thread = threading.Thread(target=discover_cancelled)
    prewarm.start()
    try:
        assert entered.wait(timeout=1.0)
        waiting.start()
        token.cancel()
        waiting.join(timeout=1.0)
        assert not waiting.is_alive()
        assert len(errors) == 1
        assert errors[0].context.code is ErrorCode.CANCELLED
    finally:
        release.set()
        prewarm.join(timeout=1.0)
        waiting.join(timeout=1.0)

    assert not prewarm.is_alive()


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows native resident file notifications")
def test_the_resident_processes_a_new_file_once_and_returns_to_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    workspace: Path = tmp_path / "workspace"
    (workspace / TRANSLATE_DIRECTORY).mkdir(parents=True)
    state_dir: Path = tmp_path / "watch"
    translation: FakeTranslationService = FakeTranslationService()
    preset: AutoPresetDraft = AutoPresetDraft("watch", "Watch", ProductIntent(frozenset({ProductKind.FULL_PL})))
    service: AppService = _service(
        workspace, translation, preset_store=[AutoPresetFile(1, (preset.to_preset(),), "watch")]
    )
    original: Callable[..., InspectedWorkspace] = service.discover
    scans: list[Sequence[Path] | None] = []

    def discover(
        *,
        cancel: CancellationToken | None = None,
        changed_paths: Sequence[Path] | None = None,
    ) -> InspectedWorkspace:
        scans.append(changed_paths)
        return original(cancel=cancel, changed_paths=changed_paths)

    monkeypatch.setattr(service, "discover", discover)
    ready: threading.Event = threading.Event()
    thread: threading.Thread = threading.Thread(
        target=lambda: run_resident(service, state_dir=state_dir, on_ready=ready.set, scan_interval_s=0.01)
    )
    thread.start()
    assert ready.wait(timeout=5.0)
    client: ControlClient | None = connect(state_dir)
    assert client is not None
    store: WatchStateStore = WatchStateStore(state_dir / WATCH_STATE_FILE_NAME)
    try:
        client.call("set_auto", {"enabled": True})
        write_text_source(workspace / TRANSLATE_DIRECTORY / "Episode.txt", "One episode")
        deadline: float = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            status: Mapping[str, object] = client.call("status")
            if (workspace / "ready/Episode.pl.txt").is_file() and not status["requests"] and not status["relocations"]:
                break
            time.sleep(0.01)
        assert (workspace / "ready/Episode.pl.txt").is_file()
        assert len(translation.calls) == 1
        (workspace / "ready/Episode.pl.txt").touch()
        time.sleep(0.1)
        settled: int = len(scans)
        time.sleep(0.1)
        assert len(scans) == settled
        assert len(translation.calls) == 1
        assert not service.active_run_ids()
    finally:
        client.call("shutdown")
        client.close()
        thread.join(timeout=5.0)
        service.close()
    assert not thread.is_alive()
    requests: tuple[ProcessingRequest, ...] = store.load().requests
    assert len(requests) == 1
    assert requests[0].state is RequestState.SUCCEEDED
    assert requests[0].automatic
