"""Legacy-compatible Rich progress for interactive automatic runs."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final, Literal, Protocol

from rich.progress import TaskID

from anishift.application import ArtifactKind, InspectedSourceGroup, RunEvent, RunEventKind, TaskKind, TaskState
from anishift.cli.run import PreparedAutoRun
from anishift.utils.rich_console import MultiProgressManager, console

__all__ = ["RichRunProgress"]

# ── Constants ──────────────────────────────────────────────────────────────────

_DESCRIPTION_LENGTH: Final[int] = 72
"""Maximum legacy stage, provider, voice and filename width."""

_NARROW_DESCRIPTION_LENGTH: Final[int] = 35
"""Readable description width that still fits one row at 80 columns."""

_MINIMAL_ROW_RESERVED_COLUMNS: Final[int] = 11
"""Columns required by the minimum bar, percentage and separators."""

_NO_ELAPSED_RESERVED_COLUMNS: Final[int] = 48
"""Columns reserved for the full bar, percentage and their separators."""

_FULL_BAR_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _NO_ELAPSED_RESERVED_COLUMNS
"""Minimum width combining the narrow description and full progress bar."""

_MINIMUM_BAR_LAYOUT_COLUMNS: Final[int] = _NARROW_DESCRIPTION_LENGTH + _MINIMAL_ROW_RESERVED_COLUMNS
"""Minimum width combining the narrow description and three-cell bar."""

_ELAPSED_LAYOUT_COLUMNS: Final[int] = 135
"""Minimum width fitting the legacy description, bar, percentage and time."""

_PHASE_WIDTH: Final[int] = 14
"""Fixed legacy phase width keeping filenames aligned."""

_COMPLETE: Final[int] = 100
"""Completed percentage used by determinate legacy rows."""

_STAGE_RANK: Final[dict[str, int]] = {
    "extracting": 0,
    "translating": 1,
    "tts": 2,
    "audio": 3,
    "terminal": 4,
}
"""Legacy stage precedence preventing late callbacks from regressing rows."""

_DETERMINATE_STAGE: Final[dict[TaskKind, Literal["extracting", "translating", "tts"]]] = {
    TaskKind.EXTRACT_AUDIO: "extracting",
    TaskKind.EXTRACT_SUBTITLES: "extracting",
    TaskKind.EXTRACT_TRACKS: "extracting",
    TaskKind.TRANSLATE_SUBTITLES: "translating",
    TaskKind.SYNTHESIZE_SPEECH: "tts",
}
"""Task kinds that own the three determinate legacy stages."""

_ACTIVE_LABEL: Final[dict[str, str]] = {
    "extracting": "Extracting",
    "translating": "Translating",
    "tts": "Synthesizing",
}
"""Legacy labels shown while determinate work is active."""

_COMPLETE_LABEL: Final[dict[str, str]] = {
    "extracting": "Extracted",
    "translating": "Translated",
}
"""Legacy labels shown after extraction and translation complete."""

_AUDIO_LABEL: Final[dict[str, str]] = {
    "normalizing": "Audio normalize",
    "timeline": "Audio timeline",
    "mixing": "Audio mixing",
    "narration_resume": "Audio resume",
    "skipped_no_spoken": "Audio skipped",
}
"""Legacy labels for coarse audio callbacks."""


class _ProgressManager(Protocol):
    """Describe the established progress manager surface used by the adapter."""

    def __enter__(self) -> _ProgressManager:
        """Start rendering progress rows."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop rendering progress rows."""
        ...

    def add_task(self, description: str, *, total: int = 100) -> TaskID:
        """Add one stable file row."""
        ...

    def update(self, task_id: TaskID, completed: int) -> None:
        """Update one row with an absolute value."""
        ...

    def update_description(self, task_id: TaskID, description: str) -> None:
        """Replace one row description."""
        ...

    def set_task_presentation(
        self,
        task_id: TaskID,
        *,
        show_bar: bool,
        show_percentage: bool,
        show_spinner: bool,
    ) -> None:
        """Switch one row between determinate and coarse audio modes."""
        ...

    def stop_task(self, task_id: TaskID) -> None:
        """Freeze the elapsed time for one row."""
        ...

    def reset_task(self, task_id: TaskID, *, completed: int = 0) -> None:
        """Restart one row for its next stage."""
        ...


