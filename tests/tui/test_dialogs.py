from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static

import anishift.tui.dialogs
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import PALETTE_KEY
from anishift.tui.dialogs.base import (
    DIALOG_MARGIN_COLUMNS,
    PANEL_ID,
    TITLE_ID,
    DialogScreen,
    DialogSize,
    dialog_top,
    dialog_width,
    open_dialog,
)
from anishift.tui.dialogs.reorder import (
    ADD_HINT,
    ADD_KEY,
    NOTHING_TO_ADD_TEXT,
    ORDER_HINT,
    ReorderDialog,
    delete_prompt,
    moved_items,
)
from anishift.tui.dialogs.select import (
    CHECKED_MARKER,
    CURRENT_MARKER,
    DISABLED_OPTION_TEXT,
    NO_RESULTS_TEXT,
    PAGE_STEP,
    SelectAction,
    SelectDialog,
    SelectOption,
    SelectOutcome,
    SelectOutcomeKind,
    SelectRow,
    moved_position,
    select_rows,
)
from anishift.tui.dialogs.value import (
    CONFIRM_HINT,
    NOT_A_NUMBER_TEXT,
    OPTIONAL_HINT,
    REQUIRED_VALUE_TEXT,
    ConfirmDialog,
    NumberDialog,
    NumberKind,
    PromptDialog,
    out_of_range_text,
    range_text,
    toggle_boolean,
)
from anishift.tui.state import RunUiState, SessionState, UiRoute

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SMALL_SIZE: Final[tuple[int, int]] = (50, 20)

_PROBE_ID: Final[str] = "focus-probe"

_OTHER_ID: Final[str] = "focus-other"

_ACTION_KEY: Final[str] = "ctrl+d"

_FORBIDDEN_DIALOG_IMPORTS: Final[tuple[str, ...]] = (
    "anishift.application",
    "anishift.config",
    "anishift.paths",
    "anishift.pipeline",
    "anishift.services",
    "json",
    "pathlib",
)


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _option(value: str, *, category: str = "", disabled: bool = False, description: str = "") -> SelectOption[str]:
    return SelectOption(
        value=value,
        title=value,
        description=description or f"Opis {value}",
        category=category,
        disabled=disabled,
    )


def _labels(dialog: DialogScreen[Any], list_id: str) -> list[str]:
    return [str(option.prompt) for option in dialog.query_one(f"#{list_id}", OptionList).options]


def _highlighted(dialog: DialogScreen[Any], list_id: str) -> int | None:
    return dialog.query_one(f"#{list_id}", OptionList).highlighted


def _text(dialog: DialogScreen[Any], widget_id: str) -> str:
    return str(dialog.query_one(f"#{widget_id}", Static).content)


def test_the_three_panel_widths_are_the_frozen_visual_grammar() -> None:
    assert (int(DialogSize.MEDIUM), int(DialogSize.LARGE), int(DialogSize.XLARGE)) == (60, 88, 116)


@pytest.mark.parametrize(
    ("size", "terminal", "expected"),
    [
        (DialogSize.MEDIUM, 200, 60),
        (DialogSize.LARGE, 200, 88),
        (DialogSize.XLARGE, 200, 116),
        (DialogSize.XLARGE, 100, 98),
        (DialogSize.LARGE, 62, 60),
        (DialogSize.MEDIUM, 20, 18),
        (DialogSize.MEDIUM, 1, 1),
    ],
)
def test_a_panel_never_claims_the_last_two_columns(size: DialogSize, terminal: int, expected: int) -> None:
    assert dialog_width(size, terminal_width=terminal) == expected
    assert dialog_width(size, terminal_width=terminal) <= max(1, terminal - DIALOG_MARGIN_COLUMNS)


@pytest.mark.parametrize(("height", "expected"), [(30, 7), (24, 6), (4, 1), (2, 0)])
def test_a_panel_starts_near_a_quarter_of_the_terminal_height(height: int, expected: int) -> None:
    assert dialog_top(terminal_height=height) == expected


