from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any, Final, cast

import httpx
import pytest
from test_acquisition import _S1, _episode_service, _slime_titles, _StreamSource, _TitleCatalog
from test_automation import _TIMEOUT_S, _real_service, _request, _serving
from test_episode_admission import _ENTRY, _Library, _subscribe
from test_episode_admission import _choice as _legacy_choice
from test_episode_admission import _library as _legacy_library
from test_episode_search import controlled, empty_response, search_service
from test_selective_lifecycle import _SelectiveNetwork, _until

from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.acquisition_staging import file_stamp
from anishift.application.artifacts import SourceGroup, create_group_id
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AutomationPolicy,
    CommandReceipt,
    EpisodeAssignment,
    EpisodePublication,
    LegacyScope,
    ProductConfirmation,
    PublishedFile,
    ReadyGroup,
    RefusalReason,
    WatchState,
    compact_acquisition,
)
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_commands import (
    EpisodeBatch,
    EpisodeFiles,
    EpisodeOfferView,
    EpisodeReason,
    EpisodeResult,
    EpisodeStatus,
)
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import EpisodeKey, StreamCandidate
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import RequestOrigin
from anishift.application.service import AppService
from anishift.application.subscription_migration import legacy_reference, migrate
from anishift.application.subscription_targets import PauseReason, SubscriptionRecord
from anishift.application.subscriptions import EpisodeOrder, EpisodeState, Subscription, SubscriptionStore
from anishift.application.transfers import TransferInspector, file_map_revision
from anishift.application.watch_state import WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.cli.resident import ResidentSession
from anishift.config import user_settings
from anishift.config.field_access import assign_setting_value
from anishift.config.field_catalog import SettingSpec, setting_catalog
from anishift.config.user_settings import UserSettings, save_user_settings
from anishift.errors import ErrorCode
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlResponse,
    ControlServer,
    control_endpoint,
)
from anishift.services.catalog.anizip import AniZipCatalog
from anishift.services.catalog.types import SeasonAiring, TitleStatus
from anishift.services.http_requests import RequestControl
from anishift.services.torrents import TorrentFile, TorrentInfo

_FIRST: Final[dict[str, object]] = {"seasonNumber": 1, "episodeNumber": 1}

_WITHOUT_NUMBERING: Final[list[Any]] = [
    pytest.param(404, {"1": _FIRST}, id="404"),
    pytest.param(500, {"1": _FIRST}, id="500"),
    pytest.param(200, {"1": _FIRST}, id="missing-key"),
    pytest.param(200, {"1": _FIRST, "4": {"title": {"en": "Fourth"}}}, id="without-season-episode"),
    pytest.param(
        200,
        {"3": {"seasonNumber": 1, "episodeNumber": 3}, "4": {"seasonNumber": 1, "episodeNumber": 3}},
        id="duplicate",
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize(("mapping_status", "episodes"), _WITHOUT_NUMBERING)
def test_offer_without_numbering_shows_releases(
    tmp_path: Path, mapping_status: int, episodes: dict[str, object]
) -> None:
    _without_numbering(tmp_path, mapping_status, episodes, repeat=False, download=False)


@pytest.mark.integration
@pytest.mark.parametrize(("mapping_status", "episodes"), _WITHOUT_NUMBERING)
def test_repeat_without_numbering_has_no_suggestion(
    tmp_path: Path, mapping_status: int, episodes: dict[str, object]
) -> None:
    _without_numbering(tmp_path, mapping_status, episodes, repeat=True, download=False)


@pytest.mark.integration
@pytest.mark.parametrize(("mapping_status", "episodes"), _WITHOUT_NUMBERING)
def test_d_without_numbering_does_not_admit(tmp_path: Path, mapping_status: int, episodes: dict[str, object]) -> None:
    _without_numbering(tmp_path, mapping_status, episodes, repeat=False, download=True)


def _without_numbering(
    tmp_path: Path,
    mapping_status: int,
    episodes: dict[str, object],
    *,
    repeat: bool,
    download: bool,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.ani.zip":
            return httpx.Response(mapping_status, json={"mappings": {}, "episodes": episodes})
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: AcquisitionService = _episode_service(tmp_path)
        service._episode_catalog = AniZipCatalog(http)
        service._episode_search = search_service(http, control)
        store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
        if repeat:
            store.save(WatchState(acquisitions=(_legacy(),)))
        with _running(service, store, inspect_transfers=False) as owner:
            server: ControlServer = ControlServer(
                control_endpoint(tmp_path / "ipc"), b"episode-test-key", owner.handle, on_disconnect=owner.disconnect
            )
            session: ResidentSession = ResidentSession(
                tmp_path, lambda: ControlClient(control_endpoint(tmp_path / "ipc"), b"episode-test-key")
            )
            try:
                view: EpisodeOfferView = session.episode_offer(EpisodeKey(_S1, 4), repeat=repeat)
                assert view.offer.candidates
                assert view.offer.suggestion is None
                assert not view.offer.numbering
                assert view.offer.status == "brak numeracji"
                assert "Torrentio: brak Kitsu ID" in view.offer.source_lines
                if not download:
                    return
                done: threading.Event = threading.Event()
                results: list[Mapping[str, object]] = []

                def event(value: Mapping[str, object], terminal: bool) -> None:
                    del terminal
                    if value.get("event") == "episode_batch":
                        results.append(value)
                        done.set()

                owner.attach_broadcast(event)
                assert (
                    session.episode_download((EpisodeKey(_S1, 4),), command_id="missing-numbering").state == "accepted"
                )
                assert done.wait(_TIMEOUT_S)
                batch: EpisodeBatch = decode_view(EpisodeBatch, results[0]["payload"])
                assert batch.results[0].reason == EpisodeReason.NO_SUGGESTION
                assert len(owner.state.acquisitions) == int(repeat)
            finally:
                session.close()
                server.close()


@pytest.mark.integration
def test_source_switch_through_settings_api_reaches_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return empty_response(request)

    monkeypatch.setattr(user_settings, "config_path", lambda: tmp_path / "settings.json")
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: AcquisitionService = _episode_service(tmp_path)
        service._episode_search = search_service(http, control)
        with _running(service, WatchStateStore(tmp_path / "state.json"), inspect_transfers=False) as owner:
            owner._service._env_file = tmp_path / "absent.env"
            initial: EpisodeOfferView = _offer(owner)
            assert "Knaben: gotowe" in initial.offer.source_lines
            assert "api.knaben.org" in seen
            settings: UserSettings = UserSettings()
            spec: SettingSpec = next(spec for spec in setting_catalog() if spec.setting_id == "source_knaben")
            assign_setting_value(settings, spec, False)
            save_user_settings(settings)
            assert owner.handle(_request("reload_settings", command_id="reload")).ok
            seen.clear()
            updated: EpisodeOfferView = _offer(owner)
            assert "Knaben: wyłączone" in updated.offer.source_lines
            assert "api.knaben.org" not in seen


@pytest.mark.integration
@pytest.mark.parametrize("blocked_host", ["api.knaben.org", "api.tsukihime.org"])
def test_episode_download_waits_for_all_sources(tmp_path: Path, blocked_host: str) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    finished: threading.Event = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == blocked_host and (blocked_host == "api.knaben.org" or "/torrents/" in request.url.path):
            entered.set()
            assert release.wait(_TIMEOUT_S)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: AcquisitionService = _episode_service(tmp_path)
        service._episode_search = search_service(http, control)
        with _running(service, WatchStateStore(tmp_path / "state.json"), inspect_transfers=False) as owner:
            owner.attach_broadcast(
                lambda event, terminal: finished.set() if event.get("event") == "episode_batch" else None
            )
            try:
                assert _download(owner, (4,)).ok
                assert entered.wait(_TIMEOUT_S)
                assert not finished.is_set()
                assert not owner.state.acquisitions
            finally:
                release.set()
            assert finished.wait(_TIMEOUT_S)
            assert _batch(owner, (4,)).state == "completed"


class _Streams(_StreamSource):
    def __init__(self) -> None:
        super().__init__()
        self.before: Callable[[int], None] | None = None

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        if self.before is not None:
            self.before(number)
        return super().streams(kitsu_id, number)


def _stream(number: int, info_hash: str = "a", *, uncertain: bool = False) -> StreamCandidate:
    name: str = "mystery.mkv" if uncertain else f"[Group] Tensei shitara Slime Datta Ken - {number:02d} [1080p].mkv"
    return StreamCandidate(info_hash * 40, None, number, name, name, None, 10, "1 GB", None, (), ())


@contextmanager
def _running(
    service: AcquisitionService,
    store: WatchStateStore,
    *,
    instance: str = "test-instance",
    inspect_transfers: bool = True,
) -> Iterator[AutomationOwner]:
    titles: _TitleCatalog = _slime_titles()
    titles.schedules[_S1] = SeasonAiring(_S1, TitleStatus.FINISHED, 24, ())
    service._title_catalog = titles
    owner: AutomationOwner = AutomationOwner(
        _real_service(service._workspace_root, acquisition=service),
        store,
        instance_id=instance,
    )
    if not inspect_transfers:
        owner._transfers = None
    thread: threading.Thread = _serving(owner)
    try:
        yield owner
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def _download(owner: AutomationOwner, numbers: tuple[int, ...], command: str = "batch") -> ControlResponse:
    return owner.handle(
        _request(
            "episode_download",
            {
                "keys": [encode_view(EpisodeKey(_S1, number)) for number in numbers],
            },
            command_id=command,
            session_id="panel",
        )
    )


def _batch(owner: AutomationOwner, numbers: tuple[int, ...], command: str = "batch") -> EpisodeBatch:
    response: ControlResponse = _download(owner, numbers, command)
    assert response.ok, response
    return decode_view(EpisodeBatch, response.result)


def _offer(owner: AutomationOwner, *, repeat: bool = False, session: str = "panel") -> EpisodeOfferView:
    response: ControlResponse = owner.handle(
        _request(
            "episode_offer",
            {
                "key": encode_view(EpisodeKey(_S1, 4)),
                "repeat": repeat,
            },
            command_id="offer",
            session_id=session,
        )
    )
    assert response.ok, response
    return decode_view(EpisodeOfferView, response.result)


def _choose(
    owner: AutomationOwner,
    view: EpisodeOfferView,
    *,
    confirm: bool = False,
    session: str = "panel",
    command: str = "choose",
) -> ControlResponse:
    return owner.handle(
        _request(
            "episode_choose",
            {
                "offer_id": view.offer_id,
                "candidate": encode_view(view.offer.candidates[0].stream),
                "conflict_confirmed": confirm,
                "deviation_confirmed": confirm,
            },
            command_id=command,
            session_id=session,
            instance_id=view.instance_id,
        )
    )


def _legacy() -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        "legacy",
        "old",
        "",
        (),
        AcquisitionState.UNCERTAIN,
        RequestOrigin.USER,
        None,
        "4",
        datetime.now(UTC).isoformat(),
        legacy_scope=LegacyScope(_S1, 4),
    )


@pytest.mark.parametrize(
    ("state", "started", "number", "expected"),
    [
        (AcquisitionState.ACCEPTED, True, 4, "downloading"),
        (AcquisitionState.ACCEPTED, False, 4, "ordered"),
        (AcquisitionState.COMPLETE, True, 4, "downloaded"),
        (AcquisitionState.FAILED, False, 4, "processing_failed"),
        (AcquisitionState.ACCEPTED, True, None, "possibly_admitted"),
    ],
)
def test_legacy_episode_projects_proven_transfer_state(
    tmp_path: Path, state: AcquisitionState, *, started: bool, number: int | None, expected: str
) -> None:
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    old: AcquisitionConfirmation = replace(
        _legacy(), state=state, content_started=started, legacy_scope=LegacyScope(_S1, number)
    )
    store.save(WatchState(acquisitions=(old,)))
    with _running(_episode_service(tmp_path), store, inspect_transfers=False) as owner:
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])
        assert states[0].state == expected


