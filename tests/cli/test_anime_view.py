from __future__ import annotations

import codecs
import shutil
import subprocess
from dataclasses import replace
from unittest.mock import Mock

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.console import Console
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
from anishift.cli.interactive.anime_view import AnimeFrame, _notice_lines, render_anime
from anishift.cli.interactive.palette import BRAND_THEME
from anishift.cli.interactive.pointer import TextCell
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


def first_row(view: AnimePanel, width: int = 80) -> int:
    return render_anime(view.state.snapshot(), width, 24, 0).first_row


@pytest.mark.parametrize("width", [50, 80, 120])
def test_selection_and_results_preserve_row_positions_and_footer(width: int) -> None:
    view: AnimePanel
    view, _, _ = panel()
    before: list[str] = view.frame(width, 24).plain.splitlines()
    top: int = first_row(view, width)
    view.handle("space")
    view.handle("down")
    view.handle("space")
    selected: list[str] = view.frame(width, 24).plain.splitlines()
    summary: int = next(index for index, line in enumerate(selected) if "Zaznaczone: 2 (1, 3)" in line)
    assert summary >= top + len(rows())
    assert first_row(view, width) == top
    assert "Zaż" in before[top]
    assert "Zaż" in selected[top]
    view.searching(("one", "three"))
    busy: str = view.frame(width, 24).plain
    assert "⠋ szukam" in busy
    assert "Zlecam" not in busy
    view.result("one", admitted=True)
    assert view.state.selected == {"three"}
    assert view.state.searching == {"three"}
    assert "Zlecono" in view.frame(width, 24).plain.splitlines()[top]
    assert before[-1] == selected[-1]
    assert all(Text(line).cell_len == width for line in selected)
    assert len(selected) == len(before) == 24


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


