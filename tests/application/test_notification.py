from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from secrets import token_hex
from typing import cast
from unittest.mock import Mock

import pytest
from fakes import FakeMediaProbe, FakeTranslationService, write_media_source, write_text_source
from test_automation import _INSTANCE, _await, _completed_library, _owned, _request, _serving
from test_service import _service

import anishift.application.automation as automation_module
import anishift.application.watch as watch_module
from anishift.application.artifacts import SourceGroup
from anishift.application.automation import AutomationOwner, _NotificationTarget
from anishift.application.control import (
    AutomationPolicy,
    ProcessingRequest,
    ProductConfirmation,
    ReadyGroup,
    RecipePreferences,
    RequestState,
    SourceSelection,
    TextResultFormat,
    TranslateRecipe,
    WatchState,
)
from anishift.application.control_views import LibraryFileIdentity, encode_view
from anishift.application.events import RunEvent, RunEventKind
from anishift.application.inspection import WorkspaceInspector
from anishift.application.intents import (
    AutoPreset,
    GroupIntent,
    ProductIntent,
    ProductKind,
    RebuildRequest,
    RequestOrigin,
    RunMode,
)
from anishift.application.library import file_identity
from anishift.application.planning import TaskState
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.recovery import RunJournal
from anishift.application.results import DISPLAYED_ABSENCE_NOTE
from anishift.application.service import AppService
from anishift.application.watch_state import WatchStateStore
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.state import StateController, _library_rows, _Tab
from anishift.cli.resident import ResidentSession
from anishift.config.presets import AutoPresetFile
from anishift.errors import ExecutionError
from anishift.platform import tray as tray_module
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import (
    ControlClient,
    ControlRequest,
    ControlResponse,
    ControlServer,
    control_endpoint,
)
from anishift.platform.tray import TrayIcon, _Message
from anishift.services.translation.types import FileTranslation


@contextmanager
def _notifications(
    service: AppService, store: WatchStateStore, *, ready: bool = True
) -> Iterator[tuple[AutomationOwner, list[Mapping[str, object]], list[Path]]]:
    frames: list[Mapping[str, object]] = []
    opened: list[Path] = []

    def broadcast(frame: Mapping[str, object], _terminal: bool) -> None:
        if frame.get("event") == "notification":
            frames.append(cast("Mapping[str, object]", frame["payload"]))

    owner: AutomationOwner = AutomationOwner(
        service,
        store,
        instance_id=_INSTANCE,
        broadcast=broadcast,
        open_result=opened.append,
        ready_store=ReadyStore(service.workspace_root / ".control" / "relocations", service.workspace_root)
        if ready
        else None,
    )
    thread: threading.Thread = _serving(owner)
    try:
        yield owner, frames, opened
    finally:
        owner.request_shutdown()
        thread.join(5.0)
        service.close()
        assert not thread.is_alive()


def _start(
    owner: AutomationOwner,
    service: AppService,
    *,
    rebuild: bool = False,
    auto: bool = False,
    products: frozenset[ProductKind] = frozenset({ProductKind.FULL_PL}),
) -> str:
    identifier: str = token_hex(8)
    groups: tuple[str, ...] = tuple(group.group_id for group in service.discover().groups)
    intents: list[dict[str, object]] = [
        encode_view(GroupIntent(group_id, RunMode.MANUAL, ProductIntent(products))) for group_id in groups
    ]
    payload: dict[str, object] = {
        "client_id": "notification-test",
        "group_ids": list(groups),
        "source_selection": "manual",
        "intents": intents,
    }
    if rebuild or auto:
        payload.pop("intents")
        payload["source_selection"] = "auto"
        payload["preset"] = encode_view(AutoPreset("notification", "Notification", ProductIntent(products)))
        if rebuild:
            payload["rebuild"] = encode_view(RebuildRequest(products))
    preview: ControlResponse = owner.handle(_request("preview", payload, command_id=f"preview-{identifier}"))
    assert preview.ok, preview
    answer: ControlResponse = owner.handle(
        _request(
            "start",
            {"client_id": "notification-test", "preview_id": preview.result["preview_id"]},
            command_id=f"start-{identifier}",
        )
    )
    assert answer.ok, answer
    return str(answer.result["run_id"])


