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
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.output import ColorDepth
from rich.console import Console
from rich.text import Text

from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR, NativeMascotImage, load_native_mascot
from anishift.cli.interactive.palette import BRAND_THEME
from anishift.utils.rich_console.theme import RICH_THEME

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

_HOME_MENU_ROWS: Final[int] = 6
"""Rows occupied by the choices and keyboard hint."""

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

_HOME_CHROME_ROWS: Final[int] = 11
"""Rows Home spends on top padding, the menu gap, the menu and the footer."""

_FULL_WORDMARK_TERMINAL_ROWS: Final[int] = _FULL_WORDMARK_ROWS + _HOME_MENU_ROWS + 1
"""Minimum height that leaves room for the wordmark, menu and footer."""

_COMPACT_BRAND_ROWS: Final[int] = 1
"""Rows occupied by the compact title."""

_MINIMUM_QUEUE_ROWS: Final[int] = 3
"""Queue rows that must survive before Auto spends height on the brand."""

_TERMINAL_SIZE_POLL_SECONDS: Final[float] = 0.005
"""Fallback resize polling interval inside the Prompt Toolkit event loop."""

_AUTO_REFRESH_SECONDS: Final[float] = 0.1
"""Interval used by the single event loop to advance visible elapsed time."""

_NORMALISED_KEYS: Final[tuple[tuple[Keys | str, str], ...]] = (
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
    (Keys.Backspace, "backspace"),
    (Keys.Escape, "escape"),
    (Keys.ControlC, "interrupt"),
)
"""Terminal keys the session forwards under a stable name.

Windows delivers every special key with empty ``data``, so ``Keys.Any`` collapses
them into one indistinguishable event. Each key needs its own binding to survive.
"""

_SAVE_CURSOR: Final[str] = "\x1b7"
"""VT sequence preserving Prompt Toolkit's current cursor position."""

_RESTORE_CURSOR: Final[str] = "\x1b8"
"""VT sequence restoring Prompt Toolkit's current cursor position."""

_ERASE_ROW: Final[str] = "\x1b[{row};{column}H\x1b[m{blanks}"
"""Row erase that overwrites cells, because ECH leaves the image raster behind."""

_CLEAR_SCREEN: Final[str] = "\x1b[2J"
"""Alternate screen clear, the only sequence that drops the image raster."""


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


class _WheelControl(FormattedTextControl):
    """Turn wheel events into scroll requests the surrounding window cannot serve.

    The frame is always exactly as tall as the window, so the default scroller sees
    nothing to scroll and drops the event. Claiming it here is the only way a list
    that pages its own content can react to the wheel.
    """

    def __init__(self, scroll_handler: Callable[[int], None] | None, **arguments: object) -> None:
        super().__init__(**arguments)  # type: ignore[arg-type]
        self._scroll_handler: Callable[[int], None] | None = scroll_handler

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        """Consume wheel events and delegate everything else to the base control."""
        wheel: dict[MouseEventType, int] = {
            MouseEventType.SCROLL_UP: -1,
            MouseEventType.SCROLL_DOWN: 1,
        }
        direction: int | None = wheel.get(mouse_event.event_type)
        if direction is None or self._scroll_handler is None:
            return super().mouse_handler(mouse_event)
        self._scroll_handler(direction)
        return None


