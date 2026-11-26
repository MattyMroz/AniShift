"""Place one native image in a Prompt Toolkit frame, so the frame's own write draws it and erases what it left."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.utils import get_cwidth

__all__ = ["Slot", "image_write", "raster_frame"]

# ── Constants ─────────────────────────────────────────────────────────────────

_KEPT: Final[str] = " fg:ansidefault"
"""Default foreground, invisible on a blank, which Prompt Toolkit counts as content and never trims from a line end."""

_SLOT_STYLE: Final[str] = f"class:raster-slot{_KEPT}"
"""Style of the blanks under the image: no frame uses it, so Prompt Toolkit never rewrites them or trims them."""

_RELEASE_STYLE: Final[str] = f" class:raster-release{_KEPT}"
"""Style added to blanks the previous image covered, so Prompt Toolkit writes them instead of trimming the line."""

_CARRIER_STYLES: Final[tuple[str, str]] = (" class:raster-even", " class:raster-odd")
"""Alternating style of the cell after the image's last row, which carries the image write when the image changes."""

_ESCAPE_STYLE: Final[str] = "[ZeroWidthEscape]"
"""Prompt Toolkit fragment style written raw right before the next cell."""

_WIDE_TAIL: Final[str] = ""
"""Second cell of a wide character."""

_SAVE_CURSOR: Final[str] = "\x1b7"
"""VT sequence saving the cursor and attributes of Prompt Toolkit's write."""

_RESTORE_CURSOR: Final[str] = "\x1b8"
"""VT sequence restoring the cursor and attributes of Prompt Toolkit's write."""


@dataclass(frozen=True, slots=True)
class Slot:
    """Terminal cells one image covers: top row, left column and size in cells."""

    row: int
    column: int
    columns: int
    rows: int

    def fits(self, columns: int, rows: int) -> bool:
        """Return whether the image and the carrier cell right of its last row fit in the terminal."""
        return (
            self.row >= 0 and self.column >= 0 and self.row + self.rows <= rows and self.column + self.columns < columns
        )

    def holds(self, row: int, column: int) -> bool:
        """Return whether the cell lies under the image."""
        return self.row <= row < self.row + self.rows and self.column <= column < self.column + self.columns


def image_write(slot: Slot, payload: str, *, opaque: bool) -> str:
    """Return the raw write drawing *payload* in *slot*, blanking the cells first under a transparent image."""
    blanks: str = " " * slot.columns
    erase: str = (
        ""
        if opaque
        else "".join(
            f"\x1b[{row + 1};{slot.column + 1}H\x1b[m{blanks}" for row in range(slot.row, slot.row + slot.rows)
        )
    )
    return f"{_SAVE_CURSOR}{erase}\x1b[{slot.row + 1};{slot.column + 1}H{payload}{_RESTORE_CURSOR}"


def raster_frame(
    fragments: StyleAndTextTuples, slot: Slot | None, write: str, released: Slot | None, *, parity: int
) -> StyleAndTextTuples:
    """Blank the slot, attach *write* to the cell after its last row and mark blanks *released* by the last image."""
    lines: list[StyleAndTextTuples] = _lines(fragments)
    touched: set[int] = set()
    for shown in (slot, released):
        if shown is not None:
            touched.update(range(shown.row, shown.row + shown.rows))
    for row in sorted(touched):
        lines.extend([] for _ in range(row + 1 - len(lines)))
        lines[row] = _line(lines[row], row, slot, write, released, parity)
    joined: StyleAndTextTuples = []
    for index, line in enumerate(lines):
        if index:
            joined.append(("", "\n"))
        joined.extend(line)
    return joined


def _lines(fragments: StyleAndTextTuples) -> list[StyleAndTextTuples]:
    lines: list[StyleAndTextTuples] = [[]]
    for style, text, *_rest in fragments:
        if "\n" not in text:
            lines[-1].append((style, text))
            continue
        for index, part in enumerate(text.split("\n")):
            if index:
                lines.append([])
            if part:
                lines[-1].append((style, part))
    return lines


def _line(  # noqa: PLR0913
    line: StyleAndTextTuples, row: int, slot: Slot | None, write: str, released: Slot | None, parity: int
) -> StyleAndTextTuples:
    cells: list[list[str]] = _cells(line)
    shown: list[Slot] = [
        item for item in (slot, released) if item is not None and item.row <= row < item.row + item.rows
    ]
    end: int = max(item.column + item.columns + 1 for item in shown)
    cells.extend(["", " "] for _ in range(end - len(cells)))
    if released is not None and released in shown:
        for column in range(released.column, released.column + released.columns):
            if cells[column][1] == " " and (slot is None or not slot.holds(row, column)):
                cells[column][0] += _RELEASE_STYLE
    carrier: int | None = None
    if slot is not None and slot in shown:
        for column in range(slot.column, slot.column + slot.columns):
            _put(cells, column, _SLOT_STYLE, " ")
        if row == slot.row + slot.rows - 1:
            carrier = slot.column + slot.columns
            if cells[carrier][1] == _WIDE_TAIL:
                _put(cells, carrier, cells[carrier][0], " ")
            cells[carrier][0] += _CARRIER_STYLES[parity] + (_KEPT if cells[carrier][1] == " " else "")
    result: StyleAndTextTuples = []
    for column, (style, character) in enumerate(cells):
        if column == carrier:
            result.append((_ESCAPE_STYLE, write))
        if character != _WIDE_TAIL:
            result.append((style, character))
    return result


def _cells(line: StyleAndTextTuples) -> list[list[str]]:
    cells: list[list[str]] = []
    for style, text, *_rest in line:
        for character in text:
            width: int = get_cwidth(character)
            if width == 0 and cells:
                cells[-2 if cells[-1][1] == _WIDE_TAIL else -1][1] += character
                continue
            cells.append([style, character])
            if width == 2:  # noqa: PLR2004
                cells.append([style, _WIDE_TAIL])
    return cells


def _put(cells: list[list[str]], column: int, style: str, character: str) -> None:
    if cells[column][1] == _WIDE_TAIL:
        cells[column - 1][1] = " "
    elif column + 1 < len(cells) and cells[column + 1][1] == _WIDE_TAIL:
        cells[column + 1][1] = " "
    cells[column] = [style, character]
