from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Final, cast

import pytest
from fakes import write_text_source

import anishift.application.automation as automation_module
import anishift.application.watch as watch_module
from anishift.application.acquisition import AcquisitionService, TorrentClient
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    RequestState,
    SourceSelection,
    WatchState,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ProductIntent, ProductKind, RebuildRequest, RequestOrigin
from anishift.application.planning import ExecutionPlan
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.application.scheduler import RunHandle
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.application.subscriptions import (
    CheckRecorder,
    Subscription,
    SubscriptionAdmission,
    SubscriptionService,
    SubscriptionStore,
)
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.platform.directory_watch import DirectoryChange
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlRequest,
    ControlResponse,
    ControlServer,
    control_endpoint,
)
from anishift.services.media import DefaultMediaProbe
from anishift.services.torrents import Release, TorrentClientError, TorrentFile, TorrentInfo, parse_release_name
from anishift.services.torrents.categories import SEARCH_CATEGORIES

_TIMEOUT_S: Final[float] = 5.0

_INSTANCE: Final[str] = "instance-1"

_CLIENT: Final[str] = "panel-1"

_MOMENT: Final[datetime] = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

_PRESET: Final[AutoPresetDraft] = AutoPresetDraft(
    "preview",
    "Preview",
    ProductIntent(frozenset({ProductKind.FULL_PL})),
)


class _TorrentNetwork:
    def __init__(self) -> None:
        self.releases: tuple[Release, ...] = tuple(
            Release(
                title=f"[SubsPlease] Neko to Ryuu - {number:02d} (1080p)",
                torrent_url=f"https://example.test/{number}.torrent",
                info_hash=str(number),
                seeders=10,
                size_text="1 GiB",
                published=None,
                subtitle_language="en",
            )
            for number in (9, 10)
        )
        self.added: list[str] = []
        self.tracked: dict[str, TorrentInfo] = {}
        self.before_search: Callable[[], None] | None = None
        self.before_add: Callable[[], None] | None = None
        self.lose_response: bool = False
        self.entries: tuple[TorrentFile, ...] = ()
        self.info_calls: int = 0

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        del query, categories
        if self.before_search is not None:
            self.before_search()
        return self.releases

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        del category
        release: Release = next(item for item in self.releases if item.torrent_url == torrent_url)
        self.added.append(release.info_hash)
        if self.before_add is not None:
            self.before_add()
        self.tracked[release.info_hash] = TorrentInfo(
            release.title, release.info_hash, 0.1, "downloading", str(save_path)
        )
        if self.lose_response:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Response lost")
            )

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        del category
        self.info_calls += 1
        return tuple(self.tracked.values())

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        del info_hash
        return self.entries


class _Subscriptions:
    def __init__(self) -> None:
        self.entries: list[SimpleNamespace] = [
            SimpleNamespace(
                subscription_id="a",
                series="Series",
                group="Group",
                next_episode="3",
                enabled=True,
                end_state=SimpleNamespace(value="active"),
            )
        ]
        self.checks: int = 0

    def list(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.entries)

    def check_all(
        self,
        *,
        admit: SubscriptionAdmission | None = None,
        record: CheckRecorder | None = None,
    ) -> tuple[SimpleNamespace, ...]:
        del admit, record
        self.checks += 1
        return (SimpleNamespace(downloaded=2, problem=""),)

    def enable(self, subscription_id: str) -> SimpleNamespace:
        del subscription_id
        return SimpleNamespace(enabled=True)

    def disable(self, subscription_id: str) -> SimpleNamespace:
        del subscription_id
        return SimpleNamespace(enabled=False)

    def remove(self, subscription_id: str) -> bool:
        del subscription_id
        return True


