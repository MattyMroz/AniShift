from __future__ import annotations

import pytest
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

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
    assert "▌" in rendered.plain
    assert "secret" not in rendered.plain
    assert any(span.style == "reverse" for span in rendered.spans)


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
