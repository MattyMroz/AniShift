from __future__ import annotations

import re
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import ArtifactKind, RunEvent, RunEventKind, TaskKind, TaskState
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.run import PreparedAutoRun


class _BlockingInvalidate:
    def __init__(self) -> None:
        self.armed: threading.Event = threading.Event()
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.calls: int = 0

    def __call__(self) -> None:
        self.calls += 1
        if self.armed.is_set() and not self.entered.is_set():
            self.entered.set()
            assert self.release.wait(timeout=5)


def _prepared(
    groups: tuple[tuple[str, str], ...],
    tasks: tuple[tuple[str, str, TaskKind], ...],
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


def _lines(progress: RichRunProgress, columns: int = 140) -> list[str]:
    return progress.render(columns).plain.split("\n")


def _parse(plain: str) -> list[tuple[str, int | None]]:
    rows: list[tuple[str, int | None]] = []
    for line in plain.split("\n"):
        head, percent_text, _ = line.split(" | ")
        percent: int | None = None if percent_text.strip() == "--" else int(percent_text.strip().rstrip("%"))
        rows.append((head.rstrip("\u2588\u258c\u2591 "), percent))
    return rows


def _rows(progress: RichRunProgress, columns: int = 140) -> list[tuple[str, int | None]]:
    return _parse(progress.render(columns).plain)


def _styles(progress: RichRunProgress, columns: int = 140) -> set[str]:
    return {str(span.style) for span in progress.render(columns).spans}


def _all_stages() -> tuple[tuple[str, str, TaskKind], ...]:
    return (
        ("extract", "group-1", TaskKind.EXTRACT_SUBTITLES),
        ("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),
        ("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),
        ("mix", "group-1", TaskKind.MIX_NARRATION),
    )


def test_progress_preallocates_rows_in_natural_order() -> None:
    frames: list[str] = []
    prepared: PreparedAutoRun = _prepared((("group-2", "Odcinek 02"), ("group-10", "Odcinek 10")), ())

    with RichRunProgress(prepared, lambda: frames.append("frame")) as progress:
        rows: list[tuple[str, int | None]] = _rows(progress)

    assert progress.row_count == 2
    assert rows == [
        ("Extracting     Odcinek 02.mkv", 0),
        ("Extracting     Odcinek 10.mkv", 0),
    ]
    assert frames == ["frame", "frame"]


def test_an_extracting_row_shows_a_bar_percentage_and_elapsed_clock() -> None:
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared, lambda: None) as progress:
        line: str = _lines(progress)[0]

    assert re.fullmatch(
        r"Extracting {5}Odcinek 01\.mkv [\u2588\u258c\u2591]+ \| {3}0% \| \d\d:\d\d:\d\d\.\d\d\d",
        line,
    )


def test_file_reuses_one_row_across_every_auto_stage() -> None:
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), _all_stages())
    seen: list[tuple[str, int | None]] = []

    with RichRunProgress(prepared, lambda: None) as progress:
        for event in (
            _event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING),
            _event(2, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=100),
            _event(3, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING),
            _event(4, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=100),
            _event(5, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING),
            _event(6, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40),
            _event(7, RunEventKind.TASK_RETRY, task_id="tts", message="TTS retry 2/3"),
            _event(8, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=50),
            _event(9, RunEventKind.TASK_PROGRESS, task_id="mix", progress_percent=0, message="mixing"),
            _event(10, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED),
        ):
            progress.emit(event)
            seen.append(_rows(progress)[0])

    assert progress.row_count == 1
    assert seen == [
        ("Extracting     Odcinek 01.mkv", None),
        ("Extracted      Odcinek 01.mkv", 100),
        ("Translating    Odcinek 01.mkv", None),
        ("Translated     Odcinek 01.mkv", 100),
        ("Synthesizing   Odcinek 01.mkv", None),
        ("Synthesizing   Odcinek 01.mkv", 40),
        ("Retrying       Odcinek 01.mkv", None),
        ("Synthesizing   Odcinek 01.mkv", 50),
        ("Audio mixing   Odcinek 01.mkv", None),
        ("Done           Odcinek 01.mkv", 100),
    ]


