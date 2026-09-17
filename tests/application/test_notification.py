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
from anishift.application.service import AppService
from anishift.application.watch_state import WatchStateStore
from anishift.errors import ExecutionError
from anishift.platform import tray as tray_module
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import ControlResponse
from anishift.platform.tray import TrayIcon, _Message
from anishift.services.translation.types import FileTranslation


@contextmanager
def _notifications(
    service: AppService, store: WatchStateStore
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
        ready_store=ReadyStore(service.workspace_root / ".control" / "relocations", service.workspace_root),
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
        for frame in frames:
            tray.notify(str(frame["title"]), str(frame["message"]), str(frame["notification_id"]))
        for index, frame in enumerate(frames):
            tray._submit_balloon(lambda _balloon: True)
            tray._balloon_event(_Message.BALLOON_SHOW, 1)
            tray._balloon_event(_Message.BALLOON_CLICK, 1)
            assert owner.handle(_request("status")).ok
            assert len(opened) == index + 1
            assert opened[-1].name == f"{frame['message']}.pl.srt"
        tray._window = 0
        tray.close()
        assert sorted(path.name for path in opened) == ["One.pl.srt", "Two.pl.srt"]
        assert all(path.parent == tmp_path / "ready" and path.is_file() for path in opened)
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
        assert [path.name for path in opened] == ["One.pl.srt"]
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
            assert not panels
            assert opened == [path]
        else:
            assert "Bibliote" in str(status.result["notification_problem"])
            assert panels == ["Home"]
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
        assert opened == [tmp_path / product.path]
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
        assert opened == [tmp_path / "ready" / "One.pl.srt"]
        assert opened[0].is_file()
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
        assert opened == [tmp_path / "ready" / "One.pl.srt"]
        assert opened[0].is_file()


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
            assert opened == ([] if changed else [product])
        independent.result(timeout=1.0)
        assert bool(owner.handle(_request("status")).result["notification_problem"]) is changed


def test_missing_windows_directory_refuses_notification_and_owner_answers_the_next_command(
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
        assert "Bibliote" in str(status.result["notification_problem"])
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
        assert opened == [tmp_path / "ready" / "One.pl.srt"]


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
            notice: str = "Windows nie wskazał powiadomienia. Otwórz wynik w Bibliotece"
            assert status.result["notification_problem"] == notice
            assert {"event": "panel_open", "payload": {"notification_problem": notice}} in desktop_frames
            assert not opened
            owner.tray_action("open")
            assert owner.handle(_request("status")).result["notification_problem"] is None
            assert {"event": "panel_open", "payload": {}} in desktop_frames
        finally:
            tray._window = 0
            tray.close()
