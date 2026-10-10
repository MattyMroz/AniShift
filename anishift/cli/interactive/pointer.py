"""Pointer gestures, list-row hit tags and painted-text selection shared by every panel view."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.style import Style
from rich.text import Text

from anishift.cli.interactive.anime_clipboard import copy_text
from anishift.cli.interactive.anime_state import TextPoint
from anishift.text.graphemes import split_graphemes

# ── Constants ─────────────────────────────────────────────────────────────────

_ROW_META: Final[str] = "anishift_row"
"""Style meta key carrying the list index of a painted row."""

COPY_KEYS: Final[frozenset[str]] = frozenset({"interrupt", "copy"})
"""Keys that copy a painted selection before the view handles them."""

_PRIVATE_USE: Final[str] = "Co"
"""Unicode category of private markers, such as the mascot anchor, that never reach copied text."""


@dataclass(frozen=True, slots=True)
class TextCell:
    """Map one selectable grapheme to screen cells and Rich character offsets."""

    point: TextPoint
    width: int
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class Gesture:
    """Report the selection after one left-button event and the point a plain click released."""

    selection: tuple[TextPoint, TextPoint] | None
    click: TextPoint | None = None


class PointerGesture:
    """Tell a left-button drag that selects painted text from a click that only points at a row."""

    def __init__(self) -> None:
        self._anchor: TextPoint | None = None
        self._dragged: bool = False

    def reset(self) -> None:
        """Forget a press whose coordinates no longer match the painted frame."""
        self._anchor = None
        self._dragged = False

    def track(self, event: MouseEvent) -> Gesture | None:
        """Follow one event; ``None`` leaves the current selection unchanged."""
        point: TextPoint = TextPoint(event.position.y, event.position.x)
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
        return Gesture((anchor, point)) if self._dragged else Gesture(None, point)


class FrameSelection:
    """Select and copy the painted text of a whole frame and name the list row a click lands on."""

    def __init__(self, clipboard: Callable[[str], bool] = copy_text) -> None:
        self._clipboard: Callable[[str], bool] = clipboard
        self._gesture: PointerGesture = PointerGesture()
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
            for cell in selected_cells(painted_cells(frame), self._selection):
                frame.stylize("reverse", cell.start, cell.end)
        self._frame = frame
        return frame

    def mouse(self, event: MouseEvent) -> int | None:
        """Follow a left-button event and return the list row a plain click landed on."""
        gesture: Gesture | None = self._gesture.track(event)
        if gesture is None:
            return None
        self.notice = ""
        self._selection = gesture.selection
        return row_at(self._frame, gesture.click.row) if gesture.click is not None else None

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


def mark_row(content: Text, index: int) -> None:
    """Tag the line ``content`` currently ends with as the painted row of list item ``index``."""
    content.stylize(Style(meta={_ROW_META: index}), content.plain.rfind("\n") + 1, len(content))


def row_at(frame: Text, row: int) -> int | None:
    """Return the list item painted on a frame row, if that row belongs to one."""
    lines: list[Text] = list(frame.split("\n", allow_blank=True))
    return _line_row(lines[row]) if 0 <= row < len(lines) else None


def _line_row(line: Text) -> int | None:
    for span in line.spans:
        if span.end <= span.start or not isinstance(span.style, Style):
            continue
        index: object = span.style.meta.get(_ROW_META)
        if isinstance(index, int):
            return index
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
    """Map every painted line of a frame without its surrounding padding."""
    lines: list[str] = frame.plain.split("\n")
    regions: list[tuple[int, int, str]] = []
    for row, line in enumerate(lines):
        value: str = line.strip()
        if value:
            regions.append((row, Text(line[: len(line) - len(line.lstrip())]).cell_len, value))
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
