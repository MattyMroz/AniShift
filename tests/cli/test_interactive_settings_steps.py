from __future__ import annotations

from typing import cast

import pytest

from anishift.application import AppService
from anishift.cli.interactive.settings import SettingsController
from anishift.config.field_access import assign_setting_value, read_setting_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.user_settings import UserSettings


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


def _enter(panel: SettingsController, category: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == f"category:{category}":
            panel._selected = index
            panel.handle_key("enter")
            return
    raise AssertionError(f"category {category} is missing")


def _focus(panel: SettingsController, setting_id: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == f"setting:{setting_id}":
            panel._selected = index
            return
    raise AssertionError(f"{setting_id} is not on this screen")


def _value_shown(panel: SettingsController, setting_id: str) -> str:
    for item in panel._items:
        if item.key == f"setting:{setting_id}":
            return item.current
    raise AssertionError(f"{setting_id} is not on this screen")


def _current(service: FakeSettingsService, setting_id: str) -> float:
    specs = {spec.setting_id: spec for spec in service.settings_catalog()}
    value = read_setting_value(service.settings, specs[setting_id])
    assert isinstance(value, (int, float))
    return value


def _current_flag(service: FakeSettingsService, setting_id: str) -> bool:
    specs = {spec.setting_id: spec for spec in service.settings_catalog()}
    value = read_setting_value(service.settings, specs[setting_id])
    assert isinstance(value, bool)
    return value


def _use_llm(service: FakeSettingsService) -> None:
    service.settings.translation_engine = "llm"
    service.settings.__post_init__()


def _flush(panel: SettingsController) -> None:
    if panel._pending is not None:
        panel._pending.deadline = 0.0
    panel.flush_pending()


def test_an_arrow_defers_the_write(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    assert service.saves == []
    assert panel._pending is not None


def test_a_run_of_arrows_becomes_one_write(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    for _press in range(20):
        panel.handle_key("right")
    assert service.saves == []
    _flush(panel)
    assert len(service.saves) == 1
    assert service.saves[0][0] == "tts_profile.postprocess_tempo"


def test_the_deferred_value_is_visible_before_it_is_written(panel: SettingsController) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    before = _value_shown(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel._refresh_menu()
    assert _value_shown(panel, "tts_profile.postprocess_tempo") != before


def test_leaving_the_row_writes_at_once(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("down")
    assert len(service.saves) == 1


def test_escaping_the_category_writes_at_once(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("escape")
    assert len(service.saves) == 1


def test_opening_an_editor_writes_at_once(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("enter")
    assert len(service.saves) == 1


def test_a_fine_range_steps_by_hundredths(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    start = _current(service, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(start + 0.05)


def test_a_wide_whole_range_lands_on_round_hundreds(panel: SettingsController, service: FakeSettingsService) -> None:
    _use_llm(service)
    service.settings.llm_max_output_tokens = None
    _enter(panel, "translation")
    _focus(panel, "llm_max_output_tokens")
    panel.handle_key("right")
    panel.handle_key("right")
    panel.handle_key("right")
    _flush(panel)
    saved = service.saves[0][1]
    assert isinstance(saved, int)
    assert saved % 100 == 0


def test_a_wide_whole_range_steps_down_onto_the_grid(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _use_llm(service)
    service.settings.llm_max_output_tokens = 250
    _enter(panel, "translation")
    _focus(panel, "llm_max_output_tokens")
    panel.handle_key("left")
    _flush(panel)
    assert service.saves[0][1] == 200


def test_a_zero_batch_size_is_shown_as_the_engine_default(panel: SettingsController) -> None:
    _enter(panel, "translation")

    assert _value_shown(panel, "translation_batch_size") == "domyślnie"


def test_a_zero_batch_size_is_shown_as_every_line_for_the_llm_engine(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _use_llm(service)
    _enter(panel, "translation")

    assert _value_shown(panel, "translation_batch_size") == "wszystkie"


def test_an_unbounded_gain_steps_by_halves(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "narrator_mix_base_gain_db")
    start = _current(service, "narrator_mix_base_gain_db")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(start + 0.5)


def test_a_narrow_whole_range_steps_by_one(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "translation")
    _focus(panel, "translation_batch_size")
    start = _current(service, "translation_batch_size")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == start + 1


def test_a_boolean_flips(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "elevenbytes_vpn_enabled")
    start = _current_flag(service, "elevenbytes_vpn_enabled")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] is not start


def test_a_choice_walks_its_allowed_values(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_output_profile")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] != "eac3"


def test_free_text_ignores_arrows(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_output_bitrate")
    panel.handle_key("right")
    panel.handle_key("left")
    assert panel._pending is None
    assert service.saves == []


def test_a_value_never_passes_its_maximum(panel: SettingsController, service: FakeSettingsService) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    for _press in range(200):
        panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(2.0)


def test_an_optional_value_falls_back_to_nothing_below_its_minimum(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _use_llm(service)
    service.settings.llm_temperature = 0.0
    _enter(panel, "translation")
    _focus(panel, "llm_temperature")
    panel.handle_key("left")
    _flush(panel)
    assert service.saves[0][1] is None


def test_a_row_that_is_not_a_setting_ignores_arrows(panel: SettingsController, service: FakeSettingsService) -> None:
    panel.handle_key("right")
    assert panel._pending is None
    assert service.saves == []


def test_an_idle_window_that_has_not_passed_keeps_the_edit_pending(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _enter(panel, "tts")
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.flush_pending()
    assert service.saves == []
    assert panel._pending is not None
