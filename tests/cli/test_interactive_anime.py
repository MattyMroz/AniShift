from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.text import Text

from anishift.application import (
    AppService,
    EntryGroup,
    EpisodeBatch,
    EpisodeKey,
    EpisodeListing,
    EpisodeResult,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    ListedEpisode,
    TitleCandidate,
    TitleStatus,
    encode_view,
)
from anishift.cli.interactive import anime as anime_module
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.anime import AnimeController, AnimeResult, _Screen
from anishift.cli.interactive.anime_view import AnimeFrame
from anishift.cli.interactive.state import StateController, _Tab
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.platform.local_control import ControlClient, ControlError, ControlErrorCode

pytestmark = pytest.mark.unit


def _title() -> TitleCandidate:
    return TitleCandidate(1, "Slime", "Slime", None, (), 2026, None, "TV", 3, TitleStatus.RELEASING, ())


def _entry(identifier: int = 1, year: int = 2026, status: str = "RELEASING") -> FranchiseEntry:
    return FranchiseEntry(identifier, "Slime", "Slime", None, "TV", status, year, None, "SELF", EntryGroup.SEASON)


class _Owner:
    def __init__(self) -> None:
        self.titles: tuple[TitleCandidate, ...] = (_title(),)
        self.franchise_view: Franchise = Franchise(1, (_entry(),), (), True)
        self.listing: EpisodeListing = EpisodeListing(
            1,
            None,
            "TV",
            "RELEASING",
            3,
            tuple(ListedEpisode(number, f"Odcinek {number}", aired=True) for number in range(1, 4)),
            (),
            3,
            None,
            None,
        )
        self.calls: list[tuple[tuple[EpisodeKey, ...], str]] = []
        self.states: tuple[EpisodeStatus, ...] = ()
        self.searches: list[str] = []
        self.failure: Exception | None = None
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.release.set()

    def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
        self.searches.append(query)
        self.entered.set()
        assert self.release.wait(5)
        if self.failure:
            raise self.failure
        return self.titles

    def franchise(self, identifier: int, *, cancel: object = None) -> Franchise:
        del identifier, cancel
        return self.franchise_view

    def episodes(self, identifier: int) -> EpisodeListing:
        return replace(self.listing, anilist_id=identifier)

    def episode_states(self, identifier: int, numbers: object) -> tuple[EpisodeStatus, ...]:
        del identifier, numbers
        return self.states

    def episode_download(self, keys: tuple[EpisodeKey, ...], *, command_id: str) -> EpisodeBatch:
        self.calls.append((keys, command_id))
        if self.failure:
            raise self.failure
        return EpisodeBatch(
            command_id, "owner", keys, "completed", tuple(EpisodeResult(key, "admitted") for key in keys)
        )

    def interrupt_reads(self) -> None:
        return


def _controller(owner: _Owner) -> AnimeController:
    return AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )


def _settle(controller: AnimeController) -> None:
    worker: threading.Thread | None = controller._worker
    if worker is not None:
        worker.join(5)
        assert not worker.is_alive()
    deadline: float = monotonic() + 5
    while controller._batch_running and monotonic() < deadline:
        threading.Event().wait(0.005)
    assert not controller._batch_running


def _first_row(controller: AnimeController) -> int:
    frame: AnimeFrame | None = controller._panel._frame
    assert frame is not None
    return frame.first_row


def _open(controller: AnimeController) -> None:
    controller.handle_key("text:slime")
    controller.handle_key("enter")
    _settle(controller)
    assert controller._screen is _Screen.EPISODES


def test_search_edits_selected_words_before_submitting_the_final_query() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    for key in ("text:old title", "ctrl-shift-left", "text:anime", "home", "ctrl-delete", "delete", "enter"):
        controller.handle_key(key)
    _settle(controller)
    assert owner.searches == ["anime"]


def test_typed_characters_and_backspace_edit_the_searched_title() -> None:
    controller: AnimeController = _controller(_Owner())
    controller.handle_key("text:oshi no koo")
    controller.handle_key("backspace")
    assert controller._query == "oshi no ko"
    assert "oshi no ko" in controller.render(80, 24).plain
    assert any(span.style == "reverse" for span in controller.render(80, 24).spans)


