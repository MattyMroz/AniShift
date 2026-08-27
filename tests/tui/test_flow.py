from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from textual.events import Paste
from textual.widgets import Input, OptionList
from tui_fakes import (
    PILOT_CATALOG_ALIAS,
    PilotTranslation,
    pilot_checks,
    pilot_service,
    shell,
    write_source_group,
)

import anishift.tui
from anishift.application import AppService, GroupStatus, ModelAvailability, RunResult
from anishift.application.artifacts import create_group_id
from anishift.application.events import sanitize_event_message
from anishift.config import presets as presets_module
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import EXIT_COMMAND_NAME, global_commands
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.screens.execution import CANCEL_KEY
from anishift.tui.screens.manual import PREVIEW_KEY
from anishift.tui.screens.preview import START_KEY
from anishift.tui.screens.results import MANUAL_KEY
from anishift.tui.state import RunUiState, UiRoute
from anishift.tui.strings import CONNECT_TEST_TITLE
from anishift.tui.tools import ToolsReport, report_body
from anishift.tui.widgets.composer import INPUT_ID
from anishift.tui.widgets.group_table import REFRESH_COMMAND_NAME

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_PAUSE_LIMIT: Final[int] = 600

_SETTLE_PAUSES: Final[int] = 30

_ADDRESS: Final[str] = "https://enrollment.example.com"

_TOKEN: Final[str] = "flow-pilot-token"  # noqa: S105

_SETTINGS_COMMANDS: Final[tuple[str, ...]] = ("tts", "translation", "prompts")

_EXPECTED_COMMANDS: Final[frozenset[str]] = frozenset(
    {
        "auto",
        "connect",
        "debug",
        "doctor",
        "exit",
        "help",
        "init",
        "manual",
        "model",
        "prompts",
        "status",
        "theme",
        "translation",
        "tts",
    }
)

_COMMAND_TOTAL: Final[int] = 14


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    monkeypatch.setattr(presets_module, "presets_path", lambda: tmp_path / "presets.json")


class _Prober:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, config: Any) -> None:
        self.calls.append(str(config.alias))


