from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineLocality,
    SynthesisProfile,
    SynthesisRequest,
    TtsCancellation,
    TtsConfig,
    TtsRateLimitError,
    VoiceInfo,
)
from anishift.services.tts.scheduler import TtsScheduler


def test_cancellation_wakes_many_waiters_from_another_thread() -> None:
    async def scenario() -> None:
        token = TtsCancellation()
        waiters = [asyncio.create_task(token.wait()) for _ in range(1_000)]
        await asyncio.sleep(0)
        thread = threading.Thread(target=token.cancel)
        thread.start()
        thread.join()
        await asyncio.wait_for(asyncio.gather(*waiters), timeout=1.0)
        await asyncio.wait_for(token.wait(), timeout=0.1)

    asyncio.run(scenario())


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Engine:
    engine_id = "fake"
    is_available = True
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=True,
        supports_native_rate=False,
        supports_native_volume=False,
        supports_pitch=False,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=None,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.CONFIG,
    )
    synthesis_profile = SynthesisProfile(
        engine_id="fake",
        endpoint_id="fake-v1",
        provider_model_id="fake-model",
        resolved_voice_id="fake-voice",
        provider_output_id="fake-mp3",
        provider_source_format=AudioFormat.MP3,
        adapter_version="fake:v1",
    )

    def __init__(self) -> None:
        self.calls: defaultdict[str, int] = defaultdict(int)
        self.started: asyncio.Queue[str] = asyncio.Queue()
        self.release: dict[str, asyncio.Event] = {}
        self.fail_once: set[str] = set()
        self.active = 0
        self.peak = 0
        self.closed = 0

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        del live
        return EngineAvailability(
            status=AvailabilityStatus.READY,
            message="ready",
            checked_at=datetime.now(UTC),
            source=AvailabilitySource.CONFIG,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        return ()

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        del cancel
        text = request.text
        self.calls[text] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        await self.started.put(text)
        gate = self.release.get(text)
        if gate is not None:
            await gate.wait()
        self.active -= 1
        if text in self.fail_once and self.calls[text] == 1:
            raise TtsRateLimitError("limited")
        request.destination.write_bytes(b"valid")
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id="fake-model",
            voice_id="fake-voice",
            request_time_ms=1.0,
        )

    async def close(self) -> None:
        self.closed += 1


def _config(*, concurrency: int = 2, retries: int = 3) -> TtsConfig:
    return TtsConfig(
        engine_id="fake",
        provider_model_id="fake-model",
        voice_id="fake-voice",
        max_concurrency=concurrency,
        queue_capacity=4,
        max_retries=retries,
        request_timeout_s=30.0,
        shutdown_deadline_s=1.0,
    )


def _factory(tmp_path: Path, text: str) -> Callable[[int], SynthesisRequest]:
    def build(attempt: int) -> SynthesisRequest:
        return SynthesisRequest(
            request_id=f"{text}-{attempt}",
            text=text,
            voice_id="fake-voice",
            provider_model_id="fake-model",
            native_rate=None,
            native_volume=None,
            native_pitch=None,
            options={},
            destination=tmp_path / f"{text}-{attempt}.mp3",
            deadline_s=30.0,
        )

    return build


async def _accept(result: EngineClipResult) -> EngineClipResult:
    return result


def test_scheduler_enforces_one_global_concurrency_limit(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = _Engine()
        token = TtsCancellation()
        for text in ("one", "two", "three"):
            engine.release[text] = asyncio.Event()
        scheduler = TtsScheduler(engine, config=_config(concurrency=2))
        tasks = [
            asyncio.create_task(
                scheduler.submit(
                    _factory(tmp_path, text),
                    batch_rank=index,
                    request_rank=0,
                    cancel=token,
                    accept_result=_accept,
                )
            )
            for index, text in enumerate(("one", "two", "three"))
        ]
        first = await engine.started.get()
        second = await engine.started.get()
        assert {first, second} == {"one", "two"}
        assert engine.peak == 2
        assert engine.started.empty()
        engine.release[first].set()
        third = await engine.started.get()
        assert third == "three"
        engine.release[second].set()
        engine.release[third].set()
        await asyncio.gather(*tasks)
        await scheduler.close()

    asyncio.run(scenario())


def test_retry_backoff_releases_slot_and_ready_retry_has_priority(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = _Clock()
        engine = _Engine()
        engine.fail_once.add("retry")
        token = TtsCancellation()
        scheduler = TtsScheduler(
            engine,
            config=_config(concurrency=1),
            clock=clock,
        )
        retry_task = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "retry"),
                batch_rank=0,
                request_rank=0,
                cancel=token,
                accept_result=_accept,
            )
        )
        assert await engine.started.get() == "retry"
        new_task = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "new"),
                batch_rank=1,
                request_rank=0,
                cancel=token,
                accept_result=_accept,
            )
        )
        assert await engine.started.get() == "new"
        clock.advance(15.0)
        await scheduler.wake()
        assert await engine.started.get() == "retry"
        retry_result, new_result = await asyncio.gather(retry_task, new_task)
        assert retry_result.attempts == 2
        assert new_result.attempts == 1
        assert engine.calls["retry"] == 2
        await scheduler.close()

    asyncio.run(scenario())


