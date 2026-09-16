from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Final, cast
from urllib.parse import parse_qs

import httpx
import pytest
from fakes import write_image_source, write_text_source
from loguru import logger as loguru_logger

import anishift.application.automation as automation_module
import anishift.application.watch as watch_module
from anishift.application import SCAN_INTERVAL_S, TaskState
from anishift.application.acquisition import (
    AcquisitionService,
    DownloadReceipt,
    ReleaseCatalog,
    TorrentClient,
    TorrentManagement,
)
from anishift.application.artifacts import ArtifactKind, ArtifactState
from anishift.application.automation import (
    TRANSFER_BACKOFF_CEILING_S,
    TRANSFER_CHECK_INTERVAL_S,
    AutomationOwner,
)
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AudiobookRecipe,
    AutomationPolicy,
    FileReservation,
    ManualHandledMarker,
    NarrationTimeline,
    PendingDeletion,
    ProcessingRequest,
    ProductConfirmation,
    ReadyGroup,
    RecipePreferences,
    RefusalReason,
    RequestState,
    SourceFingerprint,
    SourceSelection,
    TextResultFormat,
    TranslateRecipe,
    WatchState,
)
from anishift.application.control_views import encode_view
from anishift.application.discovery import discover_groups
from anishift.application.events import RunEvent, RunEventKind
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ProductIntent, ProductKind, RebuildRequest, RequestOrigin
from anishift.application.planning import ExecutionPlan
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.recovery import RunJournal
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.application.scheduler import RunHandle
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.application.subscriptions import (
    CheckOutcome,
    CheckRecorder,
    Subscription,
    SubscriptionAdmission,
    SubscriptionOrder,
    SubscriptionService,
    SubscriptionStore,
    SubscriptionUpdater,
)
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.cli.resident import ResidentSession
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.paths import COVER_DIRECTORY, READY_DIRECTORY, TRANSLATE_DIRECTORY
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
from anishift.services.torrents.qbittorrent import QBittorrentClient

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
        self.unreachable: bool = False
        self.unstartable: bool = False
        self.resume_calls: int = 0
        self.renamed: list[tuple[str, str, str]] = []
        self.started: list[str] = []
        self.actions: list[tuple[str, str]] = []
        self.released: list[frozenset[str]] = []
        self.unreadable_files: bool = False

    def transfer_action(self, info_hash: str, action: str) -> None:
        self.actions.append((info_hash, action))

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        self.released.append(hashes)
        return hashes

    def finish_transfers(self) -> None:
        return

    def rename_file(self, info_hash: str, old_path: str, new_path: str) -> None:
        self.renamed.append((info_hash, old_path, new_path))
        self.entries = tuple(replace(item, name=new_path) if item.name == old_path else item for item in self.entries)

    def resume(self, info_hash: str) -> None:
        self.started.append(info_hash)
        current: TorrentInfo | None = self.tracked.get(info_hash)
        if current is not None:
            self.tracked[info_hash] = replace(current, state="downloading")

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        del hashes
        self.resume_calls += 1
        if self.unstartable:
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                    message="The private torrent client could not start; resolve the problem and explicitly resume",
                )
            )

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        del query, categories
        if self.before_search is not None:
            self.before_search()
        return self.releases

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str, stopped: bool = False) -> None:
        del category
        release: Release = next(item for item in self.releases if item.torrent_url == torrent_url)
        self.added.append(release.info_hash)
        if self.before_add is not None:
            self.before_add()
        self.tracked[release.info_hash] = TorrentInfo(
            release.title, release.info_hash, 0.1, "stoppedDL" if stopped else "downloading", str(save_path)
        )
        if self.lose_response:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Response lost")
            )

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        del category
        self.info_calls += 1
        if self.unreachable:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="The Web UI is closed")
            )
        return tuple(self.tracked.values())

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        del info_hash
        if self.unreadable_files:
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_REFUSED, message="qBittorrent returned unreadable file metadata"
                )
            )
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
        self.stored_ranges: list[tuple[tuple[Decimal, ...], Decimal | None]] = []
        self.ordered_again: list[tuple[Decimal, ...]] = []

    def list(self) -> tuple[SimpleNamespace, ...]:
        return tuple(self.entries)

    def set_range(self, subscription_id: str, *, selected: Sequence[Decimal], future_from: Decimal | None) -> None:
        del subscription_id
        self.stored_ranges.append((tuple(selected), future_from))

    def repeat(self, subscription_id: str, numbers: Sequence[Decimal]) -> None:
        del subscription_id
        self.ordered_again.append(tuple(numbers))

    def next_check_at(self, policy: AutomationPolicy) -> datetime | None:
        del policy
        return None

    def reconcile_sources(self, confirmations: Sequence[AcquisitionConfirmation]) -> None:
        del confirmations

    def check_due(
        self,
        policy: AutomationPolicy,
        *,
        admit: SubscriptionAdmission | None = None,
        record: CheckRecorder | None = None,
        update: SubscriptionUpdater | None = None,
        refresh_calendar: bool = False,
    ) -> tuple[CheckOutcome, ...]:
        del policy, admit, record, update, refresh_calendar
        self.checks += 1
        subscription: Subscription = Subscription(
            "s1", "Series Group", "Series", "Group", Decimal(3), 1080, frozenset(), _MOMENT.isoformat(), None
        )
        return (CheckOutcome(subscription, downloaded=2),)

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
        self.recipes: list[RecipePreferences | None] = []
        self.targets: list[dict[str, WorkflowTarget]] = []
        self.published: list[frozenset[Path]] = []
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

    def plan_auto(  # noqa: PLR0913
        self,
        group_ids: Sequence[str],
        preset: object,
        *,
        rebuild: RebuildRequest | None = None,
        overrides: Mapping[str, object] | None = None,
        recipes: RecipePreferences | None = None,
        targets: Mapping[str, WorkflowTarget] | None = None,
        published: frozenset[Path] | None = None,
    ) -> ExecutionPlan:
        del group_ids, preset, rebuild, overrides
        self.recipes.append(recipes)
        self.targets.append(dict(targets or {}))
        self.published.append(frozenset(published or frozenset()))
        return self._plan

    def submit_plan(  # noqa: PLR0913
        self,
        plan: ExecutionPlan,
        sink: object,
        *,
        origin: RequestOrigin,
        run_id: str | None = None,
        automatic: bool = False,
        journal: RunJournal | None = None,
        resume: bool = False,
    ) -> RunHandle:
        del plan, sink, origin, automatic, journal, resume
        if self.submit_failure is not None:
            raise self.submit_failure
        identity: str = run_id or "run-1"
        self.submitted.append(identity)
        self.active.append(identity)
        handle = RunHandle(identity, lambda: None)
        self.handles[identity] = handle
        self.submitted_event.set()
        return handle

    def finish(self, run_id: str, status: GroupStatus, group_id: str, errors: tuple[str, ...] = ()) -> None:
        self.active.remove(run_id)
        self.handles[run_id].resolve(RunResult(run_id, (GroupResult(group_id, status, error_messages=errors),)))

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


def _owner(
    service: _Service | AppService,
    store: WatchStateStore,
    *,
    scan_interval_s: float = SCAN_INTERVAL_S,
) -> AutomationOwner:
    return AutomationOwner(
        cast("AppService", service),
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
        scan_interval_s=scan_interval_s,
    )


