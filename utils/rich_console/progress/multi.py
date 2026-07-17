"""Multi-task progress manager with per-task colors and block-style bars.

Renders one block-style bar (``█─░``) per task inside a single
``rich.Progress`` live display. Each task keeps its own color transition:
the style travels in ``task.fields`` so rows never repaint each other.
All mutating methods are thread-safe.

Usage:
    >>> with MultiProgressManager() as mp:
    ...     first = mp.add_task("episode 1.mkv")
    ...     second = mp.add_task("episode 2.mkv")
    ...     mp.update(first, 40)
    ...     mp.advance(second, 5)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from rich.progress import Progress, TaskID, TextColumn

from ..console import console
from .manager import (
    ColoredElapsedColumn,
    ColoredPercentageColumn,
    ProgressBarBuilder,
    ProgressBarManager,
)

if TYPE_CHECKING:
    from types import TracebackType

__all__ = ["MultiProgressManager"]

# ── Constants ─────────────────────────────────────────────────────────────────

_STYLE_FIELD: Final[str] = "style"
"""Per-task field carrying the current Rich style of the task's row."""

_BAR_FIELD: Final[str] = "custom_bar"
"""Per-task field carrying the pre-rendered block bar markup."""

_BASE_INFO_WIDTH: Final[int] = 23
"""Character width reserved for the percentage and elapsed columns."""

_MAX_BAR_WIDTH: Final[int] = 40
"""Maximum bar width in characters."""

_MIN_BAR_WIDTH: Final[int] = 3
"""Minimum bar width to prevent a degenerate display."""

_ELLIPSIS: Final[str] = "..."
"""Suffix appended to descriptions truncated at the tail."""


@dataclass(slots=True)
class _TaskState:
    """Mutable per-task bookkeeping.

    Attributes:
        description: Truncated task label (without color markup).
        total: Total units of the task.
        completed: Units completed so far.
        style: Current Rich style of the task's row.
    """

    description: str
    total: int
    completed: int
    style: str


class MultiProgressManager:
    """Thread-safe multi-task progress display with per-task color transitions.

    Shares the block-bar builder, colored columns and the default color
    thresholds with :class:`ProgressBarManager`; differs in cardinality
    (many tasks) and thread safety (internal lock, no external lock needed).

    Example:
        >>> with MultiProgressManager() as mp:
        ...     task = mp.add_task("file.mkv", total=100)
        ...     mp.update(task, 100)
    """

    def __init__(
        self,
        *,
        colors: dict[int, tuple[str, str]] | None = None,
        max_description_length: int = 40,
    ) -> None:
        """Initialize the display without starting it.

        Args:
            colors: Color transitions as ``{percentage: (text, bar)}``;
                defaults to ``ProgressBarManager.DEFAULT_COLORS``.
            max_description_length: Longest description before tail truncation.
        """
        self._colors = colors or ProgressBarManager.DEFAULT_COLORS
        self._max_description_length = max(5, max_description_length)
        self._lock = threading.Lock()
        self._states: dict[TaskID, _TaskState] = {}
        self._bar_width = self._calculate_bar_width()
        initial_style = next(iter(self._colors.values()))[0]
        self._progress = Progress(
            TextColumn("{task.description}"),
            TextColumn(f"{{task.fields[{_BAR_FIELD}]}}", justify="left"),
            ColoredPercentageColumn(initial_style),
            ColoredElapsedColumn(initial_style),
            console=console,
            expand=False,
        )

    def __enter__(self) -> MultiProgressManager:
        """Start the live display and return self."""
        self._progress.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop the live display, leaving every task at its last state."""
        self._progress.stop()

    def add_task(self, description: str, *, total: int = 100) -> TaskID:
        """Add one bar row and return its id.

        Args:
            description: Row label; truncated at the tail when too long.
            total: Total units of the task (100 for percent-driven feeds).

        Returns:
            The task id accepted by :meth:`advance` and :meth:`update`.
        """
        with self._lock:
            label = self._truncate(description)
            style = self._style_for(0, total)
            fields: dict[str, Any] = {
                _STYLE_FIELD: style,
                _BAR_FIELD: ProgressBarBuilder.blocks(self._bar_width, 0.0, style),
            }
            task_id = self._progress.add_task(f"[{style}]{label}", total=total, **fields)
            self._states[task_id] = _TaskState(label, total, 0, style)
            return task_id

    def advance(self, task_id: TaskID, amount: int = 1) -> None:
        """Advance one task by *amount* units.

        Args:
            task_id: Task returned by :meth:`add_task`.
            amount: Units to add to the task's completed count.
        """
        with self._lock:
            state = self._states[task_id]
            self._apply(task_id, state, state.completed + amount)

    def update(self, task_id: TaskID, completed: int) -> None:
        """Set one task's absolute completed count.

        Args:
            task_id: Task returned by :meth:`add_task`.
            completed: Absolute completed units (clamped to the task total).
        """
        with self._lock:
            self._apply(task_id, self._states[task_id], completed)

    def _apply(self, task_id: TaskID, state: _TaskState, completed: int) -> None:
        """Write one task's new completed count, restyling when needed."""
        state.completed = max(0, min(state.total, completed))
        style = self._style_for(state.completed, state.total)
        ratio = state.completed / state.total if state.total else 0.0
        bar = ProgressBarBuilder.blocks(self._bar_width, ratio, style)
        fields: dict[str, Any] = {_BAR_FIELD: bar}
        description: str | None = None
        if style != state.style:
            state.style = style
            fields[_STYLE_FIELD] = style
            description = f"[{style}]{state.description}"
        if description is not None:
            self._progress.update(task_id, completed=state.completed, description=description, **fields)
        else:
            self._progress.update(task_id, completed=state.completed, **fields)

    def _style_for(self, completed: int, total: int) -> str:
        """Return the transition style for a completed/total ratio."""
        percentage = min(100, int((completed / total) * 100)) if total else 0
        for threshold, (_text, bar_color) in sorted(self._colors.items()):
            if percentage <= threshold:
                return bar_color
        return next(reversed(list(self._colors.values())))[1]

    def _truncate(self, description: str) -> str:
        """Tail-truncate *description* to the configured maximum."""
        limit = self._max_description_length
        if len(description) <= limit:
            return description
        return description[: limit - len(_ELLIPSIS)] + _ELLIPSIS

    def _calculate_bar_width(self) -> int:
        """Fit the bar between the description and the info columns."""
        available = console.width - self._max_description_length - _BASE_INFO_WIDTH
        return max(_MIN_BAR_WIDTH, min(_MAX_BAR_WIDTH, available))
