"""CLI entry point — Typer app registered as the ``anishift`` script."""

from __future__ import annotations

import signal
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, NoReturn

import typer

from anishift.cli.exit_codes import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_REFUSED, run_exit_code
from anishift.errors import AniShiftError
from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor
from anishift.setup.installer import run_setup
from anishift.utils.logger import get_logger
from anishift.utils.rich_console import StatusType, console, get_status_icon

if TYPE_CHECKING:
    from anishift.application import (
        AppService,
        CheckOutcome,
        RunResult,
        Subscription,
        SubscriptionService,
    )
    from anishift.application.events import RunEvent
    from anishift.cli.control import ResidentStatus
    from anishift.cli.run import AutoRunRefusal
    from anishift.cli.watch import WatchStatus
    from anishift.platform.autostart import AutostartStatus
    from anishift.setup.installer import ResourceResult

app = typer.Typer(
    name="anishift",
    help="AniShift — terminal-based anime lector for Polish.",
    no_args_is_help=False,
    add_completion=False,
)

watch_app = typer.Typer(
    help="Run or control the background owner of the library.",
    no_args_is_help=False,
)

autostart_app = typer.Typer(help="Manage the Windows logon task that starts the watch.")

qbit_app = typer.Typer(help="Check and prepare the qBittorrent Web UI that downloads into the library.")

subs_app = typer.Typer(help="Followed series whose new episodes download on their own.")

app.add_typer(watch_app, name="watch")
app.add_typer(autostart_app, name="autostart")
app.add_typer(qbit_app, name="qbit")
app.add_typer(subs_app, name="subs")

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

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

_WATCH_RUNNING: Final[str] = "running (pid {pid})"
"""Status line naming the process that currently watches the library."""

_WATCH_RUNNING_UNKNOWN: Final[str] = "running"
"""Status line used when the watch runs but recorded no readable identifier."""

_WATCH_STOPPED: Final[str] = "stopped"
"""Status line stated when no process watches the library."""

_RESIDENT_LINE: Final[str] = "resident: {state}"
"""Second status line, naming the process that owns the automation."""

_WATCH_STOP_REQUESTED: Final[str] = "Stop requested; the watch ends after its current scan."
"""Confirmation of a stop request, which is accepted even with nothing running."""

_WATCH_BUSY: Final[str] = "Another watch process is already running; see `anishift watch status`"
"""Refusal stated when a second watch would take a lock somebody else holds."""

_WATCH_STARTED: Final[str] = "Watching the library; Ctrl+C or `anishift watch stop` ends it"
"""Opening line of a watch running in a terminal, so the session never looks stuck."""

_AUTOSTART_ENABLED: Final[str] = "Autostart is on; the watch runs now and after every logon."
"""Confirmation printed once the logon task exists and the watch was started."""

_AUTOSTART_DISABLED: Final[str] = "Autostart is off; the running watch was asked to stop."
"""Confirmation printed once the logon task is gone and a stop was requested."""

_QBIT_ABSENT: Final[str] = "This session has no torrent client composed."
"""Refusal stated when the facade was built without the acquisition boundary."""

_WATCH_SUGGESTION: Final[str] = "Run `anishift autostart enable` so the library is watched now and after every logon"
"""Advice printed by the doctor when nothing watches the library."""

_SUBS_EMPTY: Final[str] = "No followed series."
"""Line printed when the subscription list is empty."""

_SUBS_ROW: Final[str] = "{id} [{group}] {series} · next: {episode} · checked: {checked}"
"""One list row per followed series."""

_SUBS_REMOVED: Final[str] = "Removed."
"""Confirmation printed once a followed series is gone."""

_SUBS_UNKNOWN: Final[str] = "No followed series has that id."
"""Refusal printed when the id to remove does not exist."""

_SUBS_CHECKED: Final[str] = "[{group}] {series}: downloaded {count}"
"""Result row of one manual check."""

