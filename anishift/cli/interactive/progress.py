"""Interactive run progress backed by the shared Rich console components."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import islice
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol

from rich.text import Text

from anishift.application import (
    ArtifactKind,
    ExecutionPlan,
    InspectedSourceGroup,
    InspectedWorkspace,
    RunEvent,
    RunEventKind,
    TaskKind,
    TaskState,
)
from anishift.cli.interactive.mascot import MascotController
from anishift.cli.interactive.palette import hex_color, rim_color

__all__ = ["RichRunProgress"]

# ── Constants ─────────────────────────────────────────────────────────────────

_COMPLETE: Final[int] = 100
"""Percentage representing a completed stage."""

_PHASE_WIDTH: Final[int] = 14
"""Fixed phase width keeping filenames aligned."""

_DESCRIPTION_LENGTH: Final[int] = 72
"""Maximum description width on a wide terminal."""

_NARROW_DESCRIPTION_LENGTH: Final[int] = 35
"""Description width retained on an eighty-column terminal."""

_MAX_FILENAME_COLUMNS: Final[int] = 20
"""Largest filename rendered inside a progress description."""

_MAX_BAR_COLUMNS: Final[int] = 40
"""Largest shared block bar rendered on one row."""

_MIN_BAR_COLUMNS: Final[int] = 3
"""Smallest shared block bar rendered on one row."""

_BASE_INFO_COLUMNS: Final[int] = 23
"""Columns occupied by separators, percentage and elapsed time."""

_MINIMUM_PROGRESS_COLUMNS: Final[int] = _BASE_INFO_COLUMNS + _MIN_BAR_COLUMNS
"""Columns required after the description for a complete progress row."""

_DESCRIPTION_GROWTH_RESERVE: Final[int] = 48
"""Progress columns retained while a wide description grows."""

_WIDE_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _DESCRIPTION_GROWTH_RESERVE
"""Terminal width where the description may grow beyond its narrow size."""

_NARROW_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _MINIMUM_PROGRESS_COLUMNS
"""Terminal width fitting the narrow description and all progress fields."""

_STAGE_RANK: Final[dict[str, int]] = {
    "extracting": 0,
    "translating": 1,
    "tts": 2,
    "audio": 3,
    "composing": 4,
    "publishing": 5,
    "terminal": 6,
}
"""Public stage order preventing late callbacks from regressing a row."""

_DETERMINATE_STAGE: Final[dict[TaskKind, str]] = {
    TaskKind.EXTRACT_AUDIO: "extracting",
    TaskKind.EXTRACT_SUBTITLES: "extracting",
    TaskKind.EXTRACT_TRACKS: "extracting",
    TaskKind.TRANSLATE_SUBTITLES: "translating",
    TaskKind.SYNTHESIZE_SPEECH: "tts",
    TaskKind.NORMALIZE_SUBTITLES: "extracting",
    TaskKind.SPLIT_SUBTITLES: "translating",
    TaskKind.TRANSCODE_AUDIO: "audio",
    TaskKind.MIX_NARRATION: "audio",
    TaskKind.COMPOSE_MKV: "composing",
    TaskKind.COMPOSE_MP4: "composing",
    TaskKind.PUBLISH_ARTIFACT: "publishing",
}
"""Task kinds owning measurable public stages."""

_ACTIVE_LABEL: Final[dict[str, str]] = {
    "extracting": "Extracting",
    "translating": "Translating",
    "tts": "Synthesizing",
    "audio": "Audio processing",
    "composing": "Rendering",
    "publishing": "Publishing",
}
"""Labels shown while measurable stages are active."""

_COMPLETE_LABEL: Final[dict[str, str]] = {
    "extracting": "Extracted",
    "translating": "Translated",
}
"""Labels shown after extraction and translation complete."""

_AUDIO_LABEL: Final[dict[str, str]] = {
    "normalizing": "Normalizing",
    "timeline": "Audio timeline",
    "mixing": "Audio mixing",
    "narration_resume": "Audio resume",
    "skipped_no_spoken": "Audio skipped",
    "wrapping": "Narrator audio",
}
"""Labels for coarse audio callbacks."""


@dataclass(slots=True)
class _FileState:
    """Hold the complete public progress state of one input file."""

    label: str
    description: str
    stage_rank: int = 0
    progress_by_task: dict[str, int] = field(default_factory=dict)
    active_tasks: list[str] = field(default_factory=list)
    completed: int = 0
    terminal: bool = False
    style: str | None = None
    started_at: float | None = None
    stopped_at: float | None = None
    determinate: bool = True


@dataclass(frozen=True, slots=True)
class _RenderRow:
    """Carry an immutable row snapshot outside the state lock."""

    description: str
    completed: int
    style: str | None
    elapsed_seconds: float
    determinate: bool


class _PreparedRun(Protocol):
    """Describe the prepared run fields required by progress rendering."""

    @property
    def workspace(self) -> InspectedWorkspace:
        """Return inspected source groups."""
        ...

    @property
    def plan(self) -> ExecutionPlan:
        """Return the accepted execution plan."""
        ...


class RichRunProgress:
    """Reduce ordered run events to one shared Rich block bar per file."""

    def __init__(
        self,
        prepared: _PreparedRun,
        invalidate: Callable[[], None],
        on_run_started: Callable[[str], None] | None = None,
        *,
        mascot: MascotController | None = None,
    ) -> None:
        """Create naturally ordered file rows without taking over the terminal."""
        labels: dict[str, str] = {group.group_id: _source_label(group) for group in prepared.workspace.groups}
        self._files: dict[str, _FileState] = {
            group.group_id: _new_file_state(labels.get(group.group_id, group.group_id))
            for group in prepared.plan.groups
        }
        self._task_kinds: dict[str, TaskKind] = {task.task_id: task.kind for task in prepared.plan.tasks}
        self._stage_tasks: dict[tuple[str, str], tuple[str, ...]] = _index_stage_tasks(prepared)
        self._invalidate: Callable[[], None] = invalidate
        self._on_run_started: Callable[[str], None] | None = on_run_started
        self._mascot: MascotController | None = mascot
        self._lock: threading.Lock = threading.Lock()
        self._run_id: str | None = None
        self._last_sequence: int = 0
        self._open: bool = False

    @property
    def row_count(self) -> int:
        """Return the stable number of preallocated file rows."""
        return len(self._files)

    @property
    def run_id(self) -> str | None:
        """Return the accepted run identity, when one has arrived."""
        with self._lock:
            return self._run_id

    def __enter__(self) -> RichRunProgress:
        """Start accepting events and request the first frame."""
        with self._lock:
            self._open = True
        self._invalidate()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop accepting events while preserving the last frame."""
        del exc_type, exc_value, traceback
        with self._lock:
            self._open = False
        self._invalidate()

    def emit(self, event: RunEvent) -> None:
        """Apply one new event from the active run and invalidate on change."""
        started_run_id: str | None = None
        changed: bool = False
        with self._lock:
            if not self._open:
                return
            if self._run_id is None:
                self._run_id = event.run_id
                started_run_id = event.run_id
            if event.run_id != self._run_id or event.sequence <= self._last_sequence:
                return
            self._last_sequence = event.sequence
            changed = self._apply(event)
        if started_run_id is not None and self._on_run_started is not None:
            self._on_run_started(started_run_id)
        self._update_mascot(event)
        if changed:
            self._invalidate()

    @property
    def active_row(self) -> int:
        """Return the row index of the earliest file still doing work."""
        with self._lock:
            for index, state in enumerate(self._files.values()):
                if state.started_at is not None and not state.terminal:
                    return index
            return max(len(self._files) - 1, 0)

    def render(self, columns: int, *, offset: int = 0, limit: int | None = None) -> Text:
        """Render one width-fitted window of the queue through shared Rich bars."""
        now: float = time.monotonic()
        start: int = min(max(offset, 0), max(len(self._files) - 1, 0))
        end: int = len(self._files) if limit is None else start + max(limit, 0)
        with self._lock:
            rows: tuple[_RenderRow, ...] = tuple(
                _RenderRow(
                    state.description,
                    state.completed,
                    state.style,
                    _elapsed(state, now),
                    state.determinate,
                )
                for state in islice(self._files.values(), start, end)
            )
        return _render_rows(rows, columns)

    def _apply(self, event: RunEvent) -> bool:
        changed: bool = False
        if event.kind is RunEventKind.RUN_FINISHED:
            changed = self._finish_remaining(event.state)
        elif event.group_id is not None:
            state: _FileState | None = self._files.get(event.group_id)
            if state is not None and not state.terminal:
                _start_timer(state)
                match event.kind:
                    case RunEventKind.TASK_STARTED:
                        changed = self._start_task(state, event)
                    case RunEventKind.TASK_PROGRESS:
                        changed = self._update_task(event.group_id, state, event)
                    case RunEventKind.TASK_RETRY:
                        changed = self._retry_task(state, event)
                    case RunEventKind.TASK_FINISHED:
                        changed = self._finish_task(event.group_id, state, event)
                    case RunEventKind.GROUP_FINISHED:
                        self._finish_group(state, event.state)
                        changed = True
                    case _:
                        pass
        return changed

    def _start_task(self, state: _FileState, event: RunEvent) -> bool:
        if event.task_id is None:
            return False
        if event.task_id not in state.active_tasks:
            state.active_tasks.append(event.task_id)
        return self._show_active_task(state)

    def _show_active_task(self, state: _FileState) -> bool:
        """Keep background publication from hiding active media work."""
        candidates: list[str] = [task_id for task_id in state.active_tasks if _stage_for(self._task_kinds.get(task_id))]
        if not candidates:
            return False
        primary: list[str] = [
            task_id for task_id in candidates if self._task_kinds[task_id] is not TaskKind.PUBLISH_ARTIFACT
        ]
        selected: str = max(
            primary or candidates,
            key=lambda task_id: _STAGE_RANK[_stage_for(self._task_kinds[task_id]) or "extracting"],
        )
        stage: str | None = _stage_for(self._task_kinds[selected])
        if stage is None:
            return False
        state.stage_rank = _STAGE_RANK[stage]
        state.completed = state.progress_by_task.get(selected, 0)
        state.description = _description(state.label, _ACTIVE_LABEL[stage])
        state.style = None
        state.determinate = selected in state.progress_by_task
        return True

    def _update_task(self, group_id: str, state: _FileState, event: RunEvent) -> bool:
        if event.task_id is None:
            return False
        kind: TaskKind | None = self._task_kinds.get(event.task_id)
        if event.progress_percent is None:
            return self._show_activity(state, kind, event.message)
        if kind in {TaskKind.TRANSCODE_AUDIO, TaskKind.MIX_NARRATION} and event.message in _AUDIO_LABEL:
            state.progress_by_task[event.task_id] = event.progress_percent
            return self._show_audio_phase(state, event.message, event.progress_percent)
        stage = _stage_for(kind)
        if stage is None:
            return False
        previous: int = state.progress_by_task.get(event.task_id, 0)
        state.progress_by_task[event.task_id] = (
            max(previous, event.progress_percent) if stage == "tts" else event.progress_percent
        )
        if _STAGE_RANK[stage] != state.stage_rank:
            return False
        if stage == "tts":
            state.completed = max(state.completed, event.progress_percent)
        else:
            state.completed = event.progress_percent
        phase: str = _ACTIVE_LABEL[stage]
        if stage in _COMPLETE_LABEL and _stage_complete(group_id, stage, state, self._stage_tasks):
            phase = _COMPLETE_LABEL[stage]
        state.description = _description(state.label, phase)
        state.style = None
        state.determinate = True
        return True

    def _show_activity(self, state: _FileState, kind: TaskKind | None, message: str | None) -> bool:
        """Display an active phase without inventing a completion percentage."""
        stage: str | None = _stage_for(kind)
        if stage is None or _STAGE_RANK[stage] != state.stage_rank:
            return False
        state.determinate = False
        state.description = _description(state.label, _AUDIO_LABEL.get(message or "", _ACTIVE_LABEL[stage]))
        return True

    def _retry_task(self, state: _FileState, event: RunEvent) -> bool:
        if event.task_id is None or self._task_kinds.get(event.task_id) not in {
            TaskKind.SYNTHESIZE_SPEECH,
            TaskKind.TRANSLATE_SUBTITLES,
        }:
            return False
        state.description = _description(state.label, "Retrying")
        state.style = "warning"
        state.determinate = False
        return True

    def _finish_task(self, group_id: str, state: _FileState, event: RunEvent) -> bool:
        if event.task_id in state.active_tasks:
            state.active_tasks.remove(event.task_id)
        if event.task_id is None or event.state is not TaskState.SUCCEEDED:
            return False
        state.progress_by_task[event.task_id] = _COMPLETE
        if state.active_tasks:
            return self._show_active_task(state)
        stage: str | None = _stage_for(self._task_kinds.get(event.task_id))
        if stage is None or _STAGE_RANK[stage] != state.stage_rank:
            return False
        state.completed = _COMPLETE
        phase: str = _ACTIVE_LABEL[stage]
        if _stage_complete(group_id, stage, state, self._stage_tasks):
            phase = _COMPLETE_LABEL.get(stage, phase)
        state.description = _description(state.label, phase)
        state.style = None
        state.determinate = True
        return True

    def _show_audio_phase(self, state: _FileState, phase: str, percent: int) -> bool:
        if state.stage_rank > _STAGE_RANK["audio"]:
            return False
        state.stage_rank = _STAGE_RANK["audio"]
        state.completed = percent
        state.determinate = percent > 0
        state.description = _description(state.label, _AUDIO_LABEL[phase])
        state.style = None
        return True

    def _finish_group(self, state: _FileState, task_state: TaskState | None) -> None:
        state.terminal = True
        state.determinate = True
        state.stage_rank = _STAGE_RANK["terminal"]
        _stop_timer(state)
        if task_state is TaskState.SUCCEEDED:
            state.description = _description(state.label, "Done")
            state.completed = _COMPLETE
            state.style = "success"
            return
        state.completed = 0
        if task_state is TaskState.CANCELLED:
            state.description = _description(state.label, "Cancelled")
            state.style = "warning"
            return
        state.description = _description(state.label, "Failed")
        state.style = "error"

    def _finish_remaining(self, task_state: TaskState | None) -> bool:
        changed: bool = False
        for state in self._files.values():
            if state.terminal:
                continue
            state.terminal = True
            state.determinate = True
            state.stage_rank = _STAGE_RANK["terminal"]
            state.completed = 0
            _stop_timer(state)
            if task_state is TaskState.CANCELLED:
                state.description = _description(state.label, "Cancelled")
                state.style = "warning"
            else:
                state.description = _description(state.label, "Not processed")
                state.style = "error"
            changed = True
        return changed

    def _update_mascot(self, event: RunEvent) -> None:
        mascot: MascotController | None = self._mascot
        if mascot is None:
            return
        if event.kind is RunEventKind.RUN_FINISHED:
            mascot.run_finished(event.state)
            return
        if event.task_id is None:
            return
        if event.kind is RunEventKind.TASK_FINISHED:
            mascot.task_finished(event.task_id, event.state)
            return
        if event.kind is RunEventKind.TASK_STARTED:
            kind: TaskKind | None = self._task_kinds.get(event.task_id)
            if kind is not None:
                mascot.task_started(event.task_id, kind)


