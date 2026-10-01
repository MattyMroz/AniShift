from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest
from test_automation import _TIMEOUT_S, _accepted_transfer, _owner, _real_service, _request, _serving, _TorrentNetwork

from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    EpisodeChoice,
    ProcessingRequest,
    RequestState,
    SourceSelection,
    TorrentioReference,
    WatchState,
)
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.intents import RequestOrigin
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.errors import ConfigError, ErrorCode, ErrorContext
from anishift.platform.local_control import ControlResponse
from anishift.services.torrents import TorrentClientError, TorrentFile, TorrentInfo, parse_release_name

_ENTRY: int = 500

_HASH: str = "pack"

_PACK: tuple[TorrentFile, ...] = (
    TorrentFile(0, "Pack/Neko to Ryuu - 03.mkv", 400, 0.0, 1),
    TorrentFile(1, "Pack/Neko to Ryuu - 03.ass", 40, 0.0, 1),
    TorrentFile(2, "Pack/Neko to Ryuu - 04.mkv", 410, 0.0, 1),
    TorrentFile(3, "Pack/Neko to Ryuu - 04.ass", 41, 0.0, 1),
    TorrentFile(4, "Pack/Neko to Ryuu - 05.mkv", 420, 0.0, 1),
)

_STOPPED: frozenset[str] = frozenset({"stoppedDL", "pausedDL", "stoppedUP", "pausedUP"})


class _SelectiveNetwork(_TorrentNetwork):
    def __init__(self) -> None:
        super().__init__()
        self.metadata_added: list[tuple[str, tuple[str, ...], Path]] = []
        self.selections: list[tuple[str, frozenset[int]]] = []
        self.selected: dict[str, frozenset[int]] = {}
        self.unapproved_starts: list[str] = []
        self.before_select: Callable[[], None] | None = None
        self.lose_metadata_response: bool = False
        self.metadata_on_resume: bool = False
        self.stop_ignored: bool = False
        self.hidden: bool = False
        self.hidden_reads: int = 0
        self.before_inspection: Callable[[], None] | None = None
        self.during_check: Callable[[], None] | None = None

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        check: Callable[[], None] | None = self.during_check
        if check is not None and self.selections:
            self.during_check = None
            check()
        return super().files(info_hash)

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        listed: tuple[TorrentInfo, ...] = super().torrents(category)
        if not self.hidden and not self.hidden_reads:
            return listed
        self.hidden_reads = max(0, self.hidden_reads - 1)
        return tuple(item for item in listed if item.info_hash != _HASH)

    def resume_unconfirmed(self, hashes: frozenset[str]) -> None:
        if self.before_inspection is not None:
            self.before_inspection()
        super().resume_unconfirmed(hashes)

    def add_metadata(self, info_hash: str, *, trackers: tuple[str, ...] = (), save_path: Path, category: str) -> None:
        del category
        self.metadata_added.append((info_hash, trackers, save_path))
        self.tracked[info_hash] = TorrentInfo(info_hash, info_hash, 0.0, "metaDL", str(save_path), None, 0)
        if self.lose_metadata_response:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Response lost")
            )

    def deliver(self, info_hash: str, files: tuple[TorrentFile, ...] = _PACK) -> None:
        self.per_hash[info_hash] = files
        self.tracked[info_hash] = replace(self.tracked[info_hash], state="stoppedDL")

    def select_files(
        self, info_hash: str, files: tuple[TorrentFile, ...], selected: frozenset[int], *, save_path: Path
    ) -> tuple[TorrentFile, ...]:
        if self.before_select is not None:
            self.before_select()
        current: TorrentInfo = self.tracked[info_hash]
        if current.state not in _STOPPED or Path(current.save_path) != save_path:
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="The transfer is not stopped")
            )
        assert [(item.index, item.name, item.size) for item in files] == [
            (item.index, item.name, item.size) for item in self.per_hash[info_hash]
        ]
        self.selections.append((info_hash, selected))
        self.selected[info_hash] = selected
        self.per_hash[info_hash] = tuple(replace(item, priority=int(item.index in selected)) for item in files)
        return self.per_hash[info_hash]

    def finish(self, info_hash: str) -> None:
        self.per_hash[info_hash] = tuple(
            replace(item, progress=1.0) if item.priority > 0 else item for item in self.per_hash[info_hash]
        )
        self.tracked[info_hash] = replace(self.tracked[info_hash], progress=1.0, state="stalledUP", amount_left=0)

    def resume(self, info_hash: str) -> None:
        if self.metadata_on_resume and not self.per_hash.get(info_hash):
            self.deliver(info_hash)
        if self.per_hash.get(info_hash) and info_hash not in self.selected:
            self.unapproved_starts.append(info_hash)
        super().resume(info_hash)

    def transfer_action(self, info_hash: str, action: str) -> None:
        super().transfer_action(info_hash, action)
        if action == "stop" and info_hash in self.tracked and not self.stop_ignored:
            self.tracked[info_hash] = replace(self.tracked[info_hash], state="stoppedDL")
        if action == "resume":
            self.resume(info_hash)


