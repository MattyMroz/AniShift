"""Concurrent per-run LLM file queue with ramp-up and a shared circuit breaker."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Never

from anishift.config.user_settings import ProcessingOrderPolicy
from anishift.errors import AniShiftError, ErrorCode, ErrorContext, TransientError
from anishift.pipeline.recovery import (
    RecoveryAction,
    RecoveryContext,
    RecoveryDomain,
    RecoveryHandler,
    rebuild_error_context,
)
from anishift.pipeline.types import FileOutcome
from anishift.services.llm.errors import (
    LlmCancelledError,
    LlmContextLengthError,
    LlmOutputBlockedError,
    LlmProviderUnavailableError,
)
from anishift.utils.logger import get_logger

__all__ = [
    "LlmFailureAction",
    "LlmProgressHandler",
    "LlmProgressState",
    "LlmQueueConfig",
    "LlmQueueInput",
    "SharedProviderState",
    "run_llm_queue",
]

LlmFailureAction = RecoveryAction
"""User decision after a provider has become unusable for the current run."""

type LlmQueueWorker = Callable[[Path, SharedProviderState], FileOutcome]
"""Translate one ready file with the shared provider resilience state."""

type LlmQueueWorkerFactory = Callable[[SharedProviderState], LlmQueueWorker]
"""Build worker-local composition after settings changes."""

type LlmFailureHandler = RecoveryHandler
"""Choose whether to reconfigure and retry pending files or finish partially."""

LlmProgressState = Literal["translating", "done", "failed", "cancelled", "not_processed"]
"""Lifecycle state reported for one file in the concurrent LLM queue."""

type LlmProgressHandler = Callable[[Path, LlmProgressState], None]
"""Render or record one file's concurrent LLM lifecycle transition."""

type NotProcessedFactory = Callable[[Path, ErrorContext], FileOutcome]
"""Build a terminal outcome for a file that was never submitted."""

# ── Constants ────────────────────────────────────────────────────────────────

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Condition and future polling interval for responsive cancellation."""

_PROVIDER_TERMINAL_CODES: Final[frozenset[str]] = frozenset(
    (
        ErrorCode.LLM_AUTH_FAILED.value,
        ErrorCode.LLM_CONFIG_INVALID.value,
        ErrorCode.LLM_MODEL_INVALID.value,
        ErrorCode.LLM_PAYMENT_REQUIRED.value,
        ErrorCode.LLM_PROVIDER_UNAVAILABLE.value,
        ErrorCode.LLM_QUOTA_EXHAUSTED.value,
        ErrorCode.LLM_RATE_LIMITED.value,
        ErrorCode.LLM_REQUEST_FAILED.value,
        ErrorCode.TIMEOUT.value,
        ErrorCode.CONFIG_INVALID.value,
    )
)
"""Failures that pause all new files after provider-level retries are exhausted."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LlmQueueConfig:
    """Dynamic scheduler configuration and terminal-failure interaction."""

    configured_limit: Callable[[], int]
    cancel: threading.Event
    on_provider_failure: LlmFailureHandler | None = None
    on_progress: LlmProgressHandler | None = None
    stop_on_failure: bool = False


