from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.events import Paste
from textual.geometry import Region
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input
from tui_fakes import pilot_service, shell, write_source_group

from anishift.config import presets as presets_module
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import PALETTE_KEY
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.state import UiRoute
from anishift.tui.widgets.composer import INPUT_ID

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_MINIMUM_SIZE: Final[tuple[int, int]] = (80, 24)

_WIDE_SIZE: Final[tuple[int, int]] = (140, 40)

_PAUSE_LIMIT: Final[int] = 400

_SETTLE_PAUSES: Final[int] = 20

_RESIZE_STEPS: Final[tuple[tuple[int, int], ...]] = (
    _MINIMUM_SIZE,
    (92, 26),
    _WIDE_SIZE,
    _FULL_SIZE,
)

_BANDS: Final[tuple[str, ...]] = ("app-content", "app-composer", "app-hints", "app-footer")


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    monkeypatch.setattr(presets_module, "presets_path", lambda: tmp_path / "presets.json")


def test_the_full_layout_keeps_every_visible_pane_inside_the_screen_and_apart(tmp_path: Path) -> None:
    app: AniShiftApp = _app(tmp_path)

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, tmp_path / "workspace" / "ep01.mkv")
            assert app.session_state.route is UiRoute.WORKSPACE

            screen: Region = app.screen.region
            panes: list[tuple[str, Region]] = _panes(app)
            assert [name for name, _ in panes] == list(_BANDS)
            for name, region in panes:
                assert screen.contains_region(region), f"{name} leaves the screen"
            for first, second in _pairs(panes):
                overlap: Region | None = first[1].intersection(second[1])
                assert overlap is None or overlap.area == 0, f"{first[0]} overlaps {second[0]}"

    _run(scenario())


def test_the_smallest_supported_terminal_opens_the_palette_and_leaves_it(tmp_path: Path) -> None:
    app: AniShiftApp = _app(tmp_path)

    async def scenario() -> None:
        async with app.run_test(size=_MINIMUM_SIZE) as pilot:
            await pilot.pause()
            assert app.size.width == _MINIMUM_SIZE[0]
            assert app.size.height == _MINIMUM_SIZE[1]

            await pilot.press(PALETTE_KEY)
            await _settle(pilot)
            assert _top_dialog(app) != ""
            assert app.screen.region.width <= _MINIMUM_SIZE[0]
            assert app.screen.region.height <= _MINIMUM_SIZE[1]

            await pilot.press("escape")
            await _until(pilot, lambda: _top_dialog(app) == "")
            assert app.focused is not None
            assert app.focused.id == INPUT_ID

    _run(scenario())


def test_the_smallest_supported_terminal_types_into_the_composer_and_clears_it(tmp_path: Path) -> None:
    app: AniShiftApp = _app(tmp_path)

    async def scenario() -> None:
        async with app.run_test(size=_MINIMUM_SIZE) as pilot:
            await pilot.pause()
            field: Input = _field(app)
            field.focus()
            await pilot.pause()

            await pilot.press(*"/help")
            await pilot.press("escape")
            await pilot.pause()
            assert field.value == "/help"

            await pilot.press("enter")
            await _settle(pilot)
            assert field.value == ""
            assert app.session_state.route is UiRoute.TOOLS
            assert app.tools_report is not None

    _run(scenario())


def test_a_resize_under_an_open_dialog_keeps_the_dialog_inside_every_size(tmp_path: Path) -> None:
    app: AniShiftApp = _app(tmp_path)

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(PALETTE_KEY)
            await _settle(pilot)
            opened: str = _top_dialog(app)
            assert opened != ""

            for width, height in _RESIZE_STEPS:
                await pilot.resize_terminal(width, height)
                await _settle(pilot)
                assert _top_dialog(app) == opened
                screen: Region = app.screen.region
                assert screen.width == width
                assert screen.height == height
                for name, region in _panes(app):
                    assert screen.contains_region(region), f"{name} leaves the {width}x{height} screen"
                assert _escaping(app) == [], f"dialog leaves the {width}x{height} screen"

            await pilot.press("escape")
            await _until(pilot, lambda: _top_dialog(app) == "")

    _run(scenario())


def test_a_resize_while_the_composer_holds_a_line_keeps_the_line_and_the_focus(tmp_path: Path) -> None:
    app: AniShiftApp = _app(tmp_path)

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            field: Input = _field(app)
            field.focus()
            await pilot.press(*"/sta")
            await _settle(pilot)

            for width, height in _RESIZE_STEPS:
                await pilot.resize_terminal(width, height)
                await _settle(pilot)
                assert _field(app).value == "/sta"
                assert app.focused is not None
                assert app.focused.id == INPUT_ID

    _run(scenario())


def _app(tmp_path: Path) -> AniShiftApp:
    root: Path = tmp_path / "workspace"
    root.mkdir()
    for stem in ("ep01", "ep02"):
        write_source_group(root, stem)
    return shell(pilot_service(root))


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


def _field(app: AniShiftApp) -> Input:
    return app.query_one(f"#{INPUT_ID}", Input)


async def _drop(pilot: Any, app: AniShiftApp, source: Path) -> None:
    _field(app).post_message(Paste(f'"{source}"'))
    await _until(pilot, lambda: app.session_state.workspace is not None)


def _panes(app: AniShiftApp) -> list[tuple[str, Region]]:
    base: Screen[object] = app.screen_stack[0]
    found: list[tuple[str, Region]] = []
    for band in _BANDS:
        widget: Widget = base.query_one(f"#{band}")
        if widget.display and widget.region.area:
            found.append((band, widget.region))
    return found


def _escaping(app: AniShiftApp) -> list[str]:
    screen: Region = app.screen.region
    return [
        widget.id or type(widget).__name__
        for widget in app.screen.walk_children(Widget)
        if widget.display and widget.region.area and not screen.contains_region(widget.region)
    ]


def _pairs(panes: list[tuple[str, Region]]) -> list[tuple[tuple[str, Region], tuple[str, Region]]]:
    return [(panes[i], panes[j]) for i in range(len(panes)) for j in range(i + 1, len(panes))]


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""
