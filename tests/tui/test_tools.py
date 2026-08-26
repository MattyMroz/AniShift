from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Final, cast, get_args

import pytest
from tui_fakes import OFFLINE_ROOT, inspected_group, inspected_workspace, shell, stub_result

from anishift.application import AppService
from anishift.config import Settings, UserSettings
from anishift.config.model_catalog import CATALOG_FILE_NAME
from anishift.setup.doctor import CheckResult, CheckStatus
from anishift.setup.installer import ResourceOutcome, ResourceResult
from anishift.tui import tools, ui_state, workers
from anishift.tui.app import AniShiftApp
from anishift.tui.commands.registry import CommandRegistry
from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.dialogs.value import ConfirmDialog
from anishift.tui.lifecycle import begin_planning, begin_run
from anishift.tui.messages import DoctorReported, SetupReported
from anishift.tui.screens.tools import TOOLS_ID, ToolsView, tools_body
from anishift.tui.state import FeedbackLevel, RunUiState, SessionState, UiFeedback, UiRoute
from anishift.tui.strings import (
    EXIT_ACTIVE_RUN_QUESTION,
    SETUP_ACTION_TITLE,
    TOOLS_CATALOG_LABEL,
    TOOLS_ENCODING_LABEL,
    TOOLS_ENGINES_LABEL,
    TOOLS_ERRORS_LABEL,
    TOOLS_EVENTS_LABEL,
    TOOLS_FILES_LABEL,
    TOOLS_HELP_ACTIONS_HEADING,
    TOOLS_HELP_COMMANDS_HEADING,
    TOOLS_HELP_KEYS_HEADING,
    TOOLS_INIT_CONNECT_STEP,
    TOOLS_INIT_MODEL_STEP,
    TOOLS_INIT_READY,
    TOOLS_MAIN_MODEL_LABEL,
    TOOLS_PENDING,
    TOOLS_PLATFORM_LABEL,
    TOOLS_PRESET_LABEL,
    TOOLS_PYTHON_LABEL,
    TOOLS_RESULT_LABEL,
    TOOLS_RUN_LABEL,
    TOOLS_RUN_RUNNING,
    TOOLS_SELECTION_LABEL,
    TOOLS_TRANSLATION_LABEL,
    TOOLS_UNKNOWN,
    TOOLS_VERSION_LABEL,
    TOOLS_WORKERS_LABEL,
    TOOLS_WORKSPACE_LABEL,
)

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_CATALOG_SIZE: Final[int] = 14

_PLANTED_VALUE: Final[str] = "tokenvalue0123456789abcdef"

_CANONICAL_ENV_VAR: Final[str] = "ANISHIFT_PALANTIR_TOKEN"

_COMPAT_ENV_VAR: Final[str] = "FOUNDRY_API_TOKEN"

_DEEPL_ENV_VAR: Final[str] = "ANISHIFT_DEEPL_API_KEY"

_DEEPL_KEY: Final[str] = "deeplkeyvalue987654321"

_ENROLLMENT_HOST: Final[str] = "enrollment-host.example.invalid"

_LEAKY_MESSAGE: Final[str] = rf"Cannot read C:\Users\anishift\.env with token={_PLANTED_VALUE}"

_LEAKY_SUGGESTION: Final[str] = rf"Edit /home/anishift/config/settings.json and set api_key={_DEEPL_KEY}"

_STATUS_LABELS: Final[tuple[str, ...]] = (
    TOOLS_WORKSPACE_LABEL,
    TOOLS_SELECTION_LABEL,
    TOOLS_PRESET_LABEL,
    TOOLS_MAIN_MODEL_LABEL,
    TOOLS_TRANSLATION_LABEL,
    TOOLS_ENGINES_LABEL,
    TOOLS_RUN_LABEL,
)

_RUNTIME_LABELS: Final[tuple[str, ...]] = (
    TOOLS_VERSION_LABEL,
    TOOLS_PYTHON_LABEL,
    TOOLS_PLATFORM_LABEL,
    TOOLS_ENCODING_LABEL,
    TOOLS_FILES_LABEL,
    TOOLS_CATALOG_LABEL,
    TOOLS_EVENTS_LABEL,
    TOOLS_WORKERS_LABEL,
    TOOLS_ERRORS_LABEL,
)


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(_COMPAT_ENV_VAR, raising=False)
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: tmp_path / "ui_state.json")
    return tmp_path


