"""Confirm selected torrent files before they become processing inputs."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Final

from anishift.application.control import AcquisitionState
from anishift.application.events import failure_code, sanitize_event_message
from anishift.errors import AniShiftError
from anishift.platform.directory_watch import source_is_available
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from anishift.application.acquisition import AcquisitionService
    from anishift.application.control import AcquisitionConfirmation
    from anishift.services.torrents import TorrentFile, TorrentInfo

__all__ = ["TransferInspector", "flat_layout", "reserved_stem"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_COMPLETE_STATES: Final[frozenset[str]] = frozenset(
    {"uploading", "stalledUP", "queuedUP", "pausedUP", "stoppedUP", "forcedUP"}
)
"""Client states that have finished downloading and are not checking or moving data."""

_DOWNLOADING_STATES: Final[frozenset[str]] = frozenset(
    {"downloading", "stalledDL", "forcedDL", "metaDL", "forcedMetaDL"}
)
"""States in which the client is actively trying to obtain data."""

_SETTLING_STATES: Final[frozenset[str]] = frozenset(
    {
        "checkingDL",
        "checkingUP",
        "checkingResumeData",
        "queuedForChecking",
        "allocating",
        "moving",
        "error",
        "missingFiles",
    }
)
"""States in which the client is verifying, relocating or failing, so no file may be accepted."""

_FIRST_ORDINAL: Final[int] = 2
"""Suffix given to the first colliding set, because the free core carries no number."""


@dataclass(frozen=True, slots=True)
class _Files:
    entries: tuple[TorrentFile, ...]
    signature: tuple[str, str, bool, float, int | None]


@dataclass(frozen=True, slots=True)
class _Progress:
    value: tuple[float, int | None]
    checked_at: float
    idle_s: float
    downloading: bool


class TransferInspector:
    """Reconcile active transfers with their selected files and local readability."""

    def __init__(
        self,
        acquisition: AcquisitionService,
        workspace_root: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._acquisition: AcquisitionService = acquisition
        self._root: Path = workspace_root.resolve()
        self._files: dict[str, _Files] = {}
        self._clock: Callable[[], float] = clock
        self._progress: dict[str, _Progress] = {}
        self._progress_lock: threading.Lock = threading.Lock()
        self._stalled: frozenset[str] = frozenset()
        self._snapshot: tuple[TorrentInfo, ...] = ()
        self._failures: frozenset[tuple[str, str]] = frozenset()

    def snapshot(self) -> tuple[TorrentInfo, ...]:
        """Read the last transfer observations without contacting the client."""
        with self._progress_lock:
            return self._snapshot

    @property
    def stalled(self) -> frozenset[str]:
        """Hashes with a confirmed lack of progress during active downloading."""
        with self._progress_lock:
            return self._stalled

    def reset_clock(self) -> None:
        """Exclude an unobserved or suspended interval from transfer stall time."""
        with self._progress_lock:
            self._progress = {key: replace(value, downloading=False) for key, value in self._progress.items()}

    def inspect(
        self,
        acquisitions: Sequence[AcquisitionConfirmation],
        *,
        stall_after_s: float = float("inf"),
    ) -> tuple[AcquisitionConfirmation, ...]:
        """Read the client once and refresh the details of the selected files whenever the transfer moved bytes."""
        if not acquisitions:
            self._files.clear()
            self._note_failures(frozenset(), None)
            return ()
        self._acquisition.resume_unconfirmed(frozenset(item.info_hash for item in acquisitions))
        transfers: dict[str, TorrentInfo] = {item.info_hash.casefold(): item for item in self._acquisition.transfers()}
        active: set[str] = {item.info_hash for item in acquisitions}
        self._record_progress({key: value for key, value in transfers.items() if key in active}, stall_after_s)
        self._files = {key: value for key, value in self._files.items() if key in active}
        results: list[AcquisitionConfirmation] = []
        natures: set[tuple[str, str]] = set()
        reason: str | None = None
        for acquisition in acquisitions:
            if acquisition.state is AcquisitionState.FAILED or acquisition.problem is not None:
                results.append(acquisition)
                continue
            try:
                result: AcquisitionConfirmation = self._inspect(acquisition, transfers.get(acquisition.info_hash))
            except (AniShiftError, OSError) as problem:
                natures.add((type(problem).__name__, failure_code(problem)))
                reason = reason or sanitize_event_message(str(problem))
                result = acquisition
            results.append(result)
        self._note_failures(frozenset(natures), reason)
        return tuple(results)

    def _note_failures(self, natures: frozenset[tuple[str, str]], reason: str | None) -> None:
        previous: frozenset[tuple[str, str]] = self._failures
        self._failures = natures
        if natures == previous:
            return
        if not natures:
            logger.info("Transfer inspection recovered")
            return
        logger.warning(
            "Transfer inspection failed",
            causes=", ".join(sorted(f"{name}:{code}" if code else name for name, code in natures)),
            reason=reason,
        )

    def _record_progress(self, transfers: dict[str, TorrentInfo], stall_after_s: float) -> None:
        now: float = self._clock()
        progress: dict[str, _Progress] = {}
        with self._progress_lock:
            self._snapshot = tuple(transfers.values())
            for key, transfer in transfers.items():
                previous: _Progress | None = self._progress.get(key)
                value: tuple[float, int | None] = (transfer.progress, transfer.completed)
                downloading: bool = transfer.state in _DOWNLOADING_STATES
                idle: float = 0.0
                if previous is not None and previous.value == value:
                    idle = previous.idle_s
                    if previous.downloading and downloading:
                        idle += max(0.0, now - previous.checked_at)
                progress[key] = _Progress(value, now, idle, downloading)
            self._progress = progress
            self._stalled = frozenset(
                key for key, item in progress.items() if item.downloading and item.idle_s >= stall_after_s
            )

    def declared(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Return the file identities the last inspection read, contacting no client of its own."""
        cached: _Files | None = self._files.get(info_hash.casefold())
        return () if cached is None else cached.entries

    def forget(self, info_hash: str) -> None:
        """Drop cached file identities whose names the owner has just changed."""
        self._files.pop(info_hash.casefold(), None)

    def _inspect(self, acquisition: AcquisitionConfirmation, transfer: TorrentInfo | None) -> AcquisitionConfirmation:
        if transfer is None:
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        directory: Path = Path(transfer.save_path).resolve()
        if not directory.is_relative_to(self._root):
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        finished: bool = transfer.progress == 1.0 and transfer.amount_left == 0 and transfer.state in _COMPLETE_STATES
        files: tuple[TorrentFile, ...] = self._inspect_files(transfer, ready=finished)
        selected: tuple[TorrentFile, ...] = tuple(item for item in files if item.priority > 0)
        names: tuple[str, ...] = tuple(item.name.replace("\\", "/") for item in selected)
        if any(not _safe_path(directory, name) for name in names) or _reservation_broken(acquisition, selected, names):
            return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))
        complete: tuple[str, ...] = _complete_files(
            directory, selected, names, settling=transfer.state in _SETTLING_STATES
        )
        if finished:
            self._files.pop(acquisition.info_hash, None)
        relative: Path = directory.relative_to(self._root)
        whole: bool = finished and bool(selected) and len(complete) == len(names)
        candidate: AcquisitionConfirmation = replace(
            acquisition,
            directory=relative.as_posix() if relative.parts else "",
            required_files=names,
            complete_files=complete,
            state=AcquisitionState.COMPLETE if whole else AcquisitionState.ACCEPTED,
        )
        return _updated(acquisition, candidate)

    def _inspect_files(self, transfer: TorrentInfo, *, ready: bool) -> tuple[TorrentFile, ...]:
        info_hash: str = transfer.info_hash.casefold()
        signature: tuple[str, str, bool, float, int | None] = (
            transfer.name,
            transfer.save_path,
            ready,
            transfer.progress,
            transfer.completed,
        )
        cached: _Files | None = self._files.get(info_hash)
        if cached is None or not cached.entries or cached.signature != signature:
            cached = _Files(self._acquisition.transfer_files(info_hash), signature)
            self._files[info_hash] = cached
        return cached.entries