@pytest.mark.parametrize(
    ("position", "delta", "count", "wrap", "expected"),
    [
        (0, -1, 4, True, 3),
        (3, 1, 4, True, 0),
        (1, 1, 4, True, 2),
        (0, -1, 4, False, 0),
        (3, 1, 4, False, 3),
        (0, PAGE_STEP, 4, False, 3),
        (3, -PAGE_STEP, 4, False, 0),
        (0, 1, 0, True, 0),
    ],
)
def test_the_cursor_wraps_only_when_it_is_asked_to(
    position: int,
    delta: int,
    count: int,
    wrap: bool,
    expected: int,
) -> None:
    assert moved_position(position, delta, count, wrap=wrap) == expected


def test_an_empty_filter_keeps_the_order_and_adds_one_heading_per_category() -> None:
    rows: tuple[SelectRow, ...] = select_rows(
        (_option("a", category="Grupa"), _option("b", category="Grupa"), _option("c", category="Inne")),
        query="",
    )
    assert [row.label.strip() for row in rows] == ["Grupa", "a", "b", "Inne", "c"]
    assert [row.index for row in rows] == [None, 0, 1, None, 2]


def test_the_current_value_is_marked_independently_of_the_cursor() -> None:
    rows: tuple[SelectRow, ...] = select_rows((_option("a"), _option("b")), current="b")
    assert rows[0].label.startswith(" ")
    assert rows[1].label.startswith(CURRENT_MARKER)


def test_a_typed_filter_returns_a_flat_ranking_without_headings() -> None:
    rows: tuple[SelectRow, ...] = select_rows(
        (_option("translation", category="Grupa"), _option("tts", category="Grupa")),
        query="tt",
    )
    assert [row.label.strip() for row in rows] == ["tts", "translation"]
    assert all(row.index is not None for row in rows)


def test_a_filter_that_matches_nothing_leaves_one_unselectable_row() -> None:
    rows: tuple[SelectRow, ...] = select_rows((_option("alpha"),), query="zzzzz")
    assert [(row.label, row.index) for row in rows] == [(NO_RESULTS_TEXT, None)]


def test_the_multi_mode_marks_every_picked_row() -> None:
    rows: tuple[SelectRow, ...] = select_rows((_option("a"), _option("b")), checked=frozenset({1}))
    assert rows[0].label.startswith(" ")
    assert rows[1].label.startswith(CHECKED_MARKER)


def test_a_row_shows_its_footer_next_to_its_title() -> None:
    rows: tuple[SelectRow, ...] = select_rows((SelectOption(value="x", title="Tytuł", footer="Ctrl+P"),))
    assert "Tytuł" in rows[0].label
    assert rows[0].label.endswith("Ctrl+P")


def test_every_outcome_kind_carries_exactly_what_its_caller_needs() -> None:
    assert SelectOutcome.single("a") == SelectOutcome(kind=SelectOutcomeKind.SINGLE, values=("a",))
    assert SelectOutcome.multi(["a", "b"]).values == ("a", "b")
    assert SelectOutcome.acted("reset", "a") == SelectOutcome(
        kind=SelectOutcomeKind.ACTION,
        values=("a",),
        action="reset",
    )
    assert SelectOutcome.acted("reset").value is None
    assert SelectOutcome[str].cancelled().kind is SelectOutcomeKind.CANCELLED


def test_a_boolean_row_needs_no_modal_to_change() -> None:
    assert toggle_boolean(current=True) is False
    assert toggle_boolean(current=False) is True


def test_a_number_field_always_shows_its_range_and_its_step() -> None:
    assert range_text(minimum=0.0, maximum=10.0, step=0.5) == "Zakres 0 – 10 · krok 0.5"
    assert range_text(minimum=None, maximum=None, step=1.0) == "krok 1"
    assert out_of_range_text(minimum=0.0, maximum=10.0) == "Wartość musi być z zakresu 0 – 10."
    assert out_of_range_text(minimum=1.0, maximum=None).endswith("1.")
    assert out_of_range_text(minimum=None, maximum=9.0).endswith("9.")
    assert out_of_range_text(minimum=None, maximum=None) == ""