@pytest.mark.integration
def test_panel_search_download_and_follow_use_the_resident_and_durable_receipts(tmp_path: Path) -> None:
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
        clock=lambda: _MOMENT,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition, subscriptions=subscriptions)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(control_endpoint(tmp_path), key, owner.handle, on_disconnect=owner.disconnect)
    session: ResidentSession = ResidentSession(
        tmp_path,
        lambda: ControlClient(control_endpoint(tmp_path), key, timeout_s=_TIMEOUT_S),
    )
    network.before_add = lambda: _assert_download_receipt(store)
    try:
        assert session.find_titles("Neko") == ()
        catalog: ReleaseCatalog = session.search("Neko")
        choices = catalog.groups[0].choices
        receipt: DownloadReceipt = session.download(choices)
        assert receipt.count == 2
        assert session.download(choices).count == 0
        subscription: Subscription = session.follow(
            SubscriptionOrder("Neko to Ryuu", "SubsPlease", "neko", Decimal(20))
        )
        assert subscription.added_by_command is not None
        assert subscription.subscription_id == subscriptions.list()[0].subscription_id
        assert all(item.origin is RequestOrigin.USER for item in store.load().acquisitions)
        assert all(item.pending is None for item in store.load().command_receipts)
        assert network.added == [choice.release.info_hash for choice in choices]
    finally:
        session.close()
        server.close()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


def _assert_download_receipt(store: WatchStateStore) -> None:
    state: WatchState = store.load()
    assert len(state.acquisitions) == 2
    assert any(item.outcome.get("count") == 2 for item in state.command_receipts)


def test_transfer_action_survives_restart_and_receipt_replay_does_not_repeat_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, _ = _library(tmp_path)
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "a", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "1", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    command: ControlRequest = _request("transfer", {"info_hash": "a", "action": "stop"})
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(command).ok
        assert store.load().acquisitions[0].action_pending
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    service.acquisition = acquisition
    calls: list[tuple[str, str]] = []
    finished: threading.Event = threading.Event()

    def control(info_hash: str, action: str) -> None:
        assert store.load().acquisitions[0].action_pending
        calls.append((info_hash, action))

    def observe(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        if frame.get("event") == "state_changed" and not store.load().acquisitions[0].action_pending:
            finished.set()

    monkeypatch.setattr(acquisition, "control_transfer", control)
    owner = _owner(service, store)
    owner.attach_broadcast(observe)
    thread = _serving(owner)
    try:
        assert finished.wait(_TIMEOUT_S)
        assert owner.handle(command).ok
        assert calls == [("a", "stop")]
        assert not store.load().acquisitions[0].action_pending
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_subscription_addition_replays_after_its_confirmation_could_not_be_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        clock=lambda: _MOMENT,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition, subscriptions=subscriptions)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    save: Callable[[WatchState], None] = store.save

    def fail_confirmation(state: WatchState) -> None:
        if state.command_receipts and all(item.pending is None for item in state.command_receipts):
            raise OSError("Injected confirmation failure")
        save(state)

    order: SubscriptionOrder = SubscriptionOrder("Neko to Ryuu", "SubsPlease", "neko", Decimal(20))
    command: ControlRequest = _request("subscription_add", {"order": encode_view(order)})
    try:
        with monkeypatch.context() as failure:
            failure.setattr(store, "save", fail_confirmation)
            assert not owner.handle(command).ok
        assert subscriptions.list()[0].generation == 1
        assert store.load().command_receipts[0].pending == "subscription_add"
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    restored: AutomationOwner = _owner(service, store)
    thread = _serving(restored)
    try:
        assert restored.handle(command).ok
        assert restored.handle(command).ok
        assert subscriptions.list()[0].generation == 1
        assert store.load().command_receipts[0].pending is None
    finally:
        restored.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


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

    def submit(  # noqa: PLR0913
        plan: ExecutionPlan,
        sink: object,
        *,
        origin: RequestOrigin,
        run_id: str | None = None,
        automatic: bool = False,
        journal: RunJournal | None = None,
        resume: bool = False,
    ) -> RunHandle:
        del sink, origin, automatic, journal, resume
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


def test_a_relocation_left_by_a_killed_resident_still_records_the_target_of_its_set(tmp_path: Path) -> None:
    audiobook: Path = tmp_path / "audiobook"
    audiobook.mkdir()
    write_text_source(audiobook / "Book.txt", "Zażółć gęślą jaźń.")
    product: Path = audiobook / "Book.m4a"
    product.write_bytes(b"recording")
    accepted: RecipePreferences = RecipePreferences(audiobook=AudiobookRecipe(timeline=NarrationTimeline.SOURCE_TIMES))
    journal: ReadyStore = ReadyStore(tmp_path / "control" / "relocations", tmp_path)
    prepared: ReadyMove | None = journal.prepare(discover_groups(tmp_path).groups[0], (product,), accepted)
    assert prepared is not None
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    store.save(WatchState(recipes=RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.TEXT))))
    owner: AutomationOwner = AutomationOwner(
        service,
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
        ready_store=ReadyStore(tmp_path / "control" / "relocations", tmp_path),
    )
    thread: threading.Thread = _serving(owner)
    try:
        deadline: float = time.monotonic() + _TIMEOUT_S
        while not (tmp_path / "ready" / "Book.m4a").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()
    recorded: tuple[ReadyGroup, ...] = store.load().ready_groups
    assert len(recorded) == 1
    assert recorded[0].target is WorkflowTarget.AUDIOBOOK
    assert recorded[0].source_directory == "audiobook"
    assert recorded[0].source_stem == "Book"
    assert recorded[0].stem == "Book"
    assert recorded[0].sources == ("ready/Book.txt",)
    assert recorded[0].products == ("ready/Book.m4a",)
    assert recorded[0].main_result == "ready/Book.m4a"
    assert recorded[0].recipe == accepted
    assert recorded[0].recipe.audiobook.timeline is NarrationTimeline.SOURCE_TIMES
    assert store.load().recipes.translate.text_result is TextResultFormat.TEXT


@pytest.mark.parametrize("remembered", [True, False])
def test_a_cover_regenerated_in_ready_takes_its_target_from_the_recorded_set(tmp_path: Path, remembered: bool) -> None:
    ready: Path = tmp_path / READY_DIRECTORY
    ready.mkdir(parents=True)
    write_text_source(ready / "Book.txt", "Zażółć gęślą jaźń.")
    write_image_source(ready / "Book.png")
    service: AppService = _real_service(tmp_path)
    group_id: str = service.discover().groups[0].group_id
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    if remembered:
        store.save(
            WatchState(
                ready_groups=(
                    ReadyGroup(
                        set_id="group-before-the-move",
                        group_id=group_id,
                        stem="Book",
                        source_directory="cover",
                        source_stem="Book",
                        target=WorkflowTarget.COVER,
                        sources=("ready/Book.txt", "ready/Book.png"),
                        products=(),
                    ),
                )
            )
        )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(
            _request(
                "preview",
                {
                    "client_id": _CLIENT,
                    "group_ids": [group_id],
                    "source_selection": "manual",
                    "intents": [
                        {
                            "group_id": group_id,
                            "mode": "manual",
                            "products": {"requested_products": ["cover_mp4"]},
                        }
                    ],
                },
            )
        )
        assert response.ok
        assert response.result["can_execute"] is remembered
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


