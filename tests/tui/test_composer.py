from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Final

import pytest
from textual.app import App
from textual.events import Paste
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static
from textual.widgets.input import Selection
from tui_fakes import shell

from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import EXIT_COMMAND_NAME, PALETTE_COMMAND_NAME
from anishift.tui.commands.palette import CommandOption, slash_options
from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.value import PromptDialog
from anishift.tui.messages import AutoRequested, PlanFailed
from anishift.tui.state import RunUiState, SessionState
from anishift.tui.strings import (
    COMPOSER_PLACEHOLDER,
    COMPOSER_PLAIN_TEXT,
    COMPOSER_UNKNOWN_COMMAND,
    COMPOSER_UNKNOWN_COMMAND_SUGGESTION,
    CONTEXT_MODE_AUTO,
    CONTEXT_MODEL_UNSET,
    CONTEXT_PROVIDER,
)
from anishift.tui.widgets.composer import (
    BOX_ID,
    CONTEXT_ID,
    HINT_ID,
    INPUT_ID,
    SUGGESTIONS_ID,
    Composer,
    ComposerSubmission,
    ComposerSubmissionKind,
    classify,
    context_text,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_EDGE_COLUMNS: Final[int] = 3

_PROBE_ID: Final[str] = "composer-probe"

_DIALOG_INPUT_ID: Final[str] = "value-input"

_REPEAT: Final[int] = 12

_SUGGESTION_LIMIT: Final[int] = 20

_OVERLAY_ROW: Final[int] = 1

_POINTER_REPEATS: Final[int] = 5

_REASON: Final[str] = "Nie ukończono"

_BLANK_LINES: Final[tuple[str, ...]] = ("", " ", "   ", "\t", "\n", " \t \n ")

_PLAIN_LINES: Final[tuple[str, ...]] = ("witaj", "theme", "auto uruchom", "a/b", "  tekst  ")

_SLASH_LINES: Final[tuple[tuple[str, str], ...]] = (
    ("/theme", "theme"),
    ("  /theme  ", "theme"),
    ("/Theme", "theme"),
    ("/theme dodatkowe", "theme"),
    ("/tts", "tts"),
    ("/nieznana", "nieznana"),
    ("/", ""),
    ("/   ", ""),
)

_BUSY_STATES: Final[tuple[RunUiState, ...]] = (
    RunUiState.PLANNING,
    RunUiState.RUNNING,
    RunUiState.CANCELLING,
)


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _field(app: AniShiftApp) -> Input:
    return app.query_one(f"#{INPUT_ID}", Input)


def _hint(app: AniShiftApp) -> str:
    return str(app.query_one(f"#{HINT_ID}", Static).content)


def _suggestions(app: AniShiftApp) -> OptionList:
    return app.query_one(f"#{SUGGESTIONS_ID}", OptionList)


def _rows(app: AniShiftApp) -> list[str]:
    listing: OptionList = _suggestions(app)
    return [str(listing.get_option_at_index(index).prompt) for index in range(listing.option_count)]


def _spy_dispatch(app: AniShiftApp, calls: list[str]) -> None:
    original: Callable[[str], bool] = app.commands.dispatch

    def dispatch(name: str) -> bool:
        calls.append(name)
        return original(name)

    app.commands.dispatch = dispatch  # type: ignore[method-assign]


def _spy_auto_requests(app: AniShiftApp, generations: list[int]) -> None:
    original: Callable[[Message], bool] = app.post_message

    def post_message(message: Message) -> bool:
        if isinstance(message, AutoRequested):
            generations.append(message.generation)
        return original(message)

    app.post_message = post_message  # type: ignore[method-assign]


def test_a_blank_line_asks_for_the_default_auto_workflow() -> None:
    for line in _BLANK_LINES:
        assert classify(line) == ComposerSubmission(kind=ComposerSubmissionKind.EMPTY_AUTO)


def test_text_without_a_slash_names_no_command() -> None:
    for line in _PLAIN_LINES:
        assert classify(line) == ComposerSubmission(kind=ComposerSubmissionKind.PLAIN_TEXT)


@pytest.mark.parametrize(("line", "command"), _SLASH_LINES)
def test_a_slash_line_carries_one_folded_command_name(line: str, command: str) -> None:
    assert classify(line) == ComposerSubmission(kind=ComposerSubmissionKind.SLASH, command=command)


def test_classifying_the_same_line_twice_gives_the_same_answer() -> None:
    assert classify("/Theme  x") == classify("/Theme  x")


def test_the_context_line_names_the_mode_the_provider_and_the_model() -> None:
    assert context_text(mode="Auto", provider="Foundry", model="m") == "Auto · Foundry: m"


def test_the_composer_starts_with_the_default_context_line() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert str(app.query_one(f"#{CONTEXT_ID}", Static).content) == context_text(
                mode=CONTEXT_MODE_AUTO,
                provider=CONTEXT_PROVIDER,
                model=CONTEXT_MODEL_UNSET,
            )

    _run(scenario())


def test_the_context_line_follows_what_the_shell_says() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.query_one(Composer).show_context(mode="Manual", provider="Foundry", model="claude")
            await pilot.pause()
            assert str(app.query_one(f"#{CONTEXT_ID}", Static).content) == "Manual · Foundry: claude"

    _run(scenario())


def test_the_composer_shows_the_placeholder_of_the_specification() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert _field(app).placeholder == COMPOSER_PLACEHOLDER
            assert app.query_one(Composer) is not None

    _run(scenario())


def test_only_the_accent_edge_and_its_padding_stand_in_front_of_the_text_field() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            box: Widget = app.query_one(f"#{BOX_ID}")
            assert _field(app).region.x == box.region.x + _EDGE_COLUMNS

    _run(scenario())


def test_the_field_holds_the_focus_as_soon_as_the_shell_mounts() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.focused is _field(app)
            assert _suggestions(app).display is False
            assert _hint(app) == ""

    _run(scenario())


def test_one_empty_enter_publishes_exactly_one_auto_request() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1]
            assert app.session_state.run_state is RunUiState.PLANNING
            assert app.session_state.generation == 1

    _run(scenario())


