"""Windows logon task that starts the AniShift watch, managed through ``schtasks``."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final
from xml.etree import ElementTree
from xml.sax.saxutils import escape

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
    "register",
    "resident_command",
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

_TASK_NAMESPACE: Final[str] = "http://schemas.microsoft.com/windows/2004/02/mit/task"
"""XML namespace of every task definition the scheduler imports and exports."""

_TASK_XML: Final[str] = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{namespace}">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Enabled>{enabled}</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""
"""Task definition a standard user may register: own logon, own account, least privilege."""

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
    """Run *command* to completion, decoding its console-code-page output leniently."""
    return subprocess.run(  # noqa: S603 - fixed schtasks argv
        command,
        capture_output=True,
        text=True,
        encoding="oem",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


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


def resident_command() -> list[str]:
    """Return the argv starting the resident without a window."""
    return [*watch_command(), "resident"]


def register(command: Sequence[str], *, run: Runner = _default_run) -> None:
    """Register the logon task running *command* for this user without starting the watch now."""
    _register(command, enabled=True, run=run)


def _register(command: Sequence[str], *, enabled: bool, run: Runner) -> None:
    _require_windows()
    definition: Path = _write_definition(command, enabled=enabled)
    try:
        _schtasks(run, ["/Create", "/F", "/XML", str(definition), "/TN", TASK_NAME], "register")
    finally:
        definition.unlink(missing_ok=True)
    logger.info("Logon task registered", enabled=enabled, started=False)


def enable(command: Sequence[str], *, run: Runner = _default_run) -> None:
    """Register the logon task running *command* for this user, then start watching right away."""
    register(command, run=run)
    _schtasks(run, ["/Run", "/TN", TASK_NAME], "start")
    logger.info("Logon task registered and started")


def disable(*, run: Runner = _default_run) -> None:
    """Switch the logon task off, keeping the choice visible to every later start."""
    _require_windows()
    completed: subprocess.CompletedProcess[str] = run([_SCHTASKS, "/Change", "/TN", TASK_NAME, "/DISABLE"])
    if completed.returncode == 0:
        logger.info("Logon task switched off", existed=True)
        return
    if _query(run).returncode != 0:
        _register(watch_command(), enabled=False, run=run)
        logger.info("Logon task switched off", existed=False)
        return
    raise _failure(completed, "disable")


def status(*, run: Runner = _default_run) -> AutostartStatus:
    """Report whether the logon task is registered and switched on."""
    _require_windows()
    completed: subprocess.CompletedProcess[str] = _query(run)
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


def _query(run: Runner) -> subprocess.CompletedProcess[str]:
    """Export the task definition, which names its state independently of the display language."""
    return run([_SCHTASKS, "/Query", "/TN", TASK_NAME, "/XML"])


def _schtasks(run: Runner, arguments: Sequence[str], action: str) -> None:
    """Run one ``schtasks`` request and raise when the scheduler refuses it."""
    completed: subprocess.CompletedProcess[str] = run([_SCHTASKS, *arguments])
    if completed.returncode == 0:
        return
    raise _failure(completed, action)


def _write_definition(command: Sequence[str], *, enabled: bool) -> Path:
    """Write the task definition for *command* to a temporary UTF-16 file the scheduler imports."""
    user: str = f"{os.environ.get('USERDOMAIN', '.')}\\{getpass.getuser()}"
    text: str = _TASK_XML.format(
        namespace=_TASK_NAMESPACE,
        enabled="true" if enabled else "false",
        user=escape(user),
        command=escape(command[0]),
        arguments=escape(_arguments(command[1:])),
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-16", suffix=".xml", delete=False) as handle:
        handle.write(text)
        return Path(handle.name)


def _arguments(parts: Sequence[str]) -> str:
    """Join the arguments after the command into one line, quoting parts that hold a space."""
    return " ".join(f'"{part}"' if " " in part else part for part in parts)


def _parsed_status(definition: str) -> AutostartStatus:
    """Read the ``Settings/Enabled`` flag of an exported task definition."""
    try:
        root: ElementTree.Element = ElementTree.fromstring(definition.strip())  # noqa: S314 - local scheduler export
    except ElementTree.ParseError:
        return AutostartStatus.MISSING
    enabled: ElementTree.Element | None = root.find(f"{{{_TASK_NAMESPACE}}}Settings/{{{_TASK_NAMESPACE}}}Enabled")
    if enabled is not None and (enabled.text or "").strip().casefold() == "false":
        return AutostartStatus.DISABLED
    return AutostartStatus.ENABLED


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