@pytest.mark.parametrize(
    ("items", "position", "delta", "expected"),
    [
        (("a", "b", "c"), 0, 1, ("b", "a", "c")),
        (("a", "b", "c"), 2, -1, ("a", "c", "b")),
        (("a", "b", "c"), 0, -1, ("a", "b", "c")),
        (("a", "b", "c"), 2, 1, ("a", "b", "c")),
        ((), 0, 1, ()),
    ],
)
def test_a_move_that_would_leave_the_list_changes_nothing(
    items: tuple[str, ...],
    position: int,
    delta: int,
    expected: tuple[str, ...],
) -> None:
    assert moved_items(items, position, delta) == expected


def test_the_palette_key_opens_the_shared_selector_with_the_registry_rows() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            dialog: Screen[Any] = app.screen
            assert isinstance(dialog, SelectDialog)
            rows: list[str] = [label.strip() for label in _labels(dialog, "select-list")]
            assert set(app.commands.slash_names()) <= {row.removeprefix("/") for row in rows}
            assert app.focused is not None
            assert app.focused.id == "select-filter"

    _run(scenario())


def test_a_second_palette_key_never_opens_a_second_dialog() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            dialogs: list[str] = [type(screen).__name__ for screen in app.screen_stack if _is_dialog(screen)]
            assert dialogs == ["SelectDialog"]

    _run(scenario())


def test_open_dialog_refuses_a_second_dialog_and_says_so() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            first: bool = open_dialog(app, app.session_state, ConfirmDialog(title="A", question="A?"))
            await pilot.pause()
            second: bool = open_dialog(app, app.session_state, ConfirmDialog(title="B", question="B?"))
            await pilot.pause()
            assert (first, second) == (True, False)
            assert len([screen for screen in app.screen_stack if _is_dialog(screen)]) == 1

    _run(scenario())


def test_the_palette_runs_the_picked_command_through_the_one_registry() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"theme")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == ["theme"]
            assert [screen for screen in app.screen_stack if _is_dialog(screen)] == []

    _run(scenario())


def test_escape_cancels_a_dialog_and_gives_the_focus_back() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            probe: Input = await _mount_probe(app, pilot)
            open_dialog(app, app.session_state, _selector(), results.append)
            await pilot.pause()
            assert app.focused is not probe
            await pilot.press("escape")
            await pilot.pause()
            assert results == [SelectOutcome[str].cancelled()]
            assert app.focused is probe
            assert app.session_state.modal_focus_stack == []
            assert app.session_state.focus_id == _PROBE_ID

    _run(scenario())


def test_the_help_quit_key_cancels_a_dialog_and_gives_the_focus_back() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            probe: Input = await _mount_probe(app, pilot)
            open_dialog(app, app.session_state, _selector(), results.append)
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert results == [SelectOutcome[str].cancelled()]
            assert app.focused is probe
            assert app.is_running is True

    _run(scenario())


def test_a_dismiss_focuses_whatever_now_carries_the_remembered_id() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            slot: Widget = app.query_one("#app-composer")
            await slot.mount(Input(id=_OTHER_ID))
            probe: Input = await _mount_probe(app, pilot)
            open_dialog(app, app.session_state, _selector())
            await pilot.pause()
            await probe.remove()
            rebuilt: Input = Input(id=_PROBE_ID)
            await slot.mount(rebuilt)
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is rebuilt

    _run(scenario())


def test_a_dismiss_never_refocuses_an_element_that_is_gone() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            probe: Input = await _mount_probe(app, pilot)
            open_dialog(app, app.session_state, _selector())
            await pilot.pause()
            await probe.remove()
            await pilot.press("escape")
            await pilot.pause()
            assert app.session_state.focus_id == _PROBE_ID
            assert app.focused is None

    _run(scenario())


def test_a_disabled_row_is_never_confirmed() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("a", disabled=True), _option("b")),
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            assert _text(dialog, "select-detail") == DISABLED_OPTION_TEXT
            assert app.screen is dialog
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            assert results == [SelectOutcome.single("b")]

    _run(scenario())