def test_two_enters_in_one_burst_publish_one_auto_request() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert requests == [1]
            assert app.session_state.generation == 1

    _run(scenario())


def test_two_enters_separated_by_a_full_turn_still_publish_one_auto_request() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1]
            assert app.session_state.generation == 1

    _run(scenario())


def test_a_repeated_enter_key_publishes_one_auto_request() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press(*(["enter"] * _REPEAT))
            await pilot.pause()
            assert requests == [1]
            assert app.session_state.generation == 1

    _run(scenario())


def test_blanks_and_enter_publish_one_auto_request_and_clear_the_field() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("space", "space", "space")
            await pilot.pause()
            assert _field(app).value == "   "
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1]
            assert _field(app).value == ""

    _run(scenario())


@pytest.mark.parametrize("busy", _BUSY_STATES)
def test_no_empty_enter_starts_anything_while_the_session_is_busy(busy: RunUiState) -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            app.session_state.run_state = busy
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert requests == []
            assert app.session_state.generation == 0
            assert app.session_state.run_state is busy

    _run(scenario())


def test_the_field_keeps_its_blanks_when_the_reservation_is_refused() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            app.session_state.run_state = RunUiState.RUNNING
            await pilot.press("space", "space")
            await pilot.pause()
            typed: str = _field(app).value
            await pilot.press("enter")
            await pilot.pause()
            assert requests == []
            assert _field(app).value == typed

    _run(scenario())


def test_an_open_dialog_takes_the_focus_and_no_enter_starts_auto() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            assert open_dialog(app, app.session_state, PromptDialog(title="Wartość")) is True
            await pilot.pause()
            assert app.focused is not None
            assert app.focused.id == _DIALOG_INPUT_ID
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.generation == 0

    _run(scenario())


def test_only_the_field_of_the_composer_can_start_auto() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            probe: Input = Input(id=_PROBE_ID)
            await app.query_one(Composer).mount(probe)
            probe.focus()
            await pilot.pause()
            assert app.focused is probe
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_the_shell_answers_no_enter_of_its_own() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            app.set_focus(None)
            await pilot.pause()
            assert app.focused is None
            await pilot.press("enter", "enter")
            await pilot.pause()
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_the_shell_declares_no_bindings_of_its_own() -> None:
    assert "BINDINGS" not in vars(AniShiftApp)
    assert AniShiftApp.BINDINGS is App.BINDINGS


def test_shift_enter_is_never_read_as_an_empty_line() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("shift+enter", "shift+enter")
            await pilot.pause()
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_pasting_blanks_never_submits_anything() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            _field(app).post_message(Paste("   "))
            await pilot.pause()
            assert _field(app).value == "   "
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_pasting_a_command_and_a_newline_never_runs_it() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            _spy_auto_requests(app, requests)
            _field(app).post_message(Paste("/theme\ndalej"))
            await pilot.pause()
            assert _field(app).value == "/theme"
            assert calls == []
            assert requests == []

    _run(scenario())


