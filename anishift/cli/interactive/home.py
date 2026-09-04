"""Home menu for the interactive command line."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.cli.interactive.mascot import MascotState, mascot_art
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.palette import hex_color, mix, rim_color
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

_LOGO_WIDTH: Final[int] = max(len(row) for row in _LOGO_ROWS)
"""Widest wordmark row, which anchors the horizontal outline gradient."""

_LOGO_FILL_GLYPH: Final[str] = "█"
"""Solid glyph carrying the lit face of a wordmark letter."""


_SILVER_TOP: Final[tuple[int, int, int]] = (0xFA, 0xFA, 0xFD)
"""Near-white face of the topmost wordmark row, lit from above."""

_SILVER_BOTTOM: Final[tuple[int, int, int]] = (0xA8, 0xAB, 0xBE)
"""Grey face of the lowest wordmark row, furthest from the light."""

_BRAND_GAP: Final[str] = " " * BRAND_GAP_COLUMNS
"""Fixed separation between the mascot and wordmark, sized by the layout."""

_BOUNCE_HEIGHTS: Final[tuple[int, ...]] = (*([0] * 9), 1, 2, 2, 2, 2, 1, *([0] * 9))
"""Text fallback lift at each of the shared twenty-four animation phases."""


@lru_cache(maxsize=128)
def brand_for_geometry(
    geometry: HomeGeometry | AutoGeometry,
    state: MascotState = MascotState.IDLE,
    *,
    show_mascot: bool = True,
    native_mascot: bool = False,
    animation_phase: int = 0,
) -> Text:
    """Build the centered brand selected for one terminal geometry."""
    mascot: Text | None = None
    if show_mascot and geometry.show_mascot:
        mascot = (
            _native_mascot_placeholder(geometry.mascot_columns, geometry.mascot_rows)
            if native_mascot
            else mascot_art(geometry.mascot_columns, max(geometry.mascot_rows - 2, 1), state)
        )
        if mascot is not None and not native_mascot:
            mascot = _bouncing_mascot(_lowered(mascot, geometry.mascot_rows), animation_phase)
    brand: Text = _home_brand(
        mascot,
        show_full_wordmark=geometry.show_full_wordmark,
        reserved_rows=geometry.brand_rows if show_mascot else 0,
        wordmark_columns=geometry.wordmark_columns,
    )
    return _centered_brand(brand, geometry.terminal_columns)


@lru_cache(maxsize=4)
def _native_mascot_placeholder(columns: int, rows: int) -> Text:
    """Reserve the mascot area and expose one private native-image anchor."""
    if columns < 1 or rows < 1:
        return Text()
    first_row: str = f"{NATIVE_MASCOT_ANCHOR}{' ' * (columns - 1)}"
    remaining_rows: tuple[str, ...] = tuple(" " * columns for _ in range(rows - 1))
    return Text("\n".join((first_row, *remaining_rows)))


def _home_brand(
    mascot: Text | None,
    *,
    show_full_wordmark: bool,
    reserved_rows: int = 0,
    wordmark_columns: int = 8,
) -> Text:
    """Build one centered fixed-size wordmark and optional left mascot."""
    wordmark: Text = _full_wordmark() if show_full_wordmark else _compact_wordmark()
    if mascot is not None and wordmark_columns == 0:
        return mascot
    if mascot is None:
        return _lowered(wordmark, reserved_rows)
    return _beside(mascot, wordmark)


def _bouncing_mascot(mascot: Text, phase: int) -> Text:
    """Move the cached text mascot within its fixed reservation."""
    lines: list[Text] = list(mascot.split("\n"))
    visible: list[Text] = [line for line in lines if line.plain.strip()]
    space: int = len(lines) - len(visible)
    lift: int = min(space, _BOUNCE_HEIGHTS[phase % len(_BOUNCE_HEIGHTS)])
    blank = Text(" " * max(line.cell_len for line in lines))
    return Text("\n").join([*[blank] * (space - lift), *visible, *[blank] * lift])


def _lowered(block: Text, reserved_rows: int) -> Text:
    """Prepend blank rows until ``block`` ends at the bottom of the reservation."""
    missing: int = reserved_rows - len(block.split("\n"))
    if missing < 1:
        return block
    lowered: Text = Text("\n" * missing)
    lowered.append_text(block)
    return lowered


@lru_cache(maxsize=1)
def _full_wordmark() -> Text:
    """Render the block wordmark as silver faces inside a mascot-colored outline."""
    wordmark: Text = Text()
    for index, line in enumerate(_LOGO_ROWS):
        for column, glyph in enumerate(line):
            if glyph == _LOGO_FILL_GLYPH:
                face: str = hex_color(mix(_SILVER_TOP, _SILVER_BOTTOM, index / max(len(_LOGO_ROWS) - 1, 1)))
                wordmark.append(glyph, style=f"bold {face}")
                continue
            wordmark.append(glyph, style=hex_color(rim_color(column / max(_LOGO_WIDTH - 1, 1))))
        if index < len(_LOGO_ROWS) - 1:
            wordmark.append("\n")
    return wordmark


@lru_cache(maxsize=1)
def _compact_wordmark() -> Text:
    """Render a one-row wordmark that carries the mascot colors without an outline."""
    wordmark: Text = Text()
    letters: str = "ANISHIFT"
    for column, glyph in enumerate(letters):
        color: str = hex_color(rim_color(column / max(len(letters) - 1, 1)))
        wordmark.append(glyph, style=f"bold {color}")
    return wordmark


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
