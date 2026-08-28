"""Rich progress rendering for interactive automatic runs."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Protocol

from rich.markup import escape
from rich.progress import TaskID

from anishift.application import RunEvent, RunEventKind, TaskKind, TaskState
from anishift.cli.run import PreparedAutoRun
from anishift.utils.rich_console import MultiProgressManager

__all__ = ["RichRunProgress"]

# ── Constants ─────────────────────────────────────────────────────────────────

_STAGE_LABELS: Final[dict[TaskKind, str]] = {
    TaskKind.EXTRACT_AUDIO: "Ekstrakcja audio",
    TaskKind.EXTRACT_SUBTITLES: "Ekstrakcja napisów",
    TaskKind.NORMALIZE_SUBTITLES: "Normalizacja napisów",
    TaskKind.TRANSLATE_SUBTITLES: "Tłumaczenie",
    TaskKind.SPLIT_SUBTITLES: "Podział napisów",
    TaskKind.SYNTHESIZE_SPEECH: "Lektor",
    TaskKind.TRANSCODE_AUDIO: "Kodowanie audio",
    TaskKind.MIX_NARRATION: "Miksowanie lektora",
    TaskKind.COMPOSE_MKV: "Składanie MKV",
    TaskKind.COMPOSE_MP4: "Składanie MP4",
    TaskKind.PUBLISH_ARTIFACT: "Publikowanie",
}
"""Polish labels for public execution stages."""

_AUDIO_PHASES: Final[dict[str, str]] = {
    "mixing": "Miksowanie lektora",
    "narration_resume": "Wznawianie lektora",
    "normalizing": "Normalizacja audio",
    "timeline": "Budowanie osi czasu",
    "skipped_no_spoken": "Pominięto lektora",
    "done": "Kończenie audio",
}
"""Polish descriptions for the safe audio phase identifiers."""

_AUDIO_TASKS: Final[frozenset[TaskKind]] = frozenset(
    {
        TaskKind.EXTRACT_AUDIO,
        TaskKind.TRANSCODE_AUDIO,
        TaskKind.MIX_NARRATION,
    }
)
"""Task kinds whose progress messages may identify an audio phase."""


class _ProgressManager(Protocol):
    """Describe the existing progress manager surface used by the renderer."""

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
        """Add one stable progress row."""
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
        """Switch one row between spinner and determinate modes."""
        ...

    def stop_task(self, task_id: TaskID) -> None:
        """Freeze the elapsed time for one row."""
        ...

    def reset_task(self, task_id: TaskID, *, completed: int = 0) -> None:
        """Restart one row for its next stage."""
        ...


@dataclass(slots=True)
class _GroupProgressState:
    """Track the current presentation state of one execution group."""

    label: str
    row_id: TaskID | None = None
    current_task_id: str | None = None
    current_kind: TaskKind | None = None
    last_percent: int | None = None
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class _RowUpdate:
    """Carry one atomic progress-row presentation update."""

    row_id: TaskID
    description: str | None = None
    completed: int | None = None
    reset: bool = False
    show_bar: bool | None = None
    show_percentage: bool | None = None
    show_spinner: bool | None = None
    stop: bool = False


class RichRunProgress:
    """Render application run events into one stable row per group."""

    def __init__(self, prepared: PreparedAutoRun, manager: _ProgressManager | None = None) -> None:
        self._manager: _ProgressManager = manager or MultiProgressManager(
            align="aligned",
            max_description_length=80,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
            show_elapsed=True,
            show_eta=False,
            show_download=False,
            show_speed=False,
            transient=False,
        )
        labels: dict[str, str] = {group.group_id: escape(group.source.stem) for group in prepared.workspace.groups}
        self._groups: dict[str, _GroupProgressState] = {
            group.group_id: _GroupProgressState(labels.get(group.group_id, escape(group.group_id)))
            for group in prepared.plan.groups
        }
        self._tasks: dict[str, TaskKind] = {task.task_id: task.kind for task in prepared.plan.tasks}
        self._lock: threading.Lock = threading.Lock()
        self._run_id: str | None = None
        self._last_sequence: int = 0
        self._pending: deque[_RowUpdate] = deque()
        self._rendering: bool = False
        self._open: bool = False

    def __enter__(self) -> RichRunProgress:
        """Start progress and preallocate rows in natural plan order."""
        self._manager.__enter__()
        for state in self._groups.values():
            state.row_id = self._manager.add_task(f"Oczekuje · {state.label}")
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop progress and make later events harmless."""
        with self._lock:
            self._open = False
        self._manager.__exit__(exc_type, exc_value, traceback)

    def emit(self, event: RunEvent) -> None:
        """Apply one accepted event to its existing group row."""
        with self._lock:
            if not self._accept(event):
                return
            update: _RowUpdate | None = self._transition(event)
            if update is None:
                return
            self._pending.append(update)
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

    def _transition(self, event: RunEvent) -> _RowUpdate | None:
        """Update local state and describe the corresponding row mutation."""
        if event.group_id is None:
            return None
        state: _GroupProgressState | None = self._groups.get(event.group_id)
        if state is None or state.row_id is None or state.terminal:
            return None
        update: _RowUpdate | None = None
        if event.kind is RunEventKind.TASK_STARTED:
            update = self._task_started(state, event)
        elif event.kind is RunEventKind.TASK_PROGRESS:
            update = self._task_progress(state, event)
        elif event.kind in {RunEventKind.TASK_RETRY, RunEventKind.TASK_FALLBACK}:
            update = self._task_notice(state, event)
        elif event.kind is RunEventKind.TASK_FINISHED:
            update = self._task_finished(state, event)
        elif event.kind is RunEventKind.GROUP_FINISHED:
            update = self._group_finished(state, event.state)
        return update

    def _task_started(self, state: _GroupProgressState, event: RunEvent) -> _RowUpdate | None:
        """Begin a new stage in the existing group row."""
        if event.task_id is None:
            return None
        kind: TaskKind | None = self._tasks.get(event.task_id)
        if kind is None:
            return None
        state.current_task_id = event.task_id
        state.current_kind = kind
        state.last_percent = None
        return _RowUpdate(
            _required_row_id(state),
            description=f"{_STAGE_LABELS[kind]} · {state.label}",
            reset=True,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_progress(self, state: _GroupProgressState, event: RunEvent) -> _RowUpdate | None:
        """Render real task progress or a safe non-determinate audio phase."""
        if event.task_id != state.current_task_id or event.progress_percent is None or state.current_kind is None:
            return None
        if state.current_kind in _AUDIO_TASKS and event.message in _AUDIO_PHASES:
            description: str = _AUDIO_PHASES[event.message]
            return _RowUpdate(
                _required_row_id(state),
                description=f"{description} · {state.label}",
                show_bar=False,
                show_percentage=False,
                show_spinner=True,
            )
        if state.last_percent is not None and event.progress_percent < state.last_percent:
            return None
        state.last_percent = event.progress_percent
        return _RowUpdate(
            _required_row_id(state),
            description=f"{_STAGE_LABELS[state.current_kind]} · {state.label}",
            completed=event.progress_percent,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_notice(self, state: _GroupProgressState, event: RunEvent) -> _RowUpdate:
        """Show retry or fallback without allocating another row."""
        title: str = "Ponowna próba" if event.kind is RunEventKind.TASK_RETRY else "Fallback"
        safe_message: str = escape(event.message) if event.message else ""
        details: str = f" · {safe_message}" if safe_message else ""
        return _RowUpdate(
            _required_row_id(state),
            description=f"[warning]{title}[/warning]{details} · {state.label}",
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _task_finished(self, state: _GroupProgressState, event: RunEvent) -> _RowUpdate | None:
        """Reflect a terminal task state without freezing the reusable row."""
        if event.task_id != state.current_task_id or event.state is None:
            return None
        if event.state is TaskState.SUCCEEDED:
            return _RowUpdate(
                _required_row_id(state),
                description=f"Etap gotowy · {state.label}",
                completed=100,
                show_bar=True,
                show_percentage=True,
                show_spinner=False,
            )
        if event.state in {TaskState.FAILED, TaskState.BLOCKED, TaskState.CANCELLED}:
            title: str = "Anulowano" if event.state is TaskState.CANCELLED else "Błąd"
            style: str = "warning" if event.state is TaskState.CANCELLED else "error"
            safe_message: str = escape(event.message) if event.message else ""
            details: str = f" · {safe_message}" if safe_message else ""
            return _RowUpdate(
                _required_row_id(state),
                description=f"[{style}]{title}[/{style}]{details} · {state.label}",
                show_bar=True,
                show_percentage=True,
                show_spinner=False,
            )
        return None

    def _group_finished(self, state: _GroupProgressState, task_state: TaskState | None) -> _RowUpdate:
        """Freeze one row at its terminal group outcome."""
        state.terminal = True
        if task_state is TaskState.SUCCEEDED:
            return _RowUpdate(
                _required_row_id(state),
                description=f"Gotowe · {state.label}",
                completed=100,
                show_bar=True,
                show_percentage=True,
                show_spinner=False,
                stop=True,
            )
        if task_state is TaskState.CANCELLED:
            description: str = f"[warning]Anulowano[/warning] · {state.label}"
        else:
            description = f"[error]Błąd[/error] · {state.label}"
        return _RowUpdate(
            _required_row_id(state),
            description=description,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
            stop=True,
        )

    def _render(self, update: _RowUpdate) -> None:
        """Apply one presentation update through public manager methods."""
        if update.reset:
            self._manager.reset_task(update.row_id)
        if update.description is not None:
            self._manager.update_description(update.row_id, update.description)
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

    def _drain_pending(self) -> None:
        """Render accepted row updates serially in their event order."""
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


def _required_row_id(state: _GroupProgressState) -> TaskID:
    """Return the preallocated row guaranteed by the active progress state."""
    if state.row_id is None:
        msg = "Progress row has not been allocated"
        raise RuntimeError(msg)
    return state.row_id
