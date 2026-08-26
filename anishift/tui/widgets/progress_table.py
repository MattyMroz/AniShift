"""The one table the shell watches an active run in, folded from the events it emitted."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application import RunEventKind, TaskState
from anishift.application.events import sanitize_event_message
from anishift.tui.state import RunUiState
from anishift.tui.strings import (
    EXECUTION_CANCELLED_GLYPH,
    EXECUTION_DONE_GLYPH,
    EXECUTION_EMPTY,
    EXECUTION_FAILED_GLYPH,
    EXECUTION_FALLBACK_WORD,
    EXECUTION_FILTER_ALL,
    EXECUTION_FILTER_DONE,
    EXECUTION_FILTER_LABEL,
    EXECUTION_PERCENT,
    EXECUTION_RETRY_WORD,
    EXECUTION_RUNNING_GLYPH,
    EXECUTION_STATE_CANCELLED,
    EXECUTION_STATE_DONE,
    EXECUTION_STATE_FAILED,
    EXECUTION_STATE_RUNNING,
    EXECUTION_STATE_WAITING,
    EXECUTION_SUMMARY,
    EXECUTION_WAITING_GLYPH,
    GLYPH_GAP,
    GROUP_COLUMN_GAP,
    PLAN_INDENT,
    STATUS_GLYPH,
    TOOLS_RUN_CANCELLING,
)
from anishift.tui.widgets.plan_view import operation_label

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from anishift.application import RunEvent
    from anishift.tui.state import SessionState

__all__ = [
    "PERCENT_WIDTH",
    "ProgressFilter",
    "ProgressRow",
    "RowState",
    "listed_rows",
    "next_filter",
    "progress_body",
    "progress_rows",
]

# ── Constants ──────────────────────────────────────────────────────────────

PERCENT_WIDTH: Final[int] = 4
"""Columns the progress cell takes, so every percentage ends on one edge."""

_FULL_PERCENT: Final[int] = 100
"""Progress a group that finished its work reports, whatever its last event said."""

_TASK_PREFIX: Final[str] = "task-"
"""Prefix every task id carries in front of the operation that task runs."""

_TASK_DIGEST_GAP: Final[str] = "-"
"""Separator between the operation of one task id and the digest making it unique."""


class RowState(StrEnum):
    """What the events of one run say about the group of one row."""

    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProgressFilter(StrEnum):
    """Which of the folded rows a table currently lists."""

    ALL = "all"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"


_STATE_GLYPHS: Final[Mapping[RowState, str]] = MappingProxyType(
    {
        RowState.WAITING: EXECUTION_WAITING_GLYPH,
        RowState.RUNNING: EXECUTION_RUNNING_GLYPH,
        RowState.DONE: EXECUTION_DONE_GLYPH,
        RowState.FAILED: EXECUTION_FAILED_GLYPH,
        RowState.CANCELLED: EXECUTION_CANCELLED_GLYPH,
    },
)
"""Glyph every row state is marked with, so colour is never the only signal."""

_STATE_WORDS: Final[Mapping[RowState, str]] = MappingProxyType(
    {
        RowState.WAITING: EXECUTION_STATE_WAITING,
        RowState.RUNNING: EXECUTION_STATE_RUNNING,
        RowState.DONE: EXECUTION_STATE_DONE,
        RowState.FAILED: EXECUTION_STATE_FAILED,
        RowState.CANCELLED: EXECUTION_STATE_CANCELLED,
    },
)
"""Word every row state is named by."""

_FILTER_WORDS: Final[Mapping[ProgressFilter, str]] = MappingProxyType(
    {
        ProgressFilter.ALL: EXECUTION_FILTER_ALL,
        ProgressFilter.RUNNING: EXECUTION_STATE_RUNNING,
        ProgressFilter.FAILED: EXECUTION_STATE_FAILED,
        ProgressFilter.DONE: EXECUTION_FILTER_DONE,
    },
)
"""Word every filter is named by, in the row saying what the table hides."""

_TASK_STATES: Final[Mapping[TaskState, RowState]] = MappingProxyType(
    {
        TaskState.SUCCEEDED: RowState.DONE,
        TaskState.FAILED: RowState.FAILED,
        TaskState.CANCELLED: RowState.CANCELLED,
    },
)
"""Row state every terminal task state of the domain turns into."""

_TERMINAL_STATES: Final[frozenset[RowState]] = frozenset(
    {RowState.DONE, RowState.FAILED, RowState.CANCELLED},
)
"""Row states no later event of the same run may leave again."""

_FILTER_STATES: Final[Mapping[ProgressFilter, frozenset[RowState]]] = MappingProxyType(
    {
        ProgressFilter.RUNNING: frozenset({RowState.RUNNING}),
        ProgressFilter.FAILED: frozenset({RowState.FAILED}),
        ProgressFilter.DONE: _TERMINAL_STATES,
    },
)
"""Row states every narrowing filter keeps; the ``ALL`` filter keeps every row."""

_FILTER_ORDER: Final[tuple[ProgressFilter, ...]] = (
    ProgressFilter.ALL,
    ProgressFilter.RUNNING,
    ProgressFilter.FAILED,
    ProgressFilter.DONE,
)
"""Order one filter key walks the filters in, back to the first one after the last."""

_WORKING_KINDS: Final[frozenset[RunEventKind]] = frozenset(
    {RunEventKind.TASK_STARTED, RunEventKind.TASK_PROGRESS},
)
"""Event kinds saying one group is working right now, on the task they name."""

_DETAIL_KINDS: Final[Mapping[RunEventKind, str]] = MappingProxyType(
    {
        RunEventKind.TASK_RETRY: EXECUTION_RETRY_WORD,
        RunEventKind.TASK_FALLBACK: EXECUTION_FALLBACK_WORD,
    },
)
"""Word opening the detail line every reported recovery leaves behind."""


@dataclass(frozen=True, slots=True)
class ProgressRow:
    """What the events of one run say about one group of it."""

    group_id: str
    state: RowState = RowState.WAITING
    task: str = ""
    percent: int = 0
    details: tuple[str, ...] = ()


def progress_rows(events: Sequence[RunEvent]) -> tuple[ProgressRow, ...]:
    """Fold *events* into one row per group, in the order the run first named them."""
    rows: dict[str, ProgressRow] = {}
    for event in sorted(events, key=_sequence_of):
        rows = _folded(rows, event)
    return tuple(rows.values())


def listed_rows(rows: Sequence[ProgressRow], listed: ProgressFilter) -> tuple[ProgressRow, ...]:
    """Return the rows *listed* keeps, leaving the folded rows themselves untouched."""
    kept: frozenset[RowState] | None = _FILTER_STATES.get(listed)
    if kept is None:
        return tuple(rows)
    return tuple(row for row in rows if row.state in kept)


def next_filter(listed: ProgressFilter) -> ProgressFilter:
    """Return the filter one filter key moves to, wrapping after the last one."""
    following: int = (_FILTER_ORDER.index(listed) + 1) % len(_FILTER_ORDER)
    return _FILTER_ORDER[following]


def progress_body(state: SessionState, *, listed: ProgressFilter = ProgressFilter.ALL, details: bool = False) -> str:
    """Render the run *state* holds the events of, narrowed to *listed*."""
    rows: tuple[ProgressRow, ...] = progress_rows(state.events)
    if not rows:
        return EXECUTION_EMPTY
    header: list[str] = _header(rows, listed=listed, cancelling=state.run_state is RunUiState.CANCELLING)
    kept: tuple[ProgressRow, ...] = listed_rows(rows, listed)
    widths: tuple[int, int, int] = _widths(kept)
    body: list[str] = [line for row in kept for line in (_row_line(row, widths), *_detail_lines(row, details=details))]
    return "\n".join([*header, "", *body])


def _header(rows: Sequence[ProgressRow], *, listed: ProgressFilter, cancelling: bool) -> list[str]:
    """Return how much of the run is behind it, then the cancel and the filter rows."""
    done: int = sum(1 for row in rows if row.state in _TERMINAL_STATES)
    lines: list[str] = [EXECUTION_SUMMARY.format(done=done, total=len(rows))]
    if cancelling:
        lines.append(f"{STATUS_GLYPH}{GLYPH_GAP}{TOOLS_RUN_CANCELLING}")
    if listed is not ProgressFilter.ALL:
        lines.append(f"{EXECUTION_FILTER_LABEL}{GLYPH_GAP}{_FILTER_WORDS[listed]}")
    return lines


def _row_line(row: ProgressRow, widths: tuple[int, int, int]) -> str:
    """Return one row: its glyph, its group, the word of its state, its task and its progress."""
    cells: tuple[str, ...] = (
        row.group_id.ljust(widths[0]),
        _STATE_WORDS[row.state].ljust(widths[1]),
        row.task.ljust(widths[2]),
        EXECUTION_PERCENT.format(percent=row.percent).rjust(PERCENT_WIDTH),
    )
    return f"{_STATE_GLYPHS[row.state]}{GLYPH_GAP}{GROUP_COLUMN_GAP.join(cells)}"


def _detail_lines(row: ProgressRow, *, details: bool) -> tuple[str, ...]:
    """Return every detail of *row* while it is expanded, and its last one while it is not."""
    if not row.details:
        return ()
    shown: tuple[str, ...] = row.details if details else row.details[-1:]
    return tuple(f"{PLAN_INDENT}{line}" for line in shown)


def _widths(rows: Sequence[ProgressRow]) -> tuple[int, int, int]:
    """Return the columns the group, the state word and the task of one row each take."""
    if not rows:
        return (0, 0, 0)
    return (
        max(len(row.group_id) for row in rows),
        max(len(_STATE_WORDS[row.state]) for row in rows),
        max(len(row.task) for row in rows),
    )


def _folded(rows: Mapping[str, ProgressRow], event: RunEvent) -> dict[str, ProgressRow]:
    """Return the rows one event leaves behind, opening a row for a group not seen yet."""
    if event.kind is RunEventKind.RUN_FINISHED:
        return _closed(rows, _row_state(event.state, RowState.DONE))
    if event.group_id is None:
        return dict(rows)
    folded: dict[str, ProgressRow] = dict(rows)
    row: ProgressRow = folded.get(event.group_id, ProgressRow(event.group_id))
    folded[event.group_id] = row if row.state in _TERMINAL_STATES else _advanced(row, event)
    return folded


def _advanced(row: ProgressRow, event: RunEvent) -> ProgressRow:
    """Return the row one event of its own group leaves behind."""
    detail: str | None = _detail_of(event)
    if detail is not None:
        return replace(row, details=(*row.details, detail))
    if event.kind is RunEventKind.GROUP_FINISHED:
        return _ended(row, _row_state(event.state, RowState.DONE))
    if event.kind not in _WORKING_KINDS:
        return row
    return replace(
        row,
        state=RowState.RUNNING,
        task=_task_label(event.task_id) or row.task,
        percent=row.percent if event.progress_percent is None else event.progress_percent,
    )


def _closed(rows: Mapping[str, ProgressRow], state: RowState) -> dict[str, ProgressRow]:
    """Return every row of a run that ended, none of them left mid-flight."""
    return {group_id: row if row.state in _TERMINAL_STATES else _ended(row, state) for group_id, row in rows.items()}


def _ended(row: ProgressRow, state: RowState) -> ProgressRow:
    """Return the row of a group that reached *state*, full only once it is done."""
    percent: int = _FULL_PERCENT if state is RowState.DONE else row.percent
    return replace(row, state=state, percent=percent)


def _row_state(state: TaskState | None, fallback: RowState) -> RowState:
    """Return the row state one reported task state means, or *fallback* without one."""
    if state is None:
        return fallback
    return _TASK_STATES.get(state, fallback)


def _detail_of(event: RunEvent) -> str | None:
    """Return the detail line one reported recovery leaves, or nothing for every other event."""
    word: str | None = _DETAIL_KINDS.get(event.kind)
    if word is None:
        return None
    message: str = sanitize_event_message(event.message) or ""
    return f"{word}{GROUP_COLUMN_GAP}{message}" if message else word


def _task_label(task_id: str | None) -> str | None:
    """Return the human label of the operation one task id names, without any plan."""
    if task_id is None:
        return None
    kind: str = task_id.removeprefix(_TASK_PREFIX).rpartition(_TASK_DIGEST_GAP)[0]
    return operation_label(kind or task_id)


def _sequence_of(event: RunEvent) -> int:
    """Return the one order the events of a run fold in, whatever order they arrived in."""
    return event.sequence
