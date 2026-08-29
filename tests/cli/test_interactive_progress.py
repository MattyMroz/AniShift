from __future__ import annotations

import re
import threading
from io import StringIO
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import cast

import pytest
from rich.console import Console
from rich.progress import TaskID

import anishift.cli.interactive.progress as progress_module
import anishift.utils.rich_console.progress.manager as progress_manager_module
import anishift.utils.rich_console.progress.multi as multi_module
from anishift.application import ArtifactKind, RunEvent, RunEventKind, TaskKind, TaskState
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
        del total
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
    *,
    tts_profile_id: str = "edge",
    tts_model_id: str = "default",
    tts_voice_label: str = "Marek",
) -> PreparedAutoRun:
    workspace_groups: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(
            group_id=group_id,
            source=SimpleNamespace(stem=stem),
            artifacts=(SimpleNamespace(kind=ArtifactKind.VIDEO_MKV, path=Path(f"{stem}.mkv")),),
        )
        for group_id, stem in groups
    )
    plan_groups: tuple[SimpleNamespace, ...] = tuple(SimpleNamespace(group_id=group_id) for group_id, _ in groups)
    plan_tasks: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(task_id=task_id, group_id=group_id, kind=kind) for task_id, group_id, kind in tasks
    )
    settings: SimpleNamespace = SimpleNamespace(
        tts_profile_id=tts_profile_id,
        tts_model_id=tts_model_id,
        tts_voice_label=tts_voice_label,
    )
    value: SimpleNamespace = SimpleNamespace(
        preset_id="default",
        workspace=SimpleNamespace(groups=workspace_groups),
        group_ids=tuple(group_id for group_id, _ in groups),
        plan=SimpleNamespace(groups=plan_groups, tasks=plan_tasks, settings=settings),
    )
    return cast("PreparedAutoRun", value)


def _event(  # noqa: PLR0913
    sequence: int,
    kind: RunEventKind,
    *,
    group_id: str | None = "group-1",
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


def test_progress_preallocates_legacy_bars_in_natural_order() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-2", "Odcinek 02"), ("group-10", "Odcinek 10")),
        (),
    )

    with RichRunProgress(prepared, manager):
        pass

    assert manager.added == ["Extracting     Odcinek 02.mkv", "Extracting     Odcinek 10.mkv"]
    assert manager.presentations == []
    assert manager.entered is True
    assert manager.exited is True


def test_progress_uses_legacy_manager_defaults_without_extraction_spinner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options: dict[str, object] = {}
    manager: _FakeManager = _FakeManager()

    def manager_factory(**values: object) -> _FakeManager:
        options.update(values)
        return manager

    monkeypatch.setattr(progress_module, "MultiProgressManager", manager_factory)
    monkeypatch.setattr(progress_module, "console", SimpleNamespace(width=140))

    with RichRunProgress(_prepared((("group-1", "Odcinek 01"),), ())):
        pass

    assert options == {
        "align": "independent",
        "max_description_length": 72,
        "show_download": False,
        "show_elapsed": True,
        "transient": False,
    }


def test_file_reuses_one_row_across_legacy_auto_stages() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (
            ("extract", "group-1", TaskKind.EXTRACT_SUBTITLES),
            ("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),
            ("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),
            ("mix", "group-1", TaskKind.MIX_NARRATION),
        ),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=100))
        progress.emit(_event(3, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(4, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=100))
        progress.emit(_event(5, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(6, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40))
        progress.emit(_event(7, RunEventKind.TASK_RETRY, task_id="tts", message="TTS retry 2/3"))
        progress.emit(_event(8, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=50))
        progress.emit(_event(9, RunEventKind.TASK_PROGRESS, task_id="mix", progress_percent=0, message="mixing"))
        progress.emit(_event(10, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))

    descriptions: list[str] = [description for _, description in manager.descriptions]
    assert len(manager.added) == 1
    assert descriptions == [
        "Extracting     Odcinek 01.mkv",
        "Extracted      Odcinek 01.mkv",
        "Translating    Odcinek 01.mkv",
        "Translated     Odcinek 01.mkv",
        "Synthesizing   edge · Marek · Odcinek 01.mkv",
        "Synthesizing   edge · Marek · Odcinek 01.mkv",
        "Retrying       edge · Marek · 2/3 · Odcinek 01.mkv",
        "Synthesizing   edge · Marek · Odcinek 01.mkv",
        "Audio mixing   edge · Marek · Odcinek 01.mkv",
        "Done           Odcinek 01.mkv",
    ]
    assert manager.presentations[0] == (TaskID(0), True, True, False)
    assert manager.presentations[-2:] == [
        (TaskID(0), False, False, True),
        (TaskID(0), True, True, False),
    ]
    assert manager.updates == [
        (TaskID(0), 100),
        (TaskID(0), 100),
        (TaskID(0), 40),
        (TaskID(0), 50),
        (TaskID(0), 100),
    ]


def test_bulk_extraction_forwards_every_legacy_percent_without_averaging() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("extract", "group-1", TaskKind.EXTRACT_TRACKS),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=12))
        progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=56))
        progress.emit(_event(4, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=100))

    assert manager.updates == [(TaskID(0), 12), (TaskID(0), 56), (TaskID(0), 100)]
    assert manager.descriptions[-1] == (TaskID(0), "Extracted      Odcinek 01.mkv")
    assert all(not presentation[3] for presentation in manager.presentations)


