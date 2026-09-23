"""Bounded operational observations independent of execution and ownership state."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from anishift.application.events import sanitize_event_message
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

RETENTION_DAYS: Final[int] = 30
"""Days of observations retained without affecting any authoritative record."""

HISTORY_LIMIT: Final[int] = 50
"""Completed logical materials shown before the user searches the retained journal."""


class HistoryKind(StrEnum):
    """Operation boundaries worth recording instead of individual task progress."""

    ORDER = "order_admitted"
    DOWNLOAD = "download_confirmed"
    SUCCESS = "processing_success"
    INTERRUPTED = "processing_interrupted"
    ERROR = "processing_error"
    REGENERATION = "regeneration"
    DELETE = "delete_outcome"


@dataclass(frozen=True, slots=True)
class HistoryEvent:
    """One immutable observation with opaque references back to authoritative operations."""

    event_id: str
    material_id: str
    operation_id: str
    occurred_at: str
    kind: HistoryKind
    name: str
    generation: int = 1
    attempt: int = 1
    outcome: str = ""
    recovered_from_admission: bool = False

    def __post_init__(self) -> None:
        moment: datetime = datetime.fromisoformat(self.occurred_at)
        if moment.tzinfo is None or not self.event_id or not self.material_id or not self.operation_id:
            msg = "A history observation needs stable identities and an aware timestamp"
            raise ValueError(msg)
        label: str = re.sub(r"(?i)\b(?:https?|magnet):\S+", "<url>", self.name)
        object.__setattr__(self, "name", sanitize_event_message(label) or "")

    @classmethod
    def create(  # noqa: PLR0913 - the identity includes the operation, material and attempt
        cls,
        material_id: str,
        operation_id: str,
        occurred_at: str,
        kind: HistoryKind,
        name: str,
        *,
        generation: int = 1,
        attempt: int = 1,
        outcome: str = "",
        recovered_from_admission: bool = False,
    ) -> HistoryEvent:
        """Derive an identity independent of replay time and current filesystem paths."""
        identity: str = json.dumps([material_id, operation_id, generation, attempt, kind.value])
        return cls(
            hashlib.sha256(identity.encode()).hexdigest(),
            material_id,
            operation_id,
            occurred_at,
            kind,
            name,
            generation,
            attempt,
            outcome,
            recovered_from_admission,
        )


class HistoryJournal:
    """Append observations at the sole owner, repairing torn tails and rotating on demand."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._events: dict[str, HistoryEvent] = {}
        self._loaded: bool = False
        self._torn: bool = False
        self._day: date | None = None
        self._problem: str | None = None

    @property
    def problem(self) -> str | None:
        """Expose observation failure independently of authoritative execution state."""
        return self._problem

    def append(self, event: HistoryEvent, now: datetime) -> bool:
        """Attempt a durable append without making observation failure an execution failure."""
        try:
            if not self._prepare(now):
                return False
            if event.event_id in self._events or datetime.fromisoformat(event.occurred_at) < self._cutoff(now):
                return False
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("ab") as stream:
                stream.write(TypeAdapter(HistoryEvent).dump_json(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._events[event.event_id] = event
            self._problem = None
        except OSError, ValueError:
            self._loaded = False
            self._set_problem("history_unavailable")
            return False
        return True

    def events(self, now: datetime) -> tuple[HistoryEvent, ...]:
        """Read retained observations without consulting or changing execution state."""
        try:
            self._prepare(now)
        except OSError, ValueError:
            self._set_problem("history_unavailable")
        return tuple(
            item for item in self._events.values() if datetime.fromisoformat(item.occurred_at) >= self._cutoff(now)
        )

    def materials(self, now: datetime, query: str = "") -> tuple[HistoryEvent, ...]:
        """Group terminal observations by default, or matching retained boundaries for a search."""
        latest: dict[str, HistoryEvent] = {}
        terminal: set[HistoryKind] = {
            HistoryKind.SUCCESS,
            HistoryKind.ERROR,
            HistoryKind.INTERRUPTED,
            HistoryKind.DELETE,
        }
        for event in sorted(self.events(now), key=lambda item: datetime.fromisoformat(item.occurred_at)):
            if (query and query.casefold() in event.name.casefold()) or (not query and event.kind in terminal):
                latest[event.material_id] = event
        result: tuple[HistoryEvent, ...] = tuple(
            item
            for item in sorted(latest.values(), key=lambda item: datetime.fromisoformat(item.occurred_at), reverse=True)
        )
        return result if query else result[:HISTORY_LIMIT]

    @staticmethod
    def _cutoff(now: datetime) -> datetime:
        return now.astimezone(UTC) - timedelta(days=RETENTION_DAYS)

    def _set_problem(self, problem: str) -> None:
        if self._problem != problem:
            logger.warning("Operational history is unavailable", reason=problem)
        self._problem = problem

    def _prepare(self, now: datetime) -> bool:
        if self._problem == "history_corrupt":
            return False
        if not self._loaded:
            self._load()
        if self._problem == "history_corrupt":
            return False
        day: date = now.astimezone(UTC).date()
        if self._day == day and not self._torn:
            return True
        retained: dict[str, HistoryEvent] = {
            key: item
            for key, item in self._events.items()
            if datetime.fromisoformat(item.occurred_at) >= self._cutoff(now)
        }
        if self._torn or len(retained) != len(self._events):
            self._rewrite(retained)
        self._events = retained
        self._day = day
        self._problem = None
        return True

    def _load(self) -> None:
        try:
            data: bytes = self._path.read_bytes()
        except FileNotFoundError:
            data = b""
        lines: list[bytes] = data.splitlines(keepends=True)
        loaded: dict[str, HistoryEvent] = {}
        self._torn = bool(data and not data.endswith(b"\n"))
        for index, line in enumerate(lines):
            try:
                event: HistoryEvent = TypeAdapter(HistoryEvent).validate_json(line, strict=True)
            except ValueError:
                if index != len(lines) - 1:
                    self._set_problem("history_corrupt")
                    return
                self._torn = True
                break
            loaded[event.event_id] = event
        self._events = loaded
        self._loaded = True
        self._day = None

    def _rewrite(self, events: dict[str, HistoryEvent]) -> None:
        temporary: Path = self._path.with_suffix(".jsonl.tmp")
        with temporary.open("wb") as stream:
            for item in events.values():
                stream.write(TypeAdapter(HistoryEvent).dump_json(item) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self._path)
        self._torn = False
