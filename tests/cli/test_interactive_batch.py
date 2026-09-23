from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from rich.text import Text

from anishift.application import (
    AppService,
    ExecutionPlan,
    GroupResult,
    GroupStatus,
    ProducedArtifact,
    RunEvent,
    RunEventKind,
    RunEventSink,
    RunResult,
)
from anishift.cli.exit_codes import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.interactive import app as interactive_app
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun


class _Clock:
    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now


class _Renderer:
    def __init__(
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> None:
        del scroll_handler
        self.frame_provider: Callable[[int, int], Text] = frame_provider
        self.key_handler: Callable[[str], None] = key_handler
        self.idle_handler: Callable[[], None] | None = idle_handler
        self.native_mascot_size: tuple[int, int] | None = None
        self.exits: int = 0
        self.finished: threading.Event = threading.Event()
        self.on_idle: Callable[[], None] = lambda: None

    def run(self) -> None:
        while not self.finished.is_set():
            if self.idle_handler is not None:
                self.idle_handler()
            self.on_idle()
            self.finished.wait(timeout=0.01)

    def invalidate(self) -> None:
        return None

    def exit(self) -> None:
        self.exits += 1
        self.finished.set()


def _install(monkeypatch: pytest.MonkeyPatch) -> tuple[list[_Renderer], _Clock]:
    made: list[_Renderer] = []
    clock: _Clock = _Clock()

    def factory(
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> _Renderer:
        renderer: _Renderer = _Renderer(frame_provider, key_handler, idle_handler, scroll_handler)
        made.append(renderer)
        return renderer

    monkeypatch.setattr(interactive_app, "TerminalRenderer", factory)
    monkeypatch.setattr(interactive_app, "monotonic", clock)
    return made, clock


def _service() -> AppService:
    value: SimpleNamespace = SimpleNamespace(
        discover=lambda: None,
        default_preset_id=lambda: "default",
        cancel=lambda run_id: None,
    )
    return cast("AppService", value)


def _prepared() -> PreparedAutoRun:
    group: SimpleNamespace = SimpleNamespace(
        group_id="group-1",
        source=SimpleNamespace(stem="Odcinek 01"),
        artifacts=(),
    )
    value: SimpleNamespace = SimpleNamespace(
        preset_id="default",
        workspace=SimpleNamespace(groups=(group,)),
        group_ids=("group-1",),
        plan=SimpleNamespace(groups=(group,), tasks=()),
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


def _accept(requested: list[Sequence[str] | None]) -> Callable[..., PreparedAutoRun]:
    def prepare(
        service: AppService,
        preset_id: str,
        *,
        cancel: object = None,
        group_ids: Sequence[str] | None = None,
    ) -> PreparedAutoRun:
        del service, preset_id, cancel
        requested.append(group_ids)
        return _prepared()

    return prepare


def _returns(result: RunResult) -> Callable[..., RunResult]:
    def execute(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del service, plan, sink
        return result

    return execute


def _application(
    monkeypatch: pytest.MonkeyPatch, batch: tuple[str, ...]
) -> tuple[interactive_app._InteractiveApplication, _Renderer, _Clock]:
    made, clock = _install(monkeypatch)
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        _service(), batch=batch
    )
    return application, made[0], clock


def _settle(application: interactive_app._InteractiveApplication) -> None:
    worker: threading.Thread | None = application._worker
    if worker is None:
        return
    worker.join(timeout=5)
    assert not worker.is_alive()


def _frame(application: interactive_app._InteractiveApplication) -> str:
    return application._render_frame(120, 40).plain


def test_a_batch_window_plans_only_its_groups_and_closes_itself_with_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[Sequence[str] | None] = []
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept(requested))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.SUCCEEDED)))
    application, renderer, clock = _application(monkeypatch, ("group-1",))
    renderer.on_idle = lambda: setattr(clock, "now", clock.now + 1.0)

    code: int = application.run()

    assert requested == [("group-1",)]
    assert code == EXIT_SUCCESS
    assert renderer.exits == 1
    assert application._mode is interactive_app._ViewMode.AUTO_DONE


