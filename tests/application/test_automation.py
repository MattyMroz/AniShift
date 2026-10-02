from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Final, cast
from urllib.parse import parse_qs

import httpx
import pytest
from fakes import (
    CollectingRunSink,
    FakeMediaProbe,
    FakeTranslationService,
    write_image_source,
    write_media_source,
    write_text_source,
)
from loguru import logger as loguru_logger
from test_service import _panel_owner
from test_service import _service as _processing_service

import anishift.application.automation as automation_module
import anishift.application.library as library_module
import anishift.application.watch as watch_module
from anishift.application import SCAN_INTERVAL_S, TaskState
from anishift.application.acquisition import (
    AcquisitionService,
    DownloadReceipt,
    ReleaseCatalog,
    ReleaseChoice,
    TorrentClient,
    TorrentManagement,
)
from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
    create_group_id,
)
from anishift.application.automation import (
    TRANSFER_BACKOFF_CEILING_S,
    TRANSFER_CHECK_INTERVAL_S,
    AutomationOwner,
)
from anishift.application.cancellation import EventCancellationToken
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AudiobookRecipe,
    AutomationPolicy,
    DeletionStatus,
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
from anishift.application.control_views import DeletionPreview, LibrarySet, PlanPreview, decode_view, encode_view
from anishift.application.discovery import discover_groups
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import EpisodeKey, EpisodeListing, EpisodeOffer
from anishift.application.events import RunEvent, RunEventKind
from anishift.application.history import HistoryJournal, HistoryKind
from anishift.application.inspection import (
    InspectedSourceGroup,
    InspectedWorkspace,
    InspectionWarning,
    WorkspaceInspector,
)
from anishift.application.intents import GroupIntent, ProductIntent, ProductKind, RebuildRequest, RequestOrigin, RunMode
from anishift.application.planning import ExecutionPlan
from anishift.application.products import classify_product
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.recovery import RunJournal
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.application.scheduler import RunHandle
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.application.subscription_targets import PauseReason, SubscriptionRecord
from anishift.application.tts_handler import TtsProgressObserver
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.cli.interactive.anime import AnimeController
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext, ExecutionError, PlanningError
from anishift.paths import COVER_DIRECTORY, READY_DIRECTORY, TRANSLATE_DIRECTORY, relocation_journal_dir
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
from anishift.platform.recycle import RecycleResult
from anishift.services.catalog import AniListCatalog, AniZipCatalog
from anishift.services.http_requests import RequestControl
from anishift.services.media import DefaultMediaProbe
from anishift.services.torrents import (
    Release,
    TorrentClientError,
    TorrentFile,
    TorrentInfo,
    TorrentioSource,
    parse_release_name,
)
from anishift.services.torrents.categories import SEARCH_CATEGORIES
from anishift.services.torrents.nyaa import search_releases
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.tts import SpeechBatch, SpeechBatchResult

_TIMEOUT_S: Final[float] = 5.0

_SHARING_VIOLATION: Final[int] = 32

_INSTANCE: Final[str] = "instance-1"

_CLIENT: Final[str] = "panel-1"

_MOMENT: Final[datetime] = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

_STORE_FROZEN: Final[str] = "The state file stopped accepting writes"

_STOP_REFUSED: Final[str] = "The client refused to stop this transfer"

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
        self.before_info: Callable[[], None] | None = None
        self.before_action: Callable[[], None] | None = None
        self.lose_response: bool = False
        self.entries: tuple[TorrentFile, ...] = ()
        self.per_hash: dict[str, tuple[TorrentFile, ...]] = {}
        self.info_calls: int = 0
        self.unreachable: bool = False
        self.unstartable: bool = False
        self.resume_calls: int = 0
        self.renamed: list[tuple[str, str, str]] = []
        self.started: list[str] = []
        self.actions: list[tuple[str, str]] = []
        self.released: list[frozenset[str]] = []
        self.unreadable_files: bool = False
        self.prepared: int = 0
        self.closed_owned: int = 0
        self.unpreparable: bool = False

    def download_scope(self, hashes: frozenset[str]) -> nullcontext[None]:
        del hashes
        return nullcontext()

    def transfer_action(self, info_hash: str, action: str) -> None:
        self.actions.append((info_hash, action))
        if self.before_action is not None:
            self.before_action()

    def prepare(self) -> None:
        self.prepared += 1
        if self.unpreparable:
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                    message="The private torrent client could not start; resolve the problem and explicitly resume",
                )
            )

    def close_owned(self) -> None:
        self.closed_owned += 1

    def release_completed(self, hashes: frozenset[str]) -> frozenset[str]:
        self.released.append(hashes)
        return hashes

    def finalizable_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        return hashes

    def released_hashes(self, hashes: frozenset[str]) -> frozenset[str]:
        return hashes & frozenset(value for batch in self.released for value in batch)

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
        if self.before_info is not None:
            self.before_info()
        if self.unreachable:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="The Web UI is closed")
            )
        return tuple(self.tracked.values())

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        if self.unreadable_files:
            raise TorrentClientError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_REFUSED, message="qBittorrent returned unreadable file metadata"
                )
            )
        return self.per_hash.get(info_hash, self.entries)


class _Service:
    def __init__(
        self,
        workspace_root: Path,
        *,
        discovered: object,
        plan: ExecutionPlan,
    ) -> None:
        self.workspace_root: Path = workspace_root
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
        self.paused: list[bool] = []

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

    def pause_runs(self) -> None:
        self.paused.append(True)

    def resume_runs(self) -> None:
        self.paused.append(False)

    def retain_runs(self, run_ids: Sequence[str]) -> None:
        del run_ids

    def reload_preferences(self) -> None:
        self.reloads += 1


def _owner(
    service: _Service | AppService,
    store: WatchStateStore,
    *,
    scan_interval_s: float = SCAN_INTERVAL_S,
    recycler: Callable[[Path, tuple[int, int, int, int]], RecycleResult] | None = None,
) -> AutomationOwner:
    return AutomationOwner(
        cast("AppService", service),
        store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
        scan_interval_s=scan_interval_s,
        recycler=recycler,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario", ["titles", "empty", "catalog_failed", "source_failed", "internal", "planning", "io"]
)
def test_anime_enter_search_crosses_owner_ipc_and_controlled_http(  # noqa: PLR0915
    tmp_path: Path, scenario: str
) -> None:
    sent: list[str] = []
    now: list[float] = [1000.0]

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.host)
        assert request.url.host in {"graphql.anilist.co", "api.ani.zip", "torrentio.strem.fun"}
        if request.url.host == "api.ani.zip":
            return httpx.Response(
                200,
                json={
                    "mappings": {"kitsu_id": 10, "type": "TV"},
                    "episodeCount": 1,
                    "episodes": {"1": {"episodeNumber": 1, "seasonNumber": 1}},
                },
            )
        if request.url.host == "torrentio.strem.fun":
            return httpx.Response(503)
        failures: dict[str, Exception] = {
            "internal": RuntimeError("private-provider-payload"),
            "planning": PlanningError(
                context=ErrorContext(code=ErrorCode.IO_ERROR, message="private-provider-payload")
            ),
            "io": OSError("private-provider-payload"),
        }
        if scenario in failures:
            raise failures[scenario]
        body: dict[str, object] = {
            "data": {
                "Page": {
                    "media": []
                    if scenario == "empty"
                    else [
                        {
                            "id": 1,
                            "type": "ANIME",
                            "format": "TV",
                            "title": {"romaji": "Fixture"},
                            "status": "FINISHED",
                            "relations": {"edges": []},
                        }
                    ]
                }
            }
        }
        if scenario == "catalog_failed":
            body = {"errors": [{"message": "private-provider-payload"}]}
        if scenario == "source_failed":
            node: dict[str, object] = {
                "id": 1,
                "type": "ANIME",
                "format": "TV",
                "title": {"romaji": "Fixture"},
                "status": "FINISHED",
                "episodes": 1,
                "relations": {"edges": []},
                "airingSchedule": {
                    "pageInfo": {"currentPage": 1, "hasNextPage": False},
                    "nodes": [{"episode": 1, "airingAt": 1}],
                },
            }
            body = {"data": {"Page": {"media": [node]}, "Media": node}}
        return httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(gzip.compress(json.dumps(body).encode()))
        )

    control: RequestControl = RequestControl(
        httpx.MockTransport(respond),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as http:

        class Source:
            def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
                return search_releases(query, http=http, categories=categories)

        acquisition: AcquisitionService = AcquisitionService(
            source=Source(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
            request_control=control,
            episode_catalog=AniZipCatalog(http),
            stream_source=TorrentioSource(http),
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        controller: AnimeController = AnimeController(service, lambda: None, resident=session)
        captured: list[str] = []
        handler_id: int = loguru_logger.add(
            captured.append,
            format="{message} {extra}",
            level="WARNING",
            filter=lambda record: record["extra"].get("command_kind") in {"acquisition", "episode_offer"},
        )
        try:
            controller.handle_key("enter")
            controller.handle_key("text:Fixture")
            controller.handle_key("enter")
            worker: threading.Thread | None = controller._worker
            if worker is not None:
                worker.join(_TIMEOUT_S)
                assert not worker.is_alive()
            if scenario == "source_failed":
                controller.handle_key("text:i")
                worker = controller._worker
                assert worker is not None
                worker.join(_TIMEOUT_S)
                assert not worker.is_alive()
            frame: str = controller.render(120, 30).plain
            assert "private-provider-payload" not in frame
            if scenario == "titles":
                assert "Nr" in frame
                assert "Nie wyemitowano" in frame
                assert "Brak terminów emisji (AniList)" in frame
                assert sent == ["graphql.anilist.co", "graphql.anilist.co", "api.ani.zip", "graphql.anilist.co"]
            elif scenario == "catalog_failed":
                assert "AniList nie odpowiada" in frame
                assert sent == ["graphql.anilist.co"]
                assert "TitleCatalogError" in "".join(captured)
                assert "TITLE_CATALOG_FAILED" in "".join(captured)
            elif scenario == "source_failed":
                assert "Źródło wydań nie odpowiada" in frame
                assert sent == [
                    "graphql.anilist.co",
                    "graphql.anilist.co",
                    "api.ani.zip",
                    "graphql.anilist.co",
                    "torrentio.strem.fun",
                ]
                assert "TorrentSourceError" in "".join(captured)
                assert "TORRENT_SOURCE_FAILED" in "".join(captured)
                assert "command_id" in "".join(captured)
            elif scenario in {"internal", "planning", "io"}:
                assert "Wewnętrzny błąd procesu w tle" in frame
                assert sent == ["graphql.anilist.co"]
                expected_class: str = {"internal": "RuntimeError", "planning": "PlanningError", "io": "OSError"}[
                    scenario
                ]
                assert expected_class in "".join(captured)
            else:
                assert "Nie znaleziono tytułu" in frame
                assert sent == ["graphql.anilist.co", "graphql.anilist.co"]
            assert not owner.state.acquisitions
            assert all(value not in "".join(captured) for value in ("private-provider-payload", "Fixture", "https://"))
        finally:
            loguru_logger.remove(handler_id)
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "count"),
    [
        ("appears", 1),
        ("reacquire", 1),
        ("reacquire_failed", 1),
        ("exhausted", 1),
        ("exhausted", 2),
        ("exhausted", 16),
        ("partial", 2),
        ("pause", 1),
        ("shutdown", 1),
    ],
)
def test_async_url_add_is_observed_once_through_owner_ipc_before_content_starts(  # noqa: C901, PLR0912, PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, count: int
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.02)
    network: _TorrentNetwork = _TorrentNetwork()
    release: Release = network.releases[0]
    choice: ReleaseChoice = ReleaseChoice(release, parse_release_name(release.title))
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    repeating: bool = scenario in {"reacquire", "reacquire_failed"}
    if repeating:
        store.save(
            WatchState(
                policy=AutomationPolicy(auto_enabled=True),
                acquisitions=(
                    replace(
                        _accepted_transfer(release.info_hash),
                        state=AcquisitionState.FAILED if scenario == "reacquire_failed" else AcquisitionState.COMPLETE,
                        nyaa_release_id=1,
                        release_title=release.title,
                    ),
                ),
            )
        )
    paths: list[str] = []
    reads: int = 0
    filename: str = "Pack/09.mkv"
    added: list[str] = []
    started: threading.Event = threading.Event()
    metadata_started: threading.Event = threading.Event()
    metadata_release: threading.Event = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal reads, filename
        assert request.url.host == "private-client.test"
        path: str = request.url.path.rsplit("/", 1)[-1]
        paths.append(path)
        if path == "add":
            assert store.load().acquisitions[-1].state in {AcquisitionState.PENDING_SEND, AcquisitionState.UNCERTAIN}
            if repeating:
                assert store.load().acquisitions[0] == previous
            assert store.load().command_receipts
            assert parse_qs(request.content.decode())["stopped"] == ["true"]
            added.extend(parse_qs(request.content.decode())["urls"])
            return httpx.Response(200, text="Ok.")
        if path == "info":
            assert paths.count("add") == count
            reads += 1
            if reads == 1 or scenario == "exhausted":
                return httpx.Response(200, json=[])
            if reads == 2 and scenario in {"pause", "shutdown"}:
                action: str = "set_auto" if scenario == "pause" else "shutdown"
                with closing(ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)) as controller:
                    controller.call(action, {"enabled": False} if scenario == "pause" else {})
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": release.info_hash,
                        "name": release.title,
                        "state": "stoppedDL",
                        "progress": 0.0,
                        "save_path": str(tmp_path),
                        "size": 4,
                        "completed": 0,
                        "amount_left": 4,
                    }
                ],
            )
        if path == "files":
            if scenario == "partial":
                metadata_started.set()
                assert metadata_release.wait(_TIMEOUT_S)
            return httpx.Response(
                200,
                json=[]
                if scenario == "partial"
                else [{"index": 0, "name": filename, "size": 4, "progress": 0.0, "priority": 1}],
            )
        if path == "renameFile":
            filename = parse_qs(request.content.decode())["newPath"][0]
            return httpx.Response(200)
        assert path == "start"
        saved: AcquisitionConfirmation = store.load().acquisitions[-1]
        assert saved.state is AcquisitionState.ACCEPTED
        assert saved.file_layout == ((0, "09.mkv", 4),)
        assert not saved.content_started
        assert store.load().acquisitions[-1].manual or store.load().policy.auto_enabled
        started.set()
        return httpx.Response(200)

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=network,
            client=QBittorrentClient("http://private-client.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            request_control=control,
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, store)
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        panel: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        kind: str = "reacquire" if repeating else "download"
        payload: dict[str, object] = (
            {"operation_id": f"operation-{release.info_hash}"}
            if repeating
            else {
                "choices": [
                    encode_view(
                        replace(
                            choice,
                            release=replace(
                                release,
                                info_hash=str(9 + index),
                                torrent_url=f"https://example.test/{9 + index}.torrent",
                            ),
                        )
                    )
                    for index in range(count)
                ]
            }
        )
        try:
            if repeating:
                previous: AcquisitionConfirmation = store.load().acquisitions[0]
                with closing(ControlClient(endpoint, key)) as other_panel:
                    if scenario == "reacquire_failed":
                        with pytest.raises(ControlError, match="recorded"):
                            other_panel.call("download", {"choices": [encode_view(choice)]}, command_id="stale-panel")
                        assert paths == []
                    else:
                        assert other_panel.call("download", {"choices": [encode_view(choice)]})["count"] == 0
                assert store.load().acquisitions == (previous,)
            response: Mapping[str, object] = panel.call(kind, payload, command_id="async-add")
            assert response == (
                {"operation_id": "repeat-async-add"} if repeating else {"count": count, "directory": str(tmp_path)}
            )
            if scenario == "appears" or repeating:
                assert started.wait(_TIMEOUT_S)
                assert _await(lambda: owner.state.acquisitions[-1].content_started)
                assert panel.call("set_auto", {"enabled": False})["auto_enabled"] is False
                assert _await(lambda: panel.call("status")["paused"] is True)
            elif scenario == "partial":
                assert metadata_started.wait(_TIMEOUT_S)
                assert panel.call("set_auto", {"enabled": False})["auto_enabled"] is False
                metadata_release.set()
                assert _await(lambda: panel.call("status")["paused"] is True)
            elif scenario == "shutdown":
                thread.join(_TIMEOUT_S)
                assert not thread.is_alive()
            saved: WatchState = store.load() if scenario == "shutdown" else owner._on_owner(store.load)
            assert saved.acquisitions[-1].state is (
                AcquisitionState.UNCERTAIN if scenario in {"exhausted", "partial"} else AcquisitionState.ACCEPTED
            )
            assert saved.acquisitions[-1].content_started is (scenario == "appears" or repeating)
            if repeating:
                assert saved.acquisitions[0].operation_id == previous.operation_id
                assert saved.acquisitions[0].release_title == previous.release_title
                assert len(saved.acquisitions) == 2
                assert saved.acquisitions[-1].previous_operation_id == previous.operation_id
            assert paths.count("add") == count
            assert len(set(added)) == count
            assert reads >= 2
            if scenario in {"exhausted", "partial"}:
                assert (
                    sum(
                        cast("int", item["count"])
                        for item in control.counts()
                        if item["operation"] == "torrents/info" and item["reason"] == "user_download"
                    )
                    == 3
                )
            if scenario == "partial":
                assert saved.acquisitions[0].state is AcquisitionState.ACCEPTED
            calls: tuple[str, ...] = tuple(paths)
            time.sleep(0.1)
            assert paths.count("add") == calls.count("add")
            assert paths.count("resume") == calls.count("resume")
            if scenario != "shutdown":

                def refuse_inventory() -> tuple[SourceGroup, ...]:
                    raise AssertionError("receipt replay must not inspect the library")

                monkeypatch.setattr(service, "library_inventory", refuse_inventory)
                panel.call("status")
                saved = store.load()
                state_path: Path = tmp_path / "control" / WATCH_STATE_FILE_NAME
                stamp: int = state_path.stat().st_mtime_ns
                assert panel.call(kind, payload, command_id="async-add") == next(
                    item.outcome for item in saved.command_receipts if item.command_id == "async-add"
                )
                assert state_path.stat().st_mtime_ns == stamp
                assert store.load() == saved
                assert paths.count("add") == calls.count("add")
                assert paths.count("resume") == calls.count("resume")
            if scenario == "exhausted":
                assert reads == 3
                assert all(item.state is AcquisitionState.UNCERTAIN for item in saved.acquisitions)
                duplicate: ControlResponse = owner.handle(_request("download", payload, command_id="async-new"))
                assert duplicate.reason == "download_recorded"
                assert tuple(paths) == calls
        finally:
            metadata_release.set()
            panel.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("unavailable", "TORRENT_CLIENT_UNAVAILABLE"),
        ("unauthorized", "TORRENT_CLIENT_UNAUTHORIZED"),
        ("refused", "TORRENT_CLIENT_REFUSED"),
        ("accepted", ""),
    ],
)
def test_download_failure_and_dedup_cross_owner_ipc_and_qbittorrent_http(  # noqa: PLR0915
    tmp_path: Path, scenario: str, reason: str
) -> None:
    network: _TorrentNetwork = _TorrentNetwork()
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    paths: list[str] = []
    tracked: list[dict[str, object]] = []
    failing: bool = scenario != "accepted"

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "private-client.test"
        paths.append(request.url.path)
        if request.url.path.endswith("/info"):
            return httpx.Response(200, json=tracked)
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[])
        assert store.load().acquisitions
        assert store.load().command_receipts
        if failing and scenario == "unavailable":
            raise httpx.ConnectError("private-payload-secret", request=request)
        if failing and scenario == "unauthorized":
            return httpx.Response(200, text="Fails.") if request.url.path.endswith("/login") else httpx.Response(403)
        if failing:
            return httpx.Response(200, text="Fails.")
        data: dict[str, list[str]] = parse_qs(request.content.decode())
        release: Release = next(item for item in network.releases if item.torrent_url == data["urls"][0])
        tracked.append(
            {
                "hash": release.info_hash,
                "name": release.title,
                "progress": 0.1,
                "state": "stoppedDL",
                "save_path": str(tmp_path),
            }
        )
        return httpx.Response(200, text="Ok.")

    requests: list[ControlRequest] = []
    responses: list[ControlResponse] = []
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=network,
            client=QBittorrentClient(
                "http://private-client.test",
                username="private-user",
                password="private-secret",  # noqa: S106
                http=http,
            ),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, store)
        thread: threading.Thread = _serving(owner)

        def handle(request: ControlRequest) -> ControlResponse:
            response: ControlResponse = owner.handle(request)
            if request.kind == "download":
                requests.append(request)
                responses.append(response)
            return response

        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        captured: list[str] = []
        handler_id: int = loguru_logger.add(
            captured.append,
            format="{message} {extra}",
            level="WARNING",
            filter=lambda record: record["extra"].get("command_kind") == "download",
        )
        try:
            catalog: ReleaseCatalog = session.search("Neko")
            choices: tuple[ReleaseChoice, ...] = catalog.groups[0].choices
            assert len(choices) == 2
            if failing:
                with pytest.raises(ControlError) as error:
                    session.download(choices[:1])
                assert error.value.reason == reason
            else:
                assert session.download(choices[:1]).count == 1
            first: ControlRequest = requests[0]
            saved: WatchState = store.load()
            assert len(saved.acquisitions) == 1
            assert saved.acquisitions[0].state is (AcquisitionState.UNCERTAIN if failing else AcquisitionState.ACCEPTED)
            assert len(saved.command_receipts) == 1
            if failing:
                assert responses[0].code is ControlErrorCode.INTERNAL
                assert responses[0].reason == reason
                assert "TorrentClientError" in "".join(captured)
                assert first.command_id in "".join(captured)
                assert reason in "".join(captured)
                if scenario == "unavailable":
                    assert "ConnectError" in "".join(captured)
            assert all(
                value not in "".join(captured)
                for value in ("private-payload-secret", "private-secret", "private-user", "Neko", "http", str(tmp_path))
            )
            calls: tuple[str, ...] = tuple(paths)
            state_path: Path = tmp_path / "control" / WATCH_STATE_FILE_NAME
            modified: int = state_path.stat().st_mtime_ns
            replay: Mapping[str, object] = session._command_channel().call(
                "download", first.payload, command_id=first.command_id
            )
            assert replay == saved.command_receipts[0].outcome
            assert replay == {"count": 1, "directory": str(tmp_path)}
            assert responses[-1] == ControlResponse.succeeded(dict(saved.command_receipts[0].outcome))
            assert state_path.stat().st_mtime_ns == modified
            assert paths.count("/api/v2/torrents/add") == calls.count("/api/v2/torrents/add")
            assert store.load() == saved
            if failing:
                with pytest.raises(ControlError) as duplicate:
                    session.download(choices[:1])
                assert duplicate.value.reason == "download_recorded"
                assert responses[-1].reason == "download_recorded"
            else:
                assert session.download(choices[:1]).count == 0
                assert responses[-1].ok
                assert responses[-1].result == {"count": 0, "directory": str(tmp_path)}
            assert paths.count("/api/v2/torrents/add") == calls.count("/api/v2/torrents/add")
            failing = False
            if scenario == "accepted":
                assert session.download(choices).count == 1
                assert responses[-1].ok
                assert responses[-1].result["count"] == 1
            else:
                with pytest.raises(ControlError) as mixed:
                    session.download(choices)
                assert mixed.value.reason == "download_recorded"
                assert responses[-1].reason == "download_recorded"
            assert paths.count("/api/v2/torrents/add") == 2
            assert store.load().acquisitions[0] == saved.acquisitions[0]
            assert len(store.load().acquisitions) == 2
        finally:
            loguru_logger.remove(handler_id)
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
def test_panel_search_and_download_use_the_resident_and_durable_receipts(tmp_path: Path) -> None:
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition)
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
    service = _Service(tmp_path, discovered=workspace, plan=plan)
    return service, WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), group_id


