from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.bootstrap import AppContext
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline.narration import NarrationBatch, NarrationItem
from anishift.pipeline.tts_runtime import PipelineTtsRuntime
from anishift.services.audio import AudioConfig
from anishift.services.audio.service import AudioProgressSink
from anishift.services.audio.types import (
    AudioCodecProfile,
    AudioRenderRequest,
    AudioRenderResult,
    AudioRenderStatus,
    TimelinePolicy,
)
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SpeechRequest,
    SpeechRequestProgress,
    SynthesisStatus,
    SynthesizedRequest,
    TtsConfig,
)
from anishift.services.tts.protocols import TtsProgressSink


def test_runtime_from_context_maps_voice_and_audio_profiles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_init(self: PipelineTtsRuntime, **kwargs: object) -> None:
        del self
        captured.update(kwargs)

    monkeypatch.setattr(PipelineTtsRuntime, "__init__", fake_init)
    context = AppContext(Settings(), UserSettings(), tmp_path)

    PipelineTtsRuntime.from_context(
        context,
        discovery_order=(tmp_path / "Episode.mkv",),
        cancel=threading.Event(),
    )

    tts_config = cast("TtsConfig", captured["tts_config"])
    audio_config = cast("AudioConfig", captured["audio_config"])
    assert tts_config.engine_id == "elevenbytes"
    assert tts_config.voice_id == context.user_settings.resolved_tts_voice_id
    assert tts_config.max_concurrency == 12
    assert tts_config.metadata_cache_root is not None
    assert tts_config.metadata_cache_root.name == "config"
    assert audio_config.codec_profile is AudioCodecProfile.EAC3
    assert audio_config.timeline_policy is TimelinePolicy.SERIALIZE
    assert audio_config.voice_mix_offset_db == -2.0
    assert captured["post_process_tempo"] == 1.25


class _Progress:
    def __init__(self) -> None:
        self.audio_phases: list[tuple[str, str]] = []
        self.terminals: list[tuple[str, str]] = []

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        del state

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        self.audio_phases.append((scope_id, phase))

    def on_pipeline_terminal(self, scope_id: str, state: str) -> None:
        self.terminals.append((scope_id, state))

    def on_pipeline_retry(self, scope_id: str) -> None:
        del scope_id


class _Tts:
    def __init__(self, result: SpeechBatchResult) -> None:
        self.result = result
        self.closed = False
        self.cancelled = False
        self.batches: list[SpeechBatch] = []

    def synthesize(
        self,
        batch: SpeechBatch,
        *,
        callbacks: TtsProgressSink,
    ) -> SpeechBatchResult:
        del callbacks
        self.batches.append(batch)
        return self.result

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


class _Audio:
    def __init__(self) -> None:
        self.requests: list[AudioRenderRequest] = []

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        del cancel
        self.requests.append(request)
        if callbacks is not None:
            callbacks.on_audio_phase(request.scope_id, "mixing")
        return AudioRenderResult(
            scope_id=request.scope_id,
            status=AudioRenderStatus.COMPLETED,
            narrator_path=request.temporary_root / "narrator.wav",
            output_path=request.source_path.with_suffix(".eac3"),
            output_probe=None,
            placements=(),
            warnings=(),
            narration_fingerprint="narration",
            mix_fingerprint="mix",
        )


def _config() -> TtsConfig:
    return TtsConfig(
        engine_id="edge",
        provider_model_id="edge",
        voice_id="pl-PL-MarekNeural",
        max_concurrency=1,
        queue_capacity=4,
    )


def _narration() -> NarrationBatch:
    first = SpeechRequest(request_id="request-one", text="Pierwsza", request_rank=0)
    second = SpeechRequest(request_id="request-two", text="Druga", request_rank=1)
    return NarrationBatch(
        speech=SpeechBatch(
            scope_id="scope-runtime",
            batch_rank=0,
            requests=(first, second),
        ),
        items=(
            NarrationItem(request=first, start_ms=100, end_ms=900, source_order=10),
            NarrationItem(request=second, start_ms=1200, end_ms=1900, source_order=20),
        ),
    )


