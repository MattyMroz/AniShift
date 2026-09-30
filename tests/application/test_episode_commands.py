from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from test_acquisition import _S1, _episode_service, _slime_titles, _StreamSource, _TitleCatalog
from test_automation import _TIMEOUT_S, _real_service, _request, _serving
from test_episode_admission import _ENTRY, _Library, _subscribe
from test_episode_admission import _choice as _legacy_choice
from test_episode_admission import _library as _legacy_library
from test_selective_lifecycle import _SelectiveNetwork, _until

from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.artifacts import create_group_id
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    AutomationPolicy,
    EpisodeAssignment,
    LegacyScope,
    ReadyGroup,
    WatchState,
)
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_commands import EpisodeBatch, EpisodeFiles, EpisodeOfferView, EpisodeStatus
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import EpisodeKey, StreamCandidate
from anishift.application.intents import RequestOrigin
from anishift.application.service import AppService
from anishift.application.subscriptions import EpisodeOrder, EpisodeState, Subscription, SubscriptionService
from anishift.application.transfers import file_map_revision
from anishift.application.watch_state import WatchStateStore
from anishift.application.workflows import WorkflowTarget
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlResponse,
    ControlServer,
    control_endpoint,
)
from anishift.services.catalog.types import SeasonAiring, TitleStatus
from anishift.services.torrents import TorrentFile, TorrentInfo


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
    subscriptions: SubscriptionService | None = None,
    inspect_transfers: bool = True,
) -> Iterator[AutomationOwner]:
    titles: _TitleCatalog = _slime_titles()
    titles.schedules[_S1] = SeasonAiring(_S1, TitleStatus.FINISHED, 24, ())
    service._title_catalog = titles
    owner: AutomationOwner = AutomationOwner(
        _real_service(service._workspace_root, acquisition=service, subscriptions=subscriptions),
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
        response: ControlResponse = owner.handle(_request("episode_states", {"anilist_id": _S1, "numbers": [4]}))
        states: tuple[EpisodeStatus, ...] = decode_view(tuple[EpisodeStatus, ...], response.result["items"])
        assert states[0].state == "ready"
        assert states[0].set_id == group_id


def test_legacy_order_without_transfer_remains_possibly_admitted(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    library.subscriptions._store.save(
        (replace(subscription, enabled=False, episodes=(EpisodeOrder(Decimal(3), state=EpisodeState.ORDERED),)),)
    )
    with _running(_episode_service(tmp_path), library.store, subscriptions=library.subscriptions) as owner:
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
        monkeypatch.setattr(owner, "admit_episode", refuse)
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


def test_changed_subscription_order_invalidates_repeat_consent_for_the_same_number(tmp_path: Path) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_S1)
    order: EpisodeOrder = EpisodeOrder(Decimal(4), state=EpisodeState.ORDERED, info_hash="old")
    subscription = replace(subscription, taken_episodes=("4",), episodes=(order,), enabled=False)
    library.subscriptions._store.save((subscription,))
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(
        _episode_service(tmp_path, streams=streams), library.store, subscriptions=library.subscriptions
    ) as owner:
        view: EpisodeOfferView = _offer(owner, repeat=True)
        library.subscriptions._store.save((replace(subscription, episodes=(replace(order, info_hash="new"),)),))
        assert _choose(owner, view, confirm=True).reason == "episode_changed"
        assert not owner.state.acquisitions


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


def test_pausing_a_batch_stops_before_reading_its_next_episode(tmp_path: Path) -> None:
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
        assert batch.state == "interrupted"
        assert [item.key.number for item in batch.results] == [4]
        assert len(streams.asked) == 1


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
def test_unreadable_episode_conflict_is_invalid_instead_of_internal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    library: _Library = _legacy_library(tmp_path)
    with _running(
        _episode_service(tmp_path, streams=streams), library.store, subscriptions=library.subscriptions
    ) as owner:
        owner._on_owner(lambda: owner._save(replace(owner.state, acquisitions=(_legacy(),))))
        view: EpisodeOfferView = _offer(owner, repeat=True)

        def unreadable() -> list[Subscription]:
            raise ValueError("unreadable subscriptions")

        original: Callable[[], tuple[Subscription, ...]] = library.subscriptions.list
        monkeypatch.setattr(library.subscriptions, "list", unreadable)
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
        monkeypatch.setattr(library.subscriptions, "list", original)
        assert not answer.ok
        assert answer.code is ControlErrorCode.INVALID_PAYLOAD


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
    library.subscriptions._store.save((replace(subscription, taken_episodes=("3", "4"), enabled=False),))
    before: bytes = library.listing.read_bytes()
    service: AcquisitionService = _episode_service(tmp_path)
    store: WatchStateStore = library.store
    app: AppService = _real_service(tmp_path, acquisition=service, subscriptions=library.subscriptions)
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


def test_subscription_repeat_of_a_keyed_order_requires_episode_preview_without_mutating_subscription(
    tmp_path: Path,
) -> None:
    library: _Library = _legacy_library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    library.subscriptions._store.save((replace(subscription, enabled=False),))
    owner: AutomationOwner = AutomationOwner(library.service, library.store, instance_id="test-instance")
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.admit_episode("old", _legacy_choice(3)).ok
        before: bytes = library.listing.read_bytes()
        response: ControlResponse = owner.handle(
            _request(
                "subscription_repeat",
                {
                    "subscription_id": subscription.subscription_id,
                    "episodes": [str(Decimal(3))],
                },
            )
        )
        assert response.reason == "episode_repeat_required"
        assert library.listing.read_bytes() == before
        assert not library.network.added
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