def test_a_published_product_stops_being_this_programs_own_once_its_bytes_are_replaced(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    recording: Path = _library_dir(tmp_path) / "Episode.eac3"
    recording.write_bytes(b"the voice this program published")
    stamp: os.stat_result = recording.stat()
    store.save(
        WatchState(
            products=(
                ProductConfirmation(
                    group_id,
                    ArtifactKind.NARRATION_AUDIO.value,
                    recording.relative_to(tmp_path).as_posix(),
                    1,
                    "run-1",
                    RequestOrigin.BACKGROUND,
                    stamp.st_size,
                    stamp.st_mtime_ns,
                ),
            )
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    preview: ControlRequest = _request(
        "preview",
        {"client_id": _CLIENT, "group_ids": [group_id], "source_selection": "auto"},
    )
    try:
        assert owner.handle(preview).ok
        recording.write_bytes(b"the voice a person put here now!")
        os.utime(recording, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
        assert recording.stat().st_size == stamp.st_size
        assert owner.handle(preview).ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert service.published == [frozenset({recording}), frozenset()]


@pytest.mark.parametrize("remembered", [True, False])
def test_regenerating_a_finished_cover_plans_its_film_from_the_recorded_target(
    tmp_path: Path,
    remembered: bool,
) -> None:
    ready: Path = tmp_path / READY_DIRECTORY
    ready.mkdir(parents=True)
    write_text_source(ready / "Book.txt", "Zażółć gęślą jaźń.")
    write_image_source(ready / "Book.png")
    service: AppService = _real_service(tmp_path)
    group_id: str = service.discover().groups[0].group_id
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    if remembered:
        store.save(
            WatchState(
                ready_groups=(
                    ReadyGroup(
                        set_id="group-before-the-move",
                        group_id=group_id,
                        stem="Book",
                        source_directory="cover",
                        source_stem="Book",
                        target=WorkflowTarget.COVER,
                        sources=("ready/Book.txt", "ready/Book.png"),
                        products=(),
                    ),
                )
            )
        )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(
            _request(
                "preview",
                {"client_id": _CLIENT, "group_ids": [group_id], "source_selection": "auto"},
            )
        )
        assert response.ok
        groups: object = response.result["groups"]
        assert isinstance(groups, list)
        projection: dict[str, object] = groups[0]
        problems: object = projection["problems"]
        planned: object = projection["planned_products"]
        assert isinstance(problems, list)
        assert isinstance(planned, list)
        codes: list[str] = [str(problem["code"]) for problem in problems]
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()
    if remembered:
        assert response.result["can_execute"] is True
        assert "cover_mp4" in planned
        assert "txt_products_unsupported" not in codes
    else:
        assert response.result["can_execute"] is False
        assert "cover_mp4" not in planned
        assert "txt_products_unsupported" in codes


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
    session_id: str | None = None,
) -> ControlRequest:
    return ControlRequest(
        command_id=command_id,
        kind=kind,
        payload=payload if payload is not None else {},
        instance_id=instance_id,
        session_id=session_id,
    )


def _library_dir(root: Path) -> Path:
    directory: Path = root / TRANSLATE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _library(tmp_path: Path) -> tuple[_Service, WatchStateStore, str]:
    write_text_source(_library_dir(tmp_path) / "Episode.txt", "Text")
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


def test_cancellation_never_reaches_the_run_when_acceptance_cannot_be_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    run_id: str = _started(owner)

    def fail_save(state: WatchState) -> None:
        del state
        raise OSError("Injected write failure")

    try:
        with monkeypatch.context() as failure:
            failure.setattr(store, "save", fail_save)
            answer: ControlResponse = owner.handle(_request("cancel", {"run_id": run_id}))
        assert not answer.ok
        assert service.cancelled == []
        assert store.load().requests[0].state is RequestState.ACCEPTED
    finally:
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize("fail_confirmation", [False, True])
def test_subscription_changes_survive_the_gap_between_intent_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fail_confirmation: bool
) -> None:
    service, store, _, subscription = _subscription_library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    save: Callable[[WatchState], None] = store.save
    command: ControlRequest = _request("subscription_disable", {"subscription_id": subscription.subscription_id})

    def fail_save(state: WatchState) -> None:
        pending: bool = any(receipt.pending is not None for receipt in state.command_receipts)
        if pending != fail_confirmation:
            raise OSError("Injected write failure")
        save(state)

    try:
        with monkeypatch.context() as failure:
            failure.setattr(store, "save", fail_save)
            answer: ControlResponse = owner.handle(command)
        assert not answer.ok
        assert service.subscriptions is not None
        assert service.subscriptions.list()[0].enabled is not fail_confirmation
        assert bool(store.load().command_receipts) is fail_confirmation
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    restored: AutomationOwner = _owner(service, store)
    updates: list[Mapping[str, object]] = []

    def record_update(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        updates.append(frame)

    restored.attach_broadcast(record_update)
    thread = _serving(restored)
    try:
        assert restored.handle(command).ok
        assert restored.handle(command).ok
        assert service.subscriptions.list()[0].enabled is False
        assert any(frame.get("event") == "state_changed" for frame in updates)
        assert service.subscriptions.list()[0].generation == subscription.generation + 1
        assert all(receipt.pending is None for receipt in store.load().command_receipts)
    finally:
        restored.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


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
    assert contested.reason == RefusalReason.GROUP_RESERVED.value


def test_every_refusal_cause_has_its_own_reason_and_message() -> None:
    assert set(automation_module._REFUSALS) == set(RefusalReason)
    messages: list[str] = [message for _code, message in automation_module._REFUSALS.values()]

    assert len(set(messages)) == len(RefusalReason)
    for reason in RefusalReason:
        answer: ControlResponse = automation_module._refuse(reason)
        assert answer.reason == reason.value
        assert answer.code is automation_module._REFUSALS[reason][0]
        assert answer.message == automation_module._REFUSALS[reason][1]
        assert not answer.ok


def test_a_group_owned_by_an_active_request_is_refused_as_processing_not_as_held(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        contested: ControlResponse = owner.handle(
            _request("reserve", {"client_id": "panel-2", "group_ids": [group_id]}, command_id="reserve-1")
        )
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert contested.code is ControlErrorCode.ALREADY_PROCESSING
    assert contested.reason == RefusalReason.GROUP_PROCESSING.value
    assert store.load().reservations == ()


def test_starting_a_group_being_relocated_names_the_relocation(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}, command_id="preview-1"))
        assert preview.ok, preview.message
        owner._ready_problems[group_id] = "the move is still pending"
        answer: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
                command_id="start-1",
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.CONFLICT
    assert answer.reason == RefusalReason.GROUP_RELOCATING.value
    assert service.submitted == []


def test_starting_the_preview_of_another_client_names_the_preview_owner(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}, command_id="preview-1"))
        assert preview.ok, preview.message
        answer: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": "panel-2", "preview_id": preview.result["preview_id"]},
                command_id="start-1",
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.CONFLICT
    assert answer.reason == RefusalReason.FOREIGN_PREVIEW.value
    assert service.submitted == []


