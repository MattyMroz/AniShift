from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from unittest.mock import Mock

import pytest
import test_panel_keys as keys
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.data_structures import Point
from prompt_toolkit.input import DummyInput
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.text import Text
from test_interactive_mouse import _application, _point, _row_of, _state
from test_interactive_settings_autosave import FakeSettingsService

from anishift.application import AppService
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeViewState
from anishift.cli.interactive.menu import append_wrapped_row
from anishift.cli.interactive.palette import BRAND_THEME
from anishift.cli.interactive.pointer import (
    HOVER_STYLE,
    Click,
    ClickKind,
    FrameSelection,
    TextPoint,
    hovered,
    light_targets,
    mark_row,
    mark_target,
)
from anishift.cli.interactive.prompts import TerminalRenderer, _WheelControl
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.state import StateController
from anishift.utils.rich_console.theme import RICH_THEME

pytestmark = pytest.mark.unit

_Mode = interactive_app._ViewMode

_BACKGROUND: str = "48;2;"


def _move(point: Point, button: MouseButton = MouseButton.NONE) -> MouseEvent:
    return MouseEvent(point, MouseEventType.MOUSE_MOVE, button, frozenset())


def _lit(frame: Text) -> list[str]:
    runs: list[list[int]] = []
    for span in sorted((span for span in frame.spans if span.style == HOVER_STYLE), key=lambda span: span.start):
        if runs and span.start <= runs[-1][1]:
            runs[-1][1] = max(runs[-1][1], span.end)
            continue
        runs.append([span.start, span.end])
    return [frame.plain[start:end] for start, end in runs]


def _console() -> Console:
    console: Console = Console(color_system="truecolor", force_terminal=True, width=80, theme=RICH_THEME)
    console.push_theme(BRAND_THEME)
    return console


def _ansi_line(frame: Text, text: str) -> str:
    console: Console = _console()
    with console.capture() as captured:
        console.print(frame, end="")
    return next(line for line in captured.get().split("\n") if text in line)


def _hover(application: interactive_app._InteractiveApplication, point: Point) -> bool:
    return application._handle_hover(_move(point))


@pytest.fixture
def library(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[interactive_app._InteractiveApplication, StateController]]:
    controller: StateController = _state(monkeypatch)
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {"library": [{"set_id": f"set-{index}", "name": f"Episode {index}"} for index in range(5)]}
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = controller
    try:
        yield application, controller
    finally:
        controller.close()
        controller._thread.join(5)


def test_hovered_bands_every_line_of_a_wrapped_row_only_over_the_list() -> None:
    frame: Text = Text("NAGŁÓWEK\n")
    append_wrapped_row(frame, 2, ("pierwsza linia", "  dalszy ciąg"), False, "", index=7)
    append_wrapped_row(frame, 2, ("druga pozycja",), True, "", index=8)

    assert hovered(frame, TextPoint(2, 5)) == ((1, 2, 18), (2, 2, 18))
    assert hovered(frame, TextPoint(2, 40)) == ()
    assert hovered(frame, TextPoint(3, 5)) == ((3, 2, 18),)
    assert hovered(frame, TextPoint(0, 2)) == ()
    assert hovered(frame, TextPoint(9, 0)) == ()
    assert hovered(frame, None) == ()


def test_hovered_bands_only_the_tagged_tab_under_the_mouse() -> None:
    tabs: Text = Text("Anime · Subskrypcje")
    mark_target(tabs, 8, 19, Click(ClickKind.TAB, 1))

    assert hovered(tabs, TextPoint(0, 10)) == ((0, 8, 19),)
    assert hovered(tabs, TextPoint(0, 2)) == ()


def test_home_hover_bands_each_choice_across_the_menu_width_without_moving_the_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    frame: Text = application._render_frame(80, 24)

    changed: bool = _hover(application, _point(frame, "Wyjście"))
    short: list[str] = _lit(application._render_frame(80, 24))
    _hover(application, _point(frame, "Ustawienia"))
    long: list[str] = _lit(application._render_frame(80, 24))

    assert changed is True
    assert len(short) == len(long) == 1
    assert "Wyjście" in short[0]
    assert "Ustawienia" in long[0]
    assert application._selected == 0
    assert application._mode is _Mode.HOME