class _Service:
    def __init__(
        self,
        workspace_root: Path,
        *,
        discovered: object,
        plan: ExecutionPlan,
        subscriptions: _Subscriptions | None = None,
    ) -> None:
        self.workspace_root: Path = workspace_root
        self.subscriptions: _Subscriptions | None = subscriptions
        self.acquisition: AcquisitionService | None = None
        self._discovered: object = discovered
        self._plan: ExecutionPlan = plan
        self.background_admission: list[bool] = []
        self.submitted: list[str] = []
        self.cancelled: list[str] = []
        self.reloads: int = 0
        self.submit_failure: Exception | None = None
        self.handles: dict[str, RunHandle] = {}
        self.active: list[str] = []
        self.discover_entered: threading.Event = threading.Event()
        self.discover_calls: int = 0
        self.submitted_event: threading.Event = threading.Event()
        self.discover_release: threading.Event | None = None

    def discover(self, *, changed_paths: Sequence[Path] | None = None) -> object:
        del changed_paths
        self.discover_calls += 1
        self.discover_entered.set()
        if self.discover_release is not None:
            assert self.discover_release.wait(timeout=_TIMEOUT_S)
        return self._discovered

    def default_preset_id(self) -> str:
        return "preview"

    def get_preset(self, preset_id: str) -> object:
        del preset_id
        return _PRESET.to_preset()

    def plan_auto(
        self,
        group_ids: Sequence[str],
        preset: object,
        *,
        rebuild: RebuildRequest | None = None,
        overrides: Mapping[str, object] | None = None,
    ) -> ExecutionPlan:
        del group_ids, preset, rebuild, overrides
        return self._plan

    def submit_plan(
        self,
        plan: ExecutionPlan,
        sink: object,
        *,
        origin: RequestOrigin,
        run_id: str | None = None,
        automatic: bool = False,
    ) -> RunHandle:
        del plan, sink, origin, automatic
        if self.submit_failure is not None:
            raise self.submit_failure
        identity: str = run_id or "run-1"
        self.submitted.append(identity)
        self.active.append(identity)
        handle = RunHandle(identity, lambda: None)
        self.handles[identity] = handle
        self.submitted_event.set()
        return handle

    def finish(self, run_id: str, status: GroupStatus, group_id: str) -> None:
        self.active.remove(run_id)
        self.handles[run_id].resolve(RunResult(run_id, (GroupResult(group_id, status),)))

    def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return run_id in self.handles

    def active_run_ids(self) -> tuple[str, ...]:
        return tuple(self.active)

    def set_background_admission(self, enabled: bool) -> None:
        self.background_admission.append(enabled)

    def drain(self) -> None:
        pass

    def retain_runs(self, run_ids: Sequence[str]) -> None:
        del run_ids

    def reload_preferences(self) -> None:
        self.reloads += 1


def _owner(service: _Service | AppService, store: WatchStateStore) -> AutomationOwner:
    return AutomationOwner(
        cast("AppService", service),
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
    )


@pytest.mark.parametrize("manual", [False, True])
def test_the_resident_accepts_scoped_intents_and_keeps_their_complete_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manual: bool,
) -> None:
    for number in (1, 3, 8):
        write_text_source(tmp_path / f"Episode {number}.txt", "Text")
    service: AppService = _real_service(tmp_path)
    selected: list[str] = [group.group_id for group in service.discover().groups[1:]]
    submitted: list[ExecutionPlan] = []

    def submit(
        plan: ExecutionPlan,
        sink: object,
        *,
        origin: RequestOrigin,
        run_id: str | None = None,
        automatic: bool = False,
    ) -> RunHandle:
        del sink, origin, automatic
        assert run_id is not None
        submitted.append(plan)
        handle: RunHandle = RunHandle(run_id, lambda: None)
        handle.resolve(
            RunResult(run_id, tuple(GroupResult(group.group_id, GroupStatus.SUCCEEDED) for group in plan.groups))
        )
        return handle

    monkeypatch.setattr(service, "submit_plan", submit)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(control_endpoint(tmp_path), key, owner.handle, on_disconnect=owner.disconnect)
    client: ControlClient = ControlClient(control_endpoint(tmp_path), key, timeout_s=_TIMEOUT_S)
    products: dict[str, object] = {"requested_products": ["full_pl"]}
    payload: dict[str, object] = {
        "client_id": _CLIENT,
        "group_ids": selected,
        "overrides": {
            "tts_voice_id": "chosen-voice",
            "tts_postprocess_tempo": 1.2,
            "subtitle_language_priority": ["eng", "pol"],
            "tts_engine_options": [["normalize", True]],
            "llm_max_output_tokens": 1234,
        },
    }
    if manual:
        payload.update(
            source_selection="manual",
            intents=[{"group_id": group_id, "mode": "manual", "products": products} for group_id in selected],
        )
    else:
        payload.update(
            preset={"preset_id": "once", "name": "Once", "products": products}, rebuild={"products": ["full_pl"]}
        )
    try:
        preview: Mapping[str, object] = client.call("preview", payload)
        assert preview["can_execute"]
        started: Mapping[str, object] = client.call(
            "start", {"client_id": _CLIENT, "preview_id": preview["preview_id"]}
        )
        request = store.load().requests[0]
        assert request.request_id == started["run_id"]
        assert request.group_ids == tuple(selected)
        assert request.settings["tts_voice_id"] == "chosen-voice"
        assert request.settings["tts_postprocess_tempo"] == 1.2
        assert request.settings["llm_max_output_tokens"] == 1234
        assert request.settings["subtitle_language_priority"] == ("eng", "pol")
        assert request.settings["tts_engine_options"] == (("normalize", True),)
        assert request.intents == tuple(group.intent for group in submitted[0].groups)
        assert (request.rebuild is None) is manual
        assert service.plan_auto(selected, _PRESET).settings.tts_voice_id != "chosen-voice"
    finally:
        client.close()
        server.close()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


