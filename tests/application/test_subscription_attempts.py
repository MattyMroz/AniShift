from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from test_automation import _INSTANCE, _MOMENT, _TIMEOUT_S, _real_service, _request, _serving
from test_selective_lifecycle import _ENTRY, _HASH, _PACK, _choice, _SelectiveNetwork, _Setup, _starts, _until, _view
from test_selective_publication import _NAMES, _SUBTITLES, _VIDEO, _root_files

from anishift.application import automation as automation_module
from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.acquisition_staging import copy_staged, file_stamp
from anishift.application.automation import AutomationOwner
from anishift.application.cancellation import CancellationToken
from anishift.application.control import (
    VERIFICATION_SKIPPED,
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    EpisodeAssignment,
    EpisodeChoice,
    FileStamp,
    WatchState,
)
from anishift.application.episode_commands import EpisodeReason
from anishift.application.episode_selection import EpisodeKey
from anishift.application.history import HistoryEvent, HistoryJournal, HistoryKind
from anishift.application.subscription_targets import (
    MAX_ATTEMPTS,
    SubscriptionRecord,
    SubscriptionTarget,
    TargetState,
)
from anishift.application.watch_state import WATCH_STATE_FILE_NAME, WatchStateStore
from anishift.errors import AniShiftError, ErrorCode, ErrorContext, MediaProbeError
from anishift.platform.binaries import BinaryNotFoundError
from anishift.platform.local_control import ControlResponse
from anishift.services.media.probe import MediaProbe
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind
from anishift.services.torrents import parse_release_name

_VIDEO_TRACK: MediaTrack = MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False)

_TARGET: dict[str, object] = {"aliases": ["Neko to Ryuu"], "type": "TV", "local_episode": 3, "season": 1, "episode": 3}


def _matching() -> EpisodeChoice:
    return replace(_choice(3), target=_TARGET)


class _Probe:
    def __init__(self, *, video: bool = True, failures: int = 0, error: AniShiftError | None = None) -> None:
        self.video: bool = video
        self.failures: int = failures
        self.error: AniShiftError = error or MediaProbeError(
            context=ErrorContext(code=ErrorCode.MEDIA_PROBE_FAILED, message="probe")
        )
        self.owner: AutomationOwner | None = None
        self.seen: list[tuple[str, bool, str | None]] = []
        self.during: list[Path] = []
        self.stamps: list[FileStamp | None] = []

    def identify(self, path: Path, *, cancel: CancellationToken, timeout_s: float) -> MediaCatalog:
        del cancel, timeout_s
        assert self.owner is not None
        named: bool = self.owner.state.acquisitions[0].assignments[0].publication is not None
        self.seen.append((path.name, named, _reason(self.owner)))
        self.stamps.append(file_stamp(path))
        for changed in self.during:
            changed.write_bytes(_VIDEO[:-1] + b"!")
        self.during.clear()
        if self.failures:
            self.failures -= 1
            raise self.error
        return MediaCatalog(path, ContainerKind.MKV, 1_440_000_000, (_VIDEO_TRACK,) if self.video else ())


def _reason(owner: AutomationOwner) -> str | None:
    answer: ControlResponse = owner.handle(
        _request("episode_states", {"anilist_id": _ENTRY, "numbers": [3]}, command_id="states")
    )
    items: list[dict[str, object]] = cast("list[dict[str, object]]", answer.result["items"])
    return cast("str | None", items[0]["reason"])


def _record(attempts: int = 0, **changes: object) -> SubscriptionRecord:
    record: SubscriptionRecord = SubscriptionRecord(
        "a",
        _ENTRY,
        "Neko",
        (_MOMENT - timedelta(days=2)).isoformat(),
        2,
        targets=(
            SubscriptionTarget(
                3, (_MOMENT - timedelta(hours=1)).isoformat(), TargetState.DUE, attempts, started=attempts
            ),
        ),
    )
    return replace(record, **changes)  # type: ignore[arg-type]


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Setup:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "PANEL_TRANSFER_CHECK_INTERVAL_S", 0.01)
    monkeypatch.setattr(automation_module, "_CHECK_TIMEOUT_S", 0.05)
    return _Setup(_SelectiveNetwork(), WatchStateStore(tmp_path / WATCH_STATE_FILE_NAME), tmp_path)