def _speech_result(
    tmp_path: Path,
    narration: NarrationBatch | None = None,
) -> SpeechBatchResult:
    narration = narration or _narration()
    clips: dict[str, SpeechClip] = {}
    for request in narration.speech.requests:
        path = tmp_path / f"{request.request_id}.mp3"
        path.write_bytes(b"audio")
        clips[request.request_id] = SpeechClip(
            request_id=request.request_id,
            path=path,
            format=AudioFormat.MP3,
            sample_rate=24000,
            channels=1,
            duration_ms=500,
            engine_id="edge",
            provider_model_id="edge",
            voice_id="pl-PL-MarekNeural",
            attempts=1,
            request_time_ms=10.0,
            from_resume=False,
        )
    requests = tuple(
        SynthesizedRequest(
            request=request,
            status=SynthesisStatus.SYNTHESIZED,
            speech_clip=clips[request.request_id],
            error_code="",
            retries=0,
        )
        for request in reversed(narration.speech.requests)
    )
    return SpeechBatchResult(
        scope_id=narration.speech.scope_id,
        status=SpeechBatchStatus.COMPLETED,
        requests=requests,
        stats=SpeechBatchStats(
            total_requests=2,
            synthesized=2,
            resume_hits=0,
            skipped=0,
            failed=0,
            provider_calls=2,
            retries=0,
            synthesis_time_ms=20.0,
            engine_id="edge",
            provider_model_id="edge",
            voice_id="pl-PL-MarekNeural",
        ),
        failure=None,
    )


def test_runtime_joins_reordered_tts_results_by_request_id(tmp_path: Path) -> None:
    tts = _Tts(_speech_result(tmp_path))
    audio = _Audio()
    progress = _Progress()
    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.25,
        callbacks=progress,
        tts_service=tts,
        audio_service=audio,
    )
    runtime.put(source, _narration(), source_audio_path=None)
    outcomes = runtime.wait()
    runtime.close()

    request = audio.requests[0]
    clips = {clip.request_id: clip for clip in request.clips}
    assert clips["request-one"].start_ms == 100
    assert clips["request-one"].source_order == 10
    assert clips["request-two"].start_ms == 1200
    assert clips["request-two"].source_order == 20
    assert request.post_process_tempo == 1.25
    assert request.temporary_root == tmp_path / "tmp" / "scope-runtime" / "audio"
    assert outcomes[source].failure is None
    assert progress.audio_phases == [("scope-runtime", "mixing")]
    assert progress.terminals == [("scope-runtime", "done")]
    assert outcomes[source].audio_time_ms >= 0
    assert tts.closed


def test_terminal_progress_observer_cannot_fail_queue_execution(tmp_path: Path) -> None:
    class _ThrowingTerminal(_Progress):
        def on_pipeline_terminal(self, scope_id: str, state: str) -> None:
            del scope_id, state
            raise RuntimeError("renderer unavailable")

    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        callbacks=_ThrowingTerminal(),
        tts_service=_Tts(_speech_result(tmp_path)),
        audio_service=_Audio(),
    )
    runtime.put(source, _narration(), source_audio_path=None)

    outcome = runtime.wait()[source]
    runtime.close()

    assert outcome.failure is None


def test_runtime_does_not_render_audio_after_failed_tts(tmp_path: Path) -> None:
    narration = _narration()
    failure = ErrorContext(code=ErrorCode.TTS_AUTH_FAILED, message="missing key")
    speech = SpeechBatchResult(
        scope_id=narration.speech.scope_id,
        status=SpeechBatchStatus.FAILED,
        requests=(),
        stats=SpeechBatchStats(
            total_requests=2,
            synthesized=0,
            resume_hits=0,
            skipped=0,
            failed=2,
            provider_calls=1,
            retries=0,
            synthesis_time_ms=1.0,
            engine_id="elevenlabs",
            provider_model_id="model",
            voice_id="voice",
        ),
        failure=failure,
    )
    tts = _Tts(speech)
    audio = _Audio()
    progress = _Progress()
    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        callbacks=progress,
        tts_service=tts,
        audio_service=audio,
    )
    runtime.put(source, narration, source_audio_path=None)
    outcome = runtime.wait()[source]
    runtime.close()

    assert outcome.failure is not None
    assert outcome.failure.step == "tts"
    assert outcome.failure.context is failure
    assert progress.terminals == [("scope-runtime", "failed")]
    assert not audio.requests