def test_elevenbytes_progress_uses_the_legacy_human_voice_label() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
        tts_profile_id="elevenbytes",
        tts_model_id="run6",
        tts_voice_label="Dallin",
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))

    assert manager.descriptions[-1] == (
        TaskID(0),
        "Synthesizing   elevenbytes/run6 · Dallin · Odcinek 01.mkv",
    )


def test_bulk_extraction_does_not_replace_a_real_backend_percent() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("extract", "group-1", TaskKind.EXTRACT_TRACKS),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=56))
        progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=55))

    assert manager.updates == [(TaskID(0), 56), (TaskID(0), 55)]


def test_tts_keeps_legacy_monotonic_visible_percentage() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=75))
        progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=25))

    assert manager.updates == [(TaskID(0), 75), (TaskID(0), 75)]


@pytest.mark.parametrize(
    ("phase", "label"),
    [
        ("normalizing", "Audio normalize"),
        ("timeline", "Audio timeline"),
        ("mixing", "Audio mixing"),
        ("narration_resume", "Audio resume"),
        ("skipped_no_spoken", "Audio skipped"),
    ],
)
def test_every_legacy_audio_phase_reuses_the_file_row(phase: str, label: str) -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("mix", "group-1", TaskKind.MIX_NARRATION),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_PROGRESS, task_id="mix", progress_percent=0, message=phase))

    assert manager.descriptions[-1] == (
        TaskID(0),
        f"{label:<14} edge · Marek · Odcinek 01.mkv",
    )
    assert manager.presentations[-1] == (TaskID(0), False, False, True)


def test_translation_retry_and_fallback_keep_the_public_legacy_phase() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_RETRY, task_id="translate", message="llm retry 1/3"))
        progress.emit(_event(3, RunEventKind.TASK_FALLBACK, task_id="translate", message="llm fallback"))

    assert manager.descriptions == [(TaskID(0), "Translating    Odcinek 01.mkv")]


def test_terminal_states_match_legacy_labels_and_freeze_rows() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"), ("group-2", "Odcinek 02"), ("group-3", "Odcinek 03")),
        (("translate", "group-2", TaskKind.TRANSLATE_SUBTITLES),),
    )

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.FAILED))
        progress.emit(
            _event(2, RunEventKind.TASK_STARTED, group_id="group-2", task_id="translate", state=TaskState.RUNNING)
        )
        progress.emit(_event(3, RunEventKind.RUN_FINISHED, group_id=None, state=TaskState.CANCELLED))

    terminal: list[tuple[TaskID, str]] = [
        item for item in manager.descriptions if item[1].startswith(("Failed", "Cancelled", "Not processed"))
    ]
    assert terminal == [
        (TaskID(0), "Failed         Odcinek 01.mkv"),
        (TaskID(1), "Cancelled      Odcinek 02.mkv"),
        (TaskID(2), "Cancelled      Odcinek 03.mkv"),
    ]
    assert manager.stopped == [TaskID(0), TaskID(1), TaskID(2)]


def test_failed_run_marks_an_unstarted_legacy_row_not_processed() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared, manager) as progress:
        progress.emit(_event(1, RunEventKind.RUN_FINISHED, group_id=None, state=TaskState.FAILED))

    assert manager.descriptions[-1] == (TaskID(0), "Not processed  Odcinek 01.mkv")
    assert manager.stopped == [TaskID(0)]


def test_real_manager_renders_legacy_bar_without_escaping_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    test_console: Console = Console(file=stream, width=140, color_system=None, force_terminal=False)
    monkeypatch.setattr(multi_module, "console", test_console)
    monkeypatch.setattr(progress_manager_module, "console", test_console)
    monkeypatch.setattr(progress_module, "console", test_console)
    prepared: PreparedAutoRun = _prepared((("group-1", "[x]"),), ())

    with RichRunProgress(prepared) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))

    output: str = stream.getvalue()
    assert "\\[" not in output
    assert "[x]" in output
    assert "Done" in output
    assert "100%" in output