def test_a_selector_returns_its_decision_without_performing_it() -> None:
    async def scenario() -> None:
        stored: dict[str, str] = {"theme": "anishift-dark"}
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option("anishift-dark"), _option("anishift-light")),
                current="anishift-dark",
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            assert results == [SelectOutcome.single("anishift-light")]
            assert stored == {"theme": "anishift-dark"}

    _run(scenario())


@pytest.mark.parametrize(
    ("current", "initial", "expected"),
    [(None, None, "a"), (None, 2, "c"), ("b", None, "b"), ("b", 0, "a")],
)
def test_the_highlight_hook_announces_the_row_the_dialog_opens_on(
    current: str | None,
    initial: int | None,
    expected: str,
) -> None:
    async def scenario() -> None:
        seen: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option("a"), _option("b"), _option("c")),
                current=current,
                initial_highlight=initial,
                on_highlight=seen.append,
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            assert seen == [expected]

    _run(scenario())


def test_the_highlight_hook_announces_every_move_of_the_cursor() -> None:
    async def scenario() -> None:
        seen: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option("a"), _option("b"), _option("c")),
                on_highlight=seen.append,
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            assert seen == ["a"]
            for key in ("down", "down", "down", "end", "home", "pagedown", "pageup"):
                await pilot.press(key)
                await pilot.pause()
            assert seen == ["a", "b", "c", "a", "c", "a", "c", "a"]

    _run(scenario())


def test_the_highlight_hook_announces_what_the_filter_leaves_highlighted() -> None:
    async def scenario() -> None:
        seen: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option("alfa"), _option("beta")),
                on_highlight=seen.append,
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            assert seen == ["alfa"]
            await pilot.press("b")
            await pilot.pause()
            assert seen == ["alfa", "beta"]

    _run(scenario())


def test_the_highlight_hook_stays_silent_on_a_heading_and_on_an_empty_result() -> None:
    async def scenario() -> None:
        seen: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option("a", category="Grupa A"), _option("b", category="Grupa B")),
                on_highlight=seen.append,
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            headings: list[str] = ["Grupa A", "Grupa B"]
            assert _labels(dialog, "select-list")[0] == headings[0]
            assert seen == ["a"]
            for _ in range(3):
                await pilot.press("down")
                await pilot.pause()
            assert seen == ["a", "b", "a", "b"]
            await pilot.press(*"zzz")
            await pilot.pause()
            assert _labels(dialog, "select-list") == [NO_RESULTS_TEXT]
            assert seen == ["a", "b", "a", "b"]
            assert not [value for value in seen if value in headings]

    _run(scenario())


def test_a_live_preview_built_on_the_hook_can_roll_back_after_escape() -> None:
    async def scenario() -> None:
        before: str = "anishift-dark"
        previewed: list[str] = []
        results: list[SelectOutcome[str] | None] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Motyw",
                options=(_option(before), _option("anishift-light")),
                current=before,
                on_highlight=previewed.append,
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            assert previewed == [before]
            await pilot.press("down")
            await pilot.pause()
            assert previewed == [before, "anishift-light"]
            await pilot.press("escape")
            await pilot.pause()
            outcome: SelectOutcome[str] | None = results[0]
            assert outcome is not None
            assert outcome.kind is SelectOutcomeKind.CANCELLED
            restored: str = before if outcome.kind is SelectOutcomeKind.CANCELLED else str(outcome.value)
            assert restored == before
            assert previewed == [before, "anishift-light"]

    _run(scenario())


def test_a_dialog_without_a_caller_callback_changes_nothing_at_all() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            state: SessionState = app.session_state
            theme: str | None = app.theme
            open_dialog(app, state, _selector())
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert state.feedback is None
            assert state.route is UiRoute.WORKSPACE
            assert state.run_state is RunUiState.IDLE
            assert app.theme == theme
            assert [screen for screen in app.screen_stack if _is_dialog(screen)] == []

    _run(scenario())


