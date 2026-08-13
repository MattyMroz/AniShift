"""Run-event projection used by the execution screen."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from anishift.application.events import RunEvent, RunEventKind


@dataclass(slots=True)
class _TaskProgress:
    group_id: str
    task_id: str
    state: str = "queued"
    progress: int = 0
    note: str = ""


class ProgressTable(Vertical):
    """Render every state event once and coalesce task progress by identity."""

    def __init__(self) -> None:
        super().__init__(id="progress-view")
        self._tasks: dict[str, _TaskProgress] = {}
        self._groups: dict[str, str] = {}
        self._last_sequence: int = 0
        self._notifications: list[str] = []

    def compose(self) -> ComposeResult:
        """Compose group and task projections plus retry/fallback notices."""
        yield DataTable(id="group-progress", zebra_stripes=True)
        yield DataTable(id="task-progress", zebra_stripes=True)
        yield Static("", id="execution-notifications")

    def on_mount(self) -> None:
        """Create stable columns before accepting the first event batch."""
        self.query_one("#group-progress", DataTable).add_columns("Group", "State")
        self.query_one("#task-progress", DataTable).add_columns("Group", "Task", "State", "Progress", "Note")

    def apply(self, events: tuple[RunEvent, ...]) -> None:
        """Project a monotonic batch without duplicating older state events."""
        for event in events:
            if event.sequence <= self._last_sequence:
                continue
            self._last_sequence = event.sequence
            self._apply_event(event)
        self._render_tables()

    def _apply_event(self, event: RunEvent) -> None:
        if event.group_id is not None and event.kind is RunEventKind.GROUP_FINISHED:
            self._groups[event.group_id] = event.state.value if event.state is not None else "finished"
        if event.task_id is None:
            return
        progress = self._tasks.setdefault(
            event.task_id,
            _TaskProgress(event.group_id or "-", event.task_id),
        )
        if event.state is not None:
            progress.state = event.state.value
        if event.progress_percent is not None:
            progress.progress = event.progress_percent
        if event.kind in {RunEventKind.TASK_RETRY, RunEventKind.TASK_FALLBACK}:
            progress.note = event.message or event.kind.value
            self._notifications.append(f"{event.task_id}: {progress.note}")

    def _render_tables(self) -> None:
        groups = self.query_one("#group-progress", DataTable)
        groups.clear()
        for group_id, state in sorted(self._groups.items()):
            groups.add_row(group_id, state)
        tasks = self.query_one("#task-progress", DataTable)
        tasks.clear()
        for item in sorted(self._tasks.values(), key=lambda value: (value.group_id, value.task_id)):
            tasks.add_row(item.group_id, item.task_id, item.state, f"{item.progress}%", item.note)
        self.query_one("#execution-notifications", Static).update("\n".join(self._notifications[-10:]))
