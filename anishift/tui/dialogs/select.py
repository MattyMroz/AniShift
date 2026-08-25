"""The one list selector every AniShift domain picks a value with."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.binding import Binding
from textual.fuzzy import FuzzySearch
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from anishift.tui.commands.spec import key_display
from anishift.tui.dialogs.base import DialogScreen, DialogSize
from anishift.tui.strings import (
    DIALOG_CONFIRM_LABEL,
    DIALOG_DOWN_LABEL,
    DIALOG_FIRST_LABEL,
    DIALOG_LAST_LABEL,
    DIALOG_PAGE_DOWN_LABEL,
    DIALOG_PAGE_UP_LABEL,
    DIALOG_UP_LABEL,
    SELECT_DISABLED_OPTION,
    SELECT_FILTER_PLACEHOLDER,
    SELECT_NO_RESULTS,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from textual.app import ComposeResult
    from textual.binding import BindingType

__all__ = [
    "CHECKED_MARKER",
    "CURRENT_MARKER",
    "DISABLED_OPTION_TEXT",
    "FILTER_PLACEHOLDER",
    "NO_RESULTS_TEXT",
    "PAGE_STEP",
    "SelectAction",
    "SelectDialog",
    "SelectOption",
    "SelectOutcome",
    "SelectOutcomeKind",
    "SelectRow",
    "moved_position",
    "select_rows",
]

# ── Constants ──────────────────────────────────────────────────────────────

NO_RESULTS_TEXT: Final[str] = SELECT_NO_RESULTS
"""Row the list shows when the filter matches nothing; the dialog stays closable."""

DISABLED_OPTION_TEXT: Final[str] = SELECT_DISABLED_OPTION
"""Message the dialog shows instead of confirming a disabled row."""

FILTER_PLACEHOLDER: Final[str] = SELECT_FILTER_PLACEHOLDER
"""Hint the empty filter box shows."""

CURRENT_MARKER: Final[str] = "●"
"""Marker of the value the caller currently holds, independent of the cursor."""

CHECKED_MARKER: Final[str] = "✓"
"""Marker of a row picked in the multi mode."""

PAGE_STEP: Final[int] = 10
"""Rows one page key moves the cursor by."""

_EMPTY_MARKER: Final[str] = " "
"""Marker column of a row that is neither current nor picked."""

_LABEL_GAP: Final[str] = "  "
"""Separator between the title of a row and its footer."""

_ACTION_JOINER: Final[str] = " · "
"""Separator between the extra actions the dialog lists."""

_PREFIX_BOOST: Final[float] = 2.0
"""Factor lifting a title that starts with the query above a scattered match."""

_DESCRIPTION_WEIGHT: Final[float] = 0.5
"""Factor keeping a description match below any title match."""

_SPACE_KEY: Final[str] = "space"
"""Key the multi mode toggles a row with, taken back from the filter box."""

_FILTER_ID: Final[str] = "select-filter"
"""Id of the offline filter box."""

_LIST_ID: Final[str] = "select-list"
"""Id of the scrolling row list."""

_DETAIL_ID: Final[str] = "select-detail"
"""Id of the one row that describes the highlighted option."""

_ACTIONS_ID: Final[str] = "select-actions"
"""Id of the row listing the extra actions of the dialog."""

_ERROR_CLASS: Final[str] = "dialog-error"
"""Class marking the detail row while it holds a refusal instead of a description."""

_FUZZY: Final[FuzzySearch] = FuzzySearch()
"""Shared cached matcher; it holds queries only, never a caller's values."""


@dataclass(frozen=True, slots=True)
class SelectOption[T]:
    """One offered value and everything a row shows about it.

    Attributes:
        value: What the outcome carries back when this row is chosen.
        title: Text of the row itself.
        description: Sentence shown for the highlighted row only.
        footer: Short trailing text of the row, such as the keys of a command.
        category: Heading this row is grouped under while no filter is typed.
        disabled: Whether the row may be chosen; the caller owns the reason.
    """

    value: T
    title: str
    description: str = ""
    footer: str = ""
    category: str = ""
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class SelectAction:
    """One extra decision the dialog offers next to picking a row.

    Attributes:
        name: Identity the outcome carries back to the caller.
        key: Textual key name that runs the action.
        label: Short text the action row shows.
    """

    name: str
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class SelectRow:
    """One rendered row of the list.

    Attributes:
        label: Text the list shows for this row.
        index: Option this row stands for, or ``None`` for a heading or the empty-result row.
    """

    label: str
    index: int | None = None


