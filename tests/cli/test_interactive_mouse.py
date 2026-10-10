from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.text import Text
from test_interactive_manual import _audiobook_controller
from test_interactive_manual import _controller as _manual_controller
from test_interactive_settings_autosave import FakeSettingsService
from test_interactive_state import _row

from anishift.application import AppService
from anishift.application.control_views import RetryProposal, encode_view
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeViewState, TextPoint
from anishift.cli.interactive.manual import ManualController, ManualResult
from anishift.cli.interactive.manual import _Screen as _ManualScreen
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.menu import append_wrapped_row
from anishift.cli.interactive.pointer import (
    FrameSelection,
    PointerGesture,
    mark_row,
    painted_cells,
    row_at,
    selected_text,
)
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.settings import _PRODUCTS as _SETTINGS_PRODUCTS
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_Mode = interactive_app._ViewMode


class _Renderer:
    native_mascot_size: tuple[int, int] | None = (18, 10)
    animation_phase: int = 0

    def __init__(self, *_arguments: object, **_options: object) -> None:
        self.exits: int = 0

    def invalidate(self) -> None:
        return

    def exit(self) -> None:
        self.exits += 1


class _Queue:
    row_count: int = 12
    active_row: int = 0

    def render(self, columns: int, *, offset: int = 0, limit: int | None = None) -> Text:
        del columns
        end: int = self.row_count if limit is None else offset + limit
        return Text("\n".join(f"plik-{index:02d}" for index in range(offset, min(end, self.row_count))))


def _application(
    monkeypatch: pytest.MonkeyPatch, mode: interactive_app._ViewMode
) -> tuple[interactive_app._InteractiveApplication, list[str]]:
    monkeypatch.setattr(interactive_app, "TerminalRenderer", _Renderer)
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        cast("AppService", SimpleNamespace())
    )
    copied: list[str] = []

    def clipboard(value: str) -> bool:
        copied.append(value)
        return True

    application._frame_selection = FrameSelection(clipboard)
    application._mode = mode
    return application, copied


def _event(kind: MouseEventType, point: Point) -> MouseEvent:
    return MouseEvent(point, kind, MouseButton.LEFT, frozenset())


def _click(application: interactive_app._InteractiveApplication, point: Point) -> None:
    for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
        application._handle_mouse(_event(kind, point))


def _drag(application: interactive_app._InteractiveApplication, start: Point, end: Point) -> None:
    application._handle_mouse(_event(MouseEventType.MOUSE_DOWN, start))
    application._handle_mouse(_event(MouseEventType.MOUSE_MOVE, end))
    application._handle_mouse(_event(MouseEventType.MOUSE_UP, end))


def _point(frame: Text, text: str) -> Point:
    lines: list[str] = frame.plain.split("\n")
    rows: list[int] = [row for row, line in enumerate(lines) if text in line]
    assert len(rows) == 1, text
    line: str = lines[rows[0]]
    return Point(Text(line[: line.index(text)]).cell_len, rows[0])


def _reversed(frame: Text) -> str:
    return "".join(frame.plain[span.start : span.end] for span in frame.spans if span.style == "reverse")


def _state(monkeypatch: pytest.MonkeyPatch) -> StateController:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    session: ResidentSession = cast(
        "ResidentSession", SimpleNamespace(command=lambda kind: {"subscriptions": []}, library=lambda: ())
    )
    controller: StateController = StateController(session, lambda: None)
    controller._connected = True
    controller.set_notice("")
    return controller


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Iterator[StateController]:
    controller: StateController = _state(monkeypatch)
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {"library": [{"set_id": f"set-{index}", "name": f"Episode {index}"} for index in range(40)]}
    try:
        yield controller
    finally:
        controller.close()
        controller._thread.join(5)


def _settings(service: FakeSettingsService, category: str) -> SettingsController:
    controller: SettingsController = SettingsController(cast("AppService", service), lambda: None)
    controller._selected = next(
        index for index, item in enumerate(controller._items) if item.key == f"category:{category}"
    )
    controller.handle_key("enter")
    return controller