_SUBS_PROBLEM: Final[str] = "[{group}] {series}: {problem}"
"""Result row of one manual check that failed."""


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
def _default(
    ctx: typer.Context,
    resident: bool = typer.Option(False, "--resident", hidden=True),
    state: bool = typer.Option(False, "--state", hidden=True),
    terminal_window: str | None = typer.Option(None, "--terminal-window", hidden=True),
) -> None:
    """Open the interactive command line when invoked without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    service: AppService = _composed_service()
    from anishift.cli.control import open_control  # noqa: PLC0415
    from anishift.cli.interactive import run_interactive  # noqa: PLC0415 - keep prompts off technical commands
    from anishift.cli.resident import ResidentSession  # noqa: PLC0415
    from anishift.cli.watch import watch_state_dir  # noqa: PLC0415

    del resident
    session: ResidentSession = ResidentSession(service.workspace_root, lambda: open_control(watch_state_dir()))
    try:
        run_interactive(service, resident=session, show_state=state, terminal_window=terminal_window)
    finally:
        session.close()
        service.close()


@app.command()
def doctor(resident: bool = typer.Option(False, "--resident", hidden=True)) -> None:
    """Run diagnostics: binaries, keys, workspace, torrent client, watch and autostart."""
    del resident
    results = run_doctor(managed_torrents=True)
    results.extend(_automation_checks())
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


@watch_app.callback(invoke_without_command=True)
def _watch(ctx: typer.Context) -> None:
    """Watch the library in this terminal until `anishift watch stop`."""
    if ctx.invoked_subcommand is not None:
        return
    from anishift.cli.watch import run_resident, watch_state_dir, watch_status  # noqa: PLC0415

    state_dir: Path = watch_state_dir()
    if watch_status(state_dir).running:
        _tell(_WATCH_BUSY)
        raise typer.Exit(code=EXIT_REFUSED)
    service: AppService = _composed_service(managed_torrents=True)
    _tell(_WATCH_STARTED)
    raise typer.Exit(code=run_resident(service, state_dir=state_dir, enable_tray=True))


def _tell(sentence: str) -> None:
    """State one line of the watch, staying silent in the windowless logon process."""
    if sys.stdout is None:
        return
    typer.echo(sentence)


@watch_app.command("stop")
def watch_stop() -> None:
    """Stop resident admission and drain active work without starting a missing owner."""
    from anishift.cli.watch import request_stop, watch_state_dir  # noqa: PLC0415 - keep the watch loop lazy

    request_stop(watch_state_dir())
    typer.echo(_safe(_WATCH_STOP_REQUESTED))


@watch_app.command("status")
def watch_state() -> None:
    """Report whether a watch process and a resident are running."""
    from anishift.cli.control import resident_status  # noqa: PLC0415 - keep the transport lazy
    from anishift.cli.watch import watch_state_dir, watch_status  # noqa: PLC0415 - keep the watch loop lazy

    state_dir: Path = watch_state_dir()
    state: WatchStatus = watch_status(state_dir)
    typer.echo(_safe(_watch_status_line(state)))
    resident: ResidentStatus = resident_status(state_dir)
    typer.echo(_safe(_RESIDENT_LINE.format(state=_resident_status_line(resident))))


@watch_app.command("resident", hidden=True)
def watch_resident() -> None:
    """Own the automation of this library until a shutdown command ends the process."""
    from anishift.cli.watch import run_resident, watch_state_dir  # noqa: PLC0415 - keep the loop lazy

    raise typer.Exit(
        code=run_resident(_composed_service(managed_torrents=True), state_dir=watch_state_dir(), enable_tray=True)
    )


@watch_app.command("batch", hidden=True)
def watch_batch(
    group_ids: Annotated[
        list[str],
        typer.Argument(help="IDs of the source groups this window processes."),
    ],
) -> None:
    """Explain the replacement for obsolete automatic batch windows."""
    del group_ids
    typer.echo("Batch windows were replaced by the resident. Open AniShift and choose State or Manual.")
    raise typer.Exit(code=EXIT_REFUSED)


@autostart_app.command("enable")
def autostart_enable(resident: bool = typer.Option(False, "--resident", hidden=True)) -> None:
    """Register the logon task and start watching right away."""
    from anishift.platform.autostart import (  # noqa: PLC0415 - keep the scheduler lazy
        enable,
        watch_command,
    )

    try:
        del resident
        enable(watch_command())
    except AniShiftError as problem:
        _refuse_command(problem)
    typer.echo(_safe(_AUTOSTART_ENABLED))


@autostart_app.command("disable")
def autostart_disable() -> None:
    """Remove the logon task and ask a running watch to stop."""
    from anishift.cli.watch import request_stop, watch_state_dir  # noqa: PLC0415 - keep the watch loop lazy
    from anishift.platform.autostart import disable  # noqa: PLC0415 - keep the scheduler lazy

    try:
        disable()
    except AniShiftError as problem:
        _refuse_command(problem)
    request_stop(watch_state_dir())
    typer.echo(_safe(_AUTOSTART_DISABLED))


@autostart_app.command("status")
def autostart_state() -> None:
    """Report whether the logon task is registered and switched on."""
    from anishift.platform.autostart import status  # noqa: PLC0415 - keep the scheduler lazy

    try:
        state: AutostartStatus = status()
    except AniShiftError as problem:
        _refuse_command(problem)
    typer.echo(_safe(state.value))


@qbit_app.command("status")
def qbit_status() -> None:
    """Report private client readiness without starting a download or process."""
    from anishift.setup.doctor import check_managed_torrent_client  # noqa: PLC0415

    try:
        _print_doctor_report([check_managed_torrent_client()])
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)


@qbit_app.command("setup")
def qbit_setup() -> None:
    """Prepare the verified private binary without changing the personal installation."""
    from anishift.setup.installer import ensure_resource  # noqa: PLC0415

    try:
        ensure_resource("qbittorrent", show_progress=False)
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)
    qbit_status()


@subs_app.command("list")
def subs_list() -> None:
    """List every followed series with its next episode and last check."""
    subscriptions: SubscriptionService = _subscriptions(_composed_service())
    try:
        followed: tuple[Subscription, ...] = subscriptions.list()
    except AniShiftError as problem:
        _refuse_command(problem)
    if not followed:
        typer.echo(_SUBS_EMPTY)
        return
    for entry in followed:
        row: str = _SUBS_ROW.format(
            id=entry.subscription_id,
            group=entry.group,
            series=entry.series,
            episode=entry.next_episode,
            checked=entry.checked_at or "never",
        )
        typer.echo(_safe(row))


@subs_app.command("remove")
def subs_remove(
    subscription_id: Annotated[str, typer.Argument(help="Id shown by `anishift subs list`.")],
) -> None:
    """Stop following one series; downloaded files stay where they are."""
    removed: bool = bool(_resident_call("subscription_remove", {"subscription_id": subscription_id}).get("removed"))
    if not removed:
        typer.echo(_SUBS_UNKNOWN)
        raise typer.Exit(code=EXIT_REFUSED)
    typer.echo(_SUBS_REMOVED)


@subs_app.command("check")
def subs_check() -> None:
    """Check every followed series now and queue the new episodes."""
    from anishift.application import CheckOutcome, decode_view  # noqa: PLC0415

    response: Mapping[str, object] = _resident_call("subscriptions_check")
    raw: object = response.get("outcomes", [])
    outcomes: tuple[CheckOutcome, ...] = (
        tuple(decode_view(CheckOutcome, item) for item in raw) if isinstance(raw, list) else ()
    )
    if not outcomes:
        typer.echo(_SUBS_EMPTY)
        return
    for outcome in outcomes:
        entry: Subscription = outcome.subscription
        if outcome.problem:
            typer.echo(_safe(_SUBS_PROBLEM.format(group=entry.group, series=entry.series, problem=outcome.problem)))
            continue
        typer.echo(_safe(_SUBS_CHECKED.format(group=entry.group, series=entry.series, count=outcome.downloaded)))


def _subscriptions(service: AppService) -> SubscriptionService:
    """Return the composed subscription boundary or refuse with one sentence."""
    subscriptions: SubscriptionService | None = service.subscriptions
    if subscriptions is None:
        typer.echo(_QBIT_ABSENT)
        raise typer.Exit(code=EXIT_REFUSED)
    return subscriptions


def _automation_checks() -> list[CheckResult]:
    """Report whether the library is watched now and after every logon."""
    from anishift.cli.control import resident_status  # noqa: PLC0415
    from anishift.cli.watch import watch_state_dir  # noqa: PLC0415
    from anishift.platform.autostart import AutostartStatus, status  # noqa: PLC0415 - keep the scheduler lazy

    watch: ResidentStatus = resident_status(watch_state_dir())
    checks: list[CheckResult] = [
        CheckResult(
            "watch",
            CheckStatus.OK if watch.running else CheckStatus.WARN,
            _resident_status_line(watch),
            suggestion=_WATCH_SUGGESTION,
        )
    ]
    try:
        task: AutostartStatus = status()
    except AniShiftError as problem:
        checks.append(CheckResult("autostart", CheckStatus.SKIP, str(problem)))
        return checks
    checks.append(
        CheckResult(
            "autostart",
            CheckStatus.OK if task is AutostartStatus.ENABLED else CheckStatus.WARN,
            task.value,
            suggestion=_WATCH_SUGGESTION,
        )
    )
    return checks


def _watch_status_line(state: WatchStatus) -> str:
    """Render one stable line describing the state of the watch process."""
    if not state.running:
        return _WATCH_STOPPED
    if state.pid is None:
        return _WATCH_RUNNING_UNKNOWN
    return _WATCH_RUNNING.format(pid=state.pid)


def _resident_status_line(state: ResidentStatus) -> str:
    """Render one stable line describing the state of the resident."""
    if not state.running:
        return _WATCH_STOPPED
    if state.pid is None:
        return _WATCH_RUNNING_UNKNOWN
    return _WATCH_RUNNING.format(pid=state.pid)


def _refuse_command(problem: AniShiftError) -> NoReturn:
    """State one redacted sentence about a refused command and leave with code 1."""
    logger.warning("Command refused", error_class=type(problem).__name__)
    _echo_problem(problem)
    raise typer.Exit(code=EXIT_REFUSED) from problem


def _run_preset(service: AppService, preset: str) -> NoReturn:
    """Plan and execute one named preset, then leave with the code of its outcome."""
    from anishift.application import PlanPreview  # noqa: PLC0415
    from anishift.cli.control import open_control  # noqa: PLC0415
    from anishift.cli.resident import ResidentSession  # noqa: PLC0415
    from anishift.cli.run import AutoRunRefusal, auto_plan_refusal, select_auto_groups  # noqa: PLC0415
    from anishift.cli.watch import watch_state_dir  # noqa: PLC0415
    from anishift.platform.local_control import ControlError  # noqa: PLC0415

    session: ResidentSession | None = None
    executing: bool = False
    try:
        session = ResidentSession(service.workspace_root, lambda: open_control(watch_state_dir()))
        groups: tuple[str, ...] | AutoRunRefusal = select_auto_groups(session.discover())
        if isinstance(groups, AutoRunRefusal):
            _refuse_preparation(groups)
        session.reserve(groups)
        plan: PlanPreview = session.plan_auto(groups, service.get_preset(preset))
        refusal: AutoRunRefusal | None = auto_plan_refusal(plan)
        if refusal is not None:
            _refuse_preparation(refusal)
        executing = True
        result: RunResult = session.execute(plan, _QuietRunEvents())
    except KeyboardInterrupt:
        typer.echo(_RUN_CANCELLED)
        raise typer.Exit(code=EXIT_CANCELLED) from None
    except (AniShiftError, OSError, ControlError) as problem:
        if executing:
            _echo_problem(problem)
            raise typer.Exit(code=EXIT_INCOMPLETE) from problem
        _refuse_problem(problem)
    finally:
        if session is not None:
            session.close()
        service.close()
    _print_run_report(result, service.workspace_root)
    code: int = run_exit_code(result)
    logger.info("Non-interactive run finished", groups=len(result.groups), exit_code=code)
    raise typer.Exit(code=code)


def _resident_call(kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
    from anishift.cli.control import open_control  # noqa: PLC0415
    from anishift.cli.watch import watch_state_dir  # noqa: PLC0415
    from anishift.platform.local_control import ControlClient, ControlError  # noqa: PLC0415

    client: ControlClient | None = None
    try:
        client = open_control(watch_state_dir())
        return client.call(kind, payload)
    except (AniShiftError, OSError, ControlError) as problem:
        _refuse_problem(problem)
    finally:
        if client is not None:
            client.close()


class _QuietRunEvents:
    """Run-event observer of the non-interactive mode, which reports the outcome alone."""

    def emit(self, event: RunEvent) -> None:
        """Drop one progress event, keeping the consumable report free of interleaving."""


def _composed_service(*, managed_torrents: bool = False) -> AppService:
    """Compose the one production facade every entry point runs on."""
    from anishift.bootstrap import production_service  # noqa: PLC0415 - keep the backend off the Typer import path

    try:
        service: AppService = production_service(managed_torrents=True) if managed_torrents else production_service()
    except (AniShiftError, OSError) as problem:
        _refuse_problem(problem)
    return service


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


def _refuse_problem(problem: Exception) -> NoReturn:
    """State why the run cannot start and leave with the refusal code."""
    logger.warning("Non-interactive run refused", error_class=type(problem).__name__)
    _echo_problem(problem)
    raise typer.Exit(code=EXIT_REFUSED)


def _refuse_preparation(refusal: AutoRunRefusal) -> NoReturn:
    """Render one shared Auto refusal and leave with the refusal code."""
    logger.warning("Non-interactive run refused", reason=refusal.message, blockers=len(refusal.blockers))
    typer.echo(refusal.message)
    for blocker in refusal.blockers:
        typer.echo(f"  {blocker.scope}: {_safe(blocker.message)}")
    if refusal.suggestion:
        typer.echo(f"  {refusal.suggestion}")
    raise typer.Exit(code=EXIT_REFUSED)


def _echo_problem(problem: Exception) -> None:
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
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            log.info("AniShift process stopped")
            shutdown_logger()
        finally:
            signal.signal(signal.SIGINT, previous)


def _log_path() -> Path:
    """Resolve the application log beside the repository config directory."""
    from anishift.paths import log_path  # noqa: PLC0415

    return log_path()


if __name__ == "__main__":
    main()
