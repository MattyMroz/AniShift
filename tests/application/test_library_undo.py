from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_automation import _await, _completed_library, _owner, _real_service, _request, _serving, _TorrentNetwork

from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    DeletionOutcome,
    DeletionRestore,
    DeletionStatus,
    PendingDeletion,
    ReadyGroup,
    RestoreOutcome,
    WatchState,
)
from anishift.application.control_views import DeletionPreview, LibraryFileIdentity, decode_view, encode_view
from anishift.application.intents import RequestOrigin
from anishift.application.library import file_identity
from anishift.application.watch_state import WatchStateStore
from anishift.errors import ConfigError
from anishift.platform.local_control import ControlResponse
from anishift.platform.recycle import RecycleResult, RestoreRequest
from anishift.services.torrents import parse_release_name


@pytest.mark.parametrize("state", [AcquisitionState.COMPLETE, AcquisitionState.UNCERTAIN])
@pytest.mark.parametrize("released", [False, True])
def test_library_deletion_needs_complete_and_persisted_release(
    tmp_path: Path, state: AcquisitionState, released: bool
) -> None:
    service, store, original = _completed_library(tmp_path)
    network: _TorrentNetwork = _TorrentNetwork()
    if released:
        network.released.append(frozenset({"hash"}))
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        torrent_management=cast("TorrentManagement", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service.close()
    service = _real_service(tmp_path, acquisition=acquisition)
    owned: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "HASH", "", ("ready/01.txt",), state, RequestOrigin.USER, None, None, "now"
    )
    store.save(replace(original, acquisitions=(owned,)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": "set-01"}))
        assert response.ok is (released and state is AcquisitionState.COMPLETE)
        assert owner.state.acquisitions == (owned,)
        assert network.released == ([frozenset({"hash"})] if released else [])
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_latest_undo_uses_append_order_and_keeps_uncertain_barrier(tmp_path: Path) -> None:
    service, store, original = _completed_library(tmp_path)
    recycled: PendingDeletion = PendingDeletion(
        "first",
        "set-01",
        "2099",
        (("ready/01.txt", 1, 2),),
        recycled=("ready/01.txt",),
        identities=(("ready/01.txt", 3, 4),),
        outcomes=(DeletionOutcome("ready/01.txt", DeletionStatus.RECYCLED, "ok", "exact-receipt"),),
    )
    uncertain: PendingDeletion = replace(
        recycled,
        operation_id="second",
        requested_at="1900",
        recycled=(),
        outcomes=(DeletionOutcome("ready/01.txt", DeletionStatus.UNCERTAIN, "unknown"),),
    )
    refused: PendingDeletion = replace(
        uncertain, operation_id="third", outcomes=(DeletionOutcome("ready/01.txt", DeletionStatus.REFUSED, "refused"),)
    )
    store.save(replace(original, pending_deletions=(recycled, uncertain, refused)))
    owner: AutomationOwner = _owner(service, store)
    assert owner._latest_deletion() == uncertain
    service.close()


def test_release_read_does_not_block_owner_and_stale_proof_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, store, original = _completed_library(tmp_path)
    owned: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "hash", "", ("ready/01.txt",), AcquisitionState.COMPLETE, RequestOrigin.USER, None, None, "now"
    )
    store.save(replace(original, acquisitions=(owned,)))
    owner: AutomationOwner = _owner(service, store)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    responses: list[ControlResponse] = []

    def proof(acquisitions: tuple[AcquisitionConfirmation, ...]) -> frozenset[str]:
        assert acquisitions == (owned,)
        entered.set()
        assert release.wait(5)
        return frozenset({"hash"})

    monkeypatch.setattr(owner, "_read_released", proof)
    thread: threading.Thread = _serving(owner)
    caller: threading.Thread = threading.Thread(
        target=lambda: responses.append(owner.handle(_request("deletion_preview", {"set_id": "set-01"})))
    )
    caller.start()
    try:
        assert entered.wait(5)
        assert owner.handle(_request("status")).ok
        owner._on_owner(
            lambda: owner._save(replace(owner.state, acquisitions=(replace(owned, state=AcquisitionState.UNCERTAIN),)))
        )
        release.set()
        caller.join(5)
        assert len(responses) == 1
        assert responses[0].reason == "library_scope_changed"
    finally:
        release.set()
        caller.join(5)
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_restore_schema_two_roundtrip_and_strict_scope(tmp_path: Path) -> None:
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    operation: PendingDeletion = PendingDeletion(
        "delete", "set", "now", (("ready/01.txt", 1, 2),), identities=(("ready/01.txt", 3, 4),)
    )
    state: WatchState = WatchState(pending_deletions=(operation,))
    store.save(state)
    assert '"restore"' not in (tmp_path / "state.json").read_text()
    restored: DeletionRestore = DeletionRestore(
        "restore", (RestoreOutcome("ready/01.txt", "temp/.restore-one/0", "inflight", "pending", True),)
    )
    state = replace(state, pending_deletions=(replace(operation, restore=restored),))
    store.save(state)
    assert store.load() == state
    with pytest.raises(ValueError, match="exactly the original"):
        replace(operation, restore=replace(restored, outcomes=(replace(restored.outcomes[0], path="other.txt"),)))
    with pytest.raises(ValueError, match="every file result"):
        replace(restored, completed=True)
    document: str = (tmp_path / "state.json").read_text()
    (tmp_path / "state.json").write_text(document.replace('"started": true', '"started": "yes"'))
    with pytest.raises(ConfigError):
        store.load()


@pytest.mark.parametrize("started", [False, True])
def test_restore_refusal_protects_only_unsettled_native_effects_after_restart(tmp_path: Path, started: bool) -> None:
    service, store, state = _completed_library(tmp_path)
    record: ReadyGroup = state.ready_groups[0]
    operation: PendingDeletion = PendingDeletion(
        "delete",
        record.set_id,
        "now",
        (("ready/01.txt", 1, 2),),
        identities=(("ready/01.txt", 3, 4),),
        restore=DeletionRestore(
            "restore",
            (RestoreOutcome("ready/01.txt", "temp/.restore-one/0", "refused", "restore_receipt_missing", started),),
        ),
    )
    owned: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "hash", "", ("ready/01.txt",), AcquisitionState.COMPLETE, RequestOrigin.USER, None, None, "now"
    )
    store.save(replace(state, pending_deletions=(operation,), acquisitions=(owned,)))
    owner: AutomationOwner = _owner(service, store)
    try:
        assert (record.group_id in owner._deleting_groups()) is started
        assert owner._protected_acquisition(owned) is started
        owner._deleting[operation.operation_id] = record.set_id
        assert record.group_id in owner._deleting_groups()
        assert owner._protected_acquisition(owned)
    finally:
        service.close()