@pytest.mark.parametrize("width", [50, 80, 120])
def test_query_and_its_search_show_the_classic_heading_without_a_context_line(width: int) -> None:
    owner: _Owner = _Owner()
    owner.release.clear()
    controller: AnimeController = _controller(owner)
    controller.handle_key("text:slime")
    lines: list[str] = controller.render(width, 24).plain.splitlines()
    field: int = next(index for index, line in enumerate(lines) if "> slime" in line)
    assert lines[field - 2].strip() == "ANIME"
    assert not "".join(lines[: field - 2]).strip()
    assert not lines[field - 1].strip()
    controller.handle_key("enter")
    assert owner.entered.wait(5)
    painted: Text = controller.render(width, 24)
    start: int = painted.plain.index("Szukam tytułu…")
    assert any(span.style == "brand_accent" and span.start <= start < span.end for span in painted.spans)
    searching: list[str] = painted.plain.splitlines()
    assert searching[field - 2].strip() == "ANIME"
    assert searching[field].strip() == "Szukam tytułu…"
    assert not "".join(searching[: field - 2]).strip()
    assert "> " not in "".join(searching)
    owner.release.set()
    _settle(controller)


@pytest.mark.parametrize("entries", [1, 2])
def test_returning_from_an_entry_to_the_query_drops_its_context(entries: int) -> None:
    owner: _Owner = _Owner()
    puniru: FranchiseEntry = replace(_entry(1, 2025), english="Puniru is a Kawaii Slime Season 2")
    owner.franchise_view = Franchise(1, (puniru, _entry(3, 2024))[:entries], (), True)
    controller: AnimeController = _controller(owner)
    controller.handle_key("text:slime")
    controller.handle_key("enter")
    _settle(controller)
    if entries > 1:
        controller.handle_key("enter")
        _settle(controller)
    assert "Puniru" in controller.render(80, 24).plain
    for _ in range(entries):
        controller.handle_key("escape")
    assert controller._screen is _Screen.QUERY
    lines: list[str] = controller.render(80, 24).plain.splitlines()
    assert controller._view.title == ""
    assert "Puniru" not in "".join(lines)
    assert "ANIME" in "".join(lines)


@pytest.mark.parametrize("width", [50, 80, 120])
def test_returning_from_episodes_to_the_franchise_empties_the_breadcrumb_above_the_table(width: int) -> None:
    owner: _Owner = _Owner()
    puniru: FranchiseEntry = replace(_entry(1, 2025), english="Puniru is a Kawaii Slime Season 2")
    owner.franchise_view = Franchise(1, (puniru, _entry(3, 2024)), (), True)
    controller: AnimeController = _controller(owner)
    controller.handle_key("text:slime")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)
    episodes: list[str] = controller.render(width, 24).plain.splitlines()
    header: int = next(index for index, line in enumerate(episodes) if "Emisja" in line)
    assert episodes[header - 2].strip().startswith("Anime \u203a Puniru")
    controller.handle_key("escape")
    lines: list[str] = controller.render(width, 24).plain.splitlines()
    header = next(index for index, line in enumerate(lines) if "Premiera" in line)
    assert not lines[header - 2].strip()
    assert not lines[header - 1].strip()
    assert "\u203a" not in "".join(lines)
    controller.handle_key("enter")
    _settle(controller)
    assert controller._screen is _Screen.EPISODES
    assert "Anime \u203a Puniru" in controller.render(width, 24).plain


def test_cancelled_episode_loading_after_a_search_drops_the_entry_context() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    with controller._lock:
        controller._entry = _entry()
        controller._shown_entry = _entry()
        controller._busy_return = _Screen.QUERY
        controller._screen = _Screen.BUSY
    controller.handle_key("escape")
    controller.render(80, 24)
    assert controller._screen is _Screen.QUERY
    assert controller._view.title == ""


