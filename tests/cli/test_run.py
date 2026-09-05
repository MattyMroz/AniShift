from __future__ import annotations

import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pytest
from typer.testing import CliRunner, Result

from anishift import bootstrap
from anishift.application import (
    AppService,
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    CancellationToken,
    InspectedSourceGroup,
    InspectedWorkspace,
    SourceGroup,
    ready_group_ids,
)
from anishift.application.planning import PlanProblem
from anishift.application.results import GroupResult, GroupStatus, ProducedArtifact, RunResult
from anishift.errors import ConfigError, ErrorCode, ErrorContext, ExecutionError, PlanningError

cli_main = importlib.import_module("anishift.cli.main")

_UI_MODULE_PREFIXES: Final[tuple[str, ...]] = (
    "textual",
    "questionary",
    "prompt_toolkit",
    "anishift.tui",
    "anishift.cli.interactive",
)

_PROBE_TIMEOUT: Final[int] = 300

_PRIVATE_LOCATION: Final[str] = r"C:\Users\someone\anime.mkv"

_RUN_PROBE: Final[str] = """
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

bootstrap = importlib.import_module("anishift.bootstrap")
cli_main = importlib.import_module("anishift.cli.main")
application = importlib.import_module("anishift.application")
results = importlib.import_module("anishift.application.results")

plan = SimpleNamespace(can_execute=True, problems=(), tasks=())
result = results.RunResult(
    run_id="run-probe",
    groups=(results.GroupResult(group_id="anime-01", status=results.GroupStatus.SUCCEEDED),),
)
group = SimpleNamespace(
    group_id="anime-01",
    conflicts=(),
    artifacts=(
        SimpleNamespace(
            kind=application.ArtifactKind.SOURCE_SUBTITLES,
            state=application.ArtifactState.READY,
        ),
    ),
    media_catalogs={},
)
facade = SimpleNamespace(
    workspace_root=Path("workspace"),
    discover=lambda cancel=None: SimpleNamespace(groups=(group,)),
    get_preset=lambda preset_id: preset_id,
    plan_auto=lambda group_ids, preset: plan,
    execute=lambda plan, sink: result,
)
bootstrap.production_service = lambda: facade
code = CliRunner().invoke(cli_main.app, ["run", "--preset", "default"]).exit_code
prefixes = tuple(json.loads(sys.argv[1]))
print(json.dumps({"code": code, "loaded": sorted(n for n in sys.modules if n.startswith(prefixes))}))
"""


def _source_artifact(group_id: str, kind: ArtifactKind, path: Path) -> Artifact:
    return Artifact(
        artifact_id=f"artifact-{group_id}-{kind.value}",
        group_id=group_id,
        kind=kind,
        path=path,
        state=ArtifactState.READY,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
    )


def _inspected_group(group_id: str, *, ready: bool = True) -> InspectedSourceGroup:
    artifacts: list[Artifact] = [_source_artifact(group_id, ArtifactKind.VIDEO_MKV, Path(f"{group_id}.mkv"))]
    if ready:
        artifacts.append(_source_artifact(group_id, ArtifactKind.SOURCE_SUBTITLES, Path(f"{group_id}.ass")))
    return InspectedSourceGroup(
        source=SourceGroup(
            group_id=group_id,
            stem=group_id,
            directory=Path(),
            artifacts=tuple(artifacts),
            conflicts=(),
        ),
        artifacts=tuple(artifacts),
        media_catalogs={},
        conflicts=(),
    )


def _discovery(*group_ids: str, unready: tuple[str, ...] = ()) -> InspectedWorkspace:
    return InspectedWorkspace(
        groups=tuple(_inspected_group(group_id, ready=group_id not in unready) for group_id in group_ids),
        warnings=(),
    )


@dataclass(frozen=True, slots=True)
class _Plan:
    problems: tuple[PlanProblem, ...] = ()
    tasks: tuple[object, ...] = ()

    @property
    def can_execute(self) -> bool:
        return not any(problem.is_blocking for problem in self.problems)


class _Facade:
    def __init__(  # noqa: PLR0913
        self,
        *,
        root: Path,
        group_ids: tuple[str, ...] = ("anime-01",),
        unready: tuple[str, ...] = (),
        preset_ids: tuple[str, ...] = ("default",),
        default_preset: str = "default",
        plan: _Plan | None = None,
        result: RunResult | None = None,
        failure: BaseException | None = None,
    ) -> None:
        self.workspace_root: Path = root
        self.calls: list[str] = []
        self.planned: list[tuple[tuple[str, ...], object]] = []
        self.executed: list[object] = []
        self.workspace: InspectedWorkspace = _discovery(*group_ids, unready=unready)
        self.plan: _Plan = _Plan() if plan is None else plan
        self._preset_ids: tuple[str, ...] = preset_ids
        self._default_preset: str = default_preset
        self._result: RunResult | None = result
        self._failure: BaseException | None = failure

    def discover(self, *, cancel: CancellationToken | None = None) -> InspectedWorkspace:
        del cancel
        self.calls.append("discover")
        return self.workspace

    def default_preset_id(self) -> str:
        self.calls.append("default_preset_id")
        return self._default_preset

    def get_preset(self, preset_id: str) -> str:
        self.calls.append("get_preset")
        if preset_id not in self._preset_ids:
            raise PlanningError(f"Unknown automatic preset: {preset_id}")
        return f"preset:{preset_id}"

    def plan_auto(self, group_ids: tuple[str, ...], preset: object) -> _Plan:
        self.calls.append("plan_auto")
        self.planned.append((tuple(group_ids), preset))
        return self.plan

    def execute(self, plan: _Plan, sink: object) -> RunResult:
        self.calls.append("execute")
        self.executed.append(plan)
        if self._failure is not None:
            raise self._failure
        assert self._result is not None
        return self._result