def _facts(
    *,
    workspace_read: bool = True,
    token_configured: bool = True,
    primary_alias: str = "main",
    result_counts: tuple[tuple[str, int], ...] = (),
    run_state: RunUiState = RunUiState.IDLE,
) -> tools.SessionFacts:
    return tools.SessionFacts(
        workspace_read=workspace_read,
        group_count=2,
        warning_count=0,
        selected_count=1,
        preset_id="default",
        primary_alias=primary_alias,
        primary_state="Not verified",
        translation_provider="gemini",
        translation_alias="gemini-3.5-flash-lite",
        token_configured=token_configured,
        engines=(("tts", 1, 3), ("translation", 2, 2)),
        run_state=run_state,
        result_counts=result_counts,
    )


def _runtime(*, last_error: str = "None", error_classes: tuple[str, ...] = ()) -> tools.RuntimeFacts:
    return tools.RuntimeFacts(
        version="1.2.3",
        python="3.14.0",
        platform="Windows 11",
        encoding="utf-8",
        files=(".env", "settings.json", "models.json"),
        catalog="2 providers, 5 models, 0 warnings",
        event_count=7,
        draining=False,
        error_classes=error_classes,
        last_error=last_error,
    )


def _check(
    name: str = "binaries",
    status: CheckStatus = CheckStatus.FAIL,
    message: str = "ffmpeg is missing",
    suggestion: str = "",
) -> CheckResult:
    return CheckResult(name=name, status=status, message=message, suggestion=suggestion)


def _labels(report: tools.ToolsReport) -> tuple[str, ...]:
    return tuple(line.label for line in report.lines)


def _values(report: tools.ToolsReport) -> tuple[str, ...]:
    return tuple(line.value for line in report.lines)


def _registry(state: SessionState | None = None) -> CommandRegistry:
    held: SessionState = SessionState() if state is None else state
    return CommandRegistry(lambda: held)


def _spec(name: str, *, slash: str | None = None, enabled: bool = True) -> CommandSpec:
    return CommandSpec(
        name=name,
        title=name.capitalize(),
        description=f"Run {name}",
        category=CommandCategory.DIAGNOSTICS if slash else CommandCategory.ACTION,
        run=lambda: None,
        slash_name=slash,
        enabled=None if enabled else lambda _state: False,
    )


def _configured_service(root: Path, monkeypatch: pytest.MonkeyPatch) -> AppService:
    monkeypatch.setenv(_CANONICAL_ENV_VAR, _PLANTED_VALUE)
    monkeypatch.setenv(_DEEPL_ENV_VAR, _DEEPL_KEY)
    env_file: Path = root / ".env"
    env_file.write_text(
        f"{_CANONICAL_ENV_VAR}={_PLANTED_VALUE}\n{_DEEPL_ENV_VAR}={_DEEPL_KEY}\n",
        encoding="utf-8",
    )
    return AppService(
        workspace_root=root,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(
            palantir_enrollment_base_url=f"https://{_ENROLLMENT_HOST}",
            primary_model_alias="main",
        ),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        preset_saver=lambda file: None,
        settings_saver=lambda draft: None,
        env_file=env_file,
    )


def _secrets() -> tuple[str, ...]:
    return (_PLANTED_VALUE, _DEEPL_KEY, _ENROLLMENT_HOST)


def _view(app: AniShiftApp) -> ToolsView:
    return app.query_one(f"#{TOOLS_ID}", ToolsView)


def _body(app: AniShiftApp) -> str:
    return tools_body(app.tools_report)


def _rendered(app: AniShiftApp) -> str:
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


def test_the_status_report_holds_the_allowlisted_facts_of_the_session() -> None:
    assert _labels(tools.status_report(_facts())) == _STATUS_LABELS


def test_the_status_report_adds_the_result_of_a_run_that_ended() -> None:
    report: tools.ToolsReport = tools.status_report(_facts(result_counts=(("succeeded", 2),)))
    assert _labels(report) == (*_STATUS_LABELS, TOOLS_RESULT_LABEL)
    assert report.lines[-1].value == "2 succeeded"


