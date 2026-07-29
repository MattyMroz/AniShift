"""Thread-safe stream of narration batches ready for TTS and audio."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from anishift.errors import ErrorContext
from anishift.pipeline.narration import NarrationBatch
from anishift.services.audio.types import AudioRenderResult
from anishift.services.tts.types import SpeechBatchResult

__all__ = [
    "TtsQueueConfig",
    "TtsQueueFailure",
    "TtsQueueInput",
    "TtsQueueJob",
    "TtsQueueOutcome",
    "run_tts_queue",
]

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Future and producer polling interval for responsive cancellation."""


@dataclass(frozen=True, slots=True)
class TtsQueueJob:
    """One pipeline-owned narration batch and its media inputs."""

    source: Path
    narration: NarrationBatch
    source_audio_path: Path | None
    temporary_root: Path
    post_process_tempo: float


@dataclass(frozen=True, slots=True)
class TtsQueueFailure:
    """Typed pipeline failure produced by TTS or audio composition."""

    step: Literal["tts", "audio"]
    context: ErrorContext
    disposition: Literal["failed", "not_processed"] = "failed"


@dataclass(frozen=True, slots=True)
class TtsQueueOutcome:
    """Terminal TTS and audio result for one queued source."""

    job: TtsQueueJob
    speech: SpeechBatchResult | None
    audio: AudioRenderResult | None
    failure: TtsQueueFailure | None
    audio_time_ms: float = 0.0


type TtsQueueWorker = Callable[[TtsQueueJob], TtsQueueOutcome]
"""Process one ready narration batch through TTS and audio."""

type TtsQueueTerminalFactory = Callable[[TtsQueueJob], TtsQueueOutcome]
"""Build a terminal result for a job not submitted after cancellation."""

type TtsQueueResultHandler = Callable[[TtsQueueOutcome], None]
"""Observe one terminal queue result on the coordinator thread."""

type TtsQueuePausePredicate = Callable[[TtsQueueOutcome], bool]
"""Return whether one result pauses every not-yet-submitted batch."""


@dataclass(frozen=True, slots=True)
class TtsQueueConfig:
    """Bound file-level concurrency and cancellation behavior."""

    max_active_batches: int
    cancel: threading.Event
    terminal_factory: TtsQueueTerminalFactory
    on_result: TtsQueueResultHandler | None = None
    pause_on_result: TtsQueuePausePredicate | None = None
    paused_factory: TtsQueueTerminalFactory | None = None

    def __post_init__(self) -> None:
        """Reject a queue that cannot make progress."""
        if self.max_active_batches <= 0:
            message: str = "TTS queue max_active_batches must be positive"
            raise ValueError(message)


class TtsQueueInput:
    """Open producer channel for narration jobs becoming ready over time."""

    __slots__ = ("_closed", "_condition", "_pending", "_rank")

    def __init__(self, discovery_order: Sequence[Path] = ()) -> None:
        """Create an open stream with stable natural discovery ranks."""
        self._condition: threading.Condition = threading.Condition()
        self._pending: deque[TtsQueueJob] = deque()
        self._closed: bool = False
        self._rank: dict[Path, int] = {path: index for index, path in enumerate(discovery_order)}

    def put(self, job: TtsQueueJob) -> None:
        """Publish one ready job and wake the coordinator."""
        with self._condition:
            if self._closed:
                message: str = "cannot enqueue after closing the TTS queue input"
                raise RuntimeError(message)
            self._pending.append(job)
            self._condition.notify_all()

    def close(self) -> None:
        """Signal that no later spoken-ready callback can publish a job."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def drain(self) -> tuple[tuple[TtsQueueJob, ...], bool]:
        """Take every currently ready job and return producer state."""
        with self._condition:
            jobs: tuple[TtsQueueJob, ...] = tuple(self._pending)
            self._pending.clear()
            return jobs, self._closed

    def wait(self) -> None:
        """Wait briefly for input closure or another ready job."""
        with self._condition:
            if not self._pending and not self._closed:
                self._condition.wait(_WAIT_POLL_SECONDS)

    def rank(self, job: TtsQueueJob) -> int:
        """Return the stable discovery rank, extending it for injected jobs."""
        with self._condition:
            if job.source not in self._rank:
                self._rank[job.source] = len(self._rank)
            return self._rank[job.source]


def run_tts_queue(
    queue_input: TtsQueueInput,
    *,
    worker: TtsQueueWorker,
    config: TtsQueueConfig,
) -> dict[Path, TtsQueueOutcome]:
    """Process streamed jobs while preserving priority among ready files."""
    pending: deque[TtsQueueJob] = deque()
    outcomes: dict[Path, TtsQueueOutcome] = {}
    input_closed: bool = False
    paused: bool = False
    with ThreadPoolExecutor(max_workers=config.max_active_batches) as pool:
        active: dict[Future[TtsQueueOutcome], TtsQueueJob] = {}
        while pending or active or not input_closed:
            ready, input_closed = queue_input.drain()
            if ready:
                pending = deque(
                    sorted(
                        (*pending, *ready),
                        key=queue_input.rank,
                    ),
                )
            while pending and len(active) < config.max_active_batches and not config.cancel.is_set() and not paused:
                job: TtsQueueJob = pending.popleft()
                active[pool.submit(worker, job)] = job
            if not active:
                if config.cancel.is_set():
                    break
                if not input_closed:
                    queue_input.wait()
                    continue
                break
            done, _not_done = wait(
                set(active),
                timeout=_WAIT_POLL_SECONDS,
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                job = active.pop(future)
                outcome: TtsQueueOutcome = future.result()
                outcomes[job.source] = outcome
                _notify(config.on_result, outcome)
                if config.pause_on_result is not None and config.pause_on_result(outcome):
                    paused = True
    remaining, _closed = queue_input.drain()
    pending.extend(remaining)
    terminal_factory: TtsQueueTerminalFactory = (
        config.paused_factory
        if paused and not config.cancel.is_set() and config.paused_factory is not None
        else config.terminal_factory
    )
    for job in pending:
        outcome = terminal_factory(job)
        outcomes[job.source] = outcome
        _notify(config.on_result, outcome)
    return outcomes


def _notify(
    handler: TtsQueueResultHandler | None,
    outcome: TtsQueueOutcome,
) -> None:
    if handler is not None:
        handler(outcome)
