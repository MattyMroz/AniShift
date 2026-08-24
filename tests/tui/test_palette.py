from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import replace
from typing import Any, Final

from textual.app import App
from textual.widgets import Static

from anishift.tui.app import AniShiftApp
from anishift.tui.commands.catalog import (
    EXIT_COMMAND_NAME,
    PALETTE_COMMAND_NAME,
    PALETTE_KEY,
    palette_command,
)
from anishift.tui.commands.palette import (
    CommandOption,
    format_keys,
    palette_options,
    slash_options,
)
from anishift.tui.commands.registry import SLASH_SUGGESTION_LIMIT, CommandRegistry
from anishift.tui.commands.spec import CommandCategory, CommandRun, CommandSpec, KeyHint
from anishift.tui.messages import NavigationRequested
from anishift.tui.state import SessionState, UiRoute
from anishift.tui.widgets.footer import footer_text

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_CATALOG_SIZE: Final[int] = 14

_QUIT_KEY: Final[str] = "ctrl+q"

_HELP_QUIT_KEY: Final[str] = "ctrl+c"


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def _spy_dispatch(app: AniShiftApp, calls: list[str]) -> None:
    original: Callable[[str], bool] = app.commands.dispatch

    def dispatch(name: str) -> bool:
        calls.append(name)
        return original(name)

    app.commands.dispatch = dispatch  # type: ignore[method-assign]


def _recorder(calls: list[str], name: str) -> CommandRun:
    def run() -> None:
        calls.append(name)

    return run


def _always(_state: SessionState) -> bool:
    return True


def _slash(
    name: str,
    *,
    description: str = "Opis komendy",
    aliases: tuple[str, ...] = (),
    enabled: bool = True,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        title=name.title(),
        description=description,
        category=CommandCategory.SETTINGS,
        run=lambda: None,
        enabled=lambda _state: enabled,
        slash_name=name,
        slash_aliases=aliases,
    )


def _action(
    name: str,
    *,
    keys: tuple[str, ...] = (),
    run: CommandRun | None = None,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        title=name.title(),
        description=f"Akcja {name}",
        category=CommandCategory.ACTION,
        run=(lambda: None) if run is None else run,
        keys=keys,
    )


def _registry() -> CommandRegistry:
    session: SessionState = SessionState()
    return CommandRegistry(lambda: session)


def test_palette_rows_project_only_the_available_commands() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), _slash("model", enabled=False), _action("refresh")))
    assert [option.name for option in palette_options(registry)] == ["theme", "refresh"]


def test_palette_rows_never_offer_to_open_the_palette() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), palette_command(lambda: None)))
    assert [option.name for option in palette_options(registry)] == ["theme"]
    assert registry.command(PALETTE_COMMAND_NAME) is not None


def test_palette_rows_lift_the_suggested_command() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), replace(_slash("model"), suggested=_always)))
    rows: tuple[CommandOption, ...] = palette_options(registry)
    assert [option.name for option in rows] == ["model", "theme"]
    assert rows[0].suggested is True
    assert rows[1].suggested is False


def test_palette_row_labels_use_the_slash_form_and_the_action_title() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), _action("refresh")))
    rows: tuple[CommandOption, ...] = palette_options(registry)
    assert rows[0] == CommandOption(
        name="theme",
        label="/theme",
        description="Opis komendy",
        keys="",
        suggested=False,
    )
    assert rows[1].label == "Refresh"


def test_a_row_renders_every_key_of_its_command() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_action("refresh", keys=("ctrl+p", "f1")),))
    assert palette_options(registry)[0].keys == "Ctrl+P F1"
    assert format_keys(()) == ""


def test_slash_ranking_prefers_a_prefix_match() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("translation"), _slash("tts")))
    assert [option.label for option in slash_options(registry, "tt")] == ["/tts", "/translation"]


def test_an_alias_matches_without_adding_a_row() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("translation", aliases=("tr", "translate")),))
    assert [option.label for option in slash_options(registry, "tr")] == ["/translation"]


def test_an_alias_reaches_a_command_its_own_name_never_matches() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme", aliases=("wyglad",)),))
    assert [option.label for option in slash_options(registry, "wyglad")] == ["/theme"]


def test_the_ranking_reaches_a_command_through_its_description() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme", description="Wybiera motyw interfejsu"),))
    assert [option.label for option in slash_options(registry, "motyw")] == ["/theme"]