def test_real_completion_notifies_only_after_ready_and_does_not_repeat_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    write_text_source(tmp_path / "translate" / "Two.txt", "Second text")
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    service: AppService = _service(tmp_path, FakeTranslationService())
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 2)
        assert len(owner.state.ready_groups) == 2
        monkeypatch.setattr(TrayIcon, "_run", lambda self: self._ready.set())
        tray: TrayIcon = TrayIcon(owner.tray_action)
        tray._window = 1
        tray._arm_timer = lambda _identifier: 1
        selected: list[str] = []
        for frame in frames:
            tray.notify(str(frame["title"]), str(frame["message"]), str(frame["notification_id"]))
        for frame in frames:
            tray._submit_balloon(lambda _balloon: True)
            tray._balloon_event(_Message.BALLOON_SHOW, 1)
            tray._balloon_event(_Message.BALLOON_CLICK, 1)
            assert owner.handle(_request("status")).ok
            panel_id: str = f"panel-{frame['notification_id']}"
            navigation: Mapping[str, object] = cast(
                "Mapping[str, object]",
                owner.handle(replace(_request("panel_attach"), session_id=panel_id)).result["navigation"],
            )
            selected.append(str(navigation["set_id"]))
            record: ReadyGroup = next(item for item in owner.state.ready_groups if item.set_id == selected[-1])
            assert record.stem == frame["message"]
            owner.disconnect(panel_id)
            assert owner.handle(_request("status")).ok
        tray._window = 0
        tray.close()
        assert len(set(selected)) == 2
        assert not opened
        assert len(store.load().notified) == 2
        expired: str = str(frames[0]["notification_id"])
    restarted: AppService = _service(tmp_path, FakeTranslationService())
    with _notifications(restarted, store) as (owner, frames, opened):
        owner.files_changed(DirectoryChange(reconcile=True))
        assert _await(lambda: owner.handle(_request("status")).result.get("watch_mode") != "inactive")
        owner._queue.put(lambda: owner._notify_ready_results(tuple(item.group_id for item in owner.state.ready_groups)))
        assert owner.handle(_request("status")).ok
        assert not frames
        assert not opened
        assert len(store.load().notified) == 2
        owner.tray_action(f"notification:{expired}")
        assert owner.handle(_request("status")).result["notification_problem"]
        assert not opened


def _failing_translation(monkeypatch: pytest.MonkeyPatch, text: str) -> FakeTranslationService:
    translation: FakeTranslationService = FakeTranslationService()
    translate: Callable[..., FileTranslation] = translation.translate_file

    def selected(*args: object, **kwargs: object) -> FileTranslation:
        if text in str(args[0]):
            raise ExecutionError("Synthetic translation failure")
        return translate(*args, **kwargs)

    monkeypatch.setattr(translation, "translate_file", Mock(side_effect=selected))
    return translation


def _reconcile_automatic(owner: AutomationOwner) -> None:
    owner.files_changed(DirectoryChange(reconcile=True))
    assert owner.handle(_request("status")).ok
    assert _await(
        lambda: owner._on_owner(lambda: owner._library is not None and not owner._inspecting and not owner._recovering)
    )
    owner._on_owner(owner._refresh_automatic)