def test_enter_on_a_blank_title_starts_no_search() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    for key in ("text:   ", "enter"):
        controller.handle_key(key)
    assert owner.searches == []
    assert controller._screen is _Screen.QUERY
    assert controller._worker is None


def test_a_pasted_title_drops_its_control_characters() -> None:
    controller: AnimeController = _controller(_Owner())
    controller.handle_key("paste:oshi no ko\r\n")
    assert controller._query == "oshi no ko"
    assert "oshi no ko" in controller.render(80, 24).plain


def test_an_unknown_title_reports_no_match_without_release_search() -> None:
    owner: _Owner = _Owner()
    owner.titles = ()
    controller: AnimeController = _controller(owner)
    for key in ("text:unknown", "enter"):
        controller.handle_key(key)
    _settle(controller)
    assert "Nie znaleziono tytułu" in controller.render(80, 24).plain
    assert owner.calls == []
    controller.handle_key("enter")
    assert controller._screen is _Screen.QUERY


@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("code", [ErrorCode.TITLE_CATALOG_FAILED, ErrorCode.IO_ERROR, ErrorCode.UNKNOWN])
def test_a_catalog_failure_never_falls_back_to_release_search(*, remote: bool, code: ErrorCode) -> None:
    owner: _Owner = _Owner()
    owner.failure = (
        ControlError("private failure", reason=code.value, answered=True)
        if remote
        else AniShiftError(context=ErrorContext(code=code, message="private failure"))
    )
    controller: AnimeController = _controller(owner)
    for key in ("text:slime", "enter"):
        controller.handle_key(key)
    _settle(controller)
    assert controller._screen is _Screen.PROBLEM
    assert not owner.calls
    assert "private failure" not in controller.render(80, 24).plain


def test_escape_during_the_search_discards_a_late_result() -> None:
    owner: _Owner = _Owner()
    owner.release.clear()
    controller: AnimeController = _controller(owner)
    for key in ("text:slime", "enter"):
        controller.handle_key(key)
    worker: threading.Thread | None = controller._worker
    try:
        assert owner.entered.wait(5)
        assert str(controller._screen) == "busy"
        controller.handle_key("escape")
    finally:
        owner.release.set()
        assert worker is not None
        worker.join(5)
    assert controller._screen is _Screen.QUERY
    assert not controller._candidates


def test_a_session_without_the_acquisition_boundary_reports_it_and_escape_returns_home() -> None:
    controller: AnimeController = AnimeController(cast("AppService", SimpleNamespace(acquisition=None)), lambda: None)
    assert "Pobieranie jest niedostępne w tej sesji" in controller.render(80, 24).plain
    assert controller.handle_key("escape") is AnimeResult.HOME


@pytest.mark.parametrize("width", [50, 80, 120])
def test_live_franchise_starts_on_the_newest_announcement_and_wraps(width: int) -> None:
    owner: _Owner = _Owner()
    owner.franchise_view = Franchise(1, (_entry(1, 2018), _entry(4), _entry(5, 2027, "NOT_YET_RELEASED")), (), True)
    controller: AnimeController = _controller(owner)
    for key in ("text:slime", "enter"):
        controller.handle_key(key)
    _settle(controller)
    frame: str = controller.render(width, 24).plain
    assert frame.index("2027") < frame.index("2026") < frame.index("2018")
    assert controller._positions[_Screen.ENTRIES] == 0
    controller.handle_key("enter")
    assert controller._screen is _Screen.ENTRIES
    assert "odcinków jeszcze nie ma" in controller.render(width, 24).plain
    controller.handle_key("up")
    assert controller._positions[_Screen.ENTRIES] == 2
    controller.handle_key("down")
    assert controller._positions[_Screen.ENTRIES] == 0
    controller.handle_key("down")
    assert controller._positions[_Screen.ENTRIES] == 1
    controller.handle_key("enter")
    _settle(controller)
    assert controller._entry is not None
    assert controller._entry.anilist_id == 4
    assert controller._positions[_Screen.EPISODES] == 0
    controller.handle_key("escape")
    assert controller._positions[_Screen.ENTRIES] == 1
    assert all(Text(line).cell_len == width for line in frame.splitlines())