def test_pointer_gesture_tells_a_click_from_a_drag() -> None:
    gesture: PointerGesture = PointerGesture()
    start: Point = Point(2, 1)
    end: Point = Point(6, 1)

    gesture.track(_event(MouseEventType.MOUSE_DOWN, start))
    click = gesture.track(_event(MouseEventType.MOUSE_UP, start))
    gesture.track(_event(MouseEventType.MOUSE_DOWN, start))
    gesture.track(_event(MouseEventType.MOUSE_MOVE, end))
    drag = gesture.track(_event(MouseEventType.MOUSE_UP, end))

    assert click is not None
    assert click.selection is None
    assert click.click is not None
    assert (click.click.row, click.click.column) == (1, 2)
    assert drag is not None
    assert drag.click is None
    assert drag.selection is not None


def test_row_at_names_every_line_of_a_wrapped_row_and_nothing_else() -> None:
    content: Text = Text("NAGŁÓWEK\n")
    append_wrapped_row(content, 2, ("pierwsza linia", "  dalszy ciąg"), False, "", index=7)
    content.append("stopka")
    mark_row(Text("bez znacznika"), 3)

    assert [row_at(content, row) for row in range(5)] == [None, 7, 7, None, None]


def test_home_click_points_at_the_clicked_choice_without_running_it(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    renderer: _Renderer = cast("_Renderer", application._renderer)

    for label, index in (("Ustawienia", 2), ("Wyjście", 3), ("Panel", 0)):
        _click(application, _point(application._render_frame(80, 24), label))
        assert application._selected == index

    assert application._mode is _Mode.HOME
    assert renderer.exits == 0


def test_home_click_beside_the_choices_keeps_the_cursor_until_a_choice_is_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    application._selected = 1
    frame: Text = application._render_frame(80, 24)

    _click(application, _point(frame, "Enter"))
    _click(application, Point(0, 0))
    _click(application, Point(0, 23))
    beside: int = application._selected
    _click(application, _point(frame, "Ustawienia"))

    assert beside == 1
    assert application._selected == 2


def test_home_drag_over_the_mascot_never_copies_its_image_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.HOME)
    frame: Text = application._render_frame(80, 24)
    end: Point = _point(frame, "Panel")

    _drag(application, Point(0, 0), Point(79, end.y))
    application._render_frame(80, 24)
    application._handle_key("copy")

    assert NATIVE_MASCOT_ANCHOR in frame.plain
    assert copied
    assert copied[0].endswith("Panel")
    assert NATIVE_MASCOT_ANCHOR not in copied[0]


@pytest.mark.parametrize(("columns", "rows"), [(80, 24), (120, 30)])
def test_home_drag_over_the_brand_selects_and_copies_nothing(
    monkeypatch: pytest.MonkeyPatch, columns: int, rows: int
) -> None:
    application, copied = _application(monkeypatch, _Mode.HOME)
    frame: Text = application._render_frame(columns, rows)
    last: int = max(row for row, line in enumerate(frame.plain.split("\n")) if "█" in line)

    _drag(application, Point(0, 0), Point(columns - 1, last))
    painted: Text = application._render_frame(columns, rows)
    application._handle_key("copy")

    assert "█" in frame.plain
    assert _reversed(painted) == ""
    assert copied == []


def test_small_home_click_reaches_its_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)

    _click(application, _point(application._render_frame(50, 7), "Ręczny"))

    assert application._selected == 1


def test_home_drag_selects_painted_text_and_ctrl_c_copies_it_instead_of_exiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, copied = _application(monkeypatch, _Mode.HOME)
    renderer: _Renderer = cast("_Renderer", application._renderer)
    start: Point = _point(application._render_frame(80, 24), "Ręczny")

    _drag(application, start, Point(start.x + len("Ręczny") - 1, start.y))
    painted: Text = application._render_frame(80, 24)
    application._handle_key("interrupt")

    assert _reversed(painted) == "Ręczny"
    assert copied == ["Ręczny"]
    assert NATIVE_MASCOT_ANCHOR not in copied[0]
    assert renderer.exits == 0
    assert application._selected == 0
    assert "Skopiowano zaznaczenie" in application._render_frame(80, 24).plain