@contextmanager
def _attempting(
    setup: _Setup, probe: _Probe | None, record: SubscriptionRecord | None = None
) -> Iterator[AutomationOwner]:
    subscribed: SubscriptionRecord = record or _record()
    setup.store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), subscriptions=(subscribed,)))
    acquisition: AcquisitionService = AcquisitionService(
        source=setup.network,
        client=cast("TorrentClient", setup.network),
        workspace_root=setup.root,
        parse_name=parse_release_name,
        torrent_management=cast("TorrentManagement", setup.network),
    )
    owner: AutomationOwner = AutomationOwner(
        _real_service(setup.root, acquisition=acquisition),
        setup.store,
        instance_id=_INSTANCE,
        clock=lambda: _MOMENT,
        media_probe=cast("MediaProbe | None", probe),
    )
    if probe is not None:
        probe.owner = owner
    thread: threading.Thread = _serving(owner)
    try:
        target: SubscriptionTarget = subscribed.targets[0]
        tried: SubscriptionTarget = replace(
            target, attempts=target.attempts + 1, started=target.started + 1, tried=(*target.tried, f"{_HASH}:0")
        )
        admitted: ControlResponse = owner._on_owner(
            lambda: owner._admit_episode(f"sub:a:3:{tried.started}", _matching(), attempt=("a", tried))
        )
        assert admitted.ok
        yield owner
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert not thread.is_alive()


def _deliver(setup: _Setup, owner: AutomationOwner) -> Path:
    _until(lambda: bool(setup.network.metadata_added))
    setup.network.deliver(_HASH, _PACK[:2])
    _until(_starts(setup))
    data: Path = setup.root / "temp" / ".acquisition" / str(_view(owner)["operation_id"]) / "data" / "Pack"
    data.mkdir(parents=True, exist_ok=True)
    (data / _NAMES[0]).write_bytes(_VIDEO)
    (data / _NAMES[1]).write_bytes(_SUBTITLES)
    _until(lambda: setup.network.tracked[_HASH].state == "downloading")
    setup.network.finish(_HASH)
    return data


def _assignment(owner: AutomationOwner) -> EpisodeAssignment:
    return owner.state.acquisitions[0].assignments[0]


def _target(owner: AutomationOwner) -> SubscriptionTarget:
    return owner.state.subscriptions[0].targets[0]


def _disk_counts(owner: AutomationOwner) -> tuple[object, object]:
    listed: ControlResponse = owner.handle(_request("subscriptions_list", command_id="counts"))
    row: dict[str, object] = cast("list[dict[str, object]]", listed.result["subscriptions"])[0]
    return row["on_disk"], row["ready"]


def _decisions(setup: _Setup) -> list[dict[str, object]]:
    path: Path = setup.store.history_path().with_name("decisions.jsonl")
    entries: list[dict[str, object]] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [item for item in entries if item.get("source") != "ani.zip"]


def test_an_attempt_is_checked_on_its_staged_video_before_naming_and_satisfies_its_target_once_handed_off(
    setup: _Setup,
) -> None:
    probe: _Probe = _Probe()
    with _attempting(setup, probe) as owner:
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is TargetState.SATISFIED)
        assignment: EpisodeAssignment = _assignment(owner)
        _until(lambda: _disk_counts(owner) == (1, 0))
        listed: ControlResponse = owner.handle(_request("subscriptions_list", command_id="list"))

    assert probe.seen == [(_NAMES[0], False, EpisodeReason.SUBSCRIPTION_CHECKING)]
    assert (assignment.subscription_id, assignment.attempt) == ("a", 1)
    assert assignment.verification == "inconclusive"
    assert assignment.verified_stamp is not None
    assert assignment.publication is not None
    assert assignment.publication.handed_off
    assert probe.stamps == [assignment.verified_stamp]
    assert listed.result["shadow"] is False
    rows: list[dict[str, object]] = cast("list[dict[str, object]]", listed.result["subscriptions"])
    assert (rows[0]["on_disk"], rows[0]["ready"]) == (1, 0)
    trail: list[tuple[object, object, object]] = [
        (item["kind"], item.get("source"), item.get("attempt_result")) for item in _decisions(setup)
    ]
    assert trail == [("selection", None, None), ("check", "h2", None), ("attempt", None, "accepted")]
    assert all(item["entry"] == "subscription" for item in _decisions(setup))


