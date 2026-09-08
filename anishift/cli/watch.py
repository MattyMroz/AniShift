"""UI-neutral watch loop opening one automatic batch window at a time."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application import SCAN_INTERVAL_S, SUBSCRIPTION_CHECK_INTERVAL_S, WatchLedger
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.errors import AniShiftError
from anishift.paths import config_path
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

STATE_DIR_NAME: Final[str] = "watch"
"""Directory beside the panel preferences that holds the daemon's state files."""

LOCK_FILE_NAME: Final[str] = "daemon.lock"
"""File whose operating-system lock admits exactly one watch process."""

PID_FILE_NAME: Final[str] = "daemon.pid"
"""File carrying the identifier of the process that currently holds the lock."""

RESIDENT_LOCK_FILE_NAME: Final[str] = "resident.lock"
"""File whose operating-system lock admits exactly one resident.

The resident keeps a lock of its own beside the watch loop's, because both may exist
until the resident replaces the loop.
"""

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
    return config_path().parent / STATE_DIR_NAME


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
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)  # noqa: S603 - argv built here
    return subprocess.Popen(command)  # noqa: S603 - argv built here


def request_stop(state_dir: Path) -> None:
    """Ask the running daemon to finish after its current scan."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / STOP_FILE_NAME).touch()


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
    """Scan, spawn and poll until the stop flag appears or an interrupt arrives."""
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
    """Return the groups a batch window may take, or ``None`` when the scan failed."""
    try:
        workspace: InspectedWorkspace = service.discover()
        preset: AutoPreset = service.get_preset(service.default_preset_id())
        candidates: tuple[str, ...] = ledger.candidates(workspace, preset, now)
    except (AniShiftError, OSError) as problem:
        logger.warning("Watch scan failed", error_class=type(problem).__name__)
        return None
    return candidates


def _check_subscriptions(service: AppService, now: float, checked_at: float | None) -> float | None:
    """Check every followed series once per interval; return when the last check happened."""
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
    """Whether somebody asked the daemon to finish."""
    return (state_dir / STOP_FILE_NAME).exists()


def _clear_stop(state_dir: Path) -> None:
    """Drop a stop flag, so a request never outlives the run that consumed it."""
    _remove(state_dir / STOP_FILE_NAME)


def _write_pid(state_dir: Path) -> None:
    """Record this process identifier beside the lock for the status command."""
    try:
        (state_dir / PID_FILE_NAME).write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        logger.debug("Watch could not record its process identifier")


def _recorded_pid(state_dir: Path) -> int | None:
    """Read the identifier the running daemon wrote, or ``None`` when unreadable."""
    try:
        return int((state_dir / PID_FILE_NAME).read_text(encoding="utf-8").strip())
    except OSError, ValueError:
        return None


def _remove(path: Path) -> None:
    """Delete one state file, tolerating a directory somebody already cleaned."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Watch could not remove one of its state files")


def spawn_resident() -> subprocess.Popen[bytes]:
    """Start the resident detached from this process, without a console of its own.

    Raises:
        AutostartError: The windowless interpreter is missing beside this one.
    """
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
) -> int:
    """Own the automation of *state_dir* until a shutdown command ends the process.

    The lock is taken before anything is recorded, so a second resident racing this one
    leaves without ever naming itself as the owner.
    """
    from anishift.application import (  # noqa: PLC0415 - keep the owner off the Typer import path
        WATCH_STATE_FILE_NAME,
        AutomationOwner,
        WatchStateStore,
    )
    from anishift.platform.local_control import (  # noqa: PLC0415 - keep the transport off the CLI import
        ControlServer,
        InstanceRecord,
        control_endpoint,
        ensure_authkey,
        remove_instance,
        write_instance,
    )

    lock: ProcessLock = ProcessLock(state_dir / RESIDENT_LOCK_FILE_NAME)
    if not lock.acquire():
        logger.warning(_RESIDENT_REFUSED)
        return EXIT_REFUSED
    try:
        instance_id: str = f"instance-{token_hex(_INSTANCE_ID_BYTES)}"
        owner = AutomationOwner(
            service,
            WatchStateStore(state_dir / WATCH_STATE_FILE_NAME),
            instance_id=instance_id,
            clock=clock,
        )
        endpoint: str = control_endpoint(state_dir)
        server = ControlServer(endpoint, ensure_authkey(state_dir), owner.handle)
        owner.attach_broadcast(server.broadcast)
        try:
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
            server.close()
            remove_instance(state_dir)
    finally:
        lock.release()
    logger.info("Resident stopped")
    return EXIT_SUCCESS


def _on_signal(request_shutdown: Callable[[], None]) -> None:
    """Ask the owner to shut down when the process is asked to terminate."""
    try:
        signal.signal(signal.SIGTERM, lambda _number, _frame: request_shutdown())
    except OSError, ValueError:
        logger.debug("Termination signals are not deliverable in this process")