def test_plain_text_stays_in_the_field_and_touches_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            _spy_auto_requests(app, requests)
            await pilot.press(*"theme")
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert requests == []
            assert _field(app).value == "theme"
            assert _hint(app) == COMPOSER_PLAIN_TEXT
            assert app.session_state == SessionState()

    _run(scenario())


def test_plain_text_offers_no_suggestions() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*"theme")
            await pilot.pause()
            assert _suggestions(app).display is False

    _run(scenario())


def test_a_slash_line_offers_the_rows_of_the_one_registry() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()
            listing: OptionList = _suggestions(app)
            assert listing.display is True
            offered: tuple[CommandOption, ...] = slash_options(app.commands, "/")
            assert 0 < listing.option_count == len(offered) <= _SUGGESTION_LIMIT
            assert [row.split()[0] for row in _rows(app)] == [option.label for option in offered]
            assert {row.split()[0].removeprefix("/") for row in _rows(app)} <= set(app.commands.slash_names())

    _run(scenario())


def test_enter_writes_the_highlighted_suggestion_and_runs_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/th")
            await pilot.pause()
            expected: CommandOption = slash_options(app.commands, "/th")[0]
            assert _suggestions(app).highlighted == 0
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert _field(app).value == f"{expected.label} "
            assert _suggestions(app).display is False

    _run(scenario())


def test_ctrl_p_walks_the_suggestions_while_they_are_offered() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert _suggestions(app).highlighted == 1
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert _suggestions(app).highlighted == 0
            assert calls == []

    _run(scenario())


def test_ctrl_p_opens_the_command_list_while_no_suggestion_is_offered() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            assert _suggestions(app).display is False
            await pilot.press("ctrl+p")
            await pilot.pause()
            assert calls == [PALETTE_COMMAND_NAME]

    _run(scenario())


def test_ctrl_c_empties_a_field_that_holds_something() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/th")
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert _field(app).value == ""
            assert _suggestions(app).display is False
            assert calls == []

    _run(scenario())


def test_ctrl_c_leaves_the_application_once_the_field_holds_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            assert _field(app).value == ""
            await pilot.press("ctrl+c")
            await pilot.pause()
            assert calls == [EXIT_COMMAND_NAME]

    _run(scenario())


def test_ctrl_d_leaves_the_application() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert calls == [EXIT_COMMAND_NAME]

    _run(scenario())


def test_the_word_keys_of_the_reference_walk_and_delete_backwards() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            field: Input = _field(app)
            field.value = "alpha beta gamma"
            field.cursor_position = len(field.value)
            await pilot.pause()
            await pilot.press("alt+left")
            await pilot.pause()
            assert field.cursor_position == len("alpha beta ")
            await pilot.press("alt+right")
            await pilot.pause()
            assert field.cursor_position == len(field.value)
            await pilot.press("ctrl+backspace")
            await pilot.pause()
            assert field.value == "alpha beta "
            await pilot.press("alt+backspace")
            await pilot.pause()
            assert field.value == "alpha "

    _run(scenario())


def test_the_pointer_carries_the_one_highlight_to_the_row_it_rests_on() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()
            listing: OptionList = _suggestions(app)
            assert listing.highlighted == 0
            await pilot.hover(listing, offset=(4, 2))
            await pilot.pause()
            assert listing.highlighted == 2

    _run(scenario())


def test_the_pointer_carries_the_highlight_without_ever_scrolling_the_overlay() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()
            listing: OptionList = _suggestions(app)
            assert listing.max_scroll_y > 0
            await pilot.press("up")
            await pilot.pause()
            scrolled: int = listing.scroll_offset.y
            assert scrolled > 0
            seen: list[tuple[int | None, int]] = []
            for _ in range(_POINTER_REPEATS):
                await pilot.hover(listing, offset=(4, _OVERLAY_ROW))
                await pilot.pause()
                seen.append((listing.highlighted, listing.scroll_offset.y))
            assert seen == [(scrolled + _OVERLAY_ROW, scrolled)] * _POINTER_REPEATS

    _run(scenario())


def test_only_the_text_field_lets_one_select_what_it_holds() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*"/theme")
            await pilot.pause()
            field: Input = _field(app)
            field.selection = Selection(0, len(field.value))
            await pilot.pause()
            assert field.selected_text == "/theme"
            assert app.ALLOW_SELECT is False
            assert field.cursor_blink is False

    _run(scenario())


def test_a_second_enter_runs_the_name_the_first_one_wrote() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/th")
            await pilot.pause()
            expected: CommandOption = slash_options(app.commands, "/th")[0]
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == [expected.name]

    _run(scenario())


