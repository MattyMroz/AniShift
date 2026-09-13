from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import (
    ArtifactKind,
    GroupIntent,
    ProductIntent,
    ProductKind,
    RunEvent,
    RunEventKind,
    RunMode,
    TaskKind,
    TaskState,
)
from anishift.application.control_views import PlanPreview, PreviewGroup, PreviewTask, RunProgressSnapshot, encode_view
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.state import StateController, StateResult
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import (
    ControlClient,
    ControlRequest,
    ControlResponse,
    ControlServer,
    control_endpoint,
)


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
