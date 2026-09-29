"""Validate isolated acquisition paths without creating processing run sessions."""

from __future__ import annotations

import ntpath
from pathlib import Path, PurePosixPath, PureWindowsPath

from anishift.paths import TEMP_DIRECTORY


def torrent_relative_path(value: str) -> PurePosixPath:
    """Require a plain relative torrent path safe on Windows, including device and ADS rules."""
    normalized: str = value.replace("\\", "/")
    windows: PureWindowsPath = PureWindowsPath(value)
    parts: list[str] = normalized.split("/")
    if windows.drive or windows.root or any(part in {"", ".", ".."} or ntpath.isreserved(part) for part in parts):
        msg = "A torrent path must be a safe relative Windows path"
        raise ValueError(msg)
    return PurePosixPath(normalized)


def staging_path(workspace_root: Path, operation_id: str) -> Path:
    """Locate one operation's isolated data directory and reject linked ancestors."""
    relative: PurePosixPath = torrent_relative_path(operation_id)
    if len(relative.parts) != 1:
        msg = "An acquisition operation requires one directory component"
        raise ValueError(msg)
    return staged_file(workspace_root.absolute(), f"{TEMP_DIRECTORY}/.acquisition/{operation_id}/data")


def staged_file(directory: Path, relative: str) -> Path:
    """Resolve one validated torrent path below a link-free staging directory."""
    root: Path = directory.absolute()
    path: Path = root.joinpath(*torrent_relative_path(relative).parts)
    ancestors: tuple[Path, ...] = (path, *(parent for parent in path.parents if parent.is_relative_to(root)))
    if any(parent.is_symlink() or parent.is_junction() for parent in ancestors):
        msg = "An acquisition path cannot contain a symlink or junction"
        raise ValueError(msg)
    if not path.resolve().is_relative_to(directory.resolve()):
        msg = "An acquisition path must remain inside its staging directory"
        raise ValueError(msg)
    return path