def test_max_retries_means_initial_attempt_plus_retries(tmp_path: Path) -> None:
    class _AlwaysLimited(_Engine):
        async def synthesize(
            self,
            request: SynthesisRequest,
            *,
            cancel: CancellationToken,
        ) -> EngineClipResult:
            del cancel
            self.calls[request.text] += 1
            await self.started.put(request.text)
            raise TtsRateLimitError("limited", retry_after_s=20.0)

    async def scenario() -> None:
        clock = _Clock()
        engine = _AlwaysLimited()
        scheduler = TtsScheduler(engine, config=_config(concurrency=1), clock=clock)
        task = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "limited"),
                batch_rank=0,
                request_rank=0,
                cancel=TtsCancellation(),
                accept_result=_accept,
            )
        )
        for delay in (20.0, 30.0, 60.0):
            assert await engine.started.get() == "limited"
            clock.advance(delay)
            await scheduler.wake()
        assert await engine.started.get() == "limited"
        result = await task
        assert result.attempts == 4
        assert isinstance(result.error, TtsRateLimitError)
        await scheduler.close()

    asyncio.run(scenario())


def test_cancel_resolves_delayed_retry_without_advancing_clock(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = _Clock()
        engine = _Engine()
        engine.fail_once.add("cancelled")
        token = TtsCancellation()
        scheduler = TtsScheduler(engine, config=_config(concurrency=1), clock=clock)
        task = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "cancelled"),
                batch_rank=0,
                request_rank=0,
                cancel=token,
                accept_result=_accept,
            )
        )
        assert await engine.started.get() == "cancelled"
        token.cancel()
        await scheduler.cancel_pending()
        result = await task
        assert result.attempts == 1
        assert result.error is not None
        assert result.error.context.code.value == "CANCELLED"
        await scheduler.close()

    asyncio.run(scenario())


def test_older_ready_retry_precedes_lower_rank_retry(tmp_path: Path) -> None:
    class _DifferentDelays(_Engine):
        async def synthesize(
            self,
            request: SynthesisRequest,
            *,
            cancel: CancellationToken,
        ) -> EngineClipResult:
            self.calls[request.text] += 1
            await self.started.put(request.text)
            if self.calls[request.text] == 1:
                delay = 15.0 if request.text == "older" else 30.0
                raise TtsRateLimitError("limited", retry_after_s=delay)
            del cancel
            request.destination.write_bytes(b"valid")
            return EngineClipResult(
                request_id=request.request_id,
                path=request.destination,
                format=AudioFormat.MP3,
                engine_id=self.engine_id,
                provider_model_id="fake-model",
                voice_id="fake-voice",
                request_time_ms=1.0,
            )

    async def scenario() -> None:
        clock = _Clock()
        engine = _DifferentDelays()
        scheduler = TtsScheduler(engine, config=_config(concurrency=1), clock=clock)
        token = TtsCancellation()
        older = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "older"),
                batch_rank=9,
                request_rank=0,
                cancel=token,
                accept_result=_accept,
            )
        )
        assert await engine.started.get() == "older"
        newer = asyncio.create_task(
            scheduler.submit(
                _factory(tmp_path, "newer"),
                batch_rank=0,
                request_rank=0,
                cancel=token,
                accept_result=_accept,
            )
        )
        assert await engine.started.get() == "newer"
        clock.advance(30.0)
        await scheduler.wake()
        assert await engine.started.get() == "older"
        assert await engine.started.get() == "newer"
        await asyncio.gather(older, newer)
        await scheduler.close()

    asyncio.run(scenario())