@pytest.mark.parametrize("terminal", [RequestState.FAILED, RequestState.PARTIAL])
@pytest.mark.parametrize("followup", ["rebuild", "resume", "changed_source"])
@pytest.mark.parametrize("automatic", [False, True])
def test_terminal_failure_stays_stopped_on_reconcile_and_owner_restart(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, terminal: RequestState, followup: str, *, automatic: bool
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.0)
    write_media_source(tmp_path / "One.mkv")
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    translation: FakeTranslationService = FakeTranslationService()
    translate: Mock = Mock(wraps=translation.translate_file)
    monkeypatch.setattr(translation, "translate_file", translate)
    preset: AutoPreset = AutoPreset(
        "notification", "Notification", ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
    )
    presets: list[AutoPresetFile] = [AutoPresetFile(1, (preset,), preset.preset_id)]
    service: AppService = _service(
        tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()), preset_store=presets
    )
    original_replace: Callable[[Path, Path], Path] = Path.replace
    published: list[Path] = []

    def fail_second_product(source: Path, destination: Path) -> Path:
        if destination.parent == tmp_path and destination.name.endswith(".pl.srt"):
            if published:
                raise OSError("Synthetic publication failure")
            published.append(destination)
        return original_replace(source, destination)

    with _notifications(service, store) as (owner, frames, _opened):
        with monkeypatch.context() as failure:
            if terminal is RequestState.FAILED:
                translate.side_effect = ExecutionError("Synthetic translation failure")
            else:
                failure.setattr(Path, "replace", fail_second_product)
            if automatic:
                _reconcile_automatic(owner)
            else:
                _start(owner, service, auto=True, products=preset.products.requested_products)
            assert _await(lambda: bool(owner.state.requests) and owner.state.requests[0].state is terminal)
            run_id: str = owner.state.requests[0].request_id
        assert owner.handle(_request("status")).ok
        assert owner.state.requests[0].problem is None
        assert len(frames) == 1
        assert frames[0]["title"] == "Materiał wymaga uwagi"
        calls: int = translate.call_count
        _reconcile_automatic(owner)
        assert [item.request_id for item in owner.state.requests] == [run_id]
        assert translate.call_count == calls
        assert len(frames) == 1
    restarted: AppService = _service(
        tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()), preset_store=presets
    )
    with _notifications(restarted, store) as (owner, frames, _opened):
        _reconcile_automatic(owner)
        assert [item.request_id for item in owner.state.requests] == [run_id]
        assert translate.call_count == calls
        assert not frames
        translate.side_effect = None
        if followup == "changed_source":
            write_text_source(tmp_path / "One.srt", "1\n00:00:00,000 --> 00:00:01,000\nChanged text\n")
            _reconcile_automatic(owner)
            assert len(owner.state.requests) == 2
        elif followup == "resume":
            preview: ControlResponse = owner.handle(
                _request(
                    "preview",
                    {
                        "client_id": "notification-test",
                        "group_ids": list(owner.state.requests[0].group_ids),
                        "resume_run_id": run_id,
                    },
                    command_id="resume-preview",
                )
            )
            assert preview.ok, preview
            command: ControlRequest = _request(
                "start",
                {"client_id": "notification-test", "preview_id": preview.result["preview_id"]},
                command_id="resume-start",
            )
            response: ControlResponse = owner.handle(command)
            assert response.ok
            assert response.result["run_id"] == run_id
            assert owner.handle(command) == response
        else:
            retry_id: str = _start(
                owner, restarted, rebuild=True, products=frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL})
            )
            assert retry_id != run_id
        assert _await(lambda: owner.state.requests[-1].state is RequestState.SUCCEEDED)
        if terminal is RequestState.FAILED or followup == "rebuild":
            assert translate.call_count > calls


def test_successful_group_in_failed_run_can_regenerate_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.0)
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    write_text_source(tmp_path / "translate" / "Two.txt", "Second text")
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            recipes=RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.SUBTITLES)),
        )
    )
    service: AppService = _service(tmp_path, _failing_translation(monkeypatch, "Second text"))
    with _notifications(service, store, ready=False) as (owner, _frames, _opened):
        run_id: str = _start(owner, service)
        assert _await(lambda: bool(owner.state.requests) and owner.state.requests[0].state is RequestState.FAILED)
    (tmp_path / "translate" / "One.pl.srt").unlink()
    translation: FakeTranslationService = FakeTranslationService()
    restarted: AppService = _service(tmp_path, translation)
    with _notifications(restarted, store, ready=False) as (owner, frames, _opened):
        _reconcile_automatic(owner)
        assert _await(
            lambda: len(owner.state.requests) == 2 and owner.state.requests[-1].state is RequestState.SUCCEEDED
        )
        assert owner.state.requests[0].request_id == run_id
        assert translation.calls == [("First text",)]
        assert not frames


