from __future__ import annotations

import threading
import time
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
    NormalizedClip,
    PcmStorage,
    TimedClip,
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
    assert tts_config.max_concurrency == 85
    assert tts_config.metadata_cache_root is not None
    assert tts_config.metadata_cache_root.name == "config"
    assert audio_config.codec_profile is AudioCodecProfile.EAC3
    assert audio_config.timeline_policy is TimelinePolicy.SERIALIZE
    assert audio_config.voice_mix_offset_db == -2.0
    assert captured["post_process_tempo"] == 1.25
    assert captured["max_active_batches"] == 4
    assert captured["processing_order_policy"] == "ready_first"


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


def test_runtime_prepares_committed_clip_before_tts_batch_returns(
    tmp_path: Path,
) -> None:
    narration = _narration()
    speech = _speech_result(tmp_path, narration)
    prepared = threading.Event()
    order: list[str] = []

    class _StreamingTts(_Tts):
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            result = self.result.requests[0]
            clip = result.speech_clip
            callbacks.on_request_committed(
                SpeechRequestProgress(
                    scope_id=batch.scope_id,
                    request_id=result.request.request_id,
                    status=result.status,
                    attempts=1,
                    clip=clip,
                ),
            )
            if not prepared.wait(timeout=1.0):
                raise RuntimeError("audio preparation did not overlap TTS")
            order.append("tts_return")
            return self.result

    class _StreamingAudio(_Audio):
        def prepare_clip(
            self,
            clip: TimedClip,
            *,
            temporary_root: Path,
            tempo: float,
            cancel: threading.Event | None,
        ) -> NormalizedClip:
            del tempo, cancel
            path = temporary_root / f"{clip.request_id}.pcm"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\0\0")
            order.append("prepare")
            prepared.set()
            return NormalizedClip(
                timed_clip=clip,
                path=path,
                sample_rate=48000,
                sample_width=2,
                channels=1,
                frame_count=1,
                storage=PcmStorage.RAW,
                from_fast_path=False,
            )

        def render(
            self,
            request: AudioRenderRequest,
            *,
            callbacks: AudioProgressSink | None = None,
            cancel: threading.Event | None = None,
        ) -> AudioRenderResult:
            order.append("render")
            return super().render(request, callbacks=callbacks, cancel=cancel)

    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(normalization_concurrency=2),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        tts_service=_StreamingTts(speech),
        audio_service=_StreamingAudio(),
    )
    runtime.put(source, narration, source_audio_path=None)

    outcome = runtime.wait()[source]
    runtime.close()

    assert outcome.failure is None
    assert order == ["prepare", "tts_return", "render"]


def test_runtime_caps_streaming_normalization_globally_across_files(
    tmp_path: Path,
) -> None:
    first_source = tmp_path / "Episode 1.mkv"
    second_source = tmp_path / "Episode 2.mkv"
    first_narration = _narration()
    second_narration = replace(
        first_narration,
        speech=replace(first_narration.speech, scope_id="scope-second", batch_rank=1),
    )
    results = {
        first_narration.speech.scope_id: _speech_result(tmp_path, first_narration),
        second_narration.speech.scope_id: _speech_result(tmp_path, second_narration),
    }

    class _ConcurrentTts(_Tts):
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            result = results[batch.scope_id]
            for item in result.requests:
                callbacks.on_request_committed(
                    SpeechRequestProgress(
                        scope_id=batch.scope_id,
                        request_id=item.request.request_id,
                        status=item.status,
                        attempts=1,
                        clip=item.speech_clip,
                    ),
                )
            return result

    class _GloballyBoundedAudio(_Audio):
        def __init__(self) -> None:
            super().__init__()
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def prepare_clip(
            self,
            clip: TimedClip,
            *,
            temporary_root: Path,
            tempo: float,
            cancel: threading.Event | None,
        ) -> NormalizedClip:
            del tempo, cancel
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(0.05)
                path = temporary_root / f"{clip.request_id}.pcm"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"\0\0")
            finally:
                with self.lock:
                    self.active -= 1
            return NormalizedClip(
                timed_clip=clip,
                path=path,
                sample_rate=48000,
                sample_width=2,
                channels=1,
                frame_count=1,
                storage=PcmStorage.RAW,
                from_fast_path=False,
            )

    audio = _GloballyBoundedAudio()
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(normalization_concurrency=2),
        workspace_root=tmp_path,
        discovery_order=(first_source, second_source),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        max_active_batches=2,
        tts_service=_ConcurrentTts(results[first_narration.speech.scope_id]),
        audio_service=audio,
    )
    runtime.put(first_source, first_narration, source_audio_path=None)
    runtime.put(second_source, second_narration, source_audio_path=None)

    outcomes = runtime.wait()
    runtime.close()

    assert all(outcome.failure is None for outcome in outcomes.values())
    assert audio.peak == 2


