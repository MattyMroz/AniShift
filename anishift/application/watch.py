"""Readiness rules deciding which discovered groups a watch loop may hand to an automatic run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.intents import ProductKind
from anishift.application.selection import group_is_ready
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
    from anishift.application.intents import AutoPreset

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

SCAN_INTERVAL_S: Final[float] = 5.0
"""Delay between two consecutive library scans of the watch loop."""

QUIET_S: Final[float] = 10.0
"""Time a source file must stay unchanged before its group may be run."""

PARTIAL_SUFFIXES: Final[frozenset[str]] = frozenset({".!qb", ".part", ".tmp", ".crdownload"})
"""Lowercase name endings marking a transfer that is still in progress."""

_PRODUCT_ARTIFACTS: Final[Mapping[ProductKind, ArtifactKind]] = {
    ProductKind.SOURCE_SUBTITLES: ArtifactKind.SOURCE_SUBTITLES,
    ProductKind.FULL_PL: ArtifactKind.FULL_PL,
    ProductKind.SPOKEN_PL: ArtifactKind.SPOKEN_PL,
    ProductKind.DISPLAYED_PL: ArtifactKind.DISPLAYED_PL,
    ProductKind.NARRATION_AUDIO: ArtifactKind.NARRATION_AUDIO,
    ProductKind.MKV: ArtifactKind.FINAL_MKV,
    ProductKind.MP4: ArtifactKind.FINAL_MP4,
}
"""Artifact kind whose presence proves that one requested product already exists."""


class WatchOutcome(StrEnum):
    """State one group reached inside the current watch process."""

    STARTED = "started"
    DONE = "done"
    FAILED = "failed"


_OUTCOME_ORDER: Final[Mapping[WatchOutcome, int]] = {
    WatchOutcome.FAILED: 0,
    WatchOutcome.STARTED: 1,
    WatchOutcome.DONE: 2,
}
"""Reporting priority putting the outcomes a user must react to first."""


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Size, modification time and first sighting of one source file."""

    path: Path
    size: int
    mtime_ns: int
    first_seen: float


@dataclass(frozen=True, slots=True)
class WatchRow:
    """One group and the outcome the current watch process recorded for it."""

    group_id: str
    stem: str
    outcome: WatchOutcome
    exit_code: int | None = None


def snapshot_sources(
    group: InspectedSourceGroup,
    previous: Mapping[Path, SourceSnapshot],
    now: float,
) -> tuple[SourceSnapshot, ...]:
    """Snapshot every source file of *group*, keeping `first_seen` of unchanged files.

    Files that vanish between discovery and the scan are skipped instead of failing the scan.
    """
    snapshots: list[SourceSnapshot] = []
    for artifact in group.artifacts:
        if artifact.lifetime is not ArtifactLifetime.SOURCE or artifact.path is None:
            continue
        snapshot: SourceSnapshot | None = _snapshot_file(artifact.path, previous.get(artifact.path), now)
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


def is_stable(snapshot: SourceSnapshot, now: float) -> bool:
    """Whether one source file stopped changing and no other process holds it exclusively."""
    name: str = snapshot.path.name.casefold()
    if any(name.endswith(suffix) for suffix in PARTIAL_SUFFIXES):
        return False
    if now - snapshot.first_seen < QUIET_S:
        return False
    return _is_openable_for_writing(snapshot.path)


def needs_work(group: InspectedSourceGroup, preset: AutoPreset) -> bool:
    """Whether *group* may be run and still misses at least one product of *preset*."""
    if not group_is_ready(group):
        return False
    ready_kinds: frozenset[ArtifactKind] = frozenset(
        artifact.kind for artifact in group.artifacts if artifact.state is ArtifactState.READY
    )
    return any(_PRODUCT_ARTIFACTS[product] not in ready_kinds for product in preset.products.requested_products)


def source_fingerprint(snapshots: Sequence[SourceSnapshot]) -> tuple[tuple[str, int, int], ...]:
    """Identity of one group's input: name, size and modification time of every source file."""
    return tuple(sorted((snapshot.path.name, snapshot.size, snapshot.mtime_ns) for snapshot in snapshots))