class _RefusingStore(WatchStateStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.refused: int = 0

    def save(self, state: WatchState) -> None:
        if not self.refused and any(
            item.selective and item.state is AcquisitionState.ACCEPTED for item in state.acquisitions
        ):
            self.refused += 1
            raise OSError(28, "No space left on device")
        super().save(state)


@dataclass
class _Setup:
    network: _SelectiveNetwork
    store: WatchStateStore
    root: Path

    def owner(self) -> AutomationOwner:
        acquisition: AcquisitionService = AcquisitionService(
            source=self.network,
            client=cast("TorrentClient", self.network),
            workspace_root=self.root,
            parse_name=parse_release_name,
            torrent_management=cast("TorrentManagement", self.network),
        )
        return _owner(_real_service(self.root, acquisition=acquisition), self.store)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Setup:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.01)
    return _Setup(_SelectiveNetwork(), WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), tmp_path)


@contextmanager
def _running(setup: _Setup) -> Iterator[AutomationOwner]:
    owner: AutomationOwner = setup.owner()
    thread: threading.Thread = _serving(owner)
    try:
        yield owner
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def _choice(number: int, *, file_name: str | None = None) -> EpisodeChoice:
    return EpisodeChoice(
        anilist_id=_ENTRY,
        number=number,
        reference=TorrentioReference(
            _HASH, 0, file_name or f"Neko to Ryuu - {number:02d}.mkv", "[Group] Neko to Ryuu", ("udp://t.test:1",)
        ),
        target={"local_episode": number},
        verdict=IdentityVerdict.MATCH,
        reason="Specific work title and local episode match",
    )


def _until(condition: Callable[[], bool]) -> None:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def _state(setup: _Setup) -> WatchState:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while True:
        try:
            return setup.store.load()
        except ConfigError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)


def _stored(setup: _Setup) -> AcquisitionConfirmation:
    return _state(setup).acquisitions[0]


def _view(owner: AutomationOwner) -> dict[str, object]:
    answer: ControlResponse = owner.handle(_request("status", command_id=f"status-{time.monotonic_ns()}"))
    return cast("list[dict[str, object]]", answer.result["acquisitions"])[0]


def _starts(setup: _Setup, count: int = 1) -> Callable[[], bool]:
    return lambda: len(setup.network.started) >= count


def test_repeated_pause_preserves_ownership_of_an_unsent_resume(setup: _Setup, monkeypatch: pytest.MonkeyPatch) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    torrents: Callable[[str], tuple[TorrentInfo, ...]] = setup.network.torrents

    def gated(category: str) -> tuple[TorrentInfo, ...]:
        entered.set()
        assert release.wait(_TIMEOUT_S)
        return torrents(category)

    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(lambda: owner.state.acquisitions[0].content_started)
        owner._on_owner(
            lambda: owner._replace_acquisition(replace(owner.state.acquisitions[0], origin=RequestOrigin.BACKGROUND))
        )
        assert owner.handle(_request("set_auto", {"enabled": False}, command_id="pause-1")).ok
        _until(lambda: owner.state.acquisitions[0].action_sent and not owner.state.acquisitions[0].action_pending)
        monkeypatch.setattr(setup.network, "torrents", gated)
        try:
            assert owner.handle(_request("set_auto", {"enabled": True}, command_id="resume-1")).ok
            assert entered.wait(_TIMEOUT_S)
            assert owner.handle(_request("set_auto", {"enabled": False}, command_id="pause-2")).ok
        finally:
            release.set()
        _until(lambda: not owner.state.acquisitions[0].action_pending)
        assert owner.handle(_request("set_auto", {"enabled": True}, command_id="resume-2")).ok
        _until(lambda: (_HASH, "resume") in setup.network.actions)


