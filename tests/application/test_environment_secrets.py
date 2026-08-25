from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

from anishift.application import runtime
from anishift.application import service as service_module
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService
from anishift.bootstrap import AppContext, create_app_service
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ConfigError, ErrorCode
from anishift.services.media import DefaultMediaProbe


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)


def _unused_handlers(
    run_root: Path,
    plan: ExecutionPlan,
    source_groups: Mapping[str, InspectedSourceGroup],
) -> TaskHandler:
    del run_root, plan, source_groups
    raise AssertionError("Editing secrets must not execute a plan")


def _service(tmp_path: Path, env_file: Path | None) -> AppService:
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=_unused_handlers,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
        env_file=env_file,
    )


def _empty_plan() -> ExecutionPlan:
    snapshot = RunSettingsSnapshot(
        translation_profile_id="deepl",
        translation_fallback_chain=("google",),
        translation_max_retries=3,
        translation_concurrency=2,
        llm_profile_id="gemini",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=3,
        tts_group_jobs=2,
        audio_profile_id="eac3",
        composition_profile_id="default",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )
    return ExecutionPlan((), (), (), snapshot, ())


def test_update_secret_writes_prefixed_environment_key(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    service: AppService = _service(tmp_path, env_file)

    service.update_secret("gemini_api_key", "gemini-value")

    assert env_file.read_text(encoding="utf-8") == 'ANISHIFT_GEMINI_API_KEY="gemini-value"\n'


def test_update_secret_refuses_non_secret_unknown_and_preference_ids(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    service: AppService = _service(tmp_path, env_file)

    with pytest.raises(ConfigError, match="Unknown environment secret") as non_secret:
        service.update_secret("openai_compatible_base_url", "https://example.invalid")
    with pytest.raises(ConfigError, match="Unknown environment secret"):
        service.update_secret("nonexistent_api_key", "value")
    with pytest.raises(ConfigError, match="Unknown environment secret"):
        service.update_secret("translation_engine", "deepl")

    assert non_secret.value.context.code is ErrorCode.CONFIG_INVALID
    assert not env_file.exists()


def test_update_secret_never_exposes_the_value_in_errors_logs_or_results(tmp_path: Path) -> None:
    protected: str = "sentinel-secret-must-not-appear"
    env_file: Path = tmp_path / ".env"
    service: AppService = _service(tmp_path, env_file)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")
    try:
        service.update_secret("gemini_api_key", protected)
        with pytest.raises(ConfigError) as rejected:
            service.update_secret("nonexistent_api_key", protected)
    finally:
        loguru_logger.remove(handler_id)

    statuses: Mapping[str, bool] = service.reload_environment()

    assert captured
    assert all(protected not in message for message in captured)
    assert protected not in str(rejected.value)
    assert protected not in repr(rejected.value)
    assert protected not in repr(rejected.value.context)
    assert protected not in repr(statuses)
    assert statuses["gemini_api_key"] is True


def test_update_secret_preserves_comments_unrelated_keys_and_newline_style(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    env_file.write_bytes(b"# secrets\r\nANISHIFT_DEEPL_API_KEY=deepl\r\n")
    service: AppService = _service(tmp_path, env_file)

    service.update_secret("gemini_api_key", "gemini")

    assert env_file.read_bytes() == (
        b'# secrets\r\nANISHIFT_DEEPL_API_KEY=deepl\r\nANISHIFT_GEMINI_API_KEY="gemini"\r\n'
    )
    assert service.reload_environment()["deepl_api_key"] is True


def test_update_secret_clears_with_empty_value_and_removes_with_none(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    env_file.write_text("ANISHIFT_DEEPL_API_KEY=deepl\n", encoding="utf-8")
    service: AppService = _service(tmp_path, env_file)

    service.update_secret("gemini_api_key", "gemini")
    service.update_secret("gemini_api_key", "")

    assert "ANISHIFT_GEMINI_API_KEY=\n" in env_file.read_text(encoding="utf-8")
    assert service.reload_environment()["gemini_api_key"] is False

    service.update_secret("gemini_api_key", None)
    remaining: str = env_file.read_text(encoding="utf-8")

    assert "ANISHIFT_GEMINI_API_KEY" not in remaining
    assert "ANISHIFT_DEEPL_API_KEY=deepl" in remaining
    assert service.reload_environment()["gemini_api_key"] is False


def test_reload_environment_flips_missing_to_configured(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    service: AppService = _service(tmp_path, env_file)

    before: Mapping[str, bool] = service.reload_environment()
    service.update_secret("deepl_api_key", "deepl-value")
    after: Mapping[str, bool] = service.reload_environment()

    assert before["deepl_api_key"] is False
    assert after["deepl_api_key"] is True
    assert after["gemini_api_key"] is False
    assert service.environment_statuses()["deepl_api_key"] is True


def test_reload_environment_adopts_external_file_edits(tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    service: AppService = _service(tmp_path, env_file)

    assert service.environment_statuses()["openai_compatible_base_url"] is False

    env_file.write_text("ANISHIFT_OPENAI_COMPATIBLE_BASE_URL=https://example.invalid\n", encoding="utf-8")

    assert service.reload_environment()["openai_compatible_base_url"] is True


def test_production_handler_for_a_subsequent_run_reads_the_reloaded_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file: Path = tmp_path / ".env"
    monkeypatch.setattr(service_module, "env_path", lambda: env_file)
    context = AppContext(
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        workspace_root=tmp_path,
    )
    service: AppService = create_app_service(context)
    observed: list[str] = []
    original: Callable[[Settings, ExecutionPlan], object] = runtime._translation_service

    def spy(settings: Settings, plan: ExecutionPlan) -> object:
        observed.append(settings.deepl_api_key)
        return original(settings, plan)

    monkeypatch.setattr(runtime, "_translation_service", spy)
    service.update_secret("deepl_api_key", "fresh-deepl-key")
    service._handler_factory(tmp_path / "run-1", _empty_plan(), {})

    assert observed == ["fresh-deepl-key"]
    assert context.settings.deepl_api_key == ""


def test_reload_environment_defaults_to_the_repository_env_file(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, None)

    statuses: Mapping[str, bool] = service.reload_environment()

    assert "deepl_api_key" in statuses
    assert "openai_compatible_base_url" in statuses