def test_hover_paints_white_letters_azure_without_a_background_or_underline(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    plain: str = _ansi_line(application._render_frame(80, 24), "Ustawienia")

    _hover(application, _point(application._render_frame(80, 24), "Ustawienia"))
    lit: str = _ansi_line(application._render_frame(80, 24), "Ustawienia")

    assert "1;38;2;226;231;245m  Ustawienia" in plain
    assert "1;38;2;0;98;250m  Ustawienia" in lit
    assert _BACKGROUND not in lit
    assert "[4m" not in lit
    assert ";4m" not in lit


def test_hover_leaves_the_azure_cursor_row_and_the_cursor_as_they_are(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    application._selected = 1
    frame: Text = application._render_frame(80, 24)
    plain: str = _ansi_line(frame, "Ręczny")

    _hover(application, _point(frame, "Ręczny"))
    lit: str = _ansi_line(application._render_frame(80, 24), "Ręczny")

    assert "1;38;2;0;98;250mRęczny" in lit
    assert lit == plain
    assert application._selected == 1


def test_panel_hover_paints_a_gray_tab_azure_without_switching_to_it(
    library: tuple[interactive_app._InteractiveApplication, StateController],
) -> None:
    application, controller = library
    _hover(application, _point(application._render_frame(80, 24), "Subskrypcje"))
    frame: Text = application._render_frame(80, 24)

    assert _lit(frame) == ["Subskrypcje"]
    assert "1;38;2;0;98;250mSubskrypcje" in _ansi_line(frame, "Subskrypcje")
    assert controller._tab == state_module._Tab.FILES


def test_panel_hover_shades_a_whole_table_row_without_selecting_it(
    library: tuple[interactive_app._InteractiveApplication, StateController],
) -> None:
    application, controller = library
    frame: Text = application._render_frame(80, 24)
    _hover(application, _point(frame, "Episode 3"))
    third: list[str] = _lit(application._render_frame(80, 24))
    _hover(application, _point(frame, "Episode 1"))
    first: list[str] = _lit(application._render_frame(80, 24))

    assert len(third) == 1
    assert third[0].strip().startswith("Episode 3")
    assert third[0].rstrip().endswith("—")
    assert first[0].strip().startswith("Episode 1")
    assert controller._selected == 0


def test_a_selection_keeps_its_reverse_under_the_hover(
    library: tuple[interactive_app._InteractiveApplication, StateController],
) -> None:
    application, _controller = library
    frame: Text = application._render_frame(80, 24)
    start: Point = _point(frame, "Episode 3")
    end: Point = Point(start.x + len("Episode 3") - 1, start.y)
    for kind, point in (
        (MouseEventType.MOUSE_DOWN, start),
        (MouseEventType.MOUSE_MOVE, end),
        (MouseEventType.MOUSE_UP, end),
    ):
        application._handle_mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))
    application._render_frame(80, 24)
    _hover(application, end)
    painted: Text = application._render_frame(80, 24)
    offset: int = painted.plain.index("Episode 3")

    assert _lit(painted)
    assert painted.get_style_at_offset(_console(), offset).reverse


def test_home_hover_redraws_only_when_the_target_under_the_mouse_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    frame: Text = application._render_frame(80, 24)
    settings: Point = _point(frame, "Ustawienia")
    exit_row: Point = _point(frame, "Wyjście")

    moves: list[bool] = [
        _hover(application, settings),
        _hover(application, Point(settings.x + 3, settings.y)),
        _hover(application, exit_row),
        _hover(application, Point(0, 0)),
        _hover(application, Point(1, 0)),
    ]

    assert moves == [True, False, True, True, False]
    assert _lit(application._render_frame(80, 24)) == []