def test_legacy_hash_refusal_remains_visible_in_episode_states_after_restart(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(replace(_legacy(), info_hash="a" * 40, legacy_scope=None),),
        )
    )
    with _running(service, store, inspect_transfers=False) as owner:
        assert _download(owner, (4,)).ok
        _until(lambda: _batch(owner, (4,)).state == "completed")
        assert _batch(owner, (4,)).results[0].reason == "transfer_recorded"
    with _running(service, store, inspect_transfers=False) as owner:
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])
        assert states[0].state != "not_ordered"
        assert states[0].reason == "transfer_recorded"


def test_legacy_completed_episode_uses_its_ready_group(tmp_path: Path) -> None:
    name: str = "Episode 04.mkv"
    group_id: str = create_group_id(Path(), "Episode 04")
    old: AcquisitionConfirmation = replace(
        _legacy(),
        state=AcquisitionState.COMPLETE,
        required_files=(name,),
        file_layout=((0, name, 4),),
        complete_files=(name,),
    )
    ready: ReadyGroup = ReadyGroup(
        group_id,
        "relocated",
        "Episode 04",
        "",
        "Episode 04",
        WorkflowTarget.VIDEO,
        (f"ready/{name}",),
        (),
    )
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(acquisitions=(old,), ready_groups=(ready,)))
    with _running(_episode_service(tmp_path), store, inspect_transfers=False) as owner:
        (owner._service.workspace_root / "ready").mkdir(parents=True, exist_ok=True)
        (owner._service.workspace_root / "ready" / name).write_bytes(b"video")
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])
        assert states[0].state == "ready"
        assert states[0].set_id == group_id


def test_episode_batch_reasons_cross_ipc_as_their_plain_string_values() -> None:
    reasons: tuple[str, ...] = (
        EpisodeReason.NO_SUGGESTION,
        ErrorCode.TORRENT_SOURCE_FAILED.value,
        RefusalReason.SHUTTING_DOWN,
        "reason_from_a_newer_owner",
    )
    batch: EpisodeBatch = EpisodeBatch(
        "batch",
        "instance",
        tuple(EpisodeKey(_S1, number) for number in range(1, 5)),
        "completed",
        tuple(EpisodeResult(EpisodeKey(_S1, number), reason) for number, reason in enumerate(reasons, start=1)),
    )
    payload: str = json.dumps(encode_view(batch))
    decoded: EpisodeBatch = decode_view(EpisodeBatch, json.loads(payload))

    assert [item.reason for item in decoded.results] == [str(reason) for reason in reasons]
    assert all(type(item.reason) is str for item in decoded.results)
    assert '"reason": "no_suggestion"' in payload


def test_a_historical_batch_receipt_keeps_the_source_failure_and_owner_refusal_of_each_episode(
    tmp_path: Path,
) -> None:
    keys: tuple[EpisodeKey, ...] = (EpisodeKey(_S1, 4), EpisodeKey(_S1, 5))
    recorded: str = json.dumps(
        {
            "command_id": "old-batch",
            "instance_id": "old-instance",
            "keys": [{"anilist_id": _S1, "number": 4}, {"anilist_id": _S1, "number": 5}],
            "state": "completed",
            "results": [
                {"key": {"anilist_id": _S1, "number": 4}, "reason": "TORRENT_SOURCE_FAILED"},
                {"key": {"anilist_id": _S1, "number": 5}, "reason": "shutting_down"},
            ],
        }
    )
    receipt: CommandReceipt = CommandReceipt(
        "old-batch", datetime(2026, 1, 1, tzinfo=UTC).isoformat(), {"kind": "episode_download", "batch": recorded}
    )
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(command_receipts=(receipt,)))
    with _running(_episode_service(tmp_path), store, inspect_transfers=False) as owner:
        response: ControlResponse = owner.handle(
            _request("episode_states", {"anilist_id": _S1, "numbers": [key.number for key in keys]})
        )
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])

    assert [(item.state, item.reason) for item in states] == [
        ("not_ordered", "TORRENT_SOURCE_FAILED"),
        ("not_ordered", "shutting_down"),
    ]


def test_legacy_order_without_transfer_remains_possibly_admitted(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    SubscriptionStore(library.listing).save(
        (replace(subscription, enabled=False, episodes=(EpisodeOrder(Decimal(3), state=EpisodeState.ORDERED),)),)
    )
    with _running(_episode_service(tmp_path), library.store) as owner:
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _ENTRY, "numbers": [3]}))
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])
        assert states[0].state == "possibly_admitted"
        assert states[0].reason == "episode_possibly_admitted"


def test_batch_returns_before_source_and_survives_panel_disconnect(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5, "b", uncertain=True),)}
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def before(number: int) -> None:
        if number == 4:
            entered.set()
            assert release.wait(_TIMEOUT_S)

    streams.before = before
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    events: list[Mapping[str, object]] = []
    with _running(service, store) as owner:
        owner.attach_broadcast(lambda event, terminal: events.append(event))
        batch: EpisodeBatch = _batch(owner, (4, 5))
        try:
            assert batch.state == "accepted"
            assert entered.wait(_TIMEOUT_S)
            owner.disconnect("panel")
        finally:
            release.set()
        _until(lambda: len(owner.state.acquisitions) == 2)
        _until(lambda: any(event.get("event") == "episode_batch" for event in events))
        result: ControlResponse = owner.handle(
            _request(
                "episode_download",
                {
                    "keys": [encode_view(key) for key in batch.keys],
                },
                command_id="batch",
                session_id="new-panel",
            )
        )
        assert result.ok
        assert decode_view(EpisodeBatch, result.result).state == "completed"
        assert len(streams.asked) == 2
        assert not owner.state.acquisitions[1].assignments[0].choice.deviation_confirmed
        assert len([event for event in events if event.get("event") == "episode_result"]) == 2


@pytest.mark.parametrize("numbers", [(), (4, 4), tuple(range(1, 102)), (-1,)])
def test_invalid_batch_has_no_receipt_or_source_effect(tmp_path: Path, numbers: tuple[int, ...]) -> None:
    streams: _Streams = _Streams()
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    with _running(service, WatchStateStore(tmp_path / "state.json")) as owner:
        assert not _download(owner, numbers).ok
        assert not owner.state.command_receipts
        assert not streams.asked


def test_batch_source_failure_does_not_prevent_the_next_episode(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 5): (_stream(5),)}

    def before(number: int) -> None:
        if number == 4:
            raise OSError("source unavailable")

    streams.before = before
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        assert _download(owner, (4, 5)).ok
        _until(lambda: _batch(owner, (4, 5)).state == "completed")
        batch: EpisodeBatch = _batch(owner, (4, 5))
        assert [item.reason for item in batch.results] == ["source_failed", "admitted"]
        assert _download(owner, (4,), "batch").reason == "command_reused"


