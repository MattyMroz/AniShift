"""Public handler, ordering, and resource contracts for graph scheduling."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, RunSettingsSnapshot
from anishift.application.results import ArtifactSnapshot, TaskResult

__all__ = ["NaturalOrderGate", "ResourceLimits", "TaskHandler", "TaskProgressSink"]


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
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Execute one task without mutating shared scheduler state."""
        ...


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Bounded worker and pending-future limits for one scheduler run."""

    extraction: int
    translation: Mapping[str, int]
    tts_group_jobs: int
    audio: int
    composition: int
    max_pending_per_resource: int

    def __post_init__(self) -> None:
        copied_translation: dict[str, int] = {
            provider.strip().casefold(): limit for provider, limit in self.translation.items()
        }
        if any(not provider for provider in copied_translation):
            msg = "Translation resource IDs cannot be blank"
            raise ValueError(msg)
        limits: tuple[int, ...] = (
            self.extraction,
            self.tts_group_jobs,
            self.audio,
            self.composition,
            *copied_translation.values(),
        )
        if any(type(limit) is not int or limit < 1 for limit in limits):
            msg = "Resource worker limits must be positive integers"
            raise ValueError(msg)
        if type(self.max_pending_per_resource) is not int or self.max_pending_per_resource < 0:
            msg = "Pending resource limit must be a non-negative integer"
            raise ValueError(msg)
        object.__setattr__(self, "translation", MappingProxyType(copied_translation))

    @classmethod
    def from_settings(
        cls,
        settings: RunSettingsSnapshot,
        *,
        extraction: int = 2,
        audio: int = 2,
        composition: int = 1,
        max_pending_per_resource: int = 1,
    ) -> ResourceLimits:
        """Build default scheduler limits from one immutable settings snapshot."""
        providers: tuple[str, ...] = (
            settings.translation_profile_id,
            *settings.translation_fallback_chain,
        )
        translation: dict[str, int] = dict.fromkeys(providers, settings.translation_concurrency)
        return cls(
            extraction=extraction,
            translation=translation,
            tts_group_jobs=settings.tts_group_jobs,
            audio=audio,
            composition=composition,
            max_pending_per_resource=max_pending_per_resource,
        )

    def worker_limit(self, resource_key: str, settings: RunSettingsSnapshot) -> int:
        """Resolve one planned resource key without creating a global executor."""
        family, _, provider = normalize_resource_key(resource_key).partition(":")
        limit: int = self.extraction
        if family == "translation":
            limit = self.translation.get(provider, settings.translation_concurrency)
        elif family == "llm":
            limit = min(settings.llm_max_concurrency, 4)
        elif family == "tts":
            limit = 1 if provider.startswith("sapi") else self.tts_group_jobs
        elif family == "audio":
            limit = self.audio
        elif family == "composition":
            limit = self.composition
        elif family == "filesystem":
            limit = 1
        return limit


def normalize_resource_key(resource_key: str) -> str:
    """Return one canonical queue and executor identity for a planned resource."""
    family, separator, provider = resource_key.strip().casefold().partition(":")
    if not family or (separator and not provider):
        msg = "Resource key must contain a non-empty family and optional provider"
        raise ValueError(msg)
    return f"{family}:{provider}" if separator else family


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