@pytest.mark.parametrize(
    "invalid",
    [
        {"group_ids": []},
        {"group_ids": "all"},
        {"overrides": {"tts_group_jobs": True}},
        {"overrides": {"typo": 3}},
        {"rebuild": {"products": ["unknown"]}},
        {"source_selection": "manual", "intents": []},
        {"preset": {"preset_id": "x", "name": "X", "products": {"requested_products": ["full_pl"], "typo": True}}},
    ],
)
def test_invalid_preview_inputs_never_fall_back_to_processing_the_library(
    tmp_path: Path,
    invalid: dict[str, object],
) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _real_service(tmp_path)
    owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT, **invalid}))
        assert not response.ok
        assert response.code is ControlErrorCode.INVALID_PAYLOAD
        assert not owner.state.requests
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def _serving(owner: AutomationOwner) -> threading.Thread:
    thread = threading.Thread(target=owner.serve, daemon=True)
    thread.start()
    return thread


def _request(
    kind: str,
    payload: Mapping[str, object] | None = None,
    *,
    command_id: str = "command-1",
    instance_id: str | None = _INSTANCE,
) -> ControlRequest:
    return ControlRequest(
        command_id=command_id,
        kind=kind,
        payload=payload if payload is not None else {},
        instance_id=instance_id,
    )


def _library(tmp_path: Path) -> tuple[_Service, WatchStateStore, str]:
    write_text_source(tmp_path / "Episode.txt", "Text")
    real: AppService = _real_service(tmp_path)
    workspace = real.discover()
    group_id: str = workspace.groups[0].group_id
    plan: ExecutionPlan = real.plan_auto((group_id,), _PRESET)
    service = _Service(tmp_path, discovered=workspace, plan=plan, subscriptions=_Subscriptions())
    return service, WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), group_id


def _real_service(
    tmp_path: Path,
    *,
    acquisition: AcquisitionService | None = None,
    subscriptions: SubscriptionService | None = None,
) -> AppService:
    def unused(
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> TaskHandler:
        del run_root, plan, source_groups
        raise AssertionError("the owner tests never execute a plan")

    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=unused,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
        acquisition=acquisition,
        subscriptions=subscriptions,
    )


def _subscription_library(tmp_path: Path) -> tuple[AppService, WatchStateStore, _TorrentNetwork, Subscription]:
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    subscriptions: SubscriptionService = SubscriptionService(
        store=SubscriptionStore(tmp_path / "subscriptions.json"),
        acquisition=acquisition,
        sleep=lambda _: None,
    )
    subscription: Subscription = subscriptions.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9))
    return (
        _real_service(tmp_path, acquisition=acquisition, subscriptions=subscriptions),
        WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME),
        network,
        subscription,
    )


def _started(owner: AutomationOwner) -> str:
    preview: ControlResponse = owner.handle(
        _request("preview", {"client_id": _CLIENT, "preset_id": "preview"}, command_id="preview-1")
    )
    assert preview.ok
    started: ControlResponse = owner.handle(
        _request(
            "start",
            {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
            command_id="start-1",
        )
    )
    assert started.ok, started.message
    return str(started.result["run_id"])


def test_switching_auto_persists_the_state_before_it_answers(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}))
        admitted: bool = service.background_admission[-1]
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.ok
    assert store.load().policy.auto_enabled is True
    assert admitted is True


def test_a_repeated_command_identifier_replays_its_outcome_without_a_second_effect(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        first: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}))
        second: ControlResponse = owner.handle(_request("set_auto", {"enabled": False}))
        admissions: list[bool] = list(service.background_admission)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert first.result == second.result == {"auto_enabled": True}
    assert store.load().policy.auto_enabled is True
    assert admissions == [False, True]


