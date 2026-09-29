from __future__ import annotations

import codecs
import shutil
import subprocess
from dataclasses import replace
from unittest.mock import Mock

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.text import Text

from anishift.cli.interactive import anime_clipboard
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_state import (
    AnimeRow,
    AnimeScreen,
    AnimeSnapshot,
    AnimeViewState,
    NoticeKind,
    TextPoint,
)
from anishift.cli.interactive.anime_view import AnimeFrame, TextCell, render_anime
from anishift.cli.interactive.prompts import _WheelControl
from anishift.cli.interactive.text_input import TextInput

pytestmark = pytest.mark.unit


def rows() -> tuple[AnimeRow, ...]:
    return (
        AnimeRow("one", "Zażółć 日本語", number="1", date="01.09.2026"),
        AnimeRow("three", "A Promise", number="3", date="15.09.2026"),
        AnimeRow("special", "Special", number="7.5", date="16.09.2026"),
        AnimeRow("future", "Next", number="8", eligible=False, status="Nie wyemitowano"),
    )


def panel() -> tuple[AnimePanel, Mock, Mock]:
    action: Mock = Mock()
    clipboard: Mock = Mock(return_value=True)
    state: AnimeViewState = AnimeViewState(screen=AnimeScreen.EPISODES, title="Slime", items=rows())
    return AnimePanel(state, action, lambda: 10.0, clipboard), action, clipboard


@pytest.mark.parametrize("width", [50, 80, 120])
def test_selection_and_results_preserve_row_positions_and_footer(width: int) -> None:
    view: AnimePanel
    view, _, _ = panel()
    before: list[str] = view.frame(width, 24).plain.splitlines()
    view.handle("space")
    view.handle("down")
    view.handle("space")
    selected: list[str] = view.frame(width, 24).plain.splitlines()
    assert "Zaznaczone: 2 (1, 3)" in selected[-3 if width >= 80 else -4]
    assert all("Zaznaczone" not in line for line in selected[:5])
    assert "Zaż" in before[5]
    assert "Zaż" in selected[5]
    view.searching(("one", "three"))
    busy: str = view.frame(width, 24).plain
    assert "⠋ szukam" in busy
    assert "Zlecam" not in busy
    view.result("one", admitted=True)
    assert view.state.selected == {"three"}
    assert view.state.searching == {"three"}
    assert "Zlecono" in view.frame(width, 24).plain.splitlines()[5]
    assert before[-1] == selected[-1]
    assert all(Text(line).cell_len == width for line in selected)
    assert len(selected) == 24


def test_space_all_range_and_batch_download_use_exact_keys() -> None:
    view: AnimePanel
    action: Mock
    view, action, _ = panel()
    view.handle("text:a")
    assert view.state.selected == {"one", "three", "special"}
    view.handle("text:a")
    assert not view.state.selected
    view.handle("text:z")
    view.handle("paste:1,7.5")
    view.handle("enter")
    assert view.state.selected == {"one", "special"}
    view.handle("text:d")
    action.assert_called_once_with("download", ("one", "special"))
    view.handle("text:z")
    view.handle("paste:99")
    view.handle("enter")
    assert view.state.selected == {"one", "special"}
    assert view.state.range_input is not None


def mouse(view: AnimePanel, kind: MouseEventType, x: int, y: int) -> None:
    view.mouse(MouseEvent(Point(x, y), kind, MouseButton.LEFT, frozenset()))