def test_completed_selective_episode_keeps_its_material_identity_until_processing(setup: _Setup) -> None:
    from test_selective_publication import _download, _settled  # noqa: PLC0415

    with _running(setup) as owner:
        _download(setup, owner)
        _until(lambda: _settled(owner))
        group_id: str | None = owner.state.acquisitions[0].assignments[0].group_id
        assert group_id is not None
        response: ControlResponse = owner.handle(_request("status"))
        materials: list[dict[str, object]] = cast("list[dict[str, object]]", response.result["materials"])
        row: dict[str, object] = next(item for item in materials if item.get("group_id") == group_id)
        assert row["stage"] == "waiting"
        assert row["reason"] == "preparing"
        request: ProcessingRequest = ProcessingRequest(
            "processing",
            1,
            (group_id,),
            {},
            RequestOrigin.USER,
            SourceSelection.AUTO,
            None,
            {},
            RequestState.ACCEPTED,
            1,
            "2026-09-30T00:00:00+00:00",
        )
        assert owner._on_owner(lambda: owner._save(replace(owner.state, requests=(request,))))
        response = owner.handle(_request("status"))
        materials = cast("list[dict[str, object]]", response.result["materials"])
        processing: dict[str, object] = next(item for item in materials if item.get("group_id") == group_id)
        assert processing["material_id"] == row["material_id"]
        assert processing["stage"] == "processing"


def test_explicit_resume_preserves_confirmed_content_start_without_starting_twice(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(lambda: owner.state.acquisitions[0].content_started)
        assert owner.handle(_request("transfer", {"info_hash": _HASH, "action": "stop"}, command_id="stop")).ok
        _until(lambda: not owner.state.acquisitions[0].action_pending)
        assert owner.handle(_request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume")).ok
        _until(lambda: not owner.state.acquisitions[0].action_pending)
        _until(lambda: owner.state.acquisitions[0].content_started)
        assert setup.network.started == [_HASH, _HASH]


def test_an_admitted_episode_gets_metadata_then_a_saved_verified_selection_before_its_content_starts(
    setup: _Setup,
) -> None:
    observed: list[tuple[int, int, tuple[int, ...]]] = []

    def before_select() -> None:
        recorded: AcquisitionConfirmation = _stored(setup)
        observed.append((recorded.selection_revision, recorded.applied_revision, tuple(sorted(recorded.wanted_files))))

    setup.network.before_select = before_select
    with _running(setup) as owner:
        admitted: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        _until(lambda: bool(setup.network.metadata_added))
        _until(lambda: _view(owner)["state"] == AcquisitionState.ACCEPTED.value)
        time.sleep(0.1)
        waiting: list[tuple[str, frozenset[int]]] = list(setup.network.selections)
        setup.network.deliver(_HASH)
        _until(_starts(setup))

    assert admitted.ok
    assert waiting == []
    stored: AcquisitionConfirmation = _stored(setup)
    assert setup.network.metadata_added == [
        (_HASH, ("udp://t.test:1",), setup.root / "temp" / ".acquisition" / stored.operation_id / "data")
    ]
    assert stored.directory == f"temp/.acquisition/{stored.operation_id}/data"
    assert stored.assignments[0].files == (
        (0, "Pack/Neko to Ryuu - 03.mkv", 400),
        (1, "Pack/Neko to Ryuu - 03.ass", 40),
    )
    assert observed == [(1, 0, (0, 1))]
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]
    assert (stored.selection_revision, stored.applied_revision) == (1, 1)
    assert setup.network.started == [_HASH]
    assert setup.network.unapproved_starts == []


def test_a_second_episode_of_the_same_hash_joins_the_transfer_and_restarts_it_with_both_files(
    setup: _Setup,
) -> None:
    with _running(setup) as owner:
        first: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        second: ControlResponse = owner.admit_episode("admit-2", _choice(4))
        _until(_starts(setup, 2))

    assert first.ok
    assert second.ok
    assert second.result["operation_id"] == first.result["operation_id"]
    assert len(_state(setup).acquisitions) == 1
    assert len(setup.network.metadata_added) == 1
    assert setup.network.selections == [(_HASH, frozenset({0, 1})), (_HASH, frozenset({0, 1, 2, 3}))]
    assert (_HASH, "stop") in setup.network.actions
    assert setup.network.started == [_HASH, _HASH]
    assert setup.network.unapproved_starts == []


def test_an_episode_admitted_during_an_older_selection_is_kept_and_selected_before_any_start(
    setup: _Setup,
) -> None:
    joined: list[ControlResponse] = []
    owners: list[AutomationOwner] = []

    def admit_during_select() -> None:
        if not joined:
            joined.append(owners[0].admit_episode("admit-2", _choice(4)))

    setup.network.before_select = admit_during_select
    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))

    assert joined[0].ok
    stored: AcquisitionConfirmation = _stored(setup)
    assert [item.choice.number for item in stored.assignments] == [3, 4]
    assert all(item.mapped for item in stored.assignments)
    assert setup.network.selections == [(_HASH, frozenset({0, 1})), (_HASH, frozenset({0, 1, 2, 3}))]
    assert setup.network.started == [_HASH]
    assert (stored.selection_revision, stored.applied_revision) == (2, 2)