class SelectOutcomeKind(StrEnum):
    """What kind of decision one outcome carries."""

    SINGLE = "single"
    MULTI = "multi"
    ACTION = "action"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SelectOutcome[T]:
    """What one select dialog decided; the caller performs the effect.

    Attributes:
        kind: Which decision this outcome carries.
        values: The picked value for single or action outcomes, the whole set for multi.
        action: Name of the extra action, empty for every other kind.
    """

    kind: SelectOutcomeKind
    values: tuple[T, ...] = ()
    action: str = ""

    @classmethod
    def single(cls, value: T) -> SelectOutcome[T]:
        """One row was confirmed."""
        return cls(kind=SelectOutcomeKind.SINGLE, values=(value,))

    @classmethod
    def multi(cls, values: Sequence[T]) -> SelectOutcome[T]:
        """A whole set of rows was confirmed."""
        return cls(kind=SelectOutcomeKind.MULTI, values=tuple(values))

    @classmethod
    def acted(cls, name: str, value: T | None = None) -> SelectOutcome[T]:
        """An extra action ran, optionally on the highlighted value."""
        return cls(kind=SelectOutcomeKind.ACTION, values=() if value is None else (value,), action=name)

    @classmethod
    def cancelled(cls) -> SelectOutcome[T]:
        """The dialog was left without a decision."""
        return cls(kind=SelectOutcomeKind.CANCELLED)

    @property
    def value(self) -> T | None:
        """The single chosen value, or ``None`` when the outcome carries none."""
        return self.values[0] if self.values else None


def moved_position(position: int, delta: int, count: int, *, wrap: bool) -> int:
    """Cursor position after moving *delta* places among *count* places."""
    if count <= 0:
        return 0
    moved: int = position + delta
    if wrap:
        return moved % count
    return max(0, min(moved, count - 1))


def select_rows[T](
    options: Sequence[SelectOption[T]],
    *,
    query: str = "",
    current: T | None = None,
    checked: frozenset[int] | None = None,
) -> tuple[SelectRow, ...]:
    """Rows *options* shows for *query*: grouped by category when empty, flat when typed."""
    matched: tuple[tuple[int, SelectOption[T]], ...] = _matched(options, query)
    if not matched:
        return (SelectRow(label=NO_RESULTS_TEXT),)
    rows: list[SelectRow] = []
    heading: str = ""
    grouped: bool = not query.strip()
    for index, option in matched:
        if grouped and option.category and option.category != heading:
            heading = option.category
            rows.append(SelectRow(label=option.category))
        rows.append(SelectRow(label=_label(option, index, current=current, checked=checked), index=index))
    return tuple(rows)


def _matched[T](options: Sequence[SelectOption[T]], query: str) -> tuple[tuple[int, SelectOption[T]], ...]:
    """Options that answer *query*, best match first, with their own index."""
    normalized: str = query.strip().casefold()
    if not normalized:
        return tuple(enumerate(options))
    scored: list[tuple[int, SelectOption[T], float]] = [
        (index, option, _score(option, normalized)) for index, option in enumerate(options)
    ]
    ranked: list[tuple[int, SelectOption[T], float]] = sorted(
        (entry for entry in scored if entry[2] > 0.0),
        key=_best_first,
    )
    return tuple((index, option) for index, option, _ in ranked)


def _best_first[T](scored: tuple[int, SelectOption[T], float]) -> float:
    """Sort key putting the best score first and keeping the given order."""
    return -scored[2]


def _score[T](option: SelectOption[T], query: str) -> float:
    """Score one option against *query* over its title and its description."""
    title: str = option.title.casefold()
    score: float
    score, _ = _FUZZY.match(query, title)
    if score > 0.0 and title.startswith(query):
        score *= _PREFIX_BOOST
    described: float
    described, _ = _FUZZY.match(query, option.description.casefold())
    return max(score, described * _DESCRIPTION_WEIGHT)


def _label[T](
    option: SelectOption[T],
    index: int,
    *,
    current: T | None,
    checked: frozenset[int] | None,
) -> str:
    """Text one option shows, marker column first."""
    marker: str = _marker(option, index, current=current, checked=checked)
    body: str = option.title if not option.footer else f"{option.title}{_LABEL_GAP}{option.footer}"
    return f"{marker} {body}"


def _marker[T](
    option: SelectOption[T],
    index: int,
    *,
    current: T | None,
    checked: frozenset[int] | None,
) -> str:
    """Marker column of one row, never derived from the cursor."""
    if checked is not None:
        return CHECKED_MARKER if index in checked else _EMPTY_MARKER
    if current is not None and option.value == current:
        return CURRENT_MARKER
    return _EMPTY_MARKER


class _FilterInput(Input):
    """Filter box that can leave one printable key to the dialog around it."""

    def __init__(self, *, reserve_space: bool, placeholder: str, widget_id: str) -> None:
        """Build the filter box, optionally giving ``Space`` back to the dialog."""
        super().__init__(placeholder=placeholder, id=widget_id)
        self._reserve_space: bool = reserve_space

    def check_consume_key(self, key: str, character: str | None) -> bool:
        """Leave ``Space`` to the dialog while the multi mode toggles rows with it."""
        if self._reserve_space and key == _SPACE_KEY:
            return False
        return super().check_consume_key(key, character)