def test_a_foreign_receipt_under_an_episode_identifier_reads_as_reused_without_admission(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    searching: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def before(_number: int) -> None:
        searching.set()
        assert release.wait(_TIMEOUT_S)

    streams.before = before
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        try:
            assert owner.handle(_request("set_auto", {"enabled": False}, command_id="batch:episode:4")).ok
            assert _download(owner, (4,)).ok
            assert searching.wait(_TIMEOUT_S)
            pending: EpisodeBatch = _batch(owner, (4,))
        finally:
            release.set()
        _until(lambda: _batch(owner, (4,)).state == "completed")
        batch: EpisodeBatch = _batch(owner, (4,))
        assert owner.state.acquisitions == ()
    assert pending.state == "accepted"
    assert [item.reason for item in pending.results] == [EpisodeReason.COMMAND_REUSED]
    assert [item.reason for item in batch.results] == [EpisodeReason.COMMAND_REUSED]


@pytest.mark.parametrize("paused", [False, True])
def test_download_batch_repeats_completed_episode_and_preserves_previous_files(tmp_path: Path, paused: bool) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5, "c"),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    with _running(service, store, inspect_transfers=False) as owner:
        assert owner.handle(_request("set_auto", {"enabled": not paused}, command_id="policy")).ok
        assert _download(owner, (4,), "original").ok
        _until(lambda: _batch(owner, (4,), "original").state == "completed")
        old: AcquisitionConfirmation = owner.state.acquisitions[0]
        filename: str = str(_stream(4).file_name)
        assignment: EpisodeAssignment = replace(old.assignments[0], files=((0, filename, 123),), file_map="revision")
        complete: AcquisitionConfirmation = replace(
            old,
            state=AcquisitionState.COMPLETE,
            assignments=(assignment,),
            required_files=(filename,),
            complete_files=(filename,),
        )
        assert owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(complete,))))
        streams.answers[(41024, 4)] = (_stream(4), _stream(4, "b"))
        assert _download(owner, (4, 5), "repeat-mixed").ok
        _until(lambda: _batch(owner, (4, 5), "repeat-mixed").state == "completed")
        batch: EpisodeBatch = _batch(owner, (4, 5), "repeat-mixed")
        assert [result.reason for result in batch.results] == ["admitted", "admitted"]
        kept: EpisodeAssignment = owner.state.acquisitions[0].assignments[0]
        assert kept.files == assignment.files
        assert kept.replaced
        repeated: EpisodeAssignment = owner.state.acquisitions[1].assignments[0]
        assert repeated.previous_admission_id == assignment.admission_id
        assert repeated.choice.reference.info_hash == "b" * 40
        assert repeated.choice.number == 4
        assert owner.state.acquisitions[2].assignments[0].choice.number == 5
        assert _batch(owner, (4, 5), "repeat-mixed") == batch
        assert len(owner.state.acquisitions) == 3


def _ready_episode(
    owner: AutomationOwner, state: AcquisitionState, *, present: bool
) -> tuple[EpisodeAssignment, ReadyGroup]:
    assert _download(owner, (4,), "original").ok
    _until(lambda: _batch(owner, (4,), "original").state == "completed")
    old: AcquisitionConfirmation = owner.state.acquisitions[0]
    filename: str = str(_stream(4).file_name)
    assignment: EpisodeAssignment = replace(
        old.assignments[0], files=((0, filename, 123),), file_map="revision", group_id="episode-4"
    )
    other: EpisodeAssignment = replace(
        old.assignments[0],
        admission_id="other",
        choice=replace(old.assignments[0].choice, number=5),
        files=((1, "Slime - 05.mkv", 456),),
        file_map="revision",
    )
    ready: ReadyGroup = ReadyGroup(
        "episode-4",
        "ready-episode-4",
        "Slime - 04",
        "",
        "Slime - 04",
        WorkflowTarget.VIDEO,
        ("ready/Slime - 04.mkv",),
        ("ready/Slime - 04.pl.mkv",),
        "ready/Slime - 04.pl.mkv",
    )
    transfer: AcquisitionConfirmation = replace(
        old,
        state=state,
        assignments=(assignment,) if state is AcquisitionState.COMPLETE else (assignment, other),
        required_files=(filename,),
        complete_files=(filename,),
        cleaned=state is AcquisitionState.COMPLETE,
    )
    (owner._service.workspace_root / "ready").mkdir(parents=True, exist_ok=True)
    (owner._service.workspace_root / "ready" / "Slime - 04.mkv").write_bytes(b"source")
    products: tuple[ProductConfirmation, ...] = ()
    if present:
        result: Path = owner._service.workspace_root / "ready" / "Slime - 04.pl.mkv"
        result.write_bytes(b"result")
        products = (
            ProductConfirmation(
                "ready-episode-4",
                "video_pl",
                "ready/Slime - 04.pl.mkv",
                1,
                "run",
                RequestOrigin.USER,
                result.stat().st_size,
                result.stat().st_mtime_ns,
            ),
        )
    assert owner._on_owner(
        lambda: owner._save(replace(owner.state, acquisitions=(transfer,), ready_groups=(ready,), products=products))
    )
    groups: tuple[SourceGroup, ...] = owner._service.library_inventory()
    owner._on_owner(lambda: owner._record_ready_inventory(groups))
    return assignment, ready


def _episode_state(owner: AutomationOwner) -> EpisodeStatus:
    response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
    return decode_view(tuple[EpisodeStatus, ...], response.result["items"])[0]


def _download_reason(owner: AutomationOwner, command: str) -> str:
    assert _download(owner, (4,), command).ok
    _until(lambda: _batch(owner, (4,), command).state == "completed")
    return _batch(owner, (4,), command).results[0].reason


@pytest.mark.parametrize("present", [True, False])
def test_ready_episode_without_its_main_result_returns_to_download_and_d_reorders_the_same_release(
    tmp_path: Path, *, present: bool
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    with _running(service, store, inspect_transfers=False) as owner:
        assignment, ready = _ready_episode(owner, AcquisitionState.COMPLETE, present=present)
        status: EpisodeStatus = _episode_state(owner)
        assert owner.state.ready_groups == (ready,)
        followed: SubscriptionRecord = SubscriptionRecord(
            "s", _S1, "Slime", "2026-01-01T00:00:00+00:00", 3, paused=True, pause_reason=PauseReason.USER
        )
        assert owner._on_owner(lambda: owner._save(replace(owner.state, subscriptions=(followed,))))
        listed: ControlResponse = owner.handle(_request("subscriptions_list", command_id="list"))
        row: Mapping[str, object] = cast("list[Mapping[str, object]]", listed.result["subscriptions"])[0]
        assert (row["on_disk"], row["ready"]) == ((1, 1) if present else (0, 0))
        reason: str = _download_reason(owner, "again")
        if present:
            assert (status.state, status.reason, status.set_id) == ("ready", None, "episode-4")
            assert reason == "no_suggestion"
            assert len(owner.state.acquisitions) == 1
            return
        assert (status.state, status.reason, status.admission_id) == (
            "not_ordered",
            "result_missing",
            assignment.admission_id,
        )
        assert reason == "admitted"
        assert len(owner.state.acquisitions) == 2
        assert owner.state.acquisitions[0].assignments[0].replaced
        repeated: EpisodeAssignment = owner.state.acquisitions[1].assignments[0]
        assert repeated.previous_admission_id == assignment.admission_id
        assert repeated.choice.reference.info_hash == "a" * 40
        assert owner.state.ready_groups == (ready,)
        assert _download_reason(owner, "duplicate") == "episode_in_progress"
        assert len(owner.state.acquisitions) == 2


def _listed_counts(owner: AutomationOwner) -> list[tuple[object, object]]:
    listed: ControlResponse = owner.handle(
        _request("subscriptions_list", command_id=f"list-{len(owner.state.requests)}")
    )
    rows: list[Mapping[str, object]] = cast("list[Mapping[str, object]]", listed.result["subscriptions"])
    return [(row["on_disk"], row["ready"]) for row in rows]


def test_a_downloaded_episode_without_a_ready_set_or_a_proven_file_counts_neither_on_disk_nor_ready(
    tmp_path: Path,
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store, inspect_transfers=False) as owner:
        _ready_episode(owner, AcquisitionState.COMPLETE, present=True)
        followed: SubscriptionRecord = SubscriptionRecord(
            "s", _S1, "Slime", "2026-01-01T00:00:00+00:00", 3, paused=True, pause_reason=PauseReason.USER
        )
        assert owner._on_owner(lambda: owner._save(replace(owner.state, subscriptions=(followed,), ready_groups=())))
        groups: tuple[SourceGroup, ...] = owner._service.library_inventory()
        owner._on_owner(lambda: owner._record_ready_inventory(groups))

        assert owner.state.acquisitions[0].complete_files
        assert _listed_counts(owner) == [(0, 0)]


@pytest.mark.parametrize(
    ("left", "expected"),
    [(("Slime - 04.mkv",), (1, 0)), (("Slime - 04.txt", "Slime - 04.pl.srt"), (0, 0))],
)
def test_an_episode_counts_on_disk_by_its_source_video_before_and_after_its_transfer_is_compacted(
    tmp_path: Path, left: tuple[str, ...], expected: tuple[int, int]
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store, inspect_transfers=False) as owner:
        assignment, _ready = _ready_episode(owner, AcquisitionState.COMPLETE, present=False)
        root: Path = owner._service.workspace_root
        (root / "Slime - 04.mkv").write_bytes(b"video")
        index, source, size = assignment.files[0]
        file: PublishedFile = PublishedFile(
            index, source, "Slime - 04.mkv", size, "digest", file_stamp(root / "Slime - 04.mkv")
        )
        published: EpisodeAssignment = replace(
            assignment, group_id=None, publication=EpisodePublication((file,), handed_off=True)
        )
        transfer: AcquisitionConfirmation = replace(owner.state.acquisitions[0], assignments=(published,))
        compacted: AcquisitionConfirmation = compact_acquisition(
            replace(transfer, assignments=(automation_module._retained_episode(published),), cleaned=True)
        )
        (root / "Slime - 04.mkv").unlink()
        for name in left:
            (root / name).write_bytes(b"left")
        group: str | None = automation_module._published_group(frozenset({file.name}))
        sources: tuple[SourceGroup, ...] = tuple(
            item
            for item in owner._service.library_inventory(tuple(root / name for name in left))
            if item.group_id == group
        )
        assert len(sources) == 1
        workspace: InspectedWorkspace = InspectedWorkspace(
            tuple(InspectedSourceGroup(item, item.artifacts, {}, ()) for item in sources), ()
        )
        owner._on_owner(lambda: setattr(owner, "_library", workspace))
        followed: SubscriptionRecord = SubscriptionRecord(
            "s", _S1, "Slime", "2026-01-01T00:00:00+00:00", 3, paused=True, pause_reason=PauseReason.USER
        )
        counts: list[list[tuple[object, object]]] = []
        for item in (transfer, compacted):
            state: WatchState = replace(owner.state, acquisitions=(item,), ready_groups=(), subscriptions=(followed,))
            assert owner._on_owner(partial(owner._save, state))
            counts.append(_listed_counts(owner))

    assert compacted.assignments[0].publication is None
    assert counts == [[expected], [expected]]


def test_the_subscription_list_counts_a_full_library_from_memory_without_reading_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store, inspect_transfers=False) as owner:
        assignment, _ready = _ready_episode(owner, AcquisitionState.COMPLETE, present=True)
        assignments: tuple[EpisodeAssignment, ...] = tuple(
            replace(
                assignment,
                admission_id=f"{series}-{number}",
                choice=replace(assignment.choice, anilist_id=series, number=number),
            )
            for series in range(1, 101)
            for number in range(1, 13)
        )
        records: tuple[SubscriptionRecord, ...] = tuple(
            SubscriptionRecord(
                f"s{series}",
                series,
                "Slime",
                "2026-01-01T00:00:00+00:00",
                13,
                paused=True,
                pause_reason=PauseReason.USER,
            )
            for series in range(1, 101)
        )
        transfer: AcquisitionConfirmation = replace(owner.state.acquisitions[0], assignments=assignments)
        assert owner._on_owner(
            lambda: owner._save(replace(owner.state, acquisitions=(transfer,), subscriptions=records))
        )
        reads: list[str] = []

        def read(kind: str) -> Callable[..., None]:
            return lambda *_args: reads.append(kind)

        monkeypatch.setattr(automation_module, "file_identity", read("identity"))
        monkeypatch.setattr(automation_module, "file_stamp", read("stamp"))
        monkeypatch.setattr(AutomationOwner, "_journal_completed_groups", read("journal"))

        counts: list[tuple[object, object]] = _listed_counts(owner)

    assert counts == [(12, 12)] * 100
    assert reads == []


