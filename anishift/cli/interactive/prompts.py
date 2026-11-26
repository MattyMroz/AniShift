"""Single-owner terminal renderer for the interactive command line."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from typing import Final

from prompt_toolkit import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import ANSI, AnyFormattedText, fragment_list_to_text, to_formatted_text
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import FormattedTextControl, Layout, Window
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import ColorDepth
from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from anishift.cli.interactive.mascot import mascot_art
from anishift.cli.interactive.mascot_native import load_native_mascot
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage, native_cell
from anishift.cli.interactive.palette import BRAND_THEME
from anishift.cli.interactive.pointer import character_offset
from anishift.utils.rich_console.theme import RICH_THEME

if sys.platform == "win32":
    from prompt_toolkit.input.win32 import ConsoleInputReader, Win32Input

__all__ = [
    "BRAND_GAP_COLUMNS",
    "TEXT_MASCOT_SIZE",
    "AutoGeometry",
    "HomeGeometry",
    "TerminalRenderer",
    "resolve_auto_geometry",
    "resolve_home_geometry",
    "status_line",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_HOME_MENU_WIDTH: Final[int] = 13
"""Width of the marker, spacing and longest Home label."""

_HOME_MENU_ROWS: Final[int] = 5
"""Rows occupied by the choices and keyboard hint."""

_KEY_SEQUENCE_TIMEOUT_S: Final[float] = 0.05
"""Wait for a terminal key sequence without delaying a standalone Escape."""

TEXT_MASCOT_SIZE: Final[tuple[int, int]] = (18, 10)
"""Cells covered by the half-block mascot used without a native image."""

_FULL_WORDMARK_COLUMNS: Final[int] = 57
"""Width of the six-row ANISHIFT wordmark."""

_FULL_WORDMARK_ROWS: Final[int] = 6
"""Height of the six-row ANISHIFT wordmark."""

BRAND_GAP_COLUMNS: Final[int] = 2
"""Columns separating the mascot from the wordmark."""

_MASCOT_NUDGE_COLUMNS: Final[int] = 2
"""Columns the native image is drawn right of its reserved area, inside the gap."""

_HOME_CHROME_ROWS: Final[int] = 10
"""Rows Home spends on top padding, the menu gap, the menu and the footer."""

_MINIMUM_QUEUE_ROWS: Final[int] = 3
"""Queue rows that must survive before Auto spends height on the brand."""

_AUTO_PADDED_ROWS: Final[int] = 17
"""Minimum terminal height for a top margin above the queue header."""

_TERMINAL_SIZE_POLL_SECONDS: Final[float] = 0.1
"""Fallback resize polling interval inside the Prompt Toolkit event loop."""

_AUTO_REFRESH_SECONDS: Final[float] = 0.1
"""Interval used by the single event loop to advance visible elapsed time."""

_POINTER_EVENTS: Final[frozenset[tuple[MouseButton, MouseEventType]]] = frozenset(
    {
        (MouseButton.LEFT, MouseEventType.MOUSE_DOWN),
        (MouseButton.LEFT, MouseEventType.MOUSE_MOVE),
        (MouseButton.LEFT, MouseEventType.MOUSE_UP),
        (MouseButton.RIGHT, MouseEventType.MOUSE_DOWN),
    }
)
"""Pointer events the views follow: every left-button event and a right-button press."""

_HOVER_EVENT: Final[tuple[MouseButton, MouseEventType]] = (MouseButton.NONE, MouseEventType.MOUSE_MOVE)
"""Move with no button pressed, which only changes what lies under the mouse."""

_NORMALISED_KEYS: Final[tuple[tuple[Keys | str | tuple[Keys | str, ...], str], ...]] = (
    (Keys.Up, "up"),
    (Keys.Down, "down"),
    (Keys.Left, "left"),
    (Keys.Right, "right"),
    (Keys.PageUp, "pageup"),
    (Keys.PageDown, "pagedown"),
    (Keys.Home, "home"),
    (Keys.End, "end"),
    (Keys.Enter, "enter"),
    (" ", "space"),
    (Keys.Delete, "delete"),
    (Keys.Tab, "tab"),
    (Keys.BackTab, "backtab"),
    (Keys.Escape, "escape"),
    (Keys.ControlC, "interrupt"),
    (Keys.ControlLeft, "ctrl-left"),
    (Keys.ControlRight, "ctrl-right"),
    (Keys.ControlHome, "ctrl-home"),
    (Keys.ControlEnd, "ctrl-end"),
    (Keys.ControlW, "ctrl-backspace"),
    (Keys.ControlDelete, "ctrl-delete"),
    (Keys.ShiftLeft, "shift-left"),
    (Keys.ShiftRight, "shift-right"),
    (Keys.ShiftHome, "shift-home"),
    (Keys.ShiftEnd, "shift-end"),
    (Keys.ControlShiftLeft, "ctrl-shift-left"),
    (Keys.ControlShiftRight, "ctrl-shift-right"),
    (Keys.ControlShiftHome, "ctrl-shift-home"),
    (Keys.ControlShiftEnd, "ctrl-shift-end"),
    (Keys.ControlA, "select-all"),
    (Keys.ControlX, "cut"),
    (Keys.ControlV, "paste"),
    (Keys.ControlZ, "undo"),
    (Keys.ControlY, "redo"),
    (Keys.ControlInsert, "copy"),
    (Keys.ShiftInsert, "paste"),
    (Keys.ShiftDelete, "cut"),
    ((Keys.Escape, "d"), "ctrl-delete"),
    ((Keys.Escape, Keys.Backspace), "ctrl-backspace"),
)
"""Terminal keys the session forwards under a stable name."""

_VT_CTRL_BACKSPACE: Final[str] = "\x08"
"""Ctrl+Backspace data from a VT input reader, where plain Backspace sends DEL."""

_CONSOLE_CTRL_BACKSPACE: Final[str] = "\x7f"
"""Ctrl+Backspace data from the Windows console event reader, where plain Backspace sends BS."""

_SAVE_CURSOR: Final[str] = "\x1b7"
"""VT sequence preserving Prompt Toolkit's current cursor position."""

