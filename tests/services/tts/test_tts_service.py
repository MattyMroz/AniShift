from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

import anishift.services.tts.service as tts_service_module
from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    ClipExpectation,
    ClipValidation,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineLocality,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchStatus,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
    SynthesisProfile,
    SynthesisRequest,
    SynthesisStatus,
    TtsCancelledError,
    TtsConfig,
    TtsConfigError,
    TtsRateLimitError,
    TtsService,
    VoiceInfo,
)


class _Validator:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def validate_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
        self.calls.append(path)
        if path.is_file() and path.read_bytes() == b"valid":
            return ClipValidation(
                format=expectation.format,
                sample_rate=24000,
                channels=1,
                duration_ms=1000,
            )
        return None


class _Progress:
    def __init__(self) -> None:
        self.batches: list[SpeechBatchProgress] = []
        self.requests: list[SpeechRequestProgress] = []
        self.retries: list[SpeechRetryProgress] = []

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        self.batches.append(state)

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        self.requests.append(update)

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        self.retries.append(update)


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
        max_text_chars=100,
        max_text_bytes=400,
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
        self.calls = 0
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
        assert not cancel.is_cancelled
        self.calls += 1
        request.destination.write_bytes(b"valid")
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id="fake-model",
            voice_id="fake-voice",
            request_time_ms=2.0,
        )

    async def close(self) -> None:
        self.closed += 1


class _ResolvedVoiceEngine(_Engine):
    synthesis_profile = SynthesisProfile(
        engine_id="fake",
        endpoint_id="fake-endpoint",
        provider_model_id="resolved-model",
        resolved_voice_id="resolved-voice-id",
        provider_output_id="mp3",
        provider_source_format=AudioFormat.MP3,
        adapter_version="test-v1",
    )

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        del cancel
        self.calls += 1
        request.destination.write_bytes(b"valid")
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id="resolved-model",
            voice_id="resolved-voice-id",
            request_time_ms=1.0,
        )


def _config() -> TtsConfig:
    return TtsConfig(
        engine_id="fake",
        provider_model_id="fake-model",
        voice_id="fake-voice",
        max_concurrency=2,
        queue_capacity=4,
        request_timeout_s=5.0,
        shutdown_deadline_s=1.0,
    )


def _batch() -> SpeechBatch:
    return SpeechBatch(
        scope_id="episode-1",
        batch_rank=0,
        requests=(
            SpeechRequest(request_id="line-1", text="Dzień dobry.", request_rank=0),
            SpeechRequest(request_id="line-2", text="♪", request_rank=1),
        ),
    )


def test_service_commits_then_reuses_validated_resume_clip(tmp_path: Path) -> None:
    engine = _Engine()
    progress = _Progress()
    validator = _Validator()
    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=validator,
        engine_factory=lambda config: engine,
    ) as service:
        first = service.synthesize(_batch(), callbacks=progress)
        second = service.synthesize(_batch(), callbacks=progress)

    assert first.status is SpeechBatchStatus.COMPLETED
    assert first.requests[0].status is SynthesisStatus.SYNTHESIZED
    assert first.requests[1].status is SynthesisStatus.SKIPPED
    assert second.requests[0].status is SynthesisStatus.RESUME_HIT
    assert engine.calls == 1
    assert len(validator.calls) == 1
    assert engine.closed == 1
    assert {update.status for update in progress.requests[-2:]} == {
        SynthesisStatus.RESUME_HIT,
        SynthesisStatus.SKIPPED,
    }
    assert progress.batches[-1].total_required_requests == 1
    assert progress.batches[-1].committed_required_requests == 1


def test_service_reports_provider_response_before_clip_validation(tmp_path: Path) -> None:
    class _BlockingValidator(_Validator):
        def __init__(self) -> None:
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def validate_clip(
            self,
            path: Path,
            expectation: ClipExpectation,
        ) -> ClipValidation | None:
            self.entered.set()
            self.release.wait()
            return super().validate_clip(path, expectation)

    engine = _Engine()
    progress = _Progress()
    validator = _BlockingValidator()
    with (
        TtsService(
            _config(),
            resume_root=tmp_path,
            validator=validator,
            engine_factory=lambda config: engine,
        ) as service,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        synthesis = pool.submit(service.synthesize, _batch(), callbacks=progress)
        try:
            assert validator.entered.wait(timeout=1.0)
            assert any(
                state.received_required_requests == 1 and state.committed_required_requests == 0
                for state in progress.batches
            )
        finally:
            validator.release.set()
        result = synthesis.result(timeout=1.0)

    assert result.status is SpeechBatchStatus.COMPLETED


def test_service_stops_timer_after_batch_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    engine: _Engine = _Engine()
    stopped: list[bool] = []

    class _TimerProbe:
        def __init__(self, name: str, *, auto_start: bool) -> None:
            assert name == "tts_batch"
            assert auto_start

        def stop(self) -> int:
            assert engine.calls == 1
            stopped.append(True)
            return 1

        @property
        def duration_ms(self) -> float:
            assert stopped
            return 1.0

    monkeypatch.setattr(tts_service_module, "Timer", _TimerProbe)

    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    ) as service:
        service.synthesize(_batch(), callbacks=_Progress())

    assert stopped == [True]