class LlmQueueInput:
    """Thread-safe producer channel for files becoming ready after extraction."""

    __slots__ = ("_closed", "_condition", "_deferred", "_next_rank", "_pending", "_policy", "_rank")

    def __init__(
        self,
        discovery_order: Sequence[Path] = (),
        *,
        policy: ProcessingOrderPolicy = "ready_first",
    ) -> None:
        """Create an open channel with an optional natural discovery ranking."""
        self._condition = threading.Condition()
        self._pending: deque[Path] = deque()
        self._deferred: dict[int, Path | None] = {}
        self._closed = False
        self._next_rank = 0
        self._policy = policy
        self._rank = {path: index for index, path in enumerate(discovery_order)}

    def put(self, path: Path) -> None:
        """Enqueue one newly ready file."""
        with self._condition:
            if self._closed:
                msg = "cannot enqueue after closing the LLM queue input"
                raise RuntimeError(msg)
            if self._policy == "strict_natural":
                self._deferred[self._rank_for_path(path)] = path
                self._release_resolved()
            else:
                self._pending.append(path)
            self._condition.notify_all()

    def skip(self, path: Path) -> None:
        """Resolve one strict-order path that does not require translation."""
        if self._policy != "strict_natural":
            return
        with self._condition:
            if self._closed:
                msg = "cannot resolve after closing the LLM queue input"
                raise RuntimeError(msg)
            self._deferred[self._rank_for_path(path)] = None
            self._release_resolved()
            self._condition.notify_all()

    def close(self) -> None:
        """Signal that extraction will produce no more files."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def drain(self) -> tuple[tuple[Path, ...], bool]:
        """Return all currently ready files and the producer completion flag."""
        with self._condition:
            paths = tuple(self._pending)
            self._pending.clear()
            return paths, self._closed

    def wait(self) -> None:
        """Wait briefly for another ready file or producer completion."""
        with self._condition:
            if not self._pending and not self._closed:
                self._condition.wait(_WAIT_POLL_SECONDS)

    def rank(self, path: Path) -> int:
        """Return the stable discovery rank, extending it for unknown paths."""
        with self._condition:
            return self._rank_for_path(path)

    def take_deferred(self) -> tuple[Path, ...]:
        """Take strict-order paths blocked behind an unresolved earlier rank."""
        with self._condition:
            paths: tuple[Path, ...] = tuple(path for _rank, path in sorted(self._deferred.items()) if path is not None)
            self._deferred.clear()
            return paths

    def _rank_for_path(self, path: Path) -> int:
        """Return or allocate a rank while holding the condition lock."""
        if path not in self._rank:
            self._rank[path] = len(self._rank)
        return self._rank[path]

    def _release_resolved(self) -> None:
        """Publish the contiguous strict-order prefix while holding the lock."""
        while self._next_rank in self._deferred:
            path: Path | None = self._deferred.pop(self._next_rank)
            self._next_rank += 1
            if path is not None:
                self._pending.append(path)


class SharedProviderState:
    """Thread-safe per-run observer shared by worker-local LLM facades."""

    __slots__ = (
        "_attempt_threads",
        "_cancel",
        "_condition",
        "_disabled",
        "_open",
        "_probe_thread",
        "_ramp_limit",
    )

    def __init__(self, cancel: threading.Event) -> None:
        """Create a closed circuit using the configured healthy-run limit."""
        self._cancel = cancel
        self._condition = threading.Condition()
        self._disabled = False
        self._attempt_threads: set[int] = set()
        self._open = False
        self._probe_thread: int | None = None
        self._ramp_limit = 4

    @property
    def can_submit(self) -> bool:
        """Return whether the scheduler may start another file."""
        with self._condition:
            return not self._open and not self._disabled and not self._cancel.is_set()

    def concurrency_limit(self, configured_limit: int) -> int:
        """Return the healthy limit or the current post-failure ramp limit."""
        with self._condition:
            return min(max(1, configured_limit), self._ramp_limit)

    def before_attempt(self) -> None:
        """Acquire one shared provider-attempt slot or the exclusive probe."""
        thread_id = threading.get_ident()
        with self._condition:
            while True:
                if self._cancel.is_set():
                    _raise_cancelled()
                if self._disabled:
                    _raise_disabled()
                is_probe = self._probe_thread in (None, thread_id)
                below_limit = len(self._attempt_threads) < self._ramp_limit
                if (not self._open or is_probe) and below_limit:
                    self._attempt_threads.add(thread_id)
                    if self._open and self._probe_thread is None:
                        self._probe_thread = thread_id
                    return
                self._condition.wait(_WAIT_POLL_SECONDS)

    def on_transient_failure(self, error: TransientError) -> None:
        """Open the circuit and reserve the retry probe for this worker."""
        with self._condition:
            self._release_attempt_locked()
            self._open = True
            if self._probe_thread is None:
                self._probe_thread = threading.get_ident()
            self._ramp_limit = 1
            self._condition.notify_all()
        logger.warning(
            "LLM provider circuit opened",
            error_type=type(error).__name__,
            error_code=error.context.code.value,
            concurrency_limit=1,
        )

    def on_success(self) -> None:
        """Close a successful probe and grow scheduler capacity."""
        thread_id = threading.get_ident()
        with self._condition:
            self._release_attempt_locked()
            if self._open and self._probe_thread != thread_id:
                self._condition.notify_all()
                return
            self._open = False
            self._probe_thread = None
            self._ramp_limit = 2 if self._ramp_limit == 1 else 4
            self._condition.notify_all()
            ramp_limit = self._ramp_limit
        logger.info("LLM provider circuit healthy", concurrency_limit=ramp_limit)

    def on_fatal_failure(self, error: AniShiftError) -> None:
        """Release the attempt and block only run-wide provider failures."""
        with self._condition:
            self._release_attempt_locked()
            if not isinstance(error, (LlmContextLengthError, LlmOutputBlockedError)):
                self._disabled = True
            self._condition.notify_all()
        logger.warning(
            "LLM provider admission updated after fatal failure",
            disabled=self._disabled,
            error_type=type(error).__name__,
            error_code=error.context.code.value,
        )

    def disable(self) -> None:
        """Disable new attempts and wake workers waiting behind the circuit."""
        with self._condition:
            self._disabled = True
            self._condition.notify_all()

    def _release_attempt_locked(self) -> None:
        """Release the current thread's provider-attempt slot."""
        self._attempt_threads.discard(threading.get_ident())