_RESTORE_CURSOR: Final[str] = "\x1b8"
"""VT sequence restoring Prompt Toolkit's current cursor position."""

_ERASE_ROW: Final[str] = "\x1b[{row};{column}H\x1b[m{blanks}"
"""Row erase that overwrites cells, because ECH leaves the image raster behind."""

_CLEAR_SCREEN: Final[str] = "\x1b[2J"
"""Alternate screen clear, the only sequence that drops the image raster."""

_SLOT_GUARD: Final[str] = "bold"
"""Invisible style on the blank cells under an image, so Prompt Toolkit never erases a line end through it."""


@dataclass(frozen=True, slots=True)
class HomeGeometry:
    """Describe one terminal-size snapshot used to render Home."""

    terminal_columns: int
    terminal_rows: int
    content_width: int
    left_padding: int
    top_padding: int
    footer_padding: int
    show_mascot: bool
    show_full_wordmark: bool
    mascot_columns: int
    mascot_rows: int
    brand_rows: int
    wordmark_columns: int = 8


@dataclass(frozen=True, slots=True)
class AutoGeometry:
    """Describe the brand and progress placement for Auto."""

    terminal_columns: int
    terminal_rows: int
    top_padding: int
    progress_row: int
    show_mascot: bool
    show_full_wordmark: bool
    mascot_columns: int
    mascot_rows: int
    brand_rows: int
    wordmark_columns: int = 8


class _WheelControl(FormattedTextControl):
    """Turn wheel events into scroll requests the surrounding window cannot serve."""

    def __init__(
        self,
        scroll_handler: Callable[[int], None] | None,
        mouse_handler: Callable[[MouseEvent], None] | None = None,
        hover_handler: Callable[[MouseEvent], bool] | None = None,
        **arguments: object,
    ) -> None:
        super().__init__(**arguments)  # type: ignore[arg-type]
        self._scroll_handler: Callable[[int], None] | None = scroll_handler
        self._mouse_callback: Callable[[MouseEvent], None] | None = mouse_handler
        self._hover_callback: Callable[[MouseEvent], bool] | None = hover_handler

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        """Forward wheel, pointer gestures and hover moves; a move that changes nothing skips the redraw."""
        wheel: dict[MouseEventType, int] = {
            MouseEventType.SCROLL_UP: -1,
            MouseEventType.SCROLL_DOWN: 1,
        }
        direction: int | None = wheel.get(mouse_event.event_type)
        if direction is not None:
            if self._scroll_handler is None:
                return NotImplemented
            self._scroll_handler(direction)
            return None
        pressed: tuple[MouseButton, MouseEventType] = (mouse_event.button, mouse_event.event_type)
        if pressed == _HOVER_EVENT and self._hover_callback is not None:
            return None if self._hover_callback(self._in_cells(mouse_event)) else NotImplemented
        if pressed not in _POINTER_EVENTS or self._mouse_callback is None:
            return NotImplemented
        self._mouse_callback(self._in_cells(mouse_event))
        return None

    def _in_cells(self, mouse_event: MouseEvent) -> MouseEvent:
        lines: list[str] = fragment_list_to_text(to_formatted_text(self.text)).split("\n")
        row: int = mouse_event.position.y
        column: int = mouse_event.position.x
        if 0 <= row < len(lines):
            column = Text(lines[row][:column]).cell_len
        return MouseEvent(Point(column, row), mouse_event.event_type, mouse_event.button, mouse_event.modifiers)