def test_service_close_is_idempotent_and_rejects_new_calls(tmp_path: Path) -> None:
    engine = _Engine()
    service = TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    )
    service.synthesize(_batch(), callbacks=_Progress())
    service.close()
    service.close()

    assert engine.closed == 1
    with pytest.raises(TtsConfigError):
        service.synthesize(_batch(), callbacks=_Progress())


def test_service_cancel_wakes_active_provider_request(tmp_path: Path) -> None:
    class _BlockingEngine(_Engine):
        def __init__(self) -> None:
            super().__init__()
            self.started = threading.Event()

        async def synthesize(
            self,
            request: SynthesisRequest,
            *,
            cancel: CancellationToken,
        ) -> EngineClipResult:
            del request
            self.started.set()
            await cancel.wait()
            raise TtsCancelledError("cancelled")

    engine = _BlockingEngine()
    service = TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    )
    batch = SpeechBatch(
        scope_id="cancel-active",
        batch_rank=0,
        requests=(SpeechRequest(request_id="line-1", text="Tekst", request_rank=0),),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        synthesis = pool.submit(service.synthesize, batch, callbacks=_Progress())
        assert engine.started.wait(timeout=1.0)

        service.cancel()
        result = synthesis.result(timeout=1.0)

    service.close()
    assert result.status is SpeechBatchStatus.CANCELLED
    assert engine.closed == 1


def test_service_reports_immediate_system_engine_retry(tmp_path: Path) -> None:
    class _RetryEngine(_Engine):
        capabilities = EngineCapabilities(
            locality=EngineLocality.SYSTEM,
            native_output_formats=(AudioFormat.MP3,),
            supports_concurrency=False,
            supports_native_rate=False,
            supports_native_volume=False,
            supports_pitch=False,
            supports_voice_settings=False,
            requires_api_key=False,
            min_text_chars=1,
            max_text_chars=100,
            max_text_bytes=400,
            availability_probe=AvailabilityProbeKind.LOCAL,
        )

        async def synthesize(
            self,
            request: SynthesisRequest,
            *,
            cancel: CancellationToken,
        ) -> EngineClipResult:
            if self.calls == 0:
                self.calls += 1
                raise TtsRateLimitError("retry")
            return await super().synthesize(request, cancel=cancel)

    engine = _RetryEngine()
    progress = _Progress()
    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    ) as service:
        result = service.synthesize(
            SpeechBatch(
                scope_id="retry-system",
                batch_rank=0,
                requests=(SpeechRequest(request_id="line-1", text="Tekst", request_rank=0),),
            ),
            callbacks=progress,
        )

    assert result.status is SpeechBatchStatus.COMPLETED
    assert result.stats.retries == 1
    assert len(progress.retries) == 1
    assert progress.retries[0].retry_number == 1
    assert progress.retries[0].delay_s == 0.0


def test_service_accepts_engine_resolved_voice_identity(tmp_path: Path) -> None:
    engine = _ResolvedVoiceEngine()
    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    ) as service:
        result = service.synthesize(_batch(), callbacks=_Progress())

    assert result.status is SpeechBatchStatus.COMPLETED
    clip = result.requests[0].speech_clip
    assert clip is not None
    assert clip.provider_model_id == "resolved-model"
    assert clip.voice_id == "resolved-voice-id"


def test_close_during_loop_start_does_not_leak_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    original = TtsService._run_loop

    def delayed_start(service: TtsService) -> None:
        entered.set()
        release.wait()
        original(service)

    monkeypatch.setattr(TtsService, "_run_loop", delayed_start)
    service = TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: _Engine(),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        synthesis = pool.submit(service.synthesize, _batch(), callbacks=_Progress())
        assert entered.wait(timeout=1.0)
        closing = pool.submit(service.close)
        release.set()
        closing.result(timeout=1.0)
        with pytest.raises(TtsConfigError):
            synthesis.result(timeout=1.0)


def test_multichunk_local_failure_does_not_invent_retry(tmp_path: Path) -> None:
    engine = _Engine()
    long_text = " ".join(["długi"] * 40)
    batch = SpeechBatch(
        scope_id="episode-long",
        batch_rank=0,
        requests=(SpeechRequest(request_id="line-long", text=long_text, request_rank=0),),
    )
    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    ) as service:
        result = service.synthesize(batch, callbacks=_Progress())

    assert result.status is SpeechBatchStatus.FAILED
    assert result.requests[0].retries == 0
    assert result.stats.retries == 0