@pytest.mark.parametrize("key", ["interrupt", "text:c", "text:C"])
def test_multiline_mouse_copy_excludes_chrome_and_retains_unicode(key: str) -> None:
    view: AnimePanel
    action: Mock
    clipboard: Mock
    view, action, clipboard = panel()
    view.frame(80, 24)
    mouse(view, MouseEventType.MOUSE_DOWN, 0, 0)
    mouse(view, MouseEventType.MOUSE_MOVE, 79, 7)
    mouse(view, MouseEventType.MOUSE_UP, 79, 7)
    highlighted: Text = view.frame(80, 24)
    assert any(span.style == "anime_selection" for span in highlighted.spans)
    view.handle(key)
    value: str = clipboard.call_args.args[0]
    assert "Zażółć 日本語" in value
    assert "A Promise" in value
    assert "\n" in value
    assert view.state.notice == "Skopiowano zaznaczenie"
    assert not any(token in value for token in ("[Anime]", "[ ]", "[x]", ">", "+---", "Subskrypcje"))
    action.assert_not_called()


def test_click_clears_mouse_selection_and_unselected_interrupt_returns() -> None:
    view: AnimePanel
    action: Mock
    clipboard: Mock
    view, action, clipboard = panel()
    view.frame(80, 24)
    mouse(view, MouseEventType.MOUSE_DOWN, 11, 5)
    mouse(view, MouseEventType.MOUSE_UP, 20, 6)
    mouse(view, MouseEventType.MOUSE_DOWN, 11, 6)
    mouse(view, MouseEventType.MOUSE_UP, 11, 6)
    assert view.state.selection is None
    view.handle("text:c")
    assert view.state.cursor == 1
    assert not view.state.selected
    clipboard.assert_called_once_with(rows()[1].copy_text)
    assert view.state.notice == "Skopiowano wiersz"
    view.handle("interrupt")
    action.assert_called_once_with("back", ())


def test_cjk_hit_testing_preserves_whole_graphemes_and_columns() -> None:
    snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.EPISODES, "Slime", rows())
    frame: AnimeFrame = render_anime(snapshot, 80, 24, 0)
    japanese: TextCell = next(cell for cell in frame.cells if cell.text == "日")
    selection: tuple[TextPoint, TextPoint] = (japanese.point, TextPoint(japanese.point.row, japanese.point.column + 1))
    assert frame.selected_text(selection) == "日"
    assert frame.text.plain.splitlines()[5].index("01.09.2026") < 52
    assert Text(frame.text.plain.splitlines()[5]).cell_len == 80


def test_flash_expires_without_erasing_confirmed_status() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.result("one", admitted=True)
    snapshot: AnimeSnapshot = view.state.snapshot()
    first: AnimeFrame = render_anime(snapshot, 80, 24, 10.0)
    expired: AnimeFrame = render_anime(snapshot, 80, 24, 10.41)
    assert any(span.style == "anime_flash" for span in first.text.spans)
    assert not any(span.style == "anime_flash" for span in expired.text.spans)
    assert first.text.plain == expired.text.plain
    assert "Zlecono" in expired.text.plain


@pytest.mark.parametrize("width", [50, 80])
def test_release_columns_keep_seeds_and_no_repeat_shortcut(width: int) -> None:
    items: tuple[AnimeRow, ...] = tuple(
        replace(item, image="1080p", language="MultiSub", seeds="312") for item in rows()
    )
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", items), width, 24, 0)
    assert "1080p  MultiSub    312" in frame.text.plain.splitlines()[5]
    assert "P ponownie" not in frame.text.plain
    assert all(Text(line).cell_len == width for line in frame.text.plain.splitlines())


def test_mouse_callback_is_forwarded_by_shared_terminal_control() -> None:
    callback: Mock = Mock()
    wheel: Mock = Mock()
    control_view: _WheelControl = _WheelControl(wheel, callback, text="test")
    event: MouseEvent = MouseEvent(Point(1, 2), MouseEventType.MOUSE_MOVE, MouseButton.LEFT, frozenset())
    control_view.mouse_handler(event)
    assert callback.call_count == 1
    assert callback.call_args.args[0].position == event.position
    assert callback.call_args.args[0].event_type == event.event_type
    control_view.mouse_handler(MouseEvent(Point(1, 2), MouseEventType.SCROLL_DOWN, MouseButton.NONE, frozenset()))
    wheel.assert_called_once_with(1)


