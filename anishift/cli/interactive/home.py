"""Home menu for the interactive command line."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.cli.interactive.mascot import MascotState, mascot_art
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.prompts import BRAND_GAP_COLUMNS, AutoGeometry, HomeGeometry

__all__ = [
    "HomeAction",
    "brand_for_geometry",
    "working_directory_label",
]


class HomeAction(StrEnum):
    """Identify an action selected from Home."""

    AUTO = "auto"
    MANUAL = "manual"
    SETTINGS = "settings"
    EXIT = "exit"


# ── Constants ─────────────────────────────────────────────────────────────────

_LOGO_ROWS: Final[tuple[str, ...]] = (
    " █████╗ ███╗   ██╗██╗███████╗██╗  ██╗██╗███████╗████████╗",
    "██╔══██╗████╗  ██║██║██╔════╝██║  ██║██║██╔════╝╚══██╔══╝",
    "███████║██╔██╗ ██║██║███████╗███████║██║█████╗     ██║   ",
    "██╔══██║██║╚██╗██║██║╚════██║██╔══██║██║██╔══╝     ██║   ",
    "██║  ██║██║ ╚████║██║███████║██║  ██║██║██║        ██║   ",
    "╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   ",
)
"""Established six-row ANISHIFT wordmark reused without Textual dependencies."""

_SLIME_RAMP: Final[tuple[tuple[int, int, int], ...]] = (
    (0x18, 0x5C, 0xFF),
    (0x76, 0x11, 0xFF),
    (0xBE, 0x00, 0xFA),
    (0xFF, 0x07, 0x8B),
)
"""Blue, violet, magenta and pink sampled from the slime artwork, left to right."""

_LOGO_WIDTH: Final[int] = max(len(row) for row in _LOGO_ROWS)
"""Widest wordmark row, which anchors the horizontal color ramp."""

_LOGO_FILL_GLYPH: Final[str] = "█"
"""Solid glyph carrying the lit face of a wordmark letter."""

_FILL_HIGHLIGHT: Final[tuple[float, ...]] = (0.58, 0.50, 0.44, 0.38, 0.34, 0.30)
"""White share mixed into each filled row, so light reads as coming from above."""

_OUTLINE_SHADE: Final[float] = 0.72
"""Brightness the outline keeps, deep enough to read as the letter's own shadow."""

_WHITE: Final[tuple[int, int, int]] = (0xFF, 0xFF, 0xFF)
"""Highlight color mixed into the top of the wordmark as the only white accent."""

_BRAND_GAP: Final[str] = " " * BRAND_GAP_COLUMNS
"""Fixed separation between the mascot and wordmark, sized by the layout."""


@lru_cache(maxsize=64)
def brand_for_geometry(
    geometry: HomeGeometry | AutoGeometry,
    state: MascotState = MascotState.IDLE,
    *,
    show_mascot: bool = True,
    native_mascot: bool = False,
) -> Text:
    """Build the centered brand selected for one terminal geometry."""
    mascot: Text | None = None
    if show_mascot and geometry.show_mascot:
        mascot = (
            _native_mascot_placeholder(geometry.mascot_columns, geometry.mascot_rows)
            if native_mascot
            else mascot_art(geometry.mascot_columns, geometry.mascot_rows, state)
        )
    brand: Text = _home_brand(mascot, show_full_wordmark=geometry.show_full_wordmark)
    return _centered_brand(brand, geometry.terminal_columns)


@lru_cache(maxsize=4)
def _native_mascot_placeholder(columns: int, rows: int) -> Text:
    """Reserve the mascot area and expose one private native-image anchor."""
    if columns < 1 or rows < 1:
        return Text()
    first_row: str = f"{NATIVE_MASCOT_ANCHOR}{' ' * (columns - 1)}"
    remaining_rows: tuple[str, ...] = tuple(" " * columns for _ in range(rows - 1))
    return Text("\n".join((first_row, *remaining_rows)))


def _home_brand(mascot: Text | None, *, show_full_wordmark: bool) -> Text:
    """Build one centered fixed-size wordmark and optional left mascot."""
    wordmark: Text = _full_wordmark() if show_full_wordmark else _compact_wordmark()
    if mascot is None:
        return wordmark
    return _beside(mascot, wordmark)