def test_bulk_extraction_forwards_every_percent_without_averaging() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("extract", "group-1", TaskKind.EXTRACT_TRACKS),),
    )
    percents: list[int | None] = []

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING))
        for sequence, percent in ((2, 12), (3, 56), (4, 100)):
            progress.emit(_event(sequence, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=percent))
            percents.append(_rows(progress)[0][1])

    assert percents == [12, 56, 100]
    assert _rows(progress)[0][0] == "Extracted      Odcinek 01.mkv"


def test_extraction_keeps_the_backend_percent_even_when_it_drops() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("extract", "group-1", TaskKind.EXTRACT_TRACKS),),
    )
    percents: list[int | None] = []

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="extract", state=TaskState.RUNNING))
        for sequence, percent in ((2, 56), (3, 55)):
            progress.emit(_event(sequence, RunEventKind.TASK_PROGRESS, task_id="extract", progress_percent=percent))
            percents.append(_rows(progress)[0][1])

    assert percents == [56, 55]


def test_tts_keeps_a_monotonic_visible_percentage() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )
    percents: list[int | None] = []

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        for sequence, percent in ((2, 75), (3, 25)):
            progress.emit(_event(sequence, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=percent))
            percents.append(_rows(progress)[0][1])

    assert percents == [75, 75]


def test_a_synthesizing_row_names_only_the_file() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        description: str = _rows(progress)[0][0]

    assert description == "Synthesizing   Odcinek 01.mkv"
    assert "\u00b7" not in description


def test_a_retry_signals_itself_without_a_counter_or_a_width_change() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        before: str = _lines(progress)[0]
        progress.emit(_event(2, RunEventKind.TASK_RETRY, task_id="tts", message="TTS retry 2/3"))
        after: str = _lines(progress)[0]

    assert _rows(progress)[0][0] == "Retrying       Odcinek 01.mkv"
    assert "2/3" not in after
    assert len(after) == len(before)
    assert "warning" in _styles(progress)


@pytest.mark.parametrize(
    ("phase", "label"),
    [
        ("normalizing", "Normalizing"),
        ("timeline", "Audio timeline"),
        ("mixing", "Audio mixing"),
        ("narration_resume", "Audio resume"),
        ("skipped_no_spoken", "Audio skipped"),
    ],
)
def test_every_audio_phase_reuses_the_file_row(phase: str, label: str) -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("mix", "group-1", TaskKind.MIX_NARRATION),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_PROGRESS, task_id="mix", progress_percent=0, message=phase))

    assert progress.row_count == 1
    assert _rows(progress) == [(f"{label:<14} Odcinek 01.mkv", None)]
    assert "%" not in progress.render(140).plain


def test_translation_retry_is_visible_without_a_fabricated_percentage() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_RETRY, task_id="translate", message="llm retry 1/3"))
        progress.emit(_event(3, RunEventKind.TASK_FALLBACK, task_id="translate", message="llm fallback"))

    assert _rows(progress) == [("Retrying       Odcinek 01.mkv", None)]


def test_render_progress_uses_backend_measurements_and_brand_gradient() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Episode"),),
        (("compose", "group-1", TaskKind.COMPOSE_MKV),),
    )
    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="compose", state=TaskState.RUNNING))
        assert _rows(progress) == [("Rendering      Episode.mkv", None)]
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="compose", progress_percent=60))
        assert _rows(progress) == [("Rendering      Episode.mkv", 60)]
        colors: set[str] = {style for style in _styles(progress) if style.startswith("#")}
        assert len(colors) > 2


