"""The editor one ordered list is rearranged in, committed or rolled back whole."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.binding import Binding
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from anishift.tui.dialogs.base import DialogScreen, DialogSize
from anishift.tui.dialogs.select import NO_RESULTS_TEXT, PAGE_STEP, moved_position
from anishift.tui.strings import (
    DIALOG_CONFIRM_LABEL,
    DIALOG_DOWN_LABEL,
    DIALOG_FIRST_LABEL,
    DIALOG_LAST_LABEL,
    DIALOG_PAGE_DOWN_LABEL,
    DIALOG_PAGE_UP_LABEL,
    DIALOG_UP_LABEL,
    REORDER_ADD_HINT,
    REORDER_ADD_LABEL,
    REORDER_DELETE_PROMPT,
    REORDER_MOVE_DOWN_LABEL,
    REORDER_MOVE_UP_LABEL,
    REORDER_NOTHING_TO_ADD,
    REORDER_ORDER_HINT,
    REORDER_REMOVE_LABEL,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.app import ComposeResult
    from textual.binding import BindingType

__all__ = [
    "ADD_HINT",
    "ADD_KEY",
    "NOTHING_TO_ADD_TEXT",
    "ORDER_HINT",
    "ReorderDialog",
    "delete_prompt",
    "moved_items",
]

# ── Constants ──────────────────────────────────────────────────────────────

ADD_KEY: Final[str] = "a"
"""Key that starts the add mode, and leaves it again."""

ORDER_HINT: Final[str] = REORDER_ORDER_HINT
"""Hint shown while the order itself is being edited."""

ADD_HINT: Final[str] = REORDER_ADD_HINT
"""Hint shown while a member is being added."""

NOTHING_TO_ADD_TEXT: Final[str] = REORDER_NOTHING_TO_ADD
"""Reason shown when every candidate is already a member."""

_LIST_ID: Final[str] = "reorder-list"
"""Id of the one list this dialog edits."""

_HINT_ID: Final[str] = "reorder-hint"
"""Id of the row telling which keys the current mode answers to."""

_MESSAGE_ID: Final[str] = "reorder-message"
"""Id of the row holding a refusal or a pending removal."""

_ERROR_CLASS: Final[str] = "dialog-error"
"""Class marking the message row while it holds a refusal."""


def delete_prompt(item: str) -> str:
    """Reason shown while the removal of *item* waits for its second key."""
    return REORDER_DELETE_PROMPT.format(item=item)


def moved_items(items: Sequence[str], position: int, delta: int) -> tuple[str, ...]:
    """Members after moving the one at *position* by *delta*, unchanged when it would leave."""
    target: int = position + delta
    if not 0 <= position < len(items) or not 0 <= target < len(items):
        return tuple(items)
    moved: list[str] = list(items)
    moved.insert(target, moved.pop(position))
    return tuple(moved)


class ReorderDialog(DialogScreen[tuple[str, ...] | None]):
    """Editor of one ordered list, committed or rolled back as a whole."""

    AUTO_FOCUS: ClassVar[str | None] = f"#{_LIST_ID}"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "cursor_up", DIALOG_UP_LABEL, show=False, priority=True),
        Binding("down", "cursor_down", DIALOG_DOWN_LABEL, show=False, priority=True),
        Binding("pageup", "page_up", DIALOG_PAGE_UP_LABEL, show=False, priority=True),
        Binding("pagedown", "page_down", DIALOG_PAGE_DOWN_LABEL, show=False, priority=True),
        Binding("home", "first", DIALOG_FIRST_LABEL, show=False, priority=True),
        Binding("end", "last", DIALOG_LAST_LABEL, show=False, priority=True),
        Binding("shift+up", "move_up", REORDER_MOVE_UP_LABEL, show=False, priority=True),
        Binding("shift+down", "move_down", REORDER_MOVE_DOWN_LABEL, show=False, priority=True),
        Binding("delete", "remove", REORDER_REMOVE_LABEL, show=False, priority=True),
        Binding(ADD_KEY, "add", REORDER_ADD_LABEL, show=False, priority=True),
        Binding("enter", "confirm", DIALOG_CONFIRM_LABEL, show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        title: str,
        items: Sequence[str],
        candidates: Sequence[str] = (),
        size: DialogSize = DialogSize.MEDIUM,
    ) -> None:
        """Edit the order of *items*, offering *candidates* to the add mode."""
        super().__init__(title=title, size=size)
        self._members: tuple[str, ...] = tuple(items)
        self._candidates: tuple[str, ...] = tuple(candidates)
        self._adding: bool = False
        self._pending_removal: str | None = None
        self._cursor: int = 0
        self._list: OptionList = OptionList(id=_LIST_ID, markup=False)
        self._hint: Static = Static(ORDER_HINT, id=_HINT_ID, classes="dialog-hint")
        self._message: Static = Static(id=_MESSAGE_ID, classes="dialog-detail")

    @property
    def members(self) -> tuple[str, ...]:
        """Order edited so far; the caller's list only changes on a commit."""
        return self._members

    def compose_dialog(self) -> ComposeResult:
        """Draw the edited list, the keys of the current mode and its messages."""
        yield self._list
        yield self._hint
        yield self._message

    def on_mount(self) -> None:
        """Place the panel, then show the order the caller handed in."""
        super().on_mount()
        self._show()

    def cancel_result(self) -> tuple[str, ...] | None:
        """A cancelled reorder rolls the whole list back."""
        return None

    def action_cancel(self) -> None:
        """Leave the add mode, or roll the whole list back."""
        if self._adding:
            self._adding = False
            self._show()
            return
        super().action_cancel()

    def action_cursor_up(self) -> None:
        """Move the cursor one row up, wrapping at the first row."""
        self._move_cursor(-1, wrap=True)

    def action_cursor_down(self) -> None:
        """Move the cursor one row down, wrapping at the last row."""
        self._move_cursor(1, wrap=True)

    def action_page_up(self) -> None:
        """Move the cursor one page up, stopping at the first row."""
        self._move_cursor(-PAGE_STEP, wrap=False)

    def action_page_down(self) -> None:
        """Move the cursor one page down, stopping at the last row."""
        self._move_cursor(PAGE_STEP, wrap=False)

    def action_first(self) -> None:
        """Move the cursor to the first row."""
        self._move_cursor(-len(self._rows()), wrap=False)

    def action_last(self) -> None:
        """Move the cursor to the last row."""
        self._move_cursor(len(self._rows()), wrap=False)

    def action_move_up(self) -> None:
        """Move the highlighted member one place up."""
        self._move_member(-1)

    def action_move_down(self) -> None:
        """Move the highlighted member one place down."""
        self._move_member(1)

    def action_remove(self) -> None:
        """Take the highlighted member out, once the removal was confirmed."""
        if self._adding:
            return
        item: str | None = self._highlighted()
        if item is None:
            return
        if self._pending_removal != item:
            self._pending_removal = item
            self._show_message(delete_prompt(item), refused=False)
            return
        self._members = tuple(member for member in self._members if member != item)
        self._pending_removal = None
        self._cursor = min(self._cursor, max(len(self._members) - 1, 0))
        self._show()

    def action_add(self) -> None:
        """Offer the candidates that are not members yet."""
        if self._adding:
            self._adding = False
            self._show()
            return
        if not self._available():
            self._show_message(NOTHING_TO_ADD_TEXT, refused=True)
            return
        self._adding = True
        self._cursor = 0
        self._show()

    def action_confirm(self) -> None:
        """Add the highlighted candidate, or commit the whole order."""
        if not self._adding:
            self.dismiss(self._members)
            return
        chosen: str | None = self._highlighted()
        if chosen is None:
            return
        self._members = (*self._members, chosen)
        self._adding = False
        self._cursor = len(self._members) - 1
        self._show()

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Take the row the mouse picked as the current one."""
        event.stop()
        self._cursor = event.option_index
        self._show_cursor()

    def _available(self) -> tuple[str, ...]:
        """Candidates the caller offered that are not members yet."""
        return tuple(candidate for candidate in self._candidates if candidate not in self._members)

    def _rows(self) -> tuple[str, ...]:
        """Rows of the current mode: the members, or the free candidates."""
        return self._available() if self._adding else self._members

    def _highlighted(self) -> str | None:
        """Row the cursor stopped on, or ``None`` when the list is empty."""
        rows: tuple[str, ...] = self._rows()
        return rows[self._cursor] if 0 <= self._cursor < len(rows) else None

    def _move_cursor(self, delta: int, *, wrap: bool) -> None:
        """Move the cursor *delta* rows, wrapping only when asked."""
        rows: tuple[str, ...] = self._rows()
        if not rows:
            return
        self._pending_removal = None
        self._cursor = moved_position(self._cursor, delta, len(rows), wrap=wrap)
        self._show_message("", refused=False)
        self._show_cursor()

    def _move_member(self, delta: int) -> None:
        """Move the highlighted member *delta* places inside the order."""
        if self._adding:
            return
        moved: tuple[str, ...] = moved_items(self._members, self._cursor, delta)
        if moved == self._members:
            return
        self._members = moved
        self._pending_removal = None
        self._cursor += delta
        self._show()

    def _show(self) -> None:
        """Redraw the rows of the current mode and its hint."""
        rows: tuple[str, ...] = self._rows()
        labels: list[str] = list(rows) if rows else [NO_RESULTS_TEXT]
        self._list.set_options([Option(label, disabled=not rows) for label in labels])
        self._hint.update(ADD_HINT if self._adding else ORDER_HINT)
        self._show_message("", refused=False)
        self._show_cursor()

    def _show_cursor(self) -> None:
        """Put the list cursor where this dialog holds it."""
        if not self._rows():
            self._list.highlighted = None
            return
        self._list.highlighted = self._cursor
        self._list.scroll_to_highlight()

    def _show_message(self, text: str, *, refused: bool) -> None:
        """Show one message under the list, marking a refusal as such."""
        self._message.set_class(refused, _ERROR_CLASS)
        self._message.update(text)