def test_another_key_drops_the_selection_and_reaches_the_view(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.HOME)
    start: Point = _point(application._render_frame(80, 24), "Ręczny")
    _drag(application, start, Point(start.x + 3, start.y))
    painted: Text = application._render_frame(80, 24)

    application._handle_key("down")
    application._handle_key("copy")

    assert _reversed(painted) == "Ręcz"
    assert application._selected == 1
    assert copied == []
    assert _reversed(application._render_frame(80, 24)) == ""


def test_settings_click_moves_the_cursor_without_opening_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = SettingsController(cast("AppService", FakeSettingsService()), lambda: None)
    application._settings = controller
    target: str = controller._items[2].label

    _click(application, _point(application._render_frame(100, 30), target))

    assert controller._items[controller._selected].label == target
    assert controller._category is None
    assert controller._editor is None


def test_settings_click_ignores_the_title_section_and_hint_but_not_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = _settings(FakeSettingsService(), "subtitles")
    application._settings = controller
    controller._selected = 1
    frame: Text = application._render_frame(100, 30)
    lines: list[str] = frame.plain.split("\n")
    title: int = next(row for row, line in enumerate(lines) if line.strip())
    hint: int = max(row for row, line in enumerate(lines[:-1]) if line.strip())

    for row in (title, title + 2, hint):
        _click(application, Point(len(lines[row]) - len(lines[row].lstrip()), row))
    beside: int = controller._selected
    _click(application, Point(4, _row_of(frame, 0)))

    assert beside == 1
    assert controller._selected == 0