class TerminalRenderer:
    """Render the entire interactive session through one Prompt Toolkit application."""

    def __init__(
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> None:
        self._frame_provider: Callable[[int, int], Text] = frame_provider
        self._key_handler: Callable[[str], None] = key_handler
        self._idle_handler: Callable[[], None] | None = idle_handler
        self._render_width: int = 0
        self._render_stream: StringIO | None = None
        self._rich_console: Console | None = None
        self._native_mascot: NativeMascotImage | None = load_native_mascot()
        self._native_animation_started_at: float = time.monotonic()
        self._native_position: tuple[int, int] | None = None
        self._native_drawn_position: tuple[int, int] | None = None
        self._native_drawn_payload: str | None = None
        self._terminal_size: tuple[int, int] | None = None
        bindings: KeyBindings = self._key_bindings()
        control = _WheelControl(
            scroll_handler,
            text=self._formatted_frame,
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
            min_redraw_interval=None,
            max_render_postpone_time=0,
            refresh_interval=_AUTO_REFRESH_SECONDS,
            terminal_size_polling_interval=_TERMINAL_SIZE_POLL_SECONDS,
            after_render=self._after_render,
        )

    @property
    def native_mascot_size(self) -> tuple[int, int] | None:
        """Return the cells this session reserves for its native image, if any."""
        image: NativeMascotImage | None = self._native_mascot
        if image is None:
            return None
        return image.cell_columns, image.layout_rows

    def run(self) -> None:
        """Run the terminal event loop until the user exits."""
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
        self._application.exit()

    def _formatted_frame(self) -> AnyFormattedText:
        size = self._application.output.get_size()
        columns: int = max(size.columns, 1)
        rows: int = max(size.rows, 1)
        frame: Text = self._frame_provider(columns, rows)
        anchor: tuple[int, int] | None = _native_anchor(frame.plain)
        position: tuple[int, int] | None = None
        if anchor is not None and self._native_mascot is not None:
            position = (anchor[0], anchor[1] + _MASCOT_NUDGE_COLUMNS)
            frame = frame.copy()
            frame.plain = frame.plain.replace(NATIVE_MASCOT_ANCHOR, " ")
        self._terminal_size = (columns, rows)
        self._native_position = position
        render_console, stream = self._render_target(columns)
        stream.seek(0)
        stream.truncate(0)
        render_console.print(frame, end="", soft_wrap=True)
        return ANSI(stream.getvalue())

    def _after_render(self, application: Application[None]) -> None:
        self._draw_native_mascot(application)
        # The loop refreshes on its own interval, so this is the only place a
        # deferred write can run without doing I/O inside frame construction.
        if self._idle_handler is not None:
            self._idle_handler()

    def _draw_native_mascot(self, application: Application[None]) -> None:
        image: NativeMascotImage | None = self._native_mascot
        position: tuple[int, int] | None = self._native_position
        if image is None:
            return
        if position is None:
            self._erase_native_mascot()
            return
        row, column = position
        output = application.output
        elapsed_seconds: float = time.monotonic() - self._native_animation_started_at
        payload: str = image.payload_at(elapsed_seconds)
        if payload == self._native_drawn_payload and position == self._native_drawn_position:
            return
        previous: tuple[int, int] | None = self._native_drawn_position
        erase: str = _native_erase_sequence(position, image.cell_columns, image.cell_rows)
        if previous is not None and previous != position:
            erase = _native_erase_sequence(previous, image.cell_columns, image.cell_rows) + erase
        output.write_raw(f"{_SAVE_CURSOR}{erase}\x1b[{row + 1};{column + 1}H{payload}{_RESTORE_CURSOR}")
        output.flush()
        self._native_drawn_position = position
        self._native_drawn_payload = payload

    def _erase_native_mascot(self) -> None:
        if self._native_drawn_position is None:
            return
        self._clear_screen()
        self._native_drawn_position = None
        self._native_drawn_payload = None
        self._application.renderer.reset()
        self._application.invalidate()

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
            bindings.add(key)(self._forward(name))

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


def _native_anchor(frame: str) -> tuple[int, int] | None:
    marker_index: int = frame.find(NATIVE_MASCOT_ANCHOR)
    if marker_index < 0:
        return None
    prefix: str = frame[:marker_index]
    row: int = prefix.count("\n")
    column: int = len(prefix.rsplit("\n", maxsplit=1)[-1])
    return row, column


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
    brand_columns: int = mascot[0] + BRAND_GAP_COLUMNS + _FULL_WORDMARK_COLUMNS
    show_full_wordmark: bool = (
        terminal_columns >= _FULL_WORDMARK_COLUMNS and terminal_rows >= _FULL_WORDMARK_TERMINAL_ROWS
    )
    show_mascot: bool = terminal_columns >= brand_columns and terminal_rows >= mascot[1] + _HOME_CHROME_ROWS
    mascot_columns: int = mascot[0] if show_mascot else 0
    mascot_rows: int = mascot[1] if show_mascot else 0
    if show_mascot:
        brand_rows: int = max(mascot_rows, _FULL_WORDMARK_ROWS)
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


def resolve_auto_geometry(
    columns: int,
    rows: int,
    progress_rows: int,
    mascot: tuple[int, int] = TEXT_MASCOT_SIZE,
) -> AutoGeometry:
    """Place a responsive brand above the queue while reserving the footer."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    row_count: int = max(progress_rows, 1)
    available_rows: int = max(terminal_rows - 1, 1)
    brand_columns: int = mascot[0] + BRAND_GAP_COLUMNS + _FULL_WORDMARK_COLUMNS
    show_full_wordmark: bool = (
        terminal_columns >= _FULL_WORDMARK_COLUMNS and available_rows >= _FULL_WORDMARK_ROWS + 1 + _MINIMUM_QUEUE_ROWS
    )
    # The queue outranks the mascot, so the image only appears once the shortest
    # useful queue still fits beside the tallest brand.
    show_mascot: bool = (
        show_full_wordmark
        and terminal_columns >= brand_columns
        and available_rows >= mascot[1] + 1 + _MINIMUM_QUEUE_ROWS
    )
    wordmark_rows: int = _FULL_WORDMARK_ROWS if show_full_wordmark else _COMPACT_BRAND_ROWS
    brand_rows: int = max(mascot[1], wordmark_rows) if show_mascot else wordmark_rows
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
        mascot_columns=mascot[0] if show_mascot else 0,
        mascot_rows=mascot[1] if show_mascot else 0,
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