def run_llm_queue(  # noqa: PLR0912,PLR0915 - explicit queue state transitions
    paths: Sequence[Path] | LlmQueueInput,
    *,
    worker_factory: LlmQueueWorkerFactory,
    not_processed_factory: NotProcessedFactory,
    config: LlmQueueConfig,
) -> dict[Path, FileOutcome]:
    """Run ready files in natural caller order and preserve partial outcomes."""
    queue_input = paths if isinstance(paths, LlmQueueInput) else _closed_input(paths)
    pending: deque[Path] = deque()
    outcomes: dict[Path, FileOutcome] = {}
    original_order: dict[Path, int] = {}
    state = SharedProviderState(config.cancel)
    worker = worker_factory(state)
    logger.info("LLM queue started", configured_limit=max(1, min(4, config.configured_limit())))
    with ThreadPoolExecutor(max_workers=4) as pool:
        active: dict[Future[FileOutcome], Path] = {}
        terminal_paths: list[Path] = []
        input_closed = False
        while pending or active or not input_closed:
            ready, input_closed = queue_input.drain()
            for path in ready:
                if path not in original_order:
                    original_order[path] = queue_input.rank(path)
            if ready:
                pending = deque(
                    sorted(
                        (*pending, *ready),
                        key=queue_input.rank,
                    )
                )
            configured_limit = max(1, min(4, config.configured_limit()))
            limit = state.concurrency_limit(configured_limit)
            while pending and len(active) < limit and state.can_submit:
                path = pending.popleft()
                _notify_progress(config.on_progress, path, "translating", config.cancel)
                logger.debug("LLM file admitted", source=path.name, active_files=len(active) + 1, limit=limit)
                active[pool.submit(worker, path, state)] = path
            if not active:
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
                path = active.pop(future)
                outcome = future.result()
                outcomes[path] = outcome
                logger.debug("LLM file completed", source=path.name, status=outcome.status)
                _notify_progress(config.on_progress, path, outcome.status, config.cancel)
                if _is_provider_terminal(outcome) or (config.stop_on_failure and outcome.failure is not None):
                    terminal_paths.append(path)
                    state.disable()
                    logger.warning(
                        "LLM queue paused after provider failure",
                        source=path.name,
                        error_code=outcome.failure.code if outcome.failure is not None else "unknown",
                    )
            if terminal_paths and not active and input_closed:
                recovered = _recover_provider(
                    worker_factory,
                    config,
                    outcomes,
                    pending,
                    terminal_paths,
                    original_order,
                )
                if recovered is None:
                    break
                state, worker = recovered
                continue
    pending.extend(queue_input.take_deferred())
    if pending:
        failure = outcomes[terminal_paths[0]].failure if terminal_paths else None
        context = ErrorContext(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message=failure.message if failure is not None else "LLM processing stopped",
            suggestion=failure.suggestion if failure is not None else "Open settings or retry later.",
        )
        for path in pending:
            outcomes[path] = not_processed_factory(path, context)
            _notify_progress(config.on_progress, path, "not_processed", config.cancel)
    logger.info(
        "LLM queue finished",
        completed=sum(outcome.status == "done" for outcome in outcomes.values()),
        failed=sum(outcome.status == "failed" for outcome in outcomes.values()),
        not_processed=sum(outcome.status == "not_processed" for outcome in outcomes.values()),
        cancelled=sum(outcome.status == "cancelled" for outcome in outcomes.values()),
    )
    return outcomes