@pytest.mark.parametrize("columns", [50, 100])
def test_settings_click_after_the_wheel_lands_on_the_painted_row(monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = _settings(FakeSettingsService(), "tts")
    application._settings = controller
    application._render_frame(columns, 14)
    for _notch in range(2):
        application._handle_scroll(1)
    frame: Text = application._render_frame(columns, 14)
    offset: int = controller._offset
    target: int = offset + 1

    _click(application, Point(4, _row_of(frame, target)))
    application._render_frame(columns, 14)

    assert offset > 0
    assert controller._selected == target
    assert controller._offset == offset


def _row_of(frame: Text, index: int) -> int:
    return next(row for row in range(len(frame.plain.split("\n"))) if row_at(frame, row) == index)


def test_settings_click_saves_a_pending_number_before_leaving_its_row(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    service: FakeSettingsService = FakeSettingsService()
    controller: SettingsController = _settings(service, "subtitles")
    application._settings = controller
    controller._selected = next(
        index for index, item in enumerate(controller._items) if item.key == "setting:subtitle_max_chars_per_line"
    )
    controller.handle_key("right")
    frame: Text = application._render_frame(100, 30)
    other: int = next(index for index in range(len(controller._items)) if index != controller._selected)

    _click(application, Point(4, _row_of(frame, other)))

    assert service.saves == [("subtitle_max_chars_per_line", 43)]
    assert controller._selected == other


def test_settings_click_in_a_choice_editor_moves_without_choosing(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    service: FakeSettingsService = FakeSettingsService()
    controller: SettingsController = _settings(service, "general")
    application._settings = controller
    controller._selected = next(
        index for index, item in enumerate(controller._items) if item.key == "setting:processing_order_policy"
    )
    controller.handle_key("enter")
    editor = controller._editor
    assert editor is not None
    target: int = (editor.selected + 1) % len(editor.options)

    _click(application, _point(application._render_frame(100, 30), editor.options[target].label))

    assert editor.selected == target
    assert controller._editor is editor
    assert service.saves == []


def test_settings_drag_copies_a_row_label(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = SettingsController(cast("AppService", FakeSettingsService()), lambda: None)
    application._settings = controller
    label: str = controller._items[1].label
    start: Point = _point(application._render_frame(100, 30), label)

    _drag(application, start, Point(start.x + len(label) - 1, start.y))
    application._render_frame(100, 30)
    application._handle_key("copy")

    assert copied == [label]
    assert controller._category is None


def _manual(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[interactive_app._InteractiveApplication, ManualController, list[str]]:
    application, copied = _application(monkeypatch, _Mode.MANUAL)
    controller: ManualController = _manual_controller(tmp_path)
    application._manual = controller
    return application, controller, copied


def test_manual_click_moves_the_cursor_without_toggling_the_episode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    application, controller, _copied = _manual(monkeypatch, tmp_path)
    label: str = controller._labels[controller._group_ids[4]]

    _click(application, _point(application._render_frame(100, 40), label))

    assert controller._selected == 4
    assert controller._selected_groups == set()


def test_manual_click_in_a_windowed_narrow_list_lands_on_the_painted_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    application, controller, _copied = _manual(monkeypatch, tmp_path)
    for _step in range(10):
        controller.handle_key("down")
    frame: Text = application._render_frame(50, 16)
    shown: list[int] = [index for row in range(16) if (index := row_at(frame, row)) is not None]
    target: int = shown[1]

    _click(application, Point(4, _row_of(frame, target)))

    assert shown[0] > 0
    assert controller._selected == target


def test_manual_click_on_the_title_keeps_the_cursor_until_a_row_is_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    application, controller, _copied = _manual(monkeypatch, tmp_path)
    controller.handle_key("down")
    frame: Text = application._render_frame(100, 40)

    _click(application, _point(frame, "WYBIERZ ODCINKI"))
    beside: int = controller._selected
    _click(application, Point(4, _row_of(frame, 0)))

    assert beside == 1
    assert controller._selected == 0


def test_manual_drag_copies_an_episode_label(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    application, controller, copied = _manual(monkeypatch, tmp_path)
    label: str = controller._labels[controller._group_ids[2]]
    start: Point = _point(application._render_frame(100, 40), label)

    _drag(application, start, Point(start.x + len(label) - 1, start.y))
    application._render_frame(100, 40)
    application._handle_key("interrupt")

    assert copied == [label]
    assert application._mode is _Mode.MANUAL


def test_library_click_moves_the_cursor_without_opening_the_episode(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library

    _click(application, _point(application._render_frame(80, 24), "Episode 3"))

    assert library._selected == 3
    assert library._busy is False
    assert library._details is None


@pytest.mark.parametrize("columns", [50, 80])
def test_library_click_after_the_wheel_keeps_the_view_and_lands_on_the_row(
    monkeypatch: pytest.MonkeyPatch, library: StateController, columns: int
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    application._render_frame(columns, 20)
    for _notch in range(3):
        application._handle_scroll(1)
    frame: Text = application._render_frame(columns, 20)
    shown: list[int] = [index for row in range(20) if (index := row_at(frame, row)) is not None]
    target: int = shown[2]

    _click(application, Point(4, _row_of(frame, target)))
    after: Text = application._render_frame(columns, 20)

    assert shown[0] > 0
    assert library._selected == target
    assert [row_at(after, row) for row in range(20)] == [row_at(frame, row) for row in range(20)]


def test_library_click_on_the_last_painted_row_keeps_the_view(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    frame: Text = application._render_frame(80, 20)
    shown: list[int] = [index for row in range(20) if (index := row_at(frame, row)) is not None]

    _click(application, Point(4, _row_of(frame, shown[-1])))
    after: Text = application._render_frame(80, 20)

    assert library._selected == shown[-1]
    assert [row_at(after, row) for row in range(20)] == [row_at(frame, row) for row in range(20)]


def test_library_click_on_the_tabs_changes_nothing_until_a_row_is_hit(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    library._selected = 2
    frame: Text = application._render_frame(80, 24)

    _click(application, _point(frame, "Subskrypcje"))
    beside: int = library._selected
    _click(application, _point(frame, "Episode 0"))

    assert beside == 2
    assert library._selected == 0
    assert library._tab == state_module._Tab.FILES


def test_library_drag_copies_the_painted_names(monkeypatch: pytest.MonkeyPatch, library: StateController) -> None:
    application, copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    frame: Text = application._render_frame(80, 24)
    start: Point = _point(frame, "Episode 4")
    end: Point = _point(frame, "Episode 5")

    _drag(application, start, Point(end.x + len("Episode 5") - 1, end.y))
    application._render_frame(80, 24)
    application._handle_key("interrupt")

    assert copied == ["Episode 4\nEpisode 5"]
    assert application._mode is _Mode.STATE


def test_subscription_list_click_moves_the_cursor_without_opening_details(monkeypatch: pytest.MonkeyPatch) -> None:
    controller: StateController = _state(monkeypatch)
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._subscriptions = [encode_view(_row(f"s{index}", f"Series {index}")) for index in range(3)]
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = controller
    try:
        _click(application, _point(application._render_frame(80, 24), "Series 2"))

        assert controller._selected == 2
        assert controller._tab == state_module._Tab.SUBSCRIPTIONS
    finally:
        controller.close()
        controller._thread.join(5)


def test_processing_click_moves_the_cursor_without_a_command(monkeypatch: pytest.MonkeyPatch) -> None:
    controller: StateController = _state(monkeypatch)
    controller.show_processing()
    controller._snapshot = {
        "materials": [
            {
                "material_id": name,
                "info_hash": name,
                "stage": "download",
                "acquisition_state": "accepted",
                "state": "downloading",
                "name": f"{name}.mkv",
            }
            for name in ("Alpha", "Beta")
        ]
    }
    calls: list[object] = []
    monkeypatch.setattr(controller, "_command", lambda *args: calls.append(args))
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = controller
    try:
        _click(application, _point(application._render_frame(120, 40), "Beta.mkv"))

        assert controller._selected == 1
        assert calls == []
    finally:
        controller.close()
        controller._thread.join(5)


def test_message_drag_copies_the_report_and_a_click_keeps_it_open(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.MESSAGE)
    application._message = Text("Błąd · nie można zapisać pliku\nSzczegóły: logs/anishift.log.jsonl")
    start: Point = _point(application._render_frame(80, 24), "nie można")

    _click(application, start)
    _drag(application, start, Point(start.x + len("nie można zapisać") - 1, start.y))
    application._render_frame(80, 24)
    application._handle_key("copy")

    assert copied == ["nie można zapisać"]
    assert application._mode is _Mode.MESSAGE


def test_auto_queue_drag_copies_a_row_and_the_wheel_drops_the_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.AUTO)
    application._progress = cast("RichRunProgress", _Queue())
    start: Point = _point(application._render_frame(80, 30), "plik-03")

    _drag(application, start, Point(start.x + len("plik-03") - 1, start.y))
    painted: Text = application._render_frame(80, 30)
    application._handle_key("copy")
    application._handle_scroll(1)

    assert _reversed(painted) == "plik-03"
    assert copied == ["plik-03"]
    assert application._queue.following is False
    assert _reversed(application._render_frame(80, 30)) == ""


def test_a_resize_drops_a_selection_painted_for_the_old_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.MESSAGE)
    application._message = Text("Raport")
    start: Point = _point(application._render_frame(80, 24), "Raport")
    _drag(application, start, Point(start.x + 5, start.y))

    painted: Text = application._render_frame(80, 24)
    resized: Text = application._render_frame(90, 24)
    application._handle_key("copy")

    assert _reversed(painted) == "Raport"
    assert _point(resized, "Raport") == start
    assert _reversed(resized) == ""
    assert copied == []


def test_anime_list_screen_click_moves_only_to_a_navigable_painted_row() -> None:
    items: tuple[AnimeRow, ...] = (
        AnimeRow("line-aired", "Wyemitowane", navigable=False),
        AnimeRow("one", "Odcinek pierwszy", number="1"),
        AnimeRow("two", "Odcinek drugi", number="2"),
    )
    panel: AnimePanel = AnimePanel(
        AnimeViewState(screen=AnimeScreen.DRAFT, title="Subskrypcja", items=items, cursor=1),
        lambda _action, _keys: None,
        lambda: 0.0,
    )
    frame: Text = panel.frame(80, 24)

    for label in ("Wyemitowane", "Odcinek drugi"):
        point: Point = _point(frame, label)
        for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
            panel.mouse(_event(kind, point))
        panel.frame(80, 24)
        assert panel.state.cursor == (1 if label == "Wyemitowane" else 2)


_TO_GROUP_ACTION: tuple[str, ...] = ("space", "end", "down", "enter")
_TO_CUSTOM: tuple[str, ...] = (*_TO_GROUP_ACTION, "down", "enter")


def _audiobook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, keys: tuple[str, ...]
) -> tuple[interactive_app._InteractiveApplication, ManualController]:
    application, _copied = _application(monkeypatch, _Mode.MANUAL)
    controller: ManualController = _audiobook_controller(tmp_path)
    for key in keys:
        controller.handle_key(key)
    application._manual = controller
    return application, controller


@pytest.mark.parametrize(
    ("keys", "screen"),
    [
        (_TO_GROUP_ACTION, _ManualScreen.GROUP_ACTION),
        (_TO_CUSTOM, _ManualScreen.CUSTOM),
        ((*_TO_CUSTOM, "enter"), _ManualScreen.PRODUCTS),
        ((*_TO_CUSTOM, "down", "enter"), _ManualScreen.SUBTITLES),
        ((*_TO_CUSTOM, "down", "down", "down", "enter"), _ManualScreen.TIMELINE),
        (("space", "end", "enter"), _ManualScreen.PREVIEW),
    ],
)
def test_manual_click_on_each_screen_moves_the_cursor_without_choosing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, keys: tuple[str, ...], screen: _ManualScreen
) -> None:
    application, controller = _audiobook(monkeypatch, tmp_path, keys)
    frame: Text = application._render_frame(100, 40)
    drafts: object = dict(controller._drafts)
    last: int = controller._row_count() - 1
    target: int = last if controller._selected != last else 0

    _click(application, Point(4, _row_of(frame, target)))

    assert controller._screen is screen
    assert controller._selected == target
    assert controller._drafts == drafts
    assert controller.take_ready_run() is None


def test_manual_click_from_an_old_frame_never_reaches_the_new_screen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    application, controller = _audiobook(monkeypatch, tmp_path, ())
    groups: Text = application._render_frame(100, 40)
    for key in _TO_CUSTOM:
        application._handle_key(key)

    _click(application, Point(4, _row_of(groups, 2)))

    assert controller._screen is _ManualScreen.CUSTOM
    assert controller._selected == 0


def test_manual_select_ignores_a_row_the_current_screen_does_not_have(tmp_path: Path) -> None:
    controller: ManualController = _audiobook_controller(tmp_path)
    for key in _TO_CUSTOM:
        controller.handle_key(key)

    controller.select(9)
    result: ManualResult = controller.handle_key("enter")

    assert result is ManualResult.STAY
    assert controller._screen is _ManualScreen.PRODUCTS


def test_settings_click_on_the_back_row_points_at_it_without_leaving(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = _settings(FakeSettingsService(), "subtitles")
    application._settings = controller
    frame: Text = application._render_frame(100, 30)

    _click(application, Point(4, _row_of(frame, len(controller._items) - 1)))

    assert controller._selected == len(controller._items) - 1
    assert controller._category is not None
    assert application._mode is _Mode.SETTINGS


def test_settings_click_on_the_output_screen_moves_without_toggling(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    service: FakeSettingsService = FakeSettingsService()
    controller: SettingsController = _settings(service, "output")
    application._settings = controller
    products: object = set(controller._output_products)
    frame: Text = application._render_frame(100, 30)

    for target, label in ((2, _SETTINGS_PRODUCTS[2][1]), (len(_SETTINGS_PRODUCTS), "Przywróć domyślne")):
        _click(application, _point(frame, label))
        assert controller._selected == target

    assert controller._output_products == products
    assert controller._editor is None
    assert service.preset_saves == 0


def test_library_click_invalidates_late_results_of_the_previous_row(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    library.set_notice("Nie można usunąć")
    generation: int = library._view_generation

    _click(application, _point(application._render_frame(80, 24), "Episode 3"))

    assert library._view_generation == generation + 1
    assert library._notice == ""


def test_state_click_on_an_open_retry_keeps_the_hidden_cursor(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    library._selected = 5
    library._retry = RetryProposal("material", "manual", ("group",))
    frame: Text = application._render_frame(80, 24)

    _click(application, Point(4, _row_of(frame, 0)))

    assert library._selected == 5
    assert library._retry is not None


def test_anime_list_click_after_scrolling_lands_on_the_painted_row() -> None:
    items: tuple[AnimeRow, ...] = tuple(AnimeRow(f"key-{index}", f"Pozycja {index}") for index in range(60))
    panel: AnimePanel = AnimePanel(
        AnimeViewState(screen=AnimeScreen.DRAFT, title="Subskrypcja", items=items),
        lambda _action, _keys: None,
        lambda: 0.0,
    )
    panel.frame(80, 24)
    for _notch in range(10):
        panel.scroll(1)
    point: Point = _point(panel.frame(80, 24), "Pozycja 15")

    for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
        panel.mouse(_event(kind, point))

    assert panel.state.offset == 10
    assert panel.state.cursor == 15


def test_manual_selection_disappears_when_the_screen_changes_without_a_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    application, controller = _audiobook(monkeypatch, tmp_path, ("space", "end"))
    application._render_frame(100, 40)
    _drag(application, Point(0, 0), Point(99, 38))
    painted: Text = application._render_frame(100, 40)

    controller._open(_ManualScreen.PREVIEW, clear_feedback=False)
    changed: Text = application._render_frame(100, 40)

    assert _reversed(painted)
    assert _reversed(changed) == ""


def test_state_selection_disappears_when_the_tab_changes_without_a_key(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    application._render_frame(80, 24)
    _drag(application, Point(0, 0), Point(79, 22))
    painted: Text = application._render_frame(80, 24)

    library._switch_tab(state_module._Tab.PROGRESS)
    changed: Text = application._render_frame(80, 24)
    application._handle_key("copy")

    assert "Episode 3" in _reversed(painted)
    assert _reversed(changed) == ""
    assert copied == []


def test_auto_selection_disappears_when_the_queue_follows_other_files(monkeypatch: pytest.MonkeyPatch) -> None:
    application, copied = _application(monkeypatch, _Mode.AUTO)
    queue: _Queue = _Queue()
    queue.row_count = 60
    application._progress = cast("RichRunProgress", queue)
    start: Point = _point(application._render_frame(80, 30), "plik-03")
    _drag(application, start, Point(start.x + len("plik-03") - 1, start.y))
    painted: Text = application._render_frame(80, 30)

    queue.active_row = 50
    moved: Text = application._render_frame(80, 30)
    application._handle_key("copy")

    assert _reversed(painted) == "plik-03"
    assert _reversed(moved) == ""
    assert copied == []


def test_copied_text_keeps_soft_hyphens_and_tag_flags_but_drops_private_markers() -> None:
    flag: str = chr(0x1F3F4) + "".join(chr(code) for code in (0xE0067, 0xE0062, 0xE0065, 0xE006E, 0xE0067, 0xE007F))
    frame: Text = Text(f"po{chr(0xAD)}dział {flag} koniec{NATIVE_MASCOT_ANCHOR}")

    copied: str = selected_text(painted_cells(frame), (TextPoint(0, 0), TextPoint(0, frame.cell_len)))

    assert copied == f"po{chr(0xAD)}dział {flag} koniec"


def test_a_name_starting_with_a_choice_mark_is_copied_whole(
    monkeypatch: pytest.MonkeyPatch, library: StateController
) -> None:
    application, copied = _application(monkeypatch, _Mode.STATE)
    application._state = library
    name: str = "● Alfa.mkv"
    library._snapshot = {"library": [{"set_id": "set-0", "name": name}]}
    start: Point = _point(application._render_frame(80, 24), name)

    _drag(application, start, Point(start.x + len(name) - 1, start.y))
    application._render_frame(80, 24)
    application._handle_key("copy")

    assert copied == [name]
