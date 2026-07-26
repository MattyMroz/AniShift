from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli import pipeline_ui
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import AniShiftError
from anishift.pipeline import runner


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