def test_registering_a_file_for_an_unreserved_group_names_the_missing_reservation(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    outside: Path = tmp_path / "outside.srt"
    outside.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(
            _request(
                "register_external",
                {"client_id": _CLIENT, "group_id": group_id, "path": str(outside), "kind": "subtitle"},
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == RefusalReason.NOT_RESERVED.value


def test_a_closed_session_and_a_taken_client_identity_name_their_own_cause(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("status", {"client_id": _CLIENT}, session_id="session-1")).ok
        taken: ControlResponse = owner.handle(
            _request("status", {"client_id": _CLIENT}, command_id="second", session_id="session-2")
        )
        owner.disconnect("session-1")
        closed: ControlResponse = owner.handle(
            _request("status", {"client_id": _CLIENT}, command_id="third", session_id="session-1")
        )
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)

    assert taken.code is ControlErrorCode.CONFLICT
    assert taken.reason == RefusalReason.CLIENT_BOUND.value
    assert closed.code is ControlErrorCode.REFUSED
    assert closed.reason == RefusalReason.SESSION_CLOSED.value


def test_resuming_a_run_that_became_active_again_says_it_cannot_be_resumed(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    settled: frozenset[threading.Thread] = frozenset(threading.enumerate())
    watcher: threading.Thread | None = None
    run_id: str = ""
    try:
        run_id = _started(owner)
        watcher = _only_new_thread(settled)
        service.active.remove(run_id)
        owner._queue.put(automation_module._Completion(request_id=run_id, result=_stopped_run(run_id, group_id)))
        preview: ControlResponse = owner.handle(
            _request("resume_preview", {"client_id": _CLIENT, "group_ids": [group_id]}, command_id="resume-1")
        )
        assert preview.ok, preview.message
        service.active.append(run_id)
        answer: ControlResponse = owner.handle(
            _request(
                "start",
                {"client_id": _CLIENT, "preview_id": preview.result["preview_id"]},
                command_id="start-2",
            )
        )
        service.active.remove(run_id)
    finally:
        owner.request_shutdown()
        thread.join(timeout=_TIMEOUT_S)
        _end_watcher(service, run_id, group_id, watcher)

    assert answer.code is ControlErrorCode.REFUSED
    assert answer.reason == RefusalReason.NOT_RESUMABLE.value
    assert watcher is not None
    assert not watcher.is_alive()


def _stopped_run(run_id: str, group_id: str) -> RunResult:
    return RunResult(run_id, (GroupResult(group_id, GroupStatus.FAILED, error_messages=("stopped",)),))


def _only_new_thread(settled: frozenset[threading.Thread]) -> threading.Thread:
    fresh: list[threading.Thread] = [
        item for item in threading.enumerate() if item not in settled and not item.name.startswith("anishift-")
    ]
    assert len(fresh) == 1, [item.name for item in fresh]
    return fresh[0]


def _end_watcher(service: _Service, run_id: str, group_id: str, watcher: threading.Thread | None) -> None:
    if watcher is None:
        return
    service.handles[run_id].resolve(_stopped_run(run_id, group_id))
    watcher.join()


def _drain_owner_queue(owner: AutomationOwner) -> None:
    action: object = owner._queue.get(timeout=_TIMEOUT_S)
    assert callable(action)
    action()


def test_repeated_transfer_failures_log_one_line_and_grow_the_poll_delay(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    network.unreachable = True
    service.acquisition = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "a", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "1", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    delays: list[float] = []
    try:
        for _ in range(3):
            owner._inspect_transfers((item,), frozenset())
            _drain_owner_queue(owner)
            delays.append(owner._transfers_delay)
        network.unreachable = False
        owner._inspect_transfers((item,), frozenset())
        _drain_owner_queue(owner)
        delays.append(owner._transfers_delay)
    finally:
        loguru_logger.remove(handler_id)

    failures: list[str] = [line for line in captured if "Transfer reconciliation failed" in line]
    recoveries: list[str] = [line for line in captured if "Transfer reconciliation recovered" in line]
    assert len(failures) == 1
    assert len(recoveries) == 1
    assert "TorrentClientError" in failures[0]
    assert ErrorCode.TORRENT_CLIENT_UNAVAILABLE.value in failures[0]
    assert "The Web UI is closed" in failures[0]
    assert str(tmp_path) not in failures[0]
    assert delays == [20.0, 40.0, 80.0, TRANSFER_CHECK_INTERVAL_S]
    assert network.info_calls == 4


def test_a_client_that_cannot_be_started_logs_once_and_slows_down_instead_of_flooding(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    network.unstartable = True
    service.acquisition = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        torrent_management=cast("TorrentManagement", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "a", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "1", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    delays: list[float] = []
    try:
        for _ in range(5):
            owner._inspect_transfers((item,), frozenset())
            _drain_owner_queue(owner)
            delays.append(owner._transfers_delay)
    finally:
        loguru_logger.remove(handler_id)

    failures: list[str] = [line for line in captured if "Transfer reconciliation failed" in line]
    assert len(failures) == 1
    assert "could not start" in failures[0]
    assert network.resume_calls == 5
    assert network.info_calls == 0
    assert delays == [20.0, 40.0, 80.0, 160.0, TRANSFER_BACKOFF_CEILING_S]


def test_the_transfer_poll_delay_never_grows_past_its_ceiling(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    nature: tuple[str, str] = ("TorrentClientError", ErrorCode.TORRENT_CLIENT_UNAVAILABLE.value)

    for _ in range(20):
        owner._note_transfers("the client is unreachable", nature)

    assert owner._transfers_delay == TRANSFER_BACKOFF_CEILING_S


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
        write_text_source(_library_dir(tmp_path) / "Episode.txt", "Changed text that is clearly longer")
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
    assert markers[0].products == frozenset({ProductKind.TRANSLATED_TEXT})


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

    assert answer.ok
    assert {key: answer.result[key] for key in ("checked", "downloaded", "problems")} == {
        "checked": 1,
        "downloaded": 2,
        "problems": 0,
    }
    outcomes: object = answer.result["outcomes"]
    assert isinstance(outcomes, list)
    assert len(outcomes) == 1
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
    source: Path = _library_dir(tmp_path) / "Episode.txt"
    size: int = source.stat().st_size
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo(source.name, "9", 0.5, "downloading", str(source.parent), 1, size - 1)
    network.entries = (TorrentFile(0, source.name, size, 0.5, 1),)
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    confirmation: AcquisitionConfirmation = AcquisitionConfirmation(
        "transfer", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(confirmation,)))
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True))
        assert service.discover_entered.wait(_TIMEOUT_S)
        assert not service.submitted_event.wait(0.1)
        partial: WatchState = owner.state
        assert partial.acquisitions[0].state is AcquisitionState.ACCEPTED
        network.entries = (replace(network.entries[0], progress=1.0),)
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

    assert {frame["event"] for frame in frames} == {"state_changed", "run_finished"}
    assert sum(frame["event"] == "run_finished" for frame in frames) == 1
    assert frames[-1]["payload"]


def test_reusing_ready_results_does_not_emit_a_new_ready_notification(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    service._plan = replace(
        service._plan,
        groups=tuple(replace(group, task_ids=()) for group in service._plan.groups),
        tasks=(),
        artifacts=tuple(
            replace(
                item,
                state=ArtifactState.READY,
                path=item.path or item.planned_destination or tmp_path / item.artifact_id,
            )
            for item in service._plan.artifacts
        ),
    )
    for item in service._plan.artifacts:
        assert item.path is not None
        assert item.path.is_relative_to(tmp_path)
        if not item.path.exists():
            item.path.parent.mkdir(parents=True, exist_ok=True)
            item.path.write_bytes(b"ready")
    owner: AutomationOwner = _owner(service, store)
    frames: list[Mapping[str, object]] = []

    def record(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        frames.append(frame)

    owner.attach_broadcast(record)
    thread: threading.Thread = _serving(owner)
    run_id: str = _started(owner)
    try:
        owner._publish_event(
            RunEvent(run_id, 1, RunEventKind.GROUP_FINISHED, group_id=group_id, state=TaskState.SUCCEEDED)
        )
        assert owner.handle(_request("status")).ok
        assert not any(frame.get("event") == "notification" for frame in frames)
        assert not owner.state.notified
    finally:
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)


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
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    observed: threading.Event = threading.Event()

    def broadcast(frame: Mapping[str, object], terminal: bool) -> None:
        del terminal
        payload: object = frame.get("payload")
        if isinstance(payload, Mapping) and payload.get("library_groups") == 1:
            observed.set()

    owner.attach_broadcast(broadcast)
    thread: threading.Thread = _serving(owner)
    source: Path = _library_dir(tmp_path) / "Episode.txt"
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
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
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


def test_automatic_work_plans_with_the_persisted_recipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    recipes: RecipePreferences = RecipePreferences(translate=TranslateRecipe(text_result=TextResultFormat.SUBTITLES))
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), recipes=recipes))
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert service.recipes == [recipes]
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize(
    ("settled", "admitted"),
    [(frozenset({ProductKind.TRANSLATED_TEXT}), True), (frozenset({ProductKind.SPOKEN_PL}), False)],
)
def test_a_marker_is_weighed_against_the_products_the_group_would_get(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settled: frozenset[ProductKind],
    admitted: bool,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    marker: ManualHandledMarker = ManualHandledMarker(
        group_id=group_id,
        fingerprint=_fingerprint(tmp_path),
        products=settled,
        request_id="settled-1",
        recorded_at=_MOMENT.isoformat(),
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), markers=(marker,)))
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.submitted_event.wait(_TIMEOUT_S if admitted else 0.3) is admitted
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize(
    ("text_result", "planned"),
    [(TextResultFormat.TEXT, "translated_text"), (TextResultFormat.SUBTITLES, "full_pl")],
)
def test_a_preview_of_a_translate_group_follows_the_persisted_recipe(
    tmp_path: Path,
    text_result: TextResultFormat,
    planned: str,
) -> None:
    write_text_source(_library_dir(tmp_path) / "Episode.txt", "Text")
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME)
    store.save(WatchState(recipes=RecipePreferences(translate=TranslateRecipe(text_result=text_result))))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}))
        assert response.ok, response.message
        groups = cast("list[Mapping[str, object]]", response.result["groups"])
        assert [entry["planned_products"] for entry in groups] == [[planned]]
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