@pytest.mark.parametrize(("attempts", "state"), [(0, TargetState.DUE), (MAX_ATTEMPTS - 1, TargetState.EXHAUSTED)])
def test_a_rejected_attempt_is_never_named_and_cancels_its_own_transfer_before_the_next_try(
    setup: _Setup, attempts: int, state: TargetState
) -> None:
    probe: _Probe = _Probe(video=False)
    with _attempting(setup, probe, _record(attempts)) as owner:
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is state)
        pending: tuple[bool, str | None] = owner._on_owner(lambda: owner._attempt_previous("a", EpisodeKey(_ENTRY, 3)))
        rejected: EpisodeAssignment = _assignment(owner)
        cancelled: AcquisitionConfirmation = owner.state.acquisitions[0]
        _until(lambda: owner.state.acquisitions[0].state is AcquisitionState.FAILED)
        released: tuple[bool, str | None] = owner._on_owner(lambda: owner._attempt_previous("a", EpisodeKey(_ENTRY, 3)))
        status: str | None = _reason(owner)
        notified: frozenset[tuple[str, str, str]] = owner.state.notified

    assert rejected.verification == "reject:no_video_stream"
    assert rejected.publication is None
    assert not set(_NAMES) & _root_files(setup)
    assert cancelled.requested_action == "cancel"
    assert (_target_of(setup).attempts, _target_of(setup).reason) == (attempts + 1, "rejected")
    assert pending == (False, None)
    assert released == (True, None)
    escalated: bool = state is TargetState.EXHAUSTED
    assert (("subscription:a:3", "exhausted", "") in notified) is escalated
    assert status == (
        EpisodeReason.SUBSCRIPTION_EXHAUSTED if escalated else EpisodeReason.SUBSCRIPTION_AWAITING_RELEASE
    )
    kinds: list[tuple[object, object]] = [(item["kind"], item.get("reason")) for item in _decisions(setup)]
    assert ("attempt", "rejected") in kinds
    assert (("escalation", "exhausted") in kinds) is escalated


def _target_of(setup: _Setup) -> SubscriptionTarget:
    return setup.store.load().subscriptions[0].targets[0]


@pytest.mark.parametrize(("failures", "verification"), [(1, "inconclusive"), (2, VERIFICATION_SKIPPED)])
def test_a_failed_probe_is_retried_once_before_the_attempt_is_marked_unchecked(
    setup: _Setup, failures: int, verification: str
) -> None:
    probe: _Probe = _Probe(failures=failures)
    with _attempting(setup, probe) as owner:
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is TargetState.SATISFIED)
        assignment: EpisodeAssignment = _assignment(owner)
        target: SubscriptionTarget = _target(owner)

    assert len(probe.seen) == 2
    assert assignment.verification == verification
    assert target.check_skipped is (verification == VERIFICATION_SKIPPED)
    escalations: list[dict[str, object]] = [item for item in _decisions(setup) if item["kind"] == "escalation"]
    assert [item["reason"] for item in escalations] == (["check_skipped"] if target.check_skipped else [])


@pytest.mark.parametrize(
    ("error", "seen", "reason"),
    [
        (MediaProbeError(context=ErrorContext(code=ErrorCode.TIMEOUT, message="slow")), 2, "TIMEOUT"),
        (
            BinaryNotFoundError(context=ErrorContext(code=ErrorCode.BINARY_NOT_FOUND, message="none")),
            1,
            "binary_missing",
        ),
    ],
    ids=["timeout", "binary-missing"],
)
def test_a_probe_that_times_out_or_has_no_binary_admits_the_attempt_unchecked_and_escalates_once(
    setup: _Setup, error: AniShiftError, seen: int, reason: str
) -> None:
    probe: _Probe = _Probe(failures=2, error=error)
    with _attempting(setup, probe) as owner:
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is TargetState.SATISFIED)
        assignment: EpisodeAssignment = _assignment(owner)
        target: SubscriptionTarget = _target(owner)

    assert len(probe.seen) == seen
    assert assignment.verification == VERIFICATION_SKIPPED
    assert assignment.publication is not None
    assert assignment.publication.handed_off
    assert set(_NAMES) <= _root_files(setup)
    assert target.check_skipped
    assert [item["reason"] for item in _decisions(setup) if item.get("source") == "h2"] == [reason]
    assert [item["reason"] for item in _decisions(setup) if item["kind"] == "escalation"] == ["check_skipped"]