def test_an_episode_whose_video_another_episode_holds_is_bound_without_files(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        assert owner.admit_episode("admit-2", _choice(4, file_name="Neko to Ryuu - 03.mkv")).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))

    stored: AcquisitionConfirmation = _stored(setup)
    assert stored.assignments[1].mapped
    assert stored.assignments[1].files == ()
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]


@pytest.mark.parametrize(
    ("boundary", "paused"),
    [
        ("sent", False),
        ("uncertain", False),
        ("uncertain", True),
        ("bound", False),
        ("selected", False),
        ("started", False),
    ],
)
def test_a_restart_at_every_boundary_adds_and_admits_once_and_starts_only_selected_files(
    setup: _Setup, boundary: str, paused: bool
) -> None:
    owners: list[AutomationOwner] = []

    interrupted_at: list[str] = []

    def interrupt() -> None:
        interrupted_at.append(boundary)
        owners[0].request_shutdown()
        if boundary == "bound":
            raise TorrentClientError(
                context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Interrupted")
            )

    setup.network.lose_metadata_response = boundary == "uncertain"
    if boundary in {"bound", "selected"}:
        setup.network.before_select = interrupt
    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        _until(lambda: _view(owner)["state"] != AcquisitionState.PENDING_SEND.value)
        if boundary in {"bound", "selected", "started"}:
            setup.network.deliver(_HASH)
        if boundary == "started":
            _until(_starts(setup))
        if boundary in {"bound", "selected"}:
            _until(lambda: bool(interrupted_at))
    interrupted: AcquisitionConfirmation = _stored(setup)
    setup.network.before_select = None
    setup.network.lose_metadata_response = False
    if boundary in {"sent", "uncertain"}:
        setup.network.deliver(_HASH)
    if paused:
        setup.store.save(replace(_state(setup), policy=AutomationPolicy(auto_enabled=False)))
    with _running(setup) as owner:
        replay: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        _until(_starts(setup))
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 2)

    assert replay.ok
    assert (interrupted.state is AcquisitionState.UNCERTAIN) is (boundary == "uncertain")
    assert _state(setup).policy.auto_enabled is not paused
    assert interrupted.content_started is (boundary == "started")
    assert len(setup.network.metadata_added) == 1
    assert len(_state(setup).acquisitions) == 1
    assert len(_stored(setup).assignments) == 1
    assert setup.network.selected == {_HASH: frozenset({0, 1})}
    assert setup.network.started == [_HASH]
    assert setup.network.unapproved_starts == []


def test_manual_metadata_and_content_continue_under_automation_pause_without_duplicate_start(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["state"] == AcquisitionState.ACCEPTED.value)
        status: ControlResponse = owner.handle(_request("status", command_id="status-1"))
        paused: ControlResponse = owner.handle(_request("set_auto", {"enabled": False}, command_id="pause-1"))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        during_pause: tuple[list[tuple[str, frozenset[int]]], list[str]] = (
            list(setup.network.selections),
            list(setup.network.started),
        )
        resumed: ControlResponse = owner.handle(_request("set_auto", {"enabled": True}, command_id="resume-1"))
        _until(_starts(setup))

    assert status.ok
    assert [item["info_hash"] for item in cast("list[dict[str, object]]", status.result["acquisitions"])] == [_HASH]
    assert paused.ok
    assert resumed.ok
    assert during_pause == ([(_HASH, frozenset({0, 1}))], [_HASH])
    assert setup.network.started == [_HASH]
    assert setup.network.actions == []
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]
    assert setup.network.unapproved_starts == []


