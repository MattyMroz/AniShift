"""Workspace root resolution + directory bootstrap.

The workspace is where the user drops MKV files; intermediate files (.srt,
.eac3, ...) are written next to them. Only two subdirectories exist:
``tmp/`` (pipeline scratch, elevenbytes resume state) and ``output/`` (final
results, used only when enabled in /settings). No ``input/``, ``cache/``,
``logs/`` or ``settings.json`` live here.

Public API:
    ENV_WORKSPACE_ROOT: Env var name for an explicit override.
    DEFAULT_SUBDIRS: Subdirectories created by ``ensure_workspace_dir``.
    resolve_workspace_root: Locate the active workspace root.
    ensure_workspace_dir: Create the root and its default subdirectories.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext, FatalError

__all__ = [
    "DEFAULT_SUBDIRS",
    "ENV_WORKSPACE_ROOT",
    "WorkspaceRootNotResolvedError",
    "ensure_workspace_dir",
    "resolve_workspace_root",
]

ENV_WORKSPACE_ROOT: Final[str] = "ANISHIFT_WORKSPACE_ROOT"
"""Env var consulted before falling back to repo-root inference."""

_WORKSPACE_DIR_NAME: Final[str] = "workspace"
"""Name of the workspace directory under the repo root."""

_REPO_MARKER: Final[str] = "pyproject.toml"
"""File whose presence identifies the repository root."""

DEFAULT_SUBDIRS: Final[tuple[str, ...]] = (
    "tmp",
    "output",
)
"""Subdirectories materialised by :func:`ensure_workspace_dir`."""


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


def resolve_workspace_root() -> Path:
    """Resolve the workspace root (env override or ``<repo>/workspace``).

    Precedence: ``ANISHIFT_WORKSPACE_ROOT`` env var, otherwise
    ``<repo_root>/workspace`` inferred from this module's location.

    Returns:
        Absolute path to the workspace root (NOT created on disk).

    Raises:
        WorkspaceRootNotResolvedError: When the env var is unset and the
            module is not running from a repo checkout.
    """
    override = _read_env_override()
    if override is not None:
        return override
    return _infer_repo_workspace()


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
