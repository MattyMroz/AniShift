"""Synchronous facade over one run-scoped asynchronous TTS runtime."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Never, Self

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.cancellation import TtsCancellation
from anishift.services.tts.chunking import chunk_speech_text
from anishift.services.tts.engines import create_engine
from anishift.services.tts.errors import (
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfigError,
    TtsError,
    TtsUnsupportedError,
)
from anishift.services.tts.fingerprint import SynthesisIdentity
from anishift.services.tts.resume import CachedTtsClip, TtsResumeRepository
from anishift.services.tts.scheduler import ScheduledSynthesis, TtsScheduler
from anishift.services.tts.types import (
    ClipExpectation,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SpeechRequest,
    SpeechRequestProgress,
    SynthesisRequest,
    SynthesisStatus,
    SynthesizedRequest,
)
from anishift.services.tts.validation import is_speech_text, validate_speech_batch

if TYPE_CHECKING:
    from collections.abc import Callable

    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import (
        ClipAssembler,
        ClipValidator,
        TtsEngine,
        TtsProgressSink,
    )
    from anishift.services.tts.types import EngineClipResult

__all__ = ["TtsService"]

type TtsEngineFactory = Callable[[TtsConfig], TtsEngine]
"""Lazy engine constructor used by the run-scoped facade."""


@dataclass(frozen=True, slots=True)
class _RequestExecution:
    result: SynthesizedRequest
    provider_calls: int
    request_time_ms: float
    failure: ErrorContext | None = None


@dataclass(frozen=True, slots=True)
class _AttemptContext:
    config: TtsConfig
    repository: TtsResumeRepository
    expectation: ClipExpectation
    validator: ClipValidator
    engine_id: str


@dataclass(frozen=True, slots=True)
class _MissingContext:
    batch: SpeechBatch
    request: SpeechRequest
    chunks: tuple[str, ...]
    identity: SynthesisIdentity
    expectation: ClipExpectation
    repository: TtsResumeRepository
    engine: TtsEngine
    scheduler: TtsScheduler


class _ProviderAttempt:
    """Create isolated temp destinations and validate every provider attempt."""

    __slots__ = (
        "_config",
        "_current_path",
        "_current_request_id",
        "_engine_id",
        "_expectation",
        "_part_index",
        "_paths",
        "_repository",
        "_request",
        "_text",
        "_validator",
    )

    def __init__(
        self,
        *,
        context: _AttemptContext,
        request: SpeechRequest,
        text: str,
        part_index: int,
    ) -> None:
        """Store immutable request data and an attempt-local path registry."""
        self._config: TtsConfig = context.config
        self._request: SpeechRequest = request
        self._text: str = text
        self._part_index: int = part_index
        self._repository: TtsResumeRepository = context.repository
        self._expectation: ClipExpectation = context.expectation
        self._validator: ClipValidator = context.validator
        self._engine_id: str = context.engine_id
        self._paths: set[Path] = set()
        self._current_path: Path | None = None
        self._current_request_id: str = ""

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return every destination reserved across retries."""
        return tuple(self._paths)

    def request_for_attempt(self, attempt: int) -> SynthesisRequest:
        """Build one request with a destination unique to this payload attempt."""
        destination: Path = self._repository.temporary_clip_path(clip_format=self._expectation.format)
        self._paths.add(destination)
        request_id: str = f"{self._request.request_id}:part:{self._part_index}:attempt:{attempt}"
        self._current_path = destination
        self._current_request_id = request_id
        return SynthesisRequest(
            request_id=request_id,
            text=self._text,
            voice_id=self._config.voice_id,
            provider_model_id=self._config.provider_model_id,
            native_rate=self._config.native_rate,
            native_volume=self._config.native_volume,
            native_pitch=self._config.native_pitch,
            options=self._config.engine_options,
            destination=destination,
            deadline_s=self._config.request_timeout_s,
        )

    async def accept_result(self, result: EngineClipResult) -> EngineClipResult:
        """Decode-check a provider result before the scheduler accepts success."""
        if (
            result.path != self._current_path
            or result.request_id != self._current_request_id
            or result.format is not self._expectation.format
            or result.engine_id != self._engine_id
            or result.provider_model_id != self._config.provider_model_id
            or result.voice_id != self._config.voice_id
        ):
            raise _unowned_clip_error()
        validation = await asyncio.to_thread(
            self._validator.validate_clip,
            result.path,
            self._expectation,
        )
        if validation is None or validation.format is not self._expectation.format:
            result.path.unlink(missing_ok=True)
            raise _invalid_audio_error()
        return result


