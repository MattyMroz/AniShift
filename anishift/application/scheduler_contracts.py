"""Public handler, ordering, and resource contracts for graph scheduling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from anishift.application.cancellation import CancellationToken, CommitCancellationToken
from anishift.application.events import RunEventSink, WorkerNotification
from anishift.application.intents import RequestOrigin
from anishift.application.planning import ExecutionPlan, PlanTask, RunSettingsSnapshot, resource_family
from anishift.application.results import ArtifactSnapshot, TaskResult

if TYPE_CHECKING:
    from anishift.application.recovery import RunJournal
    from anishift.application.sessions import RunSession

__all__ = [
    "NaturalOrderGate",
    "ResourceLimits",
    "RunRequest",
    "TaskHandler",
    "TaskProgressSink",
    "extraction_worker_count",
    "is_remote",
    "resource_key",
]

# ── Constants ────────────────────────────────────────────────────────────────

_EXTRACTION_IO_HEADROOM: Final[int] = 2
"""Extra extraction workers kept above the core-derived pool size."""

_AUDIO_WORKERS: Final[int] = 2
"""Narration mixes and transcodes running at once across every graph."""

_COMPOSITION_WORKERS: Final[int] = 1
"""Containers composed at once across every graph."""


class TaskProgressSink(Protocol):
    """Task-local observer that cannot create public run events."""

    def emit(self, notification: WorkerNotification) -> None:
        """Queue one task-owned progress, retry, or fallback notification."""
        ...


class TaskHandler(Protocol):
    """Synchronous dispatcher for one planned application task."""

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        settings: RunSettingsSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Execute one task with the settings read when it started, without mutating shared scheduler state."""
        ...


@dataclass(frozen=True, slots=True)
class RunRequest:
    """One immutable graph handed to the coordinator with its own execution scope."""

    run_id: str
    plan: ExecutionPlan
    session: RunSession
    handler: TaskHandler
    cancel: CommitCancellationToken
    events: RunEventSink
    origin: RequestOrigin = RequestOrigin.USER
    automatic: bool = False
    journal: RunJournal | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            msg = "Run request requires a run ID"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Worker limits shared by every active graph, read from the settings of one admission round."""

    extraction: int
    translation: int
    llm: int
    tts: int
    audio: int = _AUDIO_WORKERS
    composition: int = _COMPOSITION_WORKERS

    def __post_init__(self) -> None:
        limits: tuple[int, ...] = (
            self.extraction,
            self.translation,
            self.llm,
            self.tts,
            self.audio,
            self.composition,
        )
        if any(type(limit) is not int or limit < 1 for limit in limits):
            msg = "Resource worker limits must be positive integers"
            raise ValueError(msg)

    @classmethod
    def from_settings(cls, settings: RunSettingsSnapshot, *, extraction: int) -> ResourceLimits:
        """Build the limits that *settings* give every pool beside the extraction pool sized by its caller."""
        return cls(
            extraction=extraction,
            translation=settings.translation_concurrency,
            llm=settings.llm_max_concurrency,
            tts=settings.tts_group_jobs,
        )

    def worker_limit(self, key: str) -> int:  # noqa: PLR0911 - one return per pool keeps the closed mapping visible
        """Return how many tasks of one resource key may run at once."""
        family, _, provider = key.partition(":")
        match family:
            case "translation":
                return self.translation
            case "llm":
                return self.llm
            case "tts":
                return 1 if provider == "sapi" else self.tts
            case "audio":
                return self.audio
            case "composition":
                return self.composition
            case "filesystem":
                return 1
            case _:
                return self.extraction


def resource_key(task: PlanTask, settings: RunSettingsSnapshot) -> str:
    """Return the pool and provider a task competes for under the settings it starts with."""
    family: str = resource_family(task.kind)
    if family == "translation" and settings.translation_profile_id == "llm":
        return f"llm:{settings.llm_profile_id}"
    if family == "translation":
        return f"translation:{settings.translation_profile_id}"
    if family == "tts":
        return f"tts:{settings.tts_profile_id}"
    return family


def is_remote(task: PlanTask, settings: RunSettingsSnapshot) -> bool:
    """Return whether a task starting with *settings* calls a remote provider that may charge for the call."""
    family: str = resource_family(task.kind)
    return family == "translation" or (family == "tts" and settings.tts_is_network)


def extraction_worker_count(group_count: int) -> int:
    """Return the extraction pool size for the given number of extracting groups."""
    cores: int = os.cpu_count() or 1
    scaled_workers: int = round(cores**0.5) + _EXTRACTION_IO_HEADROOM
    return max(1, min(group_count, scaled_workers))


class NaturalOrderGate:
    """Release resolved groups only in their declared natural order."""

    __slots__ = ("_group_ids", "_index", "_resolved")

    def __init__(self, group_ids: tuple[str, ...]) -> None:
        """Store a unique ordered group sequence."""
        if any(not group_id.strip() for group_id in group_ids) or len(group_ids) != len(set(group_ids)):
            msg = "Natural-order group IDs must be non-empty and unique"
            raise ValueError(msg)
        self._group_ids: tuple[str, ...] = group_ids
        self._index: int = 0
        self._resolved: set[str] = set()

    @property
    def current_group(self) -> str | None:
        """Return the only group whose successful task results may be forwarded."""
        if self._index == len(self._group_ids):
            return None
        return self._group_ids[self._index]

    def can_release(self, group_id: str) -> bool:
        """Return whether this group currently owns the forwarding gate."""
        return self.current_group == group_id

    def skip(self, group_id: str) -> tuple[str, ...]:
        """Resolve a terminal group and return newly ordered terminal group IDs."""
        if group_id not in self._group_ids:
            msg = f"Natural-order gate does not contain group {group_id!r}"
            raise ValueError(msg)
        self._resolved.add(group_id)
        released: list[str] = []
        while self._index < len(self._group_ids):
            candidate: str = self._group_ids[self._index]
            if candidate not in self._resolved:
                break
            released.append(candidate)
            self._index += 1
        return tuple(released)
