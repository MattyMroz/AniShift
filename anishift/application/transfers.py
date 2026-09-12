"""Confirm selected torrent files before they become processing inputs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Final

from anishift.application.control import AcquisitionState
from anishift.errors import AniShiftError
from anishift.platform.directory_watch import source_is_available
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from anishift.application.acquisition import AcquisitionService
    from anishift.application.control import AcquisitionConfirmation
    from anishift.services.torrents import TorrentFile, TorrentInfo

__all__ = ["TransferInspector"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_COMPLETE_STATES: Final[frozenset[str]] = frozenset(
    {"uploading", "stalledUP", "queuedUP", "pausedUP", "stoppedUP", "forcedUP"}
)
"""Client states that have finished downloading and are not checking or moving data."""


@dataclass(frozen=True, slots=True)
class _Files:
    entries: tuple[TorrentFile, ...]
    signature: tuple[str, str, bool]


class TransferInspector:
    """Reconcile active transfers with their selected files and local readability."""

    def __init__(self, acquisition: AcquisitionService, workspace_root: Path) -> None:
        self._acquisition: AcquisitionService = acquisition
        self._root: Path = workspace_root.resolve()
        self._files: dict[str, _Files] = {}

    def inspect(self, acquisitions: Sequence[AcquisitionConfirmation]) -> tuple[AcquisitionConfirmation, ...]:
        """Read the client once and refresh file details at metadata and completion boundaries."""
        if not acquisitions:
            self._files.clear()
            return ()
        transfers: dict[str, TorrentInfo] = {item.info_hash.casefold(): item for item in self._acquisition.transfers()}
        active: set[str] = {item.info_hash for item in acquisitions}
        self._files = {key: value for key, value in self._files.items() if key in active}
        results: list[AcquisitionConfirmation] = []
        for acquisition in acquisitions:
            try:
                result: AcquisitionConfirmation = self._inspect(acquisition, transfers.get(acquisition.info_hash))
            except (AniShiftError, OSError) as problem:
                logger.warning("Transfer inspection failed", error_class=type(problem).__name__)
                result = acquisition
            results.append(result)
        return tuple(results)

    def _inspect(self, acquisition: AcquisitionConfirmation, transfer: TorrentInfo | None) -> AcquisitionConfirmation:
        if transfer is None:
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        directory: Path = Path(transfer.save_path).resolve()
        if not directory.is_relative_to(self._root):
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        ready: bool = transfer.progress == 1.0 and transfer.amount_left == 0 and transfer.state in _COMPLETE_STATES
        files: tuple[TorrentFile, ...] = self._inspect_files(transfer, ready=ready)
        selected: tuple[TorrentFile, ...] = tuple(item for item in files if item.priority > 0)
        names: tuple[str, ...] = tuple(item.name.replace("\\", "/") for item in selected)
        if any(not _safe_path(directory, name) for name in names):
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        complete: bool = ready and bool(selected) and all(_ready_file(directory, item) for item in selected)
        if ready:
            self._files.pop(acquisition.info_hash, None)
        relative: Path = directory.relative_to(self._root)
        candidate: AcquisitionConfirmation = replace(
            acquisition,
            directory=relative.as_posix() if relative.parts else "",
            required_files=names,
            state=AcquisitionState.COMPLETE if complete else AcquisitionState.ACCEPTED,
        )
        return _updated(acquisition, candidate)

    def _inspect_files(self, transfer: TorrentInfo, *, ready: bool) -> tuple[TorrentFile, ...]:
        info_hash: str = transfer.info_hash.casefold()
        signature: tuple[str, str, bool] = (transfer.name, transfer.save_path, ready)
        cached: _Files | None = self._files.get(info_hash)
        if cached is None or not cached.entries or cached.signature != signature:
            cached = _Files(self._acquisition.transfer_files(info_hash), signature)
            self._files[info_hash] = cached
        return cached.entries


def _safe_path(directory: Path, name: str) -> bool:
    path: Path = Path(name)
    return (
        not path.is_absolute()
        and not PureWindowsPath(name).drive
        and ".." not in path.parts
        and (directory / path).resolve().is_relative_to(directory)
    )


def _ready_file(directory: Path, file: TorrentFile) -> bool:
    path: Path = directory / file.name.replace("\\", "/")
    return file.progress == 1.0 and file.is_seed and source_is_available(path) and path.stat().st_size == file.size


def _updated(before: AcquisitionConfirmation, after: AcquisitionConfirmation) -> AcquisitionConfirmation:
    return replace(after, updated_at=datetime.now(UTC).isoformat()) if after != before else before
