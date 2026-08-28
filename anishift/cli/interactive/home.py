"""Home menu for the interactive command line."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.cli.interactive.mascot import mascot_art
from anishift.cli.interactive.prompts import (
    HomeGeometry,
    InteractivePrompts,
    PromptChoice,
    _TerminalResizedError,
    home_footer,
    resolve_home_geometry,
)
from anishift.utils.rich_console import console

__all__ = [
    "HomeAction",
    "ask_home_action",
]


class HomeAction(StrEnum):
    """Identify an action selected from Home."""

    AUTO = "auto"
    MANUAL = "manual"
    SETTINGS = "settings"
    EXIT = "exit"


# ── Constants ─────────────────────────────────────────────────────────────────

_HOME_CHOICES: Final[tuple[PromptChoice, ...]] = (
    PromptChoice("Auto", HomeAction.AUTO),
    PromptChoice("Ręczny", HomeAction.MANUAL),
    PromptChoice("Ustawienia", HomeAction.SETTINGS),
    PromptChoice("Wyjście", HomeAction.EXIT),
)
"""Home actions in their product-defined display order."""

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
    "#45e7ff",
    "#4f9dff",
    "#745cff",
    "#b44cff",
    "#f24fc7",
    "#ff527f",
)
"""Slime-derived colors used across the filled wordmark glyphs."""

_LOGO_OUTLINE_PALETTE: Final[tuple[str, ...]] = (
    "#176478",
    "#24508a",
    "#392d83",
    "#5d267d",
    "#7c286a",
    "#842b49",
)
"""Dark companion colors used by the wordmark outline glyphs."""

_LOGO_FILL_GLYPH: Final[str] = "█"
"""Solid glyph receiving the bright part of the wordmark palette."""

_LOGO_ROW_BRIGHTNESS: Final[tuple[float, ...]] = (1.0, 0.94, 0.86, 0.78, 0.7, 0.62)
"""Top-to-bottom shading that gives the wordmark visible depth."""

_BRAND_GAP: Final[str] = "  "
"""Fixed separation between the mascot and wordmark."""


def ask_home_action(prompts: InteractivePrompts, *, version: str) -> HomeAction:
    """Render Home and return the selected action."""
    while True:
        geometry: HomeGeometry = resolve_home_geometry(prompts.terminal_columns(), prompts.terminal_rows())
        prompts.clear_screen()
        if geometry.top_padding:
            console.print("\n" * geometry.top_padding, end="")
        mascot: Text | None = (
            mascot_art(geometry.mascot_columns, geometry.mascot_rows) if geometry.show_mascot else None
        )
        brand: Text = _home_brand(mascot, show_full_wordmark=geometry.show_full_wordmark)
        console.print(_centered_brand(brand, geometry.terminal_columns))
        try:
            selected: str = prompts.select(
                _HOME_CHOICES,
                default=None,
                footer=home_footer(version, _working_directory_label(), geometry),
                geometry=geometry,
            )
        except _TerminalResizedError:
            continue
        return HomeAction(selected)


def _home_brand(mascot: Text | None, *, show_full_wordmark: bool) -> Text:
    """Build one centered fixed-size wordmark and optional left mascot."""
    wordmark: Text = _full_wordmark() if show_full_wordmark else _compact_wordmark()
    if mascot is None:
        return wordmark
    return _beside(mascot, wordmark)


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


def _working_directory_label(cwd: Path | None = None, home: Path | None = None) -> str:
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
