"""Confirm selected torrent files before they become processing inputs."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Final

from anishift.application.acquisition_staging import lexical_path, staged_file, torrent_relative_path
from anishift.application.control import REMOVED_FROM_CLIENT, AcquisitionState
from anishift.application.discovery import SOURCE_SUBTITLE_FORMATS, VIDEO_SOURCE_SUFFIXES
from anishift.application.episode_identity import IdentityVerdict, classify
from anishift.application.events import failure_code, sanitize_event_message
from anishift.application.products import PRODUCT_SUFFIXES
from anishift.errors import AniShiftError
from anishift.platform.directory_watch import source_is_available
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from anishift.application.acquisition import AcquisitionService
    from anishift.application.control import AcquisitionConfirmation, FileReservation, TorrentioReference
    from anishift.services.torrents import TorrentFile, TorrentInfo

__all__ = [
    "TransferInspector",
    "episode_files",
    "file_map_revision",
    "flat_layout",
    "flat_names",
    "reserved_stem",
    "video_sidecars",
]

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

_FAILURES_BEFORE_PROBLEM: Final[int] = 3
"""Consecutive failed inspections of one transfer before its release stops with a visible problem."""

_MISSING_BEFORE_TRANSITION: Final[int] = 3
"""Consecutive successful list reads missing a hash before its transfer becomes uncertain or removed."""


@dataclass(frozen=True, slots=True)
class _Files:
    entries: tuple[TorrentFile, ...]
    signature: tuple[str, str, bool, float, int | None]
    stale: bool = False


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
        self._root: Path = lexical_path(workspace_root)
        self._files: dict[str, _Files] = {}
        self._clock: Callable[[], float] = clock
        self._progress: dict[str, _Progress] = {}
        self._progress_lock: threading.Lock = threading.Lock()
        self._stalled: frozenset[str] = frozenset()
        self._snapshot: tuple[TorrentInfo, ...] = ()
        self._failures: frozenset[tuple[str, str]] = frozenset()
        self._refused: dict[str, int] = {}
        self._missing: dict[str, int] = {}

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
        held: frozenset[str] = frozenset(),
    ) -> tuple[AcquisitionConfirmation, ...]:
        """Read the client once and refresh the details of the selected files whenever the transfer moved bytes.

        A hash in *held* is not observed now, so its accrued idle time survives as a suspended measurement.
        """
        if not acquisitions:
            self._files.clear()
            self._refused.clear()
            self._missing.clear()
            self._note_failures(frozenset(), None)
            return ()
        self._acquisition.resume_unconfirmed(frozenset(item.info_hash for item in acquisitions))
        transfers: dict[str, TorrentInfo] = {item.info_hash.casefold(): item for item in self._acquisition.transfers()}
        active: set[str] = {item.info_hash for item in acquisitions}
        self._missing = {key: self._missing.get(key, 0) + 1 for key in active if key not in transfers}
        missing: frozenset[str] = frozenset(
            item.info_hash
            for item in acquisitions
            if item.selective
            and item.client_confirmed
            and item.state is not AcquisitionState.FAILED
            and item.info_hash not in transfers
            and self._missing[item.info_hash] >= _MISSING_BEFORE_TRANSITION
        )
        removed: frozenset[str] = (
            (self._acquisition.finalizable_hashes(missing) - self._acquisition.released_hashes(missing))
            if missing
            else frozenset()
        )
        self._record_progress({key: value for key, value in transfers.items() if key in active}, stall_after_s, held)
        self._files = {key: value for key, value in self._files.items() if key in active}
        self._refused = {key: value for key, value in self._refused.items() if key in active}
        results: list[AcquisitionConfirmation] = []
        natures: set[tuple[str, str]] = set()
        reason: str | None = None
        for acquisition in acquisitions:
            if 0 < self._missing.get(acquisition.info_hash, 0) < _MISSING_BEFORE_TRANSITION:
                results.append(acquisition)
                continue
            if (
                acquisition.info_hash in removed
                and acquisition.client_confirmed
                and acquisition.state is not AcquisitionState.FAILED
            ):
                results.append(
                    _updated(
                        acquisition, replace(acquisition, state=AcquisitionState.FAILED, problem=REMOVED_FROM_CLIENT)
                    )
                )
                logger.info("Previously confirmed transfer removed from its managed client")
                continue
            if acquisition.state is AcquisitionState.FAILED or acquisition.problem is not None:
                results.append(acquisition)
                continue
            try:
                result: AcquisitionConfirmation = self._inspect(acquisition, transfers.get(acquisition.info_hash))
            except (AniShiftError, OSError) as problem:
                natures.add((type(problem).__name__, failure_code(problem)))
                reason = reason or sanitize_event_message(str(problem))
                result = self._refused_inspection(acquisition, problem)
            else:
                self._refused.pop(acquisition.info_hash.casefold(), None)
            results.append(result)
        self._note_failures(frozenset(natures), reason)
        return tuple(results)

    def _refused_inspection(
        self,
        acquisition: AcquisitionConfirmation,
        problem: AniShiftError | OSError,
    ) -> AcquisitionConfirmation:
        key: str = acquisition.info_hash.casefold()
        attempts: int = self._refused.get(key, 0) + 1
        self._refused[key] = attempts
        if attempts < _FAILURES_BEFORE_PROBLEM:
            return acquisition
        logger.warning(
            "A transfer keeps failing inspection",
            attempts=attempts,
            error_class=type(problem).__name__,
            code=failure_code(problem),
        )
        return replace(acquisition, problem=sanitize_event_message(str(problem)))

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

    def _record_progress(
        self, transfers: dict[str, TorrentInfo], stall_after_s: float, held: frozenset[str] = frozenset()
    ) -> None:
        now: float = self._clock()
        progress: dict[str, _Progress] = {}
        with self._progress_lock:
            self._snapshot = tuple(transfers.values())
            for key in held:
                suspended: _Progress | None = self._progress.get(key.casefold())
                if suspended is not None and key.casefold() not in transfers:
                    progress[key.casefold()] = replace(suspended, downloading=False)
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

    def idle_s(self, info_hash: str) -> float:
        """Return how long the observed transfer kept working without any progress."""
        with self._progress_lock:
            progress: _Progress | None = self._progress.get(info_hash.casefold())
            return 0.0 if progress is None else progress.idle_s

    def restart_idle(self, info_hash: str) -> None:
        """Start a new idle measurement for one transfer, as an explicit resume begins a new attempt."""
        with self._progress_lock:
            self._progress.pop(info_hash.casefold(), None)

    def declared(self, info_hash: str) -> tuple[TorrentFile, ...]:
        """Return the file identities the last inspection read, contacting no client of its own."""
        cached: _Files | None = self._files.get(info_hash.casefold())
        return () if cached is None else cached.entries

    def forget(self, info_hash: str) -> None:
        """Drop cached file identities whose names the owner has just changed."""
        self._files.pop(info_hash.casefold(), None)

    def _inspect(self, acquisition: AcquisitionConfirmation, transfer: TorrentInfo | None) -> AcquisitionConfirmation:
        if transfer is None:
            return self._uncertain(acquisition, "missing_from_list")
        directory: Path = lexical_path(transfer.save_path)
        if not directory.is_relative_to(self._root):
            return self._uncertain(acquisition, "save_path_outside_workspace")
        relative: Path = directory.relative_to(self._root)
        try:
            if relative.parts:
                staged_file(self._root, relative.as_posix())
        except ValueError:
            return self._uncertain(acquisition, "save_path_invalid")
        finished: bool = transfer.progress == 1.0 and transfer.amount_left == 0 and transfer.state in _COMPLETE_STATES
        files: tuple[TorrentFile, ...] = self._inspect_files(transfer, ready=finished)
        selected: tuple[TorrentFile, ...] = tuple(item for item in files if item.priority > 0)
        names: tuple[str, ...] = tuple(item.name.replace("\\", "/") for item in selected)
        if any(not _safe_path(directory, name) for name in names):
            return self._uncertain(acquisition, "file_name_invalid")
        if _reservation_broken(acquisition, selected, names):
            return self._uncertain(acquisition, "reservation_mismatch")
        complete: tuple[str, ...] = _complete_files(
            directory, selected, names, settling=transfer.state in _SETTLING_STATES
        )
        if finished and transfer.info_hash.casefold() in self._files:
            key: str = transfer.info_hash.casefold()
            self._files[key] = replace(self._files[key], stale=True)
        handed_off: frozenset[str] = frozenset(
            path
            for assignment in acquisition.assignments
            if assignment.publication is not None and assignment.publication.handed_off
            for _index, path, _size in assignment.files
        )
        whole: bool = finished and bool(selected) and set(names) <= set(complete) | handed_off
        candidate: AcquisitionConfirmation = replace(
            acquisition,
            directory=relative.as_posix() if relative.parts else "",
            required_files=names,
            complete_files=complete,
            state=AcquisitionState.COMPLETE if whole else AcquisitionState.ACCEPTED,
        )
        return _updated(acquisition, candidate)

    def _uncertain(self, acquisition: AcquisitionConfirmation, reason: str) -> AcquisitionConfirmation:
        if acquisition.state is not AcquisitionState.UNCERTAIN:
            logger.info("Transfer became uncertain", reason=reason)
        return _updated(acquisition, replace(acquisition, state=AcquisitionState.UNCERTAIN))

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
        if cached is None or cached.stale or not cached.entries or cached.signature != signature:
            cached = _Files(self._acquisition.transfer_files(info_hash), signature)
            self._files[info_hash] = cached
        return cached.entries


def reserved_stem(name: str) -> str:
    """Return the comparable core of one flat name, so a video and its sidecars share one reservation."""
    return Path(name.replace("\\", "/")).stem.casefold()


def file_map_revision(files: Sequence[TorrentFile]) -> str:
    """Identify a unique safe metadata map independently of progress and priorities."""
    identities: list[tuple[int, str, int]] = sorted((item.index, item.name, item.size) for item in files)
    paths: list[str] = [str(torrent_relative_path(name)).casefold() for _index, name, _size in identities]
    if len({item.index for item in files}) != len(files) or len(set(paths)) != len(paths):
        msg = "A torrent file map requires unique indexes and Windows paths"
        raise ValueError(msg)
    return hashlib.sha256(json.dumps(identities, ensure_ascii=True).encode()).hexdigest()


def episode_files(
    files: Sequence[TorrentFile], reference: TorrentioReference, target: Mapping[str, object], release: str
) -> tuple[TorrentFile, ...]:
    """Select one uniquely named video, otherwise one decisive H1 match, with its exact sidecars."""
    file_map_revision(files)
    videos: tuple[TorrentFile, ...] = tuple(
        item for item in files if torrent_relative_path(item.name).suffix.casefold() in VIDEO_SOURCE_SUFFIXES
    )
    named: tuple[TorrentFile, ...] = tuple(
        item for item in videos if torrent_relative_path(item.name).name == reference.file_name
    )
    if len(named) == 1:
        return video_sidecars(files, named[0])
    matched: tuple[TorrentFile, ...] = tuple(
        item
        for item in videos
        if classify(
            target,
            {
                "release": release,
                "path": item.name,
                "filename": torrent_relative_path(item.name).name,
            },
        ).verdict
        is IdentityVerdict.MATCH
    )
    return video_sidecars(files, matched[0]) if len(matched) == 1 else ()


def video_sidecars(files: Sequence[TorrentFile], video: TorrentFile) -> tuple[TorrentFile, ...]:
    """Bind an exact video identity and only supported same-directory, same-stem sidecars."""
    file_map_revision(files)
    path: PurePosixPath = torrent_relative_path(video.name)
    if path.suffix.casefold() not in VIDEO_SOURCE_SUFFIXES or not any(
        (item.index, item.name, item.size) == (video.index, video.name, video.size) for item in files
    ):
        msg = "The selected video is not in the current file map"
        raise ValueError(msg)
    suffixes: frozenset[str] = frozenset(SOURCE_SUBTITLE_FORMATS) | frozenset(
        item.suffix for item in PRODUCT_SUFFIXES if item.audio_profile is not None
    )
    return tuple(
        item
        for item in files
        if item.index == video.index
        or (
            torrent_relative_path(item.name).parent == path.parent
            and torrent_relative_path(item.name).stem == path.stem
            and torrent_relative_path(item.name).suffix.casefold() in suffixes
        )
    )


def flat_layout(files: Sequence[TorrentFile], reserved: frozenset[str]) -> tuple[FileReservation, ...]:
    """Reserve one free flat name per selected file, sharing a core between a video and its sidecars."""
    return flat_names(tuple((item.index, item.name, item.size) for item in files if item.priority > 0), reserved)


def flat_names(files: Sequence[FileReservation], reserved: frozenset[str]) -> tuple[FileReservation, ...]:
    """Give every file one free flat name, sharing a core between a video and its sidecars."""
    taken: set[str] = {value.casefold() for value in reserved}
    cores: dict[str, str] = {}
    used: dict[str, set[str]] = {}
    layout: list[FileReservation] = []
    for index, name, size in sorted(files):
        stem, suffix = _split(name)
        core: str | None = cores.get(stem.casefold())
        if core is None or suffix.casefold() in used[core]:
            core = _free_core(stem, taken)
            taken.add(core.casefold())
            cores[stem.casefold()] = core
            used[core] = set()
        used[core].add(suffix.casefold())
        layout.append((index, f"{core}{suffix}", size))
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
        and lexical_path(directory / path).is_relative_to(directory)
    )


def _ready_file(directory: Path, file: TorrentFile) -> bool:
    """Return whether the client verified every piece of this file and the local bytes match its declared size."""
    try:
        path: Path = staged_file(directory, file.name)
    except ValueError:
        return False
    if file.progress != 1.0 or not source_is_available(path):
        return False
    try:
        return path.stat().st_size == file.size
    except OSError:
        return False


def _updated(before: AcquisitionConfirmation, after: AcquisitionConfirmation) -> AcquisitionConfirmation:
    return replace(after, updated_at=datetime.now(UTC).isoformat()) if after != before else before
