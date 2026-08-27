from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Final

import pytest
from tui_fakes import (
    RecordingHost,
    StubService,
    shell,
    stub_plan,
    stub_result,
)

from anishift.application import AppService, ExternalAudioRole, InspectedWorkspace, RunEvent, RunEventKind
from anishift.bootstrap import AppContext, create_app_service
from anishift.config import Settings, UserSettings
from anishift.errors import ConfigError, ErrorCode, ErrorContext, PlanningError
from anishift.tui import app as app_module
from anishift.tui import ui_state, workers
from anishift.tui.app import AniShiftApp
from anishift.tui.lifecycle import begin_planning, begin_run
from anishift.tui.messages import (
    DoctorReported,
    GroupRegistered,
    PlanFailed,
    PlanReady,
    RunFailed,
    RunFinished,
    RunProgressed,
    SetupReported,
    WorkspaceFailed,
    WorkspaceLoaded,
)
from anishift.tui.state import RunUiState, UiFeedback
from anishift.tui.strings import MISSING_SURFACE, WORKER_FAILED

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_HELD_STEP: Final[float] = 60.0

_PAUSE_LIMIT: Final[int] = 400

_LEAKY_TEXT: Final[str] = r"C:\Users\anishift\.env token=abcdef0123456789"

_OWN_RUN_ID: Final[str] = "run-own"

_FOREIGN_RUN_ID: Final[str] = "run-foreign"


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    return tmp_path


@pytest.fixture
def stub() -> StubService:
    return StubService()


@pytest.fixture
def host() -> RecordingHost:
    return RecordingHost()


def test_the_composition_root_builds_one_facade_from_one_context(isolated: Path) -> None:
    context: AppContext = AppContext(
        settings=Settings(_env_file=isolated / ".env"),
        user_settings=UserSettings(),
        workspace_root=isolated,
    )
    first: AppService = create_app_service(context)
    second: AppService = create_app_service(context)
    assert first is not second
    assert first.current_settings() is context.settings


def test_the_shell_constructor_requires_a_service() -> None:
    with pytest.raises(TypeError):
        AniShiftApp()  # type: ignore[call-arg]


@pytest.mark.usefixtures("isolated")
def test_every_configured_surface_reaches_the_one_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, object]] = []
    monkeypatch.setattr(
        app_module,
        "open_model_picker",
        lambda app, state, service, availability: seen.append(("model", service)),
    )
    monkeypatch.setattr(
        app_module,
        "open_connect_surface",
        lambda app, state, service, availability: seen.append(("connect", service)),
    )
    monkeypatch.setattr(
        app_module,
        "open_settings_panel",
        lambda app, state, service, domain: seen.append(("settings", service)),
    )

    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for command in ("model", "connect", "tts", "translation", "prompts"):
                app.commands.dispatch(command)
                await pilot.pause()
            assert [name for name, _ in seen] == ["model", "connect", "settings", "settings", "settings"]
            assert {id(service) for _, service in seen} == {id(app.service)}
            assert app.session_state.feedback is None

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_no_surface_of_a_configured_backend_reports_itself_as_missing() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("connect")
            await pilot.pause()
            feedback: UiFeedback | None = app.session_state.feedback
            assert feedback is None or feedback.message != MISSING_SURFACE

    _run(scenario())


def test_every_blocking_operation_runs_in_a_thread_worker(host: RecordingHost, stub: StubService) -> None:
    _launch_every_operation(host, stub)
    assert len(host.launched) == 8
    assert [launch["thread"] for launch in host.launched] == [True] * 8
    assert [launch["exit_on_error"] for launch in host.launched] == [False] * 8
    assert stub.calls == []
    assert host.messages == []


def test_every_launched_worker_carries_the_generation_that_asked_for_it(host: RecordingHost, stub: StubService) -> None:
    _launch_every_operation(host, stub, generation=5)
    assert [workers.worker_generation(str(launch["name"])) for launch in host.launched] == [5] * 8


def test_a_worker_name_without_a_generation_is_answered_with_none() -> None:
    assert workers.worker_generation("") is None
    assert workers.worker_generation("generation=abc") is None
    assert workers.worker_generation("generation=12") == 12


