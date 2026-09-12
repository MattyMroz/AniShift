from __future__ import annotations

import os
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Final, cast

import pytest
from fakes import write_text_source

from anishift.application.automation import AutomationOwner
from anishift.application.control import AutomationPolicy, RequestState, SourceSelection, WatchState
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ProductIntent, ProductKind, RequestOrigin
from anishift.application.planning import ExecutionPlan
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.application.scheduler import RunHandle
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ExecutionError
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

_TIMEOUT_S: Final[float] = 5.0

_INSTANCE: Final[str] = "instance-1"

_CLIENT: Final[str] = "panel-1"

_MOMENT: Final[datetime] = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

_PRESET: Final[AutoPresetDraft] = AutoPresetDraft(
    "preview",
    "Preview",
    ProductIntent(frozenset({ProductKind.FULL_PL})),
)


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

    def check_all(self) -> tuple[SimpleNamespace, ...]:
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
        self.discover_release: threading.Event | None = None

    def discover(self) -> object:
        self.discover_entered.set()
        if self.discover_release is not None:
            assert self.discover_release.wait(timeout=_TIMEOUT_S)
        return self._discovered

    def default_preset_id(self) -> str:
        return "preview"

    def get_preset(self, preset_id: str) -> object:
        del preset_id
        return _PRESET.to_preset()

    def plan_auto(self, group_ids: Sequence[str], preset: object) -> ExecutionPlan:
        del group_ids, preset
        return self._plan

    def submit_plan(
        self,
        plan: ExecutionPlan,
        sink: object,
        *,
        origin: RequestOrigin,
        run_id: str | None = None,
    ) -> RunHandle:
        del plan, sink, origin
        if self.submit_failure is not None:
            raise self.submit_failure
        identity: str = run_id or "run-1"
        self.submitted.append(identity)
        self.active.append(identity)
        handle = RunHandle(identity, lambda: None)
        self.handles[identity] = handle
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


def _owner(service: _Service, store: WatchStateStore) -> AutomationOwner:
    return AutomationOwner(
        cast("AppService", service),
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
    )


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


def _real_service(tmp_path: Path) -> AppService:
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
    assert service.background_admission == [False]


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
