"""UI-neutral watch loop running one automatic batch at a time, in a window or in this process."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application import SCAN_INTERVAL_S, SUBSCRIPTION_CHECK_INTERVAL_S, WatchLedger
from anishift.application.cancellation import EventCancellationToken
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.headless import run_batch
from anishift.errors import AniShiftError
from anishift.paths import config_path
from anishift.platform.process_lock import ProcessLock
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from anishift.application import AppService, AutoPreset, CheckOutcome, InspectedWorkspace

__all__ = [
    "BATCH_THREAD_NAME",
    "ERROR_BACKOFF_S",
    "LOCK_FILE_NAME",
    "PID_FILE_NAME",
    "STATE_DIR_NAME",
    "STOP_FILE_NAME",
    "BatchRunner",
    "Child",
    "Clock",
    "InProcessBatch",
    "Sleeper",
    "Spawner",
    "WatchStatus",
    "WindowBatch",
    "batch_command",
    "request_stop",
    "run_daemon",
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

STOP_FILE_NAME: Final[str] = "stop"
"""Flag asking the running daemon to end its loop after the current scan."""

ERROR_BACKOFF_S: Final[float] = 30.0
"""Delay after a failed scan, so a broken environment is not retried every scan."""

BATCH_THREAD_NAME: Final[str] = "anishift-batch"
"""Name of the thread a headless watch runs one batch in."""

_CONSOLE_SCRIPT_NAME: Final[str] = "anishift.exe"
"""Installed console script preferred over a module launch for a batch window."""

_REFUSED_MESSAGE: Final[str] = "Another watch process already holds the lock"
"""Reason logged when a second daemon leaves without touching the library."""


class Child(Protocol):
    """Live batch the watch loop only ever polls for its exit code."""

    def poll(self) -> int | None:
        """Return the exit code once the batch ended, ``None`` while it runs."""
        ...


class BatchRunner(Protocol):
    """Strategy processing one batch of source groups for the watch loop."""

    def start(self, group_ids: Sequence[str]) -> Child:
        """Begin one batch for *group_ids* and return the live child to poll."""
        ...

    def stop(self) -> int | None:
        """End a batch still running, returning its exit code when this call ended it."""
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


class WindowBatch:
    """Batch strategy opening one console window per batch, as a watch on a desktop does."""

    __slots__ = ("_spawner",)

    def __init__(self, spawner: Spawner = spawn_window) -> None:
        """Take the function opening one window for a batch argv."""
        self._spawner: Spawner = spawner

    def start(self, group_ids: Sequence[str]) -> Child:
        """Open one batch window and return the live process."""
        return self._spawner(batch_command(group_ids))

    def stop(self) -> int | None:
        """Leave an open window alone, because it reports its outcome and closes itself."""
        return None


class InProcessBatch:
    """Batch strategy executing one plan inside the watch process, for a run without a window."""

    __slots__ = ("_code", "_service", "_thread", "_token")

    def __init__(self, service: AppService) -> None:
        """Take the facade every batch of this watch runs on."""
        self._service: AppService = service
        self._thread: threading.Thread | None = None
        self._token: EventCancellationToken | None = None
        self._code: int = EXIT_REFUSED

    def start(self, group_ids: Sequence[str]) -> Child:
        """Run one batch in a daemon thread and return this runner as the child to poll."""
        token: EventCancellationToken = EventCancellationToken()
        self._token = token
        self._code = EXIT_REFUSED
        thread: threading.Thread = threading.Thread(
            target=self._execute,
            args=(tuple(group_ids), token),
            name=BATCH_THREAD_NAME,
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def poll(self) -> int | None:
        """Return the exit code the batch recorded once its thread ended."""
        thread: threading.Thread | None = self._thread
        if thread is None or thread.is_alive():
            return None
        return self._code

    def stop(self) -> int | None:
        """Cancel a live batch, wait for its thread and return the code it recorded."""
        thread: threading.Thread | None = self._thread
        if thread is None:
            return None
        if self._token is not None:
            self._token.cancel()
        thread.join()
        self._thread = None
        return self._code

    def _execute(self, group_ids: tuple[str, ...], token: EventCancellationToken) -> None:
        self._code = run_batch(self._service, group_ids, cancel=token)


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


def run_daemon(  # noqa: PLR0913 - every extra parameter is one injected collaborator
    service: AppService,
    *,
    state_dir: Path,
    spawner: Spawner = spawn_window,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
    batch: BatchRunner | None = None,
) -> int:
    """Watch the library until a stop is requested, running one batch at a time.

    ``batch`` replaces the console window every batch opens by default; a headless
    watch passes :class:`InProcessBatch`, which keeps the whole run in this process.
    """
    lock: ProcessLock = ProcessLock(state_dir / LOCK_FILE_NAME)
    if not lock.acquire():
        logger.warning(_REFUSED_MESSAGE)
        return EXIT_REFUSED
    _clear_stop(state_dir)
    _write_pid(state_dir)
    runner: BatchRunner = WindowBatch(spawner) if batch is None else batch
    logger.info("Watch started", headless=batch is not None)
    try:
        return _watch_loop(service, state_dir, runner, clock, sleep)
    finally:
        lock.release()
        _remove(state_dir / PID_FILE_NAME)


def _watch_loop(
    service: AppService,
    state_dir: Path,
    runner: BatchRunner,
    clock: Clock,
    sleep: Sleeper,
) -> int:
    """Scan, start and poll until the stop flag appears or an interrupt arrives."""
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
                _record_finished(ledger, started, exit_code)
            child, started = None, ()
            checked_at = _check_subscriptions(service, clock(), checked_at)
            candidates: tuple[str, ...] | None = _scan(service, ledger, clock())
            if candidates is None:
                sleep(ERROR_BACKOFF_S)
                continue
            if candidates:
                ledger.mark_started(candidates)
                child, started = runner.start(candidates), candidates
                logger.info("Batch started", groups=len(candidates))
            sleep(SCAN_INTERVAL_S)
    except KeyboardInterrupt:
        _end_live_batch(runner, ledger, child, started)
        logger.info("Watch stopped by an interrupt")
        return EXIT_SUCCESS
    _end_live_batch(runner, ledger, child, started)
    _clear_stop(state_dir)
    logger.info("Watch stopped on request")
    return EXIT_SUCCESS


def _end_live_batch(
    runner: BatchRunner,
    ledger: WatchLedger,
    child: Child | None,
    started: tuple[str, ...],
) -> None:
    """End a batch the watch is leaving behind, recording the code the runner reports."""
    if child is None:
        return
    exit_code: int | None = runner.stop()
    if exit_code is None:
        return
    _record_finished(ledger, started, exit_code)


def _record_finished(ledger: WatchLedger, started: tuple[str, ...], exit_code: int) -> None:
    """Release the groups of a finished batch and state the code it left."""
    ledger.mark_finished(started)
    logger.info("Batch finished", groups=len(started), exit_code=exit_code)


def _scan(service: AppService, ledger: WatchLedger, now: float) -> tuple[str, ...] | None:
    """Return the groups the next batch may take, or ``None`` when the scan failed."""
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
