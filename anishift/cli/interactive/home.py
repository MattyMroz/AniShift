"""Home menu for the interactive command line."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.cli.interactive.mascot import MascotState, mascot_art
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.prompts import AutoGeometry, HomeGeometry

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

_LOGO_FILL_PALETTE: Final[tuple[str, ...]] = (
    "#f7f7fa",
    "#f0f0f5",
    "#e7e7ef",
    "#d9dae5",
    "#c7c9d8",
    "#b4b7c9",
)
"""White-to-silver colors used across the filled wordmark glyphs."""

_LOGO_OUTLINE_PALETTE: Final[tuple[str, ...]] = (
    "#2fbad3",
    "#3488c7",
    "#5748bd",
    "#853fb6",
    "#b43c8a",
    "#d24670",
)
"""Slime-derived cyan-to-pink colors used by the wordmark outline."""

_LOGO_FILL_GLYPH: Final[str] = "█"
"""Solid glyph receiving the bright part of the wordmark palette."""

_LOGO_ROW_BRIGHTNESS: Final[tuple[float, ...]] = (1.0, 0.94, 0.86, 0.78, 0.7, 0.62)
"""Top-to-bottom shading that gives the wordmark visible depth."""

_BRAND_GAP: Final[str] = "  "
"""Fixed separation between the mascot and wordmark."""


@lru_cache(maxsize=64)
def brand_for_geometry(
    geometry: HomeGeometry | AutoGeometry,
    state: MascotState = MascotState.IDLE,
    *,
    native_mascot: bool = False,
) -> Text:
    """Build the centered brand selected for one terminal geometry."""
    mascot: Text | None = None
    if geometry.show_mascot:
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
            palette: tuple[str, ...] = _LOGO_FILL_PALETTE if glyph == _LOGO_FILL_GLYPH else _LOGO_OUTLINE_PALETTE
            color: str = _wordmark_color(palette, column, index)
            wordmark.append(glyph, style=f"bold {color}" if glyph == _LOGO_FILL_GLYPH else color)
        if index < len(_LOGO_ROWS) - 1:
            wordmark.append("\n")
    return wordmark


@lru_cache(maxsize=1)
def _compact_wordmark() -> Text:
    """Render a one-row wordmark when the full header cannot fit."""
    wordmark: Text = Text()
    for column, glyph in enumerate("ANISHIFT"):
        wordmark.append(glyph, style=f"bold {_wordmark_color(_LOGO_FILL_PALETTE, column, 0, width=8)}")
    return wordmark


def _wordmark_color(
    palette: tuple[str, ...],
    column: int,
    row: int,
    *,
    width: int = 57,
) -> str:
    """Choose and shade one wordmark color from its horizontal position."""
    palette_index: int = min(column * len(palette) // max(width, 1), len(palette) - 1)
    brightness: float = _LOGO_ROW_BRIGHTNESS[min(row, len(_LOGO_ROW_BRIGHTNESS) - 1)]
    color: str = palette[palette_index].lstrip("#")
    red: int = round(int(color[0:2], 16) * brightness)
    green: int = round(int(color[2:4], 16) * brightness)
    blue: int = round(int(color[4:6], 16) * brightness)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _beside(left: Text, right: Text) -> Text:
    """Place two multiline renderables beside each other without rescaling either."""
    left_lines: list[Text] = list(left.split("\n"))
    right_lines: list[Text] = list(right.split("\n"))
    left_width: int = max(line.cell_len for line in left_lines)
    right_width: int = max(line.cell_len for line in right_lines)
    row_count: int = max(len(left_lines), len(right_lines))
    left_offset: int = (row_count - len(left_lines)) // 2
    right_offset: int = (row_count - len(right_lines)) // 2
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
