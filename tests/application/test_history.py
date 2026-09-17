from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from fakes import CollectingRunSink, FakeTranslationService, write_text_source
from pydantic import TypeAdapter
from test_automation import (
    _await,
    _completed_library,
    _owned,
    _owner,
    _real_service,
    _request,
    _serving,
    _TorrentNetwork,
)
from test_service import _panel_owner, _service, _wait_for_resident

import anishift.application.automation as automation_module
import anishift.cli.interactive.state as state_module
from anishift.application.acquisition import AcquisitionService, ReleaseChoice, TorrentClient, TorrentManagement
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AutomationPolicy,
    ProcessingRequest,
    ProductConfirmation,
    ReadyGroup,
    RequestState,
    Reservation,
    SourceSelection,
    WatchState,
)
from anishift.application.control_views import RetryProposal, encode_view
from anishift.application.discovery import discover_groups
from anishift.application.history import HistoryEvent, HistoryJournal, HistoryKind
from anishift.application.intents import AutoPreset, ProductIntent, ProductKind, RequestOrigin
from anishift.application.ready import ReadyMove, ReadyStore
from anishift.application.service import AppService
from anishift.application.subscriptions import (
    EpisodeOrder,
    EpisodeState,
    Subscription,
    SubscriptionService,
    SubscriptionStore,
)
from anishift.application.watch_state import WatchStateStore
from anishift.cli.interactive.manual import ManualController, materialize_intent
from anishift.cli.interactive.state import StateController, StateResult
from anishift.errors import ConfigError
from anishift.platform.local_control import ControlError, ControlResponse
from anishift.services.torrents import Release, parse_release_name
from anishift.services.torrents.types import TorrentFile