@dataclass(slots=True)
class _FileProgressState:
    """Track the legacy presentation state of one input file."""

    label: str
    row_id: TaskID | None = None
    stage: str = "extracting"
    stage_rank: int = 0
    progress_by_task: dict[str, int] = field(default_factory=dict)
    visible_percent: int = 0
    terminal: bool = False
    description: str = ""
    completed: int = 0
    show_bar: bool = True
    show_percentage: bool = True
    show_spinner: bool = False
    stopped: bool = False


@dataclass(frozen=True, slots=True)
class _RowUpdate:
    """Carry one atomic progress-row mutation."""

    row_id: TaskID
    description: str | None = None
    completed: int | None = None
    reset: bool = False
    show_bar: bool | None = None
    show_percentage: bool | None = None
    show_spinner: bool | None = None
    stop: bool = False


class RichRunProgress:
    """Adapt current run events to the legacy one-row-per-file display."""

    def __init__(
        self,
        prepared: PreparedAutoRun,
        manager: _ProgressManager | None = None,
        layout: Callable[[], None] | None = None,
    ) -> None:
        self._layout: Callable[[], None] | None = layout
        labels: dict[str, str] = {group.group_id: _source_label(group) for group in prepared.workspace.groups}
        self._files: dict[str, _FileProgressState] = {
            group.group_id: _FileProgressState(labels.get(group.group_id, group.group_id))
            for group in prepared.plan.groups
        }
        self._task_kind: dict[str, TaskKind] = {task.task_id: task.kind for task in prepared.plan.tasks}
        self._stage_tasks: dict[tuple[str, str], tuple[str, ...]] = _index_stage_tasks(prepared)
        self._tts_label: str = _tts_progress_label(prepared)
        self._natural_description_width: int = max(
            (
                len(_description(state.label, "Retrying", f"{self._tts_label} · 10/10"))
                for state in self._files.values()
            ),
            default=1,
        )
        self._description_width: int = self._natural_description_width
        self._render_columns: int = max(console.width, 1)
        self._align_descriptions: bool = manager is None
        self._manager_factory: Callable[[], _ProgressManager] | None = self._new_manager if manager is None else None
        self._manager: _ProgressManager = manager or self._new_manager()
        self._lock: threading.Lock = threading.Lock()
        self._display_lock: threading.Lock = threading.Lock()
        self._run_id: str | None = None
        self._last_sequence: int = 0
        self._pending: deque[_RowUpdate] = deque()
        self._rendering: bool = False
        self._open: bool = False

    def __enter__(self) -> RichRunProgress:
        """Preallocate naturally ordered legacy rows and start the display."""
        if self._layout is not None:
            self._layout()
        for state in self._files.values():
            state.description = _description(state.label, "Extracting")
            state.row_id = self._manager.add_task(self._display_description(state.description))
        with self._display_lock:
            self._manager.__enter__()
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop progress and ignore callbacks received after closure."""
        with self._lock:
            self._open = False
        with self._display_lock:
            self._manager.__exit__(exc_type, exc_value, traceback)

    def relayout(self) -> None:
        """Redraw the Auto frame and refit progress after a terminal resize."""
        with self._lock:
            if not self._open or self._layout is None:
                return
            with self._display_lock:
                self._manager.__exit__(None, None, None)
                self._layout()
                if self._manager_factory is None:
                    self._manager.__enter__()
                    return
                if max(console.width, 1) == self._render_columns:
                    self._manager.__enter__()
                    return
                self._manager = self._manager_factory()
                for state in self._files.values():
                    state.row_id = self._manager.add_task(self._display_description(state.description))
                self._manager.__enter__()
                self._restore_rows()

    def _new_manager(self) -> _ProgressManager:
        """Build a manager and refresh the aligned description width."""
        self._render_columns = max(console.width, 1)
        description_limit: int
        show_elapsed: bool
        description_limit, show_elapsed = _manager_layout(self._render_columns)
        self._description_width = min(self._natural_description_width, description_limit)
        return _create_manager(description_limit, show_elapsed=show_elapsed)

    def _display_description(self, description: str) -> str:
        """Pad production descriptions so independent rows keep legacy alignment."""
        if not self._align_descriptions or len(description) >= self._description_width:
            return description
        return description.ljust(self._description_width)

    def emit(self, event: RunEvent) -> None:
        """Apply one accepted event to its preallocated legacy row."""
        with self._lock:
            if not self._accept(event):
                return
            updates: tuple[_RowUpdate, ...] = self._transitions(event)
            if not updates:
                return
            for update in updates:
                self._record(update)
            self._pending.extend(updates)
            if self._rendering:
                return
            self._rendering = True
        self._drain_pending()

    def _accept(self, event: RunEvent) -> bool:
        """Accept only new events from the active run while rendering is open."""
        if not self._open:
            return False
        if self._run_id is None:
            self._run_id = event.run_id
        if event.run_id != self._run_id or event.sequence <= self._last_sequence:
            return False
        self._last_sequence = event.sequence
        return True

    def _transitions(self, event: RunEvent) -> tuple[_RowUpdate, ...]:
        """Translate one current-backend event into legacy row mutations."""
        if event.kind is RunEventKind.RUN_FINISHED:
            return self._finish_remaining(event.state)
        if event.group_id is None:
            return ()
        state: _FileProgressState | None = self._files.get(event.group_id)
        if state is None or state.row_id is None or state.terminal:
            return ()
        update: _RowUpdate | None = None
        if event.kind is RunEventKind.TASK_STARTED:
            update = self._task_started(state, event)
        elif event.kind is RunEventKind.TASK_PROGRESS:
            update = self._task_progress(event.group_id, state, event)
        elif event.kind is RunEventKind.TASK_RETRY:
            update = self._task_retry(state, event)
        elif event.kind is RunEventKind.TASK_FINISHED:
            update = self._task_finished(event.group_id, state, event)
        elif event.kind is RunEventKind.GROUP_FINISHED:
            update = self._group_finished(state, event.state)
        return () if update is None else (update,)

    def _task_started(self, state: _FileProgressState, event: RunEvent) -> _RowUpdate | None:
        """Start the legacy determinate stage owning this task."""
        if event.task_id is None:
            return None
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None:
            return None
        rank: int = _STAGE_RANK[stage]
        if rank < state.stage_rank:
            return None
        reset: bool = rank > state.stage_rank
        if reset:
            state.progress_by_task.clear()
            state.visible_percent = 0
        state.stage = stage
        state.stage_rank = rank
        state.progress_by_task.setdefault(event.task_id, 0)
        return _RowUpdate(
            _required_row_id(state),
            description=_description(state.label, _ACTIVE_LABEL[stage], _stage_detail(stage, self._tts_label)),
            reset=reset,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_progress(
        self,
        group_id: str,
        state: _FileProgressState,
        event: RunEvent,
    ) -> _RowUpdate | None:
        """Render legacy determinate progress or a coarse audio callback."""
        if event.task_id is None or event.progress_percent is None:
            return None
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        if kind in {TaskKind.TRANSCODE_AUDIO, TaskKind.MIX_NARRATION} and event.message in _AUDIO_LABEL:
            return self._audio_phase(state, event.message)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None or _STAGE_RANK[stage] < state.stage_rank:
            return None
        previous: int = state.progress_by_task.get(event.task_id, 0)
        state.progress_by_task[event.task_id] = max(previous, event.progress_percent)
        if stage == "tts":
            state.visible_percent = max(state.visible_percent, event.progress_percent)
        else:
            state.visible_percent = event.progress_percent
        phase: str = _ACTIVE_LABEL[stage]
        if _stage_is_complete(group_id, stage, state, self._stage_tasks) and stage in _COMPLETE_LABEL:
            phase = _COMPLETE_LABEL[stage]
        return _RowUpdate(
            _required_row_id(state),
            description=_description(state.label, phase, _stage_detail(stage, self._tts_label)),
            completed=state.visible_percent,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_retry(self, state: _FileProgressState, event: RunEvent) -> _RowUpdate | None:
        """Show the legacy TTS retry label without changing its percentage."""
        if event.task_id is None or self._task_kind.get(event.task_id) is not TaskKind.SYNTHESIZE_SPEECH:
            return None
        detail: str = self._tts_label
        if event.message:
            detail = f"{detail} · {_retry_counter(event.message)}"
        return _RowUpdate(
            _required_row_id(state),
            description=_description(state.label, "Retrying", detail),
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_finished(
        self,
        group_id: str,
        state: _FileProgressState,
        event: RunEvent,
    ) -> _RowUpdate | None:
        """Complete a legacy determinate stage when its task reports success."""
        if event.task_id is None or event.state is not TaskState.SUCCEEDED:
            return None
        kind: TaskKind | None = self._task_kind.get(event.task_id)
        stage: str | None = _DETERMINATE_STAGE.get(kind) if kind is not None else None
        if stage is None or _STAGE_RANK[stage] < state.stage_rank:
            return None
        state.progress_by_task[event.task_id] = _COMPLETE
        state.visible_percent = _COMPLETE
        phase: str = (
            _COMPLETE_LABEL.get(stage, _ACTIVE_LABEL[stage])
            if _stage_is_complete(group_id, stage, state, self._stage_tasks)
            else _ACTIVE_LABEL[stage]
        )
        return _RowUpdate(
            _required_row_id(state),
            description=_description(state.label, phase, _stage_detail(stage, self._tts_label)),
            completed=state.visible_percent,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _audio_phase(self, state: _FileProgressState, phase: str) -> _RowUpdate | None:
        """Switch the row to the spinner used only by legacy audio phases."""
        if state.stage_rank > _STAGE_RANK["audio"]:
            return None
        reset: bool = state.stage_rank < _STAGE_RANK["audio"]
        state.stage = "audio"
        state.stage_rank = _STAGE_RANK["audio"]
        return _RowUpdate(
            _required_row_id(state),
            description=_description(state.label, _AUDIO_LABEL[phase], self._tts_label),
            reset=reset,
            show_bar=False,
            show_percentage=False,
            show_spinner=True,
        )

    def _group_finished(self, state: _FileProgressState, task_state: TaskState | None) -> _RowUpdate:
        """Freeze one row at the same terminal state as legacy."""
        state.terminal = True
        state.stage = "terminal"
        state.stage_rank = _STAGE_RANK["terminal"]
        if task_state is TaskState.SUCCEEDED:
            return _terminal_update(state, "Done", completed=_COMPLETE)
        if task_state is TaskState.CANCELLED:
            return _terminal_update(state, "Cancelled", reset=True)
        return _terminal_update(state, "Failed", reset=True)

    def _finish_remaining(self, task_state: TaskState | None) -> tuple[_RowUpdate, ...]:
        """Reconcile rows missing an expected group-terminal event."""
        updates: list[_RowUpdate] = []
        for state in self._files.values():
            if state.terminal:
                continue
            state.terminal = True
            state.stage = "terminal"
            state.stage_rank = _STAGE_RANK["terminal"]
            phase: str = "Cancelled" if task_state is TaskState.CANCELLED else "Not processed"
            updates.append(_terminal_update(state, phase, reset=True))
        return tuple(updates)

    def _render(self, update: _RowUpdate) -> None:
        """Apply one legacy presentation update through public manager methods."""
        with self._display_lock:
            if update.reset:
                self._manager.reset_task(update.row_id)
            if update.description is not None:
                self._manager.update_description(update.row_id, self._display_description(update.description))
            if update.show_bar is not None and update.show_percentage is not None and update.show_spinner is not None:
                self._manager.set_task_presentation(
                    update.row_id,
                    show_bar=update.show_bar,
                    show_percentage=update.show_percentage,
                    show_spinner=update.show_spinner,
                )
            if update.completed is not None:
                self._manager.update(update.row_id, update.completed)
            if update.stop:
                self._manager.stop_task(update.row_id)

    def _record(self, update: _RowUpdate) -> None:
        """Persist the latest public row presentation for resize reconstruction."""
        state: _FileProgressState | None = next(
            (item for item in self._files.values() if item.row_id == update.row_id),
            None,
        )
        if state is None:
            return
        if update.reset:
            state.completed = 0
            state.stopped = False
        if update.description is not None:
            state.description = update.description
        if update.show_bar is not None:
            state.show_bar = update.show_bar
        if update.show_percentage is not None:
            state.show_percentage = update.show_percentage
        if update.show_spinner is not None:
            state.show_spinner = update.show_spinner
        if update.completed is not None:
            state.completed = update.completed
        if update.stop:
            state.stopped = True

    def _restore_rows(self) -> None:
        """Restore current rows into a newly width-fitted manager."""
        for state in self._files.values():
            row_id: TaskID = _required_row_id(state)
            self._manager.set_task_presentation(
                row_id,
                show_bar=state.show_bar,
                show_percentage=state.show_percentage,
                show_spinner=state.show_spinner,
            )
            self._manager.update(row_id, state.completed)
            if state.stopped:
                self._manager.stop_task(row_id)

    def _drain_pending(self) -> None:
        """Render accepted row updates serially in event order."""
        try:
            while True:
                with self._lock:
                    if not self._pending:
                        self._rendering = False
                        return
                    update: _RowUpdate = self._pending.popleft()
                self._render(update)
        except BaseException:
            with self._lock:
                self._rendering = False
            raise


def _create_manager(description_length: int, *, show_elapsed: bool) -> _ProgressManager:
    """Build the established file progress display for resolved geometry."""
    return MultiProgressManager(
        align="independent",
        max_description_length=description_length,
        show_download=False,
        show_elapsed=show_elapsed,
        transient=False,
    )


def _manager_layout(terminal_columns: int) -> tuple[int, bool]:
    """Resolve description and elapsed visibility for one terminal width."""
    show_elapsed: bool = terminal_columns >= _ELAPSED_LAYOUT_COLUMNS
    return _responsive_description_length(terminal_columns, show_elapsed=show_elapsed), show_elapsed


def _responsive_description_length(terminal_columns: int, *, show_elapsed: bool) -> int:
    """Fit the description without allowing the percentage row to wrap."""
    if show_elapsed:
        return _DESCRIPTION_LENGTH
    if terminal_columns >= _FULL_BAR_LAYOUT_COLUMNS:
        return min(_DESCRIPTION_LENGTH, terminal_columns - _NO_ELAPSED_RESERVED_COLUMNS)
    if terminal_columns >= _MINIMUM_BAR_LAYOUT_COLUMNS:
        return _NARROW_DESCRIPTION_LENGTH
    return max(5, terminal_columns - _MINIMAL_ROW_RESERVED_COLUMNS)


def _index_stage_tasks(prepared: PreparedAutoRun) -> dict[tuple[str, str], tuple[str, ...]]:
    """Index determinate task IDs by file and legacy stage."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for task in prepared.plan.tasks:
        stage: str | None = _DETERMINATE_STAGE.get(task.kind)
        if stage is not None:
            grouped.setdefault((task.group_id, stage), []).append(task.task_id)
    return {key: tuple(task_ids) for key, task_ids in grouped.items()}


