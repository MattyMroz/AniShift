"""State-only Rich progress rows for the interactive renderer."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final, Literal

from rich.text import Text

from anishift.application import ArtifactKind, InspectedSourceGroup, RunEvent, RunEventKind, TaskKind, TaskState
from anishift.cli.run import PreparedAutoRun
from anishift.utils.rich_console.progress.manager import ProgressBarBuilder

__all__ = ["RichRunProgress"]

# ── Constants ─────────────────────────────────────────────────────────────────

_PHASE_WIDTH: Final[int] = 14
"""Fixed phase width keeping filenames aligned."""

_COMPLETE: Final[int] = 100
"""Completed percentage used by determinate rows."""

_DESCRIPTION_LENGTH: Final[int] = 72
"""Maximum stage, provider, voice and filename width."""

_NARROW_DESCRIPTION_LENGTH: Final[int] = 35
"""Readable description width that still fits one row at 80 columns."""

_MAX_BAR_COLUMNS: Final[int] = 40
"""Largest block bar rendered on one terminal row."""

_MIN_BAR_COLUMNS: Final[int] = 3
"""Smallest useful block bar rendered on one terminal row."""

_BASE_INFO_COLUMNS: Final[int] = 23
"""Columns occupied by spacing, percentage and elapsed time."""

_MINIMUM_PROGRESS_COLUMNS: Final[int] = _BASE_INFO_COLUMNS + _MIN_BAR_COLUMNS
"""Columns required after a description to keep every progress field visible."""

_DESCRIPTION_GROWTH_RESERVE: Final[int] = 48
"""Progress columns retained while a wide description grows."""

_WIDE_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _DESCRIPTION_GROWTH_RESERVE
"""Terminal width where the description may grow beyond its narrow size."""

_NARROW_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _MINIMUM_PROGRESS_COLUMNS
"""Terminal width fitting the narrow description and every progress field."""

_MAX_FILENAME_COLUMNS: Final[int] = 20
"""Largest filename shown inside a progress description."""

_PROGRESS_STYLES: Final[tuple[tuple[int, str], ...]] = (
    (25, "red_bold"),
    (50, "orange_bold"),
    (75, "yellow_bold"),
    (100, "green_bold"),
)
"""Established red-to-green progress thresholds and Rich styles."""

_STAGE_RANK: Final[dict[str, int]] = {
    "extracting": 0,
    "translating": 1,
    "tts": 2,
    "audio": 3,
    "terminal": 4,
}
"""Stage precedence preventing late callbacks from regressing rows."""

_DETERMINATE_STAGE: Final[dict[TaskKind, Literal["extracting", "translating", "tts"]]] = {
    TaskKind.EXTRACT_AUDIO: "extracting",
    TaskKind.EXTRACT_SUBTITLES: "extracting",
    TaskKind.EXTRACT_TRACKS: "extracting",
    TaskKind.TRANSLATE_SUBTITLES: "translating",
    TaskKind.SYNTHESIZE_SPEECH: "tts",
}
"""Task kinds that own determinate stages."""

_ACTIVE_LABEL: Final[dict[str, str]] = {
    "extracting": "Extracting",
    "translating": "Translating",
    "tts": "Synthesizing",
}
"""Labels shown while determinate work is active."""

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
}
"""Labels for coarse audio callbacks."""


@dataclass(slots=True)
class _FileProgressState:
    """Track the presentation state of one input file."""

    label: str
    stage: str = "extracting"
    stage_rank: int = 0
    progress_by_task: dict[str, int] = field(default_factory=dict)
    completed: int = 0
    description: str = ""
    terminal: bool = False
    style: str | None = None
    started_at: float | None = None
    stopped_at: float | None = None


@dataclass(frozen=True, slots=True)
class _RenderRow:
    """Carry one immutable progress-row snapshot."""

    description: str
    completed: int
    style: str | None
    elapsed_seconds: float


class RichRunProgress:
    """Reduce run events to Rich rows without owning terminal rendering."""

    def __init__(
        self,
        prepared: PreparedAutoRun,
        invalidate: Callable[[], None],
        on_run_started: Callable[[str], None] | None = None,
    ) -> None:
        labels: dict[str, str] = {group.group_id: _source_label(group) for group in prepared.workspace.groups}
        self._files: dict[str, _FileProgressState] = {
            group.group_id: _FileProgressState(
                label=labels.get(group.group_id, group.group_id),
                description=_description(labels.get(group.group_id, group.group_id), "Extracting"),
            )
            for group in prepared.plan.groups
        }
        self._task_kind: dict[str, TaskKind] = {task.task_id: task.kind for task in prepared.plan.tasks}
        self._stage_tasks: dict[tuple[str, str], tuple[str, ...]] = _index_stage_tasks(prepared)
        self._invalidate: Callable[[], None] = invalidate
        self._on_run_started: Callable[[str], None] | None = on_run_started
        self._lock: threading.Lock = threading.Lock()
        self._run_id: str | None = None
        self._last_sequence: int = 0
        self._open: bool = False

    @property
    def row_count(self) -> int:
        """Return the stable number of file rows."""
        return len(self._files)

    @property
    def run_id(self) -> str | None:
        """Return the active application run identity when known."""
        with self._lock:
            return self._run_id

    def __enter__(self) -> RichRunProgress:
        """Open event acceptance and request the initial frame."""
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
        """Close event acceptance while retaining the final rows."""
        del exc_type, exc_value, traceback
        with self._lock:
            self._open = False
        self._invalidate()

    def emit(self, event: RunEvent) -> None:
        """Apply one ordered run event and invalidate the shared screen."""
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
            changed = self._apply_event(event)
        if started_run_id is not None and self._on_run_started is not None:
            self._on_run_started(started_run_id)
        if changed:
            self._invalidate()

    def render(self, columns: int) -> Text:
        """Build width-fitted Rich rows from one locked state snapshot."""
        now: float = time.monotonic()
        with self._lock:
            rows: tuple[_RenderRow, ...] = tuple(
                _RenderRow(
                    state.description,
                    state.completed,
                    state.style,
                    _elapsed_seconds(state, now),
                )
                for state in self._files.values()
            )
        return _render_rows(rows, columns)

    def _apply_event(self, event: RunEvent) -> bool:
        if event.kind is RunEventKind.RUN_FINISHED:
            return self._finish_remaining(event.state)
        if event.group_id is None:
            return False
        state: _FileProgressState | None = self._files.get(event.group_id)
        if state is None or state.terminal:
            return False
        _start_timer(state)
        changed: bool = False
        match event.kind:
            case RunEventKind.TASK_STARTED:
                changed = self._task_started(state, event)
            case RunEventKind.TASK_PROGRESS:
                changed = self._task_progress(event.group_id, state, event)
            case RunEventKind.TASK_RETRY:
                changed = self._task_retry(state, event)
            case RunEventKind.TASK_FINISHED:
                changed = self._task_finished(event.group_id, state, event)
            case RunEventKind.GROUP_FINISHED:
                self._group_finished(state, event.state)
                changed = True
            case _:
                pass
        return changed

    def _task_started(self, state: _FileProgressState, event: RunEvent) -> bool:
        if event.task_id is None:
            return False
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None:
            return False
        rank: int = _STAGE_RANK[stage]
        if rank < state.stage_rank:
            return False
        if rank > state.stage_rank:
            state.progress_by_task.clear()
            state.completed = 0
        state.stage = stage
        state.stage_rank = rank
        state.progress_by_task.setdefault(event.task_id, 0)
        state.description = _description(state.label, _ACTIVE_LABEL[stage])
        state.style = None
        return True

    def _task_progress(self, group_id: str, state: _FileProgressState, event: RunEvent) -> bool:
        if event.task_id is None or event.progress_percent is None:
            return False
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        if kind in {TaskKind.TRANSCODE_AUDIO, TaskKind.MIX_NARRATION} and event.message in _AUDIO_LABEL:
            return self._audio_phase(state, event.message)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None or _STAGE_RANK[stage] < state.stage_rank:
            return False
        previous: int = state.progress_by_task.get(event.task_id, 0)
        state.progress_by_task[event.task_id] = max(previous, event.progress_percent)
        if stage == "tts":
            state.completed = max(state.completed, event.progress_percent)
        else:
            state.completed = event.progress_percent
        phase: str = _ACTIVE_LABEL[stage]
        if _stage_is_complete(group_id, stage, state, self._stage_tasks) and stage in _COMPLETE_LABEL:
            phase = _COMPLETE_LABEL[stage]
        state.description = _description(state.label, phase)
        state.style = None
        return True

    def _task_retry(self, state: _FileProgressState, event: RunEvent) -> bool:
        if event.task_id is None or self._task_kind.get(event.task_id) is not TaskKind.SYNTHESIZE_SPEECH:
            return False
        state.description = _description(state.label, "Retrying")
        state.style = "warning"
        return True

    def _task_finished(self, group_id: str, state: _FileProgressState, event: RunEvent) -> bool:
        if event.task_id is None or event.state is not TaskState.SUCCEEDED:
            return False
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None or _STAGE_RANK[stage] < state.stage_rank:
            return False
        state.progress_by_task[event.task_id] = _COMPLETE
        state.completed = _COMPLETE
        phase: str = (
            _COMPLETE_LABEL.get(stage, _ACTIVE_LABEL[stage])
            if _stage_is_complete(group_id, stage, state, self._stage_tasks)
            else _ACTIVE_LABEL[stage]
        )
        state.description = _description(state.label, phase)
        state.style = None
        return True

    def _audio_phase(self, state: _FileProgressState, phase: str) -> bool:
        if state.stage_rank > _STAGE_RANK["audio"]:
            return False
        state.stage = "audio"
        state.stage_rank = _STAGE_RANK["audio"]
        state.completed = 0
        state.description = _description(state.label, _AUDIO_LABEL[phase])
        state.style = None
        return True

    def _group_finished(self, state: _FileProgressState, task_state: TaskState | None) -> None:
        state.terminal = True
        state.stage = "terminal"
        state.stage_rank = _STAGE_RANK["terminal"]
        _stop_timer(state)
        if task_state is TaskState.SUCCEEDED:
            state.description = _description(state.label, "Done")
            state.completed = _COMPLETE
            state.style = "success"
        elif task_state is TaskState.CANCELLED:
            state.description = _description(state.label, "Cancelled")
            state.completed = 0
            state.style = "warning"
        else:
            state.description = _description(state.label, "Failed")
            state.completed = 0
            state.style = "error"

    def _finish_remaining(self, task_state: TaskState | None) -> bool:
        changed: bool = False
        for state in self._files.values():
            if state.terminal:
                continue
            state.terminal = True
            state.stage = "terminal"
            state.stage_rank = _STAGE_RANK["terminal"]
            _stop_timer(state)
            state.completed = 0
            if task_state is TaskState.CANCELLED:
                state.description = _description(state.label, "Cancelled")
                state.style = "warning"
            else:
                state.description = _description(state.label, "Not processed")
                state.style = "error"
            changed = True
        return changed


def _render_rows(rows: tuple[_RenderRow, ...], columns: int) -> Text:
    result = Text()
    if not rows:
        return result
    description_limit: int = _responsive_description_length(columns)
    natural_description: int = max(len(row.description) for row in rows)
    description_columns: int = min(natural_description, description_limit)
    bar_columns: int = _bar_width(columns, description_columns)
    for index, row in enumerate(rows):
        _append_row(result, row, description_columns, bar_columns)
        if index < len(rows) - 1:
            result.append("\n")
    return result


def _append_row(
    result: Text,
    row: _RenderRow,
    description_columns: int,
    bar_columns: int,
) -> None:
    style: str = row.style or _progress_style(row.completed)
    description: str = _truncate(row.description, description_columns).ljust(description_columns)
    result.append(description, style=style)
    result.append(" ")
    bar_markup: str = ProgressBarBuilder.blocks(bar_columns, row.completed / _COMPLETE, style)
    result.append_text(Text.from_markup(bar_markup))
    result.append(f" | {row.completed:>3d}%", style=style)
    result.append(f" | {_format_elapsed(row.elapsed_seconds)}", style=style)


def _progress_style(completed: int) -> str:
    for threshold, style in _PROGRESS_STYLES:
        if completed <= threshold:
            return style
    return "green_bold"


def _responsive_description_length(terminal_columns: int) -> int:
    if terminal_columns >= _WIDE_LAYOUT_COLUMNS:
        return min(_DESCRIPTION_LENGTH, terminal_columns - _DESCRIPTION_GROWTH_RESERVE)
    if terminal_columns >= _NARROW_LAYOUT_COLUMNS:
        return _NARROW_DESCRIPTION_LENGTH
    return max(5, terminal_columns - _MINIMUM_PROGRESS_COLUMNS)


def _bar_width(terminal_columns: int, description_columns: int) -> int:
    available_columns: int = terminal_columns - description_columns - _BASE_INFO_COLUMNS
    return max(_MIN_BAR_COLUMNS, min(_MAX_BAR_COLUMNS, available_columns))


def _format_elapsed(elapsed_seconds: float) -> str:
    hours: int = int(elapsed_seconds // 3600)
    minutes: int = int((elapsed_seconds % 3600) // 60)
    seconds: int = int(elapsed_seconds % 60)
    milliseconds: int = int((elapsed_seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _start_timer(state: _FileProgressState) -> None:
    if state.started_at is None:
        state.started_at = time.monotonic()


def _stop_timer(state: _FileProgressState) -> None:
    stopped_at: float = time.monotonic()
    if state.started_at is None:
        state.started_at = stopped_at
    state.stopped_at = stopped_at


def _elapsed_seconds(state: _FileProgressState, now: float) -> float:
    if state.started_at is None:
        return 0
    return max((state.stopped_at or now) - state.started_at, 0)


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _index_stage_tasks(prepared: PreparedAutoRun) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for task in prepared.plan.tasks:
        stage: str | None = _DETERMINATE_STAGE.get(task.kind)
        if stage is not None:
            grouped.setdefault((task.group_id, stage), []).append(task.task_id)
    return {key: tuple(task_ids) for key, task_ids in grouped.items()}


def _source_label(group: InspectedSourceGroup) -> str:
    source = group.source
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
    return _short_filename(source.stem)


def _short_filename(filename: str) -> str:
    if len(filename) <= _MAX_FILENAME_COLUMNS:
        return filename
    suffix: str = Path(filename).suffix
    if suffix and len(suffix) < _MAX_FILENAME_COLUMNS // 2:
        stem_columns: int = _MAX_FILENAME_COLUMNS - len(suffix) - 1
        return f"{filename[:stem_columns]}…{suffix}"
    return f"{filename[: _MAX_FILENAME_COLUMNS - 1]}…"


def _stage_is_complete(
    group_id: str,
    stage: str,
    state: _FileProgressState,
    stage_tasks: dict[tuple[str, str], tuple[str, ...]],
) -> bool:
    task_ids: tuple[str, ...] = stage_tasks.get((group_id, stage), ())
    return bool(task_ids) and all(state.progress_by_task.get(task_id, 0) >= _COMPLETE for task_id in task_ids)


def _description(label: str, phase: str) -> str:
    return f"{phase:<{_PHASE_WIDTH}} {label}"
