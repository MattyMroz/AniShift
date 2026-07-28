from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anishift.bootstrap import AppContext
from anishift.cli import pipeline_ui
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import AniShiftError
from anishift.pipeline import runner
from anishift.pipeline.llm_queue import LlmProgressState
from anishift.utils.rich_console import MultiProgressManager, console


def test_llm_progress_rows_use_standard_zero_to_complete_tasks(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    rows = pipeline_ui._LlmProgressRows(progress)
    path = tmp_path / "episode 3.mkv"

    rows.on_progress(path, "translating")
    rows.on_progress(path, "translating")
    rows.on_progress(path, "done")

    progress.add_task.assert_called_once_with(f"Translating {path.name}")
    progress.update.assert_called_once_with(7, 100)


@pytest.mark.parametrize("state", ["failed", "cancelled", "not_processed"])
def test_llm_progress_rows_leave_unsuccessful_tasks_at_zero(
    state: LlmProgressState,
    tmp_path: Path,
) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.return_value = 7
    rows = pipeline_ui._LlmProgressRows(progress)
    path = tmp_path / "episode 3.mkv"

    rows.on_progress(path, "translating")
    rows.on_progress(path, state)

    progress.update.assert_not_called()
    progress.stop_task.assert_called_once_with(7)


def test_llm_progress_rows_create_a_fresh_task_after_failed_retry(tmp_path: Path) -> None:
    progress = MagicMock(spec=MultiProgressManager)
    progress.add_task.side_effect = [7, 8]
    rows = pipeline_ui._LlmProgressRows(progress)
    path = tmp_path / "episode 3.mkv"

    rows.on_progress(path, "translating")
    rows.on_progress(path, "failed")
    rows.on_progress(path, "translating")
    rows.on_progress(path, "done")

    assert progress.add_task.call_count == 2
    progress.stop_task.assert_called_once_with(7)
    progress.update.assert_called_once_with(8, 100)


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
