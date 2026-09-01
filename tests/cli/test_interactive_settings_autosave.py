from __future__ import annotations

import time
from typing import cast

import pytest

from anishift.application import AppService, AutoPreset, AutoPresetDraft, EnvironmentSettingStatus
from anishift.application.intents import ProductIntent, ProductKind
from anishift.cli.interactive.settings import SettingsController, _Feedback
from anishift.config.field_access import assign_setting_value, read_setting_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.presets import DEFAULT_PRESET_ID
from anishift.config.user_settings import UserSettings

_DELAY = 0.5


class FakeSettingsService:
    def __init__(self) -> None:
        self.settings = UserSettings()
        self.saves: list[tuple[str, SettingValue]] = []
        self.secrets: list[tuple[str, str | None]] = []
        self.resets = 0
        self.products: frozenset[ProductKind] = frozenset(
            {ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO},
        )
        self.preset_saves = 0

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

    def environment_setting_statuses(self) -> tuple[EnvironmentSettingStatus, ...]:
        return (
            EnvironmentSettingStatus(
                setting_id="gemini_api_key",
                is_configured=False,
                is_system_override=False,
            ),
        )

    def update_secret(self, setting_id: str, value: str | None) -> None:
        self.secrets.append((setting_id, value))

    def reset_settings(self) -> UserSettings:
        self.resets += 1
        self.settings = UserSettings()
        return self.settings

    def default_preset_id(self) -> str:
        return DEFAULT_PRESET_ID

    def get_preset(self, preset_id: str) -> AutoPreset:
        return AutoPreset(
            preset_id=preset_id,
            name="Polish lector",
            products=ProductIntent(requested_products=self.products),
        )

    def save_preset(self, draft: AutoPresetDraft) -> None:
        self.preset_saves += 1
        self.products = frozenset(draft.products.requested_products)


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


def _open_field(panel: SettingsController, category: str, setting_id: str) -> None:
    _activate(panel, f"category:{category}")
    _activate(panel, f"setting:{setting_id}")


def _idle(panel: SettingsController) -> None:
    time.sleep(_DELAY)
    panel.flush_pending()


def _keys(panel: SettingsController) -> tuple[str, ...]:
    return tuple(item.key for item in panel._items)


def _stored(service: FakeSettingsService, setting_id: str) -> SettingValue:
    specs = {spec.setting_id: spec for spec in service.settings_catalog()}
    return read_setting_value(service.settings, specs[setting_id])