def test_a_group_reserved_by_another_client_refuses_the_second_reservation(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        held: ControlResponse = owner.handle(
            _request("reserve", {"client_id": _CLIENT, "group_ids": [group_id]}, command_id="reserve-1")
        )
        contested: ControlResponse = owner.handle(
            _request("reserve", {"client_id": "panel-2", "group_ids": [group_id]}, command_id="reserve-2")
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert held.ok
    assert contested.code is ControlErrorCode.CONFLICT


def test_a_command_naming_another_instance_is_refused_as_stale(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(
            _request(
                "reserve",
                {"client_id": _CLIENT, "group_ids": [group_id]},
                instance_id="instance-of-a-dead-resident",
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.STALE_INSTANCE


def test_a_start_after_the_sources_changed_asks_for_a_new_preview(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}, command_id="preview-1"))
        write_text_source(tmp_path / "Episode.txt", "Changed text that is clearly longer")
        answer: ControlResponse = owner.handle(
            _request("start", {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]})
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.STALE_PREVIEW


def test_an_unknown_preview_is_refused_instead_of_started(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(
            _request("start", {"client_id": _CLIENT, "preview_id": "preview-nothing"})
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.STALE_PREVIEW
    assert service.submitted == []


def test_an_accepted_request_finishes_after_its_client_is_gone(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    recorded = store.load().requests
    assert [item.state for item in recorded] == [RequestState.SUCCEEDED]
    assert recorded[0].origin is RequestOrigin.USER
    assert recorded[0].source_selection is SourceSelection.AUTO


def test_a_finished_explicit_request_records_what_the_user_settled_for(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    markers = store.load().markers
    assert [item.group_id for item in markers] == [group_id]
    assert markers[0].products == frozenset({ProductKind.FULL_PL})


def test_a_failed_state_save_refuses_the_command_and_changes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)

    def refuse(state: object) -> None:
        del state
        raise OSError("no disk")

    monkeypatch.setattr(store, "save", refuse)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.INTERNAL
    assert owner.state.policy.auto_enabled is False
    assert service.background_admission == [False, False]
    assert not thread.is_alive()


def test_a_slow_preview_never_delays_switching_auto(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    service.discover_release = threading.Event()
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    previews: list[ControlResponse] = []
    previewing = threading.Thread(
        target=lambda: previews.append(owner.handle(_request("preview", {"client_id": _CLIENT}, command_id="p"))),
        daemon=True,
    )
    try:
        previewing.start()
        assert service.discover_entered.wait(timeout=_TIMEOUT_S)
        switched: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}))
        service.discover_release.set()
        previewing.join(timeout=_TIMEOUT_S)
    finally:
        service.discover_release.set()
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert switched.ok
    assert previews[0].ok


def test_a_shutdown_waits_for_the_active_request_and_admits_no_new_one(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        stopping: ControlResponse = owner.handle(_request("shutdown", command_id="shutdown-1"))
        thread.join(timeout=0.5)
        still_running: bool = thread.is_alive()
        refused: ControlResponse = owner.handle(
            _request("start", {"client_id": _CLIENT, "preview_id": "preview-nothing"}, command_id="start-2")
        )
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        thread.join(timeout=_TIMEOUT_S)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert stopping.ok
    assert still_running
    assert refused.code is ControlErrorCode.REFUSED
    assert not thread.is_alive()
    assert service.background_admission[-1] is False


@pytest.mark.parametrize("failure", [ExecutionError("coordinator"), RuntimeError("handler"), SystemExit(1)])
def test_a_terminal_run_fault_is_recorded_as_a_failed_request(tmp_path: Path, failure: BaseException) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        service.active.remove(run_id)
        service.handles[run_id].fail(failure)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert [item.state for item in store.load().requests] == [RequestState.FAILED]


def test_status_reports_the_instance_the_switch_and_the_subscription_counts(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        owner.handle(_request("set_auto", {"enabled": True}))
        answer: ControlResponse = owner.handle(_request("status", command_id="status-1"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.result["instance_id"] == _INSTANCE
    assert answer.result["auto_enabled"] is True
    assert answer.result["subscriptions"] == {"enabled": 1, "disabled": 0}


def test_a_paused_request_keeps_its_intent_without_marking_manual_work_complete(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        service.active.remove(run_id)
        service.handles[run_id].resolve(RunResult(run_id, (GroupResult(group_id, GroupStatus.CANCELLED),), paused=True))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert not thread.is_alive()
    assert [item.state for item in store.load().requests] == [RequestState.PAUSED]
    assert store.load().markers == ()


def test_a_directory_exception_is_stored_and_cleared(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        owner.handle(_request("set_directory_auto", {"directory": "Series", "enabled": False}, command_id="d-1"))
        stored: bool = store.load().policy.effective_auto("Series")
        owner.handle(_request("set_directory_auto", {"directory": "Series", "enabled": None}, command_id="d-2"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert stored is False
    assert dict(store.load().policy.directory_exceptions) == {}


def test_an_unknown_command_is_refused(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("nonsense"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.UNKNOWN_COMMAND


def test_reloading_settings_reaches_the_facade(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("reload_settings"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.ok
    assert service.reloads == 1


def test_a_subscription_check_runs_off_the_owner_thread(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("subscriptions_check", command_id="check-1"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.result == {"checked": 1, "downloaded": 2, "problems": 0}
    assert service.subscriptions is not None
    assert service.subscriptions.checks == 1


@pytest.mark.parametrize("phase", ["search", "add"])
@pytest.mark.parametrize("action", ["disable", "remove", "shutdown"])
def test_subscription_control_blocks_late_adds_and_keeps_admitted_transfers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    action: str,
) -> None:
    service, store, network, subscription = _subscription_library(tmp_path)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    saves: list[str] = []
    save: Callable[[WatchState], None] = store.save

    def saving(state: WatchState) -> None:
        saves.append(threading.current_thread().name)
        save(state)

    def blocked() -> None:
        if phase == "add":
            persisted: WatchState = store.load()
            assert len(persisted.acquisitions) == 1
            assert persisted.acquisitions[0].state is AcquisitionState.PENDING_SEND
            assert persisted.acquisitions[0].info_hash == "9"
        entered.set()
        assert release.wait(_TIMEOUT_S)

    monkeypatch.setattr(store, "save", saving)
    if phase == "search":
        network.before_search = blocked
    else:
        network.before_add = blocked
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    answers: list[ControlResponse] = []
    checking: threading.Thread = threading.Thread(
        target=lambda: answers.append(owner.handle(_request("subscriptions_check", command_id="check")))
    )
    checking.start()
    try:
        assert entered.wait(_TIMEOUT_S)
        kind: str = "shutdown" if action == "shutdown" else f"subscription_{action}"
        changed: ControlResponse = owner.handle(_request(kind, {"subscription_id": subscription.subscription_id}))
        assert changed.ok
        if action == "shutdown":
            assert thread.is_alive()
    finally:
        release.set()
        checking.join(_TIMEOUT_S)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()

    assert not thread.is_alive()
    assert not checking.is_alive()
    assert len(answers) == 1
    assert answers[0].ok
    assert network.added == (["9"] if phase == "add" else [])
    assert set(saves) == {"anishift-owner"}
    acquisitions: tuple[AcquisitionConfirmation, ...] = store.load().acquisitions
    assert len(acquisitions) == (1 if phase == "add" else 0)
    if acquisitions:
        assert acquisitions[0].state is AcquisitionState.ACCEPTED


@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_a_restart_reconciles_a_lost_add_response_without_adding_again(
    tmp_path: Path, *, remove: bool, retained: bool
) -> None:
    service, store, network, subscription = _subscription_library(tmp_path)
    network.releases = network.releases[:1]
    network.lose_response = True
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("subscriptions_check", command_id="check"))
        assert answer.ok
        assert answer.result["problems"] == 1
        if remove:
            assert owner.handle(_request("subscription_remove", {"subscription_id": subscription.subscription_id})).ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    uncertain: tuple[AcquisitionConfirmation, ...] = store.load().acquisitions
    assert len(uncertain) == 1
    assert uncertain[0].state is AcquisitionState.UNCERTAIN
    network.lose_response = False
    if not retained:
        network.tracked.clear()
        network.releases = (replace(network.releases[0], info_hash="replacement-9"),)
    owner = _owner(service, store)
    thread = _serving(owner)
    try:
        answer = owner.handle(_request("subscriptions_check", command_id="recheck"))
        assert answer.ok
        assert answer.result["downloaded"] == 0
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()

    assert not thread.is_alive()
    assert network.added == ["9"]
    confirmed: tuple[AcquisitionConfirmation, ...] = store.load().acquisitions
    assert confirmed[0].operation_id == uncertain[0].operation_id
    assert confirmed[0].state is (AcquisitionState.ACCEPTED if retained else AcquisitionState.UNCERTAIN)


def test_a_failed_acquisition_journal_save_prevents_the_add(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, store, network, _ = _subscription_library(tmp_path)
    owner: AutomationOwner = _owner(service, store)

    def refuse(state: WatchState) -> None:
        del state
        raise OSError("no disk")

    monkeypatch.setattr(store, "save", refuse)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("subscriptions_check", command_id="check"))
        assert not answer.ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()

    assert not thread.is_alive()
    assert not network.added
    assert not store.load().acquisitions


def test_accepted_transfer_waits_for_file_completion_then_enters_auto_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.02)
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    source: Path = tmp_path / "Episode.txt"
    size: int = source.stat().st_size
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo(source.name, "9", 0.5, "downloading", str(tmp_path), 1, size - 1)
    network.entries = (TorrentFile(0, source.name, size, 0.5, 1, False),)
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    confirmation: AcquisitionConfirmation = AcquisitionConfirmation(
        "transfer", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(confirmation,)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True))
        assert service.discover_entered.wait(_TIMEOUT_S)
        assert not service.submitted_event.wait(0.1)
        partial: WatchState = owner.state
        assert partial.acquisitions[0].state is AcquisitionState.ACCEPTED
        network.entries = (replace(network.entries[0], progress=1.0, is_seed=True),)
        network.tracked["9"] = replace(network.tracked["9"], progress=1.0, amount_left=0, state="stoppedUP")
        assert service.submitted_event.wait(_TIMEOUT_S)
        completed: WatchState = owner.state
        assert completed.acquisitions[0].state is AcquisitionState.COMPLETE
        service.finish(service.submitted[0], GroupStatus.SUCCEEDED, group_id)
        calls: int = network.info_calls
        assert not threading.Event().wait(0.1)
        assert network.info_calls == calls
        assert len(service.submitted) == 1
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_every_state_change_reaches_the_subscribers(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    frames: list[Mapping[str, object]] = []

    def record(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        frames.append(frame)

    owner.attach_broadcast(record)
    thread: threading.Thread = _serving(owner)
    try:
        owner.handle(_request("set_auto", {"enabled": True}))
        run_id: str = _started(owner)
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert {frame["event"] for frame in frames} == {"state_changed"}
    assert frames[-1]["payload"]


def test_a_restart_drops_the_reservations_of_the_previous_instance(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    first: AutomationOwner = _owner(service, store)
    first_thread: threading.Thread = _serving(first)
    try:
        held: ControlResponse = first.handle(
            _request("reserve", {"client_id": _CLIENT, "group_ids": [group_id]}, command_id="reserve-1")
        )
    finally:
        first.request_shutdown()
        first_thread.join(timeout=_TIMEOUT_S)
    restarted: AutomationOwner = _owner(service, store)
    second_thread: threading.Thread = _serving(restarted)
    try:
        reported: ControlResponse = restarted.handle(_request("status", command_id="status-1"))
        taken: ControlResponse = restarted.handle(
            _request("reserve", {"client_id": "panel-2", "group_ids": [group_id]}, command_id="reserve-2")
        )
    finally:
        restarted.request_shutdown()
        second_thread.join(timeout=_TIMEOUT_S)

    assert held.ok
    assert reported.result["reservations"] == []
    assert taken.ok


@pytest.mark.parametrize("failure", [ExecutionError("coordinator"), RuntimeError("handler")])
def test_a_submission_failure_keeps_the_accepted_request_identity(tmp_path: Path, failure: Exception) -> None:
    service, store, _ = _library(tmp_path)
    service.submit_failure = failure
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(
            _request("preview", {"client_id": _CLIENT, "preset_id": "preview"}, command_id="preview-1")
        )
        assert preview.ok
        first: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
                command_id="start-1",
            )
        )
        repeated: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
                command_id="start-1",
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert first.ok
    assert repeated == first
    assert "run_id" in repeated.result
    assert not thread.is_alive()
    assert [item.state for item in store.load().requests] == [RequestState.FAILED]


def test_serving_applies_the_persisted_switch_before_any_command(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert service.background_admission[0] is True


@pytest.mark.parametrize("slow_preview", [False, True])
def test_a_closed_editor_releases_its_groups_and_invalidates_previews(tmp_path: Path, slow_preview: bool) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    disconnected: threading.Event = threading.Event()

    def closed(session_id: str) -> None:
        owner.disconnect(session_id)
        disconnected.set()

    endpoint: str = control_endpoint(tmp_path)
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=closed)
    client: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    waiting: threading.Thread | None = None
    try:
        client.call("reserve", {"client_id": _CLIENT, "group_ids": [group_id]}, instance_id=_INSTANCE)
        preview: Mapping[str, object] = client.call("preview", {"client_id": _CLIENT})
        if slow_preview:
            service.discover_entered.clear()
            service.discover_release = threading.Event()

            def preview_again() -> None:
                try:
                    client.call("preview", {"client_id": _CLIENT})
                except ControlError:
                    return

            waiting = threading.Thread(target=preview_again, daemon=True)
            waiting.start()
            assert service.discover_entered.wait(_TIMEOUT_S)
        client.close()
        assert disconnected.wait(_TIMEOUT_S)
        owner.handle(_request("status"))
        assert store.load().reservations == ()
        replacement: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            with pytest.raises(ControlError) as refused:
                replacement.call("start", {"client_id": _CLIENT, "preview_id": preview["preview_id"]})
            assert refused.value.code is ControlErrorCode.STALE_PREVIEW
            replacement.call("reserve", {"client_id": _CLIENT, "group_ids": [group_id]}, instance_id=_INSTANCE)
        finally:
            replacement.close()
    finally:
        if service.discover_release is not None:
            service.discover_release.set()
        if waiting is not None:
            waiting.join(_TIMEOUT_S)
        client.close()
        server.close()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing")
def test_file_events_wait_for_writers_and_manual_reservations_before_admitting_one_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    held: bool,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store)
    observed: threading.Event = threading.Event()

    def broadcast(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        payload: object = frame.get("payload")
        if isinstance(payload, Mapping) and payload.get("library_groups") == 1:
            observed.set()

    owner.attach_broadcast(broadcast)
    thread: threading.Thread = _serving(owner)
    source: Path = tmp_path / "Episode.txt"
    try:
        if held:
            assert owner.handle(_request("reserve", {"client_id": _CLIENT, "group_ids": [group_id]})).ok
        with source.open("r+b"):
            owner.files_changed(DirectoryChange(paths=(source,)))
            assert observed.wait(_TIMEOUT_S)
            assert not service.submitted_event.wait(0.06)
        if held:
            assert not service.submitted_event.wait(0.04)
            assert owner.handle(
                _request(
                    "release",
                    {"client_id": _CLIENT, "group_ids": [group_id]},
                    command_id="release",
                )
            ).ok
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert len(service.submitted) == 1
        assert store.load().requests[0].origin is RequestOrigin.USER
        for _ in range(20):
            owner.files_changed(DirectoryChange(paths=(source,)))
        service.finish(service.submitted[0], GroupStatus.SUCCEEDED, group_id)
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert len(service.submitted) == 1


def test_auto_off_keeps_the_library_current_and_auto_on_admits_without_another_file_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    observed: threading.Event = threading.Event()

    def broadcast(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        payload: object = frame.get("payload")
        if isinstance(payload, Mapping) and payload.get("library_groups") == 1:
            observed.set()

    owner.attach_broadcast(broadcast)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert observed.wait(_TIMEOUT_S)
        assert not service.submitted_event.wait(0.06)
        checks: int = service.discover_calls
        assert owner.handle(_request("set_auto", {"enabled": True})).ok
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert service.discover_calls == checks
        assert store.load().requests[0].origin is RequestOrigin.BACKGROUND
        service.finish(service.submitted[0], GroupStatus.SUCCEEDED, group_id)
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert len(service.submitted) == 1


@pytest.mark.parametrize("name", ["Episode.srt", "Episode.pl.srt"])
def test_new_sidecars_and_changed_products_invalidate_the_affected_preview(tmp_path: Path, name: str) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}))
        assert preview.ok
        source: Path = tmp_path / name
        source.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")
        owner.files_changed(DirectoryChange(paths=(source,)))
        started: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
                command_id="start",
            )
        )
        assert not started.ok
        assert started.code is ControlErrorCode.STALE_PREVIEW
        assert not service.submitted
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