def _real_service(
    tmp_path: Path,
    *,
    acquisition: AcquisitionService | None = None,
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
    )


def _completed_library(root: Path, stems: tuple[str, ...] = ("01",)) -> tuple[AppService, WatchStateStore, WatchState]:
    directory: Path = root / "ready"
    directory.mkdir(parents=True)
    records: list[ReadyGroup] = []
    confirmations: list[ProductConfirmation] = []
    for stem in stems:
        source: Path = directory / f"{stem}.txt"
        product: Path = directory / f"{stem}.pl.txt"
        source.write_text("source", encoding="utf-8")
        product.write_text("translated", encoding="utf-8")
        group_id: str = create_group_id(Path("ready"), stem)
        stamp: os.stat_result = product.stat()
        confirmations.append(
            ProductConfirmation(
                group_id,
                ArtifactKind.TRANSLATED_TEXT.value,
                f"ready/{product.name}",
                1,
                "completed",
                RequestOrigin.USER,
                stamp.st_size,
                stamp.st_mtime_ns,
            )
        )
        records.append(
            ReadyGroup(
                f"set-{stem}",
                group_id,
                stem,
                "translate",
                stem,
                WorkflowTarget.TRANSLATE,
                (f"ready/{source.name}",),
                (f"ready/{product.name}",),
                f"ready/{product.name}",
            )
        )
    state: WatchState = WatchState(
        policy=AutomationPolicy(auto_enabled=False), ready_groups=tuple(records), products=tuple(confirmations)
    )
    store: WatchStateStore = WatchStateStore(root / "state.json")
    store.save(state)
    return _real_service(root), store, state


@pytest.mark.parametrize(("profile", "extension"), [("aac", "m4a"), ("mp3", "mp3"), ("flac", "flac")])
def test_requested_results_do_not_select_another_audio_export_profile(profile: str, extension: str) -> None:
    artifacts: tuple[Artifact, ...] = tuple(
        Artifact(
            suffix,
            "episode",
            ArtifactKind.NARRATION_AUDIO,
            Path(f"ready/01.{suffix}"),
            ArtifactState.READY,
            ArtifactLifetime.DURABLE,
            planned_destination=Path(f"ready/01.{suffix}"),
        )
        for suffix in ("m4a", "flac", "mp3")
    )
    intent: GroupIntent = GroupIntent(
        "episode",
        RunMode.AUTO,
        ProductIntent(frozenset({ProductKind.NARRATION_AUDIO})),
        target=WorkflowTarget.AUDIOBOOK,
    )
    assert automation_module._requested_product_paths(artifacts, intent, profile) == frozenset(
        {Path(f"ready/01.{extension}")}
    )


def _read_ready_sets(owner: AutomationOwner) -> tuple[LibrarySet, ...]:
    response: ControlResponse = owner.handle(_request("library_refresh"))
    assert response.ok, response.message
    items: object = response.result["sets"]
    assert isinstance(items, list)
    return tuple(decode_view(LibrarySet, item) for item in items)


