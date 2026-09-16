from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import Final, Self, cast

import pytest

import anishift.application.automation as automation_module
from anishift.application import (
    AcquisitionService,
    AppService,
    DeletionPreview,
    GroupIntent,
    LibrarySet,
    ProductIntent,
    ProductKind,
    RefusalReason,
    RunEvent,
    RunEventKind,
    RunMode,
    Subscription,
    TaskKind,
    TaskState,
)
from anishift.application.control import DeletionOutcome, DeletionStatus, PendingDeletion
from anishift.application.control_views import (
    LibraryFile,
    LibraryFileIdentity,
    PlanPreview,
    PreviewGroup,
    PreviewTask,
    RunProgressSnapshot,
    encode_view,
)
from anishift.application.subscriptions import EpisodeOrder, EpisodeState, SubscriptionService, SubscriptionStore
from anishift.cli.exit_codes import EXIT_SUCCESS
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.mascot import MascotController
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.state import StateController, StateResult, refusal_text
from anishift.cli.interactive.subscriptions import SubscriptionDraft
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlRequest,
    ControlResponse,
    ControlServer,
    control_endpoint,
)

_SETTINGS_FAILURE: Final[str] = "The settings view could not be closed"
_SESSION_CLOSED: Final[str] = "The resident session is already closed"


@pytest.mark.integration
def test_reopened_state_restores_progress_and_keeps_settings_available_without_render_io(tmp_path: Path) -> None:
    plan: PlanPreview = PlanPreview(
        "preview",
        "instance",
        (
            PreviewGroup(
                "episode", GroupIntent("episode", RunMode.AUTO, ProductIntent(frozenset({ProductKind.FULL_PL}))), (), ()
            ),
        ),
        (PreviewTask("translation", "episode", TaskKind.TRANSLATE_SUBTITLES),),
        (),
    )
    events: tuple[RunEvent, ...] = (
        RunEvent("run", 1, RunEventKind.RUN_STARTED),
        RunEvent(
            "run", 2, RunEventKind.TASK_STARTED, group_id="episode", task_id="translation", state=TaskState.RUNNING
        ),
        RunEvent("run", 3, RunEventKind.TASK_PROGRESS, group_id="episode", task_id="translation", progress_percent=37),
    )
    view: RunProgressSnapshot = RunProgressSnapshot("run", plan, {"episode": "Episode.mkv"}, events)
    calls: list[str] = []
    refreshed: threading.Event = threading.Event()

    def handle(request: ControlRequest) -> ControlResponse:
        calls.append(request.kind)
        if request.kind == "status":
            return ControlResponse.succeeded(
                {
                    "auto_enabled": True,
                    "run_progress": [{"run_id": "run", "preview_id": "preview"}],
                    "requests": [{"request_id": "run", "state": "running"}],
                    "materials": [{"material_id": "episode", "group_id": "episode", "run_id": "run"}],
                }
            )
        if request.kind == "run_progress":
            return ControlResponse.succeeded(encode_view(view))
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": []})
        if request.kind == "library_refresh":
            return ControlResponse.succeeded({"sets": []})
        return ControlResponse.succeeded({})

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    controller: StateController = StateController(session, refreshed.set)
    try:
        deadline: float = time.monotonic() + 5.0
        while "37%" not in controller.render(120, 35).plain and time.monotonic() < deadline:
            refreshed.wait(0.05)
            refreshed.clear()
        frame: str = controller.render(120, 35).plain
        assert "Episode.mkv" in frame
        assert "37%" in frame
        styled = controller.render(120, 35)
        assert frame.splitlines()[0].strip() == "PANEL"
        assert any(span.style == "brand_accent" for span in styled.spans)
        assert len({str(span.style) for span in styled.spans if str(span.style).startswith("#")}) > 1
        assert not any(span.style in {"reverse", "yellow", "dim"} for span in styled.spans)
        assert "Stan · Auto" not in frame
        count: int = len(calls)
        for _ in range(20):
            controller.render(120, 35)
        assert len(calls) == count
        for _ in range(20):
            controller.handle_key("tab")
        assert set(calls[count:]) <= {"library_refresh"}
        assert controller.handle_key("text:u") is StateResult.SETTINGS
        assert controller.handle_key("escape") is StateResult.HOME
    finally:
        controller.close()
        session.close()
        server.close()
        controller._thread.join(5)
    assert not controller._thread.is_alive()


