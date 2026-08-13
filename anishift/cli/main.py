"""Typer entry point for the Textual app and non-interactive utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from anishift.application.events import EventBuffer
from anishift.application.results import GroupStatus, RunResult
from anishift.bootstrap import bootstrap, create_app_service
from anishift.errors import AniShiftError
from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor
from anishift.setup.installer import ResourceResult, run_setup
from anishift.utils.rich_console import StatusType, console, get_status_icon

app = typer.Typer(
    name="anishift",
    help="AniShift — terminal-based anime lector for Polish.",
    no_args_is_help=False,
    add_completion=False,
)

_STATUS_ICON: dict[CheckStatus, StatusType] = {
    CheckStatus.OK: "success",
    CheckStatus.WARN: "warning",
    CheckStatus.FAIL: "error",
    CheckStatus.SKIP: "stopped",
}
"""Maps a check outcome to a ``rich_console`` status-icon name."""


def _print_doctor_report(results: list[CheckResult]) -> None:
    """Render doctor results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
        if result.suggestion and result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            console.print(f"   [gray]-> {result.suggestion}[/gray]")


def _print_setup_report(results: list[ResourceResult]) -> None:
    """Render setup results without importing the retired interactive CLI."""
    for result in results:
        console.print(f"[bold]{result.name}[/bold]: {result.outcome} — {result.detail}")


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Launch the Textual interface when invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        launch_tui()


def launch_tui() -> None:
    """Compose and run the full-screen interface at the process boundary."""
    from anishift.tui import AniShiftApp  # noqa: PLC0415 - utilities must not import Textual

    context = bootstrap()
    AniShiftApp(
        create_app_service(context),
        workspace_label=context.workspace_root.name,
    ).run()


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


@app.command("run")
def run_preset(
    preset: Annotated[str, typer.Option("--preset", help="Automatic preset ID to execute.")],
) -> None:
    """Run one automatic preset without starting the Textual interface."""
    try:
        context = bootstrap()
        service = create_app_service(context)
        workspace = service.discover()
        selected_ids: tuple[str, ...] = _require_selected_groups(tuple(group.group_id for group in workspace.groups))
        plan = service.plan_auto(selected_ids, service.get_preset(preset))
        result: RunResult = service.execute(plan, EventBuffer())
    except (AniShiftError, ValueError) as error:
        console.print(f"[error]{error}[/error]")
        raise typer.Exit(code=1) from error
    for group in result.groups:
        console.print(f"{group.group_id}: {group.status.value} ({len(group.products)} products)")
    if any(group.status is not GroupStatus.SUCCEEDED for group in result.groups):
        raise typer.Exit(code=1)


def _require_selected_groups(group_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Reject a non-interactive run that discovered no supported inputs."""
    if not group_ids:
        msg = "Workspace contains no supported source groups"
        raise ValueError(msg)
    return group_ids


def main() -> None:
    """Console-script entry point (see ``[project.scripts]``)."""
    from anishift.utils.logger import (  # noqa: PLC0415 - configure logging only at the process boundary
        get_logger,
        setup_mode_from_env,
        shutdown_logger,
    )

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