@pytest.mark.parametrize("width", [50, 80, 120])
@pytest.mark.parametrize("query", ["", "slime", "日本e\u0301"])
def test_query_keeps_the_classic_heading_and_prompt_box_without_a_context_line(width: int, query: str) -> None:
    state: AnimeViewState = AnimeViewState(query=TextInput(query), query_focused=True)
    frame: AnimeFrame = render_anime(state.snapshot(width), width, 24, 0)
    lines: list[str] = frame.text.plain.splitlines()
    row: int = frame.first_row
    assert lines[row - 2].index("ANIME") == (width - len("ANIME")) // 2
    assert not "".join(lines[: row - 2]).strip()
    assert not lines[row - 1].strip()
    left: int = max((width - min(max(len(query) + 3, 32), width)) // 2, 0)
    assert lines[row][left : left + 2] == "> "
    assert not lines[row][:left].strip()
    field: Text = state.query.render(width - left - 3, focused=True)
    cells: tuple[TextCell, ...] = tuple(cell for cell in frame.cells if cell.point.row == row)
    assert cells[0].point.column == left + 2
    assert "".join(cell.text for cell in cells) == field.plain
    assert frame.selected_text((TextPoint(row, left), TextPoint(row, width - 1))) == query
    assert any(span.style == "reverse" for span in frame.text.spans)


@pytest.mark.parametrize("key", ["interrupt", "text:c", "text:C"])
def test_multiline_mouse_copy_excludes_chrome_and_retains_unicode(key: str) -> None:
    view: AnimePanel
    action: Mock
    clipboard: Mock
    view, action, clipboard = panel()
    view.frame(80, 24)
    top: int = first_row(view)
    mouse(view, MouseEventType.MOUSE_DOWN, 0, 0)
    mouse(view, MouseEventType.MOUSE_MOVE, 79, top + 4)
    mouse(view, MouseEventType.MOUSE_UP, 79, top + 4)
    highlighted: Text = view.frame(80, 24)
    assert any(span.style == "reverse" for span in highlighted.spans)
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
    top: int = first_row(view)
    mouse(view, MouseEventType.MOUSE_DOWN, 13, top)
    mouse(view, MouseEventType.MOUSE_UP, 22, top + 1)
    mouse(view, MouseEventType.MOUSE_DOWN, 13, top + 1)
    mouse(view, MouseEventType.MOUSE_UP, 13, top + 1)
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
    assert frame.text.plain.splitlines()[frame.first_row].index("01.09.2026") < 52
    assert Text(frame.text.plain.splitlines()[frame.first_row]).cell_len == 80


def test_confirmed_status_has_no_temporary_background_style() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.result("one", admitted=True)
    snapshot: AnimeSnapshot = view.state.snapshot()
    first: AnimeFrame = render_anime(snapshot, 80, 24, 10.0)
    expired: AnimeFrame = render_anime(snapshot, 80, 24, 10.41)
    assert first.text.spans == expired.text.spans
    console: Console = Console(theme=BRAND_THEME)
    assert all(first.text.get_style_at_offset(console, index).bgcolor is None for index in range(len(first.text)))
    assert first.text.plain == expired.text.plain
    assert "Zlecono" in expired.text.plain


@pytest.mark.parametrize("width", [50, 80])
def test_release_columns_keep_seeds_and_no_repeat_shortcut(width: int) -> None:
    items: tuple[AnimeRow, ...] = tuple(
        replace(item, image="1080p", language="MultiSub", seeds="312") for item in rows()
    )
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", items), width, 24, 0)
    header: str = frame.text.plain.splitlines()[frame.first_row - 1]
    assert "Seedy" in header
    assert "312" in frame.text.plain.splitlines()[frame.first_row + 2]
    assert "Jakość" in header
    assert "Pewność" in header
    assert "P ponownie" not in frame.text.plain
    assert all(Text(line).cell_len == width for line in frame.text.plain.splitlines())


@pytest.mark.parametrize("width", [50, 80, 120])
@pytest.mark.parametrize(
    "confidence", ["97%", "68% · niepewne", "inny sezon", "inny wariant montażu", "inny rodzaj materiału"]
)
def test_offer_columns_quality_confidence_last(width: int, confidence: str) -> None:
    item: AnimeRow = AnimeRow(
        "one",
        "[Group] 日本e\u0301 - 04",
        image="1080p",
        language="PL · EN",
        seeds="312",
        quality="69",
        confidence=confidence,
        suggested=True,
        uncertain=confidence == "68% · niepewne",
    )
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", (item,)), width, 24, 0)
    lines: list[str] = frame.text.plain.splitlines()
    header: str = lines[frame.first_row - 1]
    row: str = lines[frame.first_row]
    assert header.rstrip().endswith("Jakość  Pewność")
    assert "69" in row
    assert confidence in row or (width == 50 and row.rstrip().endswith("…"))
    assert "*" in row
    assert ("!" in row) is item.uncertain
    assert all(Text(line).cell_len == width for line in lines)
    copied: str = frame.selected_text((TextPoint(frame.first_row, 0), TextPoint(frame.first_row, width - 1)))
    assert "69" in copied
    assert "*" not in copied
    assert "!" not in copied
    assert item.copy_text.endswith(f"Jakość: 69 · Pewność: {confidence}")
    displayed: str = " ".join(frame.text.plain.split())
    assert "1080p" in displayed
    assert "PL · EN" in displayed
    assert "312" in displayed
    assert confidence in displayed
    if width == 120:
        assert item.title in row


@pytest.mark.parametrize("rows_count", [12, 24])
def test_narrow_episode_table_keeps_the_full_state_label(rows_count: int) -> None:
    items: tuple[AnimeRow, ...] = tuple(replace(item, title=item.title * 4) for item in rows())
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items, cursor=3), 50, rows_count, 0)
    lines: list[str] = frame.text.plain.splitlines()
    header: str = lines[frame.first_row - 1]
    assert "Tytuł" in header
    assert "Stan" in header
    assert any("Nie wyemitowano" in line for line in lines[frame.first_row :])
    assert all(Text(line).cell_len == 50 for line in lines)