def _source_label(group: InspectedSourceGroup) -> str:
    """Return the concrete legacy input filename for one inspected group."""
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
            return path.name
    return source.stem


def _stage_is_complete(
    group_id: str,
    stage: str,
    state: _FileProgressState,
    stage_tasks: dict[tuple[str, str], tuple[str, ...]],
) -> bool:
    """Return whether every backend task belonging to one public stage finished."""
    task_ids: tuple[str, ...] = stage_tasks.get((group_id, stage), ())
    return bool(task_ids) and all(state.progress_by_task.get(task_id, 0) >= _COMPLETE for task_id in task_ids)


def _stage_detail(stage: str, tts_label: str) -> str:
    """Return the provider detail used only by legacy TTS stages."""
    return tts_label if stage == "tts" else ""


def _retry_counter(message: str) -> str:
    """Keep the compact legacy retry counter from a worker message."""
    return message.rsplit(maxsplit=1)[-1]


def _tts_progress_label(prepared: PreparedAutoRun) -> str:
    """Build the legacy engine, model and voice label from the run snapshot."""
    settings = prepared.plan.settings
    engine_id: str = settings.tts_profile_id
    model_id: str = settings.tts_model_id
    voice_label: str = settings.tts_voice_label
    engine_label: str = f"{engine_id}/{model_id}" if engine_id in {"elevenbytes", "elevenlabs"} else engine_id
    return f"{engine_label} · {voice_label}"


def _description(label: str, phase: str, detail: str = "") -> str:
    """Format one row exactly like the legacy file-progress adapter."""
    suffix: str = f" {detail} ·" if detail else ""
    return f"{phase:<{_PHASE_WIDTH}}{suffix} {label}"


def _terminal_update(
    state: _FileProgressState,
    phase: str,
    *,
    completed: int | None = None,
    reset: bool = False,
) -> _RowUpdate:
    """Build one frozen legacy terminal-row update."""
    return _RowUpdate(
        _required_row_id(state),
        description=_description(state.label, phase),
        completed=completed,
        reset=reset,
        show_bar=True,
        show_percentage=True,
        show_spinner=False,
        stop=True,
    )


def _required_row_id(state: _FileProgressState) -> TaskID:
    """Return the preallocated row guaranteed by the active display."""
    if state.row_id is None:
        msg = "Progress row has not been allocated"
        raise RuntimeError(msg)
    return state.row_id