def test_missing_result_waits_for_its_unfinished_pack_and_reorders_after_it_finishes(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    with _running(service, store, inspect_transfers=False) as owner:
        assignment, _ready = _ready_episode(owner, AcquisitionState.ACCEPTED, present=False)
        held: AcquisitionConfirmation = owner.state.acquisitions[0]
        assert (_episode_state(owner).state, _episode_state(owner).reason) == ("not_ordered", "result_missing")
        assert _download_reason(owner, "while-pack") == "pack_in_progress"
        assert owner.state.acquisitions == (held,)
        finished: AcquisitionConfirmation = replace(held, state=AcquisitionState.COMPLETE, cleaned=True)
        assert owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(finished,))))
        assert _download_reason(owner, "after-pack") == "admitted"
        assert len(owner.state.acquisitions) == 2
        assert owner.state.acquisitions[1].operation_id != held.operation_id
        repeated: EpisodeAssignment = owner.state.acquisitions[1].assignments[0]
        assert repeated.previous_admission_id == assignment.admission_id
        assert repeated.choice.reference.info_hash == "a" * 40


def test_download_batch_does_not_repeat_an_active_order(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(
        _episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json"), inspect_transfers=False
    ) as owner:
        assert _download(owner, (4,), "first").ok
        _until(lambda: _batch(owner, (4,), "first").state == "completed")
        assert _download(owner, (4,), "second").ok
        _until(lambda: _batch(owner, (4,), "second").state == "completed")
        assert _batch(owner, (4,), "second").results[0].reason == "episode_in_progress"
        assert len(owner.state.acquisitions) == 1


def test_source_validation_failure_only_fails_its_episode_and_continues_the_batch(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 5): (_stream(5),)}

    def before(number: int) -> None:
        if number == 4:
            raise ValueError("Invalid source payload")

    streams.before = before
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    with _running(service, WatchStateStore(tmp_path / "state.json")) as owner:
        assert _download(owner, (4, 5)).ok
        _until(lambda: _batch(owner, (4, 5)).state == "completed")
        assert [item.reason for item in _batch(owner, (4, 5)).results] == ["source_failed", "admitted"]


def test_unexpected_batch_failure_preserves_prior_results_and_durably_interrupts_the_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 5): (_stream(5),)}

    def refuse(*args: object, **kwargs: object) -> ControlResponse:
        raise ValueError("Unexpected admission defect")

    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(service, store) as owner:
        monkeypatch.setattr(owner, "_admit_episode", refuse)
        assert _download(owner, (4, 5)).ok
        _until(lambda: _batch(owner, (4, 5)).state == "interrupted")
        batch: EpisodeBatch = _batch(owner, (4, 5))
        assert [item.reason for item in batch.results] == ["no_suggestion"]
    streams.asked.clear()
    with _running(service, store, instance="restarted") as owner:
        assert _batch(owner, (4, 5)).results == batch.results
        assert _batch(owner, (4, 5)).state == "interrupted"
        assert not streams.asked


def test_restart_replays_interrupted_batch_without_resuming_the_remaining_keys(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5, "b"),)}
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    snapshot: list[WatchState] = []
    with _running(service, store) as owner:

        def before(number: int) -> None:
            if number == 5:
                snapshot.append(store.load())

        streams.before = before
        assert _download(owner, (4, 5)).ok
        _until(lambda: _batch(owner, (4, 5)).state == "completed")
    assert len(snapshot[0].acquisitions) == 1
    store.save(snapshot[0])
    streams.asked.clear()
    with _running(service, store, instance="restarted") as restarted:
        batch: EpisodeBatch = _batch(restarted, (4, 5))
        assert batch.state == "interrupted"
        assert len(restarted.state.acquisitions) == 1
        assert not streams.asked
        assert _download(restarted, (5,), "new-batch").ok
        _until(lambda: _batch(restarted, (5,), "new-batch").state == "completed")
        assert len(restarted.state.acquisitions) == 2


def test_legacy_repeat_requires_inspected_conflict_and_keeps_old_transfer_untouched(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    old: AcquisitionConfirmation = _legacy()
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(old,)))
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        assert view.conflict
        assert view.unknown_previous
        assert not _choose(owner, view).ok
        assert _choose(owner, view, confirm=True).ok
        assert owner.state.acquisitions[0] == old
        admitted: EpisodeAssignment = owner.state.acquisitions[1].assignments[0]
        assert admitted.conflict == view.conflict
        assert admitted.previous_admission_id is None
        assert len(streams.asked) == 1
        assert _choose(owner, view, confirm=True).ok
        assert len(owner.state.acquisitions) == 2


@pytest.mark.parametrize("field", ["info_hash", "release_title", "required_files"])
def test_changed_legacy_conflict_invalidates_the_inspected_consent(tmp_path: Path, field: str) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(_legacy(),)))
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        changed: AcquisitionConfirmation = replace(
            _legacy(),
            info_hash="changed" if field == "info_hash" else "old",
            release_title="changed" if field == "release_title" else None,
            nyaa_release_id=1 if field == "release_title" else None,
            required_files=("changed.mkv",) if field == "required_files" else (),
        )
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(changed,))))
        assert _choose(owner, view, confirm=True).reason == "episode_changed"
        assert len(owner.state.acquisitions) == 1


def test_changed_legacy_order_invalidates_repeat_consent_for_the_same_number(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_S1)
    order: EpisodeOrder = EpisodeOrder(Decimal(4), state=EpisodeState.ORDERED, info_hash="old")
    subscription = replace(subscription, taken_episodes=("4",), episodes=(order,), enabled=False)
    SubscriptionStore(library.listing).save((subscription,))
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), library.store) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        changed: WatchState = replace(
            owner.state,
            legacy_orders=tuple(replace(item, reference=f"{item.reference}:new") for item in owner.state.legacy_orders),
        )
        owner._on_owner(lambda: owner._save(changed))
        assert _choose(owner, view, confirm=True).reason == "episode_changed"
        assert not owner.state.acquisitions


