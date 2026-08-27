"""CLI entry point — Typer app registered as the ``anishift`` script."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, NoReturn

import typer

from anishift.errors import AniShiftError
from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor
from anishift.setup.installer import run_setup
from anishift.utils.logger import get_logger
from anishift.utils.rich_console import StatusType, console, get_status_icon

if TYPE_CHECKING:
    from anishift.application import AppService, AutoPreset, ExecutionPlan, InspectedWorkspace, RunResult
    from anishift.application.events import RunEvent
    from anishift.application.planning import PlanProblem
    from anishift.setup.installer import ResourceResult

app = typer.Typer(
    name="anishift",
    help="AniShift — terminal-based anime lector for Polish.",
    no_args_is_help=False,
    add_completion=False,
)

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

EXIT_SUCCESS: Final[int] = 0
"""Every group of a non-interactive run reached a successful terminal state."""

EXIT_REFUSED: Final[int] = 1
"""The run never started: unusable configuration, unknown preset, no sources or a blocked plan."""

EXIT_INCOMPLETE: Final[int] = 3
"""The run finished with a failed or partial group; 2 stays reserved for command-line usage errors."""

EXIT_CANCELLED: Final[int] = 4
"""Cancellation reached the run before every group succeeded."""

_NO_SOURCES: Final[str] = "The workspace holds no source group to run."
"""Refusal stated when discovery finds nothing the preset could be applied to."""

_NO_SOURCES_HINT: Final[str] = "Put a video or a subtitle file in the workspace and run the preset again."
"""Suggestion offered beside an empty workspace."""

_NO_READY_SOURCES: Final[str] = "No discovered source group is ready to run."
"""Refusal stated when discovery finds only groups the automatic route would skip."""

_NO_READY_SOURCES_HINT: Final[str] = "Give every group usable text, resolve its conflict, then run the preset again."
"""Suggestion offered when every discovered group is unready."""

_PLAN_BLOCKED: Final[str] = "The plan cannot run because of a blocking problem."
"""Refusal stated when the planner reports a problem that forbids execution."""

_PLAN_SCOPE: Final[str] = "plan"
"""Name a blocking problem is attributed to while it belongs to no single group."""

_RUN_CANCELLED: Final[str] = "The run was cancelled before it finished."
"""Sentence stated when the process is interrupted while the run is executing."""

_RUN_SUMMARY: Final[str] = "{succeeded} of {total} groups succeeded."
"""Closing line of every completed non-interactive report."""

_STATUS_ICON: dict[CheckStatus, StatusType] = {
    CheckStatus.OK: "success",
    CheckStatus.WARN: "warning",
    CheckStatus.FAIL: "error",
    CheckStatus.SKIP: "stopped",
}
"""Maps a check outcome to a ``rich_console`` status-icon name."""

_OUTCOME_ICON: dict[str, StatusType] = {
    "installed": "success",
    "skipped": "info",
    "unavailable": "warning",
    "cancelled": "warning",
    "failed": "error",
}
"""Maps a setup outcome to a ``rich_console`` status-icon name."""


def _print_doctor_report(results: list[CheckResult]) -> None:
    """Render doctor results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
        if result.suggestion and result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            console.print(f"   [gray]-> {result.suggestion}[/gray]")