class TtsService:
    """Thread-safe sync API sharing one loop, scheduler, circuit, and engine."""

    __slots__ = (
        "_assembler",
        "_cancel",
        "_closed",
        "_config",
        "_engine",
        "_engine_factory",
        "_lifecycle_lock",
        "_loop",
        "_loop_ready",
        "_repositories",
        "_resume_root",
        "_scheduler",
        "_thread",
        "_validator",
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        resume_root: Path,
        validator: ClipValidator,
        assembler: ClipAssembler | None = None,
        engine_factory: TtsEngineFactory = create_engine,
    ) -> None:
        """Store dependencies while keeping provider construction lazy."""
        self._config: TtsConfig = config
        self._resume_root: Path = resume_root
        self._validator: ClipValidator = validator
        self._assembler: ClipAssembler | None = assembler
        self._engine_factory: TtsEngineFactory = engine_factory
        self._cancel: TtsCancellation = TtsCancellation()
        self._lifecycle_lock: threading.RLock = threading.RLock()
        self._closed: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._engine: TtsEngine | None = None
        self._scheduler: TtsScheduler | None = None
        self._repositories: dict[str, TtsResumeRepository] = {}

    def synthesize(
        self,
        batch: SpeechBatch,
        *,
        callbacks: TtsProgressSink,
    ) -> SpeechBatchResult:
        """Synthesize exactly one neutral batch on the shared runtime."""
        validated: SpeechBatch = validate_speech_batch(batch)
        loop: asyncio.AbstractEventLoop = self._ensure_loop()
        with self._lifecycle_lock:
            if self._closed or not loop.is_running():
                _raise_closed()
            future: concurrent.futures.Future[SpeechBatchResult] = asyncio.run_coroutine_threadsafe(
                self._run_batch(validated, callbacks),
                loop,
            )
        try:
            return future.result()
        except KeyboardInterrupt:
            self.cancel()
            raise

    def cancel(self) -> None:
        """Cancel the run once and close the late-result commit gate."""
        self._cancel.cancel()
        loop: asyncio.AbstractEventLoop | None = self._loop
        scheduler: TtsScheduler | None = self._scheduler
        if loop is not None and scheduler is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(scheduler.cancel_pending(), loop)

    def close(self) -> None:
        """Idempotently close admission and provider resources by deadline."""
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.cancel()
            loop: asyncio.AbstractEventLoop | None = self._loop
            thread: threading.Thread | None = self._thread
        if loop is None or thread is None:
            return
        future: concurrent.futures.Future[None] = asyncio.run_coroutine_threadsafe(
            self._shutdown_async(),
            loop,
        )
        try:
            future.result(timeout=self._config.shutdown_deadline_s)
        except concurrent.futures.TimeoutError:
            future.cancel()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=self._config.shutdown_deadline_s)

    def __enter__(self) -> Self:
        """Enter without creating a provider client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the shared runtime on every context-manager exit."""
        self.close()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lifecycle_lock:
            if self._closed:
                _raise_closed()
            existing_loop: asyncio.AbstractEventLoop | None = self._loop
            if existing_loop is not None:
                return existing_loop
            if self._thread is None:
                thread: threading.Thread = threading.Thread(
                    target=self._run_loop,
                    name="anishift-tts",
                    daemon=True,
                )
                self._thread = thread
                thread.start()
            ready: threading.Event = self._loop_ready
        ready.wait()
        loop: asyncio.AbstractEventLoop | None = self._loop
        if loop is None:
            _raise_closed()
        return loop

    def _run_loop(self) -> None:
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lifecycle_lock:
            self._loop = loop
            self._loop_ready.set()
        loop.run_forever()
        pending: set[asyncio.Task[object]] = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    async def _ensure_runtime(self) -> tuple[TtsEngine, TtsScheduler]:
        if self._engine is None:
            engine: TtsEngine = self._engine_factory(self._config)
            scheduler: TtsScheduler = TtsScheduler(
                engine,
                config=self._config,
            )
            self._engine = engine
            self._scheduler = scheduler
        if self._scheduler is None:
            _raise_closed()
        resolved_engine: TtsEngine | None = self._engine
        resolved_scheduler: TtsScheduler | None = self._scheduler
        if resolved_engine is None or resolved_scheduler is None:
            _raise_closed()
        return resolved_engine, resolved_scheduler

    async def _run_batch(
        self,
        batch: SpeechBatch,
        callbacks: TtsProgressSink,
    ) -> SpeechBatchResult:
        total: int = len(batch.requests)
        generation: int = self._cancel.generation
        await _notify_batch(
            callbacks,
            SpeechBatchProgress(
                scope_id=batch.scope_id,
                completed_requests=0,
                total_requests=total,
                status=SpeechBatchStatus.COMPLETED if total == 0 else SpeechBatchStatus.PARTIAL,
            ),
            cancel=self._cancel,
            generation=generation,
        )
        if not any(is_speech_text(request.text) for request in batch.requests):
            executions: tuple[_RequestExecution, ...] = tuple(_skipped_execution(request) for request in batch.requests)
            for completed_count, execution in enumerate(executions, start=1):
                await _notify_execution(
                    callbacks,
                    batch.scope_id,
                    execution,
                    completed_count,
                    total,
                    executions[:completed_count],
                    cancel=self._cancel,
                    generation=generation,
                )
            return _batch_result_without_engine(batch, executions, self._config)

        engine, scheduler = await self._ensure_runtime()
        indexed_executions: list[tuple[int, _RequestExecution]] = []
        next_index: int = 0
        completed: int = 0
        state_lock: asyncio.Lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal completed, next_index
            while True:
                async with state_lock:
                    if next_index >= total:
                        return
                    index: int = next_index
                    next_index += 1
                request: SpeechRequest = batch.requests[index]
                execution: _RequestExecution = await self._execute_request(
                    batch,
                    request,
                    engine,
                    scheduler,
                )
                async with state_lock:
                    indexed_executions.append((index, execution))
                    completed += 1
                    snapshot: tuple[_RequestExecution, ...] = tuple(item for _, item in indexed_executions)
                    completed_count: int = completed
                await _notify_execution(
                    callbacks,
                    batch.scope_id,
                    execution,
                    completed_count,
                    total,
                    snapshot,
                    cancel=self._cancel,
                    generation=generation,
                )

        worker_count: int = min(total, self._config.queue_capacity)
        workers: tuple[asyncio.Task[None], ...] = tuple(
            asyncio.create_task(worker(), name=f"tts-batch-{batch.scope_id}-{index}") for index in range(worker_count)
        )
        await asyncio.gather(*workers)
        ordered: tuple[_RequestExecution, ...] = tuple(
            execution for _, execution in sorted(indexed_executions, key=lambda item: item[0])
        )
        return _batch_result(batch, ordered, engine)

    async def _execute_request(
        self,
        batch: SpeechBatch,
        request: SpeechRequest,
        engine: TtsEngine,
        scheduler: TtsScheduler,
    ) -> _RequestExecution:
        if not is_speech_text(request.text):
            return _skipped_execution(request)
        chunks: tuple[str, ...] = chunk_speech_text(
            request.text,
            max_chars=engine.capabilities.max_text_chars,
            max_bytes=engine.capabilities.max_text_bytes,
        )
        identity: SynthesisIdentity = SynthesisIdentity(
            scope_id=batch.scope_id,
            request_id=request.request_id,
            text=request.text,
            chunks=chunks,
            profile=engine.synthesis_profile,
        )
        expectation: ClipExpectation = ClipExpectation(format=engine.synthesis_profile.provider_source_format)
        repository: TtsResumeRepository = self._repository(batch.scope_id)
        cached: CachedTtsClip | None = await asyncio.to_thread(
            repository.lookup,
            identity,
            expectation,
        )
        if cached is not None:
            return _cached_execution(request, cached, engine)
        return await self._synthesize_missing(
            _MissingContext(
                batch=batch,
                request=request,
                chunks=chunks,
                identity=identity,
                expectation=expectation,
                repository=repository,
                engine=engine,
                scheduler=scheduler,
            )
        )

    async def _synthesize_missing(  # noqa: PLR0915 - explicit artifact lifecycle
        self,
        context: _MissingContext,
    ) -> _RequestExecution:
        batch: SpeechBatch = context.batch
        request: SpeechRequest = context.request
        chunks: tuple[str, ...] = context.chunks
        identity: SynthesisIdentity = context.identity
        expectation: ClipExpectation = context.expectation
        repository: TtsResumeRepository = context.repository
        engine: TtsEngine = context.engine
        scheduler: TtsScheduler = context.scheduler
        generation: int = self._cancel.generation
        provider_attempts: list[_ProviderAttempt] = []
        indexed_outcomes: list[tuple[int, ScheduledSynthesis]] = []
        next_part: int = 0
        part_lock: asyncio.Lock = asyncio.Lock()
        attempt_context = _AttemptContext(
            config=self._config,
            repository=repository,
            expectation=expectation,
            validator=self._validator,
            engine_id=engine.engine_id,
        )

        async def part_worker() -> None:
            nonlocal next_part
            while True:
                async with part_lock:
                    if next_part >= len(chunks):
                        return
                    part_index: int = next_part
                    next_part += 1
                provider_attempt = _ProviderAttempt(
                    context=attempt_context,
                    request=request,
                    text=chunks[part_index],
                    part_index=part_index,
                )
                provider_attempts.append(provider_attempt)
                outcome: ScheduledSynthesis = await scheduler.submit(
                    provider_attempt.request_for_attempt,
                    batch_rank=batch.batch_rank,
                    request_rank=request.request_rank,
                    cancel=self._cancel,
                    accept_result=provider_attempt.accept_result,
                )
                indexed_outcomes.append((part_index, outcome))

        part_worker_count: int = min(len(chunks), self._config.queue_capacity)
        part_workers: tuple[asyncio.Task[None], ...] = tuple(
            asyncio.create_task(part_worker()) for _ in range(part_worker_count)
        )
        await asyncio.gather(*part_workers)
        outcomes: tuple[ScheduledSynthesis, ...] = tuple(
            outcome for _, outcome in sorted(indexed_outcomes, key=lambda item: item[0])
        )
        attempts: int = sum(outcome.attempts for outcome in outcomes)
        request_time_ms: float = sum(outcome.clip.request_time_ms for outcome in outcomes if outcome.clip is not None)
        error: TtsError | None = next(
            (outcome.error for outcome in outcomes if outcome.error is not None),
            None,
        )
        clips: tuple[EngineClipResult, ...] = tuple(outcome.clip for outcome in outcomes if outcome.clip is not None)
        all_paths: tuple[Path, ...] = tuple(
            path for provider_attempt in provider_attempts for path in provider_attempt.paths
        )
        if error is not None or len(clips) != len(chunks):
            _discard_paths(all_paths)
            return _failed_execution(request, error or _incomplete_error(), attempts, request_time_ms)
        temporary: Path = clips[0].path
        if len(clips) > 1:
            if self._assembler is None:
                _discard_paths(all_paths)
                return _failed_execution(request, _missing_assembler_error(), attempts, request_time_ms)
            temporary = repository.temporary_clip_path(clip_format=expectation.format)
            try:
                await asyncio.to_thread(
                    self._assembler.join_clips,
                    tuple(clip.path for clip in clips),
                    temporary,
                    expectation,
                )
            except (OSError, RuntimeError, ValueError) as assembler_error:
                _discard_paths((*all_paths, temporary))
                failure: TtsClipValidationError = _assembly_error()
                failure.__cause__ = assembler_error
                return _failed_execution(request, failure, attempts, request_time_ms)
            _discard_paths(all_paths)
        try:
            committed: CachedTtsClip = await asyncio.to_thread(
                repository.commit_clip,
                identity,
                temporary,
                expectation,
                can_commit=lambda: self._cancel.can_commit(generation),
            )
        except TtsError as commit_error:
            _discard_paths(all_paths)
            return _failed_execution(request, commit_error, attempts, request_time_ms)
        _discard_paths(all_paths)
        speech_clip = SpeechClip(
            request_id=request.request_id,
            path=committed.path,
            format=committed.format,
            sample_rate=committed.sample_rate,
            channels=committed.channels,
            duration_ms=committed.duration_ms,
            engine_id=engine.engine_id,
            provider_model_id=self._config.provider_model_id,
            voice_id=self._config.voice_id,
            attempts=attempts,
            request_time_ms=request_time_ms,
            from_resume=False,
        )
        result = SynthesizedRequest(
            request=request,
            status=SynthesisStatus.SYNTHESIZED,
            speech_clip=speech_clip,
            error_code="",
            retries=max(0, attempts - len(chunks)),
        )
        return _RequestExecution(
            result=result,
            provider_calls=attempts,
            request_time_ms=request_time_ms,
        )

    def _repository(self, scope_id: str) -> TtsResumeRepository:
        repository: TtsResumeRepository | None = self._repositories.get(scope_id)
        if repository is None:
            root: Path = self._resume_root / scope_id / "tts"
            repository = TtsResumeRepository(root, scope_id, self._validator)
            self._repositories[scope_id] = repository
        return repository

    async def _shutdown_async(self) -> None:
        scheduler: TtsScheduler | None = self._scheduler
        engine: TtsEngine | None = self._engine
        if scheduler is not None:
            await scheduler.close()
        if engine is not None:
            await engine.close()
        await asyncio.get_running_loop().shutdown_default_executor()