def test_an_empty_line_walks_the_workspace_through_auto_execution_to_the_results(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01", "ep02")
    translation: PilotTranslation = _holding_translation()
    app: AniShiftApp = shell(pilot_service(root, translation=translation))

    async def scenario() -> None:
        frames: list[str] = []
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert _route(app) is UiRoute.WORKSPACE
            assert app.commands.command(REFRESH_COMMAND_NAME) is None
            frames.append(_frame(app))

            await _drop(pilot, app, root / "ep01.mkv")
            assert app.session_state.workspace is not None
            assert len(app.session_state.workspace.groups) == 2
            frames.append(_frame(app))

            await pilot.press("enter")
            await _until(pilot, translation.entered.is_set)
            await _until(pilot, lambda: app.session_state.active_run_id is not None)
            assert _route(app) is UiRoute.EXECUTION
            assert _run_state(app) is RunUiState.RUNNING
            frames.append(_frame(app))

            translation.release.set()
            await _until(pilot, lambda: _route(app) is UiRoute.RESULTS)
            frames.append(_frame(app))

            result: RunResult | None = app.session_state.result
            assert result is not None
            assert {group.status for group in result.groups} == {GroupStatus.SUCCEEDED}
            assert _run_state(app) is RunUiState.TERMINAL
            assert app.is_draining is False
            assert (root / "ep01.pl.srt").is_file()
            assert (root / "ep02.pl.srt").is_file()
            assert len(frames) == len(set(frames))

    _run(scenario())


def test_the_manual_route_walks_a_preview_and_a_cancelled_start_to_the_results(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01", "ep02", "ep03")
    translation: PilotTranslation = _holding_translation()
    app: AniShiftApp = shell(pilot_service(root, translation=translation))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep01.mkv")
            await _select_every_group(pilot, app)
            assert len(app.session_state.selected_group_ids) == 3

            await _slash(pilot, "manual")
            assert _route(app) is UiRoute.MANUAL
            assert len(app.session_state.manual_drafts) == 3

            await pilot.press(PREVIEW_KEY)
            await _until(pilot, lambda: _route(app) is UiRoute.PREVIEW)
            assert app.session_state.plan is not None

            await pilot.press(START_KEY)
            await _until(pilot, translation.entered.is_set)
            await _until(pilot, lambda: app.session_state.active_run_id is not None)
            assert _route(app) is UiRoute.EXECUTION

            await pilot.press(CANCEL_KEY)
            await _settle(pilot)
            assert _top_dialog(app) == "ConfirmDialog"
            await pilot.press("enter")
            await _until(pilot, lambda: _run_state(app) is RunUiState.CANCELLING)

            translation.release.set()
            await _until(pilot, lambda: _route(app) is UiRoute.RESULTS)
            result: RunResult | None = app.session_state.result
            assert result is not None
            assert result.cancelled
            assert _run_state(app) is RunUiState.TERMINAL
            assert app.is_draining is False

    _run(scenario())


def test_a_failed_group_opens_back_in_the_manual_route_from_the_results(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01", "ep02")
    failed: str = create_group_id(Path(), "ep02")
    app: AniShiftApp = shell(pilot_service(root, failing_stem="ep02"))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep01.mkv")
            await pilot.press("enter")
            await _until(pilot, lambda: _route(app) is UiRoute.RESULTS)
            result: RunResult | None = app.session_state.result
            assert result is not None
            broken: set[str] = {
                group.group_id for group in result.groups if group.status in {GroupStatus.FAILED, GroupStatus.PARTIAL}
            }
            assert broken == {failed}
            assert (root / "ep01.pl.srt").is_file()
            assert (root / "ep02.pl.srt").is_file() is False

            await pilot.press(MANUAL_KEY)
            await _until(pilot, lambda: _route(app) is UiRoute.MANUAL)
            assert app.session_state.selected_group_ids == {failed}
            assert set(app.session_state.manual_drafts) == {failed}

    _run(scenario())


def test_every_route_of_the_shell_is_reachable_in_one_session(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01", "ep02")
    translation: PilotTranslation = _holding_translation()
    app: AniShiftApp = shell(pilot_service(root, translation=translation, checks=pilot_checks()))

    async def scenario() -> None:
        visited: set[UiRoute] = set()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            visited.add(app.session_state.route)
            await _drop(pilot, app, root / "ep01.mkv")
            visited.add(app.session_state.route)

            await _select_every_group(pilot, app)
            assert len(app.session_state.selected_group_ids) == 2

            await _slash(pilot, "auto")
            await _settle(pilot)
            visited.add(app.session_state.route)
            await _close_dialogs(pilot, app)

            await _slash(pilot, "manual")
            visited.add(app.session_state.route)

            await pilot.press(PREVIEW_KEY)
            await _until(pilot, lambda: _route(app) is UiRoute.PREVIEW)
            visited.add(app.session_state.route)

            await pilot.press(START_KEY)
            await _until(pilot, translation.entered.is_set)
            visited.add(app.session_state.route)

            translation.release.set()
            await _until(pilot, lambda: _route(app) is UiRoute.RESULTS)
            visited.add(app.session_state.route)

            await _slash(pilot, "status")
            await _settle(pilot)
            visited.add(app.session_state.route)

            assert visited == set(UiRoute)

    _run(scenario())


def test_the_settings_the_models_and_the_diagnostics_walk_one_session_to_the_exit(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01")
    prober: _Prober = _Prober()
    service: AppService = pilot_service(root, checks=pilot_checks(), prober=prober)
    service.update_setting("palantir_enrollment_base_url", _ADDRESS)
    service.update_secret("palantir_token", _TOKEN)
    app: AniShiftApp = shell(service)

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for command in _SETTINGS_COMMANDS:
                await _slash(pilot, command)
                await _settle(pilot)
                assert _top_dialog(app) != ""
                await _close_dialogs(pilot, app)

            await _slash(pilot, "model")
            await _settle(pilot)
            assert any(PILOT_CATALOG_ALIAS in label for label in _labels(app))
            assert prober.calls == []
            await _close_dialogs(pilot, app)

            await _confirm_one_probe(pilot, app)
            assert prober.calls == [PILOT_CATALOG_ALIAS]
            assert app.model_availability[PILOT_CATALOG_ALIAS].availability is ModelAvailability.VERIFIED
            await _close_dialogs(pilot, app)

            await _slash(pilot, "status")
            await _settle(pilot)
            assert _route(app) is UiRoute.TOOLS
            status_report: str = _tools_text(app)
            assert _TOKEN not in status_report
            assert _ADDRESS not in status_report

            await _slash(pilot, "doctor")
            await _until(pilot, lambda: _tools_text(app) != status_report)
            assert _route(app) is UiRoute.TOOLS
            assert "python_version" in _tools_text(app)

            app.commands.dispatch(EXIT_COMMAND_NAME)
            await _settle(pilot)
            assert app.is_running is False

    _run(scenario())


def test_the_shell_offers_exactly_the_agreed_slash_commands(tmp_path: Path) -> None:
    app: AniShiftApp = shell(pilot_service(_workspace(tmp_path, "ep01")))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            offered: set[str] = {spec.name for spec in global_commands(app)}
            assert len(offered) == _COMMAND_TOTAL
            assert offered == _EXPECTED_COMMANDS
            assert "variant" not in offered

    _run(scenario())


def test_the_shell_sources_carry_no_raw_colour_no_service_import_and_no_leftover_demo() -> None:
    tui: Path = Path(anishift.tui.__file__).parent
    coloured: list[str] = []
    imports: list[str] = []
    demo: list[str] = []
    for path in sorted(tui.rglob("*.py")) + sorted(tui.rglob("*.tcss")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where: str = f"{path.relative_to(tui).as_posix()}:{number}"
            if "theme" not in path.name and re.search(r"#[0-9a-fA-F]{3,8}\b", line):
                coloured.append(where)
            if re.match(r"\s*(from|import)\s+anishift\.services", line):
                imports.append(where)
            if re.search(r"\bDEMO\b|\bDemo\b|\bTODO\b|\bFIXME\b", line):
                demo.append(where)
    assert coloured == []
    assert imports == []
    assert demo == []


def test_a_run_event_message_never_reaches_the_session_unsanitised(tmp_path: Path) -> None:
    root: Path = _workspace(tmp_path, "ep01")
    app: AniShiftApp = shell(pilot_service(root, progress_updates=4))

    async def scenario() -> None:
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _drop(pilot, app, root / "ep01.mkv")
            await pilot.press("enter")
            await _until(pilot, lambda: _route(app) is UiRoute.RESULTS)
            assert len(app.session_state.events) > 0
            for event in app.session_state.events:
                message: str = event.message or ""
                assert message == sanitize_event_message(message)
                assert str(root) not in message
                assert "\n" not in message
                assert "\x1b" not in message

    _run(scenario())


def _workspace(tmp_path: Path, *stems: str) -> Path:
    root: Path = tmp_path / "workspace"
    root.mkdir()
    for stem in stems:
        write_source_group(root, stem)
    return root


def _holding_translation() -> PilotTranslation:
    translation: PilotTranslation = PilotTranslation()
    translation.holds = True
    return translation


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


def _rendered(app: AniShiftApp) -> list[str]:
    return [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]


def _frame(app: AniShiftApp) -> str:
    return "\n".join(_rendered(app))


def _route(app: AniShiftApp) -> UiRoute:
    return app.session_state.route


def _run_state(app: AniShiftApp) -> RunUiState:
    return app.session_state.run_state


def _field(app: AniShiftApp) -> Input:
    return app.query_one(f"#{INPUT_ID}", Input)


async def _drop(pilot: Any, app: AniShiftApp, source: Path) -> None:
    _field(app).post_message(Paste(f'"{source}"'))
    await _until(pilot, lambda: app.session_state.workspace is not None)


async def _slash(pilot: Any, command: str) -> None:
    await pilot.press(*f"/{command}")
    await pilot.press("escape")
    await pilot.press("enter")
    await pilot.pause()


async def _select_every_group(pilot: Any, app: AniShiftApp) -> None:
    total: int = len(app.session_state.workspace.groups) if app.session_state.workspace is not None else 0
    await pilot.press("tab")
    for index in range(total):
        if index:
            await pilot.press("down")
        await pilot.press("space")
    await pilot.press("tab")
    await pilot.pause()


def _labels(app: AniShiftApp) -> list[str]:
    listing: OptionList = app.screen.query_one("#select-list", OptionList)
    return [str(option.prompt) for option in listing.options]


def _filter(app: AniShiftApp, query: str) -> None:
    app.screen.query_one("#select-filter", Input).value = query


async def _confirm_one_probe(pilot: Any, app: AniShiftApp) -> None:
    await _slash(pilot, "connect")
    await _settle(pilot)
    _filter(app, CONNECT_TEST_TITLE)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)
    _filter(app, PILOT_CATALOG_ALIAS)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)
    assert _top_dialog(app) == "ConfirmDialog"
    await pilot.press("enter")
    await _settle(pilot)


def _tools_text(app: AniShiftApp) -> str:
    report: ToolsReport | None = app.tools_report
    return "" if report is None else report_body(report)


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""


async def _close_dialogs(pilot: Any, app: AniShiftApp) -> None:
    while _top_dialog(app) != "":
        await pilot.press("escape")
        await _settle(pilot)