def test_a_taken_only_legacy_order_keeps_its_conflict_references_across_an_owner_restart(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = replace(_subscribe(library, anilist_id=_S1), taken_episodes=("4",), enabled=False)
    SubscriptionStore(library.listing).save((subscription,))
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), library.store) as owner:
        first: EpisodeOfferView = _offer(owner, repeat=True)
    with _running(_episode_service(tmp_path, streams=streams), library.store, instance="restarted") as restarted:
        second: EpisodeOfferView = _offer(restarted, repeat=True)
        assert _choose(restarted, second, confirm=True).ok
        admitted: EpisodeAssignment = restarted.state.acquisitions[0].assignments[0]

    assert first.conflict == second.conflict == (f"subscription:{subscription.subscription_id}:4",)
    assert admitted.conflict == second.conflict


def test_an_unscoped_legacy_order_names_only_its_current_confirmation_after_metadata_update_and_restart(
    tmp_path: Path,
) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_S1)
    old: AcquisitionConfirmation = replace(_legacy(), subscription_id=subscription.subscription_id, legacy_scope=None)
    library.store.save(
        migrate(
            WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(old,)),
            (subscription,),
            datetime.now(UTC),
        )
    )
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    changed: AcquisitionConfirmation = replace(old, required_files=("Show - 04.mkv",))
    with _running(_episode_service(tmp_path, streams=streams), library.store) as owner:
        first: EpisodeOfferView = _offer(owner, repeat=True)
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(changed,))))
        updated: EpisodeOfferView = _offer(owner, repeat=True)
    with _running(_episode_service(tmp_path, streams=streams), library.store, instance="restarted") as restarted:
        second: EpisodeOfferView = _offer(restarted, repeat=True)

    assert first.conflict == (legacy_reference(old),)
    assert updated.conflict == second.conflict == (legacy_reference(changed),)


def test_offer_is_session_bound_and_a_late_read_cannot_restore_a_disconnected_offer(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        view: EpisodeOfferView = _offer(owner)
        assert _choose(owner, view, session="other").reason == "offer_expired"
        owner.disconnect("panel")
        response: ControlResponse = owner.handle(
            _request(
                "episode_choose",
                {
                    "offer_id": view.offer_id,
                    "candidate": encode_view(view.offer.candidates[0].stream),
                },
                session_id="new-panel",
                instance_id=view.instance_id,
            )
        )
        assert response.reason == "offer_expired"
        assert not owner.state.acquisitions


def _selective_service(tmp_path: Path, streams: _Streams, network: _SelectiveNetwork) -> AcquisitionService:
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    service._client = cast("TorrentClient", network)
    service._torrent_management = cast("TorrentManagement", network)
    return service


@pytest.mark.parametrize("shared", [True, False])
def test_repeat_removes_only_its_old_pack_scope_before_starting_the_new_transfer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shared: bool,
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5),)}
    network: _SelectiveNetwork = _SelectiveNetwork()
    service: AcquisitionService = _selective_service(tmp_path, streams, network)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    first: StreamCandidate = _stream(4)
    neighbour: StreamCandidate = _stream(5)
    original: tuple[TorrentFile, ...] = (
        TorrentFile(0, first.file_name or "", 400, 0.0, 1),
        TorrentFile(1, neighbour.file_name or "", 400, 0.0, 1),
    )
    with _running(service, store) as owner:
        assert _download(owner, (4, 5) if shared else (4,)).ok
        _until(lambda: bool(network.metadata_added))
        network.deliver("a" * 40, original)
        _until(lambda: network.selected.get("a" * 40) == (frozenset({0, 1}) if shared else frozenset({0})))
        _until(lambda: bool(network.started))
        streams.answers[(41024, 4)] = (first, _stream(4, "b"))
        view: EpisodeOfferView = _offer(owner, repeat=True)
        assert [item.stream.info_hash for item in view.offer.candidates] == ["b" * 40]
        network.stop_ignored = True
        assert _choose(owner, view, confirm=True).ok
        _until(lambda: len(network.metadata_added) == 2)
        network.deliver("b" * 40, (original[0],))
        _until(lambda: network.selected.get("b" * 40) == frozenset({0}))
        assert "b" * 40 not in network.started
        network.stop_ignored = False
        _until(lambda: "b" * 40 in network.started)
        assert network.selected["a" * 40] == (frozenset({1}) if shared else frozenset())
        old: AcquisitionConfirmation = owner.state.acquisitions[0]
        assert old.assignments[0].replaced
        if shared:
            assert not old.assignments[1].replaced
            assert old.assignments[1].files == ((1, neighbour.file_name, 400),)
        assert owner.state.acquisitions[1].assignments[0].previous_admission_id == old.assignments[0].admission_id
        assert network.unapproved_starts == []


def test_manual_file_choice_crosses_ipc_and_refuses_changed_map_then_preserves_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4, uncertain=True),)}
    network: _SelectiveNetwork = _SelectiveNetwork()
    service: AcquisitionService = _selective_service(tmp_path, streams, network)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(service, store) as owner:
        server: ControlServer = ControlServer(
            control_endpoint(tmp_path / "ipc"), b"episode-test-key", owner.handle, on_disconnect=owner.disconnect
        )
        session: ResidentSession = ResidentSession(
            tmp_path, lambda: ControlClient(control_endpoint(tmp_path / "ipc"), b"episode-test-key")
        )
        try:
            assert session.episode_download((EpisodeKey(_S1, 4),), command_id="batch-ipc").state == "accepted"
            _until(lambda: bool(network.metadata_added))
            network.deliver(
                "a" * 40,
                (
                    TorrentFile(0, "pack/unknown.mkv", 400, 0.0, 1),
                    TorrentFile(1, "pack/unknown.ass", 40, 0.0, 1),
                    TorrentFile(2, "pack/another.mkv", 400, 0.0, 1),
                ),
            )
            _until(lambda: owner.state.acquisitions[0].assignments[0].mapped)
            status: EpisodeStatus = session.episode_states(_S1, (4,))[0]
            assert status.reason == "episode_file_unresolved"
            files: EpisodeFiles = session.episode_files(str(status.admission_id))
            assert [item.path for item in files.files] == ["pack/unknown.mkv", "pack/another.mkv"]
            network.per_hash["a" * 40] = tuple(
                replace(item, size=item.size + 1) if item.index == 2 else item for item in network.per_hash["a" * 40]
            )
            with pytest.raises(ControlError, match="file list"):
                session.episode_file_choose(files, files.files[0], command_id="file-choice")
            fresh: EpisodeFiles = session.episode_files(str(status.admission_id))
            accepted: Mapping[str, object] = session.episode_file_choose(
                fresh, fresh.files[0], command_id="fresh-choice"
            )
            assert accepted["admission_id"] == status.admission_id
            assert session.episode_file_choose(fresh, fresh.files[0], command_id="fresh-choice") == accepted
            _until(lambda: network.selected.get("a" * 40) == frozenset({0, 1}))
            _until(lambda: bool(network.started))
            assert owner.state.acquisitions[0].assignments[0].files == (
                (0, "pack/unknown.mkv", 400),
                (1, "pack/unknown.ass", 40),
            )
        finally:
            session.close()
            server.close()


def test_two_sessions_repeating_one_episode_accept_only_the_first_choice(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        assert _download(owner, (4,)).ok
        _until(lambda: _batch(owner, (4,)).state == "completed")
        streams.answers[(41024, 4)] = (_stream(4, "b"),)
        first: EpisodeOfferView = _offer(owner, repeat=True, session="one")
        second: EpisodeOfferView = _offer(owner, repeat=True, session="two")
        gate: threading.Barrier = threading.Barrier(3)
        answers: list[ControlResponse] = []

        def choose(view: EpisodeOfferView, session: str) -> None:
            gate.wait(_TIMEOUT_S)
            answers.append(_choose(owner, view, confirm=True, session=session, command=session))

        workers: list[threading.Thread] = [
            threading.Thread(target=choose, args=(first, "one")),
            threading.Thread(target=choose, args=(second, "two")),
        ]
        for worker in workers:
            worker.start()
        gate.wait(_TIMEOUT_S)
        for worker in workers:
            worker.join(_TIMEOUT_S)
            assert not worker.is_alive()
        assert sum(answer.ok for answer in answers) == 1
        assert [answer.reason for answer in answers if not answer.ok] == ["episode_changed"]
        assert sum(len(item.assignments) for item in owner.state.acquisitions) == 2


def _mapped_transfer(*, replaced: bool = False) -> tuple[AcquisitionConfirmation, tuple[TorrentFile, ...]]:
    files: tuple[TorrentFile, ...] = (TorrentFile(0, "Neko to Ryuu - 04.mkv", 400, 0.0, 1),)
    assignment: EpisodeAssignment = EpisodeAssignment(
        "old-admission",
        datetime.now(UTC).isoformat(),
        AdmissionSource.MANUAL,
        _legacy_choice(4, "a" * 40, anilist_id=_S1),
        file_map=file_map_revision(files),
        files=((0, files[0].name, 400),),
        replaced=replaced,
    )
    transfer: AcquisitionConfirmation = AcquisitionConfirmation(
        "old-transfer",
        "a" * 40,
        "",
        (),
        AcquisitionState.ACCEPTED,
        RequestOrigin.USER,
        None,
        "4",
        datetime.now(UTC).isoformat(),
        assignments=(assignment,),
        selection_revision=1,
        applied_revision=1,
    )
    return transfer, files


@pytest.mark.parametrize("outcome", ["removed", "restored", "cancel", "unconfirmed", "external", "accepted_unseen"])
def test_missing_or_cancelled_episode_releases_only_confirmed_managed_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    current: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    current, files = _mapped_transfer()
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(current, requested_action=None, action_id=None, action_pending=False)
    if outcome == "cancel":
        network.before_action = network.tracked.clear
    if outcome in {"restored", "unconfirmed"}:
        current = replace(current, state=AcquisitionState.UNCERTAIN)
    if outcome == "unconfirmed":
        current = replace(current, applied_revision=0, problem=automation_module._SEND_UNCONFIRMED)
    if outcome == "accepted_unseen":
        current = replace(current, applied_revision=0, content_started=False)
    if outcome == "external":
        monkeypatch.setattr(service, "_torrent_management", None)
    if outcome != "cancel":
        network.tracked.clear()
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    service._stream_source = streams
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(current,)))
    with _running(service, store) as owner:
        if outcome == "cancel":
            assert owner.handle(_request("transfer", {"info_hash": current.info_hash, "action": "cancel"})).ok
        if outcome in {"unconfirmed", "external", "accepted_unseen"}:
            _until(lambda: owner.state.acquisitions[0].state is AcquisitionState.UNCERTAIN)
            assert owner.state.acquisitions[0].problem != "removed_from_client"
            refused: ControlResponse = owner.admit_episode("again", current.assignments[0].choice)
            assert (refused.ok, refused.reason) == (False, "episode_admitted")
            return
        _until(lambda: owner.state.acquisitions[0].state is AcquisitionState.FAILED)
        if outcome != "cancel":
            assert owner.state.acquisitions[0].problem == "removed_from_client"
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        assert decode_view(EpisodeStatus, cast("list[object]", response.result["items"])[0]).state == "not_ordered"
        assert _download(owner, (4,)).ok
        _until(lambda: len(owner.state.acquisitions) == 2)
        assert owner.state.acquisitions[-1].operation_id != current.operation_id
        _until(lambda: len(network.metadata_added) == 1)
        assert current.operation_id not in str(network.metadata_added[0][2])