def test_a_transfer_without_metadata_in_time_is_reported_and_never_selected(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "METADATA_TIMEOUT_S", 0.05)
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["problem"] is not None)

    assert _stored(setup).problem == automation_module._NO_FILE_LIST
    assert setup.network.selections == []
    assert setup.network.started == []


def test_a_resume_before_the_verified_selection_never_starts_unselected_files(setup: _Setup) -> None:
    def refuse() -> None:
        raise TorrentClientError(context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Busy"))

    setup.network.before_select = refuse
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(lambda: _view(owner)["problem"] is not None)
        answer: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        _until(lambda: not _view(owner)["action_pending"])

    assert answer.ok
    assert setup.network.started == []
    assert (_HASH, "resume") not in setup.network.actions
    assert setup.network.unapproved_starts == []


def test_an_episode_of_a_legacy_transfer_hash_is_refused_and_its_priorities_are_untouched(setup: _Setup) -> None:
    legacy: AcquisitionConfirmation = _accepted_transfer(_HASH, layout=((0, "03.mkv", 4),), started=True)
    setup.network.tracked[_HASH] = TorrentInfo("Pack", _HASH, 0.5, "downloading", str(setup.root), 4, 2)
    setup.network.per_hash[_HASH] = (TorrentFile(0, "03.mkv", 4, 0.5, 1),)
    setup.store.save(replace(setup.store.load(), acquisitions=(legacy,), policy=AutomationPolicy(auto_enabled=True)))
    with _running(setup) as owner:
        answer: ControlResponse = owner.admit_episode("admit-1", _choice(3))
        _until(lambda: setup.network.info_calls > 2)

    assert (answer.ok, answer.reason) == (False, "transfer_recorded")
    assert [(item.operation_id, item.selective) for item in _state(setup).acquisitions] == [
        (legacy.operation_id, False)
    ]
    assert setup.network.metadata_added == []
    assert setup.network.selections == []
    assert setup.network.per_hash[_HASH] == (TorrentFile(0, "03.mkv", 4, 0.5, 1),)


def _interrupted_after_selection(setup: _Setup) -> None:
    owners: list[AutomationOwner] = []
    interrupted: list[bool] = []

    def interrupt() -> None:
        interrupted.append(True)
        owners[0].request_shutdown()

    setup.network.before_select = interrupt
    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(lambda: bool(interrupted))
    setup.network.before_select = None


@pytest.mark.parametrize("change", ["priorities", "folder", "sizes"])
def test_a_restarted_owner_never_starts_a_selection_the_client_no_longer_matches(setup: _Setup, change: str) -> None:
    _interrupted_after_selection(setup)
    applied: AcquisitionConfirmation = _stored(setup)
    files: tuple[TorrentFile, ...] = setup.network.per_hash[_HASH]
    if change == "priorities":
        setup.network.per_hash[_HASH] = tuple(replace(item, priority=1) for item in files)
    if change == "folder":
        setup.network.tracked[_HASH] = replace(setup.network.tracked[_HASH], save_path=str(setup.root))
    if change == "sizes":
        setup.network.per_hash[_HASH] = tuple(replace(item, size=item.size + 1) for item in files)
    with _running(setup) as owner:
        _until(lambda: _view(owner)["problem"] is not None)

    assert (applied.selection_revision, applied.applied_revision, applied.content_started) == (1, 1, False)
    assert _stored(setup).problem == automation_module._SELECTION_MISMATCH
    assert setup.network.started == []


def test_a_restarted_owner_starts_a_selection_the_client_still_matches(setup: _Setup) -> None:
    _interrupted_after_selection(setup)
    with _running(setup):
        _until(_starts(setup))

    assert _stored(setup).problem is None
    assert setup.network.started == [_HASH]


def test_a_resume_after_the_metadata_timeout_keeps_the_client_from_fetching_unselected_files(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "METADATA_TIMEOUT_S", 0.05)
    setup.network.metadata_on_resume = True
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["problem"] is not None)
        monkeypatch.setattr(automation_module, "METADATA_TIMEOUT_S", 60.0)
        answer: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        _until(lambda: not _view(owner)["action_pending"] and _view(owner)["problem"] is None)
        setup.network.deliver(_HASH)
        _until(_starts(setup))

    assert answer.ok
    assert setup.network.unapproved_starts == []
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]
    assert setup.network.started == [_HASH]