def test_real_manager_keeps_one_space_before_progress_separators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    test_console: Console = Console(file=stream, width=140, color_system=None, force_terminal=False)
    monkeypatch.setattr(multi_module, "console", test_console)
    monkeypatch.setattr(progress_manager_module, "console", test_console)
    monkeypatch.setattr(progress_module, "console", test_console)
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))

    output: str = stream.getvalue()
    assert re.search(r"[█░]+ \|\s+100% \|", output)


def test_relayout_rebuilds_width_fitted_rows_without_losing_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managers: list[_FakeManager] = [_FakeManager(), _FakeManager()]
    layouts: list[str] = []
    test_console: SimpleNamespace = SimpleNamespace(width=140)

    def manager_factory(**values: object) -> _FakeManager:
        del values
        return managers.pop(0)

    monkeypatch.setattr(progress_module, "MultiProgressManager", manager_factory)
    monkeypatch.setattr(progress_module, "console", test_console)
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )
    first: _FakeManager = managers[0]
    second: _FakeManager = managers[1]

    with RichRunProgress(prepared, layout=lambda: layouts.append("render")) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40))
        test_console.width = 80
        progress.relayout()

    assert layouts == ["render", "render"]
    assert first.exited is True
    assert second.entered is True
    assert second.added == ["Synthesizing   edge · Marek · Odcinek 01.mkv"]
    assert second.updates == [(TaskID(0), 40)]


def test_relayout_reuses_progress_manager_when_only_height_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_FakeManager] = []
    layouts: list[str] = []

    def manager_factory(**values: object) -> _FakeManager:
        del values
        manager: _FakeManager = _FakeManager()
        created.append(manager)
        return manager

    monkeypatch.setattr(progress_module, "MultiProgressManager", manager_factory)
    monkeypatch.setattr(progress_module, "console", SimpleNamespace(width=140))

    with RichRunProgress(
        _prepared((("group-1", "Odcinek 01"),), ()),
        layout=lambda: layouts.append("render"),
    ) as progress:
        progress.relayout()

    assert layouts == ["render", "render"]
    assert len(created) == 1
    assert [description.rstrip() for description in created[0].added] == ["Extracting     Odcinek 01.mkv"]


@pytest.mark.parametrize("width", [20, 40, 60, 80, 100, 140])
def test_real_manager_keeps_each_file_on_one_terminal_row(
    monkeypatch: pytest.MonkeyPatch,
    width: int,
) -> None:
    stream: StringIO = StringIO()
    test_console: Console = Console(file=stream, width=width, color_system=None, force_terminal=False)
    monkeypatch.setattr(multi_module, "console", test_console)
    monkeypatch.setattr(progress_manager_module, "console", test_console)
    monkeypatch.setattr(progress_module, "console", test_console)
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "[Erai-raws] Very Long Anime Episode Name - 06 [1080p CR WEB-DL AVC AAC][MultiSub]"),),
        (),
    )

    with RichRunProgress(prepared) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))

    lines: list[str] = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    assert len(lines[0]) <= width
    assert "100%" in lines[0]


def test_real_manager_aligns_file_bars_with_single_cell_spacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream: StringIO = StringIO()
    test_console: Console = Console(file=stream, width=140, color_system=None, force_terminal=False)
    monkeypatch.setattr(multi_module, "console", test_console)
    monkeypatch.setattr(progress_manager_module, "console", test_console)
    monkeypatch.setattr(progress_module, "console", test_console)
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Short"), ("group-2", "A much longer episode filename")),
        (),
    )

    with RichRunProgress(prepared) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        progress.emit(_event(2, RunEventKind.GROUP_FINISHED, group_id="group-2", state=TaskState.SUCCEEDED))

    lines: list[str] = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0].index("█") == lines[1].index("█")
    assert all(re.search(r"[█░]+ \|\s+100% \|", line) for line in lines)


def test_stale_events_and_events_after_close_are_ignored() -> None:
    manager: _FakeManager = _FakeManager()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )
    progress: RichRunProgress = RichRunProgress(prepared, manager)

    with progress:
        progress.emit(_event(2, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(1, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=50))
    progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=80))

    assert len(manager.descriptions) == 1


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
    assert manager.updates[-1] == (TaskID(0), 50)
