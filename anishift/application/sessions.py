"""Exclusive ownership and cleanup of one workflow run directory."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from secrets import token_hex
from types import TracebackType
from typing import Final, Literal

from anishift.errors import ErrorCode, ErrorContext, ExecutionError, RunConflictError
from anishift.utils.logger import get_logger

__all__ = ["RunSession"]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_OWNER_MARKER_NAME: Final[str] = ".anishift-owner"
"""Private marker proving that a run root still belongs to this session."""

_ACTIVE_ROOTS: Final[set[Path]] = set()
"""Normalized run roots currently claimed by this AniShift process."""

_ACTIVE_ROOTS_LOCK: Final[threading.Lock] = threading.Lock()
"""Process-local guard preventing reuse before the former owner exits."""


class RunSession:
    """Context manager owning one run root and its late-result generation gate."""

    __slots__ = (
        "_active",
        "_generation",
        "_lock",
        "_owner_token",
        "_registry_key",
        "_run_root",
    )

    def __init__(self, run_root: Path) -> None:
        """Store an explicit run directory that this session alone will create."""
        if run_root.name in {"", ".", ".."} or run_root.parent == run_root:
            msg = "Run root must identify one dedicated child directory"
            raise ValueError(msg)
        self._run_root: Path = run_root
        self._registry_key: Path = run_root.resolve(strict=False)
        self._owner_token: str = token_hex(32)
        self._generation: int = 1
        self._active: bool = False
        self._lock: threading.Lock = threading.Lock()

    def __enter__(self) -> RunSession:
        """Create the exclusively owned run root and open its generation gate."""
        if not _claim_root(self._registry_key):
            context: ErrorContext = ErrorContext(
                code=ErrorCode.IO_ERROR,
                message="Workflow run directory is already in use",
            )
            raise RunConflictError(context=context)
        with self._lock:
            if self._active or self._run_root.exists():
                _release_root(self._registry_key)
                context = ErrorContext(
                    code=ErrorCode.IO_ERROR,
                    message="Workflow run directory is already in use",
                )
                raise RunConflictError(context=context)
            try:
                self._run_root.parent.mkdir(parents=True, exist_ok=True)
                self._run_root.mkdir()
                self._owner_marker().write_text(self._owner_token, encoding="utf-8")
            except FileExistsError as error:
                _release_root(self._registry_key)
                context = ErrorContext(
                    code=ErrorCode.IO_ERROR,
                    message="Workflow run directory is already in use",
                )
                raise RunConflictError(context=context) from error
            except OSError:
                _release_root(self._registry_key)
                raise
            self._active = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Close the generation gate and remove every file owned by this run."""
        del exception_type, traceback
        with self._lock:
            self._active = False
            self._generation += 1
        try:
            self._cleanup(exception)
        finally:
            _release_root(self._registry_key)
        return False

    @property
    def generation(self) -> int:
        """Return the generation captured by work submitted in this session."""
        with self._lock:
            return self._generation

    @property
    def run_root(self) -> Path:
        """Return the exact directory exclusively owned by this session."""
        return self._run_root

    def group_temp(self, group_id: str) -> Path:
        """Create and return one group directory inside the active run root."""
        if not group_id.strip() or Path(group_id).name != group_id or group_id in {".", ".."}:
            msg = "Group temporary directory requires one safe group ID"
            raise ValueError(msg)
        with self._lock:
            if not self._active:
                msg = "Run session must be active before creating group temporary files"
                raise ExecutionError(msg)
            group_root: Path = self._run_root / group_id
            group_root.mkdir(exist_ok=True)
            return group_root

    def accepts_generation(self, generation: int) -> bool:
        """Allow commits only from the currently active run generation."""
        with self._lock:
            return self._active and generation == self._generation

    def commit_if_generation(self, generation: int, action: Callable[[], None]) -> bool:
        """Run one final commit atomically against closing this run generation."""
        with self._lock:
            if not self._active or generation != self._generation:
                return False
            action()
            return True

    def _owner_marker(self) -> Path:
        return self._run_root / _OWNER_MARKER_NAME

    def _owns_run_root(self) -> bool:
        try:
            return self._owner_marker().read_text(encoding="utf-8") == self._owner_token
        except OSError:
            return False

    def _cleanup(self, exception: BaseException | None) -> None:
        if self._run_root.exists() and not self._owns_run_root():
            if exception is not None:
                logger.warning("Workflow run ownership changed before cleanup")
                return
            context: ErrorContext = ErrorContext(
                code=ErrorCode.IO_ERROR,
                message="Workflow run ownership changed before cleanup",
                suggestion="Retry after the other AniShift run has finished.",
            )
            raise RunConflictError(context=context)
        try:
            shutil.rmtree(self._run_root)
        except FileNotFoundError:
            return
        except OSError as error:
            if exception is not None:
                logger.warning("Workflow run cleanup failed after another error")
                return
            context = ErrorContext(
                code=ErrorCode.IO_ERROR,
                message="Workflow run cleanup failed",
                suggestion="Close programs using temporary AniShift files and retry.",
            )
            raise ExecutionError(context=context) from error


def _claim_root(root: Path) -> bool:
    with _ACTIVE_ROOTS_LOCK:
        if root in _ACTIVE_ROOTS:
            return False
        _ACTIVE_ROOTS.add(root)
        return True


def _release_root(root: Path) -> None:
    with _ACTIVE_ROOTS_LOCK:
        _ACTIVE_ROOTS.discard(root)