def test_a_run_where_every_group_succeeds_reports_them_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-1",
            groups=(GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert "group anime-01: succeeded" in result.output
    assert "1 of 1 groups succeeded." in result.output


def test_a_run_with_a_failed_group_reports_the_error_and_exits_with_the_incomplete_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-2",
            groups=(
                GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),
                GroupResult(
                    group_id="anime-02",
                    status=GroupStatus.FAILED,
                    error_messages=("The speech engine refused the request.",),
                ),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_INCOMPLETE
    assert "group anime-02: failed" in result.output
    assert "  error: The speech engine refused the request." in result.output
    assert "1 of 2 groups succeeded." in result.output


def test_a_run_with_a_partial_group_exits_with_the_incomplete_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-3",
            groups=(
                GroupResult(
                    group_id="anime-01",
                    status=GroupStatus.PARTIAL,
                    products=(ProducedArtifact("artifact-1", tmp_path / "anime-01.pl.srt", {}),),
                    error_messages=("The composition step did not finish.",),
                ),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_INCOMPLETE
    assert "group anime-01: partial" in result.output
    assert "  product: anime-01.pl.srt" in result.output


def test_a_cancelled_group_exits_with_the_cancelled_code_even_beside_a_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-4",
            groups=(
                GroupResult(
                    group_id="anime-01",
                    status=GroupStatus.FAILED,
                    error_messages=("The speech engine refused the request.",),
                ),
                GroupResult(group_id="anime-02", status=GroupStatus.CANCELLED),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_CANCELLED
    assert "group anime-02: cancelled" in result.output


def test_an_interrupted_run_states_the_cancellation_and_exits_with_the_cancelled_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path, failure=KeyboardInterrupt())

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_CANCELLED
    assert "The run was cancelled before it finished." in result.output
    assert facade.calls == ["discover", "get_preset", "plan_auto", "execute"]


def test_a_terminal_execution_error_is_stated_and_exits_with_the_incomplete_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path, failure=ExecutionError("Another AniShift workflow is already active"))

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_INCOMPLETE
    assert "Another AniShift workflow is already active" in result.output


def test_an_unknown_preset_is_refused_by_a_sentence_and_never_plans_anything(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path)

    result: Result = _invoke_run(monkeypatch, facade, preset="nope")

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "Unknown automatic preset: nope" in result.output
    assert facade.planned == []
    assert facade.executed == []


def test_a_workspace_without_sources_is_refused_before_planning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path, group_ids=())

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "The workspace holds no source group to run." in result.output
    assert facade.planned == []
    assert facade.executed == []


def test_only_the_groups_the_application_layer_reports_ready_reach_the_planner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        group_ids=("anime-01", "anime-02", "anime-03"),
        unready=("anime-02",),
        result=RunResult(
            run_id="run-8",
            groups=(
                GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),
                GroupResult(group_id="anime-03", status=GroupStatus.SUCCEEDED),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert facade.planned == [(ready_group_ids(facade.workspace.groups), "preset:default")]
    assert "anime-02" not in [group_id for planned, _ in facade.planned for group_id in planned]


def test_a_workspace_whose_every_group_is_unready_is_refused_before_planning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path, group_ids=("anime-01", "anime-02"), unready=("anime-01", "anime-02"))

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "No discovered source group is ready to run." in result.output
    assert "The workspace holds no source group to run." not in result.output
    assert facade.planned == []
    assert facade.executed == []