def test_a_product_published_beside_its_source_stays_background_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    published: Path = _library_dir(tmp_path) / "Episode.pl.txt"
    write_text_source(published, "Text")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(paths=(published,)))
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert store.load().requests[0].origin is RequestOrigin.BACKGROUND
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_an_image_arriving_in_cover_invalidates_the_preview_of_its_own_group(tmp_path: Path) -> None:
    directory: Path = tmp_path / COVER_DIRECTORY
    directory.mkdir(parents=True)
    write_text_source(directory / "Episode.txt", "Text")
    write_image_source(directory / "Episode.png")
    real: AppService = _real_service(tmp_path)
    workspace = real.discover()
    assert [group.source.stem for group in workspace.groups] == ["Episode"]
    plan: ExecutionPlan = real.plan_auto((workspace.groups[0].group_id,), _PRESET)
    service = _Service(tmp_path, discovered=workspace, plan=plan, subscriptions=_Subscriptions())
    store: WatchStateStore = WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}))
        assert preview.ok, preview.message
        joined: Path = directory / "Episode.jpg"
        write_image_source(joined)
        owner.files_changed(DirectoryChange(paths=(joined,)))
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


def _fingerprint(tmp_path: Path) -> SourceFingerprint:
    group: InspectedSourceGroup = _real_service(tmp_path).discover().groups[0]
    return watch_module.source_fingerprint(watch_module.snapshot_sources(group, {}, 0.0))


@pytest.mark.parametrize("name", ["Episode.srt", "Episode.pl.srt"])
def test_new_sidecars_and_changed_products_invalidate_the_affected_preview(tmp_path: Path, name: str) -> None:
    service, store, _ = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        preview: ControlResponse = owner.handle(_request("preview", {"client_id": _CLIENT}))
        assert preview.ok
        source: Path = _library_dir(tmp_path) / name
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


def _await(condition: Callable[[], bool]) -> bool:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def _settled_starts(service: _Service, expected: int) -> int:
    deadline: float = time.monotonic() + 0.4
    while len(service.submitted) <= expected and time.monotonic() < deadline:
        time.sleep(0.01)
    return len(service.submitted)


def _finish_started(service: _Service, groups: Sequence[str]) -> None:
    for run_id, group_id in zip(tuple(service.active), groups, strict=False):
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)


def _owned(
    files: tuple[str, ...],
    complete: tuple[str, ...],
    origin: RequestOrigin,
    size: int,
    *,
    directory: str = TRANSLATE_DIRECTORY,
) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        "operation-9",
        "9",
        directory,
        files,
        AcquisitionState.ACCEPTED,
        origin,
        None,
        "9",
        _MOMENT.isoformat(),
        complete_files=complete,
        file_layout=tuple((index, name, size) for index, name in enumerate(files)),
        content_started=True,
    )


def _two_sources(tmp_path: Path) -> tuple[_Service, WatchStateStore, dict[str, str]]:
    write_text_source(_library_dir(tmp_path) / "Episode.txt", "Text")
    write_text_source(_library_dir(tmp_path) / "Film.txt", "Text")
    real: AppService = _real_service(tmp_path)
    workspace = real.discover()
    groups: dict[str, str] = {group.source.stem: group.group_id for group in workspace.groups}
    plan: ExecutionPlan = real.plan_auto((groups["Film"],), _PRESET)
    service = _Service(tmp_path, discovered=workspace, plan=plan, subscriptions=_Subscriptions())
    return service, WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), groups


def test_an_independent_file_beside_an_incomplete_transfer_still_reaches_auto(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, groups = _two_sources(tmp_path)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("Episode.txt",), (), RequestOrigin.USER, 4),),
        )
    )
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    started: tuple[str, ...] = ()
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert _settled_starts(service, 1) == 1
        started = tuple(group for request in store.load().requests for group in request.group_ids)
    finally:
        _finish_started(service, (groups["Film"],))
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert started == (groups["Film"],)


def test_a_finished_file_of_a_transfer_reaches_auto_while_its_other_file_still_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, groups = _two_sources(tmp_path)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("Episode.txt", "Film.txt"), ("Film.txt",), RequestOrigin.USER, 4),),
        )
    )
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    recorded: tuple[ProcessingRequest, ...] = ()
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert _settled_starts(service, 1) == 1
        recorded = store.load().requests
    finally:
        _finish_started(service, (groups["Film"],))
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert tuple(group for request in recorded for group in request.group_ids) == (groups["Film"],)
    assert recorded[0].origin is RequestOrigin.USER


def test_further_progress_reads_admit_the_newly_complete_file_and_never_restart_the_earlier_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.02)
    service, store, groups = _two_sources(tmp_path)
    size: int = (_library_dir(tmp_path) / "Film.txt").stat().st_size
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(_library_dir(tmp_path)), size, size)
    network.entries = (
        TorrentFile(0, "Episode.txt", size, 0.5, 1),
        TorrentFile(1, "Film.txt", size, 1.0, 1),
    )
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("Episode.txt", "Film.txt"), (), RequestOrigin.USER, size),),
        )
    )
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    recorded: tuple[ProcessingRequest, ...] = ()
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.submitted_event.wait(_TIMEOUT_S)
        assert _settled_starts(service, 1) == 1
        network.entries = (
            TorrentFile(0, "Episode.txt", size, 1.0, 1),
            TorrentFile(1, "Film.txt", size, 1.0, 1),
        )
        network.tracked["9"] = replace(
            network.tracked["9"], progress=1.0, state="stoppedUP", amount_left=0, completed=2 * size
        )
        assert _await(lambda: len(service.submitted) == 2)
        assert _settled_starts(service, 2) == 2
        recorded = store.load().requests
    finally:
        _finish_started(service, (groups["Film"], groups["Episode"]))
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert network.info_calls >= 2
    assert store.load().acquisitions[0].state is AcquisitionState.COMPLETE
    assert tuple(group for request in recorded for group in request.group_ids) == (groups["Film"], groups["Episode"])