@pytest.mark.integration
def test_completed_library_is_naturally_ordered_and_refreshes_without_probe_or_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, state = _completed_library(tmp_path, ("10", "2", "01"))
    (tmp_path / "ready" / "failed.mkv").write_bytes(b"not a completed result")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)

    def no_probe(*args: object, **kwargs: object) -> InspectedWorkspace:
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(service, "discover", no_probe)
    try:
        assert [item.name for item in _read_ready_sets(owner)] == ["01", "2", "10"]
        primary: Path = tmp_path / "ready" / "01.pl.txt"
        parked: Path = tmp_path / "parked"
        primary.rename(parked)
        owner.files_changed(DirectoryChange(paths=(primary,)))
        _await_library_count(owner, 2)
        response: ControlResponse = owner.handle(_request("library_open", {"set_id": "set-01"}))
        assert not response.ok
        assert response.reason == "library_result_missing"
        details: ControlResponse = owner.handle(_request("library_details", {"set_id": "set-01"}))
        assert decode_view(LibrarySet, details.result).files[0].identity is None
        parked.rename(primary)
        owner.files_changed(DirectoryChange(paths=(primary,)))
        _await_library_count(owner, 3)
        assert owner.state == state
        assert service.active_run_ids() == ()
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("change", ["missing", "bytes", "mtime"])
def test_library_distinguishes_missing_main_from_existing_unconfirmed_result(tmp_path: Path, change: str) -> None:
    service, store, _state = _completed_library(tmp_path)
    primary: Path = tmp_path / "ready/01.pl.txt"
    if change == "missing":
        primary.unlink()
    elif change == "bytes":
        primary.write_bytes(b"changed output")
    else:
        stamp: os.stat_result = primary.stat()
        os.utime(primary, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        group: LibrarySet = _read_ready_sets(owner)[0]
        reason: str = "library_result_missing" if change == "missing" else "library_result_changed"
        assert not group.available
        assert group.problem == reason
        assert owner.handle(_request("library_open", {"set_id": group.set_id})).reason == reason
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def _await_library_count(owner: AutomationOwner, expected: int) -> None:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        rows: object = owner.handle(_request("status")).result["library"]
        if isinstance(rows, list) and len(rows) == expected:
            return
        time.sleep(0.01)
    pytest.fail("The ready inventory did not refresh")


@pytest.mark.parametrize(
    ("target", "products", "primary", "source"),
    [
        (WorkflowTarget.VIDEO, ("01.pl.mkv", "01.pl.mp4"), "01.pl.mkv", "ready/01.mkv"),
        (WorkflowTarget.VIDEO, ("01.pl.mp4",), "01.pl.mp4", "ready/01.mkv"),
        (WorkflowTarget.VIDEO, ("01.mp3", "01.pl.srt"), "01.mp3", "ready/01.mkv"),
        (WorkflowTarget.VIDEO, ("01.eac3", "01.pl.srt"), "01.eac3", "ready/01.mkv"),
        (WorkflowTarget.VIDEO, ("01.eac3",), "01.eac3", "01.mkv"),
        (WorkflowTarget.VIDEO, ("01.eac3",), "01.eac3", "ready/01.mp4"),
        (WorkflowTarget.VIDEO, ("01.pl.srt",), "01.pl.srt", "ready/01.txt"),
        (WorkflowTarget.AUDIOBOOK, ("01.mp3",), "01.mp3", "ready/01.txt"),
        (WorkflowTarget.TRANSLATE, ("01.pl.srt",), "01.pl.srt", "ready/01.txt"),
        (WorkflowTarget.COVER, ("01.cover.mp4", "01.mp3"), "01.cover.mp4", "ready/01.txt"),
    ],
)
def test_library_opens_owned_video_or_recorded_product_after_failed_regeneration(
    tmp_path: Path,
    target: WorkflowTarget,
    products: tuple[str, ...],
    primary: str,
    source: str,
) -> None:
    service, store, state = _completed_library(tmp_path)
    (tmp_path / source).write_bytes(b"original source")
    (tmp_path / "ready/010.mkv").write_bytes(b"another episode")
    record: ReadyGroup = state.ready_groups[0]
    confirmations: list[ProductConfirmation] = []
    for name in products:
        path: Path = tmp_path / "ready" / name
        path.write_bytes(b"confirmed output")
        product = classify_product(name)
        assert product is not None
        stamp: os.stat_result = path.stat()
        confirmations.append(
            ProductConfirmation(
                record.group_id,
                product.kind.value,
                f"ready/{name}",
                1,
                "completed",
                RequestOrigin.USER,
                stamp.st_size,
                stamp.st_mtime_ns,
            )
        )
    failed: ProcessingRequest = ProcessingRequest(
        "regeneration",
        2,
        (record.group_id,),
        {},
        RequestOrigin.USER,
        SourceSelection.MANUAL,
        None,
        {},
        RequestState.FAILED,
        1,
        _MOMENT.isoformat(),
    )
    store.save(
        replace(
            state,
            products=tuple(confirmations),
            requests=(failed,),
            ready_groups=(
                replace(
                    record,
                    target=target,
                    sources=(source,) if source.startswith("ready/") else (),
                    pending_sources=() if source.startswith("ready/") else (source,),
                    products=tuple(f"ready/{name}" for name in products),
                    main_result=f"ready/{primary}",
                ),
            ),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        sets: tuple[LibrarySet, ...] = _read_ready_sets(owner)
        assert sets[0].available
        assert sets[0].target is target
        assert sets[0].main_result == f"ready/{primary}"
        opened: ControlResponse = owner.handle(_request("library_open", {"set_id": record.set_id}))
        assert opened.ok
        expected: str = (
            source if primary in {"01.mp3", "01.eac3"} and target is WorkflowTarget.VIDEO else f"ready/{primary}"
        )
        assert opened.result["path"] == expected
        assert (tmp_path / source).read_bytes() == b"original source"
        assert owner.state.ready_groups == store.load().ready_groups
        (tmp_path / "ready" / primary).write_bytes(b"changed product")
        changed: ControlResponse = owner.handle(_request("library_open", {"set_id": record.set_id}))
        assert not changed.ok
        assert changed.reason == "library_result_changed"
        (tmp_path / "ready" / primary).unlink()
        missing: ControlResponse = owner.handle(_request("library_open", {"set_id": record.set_id}))
        assert not missing.ok
        assert missing.reason == "library_result_missing"
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("source_state", ["missing", "ambiguous", "unrecorded", "mkv_mp4"])
def test_library_video_open_selects_owned_primary_and_folder_reveals_confirmed_product(
    tmp_path: Path, source_state: str
) -> None:
    service, store, state = _completed_library(tmp_path, ("01", "010"))
    record: ReadyGroup = state.ready_groups[0]
    sources: tuple[str, ...] = ("ready/01.mkv",)
    (tmp_path / "ready/010.mkv").write_bytes(b"another episode")
    if source_state in {"ambiguous", "mkv_mp4"}:
        (tmp_path / "ready/01.mkv").write_bytes(b"source")
        second: str = "ready/01 alternate.mkv" if source_state == "ambiguous" else "ready/01.mp4"
        (tmp_path / second).write_bytes(b"second source")
        sources = (*sources, second)
    elif source_state == "unrecorded":
        (tmp_path / "ready/01.mp4").write_bytes(b"unrecorded replacement")
    store.save(
        replace(
            state,
            ready_groups=(replace(record, target=WorkflowTarget.VIDEO, sources=sources), state.ready_groups[1]),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _read_ready_sets(owner)[0].available
        revealed: ControlResponse = owner.handle(_request("library_open", {"set_id": record.set_id, "playback": False}))
        assert revealed.ok
        assert revealed.result == {"path": record.main_result}
        opened: ControlResponse = owner.handle(_request("library_open", {"set_id": record.set_id}))
        if source_state == "mkv_mp4":
            assert opened.ok
            assert opened.result == {"path": "ready/01.mkv"}
            return
        assert not opened.ok
        assert opened.reason == ("library_scope_changed" if source_state == "ambiguous" else "library_source_missing")
        assert "path" not in opened.result
        (tmp_path / "ready/01.pl.txt").unlink()
        assert owner.handle(_request("library_open", {"set_id": record.set_id, "playback": False})).reason == (
            "library_result_missing"
        )
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("playback", [None, 0, 1, "false"])
def test_library_open_rejects_non_boolean_playback(tmp_path: Path, playback: object) -> None:
    service, store, _state = _completed_library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("library_open", {"set_id": "set-01", "playback": playback}))
        assert not response.ok
        assert response.code is ControlErrorCode.INVALID_PAYLOAD
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def test_deletion_preview_matches_exact_stem_and_rejects_same_stamp_replacement(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path, ("01", "010"))
    (tmp_path / "ready" / "01.spoken.pl.srt").write_bytes(b"subtitle")
    (tmp_path / "ready" / "01.displayed.pl.ass").write_bytes(b"subtitle")
    (tmp_path / "ready" / "01 unrelated.txt").write_bytes(b"unrelated")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": "set-01"}, session_id="panel"))
        assert response.ok, response.message
        preview: DeletionPreview = decode_view(DeletionPreview, response.result)
        assert {item.path for item in preview.files} == {
            "ready/01.txt",
            "ready/01.pl.txt",
            "ready/01.spoken.pl.srt",
            "ready/01.displayed.pl.ass",
        }
        payload: dict[str, object] = {"set_id": preview.set_id, "preview_id": preview.preview_id}
        assert owner.handle(_request("deletion_validate", payload, session_id="panel")).ok
        source: Path = tmp_path / "ready" / "01.txt"
        stamp: os.stat_result = source.stat()
        replacement: Path = tmp_path / "replacement.txt"
        replacement.write_bytes(source.read_bytes())
        os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        replacement.replace(source)
        stale: ControlResponse = owner.handle(_request("deletion_validate", payload, session_id="panel"))
        assert not stale.ok
        assert stale.reason == "library_scope_changed"
        assert source.read_bytes() == b"source"
        assert owner.state == state
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("blocker", ["pending_source", "torrent", "complete_torrent", "run", "writer", "directory"])
def test_deletion_preview_refuses_owned_source_blockers_before_any_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocker: str
) -> None:
    service, store, state = _completed_library(tmp_path)
    record: ReadyGroup = state.ready_groups[0]
    expected: str = "library_source_held"
    if blocker == "pending_source":
        state = replace(state, ready_groups=(replace(record, pending_sources=("01.mkv",)),))
    elif blocker in {"torrent", "complete_torrent"}:
        state = replace(
            state,
            acquisitions=(
                AcquisitionConfirmation(
                    "download",
                    "a",
                    "ready",
                    ("01.txt",),
                    AcquisitionState.COMPLETE if blocker == "complete_torrent" else AcquisitionState.ACCEPTED,
                    RequestOrigin.USER,
                    None,
                    "1",
                    _MOMENT.isoformat(),
                ),
            ),
        )
    elif blocker == "run":
        state = replace(
            state,
            requests=(
                ProcessingRequest(
                    "run",
                    2,
                    (record.group_id,),
                    {},
                    RequestOrigin.USER,
                    SourceSelection.MANUAL,
                    None,
                    {},
                    RequestState.RUNNING,
                    1,
                    _MOMENT.isoformat(),
                ),
            ),
        )
        expected = RefusalReason.GROUP_PROCESSING.value
    elif blocker == "writer":
        monkeypatch.setattr(automation_module, "source_is_available", lambda path: False)
        expected = "library_source_busy"
    elif blocker == "directory":
        (tmp_path / "ready" / "01.txt").unlink()
        (tmp_path / "ready" / "01.txt").mkdir()
        expected = "library_scope_changed"
    store.save(state)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": record.set_id}))
        assert not response.ok
        assert response.reason == expected
        assert (tmp_path / "ready" / "01.pl.txt").read_bytes() == b"translated"
        assert owner.state.products == state.products
        assert owner.state.acquisitions == state.acquisitions
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def test_deletion_preview_does_not_own_external_manual_reference(tmp_path: Path) -> None:
    root: Path = tmp_path / "workspace"
    service, store, _state = _completed_library(root)
    external: Path = tmp_path / "01.srt"
    external.write_text("1\n00:00:00,000 --> 00:00:01,000\nExternal\n", encoding="utf-8")
    workspace: InspectedWorkspace = service.discover()
    service.register_external_subtitle(workspace.groups[0].group_id, external, "en")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": "set-01"}))
        assert response.ok
        preview: DeletionPreview = decode_view(DeletionPreview, response.result)
        assert {item.path for item in preview.files} == {"ready/01.txt", "ready/01.pl.txt"}
        assert external.read_text(encoding="utf-8").endswith("External\n")
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("directory_event", [False, True])
def test_deletion_validation_rejects_restoration_foreign_session_and_restart(
    tmp_path: Path, directory_event: bool
) -> None:
    service, store, _state = _completed_library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    payload: dict[str, object] = {}
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": "set-01"}, session_id="panel"))
        assert response.ok
        preview: DeletionPreview = decode_view(DeletionPreview, response.result)
        payload = {"set_id": preview.set_id, "preview_id": preview.preview_id}
        assert not owner.handle(_request("deletion_validate", payload, session_id="other")).ok
        primary: Path = tmp_path / "ready" / "01.pl.txt"
        parked: Path = tmp_path / "parked"
        primary.rename(parked)
        parked.rename(primary)
        owner.files_changed(DirectoryChange(paths=(primary.parent if directory_event else primary,)))
        assert not owner.handle(_request("deletion_validate", payload, session_id="panel")).ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    restarted: AutomationOwner = _owner(service, store)
    thread = _serving(restarted)
    try:
        assert not restarted.handle(_request("deletion_validate", payload, session_id="panel")).ok
        assert (tmp_path / "ready" / "01.pl.txt").read_bytes() == b"translated"
    finally:
        restarted.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("target_exists", [True, False])
def test_deletion_preview_rejects_symlink_source_without_reading_external_target(
    tmp_path: Path, target_exists: bool
) -> None:
    root: Path = tmp_path / "workspace"
    service, store, _state = _completed_library(root)
    external: Path = tmp_path / "external.txt"
    if target_exists:
        external.write_bytes(b"external")
    source: Path = root / "ready" / "01.txt"
    source.unlink()
    try:
        source.symlink_to(external)
    except OSError:
        service.close()
        pytest.skip("Creating symlinks is unavailable")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": "set-01"}))
        assert not response.ok
        assert response.reason == "library_scope_changed"
        assert source.is_symlink()
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("evidence", ["complete", "failed", "unidentified"])
def test_legacy_library_needs_success_and_identified_product_but_never_invents_a_target(
    tmp_path: Path, evidence: str
) -> None:
    service, store, state = _completed_library(tmp_path)
    group_id: str = state.ready_groups[0].group_id
    request: ProcessingRequest = ProcessingRequest(
        "completed",
        1,
        (group_id,),
        {},
        RequestOrigin.USER,
        SourceSelection.MANUAL,
        None,
        {},
        RequestState.FAILED if evidence == "failed" else RequestState.SUCCEEDED,
        1,
        _MOMENT.isoformat(),
    )
    state = replace(state, ready_groups=(), requests=(request,))
    if evidence == "unidentified":
        state = replace(state, products=tuple(replace(item, size=-1, modified_ns=-1) for item in state.products))
    store.save(state)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        sets: tuple[LibrarySet, ...] = _read_ready_sets(owner)
        assert len(sets) == int(evidence == "complete")
        if sets:
            assert sets[0].target is None
            assert sets[0].main_result == "ready/01.pl.txt"
            assert sets[0].problem == "library_ownership_unknown"
            response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": group_id}))
            assert not response.ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def test_library_status_and_details_do_not_read_disk_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, store, _state = _completed_library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)

    def unexpected_read(*args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))

    try:
        details: LibrarySet = _read_ready_sets(owner)[0]
        assert {item.format for item in details.files} == {"TXT"}
        assert sum(item.identity.size for item in details.files if item.identity is not None) == 16
        monkeypatch.setattr(library_module, "file_identity", unexpected_read)
        for _ in range(5):
            assert owner.handle(_request("status")).ok
            assert owner.handle(_request("library_details", {"set_id": "set-01"})).ok
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def _await_deletion(owner: AutomationOwner, operation_id: str) -> PendingDeletion:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        response: ControlResponse = owner.handle(_request("status"))
        rows: list[dict[str, object]] = cast("list[dict[str, object]]", response.result["deletions"])
        if any(item["operation_id"] == operation_id and not item["active"] for item in rows):
            result: ControlResponse = owner.handle(_request("deletion_get", {"operation_id": operation_id}))
            return decode_view(PendingDeletion, result.result)
        time.sleep(0.01)
    pytest.fail("The deletion did not settle")


@pytest.mark.parametrize("failure", ["refused", "uncertain", "save", "restored"])
def test_confirmed_deletion_persists_per_file_evidence_and_never_retries_restored_or_uncertain_files(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    service, store, state = _completed_library(tmp_path, ("01", "010"))
    state = replace(
        state,
        acquisitions=(
            AcquisitionConfirmation(
                "download",
                "abc",
                "translate",
                ("01.txt",),
                AcquisitionState.COMPLETE,
                RequestOrigin.USER,
                None,
                "1",
                _MOMENT.isoformat(),
                complete_files=("01.txt",),
            ),
        ),
    )
    store.save(state)
    trash: Path = tmp_path / ".synthetic-trash"
    trash.mkdir()
    calls: list[str] = []
    fail: bool = True
    original_save: Callable[[WatchState], None] = store.save

    def save(candidate: WatchState) -> None:
        if failure == "save" and candidate.pending_deletions and len(candidate.pending_deletions[-1].recycled) == 2:
            raise OSError
        original_save(candidate)

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        operation: PendingDeletion = store.load().pending_deletions[-1]
        assert operation.outcomes[-1].status is DeletionStatus.INFLIGHT
        assert operation.outcomes[-1].path == path.relative_to(tmp_path).as_posix()
        assert operation.identities
        assert identity == (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_dev, path.stat().st_ino)
        calls.append(path.name)
        if len(calls) == 2 and fail and failure != "save":
            return RecycleResult("uncertain" if failure == "uncertain" else "refused", "synthetic_failure")
        path.rename(trash / path.name)
        return RecycleResult("recycled", "recycle_completed", f"synthetic:{path.name}")

    monkeypatch.setattr(store, "save", save)
    owner: AutomationOwner = _owner(service, store, recycler=recycle)
    thread: threading.Thread = _serving(owner)
    try:
        preview: DeletionPreview = decode_view(
            DeletionPreview, owner.handle(_request("deletion_preview", {"set_id": "set-01"}, session_id="panel")).result
        )
        command: ControlRequest = _request(
            "deletion_start",
            {"set_id": preview.set_id, "preview_id": preview.preview_id},
            session_id="panel",
            command_id="delete-once",
        )
        accepted: ControlResponse = owner.handle(command)
        assert accepted.ok, accepted.message
        operation_id: str = str(accepted.result["operation_id"])
        result: PendingDeletion = _await_deletion(owner, operation_id)
        assert result.recycled == ("ready/01.pl.txt",)
        assert [
            item.outcome
            for item in HistoryJournal(store.history_path()).events(_MOMENT)
            if item.kind is HistoryKind.DELETE
        ] == ["incomplete"]
        assert owner.handle(command).result == accepted.result
        assert calls == ["01.pl.txt", "01.txt"]
        assert (tmp_path / "ready/010.txt").read_bytes() == b"source"
        assert owner.state.products == state.products
        assert owner.state.acquisitions == state.acquisitions
        _read_ready_sets(owner)
        snapshot: ControlResponse = owner.handle(_request("status"))
        deletion: dict[str, object] = cast("list[dict[str, object]]", snapshot.result["deletions"])[0]
        assert deletion["name"] == "01"
        assert deletion["remaining"] == 1
        assert deletion["can_confirm"] is (failure != "save")
        if failure == "restored":
            (trash / "01.pl.txt").rename(tmp_path / "ready/01.pl.txt")
            owner.files_changed(DirectoryChange(paths=(tmp_path / "ready/01.pl.txt",)))
            snapshot = owner.handle(_request("status"))
            assert not cast("list[dict[str, object]]", snapshot.result["deletions"])[0]["retryable"]
        fail = False
        retried: ControlResponse = owner.handle(_request("deletion_retry", {"operation_id": operation_id}))
        assert retried.ok is (failure == "refused")
        if retried.ok:
            assert len(_await_deletion(owner, operation_id).recycled) == 2
            assert calls == ["01.pl.txt", "01.txt", "01.txt"]
            assert [
                item.outcome
                for item in HistoryJournal(store.history_path()).events(_MOMENT)
                if item.kind is HistoryKind.DELETE
            ] == ["incomplete", "complete"]
        else:
            assert len(calls) == 2
        assert owner.state.products == state.products
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    restarted: AutomationOwner = _owner(service, store, recycler=recycle)
    thread = _serving(restarted)
    count: int = len(calls)
    try:
        assert not restarted.handle(
            _request(
                "deletion_retry",
                {"operation_id": operation_id},
                command_id="new-retry-after-restart",
            )
        ).ok
        assert len(calls) == count
        assert restarted.state.products == state.products
        assert restarted.state.acquisitions == state.acquisitions
    finally:
        restarted.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.parametrize("change", ["replace", "new_member", "save_failure"])
def test_deletion_start_rechecks_scope_and_persistence_before_first_native_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    service, store, state = _completed_library(tmp_path)
    calls: list[Path] = []

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        calls.append(path)
        return RecycleResult("refused", "unexpected")

    owner: AutomationOwner = _owner(service, store, recycler=recycle)
    thread: threading.Thread = _serving(owner)
    try:
        preview: DeletionPreview = decode_view(
            DeletionPreview, owner.handle(_request("deletion_preview", {"set_id": "set-01"})).result
        )
        if change == "replace":
            replacement: Path = tmp_path / "replacement.txt"
            replacement.write_bytes(b"source")
            replacement.replace(tmp_path / "ready/01.txt")
        elif change == "new_member":
            (tmp_path / "ready/01.pl.srt").write_bytes(b"new member")
        else:
            monkeypatch.setattr(store, "save", lambda _state: (_ for _ in ()).throw(OSError()))
        result: ControlResponse = owner.handle(
            _request(
                "deletion_start",
                {"set_id": preview.set_id, "preview_id": preview.preview_id},
            )
        )
        assert not result.ok
        assert calls == []
        assert owner.state.products == state.products
        assert owner.state.pending_deletions == ()
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


@pytest.mark.integration
def test_owner_death_after_file_effect_keeps_inflight_uncertainty_in_a_fresh_process(tmp_path: Path) -> None:
    script: str = """
import os
import sys
from pathlib import Path
from test_automation import _completed_library, _owner, _request, _serving
from anishift.application.control_views import DeletionPreview, decode_view
root = Path(sys.argv[1])
service, store, state = _completed_library(root)
def crash_after_effect(path, identity):
    path.rename(root / '.parked')
    os._exit(77)
owner = _owner(service, store, recycler=crash_after_effect)
thread = _serving(owner)
preview = decode_view(DeletionPreview, owner.handle(_request('deletion_preview', {'set_id': 'set-01'})).result)
assert owner.handle(_request('deletion_start', {'set_id': preview.set_id, 'preview_id': preview.preview_id})).ok
thread.join(10)
raise AssertionError('The crash boundary was not reached')
"""
    environment: dict[str, str] = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(Path(__file__).parent), str(Path(__file__).parents[1]))),
    }
    crashed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(tmp_path)],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert crashed.returncode == 77, crashed.stderr
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    operation: PendingDeletion = store.load().pending_deletions[0]
    assert operation.outcomes[0].status is DeletionStatus.INFLIGHT
    assert operation.recycled == ()
    service: AppService = _real_service(tmp_path)
    calls: list[Path] = []

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        calls.append(path)
        return RecycleResult("refused", "unexpected")

    owner: AutomationOwner = _owner(service, store, recycler=recycle)
    thread: threading.Thread = _serving(owner)
    try:
        (tmp_path / ".parked").rename(tmp_path / operation.outcomes[0].path)
        owner.files_changed(DirectoryChange(paths=(tmp_path / operation.outcomes[0].path,)))
        response: ControlResponse = owner.handle(
            _request(
                "deletion_retry",
                {"operation_id": operation.operation_id},
                command_id="fresh-retry",
            )
        )
        assert not response.ok
        assert calls == []
        assert owner.state.pending_deletions[0] == operation
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