def test_fresh_exact_bin_proof_settles_previous_noop_before_other_preflight_refusal(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    operation: PendingDeletion = PendingDeletion(
        "delete",
        "set-01",
        "now",
        (("ready/01.txt", 1, 2), ("ready/01.pl.txt", 1, 2)),
        identities=(("ready/01.txt", 3, 4), ("ready/01.pl.txt", 3, 5)),
        restore=DeletionRestore(
            "restore",
            (
                RestoreOutcome("ready/01.txt", "temp/.restore-one/0", "uncertain", "restore_incomplete", True),
                RestoreOutcome("ready/01.pl.txt", "temp/.restore-two/1"),
            ),
        ),
    )
    store.save(replace(state, pending_deletions=(operation,)))

    def restore(request: RestoreRequest, check_only: bool) -> RecycleResult:
        assert check_only
        return (
            RecycleResult("ready", "restore_ready_bin")
            if request.path == "ready/01.txt"
            else RecycleResult("refused", "restore_receipt_missing")
        )

    owner: AutomationOwner = AutomationOwner(service, store, instance_id="test", restorer=restore)
    thread: threading.Thread = _serving(owner)
    try:
        owner._restore_files(operation)
        saved: DeletionRestore | None = store.load().pending_deletions[-1].restore
        assert saved is not None
        assert not saved.unsettled
        assert not saved.completed
        assert saved.outcomes[0].status == "prepared"
        assert not saved.outcomes[0].started
        assert saved.outcomes[1].reason == "restore_receipt_missing"
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


@pytest.mark.parametrize("collision", [False, True])
@pytest.mark.parametrize("partial", [False, True])
def test_library_undo_survives_restart_and_never_falls_back(tmp_path: Path, collision: bool, partial: bool) -> None:  # noqa: PLR0915
    service, store, original = _completed_library(tmp_path)
    parked: Path = tmp_path / ".synthetic-bin"
    parked.mkdir()
    calls: list[str] = []

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        del identity
        if partial and path.name == "01.txt":
            return RecycleResult("refused", "recycle_refused")
        target: Path = parked / path.name
        path.rename(target)
        return RecycleResult("recycled", "recycle_completed", str(target))

    def restore(request: RestoreRequest, check_only: bool) -> RecycleResult:
        path: Path = request.workspace / request.path
        current: LibraryFileIdentity | None = file_identity(request.workspace, request.path)
        if path.exists():
            return (
                RecycleResult("restored", "restore_completed")
                if current is not None
                and (current.size, current.modified_ns, current.device, current.inode) == request.identity
                and (request.started or request.receipt is None)
                else RecycleResult("refused", "restore_destination_occupied")
            )
        if check_only:
            return RecycleResult("ready", "restore_ready")
        saved: DeletionRestore | None = store.load().pending_deletions[-1].restore
        assert saved is not None
        assert any(item.path == request.path and item.status == "inflight" for item in saved.outcomes)
        assert request.receipt is not None
        calls.append(request.path)
        Path(request.receipt).rename(path)
        return RecycleResult("restored", "restore_completed")

    owner: AutomationOwner = AutomationOwner(service, store, instance_id="first", recycler=recycle)
    thread: threading.Thread = _serving(owner)
    try:
        preview: DeletionPreview = decode_view(
            DeletionPreview, owner.handle(_request("deletion_preview", {"set_id": "set-01"})).result
        )
        assert owner.handle(
            _request("deletion_start", {"set_id": "set-01", "preview_id": preview.preview_id}, instance_id="first")
        ).ok
        assert _await(
            lambda: (
                bool(owner.state.pending_deletions)
                and len(owner.state.pending_deletions[-1].outcomes) == 2
                and not owner._deleting
            )
        )
    finally:
        owner.request_shutdown()
        thread.join(5)
    deleted: PendingDeletion = store.load().pending_deletions[-1]
    foreign: Path = tmp_path / "ready/01.pl.txt"
    if collision:
        foreign.write_bytes(b"foreign")
    owner = AutomationOwner(service, store, instance_id="second", restorer=restore)
    thread = _serving(owner)
    try:
        assert owner.handle(_request("deletion_undo", command_id="undo-1")).ok
        assert _await(lambda: not owner._deleting)
        if collision:
            assert foreign.read_bytes() == b"foreign"
            assert calls == []
            assert owner.handle(_request("deletion_preview", {"set_id": "set-01"})).ok
            owner.request_shutdown()
            thread.join(5)
            owner = AutomationOwner(service, store, instance_id="third", restorer=restore)
            thread = _serving(owner)
            foreign.rename(tmp_path / "foreign-preserved")
            assert owner.handle(_request("deletion_undo", command_id="undo-2")).ok
            assert _await(lambda: not owner._deleting)
        saved: WatchState = store.load()
        assert saved.pending_deletions[-1].restore is not None
        assert saved.pending_deletions[-1].restore.completed
        assert saved.pending_deletions[-1].outcomes == deleted.outcomes
        assert saved.products == original.products
        assert saved.ready_groups == original.ready_groups
        assert len(calls) == (1 if partial else 2)
        assert owner.handle(_request("deletion_undo", command_id="undo-3")).reason == "restore_already_completed"
        assert owner.handle(_request("library_open", {"set_id": "set-01"})).ok
        identity: LibraryFileIdentity | None = file_identity(tmp_path, "ready/01.txt")
        assert identity is not None
        assert owner.handle(_request("library_file_open", {"set_id": "set-01", "file": encode_view(identity)})).ok
        assert not owner.handle(
            _request("library_file_open", {"set_id": "set-01", "file": encode_view(replace(identity, inode=0))})
        ).ok
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()
