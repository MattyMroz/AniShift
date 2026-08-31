from __future__ import annotations

from typing import cast

import pytest

from anishift.application import AppService
from anishift.cli.interactive.settings import SettingsController
from anishift.config.field_access import assign_setting_value
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


_TTS_INDEX = 2

_HEIGHTS = [12, 16, 24, 60]


def _open_narration(panel: SettingsController) -> None:
    panel._selected = _TTS_INDEX
    panel.handle_key("enter")


def _lines(panel: SettingsController, rows: int) -> list[str]:
    frame = panel.render(90, rows).plain
    return [line for line in frame.split("\n") if line.strip()]


def _row_count(panel: SettingsController) -> int:
    return len(panel._items)


def test_the_narration_category_holds_more_rows_than_a_short_terminal(panel: SettingsController) -> None:
    _open_narration(panel)
    assert _row_count(panel) > 12


@pytest.mark.parametrize("rows", _HEIGHTS)
def test_the_back_row_survives_every_cursor_position(panel: SettingsController, rows: int) -> None:
    _open_narration(panel)
    for cursor in range(_row_count(panel)):
        panel._selected = cursor
        assert any("Cofnij" in line for line in _lines(panel, rows))


@pytest.mark.parametrize("rows", _HEIGHTS)
def test_the_back_row_is_the_last_row_above_the_hint(panel: SettingsController, rows: int) -> None:
    _open_narration(panel)
    panel._selected = 0
    lines = _lines(panel, rows)
    back_index = next(index for index, line in enumerate(lines) if "Cofnij" in line)
    assert back_index == len(lines) - 2


def test_a_short_terminal_still_scrolls_the_rows_above_the_back_row(panel: SettingsController) -> None:
    _open_narration(panel)
    panel._selected = 0
    top = _lines(panel, 12)
    panel._selected = _row_count(panel) - 2
    bottom = _lines(panel, 12)
    assert top != bottom
    assert any("Cofnij" in line for line in top)
    assert any("Cofnij" in line for line in bottom)


def test_the_pointer_reaches_the_back_row(panel: SettingsController) -> None:
    _open_narration(panel)
    panel._selected = _row_count(panel) - 1
    back_line = next(line for line in _lines(panel, 16) if "Cofnij" in line)
    assert "\u276f" in back_line


def test_the_pointer_leaves_the_back_row_when_the_cursor_moves_up(panel: SettingsController) -> None:
    _open_narration(panel)
    panel._selected = _row_count(panel) - 1
    panel.handle_key("up")
    back_line = next(line for line in _lines(panel, 16) if "Cofnij" in line)
    assert "\u276f" not in back_line


def test_the_root_menu_keeps_its_back_row_pinned(panel: SettingsController) -> None:
    lines = _lines(panel, 12)
    back_index = next(index for index, line in enumerate(lines) if "Cofnij" in line)
    assert back_index == len(lines) - 2


def test_a_scrolled_list_announces_rows_above_and_below(panel: SettingsController) -> None:
    _open_narration(panel)
    panel._selected = _row_count(panel) // 2
    joined = "\n".join(_lines(panel, 12))
    assert "więcej" in joined


def test_only_the_back_row_survives_a_catalog_that_cannot_load(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    _open_narration(panel)

    def _explode(draft: UserSettings | None = None) -> tuple[SettingSpec, ...]:
        del draft
        raise OSError

    service.settings_catalog = _explode  # type: ignore[method-assign]
    panel._refresh_menu()
    lines = _lines(panel, 16)
    assert sum("Cofnij" in line for line in lines) == 1
    assert any("Nie można wczytać" in line for line in lines)
