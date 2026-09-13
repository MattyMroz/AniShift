"""UI-neutral watch loop opening one automatic batch window at a time."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from shutil import which
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application import SCAN_INTERVAL_S, SUBSCRIPTION_CHECK_INTERVAL_S, WatchLedger
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.errors import AniShiftError
from anishift.paths import WATCH_DIRECTORY as STATE_DIR_NAME
from anishift.paths import relocation_journal_dir, watch_dir
from anishift.platform.child_processes import contain_children, independent_child_flags
from anishift.platform.directory_watch import DirectoryChange, DirectoryWatch
from anishift.platform.process_lock import ProcessLock
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from anishift.application import AppService, AutoPreset, CheckOutcome, InspectedWorkspace

__all__ = [
    "ERROR_BACKOFF_S",
    "LOCK_FILE_NAME",
    "PID_FILE_NAME",
    "RESIDENT_LOCK_FILE_NAME",
    "STATE_DIR_NAME",
    "STOP_FILE_NAME",
    "Child",
    "Clock",
    "Sleeper",
    "Spawner",
    "WatchStatus",
    "batch_command",
    "request_stop",
    "run_daemon",
    "run_resident",
    "spawn_resident",
    "spawn_window",
    "watch_state_dir",
    "watch_status",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LOCK_FILE_NAME: Final[str] = "daemon.lock"
"""File whose operating-system lock admits exactly one watch process."""

PID_FILE_NAME: Final[str] = "daemon.pid"
"""File carrying the identifier of the process that currently holds the lock."""

RESIDENT_LOCK_FILE_NAME: Final[str] = "resident.lock"
"""File whose operating-system lock admits exactly one resident."""

STOP_FILE_NAME: Final[str] = "stop"
"""Flag asking the running daemon to end its loop after the current scan."""

ERROR_BACKOFF_S: Final[float] = 30.0
"""Delay after a failed scan, so a broken environment is not retried every scan."""

_CONSOLE_SCRIPT_NAME: Final[str] = "anishift.exe"
"""Installed console script preferred over a module launch for a batch window."""

_INSTANCE_ID_BYTES: Final[int] = 8
"""Random bytes making the identity of one resident unique between restarts."""

_REFUSED_MESSAGE: Final[str] = "Another watch process already holds the lock"
"""Reason logged when a second daemon leaves without touching the library."""

_RESIDENT_REFUSED: Final[str] = "Another resident already holds the lock"
"""Reason logged when a second resident leaves without recording itself."""


class Child(Protocol):
    """Live batch window the watch loop only ever polls for its exit code."""

    def poll(self) -> int | None:
        """Return the exit code once the window ended, ``None`` while it runs."""
        ...


type Spawner = Callable[[Sequence[str]], Child]
"""Opens one batch window for an argv and returns the live child."""

type Clock = Callable[[], float]
"""Monotonic source of the scan timestamp handed to the ledger."""

type Sleeper = Callable[[float], None]
"""Blocks the loop for the given number of seconds."""


@dataclass(frozen=True, slots=True)
class WatchStatus:
    """Whether a watch process runs, and the identifier it recorded."""

    running: bool
    pid: int | None


def watch_state_dir() -> Path:
    """Return ``<repo>/config/watch``, the directory holding every daemon state file."""
    return watch_dir()


def batch_command(group_ids: Sequence[str]) -> list[str]:
    """Return the argv opening one batch window for *group_ids*."""
    console_script: Path = Path(sys.executable).with_name(_CONSOLE_SCRIPT_NAME)
    launcher: list[str] = (
        [str(console_script)] if console_script.is_file() else [sys.executable, "-m", "anishift.cli.main"]
    )
    return [*launcher, "watch", "batch", *group_ids]


def spawn_window(command: Sequence[str]) -> subprocess.Popen[bytes]:
    """Open *command* in its own console window, leaving its streams to the user."""
    if sys.platform == "win32":
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE | independent_child_flags())  # noqa: S603
    return subprocess.Popen(command)  # noqa: S603 - argv built here


def request_stop(state_dir: Path) -> None:
    """Stop admission in the existing resident and signal any legacy daemon."""
    from anishift.platform.local_control import ControlClient, connect  # noqa: PLC0415

    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / STOP_FILE_NAME).touch()
    client: ControlClient | None = connect(state_dir)
    if client is not None:
        try:
            client.call("shutdown")
        finally:
            client.close()


def watch_status(state_dir: Path) -> WatchStatus:
    """Report whether a daemon holds the lock; a leftover lock file proves nothing."""
    lock: ProcessLock = ProcessLock(state_dir / LOCK_FILE_NAME)
    if lock.acquire():
        lock.release()
        return WatchStatus(running=False, pid=None)
    return WatchStatus(running=True, pid=_recorded_pid(state_dir))


def run_daemon(
    service: AppService,
    *,
    state_dir: Path,
    spawner: Spawner = spawn_window,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
) -> int:
    """Watch the library until a stop is requested, running one batch window at a time."""
    lock: ProcessLock = ProcessLock(state_dir / LOCK_FILE_NAME)
    if not lock.acquire():
        logger.warning(_REFUSED_MESSAGE)
        return EXIT_REFUSED
    _clear_stop(state_dir)
    _write_pid(state_dir)
    logger.info("Watch started")
    try:
        return _watch_loop(service, state_dir, spawner, clock, sleep)
    finally:
        lock.release()
        _remove(state_dir / PID_FILE_NAME)


def _watch_loop(
    service: AppService,
    state_dir: Path,
    spawner: Spawner,
    clock: Clock,
    sleep: Sleeper,
) -> int:
    ledger: WatchLedger = WatchLedger()
    child: Child | None = None
    started: tuple[str, ...] = ()
    checked_at: float | None = None
    try:
        while not _stop_requested(state_dir):
            exit_code: int | None = None if child is None else child.poll()
            if child is not None and exit_code is None:
                sleep(SCAN_INTERVAL_S)
                continue
            if exit_code is not None:
                ledger.mark_finished(started)
                logger.info("Batch window finished", groups=len(started), exit_code=exit_code)
            child, started = None, ()
            checked_at = _check_subscriptions(service, clock(), checked_at)
            candidates: tuple[str, ...] | None = _scan(service, ledger, clock())
            if candidates is None:
                sleep(ERROR_BACKOFF_S)
                continue
            if candidates:
                ledger.mark_started(candidates)
                child, started = spawner(batch_command(candidates)), candidates
                logger.info("Batch window started", groups=len(candidates))
            sleep(SCAN_INTERVAL_S)
    except KeyboardInterrupt:
        logger.info("Watch stopped by an interrupt")
        return EXIT_SUCCESS
    _clear_stop(state_dir)
    logger.info("Watch stopped on request")
    return EXIT_SUCCESS


def _scan(service: AppService, ledger: WatchLedger, now: float) -> tuple[str, ...] | None:
    try:
        workspace: InspectedWorkspace = service.discover()
        preset: AutoPreset = service.get_preset(service.default_preset_id())
        candidates: tuple[str, ...] = ledger.candidates(workspace, preset, now)
    except (AniShiftError, OSError) as problem:
        logger.warning("Watch scan failed", error_class=type(problem).__name__)
        return None
    return candidates


def _check_subscriptions(service: AppService, now: float, checked_at: float | None) -> float | None:
    if service.subscriptions is None:
        return checked_at
    if checked_at is not None and now - checked_at < SUBSCRIPTION_CHECK_INTERVAL_S:
        return checked_at
    try:
        outcomes: tuple[CheckOutcome, ...] = service.subscriptions.check_all()
    except (AniShiftError, OSError) as problem:
        logger.warning("Subscription check failed", error_class=type(problem).__name__)
        return now
    logger.info(
        "Subscriptions checked",
        subscriptions=len(outcomes),
        downloaded=sum(outcome.downloaded for outcome in outcomes),
        problems=sum(1 for outcome in outcomes if outcome.problem),
    )
    return now


def _stop_requested(state_dir: Path) -> bool:
    return (state_dir / STOP_FILE_NAME).exists()


def _clear_stop(state_dir: Path) -> None:
    _remove(state_dir / STOP_FILE_NAME)


def _write_pid(state_dir: Path) -> None:
    try:
        (state_dir / PID_FILE_NAME).write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        logger.debug("Watch could not record its process identifier")


def _recorded_pid(state_dir: Path) -> int | None:
    try:
        return int((state_dir / PID_FILE_NAME).read_text(encoding="utf-8").strip())
    except OSError, ValueError:
        return None


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Watch could not remove one of its state files")


def spawn_resident() -> subprocess.Popen[bytes]:
    """Start the resident detached from this process, without a console of its own."""
    from anishift.platform.autostart import resident_command  # noqa: PLC0415 - keep the scheduler lazy

    command: list[str] = resident_command()
    if sys.platform == "win32":
        return subprocess.Popen(  # noqa: S603 - argv built here
            command,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return subprocess.Popen(  # noqa: S603 - argv built here
        command,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_resident(
    service: AppService,
    *,
    state_dir: Path,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_ready: Callable[[], None] | None = None,
    enable_tray: bool = False,
) -> int:
    """Own the automation of *state_dir* until a shutdown command ends the process."""
    from anishift.application import (  # noqa: PLC0415 - keep the owner off the Typer import path
        WATCH_STATE_FILE_NAME,
        AutomationOwner,
        ReadyStore,
        WatchStateStore,
    )
    from anishift.platform.local_control import (  # noqa: PLC0415 - keep the transport off the CLI import
        ControlServer,
        InstanceRecord,
        clear_endpoint,
        control_endpoint,
        ensure_authkey,
        remove_instance,
        write_instance,
    )
    from anishift.platform.tray import TrayIcon  # noqa: PLC0415 - desktop resources belong to the resident

    lock: ProcessLock = ProcessLock(state_dir / RESIDENT_LOCK_FILE_NAME)
    if not lock.acquire():
        logger.warning(_RESIDENT_REFUSED)
        return EXIT_REFUSED
    try:
        if enable_tray:
            contain_children()
        instance_id: str = f"instance-{token_hex(_INSTANCE_ID_BYTES)}"
        store: WatchStateStore = WatchStateStore(state_dir / WATCH_STATE_FILE_NAME)
        owner = AutomationOwner(
            service,
            store,
            instance_id=instance_id,
            clock=clock,
            open_panel=_spawn_panel,
            ready_store=ReadyStore(relocation_journal_dir(state_dir), service.workspace_root),
        )
        endpoint: str = control_endpoint(state_dir)
        clear_endpoint(endpoint)
        server = ControlServer(endpoint, ensure_authkey(state_dir), owner.handle, on_disconnect=owner.disconnect)
        tray: TrayIcon | None = TrayIcon(owner.tray_action) if enable_tray else None

        def broadcast(frame: Mapping[str, object], terminal: bool) -> None:
            server.broadcast(frame, terminal)
            payload: object = frame.get("payload")
            if tray is None or not isinstance(payload, Mapping):
                return
            if frame.get("event") == "state_changed":
                tray.update(
                    auto_enabled=bool(payload.get("auto_enabled")),
                    busy=bool(payload.get("requests")),
                    problem=bool(payload.get("transfers_problem") or payload.get("subscriptions_problem")),
                )
            elif frame.get("event") == "notification":
                tray.notify(str(payload.get("title", "AniShift")), str(payload.get("message", "")))

        owner.attach_broadcast(broadcast)
        file_watch: DirectoryWatch | None = None
        try:
            file_watch = DirectoryWatch(service.workspace_root, owner.files_changed)
            owner.files_changed(
                DirectoryChange(
                    reconcile=True,
                    reason="polling_fallback" if file_watch.mode == "polling" else "startup",
                )
            )
            write_instance(
                state_dir,
                InstanceRecord(
                    instance_id=instance_id,
                    pid=os.getpid(),
                    endpoint=endpoint,
                    started_at=clock().astimezone(UTC).isoformat(),
                ),
            )
            _on_signal(owner.request_shutdown)
            logger.info("Resident started")
            if on_ready is not None:
                on_ready()
            owner.serve()
        finally:
            if tray is not None:
                tray.close()
            if file_watch is not None:
                file_watch.close()
            server.close()
            if service.acquisition is not None:
                service.acquisition.close()
            remove_instance(state_dir)
    finally:
        lock.release()
    logger.info("Resident stopped")
    return EXIT_SUCCESS


def _spawn_panel() -> None:
    python: Path = Path(sys.executable)
    if python.name.casefold() == "pythonw.exe":
        python = python.with_name("python.exe")
    command: list[str] = [str(python), "-m", "anishift.cli.main", "--resident", "--state"]
    terminal: str | None = which("wt.exe")
    if terminal is not None:
        window: str = f"AniShift-{token_hex(8)}"
        command = [terminal, "-w", window, *command, "--terminal-window", window]
    try:
        if terminal is not None:
            subprocess.Popen(  # noqa: S603 - explicit panel launcher
                command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | independent_child_flags()
            )
        else:
            spawn_window(command)
    except OSError as error:
        logger.warning("Could not open the panel", error_class=type(error).__name__)


def _on_signal(request_shutdown: Callable[[], None]) -> None:
    try:
        signal.signal(signal.SIGTERM, lambda _number, _frame: request_shutdown())
    except OSError, ValueError:
        logger.debug("Termination signals are not deliverable in this process")
