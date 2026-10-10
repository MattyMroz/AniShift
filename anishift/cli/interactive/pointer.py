"""Pointer gestures, click targets and painted-text selection shared by every panel view."""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import accumulate
from time import monotonic
from typing import Final

from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.style import Style
from rich.text import Text

from anishift.cli.interactive.anime_clipboard import copy_text
from anishift.text.graphemes import split_graphemes

# ── Constants ─────────────────────────────────────────────────────────────────

_INERT_META: Final[str] = "anishift_inert"
"""Style meta key marking painted interface, such as the brand, tabs or key hints, that a drag never selects."""

_INERT_STYLE: Final[Style] = Style(meta={_INERT_META: True})
"""Shared style tagging inert characters."""

_INERT_MASK: Final[str] = "\0"
"""Character standing in for an inert one while a frame is split into selectable runs."""

_SELECTABLE_RUN: Final[re.Pattern[str]] = re.compile(r"[^\0\n]+")
"""Maximal run of one line's characters between inert interface."""

_TARGET_META: Final[str] = "anishift_target"
"""Style meta key carrying the ``(kind, value)`` a click on painted text asks for, such as a row or a tab."""

_ROW_KINDS: Final[frozenset[str]] = frozenset({"row", "line"})
"""Target kinds that tag a whole painted line, wherever on it the click lands."""
CRUMB_SEPARATOR: Final[str] = " \u203a "
"""Separator between the levels of a breadcrumb."""

DOUBLE_CLICK_SECONDS: Final[float] = 0.4
"""Longest pause between two clicks on one screen row that still runs Enter on the cursor the first one set."""

SELECTION_STYLE: Final[str] = "reverse"
"""Style of selected text cells, which inverts each cell in its own color."""

SELECTION_GAP_STYLE: Final[str] = "#0a0d14 on #e2e7f5"
"""Flat style of a selected gap between columns, matching inverted plain text so every gap keeps one shade."""

COPY_KEYS: Final[frozenset[str]] = frozenset({"interrupt", "copy"})
"""Keys that copy a painted selection before the view handles them."""

_PRIVATE_USE: Final[str] = "Co"
"""Unicode category of private markers, such as the mascot anchor, that never reach copied text."""


@dataclass(frozen=True, slots=True, order=True)
class TextPoint:
    """Address a terminal cell in reading order."""

    row: int
    column: int


@dataclass(frozen=True, slots=True)
class TextCell:
    """Map one selectable grapheme to screen cells and Rich character offsets."""

    point: TextPoint
    width: int
    start: int
    end: int
    text: str


class ClickKind(StrEnum):
    """Name what a finished pointer gesture asks the view; a LINE is a text-screen row a double click never opens."""

    NONE = "none"
    ROW = "row"
    LINE = "line"
    OPEN = "open"
    TAB = "tab"
    CRUMB = "crumb"
    BACK = "back"
    FIELD = "field"


@dataclass(frozen=True, slots=True)
class Click:
    """Carry one pointer request with the list row, tab, breadcrumb level or text-field offset it names."""

    kind: ClickKind = ClickKind.NONE
    value: int = 0


@dataclass(frozen=True, slots=True)
class Gesture:
    """Report the selection after one event, the point a plain click released and a right-button press."""

    selection: tuple[TextPoint, TextPoint] | None
    click: TextPoint | None = None
    back: bool = False