def test_a_resume_of_a_transfer_stopped_before_its_metadata_is_refused_without_starting_it(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "METADATA_TIMEOUT_S", 0.05)
    setup.network.metadata_on_resume = True
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["problem"] is not None)
        setup.network.tracked[_HASH] = replace(setup.network.tracked[_HASH], state="stoppedDL")
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1"))
        _until(lambda: _view(owner)["problem"] == automation_module._METADATA_STOPPED)

    assert setup.network.started == []
    assert setup.network.unapproved_starts == []


def test_an_explicit_resume_gives_the_metadata_a_whole_new_attempt(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(automation_module, "METADATA_TIMEOUT_S", 0.3)
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["problem"] is not None)
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1"))
        _until(lambda: not _view(owner)["action_pending"] and _view(owner)["problem"] is None)
        resumed: float = time.monotonic()
        _until(lambda: _view(owner)["problem"] is not None)
        waited: float = time.monotonic() - resumed

    assert waited >= 0.2
    assert _stored(setup).problem == automation_module._NO_FILE_LIST
    assert setup.network.started == []


def test_a_finished_transfer_with_an_unselected_joined_episode_is_neither_complete_nor_released(
    setup: _Setup,
) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        staging: Path = setup.root / "temp" / ".acquisition" / str(_view(owner)["operation_id"]) / "data" / "Pack"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "Neko to Ryuu - 03.mkv").write_bytes(b"v" * 400)
        (staging / "Neko to Ryuu - 03.ass").write_bytes(b"s" * 40)
        assert owner.admit_episode("admit-2", _choice(4)).ok
        setup.network.finish(_HASH)
        _until(lambda: len(setup.network.selections) >= 2)

    assert setup.network.released == []
    assert _stored(setup).state is AcquisitionState.ACCEPTED
    assert setup.network.selections[-1] == (_HASH, frozenset({0, 1, 2, 3}))


def test_automation_pause_does_not_claim_a_manual_transfer_awaiting_its_new_selection(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        setup.network.stop_ignored = True
        assert owner.admit_episode("admit-2", _choice(4)).ok
        _until(lambda: (_HASH, "stop") in setup.network.actions)
        paused: ControlResponse = owner.handle(_request("set_auto", {"enabled": False}, command_id="pause-1"))
        action: object = _view(owner)["action"]

    assert paused.ok
    assert action is None
    assert _state(setup).pause_owned_transfers == ()


def test_an_unsaved_acceptance_is_reconciled_from_the_client_without_a_second_add(setup: _Setup) -> None:
    store: _RefusingStore = _RefusingStore(setup.root / WATCH_STATE_FILE_NAME)
    refusing: _Setup = replace(setup, store=store)
    with _running(refusing) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(refusing.network.metadata_added))
        refusing.network.deliver(_HASH)
        _until(_starts(refusing))

    assert store.refused == 1
    assert len(refusing.network.metadata_added) == 1
    assert refusing.network.unapproved_starts == []


@pytest.mark.parametrize("moment", ["mapping", "selection"])
@pytest.mark.parametrize("selected", [False, True])
def test_stop_during_selection_requires_a_previously_confirmed_scope(
    setup: _Setup, moment: str, *, selected: bool
) -> None:
    owners: list[AutomationOwner] = []
    answers: list[ControlResponse] = []

    def request_stop() -> None:
        if not answers and setup.network.per_hash.get(_HASH):
            answers.append(
                owners[0].handle(_request("transfer", {"info_hash": _HASH, "action": "stop"}, command_id="stop-1"))
            )

    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        if selected:
            setup.network.deliver(_HASH)
            _until(_starts(setup))
        if moment == "mapping":
            setup.network.before_info = request_stop
        else:
            setup.network.before_select = request_stop
        if selected:
            assert owner.admit_episode("admit-2", _choice(4)).ok
        setup.network.deliver(_HASH)
        _until(lambda: bool(answers))
        if not selected:
            _until(_starts(setup))
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 3)

    assert answers[0].ok is selected
    if not selected:
        assert answers[0].reason == "transfer_metadata_pending"
    assert setup.network.started == [_HASH]
    assert (_HASH, "resume") not in setup.network.actions