def test_active_deletion_excludes_processing_and_expires_scope_after_a_survivor_is_restored(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    trash: Path = tmp_path / ".trash"
    trash.mkdir()
    calls: list[str] = []

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        calls.append(path.name)
        entered.set()
        assert release.wait(_TIMEOUT_S)
        path.rename(trash / path.name)
        return RecycleResult("recycled", "recycle_completed", f"synthetic:{path.name}")

    owner: AutomationOwner = _owner(service, store, recycler=recycle)
    thread: threading.Thread = _serving(owner)
    try:
        preview: DeletionPreview = decode_view(
            DeletionPreview, owner.handle(_request("deletion_preview", {"set_id": "set-01"})).result
        )
        accepted: ControlResponse = owner.handle(
            _request(
                "deletion_start",
                {"set_id": preview.set_id, "preview_id": preview.preview_id},
                command_id="delete-first",
            )
        )
        assert accepted.ok
        assert entered.wait(_TIMEOUT_S)
        reserved: ControlResponse = owner.handle(
            _request(
                "reserve",
                {
                    "group_ids": [state.ready_groups[0].group_id],
                    "client_id": "editor",
                },
                session_id="editor",
            )
        )
        assert not reserved.ok
        assert reserved.reason == "library_deleting"
        source: Path = tmp_path / "ready/01.txt"
        source.rename(tmp_path / ".parked")
        (tmp_path / ".parked").rename(source)
        owner.files_changed(DirectoryChange(paths=(source,)))
        release.set()
        operation_id: str = str(accepted.result["operation_id"])
        assert _await_deletion(owner, operation_id).recycled == ("ready/01.pl.txt",)
        assert calls == ["01.pl.txt"]
        assert not owner.handle(_request("deletion_retry", {"operation_id": operation_id})).ok
        assert source.read_bytes() == b"source"
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


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


def test_a_repeated_command_identifier_replays_its_outcome_without_a_second_effect(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))
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
    active: SubscriptionRecord = SubscriptionRecord(
        subscription_id="a",
        anilist_id=1,
        title="Series",
        subscribed_at=_MOMENT.isoformat(),
        cut=0,
        merged_from=(),
    )
    paused: SubscriptionRecord = replace(
        active, subscription_id="b", anilist_id=2, paused=True, pause_reason=PauseReason.USER
    )
    store.save(replace(store.load(), subscriptions=(active, paused)))
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
    assert answer.result["subscriptions"] == {"enabled": 1, "disabled": 1}


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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))
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
    service = _Service(tmp_path, discovered=workspace, plan=plan)
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


def _unlink_when_released(path: Path) -> None:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while True:
        try:
            path.unlink()
        except PermissionError as problem:
            if getattr(problem, "winerror", None) != _SHARING_VIOLATION or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
        else:
            return


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
    service = _Service(tmp_path, discovered=workspace, plan=plan)
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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


@pytest.mark.parametrize(("subscription", "automatic"), [(None, False), ("a", True)])
def test_a_downloaded_episode_row_carries_the_origin_of_its_order(
    tmp_path: Path, subscription: str | None, *, automatic: bool
) -> None:
    service, store, _ = _library(tmp_path)
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-9",
        "9",
        "",
        ("09.mkv",),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        subscription,
        "9",
        _MOMENT.isoformat(),
        file_layout=((0, "09.mkv", 4),),
        complete_files=("09.mkv",),
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False), acquisitions=(item,)))
    owner: AutomationOwner = _owner(service, store)

    rows: list[dict[str, object]] = list(owner._download_materials(item).values())

    assert [(row["stage"], row["reason"], row["automatic"]) for row in rows] == [("waiting", "preparing", automatic)]


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
    store.save(WatchState(acquisitions=(waiting,)))
    owner: AutomationOwner = _owner(service, store)

    assert owner._apply_transfer_action(acquisition, waiting, {}) == waiting
    assert network.actions == []

    settled: AcquisitionConfirmation = owner._apply_transfer_action(
        acquisition, replace(waiting, file_layout=((0, "09.mkv", 4),)), {}
    )

    assert network.actions == [("9", "resume")]
    assert settled.action_pending is False
    assert settled.problem is None


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


@pytest.mark.integration
@pytest.mark.parametrize("bundle", [False, True])
def test_material_identity_survives_bundle_metadata_preparation_processing_and_ready(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bundle: bool
) -> None:
    monkeypatch.setenv("ANISHIFT_PALANTIR_TOKEN", "isolated-test-token")
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.05)
    network: _TorrentNetwork = _TorrentNetwork()
    network.tracked["9"] = TorrentInfo("Original bundle name", "9", 0.0, "metaDL", str(tmp_path))
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        torrent_management=cast("TorrentManagement", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    service: AppService = _processing_service(
        tmp_path,
        FakeTranslationService(entered=entered, release=release),
        inspector=WorkspaceInspector(FakeMediaProbe()),
        acquisition=acquisition,
    )
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / WATCH_STATE_FILE_NAME)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(replace(_owned((), (), RequestOrigin.USER, 0, directory=""), content_started=False),),
        )
    )
    try:
        with closing(service), _panel_owner(service, tmp_path, ready=True) as (session, store):
            assert _await(lambda: _material_rows(session)[0].get("name") == "Original bundle name")
            assert len(_material_rows(session)) == 1
            subtitle_size: int = len("1\n00:00:00,000 --> 00:00:01,000\nHello\n".replace("\n", os.linesep).encode())
            network.entries = (
                TorrentFile(0, "09.srt", subtitle_size, 0.2, 1),
                TorrentFile(7, "09.mkv", 10, 0.4, 1),
                *(
                    (TorrentFile(2, "10.srt", subtitle_size, 0.1, 1), TorrentFile(8, "10.mkv", 10, 0.1, 1))
                    if bundle
                    else ()
                ),
            )
            network.tracked["9"] = replace(network.tracked["9"], state="downloading", progress=0.2)
            assert _await(lambda: any(item["material_id"] == "9:7" for item in _material_rows(session)))
            rows: list[dict[str, object]] = _material_rows(session)
            assert {item["material_id"] for item in rows} == ({"9:7", "9:8"} if bundle else {"9:7"})
            assert {item["name"] for item in rows} == ({"09.mkv", "10.mkv"} if bundle else {"09.mkv"})
            assert session.command("status")["material_counts"] == {
                "downloading": 1 + int(bundle),
                "processing": 0,
                "waiting": 0,
            }
            assert _await(lambda: all(item["content_started"] for item in _material_rows(session)))
            write_media_source(tmp_path / "09.mkv")
            first: str = next(group.group_id for group in session.discover().groups if group.source.stem == "09")
            session.reserve((first,))
            network.entries = tuple(
                replace(item, progress=1.0) if item.name.startswith("09") else item for item in network.entries
            )
            network.tracked["9"] = replace(
                network.tracked["9"],
                progress=0.6 if bundle else 1.0,
                state="downloading" if bundle else "stoppedUP",
                amount_left=10 if bundle else 0,
            )
            assert _await(lambda: any(item.get("stage") == "waiting" for item in _material_rows(session))), (
                network.entries,
                _material_rows(session),
            )
            prepared: dict[str, object] = next(item for item in _material_rows(session) if item["material_id"] == "9:7")
            assert prepared["name"] == "09.mkv"
            assert prepared["downloaded"] is True
            preview: PlanPreview = session.plan_manual(
                (GroupIntent(first, RunMode.MANUAL, ProductIntent(frozenset({ProductKind.SPOKEN_PL}))),)
            )
            run_id: str = session.start(preview)
            assert entered.wait(1.0)
            running: dict[str, object] = next(item for item in _material_rows(session) if item["material_id"] == "9:7")
            assert running["stage"] == "processing"
            assert running["run_id"] == run_id
            assert running["acquisition_id"] == "operation-9"
            assert len(_material_rows(session)) == 1 + int(bundle)
            release.set()
            assert _await(lambda: session.command("run_result", {"run_id": run_id})["state"] == "succeeded")
            assert _await(lambda: bool(session.library()))
            assert [item["material_id"] for item in _material_rows(session)] == (["9:8"] if bundle else [])
            assert (tmp_path / "09.mkv").is_file() is bundle
            assert bool(store.load().ready_groups[0].pending_sources) is bundle
            assert _await(lambda: len(store.load().notified) == 1)
            assert network.added == []
    finally:
        release.set()
    for product in store.load().products:
        (tmp_path / product.path).unlink()
    restarted: AppService = _processing_service(
        tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(FakeMediaProbe())
    )
    with closing(restarted), _panel_owner(restarted, tmp_path, ready=True) as (session, store):
        session.discover()
        assert [item["material_id"] for item in _material_rows(session)] == (["9:8"] if bundle else [])
        assert len(store.load().requests) == 1
        assert network.added == []
        assert len(store.load().notified) == 1


def _material_rows(session: ResidentSession) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", session.command("status")["materials"])


@pytest.mark.parametrize("title", [None, "[SubsPlease] Neko - 09 (1080p)"])
def test_admitted_download_without_metadata_uses_retained_release_name(tmp_path: Path, title: str | None) -> None:
    service, store, _ = _library(tmp_path)
    confirmation: AcquisitionConfirmation = replace(
        _accepted_transfer("a" * 40),
        state=AcquisitionState.PENDING_SEND,
        release_title=title,
        nyaa_release_id=1 if title else None,
    )
    store.save(WatchState(acquisitions=(confirmation,)))
    owner: AutomationOwner = _owner(service, store)
    rows: list[dict[str, object]] = owner._processing_materials()
    assert len(rows) == 1
    assert rows[0]["name"] == (title or "Materiał")
    assert rows[0]["progress"] is None
    assert rows[0]["acquisition_state"] == "pending_send"


def _projection_request(tmp_path: Path, state: RequestState) -> tuple[AutomationOwner, Path, tuple[str, ...]]:
    for number in range(1, 13):
        write_text_source(_library_dir(tmp_path) / f"{number:02d}.txt", "Text")
    with closing(_real_service(tmp_path)) as real:
        workspace: InspectedWorkspace = real.discover()
        identifiers: tuple[str, ...] = tuple(group.group_id for group in workspace.groups)
        plan: ExecutionPlan = real.plan_auto(identifiers, _PRESET)
    remaining: ExecutionPlan = replace(
        plan,
        groups=tuple(
            replace(group, artifact_ids=(), task_ids=()) if group.group_id != identifiers[-1] else group
            for group in plan.groups
        ),
        artifacts=tuple(artifact for artifact in plan.artifacts if artifact.group_id == identifiers[-1]),
        tasks=tuple(task for task in plan.tasks if task.group_id == identifiers[-1]),
    )
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    request: ProcessingRequest = ProcessingRequest(
        "projection",
        1,
        identifiers,
        {},
        RequestOrigin.USER,
        SourceSelection.AUTO,
        None,
        {},
        state,
        1,
        _MOMENT.isoformat(),
        intents=tuple(group.intent for group in plan.groups),
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False), requests=(request,)))
    path: Path = store.run_path(request.request_id)
    RunJournal.create(path, remaining, tmp_path / "temp" / "projection")
    owner: AutomationOwner = _owner(_Service(tmp_path, discovered=workspace, plan=plan), store)
    owner._run_events[request.request_id] = {
        (RunEventKind.GROUP_FINISHED.value, identifier, None): RunEvent(
            request.request_id, index, RunEventKind.GROUP_FINISHED, group_id=identifier, state=TaskState.SUCCEEDED
        )
        for index, identifier in enumerate((*identifiers[:10], identifiers[-1]), start=1)
    }
    return owner, path, identifiers


@pytest.mark.parametrize("state", [RequestState.PAUSED, RequestState.RUNNING])
def test_processing_projection_reads_a_twelve_group_checkpoint_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: RequestState
) -> None:
    owner, path, identifiers = _projection_request(tmp_path, state)
    read_bytes: Callable[[Path], bytes] = Path.read_bytes
    reads: list[Path] = []
    content: bytes = path.read_bytes()

    def counted_read(candidate: Path) -> bytes:
        if candidate == path:
            reads.append(candidate)
        return read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    try:
        first: list[dict[str, object]] = cast("list[dict[str, object]]", owner._status()["materials"])
        assert [row["group_id"] for row in first] == list(
            identifiers[-1:] if state is RequestState.PAUSED else identifiers[-2:]
        )
        assert all(row["state"] == state.value and row["run_id"] == "projection" for row in first)
        assert reads == [path]
        assert owner._status()["materials"] == first
        assert reads == [path, path]
        assert read_bytes(path) == content
    finally:
        owner._pool.shutdown(wait=True)


def test_processing_projection_retries_an_unavailable_terminal_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, path, identifiers = _projection_request(tmp_path, RequestState.FAILED)
    read_bytes: Callable[[Path], bytes] = Path.read_bytes
    reads: list[Path] = []

    def interrupted_read(candidate: Path) -> bytes:
        if candidate == path:
            reads.append(candidate)
            if len(reads) == 1:
                raise OSError("Injected unavailable checkpoint")
        return read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", interrupted_read)
    try:
        unavailable: list[dict[str, object]] = cast("list[dict[str, object]]", owner._status()["materials"])
        assert [row["group_id"] for row in unavailable] == list(identifiers)
        assert all(row["state"] == "failed" for row in unavailable)
        assert reads == [path]
        retried: list[dict[str, object]] = cast("list[dict[str, object]]", owner._status()["materials"])
        assert [row["group_id"] for row in retried] == [identifiers[-1]]
        assert retried[0]["state"] == "failed"
        assert reads == [path, path]
        assert owner._status()["materials"] == retried
        assert reads == [path, path]
    finally:
        owner._pool.shutdown(wait=True)