class PointerGesture:
    """Tell a drag that selects painted text from a click, a double click on one row and a right press."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock: Callable[[], float] = clock
        self._anchor: TextPoint | None = None
        self._dragged: bool = False
        self._last: tuple[int, float] | None = None

    def reset(self) -> None:
        """Forget a press and a previous click whose coordinates no longer match the painted frame."""
        self._anchor = None
        self._dragged = False
        self._last = None

    def track(self, event: MouseEvent) -> Gesture | None:
        """Follow one event; ``None`` leaves the current selection unchanged."""
        point: TextPoint = TextPoint(event.position.y, event.position.x)
        if event.event_type is MouseEventType.MOUSE_DOWN and event.button is MouseButton.RIGHT:
            self.reset()
            return Gesture(None, back=True)
        if event.event_type is MouseEventType.MOUSE_DOWN and event.button is MouseButton.LEFT:
            self._anchor = point
            self._dragged = False
            return Gesture(None)
        anchor: TextPoint | None = self._anchor
        if anchor is None:
            return None
        if event.event_type is MouseEventType.MOUSE_MOVE and event.button is MouseButton.LEFT:
            self._dragged = self._dragged or point != anchor
            return Gesture((anchor, point))
        if event.event_type is not MouseEventType.MOUSE_UP:
            return None
        self._dragged = self._dragged or point != anchor
        self._anchor = None
        if self._dragged:
            self._last = None
        return Gesture((anchor, point)) if self._dragged else Gesture(None, point)

    def resolve(self, frame: Text, gesture: Gesture) -> Click:
        """Name what ``gesture`` asks of the view painted as ``frame``; a quick second click on one screen row opens."""
        if gesture.back:
            return Click(ClickKind.BACK)
        if gesture.click is None:
            return Click()
        target: Click = click_at(frame, gesture.click)
        now: float = self._clock()
        previous: tuple[int, float] | None = self._last
        self._last = (gesture.click.row, now) if target.kind is ClickKind.ROW else None
        if previous is None or previous[0] != gesture.click.row or now - previous[1] > DOUBLE_CLICK_SECONDS:
            return target
        if target.kind is not ClickKind.ROW:
            return target
        self._last = None
        return Click(ClickKind.OPEN)


class FrameSelection:
    """Select and copy the painted text of a whole frame and name the list row a click lands on."""

    def __init__(self, clipboard: Callable[[str], bool] = copy_text, clock: Callable[[], float] = monotonic) -> None:
        self._clipboard: Callable[[str], bool] = clipboard
        self._gesture: PointerGesture = PointerGesture(clock)
        self._selection: tuple[TextPoint, TextPoint] | None = None
        self._frame: Text = Text()
        self._view: tuple[object, ...] = ()
        self.notice: str = ""

    def paint(self, frame: Text, view: tuple[object, ...]) -> Text:
        """Highlight the selection on a new frame, dropping it when the view or its geometry changed."""
        if view != self._view:
            self.clear()
        self._view = view
        if self._selection is not None:
            paint_selection(frame, selected_cells(painted_cells(frame), self._selection))
        self._frame = frame
        return frame

    def mouse(self, event: MouseEvent) -> Click:
        """Follow a mouse event and name what a click, a double click or a right press asks of the view."""
        gesture: Gesture | None = self._gesture.track(event)
        if gesture is None:
            return Click()
        self.notice = ""
        self._selection = gesture.selection
        return self._gesture.resolve(self._frame, gesture)

    def copy(self, key: str) -> bool:
        """Copy the selection for a copy key; any other key drops it and is left to the view."""
        self.notice = ""
        if key not in COPY_KEYS:
            self._frame = Text()
            self.clear()
            return False
        value: str = selected_text(painted_cells(self._frame), self._selection)
        if not value:
            return False
        self.notice = "Skopiowano zaznaczenie" if self._clipboard(value) else "Nie udało się skopiować"
        return True

    def clear(self) -> None:
        """Drop the selection and any unfinished press."""
        self._selection = None
        self._gesture.reset()


def mark_row(content: Text, index: int, *, opens: bool = True) -> None:
    """Tag the line ``content`` ends with as row ``index``; a text-screen row (``opens=False``) never opens."""
    target: Click = Click(ClickKind.ROW if opens else ClickKind.LINE, index)
    mark_target(content, content.plain.rfind("\n") + 1, len(content), target)


def mark_inert(content: Text) -> Text:
    """Tag all of ``content`` as interface that a drag never selects or copies, keeping its click targets."""
    content.stylize(_INERT_STYLE, 0, len(content))
    return content


def mark_target(content: Text, start: int, end: int, target: Click) -> None:
    """Tag the characters ``start:end`` of ``content`` as the place a click asks for ``target``."""
    content.stylize(Style(meta={_TARGET_META: (target.kind.value, target.value)}), start, end)


def mark_crumbs(line: Text, parts: Sequence[str]) -> None:
    """Tag each breadcrumb level of ``parts`` painted on ``line`` before the current one with its index."""
    start: int = len(line.plain) - len(line.plain.lstrip())
    for level, part in enumerate(parts[:-1]):
        mark_target(line, start, min(start + len(part), len(line)), Click(ClickKind.CRUMB, level))
        start += len(part) + len(CRUMB_SEPARATOR)


def click_at(frame: Text, point: TextPoint) -> Click:
    """Return the row, target or text offset a click on a frame cell names; right of a field means its end."""
    lines: list[Text] = list(frame.split("\n", allow_blank=True))
    if not 0 <= point.row < len(lines):
        return Click()
    line: Text = lines[point.row]
    row: Click | None = _line_row(line)
    if row is not None:
        return row
    offset: int = character_offset(line.plain, point.column)
    beyond: Click = Click()
    for span in line.spans:
        target: object = span.style.meta.get(_TARGET_META) if isinstance(span.style, Style) else None
        if not isinstance(target, tuple) or offset < span.start:
            continue
        kind: ClickKind = ClickKind(target[0])
        if offset < span.end:
            return Click(kind, target[1] + (offset - span.start if kind is ClickKind.FIELD else 0))
        if kind is ClickKind.FIELD:
            beyond = Click(kind, target[1] + span.end - span.start)
    return beyond


def _line_row(line: Text) -> Click | None:
    for span in line.spans:
        target: object = span.style.meta.get(_TARGET_META) if isinstance(span.style, Style) else None
        if span.end > span.start and isinstance(target, tuple) and target[0] in _ROW_KINDS:
            return Click(ClickKind(target[0]), target[1])
    return None


def character_offset(value: str, column: int) -> int:
    """Return the character index where terminal cell ``column`` starts."""
    used: int = 0
    index: int = 0
    for grapheme in split_graphemes(value):
        if used >= column:
            break
        used += Text(grapheme).cell_len
        index += len(grapheme)
    return index


def text_cells(lines: Sequence[str], regions: Iterable[tuple[int, int, str]]) -> tuple[TextCell, ...]:
    """Map the graphemes of ``(row, column, text)`` regions painted on ``lines``, skipping private markers."""
    starts: list[int] = []
    offset: int = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    cells: list[TextCell] = []
    for row, column, value in sorted(regions):
        index: int = starts[row] + character_offset(lines[row], column)
        cell_column: int = column
        for grapheme in split_graphemes(value):
            width: int = Text(grapheme).cell_len
            if unicodedata.category(grapheme[0]) != _PRIVATE_USE:
                cells.append(TextCell(TextPoint(row, cell_column), width, index, index + len(grapheme), grapheme))
            cell_column += width
            index += len(grapheme)
    return tuple(cells)


def painted_cells(frame: Text) -> tuple[TextCell, ...]:
    """Map the painted runs of a frame between its padding and inert interface."""
    plain: str = frame.plain
    masked: list[str] = list(plain)
    for span in frame.spans:
        end: int = min(span.end, len(plain))
        if span.start < end and isinstance(span.style, Style) and span.style.meta.get(_INERT_META):
            masked[span.start : end] = _INERT_MASK * (end - span.start)
    lines: list[str] = plain.split("\n")
    starts: list[int] = list(accumulate((len(line) + 1 for line in lines), initial=0))
    regions: list[tuple[int, int, str]] = []
    for run in _SELECTABLE_RUN.finditer("".join(masked)):
        value: str = run.group().strip()
        if not value:
            continue
        start: int = run.end() - len(run.group().lstrip())
        row: int = bisect_right(starts, start) - 1
        regions.append((row, Text(lines[row][: start - starts[row]]).cell_len, value))
    return text_cells(lines, regions)


def selected_cells(cells: Sequence[TextCell], selection: tuple[TextPoint, TextPoint] | None) -> tuple[TextCell, ...]:
    """Return whole graphemes intersected by an inclusive reading-order selection."""
    if selection is None:
        return ()
    start, end = sorted(selection)
    return tuple(
        cell
        for cell in cells
        if cell.point <= end and TextPoint(cell.point.row, cell.point.column + cell.width) > start
    )


def paint_selection(text: Text, cells: Sequence[TextCell]) -> None:
    """Invert selected text in its own colors; paint two or more blanks, or blanks between regions of a row, flat."""
    plain: str = text.plain
    for index, cell in enumerate(cells):
        previous: TextCell | None = cells[index - 1] if index else None
        following: TextCell | None = cells[index + 1] if index + 1 < len(cells) else None
        gap: bool = _blank_pair(previous, cell) or _blank_pair(cell, following)
        text.stylize(SELECTION_GAP_STYLE if gap else SELECTION_STYLE, cell.start, cell.end)
        if previous is None or previous.point.row != cell.point.row or previous.end >= cell.start:
            continue
        if plain[previous.end : cell.start].isspace():
            text.stylize(SELECTION_GAP_STYLE, previous.end, cell.start)


def _blank_pair(first: TextCell | None, second: TextCell | None) -> bool:
    if first is None or second is None or not (first.text.isspace() and second.text.isspace()):
        return False
    return first.point.row == second.point.row and first.end == second.start


def selected_text(cells: Sequence[TextCell], selection: tuple[TextPoint, TextPoint] | None) -> str:
    """Copy the selected cells in reading order, joining separate regions of one row with a space."""
    lines: dict[int, list[str]] = {}
    previous: TextCell | None = None
    for cell in selected_cells(cells, selection):
        line: list[str] = lines.setdefault(cell.point.row, [])
        if previous is not None and previous.point.row == cell.point.row and previous.end != cell.start:
            line.append(" ")
        line.append(cell.text)
        previous = cell
    return "\n".join("".join(line).strip() for line in lines.values()).strip()