def test_startup_save_failure_does_not_keep_reservations_from_a_dead_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service: AppService = _real_service(tmp_path)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    old: Reservation = Reservation("group", (), "dead-client", datetime.now(UTC).isoformat())
    store.save(WatchState(reservations=(old,)))

    def fail_save(_state: WatchState) -> None:
        raise OSError("synthetic startup write failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "save", fail_save)
        owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.state.reservations == ()
        assert store.load().reservations == (old,)
        response: ControlResponse = owner.handle(
            _request("reserve", {"client_id": "new-client", "group_ids": ["group"]})
        )
        assert response.ok, response
        assert [item.client_id for item in store.load().reservations] == ["new-client"]
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()
    assert not thread.is_alive()


def test_torn_tail_next_append_and_restart_preserve_prior_records_and_receipt_identity(tmp_path: Path) -> None:
    now: datetime = datetime.now(UTC)
    path: Path = tmp_path / "history.jsonl"
    journal: HistoryJournal = HistoryJournal(path)
    first: HistoryEvent = HistoryEvent.create("a", "run-a", now.isoformat(), HistoryKind.SUCCESS, "01.txt")
    second: HistoryEvent = HistoryEvent.create("b", "run-b", now.isoformat(), HistoryKind.ERROR, "02.txt")
    assert journal.append(first, now)
    with path.open("ab") as stream:
        stream.write(b'{"event_id":"unfinished-\xe2')
    restarted: HistoryJournal = HistoryJournal(path)
    assert restarted.append(second, now)
    assert not restarted.append(replace(first, occurred_at=(now + timedelta(seconds=1)).isoformat()), now)
    assert HistoryJournal(path).events(now) == (first, second)
    assert len(path.read_bytes().splitlines()) == 2


def test_rotation_search_and_latest_fifty_group_multiple_attempts_without_touching_owner_state(tmp_path: Path) -> None:
    now: datetime = datetime.now(UTC)
    path: Path = tmp_path / "history.jsonl"
    journal: HistoryJournal = HistoryJournal(path)
    for index in range(65):
        assert journal.append(
            HistoryEvent.create(
                str(index),
                f"run-{index}",
                (now + timedelta(seconds=index)).isoformat(),
                HistoryKind.SUCCESS,
                f"Episode {index:02d}",
            ),
            now,
        )
    assert journal.append(
        HistoryEvent.create(
            "64",
            "run-64",
            (now + timedelta(seconds=66)).isoformat(),
            HistoryKind.ERROR,
            "Episode 64",
            attempt=2,
        ),
        now,
    )
    assert len(journal.materials(now)) == 50
    assert journal.materials(now)[0].kind is HistoryKind.ERROR
    assert [item.name for item in journal.materials(now, "Episode 00")] == ["Episode 00"]
    service, store, state = _completed_library(tmp_path / "library")
    service.close()
    before: bytes = (tmp_path / "library" / "state.json").read_bytes()
    assert journal.materials(now + timedelta(days=31)) == ()
    assert path.read_bytes() == b""
    assert (tmp_path / "library" / "state.json").read_bytes() == before
    assert store.load() == state


def test_corrupt_middle_is_preserved_and_not_reread_or_silently_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now: datetime = datetime.now(UTC)
    path: Path = tmp_path / "history.jsonl"
    event: HistoryEvent = HistoryEvent.create("group", "run", now.isoformat(), HistoryKind.SUCCESS, "Book")
    row: bytes = TypeAdapter(HistoryEvent).dump_json(event) + b"\n"
    damaged: bytes = row + b'{"broken":\n' + row
    path.write_bytes(damaged)
    reads: list[Path] = []
    read_bytes: Callable[[Path], bytes] = Path.read_bytes

    def track_read(candidate: Path) -> bytes:
        reads.append(candidate)
        return read_bytes(candidate)

    journal: HistoryJournal = HistoryJournal(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", track_read)
        for _attempt in range(3):
            assert journal.materials(now) == ()
            assert journal.problem == "history_corrupt"
            assert not journal.append(event, now)
    assert reads == [path]
    assert path.read_bytes() == damaged
    empty: HistoryJournal = HistoryJournal(tmp_path / "empty.jsonl")
    assert empty.materials(now) == ()
    assert empty.problem is None


@pytest.mark.parametrize("kind", [HistoryKind.ORDER, HistoryKind.DOWNLOAD, HistoryKind.REGENERATION])
def test_explicit_search_groups_nonterminal_boundaries_without_changing_default_history(
    tmp_path: Path, kind: HistoryKind
) -> None:
    now: datetime = datetime.now(UTC)
    journal: HistoryJournal = HistoryJournal(tmp_path / "history.jsonl")
    completed: HistoryEvent = HistoryEvent.create("group", "old", now.isoformat(), HistoryKind.SUCCESS, "Book")
    boundary: HistoryEvent = HistoryEvent.create("group", "new", (now + timedelta(seconds=1)).isoformat(), kind, "Book")
    assert journal.append(completed, now)
    assert journal.append(boundary, now)
    assert journal.materials(now) == (completed,)
    assert journal.materials(now, "book") == (boundary,)


def test_recovered_terminal_time_is_admission_time_with_stable_identity_and_retention(tmp_path: Path) -> None:
    now: datetime = datetime.now(UTC)
    admitted: datetime = now - timedelta(days=2)
    request: ProcessingRequest = ProcessingRequest(
        "failed-run",
        1,
        ("Book",),
        {"Book": ()},
        RequestOrigin.USER,
        SourceSelection.AUTO,
        None,
        {},
        RequestState.FAILED,
        1,
        admitted.isoformat(),
    )
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    store.save(WatchState(requests=(request,)))
    service: AppService = _real_service(tmp_path)
    with closing(service), _panel_owner(service, tmp_path) as (session, _store):
        event: HistoryEvent = session.history()[0]
        assert event.occurred_at == admitted.isoformat()
        assert event.recovered_from_admission
        original: HistoryEvent = HistoryEvent.create("Book", "failed-run", now.isoformat(), HistoryKind.ERROR, "Book")
        assert event.event_id == original.event_id
        old_document: dict[str, object] = encode_view(original)
        old_document.pop("recovered_from_admission")
        assert not TypeAdapter(HistoryEvent).validate_python(old_document).recovered_from_admission
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            frame: str = controller.render(160, 30).plain
            assert "odtworzony zapis · czas przyjęcia" in frame
            assert admitted.isoformat()[:19].replace("T", " ") in frame
        finally:
            controller.close()
            controller._thread.join(5)
    assert HistoryJournal(store.history_path()).materials(admitted + timedelta(days=31)) == ()


def test_download_without_processing_is_searchable_but_never_opens_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_text_source(tmp_path / "Book.txt", "Downloaded source")
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "download",
        "9",
        "",
        ("Book.txt",),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        None,
        None,
        datetime.now(UTC).isoformat(),
        complete_files=("Book.txt",),
    )
    WatchStateStore(tmp_path / ".control" / "state.json").save(
        WatchState(policy=AutomationPolicy(auto_enabled=False), acquisitions=(item,))
    )
    opened: list[Path] = []
    monkeypatch.setattr(state_module, "_open_path", lambda path, **_kwargs: opened.append(path))
    service: AppService = _real_service(tmp_path)
    with closing(service), _panel_owner(service, tmp_path) as (session, store):
        assert session.history() == ()
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            controller.handle_key("text:s")
            controller.handle_key("paste:Book")
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            assert [event.kind for event in controller._history_items] == [HistoryKind.DOWNLOAD]
            assert "pobrano źródło" in controller.render(120, 30).plain
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            assert opened == []
            assert (tmp_path / "Book.txt").read_text(encoding="utf-8") == "Downloaded source"
            controller.handle_key("escape")
            assert not controller._history_open
            assert controller._tab == state_module._Tab.PROGRESS
            assert store.load().requests == ()
        finally:
            controller.close()
            controller._thread.join(5)


@pytest.mark.parametrize("broken", [None, 0, -1, True, "12"])
def test_retained_reference_roundtrip_and_invalid_half_references_are_rejected(tmp_path: Path, broken: object) -> None:
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    item: AcquisitionConfirmation = AcquisitionConfirmation(
        "download",
        "ab" * 20,
        "",
        (),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        "removed",
        "2",
        datetime.now(UTC).isoformat(),
        nyaa_release_id=12,
        release_title="Original season release",
    )
    store.save(WatchState(acquisitions=(item,)))
    assert store.load().acquisitions == (item,)
    document: dict[str, object] = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    row: dict[str, object] = cast("list[dict[str, object]]", document["acquisitions"])[0]
    row["nyaa_release_id"] = broken
    (tmp_path / "state.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigError):
        store.load()
    row.pop("nyaa_release_id")
    row.pop("release_title")
    row.pop("previous_operation_id")
    (tmp_path / "state.json").write_text(json.dumps(document), encoding="utf-8")
    assert store.load().acquisitions[0] == replace(item, nyaa_release_id=None, release_title=None)


@pytest.mark.parametrize(
    "url",
    [
        "https://nyaa.si/download/12.torrent",
        "https://elsewhere.test/download/12.torrent",
        "https://nyaa.si.evil.test/download/12.torrent",
        "https://user:password@nyaa.si/download/12.torrent",
        "https://nyaa.si/download/12.torrent?token=secret",
        "https://nyaa.si/download/12.torrent#fragment",
        "https://nyaa.si:443/download/12.torrent",
        "http://nyaa.si/download/12.torrent",
    ],
)
def test_admission_only_retains_source_qualified_public_references(tmp_path: Path, url: str) -> None:
    network: _TorrentNetwork = _TorrentNetwork()
    release: Release = replace(network.releases[0], torrent_url=url)
    network.releases = (release,)
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        response: ControlResponse = owner.handle(
            _request(
                "download",
                {
                    "choices": [encode_view(ReleaseChoice(release, parse_release_name(release.title)))],
                },
            )
        )
        assert response.ok
        stored: AcquisitionConfirmation = store.load().acquisitions[0]
        trusted: bool = url == "https://nyaa.si/download/12.torrent"
        assert stored.nyaa_release_id == (12 if trusted else None)
        assert stored.release_title == (release.title if trusted else None)
        assert network.added == [release.info_hash]
        assert url not in store.history_path().read_text(encoding="utf-8")
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("failure", ["none", "before_send", "after_send", "wrong_hash"])
def test_explicit_reacquire_retains_deleted_subscription_provenance_and_never_resends_receipt(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    monkeypatch.setattr(automation_module, "TRANSFER_CHECK_INTERVAL_S", 0.01)
    network: _TorrentNetwork = _TorrentNetwork()
    release: Release = replace(network.releases[0], torrent_url="https://nyaa.si/download/12.torrent")
    network.releases = (replace(release, info_hash="other") if failure == "wrong_hash" else release,)
    network.entries = (TorrentFile(0, "Pack/09.mkv", 4, 0.0, 1),)
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    original: AcquisitionConfirmation = AcquisitionConfirmation(
        "previous",
        release.info_hash,
        "",
        (),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        "removed",
        "2",
        datetime.now(UTC).isoformat(),
        nyaa_release_id=12,
        release_title=release.title,
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(original,)))
    command = _request("reacquire", {"operation_id": "previous"}, command_id="repeat-once")

    def fail_before_send(*_args: object) -> None:
        assert len(store.load().acquisitions) == 2
        raise OSError("synthetic interrupted send")

    if failure == "before_send":
        monkeypatch.setattr(acquisition, "reacquire", fail_before_send)
    network.lose_response = failure == "after_send"
    for _restart in range(2):
        owner: AutomationOwner = _owner(service, store)
        thread: threading.Thread = _serving(owner)

        def content_started(current: AutomationOwner = owner) -> bool:
            return current.state.acquisitions[1].content_started

        try:
            if _restart == 0:
                proposal: ControlResponse = owner.handle(_request("retry_prepare", {"material_id": "previous"}))
                assert proposal.ok
                assert proposal.result["action"] == "reacquire"
                assert network.added == []
            owner.handle(command)
            replay: ControlResponse = owner.handle(command)
            assert replay.ok
            assert len(owner.state.acquisitions) == 2
            if failure == "none" or (failure == "after_send" and _restart == 1):
                assert _await(content_started)
        finally:
            owner.request_shutdown()
            thread.join(5)
        assert not thread.is_alive()
    service.close()
    repeated: AcquisitionConfirmation = store.load().acquisitions[1]
    assert repeated.episode == "2"
    assert repeated.previous_operation_id == original.operation_id
    assert repeated.info_hash == original.info_hash
    assert store.load().acquisitions[0] == original
    assert len(network.added) == (0 if failure == "before_send" else 1)
    if failure in {"before_send", "wrong_hash"}:
        assert repeated.state is AcquisitionState.UNCERTAIN
        assert network.started == []
    else:
        assert network.started == [original.info_hash]
        assert repeated.file_layout == ((0, "09.mkv", 4),)
        assert repeated.directory == ""


def test_history_redacts_public_labels_and_orders_instants_across_timezones(tmp_path: Path) -> None:
    now: datetime = datetime.now(UTC)
    journal: HistoryJournal = HistoryJournal(tmp_path / "history.jsonl")
    earlier: HistoryEvent = HistoryEvent.create(
        "earlier",
        "one",
        "2026-09-16T23:00:00+02:00",
        HistoryKind.SUCCESS,
        "Title https://nyaa.si/download/12.torrent?password=private C:\\private\\source.txt api_key=hidden",
    )
    later: HistoryEvent = HistoryEvent.create("later", "two", "2026-09-16T21:30:00+00:00", HistoryKind.ERROR, "Later")
    assert journal.append(earlier, now)
    assert journal.append(later, now)
    assert [item.material_id for item in journal.materials(now)] == ["later", "earlier"]
    content: str = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    for secret in ("https://", "private", "hidden", "source.txt"):
        assert secret not in content


def test_owner_startup_rotates_history_without_losing_problem_ready_or_download_dedup(tmp_path: Path) -> None:
    service, store, state = _completed_library(tmp_path)
    service.close()
    now: datetime = datetime.now(UTC)
    before: datetime = now - timedelta(days=31)
    acquisition: AcquisitionConfirmation = AcquisitionConfirmation(
        "download",
        "9",
        "",
        ("missing.mkv",),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        "removed",
        "2",
        before.isoformat(),
        complete_files=("missing.mkv",),
    )
    request: ProcessingRequest = ProcessingRequest(
        "failed-run",
        1,
        ("failed-group",),
        {"failed-group": ()},
        RequestOrigin.USER,
        SourceSelection.AUTO,
        None,
        {},
        RequestState.FAILED,
        3,
        before.isoformat(),
        problem="retained problem",
    )
    state = replace(state, policy=AutomationPolicy(auto_enabled=True), acquisitions=(acquisition,), requests=(request,))
    store.save(state)
    assert HistoryJournal(store.history_path()).append(
        HistoryEvent.create(
            "failed-group",
            request.request_id,
            before.isoformat(),
            HistoryKind.ERROR,
            "Old material",
        ),
        before,
    )
    network: _TorrentNetwork = _TorrentNetwork()
    downloads: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service = _real_service(tmp_path, acquisition=downloads)
    owner: AutomationOwner = AutomationOwner(service, store, instance_id="rotated", clock=lambda: now)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("history", instance_id="rotated")).result == {"items": []}
        assert store.history_path().read_bytes() == b""
        assert owner.state.requests == (request,)
        assert owner.state.acquisitions == (acquisition,)
        assert owner.state.ready_groups == state.ready_groups
        choice: ReleaseChoice = ReleaseChoice(network.releases[0], parse_release_name(network.releases[0].title))
        assert owner.handle(_request("download", {"choices": [encode_view(choice)]}, instance_id="rotated")).ok
        assert network.added == []
        assert owner.state.acquisitions == (acquisition,)
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


def test_legacy_acquisition_cannot_be_retried_by_inventing_a_release_reference(tmp_path: Path) -> None:
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
    )
    service: AppService = _real_service(tmp_path, acquisition=acquisition)
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    original: AcquisitionConfirmation = AcquisitionConfirmation(
        "old",
        "9",
        "",
        (),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        "removed",
        "2",
        datetime.now(UTC).isoformat(),
    )
    store.save(WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(original,)))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        proposal: ControlResponse = owner.handle(_request("retry_prepare", {"material_id": "old"}))
        assert proposal.reason == "retry_reference_missing"
        assert not owner.handle(_request("reacquire", {"operation_id": "old"})).ok
        assert owner.state.command_receipts == ()
        assert owner.state.acquisitions == (original,)
        assert network.added == []
    finally:
        owner.request_shutdown()
        thread.join(5)
        service.close()