@pytest.mark.integration
def test_library_retry_after_refused_deletion_only_relocates(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANISHIFT_PALANTIR_TOKEN", "isolated-test-token")
    service, _old_store, state = _completed_library(tmp_path)
    service.close()
    service = _processing_service(tmp_path, FakeTranslationService(), inspector=WorkspaceInspector(FakeMediaProbe()))
    cover: Path = tmp_path / "cover"
    cover.mkdir()
    write_text_source(cover / "Pending.txt", "A source")
    audiobook: Path = tmp_path / "audiobook"
    audiobook.mkdir()
    write_text_source(audiobook / "Book.txt", "A source")
    product: Path = audiobook / "Book.m4a"
    product.write_bytes(b"synthetic audio")
    ready: ReadyStore = ReadyStore(relocation_journal_dir(tmp_path / ".control"), tmp_path)
    source: SourceGroup = next(group for group in discover_groups(tmp_path).groups if group.stem == "Book")
    assert ready.prepare(source, (product,)) is not None
    WatchStateStore(tmp_path / ".control" / WATCH_STATE_FILE_NAME).save(state)
    fail: bool = True
    original_link: Callable[[Path, Path], None] = os.link
    links: list[str] = []
    recycled: list[str] = []

    def link(source: Path, destination: Path) -> None:
        links.append(source.name)
        if fail:
            raise PermissionError("Synthetic filesystem refusal")
        original_link(source, destination)

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        del identity
        recycled.append(path.name)
        return RecycleResult("refused", "recycle_refused")

    monkeypatch.setattr(os, "link", link)
    with (
        closing(service),
        _panel_owner(service, tmp_path, ready=True, watch=True, recycler=recycle) as (session, _store),
    ):
        preview: DeletionPreview = session.preview_deletion("set-01")
        session.delete_set(preview)
        assert _await(lambda: len(recycled) == 1)
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _await(lambda: controller._connected)
            assert "Brak aktywnego przetwarzania" in controller.render(120, 40).plain
            controller.handle_key("right")
            assert _await(lambda: not controller._busy)
            controller.handle_key("home")
            frame: str = controller.render(120, 40).plain
            assert "P ponów pozostałe pliki" not in frame
            assert "P ponów przenoszenie do biblioteki" in frame
            attempts: int = len(links)
            fail = False
            controller.handle_key("text:p")
            assert _await((tmp_path / "ready/Book.m4a").is_file)
            assert len(links) > attempts
            assert recycled == ["01.pl.txt"]
            assert len(_material_rows(session)) == 1
        finally:
            controller.close()
            controller._thread.join(_TIMEOUT_S)


@pytest.mark.integration
def test_standalone_subtitle_progress_uses_the_actual_source_filename(tmp_path: Path) -> None:
    directory: Path = tmp_path / "translate"
    directory.mkdir()
    source: Path = directory / "Episode.srt"
    source.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    service: AppService = _processing_service(tmp_path, FakeTranslationService())
    with closing(service), _panel_owner(service, tmp_path) as (session, _store):
        groups: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(groups)
        preview: PlanPreview = session.plan_manual(
            tuple(
                GroupIntent(
                    group_id,
                    RunMode.MANUAL,
                    ProductIntent(frozenset({ProductKind.FULL_PL})),
                    target=WorkflowTarget.TRANSLATE,
                )
                for group_id in groups
            )
        )
        result: RunResult = session.execute(preview, CollectingRunSink())
        assert result.succeeded
        progress: Mapping[str, object] = session.command("run_progress", {"run_id": result.run_id})
        assert progress["labels"] == {groups[0]: "Episode.srt"}


class _FailedTts:
    def __init__(self) -> None:
        self.calls: int = 0

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        del batch, callbacks
        self.calls += 1
        raise ExecutionError("Synthetic provider failure")

    def cancel(self) -> None:
        return

    def close(self) -> None:
        return


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


def test_relocation_retries_a_single_failure_without_any_active_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    _prepared_audiobook(tmp_path)
    folder: Path = tmp_path / "audiobook"
    write_text_source(folder / "Other.txt", "Text")
    (folder / "Other.m4a").write_bytes(b"recording")
    journal: ReadyStore = ReadyStore(tmp_path / "control" / "relocations", tmp_path)
    group: SourceGroup = next(item for item in discover_groups(tmp_path).groups if item.stem == "Other")
    assert journal.prepare(group, (folder / "Other.m4a",)) is not None
    execute: Callable[[ReadyStore, ReadyMove], None] = ReadyStore.execute
    failed: list[str] = []

    def transient(store: ReadyStore, move: ReadyMove) -> None:
        if not failed:
            failed.append(move.group_id)
            raise OSError(13, "Temporary relocation failure")
        execute(store, move)

    monkeypatch.setattr(ReadyStore, "execute", transient)
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _relocating_owner(tmp_path, service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: len(owner.state.ready_groups) == 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert len(failed) == 1
    assert not thread.is_alive()


@pytest.mark.parametrize("deferred", [False, True])
def test_relocation_counts_only_real_failures_and_reports_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, deferred: bool
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    _prepared_audiobook(tmp_path)
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    owner: AutomationOwner = _relocating_owner(tmp_path, service, store)
    journal: ReadyStore = cast("ReadyStore", owner._ready_store)
    execute: Callable[[ReadyMove], None] = journal.execute
    defer: Callable[[ReadyMove, tuple[str, ...]], ReadyMove] = journal.defer
    calls: list[str] = []

    def held(current: ReadyMove, names: tuple[str, ...]) -> ReadyMove:
        if len(calls) <= automation_module._FINALIZE_ATTEMPTS + 2:
            return defer(current, (current.files[0].source,))
        return defer(current, names)

    def attempt(current: ReadyMove) -> None:
        calls.append(current.group_id)
        if not deferred:
            raise OSError(13, "Relocation unavailable")
        execute(current)

    monkeypatch.setattr(journal, "execute", attempt)
    if deferred:
        monkeypatch.setattr(journal, "defer", held)
    thread: threading.Thread = _serving(owner)
    try:
        if deferred:
            for count in range(1, automation_module._FINALIZE_ATTEMPTS + 4):

                def settled(expected: int = count) -> bool:
                    return len(calls) >= expected and not owner._ready_inflight

                assert _await(settled)
                assert owner.handle(_request("ready_retry")).ok
            assert _await(lambda: bool(owner.state.ready_groups) and not owner.state.ready_groups[0].pending_sources)
            assert len(calls) > automation_module._FINALIZE_ATTEMPTS + 2
        else:
            assert _await(lambda: len(calls) == automation_module._FINALIZE_ATTEMPTS)
            assert _await(lambda: bool(owner._ready_problems))
            response: ControlResponse = owner.handle(_request("status"))
            relocations: list[dict[str, object]] = cast("list[dict[str, object]]", response.result["relocations"])
            assert any("Relocation unavailable" in str(item["problem"]) for item in relocations)
            time.sleep(0.1)
            assert len(calls) == automation_module._FINALIZE_ATTEMPTS
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("external", [False, True])
def test_unmanageable_deferred_relocation_does_not_keep_an_idle_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, external: bool
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    audiobook: Path = _prepared_audiobook(tmp_path)
    size: int = (audiobook / "Book.txt").stat().st_size
    network: _TorrentNetwork = _TorrentNetwork()
    monkeypatch.setattr(network, "finalizable_hashes", lambda hashes: frozenset(), raising=False)
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
        torrent_management=None if external else cast("TorrentManagement", network),
    )
    attempts: list[frozenset[str]] = []

    def held(hashes: frozenset[str]) -> frozenset[str]:
        attempts.append(hashes)
        return frozenset()

    monkeypatch.setattr(acquisition, "release_completed", held)
    service: AppService = _real_service(tmp_path, acquisition=acquisition)
    store: WatchStateStore = WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(
                replace(
                    _owned(("Book.txt",), (), RequestOrigin.USER, size, directory="audiobook"),
                    state=AcquisitionState.COMPLETE,
                ),
            ),
        )
    )
    owner: AutomationOwner = _relocating_owner(tmp_path, service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: bool(owner.state.ready_groups) and bool(attempts))
        time.sleep(0.1)
        count: int = len(attempts)
        time.sleep(0.1)
        assert len(attempts) == count
        assert owner._on_owner(lambda: owner._transfers_at) is None
        assert owner.state.ready_groups[0].pending_sources == ("audiobook/Book.txt",)
        assert owner.handle(_request("ready_retry")).ok
        assert _await(lambda: len(attempts) > count)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()


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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("Book.txt",), (), RequestOrigin.USER, size, directory="audiobook"),),
        )
    )
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
            policy=AutomationPolicy(auto_enabled=True),
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    origin: RequestOrigin = RequestOrigin.BACKGROUND,
) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        f"operation-{info_hash}",
        info_hash,
        "",
        (),
        AcquisitionState.ACCEPTED,
        origin,
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(fresh, writing)))
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),),
        )
    )
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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),),
        )
    )
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
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def hold_first_read() -> None:
        if entered.is_set():
            return
        entered.set()
        assert release.wait(_TIMEOUT_S)

    network.before_info = hold_first_read
    thread: threading.Thread = _serving(owner)
    try:
        assert entered.wait(_TIMEOUT_S)
        assert network.started == []
        taken.unlink()
        assert _commanded(owner, "resume")
        release.set()
        assert _await(lambda: network.actions == [("9", "resume")])
        assert _await(lambda: network.started == ["9"])
    finally:
        release.set()
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
        assert _commanded(owner, "stop")
        assert store.load().acquisitions[0].requested_action == "stop"
        assert _await(lambda: network.actions == [("9", "stop")])
        taken.unlink()
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),),
        )
    )
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(item,)))
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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),),
        )
    )
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


def _pausable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    subscription_id: str | None = None,
    subscriptions: tuple[SubscriptionRecord, ...] = (),
) -> tuple[AutomationOwner, _TorrentNetwork, WatchStateStore, _Service]:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    network.tracked["10"] = TorrentInfo("Other", "10", 0.5, "stoppedDL", str(tmp_path), 4, 2)
    network.per_hash["10"] = (TorrentFile(0, "10.mkv", 4, 0.5, 1),)
    mine: AcquisitionConfirmation = _accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            subscriptions=subscriptions,
            acquisitions=(
                replace(mine, subscription_id=subscription_id, origin=RequestOrigin.BACKGROUND),
                replace(
                    _accepted_transfer("10", layout=((0, "10.mkv", 4),), started=True),
                    requested_action="stop",
                    origin=RequestOrigin.BACKGROUND,
                ),
            ),
        )
    )
    return _owner(service, store), network, store, service


def _switched(owner: AutomationOwner, *, enabled: bool, command_id: str) -> bool:
    return owner.handle(_request("set_auto", {"enabled": enabled}, command_id=command_id)).ok


def test_one_pause_stops_the_schedule_the_polling_and_records_only_the_transfers_it_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, service = _pausable(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: ("9", "stop") in network.actions)
        time.sleep(0.2)
        settled: int = network.info_calls
        time.sleep(0.3)
        assert network.info_calls == settled
        assert owner._transfers_at is None
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    state: WatchState = store.load()
    assert state.pause_owned_transfers == ("9",)
    assert service.paused == []
    assert ("10", "stop") not in network.actions


def test_a_resume_restarts_only_the_transfers_that_pause_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, service = _pausable(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: ("9", "stop") in network.actions)
        assert _switched(owner, enabled=True, command_id="resume-1")
        assert _await(lambda: ("9", "resume") in network.actions)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    state: WatchState = store.load()
    hand_stopped: AcquisitionConfirmation = next(item for item in state.acquisitions if item.info_hash == "10")
    assert state.pause_owned_transfers == ()
    assert ("10", "resume") not in network.actions
    assert hand_stopped.requested_action == "stop"
    assert service.paused == []


@pytest.mark.parametrize(
    ("followed", "paused"),
    [("a", True), ("old", True), ("gone", False), ("a", False), ("old", False)],
)
def test_a_resume_takes_up_only_the_transfer_of_a_followed_active_subscription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, followed: str, paused: bool
) -> None:
    record: SubscriptionRecord = SubscriptionRecord(
        subscription_id="a",
        anilist_id=1,
        title="Series",
        subscribed_at=_MOMENT.isoformat(),
        cut=0,
        merged_from=("old",),
        paused=paused,
        pause_reason=PauseReason.USER if paused else None,
    )
    owner, network, store, _ = _pausable(tmp_path, monkeypatch, subscription_id=followed, subscriptions=(record,))
    resumed: bool = followed != "gone" and not paused
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: ("9", "stop") in network.actions)
        assert _switched(owner, enabled=True, command_id="resume-1")
        if resumed:
            assert _await(lambda: ("9", "resume") in network.actions)
        time.sleep(0.2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert (("9", "resume") in network.actions) is resumed
    assert store.load().pause_owned_transfers == ()


def test_repeating_pause_and_resume_never_touches_the_separately_stopped_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, _ = _pausable(tmp_path, monkeypatch)

    def counted(action: str, times: int) -> Callable[[], bool]:
        return lambda: network.actions.count(("9", action)) == times

    thread: threading.Thread = _serving(owner)
    try:
        for cycle in range(2):
            assert _switched(owner, enabled=False, command_id=f"pause-{cycle}")
            assert _await(counted("stop", cycle + 1))
            assert _switched(owner, enabled=True, command_id=f"resume-{cycle}")
            assert _await(counted("resume", cycle + 1))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    state: WatchState = store.load()
    hand_stopped: AcquisitionConfirmation = next(item for item in state.acquisitions if item.info_hash == "10")
    assert [item for item in network.actions if item[0] == "10"] == []
    assert hand_stopped.requested_action == "stop"


def test_a_paused_resident_admits_an_explicit_start_as_user_work(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
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
        materials: list[dict[str, object]] = cast(
            "list[dict[str, object]]", owner.handle(_request("status", {}, command_id="status-1")).result["materials"]
        )
    finally:
        for run_id in tuple(service.active):
            service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert not thread.is_alive()
    assert started.ok
    assert [row["automatic"] for row in materials if row.get("stage") == "processing"] == [False]
    assert len(service.submitted) == 1
    assert [item.automatic for item in store.load().requests] == [False]
    assert store.load().policy.auto_enabled is False


def test_a_stored_pause_is_still_a_pause_after_a_restart(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=False)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        answer: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        admissions: list[bool] = list(service.background_admission)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert answer.result["paused"] is True
    assert answer.result["auto_enabled"] is False
    assert service.paused == []
    assert admissions == [False]


@pytest.mark.parametrize("working", [True, False])
def test_every_start_prepares_the_private_client_without_polling_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, working: bool
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    network.tracked.clear()
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=working)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        time.sleep(0.2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert network.prepared == 1
    assert network.info_calls == 0


def _transfers_problem(owner: AutomationOwner) -> object:
    return owner.handle(_request("status", command_id="status-transfers")).result["transfers_problem"]


def test_a_client_that_cannot_be_prepared_is_reported_without_stopping_the_resident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    network.tracked.clear()
    network.unpreparable = True
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.prepared == 1)
        assert _await(lambda: _transfers_problem(owner) is not None)
        answer: ControlResponse = owner.handle(_request("status", command_id="status-1"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert not thread.is_alive()
    assert answer.ok
    assert answer.result["transfers_problem"] is not None


def _qbittorrent_replies(root: Path) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/torrents/info"):
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "Pack",
                        "hash": "9",
                        "progress": 0.5,
                        "state": "downloading",
                        "save_path": str(root),
                        "size": 4,
                        "completed": 2,
                        "amount_left": 2,
                    }
                ],
            )
        if request.url.path.endswith("/torrents/files"):
            return httpx.Response(200, json=[{"index": 0, "name": "09.mkv", "size": 4, "progress": 0.5, "priority": 1}])
        return httpx.Response(200, text="Ok.")

    return respond


def _measured_acquisition(
    tmp_path: Path, service: _Service, http: httpx.Client, control: RequestControl
) -> _TorrentNetwork:
    management: _TorrentNetwork = _TorrentNetwork()
    service.acquisition = AcquisitionService(
        source=management,
        client=QBittorrentClient("http://127.0.0.1:65000", http=http),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
        request_control=control,
        torrent_management=cast("TorrentManagement", management),
    )
    return management


def _idle_counts(control: RequestControl, service: _Service, management: _TorrentNetwork) -> tuple[int, int, int]:
    requests: int = sum(int(cast("int", item["count"])) for item in control.counts())
    return (requests, service.discover_calls, management.resume_calls)