def test_a_stopped_transfer_reserves_flat_names_before_its_content_is_started(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Neko Pack", "9", 0.0, "stoppedDL", str(tmp_path), 8, 0)
    network.entries = (
        TorrentFile(0, "Neko Pack/Season 1/09.mkv", 4, 0.0, 1),
        TorrentFile(1, "Neko Pack/Season 1/09.ass", 4, 0.0, 1),
    )
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((item,), frozenset())
    _drain_owner_queue(owner)
    reserved: AcquisitionConfirmation = store.load().acquisitions[0]

    assert network.renamed == [
        ("9", "Neko Pack/Season 1/09.mkv", "09.mkv"),
        ("9", "Neko Pack/Season 1/09.ass", "09.ass"),
    ]
    assert network.started == []
    assert reserved.file_layout == ((0, "09.mkv", 4), (1, "09.ass", 4))
    assert reserved.content_started is False

    owner._inspect_transfers((reserved,), frozenset())
    _drain_owner_queue(owner)
    running: AcquisitionConfirmation = store.load().acquisitions[0]

    assert network.started == ["9"]
    assert network.renamed[-1] == ("9", "Neko Pack/Season 1/09.ass", "09.ass")
    assert running.content_started is True
    assert running.required_files == ("09.mkv", "09.ass")
    assert running.state is AcquisitionState.ACCEPTED


def test_a_transfer_whose_names_are_not_reserved_yet_defers_the_resume_a_client_asked_for(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        torrent_management=cast("TorrentManagement", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service.acquisition = acquisition
    waiting: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9",
        "9",
        "",
        (),
        AcquisitionState.ACCEPTED,
        RequestOrigin.USER,
        None,
        "9",
        _MOMENT.isoformat(),
        requested_action="resume",
        action_pending=True,
    )
    owner: AutomationOwner = _owner(service, store)

    assert owner._apply_transfer_action(acquisition, waiting) == waiting
    assert network.actions == []

    settled: AcquisitionConfirmation = owner._apply_transfer_action(
        acquisition, replace(waiting, file_layout=((0, "09.mkv", 4),))
    )

    assert network.actions == [("9", "resume")]
    assert settled.action_pending is False
    assert settled.problem is None


def test_the_stored_range_of_a_subscription_is_applied_once_for_a_repeated_command(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    subscriptions: _Subscriptions = cast("_Subscriptions", service.subscriptions)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    command: ControlRequest = _request(
        "subscription_range",
        {"subscription_id": "a", "selected": ["3", "8"], "future_from": "12"},
    )
    try:
        answer: ControlResponse = owner.handle(command)
        again: ControlResponse = owner.handle(command)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert answer.ok, answer.message
    assert again.result == answer.result
    assert subscriptions.stored_ranges == [((Decimal(3), Decimal(8)), Decimal(12))]
    assert all(item.pending is None for item in store.load().command_receipts)


def test_a_repeat_command_orders_the_named_episodes_again(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    subscriptions: _Subscriptions = cast("_Subscriptions", service.subscriptions)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(
            _request("subscription_repeat", {"subscription_id": "a", "episodes": ["7.5", "9"]})
        )
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert answer.ok, answer.message
    assert subscriptions.ordered_again == [(Decimal("7.5"), Decimal(9))]
    assert all(item.pending is None for item in store.load().command_receipts)


@pytest.mark.parametrize(
    "payload",
    [
        {"subscription_id": "a", "selected": ["nine"]},
        {"subscription_id": "a", "selected": ["0"]},
        {"subscription_id": "a", "selected": "3"},
        {"subscription_id": "a", "selected": ["3"], "future_from": "later"},
        {"subscription_id": "unknown", "selected": ["3"]},
        {"selected": ["3"]},
    ],
)
def test_a_range_command_without_valid_numbers_of_a_followed_subscription_is_refused(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    service, store, _ = _library(tmp_path)
    subscriptions: _Subscriptions = cast("_Subscriptions", service.subscriptions)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("subscription_range", payload))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert not answer.ok
    assert subscriptions.stored_ranges == []
    assert store.load().command_receipts == ()


@pytest.mark.parametrize("episodes", [[], ["nine"], ["-2"]])
def test_a_repeat_command_without_valid_episode_numbers_is_refused(tmp_path: Path, episodes: list[str]) -> None:
    service, store, _ = _library(tmp_path)
    subscriptions: _Subscriptions = cast("_Subscriptions", service.subscriptions)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(
            _request("subscription_repeat", {"subscription_id": "a", "episodes": episodes})
        )
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert not answer.ok
    assert subscriptions.ordered_again == []


def test_the_status_names_the_library_group_each_transfer_owns(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    store.save(WatchState(acquisitions=(_owned(("Episode.txt",), ("Episode.txt",), RequestOrigin.USER, 4),)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    assert answer.ok, answer.message
    acquisitions: object = answer.result["acquisitions"]
    assert isinstance(acquisitions, list)
    assert acquisitions[0]["group_ids"] == [group_id]


def _relocating_owner(tmp_path: Path, service: AppService, store: WatchStateStore) -> AutomationOwner:
    return AutomationOwner(
        service,
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
        ready_store=ReadyStore(tmp_path / "control" / "relocations", tmp_path),
    )


def _prepared_audiobook(tmp_path: Path) -> Path:
    audiobook: Path = tmp_path / "audiobook"
    audiobook.mkdir()
    write_text_source(audiobook / "Book.txt", "Zażółć gęślą jaźń.")
    (audiobook / "Book.m4a").write_bytes(b"recording")
    journal: ReadyStore = ReadyStore(tmp_path / "control" / "relocations", tmp_path)
    assert journal.prepare(discover_groups(tmp_path).groups[0], (audiobook / "Book.m4a",)) is not None
    return audiobook


def test_a_finished_group_relocates_its_product_and_leaves_the_source_its_transfer_still_holds(
    tmp_path: Path,
) -> None:
    audiobook: Path = _prepared_audiobook(tmp_path)
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    store.save(WatchState(acquisitions=(_owned(("Book.txt",), (), RequestOrigin.USER, 4, directory="audiobook"),)))
    owner: AutomationOwner = _relocating_owner(tmp_path, service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await((tmp_path / "ready" / "Book.m4a").exists)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()
    recorded: ReadyGroup = store.load().ready_groups[0]
    assert recorded.pending_sources == ("audiobook/Book.txt",)
    assert recorded.products == ("ready/Book.m4a",)
    assert recorded.sources == ()
    assert (audiobook / "Book.txt").read_text(encoding="utf-8") == "Zażółć gęślą jaźń."
    assert not (tmp_path / "ready" / "Book.txt").exists()


def test_a_transfer_that_released_its_file_lets_the_deferred_source_reach_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.05)
    audiobook: Path = _prepared_audiobook(tmp_path)
    size: int = (audiobook / "Book.txt").stat().st_size
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Book", "9", 0.5, "downloading", str(audiobook), size, 0)
    network.entries = (TorrentFile(0, "Book.txt", size, 0.5, 1),)
    service: AppService = _real_service(
        tmp_path,
        acquisition=AcquisitionService(
            source=network,
            client=cast("TorrentClient", network),
            torrent_management=cast("TorrentManagement", network),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
        ),
    )
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    store.save(WatchState(acquisitions=(_owned(("Book.txt",), (), RequestOrigin.USER, size, directory="audiobook"),)))
    owner: AutomationOwner = _relocating_owner(tmp_path, service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await((tmp_path / "ready" / "Book.m4a").exists)
        assert (audiobook / "Book.txt").exists()
        network.entries = (TorrentFile(0, "Book.txt", size, 1.0, 1),)
        network.tracked["9"] = replace(
            network.tracked["9"], progress=1.0, state="stoppedUP", amount_left=0, completed=size
        )
        assert _await((tmp_path / "ready" / "Book.txt").exists)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()
    assert frozenset({"9"}) in network.released
    assert list(audiobook.iterdir()) == []
    assert store.load().ready_groups[0].pending_sources == ()
    assert store.load().ready_groups[0].sources == ("ready/Book.txt",)


@pytest.mark.integration
def test_the_panel_stores_a_whole_range_and_repeats_an_episode_through_the_resident(tmp_path: Path) -> None:
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
        clock=lambda: _MOMENT,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition, subscriptions=subscriptions)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(control_endpoint(tmp_path), key, owner.handle, on_disconnect=owner.disconnect)
    session: ResidentSession = ResidentSession(
        tmp_path,
        lambda: ControlClient(control_endpoint(tmp_path), key, timeout_s=_TIMEOUT_S),
    )
    try:
        followed: Subscription = session.follow(SubscriptionOrder("Neko to Ryuu", "SubsPlease", "neko", Decimal(20)))
        stored: Subscription = session.set_range(
            followed.subscription_id, selected=(Decimal(9), Decimal(10)), future_from=Decimal(11)
        )
        repeated: Subscription = session.repeat(followed.subscription_id, (Decimal(9),))
    finally:
        session.close()
        server.close()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()
    assert stored.future_from == Decimal(11)
    assert {item.number for item in stored.episodes if item.selected} == {Decimal(9), Decimal(10)}
    assert stored.generation > followed.generation
    assert repeated.generation > stored.generation
    assert next(item.repeat_id for item in repeated.episodes if item.number == Decimal(9)) is not None
    assert next(item.number for item in repeated.repeats) == Decimal(9)
    assert all(item.pending is None for item in store.load().command_receipts)


def test_two_transfers_of_one_file_name_reserve_separate_names_beside_ready_and_deleted_files(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("First", "9", 0.0, "stoppedDL", str(tmp_path), 4, 0)
    network.tracked["10"] = TorrentInfo("Second", "10", 0.0, "stoppedDL", str(tmp_path), 4, 0)
    network.entries = (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),)
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    first: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    second: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-10",
        "10",
        "",
        (),
        AcquisitionState.ACCEPTED,
        RequestOrigin.BACKGROUND,
        None,
        "10",
        _MOMENT.isoformat(),
    )
    store.save(
        WatchState(
            acquisitions=(first, second),
            ready_groups=(
                ReadyGroup(
                    set_id="finished-set",
                    group_id="finished-group",
                    stem="09",
                    source_directory="",
                    source_stem="09",
                    target=WorkflowTarget.TRANSLATE,
                    sources=("ready/09.mkv",),
                    products=(),
                ),
            ),
            pending_deletions=(PendingDeletion("deletion-1", "old-set", _MOMENT.isoformat(), (("09.ass", 4, 1),)),),
        )
    )
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((first, second), owner._reserved_names())
    _drain_owner_queue(owner)

    layouts: dict[str, tuple[FileReservation, ...]] = {
        item.info_hash: item.file_layout for item in store.load().acquisitions
    }
    assert layouts == {"9": ((0, "09 [2].mkv", 4),), "10": ((0, "09 [3].mkv", 4),)}
    assert network.renamed == [("9", "Pack/09.mkv", "09 [2].mkv"), ("10", "Pack/09.mkv", "09 [3].mkv")]


def test_a_file_already_lying_in_the_workspace_keeps_an_incoming_set_off_its_name(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    standing: Path = tmp_path / "09.mkv"
    standing.write_bytes(b"the episode a person put here")
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.0, "stoppedDL", str(tmp_path), 8, 0)
    network.entries = (
        TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),
        TorrentFile(1, "Pack/09.ass", 4, 0.0, 1),
    )
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert store.load().acquisitions[0].file_layout == ((0, "09 [2].mkv", 4), (1, "09 [2].ass", 4))
    assert network.renamed == [
        ("9", "Pack/09.mkv", "09 [2].mkv"),
        ("9", "Pack/09.ass", "09 [2].ass"),
    ]
    assert standing.read_bytes() == b"the episode a person put here"


def test_a_subfolder_of_the_workspace_never_pushes_an_incoming_set_off_its_release_name(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    (tmp_path / "09").mkdir()
    (tmp_path / "09" / "Episode.txt").write_text("Text", encoding="utf-8")
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.0, "stoppedDL", str(tmp_path), 4, 0)
    network.entries = (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),)
    service.acquisition = AcquisitionService(
        source=network, client=cast("TorrentClient", network), workspace_root=tmp_path, parse_name=parse_release_name
    )
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9", "9", "", (), AcquisitionState.ACCEPTED, RequestOrigin.USER, None, "9", _MOMENT.isoformat()
    )
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert store.load().acquisitions[0].file_layout == ((0, "09.mkv", 4),)
    assert network.renamed == [("9", "Pack/09.mkv", "09.mkv")]


def _stopped_transfer(tmp_path: Path, service: _Service, entries: tuple[TorrentFile, ...]) -> _TorrentNetwork:
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.0, "stoppedDL", str(tmp_path), 4, 0)
    network.entries = entries
    service.acquisition = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
        torrent_management=cast("TorrentManagement", network),
    )
    return network


def _accepted_transfer(
    info_hash: str,
    *,
    layout: tuple[FileReservation, ...] = (),
    started: bool = False,
) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        f"operation-{info_hash}",
        info_hash,
        "",
        (),
        AcquisitionState.ACCEPTED,
        RequestOrigin.USER,
        None,
        info_hash,
        _MOMENT.isoformat(),
        file_layout=layout,
        content_started=started,
    )