@pytest.mark.parametrize("failure", ["unavailable", "corrupt"])
def test_failed_history_append_does_not_fail_execution_or_repeat_confirmed_work(tmp_path: Path, failure: str) -> None:
    write_text_source(tmp_path / "Book.txt", "Original text")
    translation: FakeTranslationService = FakeTranslationService()
    service: AppService = _service(tmp_path, translation)
    unavailable: Path = tmp_path / ".control" / "history.jsonl"
    unavailable.parent.mkdir(parents=True)
    if failure == "unavailable":
        unavailable.mkdir()
    else:
        unavailable.write_bytes(b"{}\n{}\n")

    with closing(service), _panel_owner(service, tmp_path, ready=True) as (session, store):
        with pytest.raises(ControlError) as refused:
            session.history()
        assert refused.value.reason == f"history_{failure}"
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            for _frame in range(3):
                controller.handle_key("down")
                frame: str = controller.render(120, 30).plain
                assert "Historia niedostępna" in frame
                assert "przetwarzanie działa dalej" in frame
                assert "Brak zadań" not in frame
        finally:
            controller.close()
            controller._thread.join(5)
        groups: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(groups)
        result = session.execute(
            session.plan_auto(
                groups,
                AutoPreset(
                    "once",
                    "Once",
                    ProductIntent(frozenset({ProductKind.FULL_PL})),
                ),
            ),
            CollectingRunSink(),
        )
        assert result.succeeded
        assert len(translation.calls) == 1
        assert len(store.load().ready_groups) == 1
    if failure == "unavailable":
        unavailable.rmdir()
    else:
        assert unavailable.read_bytes() == b"{}\n{}\n"
        unavailable.unlink()
    restarted: AppService = _service(tmp_path, translation)
    with closing(restarted), _panel_owner(restarted, tmp_path, ready=True) as (session, _store):
        assert len(session.history()) == 1
        assert session.history()[0].kind is HistoryKind.SUCCESS
        assert len(translation.calls) == 1


