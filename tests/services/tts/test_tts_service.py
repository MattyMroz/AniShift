from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    SynthesisProfile,
    SynthesisRequest,
    SynthesisStatus,
    TtsConfig,
    TtsConfigError,
    TtsService,
    VoiceInfo,
)


class _Validator:
    def validate_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
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

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        self.batches.append(state)

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        self.requests.append(update)


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
    with TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        engine_factory=lambda config: engine,
    ) as service:
        first = service.synthesize(_batch(), callbacks=progress)
        second = service.synthesize(_batch(), callbacks=progress)

    assert first.status is SpeechBatchStatus.COMPLETED
    assert first.requests[0].status is SynthesisStatus.SYNTHESIZED
    assert first.requests[1].status is SynthesisStatus.SKIPPED
    assert second.requests[0].status is SynthesisStatus.RESUME_HIT
    assert engine.calls == 1
    assert engine.closed == 1
    assert {update.status for update in progress.requests[-2:]} == {
        SynthesisStatus.RESUME_HIT,
        SynthesisStatus.SKIPPED,
    }


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