class SelectDialog[T](DialogScreen[SelectOutcome[T]]):
    """The only list selector of the application.

    ``on_highlight`` fires for the initial highlight, every cursor move and
    every filter change; never for a heading or the empty-result row.
    """

    AUTO_FOCUS: ClassVar[str | None] = f"#{_FILTER_ID}"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "cursor_up", DIALOG_UP_LABEL, show=False, priority=True),
        Binding("down", "cursor_down", DIALOG_DOWN_LABEL, show=False, priority=True),
        Binding("pageup", "page_up", DIALOG_PAGE_UP_LABEL, show=False, priority=True),
        Binding("pagedown", "page_down", DIALOG_PAGE_DOWN_LABEL, show=False, priority=True),
        Binding("home", "first", DIALOG_FIRST_LABEL, show=False, priority=True),
        Binding("end", "last", DIALOG_LAST_LABEL, show=False, priority=True),
        Binding("enter", "confirm", DIALOG_CONFIRM_LABEL, show=False, priority=True),
    ]

    def __init__(  # noqa: PLR0913 - one selector covers every domain, so its whole contract stays explicit
        self,
        *,
        title: str,
        options: Sequence[SelectOption[T]],
        current: T | None = None,
        multi: bool = False,
        selected: Sequence[int] = (),
        actions: Sequence[SelectAction] = (),
        initial_highlight: int | None = None,
        on_highlight: Callable[[T], None] | None = None,
        placeholder: str = FILTER_PLACEHOLDER,
        size: DialogSize = DialogSize.LARGE,
    ) -> None:
        """Offer *options*, marking *current* and starting at *initial_highlight*."""
        super().__init__(title=title, size=size)
        self._options: tuple[SelectOption[T], ...] = tuple(options)
        self._current: T | None = current
        self._multi: bool = multi
        self._selected: set[int] = {index for index in selected if 0 <= index < len(self._options)}
        self._actions: tuple[SelectAction, ...] = tuple(actions)
        self._initial_highlight: int | None = initial_highlight
        self._on_highlight: Callable[[T], None] | None = on_highlight
        self._announced: int | None = None
        self._rows: tuple[SelectRow, ...] = ()
        self._cursor: int = 0
        self._filter: _FilterInput = _FilterInput(
            reserve_space=multi,
            placeholder=placeholder,
            widget_id=_FILTER_ID,
        )
        self._list: OptionList = OptionList(id=_LIST_ID, markup=False)
        self._detail: Static = Static(id=_DETAIL_ID, classes="dialog-detail")
        self._action_row: Static = Static(self._actions_text(), id=_ACTIONS_ID, classes="dialog-hint")
        self._bind_extra_keys()

    def compose_dialog(self) -> ComposeResult:
        """Draw the filter box, the list, the detail row and the action row."""
        yield self._filter
        yield self._list
        yield self._detail
        if self._actions:
            yield self._action_row

    def on_mount(self) -> None:
        """Place the panel, then show the rows starting at the requested one."""
        super().on_mount()
        self._rebuild()
        self._cursor = self._starting_cursor()
        self._sync_cursor()

    def cancel_result(self) -> SelectOutcome[T]:
        """A cancelled selector decided nothing at all."""
        outcome: SelectOutcome[T] = SelectOutcome.cancelled()
        return outcome

    @on(Input.Changed)
    def _on_filter_changed(self, event: Input.Changed) -> None:
        """Filter offline and move the cursor to the first row that survived."""
        event.stop()
        self._rebuild()
        self._cursor = self._first_selectable()
        self._sync_cursor()

    @on(OptionList.OptionSelected)
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Confirm the row the mouse picked."""
        event.stop()
        self._cursor = event.option_index
        self._sync_cursor()
        self.action_confirm()

    def action_cursor_up(self) -> None:
        """Move one row up, wrapping at the first row."""
        self._move(-1, wrap=True)

    def action_cursor_down(self) -> None:
        """Move one row down, wrapping at the last row."""
        self._move(1, wrap=True)

    def action_page_up(self) -> None:
        """Move one page up, stopping at the first row."""
        self._move(-PAGE_STEP, wrap=False)

    def action_page_down(self) -> None:
        """Move one page down, stopping at the last row."""
        self._move(PAGE_STEP, wrap=False)

    def action_first(self) -> None:
        """Move to the first row."""
        self._move(-len(self._rows), wrap=False)

    def action_last(self) -> None:
        """Move to the last row."""
        self._move(len(self._rows), wrap=False)

    def action_toggle_row(self) -> None:
        """Add the highlighted row to the multi selection, or take it out."""
        index: int | None = self._highlighted_index()
        option: SelectOption[T] | None = self._highlighted()
        if index is None or option is None or option.disabled:
            self._refuse(option)
            return
        self._selected.symmetric_difference_update({index})
        cursor: int = self._cursor
        self._rebuild()
        self._cursor = cursor
        self._sync_cursor()

    def action_confirm(self) -> None:
        """Hand back the decision, but never a row the caller disabled."""
        if self._multi:
            self.dismiss(SelectOutcome.multi([self._options[index].value for index in sorted(self._selected)]))
            return
        option: SelectOption[T] | None = self._highlighted()
        if option is None or option.disabled:
            self._refuse(option)
            return
        self.dismiss(SelectOutcome.single(option.value))

    def action_invoke(self, name: str) -> None:
        """Hand back one extra action, together with the highlighted value."""
        option: SelectOption[T] | None = self._highlighted()
        self.dismiss(SelectOutcome.acted(name, None if option is None else option.value))

    def _bind_extra_keys(self) -> None:
        """Claim the multi toggle and every action key before the filter box."""
        if self._multi:
            self._bindings.bind(_SPACE_KEY, "toggle_row", show=False, priority=True)
        for action in self._actions:
            self._bindings.bind(action.key, f'invoke("{action.name}")', show=False, priority=True)

    def _actions_text(self) -> str:
        """Row listing the keys of the extra actions the dialog offers."""
        return _ACTION_JOINER.join(f"{key_display(action.key)} {action.label}" for action in self._actions)

    def _rebuild(self) -> None:
        """Recompute the rows for the current filter, markers included."""
        self._rows = select_rows(
            self._options,
            query=self._filter.value,
            current=self._current,
            checked=frozenset(self._selected) if self._multi else None,
        )
        self._list.set_options([Option(row.label, disabled=self._row_is_dead(row)) for row in self._rows])

    def _row_is_dead(self, row: SelectRow) -> bool:
        """Whether a row is a heading, a placeholder or an option the caller disabled."""
        return row.index is None or self._options[row.index].disabled

    def _selectable(self) -> tuple[int, ...]:
        """Rows a cursor may stop on, headings and placeholders excluded."""
        return tuple(index for index, row in enumerate(self._rows) if row.index is not None)

    def _first_selectable(self) -> int:
        """First row a cursor may stop on, or zero when there is none."""
        return next(iter(self._selectable()), 0)

    def _starting_cursor(self) -> int:
        """Row the dialog opens on: the requested one, else the current value."""
        wanted: int | None = self._initial_highlight
        if wanted is None and self._current is not None:
            wanted = next(
                (index for index, option in enumerate(self._options) if option.value == self._current),
                None,
            )
        if wanted is None:
            return self._first_selectable()
        return next(
            (index for index, row in enumerate(self._rows) if row.index == wanted),
            self._first_selectable(),
        )

    def _move(self, delta: int, *, wrap: bool) -> None:
        """Move the cursor *delta* selectable rows, wrapping only when asked."""
        places: tuple[int, ...] = self._selectable()
        if not places:
            return
        position: int = places.index(self._cursor) if self._cursor in places else 0
        self._cursor = places[moved_position(position, delta, len(places), wrap=wrap)]
        self._sync_cursor()

    def _sync_cursor(self) -> None:
        """Show the cursor on the list, describe its row and announce the option."""
        self._detail.set_class(False, _ERROR_CLASS)
        option: SelectOption[T] | None = self._highlighted()
        if option is None:
            self._list.highlighted = None
            self._detail.update("")
            return
        self._list.highlighted = self._cursor
        self._list.scroll_to_highlight()
        self._detail.update(option.description)
        self._announce(option)

    def _announce(self, option: SelectOption[T]) -> None:
        """Tell a previewing caller which option the cursor rests on now."""
        index: int | None = self._highlighted_index()
        if self._on_highlight is None or index == self._announced:
            return
        self._announced = index
        self._on_highlight(option.value)

    def _highlighted(self) -> SelectOption[T] | None:
        """Option the cursor stopped on, or ``None`` on a heading or a placeholder."""
        index: int | None = self._highlighted_index()
        return None if index is None else self._options[index]

    def _highlighted_index(self) -> int | None:
        """Offered option the cursor stopped on, or ``None`` off any real row."""
        if not 0 <= self._cursor < len(self._rows):
            return None
        return self._rows[self._cursor].index

    def _refuse(self, option: SelectOption[T] | None) -> None:
        """Keep the dialog open and say why the row was not accepted."""
        if option is None:
            return
        self._detail.set_class(True, _ERROR_CLASS)
        self._detail.update(DISABLED_OPTION_TEXT)
