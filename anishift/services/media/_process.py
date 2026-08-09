"""Internal bounded subprocess runner shared by media and extraction adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Final, Protocol

from anishift.application.cancellation import CancellationToken

_POLL_SECONDS: Final[float] = 0.1
"""Maximum delay between timeout and cancellation checks."""

_SHUTDOWN_GRACE_SECONDS: Final[float] = 5.0
"""Grace period before a stuck child process is killed."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows process flag preventing console Ctrl+C from leaking into children."""


class ProcessFailureReason(StrEnum):
    """Machine-readable reason a controlled subprocess did not succeed."""

    START_FAILED = "start_failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    NONZERO_EXIT = "nonzero_exit"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Captured streams from one successful subprocess."""

    stdout: str
    stderr: str
    returncode: int


class ProcessExecutionError(Exception):
    """Internal process failure mapped to a domain error by each adapter."""

    def __init__(
        self,
        reason: ProcessFailureReason,
        *,
        returncode: int | None = None,
        cause: OSError | None = None,
    ) -> None:
        super().__init__(reason.value)
        self.reason: ProcessFailureReason = reason
        self.returncode: int | None = returncode
        self.cause: OSError | None = cause


class ProcessRunner(Protocol):
    """Execution boundary for bounded argument-list subprocesses."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        """Run one process or raise a typed internal failure."""
        ...


class SubprocessRunner:
    """Run a process without a shell and stop it on timeout or cancellation."""

    def run(
        self,
        command: tuple[str, ...],
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> ProcessResult:
        """Run one process while polling a cooperative cancellation token."""
        if timeout_s <= 0:
            msg = "Process timeout must be positive"
            raise ValueError(msg)
        cancel.raise_if_cancelled()
        try:
            process: subprocess.Popen[str] = subprocess.Popen(  # noqa: S603
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_NEW_PROCESS_GROUP,
            )
        except OSError as error:
            raise ProcessExecutionError(ProcessFailureReason.START_FAILED, cause=error) from error

        deadline: float = monotonic() + timeout_s
        while True:
            if cancel.is_cancelled():
                self._stop(process)
                raise ProcessExecutionError(ProcessFailureReason.CANCELLED)
            remaining_s: float = deadline - monotonic()
            if remaining_s <= 0:
                self._stop(process)
                raise ProcessExecutionError(ProcessFailureReason.TIMED_OUT)
            try:
                stdout, stderr = process.communicate(timeout=min(_POLL_SECONDS, remaining_s))
                break
            except subprocess.TimeoutExpired:
                continue

        if process.returncode != 0:
            raise ProcessExecutionError(
                ProcessFailureReason.NONZERO_EXIT,
                returncode=process.returncode,
            )
        return ProcessResult(stdout=stdout, stderr=stderr, returncode=process.returncode)

    def _stop(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.communicate(timeout=_SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.communicate(timeout=_SHUTDOWN_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                return
