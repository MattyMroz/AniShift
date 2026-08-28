from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
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


class _FakeStatus(AbstractContextManager[None]):
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


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
        self.statuses: list[str] = []

    def print(self, *objects: object, **options: object) -> None:
        self.lines.append(" ".join(str(value) for value in objects))

    def status(self, message: str, **options: object) -> _FakeStatus:
        self.statuses.append(message)
        return _FakeStatus()


class _FakePrompts:
    def __init__(self, actions: Sequence[HomeAction]) -> None:
        self.actions: list[HomeAction] = list(actions)
        self.pauses: list[str] = []
        self.clears: int = 0
        self.screen_entries: int = 0
        self.screen_exits: int = 0

    def screen(self) -> _FakeScreen:
        return _FakeScreen(self)

    def clear_screen(self) -> None:
        self.clears += 1

    def next_action(self) -> HomeAction:
        return self.actions.pop(0)

    def terminal_columns(self) -> int:
        return 80

    def terminal_rows(self) -> int:
        return 24

    def select(
        self,
        choices: Sequence[PromptChoice],
        *,
        default: str | None,
        footer: str,
        geometry: HomeGeometry,
    ) -> str:
        return self.next_action().value

    def pause(self, message: str) -> None:
        self.pauses.append(message)


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

    def __enter__(self) -> _FakeProgress:
        self.entered += 1
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


def _prepared() -> PreparedAutoRun:
    value: SimpleNamespace = SimpleNamespace(
        preset_id="default",
        workspace=SimpleNamespace(
            groups=(SimpleNamespace(group_id="group-1", source=SimpleNamespace(stem="Odcinek 01")),)
        ),
        group_ids=("group-1",),
        plan=SimpleNamespace(groups=(), tasks=()),
    )
    return cast("PreparedAutoRun", value)


def _install_frontend(
    monkeypatch: pytest.MonkeyPatch,
    console: _FakeConsole,
    progress: _FakeProgress | None = None,
) -> None:
    def ask_home(prompts: object, *, version: str) -> HomeAction:
        adapter: _FakePrompts = cast("_FakePrompts", prompts)
        return adapter.next_action()

    monkeypatch.setattr(interactive_app, "console", console)
    monkeypatch.setattr(interactive_app, "ask_home_action", ask_home)
    if progress is not None:
        monkeypatch.setattr(interactive_app, "RichRunProgress", lambda prepared: progress)


def test_auto_refusal_pauses_and_returns_to_home(
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
    assert len(prompts.pauses) == 1
    assert any("Workspace nie zawiera" in line for line in console.lines)


def test_auto_success_uses_progress_reports_relative_products_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path, preset_id="evening")
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()
    received: list[tuple[AppService, PreparedAutoRun, RunEventSink]] = []
    result: RunResult = RunResult(
        run_id="run-1",
        groups=(
            GroupResult(
                group_id="group-1",
                status=GroupStatus.SUCCEEDED,
                products=(ProducedArtifact("product-1", tmp_path / "season" / "episode.pl.mkv", {}),),
            ),
        ),
    )

    def execute(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
        received.append((service, value, sink))
        return result

    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", execute)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert service.default_calls == 1
    expected_service: AppService = cast("AppService", service)
    expected_sink: RunEventSink = progress
    assert received == [(expected_service, prepared, expected_sink)]
    assert progress.entered == progress.exited == 1
    assert any("✓ Gotowe" in line for line in console.lines)
    assert any("season/episode.pl.mkv" in line for line in console.lines)
    assert all(str(tmp_path) not in line for line in console.lines)
    assert len(prompts.pauses) == 1


def test_auto_partial_result_has_a_distinct_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()
    result: RunResult = RunResult(
        run_id="run-2",
        groups=(
            GroupResult(
                group_id="group-1",
                status=GroupStatus.PARTIAL,
                products=(ProducedArtifact("product-1", tmp_path / "episode.pl.srt", {}),),
                error_messages=("Container composition failed",),
            ),
        ),
    )
    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", lambda service, value, sink: result)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert any("Zakończono częściowo" in line for line in console.lines)
    assert any("Container composition failed" in line for line in console.lines)
    assert any("logs/anishift.log.jsonl" in line for line in console.lines)


def test_expected_execution_error_is_reported_and_returns_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()

    def fail(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
        raise ExecutionError("The run could not start")

    _install_frontend(monkeypatch, console, progress)
    monkeypatch.setattr(interactive_app, "prepare_auto_run", lambda service, preset_id: prepared)
    monkeypatch.setattr(interactive_app, "execute_auto_run", fail)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    assert progress.exited == 1
    assert any("The run could not start" in line for line in console.lines)
    assert len(prompts.pauses) == 1


def test_run_keyboard_interrupt_closes_progress_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    prompts: _FakePrompts = _FakePrompts((HomeAction.AUTO, HomeAction.EXIT))
    service: _FakeService = _FakeService(tmp_path)
    prepared: PreparedAutoRun = _prepared()
    progress: _FakeProgress = _FakeProgress()

    def interrupt(service: AppService, value: PreparedAutoRun, sink: RunEventSink) -> RunResult:
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
    assert any("Tryb ręczny" in line for line in console.lines)
    assert any("Ustawienia" in line for line in console.lines)


def test_exit_and_home_keyboard_interrupt_end_the_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    console: _FakeConsole = _FakeConsole()
    service: _FakeService = _FakeService(tmp_path)
    prompts: _FakePrompts = _FakePrompts((HomeAction.EXIT,))
    _install_frontend(monkeypatch, console)

    interactive_app.run_interactive(cast("AppService", service), prompts)

    def interrupt_home(prompts: object, *, version: str) -> HomeAction:
        raise KeyboardInterrupt

    monkeypatch.setattr(interactive_app, "ask_home_action", interrupt_home)
    interactive_app.run_interactive(cast("AppService", service), _FakePrompts(()))

    assert service.default_calls == 0


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
