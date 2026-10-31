from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from test_automation import _await, _completed_library, _owner, _real_service, _request, _serving, _TorrentNetwork
from test_selective_lifecycle import _failed_request

from anishift.application.acquisition import AcquisitionService, TorrentClient, TorrentManagement
from anishift.application.artifacts import create_group_id
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    DeletionOutcome,
    DeletionRestore,
    DeletionStatus,
    PendingDeletion,
    ProcessingRequest,
    ReadyGroup,
    RequestState,
    RestoreOutcome,
    WatchState,
)
from anishift.application.control_views import DeletionPreview, LibraryFileIdentity, decode_view, encode_view
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import RequestOrigin
from anishift.application.library import file_identity, unrecorded_set_id
from anishift.application.watch_state import WatchStateStore
from anishift.errors import ConfigError
from anishift.platform.directory_watch import DirectoryChange
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
        "restore", (RestoreOutcome("ready/01.txt", "tmp/.restore-one/0", "inflight", "pending", True),)
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
            (RestoreOutcome("ready/01.txt", "tmp/.restore-one/0", "refused", "restore_receipt_missing", started),),
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
                RestoreOutcome("ready/01.txt", "tmp/.restore-one/0", "uncertain", "restore_incomplete", True),
                RestoreOutcome("ready/01.pl.txt", "tmp/.restore-two/1"),
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

    owner: AutomationOwner = AutomationOwner(service, store, instance_id="test", restorer=lambda: nullcontext(restore))
    thread: threading.Thread = _serving(owner)
    try:
        owner._restore_files(operation, restore)
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

    owner: AutomationOwner = AutomationOwner(service, store, instance_id="first", recycler=lambda: nullcontext(recycle))
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
    owner = AutomationOwner(service, store, instance_id="second", restorer=lambda: nullcontext(restore))
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
            owner = AutomationOwner(service, store, instance_id="third", restorer=lambda: nullcontext(restore))
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


def test_set_delete_and_undo_each_use_one_native_session_with_per_file_steps(tmp_path: Path) -> None:
    service, store, _state = _completed_library(tmp_path)
    recycled: list[str] = []
    sessions: list[str] = []
    steps: list[tuple[str, bool]] = []
    recycle: Callable[[Path, tuple[int, int, int, int]], RecycleResult] = _parking(tmp_path / ".bin", recycled)

    @contextmanager
    def recycling() -> Iterator[Callable[[Path, tuple[int, int, int, int]], RecycleResult]]:
        sessions.append("recycle")
        yield recycle

    def restore(request: RestoreRequest, check_only: bool) -> RecycleResult:
        steps.append((request.path, check_only))
        return _restore_parked(request, check_only)

    @contextmanager
    def restoring() -> Iterator[Callable[[RestoreRequest, bool], RecycleResult]]:
        sessions.append("restore")
        yield restore

    owner: AutomationOwner = AutomationOwner(
        service, store, instance_id="first", recycler=recycling, restorer=restoring
    )
    thread: threading.Thread = _serving(owner)
    try:
        _delete(owner, "set-01", "delete-1")
        assert _await(lambda: len(recycled) == 2 and not owner._deleting)
        assert sessions == ["recycle"]
        assert owner.handle(_request("deletion_undo", command_id="undo-1")).ok
        assert _await(lambda: not owner._deleting)
        assert sessions == ["recycle", "restore"]
        assert sorted(steps) == [
            ("ready/01.pl.txt", False),
            ("ready/01.pl.txt", True),
            ("ready/01.txt", False),
            ("ready/01.txt", True),
        ]
        assert [check for _path, check in steps] == [True, True, False, False]
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def _failed_row(owner: AutomationOwner, group_id: str, command_id: str) -> dict[str, object] | None:
    response: ControlResponse = owner.handle(_request("status", command_id=command_id))
    materials: list[dict[str, object]] = cast("list[dict[str, object]]", response.result["materials"])
    return next(
        (item for item in materials if item.get("group_id") == group_id and item.get("reason") == "processing_failed"),
        None,
    )


def _inspected(owner: AutomationOwner, group_id: str) -> InspectedSourceGroup | None:
    library: InspectedWorkspace | None = owner._library
    groups: tuple[InspectedSourceGroup, ...] = () if library is None else library.groups
    return next((group for group in groups if group.group_id == group_id), None)


def _failed_group(owner: AutomationOwner, group_id: str, *changed: Path) -> None:
    owner.files_changed(DirectoryChange(paths=changed))
    assert _await(lambda: owner._on_owner(lambda: _inspected(owner, group_id) is not None))
    group: InspectedSourceGroup | None = owner._on_owner(lambda: _inspected(owner, group_id))
    assert group is not None
    failed: ProcessingRequest = _failed_request(group, RequestState.FAILED)
    assert owner._on_owner(lambda: owner._save(replace(owner.state, requests=(failed,))))


