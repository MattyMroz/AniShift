from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anishift.bootstrap import AppContext
from anishift.cli import pipeline_ui
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.pipeline import runner
from anishift.pipeline.llm_queue import LlmProgressState
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.recovery import RecoveryAction, RecoveryContext, RecoveryDomain
from anishift.pipeline.types import FileOutcome, PipelineReport
from anishift.services.tts.types import (
    SpeechBatchProgress,
    SpeechBatchStats,
    SpeechBatchStatus,
)
from anishift.utils.rich_console import MultiProgressManager, console


def _context(root: Path) -> AppContext:
    return AppContext(Settings(), UserSettings(), root)


def test_llm_progress_rows_preallocate_natural_order_and_reuse_extraction_task(tmp_path: Path) -> None:
    episode_10 = tmp_path / "episode 10.mkv"
    episode_2 = tmp_path / "episode 2.mkv"
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.side_effect = [2, 10]

    rows = pipeline_ui._PipelineProgressRows(progress, (episode_10, episode_2), _context(tmp_path))
    extraction_task = rows.add_task(episode_2.name)
    rows.update(extraction_task, 79)

    assert [item.args[0] for item in progress.add_task.call_args_list] == [
        f"Extracting     {episode_2.name}",
        f"Extracting     {episode_10.name}",
    ]
    assert extraction_task == 2
    progress.update.assert_called_once_with(2, 79)


def test_llm_progress_rows_use_standard_zero_to_complete_tasks(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode 3.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.on_progress(path, "translating")
    rows.on_progress(path, "done")

    progress.add_task.assert_called_once_with(f"Extracting     {path.name}")
    progress.reset_task.assert_called_once_with(7)
    progress.update.assert_called_once_with(7, 100)
    assert [item.args[1] for item in progress.update_description.call_args_list] == [
        f"{'Translating':<14} {path.name}",
        f"{'Translated':<14} {path.name}",
    ]


def test_llm_progress_rows_mark_completed_extraction_on_the_same_task(
    tmp_path: Path,
) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode 3.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.update(7, 100)

    progress.update.assert_called_once_with(7, 100)
    progress.update_description.assert_called_once_with(
        7,
        f"{'Extracted':<14} {path.name}",
    )


@pytest.mark.parametrize(
    ("state", "phase"),
    [
        pytest.param("failed", "Failed", id="failed"),
        pytest.param("cancelled", "Cancelled", id="cancelled"),
        pytest.param("not_processed", "Not processed", id="not-processed"),
    ],
)
def test_llm_progress_rows_leave_unsuccessful_tasks_at_zero(
    state: LlmProgressState,
    phase: str,
    tmp_path: Path,
) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode 3.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.on_progress(path, "translating")
    rows.on_progress(path, state)

    progress.update.assert_not_called()
    progress.update_description.assert_called_with(
        7,
        f"{phase:<14} {path.name}",
    )
    progress.stop_task.assert_called_once_with(7)


def test_llm_progress_rows_retry_the_same_task_in_the_same_position(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode 3.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.on_progress(path, "translating")
    rows.on_progress(path, "failed")
    rows.on_progress(path, "translating")
    rows.on_progress(path, "done")

    progress.add_task.assert_called_once_with(f"Extracting     {path.name}")
    assert progress.reset_task.call_count == 2
    progress.stop_task.assert_called_once_with(7)
    progress.update.assert_called_once_with(7, 100)
    assert [item.args[1] for item in progress.update_description.call_args_list] == [
        f"{'Translating':<14} {path.name}",
        f"{'Failed':<14} {path.name}",
        f"{'Translating':<14} {path.name}",
        f"{'Translated':<14} {path.name}",
    ]


def test_pipeline_progress_reuses_row_for_tts_audio_and_terminal_state(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode 3.mkv"
    context = _context(tmp_path)
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), context)
    scope_id = scope_id_for_source(path, workspace_root=tmp_path)

    rows.on_batch_state(
        SpeechBatchProgress(
            scope_id=scope_id,
            completed_requests=3,
            total_requests=5,
            committed_required_requests=2,
            total_required_requests=4,
            status=SpeechBatchStatus.PARTIAL,
        ),
    )
    rows.on_audio_phase(scope_id, "normalizing")
    rows.on_pipeline_terminal(scope_id, "done")

    progress.add_task.assert_called_once()
    assert progress.reset_task.call_count == 2
    assert progress.update.call_args_list[0].args == (7, 50)
    assert progress.update.call_args_list[-1].args == (7, 100)
    progress.stop_task.assert_called_once_with(7)
    descriptions = [item.args[1] for item in progress.update_description.call_args_list]
    assert descriptions[0].startswith("Synthesizing   elevenbytes/run6 · Dallin ·")
    assert descriptions[1].startswith("Audio normalize elevenbytes/run6 · Dallin ·")
    assert descriptions[2] == f"{'Done':<14} {path.name}"
    assert any(
        item.kwargs
        == {
            "show_bar": False,
            "show_percentage": False,
            "show_spinner": True,
        }
        for item in progress.set_task_presentation.call_args_list
    )


def test_pipeline_progress_ignores_callbacks_after_close(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))
    scope_id = scope_id_for_source(path, workspace_root=tmp_path)
    progress.reset_mock()

    rows.close()
    rows.on_audio_phase(scope_id, "mixing")
    rows.on_pipeline_terminal(scope_id, "done")

    assert not progress.method_calls