def _cached_execution(
    request: SpeechRequest,
    cached: CachedTtsClip,
    engine: TtsEngine,
) -> _RequestExecution:
    clip = SpeechClip(
        request_id=request.request_id,
        path=cached.path,
        format=cached.format,
        sample_rate=cached.sample_rate,
        channels=cached.channels,
        duration_ms=cached.duration_ms,
        engine_id=engine.engine_id,
        provider_model_id=engine.synthesis_profile.provider_model_id,
        voice_id=engine.synthesis_profile.resolved_voice_id,
        attempts=0,
        request_time_ms=0.0,
        from_resume=True,
    )
    result = SynthesizedRequest(
        request=request,
        status=SynthesisStatus.RESUME_HIT,
        speech_clip=clip,
        error_code="",
        retries=0,
    )
    return _RequestExecution(result=result, provider_calls=0, request_time_ms=0.0)


def _skipped_execution(request: SpeechRequest) -> _RequestExecution:
    result = SynthesizedRequest(
        request=request,
        status=SynthesisStatus.SKIPPED,
        speech_clip=None,
        error_code="",
        retries=0,
    )
    return _RequestExecution(result=result, provider_calls=0, request_time_ms=0.0)


async def _notify_execution(  # noqa: PLR0913 - immutable progress snapshot
    callbacks: TtsProgressSink,
    scope_id: str,
    execution: _RequestExecution,
    completed: int,
    total: int,
    snapshot: tuple[_RequestExecution, ...],
    *,
    cancel: TtsCancellation,
    generation: int,
) -> None:
    if not cancel.can_commit(generation):
        return
    result: SynthesizedRequest = execution.result
    await _safe_callback(
        callbacks.on_request_committed,
        SpeechRequestProgress(
            scope_id=scope_id,
            request_id=result.request.request_id,
            status=result.status,
            attempts=execution.provider_calls,
        ),
    )
    await _notify_batch(
        callbacks,
        SpeechBatchProgress(
            scope_id=scope_id,
            completed_requests=completed,
            total_requests=total,
            status=_batch_status(tuple(item.result for item in snapshot), total),
        ),
        cancel=cancel,
        generation=generation,
    )