def _print_setup_report(results: list[ResourceResult]) -> None:
    """Render setup results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_OUTCOME_ICON.get(result.outcome, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.detail}")


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Run the preset stored as the default when invoked without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    service: AppService = _composed_service()
    _run_preset(service, service.default_preset_id())


@app.command()
def doctor() -> None:
    """Run diagnostics and report the state of binaries, keys and workspace."""
    results = run_doctor()
    _print_doctor_report(results)
    if any(r.status is CheckStatus.FAIL for r in results):
        raise typer.Exit(code=1)


@app.command()
def setup(
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-download everything, even resources already present."),
    ] = False,
) -> None:
    """Download and verify missing external tools into external/bin/."""
    try:
        results = run_setup(force=force)
    except AniShiftError as exc:
        console.print(f"[error]{exc}[/error]")
        raise typer.Exit(code=1) from exc
    _print_setup_report(results)
    if any(result.outcome == "failed" for result in results):
        raise typer.Exit(code=1)


@app.command()
def run(
    preset: Annotated[
        str,
        typer.Option("--preset", help="ID of the stored automatic preset the run applies."),
    ],
) -> None:
    """Run one stored automatic preset over the workspace and report the outcome as text."""
    _run_preset(_composed_service(), preset)


def _run_preset(service: AppService, preset: str) -> NoReturn:
    """Plan and execute one named preset, then leave with the code of its outcome."""
    plan: ExecutionPlan = _preset_plan(service, preset)
    result: RunResult = _executed_run(service, plan)
    _print_run_report(result, service.workspace_root)
    code: int = _run_exit_code(result)
    logger.info("Non-interactive run finished", groups=len(result.groups), exit_code=code)
    raise typer.Exit(code=code)


class _QuietRunEvents:
    """Run-event observer of the non-interactive mode, which reports the outcome alone."""

    def emit(self, event: RunEvent) -> None:
        """Drop one progress event, keeping the consumable report free of interleaving."""


def _composed_service() -> AppService:
    """Compose the one production facade every entry point runs on."""
    from anishift.bootstrap import production_service  # noqa: PLC0415 - keep the backend off the Typer import path

    try:
        service: AppService = production_service()
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)
    return service


def _preset_plan(service: AppService, preset_id: str) -> ExecutionPlan:
    """Plan the groups the application layer reports ready, from the stored preset through the shared facade."""
    from anishift.application import ready_group_ids  # noqa: PLC0415 - keep the backend off the Typer import path

    try:
        workspace: InspectedWorkspace = service.discover()
        preset: AutoPreset = service.get_preset(preset_id)
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)
    if not workspace.groups:
        _refuse_sentence(_NO_SOURCES, _NO_SOURCES_HINT)
    group_ids: tuple[str, ...] = ready_group_ids(workspace.groups)
    if not group_ids:
        _refuse_sentence(_NO_READY_SOURCES, _NO_READY_SOURCES_HINT)
    try:
        plan: ExecutionPlan = service.plan_auto(group_ids, preset)
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)
    if not plan.can_execute:
        _refuse_blocked(plan)
    logger.info("Non-interactive run planned", preset_id=preset_id, groups=len(group_ids), tasks=len(plan.tasks))
    return plan


def _executed_run(service: AppService, plan: ExecutionPlan) -> RunResult:
    """Execute the accepted plan through the one facade call every frontend uses."""
    try:
        result: RunResult = service.execute(plan, _QuietRunEvents())
    except KeyboardInterrupt:
        logger.info("Non-interactive run interrupted")
        typer.echo(_RUN_CANCELLED)
        raise typer.Exit(code=EXIT_CANCELLED) from None
    except (AniShiftError, OSError) as problem:
        logger.warning("Non-interactive run ended in a terminal error", error_class=type(problem).__name__)
        _echo_problem(problem)
        raise typer.Exit(code=EXIT_INCOMPLETE) from problem
    return result


def _print_run_report(result: RunResult, root: Path) -> None:
    """Print one stable line per group with its products and its redacted errors."""
    from anishift.application import GroupStatus  # noqa: PLC0415 - keep the backend off the Typer import path

    for group in result.groups:
        typer.echo(f"group {group.group_id}: {group.status.value}")
        for product in group.products:
            typer.echo(f"  product: {_located(product.path, root)}")
        for product in group.preserved_products:
            typer.echo(f"  preserved: {_located(product.path, root)}")
        for message in group.error_messages:
            typer.echo(f"  error: {message}")
    for warning in result.warnings:
        typer.echo(f"warning: {warning}")
    succeeded: int = sum(1 for group in result.groups if group.status is GroupStatus.SUCCEEDED)
    typer.echo(_RUN_SUMMARY.format(succeeded=succeeded, total=len(result.groups)))


def _run_exit_code(result: RunResult) -> int:
    """Map one terminal run result to the exit code a calling script reads."""
    if result.succeeded:
        return EXIT_SUCCESS
    if result.cancelled:
        return EXIT_CANCELLED
    return EXIT_INCOMPLETE


def _refuse_problem(problem: AniShiftError | OSError) -> NoReturn:
    """State why the run cannot start and leave with the refusal code."""
    logger.warning("Non-interactive run refused", error_class=type(problem).__name__)
    _echo_problem(problem)
    raise typer.Exit(code=EXIT_REFUSED)


def _refuse_sentence(sentence: str, hint: str) -> NoReturn:
    """State one known refusal and its suggestion, then leave with the refusal code."""
    logger.warning("Non-interactive run refused", reason=sentence)
    typer.echo(sentence)
    typer.echo(f"  {hint}")
    raise typer.Exit(code=EXIT_REFUSED)


def _refuse_blocked(plan: ExecutionPlan) -> NoReturn:
    """State every blocking problem of the plan and never execute it."""
    blockers: tuple[PlanProblem, ...] = tuple(problem for problem in plan.problems if problem.is_blocking)
    logger.warning("Non-interactive run refused, the plan is blocked", blockers=len(blockers))
    typer.echo(_PLAN_BLOCKED)
    for problem in blockers:
        typer.echo(f"  {problem.group_id or _PLAN_SCOPE}: {_safe(problem.message)}")
    raise typer.Exit(code=EXIT_REFUSED)


def _echo_problem(problem: AniShiftError | OSError) -> None:
    """State one redacted sentence about *problem*, plus its suggestion when it carries one."""
    typer.echo(_safe(str(problem)))
    suggestion: str = problem.context.suggestion if isinstance(problem, AniShiftError) else ""
    if suggestion:
        typer.echo(f"  {_safe(suggestion)}")


def _located(path: Path, root: Path) -> str:
    """Return *path* relative to the workspace root, never an absolute location."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _safe(text: str) -> str:
    """Return *text* with secrets and absolute paths redacted for public output."""
    from anishift.application.events import sanitize_event_message  # noqa: PLC0415 - pure application helper

    return sanitize_event_message(text) or ""


def main() -> None:
    """Console-script entry point (see ``[project.scripts]``)."""
    from anishift.cli.console import configure_utf8_streams  # noqa: PLC0415 - before any output
    from anishift.utils.logger import (  # noqa: PLC0415 - configure logging only at the process boundary
        get_logger,
        setup_mode_from_env,
        shutdown_logger,
    )

    configure_utf8_streams()

    setup_mode_from_env(
        console_enabled=False,
        file_path=_log_path(),
    )
    log = get_logger("anishift")
    log.info("AniShift process started")
    try:
        app()
    except Exception as error:
        log.opt(exception=error).critical("AniShift process terminated unexpectedly")
        raise
    finally:
        log.info("AniShift process stopped")
        shutdown_logger()


def _log_path() -> Path:
    """Resolve the application log beside the repository config directory."""
    from anishift.config.user_settings import config_path  # noqa: PLC0415 - keep config startup lazy

    return config_path().parent.parent / "logs" / "anishift.log.jsonl"


if __name__ == "__main__":
    main()