def test_the_run_takes_its_groups_from_one_discovery_of_the_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        group_ids=("anime-01", "anime-02", "anime-03"),
        unready=("anime-02",),
        result=RunResult(
            run_id="run-9",
            groups=(GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert facade.calls.count("discover") == 1
    assert facade.planned[0][0] == ready_group_ids(facade.workspace.groups)
    assert len(facade.planned[0][0]) < len(facade.workspace.groups)


def test_a_blocked_plan_states_every_blocker_and_is_never_executed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        plan=_Plan(
            problems=(
                PlanProblem(code="NO_SUBTITLE_SOURCE", message="No usable subtitle source.", group_id="anime-01"),
                PlanProblem(code="EMPTY_SELECTION", message="Nothing was selected.", is_blocking=False),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "The plan cannot run because of a blocking problem." in result.output
    assert "  anime-01: No usable subtitle source." in result.output
    assert "Nothing was selected." not in result.output
    assert facade.executed == []


def test_the_run_executes_exactly_the_plan_the_facade_built_from_its_own_preset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan: _Plan = _Plan()
    facade: _Facade = _Facade(
        root=tmp_path,
        group_ids=("anime-01", "anime-02"),
        plan=plan,
        result=RunResult(
            run_id="run-5",
            groups=(
                GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),
                GroupResult(group_id="anime-02", status=GroupStatus.SUCCEEDED),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert facade.calls == ["discover", "get_preset", "plan_auto", "execute"]
    assert facade.planned == [(("anime-01", "anime-02"), "preset:default")]
    assert facade.executed == [plan]


def test_the_report_locates_products_relative_to_the_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-6",
            groups=(
                GroupResult(
                    group_id="anime-01",
                    status=GroupStatus.SUCCEEDED,
                    products=(ProducedArtifact("artifact-1", tmp_path / "season" / "anime-01.pl.mkv", {}),),
                ),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert "  product: season/anime-01.pl.mkv" in result.output
    assert str(tmp_path) not in result.output


def test_a_product_outside_the_workspace_is_named_without_its_location(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside: Path = tmp_path.parent / "elsewhere" / "anime-01.pl.mkv"
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-7",
            groups=(
                GroupResult(
                    group_id="anime-01",
                    status=GroupStatus.PARTIAL,
                    products=(ProducedArtifact("artifact-1", outside, {}),),
                    error_messages=("One product stayed outside the workspace.",),
                ),
            ),
        ),
    )

    result: Result = _invoke_run(monkeypatch, facade)

    assert "  product: anime-01.pl.mkv" in result.output
    assert str(outside.parent) not in result.output


def test_an_unusable_configuration_is_refused_together_with_its_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> AppService:
        raise ConfigError(
            context=ErrorContext(
                code=ErrorCode.WORKSPACE_NOT_RESOLVED,
                message="The workspace root could not be resolved.",
                suggestion="Set ANISHIFT_WORKSPACE_ROOT or run from a repo checkout.",
            ),
        )

    monkeypatch.setattr(bootstrap, "production_service", fail)

    result: Result = CliRunner().invoke(cli_main.app, ["run", "--preset", "default"])

    assert result.exit_code == cli_main.EXIT_REFUSED
    assert "The workspace root could not be resolved." in result.output
    assert "  Set ANISHIFT_WORKSPACE_ROOT or run from a repo checkout." in result.output


def test_a_private_location_in_a_refusal_is_redacted_before_it_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(root=tmp_path, failure=ExecutionError(f"Reading {_PRIVATE_LOCATION} failed"))

    result: Result = _invoke_run(monkeypatch, facade)

    assert result.exit_code == cli_main.EXIT_INCOMPLETE
    assert _PRIVATE_LOCATION not in result.output
    assert "<path>" in result.output


def test_a_missing_preset_option_is_a_usage_error_that_keeps_two_reserved() -> None:
    result: Result = CliRunner().invoke(cli_main.app, ["run"])

    assert result.exit_code == 2
    assert cli_main.EXIT_INCOMPLETE != 2
    assert cli_main.EXIT_CANCELLED != 2


def test_the_bare_invocation_lazily_launches_interactive_with_one_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        preset_ids=("evening",),
        default_preset="evening",
        result=RunResult(
            run_id="run-11",
            groups=(GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),),
        ),
    )

    interactive = importlib.import_module("anishift.cli.interactive")
    launched: list[AppService] = []
    monkeypatch.setattr(bootstrap, "production_service", lambda: cast("AppService", facade))
    monkeypatch.setattr(interactive, "run_interactive", launched.append)
    result: Result = CliRunner().invoke(cli_main.app, [])

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert launched == [cast("AppService", facade)]
    assert facade.calls == []


def test_the_named_run_does_not_launch_the_interactive_frontend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    facade: _Facade = _Facade(
        root=tmp_path,
        result=RunResult(
            run_id="run-12",
            groups=(GroupResult(group_id="anime-01", status=GroupStatus.SUCCEEDED),),
        ),
    )
    interactive = importlib.import_module("anishift.cli.interactive")
    launched: list[AppService] = []
    monkeypatch.setattr(bootstrap, "production_service", lambda: cast("AppService", facade))
    monkeypatch.setattr(interactive, "run_interactive", launched.append)

    result: Result = CliRunner().invoke(cli_main.app, ["run", "--preset", "default"])

    assert result.exit_code == cli_main.EXIT_SUCCESS
    assert launched == []
    assert facade.calls == ["discover", "get_preset", "plan_auto", "execute"]


def test_the_run_command_loads_no_textual_module() -> None:
    probe: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _RUN_PROBE, json.dumps(_UI_MODULE_PREFIXES)],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr
    report: dict[str, Any] = json.loads(probe.stdout)
    assert report["code"] == cli_main.EXIT_SUCCESS
    assert report["loaded"] == []


def _invoke_run(monkeypatch: pytest.MonkeyPatch, facade: _Facade, *, preset: str = "default") -> Result:
    monkeypatch.setattr(bootstrap, "production_service", lambda: cast("AppService", facade))
    return CliRunner().invoke(cli_main.app, ["run", "--preset", preset])
