"""Workspace resolution, runtime paths, and orphaned-run cleanup.

The workspace is where the user drops media and receives durable products.
Its only managed subdirectory is ``temp/``. No ``input/``, ``output/``,
``cache/``, ``logs/`` or ``settings.json`` live here.

Public API:
    ENV_WORKSPACE_ROOT: Env var name for an explicit override.
    DEFAULT_SUBDIRS: Subdirectories created by ``ensure_workspace_dir``.
    resolve_workspace_root: Locate the active workspace root.
    ensure_workspace_dir: Create the root and its default subdirectories.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
from collections.abc import Collection
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.utils.logger import get_logger
from anishift.utils.safe_fs import safe_rmtree

__all__ = [
    "DEFAULT_SUBDIRS",
    "ENV_WORKSPACE_ROOT",
    "RUN_OWNER_MARKER_NAME",
    "WorkspaceRootNotResolvedError",
    "cleanup_orphaned_temp",
    "ensure_workspace_dir",
    "group_temp_dir",
    "resolve_workspace_root",
    "run_temp_dir",
]

# ── Constants ────────────────────────────────────────────────────────────────

ENV_WORKSPACE_ROOT: Final[str] = "ANISHIFT_WORKSPACE_ROOT"
"""Env var consulted before falling back to repo-root inference."""

_WORKSPACE_DIR_NAME: Final[str] = "workspace"
"""Name of the workspace directory under the repo root."""

_REPO_MARKER: Final[str] = "pyproject.toml"
"""File whose presence identifies the repository root."""

DEFAULT_SUBDIRS: Final[tuple[str, ...]] = ("temp",)
"""Subdirectories materialised by :func:`ensure_workspace_dir`."""

RUN_OWNER_MARKER_NAME: Final[str] = ".anishift-owner"
"""Marker carrying the PID and run identity of one active owner."""

_SAFE_RUNTIME_ID: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
"""Allowed generated run and group identifiers in the temporary tree."""

_PROCESS_QUERY_LIMITED_INFORMATION: Final[int] = 0x1000
"""Windows process access needed only to query whether an owner is alive."""

_ERROR_ACCESS_DENIED: Final[int] = 5
"""Windows error returned when a live process cannot be opened for querying."""

_STILL_ACTIVE: Final[int] = 259
"""Windows process exit code indicating that the process has not exited."""

logger = get_logger(__name__)


class WorkspaceRootNotResolvedError(FatalError):
    """Raised when the workspace root cannot be resolved."""


def _read_env_override() -> Path | None:
    """Return the env-provided workspace root if set and non-blank."""
    raw = os.environ.get(ENV_WORKSPACE_ROOT)
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return Path(stripped).expanduser().resolve()


def _infer_repo_workspace() -> Path:
    """Return ``<repo>/workspace`` when running from a checkout, else fail-fast."""
    candidate = Path(__file__).resolve().parents[2]
    if not (candidate / _REPO_MARKER).is_file():
        raise WorkspaceRootNotResolvedError(
            context=ErrorContext(
                code=ErrorCode.WORKSPACE_NOT_RESOLVED,
                message=f"{ENV_WORKSPACE_ROOT} not set and no {_REPO_MARKER} at {candidate}",
                suggestion=f"Set {ENV_WORKSPACE_ROOT} or run from a repo checkout",
            ),
        )
    return (candidate / _WORKSPACE_DIR_NAME).resolve()


def resolve_workspace_root(*, override: str | Path | None = None) -> Path:
    """Resolve the workspace root (env override or ``<repo>/workspace``).

    Precedence: ``ANISHIFT_WORKSPACE_ROOT`` env var, otherwise
    ``<repo_root>/workspace`` inferred from this module's location.

    Returns:
        Absolute path to the workspace root (NOT created on disk).

    Raises:
        WorkspaceRootNotResolvedError: When the env var is unset and the
            module is not running from a repo checkout.
    """
    if override is not None and str(override).strip():
        resolved = Path(override).expanduser().resolve()
        logger.debug("Workspace root resolved", source="settings", workspace_name=resolved.name)
        return resolved
    env_override: Path | None = _read_env_override()
    if env_override is not None:
        logger.debug("Workspace root resolved", source="environment", workspace_name=env_override.name)
        return env_override
    inferred = _infer_repo_workspace()
    logger.debug("Workspace root resolved", source="repository", workspace_name=inferred.name)
    return inferred


def ensure_workspace_dir(root: Path) -> None:
    """Create ``root`` and every entry in :data:`DEFAULT_SUBDIRS`.

    Idempotent. Raises :class:`NotADirectoryError` if ``root`` exists as a
    non-directory file (a path collision the user must resolve manually).
    """
    if root.exists() and not root.is_dir():
        msg = f"workspace root exists but is not a directory: {root}"
        raise NotADirectoryError(msg)
    root.mkdir(parents=True, exist_ok=True)
    for sub in DEFAULT_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    logger.debug("Workspace directories ready", workspace_name=root.name, subdirectories=DEFAULT_SUBDIRS)


def run_temp_dir(root: Path, run_id: str) -> Path:
    """Return the exact private directory for one validated run ID."""
    _validate_runtime_id(run_id, "run")
    return root / "temp" / run_id


def group_temp_dir(root: Path, run_id: str, group_id: str) -> Path:
    """Return one validated group directory inside a run-owned scope."""
    _validate_runtime_id(group_id, "group")
    return run_temp_dir(root, run_id) / group_id


def cleanup_orphaned_temp(root: Path, *, active_run_ids: Collection[str]) -> tuple[Path, ...]:
    """Remove direct inactive run directories while preserving every live owner."""
    active: frozenset[str] = frozenset(active_run_ids)
    for run_id in active:
        _validate_runtime_id(run_id, "active run")
    temp_root: Path = root / "temp"
    if not temp_root.exists():
        return ()
    if not temp_root.is_dir():
        raise NotADirectoryError(temp_root)
    removed: list[Path] = []
    for candidate in temp_root.iterdir():
        owner_pid: int | None = _owner_pid(candidate)
        if (
            candidate.name in active
            or _SAFE_RUNTIME_ID.fullmatch(candidate.name) is None
            or candidate.is_symlink()
            or not candidate.is_dir()
            or owner_pid is None
            or _process_is_running(owner_pid)
        ):
            continue
        if candidate.resolve(strict=False).parent != temp_root.resolve(strict=False):
            continue
        try:
            safe_rmtree(candidate)
        except FileNotFoundError:
            continue
        removed.append(candidate)
    return tuple(removed)


def _validate_runtime_id(value: str, label: str) -> None:
    if _SAFE_RUNTIME_ID.fullmatch(value) is None:
        msg = f"Workspace {label} ID must be one safe path component"
        raise ValueError(msg)


def _owner_pid(run_root: Path) -> int | None:
    try:
        payload: object = json.loads((run_root / RUN_OWNER_MARKER_NAME).read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("run_id") != run_root.name:
        return None
    pid: object = payload.get("pid")
    if type(pid) is not int or pid <= 0:
        return None
    return pid


def _process_is_running(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    kernel32: ctypes.WinDLL = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        exit_code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))) and exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(process)