def test_a_key_hides_the_hover_until_the_mouse_moves_again(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.HOME)
    point: Point = _point(application._render_frame(80, 24), "Wyjście")
    _hover(application, point)
    application._render_frame(80, 24)

    application._handle_key("text:q")
    hidden: list[str] = _lit(application._render_frame(80, 24))
    _hover(application, point)

    assert hidden == []
    assert "Wyjście" in "".join(_lit(application._render_frame(80, 24)))


def test_a_click_keeps_the_hover_and_a_drag_hides_it() -> None:
    frame: Text = Text("  Odcinek 1")
    mark_row(frame, 0)
    selection: FrameSelection = FrameSelection()
    selection.paint(frame.copy(), ())
    selection.hover(TextPoint(0, 4))

    for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
        selection.mouse(MouseEvent(Point(4, 0), kind, MouseButton.LEFT, frozenset()))
    clicked: list[str] = _lit(selection.paint(frame.copy(), ()))
    for kind, x in ((MouseEventType.MOUSE_DOWN, 4), (MouseEventType.MOUSE_MOVE, 6)):
        selection.mouse(MouseEvent(Point(x, 0), kind, MouseButton.LEFT, frozenset()))

    assert clicked == ["Odcinek 1"]
    assert _lit(selection.paint(frame.copy(), ())) == []


def test_settings_hover_shades_a_row_without_selecting_it(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _copied = _application(monkeypatch, _Mode.SETTINGS)
    controller: SettingsController = SettingsController(cast("AppService", FakeSettingsService()), lambda: None)
    application._settings = controller
    frame: Text = application._render_frame(100, 30)
    row: int = _row_of(frame, 2)

    line: str = frame.plain.splitlines()[row]
    _hover(application, Point(len(line) - len(line.lstrip()), row))
    lit: list[str] = _lit(application._render_frame(100, 30))

    assert len(lit) == 1
    assert lit[0].strip() == frame.plain.split("\n")[row].strip()
    assert controller._selected == 0


def test_anime_rows_shade_across_the_table_but_rows_without_a_cursor_stop_stay_unlit() -> None:
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

    def band(label: str) -> tuple[tuple[int, int, int], ...]:
        point: Point = _point(frame, label)
        return hovered(frame, TextPoint(point.y, point.x))

    cursor: tuple[tuple[int, int, int], ...] = band("Odcinek pierwszy")
    other: tuple[tuple[int, int, int], ...] = band("Odcinek drugi")

    assert band("Wyemitowane") == ()
    assert len(cursor) == len(other) == 1
    assert cursor[0][1:] == other[0][1:]
    assert panel.state.cursor == 1


def test_the_control_redraws_a_hover_move_only_when_the_handler_reports_a_change() -> None:
    hover: Mock = Mock(side_effect=[True, False])
    pointer: Mock = Mock()
    control: _WheelControl = _WheelControl(None, pointer, hover, text="日a日b")

    first: object = control.mouse_handler(_move(Point(3, 0)))
    second: object = control.mouse_handler(_move(Point(4, 0)))
    control.mouse_handler(_move(Point(1, 0), MouseButton.LEFT))

    assert first is None
    assert second is NotImplemented
    assert hover.call_args_list[0].args[0].position == Point(5, 0)
    assert hover.call_count == 2
    assert pointer.call_count == 1


def test_the_session_wires_hover_moves_into_its_only_control() -> None:
    seen: list[MouseEvent] = []

    def handler(event: MouseEvent) -> bool:
        seen.append(event)
        return True

    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None, hover_handler=handler)
    control = renderer._application.layout.container.content  # type: ignore[attr-defined]

    assert control.mouse_handler(_move(Point(0, 0))) is None
    assert len(seen) == 1


def test_frame_selection_without_a_painted_frame_reports_no_change() -> None:
    assert FrameSelection().hover(TextPoint(0, 0)) is False