@pytest.mark.parametrize("ready", [False, True])
def test_displayed_only_absence_is_noop_and_does_not_restart_unchanged_sources(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, ready: bool
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.0)
    write_media_source(tmp_path / "One.mkv")
    (tmp_path / "One.pl.srt").write_bytes((tmp_path / "One.srt").read_bytes())
    original: bytes = (tmp_path / "One.mkv").read_bytes()
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    preset: AutoPreset = AutoPreset("signless", "Signless", ProductIntent(frozenset({ProductKind.DISPLAYED_PL})))
    presets: list[AutoPresetFile] = [AutoPresetFile(1, (preset,), preset.preset_id)]
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(
        tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()), preset_store=presets
    )
    with _notifications(service, store, ready=ready) as (owner, frames, _opened):
        _reconcile_automatic(owner)
        assert _await(lambda: bool(owner.state.requests) and owner.state.requests[0].state is RequestState.SUCCEEDED)
        run_id: str = owner.state.requests[0].request_id
        assert owner.state.products == ()
        assert owner.state.ready_groups == ()
        response: ControlResponse = owner.handle(_request("run_result", {"run_id": run_id}))
        assert response.result["result"]["warnings"] == [DISPLAYED_ABSENCE_NOTE]  # type: ignore[index]
        assert not frames
        assert not owner._on_owner(lambda: owner._ready_library)
        _reconcile_automatic(owner)
        assert len(owner.state.requests) == 1
    restarted: AppService = _service(
        tmp_path, translation, inspector=WorkspaceInspector(FakeMediaProbe()), preset_store=presets
    )
    with _notifications(restarted, store, ready=ready) as (owner, frames, _opened):
        _reconcile_automatic(owner)
        assert [request.request_id for request in owner.state.requests] == [run_id]
        loaded: list[str] = []
        original_load: Callable[[Path], RunJournal] = RunJournal.load

        def observed_load(path: Path) -> RunJournal:
            loaded.append(threading.current_thread().name)
            return original_load(path)

        monkeypatch.setattr(RunJournal, "load", observed_load)
        for _ in range(3):
            owner._on_owner(owner._refresh_automatic)
        assert loaded == []
        for _ in range(3):
            _reconcile_automatic(owner)
        assert loaded == []
        response = owner.handle(_request("run_result", {"run_id": run_id}))
        assert response.result["result"]["warnings"] == [DISPLAYED_ABSENCE_NOTE]  # type: ignore[index]
        journal_path: Path = store.run_path(run_id)
        journal_path.write_bytes(journal_path.read_bytes() + b"\n")
        _reconcile_automatic(owner)
        assert loaded
        assert all(name != "anishift-owner" for name in loaded)
        assert len(owner.state.requests) == 1
        assert not owner.state.ready_groups
        assert not frames
        assert (tmp_path / "One.mkv").read_bytes() == original
        assert not (tmp_path / "One.displayed.pl.srt").exists()
        assert translation.calls == []
        (tmp_path / "One.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nChanged\n", encoding="utf-8")
        _reconcile_automatic(owner)
        assert _await(lambda: len(owner.state.requests) == 2)


def test_signless_regeneration_retains_existing_good_library_product(tmp_path: Path) -> None:
    write_media_source(tmp_path / "One.mkv")
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(FakeMediaProbe()))
    with _notifications(service, store) as (owner, frames, _opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        original: ReadyGroup = owner.state.ready_groups[0]
        assert original.main_result is not None
        original_bytes: bytes = (tmp_path / original.main_result).read_bytes()
        _start(owner, service, rebuild=True, products=frozenset({ProductKind.DISPLAYED_PL}))
        assert _await(
            lambda: len(owner.state.requests) == 2 and owner.state.requests[-1].state is RequestState.SUCCEEDED
        )
        assert owner.state.ready_groups[0].main_result == original.main_result
        assert (tmp_path / original.main_result).read_bytes() == original_bytes
        assert all(record.available for record in owner._on_owner(lambda: owner._ready_library))


def test_partial_manual_notifies_the_success_and_reports_the_failed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    write_text_source(tmp_path / "translate" / "Two.txt", "Second text")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    translation: FakeTranslationService = FakeTranslationService()
    translate: Callable[..., FileTranslation] = translation.translate_file

    def selected(*args: object, **kwargs: object) -> FileTranslation:
        if "Second text" in str(args[0]):
            entered.set()
            assert release.wait(5.0)
            raise ExecutionError("Synthetic translation failure")
        return translate(*args, **kwargs)

    monkeypatch.setattr(translation, "translate_file", Mock(side_effect=selected))
    service: AppService = _service(tmp_path, translation)
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened):
        try:
            _start(owner, service)
            assert entered.wait(5.0)
            assert _await((tmp_path / "translate" / "One.pl.srt").is_file)
            assert owner.handle(_request("status")).ok
            assert not frames
            assert not owner.state.ready_groups
        finally:
            release.set()
        assert _await(lambda: len(frames) == 2)
        successes: list[Mapping[str, object]] = [frame for frame in frames if frame["title"] == "Gotowy materiał"]
        assert len(successes) == 1
        assert successes[0]["message"] == "One"
        owner.tray_action(f"notification:{successes[0]['notification_id']}")
        assert owner.handle(_request("status")).ok
        navigation: Mapping[str, object] = cast(
            "Mapping[str, object]",
            owner.handle(replace(_request("panel_attach"), session_id="panel")).result["navigation"],
        )
        assert navigation["set_id"] == owner.state.ready_groups[0].set_id
        assert not opened
        assert any(frame["title"] == "Materiał wymaga uwagi" for frame in frames)