@pytest.mark.integration
def test_connected_panels_refresh_real_transfers_without_fanout_or_resetting_backoff(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now: list[float] = [100.0]
    monkeypatch.setattr(automation_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    service, store, _ = _library(tmp_path)
    reads: list[float] = []
    files: list[float] = []
    failing: bool = False
    progress: float = 0.5
    inspecting: threading.Event = threading.Event()
    inspected: threading.Event = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/info"):
            reads.append(now[0])
            if now[0] == 113.0:
                inspecting.set()
                assert inspected.wait(_TIMEOUT_S)
            if failing:
                return httpx.Response(503)
            return httpx.Response(
                200,
                json=[
                    {
                        "hash": "9",
                        "name": "Pack",
                        "progress": progress,
                        "state": "downloading",
                        "save_path": str(tmp_path),
                        "size": 4,
                        "completed": 2,
                        "amount_left": 2,
                    }
                ],
            )
        assert request.url.path.endswith("/files")
        files.append(now[0])
        return httpx.Response(200, json=[{"index": 0, "name": "09.mkv", "size": 4, "progress": 0.5, "priority": 1}])

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as http:
        _measured_acquisition(tmp_path, service, http, control)
        store.save(
            WatchState(
                policy=AutomationPolicy(auto_enabled=True),
                acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
            )
        )
        owner: AutomationOwner = _owner(service, store)
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        observer: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        first: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        second: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)

        def settled(count: int) -> None:
            assert _await(lambda: owner._on_owner(lambda: len(reads) == count and not owner._transfers_inspecting))

        def tick(moment: float, count: int) -> None:
            now[0] = moment
            for _ in range(3):
                observer.call("status")
            settled(count)

        try:
            settled(1)
            tick(109.9, 1)
            tick(110.0, 2)
            now[0] = 112.0
            progress = 0.6
            first.call("panel_attach")
            settled(3)
            assert cast("list[dict[str, object]]", observer.call("status")["transfers"])[0]["progress"] == 0.6
            now[0] = 112.2
            second.call("panel_attach")
            first.call("panel_attach")
            tick(112.9, 3)
            now[0] = 113.0
            observer.call("status")
            assert inspecting.wait(_TIMEOUT_S)
            first.call("panel_attach")
            second.call("panel_attach")
            assert reads == [100.0, 110.0, 112.0, 113.0]
            inspected.set()
            settled(4)
            first.close()
            assert _await(lambda: owner._on_owner(lambda: len(owner._panels) == 1))
            tick(114.0, 5)
            second.close()
            assert _await(lambda: owner._on_owner(lambda: not owner._panels))
            tick(123.9, 5)
            tick(124.0, 6)
            assert reads == [100.0, 110.0, 112.0, 113.0, 114.0, 124.0]
            assert files == [100.0, 112.0]
            failing = True
            tick(134.0, 7)
            for moment in (135.0, 140.0):
                now[0] = moment
                with closing(ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)) as reconnect:
                    reconnect.call("panel_attach")
                    reconnect.call("panel_attach")
                assert _await(lambda: owner._on_owner(lambda: not owner._panels))
            tick(153.9, 7)
            observer.call("panel_attach")
            tick(154.0, 8)
            tick(193.9, 8)
            failing = False
            tick(194.0, 9)
            tick(195.0, 10)
            assert reads[-4:] == [134.0, 154.0, 194.0, 195.0]
        finally:
            inspected.set()
            first.close()
            second.close()
            observer.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
        assert not thread.is_alive()


@pytest.mark.integration
def test_paused_broadcast_and_ipc_wait_for_completed_transfer_release_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, _ = _library(tmp_path)
    control: RequestControl = RequestControl(httpx.MockTransport(_qbittorrent_replies(tmp_path)))
    releasing: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    frames: list[Mapping[str, object]] = []
    with httpx.Client(transport=control) as http:
        management: _TorrentNetwork = _measured_acquisition(tmp_path, service, http, control)

        def release_completed(hashes: frozenset[str]) -> frozenset[str]:
            releasing.set()
            assert release.wait(_TIMEOUT_S)
            http.get("http://127.0.0.1:65000/api/v2/torrents/info")
            return hashes

        monkeypatch.setattr(management, "release_completed", release_completed)
        completed: AcquisitionConfirmation = replace(_accepted_transfer("10"), state=AcquisitionState.COMPLETE)
        pending: AcquisitionConfirmation = replace(
            _accepted_transfer("9"), requested_action="stop", action_pending=True, action_id="stop-test"
        )
        store.save(
            WatchState(policy=AutomationPolicy(auto_enabled=False), acquisitions=(_accepted_transfer("10"), pending))
        )
        owner: AutomationOwner = _owner(service, store)
        owner.attach_broadcast(lambda frame, terminal: frames.append(frame))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        panel: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            owner._on_owner(lambda: owner._replace_acquisition(completed))
            owner._on_owner(owner._finalize_transfers)
            assert releasing.wait(_TIMEOUT_S)
            assert panel.call("status")["pausing"] is True
            assert not any(cast("Mapping[str, object]", frame["payload"])["paused"] for frame in frames)
            release.set()
            assert _await(lambda: panel.call("status")["paused"] is True)
            counts: list[dict[str, object]] = control.counts()
            panel.call("panel_attach")
            for _ in range(3):
                assert panel.call("status")["paused"] is True
            time.sleep(0.1)
            assert control.counts() == counts
            assert any(item["reason"] == "completed_download" for item in counts)
        finally:
            release.set()
            panel.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
        assert not thread.is_alive()


def test_a_full_pause_stops_every_real_request_and_probe_that_a_live_panel_cannot_revive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    control: RequestControl = RequestControl(httpx.MockTransport(_qbittorrent_replies(tmp_path)))
    http: httpx.Client = httpx.Client(transport=control)
    management: _TorrentNetwork = _measured_acquisition(tmp_path, service, http, control)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    key: bytes = os.urandom(32)
    server: ControlServer = ControlServer(control_endpoint(tmp_path), key, owner.handle, on_disconnect=owner.disconnect)
    owner.attach_broadcast(server.broadcast)
    thread: threading.Thread = _serving(owner)
    panel: ControlClient = ControlClient(control_endpoint(tmp_path), key, timeout_s=_TIMEOUT_S)
    stream: ControlClient = ControlClient(control_endpoint(tmp_path), key, timeout_s=_TIMEOUT_S)
    frames: list[Mapping[str, object]] = []
    stream.subscribe()
    reader: threading.Thread = threading.Thread(target=lambda: frames.extend(stream.events()), daemon=True)
    reader.start()
    try:
        assert _await(lambda: _idle_counts(control, service, management)[0] > 1)
        assert panel.call("set_auto", {"enabled": False})["auto_enabled"] is False
        assert _await(lambda: ("9", "stop") in management.actions)
        assert _await(lambda: panel.call("status")["paused"] is True)
        watched: tuple[int, int, int] = _idle_counts(control, service, management)
        time.sleep(0.4)
        assert _idle_counts(control, service, management) == watched
        for index in range(3):
            assert panel.call("status", command_id=f"status-{index}")["paused"] is True
        assert _idle_counts(control, service, management) == watched
        assert frames != []
        panel.close()
        stream.close()
        assert _await(lambda: not reader.is_alive())
        time.sleep(0.4)
        assert _idle_counts(control, service, management) == watched
    finally:
        panel.close()
        stream.close()
        server.close()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        http.close()

    assert watched[0] > 1
    assert watched[2] > 0
    assert store.load().pause_owned_transfers == ("9",)


@pytest.mark.parametrize("state", [AcquisitionState.COMPLETE, AcquisitionState.UNCERTAIN])
def test_a_settled_working_resident_polls_nothing_while_its_schedule_stays_armed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: AcquisitionState
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    control: RequestControl = RequestControl(httpx.MockTransport(_qbittorrent_replies(tmp_path)))
    http: httpx.Client = httpx.Client(transport=control)
    management: _TorrentNetwork = _measured_acquisition(tmp_path, service, http, control)
    finished: AcquisitionConfirmation = replace(
        _accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True), state=AcquisitionState.COMPLETE
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(finished,)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: owner._on_owner(lambda: owner._active_io == 0))
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(replace(finished, state=state),))))
        assert owner.handle(_request("panel_attach", session_id="panel")).ok
        time.sleep(0.3)
        measured: tuple[int, int, int] = _idle_counts(control, service, management)
        time.sleep(0.4)
        assert _idle_counts(control, service, management) == measured
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        http.close()

    assert measured == (0, 0, 0)


def test_pausing_is_reported_until_the_started_work_reaches_its_boundary(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        assert _switched(owner, enabled=False, command_id="pause-1")
        during: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        settled: bool = _await(lambda: bool(owner.handle(_request("status", command_id="status-2")).result["paused"]))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert during.result["pausing"] is True
    assert during.result["paused"] is False
    assert during.result["auto_enabled"] is False
    assert settled


def test_repeated_pause_and_resume_never_spends_the_recovery_budget_of_a_paused_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(watch_module, "QUIET_S", 0.02)
    monkeypatch.setattr(watch_module, "SCAN_INTERVAL_S", 0.01)
    service, store, group_id = _library(tmp_path)
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        run_id: str = _started(owner)
        service.active.remove(run_id)
        service.handles[run_id].resolve(RunResult(run_id, (GroupResult(group_id, GroupStatus.CANCELLED),), paused=True))
        assert _await(lambda: _request_states(owner) == [RequestState.PAUSED.value])
        for cycle in range(4):
            assert _switched(owner, enabled=False, command_id=f"pause-{cycle}")
            assert _switched(owner, enabled=True, command_id=f"resume-{cycle}")
            time.sleep(0.05)
    finally:
        for active in tuple(service.active):
            service.finish(active, GroupStatus.SUCCEEDED, group_id)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    recorded: ProcessingRequest = store.load().requests[0]
    assert recorded.state is not RequestState.FAILED
    assert recorded.problem is None
    assert recorded.attempts == 1


def test_a_transfer_a_person_stopped_in_the_client_is_neither_recorded_nor_restarted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    network.tracked["10"] = TorrentInfo("Other", "10", 0.5, "stoppedDL", str(tmp_path), 4, 2)
    network.per_hash["10"] = (TorrentFile(0, "10.mkv", 4, 0.5, 1),)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(
                _accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),
                _accepted_transfer("10", layout=((0, "10.mkv", 4),), started=True),
            ),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: ("9", "stop") in network.actions)
        assert _switched(owner, enabled=True, command_id="resume-1")
        assert _await(lambda: ("9", "resume") in network.actions)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert store.load().pause_owned_transfers == ()
    assert [item for item in network.actions if item[0] == "10"] == []


def test_an_explicit_stop_during_the_pause_takes_that_transfer_out_of_the_resumed_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, _ = _pausable(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: ("9", "stop") in network.actions)
        assert owner.handle(_request("transfer", {"info_hash": "9", "action": "stop"}, command_id="stop-9")).ok
        assert store.load().pause_owned_transfers == ()
        assert _switched(owner, enabled=True, command_id="resume-1")
        time.sleep(0.2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert ("9", "resume") not in network.actions
    assert store.load().pause_owned_transfers == ()


def test_a_pause_landing_during_the_client_read_reserves_no_name_and_starts_no_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),))
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(_accepted_transfer("9"),)))
    owner: AutomationOwner = _owner(service, store)
    switched: threading.Event = threading.Event()

    def pause_during_read() -> None:
        if switched.is_set():
            return
        switched.set()
        assert _switched(owner, enabled=False, command_id="pause-1")

    network.before_info = pause_during_read
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(switched.is_set)
        time.sleep(0.3)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    stored: AcquisitionConfirmation = store.load().acquisitions[0]
    assert network.renamed == []
    assert network.started == []
    assert stored.file_layout == ()
    assert stored.content_started is False


def test_a_confirmed_pause_already_carries_its_recorded_stop_in_the_stored_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, _ = _pausable(tmp_path, monkeypatch)
    thread: threading.Thread = _serving(owner)
    saves: list[int] = []
    original: Callable[[WatchState], None] = store.save

    def once(state: WatchState) -> None:
        saves.append(1)
        if len(saves) > 1:
            raise OSError("no disk")
        original(state)

    try:
        assert _await(lambda: network.info_calls > 1)
        monkeypatch.setattr(store, "save", once)
        assert _switched(owner, enabled=False, command_id="pause-1")
        recorded: WatchState = store.load()
    finally:
        monkeypatch.setattr(store, "save", original)
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    stopped: AcquisitionConfirmation = next(item for item in recorded.acquisitions if item.info_hash == "9")
    assert recorded.policy.auto_enabled is False
    assert recorded.pause_owned_transfers == ("9",)
    assert stopped.requested_action == "stop"
    assert stopped.action_pending is True


def test_a_full_pause_refuses_a_client_resume(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=False),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        resumed: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": "9", "action": "resume"}, command_id="resume-1")
        )
        browsed: ControlResponse = owner.handle(
            _request("acquisition", {"operation": "search", "query": "Neko"}, command_id="browse-1")
        )
        stopped: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": "9", "action": "stop"}, command_id="stop-1")
        )
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert resumed.code is ControlErrorCode.REFUSED
    assert resumed.reason == RefusalReason.PAUSED.value
    assert browsed.ok
    assert stopped.ok
    assert network.added == []
    assert [item for item in network.actions if item[1] == "resume"] == []
    assert store.load().acquisitions[0].requested_action == "stop"


def _stale_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, seen: str, current: str
) -> tuple[AutomationOwner, _TorrentNetwork, WatchStateStore, threading.Thread, threading.Event]:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, seen, str(tmp_path), 4, 2)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    held: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    holds: list[int] = []

    def hold() -> None:
        if holds:
            return
        holds.append(1)
        held.set()
        release.wait(_TIMEOUT_S)

    thread: threading.Thread = _serving(owner)
    assert _await(lambda: network.info_calls > 0)
    network.before_info = hold
    assert held.wait(_TIMEOUT_S)
    network.tracked["9"] = replace(network.tracked["9"], state=current)
    return owner, network, store, thread, release


def test_a_pause_stops_a_transfer_the_client_reports_working_after_an_older_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, thread, release = _stale_snapshot(
        tmp_path, monkeypatch, seen="stoppedDL", current="downloading"
    )
    try:
        assert _switched(owner, enabled=False, command_id="pause-1")
        release.set()
        assert _await(lambda: ("9", "stop") in network.actions)
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert store.load().pause_owned_transfers == ("9",)


def test_a_pause_withdraws_its_stop_for_a_transfer_the_client_reports_already_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, network, store, thread, release = _stale_snapshot(
        tmp_path, monkeypatch, seen="downloading", current="stoppedDL"
    )
    try:
        assert _switched(owner, enabled=False, command_id="pause-1")
        release.set()
        assert _await(lambda: _acquisition_fields(owner, "action") == [None])
        assert _switched(owner, enabled=True, command_id="resume-1")
        assert _await(lambda: network.info_calls > 5)
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert network.actions == []
    assert network.started == []
    assert store.load().acquisitions[0].requested_action is None


def _request_states(owner: AutomationOwner) -> list[object]:
    rows: object = owner.handle(_request("status", command_id="status-requests")).result["requests"]
    return [row["state"] for row in cast("list[Mapping[str, object]]", rows)]


def _pause_flags(owner: AutomationOwner) -> tuple[object, object, object]:
    result: Mapping[str, object] = owner.handle(_request("status", command_id="status-pause")).result
    return result["paused"], result["pausing"], result["pause_incomplete"]


def _as_background(owner: AutomationOwner) -> None:
    def convert() -> bool:
        current: AcquisitionConfirmation = owner.state.acquisitions[0]
        if current.origin is RequestOrigin.BACKGROUND:
            return True
        if owner._transfers_inspecting:
            return False
        return owner._replace_acquisition(replace(current, origin=RequestOrigin.BACKGROUND))

    assert _await(lambda: owner._on_owner(convert))


def _acquisition_fields(owner: AutomationOwner, field: str) -> list[object]:
    rows: object = owner.handle(_request("status", command_id=f"status-{field}")).result["acquisitions"]
    return [row[field] for row in cast("list[Mapping[str, object]]", rows)]