def test_the_debug_report_extends_the_status_rows_instead_of_repeating_them() -> None:
    facts: tools.SessionFacts = _facts()
    shared: tuple[tools.ReportLine, ...] = tools.status_lines(facts)
    report: tools.ToolsReport = tools.debug_report(facts, _runtime())
    assert report.lines[: len(shared)] == shared
    assert _labels(report)[len(shared) :] == _RUNTIME_LABELS


def test_the_status_and_the_debug_report_share_one_projection_of_the_facts() -> None:
    facts: tools.SessionFacts = _facts()
    assert tools.status_report(facts).lines == tools.debug_report(facts, _runtime()).lines[: len(_STATUS_LABELS)]


def test_the_run_state_is_named_by_a_word_and_never_by_a_colour() -> None:
    report: tools.ToolsReport = tools.status_report(_facts(run_state=RunUiState.RUNNING))
    assert report.lines[-1].value == TOOLS_RUN_RUNNING


def test_the_doctor_report_keeps_the_status_and_the_message_of_every_check() -> None:
    checks: tuple[CheckResult, ...] = (
        _check("python_version", CheckStatus.OK, "Python 3.14.0"),
        _check("uv_installed", CheckStatus.WARN, "uv is old"),
    )
    report: tools.ToolsReport = tools.doctor_report(checks)
    assert _labels(report) == ("python_version", "uv_installed")
    assert "Python 3.14.0" in report.lines[0].value
    assert "uv is old" in report.lines[1].value


def test_the_doctor_report_shows_the_suggestion_of_a_check_that_offers_one() -> None:
    report: tools.ToolsReport = tools.doctor_report((_check(suggestion="Install ffmpeg"),))
    assert len(report.lines) == 2
    assert "Install ffmpeg" in report.lines[1].value


def test_every_diagnostic_status_is_marked_by_a_glyph_and_a_word() -> None:
    assert set(tools.CHECK_MARKS) == {status.value for status in CheckStatus}
    assert CheckStatus.OK.value == tools.OK_CHECK_STATUS
    for status in CheckStatus:
        mark: str = tools.CHECK_MARKS[status.value]
        assert len(mark.split()) == 2


def test_every_installation_outcome_is_marked_and_named() -> None:
    outcomes: tuple[str, ...] = get_args(ResourceOutcome)
    assert set(tools.SETUP_MARKS) == set(outcomes)
    report: tools.ToolsReport = tools.setup_report(
        tuple(ResourceResult(name=outcome, outcome=cast("Any", outcome), detail="done") for outcome in outcomes),
    )
    assert _labels(report) == outcomes
    for outcome, value in zip(outcomes, _values(report), strict=True):
        assert outcome in value


def test_the_init_report_names_only_the_steps_that_are_still_missing() -> None:
    checks: tuple[CheckResult, ...] = (
        _check("python_version", CheckStatus.OK, "Python 3.14.0"),
        _check("binaries", CheckStatus.FAIL, "ffmpeg is missing"),
    )
    report: tools.ToolsReport = tools.init_report(checks, _facts(), _registry())
    assert _labels(report) == ("binaries",)
    assert "Python 3.14.0" not in "".join(_values(report))


def test_the_init_report_asks_for_the_connection_and_the_model_that_are_unset() -> None:
    report: tools.ToolsReport = tools.init_report(
        (),
        _facts(token_configured=False, primary_alias=""),
        _registry(),
    )
    assert _values(report) == (TOOLS_INIT_CONNECT_STEP, TOOLS_INIT_MODEL_STEP)


def test_the_init_report_says_everything_is_ready_when_no_step_is_missing() -> None:
    report: tools.ToolsReport = tools.init_report((_check(status=CheckStatus.OK),), _facts(), _registry())
    assert _values(report) == (TOOLS_INIT_READY,)


def test_the_init_report_offers_the_setup_action_the_registry_holds() -> None:
    registry: CommandRegistry = _registry()
    registry.register((tools.setup_action(lambda: None),))
    report: tools.ToolsReport = tools.init_report((_check(),), _facts(), registry)
    assert any(SETUP_ACTION_TITLE in line.value for line in report.lines)