def test_shared_mouse_control_converts_unicode_character_offsets_to_cells() -> None:
    callback: Mock = Mock()
    control_view: _WheelControl = _WheelControl(None, callback, text="日a日b")
    control_view.mouse_handler(MouseEvent(Point(3, 0), MouseEventType.MOUSE_DOWN, MouseButton.LEFT, frozenset()))
    assert callback.call_args.args[0].position == Point(5, 0)


def test_query_selected_ctrl_c_copies_to_windows_before_blur() -> None:
    view: AnimePanel
    action: Mock
    clipboard: Mock
    view, action, clipboard = panel()
    view.show(AnimeScreen.QUERY, "Anime", ())
    view.state.query.reset("Zażółć 日本語")
    view.handle("select-all")
    view.handle("interrupt")
    clipboard.assert_called_once_with("Zażółć 日本語")
    assert view.state.query_focused
    view.handle("right")
    view.handle("interrupt")
    assert not view.state.query_focused
    action.assert_not_called()
    view.handle("interrupt")
    action.assert_called_once_with("back", ())


def test_query_letters_never_invoke_download_or_select_all() -> None:
    view: AnimePanel
    action: Mock
    view, action, _ = panel()
    view.show(AnimeScreen.QUERY, "Anime", ())
    for key in ("text:d", "text:a", "text:z", "text:c"):
        view.handle(key)
    assert view.state.query.text == "dazc"
    action.assert_not_called()


@pytest.mark.parametrize(
    "selection",
    [
        (TextPoint(5, 11), TextPoint(6, 19)),
        (TextPoint(6, 19), TextPoint(5, 11)),
    ],
)
def test_selection_direction_does_not_change_copied_text(selection: tuple[TextPoint, TextPoint]) -> None:
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", rows()), 80, 24, 0)
    assert frame.selected_text(selection).startswith("Zażółć 日本語")
    assert frame.selected_text(selection).endswith("A Promise")


def test_failed_result_keeps_selection_and_has_no_success_flash() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.state.selected.add("three")
    view.searching(("three",))
    view.result("three", admitted=False)
    assert view.state.selected == {"three"}
    assert not view.state.flashes
    assert not view.state.searching
    assert view.state.items[1].status == "Brak wydania"


def test_pending_download_blocks_repeated_download_and_selection_mutations() -> None:
    view: AnimePanel
    action: Mock
    view, action, _ = panel()
    view.state.selected.add("one")
    view.searching(("one",))
    for key in ("text:d", "space", "text:a", "text:z", "text:p"):
        view.handle(key)
    assert view.state.selected == {"one"}
    assert view.state.range_input is None
    action.assert_not_called()


def test_mouse_selection_is_cleared_after_resize_and_scroll() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.frame(80, 24)
    view.state.selection = (TextPoint(6, 11), TextPoint(7, 20))
    view.frame(50, 24)
    assert view.state.selection is None
    view.state.selection = (TextPoint(6, 11), TextPoint(7, 20))
    view.scroll(1)
    assert view.state.selection is None


def test_clipboard_receives_bom_and_utf16_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    run: Mock = Mock()
    monkeypatch.setattr(shutil, "which", lambda _: "C:/Windows/System32/clip.exe")
    monkeypatch.setattr(subprocess, "run", run)
    value: str = "Zażółć 日本語 😀\nDrugi wiersz"
    assert anime_clipboard.copy_text(value)
    assert run.call_args.kwargs["input"] == codecs.BOM_UTF16_LE + value.encode("utf-16-le")
    assert value not in run.call_args.args[0]
    assert run.call_args.kwargs["timeout"] == 2


def test_clipboard_failure_is_not_reported_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "clip.exe")
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("clip", 2)))
    assert not anime_clipboard.copy_text("text")


def test_open_range_skips_ineligible_rows_and_keeps_fractional_specials() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.state.items = (*rows(), AnimeRow("five", "Fifth", number="5"))
    view.handle("text:z")
    view.handle("paste:5-")
    view.handle("enter")
    assert view.state.selected == {"five", "special"}