@pytest.mark.parametrize("changed", [True, False])
def test_an_explicit_resume_restarts_a_stopped_selection_only_while_the_client_still_matches_it(
    setup: _Setup, changed: bool
) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "stop"}, command_id="stop-1"))
        _until(lambda: not _view(owner)["action_pending"])
        if changed:
            setup.network.per_hash[_HASH] = tuple(replace(item, priority=1) for item in setup.network.per_hash[_HASH])
        answer: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        if changed:
            _until(lambda: _view(owner)["problem"] is not None)
        else:
            _until(_starts(setup, 2))

    assert answer.ok
    assert _stored(setup).problem == (automation_module._SELECTION_MISMATCH if changed else None)
    assert setup.network.started == ([_HASH] if changed else [_HASH, _HASH])


def test_the_end_of_a_global_pause_never_restarts_a_selection_whose_priorities_changed(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        owner._on_owner(
            lambda: owner._replace_acquisition(replace(owner.state.acquisitions[0], origin=RequestOrigin.BACKGROUND))
        )
        owner.handle(_request("set_auto", {"enabled": False}, command_id="pause-1"))
        _until(lambda: (_HASH, "stop") in setup.network.actions and not _view(owner)["action_pending"])
        setup.network.per_hash[_HASH] = tuple(replace(item, priority=1) for item in setup.network.per_hash[_HASH])
        owner.handle(_request("set_auto", {"enabled": True}, command_id="resume-1"))
        _until(lambda: _view(owner)["problem"] is not None)

    assert _stored(setup).problem == automation_module._SELECTION_MISMATCH
    assert setup.network.started == [_HASH]


def test_explicit_resume_after_a_selection_mismatch_reapplies_the_saved_union_before_start(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "stop"}, command_id="stop-1"))
        _until(lambda: not _view(owner)["action_pending"])
        setup.network.per_hash[_HASH] = tuple(replace(item, priority=1) for item in setup.network.per_hash[_HASH])
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1"))
        _until(lambda: _view(owner)["problem"] == automation_module._SELECTION_MISMATCH)
    with _running(setup) as owner:
        assert owner.handle(_request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-2")).ok
        _until(_starts(setup, 2))
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))] * 2
    assert (_stored(setup).selection_revision, _stored(setup).applied_revision) == (2, 2)
    assert _stored(setup).problem is None
    assert setup.network.unapproved_starts == []


def test_a_finished_transfer_with_an_unresolved_episode_is_neither_complete_nor_released(setup: _Setup) -> None:
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        assert owner.admit_episode("admit-2", _choice(4, file_name="Neko to Ryuu - 03.mkv")).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        staging: Path = setup.root / "temp" / ".acquisition" / str(_view(owner)["operation_id"]) / "data" / "Pack"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "Neko to Ryuu - 03.mkv").write_bytes(b"v" * 400)
        (staging / "Neko to Ryuu - 03.ass").write_bytes(b"s" * 40)
        setup.network.finish(_HASH)
        polled: int = setup.network.info_calls
        _until(lambda: setup.network.info_calls > polled + 5)

    stored: AcquisitionConfirmation = _stored(setup)
    assert setup.network.released == []
    assert stored.state is AcquisitionState.ACCEPTED
    assert stored.assignments[1].files == ()


def test_a_submission_the_client_briefly_does_not_list_is_rechecked_without_a_second_add(setup: _Setup) -> None:
    store: _RefusingStore = _RefusingStore(setup.root / WATCH_STATE_FILE_NAME)
    refusing: _Setup = replace(setup, store=store)
    refusing.network.hidden_reads = 2
    with _running(refusing) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(refusing.network.metadata_added))
        refusing.network.deliver(_HASH)
        _until(_starts(refusing))

    assert store.refused == 1
    assert len(refusing.network.metadata_added) == 1


def test_a_submission_the_client_keeps_not_listing_is_reported_and_resumed_without_a_second_add(
    setup: _Setup,
) -> None:
    store: _RefusingStore = _RefusingStore(setup.root / WATCH_STATE_FILE_NAME)
    refusing: _Setup = replace(setup, store=store)
    refusing.network.hidden = True
    with _running(refusing) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: _view(owner)["problem"] == automation_module._SEND_UNCONFIRMED)
        reported: object = _view(owner)["state"]
        refusing.network.hidden = False
        refusing.network.deliver(_HASH)
        answer: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        _until(_starts(refusing))

    assert reported == AcquisitionState.UNCERTAIN.value
    assert answer.ok
    assert len(refusing.network.metadata_added) == 1
    assert refusing.network.unapproved_starts == []


