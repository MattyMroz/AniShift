"""Bound one Windows recycle operation in an owned, noninteractive helper process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
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
    """Distinguish native evidence from refusal and an interrupted operation with unknown effects."""

    outcome: Literal["recycled", "refused", "uncertain"]
    reason: str
    receipt: str | None = None


def recycle_file(path: Path, identity: tuple[int, int, int, int]) -> RecycleResult:
    """Recycle exactly one identified file; timeout or malformed evidence never authorizes a retry."""
    if not is_windows():
        return RecycleResult("refused", "recycle_unsupported")
    executable: object = getattr(sys, "_base_executable", None)
    if not isinstance(executable, str):
        return RecycleResult("refused", "recycle_unavailable")
    payload: str = json.dumps({"path": str(path), "identity": identity, "parent_pid": os.getpid()})
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
    try:
        output, _ = process.communicate(payload, timeout=RECYCLE_TIMEOUT_S)
    except (subprocess.TimeoutExpired, OSError, ValueError) as error:
        return _interrupt_helper(
            process, "recycle_timeout" if isinstance(error, subprocess.TimeoutExpired) else "recycle_interrupted"
        )
    finally:
        _close_pipes(process)
    if process.returncode != 0:
        return RecycleResult("uncertain", "recycle_interrupted")
    return _decode_result(output)


def _interrupt_helper(process: subprocess.Popen[str], reason: str) -> RecycleResult:
    try:
        process.kill()
    except OSError:
        logger.warning("Recycle helper termination could not be confirmed")
    try:
        process.communicate(timeout=RECYCLE_CLEANUP_TIMEOUT_S)
    except subprocess.TimeoutExpired, OSError, ValueError:
        reason = "recycle_cleanup_timeout"
    try:
        process.wait(timeout=RECYCLE_CLEANUP_TIMEOUT_S)
    except subprocess.TimeoutExpired, OSError:
        reason = "recycle_cleanup_timeout"
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


def _decode_result(output: str) -> RecycleResult:
    try:
        data: object = json.loads(output)
    except ValueError:
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if not isinstance(data, dict) or data.get("outcome") not in {"recycled", "refused", "uncertain"}:
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if not isinstance(data.get("reason"), str) or not isinstance(data.get("receipt"), str | type(None)):
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    if data["outcome"] == "recycled" and not data.get("receipt"):
        return RecycleResult("uncertain", "recycle_invalid_evidence")
    return RecycleResult(data["outcome"], data["reason"], data.get("receipt"))