class TerminalRenderer:
    """Render the entire interactive session through one Prompt Toolkit application."""

    def __init__(  # noqa: PLR0913
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
        *,
        mouse_handler: Callable[[MouseEvent], None] | None = None,
        hover_handler: Callable[[MouseEvent], bool] | None = None,
        image_provider: Callable[[], NativeImage | None] | None = None,
        use_mascot: bool = True,
    ) -> None:
        self._frame_provider: Callable[[int, int], Text] = frame_provider
        self._key_handler: Callable[[str], None] = key_handler
        self._idle_handler: Callable[[], None] | None = idle_handler
        self._image_provider: Callable[[], NativeImage | None] | None = image_provider
        self._use_mascot: bool = use_mascot
        self._render_width: int = 0
        self._render_stream: StringIO | None = None
        self._rich_console: Console | None = None
        self._native_cell: tuple[int, int] | None = None
        self._native_mascot: NativeImage | None = None
        self._native_animation_started_at: float = time.monotonic()
        self._native_position: tuple[int, int] | None = None
        self._native_slot: tuple[object, ...] | None = None
        self._native_drawn_position: tuple[int, int] | None = None
        self._native_drawn_payload: str | None = None
        self._native_drawn_image: NativeImage | None = None
        self._native_drawn_slot: tuple[object, ...] | None = None
        self._native_drawn_size: tuple[int, int] | None = None
        self._terminal_size: tuple[int, int] | None = None
        self._prepared_frame: AnyFormattedText = ""
        bindings: KeyBindings = self._key_bindings()
        control = _WheelControl(
            scroll_handler,
            mouse_handler,
            hover_handler,
            text=lambda: self._prepared_frame,
            focusable=False,
            show_cursor=False,
        )
        window = Window(content=control, always_hide_cursor=True, wrap_lines=False)
        self._application: Application[None] = Application(
            layout=Layout(window),
            key_bindings=bindings,
            full_screen=True,
            color_depth=ColorDepth.TRUE_COLOR,
            mouse_support=True,
            erase_when_done=True,
            min_redraw_interval=1 / 30,
            max_render_postpone_time=0,
            refresh_interval=_AUTO_REFRESH_SECONDS,
            terminal_size_polling_interval=_TERMINAL_SIZE_POLL_SECONDS,
            before_render=self._before_render,
            after_render=self._after_render,
        )
        self._application.timeoutlen = _KEY_SEQUENCE_TIMEOUT_S
        self._application.ttimeoutlen = _KEY_SEQUENCE_TIMEOUT_S
        self._ctrl_backspace: str = _ctrl_backspace_data(self._application.input)

    @property
    def native_mascot_size(self) -> tuple[int, int] | None:
        """Return the cells this session reserves for its native mascot, if any."""
        image: NativeImage | None = self._native_mascot
        if image is None:
            return None
        return image.cell_columns, image.cell_rows

    @property
    def native_mascot(self) -> NativeImage | None:
        """Return the encoded native mascot, or None without SIXEL."""
        return self._native_mascot

    @property
    def native_cell(self) -> tuple[int, int] | None:
        """Return the pixel size of one cell of a SIXEL terminal, or None without SIXEL."""
        return self._native_cell

    @property
    def animation_phase(self) -> int:
        """Share one bounded animation clock with the wordmark and text mascot."""
        cycle: float = self._native_mascot.cycle_seconds if self._native_mascot is not None else 2.76
        elapsed: float = time.monotonic() - self._native_animation_started_at
        return int(elapsed % cycle / cycle * 24)

    def run(self) -> None:
        """Run the terminal event loop until the user exits."""
        cell: tuple[int, int] | None = native_cell() if self._use_mascot else None
        self._native_cell = cell
        if cell is not None:
            self._native_mascot = load_native_mascot(cell_size=cell, query_terminal=False)
        if self._native_mascot is None and self._use_mascot:
            mascot_art(TEXT_MASCOT_SIZE[0], TEXT_MASCOT_SIZE[1] - 2)
        self._native_animation_started_at = time.monotonic()
        self._application.run()

    def invalidate(self) -> None:
        """Request one coalesced redraw from any thread."""
        self._application.invalidate()

    def exit(self) -> None:
        """Finish the active interactive application."""
        self._native_position = None
        if self._native_drawn_position is not None:
            self._clear_screen()
            self._native_drawn_position = None
            self._native_drawn_payload = None
            self._native_drawn_image = None
        self._application.exit()

    def _current_image(self) -> NativeImage | None:
        return self._image_provider() if self._image_provider is not None else self._native_mascot

    def _before_render(self, application: Application[None]) -> None:
        if application.is_done:
            self._prepared_frame = ""
            self._native_position = None
            self._erase_native_image()
            return
        self._prepared_frame = self._formatted_frame()
        if application.renderer._last_screen is None:
            self._native_drawn_slot = None
        if self._native_drawn_position == self._native_position:
            return
        if self._terminal_size != self._native_drawn_size:
            self._erase_native_image()
            return
        self._erase_drawn_cells()

    def _erase_drawn_cells(self) -> None:
        position: tuple[int, int] | None = self._native_drawn_position
        image: NativeImage | None = self._native_drawn_image
        if position is not None and image is not None:
            erase: str = _native_erase_sequence(position, image.cell_columns, image.cell_rows)
            self._application.output.write_raw(f"{_SAVE_CURSOR}{erase}{_RESTORE_CURSOR}")
        self._native_drawn_position = None
        self._native_drawn_payload = None
        self._native_drawn_image = None

    def _formatted_frame(self) -> AnyFormattedText:
        size = self._application.output.get_size()
        columns: int = max(size.columns, 1)
        rows: int = max(size.rows, 1)
        frame: Text = self._frame_provider(columns, rows)
        anchor: tuple[int, int] | None = _native_anchor(frame.plain)
        image: NativeImage | None = self._current_image() if anchor is not None else None
        position: tuple[int, int] | None = None
        if anchor is not None:
            nudge: int = _MASCOT_NUDGE_COLUMNS if image is not None and image is self._native_mascot else 0
            shown: tuple[int, int] = (anchor[0], anchor[1] + nudge)
            position = shown if image is not None or shown == self._native_drawn_position else None
            frame = frame.copy()
            frame.plain = frame.plain.replace(NATIVE_IMAGE_ANCHOR, " ")
        sized: NativeImage | None = image or self._native_drawn_image
        self._native_slot = None
        if position is not None and sized is not None:
            frame, cells = _guard_slot(frame, position, sized.cell_columns, sized.cell_rows)
            self._native_slot = (columns, rows, cells)
        self._terminal_size = (columns, rows)
        self._native_position = position
        render_console, stream = self._render_target(columns)
        stream.seek(0)
        stream.truncate(0)
        render_console.print(frame, end="", soft_wrap=True)
        return ANSI(stream.getvalue())

    def _after_render(self, application: Application[None]) -> None:
        if application.is_done:
            return
        self._draw_native_image(application)
        if self._idle_handler is not None:
            self._idle_handler()

    def _draw_native_image(self, application: Application[None]) -> None:
        position: tuple[int, int] | None = self._native_position
        if position is None:
            return
        image: NativeImage | None = self._current_image()
        output = application.output
        drawn: NativeImage | None = self._native_drawn_image or image
        erase: str = "" if drawn is None else _native_erase_sequence(position, drawn.cell_columns, drawn.cell_rows)
        if image is None:
            if self._native_drawn_payload is not None:
                output.write_raw(f"{_SAVE_CURSOR}{erase}{_RESTORE_CURSOR}")
                output.flush()
            self._mark_drawn(position, None, None)
            return
        row, column = position
        elapsed_seconds: float = time.monotonic() - self._native_animation_started_at
        payload: str = image.payload_at(elapsed_seconds)
        same: bool = payload == self._native_drawn_payload and position == self._native_drawn_position
        if same and self._native_slot == self._native_drawn_slot:
            return
        cleared: str = "" if same else erase
        output.write_raw(f"{_SAVE_CURSOR}{cleared}\x1b[{row + 1};{column + 1}H{payload}{_RESTORE_CURSOR}")
        output.flush()
        self._mark_drawn(position, payload, image)

    def _mark_drawn(self, position: tuple[int, int], payload: str | None, image: NativeImage | None) -> None:
        self._native_drawn_position = position
        self._native_drawn_payload = payload
        self._native_drawn_image = image
        self._native_drawn_slot = self._native_slot
        self._native_drawn_size = self._terminal_size

    def _erase_native_image(self) -> None:
        if self._native_drawn_position is None:
            return
        self._application.renderer.reset(leave_alternate_screen=False)
        self._application.output.write_raw(_CLEAR_SCREEN)
        self._native_drawn_position = None
        self._native_drawn_payload = None
        self._native_drawn_image = None

    def _clear_screen(self) -> None:
        output = self._application.output
        output.write_raw(_CLEAR_SCREEN)
        output.flush()

    def _render_target(self, columns: int) -> tuple[Console, StringIO]:
        if self._rich_console is not None and self._render_stream is not None and columns == self._render_width:
            return self._rich_console, self._render_stream
        self._render_width = columns
        self._render_stream = StringIO()
        self._rich_console = Console(
            file=self._render_stream,
            theme=RICH_THEME,
            width=columns,
            color_system="truecolor",
            force_terminal=True,
            legacy_windows=False,
            highlight=False,
        )
        self._rich_console.push_theme(BRAND_THEME)
        return self._rich_console, self._render_stream

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()
        for key, name in _NORMALISED_KEYS:
            sequence: tuple[Keys | str, ...] = key if isinstance(key, tuple) else (key,)
            bindings.add(*sequence)(self._forward(name))

        @bindings.add(Keys.Backspace)
        def backspace(event: KeyPressEvent) -> None:
            self._key_handler("ctrl-backspace" if event.data == self._ctrl_backspace else "backspace")

        @bindings.add(Keys.BracketedPaste)
        def paste(event: KeyPressEvent) -> None:
            self._key_handler(f"paste:{event.data}")

        @bindings.add(Keys.Any)
        def any_key(event: KeyPressEvent) -> None:
            data: str = event.data
            if data and data.isprintable():
                self._key_handler(f"text:{data}")
                return
            self._key_handler("any")

        return bindings

    def _forward(self, name: str) -> Callable[[KeyPressEvent], None]:
        def handler(event: KeyPressEvent) -> None:
            del event
            self._key_handler(name)

        return handler


