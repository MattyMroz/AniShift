"""Validate isolated acquisition paths, publish proven episode copies and clean an operation's own staging."""

from __future__ import annotations

import hashlib
import ntpath
import os
import stat
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Final

from anishift.application.ready import retry_file_release
from anishift.paths import TEMP_DIRECTORY

if TYPE_CHECKING:
    from _hashlib import HASH
    from collections.abc import Sequence

    from anishift.application.control import FileStamp, PublishedFile

# ── Constants ─────────────────────────────────────────────────────────────────

INCOMPLETE_SUFFIX: Final[str] = ".!qB"
"""Ending the private client gives a file it has not finished writing."""

_CHUNK_BYTES: Final[int] = 1 << 20
"""Bytes read at once while one staged file is copied and hashed."""

_CHANGED_WHILE_COPIED: Final[str] = "A staged file changed while it was copied"
"""Reason a copy is discarded when its source or its bytes no longer match the declared file."""

_NOT_A_FILE: Final[str] = "A staged name holds something other than a regular file"
"""Reason cleanup stops instead of removing an unexpected object from its own staging."""


@dataclass(frozen=True, slots=True)
class SetPublication:
    """Indexes whose private copy is lost or whose reserved name another object holds."""

    lost: tuple[int, ...] = ()
    occupied: tuple[int, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether every file of the set now holds its proven copy under its reserved name."""
        return not self.lost and not self.occupied


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
    return _operation_path(workspace_root, operation_id, "data")


def publication_path(workspace_root: Path, operation_id: str) -> Path:
    """Locate the private directory where one operation keeps verified copies before they are published."""
    return _operation_path(workspace_root, operation_id, "publish")


def staged_file(directory: Path, relative: str) -> Path:
    """Resolve one validated torrent path below a link-free staging directory."""
    root: Path = lexical_path(directory)
    path: Path = root.joinpath(*torrent_relative_path(relative).parts)
    ancestors: tuple[Path, ...] = (path, *(parent for parent in path.parents if parent.is_relative_to(root)))
    if any(parent.is_symlink() or parent.is_junction() for parent in ancestors):
        msg = "An acquisition path cannot contain a symlink or junction"
        raise ValueError(msg)
    return path


def lexical_path(path: str | Path) -> Path:
    """Normalize an absolute path without filesystem reads or Windows extended-path prefixes."""
    value: str = os.fspath(path)
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(os.path.normpath(Path(value).absolute()))


def file_stamp(path: Path) -> FileStamp | None:
    """Return the size, modification time, device and inode of one regular file, or ``None`` for anything else."""
    try:
        status: os.stat_result = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    return status.st_size, status.st_mtime_ns, status.st_dev, status.st_ino


def copy_staged(source: Path, destination: Path, size: int) -> tuple[str, FileStamp]:
    """Copy one finished staged file into private storage, returning its content digest and the copy's stamp."""
    before: FileStamp | None = file_stamp(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy: Path = staged_file(destination.parent, destination.name)
    copy.unlink(missing_ok=True)
    digest: HASH = hashlib.sha256()
    try:
        with source.open("rb") as reader, copy.open("xb") as writer:
            while chunk := reader.read(_CHUNK_BYTES):
                digest.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    except OSError:
        copy.unlink(missing_ok=True)
        raise
    copied: FileStamp | None = file_stamp(copy)
    if before is None or before[0] != size or file_stamp(source) != before or copied is None or copied[0] != size:
        copy.unlink(missing_ok=True)
        raise OSError(_CHANGED_WHILE_COPIED)
    return digest.hexdigest(), copied


def published_copy(path: Path, item: PublishedFile) -> bool:
    """Verify the recorded file object and content before deleting its staged original."""
    if item.stamp is None or file_stamp(path) != item.stamp:
        return False
    try:
        with path.open("rb") as reader:
            digest: str = hashlib.file_digest(reader, "sha256").hexdigest()
        return digest == item.digest and file_stamp(path) == item.stamp
    except OSError:
        return False


def publish_set(workspace_root: Path, private: Path, files: Sequence[PublishedFile]) -> SetPublication:
    """Link every proven copy under its reserved flat name, never replacing an object that already holds one."""
    published: list[int] = []
    lost: list[int] = []
    occupied: list[int] = []
    pending: list[PublishedFile] = []
    for item in files:
        destination: Path = workspace_root / item.name
        if item.stamp is not None and file_stamp(destination) == item.stamp:
            published.append(item.index)
        elif _present(destination):
            occupied.append(item.index)
        elif item.stamp is None or file_stamp(staged_file(private, str(item.index))) != item.stamp:
            lost.append(item.index)
        else:
            pending.append(item)
    if lost or occupied:
        return _publication_conflict(workspace_root, private, files, published, lost, occupied)
    for item in pending:
        destination = workspace_root / item.name
        try:
            os.link(staged_file(private, str(item.index)), destination)
        except FileExistsError:
            if file_stamp(destination) != item.stamp:
                return _publication_conflict(workspace_root, private, files, published, [], [item.index])
        published.append(item.index)
    return SetPublication()


def _publication_conflict(  # noqa: PLR0913 - one publication outcome and its filesystem boundary
    root: Path,
    private: Path,
    files: Sequence[PublishedFile],
    published: Sequence[int],
    lost: Sequence[int],
    occupied: Sequence[int],
) -> SetPublication:
    if not occupied:
        return SetPublication(lost=tuple(lost))
    for item in files:
        if item.index not in published:
            continue
        destination: Path = root / item.name
        copy: Path = staged_file(private, str(item.index))
        if file_stamp(copy) != item.stamp or file_stamp(destination) != item.stamp:
            raise OSError(_CHANGED_WHILE_COPIED)
        destination.unlink()
    return SetPublication(tuple(lost), tuple(occupied))


def clean_staging(  # noqa: PLR0913 - every protected fact stays an explicit call-site value
    workspace_root: Path,
    operation_id: str,
    info_hash: str,
    manifest: Sequence[str],
    kept: frozenset[str],
    exported: frozenset[int],
) -> bool:
    """Remove disposable staged files and report whether the operation directory is gone."""
    data: Path = staging_path(workspace_root, operation_id)
    private: Path = publication_path(workspace_root, operation_id)
    names: tuple[str, ...] = (
        *(name for path in manifest if path not in kept for name in (path, f"{path}{INCOMPLETE_SUFFIX}")),
        f".{info_hash}.parts",
    )
    for name in names:
        _remove_file(staged_file(data, name))
    for index in sorted(exported):
        _remove_file(staged_file(private, str(index)))
    folders: set[Path] = {
        parent
        for path in manifest
        for parent in staged_file(data, path).parents
        if parent.is_relative_to(data) and parent != data
    }
    for folder in (*sorted(folders, key=lambda item: len(item.parts), reverse=True), private, data, data.parent):
        _remove_empty(folder)
    return not _present(data.parent)


def _operation_path(workspace_root: Path, operation_id: str, part: str) -> Path:
    relative: PurePosixPath = torrent_relative_path(operation_id)
    if len(relative.parts) != 1:
        msg = "An acquisition operation requires one directory component"
        raise ValueError(msg)
    return staged_file(workspace_root.absolute(), f"{TEMP_DIRECTORY}/.acquisition/{operation_id}/{part}")


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _remove_file(path: Path) -> None:
    try:
        status: os.stat_result = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(status.st_mode):
        raise OSError(_NOT_A_FILE)
    retry_file_release(partial(path.unlink, missing_ok=True))


def _remove_empty(folder: Path) -> None:
    if folder.is_symlink() or folder.is_junction():
        raise OSError(_NOT_A_FILE)
    try:
        retry_file_release(folder.rmdir)
    except FileNotFoundError:
        return
    except OSError:
        if not any(folder.iterdir()):
            raise