def test_pipeline_progress_does_not_regress_after_terminal_or_older_tts_update(
    tmp_path: Path,
) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))
    scope_id = scope_id_for_source(path, workspace_root=tmp_path)

    rows.on_batch_state(
        SpeechBatchProgress(
            scope_id=scope_id,
            completed_requests=3,
            total_requests=4,
            committed_required_requests=3,
            total_required_requests=4,
            status=SpeechBatchStatus.PARTIAL,
        ),
    )
    rows.on_batch_state(
        SpeechBatchProgress(
            scope_id=scope_id,
            completed_requests=1,
            total_requests=4,
            committed_required_requests=1,
            total_required_requests=4,
            status=SpeechBatchStatus.PARTIAL,
        ),
    )
    rows.on_pipeline_terminal(scope_id, "done")
    calls_before_late_llm = len(progress.method_calls)
    rows.on_progress(path, "done")

    assert [item.args[1] for item in progress.update.call_args_list[:2]] == [75, 75]
    assert len(progress.method_calls) == calls_before_late_llm
    progress.update_description.assert_called_with(7, f"{'Done':<14} {path.name}")


def test_pipeline_progress_finalizes_files_without_tts(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "notes.txt"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.finalize(PipelineReport((FileOutcome(path, "done"),)))

    progress.add_task.assert_called_once()
    progress.update.assert_called_once_with(7, 100)
    progress.update_description.assert_called_once_with(
        7,
        f"{'Done':<14} {path.name}",
    )
    progress.stop_task.assert_called_once_with(7)


def test_pipeline_progress_resets_unsuccessful_terminal_row(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))

    rows.finalize(PipelineReport((FileOutcome(path, "failed"),)))

    progress.reset_task.assert_called_once_with(7)
    progress.update_description.assert_called_once_with(
        7,
        f"{'Failed':<14} {path.name}",
    )
    progress.stop_task.assert_called_once_with(7)