def test_a_pause_keeps_settling_while_an_owned_search_is_still_in_flight(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def hold() -> None:
        entered.set()
        release.wait(_TIMEOUT_S)

    network.before_search = hold
    thread: threading.Thread = _serving(owner)
    answers: list[ControlResponse] = []
    searching: threading.Thread = threading.Thread(
        target=lambda: answers.append(
            owner.handle(_request("acquisition", {"operation": "search", "query": "Neko"}, command_id="browse-1"))
        ),
        daemon=True,
    )
    searching.start()
    try:
        assert entered.wait(_TIMEOUT_S)
        assert _switched(owner, enabled=False, command_id="pause-1")
        during: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        release.set()
        searching.join(_TIMEOUT_S)
        settled: bool = _await(lambda: bool(owner.handle(_request("status", command_id="status-2")).result["paused"]))
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert during.result["pausing"] is True
    assert during.result["paused"] is False
    assert settled
    assert answers[0].ok


def test_a_replayed_shutdown_command_still_ends_the_resident(tmp_path: Path) -> None:
    service, store, _ = _library(tmp_path)
    first: AutomationOwner = _owner(service, store)
    opening: threading.Thread = _serving(first)
    accepted: ControlResponse = first.handle(_request("shutdown", command_id="end-1"))
    opening.join(_TIMEOUT_S)
    second: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(second)
    replayed: ControlResponse = second.handle(_request("shutdown", command_id="end-1"))
    thread.join(_TIMEOUT_S)

    assert accepted.ok
    assert replayed.ok
    assert not opening.is_alive()
    assert not thread.is_alive()
    assert [receipt.command_id for receipt in store.load().command_receipts] == ["end-1"]


def test_a_shutdown_refuses_a_global_resume_and_keeps_the_stored_pause(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        assert _switched(owner, enabled=False, command_id="pause-1")
        stopping: ControlResponse = owner.handle(_request("shutdown", command_id="end-1"))
        assert _await(lambda: network.prepared > 0)
        prepared: int = network.prepared
        resumed: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}, command_id="resume-1"))
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        thread.join(_TIMEOUT_S)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert stopping.ok
    assert network.prepared == prepared
    assert resumed.code is ControlErrorCode.REFUSED
    assert resumed.reason == RefusalReason.SHUTTING_DOWN.value
    assert not thread.is_alive()
    assert store.load().policy.auto_enabled is False
    assert service.background_admission[-1] is False


def test_a_shutdown_refuses_a_transfer_action_it_would_leave_for_the_next_start(tmp_path: Path) -> None:
    service, store, group_id = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    finished: AcquisitionConfirmation = replace(
        _accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True), state=AcquisitionState.COMPLETE
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(finished,)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        run_id: str = _started(owner)
        stopping: ControlResponse = owner.handle(_request("shutdown", command_id="end-1"))
        resumed: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": "9", "action": "resume"}, command_id="resume-1")
        )
        service.finish(run_id, GroupStatus.SUCCEEDED, group_id)
        thread.join(_TIMEOUT_S)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)

    assert stopping.ok
    assert resumed.code is ControlErrorCode.REFUSED
    assert resumed.reason == RefusalReason.SHUTTING_DOWN.value
    assert not thread.is_alive()
    assert store.load().acquisitions[0].requested_action is None
    assert network.actions == []
    assert network.started == []


class _GatedReadyStore(ReadyStore):
    def __init__(self, directory: Path, workspace: Path) -> None:
        super().__init__(directory, workspace)
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()

    def execute(self, move: ReadyMove) -> None:
        self.entered.set()
        self.release.wait(_TIMEOUT_S)
        super().execute(move)


def test_a_pause_waits_for_a_relocation_in_flight_and_settles_with_a_parked_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
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
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_owned(("Book.txt",), (), RequestOrigin.BACKGROUND, size, directory="audiobook"),),
        )
    )
    journal: _GatedReadyStore = _GatedReadyStore(tmp_path / "control" / "relocations", tmp_path)
    owner: AutomationOwner = AutomationOwner(
        service, store, instance_id=_INSTANCE, clock=lambda: _MOMENT, ready_store=journal
    )
    thread: threading.Thread = _serving(owner)
    try:
        assert journal.entered.wait(_TIMEOUT_S)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: _acquisition_fields(owner, "action_pending") == [False])
        during: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        journal.release.set()
        settled: bool = _await(lambda: bool(owner.handle(_request("status", command_id="status-2")).result["paused"]))
        parked: int = len(owner._ready_moves)
    finally:
        journal.release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        service.close()

    assert during.result["pausing"] is True
    assert during.result["paused"] is False
    assert settled
    assert parked == 1
    assert store.load().ready_groups[0].pending_sources == ("audiobook/Book.txt",)
    assert (audiobook / "Book.txt").exists()


def test_a_stored_pause_still_starts_the_private_client_without_polling_or_starting_a_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    control: RequestControl = RequestControl(httpx.MockTransport(_qbittorrent_replies(tmp_path)))
    http: httpx.Client = httpx.Client(transport=control)
    management: _TorrentNetwork = _measured_acquisition(tmp_path, service, http, control)
    management.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "stoppedDL", str(tmp_path), 4, 2)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=False),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: management.prepared == 1)
        time.sleep(0.4)
        answer: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        requests: int = sum(int(cast("int", item["count"])) for item in control.counts())
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
        http.close()

    assert answer.result["paused"] is True
    assert management.prepared == 1
    assert requests == 0
    assert management.resume_calls == 0
    assert management.started == []
    assert management.actions == []
    assert store.load().acquisitions[0].requested_action is None


def _raced_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[tuple[str, str]], WatchState]:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    network.tracked["10"] = TorrentInfo("Other", "10", 0.5, "stoppedDL", str(tmp_path), 4, 2)
    network.per_hash["10"] = (TorrentFile(0, "10.mkv", 4, 0.5, 1),)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(
                _accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),
                _accepted_transfer("10", layout=((0, "10.mkv", 4),), started=True),
            ),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def hold_one_batch() -> None:
        if entered.is_set():
            return
        entered.set()
        release.wait(_TIMEOUT_S)

    try:
        assert _await(lambda: network.info_calls > 1)
        network.before_info = hold_one_batch
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert entered.wait(_TIMEOUT_S)
        assert _switched(owner, enabled=True, command_id="resume-1")
        release.set()
        assert _await(lambda: not any(_acquisition_fields(owner, "action_pending")))
        assert _await(lambda: ("9", "resume") in network.actions)
    finally:
        release.set()
        network.before_info = None
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    return list(network.actions), store.load()


def test_a_hand_stop_in_the_client_is_never_resumed_by_a_pause_whose_stops_are_still_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions, state = _raced_resume(tmp_path, monkeypatch)

    assert [item for item in actions if item[0] == "10"] == []
    assert state.pause_owned_transfers == ()


def test_a_transfer_this_pause_stopped_is_still_taken_up_when_the_resume_overtook_its_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions, state = _raced_resume(tmp_path, monkeypatch)
    mine: list[str] = [action for info_hash, action in actions if info_hash == "9"]

    assert mine[:2] == ["stop", "resume"]
    assert state.pause_owned_transfers == ()


def test_a_cancel_a_newer_resume_replaced_is_never_sent_while_that_resume_still_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    read_states = automation_module._fresh_transfer_states

    def hold_the_batch_that_carries_the_cancel(
        acquisition: AcquisitionService, acquisitions: tuple[AcquisitionConfirmation, ...]
    ) -> Mapping[str, str]:
        if not entered.is_set() and any(item.action_id == "cancel-1" for item in acquisitions):
            entered.set()
            release.wait(_TIMEOUT_S)
        return read_states(acquisition, acquisitions)

    monkeypatch.setattr(automation_module, "_fresh_transfer_states", hold_the_batch_that_carries_the_cancel)
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        assert owner.handle(_request("transfer", {"info_hash": "9", "action": "cancel"}, command_id="cancel-1")).ok
        assert entered.wait(_TIMEOUT_S)
        assert owner.handle(_request("transfer", {"info_hash": "9", "action": "resume"}, command_id="resume-1")).ok
        release.set()
        assert _await(lambda: not any(_acquisition_fields(owner, "action_pending")))
        time.sleep(0.2)
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    settled: WatchState = store.load()

    assert ("9", "cancel") not in network.actions
    assert ("9", "resume") in network.actions
    assert [item.state for item in settled.acquisitions] == [AcquisitionState.ACCEPTED]
    assert [item.problem for item in settled.acquisitions] == [None]


class _FreezingStore(WatchStateStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.frozen: bool = False

    def save(self, state: WatchState) -> None:
        if self.frozen:
            raise OSError(_STORE_FROZEN)
        super().save(state)


def test_a_stop_that_reached_the_client_before_a_crash_is_taken_up_by_the_restarted_resident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, _, _ = _library(tmp_path)
    store: _FreezingStore = _FreezingStore(tmp_path / WATCH_STATE_FILE_NAME)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    crashed: threading.Event = threading.Event()

    def stop_the_transfer_and_lose_the_write_back() -> None:
        network.tracked["9"] = replace(network.tracked["9"], state="stoppedDL")
        store.frozen = True
        crashed.set()

    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        network.before_action = stop_the_transfer_and_lose_the_write_back
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert crashed.wait(_TIMEOUT_S)
    finally:
        network.before_action = None
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    restarted_store: WatchStateStore = WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME)
    lost: WatchState = restarted_store.load()
    restarted: AutomationOwner = _owner(service, restarted_store)
    resumed: threading.Thread = _serving(restarted)
    try:
        assert _await(lambda: not any(_acquisition_fields(restarted, "action_pending")))
        assert _switched(restarted, enabled=True, command_id="resume-1")
        assert _await(lambda: ("9", "resume") in network.actions)
    finally:
        restarted.request_shutdown()
        resumed.join(_TIMEOUT_S)

    assert lost.pause_owned_transfers == ("9",)
    assert [(item.requested_action, item.action_pending) for item in lost.acquisitions] == [("stop", True)]
    assert restarted_store.load().pause_owned_transfers == ()


def test_a_stop_the_client_refuses_is_retried_and_then_reported_instead_of_a_finished_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.5, 1),))
    network.tracked["9"] = TorrentInfo("Pack", "9", 0.5, "downloading", str(tmp_path), 4, 2)
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),), started=True),),
        )
    )
    held: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    retried: list[list[object]] = []
    published: list[tuple[object, object, object]] = []

    def refuse_every_stop() -> None:
        if network.actions.count(("9", "stop")) == 2:
            held.set()
            release.wait(_TIMEOUT_S)
        raise TorrentClientError(_STOP_REFUSED)

    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert _await(lambda: network.info_calls > 1)
        network.before_action = refuse_every_stop
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert held.wait(_TIMEOUT_S)
        retried.append(_acquisition_fields(owner, "action_pending"))
        release.set()
        assert _await(lambda: not any(_acquisition_fields(owner, "action_pending")))
        time.sleep(0.2)
        published.append(_pause_flags(owner))
        assert network.tracked["9"].state == "downloading"
    finally:
        release.set()
        network.before_action = None
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    settled: WatchState = store.load()

    assert published == [(False, False, True)]
    assert retried == [[True]]
    assert network.actions.count(("9", "stop")) == automation_module._ACTION_ATTEMPTS
    assert network.tracked["9"].state == "downloading"
    assert [item.problem is not None for item in settled.acquisitions] == [True]
    assert settled.pause_owned_transfers == ("9",)


@pytest.mark.parametrize("manual", [False, True])
def test_an_exhausted_stop_stays_visible_and_does_not_resume_until_an_explicit_transfer_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manual: bool
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    owner, network, store, service = _pausable(tmp_path, monkeypatch)

    def refuse() -> None:
        raise TorrentClientError(_STOP_REFUSED)

    network.before_action = refuse
    thread: threading.Thread = _serving(owner)
    try:
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: _pause_flags(owner) == (False, False, True))
        if manual:
            assert owner.handle(_request("transfer", {"info_hash": "9", "action": "stop"}, command_id="stop-1")).ok
            assert _await(lambda: not any(_acquisition_fields(owner, "action_pending")))
            assert _pause_flags(owner) == (False, False, True)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    attempts: int = len(network.actions)
    restarted: AutomationOwner = _owner(service, store)
    thread = _serving(restarted)
    try:
        assert _await(lambda: _pause_flags(restarted) == (False, False, True))
        assert len(network.actions) == attempts
        network.before_action = None
        assert _switched(restarted, enabled=True, command_id="resume-1")
        assert _await(lambda: network.prepared == 3)
        assert _acquisition_fields(restarted, "action") == ["stop", "stop"]
        assert _acquisition_fields(restarted, "problem")[0] is not None
        assert ("9", "resume") not in network.actions
        assert restarted.handle(_request("transfer", {"info_hash": "9", "action": "resume"}, command_id="retry-1")).ok
        assert _await(lambda: ("9", "resume") in network.actions)
        assert _await(lambda: _acquisition_fields(restarted, "problem")[0] is None)
    finally:
        restarted.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_an_unreachable_client_exhausts_pause_reads_and_keeps_the_failure_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(automation_module, "TRANSFER_BACKOFF_CEILING_S", 0.01)
    owner, network, store, service = _pausable(tmp_path, monkeypatch)
    network.unreachable = True
    thread: threading.Thread = _serving(owner)
    try:
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: _pause_flags(owner) == (False, False, True))
        reads: int = network.info_calls
        time.sleep(0.1)
        assert network.info_calls == reads
        assert network.actions == []
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()
    restarted: AutomationOwner = _owner(service, store)
    thread = _serving(restarted)
    try:
        assert _await(lambda: _pause_flags(restarted) == (False, False, True))
        assert network.info_calls == reads
        network.unreachable = False
        assert restarted.handle(_request("transfer", {"info_hash": "9", "action": "stop"}, command_id="retry-1")).ok
        assert _await(lambda: _pause_flags(restarted) == (True, False, False))
        assert network.actions == [("9", "stop")]
    finally:
        restarted.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_a_full_pause_parks_inspection_retries_and_resume_reconciles_pending_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    service, store, _ = _library(tmp_path)
    group: InspectedSourceGroup = cast("InspectedWorkspace", service._discovered).groups[0]
    service._discovered = InspectedWorkspace(
        (group,), (InspectionWarning("source_busy", "Still copying", group.group_id, group.artifacts[0].artifact_id),)
    )
    service.discover_release = threading.Event()
    owner: AutomationOwner = _owner(service, store, scan_interval_s=0.01)
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert service.discover_entered.wait(_TIMEOUT_S)
        assert _switched(owner, enabled=False, command_id="pause-1")
        service.discover_release.set()
        assert _await(lambda: _pause_flags(owner) == (True, False, False))
        inspected: int = service.discover_calls
        time.sleep(0.1)
        assert service.discover_calls == inspected
        service._discovered = InspectedWorkspace((), ())
        assert _switched(owner, enabled=True, command_id="resume-1")
        assert _await(lambda: service.discover_calls > inspected)
    finally:
        service.discover_release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_a_transfer_command_during_a_slow_read_prevents_starting_the_superseded_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, (TorrentFile(0, "09.mkv", 4, 0.0, 1),))
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(_accepted_transfer("9", layout=((0, "09.mkv", 4),)),),
        )
    )
    owner: AutomationOwner = _owner(service, store)
    switched: threading.Event = threading.Event()

    def change_during_read() -> None:
        if switched.is_set():
            return
        assert owner.handle(_request("transfer", {"info_hash": "9", "action": action}, command_id="change-1")).ok
        switched.set()

    network.before_info = change_during_read
    thread: threading.Thread = _serving(owner)
    try:
        assert switched.wait(_TIMEOUT_S)
        assert _await(lambda: ("9", action) in network.actions)
        assert _await(lambda: not any(_acquisition_fields(owner, "action_pending")))
        assert network.started == []
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_resuming_never_counts_the_pause_as_stall_time_when_the_last_client_read_still_showed_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    owner, network, _, service = _pausable(tmp_path, monkeypatch)
    service._discovered = InspectedWorkspace((), ())
    now: list[float] = [0.0]
    assert owner._transfers is not None
    monkeypatch.setattr(owner._transfers, "_clock", lambda: now[0])
    thread: threading.Thread = _serving(owner)
    try:
        owner.files_changed(DirectoryChange(reconcile=True, reason="startup"))
        assert _await(lambda: service.discover_calls == 1)
        assert _await(lambda: network.info_calls > 1)
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: _pause_flags(owner) == (True, False, False))
        reads: int = network.info_calls
        now[0] = 3600.0
        assert _switched(owner, enabled=True, command_id="resume-1")
        assert _await(lambda: network.info_calls >= reads + 2)
        assert _acquisition_fields(owner, "stalled") == [False, False]
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize("state", [AcquisitionState.ACCEPTED, AcquisitionState.UNCERTAIN, AcquisitionState.FAILED])
def test_global_pause_settles_a_public_resume_waiting_for_metadata_after_the_transfer_changes_state(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: AcquisitionState
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    network.tracked.clear()
    assert service.acquisition is not None
    catalog: ReleaseCatalog = service.acquisition.search("Neko")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)

    def apply_action() -> None:
        info_hash, action = network.actions[-1]
        if action == "cancel":
            network.tracked.pop(info_hash, None)

    network.before_action = apply_action
    try:
        downloaded: ControlResponse = owner.handle(
            _request("download", {"choices": [encode_view(catalog.groups[0].choices[0])]}, command_id="download-1")
        )
        assert downloaded.ok
        assert _acquisition_fields(owner, "state") == [AcquisitionState.ACCEPTED.value]
        _as_background(owner)
        info_hash: str = network.added[0]
        if state is AcquisitionState.FAILED:
            assert owner.handle(_request("transfer", {"info_hash": info_hash, "action": "cancel"})).ok
        elif state is AcquisitionState.UNCERTAIN:
            network.tracked.clear()
        assert _await(lambda: _acquisition_fields(owner, "state") == [state.value])
        assert owner.handle(
            _request("transfer", {"info_hash": info_hash, "action": "resume"}, command_id="resume-transfer")
        ).ok
        pending: AcquisitionConfirmation = store.load().acquisitions[0]
        assert pending.state is state
        assert pending.action_pending
        assert pending.file_layout == ()
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert _await(lambda: _pause_flags(owner) == (True, False, False))
        assert not any(_acquisition_fields(owner, "action_pending"))
        reads: int = network.info_calls
        time.sleep(0.1)
        assert network.info_calls == reads
        assert network.started == []
        assert (info_hash, "resume") not in network.actions
        settled: AcquisitionConfirmation = store.load().acquisitions[0]
        assert _switched(owner, enabled=True, command_id="resume-global")
        reordered: ControlResponse = owner.handle(
            _request("download", {"choices": [encode_view(catalog.groups[0].choices[0])]}, command_id="download-2")
        )
        if state in {AcquisitionState.UNCERTAIN, AcquisitionState.FAILED}:
            assert not reordered.ok
            assert reordered.reason == "download_recorded"
            assert reordered.details == {"sent": 0, "accepted": 0, "uncertain": 1}
        else:
            assert reordered.ok
            assert reordered.result["count"] == 0
        assert settled.state is state
        assert len(network.added) == 1
        assert store.load().acquisitions[0].operation_id == settled.operation_id
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


