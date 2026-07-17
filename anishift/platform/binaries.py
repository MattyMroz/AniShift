"""External binary resolution — locate mkvtoolnix / ffmpeg / balcon per OS.

Binaries live under ``external/bin/<tool>/`` (gitignored). Resolution order:

1. ``external/bin/<tool>/<exe>`` inside the repo checkout.
2. On non-Windows, fall back to the same executable on ``PATH`` (mkvtoolnix
   and ffmpeg ship in every Linux distro; balcon is Windows-only).

``is_windows()`` gates the Windows-only ``balcon`` binary so callers never
branch on the OS themselves.

Public API:
    Binary: Enum of the binaries the app needs.
    TOOL_DIR: Subdirectory holding each binary.
    is_windows: Whether the current OS is Windows.
    external_bin_root: Root of the bundled-binary tree.
    resolve_binary: Best-effort path to a binary (repo, then PATH).
    require_binary: Like ``resolve_binary`` but raises when missing.
"""

from __future__ import annotations

import shutil
import sys
from enum import StrEnum
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext, FatalError

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

    BALCON = "balcon"
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"
    MKVEXTRACT = "mkvextract"
    MKVMERGE = "mkvmerge"


class BinaryNotFoundError(FatalError):
    """Raised when a required external binary cannot be located."""


# ── Constants ─────────────────────────────────────────────────────────────────

TOOL_DIR: Final[dict[Binary, str]] = {
    Binary.BALCON: "balabolka",
    Binary.FFMPEG: "ffmpeg",
    Binary.FFPROBE: "ffmpeg",
    Binary.MKVEXTRACT: "mkvtoolnix",
    Binary.MKVMERGE: "mkvtoolnix",
}
"""Subdirectory of ``external/bin/`` that holds each binary."""

_WINDOWS_ONLY: Final[frozenset[Binary]] = frozenset({Binary.BALCON})
"""Binaries that only exist on Windows."""


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
    """Return the best path for *binary*, or ``None`` if unavailable.

    Looks in ``external/bin/<tool>/`` first, then falls back to ``PATH`` on
    non-Windows systems. Windows-only binaries always return ``None`` off
    Windows.

    Args:
        binary: The executable to locate.

    Returns:
        Absolute path to the executable, or ``None`` when it cannot be found.
    """
    if binary in _WINDOWS_ONLY and not is_windows():
        return None

    bundled = external_bin_root() / TOOL_DIR[binary] / _exe_name(binary)
    if bundled.is_file():
        return bundled

    if not is_windows():
        found = shutil.which(binary.value)
        if found is not None:
            return Path(found)

    return None


def require_binary(binary: Binary) -> Path:
    """Return the path for *binary* or raise when it is missing.

    Args:
        binary: The executable to locate.

    Returns:
        Absolute path to the executable.

    Raises:
        BinaryNotFoundError: When the binary cannot be resolved.
    """
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