def test_a_destination_that_cannot_be_read_holds_that_release_without_starting_its_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    network.tracked["10"] = TorrentInfo("Other", "10", 0.5, "downloading", str(tmp_path), 2, 2)
    fresh: AcquisitionConfirmation = _accepted_transfer("9")
    writing: AcquisitionConfirmation = _accepted_transfer("10", layout=((0, "09.mkv", 4),), started=True)
    store.save(WatchState(acquisitions=(fresh, writing)))
    owner: AutomationOwner = _owner(service, store)
    listing: Callable[[Path], Iterator[Path]] = Path.iterdir

    def refuse(self: Path) -> Iterator[Path]:
        if self == tmp_path:
            raise PermissionError(13, "denied")
        return listing(self)

    monkeypatch.setattr(Path, "iterdir", refuse)
    reserved: frozenset[str] | None = owner._reserved_names()
    owner._inspect_transfers((fresh, writing), reserved)
    _drain_owner_queue(owner)

    stored: dict[str, AcquisitionConfirmation] = {item.info_hash: item for item in store.load().acquisitions}
    assert stored["9"].problem is not None
    assert stored["9"].file_layout == ()
    assert stored["9"].content_started is False
    assert stored["10"].problem is None
    assert stored["10"].file_layout == ((0, "09.mkv", 4),)
    assert network.renamed == []
    assert network.started == []
    assert reserved is None


def test_a_hidden_file_already_lying_in_the_workspace_keeps_an_incoming_set_off_its_name(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    hidden: Path = tmp_path / ".09.mkv"
    hidden.write_bytes(b"the hidden episode a person put here")
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "Pack/.09.mkv", 4, 0.0, 1),))
    item: AcquisitionConfirmation = _accepted_transfer("9")
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert store.load().acquisitions[0].file_layout == ((0, ".09 [2].mkv", 4),)
    assert network.renamed == [("9", "Pack/.09.mkv", ".09 [2].mkv")]
    assert hidden.read_bytes() == b"the hidden episode a person put here"


def test_anything_taking_a_reserved_name_before_the_start_holds_that_release_without_reserving_again(
    tmp_path: Path,
) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    store.save(WatchState(acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),)))
    taken: Path = tmp_path / "09.mkv"
    taken.write_bytes(b"the episode a person put here")
    owner: AutomationOwner = _owner(service, store)

    for _ in range(2):
        owner._inspect_transfers((store.load().acquisitions[0],), owner._reserved_names())
        _drain_owner_queue(owner)

    held: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.started == []
    assert network.renamed == []
    assert held.problem is not None
    assert held.file_layout == ((0, "09.mkv", 4),)
    assert held.content_started is False
    assert taken.read_bytes() == b"the episode a person put here"


def _held_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AutomationOwner, _TorrentNetwork, WatchStateStore, Path]:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    store.save(WatchState(acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),)))
    taken: Path = tmp_path / "09.mkv"
    taken.write_bytes(b"the episode a person put here")
    return _owner(service, store), network, store, taken


def _commanded(owner: AutomationOwner, action: str) -> bool:
    return owner.handle(_request("transfer", {"info_hash": "9", "action": action})).ok


def test_a_resume_starts_a_held_release_once_the_name_that_held_it_up_is_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, network, store, taken = _held_release(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 0)
        assert network.started == []
        taken.unlink()
        assert _commanded(owner, "resume")
        assert _await(lambda: network.started == ["9"])
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    settled: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.actions == [("9", "resume")]
    assert network.renamed == []
    assert settled.content_started is True
    assert settled.problem is None


def test_a_stop_leaves_a_held_release_stopped_even_once_its_name_is_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, network, store, taken = _held_release(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 0)
        taken.unlink()
        assert _commanded(owner, "stop")
        assert _await(lambda: network.actions == [("9", "stop")])
        polled: int = network.info_calls
        assert _await(lambda: network.info_calls > polled + 1)
        assert network.started == []
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    settled: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.started == []
    assert network.renamed == []
    assert settled.content_started is False