def test_a_finished_batch_shows_the_countdown_in_the_footer_until_a_key_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept([]))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.SUCCEEDED)))
    application, renderer, clock = _application(monkeypatch, ("group-1",))

    application._start_auto()
    _settle(application)
    finished: str = _frame(application)
    application._handle_idle()

    assert "Odcinek 01" in finished
    assert "Okno zamknie się za 10 s" in finished
    assert renderer.exits == 0

    clock.now += 4.0
    assert "Okno zamknie się za 6 s" in _frame(application)

    application._handle_key("any")

    assert renderer.exits == 1
    assert application._exit_code == EXIT_SUCCESS


def test_a_batch_closes_on_its_own_when_the_countdown_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept([]))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.SUCCEEDED)))
    application, renderer, clock = _application(monkeypatch, ("group-1",))

    application._start_auto()
    _settle(application)
    clock.now += 9.5
    application._handle_idle()
    assert renderer.exits == 0

    clock.now += 0.5
    application._handle_idle()

    assert renderer.exits == 1


def test_a_partial_batch_reports_its_failure_and_exits_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept([]))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.PARTIAL)))
    application, renderer, clock = _application(monkeypatch, ("group-1",))
    renderer.on_idle = lambda: setattr(clock, "now", clock.now + 1.0)

    code: int = application.run()

    assert code == EXIT_INCOMPLETE
    assert application._mode is interactive_app._ViewMode.MESSAGE
    assert "Composition failed" in _frame(application)


def test_a_refused_batch_exits_refused_after_showing_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(
        service: AppService,
        preset_id: str,
        *,
        cancel: object = None,
        group_ids: Sequence[str] | None = None,
    ) -> AutoRunRefusal:
        del service, preset_id, cancel, group_ids
        return AutoRunRefusal("No discovered source group is ready to run.")

    monkeypatch.setattr(interactive_app, "prepare_auto_run", refuse)
    application, renderer, clock = _application(monkeypatch, ("group-1",))
    renderer.on_idle = lambda: setattr(clock, "now", clock.now + 1.0)

    code: int = application.run()

    assert code == EXIT_REFUSED
    assert "Żadna wykryta grupa nie jest gotowa" in _frame(application)


def test_interrupting_a_batch_cancels_its_run_and_exits_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    running: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    cancelled: list[str] = []

    def execute(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del service, plan
        sink.emit(RunEvent(run_id="run-1", sequence=1, kind=RunEventKind.RUN_STARTED))
        running.set()
        assert release.wait(timeout=5)
        return _result(GroupStatus.CANCELLED)

    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept([]))
    monkeypatch.setattr(interactive_app, "execute_plan", execute)
    made, _clock = _install(monkeypatch)
    service: SimpleNamespace = SimpleNamespace(
        discover=lambda: None,
        default_preset_id=lambda: "default",
        cancel=cancelled.append,
    )
    application = interactive_app._InteractiveApplication(cast("AppService", service), batch=("group-1",))
    renderer: _Renderer = made[0]

    application._start_auto()
    assert running.wait(timeout=5)
    application._handle_key("interrupt")
    release.set()
    _settle(application)

    assert cancelled == ["run-1"]
    assert renderer.exits == 1
    assert application._exit_code == EXIT_CANCELLED


def test_a_session_without_a_batch_keeps_home_and_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    made, _clock = _install(monkeypatch)
    application = interactive_app._InteractiveApplication(_service())
    renderer: _Renderer = made[0]
    renderer.on_idle = renderer.exit

    code: int = application.run()

    assert code == EXIT_SUCCESS
    assert application._mode is interactive_app._ViewMode.HOME
    assert "Okno zamknie się" not in _frame(application)