@pytest.mark.parametrize("height", [12, 24])
def test_hidden_release_columns_follow_cursor_and_remain_copyable_at_fifty_columns(height: int) -> None:
    first: AnimeRow = AnimeRow(
        "one",
        "[Group] Slime - 04 [1080p]",
        image="1080p",
        language="PL · EN",
        seeds="321",
        quality="69",
        confidence="95% · niepewne",
        detail="Details " * 40,
    )
    second: AnimeRow = replace(first, key="two", image="2160p", language="EN", seeds="?")
    snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", (first, second))
    frame: AnimeFrame = render_anime(snapshot, 50, height, 0)
    next_frame: AnimeFrame = render_anime(replace(snapshot, cursor=1), 50, height, 0)
    lines: list[str] = frame.text.plain.splitlines()
    next_lines: list[str] = next_frame.text.plain.splitlines()
    footer: str = " ".join(" ".join(lines[-5:]).split())
    next_footer: str = " ".join(" ".join(next_lines[-5:]).split())
    assert "obraz 1080p · język PL · EN · seedy 321" in footer
    assert "obraz 2160p · język EN · seedy ?" in next_footer
    assert "Details" not in footer
    assert frame.first_row == next_frame.first_row
    assert lines[frame.first_row - 1] == next_lines[next_frame.first_row - 1]
    assert frame.selected_text((TextPoint(height - 5, 0), TextPoint(height - 3, 49))).startswith("obraz 1080p")
    assert all(Text(line).cell_len == 50 for line in lines)


@pytest.mark.parametrize("width", [50, 80])
def test_truncated_release_name_is_shown_in_full_without_moving_the_table(width: int) -> None:
    name: str = "[SubsPlease] Tensei shitara Slime Datta Ken - 01 (1080p) [ABCDEF12].mkv"
    short: AnimeRow = AnimeRow("one", "Short", image="1080p", language="PL", seeds="312", detail="Rozmiar: 1 GB")
    long: AnimeRow = replace(short, title=name)
    plain: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", (short,)), width, 24, 0)
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.RELEASES, "Wydania", (long,)), width, 24, 0)
    lines: list[str] = frame.text.plain.splitlines()
    assert name not in lines[frame.first_row]
    assert name in " ".join(" ".join(lines[frame.first_row + 1 :]).split())
    assert "Rozmiar: 1 GB" not in frame.text.plain
    assert "Rozmiar: 1 GB" in plain.text.plain or "język PL" in plain.text.plain
    assert frame.first_row == plain.first_row
    assert all(Text(line).cell_len == width for line in lines)


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


@pytest.mark.parametrize("reverse", [False, True])
def test_selection_direction_does_not_change_copied_text(*, reverse: bool) -> None:
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", rows()), 80, 24, 0)
    lines: list[str] = frame.text.plain.splitlines()
    row: int = frame.first_row
    start: TextPoint = TextPoint(row, lines[row].index("Zaż"))
    end: TextPoint = TextPoint(row + 1, lines[row + 1].index("A Promise") + len("A Promise") - 1)
    adjusted: tuple[TextPoint, TextPoint] = (end, start) if reverse else (start, end)
    assert frame.selected_text(adjusted).startswith("Zażółć 日本語")
    assert frame.selected_text(adjusted).endswith("A Promise")


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


@pytest.mark.parametrize("status", ["", "w emisji", "Zlecono", "Nie wyemitowano"])
def test_footer_is_empty_until_content_needs_explanation(status: str) -> None:
    snapshot: AnimeSnapshot = AnimeSnapshot(
        AnimeScreen.EPISODES, "Slime", (replace(rows()[0], status=status), *rows()[1:])
    )
    assert not render_anime(snapshot, 80, 24, 0).text.plain.splitlines()[-2].strip()
    assert "Zażółć 日本語" in render_anime(snapshot, 50, 24, 0).text.plain.splitlines()[-2]


