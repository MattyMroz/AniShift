"""Safe filesystem operations — retry-on-lock for Windows.

Windows antivirus scanners, filesystem indexers and readers without delete
sharing can hold file locks briefly, causing ``PermissionError`` on
``shutil.rmtree`` / ``shutil.move`` / ``Path.replace``.  These wrappers add
exponential backoff retries to handle transient locks.

Usage:
    >>> from <pkg>.utils.safe_fs import safe_rmtree, safe_move, safe_replace
    >>> safe_rmtree("workspace/tmp")
    >>> safe_move("old/dir", "new/dir")
    >>> safe_replace("state.json.tmp", "state.json")
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

from .logger import get_logger

logger = get_logger(__name__)

__all__ = ["safe_move", "safe_replace", "safe_rmtree"]

_MAX_RETRIES: Final[int] = 3
"""Maximum retry attempts for transient filesystem lock errors."""

_BASE_DELAY_S: Final[float] = 0.5
"""Initial backoff delay in seconds (doubles each retry: 0.5 → 1.0 → 2.0)."""

_REPLACE_RETRIES: Final[int] = 5
"""Retry attempts for an atomic replace, which callers wait on synchronously."""

_REPLACE_BASE_DELAY_S: Final[float] = 0.05
"""Initial replace backoff in seconds (0.05 → 0.8, about 1.5 s in total)."""


def safe_rmtree(path: str | Path, *, retries: int = _MAX_RETRIES) -> None:
    """Remove directory tree with retry on ``PermissionError``.

    Args:
        path: Directory to remove.
        retries: Max retry attempts (exponential backoff).

    Raises:
        PermissionError: If removal fails after all retries.
        FileNotFoundError: If *path* does not exist.
    """
    path = Path(path)
    _retry_on_lock(lambda: shutil.rmtree(path), f"removing {path.name}", retries, _BASE_DELAY_S)


def safe_move(src: str | Path, dst: str | Path, *, retries: int = _MAX_RETRIES) -> Path:
    """Move file/directory with retry on ``PermissionError``.

    Args:
        src: Source path.
        dst: Destination path.
        retries: Max retry attempts (exponential backoff).

    Returns:
        Destination path.

    Raises:
        PermissionError: If move fails after all retries.
        FileNotFoundError: If *src* does not exist.
    """
    src, dst = Path(src), Path(dst)
    _retry_on_lock(lambda: shutil.move(str(src), str(dst)), f"moving {src.name} → {dst.name}", retries, _BASE_DELAY_S)
    return dst


def safe_replace(src: str | Path, dst: str | Path, *, retries: int = _REPLACE_RETRIES) -> Path:
    """Atomically replace *dst* with *src*, retrying a briefly locked destination on ``PermissionError``."""
    src, dst = Path(src), Path(dst)
    _retry_on_lock(lambda: src.replace(dst), f"replacing {dst.name}", retries, _REPLACE_BASE_DELAY_S)
    return dst


def _retry_on_lock(action: Callable[[], object], label: str, retries: int, base_delay_s: float) -> None:
    for attempt in range(retries + 1):
        try:
            action()
        except PermissionError:
            if attempt == retries:
                raise
            delay: float = base_delay_s * (2**attempt)
            logger.debug(
                "PermissionError {label}, retrying in {delay:.2f}s ({attempt}/{retries})",
                label=label,
                delay=delay,
                attempt=attempt + 1,
                retries=retries,
            )
            time.sleep(delay)
        else:
            return
