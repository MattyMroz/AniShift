"""Bound the Windows recycle and restore steps of one set operation in one owned, noninteractive helper process."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from anishift.platform.binaries import is_windows
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RECYCLE_TIMEOUT_S: Final[float] = 15.0
"""Maximum time a single native shell operation may occupy its private desktop."""

RECYCLE_CLEANUP_TIMEOUT_S: Final[float] = 1.0
"""Bound each post-kill pipe drain, process reap and best-effort stream close."""


@dataclass(frozen=True, slots=True)
class RecycleResult:
    """Report recycle/restore completion, read-only readiness, refusal or uncertain native effects."""

    outcome: Literal["recycled", "restored", "ready", "refused", "uncertain"]
    reason: str
    receipt: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreRequest:
    """Exact durable paths and file identity supplied only by the deletion owner."""

    workspace: Path
    path: str
    staging: str
    identity: tuple[int, int, int, int]
    receipt: str | None
    started: bool = False


type RecycleStep = Callable[[Path, tuple[int, int, int, int]], RecycleResult]
"""Recycle exactly one identified file of the open set operation."""

type RestoreStep = Callable[[RestoreRequest, bool], RecycleResult]
"""Inspect (True) or restore (False) one exact recorded item of the open set operation."""


@contextmanager
def recycle_session() -> Iterator[RecycleStep]:
    """Recycle the files of one set through one helper; timeout or malformed evidence never authorizes a retry."""
    helper: _Helper = _Helper()
    try:
        yield lambda path, identity: _recycled(helper.call({"path": str(path), "identity": identity}))
    finally:
        helper.close()


@contextmanager
def restore_session() -> Iterator[RestoreStep]:
    """Inspect and restore the recorded items of one set through one helper process."""
    helper: _Helper = _Helper()
    try:
        yield lambda request, check_only: helper.call(
            {
                "operation": "restore",
                "workspace": str(request.workspace),
                "path": request.path,
                "staging": request.staging,
                "identity": request.identity,
                "receipt": request.receipt,
                "started": request.started,
                "check_only": check_only,
            }
        )
    finally:
        helper.close()


def _recycled(result: RecycleResult) -> RecycleResult:
    if result.outcome in {"recycled", "refused", "uncertain"}:
        return result
    return RecycleResult("uncertain", "recycle_invalid_evidence")


class _Helper:
    """One helper started on the first request and answering one JSON line per request line, in order."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._answers: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._broken: bool = False

    def call(self, request: dict[str, object]) -> RecycleResult:
        """Send one request and wait for its answer; a lost, late or foreign answer ends the helper for good."""
        if self._broken:
            return RecycleResult("refused", "recycle_unavailable")
        process: subprocess.Popen[str] | RecycleResult = self._process or self._start()
        if isinstance(process, RecycleResult):
            self._broken = True
            return process
        if not self._send(process, request):
            return self._interrupt(process, "recycle_interrupted")
        return self._receive(process, request.get("path"))

    def _receive(self, process: subprocess.Popen[str], path: object) -> RecycleResult:
        try:
            answer: str | None = self._answers.get(timeout=RECYCLE_TIMEOUT_S)
        except queue.Empty:
            return self._interrupt(process, "recycle_timeout")
        if answer is None:
            return self._interrupt(process, "recycle_interrupted")
        result: RecycleResult = _decode_result(answer, path)
        if result.reason == "recycle_invalid_evidence":
            self._interrupt(process, result.reason)
        return result

    def close(self) -> None:
        """End the helper after its last answer, killing it only when it does not exit in time."""
        process: subprocess.Popen[str] | None = self._process
        if process is None or self._broken:
            return
        self._broken = True
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=RECYCLE_CLEANUP_TIMEOUT_S)
        except subprocess.TimeoutExpired, OSError, ValueError:
            self._interrupt(process, "recycle_cleanup_timeout")
            return
        _close_pipes(process)

    def _start(self) -> subprocess.Popen[str] | RecycleResult:
        if not is_windows():
            return RecycleResult("refused", "recycle_unsupported")
        executable: object = getattr(sys, "_base_executable", None)
        if not isinstance(executable, str):
            return RecycleResult("refused", "recycle_unavailable")
        try:
            process: subprocess.Popen[str] = subprocess.Popen(  # noqa: S603
                [executable, "-m", "anishift.platform.recycle_worker"],
                env={**os.environ, "__PYVENV_LAUNCHER__": sys.executable},
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            return RecycleResult("refused", "recycle_unavailable")
        self._process = process
        self._reader = threading.Thread(target=self._read, args=(process,), daemon=True, name="recycle-answers")
        self._reader.start()
        return process

    @staticmethod
    def _send(process: subprocess.Popen[str], request: dict[str, object]) -> bool:
        if process.stdin is None:
            return False
        try:
            process.stdin.write(json.dumps({**request, "parent_pid": os.getpid()}) + "\n")
            process.stdin.flush()
        except OSError, ValueError:
            return False
        return True

    def _read(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self._answers.put(line)
        except OSError, ValueError:
            logger.warning("Recycle helper answers could not be read")
        finally:
            self._answers.put(None)

    def _interrupt(self, process: subprocess.Popen[str], reason: str) -> RecycleResult:
        self._broken = True
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            logger.warning("Recycle helper termination could not be confirmed")
        try:
            process.wait(timeout=RECYCLE_CLEANUP_TIMEOUT_S)
        except subprocess.TimeoutExpired, OSError:
            reason = "recycle_cleanup_timeout"
        if self._reader is not None:
            self._reader.join(RECYCLE_CLEANUP_TIMEOUT_S)
            if self._reader.is_alive():
                reason = "recycle_cleanup_timeout"
        _close_pipes(process)
        logger.warning("Recycle helper interrupted; file effects remain uncertain", reason=reason)
        return RecycleResult("uncertain", reason)


def _close_pipes(process: subprocess.Popen[str]) -> None:
    def close() -> None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError, ValueError:
                    logger.warning("Recycle helper pipe could not be closed")

    cleanup: threading.Thread = threading.Thread(target=close, daemon=True, name="recycle-pipe-cleanup")
    cleanup.start()
    cleanup.join(RECYCLE_CLEANUP_TIMEOUT_S)
    if cleanup.is_alive():
        logger.warning("Recycle helper pipe close remains pending after its deadline")


def _decode_result(output: str, path: object) -> RecycleResult:
    try:
        data: object = json.loads(output)
    except ValueError:
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if (
        not isinstance(data, dict)
        or data.get("path") != path
        or data.get("outcome")
        not in {
            "recycled",
            "restored",
            "ready",
            "refused",
            "uncertain",
        }
    ):
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if not isinstance(data.get("reason"), str) or not isinstance(data.get("receipt"), str | type(None)):
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if data["outcome"] == "recycled" and not data.get("receipt"):
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    return RecycleResult(data["outcome"], data["reason"], data.get("receipt"))