async def _notify_batch(
    callbacks: TtsProgressSink,
    progress: SpeechBatchProgress,
    *,
    cancel: TtsCancellation,
    generation: int,
) -> None:
    if cancel.can_commit(generation):
        await _safe_callback(callbacks.on_batch_state, progress)


async def _safe_callback[T](callback: Callable[[T], None], value: T) -> None:
    try:
        await asyncio.to_thread(callback, value)
    except Exception:  # noqa: BLE001 - observers cannot own domain execution
        return


def _failed_execution(
    request: SpeechRequest,
    error: TtsError,
    attempts: int,
    request_time_ms: float,
) -> _RequestExecution:
    status: SynthesisStatus = (
        SynthesisStatus.CANCELLED if isinstance(error, TtsCancelledError) else SynthesisStatus.FAILED
    )
    result = SynthesizedRequest(
        request=request,
        status=status,
        speech_clip=None,
        error_code=error.context.code.value,
        retries=max(0, attempts - 1),
    )
    return _RequestExecution(
        result=result,
        provider_calls=attempts,
        request_time_ms=request_time_ms,
        failure=error.context,
    )


def _batch_result(
    batch: SpeechBatch,
    executions: tuple[_RequestExecution, ...],
    engine: TtsEngine,
) -> SpeechBatchResult:
    requests: tuple[SynthesizedRequest, ...] = tuple(item.result for item in executions)
    failed: tuple[SynthesizedRequest, ...] = tuple(
        item for item in requests if item.status in {SynthesisStatus.FAILED, SynthesisStatus.CANCELLED}
    )
    stats = SpeechBatchStats(
        total_requests=len(requests),
        synthesized=sum(item.status is SynthesisStatus.SYNTHESIZED for item in requests),
        resume_hits=sum(item.status is SynthesisStatus.RESUME_HIT for item in requests),
        skipped=sum(item.status is SynthesisStatus.SKIPPED for item in requests),
        failed=len(failed),
        provider_calls=sum(item.provider_calls for item in executions),
        retries=sum(item.result.retries for item in executions),
        synthesis_time_ms=sum(item.request_time_ms for item in executions),
        engine_id=engine.engine_id,
        provider_model_id=engine.synthesis_profile.provider_model_id,
        voice_id=engine.synthesis_profile.resolved_voice_id,
    )
    status: SpeechBatchStatus = _batch_status(requests, len(requests))
    failure: ErrorContext | None = next(
        (item.failure for item in executions if item.failure is not None),
        None,
    )
    return SpeechBatchResult(
        scope_id=batch.scope_id,
        status=status,
        requests=requests,
        stats=stats,
        failure=failure,
    )