def test_announcement_uses_existing_gray_for_every_visible_character() -> None:
    snapshot: AnimeSnapshot = AnimeSnapshot(
        AnimeScreen.ENTRIES,
        "Slime",
        (
            AnimeRow("future", "Season 5", date="2027", kind="TV", status="zapowiedź", navigable=False),
            AnimeRow("current", "Season 4", date="2026", kind="TV", status="w emisji"),
        ),
        cursor=1,
    )
    console: Console = Console(theme=BRAND_THEME)
    frame: AnimeFrame = render_anime(snapshot, 80, 24, 0)
    lines: list[Text] = list(frame.text.split("\n"))
    row: int = frame.first_row
    assert all(
        lines[row].get_style_at_offset(console, index).color == BRAND_THEME.styles["gray"].color
        for index, character in enumerate(lines[row].plain)
        if not character.isspace()
    )
    assert "\u276f" not in lines[row].plain
    assert lines[row + 1].plain.lstrip().startswith("\u276f")


def _blank_margins(lines: list[str], columns: int) -> tuple[int, int, int, int]:
    occupied: list[int] = [index for index, line in enumerate(lines) if line.strip()]
    keys: int = len(lines)
    while keys - 1 in occupied:
        keys -= 1
    content: list[int] = [index for index in occupied if index < keys]
    left: int = min(len(lines[index]) - len(lines[index].lstrip()) for index in content)
    right: int = columns - max(Text(lines[index].rstrip()).cell_len for index in content)
    return content[0], keys - content[-1] - 1, left, right


@pytest.mark.parametrize(("columns", "height"), [(80, 20), (120, 26)])
@pytest.mark.parametrize("screen", [AnimeScreen.QUERY, AnimeScreen.ENTRIES, AnimeScreen.EPISODES])
def test_content_is_centered_between_top_and_bottom_pinned_keys(screen: AnimeScreen, columns: int, height: int) -> None:
    state: AnimeViewState = AnimeViewState(
        screen=screen,
        title="Slime",
        items=()
        if screen is AnimeScreen.QUERY
        else tuple(replace(item, status="Czeka na wydanie") for item in rows()[:2]),
        query=TextInput("slime"),
    )
    frame: AnimeFrame = render_anime(state.snapshot(columns), columns, height, 0)
    lines: list[str] = frame.text.plain.splitlines()
    above, below, left, right = _blank_margins(lines, columns)
    heading: int = frame.first_row - (2 if screen is AnimeScreen.QUERY else 3)
    assert lines[heading].strip() == ("ANIME" if screen is AnimeScreen.QUERY else "Slime")
    assert not lines[heading + 1].strip()
    assert above == heading
    assert len(lines) == height
    assert lines[-1].strip()
    assert abs((frame.first_row if screen is AnimeScreen.QUERY else above) - below) <= 1
    assert screen is AnimeScreen.QUERY or abs(left - right) <= 1


@pytest.mark.parametrize("offset", [0, 6, 16])
def test_a_scrolled_long_table_keeps_its_context_above_the_column_labels(offset: int) -> None:
    items: tuple[AnimeRow, ...] = tuple(
        AnimeRow(str(number), f"Odcinek {number}", number=str(number), date="01.09.2026") for number in range(1, 21)
    )
    title: str = "Anime \u203a That Time I Got Reincarnated as a Slime Season 4 (2026)"
    snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.EPISODES, title, items, cursor=offset, offset=offset)
    frame: AnimeFrame = render_anime(snapshot, 50, 12, 0)
    lines: list[str] = frame.text.plain.splitlines()
    assert frame.first_row == 3
    assert lines[0].strip().startswith("Anime \u203a That Time")
    assert lines[0].strip().endswith("…")
    assert lines[0].count("…") == 1
    assert "Emisja" in lines[2]
    assert f"] {offset + 1} " in lines[frame.first_row]