def test_history_retry_render_and_back_preserve_selected_material_and_tab_context(tmp_path: Path) -> None:
    service, _store, state = _completed_library(tmp_path, ("01", "02", "03"))
    WatchStateStore(tmp_path / ".control" / "state.json").save(
        replace(state, policy=AutomationPolicy(auto_enabled=True))
    )
    now: datetime = datetime.now(UTC)
    journal: HistoryJournal = HistoryJournal(tmp_path / ".control" / "history.jsonl")
    for group in state.ready_groups:
        assert journal.append(
            HistoryEvent.create(
                group.set_id,
                "completed",
                now.isoformat(),
                HistoryKind.SUCCESS,
                group.stem,
            ),
            now,
        )
    with closing(service), _panel_owner(service, tmp_path) as (session, store):
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            controller.handle_key("down")
            selected: str = controller._history_items[controller._selected].material_id
            controller.handle_key("text:p")
            assert _await(lambda: not controller._busy)
            assert controller._retry is not None
            assert controller._retry.material_id == selected
            controller.render(80, 24)
            controller.handle_key("escape")
            assert controller._history_items[controller._selected].material_id == selected
            controller.handle_key("right")
            assert _await(lambda: not controller._busy)
            controller.handle_key("left")
            assert controller._history_open
            assert controller._history_items[controller._selected].material_id == selected
            assert store.load().requests == ()
        finally:
            controller.close()
            controller._thread.join(5)