def test_the_init_report_names_no_setup_action_a_registry_does_not_hold() -> None:
    report: tools.ToolsReport = tools.init_report((_check(),), _facts(), _registry())
    assert not any(SETUP_ACTION_TITLE in line.value for line in report.lines)


def test_the_help_report_lists_every_slash_command_the_registry_holds() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_spec("first", slash="first"), _spec("second", slash="second")))
    report: tools.ToolsReport = tools.help_report(registry)
    assert _labels(report)[:3] == ("", "/first", "/second")
    assert report.lines[0].value == TOOLS_HELP_COMMANDS_HEADING


def test_the_help_report_follows_a_registry_that_changed() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_spec("first", slash="first"),))
    registry.register((_spec("later", slash="later"),), scope="later")
    assert "/later" in _labels(tools.help_report(registry))
    registry.unregister("later")
    assert "/later" not in _labels(tools.help_report(registry))


def test_the_help_report_leaves_out_a_command_the_state_disables() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_spec("first", slash="first"), _spec("locked", slash="locked", enabled=False)))
    assert "/locked" not in _labels(tools.help_report(registry))


def test_the_help_report_groups_the_actions_and_the_keys_apart() -> None:
    registry: CommandRegistry = _registry()
    registry.register((_spec("first", slash="first"), tools.setup_action(lambda: None)))
    values: tuple[str, ...] = _values(tools.help_report(registry))
    assert TOOLS_HELP_ACTIONS_HEADING in values
    assert TOOLS_HELP_KEYS_HEADING in values


def test_no_report_row_carries_an_absolute_path_or_a_secret() -> None:
    report: tools.ToolsReport = tools.doctor_report(
        (_check(message=_LEAKY_MESSAGE, suggestion=_LEAKY_SUGGESTION),),
    )
    body: str = tools.report_body(report)
    assert _PLANTED_VALUE not in body
    assert _DEEPL_KEY not in body
    assert "C:\\Users" not in body
    assert "/home/anishift" not in body
    assert body.count("<path>") == 2
    assert body.count("<redacted>") == 2


def test_the_last_reason_of_the_session_reaches_the_debug_report_redacted() -> None:
    state: SessionState = SessionState(feedback=UiFeedback(level=FeedbackLevel.ERROR, message=_LEAKY_MESSAGE))
    assert _PLANTED_VALUE not in tools.feedback_text(state.feedback)
    assert "C:\\Users" not in tools.feedback_text(state.feedback)


def test_the_configuration_files_are_named_without_their_directories() -> None:
    names: tuple[str, ...] = tools.config_names()
    assert names == (".env", "settings.json", CATALOG_FILE_NAME)
    assert not any(os.sep in name or "/" in name for name in names)


def test_the_console_encoding_comes_from_the_stream_the_frame_is_written_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout", cast("Any", type("Stream", (), {"encoding": "cp1250"})()))
    assert tools.console_encoding() == "cp1250"
    monkeypatch.setattr("sys.stdout", cast("Any", type("Stream", (), {"encoding": None})()))
    assert tools.console_encoding() == TOOLS_UNKNOWN


def test_the_engine_summary_counts_the_ready_engines_of_every_domain() -> None:
    statuses: tuple[Any, ...] = (
        _status("tts", available=True),
        _status("tts", available=False),
        _status("translation", available=True),
    )
    assert tools.engine_counts(statuses) == (("tts", 1, 2), ("translation", 1, 1))


def _status(domain: str, *, available: bool) -> Any:
    return type("Status", (), {"domain": domain, "is_available": available})()


def test_the_result_summary_counts_the_groups_and_names_none_of_them() -> None:
    assert tools.result_counts(None) == ()
    assert tools.result_counts(stub_result()) == (("succeeded", 1),)


def test_the_report_body_keeps_the_title_first_and_pads_every_label() -> None:
    report: tools.ToolsReport = tools.ToolsReport(
        title="Status",
        lines=(
            tools.ReportLine("Run", "Idle"),
            tools.ReportLine("Workspace", "2 groups"),
            tools.ReportLine("", "Bare"),
        ),
    )
    rows: list[str] = tools.report_body(report).splitlines()
    assert rows[0] == "Status"
    assert rows[1] == ""
    assert rows[2].startswith("Run      ")
    assert rows[4] == "Bare"