def test_owner_refusal_keeps_marks_and_names_the_refusal() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    _open(controller)
    owner.failure = ControlError("refused", code=ControlErrorCode.REFUSED, reason="shutting_down", answered=True)
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)
    frame: str = controller.render(80, 24).plain
    assert len(owner.calls) == 1
    assert controller._episode_marks == {1}
    assert "[x]" in frame
    assert controller._pending_batch is None
    assert "Nie zlecono · AniShift się kończy · nie przyjmuje już nowej pracy" in frame
    assert "AniShift wstrzymany" not in frame


@pytest.mark.parametrize("aired", [False, True])
@pytest.mark.parametrize("recorded", [False, True])
def test_unordered_episode_label_depends_on_airing_not_on_presence_of_owner_record(
    *, aired: bool, recorded: bool
) -> None:
    owner: _Owner = _Owner()
    owner.listing = replace(owner.listing, episodes=(ListedEpisode(1, "First", aired=aired),))
    controller: AnimeController = _controller(owner)
    _open(controller)
    if recorded:
        controller._episode_states[EpisodeKey(1, 1)] = EpisodeStatus(EpisodeKey(1, 1), "not_ordered")
    lines: list[str] = controller.render(80, 24).plain.splitlines()
    row: int = _first_row(controller)
    assert lines[row][lines[row - 1].index("Stan") :].strip() == ("Do pobrania" if aired else "Nie wyemitowano")
    assert not lines[-4].strip()


def test_download_unknown_result_replays_exact_command_and_payload() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    _open(controller)
    owner.failure = OSError("lost response")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)
    assert "Wynik nieznany" in controller.render(80, 24).plain
    for key in ("space", "text:a", "text:z", "text:d"):
        controller.handle_key(key)
    assert controller._episode_marks == {1}
    assert len(owner.calls) == 1
    owner.failure = None
    controller.handle_key("enter")
    _settle(controller)
    assert len(owner.calls) == 2
    assert owner.calls[0] == owner.calls[1]
    assert not controller._episode_marks
    assert controller._pending_batch is None


def test_live_batch_feedback_resets_before_the_next_download() -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    _open(controller)
    controller.handle_key("text:d")
    _settle(controller)
    assert controller._notice == "Zlecono 1"
    controller.handle_key("down")
    controller.handle_key("text:d")
    _settle(controller)
    assert controller._notice == "Zlecono 2"


@pytest.mark.parametrize("state", ["ready", "downloaded", "processing_failed", "possibly_admitted", "unknown"])
def test_terminal_episode_space_download_submits_repeat_capable_owner_batch(state: str) -> None:
    owner: _Owner = _Owner()
    owner.states = (EpisodeStatus(EpisodeKey(1, 1), state, admission_id="previous"),)
    controller: AnimeController = _controller(owner)
    _open(controller)
    controller.handle_key("space")
    assert controller._episode_marks == {1}
    controller.handle_key("text:d")
    _settle(controller)
    assert owner.calls[0][0] == (EpisodeKey(1, 1),)
    assert controller._screen is _Screen.EPISODES
    assert controller._confirm_choice is None


def test_mixed_download_includes_new_and_ready_and_skips_active_episode() -> None:
    owner: _Owner = _Owner()
    owner.states = (EpisodeStatus(EpisodeKey(1, 2), "ready"), EpisodeStatus(EpisodeKey(1, 3), "downloading"))
    controller: AnimeController = _controller(owner)
    _open(controller)
    controller.handle_key("text:a")
    assert controller._episode_marks == {1, 2}
    controller.handle_key("text:d")
    _settle(controller)
    assert owner.calls[0][0] == (EpisodeKey(1, 1), EpisodeKey(1, 2))