def _parking(parked: Path, recycled: list[str]) -> Callable[[Path, tuple[int, int, int, int]], RecycleResult]:
    parked.mkdir()

    def recycle(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
        del identity
        recycled.append(path.name)
        target: Path = parked / path.name
        path.rename(target)
        return RecycleResult("recycled", "recycle_completed", str(target))

    return recycle


def _restore_parked(request: RestoreRequest, check_only: bool) -> RecycleResult:
    path: Path = request.workspace / request.path
    if path.exists():
        return RecycleResult("restored", "restore_completed")
    if check_only:
        return RecycleResult("ready", "restore_ready")
    assert request.receipt is not None
    Path(request.receipt).rename(path)
    return RecycleResult("restored", "restore_completed")


def _delete(owner: AutomationOwner, set_id: str, command_id: str) -> DeletionPreview:
    preview: DeletionPreview = decode_view(
        DeletionPreview, owner.handle(_request("deletion_preview", {"set_id": set_id})).result
    )
    started: ControlResponse = owner.handle(
        _request(
            "deletion_start",
            {"set_id": set_id, "preview_id": preview.preview_id},
            command_id=command_id,
            instance_id="first",
        )
    )
    assert started.ok
    return preview


def test_a_failed_workspace_episode_is_recycled_and_restored_like_a_library_set(tmp_path: Path) -> None:
    service, store, _state = _completed_library(tmp_path)
    source: Path = tmp_path / "02.txt"
    source.write_text("source", encoding="utf-8")
    group_id: str = create_group_id(Path(), "02")
    recycled: list[str] = []
    recycle: Callable[[Path, tuple[int, int, int, int]], RecycleResult] = _parking(tmp_path / ".bin", recycled)
    owner: AutomationOwner = AutomationOwner(
        service,
        store,
        instance_id="first",
        recycler=lambda: nullcontext(recycle),
        restorer=lambda: nullcontext(_restore_parked),
    )
    thread: threading.Thread = _serving(owner)
    try:
        _failed_group(owner, group_id, source)
        row: dict[str, object] | None = _failed_row(owner, group_id, "status-1")
        assert row is not None
        assert row["set_id"] == unrecorded_set_id(group_id)
        preview: DeletionPreview = _delete(owner, str(row["set_id"]), "delete-1")
        assert [item.path for item in preview.files] == ["02.txt"]
        assert _await(lambda: not source.exists() and not owner._deleting)
        assert recycled == ["02.txt"]
        assert _await(lambda: _failed_row(owner, group_id, "status-2") is None)
        assert owner.handle(_request("deletion_undo", command_id="undo-1")).ok
        assert _await(lambda: source.is_file() and not owner._deleting)
        assert source.read_text(encoding="utf-8") == "source"
        assert _await(lambda: _failed_row(owner, group_id, "status-3") is not None)
        assert owner.handle(_request("deletion_undo", command_id="undo-2")).reason == "restore_already_completed"
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_del_on_a_failed_return_of_a_ready_episode_recycles_only_the_returned_file(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    root_id: str = create_group_id(Path(), "01")
    record: ReadyGroup = replace(state.ready_groups[0], set_id=root_id)
    store.save(replace(state, ready_groups=(record,)))
    again: Path = tmp_path / "01.txt"
    again.write_text("again", encoding="utf-8")
    recycled: list[str] = []
    recycle: Callable[[Path, tuple[int, int, int, int]], RecycleResult] = _parking(tmp_path / ".bin", recycled)
    owner: AutomationOwner = AutomationOwner(service, store, instance_id="first", recycler=lambda: nullcontext(recycle))
    thread: threading.Thread = _serving(owner)
    try:
        _failed_group(owner, root_id, tmp_path / "ready/01.txt", again)
        row: dict[str, object] | None = _failed_row(owner, root_id, "status-1")
        assert row is not None
        assert row["set_id"] == unrecorded_set_id(root_id)
        preview: DeletionPreview = _delete(owner, str(row["set_id"]), "delete-1")
        assert [item.path for item in preview.files] == ["01.txt"]
        assert _await(lambda: not again.exists() and not owner._deleting)
        assert recycled == ["01.txt"]
        assert (tmp_path / "ready/01.txt").is_file()
        assert (tmp_path / "ready/01.pl.txt").is_file()
        assert owner.handle(_request("library_open", {"set_id": root_id})).ok
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_a_failed_episode_inside_the_library_offers_no_unrecorded_scope(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    record: ReadyGroup = state.ready_groups[0]
    other: Path = tmp_path / "02.txt"
    other.write_text("source", encoding="utf-8")
    owner: AutomationOwner = AutomationOwner(service, store, instance_id="first")
    thread: threading.Thread = _serving(owner)
    try:
        _failed_group(owner, record.group_id, tmp_path / "ready/01.txt", other)
        row: dict[str, object] | None = _failed_row(owner, record.group_id, "status-1")
        assert row is not None
        assert "set_id" not in row
        refused: ControlResponse = owner.handle(
            _request("deletion_preview", {"set_id": unrecorded_set_id(record.group_id)})
        )
        assert refused.reason == "library_set_missing"
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_a_failed_workspace_episode_held_by_its_torrent_is_refused(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    source: Path = tmp_path / "02.txt"
    source.write_text("source", encoding="utf-8")
    group_id: str = create_group_id(Path(), "02")
    owned: AcquisitionConfirmation = AcquisitionConfirmation(
        "download", "hash", "", ("02.txt",), AcquisitionState.COMPLETE, RequestOrigin.USER, None, None, "now"
    )
    store.save(replace(state, acquisitions=(owned,)))
    owner: AutomationOwner = AutomationOwner(service, store, instance_id="first")
    thread: threading.Thread = _serving(owner)
    try:
        _failed_group(owner, group_id, source)
        refused: ControlResponse = owner.handle(_request("deletion_preview", {"set_id": unrecorded_set_id(group_id)}))
        assert refused.reason == "library_source_held"
        assert source.is_file()
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()