def test_no_dialog_module_can_reach_persistence_or_the_application_layer() -> None:
    offenders: list[str] = [
        f"{path.name}:{module}"
        for path in _dialog_sources()
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if module.startswith(_FORBIDDEN_DIALOG_IMPORTS)
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "source",
    [
        "from anishift.config.user_settings import load_preferences\n",
        "import json\n",
        "from pathlib import Path\n",
        "from anishift.application import ExecutionPlan\n",
    ],
)
def test_the_dialog_import_guard_flags_every_way_to_persist(source: str) -> None:
    assert [module for module in _imported_modules(source) if module.startswith(_FORBIDDEN_DIALOG_IMPORTS)]


def test_the_cursor_starts_on_the_current_value_or_where_the_caller_asked() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            current: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("a"), _option("b"), _option("c")),
                current="c",
            )
            open_dialog(app, app.session_state, current)
            await pilot.pause()
            assert _highlighted(current, "select-list") == 2
            await pilot.press("escape")
            await pilot.pause()
            asked: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("a"), _option("b"), _option("c")),
                current="c",
                initial_highlight=1,
            )
            open_dialog(app, app.session_state, asked)
            await pilot.pause()
            assert _highlighted(asked, "select-list") == 1

    _run(scenario())


def test_the_cursor_skips_headings_and_wraps_around_the_list() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("a", category="Grupa"), _option("b", category="Inne")),
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == 1
            await pilot.press("down")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == 3
            await pilot.press("down")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == 1

    _run(scenario())


def test_the_list_keys_beat_the_text_cursor_of_the_filter_box() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=tuple(_option(f"a{index}") for index in range(20)),
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            await pilot.press(*"a1")
            await pilot.pause()
            filter_box: Input = dialog.query_one("#select-filter", Input)
            await pilot.press("end")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == len(_labels(dialog, "select-list")) - 1
            assert filter_box.cursor_position == 2
            await pilot.press("home")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == 0
            assert filter_box.cursor_position == 2

    _run(scenario())


def test_a_page_key_moves_ten_rows_without_wrapping() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=tuple(_option(f"a{index}") for index in range(30)),
            )
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            await pilot.press("pagedown")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == PAGE_STEP
            await pilot.press("pageup")
            await pilot.press("pageup")
            await pilot.pause()
            assert _highlighted(dialog, "select-list") == 0

    _run(scenario())


def test_an_empty_result_stays_closable() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(title="Wybór", options=(_option("alpha"),))
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press(*"zzz")
            await pilot.pause()
            assert [label.strip() for label in _labels(dialog, "select-list")] == [NO_RESULTS_TEXT]
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            await pilot.press("escape")
            await pilot.pause()
            assert results == [SelectOutcome[str].cancelled()]

    _run(scenario())


def test_the_multi_mode_toggles_with_space_and_confirms_the_whole_set() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("a"), _option("b"), _option("c")),
                multi=True,
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            assert _labels(dialog, "select-list")[0].startswith(CHECKED_MARKER)
            assert dialog.query_one("#select-filter", Input).value == ""
            await pilot.press("down")
            await pilot.press("down")
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert results == [SelectOutcome.multi(["a", "c"])]

    _run(scenario())


