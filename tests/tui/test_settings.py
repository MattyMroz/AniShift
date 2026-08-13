from __future__ import annotations

import asyncio
from unittest.mock import Mock

from textual.widgets import Button, Input, Select, Static
from tui_fakes import app_service

from anishift.config.field_catalog import SettingCatalogContext, setting_catalog
from anishift.config.user_settings import UserSettings
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import SettingsScreen, WorkspaceScreen
from anishift.tui.widgets.setting_field import SettingField


def _settings_service() -> Mock:
    service = app_service()
    draft = UserSettings()
    service.settings_snapshot.return_value = draft
    service.settings_catalog.side_effect = lambda current=None: setting_catalog()
    service.environment_statuses.return_value = {
        "deepl_api_key": True,
        "elevenlabs_api_key": False,
        "anthropic_api_key": False,
        "gemini_api_key": True,
        "openai_api_key": False,
        "deepseek_api_key": False,
        "openrouter_api_key": False,
        "openai_compatible_api_key": False,
        "openai_compatible_base_url": False,
    }
    return service


async def _assert_save_and_secret_status() -> None:
    service = _settings_service()
    app = AniShiftApp(service)
    async with app.run_test(size=(140, 44)) as pilot:
        await app.open_route("settings")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert not any(field.spec.scope.value.endswith("run") for field in app.screen.query(SettingField))
        configured = app.screen.query_one("#setting-deepl_api_key", Static)
        missing = app.screen.query_one("#setting-elevenlabs_api_key", Static)
        assert str(configured.render()) == "configured"
        assert str(missing.render()) == "missing"
        translation_concurrency = app.screen.query_one("#setting-translation_concurrency", Input)
        translation_concurrency.value = "3"
        app.screen.query_one("#settings-save", Button).press()
        await pilot.pause()
        saved = service.save_settings.call_args.args[0]
        assert isinstance(saved, UserSettings)
        assert saved.translation_concurrency == 3
        assert not hasattr(saved, "deepl_api_key")


def test_settings_save_uses_typed_fields_without_exposing_secrets() -> None:
    asyncio.run(_assert_save_and_secret_status())


async def _assert_dynamic_fields_and_cancel() -> None:
    service = _settings_service()

    def catalog(current: UserSettings | None = None) -> object:
        return setting_catalog(SettingCatalogContext.from_user_settings(current or UserSettings()))

    service.settings_catalog.side_effect = catalog
    app = AniShiftApp(service)
    async with app.run_test(size=(140, 44)) as pilot:
        await app.open_route("settings")
        await pilot.pause()
        engine = app.screen.query_one("#setting-tts_engine", Select)
        for _ in range(20):
            if engine.is_mounted and engine.children:
                break
            await pilot.pause(0.01)
        engine.value = "sapi"
        await pilot.pause()
        assert isinstance(app.screen.query_one("#setting-tts_profile-native_rate"), Input)
        app.screen.query_one("#settings-cancel", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, WorkspaceScreen)
        service.save_settings.assert_not_called()


def test_settings_rebuilds_provider_fields_and_cancel_discards() -> None:
    asyncio.run(_assert_dynamic_fields_and_cancel())