def test_choosing_in_a_choice_editor_needs_no_confirmation_step(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "general", "processing_order_policy")
    before = _stored(service, "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert _stored(service, "processing_order_policy") != before


def test_a_walked_choice_lands_as_one_saved_value(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "general", "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("down")
    panel.handle_key("down")
    panel.handle_key("enter")
    _idle(panel)

    assert len(service.saves) == 1


def test_only_looking_at_a_choice_reports_nothing(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "general", "processing_order_policy")
    _idle(panel)

    assert service.saves == []
    assert panel._feedback is None


def test_walking_the_menu_never_claims_a_save(panel: SettingsController, service: FakeSettingsService) -> None:
    _activate(panel, "category:subtitles")
    for _ in range(4):
        panel.handle_key("down")
    _idle(panel)

    assert service.saves == []
    assert panel._feedback is None


def test_a_real_change_is_saved_without_announcing_it(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "general", "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("enter")
    _idle(panel)

    assert len(service.saves) == 1
    assert panel._feedback is None


def test_a_stepped_number_shows_up_before_it_reaches_storage(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:subtitles")
    for index, item in enumerate(panel._items):
        if item.key == "setting:subtitle_max_chars_per_line":
            panel._selected = index
    panel.handle_key("right")

    assert panel._items[panel._selected].current == "43"
    assert service.saves == []


@pytest.mark.parametrize(
    "keys",
    [
        (),
        ("category:general",),
        ("category:subtitles",),
        ("category:output",),
        ("category:connections",),
        ("category:connections", "connection:gemini"),
        ("category:tts", f"setting:{'elevenbytes_custom_voices'}"),
    ],
)
def test_no_screen_moves_when_a_status_appears(panel: SettingsController, keys: tuple[str, ...]) -> None:
    for key in keys:
        _activate(panel, key)
    quiet = panel.render(100, 30).plain

    panel._feedback = _Feedback("✓ Przywrócono ustawienia domyślne", "success")
    noisy = panel.render(100, 30).plain

    assert quiet.count("\n") == noisy.count("\n")
    assert quiet.splitlines()[:-2] == noisy.splitlines()[:-2]


def test_a_long_status_does_not_wrap_the_screen(panel: SettingsController) -> None:
    _activate(panel, "category:subtitles")
    quiet = panel.render(60, 30).plain

    panel._feedback = _Feedback("✗ " + "bardzo długi komunikat " * 12, "error")
    noisy = panel.render(60, 30).plain

    assert quiet.count("\n") == noisy.count("\n")
    assert max(len(line) for line in noisy.splitlines()) <= 60


def test_the_status_row_is_reserved_whether_it_says_anything_or_not(panel: SettingsController) -> None:
    _activate(panel, "category:subtitles")
    quiet = panel.render(100, 30).plain

    panel._feedback = _Feedback("✗ Nie udało się zapisać ustawienia", "error")
    noisy = panel.render(100, 30).plain

    assert quiet.count("\n") == noisy.count("\n")


def test_an_editor_keeps_its_height_when_a_status_appears(panel: SettingsController) -> None:
    _open_field(panel, "general", "processing_order_policy")
    quiet = panel.render(100, 30).plain

    panel._feedback = _Feedback("✗ Nie udało się zapisać ustawienia", "error")
    noisy = panel.render(100, 30).plain

    assert quiet.count("\n") == noisy.count("\n")


def test_stepping_a_number_back_to_its_stored_value_saves_nothing(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:subtitles")
    for index, item in enumerate(panel._items):
        if item.key == "setting:subtitle_max_chars_per_line":
            panel._selected = index
    panel.handle_key("right")
    panel.handle_key("left")
    _idle(panel)

    assert service.saves == []
    assert panel._feedback is None


def test_walking_a_choice_editor_changes_nothing(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "general", "processing_order_policy")
    assert panel._editor is not None
    stored = _stored(service, "processing_order_policy")
    for _ in range(len(panel._editor.options) + 2):
        panel.handle_key("down")
    for _ in range(len(panel._editor.options) + 2):
        panel.handle_key("up")
    _idle(panel)

    assert service.saves == []
    assert _stored(service, "processing_order_policy") == stored
    assert panel._feedback is None


def test_leaving_a_choice_editor_after_walking_it_keeps_the_stored_value(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "general", "processing_order_policy")
    stored = _stored(service, "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("escape")
    _idle(panel)

    assert service.saves == []
    assert _stored(service, "processing_order_policy") == stored


def test_the_bullet_stays_on_the_stored_value_while_the_cursor_moves(panel: SettingsController) -> None:
    _open_field(panel, "general", "processing_order_policy")
    assert panel._editor is not None
    marked = panel._editor.current_value
    panel.handle_key("down")

    assert panel._editor.current_value == marked


def test_choosing_in_a_choice_editor_saves_once(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "general", "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert len(service.saves) == 1
    assert panel._editor is None
    assert panel._feedback is None


def test_walking_a_menu_changes_nothing(panel: SettingsController, service: FakeSettingsService) -> None:
    _activate(panel, "category:subtitles")
    for _ in range(6):
        panel.handle_key("down")
    panel.handle_key("home")
    panel.handle_key("end")
    panel.scroll(1)
    panel.scroll(-1)
    _idle(panel)

    assert service.saves == []


def test_closing_the_panel_saves_a_change_younger_than_the_delay(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:subtitles")
    for index, item in enumerate(panel._items):
        if item.key == "setting:subtitle_max_chars_per_line":
            panel._selected = index
    panel.handle_key("right")
    assert service.saves == []

    panel.close()

    assert _stored(service, "subtitle_max_chars_per_line") == 43


def test_closing_the_panel_twice_saves_once(panel: SettingsController, service: FakeSettingsService) -> None:
    _activate(panel, "category:subtitles")
    for index, item in enumerate(panel._items):
        if item.key == "setting:subtitle_max_chars_per_line":
            panel._selected = index
    panel.handle_key("right")
    panel.close()
    panel.close()

    assert len(service.saves) == 1


def test_closing_a_panel_without_a_pending_change_writes_nothing(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:subtitles")
    panel.close()

    assert service.saves == []
    assert panel._feedback is None


def test_the_editor_shows_no_save_action(panel: SettingsController) -> None:
    _open_field(panel, "general", "processing_order_policy")
    frame = panel.render(120, 40).plain

    assert "zapisz" not in frame.casefold()


def test_leaving_a_choice_editor_keeps_the_chosen_value(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "general", "processing_order_policy")
    before = _stored(service, "processing_order_policy")
    panel.handle_key("down")
    panel.handle_key("enter")
    panel.handle_key("escape")

    assert _stored(service, "processing_order_policy") != before


def test_typing_a_number_saves_itself_once_the_typing_stops(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "subtitles", "subtitle_max_chars_per_line")
    for character in "60":
        panel.handle_key(f"text:{character}")
    _idle(panel)

    assert _stored(service, "subtitle_max_chars_per_line") == 60


def test_the_first_typed_character_replaces_the_stored_value(panel: SettingsController) -> None:
    _open_field(panel, "subtitles", "subtitle_max_lines_per_event")
    assert panel._editor is not None
    assert panel._editor.buffer == "2"
    panel.handle_key("text:3")

    assert panel._editor.buffer == "3"


def test_typing_over_a_short_range_stays_inside_it(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "subtitles", "subtitle_max_lines_per_event")
    panel.handle_key("text:3")
    _idle(panel)

    assert _stored(service, "subtitle_max_lines_per_event") == 3
    assert panel._feedback is None


def test_an_out_of_range_number_is_not_announced_while_it_is_typed(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "subtitles", "subtitle_max_lines_per_event")
    panel.handle_key("text:9")
    _idle(panel)

    assert service.saves == []
    assert panel._feedback is None


def test_backspace_edits_the_stored_value_instead_of_replacing_it(panel: SettingsController) -> None:
    _open_field(panel, "subtitles", "subtitle_max_chars_per_line")
    assert panel._editor is not None
    assert panel._editor.buffer == "42"
    panel.handle_key("backspace")
    panel.handle_key("text:0")

    assert panel._editor.buffer == "40"


def test_an_unfinished_number_is_not_saved_before_the_typing_stops(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_field(panel, "subtitles", "subtitle_max_chars_per_line")
    panel.handle_key("text:6")
    panel.handle_key("text:0")

    assert service.saves == []


def test_a_toggled_multi_choice_saves_on_the_toggle(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_field(panel, "general", "audio_language_priority")
    panel.handle_key("down")
    panel.handle_key("space")
    _idle(panel)

    assert [setting_id for setting_id, _value in service.saves] == ["audio_language_priority"]


def test_a_secret_is_never_saved_while_it_is_being_typed(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:connections")
    _activate(panel, "connection:gemini")
    _activate(panel, "connection-secret")
    for character in "abc":
        panel.handle_key(f"text:{character}")
    _idle(panel)

    assert service.secrets == []


def test_a_secret_is_stored_once_it_is_confirmed(panel: SettingsController, service: FakeSettingsService) -> None:
    _activate(panel, "category:connections")
    _activate(panel, "connection:gemini")
    _activate(panel, "connection-secret")
    for character in "abc":
        panel.handle_key(f"text:{character}")
    panel.handle_key("enter")

    assert service.secrets == [("gemini_api_key", "abc")]


def test_the_output_screen_dropped_its_save_action(panel: SettingsController) -> None:
    _activate(panel, "category:output")
    frame = panel.render(120, 40).plain

    assert "Zapisz" not in frame
    assert "Przywróć domyślne" in frame


def test_toggling_an_output_product_is_stored_at_once(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:output")
    panel._selected = 2
    panel.handle_key("space")

    assert ProductKind.MKV in service.products
    assert service.preset_saves == 1


def test_the_output_screen_refuses_to_clear_its_last_product(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:output")
    for index in (0, 1):
        panel._selected = index
        panel.handle_key("space")

    assert service.products
    assert panel._feedback is not None
    assert panel._feedback.style == "error"


def test_the_marks_on_the_output_screen_match_what_is_stored(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:output")
    for index in (0, 1):
        panel._selected = index
        panel.handle_key("space")

    assert panel._output_products == set(service.products)


@pytest.mark.parametrize("category", ["general", "subtitles", "translation", "tts"])
def test_every_settings_screen_offers_a_reset(panel: SettingsController, category: str) -> None:
    _activate(panel, f"category:{category}")

    assert f"reset-scope:{category}" in _keys(panel)


def test_a_screen_reset_restores_only_its_own_fields(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings.subtitle_max_chars_per_line = 100
    service.settings.translation_chunk_chars = 2000
    _activate(panel, "category:subtitles")
    _activate(panel, "reset-scope:subtitles")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert _stored(service, "subtitle_max_chars_per_line") == 42
    assert _stored(service, "translation_chunk_chars") == 2000


def test_a_refused_reset_changes_nothing(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.subtitle_max_chars_per_line = 100
    _activate(panel, "category:subtitles")
    _activate(panel, "reset-scope:subtitles")
    panel.handle_key("enter")

    assert _stored(service, "subtitle_max_chars_per_line") == 100


def test_the_voice_list_offers_a_reset_that_clears_it(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _activate(panel, "category:tts")
    _activate(panel, "setting:elevenbytes_custom_voices")
    _activate(panel, "reset-scope:voices")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.settings.elevenbytes_custom_voices == []


def test_the_root_reset_still_restores_everything(panel: SettingsController, service: FakeSettingsService) -> None:
    _activate(panel, "reset-settings")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.resets == 1