def test_an_action_key_returns_the_action_with_the_highlighted_value() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(
                title="Wybór",
                options=(_option("ab"), _option("c")),
                actions=(SelectAction(name="reset", key=_ACTION_KEY, label="Domyślne"),),
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            assert "Domyślne" in _text(dialog, "select-actions")
            box: Input = dialog.query_one("#select-filter", Input)
            await pilot.press(*"ab")
            await pilot.press("left")
            await pilot.pause()
            await pilot.press(_ACTION_KEY)
            await pilot.pause()
            assert results == [SelectOutcome.acted("reset", "ab")]
            assert box.value == "ab"

    _run(scenario())


def test_a_click_on_the_dim_backdrop_cancels_the_dialog() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = _selector()
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.click(offset=(1, 1))
            await pilot.pause()
            assert results == [SelectOutcome[str].cancelled()]

    _run(scenario())


def test_shrinking_the_terminal_never_pushes_the_panel_off_the_screen() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: SelectDialog[str] = SelectDialog(title="Wybór", options=(_option("a"),), size=DialogSize.XLARGE)
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            assert dialog.query_one(f"#{PANEL_ID}").outer_size.width == _FULL_SIZE[0] - DIALOG_MARGIN_COLUMNS
            await pilot.resize_terminal(*_SMALL_SIZE)
            await pilot.pause()
            assert dialog.query_one(f"#{PANEL_ID}").outer_size.width == _SMALL_SIZE[0] - DIALOG_MARGIN_COLUMNS
            assert _text(dialog, TITLE_ID) == "Wybór"

    _run(scenario())


def test_a_refused_text_stays_in_the_editor_with_its_reason() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: PromptDialog = PromptDialog(
                title="Nazwa",
                value="zle",
                validate=lambda text: None if text == "dobre" else "Zła nazwa.",
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            assert dialog.query_one("#value-input", Input).value == "zle"
            assert _text(dialog, "value-error") == "Zła nazwa."
            await pilot.press("ctrl+u")
            await pilot.press(*"dobre")
            await pilot.pause()
            assert _text(dialog, "value-error") == ""
            await pilot.press("enter")
            await pilot.pause()
            assert results == ["dobre"]

    _run(scenario())


def test_a_required_text_refuses_an_empty_value() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: PromptDialog = PromptDialog(title="Nazwa")
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            assert _text(dialog, "value-error") == REQUIRED_VALUE_TEXT

    _run(scenario())


def test_an_optional_text_returns_nothing_when_it_is_left_empty() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: PromptDialog = PromptDialog(title="Nazwa", optional=True)
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            assert OPTIONAL_HINT in _text(dialog, "value-hint")
            await pilot.press("enter")
            await pilot.pause()
            assert results == [None]

    _run(scenario())


def test_a_decimal_field_steps_and_refuses_a_value_outside_its_range() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: NumberDialog = NumberDialog(
                title="Głośność",
                value=1.0,
                minimum=0.0,
                maximum=2.0,
                step=0.5,
            )
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            box: Input = dialog.query_one("#value-input", Input)
            assert "krok 0.5" in _text(dialog, "value-hint")
            await pilot.press("up")
            await pilot.pause()
            assert box.value == "1.5"
            await pilot.press("down")
            await pilot.press("down")
            await pilot.pause()
            assert box.value == "0.5"
            box.value = "9"
            await pilot.pause()
            assert _text(dialog, "value-error") == out_of_range_text(minimum=0.0, maximum=2.0)
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            box.value = "1.5"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert results == [1.5]

    _run(scenario())


def test_a_whole_field_refuses_a_decimal_and_returns_an_integer() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: NumberDialog = NumberDialog(title="Liczba", value=2, kind=NumberKind.WHOLE, minimum=0.0)
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            box: Input = dialog.query_one("#value-input", Input)
            box.value = "2.5"
            await pilot.pause()
            assert _text(dialog, "value-error") == NOT_A_NUMBER_TEXT
            await pilot.press("enter")
            await pilot.pause()
            assert results == []
            box.value = "2"
            await pilot.press("up")
            await pilot.pause()
            assert box.value == "3"
            await pilot.press("enter")
            await pilot.pause()
            assert results == [3]
            assert isinstance(results[0], int)

    _run(scenario())


def test_a_confirmation_answers_yes_on_enter_and_no_on_escape() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            first: ConfirmDialog = ConfirmDialog(title="Wyjście", question="Zamknąć aplikację?")
            open_dialog(app, app.session_state, first, results.append)
            await pilot.pause()
            assert _text(first, "confirm-message") == "Zamknąć aplikację?"
            assert CONFIRM_HINT in str(first.query_one(f"#{PANEL_ID}").query(Static).nodes[-1].content)
            await pilot.press("enter")
            await pilot.pause()
            second: ConfirmDialog = ConfirmDialog(title="Wyjście", question="Zamknąć aplikację?")
            open_dialog(app, app.session_state, second, results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert results == [True, False]

    _run(scenario())


def test_a_reorder_commits_the_whole_moved_list() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        items: list[str] = ["a", "b", "c"]
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=items)
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            assert _text(dialog, "reorder-hint") == ORDER_HINT
            await pilot.press("shift+down")
            await pilot.pause()
            assert _labels(dialog, "reorder-list") == ["b", "a", "c"]
            assert _highlighted(dialog, "reorder-list") == 1
            await pilot.press("enter")
            await pilot.pause()
            assert results == [("b", "a", "c")]
            assert items == ["a", "b", "c"]

    _run(scenario())


def test_a_reorder_rolls_the_whole_list_back_on_escape() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        items: list[str] = ["a", "b", "c"]
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=items)
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press("shift+down")
            await pilot.pause()
            assert dialog.members == ("b", "a", "c")
            await pilot.press("escape")
            await pilot.pause()
            assert results == [None]
            assert items == ["a", "b", "c"]

    _run(scenario())


def test_a_removal_needs_its_confirmation() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=("a", "b"))
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            await pilot.press("delete")
            await pilot.pause()
            assert _text(dialog, "reorder-message") == delete_prompt("a")
            armed: tuple[str, ...] = dialog.members
            assert armed == ("a", "b")
            await pilot.press("down")
            await pilot.press("delete")
            await pilot.pause()
            rearmed: tuple[str, ...] = dialog.members
            assert rearmed == ("a", "b")
            await pilot.press("delete")
            await pilot.pause()
            removed: tuple[str, ...] = dialog.members
            assert removed == ("a",)

    _run(scenario())