@pytest.mark.parametrize("invalid_result", ["scope", "missing", "clip_id"])
def test_runtime_rejects_incomplete_or_mismatched_tts_identity(
    invalid_result: str,
    tmp_path: Path,
) -> None:
    speech = _speech_result(tmp_path)
    if invalid_result == "scope":
        speech = replace(speech, scope_id="wrong-scope")
    elif invalid_result == "missing":
        speech = replace(speech, requests=speech.requests[:1])
    else:
        first = speech.requests[0]
        assert first.speech_clip is not None
        wrong_clip = replace(first.speech_clip, request_id="wrong-request")
        speech = replace(
            speech,
            requests=(replace(first, speech_clip=wrong_clip), *speech.requests[1:]),
        )
    tts = _Tts(speech)
    audio = _Audio()
    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        tts_service=tts,
        audio_service=audio,
    )
    runtime.put(source, _narration(), source_audio_path=None)

    outcome = runtime.wait()[source]
    runtime.close()

    assert outcome.failure is not None
    assert outcome.failure.step == "tts"
    assert outcome.failure.context.code is ErrorCode.PIPELINE_STEP_FAILED
    assert not audio.requests


def test_runtime_isolates_unexpected_audio_failure_per_file(tmp_path: Path) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    first_narration = _narration()
    second_speech = replace(first_narration.speech, scope_id="scope-second", batch_rank=1)
    second_narration = replace(first_narration, speech=second_speech)

    class _PerBatchTts:
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            del callbacks
            narration = first_narration if batch.scope_id == first_narration.speech.scope_id else second_narration
            return _speech_result(tmp_path, narration)

        def cancel(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _PerFileAudio(_Audio):
        def render(
            self,
            request: AudioRenderRequest,
            *,
            callbacks: AudioProgressSink | None = None,
            cancel: threading.Event | None = None,
        ) -> AudioRenderResult:
            if request.source_path == first:
                raise PermissionError("destination denied")
            return super().render(request, callbacks=callbacks, cancel=cancel)

    audio = _PerFileAudio()
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(first, second),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        max_active_batches=2,
        tts_service=_PerBatchTts(),
        audio_service=audio,
    )
    runtime.put(first, first_narration, source_audio_path=None)
    runtime.put(second, second_narration, source_audio_path=None)

    outcomes = runtime.wait()
    runtime.close()

    failure = outcomes[first].failure
    assert failure is not None
    assert failure.context.code is ErrorCode.IO_ERROR
    assert outcomes[second].failure is None
    assert outcomes[second].audio is not None


def test_runtime_pauses_later_batches_after_provider_wide_tts_failure(
    tmp_path: Path,
) -> None:
    first = tmp_path / "Episode 1.mkv"
    second = tmp_path / "Episode 2.mkv"
    first_narration = _narration()
    second_narration = replace(
        first_narration,
        speech=replace(
            first_narration.speech,
            scope_id="scope-second",
            batch_rank=1,
        ),
    )

    class _ProviderFailureTts:
        def __init__(self) -> None:
            self.scopes: list[str] = []

        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            del callbacks
            self.scopes.append(batch.scope_id)
            return SpeechBatchResult(
                scope_id=batch.scope_id,
                status=SpeechBatchStatus.FAILED,
                requests=(),
                stats=SpeechBatchStats(
                    total_requests=len(batch.requests),
                    synthesized=0,
                    resume_hits=0,
                    skipped=0,
                    failed=len(batch.requests),
                    provider_calls=1,
                    retries=0,
                    synthesis_time_ms=1.0,
                    engine_id="elevenlabs",
                    provider_model_id="model",
                    voice_id="voice",
                ),
                failure=ErrorContext(
                    code=ErrorCode.TTS_AUTH_FAILED,
                    message="auth",
                ),
            )

        def cancel(self) -> None:
            pass

        def close(self) -> None:
            pass

    tts = _ProviderFailureTts()
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(first, second),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        max_active_batches=1,
        tts_service=tts,
        audio_service=_Audio(),
    )
    runtime.put(first, first_narration, source_audio_path=None)
    runtime.put(second, second_narration, source_audio_path=None)

    outcomes = runtime.wait()
    runtime.close()

    assert tts.scopes == ["scope-runtime"]
    assert outcomes[first].failure is not None
    second_failure = outcomes[second].failure
    assert second_failure is not None
    assert second_failure.disposition == "not_processed"
