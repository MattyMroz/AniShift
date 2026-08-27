from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from time import perf_counter
from typing import Any, Final

import pytest
from textual.events import Paste
from textual.widgets import Input
from tui_fakes import PilotTranslation, pilot_service, shell, write_source_group

from anishift.application import RunResult
from anishift.config import presets as presets_module
from anishift.tui import ui_state, workers
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import PALETTE_KEY
from anishift.tui.state import RunUiState, UiRoute
from anishift.tui.widgets.composer import INPUT_ID

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_LARGE_GROUPS: Final[int] = 100

_DENSE_GROUPS: Final[int] = 20

_PROGRESS_PER_TASK: Final[int] = 40

_SMALL_GROUPS: Final[int] = 5

_SCALE_TOLERANCE: Final[float] = 3.0

_SAMPLED_KEYS: Final[int] = 20

_BROWSE_BUDGET_SECONDS: Final[float] = 5.0

_INPUT_BUDGET_SECONDS: Final[float] = 2.0

_PAUSE_LIMIT: Final[int] = 4000

_SETTLE_PAUSES: Final[int] = 20

_TYPED: Final[str] = "/status"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    monkeypatch.setattr(presets_module, "presets_path", lambda: tmp_path / "presets.json")


def test_a_hundred_groups_scroll_and_select_every_row(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, _LARGE_GROUPS)
    app: AniShiftApp = shell(pilot_service(root))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep0000.mkv")
            assert app.session_state.workspace is not None
            assert len(app.session_state.workspace.groups) == _LARGE_GROUPS

            await pilot.press("tab")
            await pilot.pause()
            for _ in range(_LARGE_GROUPS):
                await pilot.press("space")
                await pilot.press("down")
            await pilot.pause()

            assert len(app.session_state.selected_group_ids) == _LARGE_GROUPS
            assert app.session_state.route is UiRoute.WORKSPACE

    _run(scenario())


def test_a_hundred_groups_cost_no_more_per_keystroke_than_a_small_workspace(tmp_path: Path) -> None:
    async def scenario() -> None:
        small: float = await _key_cost(tmp_path / "small", _SMALL_GROUPS)
        large: float = await _key_cost(tmp_path / "large", _LARGE_GROUPS)
        allowed: float = small * _SCALE_TOLERANCE
        assert large < allowed, (
            f"{_LARGE_GROUPS} groups cost {large * 1000:.1f}ms per key against "
            f"{small * 1000:.1f}ms at {_SMALL_GROUPS} groups"
        )

    _run(scenario())


def test_dense_progress_events_keep_the_composer_accepting_a_typed_line(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, _DENSE_GROUPS)
    translation: PilotTranslation = PilotTranslation()
    translation.holds = True
    app: AniShiftApp = shell(
        pilot_service(root, translation=translation, progress_updates=_PROGRESS_PER_TASK),
    )

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep0000.mkv")
            assert app.session_state.workspace is not None
            assert len(app.session_state.workspace.groups) == _DENSE_GROUPS

            await pilot.press("enter")
            await _until(pilot, translation.entered.is_set)
            await _until(pilot, lambda: len(app.session_state.events) > _PROGRESS_PER_TASK)
            assert app.session_state.run_state is RunUiState.RUNNING
            assert app.is_draining is True

            field: Input = _field(app)
            field.focus()
            await pilot.pause()

            started: float = perf_counter()
            for character in _TYPED:
                await pilot.press(character)
            await pilot.press("escape")
            elapsed: float = perf_counter() - started

            assert field.value == _TYPED
            assert elapsed < _INPUT_BUDGET_SECONDS, f"typing under dense progress took {elapsed:.2f}s"
            assert len(app.session_state.events) <= workers.STATE_EVENT_LIMIT

            translation.release.set()
            await _until(pilot, lambda: app.session_state.route is UiRoute.RESULTS)
            result: RunResult | None = app.session_state.result
            assert result is not None
            assert len(result.groups) == _DENSE_GROUPS

    _run(scenario())


def test_a_dense_run_keeps_the_palette_openable_and_closable(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, _DENSE_GROUPS)
    translation: PilotTranslation = PilotTranslation()
    translation.holds = True
    app: AniShiftApp = shell(
        pilot_service(root, translation=translation, progress_updates=_PROGRESS_PER_TASK),
    )

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep0000.mkv")
            await pilot.press("enter")
            await _until(pilot, translation.entered.is_set)
            await _until(pilot, lambda: len(app.session_state.events) > _PROGRESS_PER_TASK)

            started: float = perf_counter()
            await pilot.press(PALETTE_KEY)
            await _until(pilot, lambda: len(app.screen_stack) > 1)
            await pilot.press("escape")
            await _until(pilot, lambda: len(app.screen_stack) == 1)
            elapsed: float = perf_counter() - started

            assert elapsed < _BROWSE_BUDGET_SECONDS, f"palette round trip took {elapsed:.2f}s"
            translation.release.set()
            await _until(pilot, lambda: app.session_state.route is UiRoute.RESULTS)

    _run(scenario())


def test_an_idle_shell_holds_no_drain_timer_before_or_after_a_run(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, 2)
    app: AniShiftApp = shell(pilot_service(root))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.is_draining is False
            await _settle(pilot)
            assert app.is_draining is False

            await _drop(pilot, app, root / "ep0000.mkv")
            await _settle(pilot)
            assert app.is_draining is False

            await pilot.press("enter")
            await _until(pilot, lambda: app.session_state.route is UiRoute.RESULTS)
            assert app.session_state.run_state is RunUiState.TERMINAL
            await _settle(pilot)
            assert app.is_draining is False

    _run(scenario())


async def _key_cost(base: Path, total: int) -> float:
    base.mkdir(parents=True)
    root: Path = _workspace(base, total)
    app: AniShiftApp = shell(pilot_service(root))
    async with app.run_test(size=_FULL_SIZE) as pilot:
        await pilot.pause()
        await _drop(pilot, app, root / "ep0000.mkv")
        assert app.session_state.workspace is not None
        assert len(app.session_state.workspace.groups) == total
        await pilot.press("tab")
        await pilot.pause()
        started: float = perf_counter()
        for _ in range(_SAMPLED_KEYS):
            await pilot.press("down")
            await pilot.press("space")
        return (perf_counter() - started) / (_SAMPLED_KEYS * 2)


def _workspace(tmp_path: Path, total: int) -> Path:
    root: Path = tmp_path / "workspace"
    root.mkdir()
    for index in range(total):
        write_source_group(root, f"ep{index:04d}")
    return root


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