@pytest.mark.parametrize("fail", [False, True])
def test_inline_regeneration_notifies_only_its_successful_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            recipes=RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.SUBTITLES)),
        )
    )
    service: AppService = _service(tmp_path, FakeTranslationService())
    with _notifications(service, store) as (owner, frames, _opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        old: bytes = (tmp_path / "ready" / "One.pl.srt").read_bytes()
    service = _service(tmp_path, _failing_translation(monkeypatch, "First text") if fail else FakeTranslationService())
    with _notifications(service, store) as (owner, frames, _opened):
        _start(owner, service, rebuild=True)
        assert _await(lambda: len(frames) == 1)
        assert frames[0]["title"] == ("Materiał wymaga uwagi" if fail else "Gotowy materiał")
        assert len(owner.state.ready_groups) == 1
        assert len(owner.state.notified) == 2
        if fail:
            assert (tmp_path / "ready" / "One.pl.srt").read_bytes() == old


@pytest.mark.parametrize("change", ["none", "missing", "replaced", "generation", "attempt", "unknown", "ambiguous"])
def test_notification_refuses_changed_missing_or_unidentified_results_with_a_visible_hint(
    tmp_path: Path, change: str
) -> None:
    service, store, state = _completed_library(tmp_path)
    product: ProductConfirmation = state.products[0]
    request: ProcessingRequest = ProcessingRequest(
        product.request_id,
        product.generation,
        (product.group_id,),
        {},
        product.origin,
        SourceSelection.MANUAL,
        None,
        {},
        RequestState.SUCCEEDED,
        1,
        "2026-09-17T12:00:00+00:00",
    )
    state = replace(state, requests=(request,))
    store.save(state)
    opened: list[Path] = []
    panels: list[str] = []
    owner: AutomationOwner = AutomationOwner(
        service, store, instance_id=_INSTANCE, open_result=opened.append, open_panel=lambda: panels.append("Home")
    )
    record: ReadyGroup = state.ready_groups[0]
    identity: LibraryFileIdentity | None = file_identity(tmp_path, product.path)
    assert identity is not None
    owner._publish_notification(
        "Ready", "One", _NotificationTarget(record.set_id, product, identity, (product.request_id, product.generation))
    )
    identifier: str = next(iter(owner._notification_targets))
    path: Path = tmp_path / product.path
    if change == "missing":
        path.unlink()
    elif change == "replaced":
        replacement: Path = tmp_path / "replacement"
        replacement.write_bytes(path.read_bytes())
        os.utime(replacement, ns=(identity.modified_ns, identity.modified_ns))
        replacement.replace(path)
    elif change == "generation":
        owner._state = replace(state, products=(replace(product, generation=product.generation + 1),))
    elif change == "attempt":
        owner._state = replace(state, requests=(replace(request, generation=request.generation + 1),))
    elif change == "unknown":
        identifier = "previous-owner-id"
    elif change == "ambiguous":
        identifier = ""
    thread: threading.Thread = _serving(owner)
    try:
        owner.tray_action(f"notification:{identifier}")
        status: ControlResponse = owner.handle(_request("status"))
        if change == "none":
            assert status.result["notification_problem"] is None
            assert panels == ["Home"]
        else:
            assert bool(status.result["notification_problem"]) is (change != "ambiguous")
            assert panels == ["Home"]
            assert not opened
        navigation: Mapping[str, object] = cast(
            "Mapping[str, object]",
            owner.handle(replace(_request("panel_attach"), session_id="panel")).result["navigation"],
        )
        assert navigation["tab"] == "library"
        assert navigation.get("set_id") == (record.set_id if change == "none" else None)
        assert not opened
    finally:
        owner.request_shutdown()
        thread.join(5.0)
        service.close()
        assert not thread.is_alive()


def test_group_finished_cannot_claim_ready_before_confirmation(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    owner: AutomationOwner = AutomationOwner(service, store, instance_id=_INSTANCE)
    owner._notify_group(
        RunEvent(
            "new-attempt",
            1,
            RunEventKind.GROUP_FINISHED,
            group_id=state.ready_groups[0].group_id,
            state=TaskState.SUCCEEDED,
        )
    )
    assert owner.state.notified == frozenset()
    assert not owner._notification_targets
    owner._pool.shutdown()
    service.close()


def test_new_products_notify_once_and_a_cache_only_run_does_not_repeat(tmp_path: Path) -> None:
    write_media_source(tmp_path / "One.mkv")
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(FakeMediaProbe()))
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened):
        first: str = _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        second: str = _start(owner, service, products=frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
        assert _await(lambda: len(frames) == 2)
        assert first != second
        record: ReadyGroup = owner.state.ready_groups[0]
        product: ProductConfirmation = next(item for item in owner.state.products if item.path == record.main_result)
        assert product.request_id == second
        owner.tray_action(f"notification:{frames[-1]['notification_id']}")
        assert owner.handle(_request("status")).ok
        assert owner._pending_panel_open == {"tab": "library", "set_id": record.set_id}
        assert not opened
        third: str = _start(owner, service, auto=True, products=frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL}))
        assert _await(
            lambda: owner.handle(_request("run_result", {"run_id": third})).result.get("state") == "succeeded"
        )
        assert len(frames) == 2
        assert len(owner.state.notified) == 2


