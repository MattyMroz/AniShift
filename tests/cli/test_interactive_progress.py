from __future__ import annotations

import threading
from types import SimpleNamespace, TracebackType
from typing import cast

import pytest
from rich.progress import TaskID

import anishift.cli.interactive.progress as progress_module
from anishift.application import RunEvent, RunEventKind, TaskKind, TaskState
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.run import PreparedAutoRun


class _FakeManager:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.descriptions: list[tuple[TaskID, str]] = []
        self.presentations: list[tuple[TaskID, bool, bool, bool]] = []
        self.updates: list[tuple[TaskID, int]] = []
        self.resets: list[TaskID] = []
        self.stopped: list[TaskID] = []
        self.entered: bool = False
        self.exited: bool = False

    def __enter__(self) -> _FakeManager:
        self.entered = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited = True

    def add_task(self, description: str, *, total: int = 100) -> TaskID:
        task_id: TaskID = TaskID(len(self.added))
        self.added.append(description)
        return task_id

    def update(self, task_id: TaskID, completed: int) -> None:
        self.updates.append((task_id, completed))

    def update_description(self, task_id: TaskID, description: str) -> None:
        self.descriptions.append((task_id, description))

    def set_task_presentation(
        self,
        task_id: TaskID,
        *,
        show_bar: bool,
        show_percentage: bool,
        show_spinner: bool,
    ) -> None:
        self.presentations.append((task_id, show_bar, show_percentage, show_spinner))

    def stop_task(self, task_id: TaskID) -> None:
        self.stopped.append(task_id)

    def reset_task(self, task_id: TaskID, *, completed: int = 0) -> None:
        self.resets.append(task_id)
        if completed:
            self.updates.append((task_id, completed))


class _BlockingManager(_FakeManager):
    def __init__(self) -> None:
        super().__init__()
        self.started: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()

    def reset_task(self, task_id: TaskID, *, completed: int = 0) -> None:
        self.started.set()
        assert self.release.wait(timeout=5)
        super().reset_task(task_id, completed=completed)


def _prepared(
    groups: tuple[tuple[str, str], ...],
    tasks: tuple[tuple[str, str, TaskKind], ...],
) -> PreparedAutoRun:
    workspace_groups: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(group_id=group_id, source=SimpleNamespace(stem=stem)) for group_id, stem in groups
    )
    plan_groups: tuple[SimpleNamespace, ...] = tuple(SimpleNamespace(group_id=group_id) for group_id, _ in groups)
    plan_tasks: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(task_id=task_id, group_id=group_id, kind=kind) for task_id, group_id, kind in tasks
    )
    value: SimpleNamespace = SimpleNamespace(
        preset_id="default",
        workspace=SimpleNamespace(groups=workspace_groups),
        group_ids=tuple(group_id for group_id, _ in groups),
        plan=SimpleNamespace(groups=plan_groups, tasks=plan_tasks),
    )
    return cast("PreparedAutoRun", value)


def _event(  # noqa: PLR0913
    sequence: int,
    kind: RunEventKind,
    *,
    group_id: str = "group-1",
    task_id: str | None = None,
    state: TaskState | None = None,
    progress_percent: int | None = None,
    message: str | None = None,
) -> RunEvent:
    return RunEvent(
        run_id="run-1",
        sequence=sequence,
        kind=kind,
        group_id=group_id,
        task_id=task_id,
        state=state,
        progress_percent=progress_percent,
        message=message,
    )


def test_progress_preallocates_one_row_per_group_in_natural_order() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-2", "Odcinek 02"), ("group-10", "Odcinek 10")),
        (),
    )

    with RichRunProgress(prepared, manager):
        pass

    assert manager.added == ["Oczekuje · Odcinek 02", "Oczekuje · Odcinek 10"]
    assert manager.entered is True
    assert manager.exited is True


def test_progress_uses_the_existing_manager_palette(monkeypatch: pytest.MonkeyPatch) -> None:
    manager: _FakeManager = _FakeManager()
    options: dict[str, object] = {}

    def manager_factory(**values: object) -> _FakeManager:
        options.update(values)
        return manager

    monkeypatch.setattr(progress_module, "MultiProgressManager", manager_factory)
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared):
        pass

    assert "colors" not in options
    assert options["align"] == "aligned"
    assert options["show_bar"] is True
    assert options["show_percentage"] is True
    assert options["show_spinner"] is False


