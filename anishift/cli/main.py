"""CLI entry point — Typer app registered as the ``anishift`` script.

Stage 1 scope: a banner stub (default, when no subcommand is given) and the
``doctor`` subcommand. Stage 2 replaces the default action with the interactive
shell (banner + REPL).
"""

from __future__ import annotations

from typing import Annotated

import typer

from anishift.cli.commands import print_setup_report
from anishift.errors import AniShiftError
from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor
from anishift.setup.installer import run_setup
from utils.rich_console import StatusType, console, get_status_icon

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


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Launch the interactive shell when invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        from anishift.bootstrap import bootstrap  # noqa: PLC0415
        from anishift.cli.shell import run_shell  # noqa: PLC0415

        run_shell(bootstrap())


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
    print_setup_report(results)
    if any(result.outcome == "failed" for result in results):
        raise typer.Exit(code=1)


def main() -> None:
    """Console-script entry point (see ``[project.scripts]``)."""
    app()


if __name__ == "__main__":
    main()