@pytest.mark.parametrize("connected_client", [False, True])
def test_download_view_distinguishes_saved_orders_from_measured_progress(
    tmp_path: Path, connected_client: bool
) -> None:
    calls: list[ControlRequest] = []
    snapshot: dict[str, object] = {
        "auto_enabled": False,
        "materials": [
            {
                "material_id": "episode",
                "stage": "download",
                "info_hash": "episode",
                "name": "Episode.mkv",
                "progress": 0.37,
                "state": "downloading",
            }
        ],
        "transfers_problem": None
        if connected_client
        else ("The private torrent window was closed; downloads remain stopped until explicitly resumed"),
        "library": [
            {
                "name": "Episode",
                "directory": "ready",
                "products": [{"kind": "full_pl", "state": "ready"}, {"kind": "narration_audio", "state": "ready"}],
            }
        ],
    }

    def handle(request: ControlRequest) -> ControlResponse:
        calls.append(request)
        if request.kind == "status":
            return ControlResponse.succeeded(snapshot)
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded(
                {
                    "subscriptions": [
                        {
                            "subscription_id": "series",
                            "series": "Example",
                            "enabled": True,
                            "group": "SubsPlease",
                            "next_episode": "22",
                            "end_state": "active",
                        },
                        {
                            "subscription_id": "other",
                            "series": "Other",
                            "enabled": False,
                            "group": "Group",
                            "next_episode": "1",
                        },
                    ]
                }
            )
        return ControlResponse.succeeded({})

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    refreshed: threading.Event = threading.Event()
    controller: StateController = StateController(session, refreshed.set)
    try:
        deadline: float = time.monotonic() + 5
        while not controller._connected and time.monotonic() < deadline:
            refreshed.wait(0.05)
            refreshed.clear()
        assert controller._connected
        frame: str = controller.render(80, 24).plain
        _assert_download_measurement(frame, connected_client)
        assert len(frame.splitlines()) <= 24
        assert all(len(line) <= 80 for line in frame.splitlines())
        controller.handle_key("left")
        frame = controller.render(80, 24).plain
        assert "[SubsPlease] · Brak terminu" in frame
        assert "● Example" in frame
        assert "X usuń" in frame
        assert "Space aktywność" in frame
        assert "pobieraj nowe" not in frame
        _assert_wrapping_navigation(controller)
        _assert_list_fills_available_rows(controller)
        _assert_title_wraps(controller)
        controller.handle_key("tab")
        controller.handle_key("tab")
        frame = controller.render(80, 24).plain
        assert "Biblioteka" in frame
        assert "\u276f Episode" in frame
        assert "○" not in frame
        assert frame.splitlines()[0].strip() == "PANEL"
        assert not any(item.kind in {"transfer", "download", "set_auto"} for item in calls)
    finally:
        controller.close()
        session.close()
        server.close()
        controller._thread.join(5)


def _assert_wrapping_navigation(controller: StateController) -> None:
    controller.handle_key("up")
    assert controller._selected == 1
    assert "\u276f ○ Other" in controller.render(80, 24).plain
    controller.handle_key("down")
    assert controller._selected == 0


def _assert_title_wraps(controller: StateController) -> None:
    controller._subscriptions[0] = {
        **controller._subscriptions[0],
        "series": "A very long anime title " * 10 + "Finale",
    }
    frame: str = controller.render(80, 24).plain
    assert "Finale" in frame
    assert "…" not in frame
    assert len(frame.splitlines()) <= 24


@pytest.mark.parametrize("show_folder", [False, True])
def test_library_opens_only_the_owner_selected_result_or_selects_it_in_its_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_folder: bool
) -> None:
    video: Path = tmp_path / "Episode.pl.mkv"
    session = cast("ResidentSession", SimpleNamespace(library_result=lambda set_id: video))
    opened: list[tuple[Path, bool]] = []

    def open_path(path: Path, *, show_folder: bool = False) -> None:
        opened.append((path, show_folder))

    monkeypatch.setattr(state_module, "_open_path", open_path)
    state_module._open_episode(session, "episode", show_folder=show_folder)
    assert opened == [(video, show_folder)]