def test_translation_uses_the_existing_dynamic_progress_bar() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=100))

    assert manager.presentations == [
        (TaskID(0), True, True, False),
        (TaskID(0), True, True, False),
    ]
    assert manager.updates == [(TaskID(0), 100)]
    assert manager.descriptions[-1] == (TaskID(0), "Tłumaczenie · Odcinek 01")


def test_tts_uses_real_progress_and_keeps_retry_and_fallback_in_the_same_row() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=25))
        progress.emit(_event(3, RunEventKind.TASK_RETRY, task_id="tts", message="ElevenLabs · 2/3"))
        progress.emit(_event(4, RunEventKind.TASK_FALLBACK, task_id="tts", message="ElevenLabs -> SAPI"))

    assert (TaskID(0), 25) in manager.updates
    assert (TaskID(0), True, True, False) in manager.presentations
    assert all(task_id == TaskID(0) for task_id, _ in manager.descriptions)
    assert any("Ponowna próba" in description for _, description in manager.descriptions)
    assert any("Fallback" in description for _, description in manager.descriptions)
    assert len(manager.added) == 1


def test_tts_progress_never_moves_backwards() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=60))
        progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40))

    assert manager.updates == [(TaskID(0), 60)]


def test_audio_phase_uses_a_polish_spinner_description() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("audio", "group-1", TaskKind.MIX_NARRATION),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="audio", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="audio", progress_percent=0, message="normalizing"))

    assert manager.descriptions[-1] == (TaskID(0), "Normalizacja audio · Odcinek 01")
    assert manager.presentations[-1] == (TaskID(0), False, False, True)


def test_group_success_and_failure_freeze_their_rows() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"), ("group-2", "Odcinek 02")),
        (),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        progress.emit(_event(2, RunEventKind.GROUP_FINISHED, group_id="group-2", state=TaskState.FAILED))

    assert manager.updates == [(TaskID(0), 100)]
    assert manager.presentations[-2:] == [
        (TaskID(0), True, True, False),
        (TaskID(1), True, True, False),
    ]
    assert manager.stopped == [TaskID(0), TaskID(1)]
    assert manager.descriptions[-2:] == [
        (TaskID(0), "Gotowe · Odcinek 01"),
        (TaskID(1), "[error]Błąd[/error] · Odcinek 02"),
    ]


def test_stale_events_and_events_after_close_are_ignored() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )
    progress: RichRunProgress = RichRunProgress(prepared, manager)

    with progress:
        progress.emit(_event(2, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(1, RunEventKind.TASK_RETRY, task_id="translate", message="late"))
    progress.emit(_event(3, RunEventKind.TASK_FALLBACK, task_id="translate", message="closed"))

    assert len(manager.descriptions) == 1
    assert "Tłumaczenie" in manager.descriptions[0][1]


def test_group_labels_are_escaped_before_rich_renders_them() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared((("group-1", "[secret] episode"),), ())

    with RichRunProgress(prepared, manager):
        pass

    assert manager.added == [r"Oczekuje · \[secret] episode"]


def test_stage_transition_reuses_the_preallocated_row() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (
            ("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),
            ("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),
        ),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_FINISHED, task_id="translate", state=TaskState.SUCCEEDED))
        progress.emit(_event(3, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))

    assert len(manager.added) == 1
    assert manager.resets == [TaskID(0), TaskID(0)]
    assert all(task_id == TaskID(0) for task_id, _ in manager.descriptions)


def test_concurrent_events_render_in_sequence_order() -> None:
    manager: _BlockingManager = _BlockingManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, manager) as progress:
        started: threading.Thread = threading.Thread(
            target=progress.emit,
            args=(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING),),
        )
        started.start()
        assert manager.started.wait(timeout=5)
        progressed: threading.Thread = threading.Thread(
            target=progress.emit,
            args=(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=50),),
        )
        progressed.start()
        progressed.join(timeout=5)
        manager.release.set()
        started.join(timeout=5)

    assert not started.is_alive()
    assert not progressed.is_alive()
    assert manager.presentations[-1] == (TaskID(0), True, True, False)
    assert manager.updates[-1] == (TaskID(0), 50)
