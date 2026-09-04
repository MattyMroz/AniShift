from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from anishift import __version__
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
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun
from anishift.errors import ExecutionError


class _Renderer:
    def __init__(
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> None:
        self.frame_provider: Callable[[int, int], Text] = frame_provider
        self.key_handler: Callable[[str], None] = key_handler
        self.idle_handler: Callable[[], None] | None = idle_handler
        self.scroll_handler: Callable[[int], None] | None = scroll_handler
        self.native_mascot_size: tuple[int, int] | None = None
        self.script: list[str] = []
        self.runs: int = 0
        self.exits: int = 0
        self.invalidations: int = 0

    def run(self) -> None:
        self.runs += 1
        while self.script and self.exits == 0:
            self.key_handler(self.script.pop(0))

    def invalidate(self) -> None:
        self.invalidations += 1

    def exit(self) -> None:
        self.exits += 1


class _Manual:
    def __init__(
        self,
        service: object,
        workspace: object,
        preset: object,
        invalidate: Callable[[], None],
    ) -> None:
        self.service: object = service
        self.workspace: object = workspace
        self.preset: object = preset
        self.invalidate: Callable[[], None] = invalidate

    def render(self, columns: int, rows: int) -> Text:
        del columns, rows
        return Text("MANUAL LIST")


def _install_renderer(monkeypatch: pytest.MonkeyPatch, script: tuple[str, ...] = ()) -> list[_Renderer]:
    made: list[_Renderer] = []

    def factory(
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> _Renderer:
        renderer: _Renderer = _Renderer(frame_provider, key_handler, idle_handler, scroll_handler)
        renderer.script = list(script)
        made.append(renderer)
        return renderer

    monkeypatch.setattr(interactive_app, "TerminalRenderer", factory)
    return made


def _service(**members: object) -> SimpleNamespace:
    defaults: dict[str, object] = {"discover": lambda: None, "default_preset_id": lambda: "default"}
    defaults.update(members)
    return SimpleNamespace(**defaults)


def _application(
    monkeypatch: pytest.MonkeyPatch,
    service: object,
) -> tuple[interactive_app._InteractiveApplication, _Renderer]:
    made: list[_Renderer] = _install_renderer(monkeypatch)
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        cast("AppService", service)
    )
    return application, made[0]


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


def _accept(prepared: PreparedAutoRun) -> Callable[..., PreparedAutoRun]:
    def prepare(service: AppService, preset_id: str, *, cancel: object = None) -> PreparedAutoRun:
        del service, preset_id, cancel
        return prepared

    return prepare


def _returns(result: RunResult) -> Callable[..., RunResult]:
    def execute(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del service, plan, sink
        return result

    return execute


def _settle(application: interactive_app._InteractiveApplication) -> None:
    worker: threading.Thread | None = application._worker
    if worker is None:
        return
    worker.join(timeout=5)
    assert not worker.is_alive()


def _mode(application: interactive_app._InteractiveApplication) -> interactive_app._ViewMode:
    return application._mode


def _frame(application: interactive_app._InteractiveApplication, columns: int = 120, rows: int = 40) -> str:
    return application._render_frame(columns, rows).plain


def test_the_session_runs_one_full_screen_renderer_and_leaves_from_the_exit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    made: list[_Renderer] = _install_renderer(monkeypatch, ("down", "down", "down", "enter"))

    interactive_app.run_interactive(cast("AppService", _service()))

    assert len(made) == 1
    assert (made[0].runs, made[0].exits) == (1, 1)
    assert made[0].script == []


def test_the_only_renderer_owns_the_alternate_screen_for_the_whole_session() -> None:
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        renderer: TerminalRenderer = TerminalRenderer(lambda _columns, _rows: Text(), lambda _key: None)

    assert renderer._application.full_screen is True
    assert renderer._application.erase_when_done is True


def test_the_auto_row_starts_the_preflight_of_the_default_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    presets: list[str] = []

    def refuse(service: AppService, preset_id: str, *, cancel: object = None) -> AutoRunRefusal:
        del service, cancel
        presets.append(preset_id)
        return AutoRunRefusal("The workspace holds no source group to run.")

    monkeypatch.setattr(interactive_app, "prepare_auto_run", refuse)
    application, _renderer = _application(monkeypatch, _service(default_preset_id=lambda: "evening"))
    application._selected = 0

    application._handle_key("enter")
    _settle(application)

    assert presets == ["evening"]
    assert _mode(application) is interactive_app._ViewMode.MESSAGE


def test_the_manual_row_opens_the_manual_screen_over_the_discovered_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace: SimpleNamespace = SimpleNamespace(groups=(SimpleNamespace(group_id="group-1"),))
    preset: SimpleNamespace = SimpleNamespace(preset_id="default")
    made: list[_Manual] = []
    requested: list[str] = []

    def discover(cancel: object = None) -> SimpleNamespace:
        del cancel
        return workspace

    def get_preset(preset_id: str) -> SimpleNamespace:
        requested.append(preset_id)
        return preset

    def factory(service: object, discovered: object, chosen: object, invalidate: Callable[[], None]) -> _Manual:
        controller: _Manual = _Manual(service, discovered, chosen, invalidate)
        made.append(controller)
        return controller

    monkeypatch.setattr(interactive_app, "ManualController", factory)
    application, _renderer = _application(monkeypatch, _service(discover=discover, get_preset=get_preset))
    application._selected = 1

    application._handle_key("enter")
    _settle(application)

    assert _mode(application) is interactive_app._ViewMode.MANUAL
    assert requested == ["default"]
    assert made[0].workspace is workspace
    assert made[0].preset is preset
    assert "MANUAL LIST" in _frame(application)


def test_the_settings_row_opens_the_panel_inside_the_same_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    application, renderer = _application(monkeypatch, _service())
    application._selected = 2

    application._handle_key("enter")
    panel: str = _frame(application)

    assert _mode(application) is interactive_app._ViewMode.SETTINGS
    assert application._settings is not None
    assert "USTAWIENIA" in panel
    assert panel.rsplit("\n", maxsplit=1)[-1].endswith(f"v{__version__}")
    assert (renderer.runs, renderer.exits) == (0, 0)


def test_the_exit_row_finishes_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    application, renderer = _application(monkeypatch, _service())
    application._selected = 3

    application._handle_key("enter")

    assert renderer.exits == 1
    assert _mode(application) is interactive_app._ViewMode.HOME


def test_an_auto_refusal_stays_a_sentence_with_a_hint_and_returns_home(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(service: AppService, preset_id: str, *, cancel: object = None) -> AutoRunRefusal:
        del service, preset_id, cancel
        return AutoRunRefusal(
            "The workspace holds no source group to run.",
            "Put a video or a subtitle file in the workspace and run the preset again.",
        )

    monkeypatch.setattr(interactive_app, "prepare_auto_run", refuse)
    application, _renderer = _application(monkeypatch, _service())

    application._start_auto()
    _settle(application)
    refused: str = _frame(application)

    assert "Workspace nie zawiera materiału do uruchomienia" in refused
    assert "Umieść plik wideo lub napisów w workspace i spróbuj ponownie" in refused
    assert "dowolny inny klawisz: powrót" in refused
    assert "source group" not in refused
    assert "Traceback" not in refused

    application._handle_key("any")

    assert _mode(application) is interactive_app._ViewMode.HOME
    assert "Auto" in _frame(application)


def test_a_finished_auto_run_keeps_the_queue_and_footer_until_a_key_returns_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept(_prepared()))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.SUCCEEDED)))
    application, _renderer = _application(monkeypatch, _service())

    application._start_auto()
    _settle(application)
    finished: str = _frame(application)

    assert _mode(application) is interactive_app._ViewMode.AUTO_DONE
    assert application._progress is not None
    assert "Odcinek 01" in finished
    assert finished.rsplit("\n", maxsplit=1)[-1].endswith(f"v{__version__}")
    assert "Gotowe" not in finished
    assert "Naciśnij dowolny klawisz" not in finished

    application._handle_key("any")

    assert _mode(application) is interactive_app._ViewMode.HOME
    assert application._progress is None
    assert "Odcinek 01" not in _frame(application)


