from __future__ import annotations

from typing import cast

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.data_structures import Point
from prompt_toolkit.input import DummyInput
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType, MouseModifier
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from anishift.application import AppService
from anishift.cli.interactive.prompts import TerminalRenderer, _WheelControl
from anishift.cli.interactive.settings import SettingsController
from anishift.config.field_access import assign_setting_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.user_settings import UserSettings

_TTS_INDEX = 2


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
    controller = SettingsController(cast("AppService", service), lambda: None)
    controller._selected = _TTS_INDEX
    controller.handle_key("enter")
    return controller


def _wheel(event_type: MouseEventType) -> MouseEvent:
    return MouseEvent(
        position=Point(x=0, y=0),
        event_type=event_type,
        button=MouseButton.NONE,
        modifiers=frozenset[MouseModifier](),
    )


def test_a_notch_down_moves_the_view(panel: SettingsController) -> None:
    panel.scroll(1)
    assert panel._offset == 3


def test_a_notch_down_leaves_the_selection_alone(panel: SettingsController) -> None:
    before = panel._selected
    panel.scroll(1)
    assert panel._selected == before


def test_a_detached_view_stops_following_the_cursor(panel: SettingsController) -> None:
    panel.scroll(1)
    assert panel._follow_cursor is False


def test_an_arrow_reattaches_the_view_to_the_cursor(panel: SettingsController) -> None:
    panel.scroll(1)
    panel.handle_key("down")
    assert panel._follow_cursor is True


def test_the_view_never_scrolls_above_the_first_row(panel: SettingsController) -> None:
    panel.scroll(-1)
    panel.scroll(-1)
    assert panel._offset == 0


def test_the_view_never_scrolls_past_the_last_row(panel: SettingsController) -> None:
    for _notch in range(50):
        panel.scroll(1)
    assert panel._offset == panel._scrollable_length() - 1


def test_the_back_row_is_outside_the_scrollable_length(panel: SettingsController) -> None:
    assert panel._scrollable_length() == len(panel._items) - 1


def test_an_open_editor_ignores_the_wheel(panel: SettingsController) -> None:
    panel.handle_key("enter")
    before = panel._offset
    panel.scroll(1)
    assert panel._offset == before


def test_the_control_claims_a_wheel_event() -> None:
    seen: list[int] = []
    control = _WheelControl(seen.append, text=lambda: "", focusable=False, show_cursor=False)
    assert control.mouse_handler(_wheel(MouseEventType.SCROLL_DOWN)) is None
    assert seen == [1]


def test_the_control_reports_the_direction_of_each_notch() -> None:
    seen: list[int] = []
    control = _WheelControl(seen.append, text=lambda: "", focusable=False, show_cursor=False)
    control.mouse_handler(_wheel(MouseEventType.SCROLL_UP))
    control.mouse_handler(_wheel(MouseEventType.SCROLL_DOWN))
    assert seen == [-1, 1]


def test_a_control_without_a_handler_defers_to_the_base_class() -> None:
    control = _WheelControl(None, text=lambda: "", focusable=False, show_cursor=False)
    assert control.mouse_handler(_wheel(MouseEventType.SCROLL_DOWN)) is NotImplemented


def test_other_mouse_events_are_left_to_the_base_class() -> None:
    seen: list[int] = []
    control = _WheelControl(seen.append, text=lambda: "", focusable=False, show_cursor=False)
    control.mouse_handler(_wheel(MouseEventType.MOUSE_MOVE))
    assert seen == []


def test_the_session_wires_the_wheel_into_its_only_control() -> None:
    seen: list[int] = []
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None, None, seen.append)
    control = renderer._application.layout.container.content  # type: ignore[attr-defined]
    control.mouse_handler(_wheel(MouseEventType.SCROLL_DOWN))
    assert seen == [1]