def test_each_operation_delivers_the_message_of_its_own_answer(host: RecordingHost, stub: StubService) -> None:
    _launch_every_operation(host, stub)
    host.run_all()
    assert [type(message).__name__ for message in host.messages] == [
        WorkspaceLoaded.__name__,
        GroupRegistered.__name__,
        GroupRegistered.__name__,
        PlanReady.__name__,
        PlanReady.__name__,
        DoctorReported.__name__,
        SetupReported.__name__,
        RunFinished.__name__,
    ]
    assert stub.calls == [
        "discover",
        "register_external_subtitle",
        "register_external_audio",
        "plan_auto",
        "plan_manual",
        "doctor",
        "setup",
        "execute",
    ]


def test_a_domain_failure_is_delivered_as_a_redacted_reason(host: RecordingHost, stub: StubService) -> None:
    stub.error = ConfigError(
        context=ErrorContext(code=ErrorCode.CONFIG_INVALID, message=f"Cannot read {_LEAKY_TEXT}"),
    )
    workers.discover(host, stub.as_service(), generation=0)
    host.run_all()
    failure: WorkspaceFailed = _only(host.messages, WorkspaceFailed)
    assert "abcdef0123456789" not in failure.reason
    assert "C:\\Users" not in failure.reason
    assert "<path>" in failure.reason


def test_a_failed_plan_is_delivered_as_a_plan_failure(host: RecordingHost, stub: StubService) -> None:
    stub.error = PlanningError("Selected group IDs must be non-empty and unique")
    workers.plan_auto(host, stub.as_service(), generation=3, group_ids=(), preset=_preset())
    host.run_all()
    assert _only(host.messages, PlanFailed).generation == 3


def test_an_execution_refused_before_any_run_is_delivered_as_a_plan_failure(
    host: RecordingHost, stub: StubService
) -> None:
    stub.error = PlanningError("A plan with blocking problems cannot be executed")
    workers.execute(host, stub.as_service(), plan=stub_plan(), pump=workers.RunEventPump(2))
    host.run_all()
    assert _only(host.messages, PlanFailed).generation == 2


def test_an_execution_refused_after_the_run_started_is_delivered_as_a_run_failure(
    host: RecordingHost, stub: StubService
) -> None:
    pump: workers.RunEventPump = workers.RunEventPump(1)
    stub.emit = lambda sink: sink.emit(_event(1, RunEventKind.RUN_STARTED))
    stub.error = PlanningError("Task graph broke")
    workers.execute(host, stub.as_service(), plan=stub_plan(), pump=pump)
    host.run_all()
    failure: RunFailed = _only(host.messages, RunFailed)
    assert failure.run_id == _OWN_RUN_ID
    assert failure.generation == 1