def test_a_transfer_whose_own_reserved_names_are_in_place_never_reserves_them_again(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    ours: Path = tmp_path / "09.mkv"
    ours.write_bytes(b"data")
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 2, 2)
    store.save(
        WatchState(acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),)),
    )
    owner: AutomationOwner = _owner(service, store)

    for _ in range(2):
        owner._inspect_transfers((store.load().acquisitions[0],), owner._reserved_names())
        _drain_owner_queue(owner)

    settled: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.renamed == []
    assert network.started == []
    assert settled.file_layout == ((0, "09.mkv", 4),)
    assert settled.content_started is True
    assert settled.problem is None


def _dangling_link(link: Path) -> None:
    try:
        link.symlink_to(link.with_name("missing-target.mkv"))
    except OSError:
        pytest.skip("File symlinks are unavailable on this system")


def test_a_dangling_link_wearing_an_incoming_name_keeps_that_set_off_it(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    _dangling_link(tmp_path / "09.mkv")
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),))
    item: AcquisitionConfirmation = _accepted_transfer("9")
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert store.load().acquisitions[0].file_layout == ((0, "09 [2].mkv", 4),)
    assert network.renamed == [("9", "Pack/09.mkv", "09 [2].mkv")]
    assert network.started == []


def _unreadable_entry(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    reading: Callable[..., os.stat_result] = Path.stat
    testing: Callable[..., bool] = Path.is_file

    def missing(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise FileNotFoundError(2, "missing target")
        return reading(self, follow_symlinks=follow_symlinks)

    def plain(self: Path, *, follow_symlinks: bool = True) -> bool:
        return False if self == path else testing(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", missing)
    monkeypatch.setattr(Path, "is_file", plain)


def test_an_entry_that_no_longer_reads_as_a_file_still_keeps_an_incoming_set_off_its_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = _library(tmp_path)
    (tmp_path / "09.mkv").write_bytes(b"link")
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),))
    item: AcquisitionConfirmation = _accepted_transfer("9")
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)
    _unreadable_entry(monkeypatch, tmp_path / "09.mkv")

    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert store.load().acquisitions[0].file_layout == ((0, "09 [2].mkv", 4),)
    assert network.renamed == [("9", "Pack/09.mkv", "09 [2].mkv")]
    assert network.started == []


def test_a_name_that_still_has_a_directory_entry_holds_a_release_that_reserved_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    store.save(WatchState(acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),)))
    (tmp_path / "09.mkv").write_bytes(b"link")
    owner: AutomationOwner = _owner(service, store)
    _unreadable_entry(monkeypatch, tmp_path / "09.mkv")

    owner._inspect_transfers((store.load().acquisitions[0],), owner._reserved_names())
    _drain_owner_queue(owner)

    held: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.started == []
    assert network.renamed == []
    assert held.problem is not None
    assert held.content_started is False


def _real_client_handler(root: Path, seen: list[tuple[str, str]]) -> Callable[[httpx.Request], httpx.Response]:
    names: dict[int, str] = {0: "Neko no Ken - 06/06.mkv", 1: "Neko no Ken - 06/06.ass"}

    def handler(request: httpx.Request) -> httpx.Response:
        path: str = request.url.path.removeprefix("/api/v2")
        body: str = request.content.decode("utf-8")
        seen.append((path, body))
        if path == "/torrents/renameFile":
            form: dict[str, list[str]] = parse_qs(body)
            moved: int = next(key for key, name in names.items() if name == form["oldPath"][0])
            names[moved] = form["newPath"][0]
        if path == "/torrents/info":
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": "9",
                        "name": "Neko no Ken - 06",
                        "progress": 0.0,
                        "state": "stoppedDL",
                        "save_path": str(root),
                        "amount_left": 6,
                        "completed": 0,
                    }
                ],
            )
        if path == "/torrents/files":
            return httpx.Response(
                200,
                json=[
                    {
                        "index": 0,
                        "name": names[0],
                        "size": 4,
                        "progress": 0.0,
                        "priority": 1,
                        "is_seed": False,
                        "availability": 0.0,
                        "piece_range": [0, 3],
                    },
                    {
                        "index": 1,
                        "name": names[1],
                        "size": 2,
                        "progress": 0.0,
                        "priority": 1,
                        "availability": 0.0,
                        "piece_range": [4, 4],
                    },
                ],
            )
        return httpx.Response(200, text="Ok.")

    return handler


def test_a_multi_file_release_of_the_real_client_reserves_every_name_and_starts(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    seen: list[tuple[str, str]] = []
    http: httpx.Client = httpx.Client(transport=httpx.MockTransport(_real_client_handler(tmp_path, seen)))
    client: QBittorrentClient = QBittorrentClient("http://127.0.0.1:8080", http=http)
    service.acquisition = AcquisitionService(
        source=_TorrentNetwork(),
        client=client,
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    item: AcquisitionConfirmation = _accepted_transfer("9")
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    with http:
        owner._inspect_transfers((item,), owner._reserved_names())
        _drain_owner_queue(owner)
        reserved: AcquisitionConfirmation = store.load().acquisitions[0]
        owner._inspect_transfers((reserved,), owner._reserved_names())
        _drain_owner_queue(owner)

    started: AcquisitionConfirmation = store.load().acquisitions[0]
    assert reserved.problem is None
    assert reserved.file_layout == ((0, "06.mkv", 4), (1, "06.ass", 2))
    assert started.content_started is True
    assert ("/torrents/renameFile", "hash=9&oldPath=Neko+no+Ken+-+06%2F06.mkv&newPath=06.mkv") in seen
    assert ("/torrents/renameFile", "hash=9&oldPath=Neko+no+Ken+-+06%2F06.ass&newPath=06.ass") in seen
    assert ("/torrents/start", "hashes=9") in seen


def _reported_problem(owner: AutomationOwner) -> tuple[bool, bool]:
    status: Mapping[str, object] = owner._status()
    transfers: list[Mapping[str, object]] = cast("list[Mapping[str, object]]", status["transfers"])
    acquisitions: list[Mapping[str, object]] = cast("list[Mapping[str, object]]", status["acquisitions"])
    return (
        any(item["info_hash"] == "9" for item in transfers),
        any(item["info_hash"] == "9" and item["problem"] for item in acquisitions),
    )


def test_a_release_the_client_still_reports_publishes_its_unreadable_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, store, _ = _library(tmp_path)
    _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    item: AcquisitionConfirmation = _accepted_transfer("9")
    store.save(WatchState(acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)
    listing: Callable[[Path], Iterator[Path]] = Path.iterdir

    def refuse(self: Path) -> Iterator[Path]:
        if self == tmp_path:
            raise PermissionError(13, "denied")
        return listing(self)

    monkeypatch.setattr(Path, "iterdir", refuse)
    owner._inspect_transfers((item,), owner._reserved_names())
    _drain_owner_queue(owner)

    assert _reported_problem(owner) == (True, True)


def test_a_release_the_client_still_reports_publishes_its_occupied_name(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    store.save(WatchState(acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),)))
    (tmp_path / "09.mkv").write_bytes(b"the episode a person put here")
    owner: AutomationOwner = _owner(service, store)

    owner._inspect_transfers((store.load().acquisitions[0],), owner._reserved_names())
    _drain_owner_queue(owner)

    assert _reported_problem(owner) == (True, True)


def test_a_release_the_client_still_reports_publishes_its_failing_inspection(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    network.unreadable_files = True
    store.save(WatchState(acquisitions=(_accepted_transfer("9"),)))
    owner: AutomationOwner = _owner(service, store)

    for _ in range(3):
        owner._inspect_transfers((store.load().acquisitions[0],), owner._reserved_names())
        _drain_owner_queue(owner)

    assert _reported_problem(owner) == (True, True)
