from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from test_acquisition import _TitleCatalog
from test_automation import (
    _TIMEOUT_S,
    _accepted_transfer,
    _owner,
    _real_service,
    _request,
    _serving,
    _TorrentNetwork,
)

from anishift.application.acquisition import (
    AcquisitionService,
    ReleaseChoice,
    SeasonContext,
    TorrentClient,
    TorrentManagement,
    catalog_releases,
    read_episode,
)
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    EpisodeChoice,
    LegacyScope,
    TorrentioReference,
    WatchState,
)
from anishift.application.control_views import encode_view
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.intents import RequestOrigin
from anishift.application.service import AppService
from anishift.application.subscription_migration import migrate
from anishift.application.subscriptions import Subscription, SubscriptionStore
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlResponse,
    ControlServer,
    control_endpoint,
)
from anishift.services.catalog.types import EpisodeAiring, SeasonAiring, TitleStatus
from anishift.services.torrents import Release, ReleaseName, TorrentFile, TorrentInfo, parse_release_name

_ENTRY: int = 500

_OTHER_ENTRY: int = 501

_SEASON: SeasonContext = SeasonContext(index=2, offset=24, episodes=12)


@dataclass
class _Library:
    service: AppService
    store: WatchStateStore
    network: _TorrentNetwork
    listing: Path


def _release(number: int, info_hash: str | None = None) -> Release:
    return Release(
        title=f"[SubsPlease] Neko to Ryuu - {number:02d} (1080p)",
        torrent_url=f"https://example.test/{number}.torrent",
        info_hash=info_hash or f"g{number}",
        seeders=10,
        size_text="1 GiB",
        published=None,
        subtitle_language="en",
    )


def _aired() -> SeasonAiring:
    aired: datetime = datetime.now(UTC) - timedelta(hours=4)
    return SeasonAiring(
        _ENTRY, TitleStatus.FINISHED, 12, tuple(EpisodeAiring(number, aired) for number in range(1, 13))
    )


def _library(tmp_path: Path, *releases: Release, managed: bool = False) -> _Library:
    network: _TorrentNetwork = _TorrentNetwork()
    network.releases = releases
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
        title_catalog=_TitleCatalog(schedules={_ENTRY: _aired()}),
        torrent_management=cast("TorrentManagement", network) if managed else None,
    )
    listing: Path = tmp_path / "subscriptions.json"
    return _Library(
        _real_service(tmp_path, acquisition=acquisition),
        WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME, subscriptions_path=listing),
        network,
        listing,
    )


@contextmanager
def _running(library: _Library) -> Iterator[AutomationOwner]:
    owner: AutomationOwner = _owner(library.service, library.store)
    thread: threading.Thread = _serving(owner)
    try:
        yield owner
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def _choice(number: int, info_hash: str | None = None, *, anilist_id: int = _ENTRY) -> EpisodeChoice:
    return EpisodeChoice(
        anilist_id=anilist_id,
        number=number,
        reference=TorrentioReference(info_hash or f"t{anilist_id}-{number}", 0, f"Neko to Ryuu - {number:02d}.mkv"),
        target={"local_episode": number},
        verdict=IdentityVerdict.MATCH,
        reason="Specific work title and local episode match",
    )


def _selection(release: Release, context: SeasonContext | None = None) -> ReleaseChoice:
    name: ReleaseName = parse_release_name(release.title)
    return ReleaseChoice(release, name, None if context is None else read_episode(name, context))


def _download(
    owner: AutomationOwner,
    choice: ReleaseChoice,
    *,
    command_id: str,
    anilist_id: int | None = _ENTRY,
    offset: int | None = 0,
) -> ControlResponse:
    payload: dict[str, object] = {"choices": [encode_view(choice)]}
    if offset is not None:
        payload["episode_offset"] = offset
    if anilist_id is not None:
        payload["anilist_id"] = anilist_id
    return owner.handle(_request("download", payload, command_id=command_id))


def _subscribe(library: _Library, *, anilist_id: int | None, first: int = 3) -> Subscription:
    subscription: Subscription = Subscription(
        subscription_id="neko-subsplease",
        query="neko",
        series="Neko to Ryuu",
        group="SubsPlease",
        next_episode=Decimal(first),
        min_resolution=1080,
        taken=frozenset(),
        added_at="2026-09-01T12:00:00+00:00",
        checked_at=None,
        season_index=_SEASON.index,
        episode_offset=_SEASON.offset,
        season_episodes=_SEASON.episodes,
        anilist_id=anilist_id,
    )
    SubscriptionStore(library.listing).save([subscription])
    return subscription