def test_a_cancel_recorded_after_a_round_began_keeps_that_worker_from_selecting_files(setup: _Setup) -> None:
    owners: list[AutomationOwner] = []
    interrupted: list[bool] = []

    def interrupt() -> None:
        interrupted.append(True)
        owners[0].request_shutdown()
        raise TorrentClientError(context=ErrorContext(code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE, message="Stopped"))

    setup.network.before_select = interrupt
    with _running(setup) as owner:
        owners.append(owner)
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(lambda: bool(interrupted))
    bound: AcquisitionConfirmation = _stored(setup)
    setup.network.before_select = None
    answers: list[ControlResponse] = []

    def cancel() -> None:
        if len(owners) == 2 and not answers:
            answers.append(
                owners[1].handle(_request("transfer", {"info_hash": _HASH, "action": "cancel"}, command_id="cancel-1"))
            )

    setup.network.before_inspection = cancel
    with _running(setup) as owner:
        owners.append(owner)
        _until(lambda: bool(answers))
        _until(lambda: _view(owner)["state"] == AcquisitionState.FAILED.value)

    assert (bound.selection_revision, bound.applied_revision) == (1, 0)
    assert answers[0].ok
    assert setup.network.selections == []
    assert setup.network.started == []
    assert _stored(setup).state is AcquisitionState.FAILED


@pytest.mark.parametrize(
    ("kind", "payload"),
    [("set_auto", {"enabled": False}), ("transfer", {"info_hash": _HASH, "action": "cancel"})],
)
def test_fresh_manual_selection_survives_automation_pause_but_respects_cancel(
    setup: _Setup, kind: str, payload: dict[str, object]
) -> None:
    owners: list[AutomationOwner] = []
    answers: list[ControlResponse] = []
    polled: list[int] = []

    def interrupt() -> None:
        answers.append(owners[0].handle(_request(kind, payload, command_id="interrupt-1")))
        polled.append(setup.network.info_calls)

    setup.network.during_check = interrupt
    with _running(setup) as owner:
        owners.append(owner)
        owner.admit_episode("admit-1", _choice(3))
        _until(lambda: _view(owner)["state"] == AcquisitionState.ACCEPTED.value)
        setup.network.deliver(_HASH)
        _until(lambda: bool(polled))
        _until(
            lambda: setup.network.info_calls > polled[0] + 1 or _view(owner)["state"] == AcquisitionState.FAILED.value
        )

    assert answers[0].ok
    assert setup.network.selections == [(_HASH, frozenset({0, 1}))]
    assert setup.network.started == ([_HASH] if kind == "set_auto" else [])
    assert _stored(setup).content_started is (kind == "set_auto")


@pytest.mark.parametrize(
    ("kind", "payload"),
    [("set_auto", {"enabled": False}), ("transfer", {"info_hash": _HASH, "action": "cancel"})],
)
def test_fresh_manual_resume_survives_automation_pause_but_respects_cancel(
    setup: _Setup, kind: str, payload: dict[str, object]
) -> None:
    answers: list[ControlResponse] = []
    polled: list[int] = []
    with _running(setup) as owner:
        assert owner.admit_episode("admit-1", _choice(3)).ok
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH)
        _until(_starts(setup))
        owner.handle(_request("transfer", {"info_hash": _HASH, "action": "stop"}, command_id="stop-1"))
        _until(lambda: not _view(owner)["action_pending"])

        def interrupt() -> None:
            answers.append(owner.handle(_request(kind, payload, command_id="interrupt-1")))
            polled.append(setup.network.info_calls)

        setup.network.during_check = interrupt
        resumed: ControlResponse = owner.handle(
            _request("transfer", {"info_hash": _HASH, "action": "resume"}, command_id="resume-1")
        )
        _until(lambda: bool(polled))
        _until(
            lambda: setup.network.info_calls > polled[0] + 1 or _view(owner)["state"] == AcquisitionState.FAILED.value
        )

    assert resumed.ok
    assert answers[0].ok
    assert setup.network.started == ([_HASH, _HASH] if kind == "set_auto" else [_HASH])
    assert ((_HASH, "resume") in setup.network.actions) is (kind == "set_auto")
