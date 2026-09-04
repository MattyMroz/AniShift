"""External binary resolution — locate mkvtoolnix and ffmpeg per OS."""

from __future__ import annotations

import shutil
import sys
from enum import StrEnum
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.utils.logger import get_logger

__all__ = [
    "TOOL_DIR",
    "Binary",
    "BinaryNotFoundError",
    "external_bin_root",
    "is_windows",
    "require_binary",
    "resolve_binary",
]


class Binary(StrEnum):
    """External executables the app depends on (stem, no extension)."""

    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"
    MKVEXTRACT = "mkvextract"
    MKVMERGE = "mkvmerge"


class BinaryNotFoundError(FatalError):
    """Raised when a required external binary cannot be located."""


# ── Constants ─────────────────────────────────────────────────────────────────

TOOL_DIR: Final[dict[Binary, str]] = {
    Binary.FFMPEG: "ffmpeg",
    Binary.FFPROBE: "ffmpeg",
    Binary.MKVEXTRACT: "mkvtoolnix",
    Binary.MKVMERGE: "mkvtoolnix",
}
"""Subdirectory of ``external/bin/`` that holds each binary."""

logger = get_logger(__name__)


# ── Resolution ────────────────────────────────────────────────────────────────


def is_windows() -> bool:
    """Return ``True`` when running on Windows."""
    return sys.platform == "win32"


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[2]


def external_bin_root() -> Path:
    """Return ``<repo>/external/bin`` (not guaranteed to exist)."""
    return _repo_root() / "external" / "bin"


def _exe_name(binary: Binary) -> str:
    """Return the filename for *binary* on the current OS."""
    return f"{binary.value}.exe" if is_windows() else binary.value


def resolve_binary(binary: Binary) -> Path | None:
    """Return the best non-empty file for *binary*, or ``None`` if unavailable."""
    bundled: Path = external_bin_root() / TOOL_DIR[binary] / _exe_name(binary)
    if _is_nonempty_file(bundled):
        logger.debug("External binary resolved", binary=binary.value, source="bundled")
        return bundled

    if not is_windows():
        found: str | None = shutil.which(binary.value)
        if found is not None and _is_nonempty_file(Path(found)):
            logger.debug("External binary resolved", binary=binary.value, source="path")
            return Path(found)

    logger.warning("External binary unavailable", binary=binary.value)
    return None


def _is_nonempty_file(path: Path) -> bool:
    """Treat missing, unreadable and empty executable candidates as unavailable."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def require_binary(binary: Binary) -> Path:
    """Return the path for *binary* or raise when it is missing."""
    path = resolve_binary(binary)
    if path is not None:
        return path

    suggestion = f"Run `anishift setup` to download {binary.value}"
    if not is_windows():
        suggestion += f", or add it under {external_bin_root() / TOOL_DIR[binary]}"
    raise BinaryNotFoundError(
        context=ErrorContext(
            code=ErrorCode.BINARY_NOT_FOUND,
            message=f"binary not found: {binary.value}",
            suggestion=suggestion,
            details={"binary": binary.value},
        ),
    )