def test_the_pending_report_names_the_answer_the_session_waits_for() -> None:
    assert tools.pending_report("Doctor") == tools.ToolsReport(
        title="Doctor",
        lines=(tools.ReportLine("", TOOLS_PENDING),),
    )


def test_the_setup_action_is_no_slash_command() -> None:
    spec: CommandSpec = tools.setup_action(lambda: None)
    assert spec.slash_name is None
    assert spec.category is CommandCategory.ACTION
    assert spec.name == tools.SETUP_ACTION_NAME


@pytest.mark.usefixtures("isolated")
def test_the_shell_keeps_the_catalog_of_slash_commands_at_its_fixed_size() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert len(app.commands.slash_names()) == _CATALOG_SIZE
            assert app.commands.command(tools.SETUP_ACTION_NAME) is not None

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_status_command_shows_the_session_facts_on_the_tools_route() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("status")
            await pilot.pause()
            assert app.session_state.route is UiRoute.TOOLS
            assert _view(app).display is True
            assert _labels(_notnone(app.tools_report)) == _STATUS_LABELS

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_status_command_reports_the_workspace_the_session_holds() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.session_state.workspace = inspected_workspace(inspected_group("ep01"))
            app.commands.dispatch("status")
            await pilot.pause()
            assert "1 groups" in _body(app)

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_debug_command_extends_what_the_status_command_shows() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("status")
            await pilot.pause()
            status: tuple[str, ...] = _labels(_notnone(app.tools_report))
            app.commands.dispatch("debug")
            await pilot.pause()
            debug: tuple[str, ...] = _labels(_notnone(app.tools_report))
            assert debug[: len(status)] == status
            assert debug[len(status) :] == _RUNTIME_LABELS

    _run(scenario())