@pytest.mark.parametrize("refusing", [False, True])
def test_a_pause_of_an_uncertain_resume_waits_for_stop_and_reports_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusing: bool
) -> None:
    monkeypatch.setenv("ANISHIFT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    service, store, _ = _library(tmp_path)
    network: _TorrentNetwork = _stopped_transfer(tmp_path, service, ())
    network.tracked.clear()
    assert service.acquisition is not None
    catalog: ReleaseCatalog = service.acquisition.search("Neko")
    owner: AutomationOwner = _owner(service, store)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    thread: threading.Thread = _serving(owner)

    def stop_returning_transfer() -> None:
        network.tracked[info_hash] = replace(transfer, state="downloading")
        entered.set()
        assert release.wait(_TIMEOUT_S)
        if refusing:
            raise TorrentClientError(_STOP_REFUSED)
        network.tracked[info_hash] = replace(transfer, state="stoppedDL")

    try:
        assert owner.handle(
            _request("download", {"choices": [encode_view(catalog.groups[0].choices[0])]}, command_id="download-1")
        ).ok
        info_hash: str = network.added[0]
        transfer: TorrentInfo = network.tracked.pop(info_hash)
        _as_background(owner)
        assert _await(lambda: _acquisition_fields(owner, "state") == [AcquisitionState.UNCERTAIN.value])
        network.before_action = stop_returning_transfer
        assert owner.handle(
            _request("transfer", {"info_hash": info_hash, "action": "resume"}, command_id="resume-transfer")
        ).ok
        assert _switched(owner, enabled=False, command_id="pause-1")
        assert entered.wait(_TIMEOUT_S)
        assert _pause_flags(owner) == (False, True, False)
        assert network.tracked[info_hash].state == "downloading"
        release.set()
        assert _await(lambda: _pause_flags(owner) == (not refusing, False, refusing))
        assert network.tracked[info_hash].state == ("downloading" if refusing else "stoppedDL")
        assert network.actions == [(info_hash, "stop")] * (automation_module._ACTION_ATTEMPTS if refusing else 1)
        assert network.started == []
        reads: int = network.info_calls
        time.sleep(0.1)
        assert network.info_calls == reads
    finally:
        release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


_SEARCH_FIXTURES: Final[Path] = Path(__file__).parents[1] / "fixtures" / "search"

_SLIME_S1: Final[int] = 101280


def _slime_replay(scenario: str, sent: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    recorded: dict[str, object] = json.loads(
        (_SEARCH_FIXTURES / f"anilist__franchise__{_SLIME_S1}.json").read_text(encoding="utf-8")
    )
    requests: object = recorded["requests"]
    assert isinstance(requests, list)
    pages: dict[tuple[int, ...], object] = {tuple(sorted(page["ids"])): page["body"] for page in requests}
    schedule: dict[str, object] = {
        "data": {
            "Media": {
                "id": _SLIME_S1,
                "status": "FINISHED",
                "episodes": 24,
                "startDate": {"year": 2018, "month": 10, "day": 2},
                "airingSchedule": {"pageInfo": {"currentPage": 1, "hasNextPage": False}, "nodes": []},
            }
        }
    }

    failing: str | None = {
        "anilist_failed": "graphql.anilist.co",
        "anizip_failed": "api.ani.zip",
        "torrentio_failed": "torrentio.strem.fun",
    }.get(scenario)

    def respond(request: httpx.Request) -> httpx.Response:
        host: str = request.url.host
        sent.append(host)
        variables: dict[str, object] = json.loads(request.content)["variables"] if request.content else {}
        if host == failing:
            return httpx.Response(503)
        if host == "graphql.anilist.co" and "ids" not in variables and scenario == "long_schedule":
            page: object = variables["page"]
            assert isinstance(page, int)
            return httpx.Response(200, json=_long_schedule_page(page))
        if host == "graphql.anilist.co" and "ids" not in variables:
            return (
                httpx.Response(429, headers={"Retry-After": "60"})
                if scenario == "schedule_limited"
                else (httpx.Response(200, json=schedule))
            )
        if host == "graphql.anilist.co":
            ids: object = variables["ids"]
            assert isinstance(ids, list)
            return httpx.Response(200, json=pages[tuple(sorted(ids))])
        if host == "api.ani.zip":
            return httpx.Response(200, content=(_SEARCH_FIXTURES / f"anizip__{_SLIME_S1}.json").read_bytes())
        assert (host, request.url.path) == ("torrentio.strem.fun", "/stream/series/kitsu:41024:4.json")
        return httpx.Response(200, content=(_SEARCH_FIXTURES / "torrentio__kitsu-41024-4.json").read_bytes())

    return respond


_LONG_SCHEDULE_EPISODES: Final[int] = 425


def _long_schedule_page(page: int) -> dict[str, object]:
    numbers: range = range((page - 1) * 25 + 1, min(page * 25, _LONG_SCHEDULE_EPISODES) + 1)
    return {
        "data": {
            "Media": {
                "id": _SLIME_S1,
                "status": "RELEASING",
                "episodes": None,
                "startDate": {"year": 2018, "month": 10, "day": 2},
                "airingSchedule": {
                    "pageInfo": {"currentPage": page, "hasNextPage": numbers.stop <= _LONG_SCHEDULE_EPISODES},
                    "nodes": [{"episode": number, "airingAt": number} for number in numbers],
                },
            }
        }
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario",
    ["ok", "schedule_limited", "long_schedule", "anilist_failed", "anizip_failed", "torrentio_failed", "offer_raises"],
)
def test_episode_selection_crosses_owner_ipc_with_the_provider_reason_preserved(  # noqa: PLR0915
    tmp_path: Path, scenario: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    now: list[float] = [1000.0]
    control: RequestControl = RequestControl(
        httpx.MockTransport(_slime_replay(scenario, sent)),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=_NoSource(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
            request_control=control,
            episode_catalog=AniZipCatalog(http),
            stream_source=TorrentioSource(http),
            clock=lambda: now[0],
        )
        if scenario == "offer_raises":

            def broken(key: EpisodeKey) -> EpisodeOffer:
                raise ValueError(key.number)

            monkeypatch.setattr(acquisition, "offer", broken)
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        captured: list[str] = []
        handler_id: int = loguru_logger.add(
            captured.append,
            format="{message} {extra}",
            level="WARNING",
            filter=lambda record: record["extra"].get("command_kind") == "acquisition",
        )
        try:
            failures: dict[str, ControlError] = {}
            for name, call in (
                ("franchise", lambda: session.franchise(_SLIME_S1)),
                ("episodes", lambda: session.episodes(_SLIME_S1)),
                ("offer", lambda: session.offer(EpisodeKey(_SLIME_S1, 4))),
            ):
                try:
                    call()
                except ControlError as error:
                    failures[name] = error
            expected: dict[str, tuple[str, str]] = {
                "anilist_failed": ("franchise", ErrorCode.TITLE_CATALOG_FAILED.value),
                "anizip_failed": ("episodes", ErrorCode.EPISODE_CATALOG_FAILED.value),
                "torrentio_failed": ("offer", ErrorCode.TORRENT_SOURCE_FAILED.value),
                "offer_raises": ("offer", "command_failed"),
            }
            if scenario in expected:
                operation, reason = expected[scenario]
                assert operation in failures
                assert (failures[operation].code, failures[operation].reason) == (ControlErrorCode.INTERNAL, reason)
                assert "error_class" in "".join(captured)
            if scenario == "offer_raises":
                assert "ValueError" in "".join(captured)
            if scenario in {"ok", "schedule_limited"}:
                assert not failures
                listing: EpisodeListing = session.episodes(_SLIME_S1)
                offer: EpisodeOffer = session.offer(EpisodeKey(_SLIME_S1, 4))
                assert offer.suggestion is not None
                assert offer.candidates[offer.suggestion].identity.verdict is IdentityVerdict.MATCH
                assert len(listing.episodes) == 24
            if scenario == "schedule_limited":
                assert (listing.schedule_warning, listing.schedule_retry_at) == (
                    "TITLE_CATALOG_FAILED",
                    datetime.fromtimestamp(control.blocked_until(("anilist",)), UTC),
                )
                assert (listing.status, listing.aired) == ("FINISHED", None)
                assert not any(episode.aired for episode in listing.episodes)
            if scenario == "ok":
                assert (listing.schedule_warning, listing.aired) == (None, 24)
                assert all(episode.aired for episode in listing.episodes)
                assert sent.count("api.ani.zip") == 1
            if scenario == "long_schedule":
                assert not failures
                long: EpisodeListing = session.episodes(_SLIME_S1)
                assert (long.schedule_warning, long.status, long.aired) == (None, "RELEASING", _LONG_SCHEDULE_EPISODES)
                assert len(long.episodes) == _LONG_SCHEDULE_EPISODES
                assert all(episode.aired for episode in long.episodes)
                assert sent.count("graphql.anilist.co") == 3 + 17
            assert all(value not in "".join(captured) for value in ("https://", "Slime", "kitsu"))
        finally:
            loguru_logger.remove(handler_id)
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
def test_interrupted_catalogue_channel_stops_the_owner_franchise_expansion(tmp_path: Path) -> None:
    requested: list[int] = []
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        identifier: int = json.loads(request.content)["variables"]["ids"][0]
        requested.append(identifier)
        entered.set()
        assert release.wait(_TIMEOUT_S)
        child: dict[str, object] = {"id": identifier + 1, "type": "ANIME", "format": "TV", "title": {"romaji": "Next"}}
        node: dict[str, object] = {
            "id": identifier,
            "type": "ANIME",
            "format": "TV",
            "title": {"romaji": "Root"},
            "relations": {"edges": [{"relationType": "SEQUEL", "node": child}]},
        }
        return httpx.Response(200, json={"data": {"Page": {"media": [node]}}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=_NoSource(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        failures: list[ControlError] = []

        def read() -> None:
            try:
                session.franchise(1)
            except ControlError as error:
                failures.append(error)

        reader: threading.Thread = threading.Thread(target=read, daemon=True)
        try:
            reader.start()
            assert entered.wait(_TIMEOUT_S)
            session.interrupt_reads()
            reader.join(_TIMEOUT_S)
            assert failures
            deadline: float = time.monotonic() + _TIMEOUT_S
            while owner._catalog_reads and time.monotonic() < deadline:
                time.sleep(0.01)
            assert not owner._catalog_reads
            release.set()
        finally:
            release.set()
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()
    assert requested == [1]


@pytest.mark.integration
def test_a_catalogue_channel_opened_after_an_interrupt_is_discarded_and_the_next_read_works(tmp_path: Path) -> None:
    requested: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(json.loads(request.content)["variables"]["ids"][0])
        media: list[dict[str, object]] = [
            {"id": requested[-1], "type": "ANIME", "format": "TV", "title": {"romaji": "R"}, "relations": {"edges": []}}
        ]
        return httpx.Response(200, json={"data": {"Page": {"media": media}}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=_NoSource(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        connecting: threading.Event = threading.Event()
        proceed: threading.Event = threading.Event()
        opened: list[ControlClient] = []

        def connect() -> ControlClient:
            if opened:
                connecting.set()
                assert proceed.wait(_TIMEOUT_S)
            client: ControlClient = ControlClient(endpoint, key)
            opened.append(client)
            return client

        session: ResidentSession = ResidentSession(tmp_path, connect)
        cancel: EventCancellationToken = EventCancellationToken()
        failures: list[Exception] = []

        def read() -> None:
            try:
                session.franchise(1, cancel=cancel)
            except (ControlError, ExecutionError) as error:
                failures.append(error)

        reader: threading.Thread = threading.Thread(target=read, daemon=True)
        try:
            reader.start()
            assert connecting.wait(_TIMEOUT_S)
            cancel.cancel()
            session.interrupt_reads()
            proceed.set()
            reader.join(_TIMEOUT_S)
            assert [type(failure) for failure in failures] == [ControlError]
            assert requested == []
            assert session.franchise(1).selected_id == 1
            assert requested == [1]
        finally:
            proceed.set()
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
def test_a_long_schedule_read_outlasts_the_default_answer_wait_while_other_commands_stay_answered(
    tmp_path: Path,
) -> None:
    sent: list[str] = []
    paging: threading.Event = threading.Event()
    replay: Callable[[httpx.Request], httpx.Response] = _slime_replay("long_schedule", sent)

    def slow(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graphql.anilist.co" and "ids" not in json.loads(request.content)["variables"]:
            paging.set()
            time.sleep(0.04)
        return replay(request)

    now: list[float] = [1000.0]
    control: RequestControl = RequestControl(
        httpx.MockTransport(slow), clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay)
    )
    with httpx.Client(transport=control) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=_NoSource(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
            request_control=control,
            episode_catalog=AniZipCatalog(http),
            stream_source=TorrentioSource(http),
            clock=lambda: now[0],
        )
        service: AppService = _real_service(tmp_path, acquisition=acquisition)
        owner: AutomationOwner = _owner(service, WatchStateStore(tmp_path / "control" / WATCH_STATE_FILE_NAME))
        thread: threading.Thread = _serving(owner)
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key, timeout_s=0.2))
        listings: list[EpisodeListing] = []
        reader: threading.Thread = threading.Thread(target=lambda: listings.append(session.episodes(_SLIME_S1)))
        try:
            reader.start()
            assert paging.wait(_TIMEOUT_S)
            assert "material_counts" in session.command("status")
            reader.join(_TIMEOUT_S)
            assert not reader.is_alive()
            assert [len(listing.episodes) for listing in listings] == [_LONG_SCHEDULE_EPISODES]
            assert sent.count("graphql.anilist.co") == 17
        finally:
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(_TIMEOUT_S)
            service.close()
        assert not thread.is_alive()


class _NoSource:
    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        raise AssertionError(query)
