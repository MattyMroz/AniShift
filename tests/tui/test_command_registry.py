from __future__ import annotations

from typing import Final

import pytest

from anishift.tui.commands.catalog import (
    PALETTE_COMMAND_NAME,
    PALETTE_KEY,
    global_commands,
    palette_command,
)
from anishift.tui.commands.registry import GLOBAL_SCOPE, KEY_HINT_LIMIT, CommandRegistry
from anishift.tui.commands.spec import (
    CommandCategory,
    CommandRun,
    CommandSpec,
    KeyHint,
    key_display,
)
from anishift.tui.state import FeedbackLevel, SessionState, UiFeedback

_SPEC_SLASH_NAMES: Final[tuple[str, ...]] = (
    "init",
    "connect",
    "status",
    "debug",
    "help",
    "exit",
    "auto",
    "manual",
    "model",
    "translation",
    "prompts",
    "tts",
    "theme",
    "doctor",
)

_CATALOG_SIZE: Final[int] = 14


class _Host:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def open_init(self) -> None:
        self.calls.append("init")

    def open_connect(self) -> None:
        self.calls.append("connect")

    def show_status(self) -> None:
        self.calls.append("status")

    def show_debug(self) -> None:
        self.calls.append("debug")

    def show_help(self) -> None:
        self.calls.append("help")

    def exit_app(self) -> None:
        self.calls.append("exit")

    def open_auto(self) -> None:
        self.calls.append("auto")

    def open_manual(self) -> None:
        self.calls.append("manual")

    def open_model(self) -> None:
        self.calls.append("model")

    def open_translation(self) -> None:
        self.calls.append("translation")

    def open_prompts(self) -> None:
        self.calls.append("prompts")

    def open_tts(self) -> None:
        self.calls.append("tts")

    def open_theme(self) -> None:
        self.calls.append("theme")

    def run_doctor(self) -> None:
        self.calls.append("doctor")


def _recorder(calls: list[str], name: str) -> CommandRun:
    def run() -> None:
        calls.append(name)

    return run


def _feedback_run(state: SessionState, message: str) -> CommandRun:
    def run() -> None:
        state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=message)

    return run


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
    hidden: bool = False,
    run: CommandRun | None = None,
) -> CommandSpec:
    return CommandSpec(
        name=name,
        title=name.title(),
        description=f"Akcja {name}",
        category=CommandCategory.ACTION,
        run=(lambda: None) if run is None else run,
        hidden=hidden,
        keys=keys,
    )


def _registry(state: SessionState | None = None) -> CommandRegistry:
    session: SessionState = SessionState() if state is None else state
    return CommandRegistry(lambda: session)


def _catalog() -> tuple[CommandRegistry, _Host]:
    host: _Host = _Host()
    registry: CommandRegistry = _registry()
    registry.register(global_commands(host))
    return registry, host


def test_the_catalog_holds_exactly_the_fourteen_slash_commands_of_the_specification() -> None:
    registry, _ = _catalog()
    assert registry.slash_names() == _SPEC_SLASH_NAMES
    assert len(registry.slash_names()) == _CATALOG_SIZE


def test_the_exact_catalog_guard_reddens_when_a_fifteenth_command_joins() -> None:
    registry, _ = _catalog()
    registry.register((_slash("variant"),), scope="extra")
    assert registry.slash_names() != _SPEC_SLASH_NAMES
    assert "variant" in registry.slash_names()
    assert len(registry.slash_names()) == _CATALOG_SIZE + 1


def test_every_catalog_command_runs_through_its_host() -> None:
    registry, host = _catalog()
    for name in _SPEC_SLASH_NAMES:
        assert registry.dispatch(name) is True
    assert host.calls == list(_SPEC_SLASH_NAMES)


def test_every_catalog_command_stays_visible_and_enabled() -> None:
    registry, _ = _catalog()
    assert registry.available() == registry.commands()


def test_no_catalog_command_owns_a_key_the_footer_would_show() -> None:
    registry, _ = _catalog()
    assert registry.key_hints() == ()


def test_the_palette_action_is_hidden_and_owns_the_reserved_key() -> None:
    spec: CommandSpec = palette_command(lambda: None)
    assert spec.name == PALETTE_COMMAND_NAME
    assert spec.hidden is True
    assert spec.slash_name is None
    assert spec.keys == (PALETTE_KEY,)
    assert spec.category is CommandCategory.ACTION


def test_the_registry_refuses_a_duplicate_command_name() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"),))
    with pytest.raises(ValueError, match="theme"):
        registry.register((_slash("theme"),), scope="screen")


def test_the_registry_refuses_the_same_name_twice_in_one_scope() -> None:
    registry: CommandRegistry = _registry()
    with pytest.raises(ValueError, match="twice"):
        registry.register((_slash("theme"), _slash("theme")))


def test_the_registry_refuses_a_scope_it_already_holds() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"),), scope="screen")
    with pytest.raises(ValueError, match="screen"):
        registry.register((_slash("model"),), scope="screen")


def test_a_refused_registration_leaves_the_registry_untouched() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"),))
    with pytest.raises(ValueError, match="theme"):
        registry.register((_slash("model"), _slash("theme")), scope="screen")
    assert registry.slash_names() == ("theme",)
    assert registry.command("model") is None


def test_a_screen_scope_adds_its_actions_and_drops_them_on_unmount() -> None:
    registry, _ = _catalog()
    registry.register((_action("refresh"), _action("back")), scope="workspace")
    assert [spec.name for spec in registry.available()[-2:]] == ["refresh", "back"]
    registry.unregister("workspace")
    assert registry.command("refresh") is None
    assert registry.slash_names() == _SPEC_SLASH_NAMES