@pytest.mark.parametrize("key", ["down", "space", "text:z", "enter"])
def test_next_navigation_or_action_clears_one_shot_notice(key: str) -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.handle("text:c")
    view.handle(key)
    assert view.state.notice == ""
    assert view.state.notice_kind is NoticeKind.INFO


@pytest.mark.parametrize("query", [False, True])
def test_c_is_inserted_in_editor_even_with_mouse_selection(*, query: bool) -> None:
    view: AnimePanel
    clipboard: Mock
    view, _, clipboard = panel()
    if query:
        view.show(AnimeScreen.QUERY, "Anime", ())
        view.state.query.reset("ab")
    else:
        view.handle("text:z")
        view.handle("paste:1")
    view.frame(80, 24)
    view.state.selection = (TextPoint(0, 0), TextPoint(23, 79))
    view.handle("text:c")
    editor: TextInput | None = view.state.query if query else view.state.range_input
    assert editor is not None
    assert editor.text.endswith("c")
    clipboard.assert_not_called()


def test_batch_results_are_aggregated_once_and_reset_for_next_batch() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.searching(("one", "three"))
    view.result("one", admitted=True)
    assert view.state.notice == "Zlecono 1"
    assert view.state.snapshot().notice_kind is NoticeKind.SUCCESS
    view.result("three", admitted=False)
    view.result("one", admitted=True)
    assert view.state.notice == "Zlecono 1 · nie zlecono 3 · I wydania"
    assert view.state.snapshot().notice_kind is NoticeKind.WARNING
    view.searching(("special",))
    view.result("special", admitted=True)
    assert view.state.notice == "Zlecono 7.5"


def test_frame_removes_expired_flash_deadlines() -> None:
    clock: Mock = Mock(return_value=10.0)
    view: AnimePanel = AnimePanel(AnimeViewState(items=rows()), Mock(), clock)
    view.result("one", admitted=True)
    clock.return_value = 10.41
    view.frame(80, 24)
    assert not view.state.flashes
    assert view.state.items[0].status == "Zlecono"


def test_switch_state_discards_old_mouse_map_and_selection() -> None:
    view: AnimePanel
    clipboard: Mock
    view, _, clipboard = panel()
    old: AnimeViewState = view.state
    view.frame(80, 24)
    mouse(view, MouseEventType.MOUSE_DOWN, 11, 5)
    mouse(view, MouseEventType.MOUSE_MOVE, 19, 6)
    new: AnimeViewState = AnimeViewState(screen=AnimeScreen.EPISODES, items=(AnimeRow("new", "New"),))
    view.switch_state(new)
    mouse(view, MouseEventType.MOUSE_UP, 19, 6)
    view.handle("text:c")
    assert old.selection is None
    assert new.selection is None
    clipboard.assert_called_once_with("New")


@pytest.mark.parametrize("button", [MouseButton.NONE, MouseButton.RIGHT, MouseButton.MIDDLE])
def test_unhandled_mouse_events_do_not_read_frame_or_request_redraw(button: MouseButton) -> None:
    callback: Mock = Mock()
    text: Mock = Mock(return_value="text")
    control_view: _WheelControl = _WheelControl(None, callback, text=text)
    event: MouseEvent = MouseEvent(Point(1, 0), MouseEventType.MOUSE_MOVE, button, frozenset())
    assert control_view.mouse_handler(event) is NotImplemented
    callback.assert_not_called()
    text.assert_not_called()


def test_footer_is_empty_until_content_needs_explanation() -> None:
    snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.EPISODES, "Slime", rows())
    assert not render_anime(snapshot, 80, 24, 0).text.plain.splitlines()[-2].strip()
    assert "Zażółć 日本語" in render_anime(snapshot, 50, 24, 0).text.plain.splitlines()[-3]