def test_a_query_that_matches_nothing_returns_no_row() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme", description="Wybiera motyw"),))
    assert slash_options(registry, "zzz") == ()


def test_slash_suggestions_stop_at_ten() -> None:
    registry: CommandRegistry = _registry()
    registry.register(tuple(_slash(f"command{index}") for index in range(SLASH_SUGGESTION_LIMIT + 4)))
    assert len(slash_options(registry, "command")) == SLASH_SUGGESTION_LIMIT
    assert len(slash_options(registry, "")) == SLASH_SUGGESTION_LIMIT


def test_an_empty_query_lists_the_slash_catalog_in_registration_order() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), _slash("model"), _action("refresh")))
    assert [option.label for option in slash_options(registry, "")] == ["/theme", "/model"]
    assert [option.label for option in slash_options(registry, "/")] == ["/theme", "/model"]


def test_a_tie_keeps_the_registration_order() -> None:
    first: CommandRegistry = _registry()
    first.register((_slash("alpha"), _slash("alphb")))
    assert [option.label for option in slash_options(first, "al")] == ["/alpha", "/alphb"]
    second: CommandRegistry = _registry()
    second.register((_slash("alphb"), _slash("alpha")))
    assert [option.label for option in slash_options(second, "al")] == ["/alphb", "/alpha"]


def test_the_footer_renders_the_key_hints_the_registry_offers() -> None:
    state: SessionState = SessionState()
    assert footer_text(state) == "workspace: 0 · selected: 0 · preset: default · run: idle"
    assert footer_text(state, (KeyHint(key="f5", label="Odśwież"),)).endswith(" · F5 Odśwież")


def test_the_shell_switches_off_the_built_in_textual_palette() -> None:
    assert App.ENABLE_COMMAND_PALETTE is True
    assert AniShiftApp.ENABLE_COMMAND_PALETTE is False


def test_the_shell_registers_the_frozen_catalog_once() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert len(app.commands.slash_names()) == _CATALOG_SIZE
            assert app.commands.command(PALETTE_COMMAND_NAME) is not None
            assert [option.name for option in palette_options(app.commands)] == list(app.commands.slash_names())

    _run(scenario())


def test_the_reserved_key_runs_the_palette_command_through_the_registry() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.session_state.feedback is None
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            assert app.session_state.feedback is not None

    _run(scenario())


def test_a_screen_scope_key_runs_and_stops_running_with_its_scope() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.register(
                (_action("refresh", keys=("f5",), run=_recorder(calls, "refresh")),),
                scope="workspace",
            )
            await pilot.press("f5")
            await pilot.pause()
            assert calls == ["refresh"]
            app.commands.unregister("workspace")
            await pilot.press("f5")
            await pilot.pause()
            assert calls == ["refresh"]

    _run(scenario())


def test_the_shell_footer_takes_its_labels_from_the_registry() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            footer: Static = app.query_one("#app-footer", Static)
            assert str(footer.content) == footer_text(app.session_state)
            app.commands.register((_action("refresh", keys=("f5",)),), scope="workspace")
            app.post_message(NavigationRequested(UiRoute.AUTO))
            await pilot.pause()
            assert str(footer.content).endswith(" · F5 Refresh")

    _run(scenario())


def test_the_inherited_quit_key_runs_the_exit_command_through_the_registry() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(_QUIT_KEY)
            await pilot.pause()
        assert calls == [EXIT_COMMAND_NAME]

    _run(scenario())


def test_the_inherited_quit_key_still_closes_the_application() -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.is_running is True
            await pilot.press(_QUIT_KEY)
            await pilot.pause()
        assert app.is_running is False

    _run(scenario())


def test_the_help_quit_key_is_no_second_way_out_of_the_application() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _spy_dispatch(app, calls)
            await pilot.press(_HELP_QUIT_KEY)
            await pilot.pause()
            assert calls == []
            assert app.is_running is True
            await pilot.press(PALETTE_KEY)
            await pilot.pause()
            assert calls == [PALETTE_COMMAND_NAME]

    _run(scenario())


def test_a_scope_claims_the_help_quit_key_before_textual_answers_it() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        app: AniShiftApp = AniShiftApp()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.register(
                (_action("close", keys=(_HELP_QUIT_KEY,), run=_recorder(calls, "close")),),
                scope="dialog",
            )
            await pilot.press(_HELP_QUIT_KEY)
            await pilot.pause()
            assert calls == ["close"]
            assert app.is_running is True
            assert len(app._notifications) == 0

    _run(scenario())
