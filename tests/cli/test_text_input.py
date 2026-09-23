from __future__ import annotations

import pytest
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.text import Text

from anishift.cli.interactive.palette import BRAND_THEME
from anishift.cli.interactive.text_input import TextInput


def test_backwards_selection_replaces_text_and_can_be_undone() -> None:
    editor: TextInput = TextInput("one two")
    editor.handle("ctrl-shift-left")
    assert editor.selected
    editor.handle("text:three")
    assert editor.text == "one three"
    editor.handle("undo")
    assert editor.text == "one two"
    editor.handle("redo")
    assert editor.text == "one three"


def test_word_navigation_and_deletion_keep_the_rest_of_the_line() -> None:
    editor: TextInput = TextInput("one two three")
    editor.handle("home")
    editor.handle("ctrl-right")
    assert editor.cursor == 4
    editor.handle("ctrl-delete")
    assert editor.text == "one  three"
    editor.handle("end")
    editor.handle("ctrl-backspace")
    assert editor.text == "one  "


def test_copy_and_cut_share_the_application_clipboard_between_fields() -> None:
    application: Application[None] = Application(input=DummyInput(), output=DummyOutput())
    first: TextInput = TextInput("anime title")
    second: TextInput = TextInput()
    with set_app(application):
        first.handle("select-all")
        assert first.handle("interrupt")
        assert first.selected
        second.handle("paste")
        assert second.text == "anime title"
        first.handle("cut")
        assert first.text == ""
        assert not first.handle("interrupt")


def test_cursor_is_visible_in_a_narrow_masked_field_without_exposing_text() -> None:
    editor: TextInput = TextInput("secret" * 20)
    editor.handle("shift-left")
    rendered = editor.render(12, masked=True)
    assert rendered.cell_len <= 12
    assert any(span.style == "reverse" and span.end == len(rendered.plain) for span in rendered.spans)
    assert "secret" not in rendered.plain
    assert any(span.style == "reverse" for span in rendered.spans)


@pytest.mark.parametrize("masked", [False, True])
def test_inactive_render_hides_selection_and_cursor_without_changing_the_buffer(masked: bool) -> None:
    editor: TextInput = TextInput("anime title" * 5)
    editor.handle("select-all")
    active: Text = editor.render(12, masked=masked)
    inactive: Text = editor.render(12, masked=masked, focused=False)
    assert inactive.cell_len <= 12
    assert inactive.plain == ("•" * 12 if masked else editor.text[:12])
    assert not inactive.spans
    assert inactive.style == "gray"
    assert "anime" not in inactive.plain if masked else inactive.plain.startswith("anime")
    assert editor.selected
    assert editor.render(12, masked=masked) == active


@pytest.mark.parametrize("width", [12, 80, 120])
@pytest.mark.parametrize("masked", [False, True])
def test_block_cursor_styles_existing_characters_without_moving_text(width: int, masked: bool) -> None:
    editor: TextInput = TextInput("anime title")
    editor.handle("home")
    expected: str = "•" * len(editor.text) if masked else editor.text
    console: Console = Console(theme=BRAND_THEME)
    for position in range(len(editor.text)):
        rendered: Text = editor.render(width, masked=masked)
        assert rendered.plain == expected
        assert rendered.cell_len == len(expected)
        assert rendered.get_style_at_offset(console, position).reverse
        assert any(
            span.style == "reverse" and (span.start, span.end) == (position, position + 1) for span in rendered.spans
        )
        editor.handle("right")


@pytest.mark.parametrize("value", ["", "anime"])
@pytest.mark.parametrize("width", [1, 80])
def test_end_cursor_highlights_one_trailing_space(value: str, width: int) -> None:
    editor: TextInput = TextInput(value)
    rendered: Text = editor.render(width)
    assert rendered.plain == (value + " ")[-width:]
    assert any(
        span.style == "reverse" and (span.start, span.end) == (len(rendered) - 1, len(rendered))
        for span in rendered.spans
    )
    assert editor.render(80, focused=False).plain == value


@pytest.mark.parametrize("value", ["漢" * 20, "a\u0301" * 20])
@pytest.mark.parametrize("width", [2, 3, 12])
def test_narrow_cursor_highlights_a_whole_grapheme(value: str, width: int) -> None:
    editor: TextInput = TextInput(value)
    editor.handle("left")
    rendered: Text = editor.render(width)
    assert rendered.cell_len <= width
    assert not rendered.plain.startswith("\u0301")
    assert any(
        span.style == "reverse" and rendered.plain[span.start : span.end] in {"漢", "a\u0301"}
        for span in rendered.spans
    )


def test_typing_replaces_a_pristine_value_but_cursor_movement_preserves_it() -> None:
    editor: TextInput = TextInput("42", pristine=True)
    editor.handle("text:6")
    assert editor.text == "6"
    editor.reset("42", pristine=True)
    editor.handle("left")
    editor.handle("paste:0")
    assert editor.text == "402"


@pytest.mark.parametrize("text", ["home", "weekend", "turn left", "copyright"])
def test_pasted_text_is_never_interpreted_as_a_navigation_key(text: str) -> None:
    editor: TextInput = TextInput()
    editor.handle(f"paste:{text}")
    assert editor.text == text