def test_hover_repaints_white_and_gray_letters_and_keeps_a_status_color() -> None:
    frame: Text = Text("  [ ] Odcinek 1   Gotowe")
    frame.stylize("gray", 2, 5)
    frame.stylize("white_bold", 6, 15)
    frame.stylize("success", 18, 24)
    mark_row(frame, 0)

    lit: Text = light_targets(frame.copy(), hovered(frame, TextPoint(0, 8)))

    assert _lit(lit) == ["[ ] Odcinek 1   "]


@pytest.fixture
def episodes_app(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[interactive_app._InteractiveApplication, keys._Probe]]:
    monkeypatch.setattr(StateController, "_watch", lambda _self: None)
    probe: keys._Probe = keys._episodes(monkeypatch)
    application, _copied = _application(monkeypatch, _Mode.STATE)
    application._state = probe.panel
    try:
        yield application, probe
    finally:
        probe.panel.close()
        probe.panel._thread.join(5)


def _box(frame: Text, nth: int) -> Point:
    lines: list[str] = frame.plain.split("\n")
    row: int = [index for index, line in enumerate(lines) if "[ ]" in line][nth]
    return Point(Text(lines[row][: lines[row].index("[ ]")]).cell_len + 1, row)


def _press(application: interactive_app._InteractiveApplication, point: Point) -> None:
    for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
        application._handle_mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))


def test_a_box_click_marks_the_episode_and_keeps_the_hover(
    episodes_app: tuple[interactive_app._InteractiveApplication, keys._Probe],
) -> None:
    application, _probe = episodes_app
    point: Point = _box(application._render_frame(80, 24), 3)
    _hover(application, point)

    _press(application, point)
    lines: list[str] = application._render_frame(80, 24).plain.splitlines()
    line: str = next(line for line in lines if "Episode 4 " in line)

    assert "[x]" in line
    assert chr(0x276F) in line
    assert application._frame_selection._hover == TextPoint(point.y, point.x)


def test_a_box_click_with_the_range_field_open_never_types_into_it(
    episodes_app: tuple[interactive_app._InteractiveApplication, keys._Probe],
) -> None:
    application, probe = episodes_app
    for key in ("text:z", "text:1"):
        application._handle_key(key)
    point: Point = _box(application._render_frame(80, 24), 2)

    _press(application, point)

    assert probe.anime._range_input is not None
    assert probe.anime._range_input.text == "1"


def test_a_drag_on_the_anime_tab_hides_the_hover(
    episodes_app: tuple[interactive_app._InteractiveApplication, keys._Probe],
) -> None:
    application, _probe = episodes_app
    box: Point = _box(application._render_frame(80, 24), 1)
    start: Point = Point(box.x + 4, box.y)
    _hover(application, start)

    application._handle_mouse(MouseEvent(start, MouseEventType.MOUSE_DOWN, MouseButton.LEFT, frozenset()))
    application._handle_mouse(
        MouseEvent(Point(start.x + 5, start.y), MouseEventType.MOUSE_MOVE, MouseButton.LEFT, frozenset())
    )

    assert _lit(application._render_frame(80, 24)) == []


def test_hover_leaves_the_episode_cursor_row_with_its_gray_box_as_it_is(
    episodes_app: tuple[interactive_app._InteractiveApplication, keys._Probe],
) -> None:
    application, _probe = episodes_app
    frame: Text = application._render_frame(80, 24)
    row: int = next(index for index, line in enumerate(frame.plain.split("\n")) if "\u276f" in line)
    line: str = frame.plain.split("\n")[row]

    _hover(application, Point(line.index("\u276f") + 2, row))

    assert _lit(application._render_frame(80, 24)) == []


def test_hover_keeps_the_field_caret_in_its_own_color() -> None:
    frame: Text = Text("  > slime")
    mark_target(frame, 4, 9, Click(ClickKind.FIELD, 0))
    frame.stylize("white_bold", 4, 9)
    frame.stylize("reverse", 6, 7)

    lit: Text = light_targets(frame.copy(), hovered(frame, TextPoint(0, 5)))

    assert _lit(lit) == ["> sl", "me"]
