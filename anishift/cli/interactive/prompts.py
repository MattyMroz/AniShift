"""Questionary boundary for the interactive command line."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Final, Protocol, cast

import questionary
from prompt_toolkit.output import Output, create_output

__all__ = [
    "HomeGeometry",
    "InteractivePrompts",
    "PromptChoice",
    "QuestionaryPrompts",
    "home_footer",
    "resolve_home_geometry",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_HOME_MENU_WIDTH: Final[int] = 13
"""Width of the marker, spacing and longest Home label."""

_HOME_MENU_ROWS: Final[int] = 6
"""Rows occupied by menu spacing, choices and the keyboard hint."""

_HOME_HINT: Final[str] = "↑↓ · Enter"
"""Compact keyboard hint aligned directly below the Home choices."""

_MASCOT_COLUMNS: Final[int] = 20
"""Fixed mascot width that does not stretch between Home renders."""

_MASCOT_ROWS: Final[int] = 14
"""Fixed mascot height that does not stretch between Home renders."""

_FULL_WORDMARK_COLUMNS: Final[int] = 57
"""Width of the established six-row ANISHIFT wordmark."""

_FULL_BRAND_COLUMNS: Final[int] = _MASCOT_COLUMNS + 2 + _FULL_WORDMARK_COLUMNS
"""Width required to place the mascot and wordmark beside each other."""

_FULL_BRAND_ROWS: Final[int] = _MASCOT_ROWS
"""Height of the fixed mascot and wordmark composition."""

_FULL_BRAND_TERMINAL_ROWS: Final[int] = 22
"""Minimum height that leaves room for the full brand and menu."""

_COMPACT_BRAND_ROWS: Final[int] = 1
"""Rows occupied by the title when the mascot is hidden."""

_ACCENT: Final[str] = "#5c9cf5"
"""OpenCode secondary blue used by active Home elements."""

_QUESTIONARY_STYLE: Final[questionary.Style] = questionary.Style(
    [
        ("pointer", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("highlighted", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("selected", f"noinherit fg:{_ACCENT} bold noreverse"),
        ("text", "fg:#eeeeee"),
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


class InteractivePrompts(Protocol):
    """Define the prompt operations used by the interactive application."""

    def screen(self) -> AbstractContextManager[None]:
        """Own one alternate terminal screen for the interactive session."""
        ...

    def clear_screen(self) -> None:
        """Erase the active interactive screen and return its cursor home."""
        ...

    def terminal_columns(self) -> int:
        """Return the terminal width for the next Home render."""
        ...

    def terminal_rows(self) -> int:
        """Return the terminal height for the next Home render."""
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
    """Describe the public application action needed by the resize callback."""

    def exit(
        self,
        result: object | None = None,
        exception: BaseException | type[BaseException] | None = None,
        style: str = "",
    ) -> None:
        """Finish the active prompt with a result or exception."""
        ...


class _TerminalResizedError(Exception):
    """Request a clean Home rerender after the terminal dimensions change."""


def resolve_home_geometry(columns: int, rows: int = 24) -> HomeGeometry:
    """Resolve the responsive Home block for one terminal snapshot."""
    terminal_columns: int = max(columns, 1)
    terminal_rows: int = max(rows, 1)
    content_width: int = min(_HOME_MENU_WIDTH, terminal_columns)
    left_padding: int = max((terminal_columns - content_width) // 2, 0)
    show_full_wordmark: bool = terminal_columns >= _FULL_WORDMARK_COLUMNS and terminal_rows >= _FULL_BRAND_TERMINAL_ROWS
    show_mascot: bool = terminal_columns >= _FULL_BRAND_COLUMNS and show_full_wordmark
    mascot_rows: int = _MASCOT_ROWS if show_mascot else 0
    mascot_columns: int = _MASCOT_COLUMNS if show_mascot else 0
    brand_rows: int = _FULL_BRAND_ROWS if show_full_wordmark else _COMPACT_BRAND_ROWS
    content_rows: int = brand_rows + _HOME_MENU_ROWS
    top_padding: int = max((terminal_rows - content_rows - 1) // 2, 0)
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


def home_footer(version: str, directory: str, geometry: HomeGeometry) -> str:
    """Build the menu hint and bottom directory/version status line."""
    version_label: str = f"v{version}"
    usable_width: int = max(geometry.terminal_columns - 1, 1)
    footer_spacing: str = "\n" * geometry.footer_padding
    if usable_width <= len(version_label) + 1:
        compact_version: str = _truncate_left(version_label, usable_width)
        return f"{_HOME_HINT}{footer_spacing}{compact_version.rjust(usable_width)}"
    directory_width: int = usable_width - len(version_label) - 1
    directory_label: str = _truncate_left(directory, directory_width)
    spacing: int = max(usable_width - len(directory_label) - len(version_label), 1)
    status: str = f"{directory_label}{' ' * spacing}{version_label}"
    return f"{_HOME_HINT}{footer_spacing}{status}"


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
        self._output.flush()

    def terminal_columns(self) -> int:
        """Return the injected or current terminal width."""
        return self._width_provider()

    def terminal_rows(self) -> int:
        """Return the injected or current terminal height."""
        return self._height_provider()

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
        """Render a single-select prompt with a non-selectable footer."""
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
            pointer=f"{' ' * geometry.left_padding}▶",
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
        _register_resize_rerender(question, initial_size=initial_size, size_provider=self._terminal_size)
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
) -> None:
    """Close one active prompt when its terminal dimensions change."""
    resize_requested: bool = False

    def rerender_on_resize(application: object) -> None:
        nonlocal resize_requested
        if resize_requested or size_provider() == initial_size:
            return
        resize_requested = True
        prompt_application: _PromptApplication = cast("_PromptApplication", application)
        prompt_application.exit(exception=_TerminalResizedError())

    question.application.after_render += rerender_on_resize