def test_long_title_uses_two_bottom_lines_without_moving_the_table() -> None:
    title: str = " ".join(f"Słowo{index}" for index in range(18))
    items: tuple[AnimeRow, ...] = (*rows()[:2], AnimeRow("long", title, number="9", date="01.10.2026"))
    plain: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items), 80, 24, 0)
    long: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items, cursor=2), 80, 24, 0)
    lines: list[str] = long.text.plain.splitlines()
    assert long.first_row == plain.first_row
    assert title not in lines[long.first_row + 2]
    assert f"{lines[-3].strip()} {lines[-2].strip()}" == title
    assert plain.text.plain.splitlines()[: plain.first_row] == lines[: long.first_row]


def test_cursor_highlights_a_ready_row_and_keeps_its_green_state() -> None:
    items: tuple[AnimeRow, ...] = (replace(rows()[1], status="Gotowe"), rows()[0])
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items), 80, 24, 0)
    styles: dict[str, str] = {frame.text.plain[span.start : span.end]: str(span.style) for span in frame.text.spans}
    assert styles["A Promise"] == "brand_accent"
    assert styles["Gotowe"] == "success"
    assert styles["\u276f "] == "brand_accent"


@pytest.mark.parametrize("width", [50, 80, 120])
def test_an_episode_in_progress_keeps_its_checkbox_in_line_with_the_others(width: int) -> None:
    items: tuple[AnimeRow, ...] = (replace(rows()[0], status="Pobieram", eligible=False), rows()[1], rows()[3])
    frame: AnimeFrame = render_anime(AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items), width, 24, 0)
    lines: list[str] = frame.text.plain.splitlines()[frame.first_row : frame.first_row + len(items)]
    assert len({line.index("[ ]") for line in lines}) == 1


def test_up_and_down_wrap_around_the_episode_list() -> None:
    view: AnimePanel
    view, _, _ = panel()
    view.handle("up")
    assert view.state.cursor == len(rows()) - 1
    view.handle("down")
    assert view.state.cursor == 0


@pytest.mark.parametrize("width", [50, 80, 120])
def test_changing_episode_states_never_shift_the_table(width: int) -> None:
    starts: set[int] = set()
    for status in ("", "Zlecono", "Przetwarzam", "Nie wyemitowano"):
        items: tuple[AnimeRow, ...] = (replace(rows()[1], status=status), rows()[0])
        for searching in (frozenset(), frozenset({"three"})):
            snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items, searching=searching)
            frame: AnimeFrame = render_anime(snapshot, width, 24, 0)
            starts.add(frame.text.plain.splitlines()[frame.first_row].index("A Pro"))
    assert len(starts) == 1


def test_selection_summary_joins_consecutive_numbers_into_ranges() -> None:
    numbers: tuple[str, ...] = ("1", "2", "3", "4", "6", "7", "7.5", "8", "9", "11", "13", "14", "15")
    items: tuple[AnimeRow, ...] = tuple(AnimeRow(number, f"Odcinek {number}", number=number) for number in numbers)
    snapshot: AnimeSnapshot = AnimeSnapshot(AnimeScreen.EPISODES, "Slime", items, selected=frozenset(numbers))
    assert "Zaznaczone: 13 (1-4, 6-7, 7.5, 8-9, 11, 13-15)" in render_anime(snapshot, 120, 30, 0).text.plain


@pytest.mark.parametrize("width", [13, 14])
def test_a_notice_wrapped_at_a_separator_neither_starts_nor_ends_a_row_with_it(width: int) -> None:
    assert _notice_lines("odcinki 1/12 · gotowe 0", width) == ["odcinki 1/12", "gotowe 0"]


def test_a_notice_longer_than_two_rows_joins_its_tail_with_single_spaces() -> None:
    lines: list[str] = _notice_lines("alpha beta ee ffffffffffff ggg", 12)

    assert lines[1:] == ["ee ffffffff…"]