def test_runtime_focuses_tts_per_episode_and_overlaps_next_tts_with_audio(
    tmp_path: Path,
) -> None:
    first_source = tmp_path / "Episode 1.mkv"
    second_source = tmp_path / "Episode 2.mkv"
    first_narration = _narration()
    second_narration = replace(
        first_narration,
        speech=replace(
            first_narration.speech,
            scope_id="scope-second",
            batch_rank=1,
        ),
    )
    first_tts_started = threading.Event()
    release_first_tts = threading.Event()
    second_tts_started = threading.Event()
    first_audio_started = threading.Event()
    release_first_audio = threading.Event()

    class _FocusedTts:
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            del callbacks
            narration = first_narration if batch.scope_id == first_narration.speech.scope_id else second_narration
            if batch.scope_id == first_narration.speech.scope_id:
                first_tts_started.set()
                assert release_first_tts.wait(timeout=2.0)
            else:
                second_tts_started.set()
            return _speech_result(tmp_path, narration)

        def cancel(self) -> None:
            pass

        def close(self) -> None:
            pass

    class _BlockingFirstAudio(_Audio):
        def render(
            self,
            request: AudioRenderRequest,
            *,
            callbacks: AudioProgressSink | None = None,
            cancel: threading.Event | None = None,
        ) -> AudioRenderResult:
            if request.source_path == first_source:
                first_audio_started.set()
                assert release_first_audio.wait(timeout=2.0)
            return super().render(request, callbacks=callbacks, cancel=cancel)

    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(first_source, second_source),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        max_active_batches=2,
        tts_service=_FocusedTts(),
        audio_service=_BlockingFirstAudio(),
    )
    runtime.put(first_source, first_narration, source_audio_path=None)
    runtime.put(second_source, second_narration, source_audio_path=None)

    assert first_tts_started.wait(timeout=1.0)
    assert not second_tts_started.wait(timeout=0.05)
    release_first_tts.set()
    assert first_audio_started.wait(timeout=1.0)
    assert second_tts_started.wait(timeout=1.0)
    release_first_audio.set()
    outcomes = runtime.wait()
    runtime.close()

    assert all(outcome.failure is None for outcome in outcomes.values())


def test_ready_first_orders_waiting_tts_batches_by_natural_rank(tmp_path: Path) -> None:
    sources = tuple(tmp_path / f"Episode {rank}.mkv" for rank in range(1, 4))
    narrations = tuple(
        replace(
            _narration(),
            speech=replace(
                _narration().speech,
                scope_id=f"scope-{rank}",
                batch_rank=rank,
            ),
        )
        for rank in range(3)
    )
    first_started = threading.Event()
    release_first = threading.Event()
    observed: list[int] = []

    class _OrderedTts:
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            del callbacks
            observed.append(batch.batch_rank)
            if batch.batch_rank == 0:
                first_started.set()
                assert release_first.wait(timeout=2.0)
            return _speech_result(tmp_path, narrations[batch.batch_rank])

        def cancel(self) -> None:
            pass

        def close(self) -> None:
            pass

    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=sources,
        cancel=threading.Event(),
        post_process_tempo=1.0,
        max_active_batches=3,
        tts_service=_OrderedTts(),
        audio_service=_Audio(),
    )
    runtime.put(sources[0], narrations[0], source_audio_path=None)
    assert first_started.wait(timeout=1.0)
    runtime.put(sources[2], narrations[2], source_audio_path=None)
    runtime.put(sources[1], narrations[1], source_audio_path=None)
    release_first.set()
    outcomes = runtime.wait()
    runtime.close()

    assert observed == [0, 1, 2]
    assert all(outcome.failure is None for outcome in outcomes.values())


def test_runtime_attributes_streaming_preparation_failure_to_audio(
    tmp_path: Path,
) -> None:
    narration = _narration()
    speech = _speech_result(tmp_path, narration)

    class _CommittingTts(_Tts):
        def synthesize(
            self,
            batch: SpeechBatch,
            *,
            callbacks: TtsProgressSink,
        ) -> SpeechBatchResult:
            result = self.result.requests[0]
            callbacks.on_request_committed(
                SpeechRequestProgress(
                    scope_id=batch.scope_id,
                    request_id=result.request.request_id,
                    status=result.status,
                    attempts=1,
                    clip=result.speech_clip,
                ),
            )
            return self.result

    class _FailingPreparationAudio(_Audio):
        def prepare_clip(
            self,
            clip: TimedClip,
            *,
            temporary_root: Path,
            tempo: float,
            cancel: threading.Event | None,
        ) -> NormalizedClip:
            del clip, temporary_root, tempo, cancel
            raise RuntimeError("normalization worker failed")

    source = tmp_path / "Episode.mkv"
    runtime = PipelineTtsRuntime(
        tts_config=_config(),
        audio_config=AudioConfig(),
        workspace_root=tmp_path,
        discovery_order=(source,),
        cancel=threading.Event(),
        post_process_tempo=1.0,
        tts_service=_CommittingTts(speech),
        audio_service=_FailingPreparationAudio(),
    )
    runtime.put(source, narration, source_audio_path=None)

    outcome = runtime.wait()[source]
    runtime.close()

    assert outcome.failure is not None
    assert outcome.failure.step == "audio"
    assert outcome.failure.context.message == "Audio normalization failed: normalization worker failed"


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
        max_active_batches=2,
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