def _ctrl_backspace_data(terminal_input: Input) -> str:
    """Return the Backspace data that means Ctrl was held, as sent by the reader behind *terminal_input*."""
    if sys.platform == "win32" and isinstance(terminal_input, Win32Input):
        if isinstance(terminal_input.console_input_reader, ConsoleInputReader):
            return _CONSOLE_CTRL_BACKSPACE
    return _VT_CTRL_BACKSPACE


def _native_anchor(frame: str) -> tuple[int, int] | None:
    marker_index: int = frame.find(NATIVE_IMAGE_ANCHOR)
    if marker_index < 0:
        return None
    prefix: str = frame[:marker_index]
    row: int = prefix.count("\n")
    column: int = cell_len(prefix.rsplit("\n", maxsplit=1)[-1])
    return row, column


def _guard_slot(frame: Text, position: tuple[int, int], columns: int, rows: int) -> tuple[Text, tuple[str, ...]]:
    """Mark the blank cells under the image as content and return their text, one string per row."""
    lines: list[Text] = list(frame.split("\n", allow_blank=True))
    cells: list[str] = []
    for line in lines[position[0] : position[0] + rows]:
        line.pad_right(max(position[1] + columns - line.cell_len, 0))
        start: int = character_offset(line.plain, position[1])
        end: int = character_offset(line.plain, position[1] + columns)
        line.stylize(_SLOT_GUARD, start, end)
        cells.append(line.plain[start:end])
    return Text("\n").join(lines), tuple(cells)