def _new_file_state(label: str) -> _FileState:
    """Create the initial extracting row for one source label."""
    return _FileState(label=label, description=_description(label, "Extracting"))


def _render_rows(rows: tuple[_RenderRow, ...], columns: int) -> Text:
    """Render all file snapshots into one Rich text block."""
    result = Text()
    if not rows:
        return result
    description_limit: int = _description_limit(columns)
    natural_width: int = max(len(row.description) for row in rows)
    description_width: int = min(natural_width, description_limit)
    bar_width: int = _bar_width(columns, description_width)
    for index, row in enumerate(rows):
        _append_row(result, row, description_width, bar_width)
        if index < len(rows) - 1:
            result.append("\n")
    return result


def _append_row(result: Text, row: _RenderRow, description_width: int, bar_width: int) -> None:
    """Append measured progress or an honest activity indicator."""
    style: str = row.style or "brand_accent"
    description: str = _truncate(row.description, description_width).ljust(description_width)
    result.append(description, style=style)
    result.append(" ")
    colors: tuple[str, ...] = _bar_colors(bar_width)
    filled: int = min(bar_width, max(0, row.completed) * bar_width // _COMPLETE)
    cursor: int = int(row.elapsed_seconds * 8) % bar_width
    for index, color in enumerate(colors):
        active: bool = index < filled if row.determinate else index == cursor
        result.append("█" if active else "░", style=(row.style or color) if active else "gray")
    result.append(f" | {row.completed:>3d}%" if row.determinate else " |  -- ", style=style)
    result.append(f" | {_format_elapsed(row.elapsed_seconds)}", style=style)


@lru_cache(maxsize=_MAX_BAR_COLUMNS)
def _bar_colors(width: int) -> tuple[str, ...]:
    """Cache the wordmark palette at each bounded bar width."""
    return tuple(hex_color(rim_color(index / max(width - 1, 1))) for index in range(width))


def _description_limit(columns: int) -> int:
    """Resolve a description width that keeps every row on one line."""
    if columns >= _WIDE_LAYOUT_COLUMNS:
        return min(_DESCRIPTION_LENGTH, columns - _DESCRIPTION_GROWTH_RESERVE)
    if columns >= _NARROW_LAYOUT_COLUMNS:
        return _NARROW_DESCRIPTION_LENGTH
    return max(5, columns - _MINIMUM_PROGRESS_COLUMNS)


def _bar_width(columns: int, description_width: int) -> int:
    """Resolve the shared bar width from remaining terminal columns."""
    available: int = columns - description_width - _BASE_INFO_COLUMNS
    return max(_MIN_BAR_COLUMNS, min(_MAX_BAR_COLUMNS, available))


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a fixed-width clock with milliseconds."""
    hours: int = int(seconds // 3600)
    minutes: int = int((seconds % 3600) // 60)
    whole_seconds: int = int(seconds % 60)
    milliseconds: int = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _start_timer(state: _FileState) -> None:
    """Start one row timer once."""
    if state.started_at is None:
        state.started_at = time.monotonic()


def _stop_timer(state: _FileState) -> None:
    """Freeze one row timer."""
    stopped_at: float = time.monotonic()
    if state.started_at is None:
        state.started_at = stopped_at
    state.stopped_at = stopped_at


def _elapsed(state: _FileState, now: float) -> float:
    """Return the non-negative elapsed time of one row."""
    if state.started_at is None:
        return 0
    return max((state.stopped_at or now) - state.started_at, 0)


def _truncate(value: str, width: int) -> str:
    """Truncate text with a single ellipsis to the requested width."""
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _stage_for(kind: TaskKind | None) -> str | None:
    """Return the public measurable stage for a task kind."""
    if kind is None:
        return None
    return _DETERMINATE_STAGE.get(kind)


def _index_stage_tasks(prepared: _PreparedRun) -> dict[tuple[str, str], tuple[str, ...]]:
    """Index measurable task IDs by source group and public stage."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for task in prepared.plan.tasks:
        stage: str | None = _stage_for(task.kind)
        if stage is not None:
            grouped.setdefault((task.group_id, stage), []).append(task.task_id)
    return {key: tuple(task_ids) for key, task_ids in grouped.items()}


def _stage_complete(
    group_id: str,
    stage: str,
    state: _FileState,
    stage_tasks: dict[tuple[str, str], tuple[str, ...]],
) -> bool:
    """Return whether every task behind one public stage completed."""
    task_ids: tuple[str, ...] = stage_tasks.get((group_id, stage), ())
    return bool(task_ids) and all(state.progress_by_task.get(task_id, 0) >= _COMPLETE for task_id in task_ids)


def _source_label(group: InspectedSourceGroup) -> str:
    """Return a compact concrete filename for one inspected source group."""
    preferred_kinds: tuple[ArtifactKind, ...] = (
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.VIDEO_MP4,
        ArtifactKind.STANDALONE_TEXT,
    )
    for kind in preferred_kinds:
        path: Path | None = next(
            (artifact.path for artifact in group.artifacts if artifact.kind is kind and artifact.path is not None),
            None,
        )
        if path is not None:
            return _short_filename(path.name)
    return _short_filename(group.source.stem)


def _short_filename(filename: str) -> str:
    """Shorten a filename while retaining a compact extension when possible."""
    if len(filename) <= _MAX_FILENAME_COLUMNS:
        return filename
    suffix: str = Path(filename).suffix
    if suffix and len(suffix) < _MAX_FILENAME_COLUMNS // 2:
        stem_width: int = _MAX_FILENAME_COLUMNS - len(suffix) - 1
        return f"{filename[:stem_width]}…{suffix}"
    return f"{filename[: _MAX_FILENAME_COLUMNS - 1]}…"


def _description(label: str, phase: str) -> str:
    """Build an aligned public phase and source description."""
    return f"{phase:<{_PHASE_WIDTH}} {label}"