def test_a_click_runs_the_suggestion_it_lands_on() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press("/")
            await pilot.pause()
            listing: OptionList = _suggestions(app)
            expected: str = slash_options(app.commands, "/")[1].name
            await pilot.click(listing, offset=(4, 1))
            await pilot.pause()
            assert calls == [expected]
            assert listing.display is False

    _run(scenario())


def test_moving_the_highlight_changes_which_name_enter_writes() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/th")
            await pilot.pause()
            offered: tuple[CommandOption, ...] = slash_options(app.commands, "/th")
            await pilot.press("down")
            await pilot.pause()
            assert _suggestions(app).highlighted == 1
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert _field(app).value == f"{offered[1].label} "
            assert offered[1].label != offered[0].label

    _run(scenario())


def test_the_highlight_wraps_at_the_first_suggestion() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*"/th")
            await pilot.pause()
            last: int = _suggestions(app).option_count - 1
            await pilot.press("up")
            await pilot.pause()
            assert last > 0
            assert _suggestions(app).highlighted == last

    _run(scenario())


def test_tab_completes_the_name_and_runs_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/th")
            await pilot.pause()
            expected: str = slash_options(app.commands, "/th")[0].label
            await pilot.press("tab")
            await pilot.pause()
            assert _field(app).value == f"{expected} "
            assert calls == []
            assert _suggestions(app).display is False
            assert app.focused is _field(app)

    _run(scenario())


def test_tab_keeps_moving_the_focus_while_no_suggestion_is_offered() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            probe: Input = Input(id=_PROBE_ID)
            await app.query_one(Composer).mount(probe)
            await pilot.pause()
            assert app.focused is _field(app)
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is probe

    _run(scenario())


def test_escape_hides_the_suggestions_and_keeps_the_typed_line() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*"/th")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert _suggestions(app).display is False
            assert _field(app).value == "/th"

    _run(scenario())


@pytest.mark.parametrize("line", ["/", "/th"])
def test_deleting_the_typed_line_hides_the_suggestions(line: str) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*line)
            await pilot.pause()
            assert _suggestions(app).display is True
            await pilot.press(*["backspace"] * len(line))
            await pilot.pause()
            assert _field(app).value == ""
            assert _suggestions(app).display is False

    _run(scenario())


def test_completing_a_suggestion_keeps_the_list_closed() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*"/th")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert _suggestions(app).display is False
            assert _field(app).value.startswith("/")

    _run(scenario())


def test_a_bare_slash_never_reaches_the_registry() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            _spy_auto_requests(app, requests)
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert requests == []
            assert _hint(app) == COMPOSER_UNKNOWN_COMMAND
            assert _field(app).value == "/"

    _run(scenario())


def test_an_unknown_command_shows_one_close_name_and_runs_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/thme")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert _hint(app) == COMPOSER_UNKNOWN_COMMAND_SUGGESTION.format(command="/theme")
            assert _field(app).value == "/thme"

    _run(scenario())


def test_an_unknown_command_without_a_close_name_names_nothing() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(*"/qqqq")
            await pilot.pause()
            assert _suggestions(app).display is False
            await pilot.press("enter")
            await pilot.pause()
            assert calls == []
            assert _hint(app) == COMPOSER_UNKNOWN_COMMAND
            assert _field(app).value == "/qqqq"

    _run(scenario())


def test_a_command_that_opens_a_route_clears_the_field() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            _spy_auto_requests(app, requests)
            await pilot.press(*"/manual")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == ["manual"]
            assert _field(app).value == ""
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE

    _run(scenario())


def test_the_auto_command_never_starts_a_run() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            _spy_auto_requests(app, requests)
            await pilot.press(*"/auto")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert calls == ["auto"]
            assert requests == []
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.generation == 0

    _run(scenario())


def test_a_failed_plan_gives_the_gate_back_to_the_next_empty_enter() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("enter")
            await pilot.pause()
            app.post_message(PlanFailed(reason=_REASON, generation=1))
            await pilot.pause()
            assert app.session_state.run_state is RunUiState.IDLE
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1, 2]

    _run(scenario())


def test_a_plan_failure_of_a_replaced_generation_never_reopens_the_gate() -> None:
    async def scenario() -> None:
        requests: list[int] = []
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_auto_requests(app, requests)
            await pilot.press("enter")
            await pilot.pause()
            app.post_message(PlanFailed(reason=_REASON, generation=1))
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1, 2]
            app.post_message(PlanFailed(reason=_REASON, generation=1))
            await pilot.pause()
            assert app.session_state.run_state is RunUiState.PLANNING
            assert app.session_state.generation == 2
            await pilot.press("enter")
            await pilot.pause()
            assert requests == [1, 2]

    _run(scenario())