def test_a_partial_run_shows_its_failure_and_preserved_products(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept(_prepared()))
    monkeypatch.setattr(interactive_app, "execute_plan", _returns(_result(GroupStatus.PARTIAL)))
    application, _renderer = _application(monkeypatch, _service())

    application._start_auto()
    _settle(application)
    finished: str = _frame(application)

    assert _mode(application) is interactive_app._ViewMode.MESSAGE
    assert "Odcinek 01" in finished
    assert "episode.pl.srt" in finished
    assert "Composition failed" in finished
    assert "Gotowe" not in finished


def test_result_scrolling_clamps_edges_and_end_reaches_the_last_line(monkeypatch: pytest.MonkeyPatch) -> None:
    application, _renderer = _application(monkeypatch, _service())
    application._finish_with_message(0, Text("\n".join(f"result-line-{index:03d}" for index in range(100))))
    _frame(application)

    application._handle_key("end")
    assert "result-line-099" in _frame(application)
    for _ in range(100):
        application._handle_key("down")
    at_end: str = _frame(application)
    application._handle_key("up")

    assert _frame(application) != at_end
    assert "result-line-099" not in _frame(application)
    application._handle_key("home")
    assert "result-line-000" in _frame(application)


def test_an_expected_execution_error_is_reported_safely_and_returns_home(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del service, plan, sink
        raise ExecutionError("The run could not start")

    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept(_prepared()))
    monkeypatch.setattr(interactive_app, "execute_plan", fail)
    application, _renderer = _application(monkeypatch, _service())

    application._start_auto()
    _settle(application)
    reported: str = _frame(application)

    assert _mode(application) is interactive_app._ViewMode.MESSAGE
    assert application._progress is None
    assert "Błąd · The run could not start" in reported
    assert "Szczegóły: logs/anishift.log.jsonl" in reported
    assert "Traceback" not in reported

    application._handle_key("any")

    assert _mode(application) is interactive_app._ViewMode.HOME


def test_interrupting_a_running_auto_cancels_it_and_leaves_no_error_on_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    cancelled: list[str] = []

    def execute(service: AppService, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        del service, plan
        sink.emit(RunEvent(run_id="run-1", sequence=1, kind=RunEventKind.RUN_STARTED))
        running.set()
        assert release.wait(timeout=5)
        raise ExecutionError("the run was cancelled")

    monkeypatch.setattr(interactive_app, "prepare_auto_run", _accept(_prepared()))
    monkeypatch.setattr(interactive_app, "execute_plan", execute)
    application, _renderer = _application(monkeypatch, _service(cancel=cancelled.append))

    application._start_auto()
    assert running.wait(timeout=5)
    assert _mode(application) is interactive_app._ViewMode.AUTO

    application._handle_key("interrupt")
    release.set()
    _settle(application)
    home: str = _frame(application)

    assert cancelled == ["run-1"]
    assert _mode(application) is interactive_app._ViewMode.HOME
    assert application._progress is None
    assert "Odcinek 01" not in home
    assert "Błąd" not in home
    assert "Auto" in home
