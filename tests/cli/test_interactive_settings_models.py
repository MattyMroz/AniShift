from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.planning import ExecutionPlan
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService
from anishift.cli.interactive.settings import SettingsController
from anishift.config.model_catalog import (
    CatalogDefaults,
    ModelCatalog,
    ModelEntry,
    ModelProtocol,
    ProviderEntry,
)
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ConfigError
from anishift.services.media import DefaultMediaProbe


def _unused_handler(
    run_root: Path,
    plan: ExecutionPlan,
    source_groups: Mapping[str, InspectedSourceGroup],
) -> TaskHandler:
    del run_root, plan, source_groups
    raise AssertionError("Model selection must not execute a plan")


def _catalog() -> ModelCatalog:
    return ModelCatalog(
        1,
        {"proxy": ProviderEntry("proxy", ModelProtocol.OPENAI_CHAT, "/proxy")},
        {"valid": ModelEntry("valid", "proxy", "model-1", "Valid model")},
        CatalogDefaults(),
        (),
    )


def _service(
    tmp_path: Path,
    saved: list[UserSettings],
    *,
    settings: Settings | None = None,
    preferences: UserSettings | None = None,
) -> AppService:
    return AppService(
        workspace_root=tmp_path,
        settings=settings or Settings.model_construct(openai_compatible_base_url="https://gateway.example.invalid/v1"),
        user_settings=preferences or UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=_unused_handler,
        settings_saver=saved.append,
        catalog_loader=_catalog,
        env_file=tmp_path / "unused.env",
    )


def test_first_custom_model_is_selectable_without_editing_configuration_files(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service = _service(tmp_path, saved)
    panel = SettingsController(service, lambda: None)
    panel._open_model_editor()
    assert panel._editor is not None
    assert [option.label for option in panel._editor.options] == ["Własny model…"]

    panel.handle_key("enter")
    panel.handle_key("enter")
    panel.handle_key("paste:local/model-v2:latest")
    assert saved == []
    panel.handle_key("enter")

    assert len(saved) == 1
    assert saved[0].llm_provider == "openai_compatible"
    assert saved[0].llm_provider_model_id == "local/model-v2:latest"
    assert [(option.provider_id, option.model_id) for option in service.translation_model_options()] == [
        ("openai_compatible", "local/model-v2:latest"),
    ]


def test_cancelled_custom_model_never_changes_provider_or_identifier(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service = _service(tmp_path, saved)
    previous = service.settings_snapshot()
    panel = SettingsController(service, lambda: None)
    panel._open_model_editor()
    panel.handle_key("enter")
    panel.handle_key("enter")
    panel.handle_key("text:local-model")

    panel.handle_key("escape")

    assert saved == []
    assert service.settings_snapshot() == previous


def test_retired_palantir_alias_can_be_replaced_with_an_existing_alias(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service = _service(
        tmp_path,
        saved,
        settings=Settings.model_construct(palantir_token="synthetic-token-sentinel"),  # noqa: S106
        preferences=UserSettings(
            llm_provider="palantir",
            llm_provider_model_id="retired",
            palantir_enrollment_base_url="https://enrollment.example.invalid",
        ),
    )
    assert not next(status for status in service.engine_availability() if status.engine_id == "palantir").is_available
    panel = SettingsController(service, lambda: None)
    panel._open_model_editor()
    panel.handle_key("enter")

    assert len(saved) == 1
    assert saved[0].llm_provider_model_id == "valid"
    assert next(status for status in service.engine_availability() if status.engine_id == "palantir").is_available
    with pytest.raises(ConfigError):
        service.select_translation_model("palantir", "unknown")
    assert len(saved) == 1


@pytest.mark.parametrize(
    "model_id",
    ["", "C:/private/model", "/private/model", "../model", "a/../model", "model\nprivate", "https://host/model"],
)
def test_invalid_custom_model_keeps_preferences_and_errors_private(tmp_path: Path, model_id: str) -> None:
    saved: list[UserSettings] = []
    service = _service(tmp_path, saved)
    previous = service.settings_snapshot()

    with pytest.raises(ConfigError) as caught:
        service.select_translation_model("openai_compatible", model_id)

    assert saved == []
    assert service.settings_snapshot() == previous
    if model_id:
        assert model_id not in str(caught.value)


def test_configured_secret_cannot_be_saved_as_a_model_identifier(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    secret: str = "synthetic-secret-model-sentinel"  # noqa: S105
    service = _service(
        tmp_path,
        saved,
        settings=Settings.model_construct(openai_api_key=secret),
    )

    with pytest.raises(ConfigError) as caught:
        service.select_translation_model("openai", secret)

    assert saved == []
    assert secret not in str(caught.value)


def test_custom_model_for_a_provider_with_suggestions_remains_in_the_picker(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service = _service(tmp_path, saved, settings=Settings.model_construct(openai_api_key="synthetic-token"))

    service.select_translation_model("openai", "my-custom-model")
    service.select_translation_model("openai", "my-custom-model")

    assert len(saved) == 1
    assert any(option.model_id == "my-custom-model" for option in service.translation_model_options())


def test_unconfigured_provider_cannot_be_selected(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service = _service(tmp_path, saved)

    with pytest.raises(ConfigError):
        service.select_translation_model("openai", "custom-model")

    assert saved == []


def test_stepping_a_value_does_not_reload_the_model_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[UserSettings] = []
    service = _service(
        tmp_path,
        saved,
        preferences=UserSettings(translation_engine="llm", llm_provider="palantir", llm_provider_model_id="valid"),
    )
    calls: list[str] = []

    def load_catalog() -> ModelCatalog:
        calls.append("load")
        return _catalog()

    monkeypatch.setattr(service, "model_catalog", load_catalog)
    panel = SettingsController(service, lambda: None)
    panel._selected = next(index for index, item in enumerate(panel._items) if item.key == "category:translation")
    panel.handle_key("enter")
    panel._selected = next(
        index for index, item in enumerate(panel._items) if item.key == "setting:translation_chunk_chars"
    )
    assert calls == ["load"]

    for _ in range(20):
        panel.handle_key("right")
        panel.render(100, 30)

    assert calls == ["load"]
    assert saved == []