def test_the_planted_secrets_reach_the_facade_the_reports_read(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service: AppService = _configured_service(isolated, monkeypatch)
    assert service.current_settings().palantir_token == _PLANTED_VALUE
    assert service.current_settings().deepl_api_key == _DEEPL_KEY
    assert service.settings_snapshot().palantir_enrollment_base_url.endswith(_ENROLLMENT_HOST)
    assert service.environment_statuses()["palantir_token"] is True


def test_neither_report_of_a_configured_session_leaks_one_secret(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell(_configured_service(isolated, monkeypatch))
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            for command in ("status", "debug"):
                app.commands.dispatch(command)
                await pilot.pause()
                body: str = _body(app)
                frame: str = _rendered(app)
                for secret in _secrets():
                    assert secret not in body
                    assert secret not in frame
                assert str(isolated) not in body
                assert str(OFFLINE_ROOT) not in body

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_help_command_shows_the_commands_of_the_live_registry() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("help")
            await pilot.pause()
            report: tools.ToolsReport = _notnone(app.tools_report)
            slashes: tuple[str, ...] = tuple(label for label in _labels(report) if label.startswith("/"))
            assert sorted(slashes) == sorted(f"/{name}" for name in app.commands.slash_names())
            assert len(slashes) == _CATALOG_SIZE
            assert SETUP_ACTION_TITLE in _labels(report)

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_doctor_command_asks_for_its_diagnostics_off_the_ui_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        asked: list[int] = []
        monkeypatch.setattr(
            workers,
            "run_doctor",
            lambda host, service, *, generation: asked.append(generation),
        )
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("doctor")
            await pilot.pause()
            assert asked == [app.session_state.generation]
            assert _notnone(app.tools_report).lines[0].value == TOOLS_PENDING

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_init_command_asks_for_its_diagnostics_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        called: list[str] = []
        monkeypatch.setattr(workers, "run_doctor", lambda host, service, *, generation: called.append("doctor"))
        monkeypatch.setattr(workers, "run_setup", lambda *args, **kwargs: called.append("setup"))
        monkeypatch.setattr(workers, "execute", lambda *args, **kwargs: called.append("execute"))
        monkeypatch.setattr(workers, "plan_auto", lambda *args, **kwargs: called.append("plan"))
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("init")
            await pilot.pause()
            assert called == ["doctor"]
            assert app.session_state.run_state is RunUiState.IDLE
            assert app.session_state.workspace is None

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_init_command_proposes_the_steps_of_the_answered_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(workers, "run_doctor", lambda host, service, *, generation: None)
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("init")
            await pilot.pause()
            app.post_message(
                DoctorReported(
                    checks=(_check("python_version", CheckStatus.OK, "Python 3.14.0"), _check()),
                    generation=app.session_state.generation,
                ),
            )
            await pilot.pause()
            body: str = _body(app)
            assert "ffmpeg is missing" in body
            assert "Python 3.14.0" not in body

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_doctor_command_shows_every_answered_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(workers, "run_doctor", lambda host, service, *, generation: None)
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("doctor")
            await pilot.pause()
            app.post_message(
                DoctorReported(
                    checks=(_check("python_version", CheckStatus.OK, "Python 3.14.0"), _check(suggestion="Install it")),
                    generation=app.session_state.generation,
                ),
            )
            await pilot.pause()
            body: str = _body(app)
            assert "Python 3.14.0" in body
            assert "ffmpeg is missing" in body
            assert "Install it" in body

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_a_late_diagnostic_answer_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        monkeypatch.setattr(workers, "run_doctor", lambda host, service, *, generation: None)
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("doctor")
            await pilot.pause()
            app.post_message(DoctorReported(checks=(_check(),), generation=app.session_state.generation + 1))
            await pilot.pause()
            assert _notnone(app.tools_report).lines[0].value == TOOLS_PENDING

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_setup_action_installs_nothing_before_the_user_confirms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        started: list[str] = []
        monkeypatch.setattr(workers, "run_setup", lambda *args, **kwargs: started.append("setup"))
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch(tools.SETUP_ACTION_NAME)
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDialog)
            assert started == []
            await pilot.press("escape")
            await pilot.pause()
            assert started == []

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_confirmed_setup_action_reports_every_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        started: list[int] = []
        monkeypatch.setattr(
            workers,
            "run_setup",
            lambda host, service, *, generation, force=False: started.append(generation),
        )
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch(tools.SETUP_ACTION_NAME)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert started == [app.session_state.generation]
            app.post_message(
                SetupReported(
                    resources=(ResourceResult(name="ffmpeg", outcome="installed", detail="ready"),),
                    generation=app.session_state.generation,
                ),
            )
            await pilot.pause()
            assert "ffmpeg" in _body(app)
            assert "installed" in _body(app)

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_exit_command_leaves_at_once_while_no_work_is_in_flight() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("exit")
            await pilot.pause()
        assert app.is_running is False

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_exit_command_asks_before_it_abandons_work_in_flight() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _enter_run(app)
            app.commands.dispatch("exit")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDialog)
            assert app.is_running is True
            assert EXIT_ACTIVE_RUN_QUESTION in _rendered(app)
            await pilot.press("enter")
            await pilot.pause()
        assert app.is_running is False

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_a_refused_exit_confirmation_keeps_the_session_and_its_run() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _enter_run(app)
            app.commands.dispatch("exit")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert app.is_running is True
            assert app.session_state.run_state is RunUiState.RUNNING

    _run(scenario())


@pytest.mark.usefixtures("isolated")
def test_the_exit_command_opens_no_second_dialog_over_the_first() -> None:
    async def scenario() -> None:
        app: AniShiftApp = shell()
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            _enter_run(app)
            app.commands.dispatch("exit")
            await pilot.pause()
            app.commands.dispatch("exit")
            await pilot.pause()
            dialogs: int = sum(isinstance(screen, ConfirmDialog) for screen in app.screen_stack)
            assert dialogs == 1
            assert app.is_running is True

    _run(scenario())


def _enter_run(app: AniShiftApp) -> None:
    assert begin_planning(app.session_state) is not None
    assert begin_run(app.session_state, "run-1") is True


def _notnone(report: tools.ToolsReport | None) -> tools.ToolsReport:
    assert report is not None
    return report