def test_failed_notification_receipt_does_not_change_processing_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    save: Callable[[WatchState], None] = store.save

    def without_notifications(state: WatchState) -> None:
        if state.notified:
            raise OSError("Synthetic notification receipt failure")
        save(state)

    monkeypatch.setattr(store, "save", without_notifications)
    with _notifications(service, store) as (owner, frames, opened):
        run_id: str = _start(owner, service)
        assert _await(lambda: bool(owner.state.ready_groups))
        answer: ControlResponse = owner.handle(_request("run_result", {"run_id": run_id}))
        assert answer.result["state"] == "succeeded"
        assert (tmp_path / "ready" / "One.pl.srt").is_file()
        assert not frames
        assert not opened
        assert not store.load().notified


def test_evicted_notification_ids_refuse_instead_of_selecting_a_recent_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, _state = _completed_library(tmp_path)
    owner: AutomationOwner = AutomationOwner(service, store, instance_id=_INSTANCE)
    monkeypatch.setattr(automation_module, "_NOTIFICATION_LIMIT", 2)
    owner._publish_notification("Decision", "One", None)
    first: str = next(iter(owner._notification_targets))
    owner._publish_notification("Decision", "Two", None)
    owner._publish_notification("Decision", "Three", None)
    assert len(owner._notification_targets) == 2
    owner._open_notification(first)
    assert owner._status()["notification_problem"]
    owner._pool.shutdown()
    service.close()


def test_pending_source_does_not_delay_notification_or_exact_main_result_opening(tmp_path: Path) -> None:
    source: Path = tmp_path / "translate" / "One.txt"
    source.parent.mkdir()
    write_text_source(source, "First text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("One.txt", "Two.txt"), ("One.txt",), RequestOrigin.USER, source.stat().st_size),),
        )
    )
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        record: ReadyGroup = owner.state.ready_groups[0]
        assert record.pending_sources == ("translate/One.txt",)
        assert source.is_file()
        owner.tray_action(f"notification:{frames[0]['notification_id']}")
        assert owner.handle(_request("status")).ok
        assert owner._pending_panel_open == {"tab": "library", "set_id": record.set_id}
        assert not opened
        owner._queue.put(lambda: owner._notify_ready_results((record.group_id,)))
        assert owner.handle(_request("status")).ok
        assert len(frames) == 1


def test_inline_ready_completion_uses_library_provenance_without_a_relocation_record(tmp_path: Path) -> None:
    (tmp_path / "ready").mkdir()
    write_media_source(tmp_path / "ready" / "One.mkv")
    service: AppService = _service(tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(FakeMediaProbe()))
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        assert not owner.state.ready_groups
        owner.tray_action(f"notification:{frames[0]['notification_id']}")
        assert owner.handle(_request("status")).result["notification_problem"] is None
        assert owner._pending_panel_open == {"tab": "library", "set_id": owner._ready_library[0].set_id}
        assert not opened