def _batch_result_without_engine(
    batch: SpeechBatch,
    executions: tuple[_RequestExecution, ...],
    config: TtsConfig,
) -> SpeechBatchResult:
    requests: tuple[SynthesizedRequest, ...] = tuple(item.result for item in executions)
    stats = SpeechBatchStats(
        total_requests=len(requests),
        synthesized=0,
        resume_hits=0,
        skipped=len(requests),
        failed=0,
        provider_calls=0,
        retries=0,
        synthesis_time_ms=0.0,
        engine_id=config.engine_id,
        provider_model_id=config.provider_model_id,
        voice_id=config.voice_id,
    )
    return SpeechBatchResult(
        scope_id=batch.scope_id,
        status=SpeechBatchStatus.COMPLETED,
        requests=requests,
        stats=stats,
        failure=None,
    )


def _batch_status(
    requests: tuple[SynthesizedRequest, ...],
    total: int,
) -> SpeechBatchStatus:
    if total == 0:
        return SpeechBatchStatus.COMPLETED
    cancelled: int = sum(item.status is SynthesisStatus.CANCELLED for item in requests)
    failed: int = sum(item.status is SynthesisStatus.FAILED for item in requests)
    if cancelled == total:
        return SpeechBatchStatus.CANCELLED
    if failed + cancelled == total:
        return SpeechBatchStatus.FAILED
    if failed or cancelled or len(requests) < total:
        return SpeechBatchStatus.PARTIAL
    return SpeechBatchStatus.COMPLETED


def _discard_paths(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _missing_assembler_error() -> TtsUnsupportedError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message="Long TTS input requires a provider-native clip assembler",
        suggestion="Provide the shared audio clip assembler dependency.",
    )
    return TtsUnsupportedError(context=context)


def _incomplete_error() -> TtsError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_FAILED,
        message="TTS provider did not return every requested chunk",
        suggestion="Retry the request to resume validated work.",
    )
    return TtsError(context=context)


def _unowned_clip_error() -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="TTS engine returned an unowned artifact path",
        suggestion="Retry the request; the invalid provider artifact was discarded.",
    )
    return TtsClipValidationError(context=context)


def _invalid_audio_error() -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="TTS engine returned an invalid audio clip",
        suggestion="Retry the request; the invalid provider artifact was discarded.",
    )
    return TtsClipValidationError(context=context)


def _assembly_error() -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="TTS chunks could not be assembled into one valid clip",
        suggestion="Retry the request or inspect the shared audio assembler.",
    )
    return TtsClipValidationError(context=context)


def _raise_closed() -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message="TTS service is closed",
        suggestion="Create one new run-scoped TTS service.",
    )
    raise TtsConfigError(context=context)
