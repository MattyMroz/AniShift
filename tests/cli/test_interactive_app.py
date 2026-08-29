from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import cast

import pytest

from anishift.application import (
    AppService,
    GroupResult,
    GroupStatus,
    ProducedArtifact,
    RunEvent,
    RunEventSink,
    RunResult,
)
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.home import HomeAction
from anishift.cli.interactive.prompts import HomeGeometry, PromptChoice
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun
from anishift.errors import ExecutionError


class _FakeScreen(AbstractContextManager[None]):
    def __init__(self, prompts: _FakePrompts) -> None:
        self.prompts: _FakePrompts = prompts

    def __enter__(self) -> None:
        self.prompts.screen_entries += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.prompts.screen_exits += 1


class _FakeConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *objects: object, **options: object) -> None:
        del options
        self.lines.append(" ".join(str(value) for value in objects))


class _FakePrompts:
    def __init__(self, actions: Sequence[HomeAction]) -> None:
        self.actions: list[HomeAction] = list(actions)
        self.pauses: list[str] = []
        self.clears: int = 0
        self.screen_entries: int = 0
        self.screen_exits: int = 0
        self.footers: list[tuple[str, str]] = []
        self.cursor_positions: list[tuple[int, int]] = []
        self.resize_callbacks: list[Callable[[], None]] = []

    def screen(self) -> _FakeScreen:
        return _FakeScreen(self)

    def clear_screen(self) -> None:
        self.clears += 1

    def terminal_columns(self) -> int:
        return 80

    def terminal_rows(self) -> int:
        return 24

    def render_footer(self, version: str, directory: str) -> None:
        self.footers.append((version, directory))

    def position_cursor(self, row: int, column: int = 0) -> None:
        self.cursor_positions.append((row, column))

    def watch_resize(self, callback: Callable[[], None]) -> AbstractContextManager[None]:
        self.resize_callbacks.append(callback)
        return nullcontext()

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        del choices, default, footer, geometry
        return self.next_action().value

    def pause(self, message: str) -> None:
        self.pauses.append(message)

    def next_action(self) -> HomeAction:
        return self.actions.pop(0)


class _FakeService:
    def __init__(self, root: Path, preset_id: str = "default") -> None:
        self.workspace_root: Path = root
        self.preset_id: str = preset_id
        self.default_calls: int = 0

    def default_preset_id(self) -> str:
        self.default_calls += 1
        return self.preset_id


class _FakeProgress:
    def __init__(self) -> None:
        self.entered: int = 0
        self.exited: int = 0
        self.events: list[RunEvent] = []
        self.layout: Callable[[], None] | None = None
        self.relayouts: int = 0

    def __enter__(self) -> _FakeProgress:
        self.entered += 1
        if self.layout is not None:
            self.layout()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited += 1

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)

    def relayout(self) -> None:
        self.relayouts += 1
        if self.layout is not None:
            self.layout()


def _prepared() -> PreparedAutoRun:
    value: SimpleNamespace = SimpleNamespace(
        preset_id="default",
        workspace=SimpleNamespace(
            groups=(SimpleNamespace(group_id="group-1", source=SimpleNamespace(stem="Odcinek 01")),)
        ),
        group_ids=("group-1",),
        plan=SimpleNamespace(groups=(SimpleNamespace(group_id="group-1"),), tasks=()),
    )
    return cast("PreparedAutoRun", value)


def _result(status: GroupStatus) -> RunResult:
    products: tuple[ProducedArtifact, ...] = ()
    errors: tuple[str, ...] = ()
    if status is GroupStatus.PARTIAL:
        products = (ProducedArtifact("product-1", Path("episode.pl.srt"), {}),)
        errors = ("Composition failed",)
    return RunResult(
        run_id="run-1",
        groups=(GroupResult(group_id="group-1", status=status, products=products, error_messages=errors),),
    )


def _install_frontend(
    monkeypatch: pytest.MonkeyPatch,
    console: _FakeConsole,
    progress: _FakeProgress | None = None,
) -> None:
    def ask_home(prompts: object, *, version: str) -> HomeAction:
        del version
        adapter: _FakePrompts = cast("_FakePrompts", prompts)
        return adapter.next_action()

    monkeypatch.setattr(interactive_app, "console", console)
    monkeypatch.setattr(interactive_app, "ask_home_action", ask_home)
    if progress is None:
        return

    def progress_factory(
        prepared: object,
        manager: object | None = None,
        layout: Callable[[], None] | None = None,
    ) -> _FakeProgress:
        del prepared
        assert manager is None
        progress.layout = layout
        return progress

    monkeypatch.setattr(interactive_app, "RichRunProgress", progress_factory)


def test_auto_refusal_is_silent_during_preflight_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    _install_frontend(monkeypatch, console)
    monkeypatch.setattr(
        interactive_app,
        "prepare_auto_run",
        lambda service, preset_id: AutoRunRefusal("The workspace holds no source group to run."),
    )

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert service.default_calls == 1
    assert prompts.pauses == ["Naciśnij dowolny klawisz, aby wrócić"]
    assert len(prompts.footers) == 2
    assert any("Workspace nie zawiera" in line for line in console.lines)
    assert all("Skanowanie" not in line and "Przygotowanie" not in line for line in console.lines)


def test_auto_success_keeps_progress_and_footer_until_silent_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path, preset_id="evening")
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()
    received: list[tuple[AppService, PreparedAutoRun, RunEventSink]] = []

    def execute(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
        received.append((service, value, sink))
        prompts.resize_callbacks[-1]()
        return _result(GroupStatus.SUCCEEDED)

    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", execute)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    expected_service: AppService = cast("AppService", service)
    expected_sink: RunEventSink = progress
    assert received == [(expected_service, prepared, expected_sink)]
    assert progress.entered == progress.exited == 1
    assert progress.relayouts == 1
    assert prompts.pauses == [""]
    assert len(prompts.footers) == 3
    assert len(prompts.cursor_positions) == 2
    assert any("ANISHIFT" in line or "█" in line for line in console.lines)


def test_auto_partial_result_does_not_print_products_or_success_screen(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()
    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(
        interactive_app,
        "execute_auto_run",
        lambda service, value, sink: _result(GroupStatus.PARTIAL),
    )

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert prompts.pauses == [""]
    assert all("produkt:" not in line and "Gotowe" not in line for line in console.lines)


def test_expected_execution_error_is_safe_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()

    def fail(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
        del service, value, sink
        raise ExecutionError("The run could not start")

    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", fail)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert progress.exited == 1
    assert any("The run could not start" in line for line in console.lines)
    assert prompts.pauses == ["Naciśnij dowolny klawisz, aby wrócić"]


def test_run_keyboard_interrupt_closes_progress_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()

    def interrupt(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
        del service, value, sink
        raise KeyboardInterrupt

    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", interrupt)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert progress.exited == 1
    assert any("Anulowano" in line for line in console.lines)
    assert len(prompts.pauses) == 1


def test_manual_and_settings_are_temporary_actions_without_backend_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.MANUAL, HomeAction.SETTINGS, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    _install_frontend(monkeypatch, console)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert service.default_calls == 0
    assert len(prompts.pauses) == 2
    assert len(prompts.footers) == 2
    assert any("Tryb ręczny" in line for line in console.lines)
    assert any("Ustawienia" in line for line in console.lines)


def test_interactive_session_uses_one_full_screen_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    service: _FakeService = _FakeService(tmp_path)
    prompts: _FakePrompts = _FakePrompts((HomeAction.EXIT,))
    _install_frontend(monkeypatch, console)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert prompts.screen_entries == 1
    assert prompts.screen_exits == 1
