from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import AppService
from anishift.cli.interactive.settings import SettingsController, SettingsResult


@pytest.fixture
def controller() -> SettingsController:
    service = cast("AppService", SimpleNamespace())
    panel = SettingsController(service, lambda: None)
    panel._visible_count = 4
    return panel


def _rows(panel: SettingsController) -> int:
    return len(panel._items)


def test_the_root_menu_starts_on_its_first_row(controller: SettingsController) -> None:
    assert controller._selected == 0
    assert _rows(controller) > 4


def test_home_returns_to_the_first_row(controller: SettingsController) -> None:
    controller._selected = 3
    assert controller.handle_key("home") is SettingsResult.STAY
    assert controller._selected == 0


def test_end_reaches_the_last_row(controller: SettingsController) -> None:
    controller.handle_key("end")
    assert controller._selected == _rows(controller) - 1


def test_a_page_down_advances_by_one_screen_minus_one_row(controller: SettingsController) -> None:
    controller.handle_key("pagedown")
    assert controller._selected == 3


def test_a_page_down_stops_at_the_last_row(controller: SettingsController) -> None:
    controller.handle_key("end")
    controller.handle_key("pagedown")
    assert controller._selected == _rows(controller) - 1


def test_a_page_up_stops_at_the_first_row(controller: SettingsController) -> None:
    controller._selected = 2
    controller.handle_key("pageup")
    assert controller._selected == 0


def test_up_still_wraps_around_the_top(controller: SettingsController) -> None:
    controller.handle_key("up")
    assert controller._selected == _rows(controller) - 1


def test_down_still_wraps_around_the_bottom(controller: SettingsController) -> None:
    controller.handle_key("end")
    controller.handle_key("down")
    assert controller._selected == 0


def test_pages_never_wrap_unlike_single_steps(controller: SettingsController) -> None:
    controller.handle_key("pageup")
    assert controller._selected == 0
    controller.handle_key("end")
    for _attempt in range(4):
        controller.handle_key("pagedown")
    assert controller._selected == _rows(controller) - 1


@pytest.mark.parametrize("key", ["up", "down", "pageup", "pagedown", "home", "end"])
def test_every_navigation_key_reattaches_the_view_to_the_cursor(
    controller: SettingsController,
    key: str,
) -> None:
    controller._follow_cursor = False
    controller.handle_key(key)
    assert controller._follow_cursor is True


def test_an_unknown_key_leaves_the_cursor_alone(controller: SettingsController) -> None:
    controller._selected = 2
    controller.handle_key("any")
    assert controller._selected == 2


def test_a_stride_of_one_survives_a_list_never_rendered() -> None:
    panel = SettingsController(cast("AppService", SimpleNamespace()), lambda: None)
    panel.handle_key("pagedown")
    assert panel._selected == 1