def reserved_stem(name: str) -> str:
    """Return the comparable core of one flat name, so a video and its sidecars share one reservation."""
    return Path(name.replace("\\", "/")).stem.casefold()


def flat_layout(files: Sequence[TorrentFile], reserved: frozenset[str]) -> tuple[tuple[int, str, int], ...]:
    """Reserve one free flat name per selected file, sharing a core between a video and its sidecars."""
    selected: tuple[TorrentFile, ...] = tuple(item for item in files if item.priority > 0)
    if not selected:
        return ()
    taken: set[str] = {value.casefold() for value in reserved}
    cores: dict[str, str] = {}
    used: dict[str, set[str]] = {}
    layout: list[tuple[int, str, int]] = []
    for item in sorted(selected, key=lambda entry: entry.index):
        stem, suffix = _split(item.name)
        core: str | None = cores.get(stem.casefold())
        if core is None or suffix.casefold() in used[core]:
            core = _free_core(stem, taken)
            taken.add(core.casefold())
            cores[stem.casefold()] = core
            used[core] = set()
        used[core].add(suffix.casefold())
        layout.append((item.index, f"{core}{suffix}", item.size))
    return tuple(layout)


def _split(name: str) -> tuple[str, str]:
    path: Path = Path(name.replace("\\", "/"))
    return path.stem, path.suffix


def _free_core(stem: str, taken: set[str]) -> str:
    if stem.casefold() not in taken:
        return stem
    ordinal: int = _FIRST_ORDINAL
    while f"{stem} [{ordinal}]".casefold() in taken:
        ordinal += 1
    return f"{stem} [{ordinal}]"


def _reservation_broken(
    acquisition: AcquisitionConfirmation,
    selected: Sequence[TorrentFile],
    names: Sequence[str],
) -> bool:
    if not acquisition.file_layout:
        return False
    observed: tuple[tuple[int, str, int], ...] = tuple(
        sorted((item.index, name, item.size) for item, name in zip(selected, names, strict=True))
    )
    return observed != tuple(sorted(acquisition.file_layout))


def _complete_files(
    directory: Path,
    selected: Sequence[TorrentFile],
    names: Sequence[str],
    *,
    settling: bool,
) -> tuple[str, ...]:
    if settling:
        return ()
    sets: dict[str, bool] = {}
    for item, name in zip(selected, names, strict=True):
        core: str = reserved_stem(name)
        sets[core] = sets.get(core, True) and _ready_file(directory, item)
    return tuple(name for name in names if sets[reserved_stem(name)])


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
