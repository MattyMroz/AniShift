"""Questionary boundary for the interactive command line."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Protocol, cast

import questionary
from prompt_toolkit.output import Output, create_output

__all__ = [
    "AutoGeometry",
    "HomeGeometry",
    "InteractivePrompts",
    "PromptChoice",
    "QuestionaryPrompts",
    "home_footer",
    "resolve_auto_geometry",
    "resolve_home_geometry",
    "status_line",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_HOME_MENU_WIDTH: Final[int] = 13
"""Width of the marker, spacing and longest Home label."""

_HOME_MENU_ROWS: Final[int] = 6
"""Rows occupied by the choices and keyboard hint."""

_HOME_HINT: Final[str] = "↑↓ · Enter"
"""Compact keyboard hint aligned directly below the Home choices."""

_MASCOT_COLUMNS: Final[int] = 20
"""Fixed mascot width that does not stretch between Home renders."""

_MASCOT_ROWS: Final[int] = 14
"""Fixed mascot height that does not stretch between Home renders."""

_FULL_WORDMARK_COLUMNS: Final[int] = 57
"""Width of the established six-row ANISHIFT wordmark."""

_FULL_WORDMARK_ROWS: Final[int] = 6
"""Height of the established ANISHIFT wordmark."""

_FULL_BRAND_COLUMNS: Final[int] = _MASCOT_COLUMNS + 2 + _FULL_WORDMARK_COLUMNS
"""Width required to place the mascot and wordmark beside each other."""

_FULL_BRAND_ROWS: Final[int] = _MASCOT_ROWS
"""Height of the fixed mascot and wordmark composition."""

_FULL_BRAND_TERMINAL_ROWS: Final[int] = 21
"""Minimum height that leaves room for the full brand and menu."""

_FULL_WORDMARK_TERMINAL_ROWS: Final[int] = _FULL_WORDMARK_ROWS + _HOME_MENU_ROWS + 1
"""Minimum height that leaves room for the wordmark, menu and footer."""

_COMPACT_BRAND_ROWS: Final[int] = 1
"""Rows occupied by the title when the full brand cannot fit."""

_ACCENT: Final[str] = "#a855f7"
"""Slime purple used by active Home elements."""

_RESIZE_POLL_SECONDS: Final[float] = 0.01
"""Interval used to sample terminal dimensions in an active view."""

_RESIZE_SETTLE_POLLS: Final[int] = 3
"""Unchanged samples required before one coalesced resize redraw."""

_QUESTIONARY_STYLE: Final[questionary.Style] = questionary.Style(
    [
        ("pointer", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("highlighted", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("selected", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("text", "fg:#eeeeee bold"),
        ("separator", "fg:#808080"),
        ("instruction", "fg:#808080"),
        ("question", "fg:#eeeeee"),
        ("answer", f"fg:{_ACCENT}"),
        ("validation-toolbar", "fg:#ff0000"),
    ]
)
"""Small local style shared by AniShift Questionary prompts."""


@dataclass(frozen=True, slots=True)
class PromptChoice:
    """Represent one selectable prompt value."""

    title: str
    value: str


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
    """Describe the brand, progress and footer placement for Auto."""

    terminal_columns: int
    terminal_rows: int
    top_padding: int
    progress_row: int
    show_mascot: bool
    show_full_wordmark: bool
    mascot_columns: int
    mascot_rows: int


class InteractivePrompts(Protocol):
    """Define the prompt operations used by the interactive application."""

    def screen(self) -> AbstractContextManager[None]:
        """Own one alternate terminal screen for the interactive session."""
        ...

    def clear_screen(self) -> None:
        """Erase the active interactive screen and return its cursor home."""
        ...

    def terminal_columns(self) -> int:
        """Return the terminal width for the next render."""
        ...

    def terminal_rows(self) -> int:
        """Return the terminal height for the next render."""
        ...

    def render_footer(self, version: str, directory: str) -> None:
        """Render the essential directory and version status line."""
        ...

    def position_cursor(self, row: int, column: int = 0) -> None:
        """Move the cursor to an exact screen cell."""
        ...

    def watch_resize(self, callback: Callable[[], None]) -> AbstractContextManager[None]:
        """Invoke a redraw callback whenever terminal dimensions change."""
        ...

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        """Ask the user to select one value."""
        ...

    def pause(self, message: str) -> None:
        """Wait until the user presses a key."""
        ...


class _PromptApplication(Protocol):
    """Describe the application action needed by the resize callback."""

    def exit(
        self,
        result: object | None = None,
        exception: BaseException | type[BaseException] | None = None,
        style: str = "",
    ) -> None:
        """Finish the active prompt with a result or exception."""
        ...


class _TerminalResizedError(Exception):
    """Request one clean Home rerender after terminal dimensions change."""


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


def home_footer(version: str, directory: str, geometry: HomeGeometry) -> str:
    """Build the keyboard hint and essential bottom status line."""
    footer_spacing: str = "\n" * geometry.footer_padding
    return f"{_HOME_HINT}{footer_spacing}{status_line(version, directory, geometry.terminal_columns)}"


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
    """Keep the end of an overlong status value visible."""
    if len(value) <= width:
        return value
    if width == 1:
        return "…"
    return f"…{value[-(width - 1) :]}"


class QuestionaryPrompts:
    """Provide production prompts through public Questionary APIs."""

    def __init__(
        self,
        width_provider: Callable[[], int] | None = None,
        height_provider: Callable[[], int] | None = None,
        output: Output | None = None,
    ) -> None:
        self._width_provider: Callable[[], int] = width_provider or _terminal_columns
        self._height_provider: Callable[[], int] = height_provider or _terminal_rows
        self._output: Output = output or create_output(always_prefer_tty=True)

    def screen(self) -> AbstractContextManager[None]:
        """Own one native Prompt Toolkit alternate screen."""
        return _terminal_screen(self._output)

    def clear_screen(self) -> None:
        """Erase and flush the active terminal screen."""
        self._output.erase_screen()
        self._output.cursor_goto(0, 0)
        self._output.flush()

    def terminal_columns(self) -> int:
        """Return the injected or current terminal width."""
        return self._width_provider()

    def terminal_rows(self) -> int:
        """Return the injected or current terminal height."""
        return self._height_provider()

    def render_footer(self, version: str, directory: str) -> None:
        """Write the essential status line into the last terminal row."""
        columns: int
        rows: int
        columns, rows = self._terminal_size()
        self._output.cursor_goto(max(rows - 1, 0), 0)
        self._output.erase_end_of_line()
        self._output.write(status_line(version, directory, columns))
        self._output.cursor_goto(0, 0)
        self._output.flush()

    def position_cursor(self, row: int, column: int = 0) -> None:
        """Move and flush the native terminal cursor."""
        self._output.cursor_goto(max(row, 0), max(column, 0))
        self._output.flush()

    def watch_resize(self, callback: Callable[[], None]) -> AbstractContextManager[None]:
        """Watch terminal dimensions only while a live Auto view is active."""
        return _ResizeWatcher(self._terminal_size, callback)

    def _terminal_size(self) -> tuple[int, int]:
        """Return both injected terminal dimensions as one snapshot."""
        return self.terminal_columns(), self.terminal_rows()

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        """Render one single-select prompt with a keyboard hint."""
        initial_size: tuple[int, int] = (geometry.terminal_columns, geometry.terminal_rows)
        prompt_choices: list[questionary.Choice | questionary.Separator] = [
            questionary.Choice(choice.title, value=choice.value) for choice in choices
        ]
        prompt_choices.append(questionary.Separator(footer))
        question: questionary.Question = questionary.select(
            "",
            choices=prompt_choices,
            default=default,
            qmark="",
            pointer=f"{' ' * geometry.left_padding}❯",  # noqa: RUF001
            style=_QUESTIONARY_STYLE,
            use_shortcuts=False,
            use_arrow_keys=True,
            use_indicator=False,
            use_jk_keys=False,
            use_emacs_keys=False,
            show_selected=False,
            show_description=False,
            instruction=" ",
            erase_when_done=True,
            output=self._output,
        )
        with _register_resize_rerender(
            question,
            initial_size=initial_size,
            size_provider=self._terminal_size,
        ):
            return cast("str", question.unsafe_ask())

    def pause(self, message: str) -> None:
        """Wait for one key without swallowing keyboard interruption."""
        question: questionary.Question = questionary.press_any_key_to_continue(
            message,
            style=_QUESTIONARY_STYLE,
            erase_when_done=True,
            output=self._output,
        )
        question.unsafe_ask()


@contextmanager
def _terminal_screen(output: Output) -> Iterator[None]:
    """Keep one cross-platform alternate screen active for the session."""
    output.enter_alternate_screen()
    output.erase_screen()
    output.flush()
    try:
        yield
    finally:
        output.erase_screen()
        output.show_cursor()
        output.quit_alternate_screen()
        output.flush()


def _terminal_columns() -> int:
    """Read the current terminal width with a stable fallback."""
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def _terminal_rows() -> int:
    """Read the current terminal height with a stable fallback."""
    return shutil.get_terminal_size(fallback=(80, 24)).lines


def _register_resize_rerender(
    question: questionary.Question,
    *,
    initial_size: tuple[int, int],
    size_provider: Callable[[], tuple[int, int]],
) -> AbstractContextManager[None]:
    """Close one active prompt after a coalesced terminal resize."""
    resize_requested: threading.Event = threading.Event()

    def request_rerender() -> None:
        resize_requested.set()
        question.application.invalidate()

    def rerender_on_resize(application: object) -> None:
        if not resize_requested.is_set():
            return
        prompt_application: _PromptApplication = cast("_PromptApplication", application)
        prompt_application.exit(exception=_TerminalResizedError())

    question.application.after_render += rerender_on_resize
    return _ResizeWatcher(size_provider, request_rerender, initial_size=initial_size)


class _ResizeWatcher(AbstractContextManager[None]):
    """Poll terminal size during Auto and serialize redraw requests."""

    def __init__(
        self,
        size_provider: Callable[[], tuple[int, int]],
        callback: Callable[[], None],
        *,
        initial_size: tuple[int, int] | None = None,
    ) -> None:
        self._size_provider: Callable[[], tuple[int, int]] = size_provider
        self._callback: Callable[[], None] = callback
        self._initial_size: tuple[int, int] | None = initial_size
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def __enter__(self) -> None:
        """Start one short-lived resize watcher."""
        self._thread = threading.Thread(target=self._run, name="anishift-auto-resize", daemon=True)
        self._thread.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the watcher and surface redraw failures on the owning thread."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self._error is not None and exc_type is None:
            raise self._error

    def _run(self) -> None:
        size: tuple[int, int] = self._initial_size or self._size_provider()
        pending_size: tuple[int, int] = size
        stable_polls: int = 0
        while not self._stop.wait(_RESIZE_POLL_SECONDS):
            current: tuple[int, int] = self._size_provider()
            if current != pending_size:
                pending_size = current
                stable_polls = 0
                continue
            if pending_size == size:
                continue
            stable_polls += 1
            if stable_polls < _RESIZE_SETTLE_POLLS:
                continue
            try:
                self._callback()
            except BaseException as error:  # noqa: BLE001 - surfaced by the context owner
                self._error = error
                self._stop.set()
                return
            size = pending_size
            stable_polls = 0