def _native_erase_sequence(position: tuple[int, int], columns: int, rows: int) -> str:
    """Overwrite only terminal cells occupied by the previous native frame."""
    row, column = position
    blanks: str = " " * max(columns, 1)
    return "".join(
        _ERASE_ROW.format(row=row + offset + 1, column=column + 1, blanks=blanks) for offset in range(max(rows, 1))
    )


def resolve_home_geometry(
    columns: int,
    rows: int = 24,
    mascot: tuple[int, int] = TEXT_MASCOT_SIZE,
) -> HomeGeometry:
    """Resolve the responsive Home block around one measured mascot size."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    content_width: int = min(_HOME_MENU_WIDTH, terminal_columns)
    left_padding: int = max((terminal_columns - content_width) // 2, 0)
    show_mascot, wordmark_columns, brand_rows = _brand_dimensions(
        terminal_columns, max(terminal_rows - _HOME_CHROME_ROWS, 1), mascot
    )
    show_full_wordmark: bool = wordmark_columns == _FULL_WORDMARK_COLUMNS
    mascot_columns: int = mascot[0] if show_mascot else 0
    mascot_rows: int = mascot[1] if show_mascot else 0
    content_rows: int = brand_rows + _HOME_MENU_ROWS
    top_padding: int = max((terminal_rows - content_rows) // 2, 0)
    footer_padding: int = max(terminal_rows - top_padding - content_rows, 1)
    return HomeGeometry(
        terminal_columns=terminal_columns,
        terminal_rows=terminal_rows,
        content_width=content_width,
        left_padding=left_padding,
        top_padding=top_padding,
        footer_padding=footer_padding,
        show_mascot=show_mascot,
        show_full_wordmark=show_full_wordmark,
        mascot_columns=mascot_columns,
        mascot_rows=mascot_rows,
        brand_rows=brand_rows,
        wordmark_columns=wordmark_columns,
    )


def resolve_auto_geometry(
    columns: int, rows: int, progress_rows: int, mascot: tuple[int, int] = TEXT_MASCOT_SIZE
) -> AutoGeometry:
    """Place a responsive wordmark above the queue while reserving the footer."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    del progress_rows
    available_rows: int = max(terminal_rows - 1, 1)
    top_padding: int = 1 if terminal_rows >= _AUTO_PADDED_ROWS else 0
    show_mascot, wordmark_columns, brand_rows = _brand_dimensions(
        terminal_columns, max(available_rows - top_padding - 3 - _MINIMUM_QUEUE_ROWS, 1), mascot
    )
    show_full_wordmark: bool = wordmark_columns == _FULL_WORDMARK_COLUMNS
    progress_row: int = top_padding + brand_rows + 1
    return AutoGeometry(
        terminal_columns=terminal_columns,
        terminal_rows=terminal_rows,
        top_padding=top_padding,
        progress_row=progress_row,
        show_mascot=show_mascot,
        show_full_wordmark=show_full_wordmark,
        mascot_columns=mascot[0] if show_mascot else 0,
        mascot_rows=mascot[1] if show_mascot else 0,
        brand_rows=brand_rows,
        wordmark_columns=wordmark_columns,
    )