def test_early_publication_does_not_hide_later_speech_work() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Episode"),),
        (("publish", "group-1", TaskKind.PUBLISH_ARTIFACT), ("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH)),
    )
    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="publish", state=TaskState.RUNNING))
        assert _rows(progress) == [("Publishing     Episode.mkv", None)]
        progress.emit(_event(2, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=35))
        assert _rows(progress) == [("Synthesizing   Episode.mkv", 35)]


@pytest.mark.parametrize("publish_finishes_first", [False, True])
@pytest.mark.parametrize("kind", [TaskKind.SYNTHESIZE_SPEECH, TaskKind.MIX_NARRATION])
def test_background_publication_never_hides_active_speech(publish_finishes_first: bool, kind: TaskKind) -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Episode"),),
        (("publish", "group-1", TaskKind.PUBLISH_ARTIFACT), ("tts", "group-1", kind)),
    )
    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        phase: str | None = "mixing" if kind is TaskKind.MIX_NARRATION else None
        label: str = "Audio processing" if phase else "Synthesizing"
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40, message=phase))
        progress.emit(_event(3, RunEventKind.TASK_STARTED, task_id="publish", state=TaskState.RUNNING))
        assert _rows(progress) == [(f"{label:<14} Episode.mkv", 40)]
        finished: str = "publish" if publish_finishes_first else "tts"
        progress.emit(_event(4, RunEventKind.TASK_FINISHED, task_id=finished, state=TaskState.SUCCEEDED))
        if publish_finishes_first:
            progress.emit(_event(5, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=60))
            assert _rows(progress) == [(f"{label:<14} Episode.mkv", 60)]
        else:
            assert _rows(progress) == [("Publishing     Episode.mkv", None)]


def test_terminal_states_label_and_freeze_every_row() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"), ("group-2", "Odcinek 02"), ("group-3", "Odcinek 03")),
        (("translate", "group-2", TaskKind.TRANSLATE_SUBTITLES),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.FAILED))
        progress.emit(
            _event(2, RunEventKind.TASK_STARTED, group_id="group-2", task_id="translate", state=TaskState.RUNNING)
        )
        progress.emit(_event(3, RunEventKind.RUN_FINISHED, group_id=None, state=TaskState.CANCELLED))
        progress.emit(
            _event(4, RunEventKind.TASK_PROGRESS, group_id="group-2", task_id="translate", progress_percent=90)
        )

    assert _rows(progress) == [
        ("Failed         Odcinek 01.mkv", 0),
        ("Cancelled      Odcinek 02.mkv", 0),
        ("Cancelled      Odcinek 03.mkv", 0),
    ]
    assert {"error", "warning"} <= _styles(progress)


def test_a_failed_run_marks_an_unstarted_row_not_processed() -> None:
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.RUN_FINISHED, group_id=None, state=TaskState.FAILED))

    assert _rows(progress) == [("Not processed  Odcinek 01.mkv", 0)]
    assert "error" in _styles(progress)


def test_a_bracketed_filename_survives_without_markup_escaping() -> None:
    prepared: PreparedAutoRun = _prepared((("group-1", "[x]"),), ())

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        line: str = _lines(progress)[0]

    assert "[x].mkv" in line
    assert "\\[" not in line
    assert "Done" in line
    assert "100%" in line


def test_a_row_keeps_one_space_before_every_progress_separator() -> None:
    prepared: PreparedAutoRun = _prepared((("group-1", "Odcinek 01"),), ())

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        line: str = _lines(progress)[0]

    assert re.search(r"[\u2588\u258c\u2591]+ \| +100% \| ", line)


def test_rendering_at_another_width_refits_rows_without_losing_state() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40))
        wide: list[tuple[str, int | None]] = _rows(progress, 140)
        narrow: list[tuple[str, int | None]] = _rows(progress, 80)

    assert wide == [("Synthesizing   Odcinek 01.mkv", 40)]
    assert narrow == wide
    assert len(_lines(progress, 140)[0]) > len(_lines(progress, 80)[0])