def test_a_reorder_adds_a_candidate_without_stacking_a_second_dialog() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=("a",), candidates=("a", "b", "c"))
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            await pilot.press(ADD_KEY)
            await pilot.pause()
            assert _labels(dialog, "reorder-list") == ["b", "c"]
            assert _text(dialog, "reorder-hint") == ADD_HINT
            assert len([screen for screen in app.screen_stack if _is_dialog(screen)]) == 1
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            assert dialog.members == ("a", "c")
            assert _text(dialog, "reorder-hint") == ORDER_HINT
            assert app.screen is dialog

    _run(scenario())


def test_a_reorder_says_when_there_is_nothing_left_to_add() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=("a",), candidates=("a",))
            open_dialog(app, app.session_state, dialog)
            await pilot.pause()
            await pilot.press(ADD_KEY)
            await pilot.pause()
            assert _text(dialog, "reorder-message") == NOTHING_TO_ADD_TEXT
            assert _text(dialog, "reorder-hint") == ORDER_HINT

    _run(scenario())


def test_escape_leaves_the_add_mode_before_it_leaves_the_dialog() -> None:
    async def scenario() -> None:
        results: list[Any] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            dialog: ReorderDialog = ReorderDialog(title="Kolejność", items=("a",), candidates=("a", "b"))
            open_dialog(app, app.session_state, dialog, results.append)
            await pilot.pause()
            await pilot.press(ADD_KEY)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert results == []
            assert _text(dialog, "reorder-hint") == ORDER_HINT
            await pilot.press("escape")
            await pilot.pause()
            assert results == [None]

    _run(scenario())


def _is_dialog(screen: object) -> bool:
    return isinstance(screen, DialogScreen)


def _imported_modules(source: str) -> list[str]:
    tree: ast.Module = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def _dialog_sources() -> list[Path]:
    root: Path = Path(anishift.tui.dialogs.__file__).parent
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _selector() -> SelectDialog[str]:
    return SelectDialog(title="Wybór", options=(_option("a"), _option("b")))


def _spy_dispatch(app: AniShiftApp, calls: list[str]) -> None:
    original: Callable[[str], bool] = app.commands.dispatch

    def dispatch(name: str) -> bool:
        calls.append(name)
        return original(name)

    app.commands.dispatch = dispatch  # type: ignore[method-assign]


async def _mount_probe(app: AniShiftApp, pilot: Any) -> Input:
    probe: Input = Input(id=_PROBE_ID)
    await app.query_one("#app-composer").mount(probe)
    probe.focus()
    await pilot.pause()
    return probe
