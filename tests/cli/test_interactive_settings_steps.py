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

_TTS_INDEX = 2

_TRANSLATION_INDEX = 1


class _FakeService:
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
def service() -> _FakeService:
    return _FakeService()


@pytest.fixture
def panel(service: _FakeService) -> SettingsController:
    return SettingsController(cast("AppService", service), lambda: None)


def _open(panel: SettingsController, index: int) -> None:
    panel._selected = index
    panel.handle_key("enter")


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


def _current(service: _FakeService, setting_id: str) -> SettingValue:
    specs = {spec.setting_id: spec for spec in service.settings_catalog()}
    return read_setting_value(service.settings, specs[setting_id])


def _use_llm(service: _FakeService) -> None:
    service.settings.translation_engine = "llm"
    service.settings.translation_fallback_chain = ["llm"]
    service.settings.__post_init__()


def _flush(panel: SettingsController) -> None:
    if panel._pending is not None:
        panel._pending.deadline = 0.0
    panel.flush_pending()


def test_an_arrow_defers_the_write(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    assert service.saves == []
    assert panel._pending is not None


def test_a_run_of_arrows_becomes_one_write(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    for _press in range(20):
        panel.handle_key("right")
    assert service.saves == []
    _flush(panel)
    assert len(service.saves) == 1
    assert service.saves[0][0] == "tts_profile.postprocess_tempo"


def test_the_deferred_value_is_visible_before_it_is_written(panel: SettingsController) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    before = _value_shown(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel._refresh_menu()
    assert _value_shown(panel, "tts_profile.postprocess_tempo") != before


def test_leaving_the_row_writes_at_once(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("down")
    assert len(service.saves) == 1


def test_escaping_the_category_writes_at_once(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("escape")
    assert len(service.saves) == 1


def test_opening_an_editor_writes_at_once(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.handle_key("enter")
    assert len(service.saves) == 1


def test_a_fine_range_steps_by_hundredths(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    start = _current(service, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(start + 0.05)


def test_a_wide_whole_range_steps_by_hundreds(panel: SettingsController, service: _FakeService) -> None:
    _use_llm(service)
    _open(panel, _TRANSLATION_INDEX)
    _focus(panel, "llm_max_output_tokens")
    panel.handle_key("right")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == 101


def test_an_unbounded_gain_steps_by_halves(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "narrator_mix_base_gain_db")
    start = _current(service, "narrator_mix_base_gain_db")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(start + 0.5)


def test_a_narrow_whole_range_steps_by_one(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TRANSLATION_INDEX)
    _focus(panel, "translation_batch_size")
    start = _current(service, "translation_batch_size")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == start + 1


def test_a_boolean_flips(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "elevenbytes_vpn_enabled")
    start = _current(service, "elevenbytes_vpn_enabled")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] is not start


def test_a_choice_walks_its_allowed_values(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_output_profile")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] != "eac3"


def test_free_text_ignores_arrows(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_output_bitrate")
    panel.handle_key("right")
    panel.handle_key("left")
    assert panel._pending is None
    assert service.saves == []


def test_a_value_never_passes_its_maximum(panel: SettingsController, service: _FakeService) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    for _press in range(200):
        panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(2.0)


def test_an_optional_value_falls_back_to_nothing_below_its_minimum(
    panel: SettingsController,
    service: _FakeService,
) -> None:
    _use_llm(service)
    _open(panel, _TRANSLATION_INDEX)
    _focus(panel, "llm_temperature")
    panel.handle_key("right")
    _flush(panel)
    assert service.saves[0][1] == pytest.approx(0.0)
    _focus(panel, "llm_temperature")
    panel.handle_key("left")
    _flush(panel)
    assert service.saves[1][1] is None


def test_a_row_that_is_not_a_setting_ignores_arrows(panel: SettingsController, service: _FakeService) -> None:
    panel.handle_key("right")
    assert panel._pending is None
    assert service.saves == []


def test_an_idle_window_that_has_not_passed_keeps_the_edit_pending(
    panel: SettingsController,
    service: _FakeService,
) -> None:
    _open(panel, _TTS_INDEX)
    _focus(panel, "tts_profile.postprocess_tempo")
    panel.handle_key("right")
    panel.flush_pending()
    assert service.saves == []
    assert panel._pending is not None