def test_live_details_keep_selection_across_frames_and_preserve_episode_cursor() -> None:
    controller: AnimeController = _controller(_Owner())
    _open(controller)
    copied: list[str] = []

    def clipboard(text: str) -> bool:
        copied.append(text)
        return True

    controller._panel._clipboard = clipboard
    controller.handle_key("down")
    controller.handle_key("text:?")
    lines: list[str] = controller.render(80, 24).plain.splitlines()
    row: int = _first_row(controller)
    start: int = len(lines[row]) - len(lines[row].lstrip())
    for kind, point in (
        (MouseEventType.MOUSE_DOWN, Point(start, row)),
        (MouseEventType.MOUSE_MOVE, Point(start + 12, row)),
        (MouseEventType.MOUSE_UP, Point(start + 12, row)),
    ):
        controller.mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))
    controller.render(80, 24)
    controller.handle_key("interrupt")
    assert copied
    assert "Odcinek 2" in copied[0]
    assert controller._details_open
    controller.handle_key("escape")
    assert not controller._details_open
    assert controller._positions[_Screen.EPISODES] == 1


@pytest.mark.parametrize(("leave", "back"), [("tab", "backtab"), ("backtab", "tab")])
def test_application_tab_cancels_pending_search_and_returns_to_an_idle_draft(
    monkeypatch: pytest.MonkeyPatch, leave: str, back: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    owner: _Owner = _Owner()
    owner.release.clear()
    anime: AnimeController = _controller(owner)
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    worker: threading.Thread | None = None
    try:
        for key in ("left", "left", "text:slime", "enter"):
            panel.handle_key(key)
        assert owner.entered.wait(5)
        worker = anime._worker
        panel.handle_key(leave)
        panel.handle_key(back)
        before: str = panel.render(80, 24).plain
        assert "slime" in before
        assert not anime.input_focused
        owner.release.set()
        assert worker is not None
        worker.join(5)
        assert not worker.is_alive()
        assert panel.render(80, 24).plain == before
        panel.handle_key("enter")
        assert anime.input_focused
        assert anime._worker is None
    finally:
        owner.release.set()
        if worker is not None:
            worker.join(5)
        panel.close()
        panel._thread.join(5)


def test_correlated_results_clear_each_mark_once_and_survive_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anime_module, "_BATCH_POLL_S", 0.001)
    entered: threading.Event = threading.Event()
    released: threading.Event = threading.Event()
    owner: _Owner = _Owner()
    controller: AnimeController = _controller(owner)
    _open(controller)
    controller.handle_key("text:a")

    def download(keys: tuple[EpisodeKey, ...], *, command_id: str) -> EpisodeBatch:
        entered.set()
        assert released.wait(5)
        return EpisodeBatch(
            command_id,
            "owner",
            keys,
            "completed",
            (
                EpisodeResult(keys[0], "admitted"),
                EpisodeResult(keys[1], "no_suggestion"),
                EpisodeResult(keys[2], "no_suggestion"),
            ),
        )

    monkeypatch.setattr(owner, "episode_download", download)
    controller.handle_key("text:d")
    try:
        assert entered.wait(5)
        batch: EpisodeBatch | None = controller._pending_batch
        assert batch is not None
        payload: dict[str, object] = {
            "command_id": batch.command_id,
            **encode_view(EpisodeResult(batch.keys[0], "admitted")),
        }
        controller.receive("episode_result", {**payload, "command_id": "foreign"})
        assert controller._episode_marks == {1, 2, 3}
        controller.receive("episode_result", payload)
        assert controller._episode_marks == {2, 3}
        deadline: float = controller._view.flashes["1"]
        controller.receive("episode_result", payload)
        assert controller._view.flashes["1"] == deadline
        controller.handle_key("escape")
        before: _Screen = controller._screen
    finally:
        released.set()
        _settle(controller)
    assert controller._screen is before
    assert controller._episode_marks == {2, 3}