@pytest.mark.parametrize("ready", [False, True])
def test_single_highlight_subscription_retry_opens_actual_selected_manual_after_relocation(
    tmp_path: Path,
    *,
    ready: bool,
) -> None:
    write_text_source(tmp_path / "Book.txt", "Original text")
    write_text_source(tmp_path / "Other.txt", "Unrelated text")
    network: _TorrentNetwork = _TorrentNetwork()
    acquisition: AcquisitionService = AcquisitionService(
        source=network,
        client=cast("TorrentClient", network),
        workspace_root=tmp_path,
        parse_name=parse_release_name,
        torrent_management=cast("TorrentManagement", network),
    )
    subscription: Subscription = Subscription(
        "series",
        "query",
        "Series",
        "Group",
        Decimal(2),
        1080,
        frozenset({"old"}),
        datetime.now(UTC).isoformat(),
        None,
        enabled=False,
        episodes=(
            EpisodeOrder(Decimal(2), state=EpisodeState.COMPLETE, acquisition_id="old"),
            EpisodeOrder(Decimal(3), state=EpisodeState.COMPLETE, acquisition_id="gone"),
        ),
        future_from=None,
    )
    subscriptions: SubscriptionService = SubscriptionService(
        store=SubscriptionStore(tmp_path / ".subscriptions.json"),
        acquisition=acquisition,
    )
    SubscriptionStore(tmp_path / ".subscriptions.json").save((subscription,))
    confirmation: AcquisitionConfirmation = AcquisitionConfirmation(
        "old",
        "old",
        "",
        ("Book.txt",),
        AcquisitionState.COMPLETE,
        RequestOrigin.USER,
        "series",
        "2",
        datetime.now(UTC).isoformat(),
        complete_files=("Book.txt",),
    )
    WatchStateStore(tmp_path / ".control" / "state.json").save(
        WatchState(
            policy=AutomationPolicy(auto_enabled=True),
            acquisitions=(confirmation,),
        )
    )
    translation: FakeTranslationService = FakeTranslationService()
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    service: AppService = _service(tmp_path, translation, acquisition=acquisition, subscriptions=subscriptions)
    with closing(service), _panel_owner(service, tmp_path, ready=ready) as (session, store):
        groups: tuple[str, ...] = tuple(
            group.group_id for group in session.discover().groups if group.source.stem == "Book"
        )
        session.reserve(groups)
        assert session.execute(session.plan_auto(groups, preset), CollectingRunSink()).succeeded
        with pytest.raises(ControlError) as mixed:
            session.subscription_retry_proposal("series", (Decimal(2), Decimal(3)))
        assert mixed.value.reason == "retry_choose_one"
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("left")
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            controller.handle_key("text:p")
            assert _await(lambda: not controller._busy)
            assert controller._retry is not None, controller.render(120, 40).plain
            assert controller._retry.action == "manual", controller.render(120, 40).plain
            assert controller.handle_key("enter") is StateResult.MANUAL
            proposal: RetryProposal | None = controller.take_manual_retry()
            assert proposal is not None
            assert proposal.action == "manual"
            expected: str = store.load().ready_groups[0].group_id if ready else groups[0]
            assert proposal.group_ids == (expected,)
            manual: ManualController = ManualController(session, session.discover(), preset, lambda: None)
            manual.prepare_retry(proposal)
            assert manual._selected_groups == {expected}
            assert materialize_intent(manual._drafts[expected]) == proposal.intents[0]
            session.release()
        finally:
            controller.close()
            controller._thread.join(5)
        assert len(translation.calls) == 1
        assert network.added == []
        assert subscriptions.list()[0].repeats == ()