def test_a_resident_without_a_probe_admits_the_attempt_marked_unchecked(setup: _Setup) -> None:
    with _attempting(setup, None) as owner:
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is TargetState.SATISFIED)
        assignment: EpisodeAssignment = _assignment(owner)

    assert assignment.verification == VERIFICATION_SKIPPED
    assert [item["reason"] for item in _decisions(setup) if item.get("source") == "h2"] == ["probe_unavailable"]


def test_a_video_changed_during_its_check_is_checked_again(setup: _Setup) -> None:
    probe: _Probe = _Probe()
    with _attempting(setup, probe) as owner:
        _until(lambda: bool(setup.network.metadata_added))
        operation: str = str(_view(owner)["operation_id"])
        probe.during.append(setup.root / "temp" / ".acquisition" / operation / "data" / "Pack" / _NAMES[0])
        _deliver(setup, owner)
        _until(lambda: _target(owner).state is TargetState.SATISFIED)

    assert len(probe.seen) == 2
    assert [item.get("source") for item in _decisions(setup)].count("h2") == 1


def test_a_video_changed_after_its_check_is_never_copied_into_the_library(
    setup: _Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    def changed(source: Path, target: Path, size: int, *, expected: FileStamp | None = None) -> tuple[str, FileStamp]:
        if source.suffix == ".mkv":
            source.write_bytes(_VIDEO[:-1] + b"!")
        return copy_staged(source, target, size, expected=expected)

    monkeypatch.setattr(automation_module, "copy_staged", changed)
    with _attempting(setup, _Probe()) as owner:
        _deliver(setup, owner)
        _until(lambda: getattr(_assignment(owner).publication, "problem", None) is not None)
        target: SubscriptionTarget = _target(owner)

    assert not set(_NAMES) & _root_files(setup)
    assert target.state is TargetState.ATTEMPTING
    assert target.attempts == 1


def test_a_global_pause_stops_an_attempt_once_and_a_manual_order_joining_it_resumes_it(setup: _Setup) -> None:
    with _attempting(setup, _Probe()) as owner:
        _until(lambda: bool(setup.network.metadata_added))
        setup.network.deliver(_HASH, _PACK[:2])
        _until(lambda: owner.state.acquisitions[0].content_started)
        for command in ("pause-1", "pause-2"):
            assert owner.handle(_request("set_auto", {"enabled": False}, command_id=command)).ok
        _until(lambda: _HASH in owner.state.pause_owned_transfers)
        _until(lambda: not owner.state.acquisitions[0].action_pending)
        stops: int = setup.network.actions.count((_HASH, "stop"))
        owned: tuple[str, ...] = owner.state.pause_owned_transfers
        assert owner.admit_episode("manual-4", _choice(4)).ok
        _until(lambda: _HASH not in owner.state.pause_owned_transfers)
        _until(lambda: (_HASH, "resume") in setup.network.actions)
        attempt: SubscriptionTarget = _target(owner)

    assert stops == 1
    assert owned == (_HASH,)
    assert attempt.state is TargetState.ATTEMPTING


def test_the_last_satisfied_target_of_a_finished_season_moves_the_subscription_into_history(setup: _Setup) -> None:
    record: SubscriptionRecord = _record(catalog_status="FINISHED", episode_count=3)
    with _attempting(setup, _Probe(), record) as owner:
        _deliver(setup, owner)
        _until(lambda: not owner.state.subscriptions)
        listed: ControlResponse = owner.handle(_request("subscriptions_list", command_id="list"))

    assert listed.result["subscriptions"] == []
    events: tuple[HistoryEvent, ...] = HistoryJournal(setup.store.history_path()).events(_MOMENT)
    assert [item.name for item in events if item.kind is HistoryKind.SUBSCRIPTION_FINISHED] == ["Neko"]
