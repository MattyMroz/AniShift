"""Windows logon task that starts the AniShift watch, managed through ``schtasks``."""

from __future__ import annotations

import csv
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.platform.binaries import is_windows
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

__all__ = [
    "TASK_NAME",
    "AutostartError",
    "AutostartStatus",
    "AutostartUnsupportedError",
    "Runner",
    "disable",
    "enable",
    "status",
    "watch_command",
]

logger = get_logger(__name__)

type Runner = Callable[..., subprocess.CompletedProcess[str]]
"""Command executor injected in tests, shaped like :func:`subprocess.run`."""

# ── Constants ─────────────────────────────────────────────────────────────────

TASK_NAME: Final[str] = "AniShift Watch"
"""Name of the one scheduled task this module ever creates, queries or removes."""

_SCHTASKS: Final[str] = "schtasks"
"""Windows scheduler client shipped with the system."""

_WATCH_MODULE: Final[str] = "anishift.cli.main"
"""Module the logon task runs to start the watch loop."""

_PYTHONW_NAME: Final[str] = "pythonw.exe"
"""Windowless interpreter that keeps the watch process free of a console."""

_MISSING_TASK_MARKER: Final[str] = "cannot find"
"""Fragment of the ``schtasks`` refusal that means the task simply does not exist."""

_DISABLED_STATUS: Final[str] = "disabled"
"""Value of the CSV status column for a registered but switched-off task."""

_STATUS_COLUMN: Final[int] = 2
"""Index of the ``Status`` column in the headerless ``/FO CSV`` query row."""

_UNSUPPORTED_MESSAGE: Final[str] = "Autostart needs the Windows task scheduler"
"""Refusal stated when autostart is requested on a system without ``schtasks``."""

_UNSUPPORTED_HINT: Final[str] = "Start `anishift watch` yourself on this system"
"""Suggestion offered beside a refused autostart request."""

_MISSING_PYTHONW: Final[str] = "The watch process needs pythonw.exe beside the interpreter"
"""Failure stated when the windowless interpreter is absent from the environment."""

_MISSING_PYTHONW_HINT: Final[str] = "Recreate the environment with a full Python installation"
"""Suggestion offered when the windowless interpreter cannot be located."""

_FAILED_MESSAGE: Final[str] = "The task scheduler refused to {action} the AniShift Watch task"
"""Failure stated when ``schtasks`` leaves with a non-zero code."""


class AutostartStatus(StrEnum):
    """State of the logon task as the scheduler reports it."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    MISSING = "missing"


class AutostartError(FatalError):
    """Raised when the task scheduler refuses a create, delete or run request."""


class AutostartUnsupportedError(FatalError):
    """Raised when autostart is requested on a system without the Windows scheduler."""


def _default_run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run *command* to completion and capture its text output."""
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603 - fixed schtasks argv


def watch_command() -> list[str]:
    """Return the argv the logon task runs to watch the library without a window."""
    launcher: Path = Path(sys.executable).with_name(_PYTHONW_NAME)
    if not launcher.is_file():
        raise AutostartError(
            context=ErrorContext(
                code=ErrorCode.AUTOSTART_FAILED,
                message=_MISSING_PYTHONW,
                suggestion=_MISSING_PYTHONW_HINT,
            ),
        )
    return [str(launcher), "-m", _WATCH_MODULE, "watch"]


def enable(command: Sequence[str], *, run: Runner = _default_run) -> None:
    """Register the logon task running *command*, then start watching right away."""
    _require_windows()
    _schtasks(
        run,
        ["/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED", "/TN", TASK_NAME, "/TR", _task_argument(command)],
        "register",
    )
    _schtasks(run, ["/Run", "/TN", TASK_NAME], "start")
    logger.info("Logon task registered and started")


def disable(*, run: Runner = _default_run) -> None:
    """Remove the logon task, treating an already absent task as success."""
    _require_windows()
    completed: subprocess.CompletedProcess[str] = run([_SCHTASKS, "/Delete", "/F", "/TN", TASK_NAME])
    if completed.returncode == 0 or _reports_missing_task(completed):
        logger.info("Logon task removed", existed=completed.returncode == 0)
        return
    raise _failure(completed, "remove")


def status(*, run: Runner = _default_run) -> AutostartStatus:
    """Report whether the logon task is registered and switched on."""
    _require_windows()
    completed: subprocess.CompletedProcess[str] = run(
        [_SCHTASKS, "/Query", "/TN", TASK_NAME, "/FO", "CSV", "/NH"],
    )
    if completed.returncode != 0:
        return AutostartStatus.MISSING
    return _parsed_status(completed.stdout)


def _require_windows() -> None:
    """Refuse every scheduler request outside Windows before touching a process."""
    if is_windows():
        return
    raise AutostartUnsupportedError(
        context=ErrorContext(
            code=ErrorCode.AUTOSTART_UNSUPPORTED,
            message=_UNSUPPORTED_MESSAGE,
            suggestion=_UNSUPPORTED_HINT,
        ),
    )


def _schtasks(run: Runner, arguments: Sequence[str], action: str) -> None:
    """Run one ``schtasks`` request and raise when the scheduler refuses it."""
    completed: subprocess.CompletedProcess[str] = run([_SCHTASKS, *arguments])
    if completed.returncode == 0:
        return
    raise _failure(completed, action)


def _task_argument(command: Sequence[str]) -> str:
    """Join *command* into the single string ``/TR`` accepts, quoting spaced parts."""
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _reports_missing_task(completed: subprocess.CompletedProcess[str]) -> bool:
    """Whether the scheduler refused only because the task does not exist."""
    output: str = f"{completed.stderr or ''}\n{completed.stdout or ''}".casefold()
    return _MISSING_TASK_MARKER in output


def _parsed_status(output: str) -> AutostartStatus:
    """Read the status column of the headerless CSV row the scheduler printed."""
    for row in csv.reader(output.splitlines()):
        if len(row) <= _STATUS_COLUMN:
            continue
        if row[_STATUS_COLUMN].strip().casefold() == _DISABLED_STATUS:
            return AutostartStatus.DISABLED
        return AutostartStatus.ENABLED
    return AutostartStatus.MISSING


def _failure(completed: subprocess.CompletedProcess[str], action: str) -> AutostartError:
    """Build the error for a refused request, keeping only the first stderr line."""
    logger.warning("Task scheduler refused a request", action=action, exit_code=completed.returncode)
    return AutostartError(
        context=ErrorContext(
            code=ErrorCode.AUTOSTART_FAILED,
            message=_FAILED_MESSAGE.format(action=action),
            suggestion=_first_line(completed.stderr),
        ),
    )


def _first_line(text: str | None) -> str:
    """Return the first non-empty line of *text* as one plain sentence."""
    for line in (text or "").splitlines():
        stripped: str = line.strip()
        if stripped:
            return stripped
    return ""
