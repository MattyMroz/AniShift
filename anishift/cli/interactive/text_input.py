"""Shared single-line editing, selection and cursor rendering for every text field."""

from __future__ import annotations

from typing import Final

from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.selection import SelectionState
from rich.cells import get_character_cell_size
from rich.text import Text

__all__ = ["EDIT_KEYS", "TextInput", "is_edit_key"]

# ── Constants ─────────────────────────────────────────────────────────────────

EDIT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "left",
        "right",
        "home",
        "end",
        "backspace",
        "delete",
        "space",
        "ctrl-left",
        "ctrl-right",
        "ctrl-home",
        "ctrl-end",
        "ctrl-backspace",
        "ctrl-delete",
        "shift-left",
        "shift-right",
        "shift-home",
        "shift-end",
        "ctrl-shift-left",
        "ctrl-shift-right",
        "ctrl-shift-home",
        "ctrl-shift-end",
        "select-all",
        "cut",
        "copy",
        "paste",
        "undo",
        "redo",
    }
)
"""Normalized editing keys shared by all fields and delayed settings saves."""


def is_edit_key(key: str) -> bool:
    """Whether a normalized key belongs to single-line editing."""
    return key in EDIT_KEYS or key.startswith(("text:", "paste:"))


class TextInput:
    """One text buffer with ordinary editing and an optional replace-on-first-type value."""

    def __init__(self, text: str = "", *, pristine: bool = False) -> None:
        self._buffer: Buffer = Buffer(document=Document(text, len(text)), multiline=False)
        self.pristine: bool = pristine

    @property
    def text(self) -> str:
        """Return the complete unmasked value."""
        return self._buffer.text

    @property
    def cursor(self) -> int:
        """Return the cursor's character offset."""
        return self._buffer.cursor_position

    @property
    def selected(self) -> bool:
        """Whether a nonempty range is selected."""
        start, end = self._buffer.document.selection_range()
        return self._buffer.selection_state is not None and start != end

    def reset(self, text: str = "", *, pristine: bool = False) -> None:
        """Replace the field value and discard selection and undo history."""
        self._buffer.reset(document=Document(text, len(text)))
        self.pristine = pristine

    def handle(self, key: str) -> bool:
        """Apply one key and report consumption; unselected Ctrl+C remains an interrupt."""
        if key == "interrupt":
            if not self.selected:
                return False
            key = "copy"
        if not is_edit_key(key):
            return False
        if key in EDIT_KEYS and key.endswith(("left", "right", "home", "end")):
            self._move(key)
            return True
        if key in {"copy", "cut", "select-all", "undo", "redo"}:
            self._command(key)
            return True
        if key in {"backspace", "delete", "ctrl-backspace", "ctrl-delete"}:
            self._delete(key)
            return True
        text: str = (
            get_app().clipboard.get_data().text if key == "paste" else " " if key == "space" else key.split(":", 1)[1]
        )
        self._insert("".join(character for character in text if character.isprintable()))
        return True

    def render(self, width: int, *, masked: bool = False) -> Text:
        """Render the visible value with its cursor and highlighted selection."""
        value: str = "•" * len(self.text) if masked else self.text
        line: Text = Text(value, style="white_bold")
        if self.selected:
            start, end = self._buffer.document.selection_range()
            line.stylize("reverse", start, end)
        result: Text = line[: self.cursor] + Text("▌", style="brand_accent") + line[self.cursor :]
        cursor_cells: int = Text(value[: self.cursor]).cell_len
        offset: int = max(cursor_cells - max(width - 2, 0), 0)
        if offset:
            result = _visible_tail(result, offset)
        result.truncate(max(width, 1), overflow="crop")
        return result

    def _move(self, key: str) -> None:
        selecting: bool = "shift-" in key
        document: Document = self._buffer.document
        if selecting and self._buffer.selection_state is None:
            self._buffer.selection_state = SelectionState(self.cursor)
        if key.endswith("home"):
            target: int = 0
        elif key.endswith("end"):
            target = len(self.text)
        elif key.startswith("ctrl-"):
            delta: int = (
                (document.find_previous_word_beginning() or -self.cursor)
                if key.endswith("left")
                else (document.find_next_word_beginning() or len(self.text) - self.cursor)
            )
            target = self.cursor + delta
        elif self.selected and not selecting:
            start, end = document.selection_range()
            target = start if key.endswith("left") else end
        else:
            target = self.cursor + (-1 if key.endswith("left") else 1)
        self._buffer.cursor_position = min(max(target, 0), len(self.text))
        if not selecting:
            self._buffer.selection_state = None
        self.pristine = False

    def _delete(self, key: str) -> None:
        self._buffer.save_to_undo_stack()
        self.pristine = False
        if self.selected:
            self._buffer.cut_selection()
            return
        previous: bool = key.endswith("backspace")
        count: int = 1
        if key.startswith("ctrl-"):
            document: Document = self._buffer.document
            count = (
                -(document.find_previous_word_beginning() or -self.cursor)
                if previous
                else (document.find_next_word_ending() or len(self.text) - self.cursor)
            )
        if previous:
            self._buffer.delete_before_cursor(count)
        else:
            self._buffer.delete(count)

    def _insert(self, text: str) -> None:
        if not text:
            return
        self._buffer.save_to_undo_stack()
        if self.pristine:
            self._buffer.document = Document()
        elif self.selected:
            self._buffer.cut_selection()
        self.pristine = False
        self._buffer.insert_text(text)

    def _command(self, key: str) -> None:
        self.pristine = False
        if key == "select-all":
            self._buffer.selection_state = SelectionState(0)
            self._buffer.cursor_position = len(self.text)
        elif key == "undo":
            self._buffer.undo()
        elif key == "redo":
            self._buffer.redo()
        elif self.selected:
            selection: SelectionState | None = self._buffer.selection_state
            if key == "cut":
                self._buffer.save_to_undo_stack()
            get_app().clipboard.set_data(
                self._buffer.cut_selection() if key == "cut" else self._buffer.copy_selection()
            )
            if key == "copy":
                self._buffer.selection_state = selection


def _visible_tail(text: Text, cells: int) -> Text:
    index: int = 0
    used: int = 0
    while index < len(text) and used < cells:
        used += get_character_cell_size(text.plain[index])
        index += 1
    return text[index:]