def test_rendering_a_shorter_window_keeps_every_row_intact() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"), ("group-2", "Odcinek 02")),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING))
        progress.emit(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=40))
        full: list[tuple[str, int | None]] = _rows(progress)
        first_only: list[tuple[str, int | None]] = _parse(progress.render(140, limit=1).plain)
        last_only: list[tuple[str, int | None]] = _parse(progress.render(140, offset=1, limit=1).plain)

    assert full == [("Synthesizing   Odcinek 01.mkv", 40), ("Extracting     Odcinek 02.mkv", 0)]
    assert first_only == [full[0]]
    assert last_only == [full[1]]


@pytest.mark.parametrize("width", [40, 60, 80, 100, 140])
def test_every_file_fits_one_terminal_row(width: int) -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "[Erai-raws] Very Long Anime Episode Name - 06 [1080p CR WEB-DL AVC AAC][MultiSub]"),),
        (),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        lines: list[str] = _lines(progress, width)

    assert len(lines) == 1
    assert len(lines[0]) <= width
    assert "100%" in lines[0]


def test_file_bars_align_across_rows_of_different_name_length() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Short"), ("group-2", "A much longer episode filename")),
        (),
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.GROUP_FINISHED, state=TaskState.SUCCEEDED))
        progress.emit(_event(2, RunEventKind.GROUP_FINISHED, group_id="group-2", state=TaskState.SUCCEEDED))
        lines: list[str] = _lines(progress)

    assert len(lines) == 2
    assert lines[0].index("\u2588") == lines[1].index("\u2588")
    assert all(re.search(r"[\u2588\u258c\u2591]+ \| +100% \| ", line) for line in lines)


def test_stale_events_and_events_after_close_are_ignored() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )
    progress: RichRunProgress = RichRunProgress(prepared, lambda: None)

    with progress:
        progress.emit(_event(2, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(_event(1, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=50))
    progress.emit(_event(3, RunEventKind.TASK_PROGRESS, task_id="translate", progress_percent=80))

    assert _rows(progress) == [("Translating    Odcinek 01.mkv", None)]


def test_events_from_another_run_are_ignored() -> None:
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("translate", "group-1", TaskKind.TRANSLATE_SUBTITLES),),
    )
    foreign: RunEvent = RunEvent(
        run_id="run-2",
        sequence=2,
        kind=RunEventKind.TASK_PROGRESS,
        group_id="group-1",
        task_id="translate",
        progress_percent=70,
    )

    with RichRunProgress(prepared, lambda: None) as progress:
        progress.emit(_event(1, RunEventKind.TASK_STARTED, task_id="translate", state=TaskState.RUNNING))
        progress.emit(foreign)

    assert progress.run_id == "run-1"
    assert _rows(progress) == [("Translating    Odcinek 01.mkv", None)]


def test_concurrent_events_settle_in_sequence_order() -> None:
    invalidate: _BlockingInvalidate = _BlockingInvalidate()
    prepared: PreparedAutoRun = _prepared(
        (("group-1", "Odcinek 01"),),
        (("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH),),
    )

    with RichRunProgress(prepared, invalidate) as progress:
        invalidate.armed.set()
        started: threading.Thread = threading.Thread(
            target=progress.emit,
            args=(_event(1, RunEventKind.TASK_STARTED, task_id="tts", state=TaskState.RUNNING),),
        )
        started.start()
        assert invalidate.entered.wait(timeout=5)
        progressed: threading.Thread = threading.Thread(
            target=progress.emit,
            args=(_event(2, RunEventKind.TASK_PROGRESS, task_id="tts", progress_percent=50),),
        )
        progressed.start()
        progressed.join(timeout=5)
        invalidate.release.set()
        started.join(timeout=5)

    assert not started.is_alive()
    assert not progressed.is_alive()
    assert _rows(progress) == [("Synthesizing   Odcinek 01.mkv", 50)]