@pytest.mark.parametrize("confirmed", [False, True])
def test_transient_missing_hash_keeps_acceptance_and_presence_resets_the_removal_budget(
    tmp_path: Path, *, confirmed: bool
) -> None:
    current: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    current, files = _mapped_transfer()
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(
        current,
        applied_revision=int(confirmed),
        content_started=confirmed,
        requested_action=None,
        action_id=None,
        action_pending=False,
    )
    inspector: TransferInspector = TransferInspector(service, tmp_path)
    present: TorrentInfo = network.tracked.pop(current.info_hash)
    for _ in range(2):
        assert inspector.inspect((current,)) == (current,)
        network.tracked[current.info_hash] = present
        current = inspector.inspect((current,))[0]
        assert current.state is AcquisitionState.ACCEPTED
        assert current.problem is None
        network.tracked.clear()
    for _ in range(2):
        assert inspector.inspect((current,)) == (current,)
    terminal: AcquisitionConfirmation = inspector.inspect((current,))[0]
    assert terminal.state is (AcquisitionState.FAILED if confirmed else AcquisitionState.UNCERTAIN)
    assert terminal.problem == ("removed_from_client" if confirmed else None)


@pytest.mark.parametrize("mode", ["legacy_start", "legacy_rename", "selective"])
def test_layout_settlement_waits_for_a_present_hash_despite_cached_files(tmp_path: Path, mode: str) -> None:
    current: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    current, files = _mapped_transfer()
    if mode == "legacy_rename":
        files = tuple(replace(item, name=f"Pack/{item.name}") for item in files)
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(current, requested_action=None, action_id=None, action_pending=False, content_started=False)
    if mode == "selective":
        current = replace(
            current,
            applied_revision=0,
            assignments=tuple(replace(item, files=(), file_map=None) for item in current.assignments),
        )
    else:
        current = replace(
            current,
            assignments=(),
            selection_revision=0,
            applied_revision=0,
            file_layout=((files[0].index, files[0].name, files[0].size),) if mode == "legacy_start" else (),
        )
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(current,)))
    owner: AutomationOwner = AutomationOwner(_real_service(tmp_path, acquisition=service), store, instance_id="test")
    inspector: TransferInspector = TransferInspector(service, tmp_path)
    owner._transfers = inspector
    try:
        current = inspector.inspect((current,))[0]
        owner._state = replace(owner.state, acquisitions=(current,))
        assert inspector.declared(current.info_hash)
        present: TorrentInfo = network.tracked.pop(current.info_hash)
        selections: int = len(network.selections)
        assert inspector.inspect((current,)) == (current,)
        assert owner._settle_layouts(service, (current,), frozenset()) == (current,)
        assert network.started == []
        assert network.renamed == []
        assert len(network.selections) == selections
        assert owner.state.acquisitions == (current,)
        network.tracked[current.info_hash] = present
        current = inspector.inspect((current,))[0]
        owner._state = replace(owner.state, acquisitions=(current,))
        result: AcquisitionConfirmation = owner._settle_layouts(service, (current,), frozenset())[0]
        if mode == "legacy_rename":
            assert network.renamed
            owner._state = replace(owner.state, acquisitions=(result,))
            result = owner._settle_layouts(service, (result,), frozenset())[0]
        assert network.started == [current.info_hash]
        if mode == "selective":
            assert len(network.selections) == selections + 1
        else:
            assert result.content_started
    finally:
        owner._pool.shutdown(wait=True)
        owner._service.close()


def test_manual_file_choice_refuses_a_video_assigned_to_another_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    transfer, files = _mapped_transfer()
    unresolved: EpisodeAssignment = replace(
        transfer.assignments[0],
        admission_id="new-admission",
        choice=_legacy_choice(5, "a" * 40, anilist_id=_S1),
        files=(),
    )
    transfer = replace(transfer, assignments=(*transfer.assignments, unresolved))
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(transfer,)))
    service: AcquisitionService = _episode_service(tmp_path)
    monkeypatch.setattr(service, "transfer_files", lambda _hash: files)
    with _running(service, store, inspect_transfers=False) as owner:
        response: ControlResponse = owner.handle(
            _request(
                "episode_file_choose",
                {
                    "admission_id": unresolved.admission_id,
                    "revision": file_map_revision(files),
                    "file": {"index": 0, "path": files[0].name, "size": 400},
                },
            )
        )
        assert response.reason == "episode_file_taken", response
        assert owner.state.acquisitions == (transfer,)


def test_repeat_offer_excludes_the_hash_of_a_known_legacy_transfer(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4), _stream(4, "b"))}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(acquisitions=(replace(_legacy(), info_hash="a" * 40),)))
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        assert [item.stream.info_hash for item in view.offer.candidates] == ["b" * 40]


def test_mapping_never_reuses_a_video_held_by_a_replaced_assignment(tmp_path: Path) -> None:
    transfer: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    transfer, files = _mapped_transfer(replaced=True)
    fresh: EpisodeAssignment = replace(
        transfer.assignments[0],
        admission_id="new-admission",
        replaced=False,
        files=(),
        file_map=None,
    )
    transfer = replace(transfer, assignments=(*transfer.assignments, fresh))
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(acquisitions=(transfer,)))
    with _running(_episode_service(tmp_path), store) as owner:
        result: AcquisitionConfirmation | None = owner._on_owner(
            lambda: owner._record_mapping(
                transfer,
                file_map_revision(files),
                automation_module._episode_bindings(transfer, files),
                (),
            )
        )
        assert result is not None
        assert result.assignments[1].mapped
        assert result.assignments[1].files == ()
        assert result.assignments[0].files == transfer.assignments[0].files


def test_pausing_automation_keeps_reading_every_episode_of_a_manual_batch(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5),)}
    finished: threading.Event = threading.Event()
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:

        def observe(event: Mapping[str, object], terminal: bool) -> None:
            del terminal
            if event.get("event") == "episode_result":
                assert owner.handle(_request("set_auto", {"enabled": False}, command_id="pause")).ok
            if event.get("event") == "episode_batch":
                finished.set()

        owner.attach_broadcast(observe)
        assert _download(owner, (4, 5)).ok
        assert finished.wait(_TIMEOUT_S)
        batch: EpisodeBatch = _batch(owner, (4, 5))
        assert batch.state == "completed"
        assert [item.key.number for item in batch.results] == [4, 5]
        assert all(item.reason == "admitted" for item in batch.results)
        assert len(streams.asked) == 2


@pytest.mark.parametrize(
    ("state", "problem"),
    [
        (AcquisitionState.PENDING_SEND, None),
        (AcquisitionState.ACCEPTED, automation_module._SELECTION_MISMATCH),
        (AcquisitionState.ACCEPTED, automation_module._METADATA_STOPPED),
    ],
)
def test_repeat_waiting_for_an_unsettled_predecessor_has_an_explicit_episode_reason(
    tmp_path: Path,
    state: AcquisitionState,
    problem: str | None,
) -> None:
    old: AcquisitionConfirmation = replace(_mapped_transfer()[0], state=state, problem=problem)
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4, "b"),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(old,)))
    with _running(_episode_service(tmp_path, streams=streams), store, inspect_transfers=False) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        assert _choose(owner, view, confirm=True).ok
        _until(lambda: owner._active_io == 0)
        owner._on_owner(
            lambda: owner._save(
                replace(
                    owner.state,
                    acquisitions=(replace(owner.state.acquisitions[0], state=state), *owner.state.acquisitions[1:]),
                )
            )
        )
        assert owner.state.acquisitions[0].state is state
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        assert (
            decode_view(EpisodeStatus, cast("list[object]", response.result["items"])[0]).reason
            == "waiting_previous_transfer"
        )
        materials: list[dict[str, object]] = cast(
            "list[dict[str, object]]", owner.handle(_request("status")).result["materials"]
        )
        waiting: dict[str, object] = next(row for row in materials if row.get("reason") == "waiting_previous_transfer")
        assert waiting["problem"] is None


