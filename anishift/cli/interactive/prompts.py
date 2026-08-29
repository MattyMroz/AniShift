"""Single-owner terminal renderer for the interactive command line."""

from __future__ import annotations

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

_AUTO_REFRESH_SECONDS: Final[float] = 0.1
"""Interval used by the single event loop to advance visible elapsed time."""


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
        bindings: KeyBindings = self._key_bindings()
        control = FormattedTextControl(self._formatted_frame, focusable=False, show_cursor=False)
        window = Window(content=control, always_hide_cursor=True, wrap_lines=False)
        self._application: Application[None] = Application(
            layout=Layout(window),
            key_bindings=bindings,
            full_screen=True,
            color_depth=ColorDepth.TRUE_COLOR,
            mouse_support=False,
            erase_when_done=False,
            min_redraw_interval=None,
            max_render_postpone_time=0,
            refresh_interval=_AUTO_REFRESH_SECONDS,
            terminal_size_polling_interval=_TERMINAL_SIZE_POLL_SECONDS,
        )

    def run(self) -> None:
        """Run the terminal event loop until the user exits."""
        self._application.run()

    def invalidate(self) -> None:
        """Request one coalesced redraw from any thread."""
        self._application.invalidate()

    def exit(self) -> None:
        """Finish the active interactive application."""
        self._application.exit()

    def _formatted_frame(self) -> AnyFormattedText:
        size = self._application.output.get_size()
        columns: int = max(size.columns, 1)
        rows: int = max(size.rows, 1)
        frame: Text = self._frame_provider(columns, rows)
        render_console, stream = self._render_target(columns)
        stream.seek(0)
        stream.truncate(0)
        render_console.print(frame, end="", soft_wrap=True)
        return ANSI(stream.getvalue())

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