@pytest.mark.parametrize("change", ["none", "missing", "replaced"])
def test_history_view_search_hotkeys_and_validated_open_remain_read_only_under_pause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    service, fixture_store, state = _completed_library(tmp_path)
    WatchStateStore(tmp_path / ".control" / "state.json").save(state)
    journal: HistoryJournal = HistoryJournal(tmp_path / ".control" / "history.jsonl")
    now: datetime = datetime.now(UTC)
    for index in range(65):
        assert journal.append(
            HistoryEvent.create(
                f"set-{index:02d}",
                f"run-{index}",
                now.isoformat(),
                HistoryKind.SUCCESS,
                f"Episode {index:02d}",
            ),
            now,
        )
    opened: list[Path] = []
    monkeypatch.setattr(state_module, "_open_path", lambda path, **_kwargs: opened.append(path))
    with closing(service), _panel_owner(service, tmp_path) as (session, store):
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            assert len(controller._history_items) == 50
            controller.handle_key("text:s")
            for letter in "muoph":
                assert controller.handle_key(f"text:{letter}") is StateResult.CONTINUE
            assert controller._history_input is not None
            assert controller._history_input.text == "muoph"
            controller.handle_key("escape")
            controller.handle_key("text:s")
            controller.handle_key("paste:Episode 01")
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            assert [item.material_id for item in controller._history_items] == ["set-01"]
            product: Path = tmp_path / "ready" / "01.pl.txt"
            if change == "missing":
                product.unlink()
            elif change == "replaced":
                product.write_text("different unrelated bytes", encoding="utf-8")
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            assert opened == ([product] if change == "none" else [])
            controller.handle_key("text:p")
            assert _await(lambda: not controller._busy)
            assert "AniShift jest wstrzymany" in controller.render(80, 24).plain
            controller.handle_key("escape")
            assert not controller._history_open
            assert controller._tab == state_module._Tab.PROGRESS
        finally:
            controller.close()
            controller._thread.join(5)
        assert store.load().requests == ()
        assert store.load().policy == state.policy
        assert fixture_store.load() == state