@pytest.mark.usefixtures("isolated")
def test_a_completed_worker_of_an_old_generation_changes_nothing_observable(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            stale: int = app.session_state.generation
            assert begin_planning(app.session_state) is not None
            before: list[str] = _rendered(app)
            app.post_message(WorkspaceLoaded(workspace=_workspace(), generation=stale))
            app.post_message(PlanReady(plan=stub_plan(), generation=stale))
            app.post_message(PlanFailed(reason=_LEAKY_TEXT, generation=stale))
            app.post_message(WorkspaceFailed(reason=_LEAKY_TEXT, generation=stale))
            app.post_message(RunFinished(result=stub_result(), run_id=_OWN_RUN_ID, generation=stale))
            app.post_message(RunFailed(reason=_LEAKY_TEXT, run_id=_OWN_RUN_ID, generation=stale))
            app.post_message(
                RunProgressed(
                    events=(_event(1, RunEventKind.RUN_STARTED),),
                    run_id=_OWN_RUN_ID,
                    generation=stale,
                ),
            )
            await pilot.pause()
            await pilot.pause()
            state = app.session_state
            assert state.workspace is None
            assert state.plan is None
            assert state.result is None
            assert state.feedback is None
            assert state.events == []
            assert state.active_run_id is None
            assert state.run_state is RunUiState.PLANNING
            assert state.generation == stale + 1
            assert _rendered(app) == before
            assert app.is_draining is False

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_a_foreign_run_is_ignored_while_its_generation_still_matches(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            assert begin_run(app.session_state, _OWN_RUN_ID) is True
            before: list[str] = _rendered(app)
            app.post_message(
                RunProgressed(
                    events=(_event(1, RunEventKind.RUN_STARTED, run_id=_FOREIGN_RUN_ID),),
                    run_id=_FOREIGN_RUN_ID,
                    generation=generation,
                ),
            )
            app.post_message(
                RunFinished(
                    result=stub_result(_FOREIGN_RUN_ID),
                    run_id=_FOREIGN_RUN_ID,
                    generation=generation,
                ),
            )
            app.post_message(RunFailed(reason=_LEAKY_TEXT, run_id=_FOREIGN_RUN_ID, generation=generation))
            await pilot.pause()
            await pilot.pause()
            state = app.session_state
            assert state.events == []
            assert state.result is None
            assert state.feedback is None
            assert state.active_run_id == _OWN_RUN_ID
            assert state.run_state is RunUiState.RUNNING
            assert _rendered(app) == before

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_shell_enters_only_the_run_the_batch_announces(stub: StubService) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            generation: int | None = begin_planning(app.session_state)
            assert generation is not None
            app.post_message(
                RunProgressed(
                    events=(_event(4, RunEventKind.TASK_QUEUED),),
                    run_id=_OWN_RUN_ID,
                    generation=generation,
                ),
            )
            await pilot.pause()
            assert app.session_state.active_run_id is None
            assert app.session_state.events == []
            app.post_message(
                RunProgressed(
                    events=(_event(1, RunEventKind.RUN_STARTED),),
                    run_id=_OWN_RUN_ID,
                    generation=generation,
                ),
            )
            await pilot.pause()
            assert app.session_state.active_run_id == _OWN_RUN_ID
            assert [event.sequence for event in app.session_state.events] == [1]

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_an_unexpected_worker_exception_reaches_the_shell_redacted(stub: StubService) -> None:
    stub.error = RuntimeError(_LEAKY_TEXT)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            workers.discover(app, app.service, generation=app.session_state.generation)
            await _until(pilot, lambda: app.session_state.feedback is not None)
            assert app.session_state.feedback == UiFeedback.error(WORKER_FAILED)
            assert app.session_state.workspace is None
            assert "abcdef0123456789" not in "\n".join(_rendered(app))
            assert app.is_draining is False

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_an_unexpected_worker_exception_of_an_old_generation_changes_nothing(stub: StubService) -> None:
    stub.error = RuntimeError(_LEAKY_TEXT)

    async def scenario() -> None:
        app: AniShiftApp = shell(stub.as_service())
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            workers.discover(app, app.service, generation=app.session_state.generation)
            assert begin_planning(app.session_state) is not None
            for _ in range(_PAUSE_LIMIT // 8):
                await pilot.pause()
            assert app.session_state.feedback is None
            assert app.session_state.run_state is RunUiState.PLANNING

    _run(scenario())


def _launch_every_operation(host: RecordingHost, stub: StubService, generation: int = 0) -> None:
    service: AppService = stub.as_service()
    workers.discover(host, service, generation=generation)
    workers.register_external_subtitle(
        host,
        service,
        generation=generation,
        group_id="group-1",
        path=Path("ep01.srt"),
        declared_language="pl",
    )
    workers.register_external_audio(
        host,
        service,
        generation=generation,
        group_id="group-1",
        path=Path("ep01.mka"),
        role=ExternalAudioRole.NARRATION_MIX,
    )
    workers.plan_auto(host, service, generation=generation, group_ids=("group-1",), preset=_preset())
    workers.plan_manual(host, service, generation=generation, intents=())
    workers.run_doctor(host, service, generation=generation)
    workers.run_setup(host, service, generation=generation)
    workers.execute(host, service, plan=stub_plan(), pump=workers.RunEventPump(generation))


def _preset() -> Any:
    return None


def _workspace() -> InspectedWorkspace:
    return InspectedWorkspace(groups=(), warnings=())


def _event(sequence: int, kind: RunEventKind, run_id: str = _OWN_RUN_ID) -> RunEvent:
    return RunEvent(run_id=run_id, sequence=sequence, kind=kind)


def _only[T](messages: list[Any], kind: type[T]) -> T:
    matches: list[T] = [message for message in messages if isinstance(message, kind)]
    assert len(matches) == 1
    return matches[0]


def _rendered(app: AniShiftApp) -> list[str]:
    return [strip.text.rstrip() for strip in app.screen._compositor.render_strips()]


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _until(pilot: Any, ready: Callable[[], bool]) -> None:
    for _ in range(_PAUSE_LIMIT):
        if ready():
            return
        await pilot.pause()