def _recover_provider(  # noqa: PLR0913 - queue ownership remains explicit
    worker_factory: LlmQueueWorkerFactory,
    config: LlmQueueConfig,
    outcomes: dict[Path, FileOutcome],
    pending: deque[Path],
    terminal_paths: list[Path],
    original_order: dict[Path, int],
) -> tuple[SharedProviderState, LlmQueueWorker] | None:
    """Build a valid worker before returning failed files to the live queue."""
    recovery_error: ErrorContext | None = None
    while True:
        action = _failure_action(
            config.on_provider_failure,
            outcomes[terminal_paths[0]],
            outcomes,
            pending,
            terminal_paths,
            original_order,
            error_override=recovery_error,
        )
        logger.info(
            "LLM recovery action selected",
            action=action.value,
            failed_files=len(terminal_paths),
            pending_files=len(pending),
        )
        if action is RecoveryAction.FINISH:
            return None
        candidate_state = SharedProviderState(config.cancel)
        try:
            candidate_worker = worker_factory(candidate_state)
        except (AniShiftError, OSError, RuntimeError, ValueError) as exc:
            recovery_error = rebuild_error_context(exc, RecoveryDomain.LLM)
            logger.warning(
                "LLM recovery rebuild failed",
                error_type=type(exc).__name__,
                error_code=recovery_error.code.value,
            )
            continue
        retry_paths = sorted(set(terminal_paths), key=original_order.__getitem__)
        for path in retry_paths:
            outcomes.pop(path, None)
        pending.extendleft(reversed(retry_paths))
        terminal_paths.clear()
        return candidate_state, candidate_worker


def _notify_progress(
    handler: LlmProgressHandler | None,
    path: Path,
    state: LlmProgressState,
    cancel: threading.Event,
) -> None:
    """Report a queue transition when the caller supplied an observer."""
    if handler is not None and not cancel.is_set():
        handler(path, state)


def _closed_input(paths: Sequence[Path]) -> LlmQueueInput:
    """Build a closed producer channel for an already known sequence."""
    queue_input = LlmQueueInput(paths)
    for path in paths:
        queue_input.put(path)
    queue_input.close()
    return queue_input


def _is_provider_terminal(outcome: FileOutcome) -> bool:
    """Return whether a file exposed a run-wide provider failure."""
    return outcome.failure is not None and outcome.failure.code in _PROVIDER_TERMINAL_CODES


def _failure_action(  # noqa: PLR0913 - immutable recovery snapshot inputs
    handler: LlmFailureHandler | None,
    outcome: FileOutcome,
    outcomes: dict[Path, FileOutcome],
    pending: deque[Path],
    terminal_paths: list[Path],
    original_order: dict[Path, int],
    *,
    error_override: ErrorContext | None = None,
) -> LlmFailureAction:
    """Ask the caller after active work drains, defaulting safely to finish."""
    if handler is None:
        return RecoveryAction.FINISH
    failure = outcome.failure
    if error_override is not None:
        error = error_override
    elif failure is None:
        error = ErrorContext(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message="LLM provider became unavailable",
        )
    else:
        error = ErrorContext(
            code=ErrorCode(failure.code),
            message=failure.message,
            suggestion=failure.suggestion,
        )
    order = original_order.__getitem__
    return handler(
        RecoveryContext(
            domain=RecoveryDomain.LLM,
            error=error,
            completed_files=tuple(
                sorted(
                    (path for path, result in outcomes.items() if result.status == "done"),
                    key=order,
                ),
            ),
            failed_files=tuple(sorted(set(terminal_paths), key=order)),
            pending_files=tuple(sorted(pending, key=order)),
        ),
    )


def _raise_cancelled() -> Never:
    """Raise a structured cancellation observed while waiting for a probe."""
    context = ErrorContext(code=ErrorCode.CANCELLED, message="LLM queue cancelled")
    raise LlmCancelledError(context=context)


def _raise_disabled() -> Never:
    """Raise a structured unavailable error after the provider is disabled."""
    context = ErrorContext(
        code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
        message="LLM provider disabled for this run",
        suggestion="Open settings or finish with completed files.",
    )
    raise LlmProviderUnavailableError(context=context)