def _admitted(store: WatchStateStore) -> list[tuple[int, int]]:
    return [
        (item.choice.anilist_id, item.choice.number)
        for acquisition in store.load().acquisitions
        for item in acquisition.assignments
    ]


def test_an_admission_saves_the_assignment_with_its_receipt_and_touches_no_client(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    saves: list[WatchState] = []
    save: Callable[[WatchState], None] = library.store.save

    def recording(state: WatchState) -> None:
        saves.append(state)
        save(state)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(library.store, "save", recording)
        with _running(library) as owner:
            answer: ControlResponse = owner.admit_episode("admit-1", _choice(3))

    assert answer.ok, answer.message
    assert answer.result["anilist_id"] == _ENTRY
    assert answer.result["number"] == 3
    admissions: list[WatchState] = [state for state in saves if state.acquisitions]
    assert len(admissions) == 1
    recorded: AcquisitionConfirmation = admissions[0].acquisitions[0]
    assert recorded.state is AcquisitionState.ADMITTED
    assert recorded.selective
    assert recorded.assignments[0].admission_id == answer.result["admission_id"]
    assert [item.command_id for item in admissions[0].command_receipts] == ["admit-1"]
    assert library.store.load().acquisitions == (recorded,)
    assert library.network.added == []
    assert library.network.info_calls == 0


def test_a_repeated_command_replays_its_admission_and_refuses_another_episode(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    with _running(library) as owner:
        first: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        replay: ControlResponse = owner.admit_episode("admit-1", _choice(3, "another-stream"))
        reused: ControlResponse = owner.admit_episode("admit-1", _choice(4))

    assert first.ok
    assert replay.ok
    assert replay.result == first.result
    assert not reused.ok
    assert reused.reason == "command_reused"
    assert _admitted(library.store) == [(_ENTRY, 3)]


def test_one_episode_is_admitted_once_whatever_stream_while_its_neighbour_still_passes(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    with _running(library) as owner:
        first: ControlResponse = owner.admit_episode("admit-1", _choice(3, "first-stream"))
        duplicate: ControlResponse = owner.admit_episode("admit-2", _choice(3, "second-stream"))
        same_stream: ControlResponse = owner.admit_episode("admit-3", _choice(4, "first-stream"))
        repeated: ControlResponse = owner.admit_episode("admit-4", _choice(4, "third-stream"))
        neighbour: ControlResponse = owner.admit_episode("admit-5", _choice(5, "third-stream"))
        other_entry: ControlResponse = owner.admit_episode("admit-6", _choice(3, anilist_id=_OTHER_ENTRY))

    assert (duplicate.ok, duplicate.reason) == (False, "episode_admitted")
    assert same_stream.ok
    assert same_stream.result["operation_id"] == first.result["operation_id"]
    assert (repeated.ok, repeated.reason) == (False, "episode_admitted")
    assert neighbour.ok
    assert other_entry.ok
    assert _admitted(library.store) == [(_ENTRY, 3), (_ENTRY, 4), (_ENTRY, 5), (_OTHER_ENTRY, 3)]
    assert [len(item.assignments) for item in library.store.load().acquisitions] == [2, 1, 1]


def test_two_clients_admitting_one_episode_at_once_create_one_admission(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    answers: list[ControlResponse] = []
    start: threading.Barrier = threading.Barrier(2)

    def admit(command_id: str, info_hash: str, owner: AutomationOwner) -> None:
        start.wait(_TIMEOUT_S)
        answers.append(owner.admit_episode(command_id, _choice(3, info_hash)))

    with _running(library) as owner:
        clients: list[threading.Thread] = [
            threading.Thread(target=admit, args=(f"panel-{index}", f"stream-{index}", owner)) for index in (1, 2)
        ]
        for client in clients:
            client.start()
        for client in clients:
            client.join(_TIMEOUT_S)

    assert sorted(answer.ok for answer in answers) == [False, True]
    assert {answer.reason for answer in answers if not answer.ok} == {"episode_admitted"}
    assert _admitted(library.store) == [(_ENTRY, 3)]


def test_an_admission_that_cannot_be_saved_leaves_nothing_and_can_be_repeated(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)

    def failing(state: WatchState) -> None:
        del state
        raise OSError("Injected write failure")

    with _running(library) as owner:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(library.store, "save", failing)
            failed: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        status: object = owner.handle(_request("status", command_id="status")).result["acquisitions"]
        retried: ControlResponse = owner.admit_episode("admit-1", _choice(3))

    assert failed.code is ControlErrorCode.INTERNAL
    assert status == []
    assert retried.ok
    assert _admitted(library.store) == [(_ENTRY, 3)]


@pytest.mark.parametrize("loss", ["restart", "library_file", "history"])
def test_an_admission_still_refuses_its_episode_after_restart_file_removal_or_history_loss(
    tmp_path: Path, loss: str
) -> None:
    library: _Library = _library(tmp_path)
    video: Path = tmp_path / "Neko to Ryuu - 03.mkv"
    video.write_bytes(b"video")
    with _running(library) as owner:
        first: ControlResponse = owner.admit_episode("admit-1", _choice(3))
    assert first.ok
    if loss == "library_file":
        video.unlink()
    if loss == "history":
        assert library.store.history_path().is_file()
        library.store.history_path().unlink()

    with _running(library) as owner:
        again: ControlResponse = owner.admit_episode("admit-2", _choice(3, "later-stream"))
        replay: ControlResponse = owner.admit_episode("admit-1", _choice(3))

    assert (again.ok, again.reason) == (False, "episode_admitted")
    assert replay.result == first.result
    assert _admitted(library.store) == [(_ENTRY, 3)]


@pytest.mark.parametrize(("printed", "offset"), [(27, 24), (3, 0)], ids=["offset-24", "offset-0"])
def test_a_legacy_download_after_the_gate_adds_nothing_for_the_admitted_episode(
    tmp_path: Path, printed: int, offset: int
) -> None:
    library: _Library = _library(tmp_path, _release(printed))
    with _running(library) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        blocked: ControlResponse = _download(
            owner, _selection(_release(printed)), command_id="download-1", offset=offset
        )

    assert not blocked.ok
    assert blocked.reason == "episode_admitted"
    assert library.network.added == []
    assert len(library.store.load().acquisitions) == 1


@pytest.mark.parametrize(
    ("printed", "context", "offset"),
    [(27, None, 24), (27, _SEASON, 24), (3, None, 0)],
    ids=["raw-offset-24", "season-read-offset-24", "offset-0"],
)
def test_the_gate_after_a_legacy_download_refuses_only_the_possibly_ordered_episode(
    tmp_path: Path, printed: int, context: SeasonContext | None, offset: int
) -> None:
    library: _Library = _library(tmp_path, _release(printed))
    with _running(library) as owner:
        assert _download(owner, _selection(_release(printed), context), command_id="download-1", offset=offset).ok
        same: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        neighbour: ControlResponse = owner.admit_episode("admit-2", _choice(4))

    assert library.network.added == [f"g{printed}"]
    assert (same.ok, same.reason) == (False, "episode_possibly_admitted")
    assert neighbour.ok
    scopes: list[LegacyScope | None] = [item.legacy_scope for item in library.store.load().acquisitions]
    assert scopes[0] == LegacyScope(_ENTRY, 3)


def test_a_legacy_download_without_a_valid_local_number_holds_its_whole_entry(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path, _release(3))
    with _running(library) as owner:
        assert _download(owner, _selection(_release(3)), command_id="download-1", offset=24).ok
        entry: ControlResponse = owner.admit_episode("admit-1", _choice(7))
        other_entry: ControlResponse = owner.admit_episode("admit-2", _choice(7, anilist_id=_OTHER_ENTRY))

    assert (entry.ok, entry.reason) == (False, "episode_possibly_admitted")
    assert other_entry.ok
    assert library.store.load().acquisitions[0].legacy_scope == LegacyScope(_ENTRY, None)


@pytest.mark.parametrize("anilist_id", [_OTHER_ENTRY, None], ids=["other-entry", "no-entry"])
def test_a_legacy_download_of_another_or_no_entry_is_not_blocked_by_the_gate(
    tmp_path: Path, anilist_id: int | None
) -> None:
    library: _Library = _library(tmp_path, _release(3))
    with _running(library) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        answer: ControlResponse = _download(owner, _selection(_release(3)), command_id="d-1", anilist_id=anilist_id)

    assert answer.ok, answer.message
    assert library.network.added == ["g3"]


def test_a_legacy_download_of_the_admitted_stream_is_deduplicated_without_any_entry(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path, _release(3, "t500-3"))
    with _running(library) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        answer: ControlResponse = _download(
            owner, _selection(_release(3, "t500-3")), command_id="download-1", anilist_id=None
        )

    assert not answer.ok
    assert library.network.added == []


@pytest.mark.parametrize(
    ("taken", "blocked", "passing"),
    [(("3",), 3, 4), (("7.5",), 9, None)],
    ids=["local-number", "fractional-number"],
)
def test_taken_episodes_of_a_linked_subscription_are_read_without_becoming_transfers(
    tmp_path: Path, taken: tuple[str, ...], blocked: int, passing: int | None
) -> None:
    library: _Library = _library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    SubscriptionStore(library.listing).save([replace(subscription, taken_episodes=taken)])
    listing: bytes = library.listing.read_bytes()
    with _running(library) as owner:
        refused: ControlResponse = owner.admit_episode("admit-1", _choice(blocked))
        other_entry: ControlResponse = owner.admit_episode("admit-2", _choice(blocked, anilist_id=_OTHER_ENTRY))
        neighbour: ControlResponse | None = (
            None if passing is None else owner.admit_episode("admit-3", _choice(passing))
        )

    assert (refused.ok, refused.reason) == (False, "episode_possibly_admitted")
    assert other_entry.ok
    assert neighbour is None or neighbour.ok
    assert library.listing.read_bytes() == listing
    assert all(item.selective for item in library.store.load().acquisitions)
    assert library.network.added == []
    assert library.network.info_calls == 0


def test_taken_episodes_of_an_unlinked_subscription_block_no_entry(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=None)
    SubscriptionStore(library.listing).save([replace(subscription, taken_episodes=("3",))])
    with _running(library) as owner:
        answer: ControlResponse = owner.admit_episode("admit-1", _choice(3))

    assert answer.ok


def test_an_older_subscription_order_is_scoped_through_its_subscription_at_the_gate(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path)
    subscription: Subscription = _subscribe(library, anilist_id=_ENTRY)
    older: AcquisitionConfirmation = AcquisitionConfirmation(
        operation_id="older",
        info_hash="older-hash",
        directory="",
        required_files=(),
        state=AcquisitionState.ACCEPTED,
        origin=RequestOrigin.USER,
        subscription_id=subscription.subscription_id,
        episode="5",
        updated_at="2026-09-08T12:00:00+00:00",
    )
    library.store.save(
        migrate(
            WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(older,)),
            (subscription,),
            datetime(2026, 9, 9, tzinfo=UTC),
        )
    )
    with _running(library) as owner:
        answer: ControlResponse = owner.admit_episode("admit-1", _choice(5))

    assert (answer.ok, answer.reason) == (False, "episode_possibly_admitted")
    assert len(library.store.load().acquisitions) == 1


@contextmanager
def _resident(library: _Library, owner: AutomationOwner) -> Iterator[ResidentSession]:
    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(library.store.history_path().parent)
    server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
    session: ResidentSession = ResidentSession(
        library.store.history_path().parent, lambda: ControlClient(endpoint, key)
    )
    try:
        yield session
    finally:
        session.close()
        server.close()


def test_a_panel_download_through_the_resident_channel_is_held_by_the_admitted_episode(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path, _release(27))
    with _running(library) as owner, _resident(library, owner) as session:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        with pytest.raises(ControlError) as refusal:
            session.download((_selection(_release(27)),), anilist_id=_ENTRY, episode_offset=24)

    assert refusal.value.reason == "episode_admitted"
    assert library.network.added == []


@pytest.mark.parametrize(("offset", "scope"), [(24, LegacyScope(_ENTRY, 3)), (None, LegacyScope(_ENTRY, None))])
def test_a_panel_download_through_the_resident_channel_records_its_entry_scope(
    tmp_path: Path, offset: int | None, scope: LegacyScope
) -> None:
    library: _Library = _library(tmp_path, _release(27))
    with _running(library) as owner, _resident(library, owner) as session:
        assert session.download((_selection(_release(27)),), anilist_id=_ENTRY, episode_offset=offset).count == 1
        same: ControlResponse = owner.admit_episode("admit-1", _choice(3))

    assert (same.ok, same.reason) == (False, "episode_possibly_admitted")
    assert [item.legacy_scope for item in library.store.load().acquisitions] == [scope]


def test_a_legacy_download_without_a_known_offset_holds_its_whole_entry(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path, _release(27))
    with _running(library) as owner:
        assert _download(owner, _selection(_release(27)), command_id="download-1", offset=None).ok
        other: ControlResponse = owner.admit_episode("admit-1", _choice(9))

    assert (other.ok, other.reason) == (False, "episode_possibly_admitted")


def _unnumbered_listing(release: Release) -> ReleaseChoice:
    return catalog_releases((release,), parse_release_name, context=None).groups[0].choices[0]


@pytest.mark.parametrize("admitted_first", [True, False], ids=["gate-then-g", "g-then-gate"])
def test_a_panel_download_read_without_season_numbering_holds_the_whole_entry(
    tmp_path: Path, admitted_first: bool
) -> None:
    library: _Library = _library(tmp_path, _release(27))
    choice: ReleaseChoice = _unnumbered_listing(_release(27))
    assert choice.reading is not None
    with _running(library) as owner, _resident(library, owner) as session:
        if admitted_first:
            assert owner.admit_episode("admit-1", _choice(3)).ok
            with pytest.raises(ControlError) as refusal:
                session.download((choice,), anilist_id=_ENTRY)
            assert refusal.value.reason == "episode_admitted"
        else:
            assert session.download((choice,), anilist_id=_ENTRY).count == 1
            same: ControlResponse = owner.admit_episode("admit-1", _choice(3))
            assert (same.ok, same.reason) == (False, "episode_possibly_admitted")

    assert library.network.added == ([] if admitted_first else ["g27"])
    legacy: list[LegacyScope | None] = [
        item.legacy_scope for item in library.store.load().acquisitions if not item.selective
    ]
    assert legacy == ([] if admitted_first else [LegacyScope(_ENTRY, None)])


@pytest.mark.parametrize("action", ["resume", "stop", "cancel"])
@pytest.mark.parametrize("restart", [False, True], ids=["running", "restarted"])
def test_a_transfer_action_on_an_admission_is_refused_and_leaves_it_untouched(
    tmp_path: Path, action: str, restart: bool
) -> None:
    library: _Library = _library(tmp_path, managed=True)
    with _running(library) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        answer: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": "t500-3", "action": action}, command_id="action-1")
        )
        if restart:
            with _running(library) as later:
                answer = later.handle(
                    _request("transfer", {"info_hash": "t500-3", "action": action}, command_id="action-2")
                )

    assert (answer.ok, answer.reason) == (False, "transfer_not_started")
    stored: AcquisitionConfirmation = library.store.load().acquisitions[0]
    assert stored.state is AcquisitionState.ADMITTED
    assert not stored.action_pending
    assert stored.requested_action is None
    assert library.network.info_calls == 0
    assert library.network.actions == []


def test_a_stored_action_on_an_admission_never_reaches_the_client_poller(tmp_path: Path) -> None:
    library: _Library = _library(tmp_path, managed=True)
    with _running(library) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
    admitted: AcquisitionConfirmation = replace(
        library.store.load().acquisitions[0],
        requested_action="stop",
        action_id="action-1",
        action_pending=True,
    )
    sibling: AcquisitionConfirmation = replace(
        _accepted_transfer("g9", layout=((0, "09.mkv", 4),), started=True),
        requested_action="stop",
        action_id="action-2",
        action_pending=True,
    )
    library.network.tracked["g9"] = TorrentInfo("Pack", "g9", 0.5, "downloading", str(tmp_path), 4, 2)
    library.network.per_hash["g9"] = (TorrentFile(0, "09.mkv", 4, 0.5, 1),)
    library.store.save(replace(library.store.load(), acquisitions=(admitted, sibling)))
    with _running(library):
        deadline: float = time.monotonic() + _TIMEOUT_S
        while not library.network.actions and time.monotonic() < deadline:
            time.sleep(0.01)

    assert library.network.actions == [("g9", "stop")]
    assert library.store.load().acquisitions[0].state is AcquisitionState.ADMITTED
