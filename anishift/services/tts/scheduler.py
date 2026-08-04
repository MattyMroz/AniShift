"""Global asynchronous request scheduler for one TTS engine lifecycle."""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from anishift.errors import ErrorCode, ErrorContext, TransientError
from anishift.services.tts.errors import (
    TtsAuthError,
    TtsCancelledError,
    TtsConfigError,
    TtsError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsVoiceError,
)
from anishift.services.tts.types import EngineLocality
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import CancellationToken, TtsEngine
    from anishift.services.tts.types import EngineClipResult, SynthesisRequest

__all__ = ["ScheduledSynthesis", "TtsScheduler"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ScheduledSynthesis:
    """Terminal provider-attempt outcome returned to the TTS facade."""

    clip: EngineClipResult | None
    error: TtsError | None
    attempts: int


@dataclass(order=True, slots=True)
class _ReadyItem:
    key: tuple[int, float, int, int, int]
    work: _WorkItem = field(compare=False)


@dataclass(order=True, slots=True)
class _DelayedItem:
    ready_at: float
    sequence: int
    work: _WorkItem = field(compare=False)


@dataclass(slots=True)
class _WorkItem:
    request_factory: Callable[[int], SynthesisRequest]
    accept_result: Callable[[EngineClipResult], Awaitable[EngineClipResult]]
    on_result: Callable[[EngineClipResult], Awaitable[None]] | None
    batch_rank: int
    request_rank: int
    cancel: CancellationToken
    on_retry: Callable[[int, int, float, TtsError], Awaitable[None]] | None
    generation: int
    future: asyncio.Future[ScheduledSynthesis]
    attempts: int = 0


class TtsScheduler:
    """Bounded priority scheduler shared by every concurrent speech batch."""

    __slots__ = (
        "_accepting",
        "_admission",
        "_backoff_seconds",
        "_circuit_error",
        "_clock",
        "_condition",
        "_delayed",
        "_engine",
        "_max_retries",
        "_ready",
        "_sequence",
        "_stopping",
        "_timeout_s",
        "_workers",
    )

    def __init__(
        self,
        engine: TtsEngine,
        *,
        config: TtsConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a loop-owned scheduler without starting provider work."""
        self._engine: TtsEngine = engine
        self._max_retries: int = config.max_retries
        self._backoff_seconds: tuple[float, ...] = config.retry_backoff_seconds
        self._timeout_s: float | None = config.request_timeout_s if config.scheduler_timeout_enabled else None
        self._clock: Callable[[], float] = clock
        self._condition: asyncio.Condition = asyncio.Condition()
        self._admission: asyncio.Semaphore = asyncio.Semaphore(config.queue_capacity)
        self._accepting: set[asyncio.Task[None]] = set()
        self._ready: list[_ReadyItem] = []
        self._delayed: list[_DelayedItem] = []
        self._sequence: itertools.count[int] = itertools.count()
        self._circuit_error: TtsError | None = None
        self._stopping: bool = False
        self._workers: tuple[asyncio.Task[None], ...] = tuple(
            asyncio.create_task(self._worker(), name=f"tts-provider-{index}") for index in range(config.max_concurrency)
        )

    async def submit(  # noqa: PLR0913 - admission requires explicit ownership callbacks
        self,
        request_factory: Callable[[int], SynthesisRequest],
        *,
        batch_rank: int,
        request_rank: int,
        cancel: CancellationToken,
        accept_result: Callable[[EngineClipResult], Awaitable[EngineClipResult]],
        on_result: Callable[[EngineClipResult], Awaitable[None]] | None = None,
        on_retry: Callable[[int, int, float, TtsError], Awaitable[None]] | None = None,
    ) -> ScheduledSynthesis:
        """Admit one request and await its terminal provider outcome."""
        await self._admission.acquire()
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        future: asyncio.Future[ScheduledSynthesis] = loop.create_future()
        work: _WorkItem = _WorkItem(
            request_factory=request_factory,
            accept_result=accept_result,
            on_result=on_result,
            batch_rank=batch_rank,
            request_rank=request_rank,
            cancel=cancel,
            on_retry=on_retry,
            generation=cancel.generation,
            future=future,
        )
        async with self._condition:
            blocked_error: TtsError | None = self._admission_error(cancel)
            if blocked_error is not None:
                self._finish(work, error=blocked_error)
            else:
                self._push_ready(work, retry=False)
                self._condition.notify_all()
        return await asyncio.shield(future)

    async def close(self) -> None:
        """Stop admission, resolve queued work, and join worker tasks."""
        async with self._condition:
            if self._stopping:
                return
            self._stopping = True
            self._fail_queued(_cancelled_error("TTS scheduler is closing"))
            self._condition.notify_all()
        await asyncio.gather(*self._workers, return_exceptions=True)
        accepting: tuple[asyncio.Task[None], ...] = tuple(self._accepting)
        if accepting:
            await asyncio.gather(*accepting, return_exceptions=True)
        async with self._condition:
            self._fail_queued(_cancelled_error("TTS scheduler is closing"))

    async def cancel_pending(self) -> None:
        """Resolve ready and delayed work whose run token was cancelled."""
        async with self._condition:
            retained_ready: list[_ReadyItem] = []
            for ready_item in self._ready:
                if ready_item.work.cancel.is_cancelled:
                    self._finish(ready_item.work, error=_cancelled_error("TTS run was cancelled"))
                else:
                    retained_ready.append(ready_item)
            self._ready = retained_ready
            heapq.heapify(self._ready)
            retained_delayed: list[_DelayedItem] = []
            for delayed_item in self._delayed:
                if delayed_item.work.cancel.is_cancelled:
                    self._finish(delayed_item.work, error=_cancelled_error("TTS run was cancelled"))
                else:
                    retained_delayed.append(delayed_item)
            self._delayed = retained_delayed
            heapq.heapify(self._delayed)
            self._condition.notify_all()

    async def wake(self) -> None:
        """Wake workers after an injected test clock advances."""
        async with self._condition:
            self._condition.notify_all()

    async def _worker(self) -> None:
        while True:
            work: _WorkItem | None = await self._next_work()
            if work is None:
                return
            await self._attempt(work)

    async def _next_work(self) -> _WorkItem | None:
        async with self._condition:
            while True:
                self._promote_due_retries()
                if self._stopping:
                    return None
                if self._ready:
                    work: _WorkItem = heapq.heappop(self._ready).work
                    blocked_error: TtsError | None = self._admission_error(work.cancel)
                    if blocked_error is not None:
                        self._finish(work, error=blocked_error)
                        continue
                    return work
                timeout: float | None = self._next_retry_delay()
                try:
                    if timeout is None:
                        await self._condition.wait()
                    else:
                        await asyncio.wait_for(self._condition.wait(), timeout=timeout)
                except TimeoutError:
                    continue

    async def _attempt(self, work: _WorkItem) -> None:
        if not work.cancel.can_commit(work.generation):
            self._finish(work, error=_cancelled_error("TTS request cancelled before start"))
            return
        work.attempts += 1
        try:
            request: SynthesisRequest = work.request_factory(work.attempts)
            async with asyncio.timeout(self._timeout_s):
                clip: EngineClipResult = await self._engine.synthesize(
                    request,
                    cancel=work.cancel,
                )
        except asyncio.CancelledError:
            self._finish(work, error=_cancelled_error("TTS provider task cancelled"))
            return
        except TimeoutError as error:
            provider_error = TtsTimeoutError("TTS provider request timed out")
            provider_error.__cause__ = error
            await self._handle_error(work, provider_error)
            return
        except TtsError as error:
            await self._handle_error(work, error)
            return
        except Exception as error:  # noqa: BLE001 - isolate third-party engine failures
            mapped_error = TtsProviderUnavailableError("TTS engine failed outside its typed contract")
            mapped_error.__cause__ = error
            await self._handle_error(
                work,
                mapped_error,
            )
            return
        task: asyncio.Task[None] = asyncio.create_task(
            self._accept(work, clip),
            name=f"tts-accept-{work.batch_rank}-{work.request_rank}-{work.attempts}",
        )
        self._accepting.add(task)
        task.add_done_callback(self._accepting.discard)

    async def _accept(self, work: _WorkItem, clip: EngineClipResult) -> None:
        await self._notify_result(work, clip)
        try:
            accepted: EngineClipResult = await work.accept_result(clip)
        except asyncio.CancelledError:
            self._finish(work, error=_cancelled_error("TTS clip acceptance cancelled"))
            return
        except TtsError as error:
            await self._handle_error(work, error)
            return
        except Exception as error:  # noqa: BLE001 - isolate injected validation failures
            mapped_error = TtsProviderUnavailableError("TTS clip acceptance failed outside its typed contract")
            mapped_error.__cause__ = error
            await self._handle_error(
                work,
                mapped_error,
            )
            return
        if not work.cancel.can_commit(work.generation):
            self._finish(work, error=_cancelled_error("TTS result arrived after cancellation"))
            return
        self._finish(work, clip=accepted)

    @staticmethod
    async def _notify_result(work: _WorkItem, clip: EngineClipResult) -> None:
        if work.on_result is None:
            return
        try:
            await work.on_result(clip)
        except Exception:  # noqa: BLE001 - progress observers cannot own provider execution
            return

    async def _handle_error(self, work: _WorkItem, error: TtsError) -> None:
        if isinstance(error, TransientError) and work.attempts <= self._max_retries:
            delay: float = self._retry_delay(work.attempts, error)
            logger.bind(
                batch_rank=work.batch_rank,
                request_rank=work.request_rank,
                error_code=error.context.code.value,
                retry_number=work.attempts,
                max_retries=self._max_retries,
                delay_s=delay,
            ).warning(
                "TTS retry {retry}/{maximum} scheduled in {delay:.3f}s",
                retry=work.attempts,
                maximum=self._max_retries,
                delay=delay,
            )
            if work.on_retry is not None:
                await work.on_retry(
                    work.attempts,
                    self._max_retries,
                    delay,
                    error,
                )
            async with self._condition:
                sequence: int = next(self._sequence)
                heapq.heappush(
                    self._delayed,
                    _DelayedItem(
                        ready_at=self._clock() + delay,
                        sequence=sequence,
                        work=work,
                    ),
                )
                self._condition.notify_all()
            return
        logger.bind(
            batch_rank=work.batch_rank,
            request_rank=work.request_rank,
            error_code=error.context.code.value,
            attempts=work.attempts,
        ).error(
            "TTS request failed after {attempts} attempts",
            attempts=work.attempts,
        )
        if _opens_circuit(error):
            async with self._condition:
                if self._circuit_error is None:
                    self._circuit_error = error
                    self._fail_queued(error)
                self._condition.notify_all()
        self._finish(work, error=error)

    def _push_ready(
        self,
        work: _WorkItem,
        *,
        retry: bool,
        retry_ready_at: float = 0.0,
    ) -> None:
        sequence: int = next(self._sequence)
        priority_class: int = 0 if retry else 1
        ready_at: float = retry_ready_at if retry else 0.0
        key: tuple[int, float, int, int, int] = (
            priority_class,
            ready_at,
            work.batch_rank,
            work.request_rank,
            sequence,
        )
        heapq.heappush(self._ready, _ReadyItem(key=key, work=work))

    def _promote_due_retries(self) -> None:
        now: float = self._clock()
        while self._delayed and self._delayed[0].ready_at <= now:
            delayed: _DelayedItem = heapq.heappop(self._delayed)
            self._push_ready(
                delayed.work,
                retry=True,
                retry_ready_at=delayed.ready_at,
            )

    def _next_retry_delay(self) -> float | None:
        if not self._delayed:
            return None
        return max(0.0, self._delayed[0].ready_at - self._clock())

    def _retry_delay(self, attempts: int, error: TtsError) -> float:
        if self._engine.capabilities.locality is EngineLocality.SYSTEM:
            return 0.0
        index: int = min(attempts - 1, len(self._backoff_seconds) - 1)
        local_delay: float = self._backoff_seconds[index]
        retry_after: float | None = None
        if isinstance(error, (TtsRateLimitError, TtsProviderUnavailableError)):
            retry_after = error.retry_after_s
        if retry_after is None or retry_after < 0:
            return local_delay
        return max(local_delay, retry_after)

    def _admission_error(self, cancel: CancellationToken) -> TtsError | None:
        if self._stopping:
            return _cancelled_error("TTS scheduler is closed")
        if cancel.is_cancelled:
            return _cancelled_error("TTS run was cancelled")
        return self._circuit_error

    def _fail_queued(self, error: TtsError) -> None:
        pending: list[_WorkItem] = [item.work for item in self._ready]
        pending.extend(item.work for item in self._delayed)
        self._ready.clear()
        self._delayed.clear()
        for work in pending:
            self._finish(work, error=error)

    def _finish(
        self,
        work: _WorkItem,
        *,
        clip: EngineClipResult | None = None,
        error: TtsError | None = None,
    ) -> None:
        if work.future.done():
            return
        work.future.set_result(
            ScheduledSynthesis(
                clip=clip,
                error=error,
                attempts=work.attempts,
            )
        )
        self._admission.release()


def _opens_circuit(error: TtsError) -> bool:
    if isinstance(error, (TtsAuthError, TtsConfigError, TtsVoiceError)):
        return True
    return isinstance(error, TransientError)


def _cancelled_error(message: str) -> TtsCancelledError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.CANCELLED,
        message=message,
        suggestion="Run synthesis again to resume validated clips.",
    )
    return TtsCancelledError(context=context)