def _brand_dimensions(columns: int, rows: int, mascot: tuple[int, int]) -> tuple[bool, int, int]:
    """Choose the largest wordmark beside a mascot that leaves controls usable."""
    show_mascot: bool = columns >= mascot[0] + BRAND_GAP_COLUMNS and rows >= mascot[1]
    available: int = columns - mascot[0] - BRAND_GAP_COLUMNS if show_mascot else columns
    choices: tuple[tuple[int, int], ...] = ((_FULL_WORDMARK_COLUMNS, _FULL_WORDMARK_ROWS),)
    if not show_mascot:
        choices = (*choices, (8, 1))
    width, height = next(
        ((width, height) for width, height in choices if width <= available and height <= rows), (0, 1)
    )
    return show_mascot, width, max(height, mascot[1] if show_mascot else 0)


def status_line(version: str, directory: str, columns: int) -> str:
    """Place the current directory and version at opposite terminal edges."""
    version_label: str = f"v{version}"
    usable_width: int = max(columns - 1, 1)
    if usable_width <= len(version_label) + 1:
        return _truncate_left(version_label, usable_width).rjust(usable_width)
    directory_width: int = usable_width - len(version_label) - 1
    directory_label: str = _truncate_left(directory, directory_width)
    spacing: int = max(usable_width - len(directory_label) - len(version_label), 1)
    return f"{directory_label}{' ' * spacing}{version_label}"


def _truncate_left(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width == 1:
        return "…"
    return f"…{value[-(width - 1) :]}"