@pytest.mark.parametrize("changed", [False, True])
def test_notification_inventory_and_click_do_not_block_owner_pause_behind_an_independent_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: bool,
) -> None:
    (tmp_path / "ready").mkdir()
    write_media_source(tmp_path / "ready" / "One.mkv")
    translating: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    inventory_entered: threading.Event = threading.Event()
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(entered=translating, release=release),
        inspector=WorkspaceInspector(FakeMediaProbe()),
    )
    inventory: Callable[[Sequence[Path] | None], tuple[SourceGroup, ...]] = service.library_inventory

    def observed_inventory(paths: Sequence[Path] | None = None) -> tuple[SourceGroup, ...]:
        inventory_entered.set()
        return inventory(paths)

    monkeypatch.setattr(service, "library_inventory", observed_inventory)
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened), ThreadPoolExecutor(max_workers=2) as clients:
        try:
            _start(owner, service)
            assert translating.wait(1.0)
            with service._discover_lock:
                release.set()
                assert inventory_entered.wait(1.0)
                answer: ControlResponse = clients.submit(
                    owner.handle,
                    _request("set_auto", {"enabled": False}, command_id="pause-during-offer"),
                ).result(timeout=1.0)
                assert answer.ok
                assert not frames
        finally:
            release.set()
        assert _await(lambda: len(frames) == 1)
        assert not owner.state.ready_groups
        product: Path = tmp_path / "ready" / "One.pl.srt"
        if changed:
            product.write_bytes(b"Replaced result")
        inventory_entered.clear()
        with service._discover_lock:
            independent: Future[tuple[SourceGroup, ...]] = clients.submit(service.library_inventory)
            assert inventory_entered.wait(1.0)
            owner.tray_action(f"notification:{frames[0]['notification_id']}")
            answer = clients.submit(
                owner.handle,
                _request("set_auto", {"enabled": False}, command_id="pause-after-click"),
            ).result(timeout=1.0)
            assert answer.ok
            assert not opened
            assert owner._pending_panel_open is not None
            assert owner._pending_panel_open.get("set_id") == (None if changed else owner._ready_library[0].set_id)
        independent.result(timeout=1.0)
        assert bool(owner.handle(_request("status")).result["notification_problem"]) is changed


def test_notification_navigation_does_not_require_explorer_and_owner_answers_the_next_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        launch: Mock = Mock()
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("SYSTEMROOT", raising=False)
        monkeypatch.setattr(subprocess, "Popen", launch)
        owner._open_result = lambda path: tray_module.open_path(path, show_folder=True)
        owner.tray_action(f"notification:{frames[0]['notification_id']}")
        answer: ControlResponse = owner.handle(_request("set_auto", {"enabled": False}))
        assert answer.ok
        status: ControlResponse = owner.handle(_request("status"))
        assert status.ok
        assert status.result["notification_problem"] is None
        assert owner._pending_panel_open == {"tab": "library", "set_id": owner.state.ready_groups[0].set_id}
        assert not opened
        launch.assert_not_called()


def test_previous_notification_cannot_open_the_next_regenerated_revision(tmp_path: Path) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            recipes=RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.SUBTITLES)),
        )
    )
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 1)
        _start(owner, service, rebuild=True)
        assert _await(lambda: len(frames) == 2)
        owner.tray_action(f"notification:{frames[0]['notification_id']}")
        assert owner.handle(_request("status")).result["notification_problem"]
        assert not opened
        owner.tray_action(f"notification:{frames[1]['notification_id']}")
        assert owner.handle(_request("status")).result["notification_problem"] is None
        assert owner._pending_panel_open == {"tab": "library", "set_id": owner.state.ready_groups[0].set_id}
        assert not opened


def test_legacy_success_receipt_still_suppresses_an_offer_after_relocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    execute: Callable[[ReadyStore, ReadyMove], None] = ReadyStore.execute

    def held(ready: ReadyStore, move: ReadyMove) -> None:
        entered.set()
        assert release.wait(5.0)
        execute(ready, move)

    monkeypatch.setattr(ReadyStore, "execute", held)
    with _notifications(service, store) as (owner, frames, _opened):
        try:
            run_id: str = _start(owner, service)
            assert entered.wait(5.0)
            assert owner.handle(_request("status")).ok
            assert not frames
            request: ProcessingRequest = owner.state.requests[0]
            key: tuple[str, str, str] = (
                request.group_ids[0],
                f"{run_id}:{request.generation}",
                str(TaskState.SUCCEEDED),
            )

            def record_receipt() -> None:
                assert owner._save(replace(owner.state, notified=frozenset({key})))

            owner._queue.put(record_receipt)
            assert owner.handle(_request("status")).ok
        finally:
            release.set()
        assert _await(lambda: bool(owner.state.ready_groups))
        assert owner.handle(_request("status")).ok
        assert not frames
        record: ReadyGroup = owner.state.ready_groups[0]
        assert owner.state.notified == frozenset({(record.group_id, key[1], key[2])})