def test_actual_success_history_survives_relocation_restart_and_manual_routing_without_redo(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Book.txt", "Original text")
    translation: FakeTranslationService = FakeTranslationService()
    preset: AutoPreset = AutoPreset("once", "Once", ProductIntent(frozenset({ProductKind.FULL_PL})))
    service: AppService = _service(tmp_path, translation)
    with closing(service), _panel_owner(service, tmp_path, ready=True) as (session, store):
        groups: tuple[str, ...] = tuple(group.group_id for group in session.discover().groups)
        session.reserve(groups)
        assert session.execute(session.plan_auto(groups, preset), CollectingRunSink()).succeeded
        history: tuple[HistoryEvent, ...] = session.history()
        assert len(history) == 1
        assert history[0].kind is HistoryKind.SUCCESS
        identifier: str = history[0].material_id
        result: Path = session.library_result(identifier)
        stamp: os.stat_result = result.stat()
        proposal: RetryProposal = session.retry_proposal(identifier)
        assert proposal.action == "manual"
        assert proposal.group_ids == (store.load().ready_groups[0].group_id,)
        controller: ManualController = ManualController(session, session.discover(), preset, lambda: None)
        controller.prepare_retry(proposal)
        assert controller._selected_groups == set(proposal.group_ids)
        assert len(translation.calls) == 1
        session.release()
    restarted: AppService = _service(tmp_path, translation)
    with closing(restarted), _panel_owner(restarted, tmp_path, ready=True) as (session, store):
        assert session.history() == history
        assert session.library_result(identifier).stat().st_ino == stamp.st_ino
        for name in store.load().ready_groups[0].sources:
            (tmp_path / name).unlink()
        with pytest.raises(ControlError, match="retry_source_missing"):
            session.retry_proposal(identifier)
        assert len(translation.calls) == 1


def test_history_opens_ready_product_while_held_source_keeps_local_retry_scope_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source: Path = tmp_path / "audiobook" / "Book.txt"
    source.parent.mkdir()
    write_text_source(source, "Held source")
    product: Path = source.with_suffix(".m4a")
    product.write_bytes(b"recording")
    ready: ReadyStore = ReadyStore(tmp_path / ".control" / "relocations", tmp_path)
    move: ReadyMove | None = ready.prepare(discover_groups(tmp_path).groups[0], (product,))
    assert move is not None
    confirmation: AcquisitionConfirmation = _owned(
        ("Book.txt",), (), RequestOrigin.USER, source.stat().st_size, directory="audiobook"
    )
    store: WatchStateStore = WatchStateStore(tmp_path / ".control" / "state.json")
    stamp: os.stat_result = product.stat()
    confirmed: ProductConfirmation = ProductConfirmation(
        move.group_id,
        "final_audio",
        "audiobook/Book.m4a",
        1,
        "finished",
        RequestOrigin.USER,
        stamp.st_size,
        stamp.st_mtime_ns,
    )
    store.save(
        WatchState(policy=AutomationPolicy(auto_enabled=True), acquisitions=(confirmation,), products=(confirmed,))
    )
    now: datetime = datetime.now(UTC)
    assert HistoryJournal(store.history_path()).append(
        HistoryEvent.create(move.group_id, "finished", now.isoformat(), HistoryKind.SUCCESS, "Book"), now
    )
    opened: list[Path] = []
    monkeypatch.setattr(state_module, "_open_path", lambda path, **_kwargs: opened.append(path))
    service: AppService = _real_service(tmp_path)
    with closing(service), _panel_owner(service, tmp_path, ready=True) as (session, store):
        assert _await(lambda: bool(store.load().ready_groups))
        record: ReadyGroup = store.load().ready_groups[0]
        assert record.pending_sources == ("audiobook/Book.txt",)
        assert record.products == ("ready/Book.m4a",)
        controller: StateController = StateController(session, lambda: None)
        try:
            assert _wait_for_resident(session, lambda _status: controller._connected)
            controller.handle_key("text:h")
            assert _await(lambda: not controller._busy)
            controller.handle_key("enter")
            assert _await(lambda: not controller._busy)
            assert opened == [tmp_path / "ready" / "Book.m4a"], controller.render(120, 30).plain
            for identifier in (record.set_id, record.group_id):
                with pytest.raises(ControlError) as refused:
                    session.retry_proposal(identifier)
                assert refused.value.reason == "group_relocating"
            assert source.read_text(encoding="utf-8") == "Held source"
            assert store.load().requests == ()
        finally:
            controller.close()
            controller._thread.join(5)
