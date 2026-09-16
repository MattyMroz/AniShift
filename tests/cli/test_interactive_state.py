from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import Final, cast

import pytest

import anishift.application.automation as automation_module
from anishift.application import (
    AppService,
    ArtifactKind,
    GroupIntent,
    ProductIntent,
    ProductKind,
    RefusalReason,
    RunEvent,
    RunEventKind,
    RunMode,
    TaskKind,
    TaskState,
)
from anishift.application.control_views import PlanPreview, PreviewGroup, PreviewTask, RunProgressSnapshot, encode_view
from anishift.cli.exit_codes import EXIT_SUCCESS
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.mascot import MascotController
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.state import StateController, StateResult, refusal_text
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
                }
            )
        if request.kind == "run_progress":
            return ControlResponse.succeeded(encode_view(view))
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": []})
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
            controller.handle_key("tab")
        assert len(calls) == count
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
        "acquisitions": [{"info_hash": "episode", "directory": "Episode", "episode": "22", "state": "accepted"}],
        "transfers": [{"info_hash": "episode", "name": "Episode.mkv", "progress": 0.37, "state": "downloading"}],
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
        controller.handle_key("tab")
        frame: str = controller.render(80, 24).plain
        assert "Episode.mkv" in frame
        assert "0.0%" not in frame
        assert ("37.0%" in frame) is connected_client
        assert ("—" in frame) is not connected_client
        assert len(frame.splitlines()) <= 24
        assert all(len(line) <= 80 for line in frame.splitlines())
        controller.handle_key("tab")
        frame = controller.render(80, 24).plain
        assert "[SubsPlease] · 22" in frame
        assert "● Example" in frame
        assert "X usuń" in frame
        assert "Space wybierz" in frame
        assert "pobieraj nowe" not in frame
        _assert_wrapping_navigation(controller)
        _assert_list_fills_available_rows(controller)
        _assert_title_wraps(controller)
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
def test_library_opens_the_selected_video_or_selects_it_in_its_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, show_folder: bool
) -> None:
    video: Path = tmp_path / "Episode.mkv"
    video.write_bytes(b"video")
    group = SimpleNamespace(group_id="episode", artifacts=(SimpleNamespace(kind=ArtifactKind.VIDEO_MKV, path=video),))
    session = cast(
        "ResidentSession", SimpleNamespace(workspace_root=tmp_path, discover=lambda: SimpleNamespace(groups=(group,)))
    )
    opened: list[tuple[Path, bool]] = []

    def open_path(path: Path, *, show_folder: bool = False) -> None:
        opened.append((path, show_folder))

    monkeypatch.setattr(state_module, "_open_path", open_path)
    state_module._open_episode(session, "episode", ".", show_folder=show_folder)
    assert opened == [(video, show_folder)]


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


def _assert_list_fills_available_rows(controller: StateController) -> None:
    controller._subscriptions.extend(
        {"series": f"Series {index}", "enabled": False, "group": "Group", "next_episode": 1} for index in range(20)
    )
    frame: str = controller.render(80, 24).plain
    assert sum("● " in line or "○ " in line for line in frame.splitlines()) == 17
    assert "Space wybierz" in frame
    assert len(frame.splitlines()) <= 24
    controller.handle_key("end")
    assert controller._selected == 21
    controller.handle_key("home")
    assert controller._selected == 0


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
        controller.handle_key("tab")
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
            "acquisitions": [
                {
                    "info_hash": "episode",
                    "directory": "Episode",
                    "episode": "22",
                    "state": "accepted",
                    "problem": problem,
                }
            ],
            "transfers": [{"info_hash": "episode", "name": "Episode.mkv", "progress": 0.0, "state": "stoppedDL"}],
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
            "acquisitions": [
                {"info_hash": "episode", "directory": "Episode", "episode": "22", "state": "accepted"},
            ],
            "transfers": [],
            "transfers_problem": None,
        },
    )

    assert "brak potwierdzenia klienta" in frame
    assert "wymaga uwagi" not in frame


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