def test_ambiguous_native_click_selects_nothing_and_requests_visible_panel_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    write_text_source(tmp_path / "translate" / "Two.txt", "Second text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 2)
        desktop_frames: list[Mapping[str, object]] = []
        owner.attach_broadcast(lambda frame, _terminal: desktop_frames.append(frame))
        assert owner.handle(replace(_request("panel_attach"), session_id="notification-panel")).ok
        monkeypatch.setattr(TrayIcon, "_run", lambda self: self._ready.set())
        tray: TrayIcon = TrayIcon(owner.tray_action)
        tray._window = 1
        tray._arm_timer = lambda _identifier: 1
        try:
            for frame in frames:
                tray.notify(str(frame["title"]), str(frame["message"]), str(frame["notification_id"]))
            tray._submit_balloon(lambda _balloon: True)
            tray._tray_event(1, (1 << 16) | _Message.BALLOON_SHOW)
            tray._tray_event(1, (1 << 16) | _Message.BALLOON_TIMEOUT)
            tray._submit_balloon(lambda _balloon: True)
            tray._tray_event(1, (1 << 16) | _Message.BALLOON_SHOW)
            tray._tray_event(1, (1 << 16) | _Message.BALLOON_CLICK)
            status: ControlResponse = owner.handle(_request("status"))
            assert status.result["notification_problem"] is None
            assert {"event": "panel_open", "payload": {"tab": "library"}} in desktop_frames
            assert not opened
            owner.tray_action("open")
            assert owner.handle(_request("status")).result["notification_problem"] is None
            assert {"event": "panel_open", "payload": {}} in desktop_frames
        finally:
            tray._window = 0
            tray.close()


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("change", ["valid", "unknown", "deleted", "deleted_before_attach"])
def test_notification_routes_through_owner_session_and_app_to_library(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, attached: bool, change: str
) -> None:
    (tmp_path / "translate").mkdir()
    write_text_source(tmp_path / "translate" / "One.txt", "First text")
    write_text_source(tmp_path / "translate" / "Two.txt", "Second text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    monkeypatch.setattr(interactive_app, "TerminalRenderer", Mock())
    monkeypatch.setattr(tray_module, "raise_panel", Mock())
    with _notifications(service, store) as (owner, frames, opened):
        _start(owner, service)
        assert _await(lambda: len(frames) == 2)
        frame: Mapping[str, object] = next(item for item in frames if item["message"] == "Two")
        record: ReadyGroup = next(item for item in owner.state.ready_groups if item.stem == "Two")
        assert record.main_result is not None
        launch: Mock = Mock()
        owner._open_panel = launch
        endpoint: str = control_endpoint(tmp_path / ".control")
        key: bytes = os.urandom(32)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        owner.attach_broadcast(server.broadcast)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(service)
        controller: StateController | None = None
        try:
            if attached:
                controller = StateController(session, lambda: None)
                application._state = controller
                assert _await(lambda: bool(owner._panels))
            if change == "deleted":
                (tmp_path / record.main_result).unlink()
            identifier: str = "" if change == "unknown" else str(frame["notification_id"])
            owner.tray_action(f"notification:{identifier}")
            assert owner.handle(_request("status")).ok
            if not attached:
                launch.assert_called_once_with()
                if change == "deleted_before_attach":
                    (tmp_path / record.main_result).unlink()
                controller = StateController(session, lambda: None)
                application._state = controller
            else:
                launch.assert_not_called()
            assert controller is not None
            assert _await(lambda: controller is not None and controller._open_requested is not None)
            application._handle_idle()
            assert application._mode is interactive_app._ViewMode.STATE
            assert controller._tab == _Tab.FILES
            assert _await(lambda: controller is not None and controller._connected)
            if change == "valid" or (attached and change == "deleted_before_attach"):
                assert _await(lambda: controller is not None and controller._library_target is None)
                assert _library_rows(controller._snapshot)[controller._selected]["set_id"] == record.set_id
            else:
                assert controller._library_target is None
                rows: list[Mapping[str, object]] = _library_rows(controller._snapshot)
                assert not rows or rows[controller._selected]["set_id"] != record.set_id
            owner.tray_action(f"notification:{identifier}")
            assert owner.handle(_request("status")).ok
            assert _await(lambda: controller is not None and controller._open_requested is not None)
            application._handle_idle()
            assert controller._library_target is None
            assert controller._tab == _Tab.FILES
            owner.tray_action("open")
            assert owner.handle(_request("status")).ok
            assert _await(lambda: controller is not None and controller._open_requested is not None)
            application._handle_idle()
            assert str(application._mode) == "home"
            assert not opened
        finally:
            if controller is not None:
                controller.close()
                controller._thread.join(5.0)
            application._mascot.close()
            session.close()
            server.close()