@pytest.mark.parametrize("size", [(50, 24), (80, 24), (120, 40), (40, 6)])
def test_panel_query_requires_focus_and_preserves_text_across_tabs(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    anime: AnimeController = _controller(_Owner())
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    try:
        for key in ("left", "left", "text:abc", "left", "text:x", "escape"):
            panel.handle_key(key)
        assert anime._query == "abxc"
        assert not anime.input_focused
        frame: str = panel.render(*size).plain
        for key in ("tab", "backtab"):
            panel.handle_key(key)
        assert panel.render(*size).plain == frame
        assert len(frame.splitlines()) <= size[1]
        assert all(Text(line).cell_len <= size[0] for line in frame.splitlines())
    finally:
        panel.close()
        panel._thread.join(5)


def test_live_app_mouse_routes_unicode_text_selection_and_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    owner: _Owner = _Owner()
    anime: AnimeController = _controller(owner)
    _open(anime)
    copied: list[str] = []

    def clipboard(text: str) -> bool:
        copied.append(text)
        return True

    anime._panel._clipboard = clipboard
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    application: interactive_app._InteractiveApplication = object.__new__(interactive_app._InteractiveApplication)
    application._mode = interactive_app._ViewMode.STATE
    application._state = panel
    try:
        for key in ("left", "left"):
            panel.handle_key(key)
        lines: list[str] = panel.render(120, 24).plain.splitlines()
        first: int = panel._anime_top + _first_row(anime)
        start: Point = Point(lines[first].index("Odcinek 1"), first)
        end: Point = Point(lines[first + 1].index("Odcinek 2") + len("Odcinek 2"), first + 1)
        for kind, point in (
            (MouseEventType.MOUSE_DOWN, start),
            (MouseEventType.MOUSE_MOVE, end),
            (MouseEventType.MOUSE_UP, end),
        ):
            application._handle_mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))
        panel.render(120, 24)
        panel.handle_key("interrupt")
        assert copied
        assert "Odcinek 1" in copied[0]
        assert "Odcinek 2" in copied[0]
        assert "[ ]" not in copied[0]
        assert anime._screen is _Screen.EPISODES
        panel.scroll(1)
        assert anime._view.selection is None
    finally:
        panel.close()
        panel._thread.join(5)


def test_typing_on_the_fresh_search_field_writes_every_letter_without_toggling_automation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[str] = []

    def call(kind: str, payload: Mapping[str, object], **options: object) -> Mapping[str, object]:
        del payload, options
        calls.append(kind)
        return {"auto_enabled": True}

    client: ControlClient = cast("ControlClient", SimpleNamespace(call=call, close=lambda: None))
    session: ResidentSession = ResidentSession(Path("workspace"), lambda: client)
    panel: StateController = StateController(session, lambda: None)
    anime: AnimeController = _controller(_Owner())
    panel.attach_anime(anime)
    panel._snapshot = {"auto_enabled": False}
    panel._connected = True
    try:
        panel._switch_tab(_Tab.ANIME)
        assert anime._screen is _Screen.QUERY
        assert not anime.input_focused
        for letter in "Overlord":
            panel.handle_key(f"text:{letter}")
        deadline: float = monotonic() + 5
        while panel._busy and monotonic() < deadline:
            threading.Event().wait(0.005)
        assert anime._query == "Overlord"
        assert calls == []
    finally:
        panel.close()
        panel._thread.join(5)
        session.close()


def test_global_resume_in_anime_uses_owner_without_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[str] = []

    def call(kind: str, payload: Mapping[str, object], **options: object) -> Mapping[str, object]:
        del options
        calls.append(kind)
        assert kind == "set_auto"
        assert payload["enabled"] is True
        return {"auto_enabled": True}

    client: ControlClient = cast("ControlClient", SimpleNamespace(call=call, close=lambda: None))
    session: ResidentSession = ResidentSession(Path("workspace"), lambda: client)
    panel: StateController = StateController(session, lambda: None)
    anime: AnimeController = _controller(_Owner())
    _open(anime)
    panel.attach_anime(anime)
    panel._snapshot = {"auto_enabled": False}
    panel._connected = True
    try:
        for key in ("left", "left", "text:o"):
            panel.handle_key(key)
        deadline: float = monotonic() + 5
        while panel._busy and monotonic() < deadline:
            threading.Event().wait(0.005)
        assert calls == ["set_auto"]
    finally:
        panel.close()
        panel._thread.join(5)
        session.close()