@lru_cache(maxsize=1)
def _full_wordmark() -> Text:
    """Render the established block wordmark with a shaded slime palette."""
    wordmark: Text = Text()
    for index, line in enumerate(_LOGO_ROWS):
        for column, glyph in enumerate(line):
            fill: bool = glyph == _LOGO_FILL_GLYPH
            color: str = _wordmark_color(column, index, width=_LOGO_WIDTH, fill=fill)
            wordmark.append(glyph, style=f"bold {color}" if fill else color)
        if index < len(_LOGO_ROWS) - 1:
            wordmark.append("\n")
    return wordmark


@lru_cache(maxsize=1)
def _compact_wordmark() -> Text:
    """Render a one-row wordmark when the full header cannot fit."""
    wordmark: Text = Text()
    letters: str = "ANISHIFT"
    for column, glyph in enumerate(letters):
        color: str = _wordmark_color(column, 0, width=len(letters), fill=True)
        wordmark.append(glyph, style=f"bold {color}")
    return wordmark


def _wordmark_color(column: int, row: int, *, width: int, fill: bool) -> str:
    """Blend one wordmark cell from the slime ramp and its row lighting."""
    red, green, blue = _ramp_color(column / max(width - 1, 1))
    if not fill:
        return _hex(round(red * _OUTLINE_SHADE), round(green * _OUTLINE_SHADE), round(blue * _OUTLINE_SHADE))
    share: float = _FILL_HIGHLIGHT[min(row, len(_FILL_HIGHLIGHT) - 1)]
    return _hex(
        round(red + (_WHITE[0] - red) * share),
        round(green + (_WHITE[1] - green) * share),
        round(blue + (_WHITE[2] - blue) * share),
    )


def _ramp_color(position: float) -> tuple[int, int, int]:
    """Interpolate the slime ramp at a normalized horizontal position."""
    span: float = min(max(position, 0.0), 1.0) * (len(_SLIME_RAMP) - 1)
    index: int = min(int(span), len(_SLIME_RAMP) - 2)
    weight: float = span - index
    start: tuple[int, int, int] = _SLIME_RAMP[index]
    end: tuple[int, int, int] = _SLIME_RAMP[index + 1]
    return (
        round(start[0] + (end[0] - start[0]) * weight),
        round(start[1] + (end[1] - start[1]) * weight),
        round(start[2] + (end[2] - start[2]) * weight),
    )


def _hex(red: int, green: int, blue: int) -> str:
    """Format one color channel triple as a Rich hex style."""
    return f"#{red:02x}{green:02x}{blue:02x}"


def _beside(left: Text, right: Text) -> Text:
    """Place two multiline renderables beside each other, level at the bottom."""
    left_lines: list[Text] = list(left.split("\n"))
    right_lines: list[Text] = list(right.split("\n"))
    left_width: int = max(line.cell_len for line in left_lines)
    right_width: int = max(line.cell_len for line in right_lines)
    row_count: int = max(len(left_lines), len(right_lines))
    left_offset: int = row_count - len(left_lines)
    right_offset: int = row_count - len(right_lines)
    result: Text = Text()
    for index in range(row_count):
        left_index: int = index - left_offset
        right_index: int = index - right_offset
        left_line: Text = left_lines[left_index] if 0 <= left_index < len(left_lines) else Text()
        right_line: Text = right_lines[right_index] if 0 <= right_index < len(right_lines) else Text()
        result.append_text(left_line)
        result.append(" " * (left_width - left_line.cell_len))
        result.append(_BRAND_GAP)
        result.append_text(right_line)
        result.append(" " * (right_width - right_line.cell_len))
        if index < row_count - 1:
            result.append("\n")
    return result


def _centered_brand(brand: Text, terminal_columns: int) -> Text:
    """Apply one shared horizontal offset to every row of the brand block."""
    lines: list[Text] = list(brand.split("\n"))
    width: int = max(line.cell_len for line in lines)
    padding: int = max((terminal_columns - width) // 2, 0)
    result: Text = Text()
    for index, line in enumerate(lines):
        result.append(" " * padding)
        result.append_text(line)
        if index < len(lines) - 1:
            result.append("\n")
    return result


def working_directory_label(cwd: Path | None = None, home: Path | None = None) -> str:
    """Format the current directory like OpenCode without exposing an absolute path."""
    current: Path = Path.cwd() if cwd is None else cwd
    home_directory: Path = Path.home() if home is None else home
    try:
        relative: Path = current.relative_to(home_directory)
    except ValueError:
        return current.name
    if relative == Path():
        return "~"
    relative_label: str = str(relative).replace("/", "\\")
    return f"~\\{relative_label}"