class WatchLedger:
    """What the current watch process observed and already handed to a batch window."""

    def __init__(self) -> None:
        self._snapshots: dict[str, tuple[SourceSnapshot, ...]] = {}
        self._stems: dict[str, str] = {}
        self._started: dict[str, tuple[tuple[str, int, int], ...]] = {}
        self._outcomes: dict[str, _RecordedOutcome] = {}

    def candidates(self, workspace: InspectedWorkspace, preset: AutoPreset, now: float) -> tuple[str, ...]:
        """Refresh every group snapshot and return the groups a batch window may take now."""
        ready: list[str] = []
        for group in workspace.groups:
            snapshots: tuple[SourceSnapshot, ...] = self._refresh(group, now)
            if self._is_candidate(group, snapshots, preset, now):
                ready.append(group.group_id)
        return tuple(ready)

    def mark_started(self, group_ids: Sequence[str]) -> None:
        """Bind the groups of one batch window to the input fingerprint it was started for."""
        for group_id in group_ids:
            self._started[group_id] = source_fingerprint(self._snapshots.get(group_id, ()))
            self._outcomes.pop(group_id, None)

    def record_exit(self, group_ids: Sequence[str], exit_code: int) -> None:
        """Record the exit code one batch window returned for the groups it processed."""
        outcome: WatchOutcome = WatchOutcome.DONE if exit_code == 0 else WatchOutcome.FAILED
        for group_id in group_ids:
            fingerprint: tuple[tuple[str, int, int], ...] | None = self._started.pop(group_id, None)
            if fingerprint is None:
                fingerprint = source_fingerprint(self._snapshots.get(group_id, ()))
            self._outcomes[group_id] = _RecordedOutcome(outcome, fingerprint, exit_code)

    def rows(self) -> tuple[WatchRow, ...]:
        """Return one row per running or finished group, failures first, then by stem."""
        rows: list[WatchRow] = [
            WatchRow(group_id, self._stem(group_id), WatchOutcome.STARTED) for group_id in self._started
        ]
        rows.extend(
            WatchRow(group_id, self._stem(group_id), record.outcome, record.exit_code)
            for group_id, record in self._outcomes.items()
        )
        return tuple(sorted(rows, key=lambda row: (_OUTCOME_ORDER[row.outcome], row.stem)))

    def _refresh(self, group: InspectedSourceGroup, now: float) -> tuple[SourceSnapshot, ...]:
        previous: dict[Path, SourceSnapshot] = {
            snapshot.path: snapshot for snapshot in self._snapshots.get(group.group_id, ())
        }
        snapshots: tuple[SourceSnapshot, ...] = snapshot_sources(group, previous, now)
        self._snapshots[group.group_id] = snapshots
        self._stems[group.group_id] = group.source.stem
        return snapshots

    def _is_candidate(
        self,
        group: InspectedSourceGroup,
        snapshots: Sequence[SourceSnapshot],
        preset: AutoPreset,
        now: float,
    ) -> bool:
        if group.group_id in self._started or not needs_work(group, preset):
            return False
        if not snapshots or not all(is_stable(snapshot, now) for snapshot in snapshots):
            return False
        record: _RecordedOutcome | None = self._outcomes.get(group.group_id)
        if record is None:
            return True
        return record.fingerprint != source_fingerprint(snapshots)

    def _stem(self, group_id: str) -> str:
        return self._stems.get(group_id, group_id)


@dataclass(frozen=True, slots=True)
class _RecordedOutcome:
    """Outcome of one batch window together with the input fingerprint it referred to."""

    outcome: WatchOutcome
    fingerprint: tuple[tuple[str, int, int], ...]
    exit_code: int


def _snapshot_file(path: Path, previous: SourceSnapshot | None, now: float) -> SourceSnapshot | None:
    try:
        stat: os.stat_result = path.stat()
    except OSError:
        logger.debug("Skipped a watched source that disappeared during the scan")
        return None
    first_seen: float = now
    if previous is not None and previous.size == stat.st_size and previous.mtime_ns == stat.st_mtime_ns:
        first_seen = previous.first_seen
    return SourceSnapshot(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns, first_seen=first_seen)


def _is_openable_for_writing(path: Path) -> bool:
    try:
        with path.open("r+b"):
            pass
    except OSError:
        return False
    return True