@pytest.mark.parametrize("change", ["refresh", "dismiss", "missing"])
def test_library_details_refresh_preserves_selection_without_reopening_or_disconnect(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    session: ResidentSession = cast("ResidentSession", SimpleNamespace())
    controller: StateController = StateController(session, lambda: None)
    details: LibrarySet = LibrarySet(
        "set-10",
        "group-10",
        "Episode 10",
        None,
        "ready/10.pl.txt",
        (LibraryFile("ready/10.pl.txt", "product", "TXT", LibraryFileIdentity("ready/10.pl.txt", 123, 1, 1, 1)),),
        True,
    )
    refreshed: LibrarySet = replace(details, files=(replace(details.files[0], identity=None),), available=False)

    def read_details(set_id: str) -> LibrarySet:
        assert set_id == "set-10"
        if change == "dismiss":
            controller.handle_key("escape")
        if change == "missing":
            raise ControlError("Set is missing", reason="library_set_missing", answered=True)
        return refreshed

    def command(kind: str) -> Mapping[str, object]:
        assert kind == "subscriptions_list"
        return {"subscriptions": []}

    client: ResidentSession = cast("ResidentSession", SimpleNamespace(command=command, library_details=read_details))
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {
        "library": [{"set_id": "set-2", "name": "Episode 2"}, {"set_id": "set-10", "name": "Episode 10"}]
    }
    controller._detail_selection = 1
    controller._details = details
    payload: dict[str, object] = {"library": [{"set_id": "set-10", "name": "Episode 10"}]}
    try:
        controller._receive(client, {"event": "state_changed", "payload": payload})
        assert controller._connected
        assert controller._snapshot == payload
        frame: str = controller.render(120, 35).plain
        if change == "refresh":
            assert "brak" in frame
            assert "TXT" in frame
            assert "główny" in frame
            assert controller.handle_key("escape") is StateResult.CONTINUE
        else:
            assert controller._details is None
            assert "Esc wróć do biblioteki" not in frame
        assert controller._selected == 0
        assert "\u276f Episode 10" in controller.render(120, 35).plain
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("action", ["cancel", "confirm", "leave"])
def test_whole_set_deletion_uses_one_confirmation_default_cancel_and_retains_its_session(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    prepared: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    submitted: list[DeletionPreview] = []
    sessions: list[Session] = []
    preview: DeletionPreview = DeletionPreview(
        "preview-01",
        "instance",
        "set-01",
        "Episode 01",
        (LibraryFileIdentity("ready/01.txt", 123, 1, 2, 3),),
    )

    class Session:
        closed: bool = False

        def new_session(self) -> ResidentSession:
            session: Session = Session()
            sessions.append(session)
            return cast("ResidentSession", session)

        def preview_deletion(self, set_id: str) -> DeletionPreview:
            assert set_id == preview.set_id
            prepared.set()
            assert release.wait(5)
            return preview

        def delete_set(self, value: DeletionPreview) -> str:
            assert not self.closed
            submitted.append(value)
            return "operation-01"

        def close(self) -> None:
            self.closed = True

    controller: StateController = StateController(cast("ResidentSession", Session()), lambda: None)
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {
        "library": [{"set_id": f"other-{index}", "name": f"Earlier {index}"} for index in range(3)]
        + [{"set_id": "set-01", "name": "Episode 01"}]
    }
    controller._selected = 3
    controller._connected = True
    try:
        controller.handle_key("delete")
        assert prepared.wait(5)
        if action == "leave":
            assert controller.handle_key("escape") is StateResult.HOME
        release.set()
        _await_state_action(controller)
        if action == "leave":
            assert controller._deletion is None
            assert submitted == []
            return
        assert len(sessions) == 1
        assert not sessions[0].closed
        for width, height in ((120, 40), (80, 24), (40, 10), (40, 6), (40, 4)):
            frame: str = controller.render(width, height).plain
            assert "[Anuluj]" in frame
            assert "1 plików" in frame
            assert len(frame.splitlines()) <= height
        if action == "confirm":
            controller.handle_key("right")
            for width, height in ((120, 40), (80, 24), (40, 6), (40, 4)):
                assert "[Przenieś do Kosza]" in controller.render(width, height).plain
        controller.handle_key("enter")
        _await_state_action(controller)
        assert submitted == ([preview] if action == "confirm" else [])
        assert controller._deletion is None
        assert controller._selected == 3
    finally:
        release.set()
        _await_state_action(controller)
        controller.close()
        controller._thread.join(5)
        assert all(session.closed for session in sessions)


@pytest.mark.parametrize("tab", [state_module._Tab.PROGRESS, state_module._Tab.FILES])
def test_unresolved_deletion_stays_visible_and_retry_targets_that_selected_operation(
    monkeypatch: pytest.MonkeyPatch, tab: int
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[tuple[str, Mapping[str, object]]] = []
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    monkeypatch.setattr(controller, "_command", lambda kind, payload: calls.append((kind, payload)))
    operations: list[dict[str, object]] = [
        {
            "operation_id": f"delete-{name}",
            "set_id": f"set-{name}",
            "name": name,
            "active": False,
            "recycled": 1 if name == "B" else 2,
            "total": 2,
            "remaining": 1 if name == "B" else 0,
            "uncertain": False,
            "retryable": name == "B",
            "can_confirm": False,
        }
        for name in ("A", "B", "C")
    ]
    controller._tab = tab
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {"deletions": operations, "library": [], "library_problems": []}
    try:
        frame: str = controller.render(120, 40).plain
        assert "Kosz: B" in frame
        assert "nierozliczone: 1/2" in frame
        assert "P ponów" in frame
        assert calls == []
        controller.handle_key("text:p")
        assert calls == [("deletion_retry", {"operation_id": "delete-B"})]
        operations[1].update(recycled=2, remaining=0, retryable=False)
        frame = controller.render(120, 40).plain
        assert "Kosz:" not in frame
        assert "P ponów" not in frame
        controller.handle_key("text:p")
        assert len(calls) == 1
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("context", ["empty", "library", "deletion", "uncertain", "healthy"])
def test_files_retries_reported_relocations_without_overriding_selected_deletion(
    monkeypatch: pytest.MonkeyPatch, context: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[tuple[str, Mapping[str, object] | None]] = []

    class Session:
        def new_session(self) -> ResidentSession:
            return cast("ResidentSession", self)

        def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
            calls.append((kind, payload))
            return {"pending": 1}

        def close(self) -> None:
            pass

    controller: StateController = StateController(cast("ResidentSession", Session()), lambda: None)
    controller._tab = state_module._Tab.FILES
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {
        "relocations": [
            {
                "group_id": "group-episode",
                "name": "Episode.mkv",
                "problem": None if context == "healthy" else "Relocation could not finish",
            }
        ],
        "library": [
            {
                "group_id": "group-ready",
                "set_id": "set-ready",
                "name": "Ready",
                "main_result": "ready/Ready.pl.mkv",
                "target": "video",
            }
        ]
        if context == "library"
        else [],
        "library_problems": [],
        "deletions": [
            {
                "operation_id": "delete-B",
                "set_id": "set-B",
                "name": "B",
                "active": False,
                "recycled": 1,
                "total": 2,
                "remaining": 1,
                "uncertain": context == "uncertain",
                "retryable": context == "deletion",
                "can_confirm": False,
            }
        ]
        if context in {"deletion", "uncertain"}
        else [],
    }
    try:
        for key in ("home", "down", "end", "up"):
            controller.handle_key(key)
        frame: str = controller.render(120, 40).plain
        controller.render(80, 24)
        assert calls == []
        relocation_hint: str = "P ponów przenoszenie do biblioteki"
        if context in {"empty", "library"}:
            assert relocation_hint in frame
            assert "Episode.mkv" in frame
        else:
            assert relocation_hint not in frame
        assert ("P ponów pozostałe pliki" in frame) is (context == "deletion")
        controller.handle_key("text:P")
        _await_state_action(controller)
        if context in {"empty", "library"}:
            assert calls == [("ready_retry", None)]
        elif context == "deletion":
            assert calls == [("deletion_retry", {"operation_id": "delete-B"})]
        else:
            assert calls == []
    finally:
        controller.close()
        controller._thread.join(5)


def test_merged_library_is_naturally_ordered_and_preserves_missing_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {
        "library": [{"set_id": "2", "name": "Episode 2"}, {"set_id": "10", "name": "Episode 10"}],
        "library_problems": [{"set_id": "3", "name": "Episode 3", "available": False}],
    }
    try:
        assert [row["set_id"] for row in state_module._library_rows(controller._snapshot)] == ["2", "3", "10"]
        controller._selected = 1
        payload: dict[str, object] = {
            "library": [{"set_id": "10", "name": "Episode 10"}],
            "library_problems": [{"set_id": "3", "name": "Episode 3", "available": False}],
        }
        controller._preserve_library_selection(payload)
        controller._snapshot = payload
        assert controller._selected == 0
        assert "Episode 3" in controller.render(80, 24).plain
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("problem", ["library_ownership_unknown", "library_result_changed", "library_result_missing"])
def test_library_details_explain_machine_coded_provenance_and_result_problem(
    monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._details = LibrarySet(
        "set", "group", "Episode", None, "ready/01.txt", (), problem == "library_ownership_unknown", problem
    )
    try:
        frame: str = controller.render(120, 40).plain
        assert state_module._LIBRARY_PROBLEMS[problem] in frame
        if problem == "library_result_changed":
            assert state_module._LIBRARY_PROBLEMS["library_result_missing"] not in frame
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("can_confirm", [False, True])
def test_uncertain_deletion_details_name_exact_paths_and_require_fresh_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    can_confirm: bool,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    operation: PendingDeletion = PendingDeletion(
        "delete-B",
        "set-B",
        "2026-09-16T12:00:00+00:00",
        (("ready/B.pl.txt", 1, 1), ("ready/B.txt", 2, 2), ("ready/B.srt", 3, 3)),
        recycled=("ready/B.pl.txt",),
        identities=(("ready/B.pl.txt", 1, 1), ("ready/B.txt", 1, 2), ("ready/B.srt", 1, 3)),
        outcomes=(
            DeletionOutcome("ready/B.pl.txt", DeletionStatus.RECYCLED, "recycle_completed", "receipt"),
            DeletionOutcome("ready/B.txt", DeletionStatus.UNCERTAIN, "recycle_cleanup_timeout"),
        ),
    )
    calls: list[tuple[str, Mapping[str, object]]] = []
    preview: DeletionPreview = DeletionPreview("new-preview", "instance", "set-B", "B", ())

    class Session:
        def new_session(self) -> ResidentSession:
            return cast("ResidentSession", self)

        def command(self, kind: str, payload: Mapping[str, object]) -> Mapping[str, object]:
            calls.append((kind, payload))
            assert kind == "deletion_get"
            return encode_view(operation)

        def preview_deletion(self, set_id: str) -> DeletionPreview:
            calls.append(("deletion_preview", {"set_id": set_id}))
            return preview

        def close(self) -> None:
            pass

    controller: StateController = StateController(cast("ResidentSession", Session()), lambda: None)
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {
        "deletions": [
            {
                "operation_id": "delete-B",
                "set_id": "set-B",
                "name": "B",
                "total": 3,
                "recycled": 1,
                "remaining": 2,
                "uncertain": True,
                "retryable": False,
                "can_confirm": can_confirm,
            }
        ]
    }
    try:
        assert "wynik niepewny" in controller.render(120, 40).plain
        controller.handle_key("enter")
        _await_state_action(controller)
        frame: str = controller.render(120, 40).plain
        assert "ready/B.pl.txt · w Koszu" in frame
        assert "ready/B.txt · wynik niepewny" in frame
        assert "ready/B.srt · nie podjęto" in frame
        assert "P ponów" not in frame
        assert ("Delete nowe potwierdzenie" in frame) is can_confirm
        controller.handle_key("text:p")
        controller.handle_key("down")
        controller.render(80, 24)
        assert calls == [("deletion_get", {"operation_id": "delete-B"})]
        controller.handle_key("delete")
        _await_state_action(controller)
        assert controller._deletion == (preview if can_confirm else None)
        if can_confirm:
            assert "[Anuluj]" in controller.render(80, 24).plain
        assert all(kind != "deletion_retry" for kind, _payload in calls)
    finally:
        controller.close()
        controller._thread.join(5)


def _await_state_action(controller: StateController) -> None:
    deadline: float = time.monotonic() + 5
    while controller._busy and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not controller._busy


def test_every_refusal_cause_reaches_the_panel_as_its_own_translated_sentence() -> None:
    assert set(state_module._REFUSAL_TEXTS) == {reason.value for reason in RefusalReason}
    texts: list[str] = []
    for reason in RefusalReason:
        english: str = automation_module._REFUSALS[reason][1]
        stated: str = refusal_text(
            ControlError(english, code=ControlErrorCode.CONFLICT, reason=reason.value, answered=True)
        )
        assert stated == state_module._REFUSAL_TEXTS[reason.value]
        assert stated != english
        assert stated
        assert not stated.endswith(".")
        texts.append(stated)

    assert len(set(texts)) == len(RefusalReason)


def test_an_unmapped_or_absent_reason_still_states_something_honest() -> None:
    unmapped: str = refusal_text(
        ControlError("The resident invented a new cause", code=ControlErrorCode.CONFLICT, reason="from_the_future")
    )
    silent: str = refusal_text(ControlError("", code=ControlErrorCode.REFUSED, reason="from_the_future"))
    foreign: str = refusal_text(OSError("the pipe is gone"))

    assert unmapped == "The resident invented a new cause"
    assert silent == state_module._UNKNOWN_REFUSAL
    assert foreign == "the pipe is gone"


def test_the_panel_never_picks_refusal_text_by_matching_the_message() -> None:
    stated: str = refusal_text(
        ControlError(
            "Another client holds one of the requested groups",
            code=ControlErrorCode.CONFLICT,
            answered=True,
        )
    )

    assert stated == "Another client holds one of the requested groups"
    assert stated != state_module._REFUSAL_TEXTS[RefusalReason.GROUP_RESERVED.value]


def _await(condition: Callable[[], bool], refreshed: threading.Event) -> None:
    deadline: float = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        refreshed.wait(0.05)
        refreshed.clear()
    assert condition()


@pytest.mark.integration
def test_a_panel_notice_disappears_once_the_resident_state_moves_on(tmp_path: Path) -> None:
    def handle(request: ControlRequest) -> ControlResponse:
        if request.kind == "status":
            return ControlResponse.succeeded({"auto_enabled": True, "acquisitions": [], "library": []})
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": []})
        return ControlResponse.succeeded({})

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    refreshed: threading.Event = threading.Event()
    controller: StateController = StateController(session, refreshed.set)
    try:
        _await(lambda: controller._connected, refreshed)
        _await(lambda: "Łączenie" not in controller.render(80, 24).plain, refreshed)
        controller.set_notice("Grupa jest już przetwarzana")
        assert "Grupa jest już przetwarzana" in controller.render(80, 24).plain
        server.broadcast(
            {"event": "state_changed", "payload": {"auto_enabled": False, "acquisitions": [], "library": []}},
            terminal=False,
        )
        _await(lambda: "Grupa jest już przetwarzana" not in controller.render(80, 24).plain, refreshed)
    finally:
        controller.close()
        session.close()
        server.close()
        controller._thread.join(5)


def test_library_return_keeps_identity_and_detached_scroll_after_an_inactive_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    session: ResidentSession = cast(
        "ResidentSession", SimpleNamespace(command=lambda kind: {"subscriptions": []}, library=lambda: ())
    )
    controller: StateController = StateController(session, lambda: None)
    controller._tab = state_module._Tab.FILES
    library: list[dict[str, object]] = [{"set_id": f"set-{index}", "name": f"Episode {index}"} for index in range(40)]
    controller._snapshot = {"library": library}
    controller._connected = True
    controller.set_notice("")
    try:
        controller.handle_key("end")
        controller.render(80, 24)
        controller.scroll(-3)
        before: str = controller.render(80, 24).plain
        offset: int = controller._offsets[state_module._Tab.FILES]
        controller.handle_key("left")
        controller.handle_key("end")
        controller._receive(session, {"event": "state_changed", "payload": {"library": library}})
        controller._switch_tab(state_module._Tab.FILES)
        assert controller._selected == 39
        assert controller.render(80, 24).plain == before
        assert controller._offsets[state_module._Tab.FILES] == offset
        controller.handle_key("left")
        controller._receive(session, {"event": "state_changed", "payload": {"library": library[1:]}})
        controller._switch_tab(state_module._Tab.FILES)
        assert controller._selected == 38
        assert state_module._library_rows(controller._snapshot)[controller._selected]["set_id"] == "set-39"
        controller.handle_key("up")
        assert "\u276f Episode 38" in controller.render(80, 24).plain
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("action", ["escape", "enter", "text:p"])
def test_subscription_card_keeps_completed_facts_and_requires_explicit_repeat(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    subscription: Subscription = Subscription(
        "series",
        "query",
        "Series",
        "Group",
        Decimal(8),
        1080,
        frozenset({"old-hash"}),
        "2026-09-16",
        None,
        episodes=(
            EpisodeOrder(Decimal(3), state=EpisodeState.COMPLETE, info_hash="old-hash", acquisition_id="old"),
            EpisodeOrder(Decimal("7.5")),
            EpisodeOrder(Decimal(8)),
        ),
        future_from=Decimal(9),
    )
    repeated: list[tuple[str, tuple[Decimal, ...]]] = []

    def repeat(identifier: str, numbers: tuple[Decimal, ...]) -> Subscription:
        repeated.append((identifier, numbers))
        return replace(subscription, episodes=(replace(subscription.episodes[0], state=EpisodeState.DUE),))

    session: ResidentSession = cast(
        "ResidentSession",
        SimpleNamespace(
            command=lambda kind, payload: {**encode_view(subscription), "work_states": {"3": "completed"}},
            repeat=repeat,
            close=lambda: None,
        ),
    )
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace(new_session=lambda: session)), lambda: None
    )
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._subscriptions = [{"subscription_id": "series", "series": "Series", "group": "Group"}]
    try:
        controller.handle_key("enter")
        _await_state_action(controller)
        assert "○ 3 · ukończono produkty" in controller.render(80, 24).plain
        controller.handle_key("text:a")
        assert "○ 3 · ukończono produkty" in controller.render(80, 24).plain
        controller.handle_key("space")
        controller.handle_key(action)
        _await_state_action(controller)
        assert repeated == ([("series", (Decimal(3),))] if action == "text:p" else [])
        assert subscription.episodes[0].acquisition_id == "old"
        assert subscription.episodes[0].state is EpisodeState.COMPLETE
        if action == "enter":
            assert "wymagają jawnego P Ponów" in controller.render(80, 24).plain
        elif action == "escape":
            assert controller._draft is None
        else:
            assert controller._draft is not None
            assert not controller._draft.completed
            assert "Przyjęto ponowienie: 3" in controller.render(120, 24).plain
            assert "Enter stosuje pozostały zakres" in controller.render(120, 24).plain
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize("finish", ["enter", "escape"])
def test_repeat_preserves_mixed_draft_until_separate_range_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    store: SubscriptionStore = SubscriptionStore(tmp_path / "subscriptions.json")
    original: Subscription = Subscription(
        "series",
        "query",
        "Series",
        "Group",
        Decimal(1),
        1080,
        frozenset(),
        "2026-09-16",
        None,
        episodes=(
            EpisodeOrder(Decimal(1)),
            EpisodeOrder(Decimal(2), selected=False),
            EpisodeOrder(Decimal(3), state=EpisodeState.COMPLETE, acquisition_id="old"),
        ),
        future_from=Decimal(4),
    )
    store.save((original,))
    service: SubscriptionService = SubscriptionService(store=store, acquisition=cast("AcquisitionService", object()))
    commands: list[str] = []
    refused: bool = True

    def handle(request: ControlRequest) -> ControlResponse:
        commands.append(request.kind)
        current: Subscription = service.list()[0]
        if request.kind == "subscription_get":
            return ControlResponse.succeeded({**encode_view(current), "work_states": {"3": "completed"}})
        if request.kind == "subscription_repeat":
            assert request.payload["episodes"] == ["3"]
            if refused:
                return ControlResponse.refused(ControlErrorCode.REFUSED, "Refused", RefusalReason.PAUSED.value)
            return ControlResponse.succeeded(encode_view(service.repeat("series", (Decimal(3),))))
        if request.kind == "subscription_range":
            assert request.payload["selected"] == ["2", "3"]
            assert request.payload["future_from"] is None
            return ControlResponse.succeeded(
                encode_view(service.set_range("series", selected=(Decimal(2), Decimal(3)), future_from=None))
            )
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded(
                {"subscriptions": [{"subscription_id": "series", "work_states": {"3": "due"}}]}
            )
        return ControlResponse.succeeded({})

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    controller: StateController = StateController(session, lambda: None)
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._subscriptions = [{"subscription_id": "series"}]
    try:
        controller.handle_key("enter")
        _await_state_action(controller)
        for action in ("space", "down", "space", "down", "space", "end", "space", "enter"):
            controller.handle_key(action)
        draft: SubscriptionDraft | None = controller._draft
        assert draft is not None
        assert draft.selected == {Decimal(2), Decimal(3)}
        assert draft.future_from is None
        assert "subscription_range" not in commands
        controller.handle_key("text:p")
        _await_state_action(controller)
        assert controller._draft is draft
        assert draft.completed == {Decimal(3)}
        assert draft.selected == {Decimal(2), Decimal(3)}
        assert draft.future_from is None
        assert store.load() == (original,)
        refused = False
        _finish_mixed_draft_repeat(controller, session, store, commands, finish)
    finally:
        controller.close()
        controller._thread.join(5)
        session.close()
        server.close()


@pytest.mark.parametrize("leave", ["escape", "close"])
def test_late_repeat_result_does_not_change_a_cancelled_subscription_draft(
    monkeypatch: pytest.MonkeyPatch, leave: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    subscription: Subscription = Subscription(
        "series",
        "query",
        "Series",
        "Group",
        Decimal(1),
        1080,
        frozenset(),
        "2026-09-16",
        None,
        episodes=(EpisodeOrder(Decimal(1), state=EpisodeState.COMPLETE),),
    )
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def repeat(identifier: str, numbers: tuple[Decimal, ...]) -> Subscription:
        assert identifier == "series"
        assert numbers == (Decimal(1),)
        entered.set()
        assert release.wait(5)
        return replace(subscription, generation=subscription.generation + 1)

    session: ResidentSession = cast("ResidentSession", SimpleNamespace(repeat=repeat, close=lambda: None))
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace(new_session=lambda: session)), lambda: None
    )
    draft: SubscriptionDraft = SubscriptionDraft.from_subscription(subscription, {"1": "completed"})
    controller._draft = draft
    try:
        controller.handle_key("space")
        controller.handle_key("text:p")
        assert entered.wait(5)
        if leave == "close":
            controller.close()
        else:
            controller.handle_key("escape")
        release.set()
        _await_state_action(controller)
        assert draft.subscription == subscription
        assert draft.completed == {Decimal(1)}
        assert draft.states[Decimal(1)] == "completed"
    finally:
        release.set()
        _await_state_action(controller)
        controller.close()
        controller._thread.join(5)


def _finish_mixed_draft_repeat(
    controller: StateController, session: ResidentSession, store: SubscriptionStore, commands: list[str], finish: str
) -> None:
    draft: SubscriptionDraft | None = controller._draft
    assert draft is not None
    controller.handle_key("text:p")
    _await_state_action(controller)
    accepted: Subscription = store.load()[0]
    assert len(accepted.repeats) == 1
    assert accepted.episodes[0].selected
    assert not accepted.episodes[1].selected
    assert accepted.future_from == Decimal(4)
    assert controller._draft is draft
    assert draft.subscription == accepted
    assert not draft.completed
    assert draft.states[Decimal(3)] == "due"
    assert "Enter stosuje pozostały zakres" in controller.render(120, 24).plain
    controller.handle_key("text:p")
    controller._receive(session, {"event": "state_changed", "payload": {"auto_enabled": True}})
    controller.poll()
    assert draft.selected == {Decimal(2), Decimal(3)}
    assert draft.future_from is None
    assert commands.count("subscription_repeat") == 2
    controller.handle_key(finish)
    _await_state_action(controller)
    assert controller._draft is None
    saved: Subscription = store.load()[0]
    assert len(saved.repeats) == 1
    assert saved.repeats[0].previous_acquisition_id == "old"
    if finish == "enter":
        assert {item.number for item in saved.episodes if item.selected} == {Decimal(2), Decimal(3)}
        assert saved.future_from is None
        assert commands.count("subscription_range") == 1
    else:
        assert saved == accepted
        assert "subscription_range" not in commands


def test_subscription_term_converts_utc_to_a_non_utc_local_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    class LocalDateTime(datetime):
        def astimezone(self, tz: tzinfo | None = None) -> Self:
            return super().astimezone(tz or timezone(timedelta(hours=2)))

    monkeypatch.setattr(state_module, "datetime", LocalDateTime)
    assert state_module._subscription_term({"airing_at": "2026-10-03T23:30:00+00:00"}) == "04.10.2026 01:30"


def _assert_list_fills_available_rows(controller: StateController) -> None:
    controller._subscriptions.extend(
        {"series": f"Series {index}", "enabled": False, "group": "Group", "next_episode": 1} for index in range(20)
    )
    frame: str = controller.render(80, 24).plain
    assert sum("● " in line or "○ " in line for line in frame.splitlines()) == 17
    assert "Space aktywność" in frame
    assert len(frame.splitlines()) <= 24
    controller.handle_key("end")
    assert controller._selected == 21
    controller.handle_key("home")
    assert controller._selected == 0


@pytest.mark.parametrize("inactive", [False, True])
@pytest.mark.parametrize("selected", ["material", "deletion"])
def test_processing_preserves_selected_identity_when_material_counts_change(
    monkeypatch: pytest.MonkeyPatch, inactive: bool, selected: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    session: ResidentSession = cast("ResidentSession", SimpleNamespace(command=lambda kind: {"subscriptions": []}))
    controller: StateController = StateController(session, lambda: None)
    materials: list[dict[str, object]] = [
        {"material_id": f"material-{index}", "name": f"Episode {index}", "stage": "waiting"} for index in range(3)
    ]
    deletions: list[dict[str, object]] = [
        {"operation_id": "delete", "set_id": "set", "name": "Deleted", "total": 2, "recycled": 1}
    ]
    controller._snapshot = {"materials": materials, "deletions": deletions}
    controller._connected = True
    controller._selected = 1 if selected == "material" else 3
    try:
        if inactive:
            controller.handle_key("left")
        controller._receive(
            session, {"event": "state_changed", "payload": {"materials": materials[1:], "deletions": deletions}}
        )
        if inactive:
            controller.handle_key("right")
        assert controller._selected == (0 if selected == "material" else 2)
        assert (controller._selected_deletion() is not None) is (selected == "deletion")
        controller._receive(
            session, {"event": "state_changed", "payload": {"materials": materials, "deletions": deletions}}
        )
        assert controller._selected == (1 if selected == "material" else 3)
    finally:
        controller.close()
        controller._thread.join(5)


@pytest.mark.parametrize(("columns", "rows"), [(120, 40), (80, 24), (80, 8)])
@pytest.mark.parametrize("tab", [1, 2, 3])
def test_each_panel_tab_retains_contextual_actions_and_owner_counts_at_feasible_sizes(
    monkeypatch: pytest.MonkeyPatch, columns: int, rows: int, tab: int
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._tab = tab
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {
        "auto_enabled": True,
        "material_counts": {"downloading": 2, "processing": 3, "waiting": 4},
        "materials": [
            {
                "material_id": "material",
                "name": "Full original name.mkv",
                "stage": "processing",
                "run_id": "run",
                "group_ids": ["a", "b"],
                "active": True,
            }
        ],
    }
    controller._subscriptions = [
        {"series": "Title", "group": "Group", "enabled": True, "airing_at": "2026-10-03T18:30:00+00:00"}
    ]
    try:
        frame: str = interactive_app._fit_frame(
            controller.render(columns, rows), "test", "workspace", columns, rows
        ).plain
        assert "↓ 2 · Przetwarzanie 3 · Czeka 4 · Praca" in frame
        assert "←→ widok" in frame
        assert ("Enter odcinki", "C anuluj całe zlecenie · 2 materiałów", "Delete Kosz")[tab - 1] in frame
        assert len(frame.splitlines()) <= rows
        assert all(len(line) <= columns for line in frame.splitlines())
        if tab == 1:
            expected: str = datetime.fromisoformat("2026-10-03T18:30:00+00:00").astimezone().strftime("%d.%m.%Y %H:%M")
            assert expected in frame
    finally:
        controller.close()
        controller._thread.join(5)


def _assert_download_measurement(frame: str, connected_client: bool) -> None:
    assert "Episode.mkv" in frame
    assert "0.0%" not in frame
    assert ("37.0%" in frame) is connected_client
    assert ("pobieranie" in frame) is connected_client
    assert "downloading" not in frame
    assert "The private torrent" not in frame


def _rendered_transfers(tmp_path: Path, snapshot: dict[str, object]) -> str:
    def handle(request: ControlRequest) -> ControlResponse:
        return ControlResponse.succeeded(snapshot if request.kind == "status" else {})

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    refreshed: threading.Event = threading.Event()
    controller: StateController = StateController(session, refreshed.set)
    try:
        deadline: float = time.monotonic() + 5.0
        while not controller._connected and time.monotonic() < deadline:
            refreshed.wait(0.05)
            refreshed.clear()
        assert controller._connected
        return controller.render(80, 24).plain
    finally:
        controller.close()
        session.close()
        server.close()
        controller._thread.join(5)


@pytest.mark.parametrize("problem", ["The download destination could not be read", "Something took a name", "Refused"])
def test_a_problem_of_a_release_the_client_still_reports_is_named_in_the_download_view(
    tmp_path: Path,
    problem: str,
) -> None:
    frame: str = _rendered_transfers(
        tmp_path,
        {
            "auto_enabled": False,
            "materials": [
                {
                    "material_id": "episode",
                    "stage": "download",
                    "info_hash": "episode",
                    "name": "Episode.mkv",
                    "progress": 0.0,
                    "state": "stoppedDL",
                    "problem": problem,
                }
            ],
            "transfers_problem": None,
        },
    )

    assert "Episode.mkv" in frame
    assert "wymaga uwagi" in frame
    assert "wstrzymane" not in frame
    assert problem not in frame


def test_an_ordered_release_the_client_never_reported_still_says_so(tmp_path: Path) -> None:
    frame: str = _rendered_transfers(
        tmp_path,
        {
            "auto_enabled": False,
            "materials": [
                {
                    "material_id": "episode",
                    "stage": "download",
                    "info_hash": "episode",
                    "name": "Episode 22",
                    "state": None,
                    "progress": None,
                },
            ],
            "transfers_problem": None,
        },
    )

    assert "brak potwierdzenia klienta" in frame
    assert "wymaga uwagi" not in frame
    assert "%" not in frame


class _PanelRenderer:
    def __init__(
        self,
        frame_provider: Callable[[int, int], object],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> None:
        del frame_provider, key_handler, scroll_handler
        self.idle_handler: Callable[[], None] | None = idle_handler
        self.native_mascot_size: tuple[int, int] | None = None
        self.exits: int = 0
        self.finished: threading.Event = threading.Event()

    def run(self) -> None:
        while not self.finished.wait(timeout=0.01):
            if self.idle_handler is not None:
                self.idle_handler()

    def invalidate(self) -> None:
        return None

    def exit(self) -> None:
        self.exits += 1
        self.finished.set()


@pytest.mark.integration
def test_a_real_panel_closes_itself_when_the_resident_announces_its_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attached: threading.Event = threading.Event()
    snapshot: dict[str, object] = {"auto_enabled": True, "shutting_down": False}

    def handle(request: ControlRequest) -> ControlResponse:
        if request.kind == "panel_attach":
            attached.set()
        if request.kind == "status":
            return ControlResponse.succeeded(snapshot)
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": []})
        if request.kind == "discover":
            return ControlResponse.succeeded({"groups": [], "warnings": []})
        return ControlResponse.succeeded({})

    renderers: list[_PanelRenderer] = []
    monkeypatch.setattr(interactive_app, "TerminalRenderer", _recording_renderer(renderers))
    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        cast("AppService", SimpleNamespace(discover=lambda: None, default_preset_id=lambda: "default")),
        resident=session,
        show_state=True,
    )
    codes: list[int] = []
    panel: threading.Thread = threading.Thread(target=lambda: codes.append(application.run()), daemon=True)
    panel.start()
    closed: bool = False
    exits: int = 0
    try:
        assert attached.wait(5.0)
        assert renderers[0].exits == 0
        deadline: float = monotonic() + 10.0
        while panel.is_alive() and monotonic() < deadline:
            server.broadcast({"event": "state_changed", "payload": {**snapshot, "shutting_down": True}}, False)
            panel.join(0.2)
        closed = not panel.is_alive()
        exits = renderers[0].exits
    finally:
        renderers[0].exit()
        panel.join(5.0)
        session.close()
        server.close()

    assert closed
    assert exits == 1
    assert codes == [EXIT_SUCCESS]


def _recording_renderer(renderers: list[_PanelRenderer]) -> Callable[..., _PanelRenderer]:
    def build(
        frame_provider: Callable[[int, int], object],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> _PanelRenderer:
        renderer: _PanelRenderer = _PanelRenderer(frame_provider, key_handler, idle_handler, scroll_handler)
        renderers.append(renderer)
        return renderer

    return build


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (RefusalReason.PAUSED, "AniShift jest wstrzymany · wybierz Wznów, aby podjąć pracę"),
        (RefusalReason.SHUTTING_DOWN, "AniShift się kończy · nie przyjmuje już nowej pracy"),
    ],
)
def test_the_panel_names_a_pause_and_an_end_in_polish_chosen_by_the_refusal_code(
    tmp_path: Path, reason: RefusalReason, expected: str
) -> None:
    english: str = "AniShift is paused; choose Resume before starting new work"

    def handle(request: ControlRequest) -> ControlResponse:
        del request
        return ControlResponse.refused(ControlErrorCode.REFUSED, english, reason.value)

    key: bytes = os.urandom(32)
    endpoint: str = control_endpoint(tmp_path)
    server: ControlServer = ControlServer(endpoint, key, handle)
    session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
    try:
        with pytest.raises(ControlError) as refusal:
            session.command("start")
    finally:
        session.close()
        server.close()

    assert refusal.value.reason == reason.value
    assert refusal_text(refusal.value) == expected
    assert english not in refusal_text(refusal.value)


class _Settings:
    def __init__(self, calls: list[str], *, failing: bool) -> None:
        self.calls: list[str] = calls
        self.failing: bool = failing

    def close(self) -> None:
        self.calls.append("settings.close")
        if self.failing:
            raise OSError(_SETTINGS_FAILURE)


class _Session:
    def __init__(self, calls: list[str]) -> None:
        self.calls: list[str] = calls
        self.closed: bool = False

    def command(self, kind: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        del payload
        self.calls.append(kind)
        if self.closed:
            raise OSError(_SESSION_CLOSED)
        return {}

    def close(self) -> None:
        self.calls.append("resident.close")
        self.closed = True


class _Mascot:
    def __init__(self, calls: list[str]) -> None:
        self.calls: list[str] = calls

    def close(self) -> None:
        self.calls.append("mascot.close")


@pytest.mark.parametrize(
    ("failing", "expected"),
    [
        (False, ["settings.close", "reload_settings", "resident.close", "mascot.close"]),
        (True, ["settings.close", "resident.close", "mascot.close"]),
    ],
)
def test_an_end_with_settings_open_persists_them_first_and_finishes_every_other_step(
    monkeypatch: pytest.MonkeyPatch, failing: bool, expected: list[str]
) -> None:
    renderers: list[_PanelRenderer] = []
    monkeypatch.setattr(interactive_app, "TerminalRenderer", _recording_renderer(renderers))
    calls: list[str] = []
    session = _Session(calls)
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        cast("AppService", SimpleNamespace(discover=lambda: None, default_preset_id=lambda: "default")),
        resident=cast("ResidentSession", session),
        show_state=True,
    )
    application._settings = cast("SettingsController", _Settings(calls, failing=failing))
    application._mascot = cast("MascotController", _Mascot(calls))

    application._finish_session()

    assert calls == expected