def test_pipeline_progress_reopens_terminal_row_for_tts_retry(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    path = tmp_path / "episode.mkv"
    rows = pipeline_ui._PipelineProgressRows(progress, (path,), _context(tmp_path))
    scope_id = scope_id_for_source(path, workspace_root=tmp_path)
    rows.on_pipeline_terminal(scope_id, "failed")
    progress.reset_mock()

    rows.on_pipeline_retry(scope_id)
    rows.on_batch_state(
        SpeechBatchProgress(
            scope_id=scope_id,
            completed_requests=1,
            total_requests=1,
            committed_required_requests=1,
            total_required_requests=1,
            status=SpeechBatchStatus.COMPLETED,
        ),
    )

    assert progress.reset_task.call_count == 2
    progress.update.assert_called_once_with(7, 100)
    assert (
        progress.update_description.call_args_list[-1]
        .args[1]
        .startswith(
            "Synthesizing   elevenbytes/run6 · Dallin ·",
        )
    )


def test_tts_summary_reports_profile_counts_and_stage_times(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outcome = FileOutcome(
        source=tmp_path / "episode.mkv",
        status="done",
        audio_time_ms=2300.0,
        tts_stats=SpeechBatchStats(
            total_requests=5,
            synthesized=3,
            resume_hits=1,
            skipped=1,
            failed=0,
            provider_calls=3,
            retries=1,
            synthesis_time_ms=61000.0,
            engine_id="edge",
            provider_model_id="edge-tts",
            voice_id="pl-PL-MarekNeural",
        ),
    )
    rendered: list[str] = []
    monkeypatch.setattr(console, "print", rendered.append)

    pipeline_ui._render_tts_summary(PipelineReport((outcome,)))

    assert any("TTS edge/edge-tts · pl-PL-MarekNeural" in item for item in rendered)
    assert any("Events 5 · synthesized 3 · resumed 1 · skipped 1 · failed 0" in item for item in rendered)
    assert any("Provider calls 3 · retries 1" in item for item in rendered)
    assert any("TTS 01:01 · audio 00:02" in item for item in rendered)


def test_pipeline_command_uses_timer_formatter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.txt"
    source.touch()
    report = PipelineReport((FileOutcome(source, "done"),))
    timer = MagicMock()
    timer.duration_ns = 2_345_000_000
    timer.start_date = None
    timer.end_date = None
    formatted: list[tuple[int, object, object, str]] = []

    def fake_pipeline(*_: object, **__: object) -> PipelineReport:
        return report

    def fake_timer(name: str, *, auto_start: bool) -> MagicMock:
        assert name == "pipeline"
        assert auto_start
        return timer

    monkeypatch.setattr(pipeline_ui, "Timer", fake_timer)
    monkeypatch.setattr(pipeline_ui, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(pipeline_ui, "_render_report", lambda _report: None)
    monkeypatch.setattr(
        pipeline_ui,
        "format_duration",
        lambda duration_ns, start_date, end_date, *, mode: formatted.append((duration_ns, start_date, end_date, mode)),
    )

    pipeline_ui.run_pipeline_command(
        AppContext(Settings(), UserSettings(mode="manual"), tmp_path),
    )

    timer.stop.assert_called_once_with()
    assert formatted == [(2_345_000_000, None, None, "minimal")]


def test_shared_recovery_prompt_accepts_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mkv"
    recovery = RecoveryContext(
        domain=RecoveryDomain.TTS,
        error=ErrorContext(
            code=ErrorCode.TTS_RATE_LIMITED,
            message="rate limited",
        ),
        completed_files=(),
        failed_files=(source,),
        pending_files=(),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "retry")
    monkeypatch.setattr(console, "print", lambda *_args, **_kwargs: None)

    action = pipeline_ui._choose_recovery(_context(tmp_path), recovery)

    assert action is RecoveryAction.RETRY


def test_llm_progress_names_file_provider_and_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(
            translation_engine="llm",
            llm_provider="gemini",
            llm_provider_model_id="gemini-3.5-flash-lite",
        ),
        tmp_path,
    )
    rendered: list[str] = []
    monkeypatch.setattr(console, "print", rendered.append)
    path = tmp_path / "episode 3.mkv"

    pipeline_ui._render_llm_progress(context, path, "translating")
    pipeline_ui._render_llm_progress(context, path, "done")

    assert "Translating" in rendered[0]
    assert path.name in rendered[0]
    assert "gemini/gemini-3.5-flash-lite" in rendered[0]
    assert "Translated" in rendered[1]
    assert path.name in rendered[1]


def test_pipeline_command_renders_invalid_custom_prompt_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.txt"
    source.write_text("Source", encoding="utf-8")
    config_dir = tmp_path / "config"
    prompt = config_dir / "prompts" / "tasks" / "broken.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("", encoding="utf-8")
    context = AppContext(
        Settings(gemini_api_key="secret"),
        UserSettings(translation_engine="llm"),
        tmp_path,
    )
    rendered: list[AniShiftError] = []
    monkeypatch.setattr(runner, "config_path", lambda: config_dir / "settings.json")
    monkeypatch.setattr(pipeline_ui, "_render_pipeline_error", rendered.append)

    pipeline_ui.run_pipeline_command(context)

    assert len(rendered) == 1
    assert "empty" in rendered[0].context.message
