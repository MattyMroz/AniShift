from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli.settings_panel import (
    _LLM_FIELDS,
    _prompt_registry,
    _provider_availability,
    _step_field,
    _translation_engines,
    _visible_fields,
)
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.services.llm.engines import suggested_model_ids
from anishift.services.translation.engines.llm.prompts import PromptRegistry


def _context(*, gemini_key: str = "", compatible_url: str = "") -> AppContext:
    return AppContext(
        settings=Settings(
            gemini_api_key=gemini_key,
            openai_compatible_base_url=compatible_url,
        ),
        user_settings=UserSettings(),
        workspace_root=Path("workspace"),
    )


def test_translation_picker_keeps_llm_and_unconfigured_deepl_visible() -> None:
    engines = _translation_engines()
    assert "llm" in engines
    assert "deepl" in engines


def test_provider_availability_reports_missing_and_ready_states() -> None:
    assert _provider_availability(_context(), "gemini") == "missing key"
    assert _provider_availability(_context(gemini_key="key"), "gemini") == "ready"
    assert _provider_availability(_context(), "openai_compatible") == "missing base URL"
    assert _provider_availability(_context(compatible_url="http://localhost"), "openai_compatible") == "ready"


def test_llm_fields_are_visible_before_selecting_llm_translation() -> None:
    settings = UserSettings(translation_engine="google")
    keys = [field.key for field in _visible_fields(settings)]
    assert [field.key for field in _LLM_FIELDS] == keys[4:10]


def test_processing_order_picker_cycles_between_supported_policies() -> None:
    settings = UserSettings()
    field = next(field for field in _visible_fields(settings) if field.key == "processing_order_policy")

    _step_field(settings, field, 1, ("google", "deepl", "llm"), PromptRegistry())

    assert settings.processing_order_policy == "strict_natural"


def test_provider_change_moves_known_suggestion_to_new_provider_default() -> None:
    settings = UserSettings(
        llm_provider="gemini",
        llm_provider_model_id=suggested_model_ids("gemini")[0],
    )
    field = next(field for field in _LLM_FIELDS if field.key == "llm_provider")
    _step_field(
        settings,
        field,
        1,
        ("google", "deepl", "llm"),
        PromptRegistry(),
    )
    assert settings.llm_provider != "gemini"
    assert settings.llm_provider_model_id == suggested_model_ids(settings.llm_provider)[0]


def test_provider_change_preserves_custom_model_id() -> None:
    settings = UserSettings(
        llm_provider="gemini",
        llm_provider_model_id="my-custom-model",
    )
    field = next(field for field in _LLM_FIELDS if field.key == "llm_provider")
    _step_field(
        settings,
        field,
        1,
        ("google", "deepl", "llm"),
        PromptRegistry(),
    )
    assert settings.llm_provider_model_id == "my-custom-model"


def test_module_picker_adds_many_and_left_removes_last() -> None:
    settings = UserSettings()
    field = next(field for field in _LLM_FIELDS if field.key == "llm_module_ids")
    registry = PromptRegistry()

    _step_field(settings, field, 1, ("google", "deepl", "llm"), registry)
    _step_field(settings, field, 1, ("google", "deepl", "llm"), registry)

    assert len(settings.llm_module_ids) == min(2, len(registry.list_ids("module")))
    _step_field(settings, field, -1, ("google", "deepl", "llm"), registry)
    assert len(settings.llm_module_ids) == max(0, min(2, len(registry.list_ids("module"))) - 1)


def test_prompt_registry_uses_config_path_outside_current_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "project" / "config"
    task_dir = config_dir / "prompts" / "tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "custom_task.txt").write_text("Custom prompt", encoding="utf-8")
    monkeypatch.setattr("anishift.cli.settings_panel.config_path", lambda: config_dir / "settings.json")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert "custom_task" in _prompt_registry().list_ids("task")
