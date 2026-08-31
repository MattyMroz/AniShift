from __future__ import annotations

from typing import cast

import pytest

from anishift.application import AppService
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.settings_editors import format_voice_input, parse_voice_input
from anishift.config.field_access import assign_setting_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.user_settings import CustomVoiceSetting, UserSettings


class FakeSettingsService:
    def __init__(self) -> None:
        self.settings = UserSettings()
        self.saves: list[tuple[str, SettingValue]] = []

    def settings_snapshot(self) -> UserSettings:
        return self.settings

    def settings_catalog(self, draft: UserSettings | None = None) -> tuple[SettingSpec, ...]:
        context = SettingCatalogContext.from_user_settings(draft if draft is not None else self.settings)
        return setting_catalog(context)

    def update_setting(self, setting_id: str, value: SettingValue) -> UserSettings:
        self.saves.append((setting_id, value))
        specs = {spec.setting_id: spec for spec in self.settings_catalog()}
        assign_setting_value(self.settings, specs[setting_id], value)
        self.settings.__post_init__()
        return self.settings


@pytest.fixture
def service() -> FakeSettingsService:
    return FakeSettingsService()


@pytest.fixture
def panel(service: FakeSettingsService) -> SettingsController:
    return SettingsController(cast("AppService", service), lambda: None)


def _activate(panel: SettingsController, key: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == key:
            panel._selected = index
            panel.handle_key("enter")
            return
    raise AssertionError(f"{key} is not on this screen")


def _type(panel: SettingsController, text: str) -> None:
    for character in text:
        panel.handle_key("space" if character == " " else f"text:{character}")


def _open_voices(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    _activate(panel, "setting:elevenbytes_custom_voices")


def _keys(panel: SettingsController) -> tuple[str, ...]:
    return tuple(item.key for item in panel._items)


def test_the_voice_list_is_reachable_from_the_narration_category(panel: SettingsController) -> None:
    _open_voices(panel)
    assert "voice-add" in _keys(panel)


def test_the_narration_category_shows_the_voice_row(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    assert "setting:elevenbytes_custom_voices" in _keys(panel)


def test_an_empty_list_is_reported_as_such(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    row = next(item for item in panel._items if item.key == "setting:elevenbytes_custom_voices")
    assert row.current == "brak"


def test_a_stored_voice_is_listed_by_its_alias(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    _activate(panel, "category:tts")
    row = next(item for item in panel._items if item.key == "setting:elevenbytes_custom_voices")
    assert row.current == "kaja"


def test_a_new_voice_is_added_by_one_typed_line(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja | voice-1")
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [CustomVoiceSetting("kaja", "Kaja", "voice-1")]


def test_the_added_voice_shows_up_on_the_list(panel: SettingsController) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja | voice-1")
    panel.handle_key("enter")
    assert "voice:kaja" in _keys(panel)


def test_an_existing_voice_opens_prefilled(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    assert panel._editor.buffer == "kaja | Kaja | voice-1"


def test_editing_a_voice_replaces_it_in_place(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [
        CustomVoiceSetting("kaja", "Kaja", "voice-1"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = "kaja | Kaja Nowa | voice-9"
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [
        CustomVoiceSetting("kaja", "Kaja Nowa", "voice-9"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]


def test_an_emptied_line_removes_that_voice(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [
        CustomVoiceSetting("kaja", "Kaja", "voice-1"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = ""
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [CustomVoiceSetting("piotr", "Piotr", "voice-2")]


def test_removing_the_selected_voice_falls_back_to_a_built_in_one(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    service.settings.tts_voice_id = "kaja"
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = ""
    panel.handle_key("enter")
    assert service.settings.tts_voice_id != "kaja"


def test_a_malformed_line_is_refused_without_saving(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja")
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == []
    assert panel._editor is not None


def test_leaving_the_voice_list_returns_to_the_narration_category(panel: SettingsController) -> None:
    _open_voices(panel)
    panel.handle_key("escape")
    assert "setting:elevenbytes_custom_voices" in _keys(panel)


def test_the_voice_list_survives_a_cancelled_editor(panel: SettingsController) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    panel.handle_key("escape")
    assert panel._editor is None
    assert "voice-add" in _keys(panel)


@pytest.mark.parametrize("raw", ["", "kaja", "kaja | Kaja", "kaja | Kaja | voice | extra", " |  | "])
def test_the_parser_refuses_a_line_that_is_not_three_filled_parts(raw: str) -> None:
    with pytest.raises(ValueError, match="Custom voice needs"):
        parse_voice_input(raw)


def test_the_parser_trims_every_part() -> None:
    assert parse_voice_input("  kaja |  Kaja  | voice-1 ") == CustomVoiceSetting("kaja", "Kaja", "voice-1")


def test_a_formatted_voice_parses_back_into_the_same_voice() -> None:
    voice = CustomVoiceSetting("kaja", "Kaja", "voice-1")
    assert parse_voice_input(format_voice_input(voice)) == voice