def test_failed_batch_result_save_still_publishes_a_terminal_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),), (41024, 5): (_stream(5),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    save: Callable[[WatchState], None] = store.save
    events: list[Mapping[str, object]] = []

    def fail_result(state: WatchState) -> None:
        if state.acquisitions and any(
            receipt.outcome.get("kind") == "episode_download"
            and decode_view(EpisodeBatch, json.loads(str(receipt.outcome["batch"]))).results
            for receipt in state.command_receipts
        ):
            raise OSError("result save failed")
        save(state)

    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        monkeypatch.setattr(store, "save", fail_result)
        owner.attach_broadcast(lambda event, terminal: events.append(event))
        assert _download(owner, (4, 5)).ok
        _until(lambda: any(event.get("event") == "episode_batch" for event in events))
        event: Mapping[str, object] = next(event for event in events if event.get("event") == "episode_batch")
        batch: EpisodeBatch = decode_view(EpisodeBatch, event["payload"])
        assert batch.state == "interrupted"
        assert batch.results[0].reason == "admitted"
        assert len(store.load().acquisitions) == 1
        assert len(streams.asked) == 1


def test_explicit_uncertain_choice_requires_r04_and_replays_after_lost_response_through_ipc(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4, uncertain=True),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        endpoint: str = control_endpoint(tmp_path / "ipc")
        server: ControlServer = ControlServer(endpoint, b"test-key", owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, b"test-key"))
        try:
            view: EpisodeOfferView = session.episode_offer(EpisodeKey(_S1, 4))
            candidate: StreamCandidate = view.offer.candidates[0].stream
            with pytest.raises(ControlError) as error:
                session.episode_choose(view, candidate, command_id="choose-ipc")
            assert error.value.reason == "deviation_unconfirmed"
            admitted: Mapping[str, object] = session.episode_choose(
                view,
                candidate,
                command_id="choose-ipc",
                deviation_confirmed=True,
            )
            session.close()
            session = ResidentSession(tmp_path, lambda: ControlClient(endpoint, b"test-key"))
            assert (
                session.episode_choose(view, candidate, command_id="choose-ipc", deviation_confirmed=True) == admitted
            )
            assert len(owner.state.acquisitions) == 1
            assert len(streams.asked) == 1
        finally:
            session.close()
            server.close()


def _resume_fixture(
    tmp_path: Path,
    transfer: AcquisitionConfirmation,
    files: tuple[TorrentFile, ...],
) -> tuple[AcquisitionConfirmation, AcquisitionService, _SelectiveNetwork]:
    transfer = replace(
        transfer,
        directory=f"temp/.acquisition/{transfer.operation_id}/data",
        requested_action="resume",
        action_id="resume",
        action_pending=True,
        action_sent=False,
    )
    network: _SelectiveNetwork = _SelectiveNetwork()
    network.tracked[transfer.info_hash] = TorrentInfo(
        "pack",
        transfer.info_hash,
        0.0,
        "stoppedDL",
        str(tmp_path / transfer.directory),
        None,
        400,
    )
    network.per_hash[transfer.info_hash] = files
    network.selected[transfer.info_hash] = transfer.wanted_files
    network.selections.append((transfer.info_hash, transfer.wanted_files))
    return transfer, _selective_service(tmp_path, _Streams(), network), network


def test_resume_waits_until_the_replaced_transfer_scope_is_confirmed(tmp_path: Path) -> None:
    old, files = _mapped_transfer(replaced=True)
    old = replace(old, selection_revision=2)
    assignment: EpisodeAssignment = replace(
        old.assignments[0],
        admission_id="new-admission",
        replaced=False,
        previous_admission_id="old-admission",
        choice=_legacy_choice(4, "b" * 40, anilist_id=_S1),
    )
    current: AcquisitionConfirmation = replace(
        old, operation_id="new-transfer", info_hash="b" * 40, state=AcquisitionState.ACCEPTED, assignments=(assignment,)
    )
    current, service, network = _resume_fixture(tmp_path, current, files)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path), store, inspect_transfers=False) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(old, current))))
        result: AcquisitionConfirmation = owner._resume_selection(service, current)
        assert not result.action_pending
        assert (current.info_hash, "resume") not in network.actions
        assert not network.started


@pytest.mark.parametrize("same_hash", [False, True])
def test_restored_repeat_starts_past_an_uncertain_predecessor_only_for_another_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, same_hash: bool
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    old: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    old, files = _mapped_transfer(replaced=True)
    old = replace(old, state=AcquisitionState.UNCERTAIN, directory="temp/.acquisition/old-transfer/data")
    info_hash: str = old.info_hash if same_hash else "b" * 40
    assignment: EpisodeAssignment = replace(
        old.assignments[0],
        admission_id="new-admission",
        replaced=False,
        previous_admission_id="old-admission",
        choice=_legacy_choice(4, info_hash, anilist_id=_S1),
    )
    current: AcquisitionConfirmation = replace(
        old,
        operation_id="new-transfer",
        info_hash=info_hash,
        state=AcquisitionState.ACCEPTED,
        assignments=(assignment,),
    )
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(current, requested_action=None, action_id=None, action_pending=False)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(old, current)))
    with _running(service, store) as owner:
        if same_hash:
            assert not owner._on_owner(lambda: owner._replacement_ready(current))
            owner._start_selection(service, current)
            assert network.started == []
        else:
            _until(lambda: network.started == [info_hash])
            _until(lambda: owner.state.acquisitions[-1].content_started)


@pytest.mark.parametrize("state", [AcquisitionState.ACCEPTED, AcquisitionState.PENDING_SEND])
def test_stop_refuses_selective_metadata_without_recording_or_sending_an_action(
    tmp_path: Path, state: AcquisitionState
) -> None:
    current: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    current, files = _mapped_transfer()
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(
        current,
        state=state,
        applied_revision=0,
        requested_action=None,
        action_id=None,
        action_pending=False,
    )
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(service, store, inspect_transfers=False) as owner:

        def request_stop() -> None:
            assert owner._save(replace(owner.state, acquisitions=(current,)))
            response: ControlResponse = owner._transfer_command(
                _request("transfer", {"info_hash": current.info_hash, "action": "stop"})
            )
            assert not response.ok
            assert response.code is ControlErrorCode.REFUSED
            assert response.reason == "transfer_metadata_pending"
            assert owner.state.acquisitions == (current,)
            assert store.load().acquisitions == (current,)

        owner._on_owner(request_stop)
        assert network.actions == []


def test_explicit_resume_starts_a_stopped_client_without_pause_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    current: AcquisitionConfirmation
    files: tuple[TorrentFile, ...]
    current, files = _mapped_transfer()
    current, service, network = _resume_fixture(tmp_path, current, files)
    current = replace(current, requested_action=None, action_id=None, action_pending=False, content_started=True)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(current,)))
    with _running(service, store) as owner:
        assert owner.state.pause_owned_transfers == ()
        assert owner.handle(_request("transfer", {"info_hash": current.info_hash, "action": "resume"})).ok
        _until(lambda: (current.info_hash, "resume") in network.actions)
        _until(lambda: network.started == [current.info_hash])


def test_resume_drops_a_scope_changed_during_its_fresh_client_read(tmp_path: Path) -> None:
    current, files = _mapped_transfer()
    current, service, network = _resume_fixture(tmp_path, current, files)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path), store, inspect_transfers=False) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(current,))))

        def change_scope() -> None:
            changed: AcquisitionConfirmation = replace(current, selection_revision=current.selection_revision + 1)
            owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(changed,))))

        network.during_check = change_scope
        owner._resume_selection(service, current)
        assert owner.state.acquisitions[0].selection_revision == 2
        assert (current.info_hash, "resume") not in network.actions
        assert not network.started


def test_metadata_worker_cannot_send_an_admission_replaced_before_it_runs(tmp_path: Path) -> None:
    current: AcquisitionConfirmation = replace(_mapped_transfer(replaced=True)[0], state=AcquisitionState.ADMITTED)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    network: _SelectiveNetwork = _SelectiveNetwork()
    service: AcquisitionService = _selective_service(tmp_path, _Streams(), network)
    with _running(_episode_service(tmp_path), store) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(current,))))
        owner._send_selective(service, current)
        assert not network.metadata_added
        assert owner.state.acquisitions[0].state is AcquisitionState.ADMITTED


@pytest.mark.parametrize("kind", ["episode_offer", "episode_choose", "episode_file_choose"])
def test_malformed_episode_payload_is_invalid_instead_of_internal(tmp_path: Path, kind: str) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store, inspect_transfers=False) as owner:
        view: EpisodeOfferView = _offer(owner)
        current, _files = _mapped_transfer()
        current = replace(current, assignments=(replace(current.assignments[0], files=()),))
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(current,))))
        answer: ControlResponse = owner.handle(
            _request(
                kind,
                {
                    "key": {"anilist_id": "invalid", "number": 4},
                    "offer_id": view.offer_id,
                    "candidate": {},
                    "admission_id": "old-admission",
                    "file": {},
                },
                session_id="panel",
                instance_id=view.instance_id,
            )
        )
        assert not answer.ok
        assert answer.code is ControlErrorCode.INVALID_PAYLOAD


