"""Single-owner terminal renderer for the interactive command line."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from typing import Final

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import FormattedTextControl, Layout, Window
from prompt_toolkit.output import ColorDepth
from rich.console import Console
from rich.text import Text

from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR, NativeMascotImage, load_native_mascot
from anishift.utils.rich_console.theme import RICH_THEME

__all__ = [
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

_HOME_MENU_ROWS: Final[int] = 6
"""Rows occupied by the choices and keyboard hint."""

_MASCOT_COLUMNS: Final[int] = 20
"""Fixed mascot width that does not stretch between renders."""

_MASCOT_ROWS: Final[int] = 14
"""Fixed mascot height that does not stretch between renders."""

_FULL_WORDMARK_COLUMNS: Final[int] = 57
"""Width of the six-row ANISHIFT wordmark."""

_FULL_WORDMARK_ROWS: Final[int] = 6
"""Height of the six-row ANISHIFT wordmark."""

_FULL_BRAND_COLUMNS: Final[int] = _MASCOT_COLUMNS + 2 + _FULL_WORDMARK_COLUMNS
"""Width required to place the mascot and wordmark beside each other."""

_FULL_BRAND_ROWS: Final[int] = _MASCOT_ROWS
"""Height of the mascot and wordmark composition."""

_FULL_BRAND_TERMINAL_ROWS: Final[int] = 21
"""Minimum height that leaves room for the full brand and menu."""

_FULL_WORDMARK_TERMINAL_ROWS: Final[int] = _FULL_WORDMARK_ROWS + _HOME_MENU_ROWS + 1
"""Minimum height that leaves room for the wordmark, menu and footer."""

_COMPACT_BRAND_ROWS: Final[int] = 1
"""Rows occupied by the compact title."""

_TERMINAL_SIZE_POLL_SECONDS: Final[float] = 0.005
"""Fallback resize polling interval inside the Prompt Toolkit event loop."""

_AUTO_REFRESH_SECONDS: Final[float] = 0.06
"""Interval used by the single event loop to advance visible elapsed time."""

_SAVE_CURSOR: Final[str] = "\x1b7"
"""VT sequence preserving Prompt Toolkit's current cursor position."""

_RESTORE_CURSOR: Final[str] = "\x1b8"
"""VT sequence restoring Prompt Toolkit's current cursor position."""

_NATIVE_IMAGE_ROWS: Final[int] = 8
"""Terminal rows covered by a 128-pixel native image."""

_CLEAR_TERMINAL: Final[str] = "\x1b[2J\x1b[3J\x1b[H"
"""VT sequence clearing the visible terminal, scrollback and cursor origin."""


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


class TerminalRenderer:
    """Render the entire interactive session through one Prompt Toolkit application."""

    def __init__(
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
    ) -> None:
        self._frame_provider: Callable[[int, int], Text] = frame_provider
        self._key_handler: Callable[[str], None] = key_handler
        self._render_width: int = 0
        self._render_stream: StringIO | None = None
        self._rich_console: Console | None = None
        self._native_mascot: NativeMascotImage | None = load_native_mascot()
        self._native_animation_started_at: float = time.monotonic()
        self._native_position: tuple[int, int] | None = None
        self._native_drawn_position: tuple[int, int] | None = None
        self._terminal_size: tuple[int, int] | None = None
        bindings: KeyBindings = self._key_bindings()
        control = FormattedTextControl(self._formatted_frame, focusable=False, show_cursor=False)
        window = Window(content=control, always_hide_cursor=True, wrap_lines=False)
        self._application: Application[None] = Application(
            layout=Layout(window),
            key_bindings=bindings,
            full_screen=True,
            color_depth=ColorDepth.TRUE_COLOR,
            mouse_support=True,
            erase_when_done=True,
            min_redraw_interval=None,
            max_render_postpone_time=0,
            refresh_interval=_AUTO_REFRESH_SECONDS,
            terminal_size_polling_interval=_TERMINAL_SIZE_POLL_SECONDS,
            after_render=self._draw_native_mascot,
        )

    @property
    def has_native_mascot(self) -> bool:
        """Return whether this session has a native terminal image payload."""
        return self._native_mascot is not None

    def run(self) -> None:
        """Run the terminal event loop until the user exits."""
        try:
            self._application.run()
        finally:
            output = self._application.output
            output.write_raw(_CLEAR_TERMINAL)
            output.flush()

    def invalidate(self) -> None:
        """Request one coalesced redraw from any thread."""
        self._application.invalidate()

    def exit(self) -> None:
        """Finish the active interactive application."""
        self._erase_native_mascot()
        self._application.exit()

    def _formatted_frame(self) -> AnyFormattedText:
        size = self._application.output.get_size()
        columns: int = max(size.columns, 1)
        rows: int = max(size.rows, 1)
        frame: Text = self._frame_provider(columns, rows)
        anchor: tuple[int, int] | None = _native_anchor(frame.plain)
        position: tuple[int, int] | None = None
        if anchor is not None and self._native_mascot is not None:
            position = (
                anchor[0] + self._native_mascot.row_offset,
                anchor[1] + self._native_mascot.column_offset,
            )
            frame = frame.copy()
            frame.plain = frame.plain.replace(NATIVE_MASCOT_ANCHOR, " ")
        size_changed: bool = self._terminal_size != (columns, rows)
        position_changed: bool = self._native_drawn_position != position
        if self._native_drawn_position is not None and (size_changed or position_changed):
            self._erase_native_mascot()
        self._terminal_size = (columns, rows)
        self._native_position = position
        render_console, stream = self._render_target(columns)
        stream.seek(0)
        stream.truncate(0)
        render_console.print(frame, end="", soft_wrap=True)
        return ANSI(stream.getvalue())

    def _draw_native_mascot(self, application: Application[None]) -> None:
        image: NativeMascotImage | None = self._native_mascot
        position: tuple[int, int] | None = self._native_position
        if image is None or position is None:
            return
        row, column = position
        output = application.output
        elapsed_seconds: float = time.monotonic() - self._native_animation_started_at
        payload: str = image.payload_at(elapsed_seconds)
        output.write_raw(f"{_SAVE_CURSOR}\x1b[{row + 1};{column + 1}H{payload}{_RESTORE_CURSOR}")
        output.flush()
        self._native_drawn_position = position

    def _erase_native_mascot(self) -> None:
        position: tuple[int, int] | None = self._native_drawn_position
        if position is None:
            return
        output = self._application.output
        output.write_raw(f"{_SAVE_CURSOR}{_native_erase_sequence(position)}{_RESTORE_CURSOR}")
        output.flush()
        self._native_drawn_position = None

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
        return self._rich_console, self._render_stream

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add(Keys.Up)
        def move_up(event: KeyPressEvent) -> None:
            del event
            self._key_handler("up")

        @bindings.add(Keys.Down)
        def move_down(event: KeyPressEvent) -> None:
            del event
            self._key_handler("down")

        @bindings.add(Keys.Enter)
        def accept(event: KeyPressEvent) -> None:
            del event
            self._key_handler("enter")

        @bindings.add(" ")
        def toggle(event: KeyPressEvent) -> None:
            del event
            self._key_handler("space")

        @bindings.add(Keys.Backspace)
        def backspace(event: KeyPressEvent) -> None:
            del event
            self._key_handler("backspace")

        @bindings.add(Keys.Escape)
        def escape(event: KeyPressEvent) -> None:
            del event
            self._key_handler("escape")

        @bindings.add(Keys.ControlC)
        def interrupt(event: KeyPressEvent) -> None:
            del event
            self._key_handler("interrupt")

        @bindings.add(Keys.Any)
        def any_key(event: KeyPressEvent) -> None:
            data: str = event.data
            if data and data.isprintable():
                self._key_handler(f"text:{data}")
                return
            self._key_handler("any")

        return bindings