def test_unregistering_an_unknown_scope_changes_nothing() -> None:
    registry, _ = _catalog()
    registry.unregister("nothing")
    assert registry.slash_names() == _SPEC_SLASH_NAMES


def test_the_global_scope_is_the_default_scope() -> None:
    registry, _ = _catalog()
    registry.unregister(GLOBAL_SCOPE)
    assert registry.commands() == ()


def test_dispatch_runs_the_command_exactly_once() -> None:
    calls: list[str] = []
    registry: CommandRegistry = _registry()
    registry.register((_action("refresh", run=_recorder(calls, "refresh")),))
    assert registry.dispatch("refresh") is True
    assert calls == ["refresh"]


def test_dispatch_refuses_an_unknown_command() -> None:
    registry, host = _catalog()
    assert registry.dispatch("variant") is False
    assert host.calls == []


def test_dispatch_refuses_a_disabled_command() -> None:
    calls: list[str] = []
    registry: CommandRegistry = _registry()
    registry.register(
        (
            CommandSpec(
                name="preview",
                title="Preview",
                description="Akcja preview",
                category=CommandCategory.ACTION,
                run=_recorder(calls, "preview"),
                enabled=lambda _state: False,
            ),
        ),
    )
    assert registry.dispatch("preview") is False
    assert calls == []


def test_a_disabled_command_leaves_every_listing() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_slash("theme"), _slash("model", enabled=False)))
    assert [spec.name for spec in registry.available()] == ["theme"]
    assert [spec.name for spec in registry.suggestions("model")] == []
    assert registry.command("model") is not None


def test_a_repair_command_stays_enabled_and_reports_its_missing_state() -> None:
    state: SessionState = SessionState()
    registry: CommandRegistry = _registry(state)
    registry.register(
        (
            CommandSpec(
                name="init",
                title="Inicjalizacja",
                description="Przygotowuje workspace",
                category=CommandCategory.SESSION,
                run=_feedback_run(state, "Brak workspace"),
                slash_name="init",
            ),
        ),
    )
    assert [spec.name for spec in registry.available()] == ["init"]
    assert registry.dispatch("init") is True
    assert state.feedback == UiFeedback(level=FeedbackLevel.WARNING, message="Brak workspace")


def test_a_key_runs_its_command_through_dispatch() -> None:
    calls: list[str] = []
    registry: CommandRegistry = _registry()
    registry.register((_action("refresh", keys=("f5",), run=_recorder(calls, "refresh")),))
    assert registry.dispatch_key("f5") is True
    assert registry.dispatch_key("f6") is False
    assert calls == ["refresh"]


def test_a_key_of_a_disabled_command_runs_nothing() -> None:
    calls: list[str] = []
    registry: CommandRegistry = _registry()
    registry.register(
        (
            CommandSpec(
                name="cancel",
                title="Cancel",
                description="Akcja cancel",
                category=CommandCategory.ACTION,
                run=_recorder(calls, "cancel"),
                enabled=lambda _state: False,
                keys=("f8",),
            ),
        ),
    )
    assert registry.dispatch_key("f8") is False
    assert calls == []


def test_a_hidden_command_keeps_its_key_but_leaves_the_key_hints() -> None:
    calls: list[str] = []
    registry: CommandRegistry = _registry()
    registry.register((_action("palette", keys=("ctrl+p",), hidden=True, run=_recorder(calls, "palette")),))
    assert registry.key_hints() == ()
    assert registry.dispatch_key("ctrl+p") is True
    assert calls == ["palette"]


def test_key_hints_carry_the_titles_the_registry_holds() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_action("refresh", keys=("f5",)), _action("back", keys=("escape",))))
    assert registry.key_hints() == (
        KeyHint(key="f5", label="Refresh"),
        KeyHint(key="escape", label="Back"),
    )


def test_key_hints_stop_at_the_footer_limit() -> None:
    registry: CommandRegistry = _registry()
    registry.register(tuple(_action(f"action{index}", keys=(f"f{index}",)) for index in range(KEY_HINT_LIMIT + 2)))
    assert len(registry.key_hints()) == KEY_HINT_LIMIT


def test_a_contextual_action_cannot_own_a_slash_name() -> None:
    with pytest.raises(ValueError, match="slash name"):
        CommandSpec(
            name="refresh",
            title="Refresh",
            description="Akcja refresh",
            category=CommandCategory.ACTION,
            run=lambda: None,
            slash_name="refresh",
        )


def test_aliases_need_a_slash_name() -> None:
    with pytest.raises(ValueError, match="aliases"):
        CommandSpec(
            name="refresh",
            title="Refresh",
            description="Akcja refresh",
            category=CommandCategory.WORKFLOW,
            run=lambda: None,
            slash_aliases=("r",),
        )


def test_a_command_needs_a_name() -> None:
    with pytest.raises(ValueError, match="needs a name"):
        CommandSpec(
            name="",
            title="Refresh",
            description="Akcja refresh",
            category=CommandCategory.ACTION,
            run=lambda: None,
        )


def test_slash_forms_hold_the_name_and_its_aliases() -> None:
    assert _slash("translation", aliases=("tr",)).slash_forms == ("translation", "tr")
    assert _action("refresh").slash_forms == ()


def test_key_display_renders_the_modifiers_and_the_key() -> None:
    assert key_display("ctrl+p") == "Ctrl+P"
    assert key_display("f5") == "F5"
    assert key_display("escape") == "Escape"