@pytest.mark.parametrize("kind", ["episode_offer", "episode_choose"])
def test_a_migrated_owner_never_reads_the_frozen_subscription_file_for_episode_conflicts(
    tmp_path: Path,
    kind: str,
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    library: _Library = _legacy_library(tmp_path)
    _subscribe(library, anilist_id=_ENTRY)
    with _running(_episode_service(tmp_path, streams=streams), library.store) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(_legacy(),))))
        view: EpisodeOfferView = _offer(owner, repeat=True)
        library.listing.write_text("{broken", encoding="utf-8")
        answer: ControlResponse = owner.handle(
            _request(
                kind,
                {
                    "key": encode_view(EpisodeKey(_S1, 4)),
                    "repeat": True,
                    "offer_id": view.offer_id,
                    "candidate": encode_view(view.offer.candidates[0].stream),
                    "conflict_confirmed": True,
                },
                session_id="panel",
                instance_id=view.instance_id,
            )
        )
        assert answer.ok, answer
        assert answer.reason != EpisodeReason.LEGACY_UNREADABLE


def test_file_choice_accepts_a_timestamp_only_change_during_the_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, files = _mapped_transfer()
    current = replace(current, assignments=(replace(current.assignments[0], files=()),))
    service: AcquisitionService = _episode_service(tmp_path)
    with _running(service, WatchStateStore(tmp_path / "state.json"), inspect_transfers=False) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(current,))))

        def read_files(_hash: str) -> tuple[TorrentFile, ...]:
            changed: AcquisitionConfirmation = replace(current, updated_at="2030-01-01T00:00:00+00:00")
            owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(changed,))))
            return files

        monkeypatch.setattr(service, "transfer_files", read_files)
        answer: ControlResponse = owner.handle(
            _request(
                "episode_file_choose",
                {
                    "admission_id": "old-admission",
                    "revision": file_map_revision(files),
                    "file": {"index": 0, "path": files[0].name, "size": 400},
                },
            )
        )
        assert answer.ok, answer
        assert owner.state.acquisitions[0].assignments[0].files == ((0, files[0].name, 400),)


def test_offer_finishing_after_disconnect_cannot_be_accepted(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    entered: threading.Event = threading.Event()
    released: threading.Event = threading.Event()
    answers: list[ControlResponse] = []

    def before(_number: int) -> None:
        entered.set()
        assert released.wait(_TIMEOUT_S)

    streams.before = before
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        worker: threading.Thread = threading.Thread(
            target=lambda: answers.append(
                owner.handle(
                    _request(
                        "episode_offer",
                        {"key": encode_view(EpisodeKey(_S1, 4))},
                        session_id="panel",
                    )
                )
            )
        )
        worker.start()
        try:
            assert entered.wait(_TIMEOUT_S)
            owner.disconnect("panel")
            owner.handle(_request("status"))
        finally:
            released.set()
            worker.join(_TIMEOUT_S)
        assert not worker.is_alive()
        assert answers[0].reason == "offer_expired"
        assert not owner.state.acquisitions


def test_taken_conflict_repeat_preserves_subscription_bytes_and_only_overrides_one_number(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    SubscriptionStore(library.listing).save((replace(subscription, taken_episodes=("3", "4"), enabled=False),))
    before: bytes = library.listing.read_bytes()
    service: AcquisitionService = _episode_service(tmp_path)
    store: WatchStateStore = library.store
    app: AppService = _real_service(tmp_path, acquisition=service)
    owner: AutomationOwner = AutomationOwner(app, store, instance_id="test-instance")
    thread: threading.Thread = _serving(owner)
    try:
        state: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _ENTRY, "numbers": [3, 4, 5]}))
        rows: object = state.result["items"]
        assert isinstance(rows, list)
        assert [decode_view(EpisodeStatus, item).state for item in rows] == [
            "possibly_admitted",
            "possibly_admitted",
            "not_ordered",
        ]
        conflict: tuple[str, ...] = owner._on_owner(lambda: owner._episode_conflicts(EpisodeKey(_ENTRY, 3)))
        assert conflict == (f"subscription:{subscription.subscription_id}:3",)
        response: ControlResponse = owner._on_owner(
            lambda: owner._admit_episode("override", _legacy_choice(3), conflict=conflict)
        )
        assert response.ok
        state = owner.handle(_request("episode_states", {"anilist_id": _ENTRY, "numbers": [3, 4]}))
        rows = state.result["items"]
        assert isinstance(rows, list)
        assert [decode_view(EpisodeStatus, item).state for item in rows] == ["ordered", "possibly_admitted"]
        assert library.listing.read_bytes() == before
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def test_repeat_keeps_an_alternative_file_of_the_same_pack_and_excludes_index_only_aliases(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    original: StreamCandidate = _stream(4)
    streams.answers = {(41024, 4): (original,)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        assert _download(owner, (4,)).ok
        _until(lambda: _batch(owner, (4,)).state == "completed")
        alternative: StreamCandidate = replace(original, file_name="different-video.mkv", file_index=7)
        streams.answers[(41024, 4)] = (replace(original, file_index=99), alternative)
        view: EpisodeOfferView = _offer(owner, repeat=True)
        assert tuple(item.stream for item in view.offer.candidates) == (alternative,)
        assert view.unknown_previous
        assert _choose(owner, view, confirm=True).ok
        assert len(owner.state.acquisitions) == 1
        assert len(owner.state.acquisitions[0].assignments) == 2
        assert owner.state.acquisitions[0].assignments[0].replaced


def test_download_batch_repeat_admits_another_file_of_the_previous_pack(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    original: StreamCandidate = _stream(4)
    streams.answers = {(41024, 4): (original,)}
    with _running(
        _episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json"), inspect_transfers=False
    ) as owner:
        assert _download(owner, (4,), "original").ok
        _until(lambda: _batch(owner, (4,), "original").state == "completed")
        old: AcquisitionConfirmation = owner.state.acquisitions[0]
        filename: str = str(original.file_name)
        assignment: EpisodeAssignment = replace(old.assignments[0], files=((0, filename, 123),), file_map="revision")
        complete: AcquisitionConfirmation = replace(
            old,
            state=AcquisitionState.COMPLETE,
            assignments=(assignment,),
            required_files=(filename,),
            complete_files=(filename,),
        )
        assert owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(complete,))))
        alternative: StreamCandidate = replace(
            original, file_name="[Group] Tensei shitara Slime Datta Ken - 04v2 [1080p].mkv", file_index=7
        )
        streams.answers[(41024, 4)] = (original, alternative)
        assert _download(owner, (4,), "repeat").ok
        _until(lambda: _batch(owner, (4,), "repeat").state == "completed")
        assert [result.reason for result in _batch(owner, (4,), "repeat").results] == ["admitted"]
        repeated: EpisodeAssignment = owner.state.acquisitions[-1].assignments[-1]
        assert repeated.choice.reference.file_name == alternative.file_name


def test_batch_cannot_automatically_admit_a_mismatched_release(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    wrong: StreamCandidate = replace(
        _stream(4),
        file_name="Tensei shitara Slime Datta Ken - 04-trailer.mkv",
        release="Tensei shitara Slime Datta Ken - 04",
    )
    streams.answers = {(41024, 4): (wrong,)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        view: EpisodeOfferView = _offer(owner)
        assert view.offer.candidates[0].identity.verdict is IdentityVerdict.MISMATCH
        assert _download(owner, (4,)).ok
        _until(lambda: _batch(owner, (4,)).state == "completed")
        assert _batch(owner, (4,)).results[0].reason == "no_suggestion"
        assert not owner.state.acquisitions


def test_failed_batch_receipt_save_prevents_all_source_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    streams: _Streams = _Streams()
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:

        def refuse(_state: WatchState) -> None:
            raise OSError("state unavailable")

        monkeypatch.setattr(store, "save", refuse)
        assert not _download(owner, (4,)).ok
        assert not owner.state.command_receipts
        assert not streams.asked


def test_batch_recovery_finds_admission_saved_before_its_result(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    service: AcquisitionService = _episode_service(tmp_path, streams=streams)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    snapshots: list[WatchState] = []
    with _running(service, store) as owner:
        owner.attach_broadcast(
            lambda event, terminal: (
                snapshots.append(store.load())
                if event.get("event") == "state_changed" and owner.state.acquisitions
                else None
            )
        )
        assert _download(owner, (4,)).ok
        _until(lambda: _batch(owner, (4,)).state == "completed")
    assert snapshots
    store.save(snapshots[0])
    streams.asked.clear()
    with _running(service, store, instance="restarted") as owner:
        batch: EpisodeBatch = _batch(owner, (4,))
        assert batch.state == "interrupted"
        assert len(batch.results) == 1
        assert batch.results[0].admission_id == snapshots[0].acquisitions[0].assignments[0].admission_id
        assert not streams.asked


def test_interrupting_episode_interaction_invalidates_its_offer_without_blocking_control(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        endpoint: str = control_endpoint(tmp_path / "ipc")
        server: ControlServer = ControlServer(endpoint, b"test-key", owner.handle, on_disconnect=owner.disconnect)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, b"test-key"))
        try:
            view: EpisodeOfferView = session.episode_offer(EpisodeKey(_S1, 4))
            session.interrupt_reads()
            assert session.episode_states(_S1, (4,))[0].state == "not_ordered"
            with pytest.raises(ControlError) as error:
                session.episode_choose(view, view.offer.candidates[0].stream, command_id="expired")
            assert error.value.reason == "offer_expired"
            assert not owner.state.acquisitions
        finally:
            session.close()
            server.close()