def _native_anchor(frame: str) -> tuple[int, int] | None:
    marker_index: int = frame.find(NATIVE_MASCOT_ANCHOR)
    if marker_index < 0:
        return None
    prefix: str = frame[:marker_index]
    row: int = prefix.count("\n")
    column: int = len(prefix.rsplit("\n", maxsplit=1)[-1])
    return row, column


def _native_erase_sequence(position: tuple[int, int]) -> str:
    """Build line erases removing a native image before the next view."""
    row, column = position
    return "".join(f"\x1b[{row + offset + 1};{column + 1}H\x1b[2K" for offset in range(_NATIVE_IMAGE_ROWS))


def resolve_home_geometry(columns: int, rows: int = 24) -> HomeGeometry:
    """Resolve the responsive Home block for one terminal snapshot."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    content_width: int = min(_HOME_MENU_WIDTH, terminal_columns)
    left_padding: int = max((terminal_columns - content_width) // 2, 0)
    show_full_wordmark: bool = (
        terminal_columns >= _FULL_WORDMARK_COLUMNS and terminal_rows >= _FULL_WORDMARK_TERMINAL_ROWS
    )
    show_mascot: bool = terminal_columns >= _FULL_BRAND_COLUMNS and terminal_rows >= _FULL_BRAND_TERMINAL_ROWS
    mascot_rows: int = _MASCOT_ROWS if show_mascot else 0
    mascot_columns: int = _MASCOT_COLUMNS if show_mascot else 0
    if show_mascot:
        brand_rows: int = _FULL_BRAND_ROWS
    elif show_full_wordmark:
        brand_rows = _FULL_WORDMARK_ROWS
    else:
        brand_rows = _COMPACT_BRAND_ROWS
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
    )


def resolve_auto_geometry(columns: int, rows: int, progress_rows: int) -> AutoGeometry:
    """Place a responsive brand above progress while reserving the footer."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    row_count: int = max(progress_rows, 1)
    available_rows: int = max(terminal_rows - 1, 1)
    show_mascot: bool = terminal_columns >= _FULL_BRAND_COLUMNS and available_rows >= _FULL_BRAND_ROWS + 1 + row_count
    show_full_wordmark: bool = show_mascot or (
        terminal_columns >= _FULL_WORDMARK_COLUMNS and available_rows >= _FULL_WORDMARK_ROWS + 1 + row_count
    )
    if show_mascot:
        brand_rows: int = _FULL_BRAND_ROWS
    elif show_full_wordmark:
        brand_rows = _FULL_WORDMARK_ROWS
    else:
        brand_rows = _COMPACT_BRAND_ROWS
    content_rows: int = brand_rows + 1 + row_count
    top_padding: int = max((available_rows - content_rows) // 2, 0)
    progress_row: int = min(top_padding + brand_rows + 1, max(available_rows - row_count, 0))
    return AutoGeometry(
        terminal_columns=terminal_columns,
        terminal_rows=terminal_rows,
        top_padding=top_padding,
        progress_row=progress_row,
        show_mascot=show_mascot,
        show_full_wordmark=show_full_wordmark,
        mascot_columns=_MASCOT_COLUMNS if show_mascot else 0,
        mascot_rows=_MASCOT_ROWS if show_mascot else 0,
    )


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
