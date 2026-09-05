"""Thread-safe application event contracts independent of TUI rendering."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from anishift.application.planning import TaskState
from anishift.utils.logger import get_logger

__all__ = [
    "RunEvent",
    "RunEventEmitter",
    "RunEventKind",
    "RunEventSink",
    "WorkerNotification",
    "WorkerNotificationKind",
    "sanitize_event_message",
]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_PROGRESS_MAX: Final[int] = 100
"""Largest public task progress percentage."""


class RunEventKind(StrEnum):
    """Coordinator-owned lifecycle events exposed to frontends."""

    RUN_STARTED = "run_started"
    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_RETRY = "task_retry"
    TASK_FALLBACK = "task_fallback"
    TASK_FINISHED = "task_finished"
    GROUP_FINISHED = "group_finished"
    RUN_FINISHED = "run_finished"


class WorkerNotificationKind(StrEnum):
    """Non-owning updates a task handler may send to the coordinator."""

    PROGRESS = "progress"
    RETRY = "retry"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One numbered public transition belonging to exactly one run."""

    run_id: str
    sequence: int
    kind: RunEventKind
    group_id: str | None = None
    task_id: str | None = None
    state: TaskState | None = None
    progress_percent: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip() or self.sequence < 1:
            msg = "Run events require a run ID and positive sequence"
            raise ValueError(msg)
        _validate_optional_id(self.group_id)
        _validate_optional_id(self.task_id)
        _validate_progress(self.progress_percent)
        if self.kind is RunEventKind.TASK_PROGRESS and (
            self.task_id is None or (self.progress_percent is None and not (self.message or "").strip())
        ):
            msg = "Task progress events require a task ID and percentage or activity message"
            raise ValueError(msg)
        object.__setattr__(self, "message", sanitize_event_message(self.message))


@dataclass(frozen=True, slots=True)
class WorkerNotification:
    """Task-local notification without run identity or graph ownership."""

    kind: WorkerNotificationKind
    task_id: str
    progress_percent: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            msg = "Worker notification requires a task ID"
            raise ValueError(msg)
        _validate_progress(self.progress_percent)
        if (
            self.kind is WorkerNotificationKind.PROGRESS
            and self.progress_percent is None
            and not (self.message or "").strip()
        ):
            msg = "Worker progress notification requires a percentage or activity message"
            raise ValueError(msg)
        object.__setattr__(self, "message", sanitize_event_message(self.message))


class RunEventSink(Protocol):
    """Observer of numbered application events."""

    def emit(self, event: RunEvent) -> None:
        """Observe one event without owning workflow state."""
        ...


class RunEventEmitter:
    """Single sequence owner that isolates failures of an event observer."""

    __slots__ = ("_lock", "_run_id", "_sequence", "_sink")

    def __init__(self, run_id: str, sink: RunEventSink) -> None:
        """Bind one observer to a non-empty run identity."""
        if not run_id.strip():
            msg = "Run event emitter requires a run ID"
            raise ValueError(msg)
        self._run_id: str = run_id
        self._sink: RunEventSink = sink
        self._sequence: int = 0
        self._lock: threading.Lock = threading.Lock()

    def emit(  # noqa: PLR0913
        self,
        kind: RunEventKind,
        *,
        group_id: str | None = None,
        task_id: str | None = None,
        state: TaskState | None = None,
        progress_percent: int | None = None,
        message: str | None = None,
    ) -> RunEvent:
        """Create the next event and notify the observer without affecting work."""
        with self._lock:
            self._sequence += 1
            event: RunEvent = RunEvent(
                run_id=self._run_id,
                sequence=self._sequence,
                kind=kind,
                group_id=group_id,
                task_id=task_id,
                state=state,
                progress_percent=progress_percent,
                message=message,
            )
        try:
            self._sink.emit(event)
        except Exception:  # noqa: BLE001
            logger.warning("Run event observer failed", observer_type=type(self._sink).__name__)
        return event


def sanitize_event_message(message: str | None) -> str | None:
    """Redact common secret and absolute-path forms from public event text."""
    if message is None:
        return None
    sanitized: str = " ".join(message.split())
    secret_value_pattern: str = r'(?:"[^"]*"|\'[^\']*\'|\S+)'  # noqa: S105
    sanitized = re.sub(
        rf"(?i)\bbearer\s+{secret_value_pattern}",
        "Bearer <redacted>",
        sanitized,
    )
    sanitized = re.sub(
        rf"(?i)\b(api[_ -]?key|authorization|secret|token)\s*[:=]\s*{secret_value_pattern}",
        r"\1=<redacted>",
        sanitized,
    )
    sanitized = re.sub(r"(?i)\bsk-[A-Za-z0-9_-]+", "<redacted>", sanitized)
    sanitized = re.sub(r"\\\\[^\\\s]+\\[^\s]+", "<path>", sanitized)
    sanitized = re.sub(r"\b[A-Za-z]:[\\/][^\s]+", "<path>", sanitized)
    sanitized = re.sub(r"(?<![\w:/\\])/(?:[^/\s]+/)*[^/\s]+", "<path>", sanitized)
    return sanitized[:500]


def _validate_optional_id(value: str | None) -> None:
    if value is not None and not value.strip():
        msg = "Optional event IDs cannot be blank"
        raise ValueError(msg)


def _validate_progress(value: int | None) -> None:
    if value is not None and (type(value) is not int or not 0 <= value <= _PROGRESS_MAX):
        msg = "Event progress must be an integer from 0 through 100"
        raise ValueError(msg)
