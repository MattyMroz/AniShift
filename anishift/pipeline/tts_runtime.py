"""Composition adapter joining neutral TTS results with pipeline timing."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Final, Literal, Protocol, Self

from anishift.config.user_settings import config_path
from anishift.errors import ErrorCode, ErrorContext
from anishift.pipeline.tts_queue import (
    TtsQueueConfig,
    TtsQueueFailure,
    TtsQueueInput,
    TtsQueueJob,
    TtsQueueOutcome,
    run_tts_queue,
)
from anishift.platform.binaries import Binary, require_binary
from anishift.services.audio import AudioConfig, AudioService
from anishift.services.audio.commands import (
    CommandRunner,
    SubprocessRunner,
    join_clips_command,
)
from anishift.services.audio.errors import AudioError
from anishift.services.audio.probe import probe_audio, validate_decode
from anishift.services.audio.service import AudioProgressSink
from anishift.services.audio.types import (
    AudioCodecProfile,
    AudioRenderRequest,
    AudioRenderResult,
    TimedClip,
    TimelinePolicy,
)
from anishift.services.audio.types import (
    AudioFormat as RenderAudioFormat,
)
from anishift.services.tts import (
    ClipExpectation,
    ClipValidation,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStatus,
    SpeechRequestProgress,
    TtsConfig,
    TtsError,
    TtsService,
)
from anishift.services.tts.protocols import TtsProgressSink

from .narration import NarrationBatch, NarrationItem

if TYPE_CHECKING:
    from anishift.bootstrap import AppContext

__all__ = ["PipelineTtsProgressSink", "PipelineTtsRuntime"]

_DEFAULT_ENGINE_CONCURRENCY: Final[dict[str, int]] = {
    "edge": 8,
    "elevenbytes": 12,
    "elevenlabs": 4,
    "sapi": 1,
}
"""Measured or conservative fallback concurrency by engine."""


class _TtsBatchService(Protocol):
    def synthesize(
        self,
        batch: SpeechBatch,
        *,
        callbacks: TtsProgressSink,
    ) -> SpeechBatchResult:
        """Synthesize one neutral batch."""
        ...

    def cancel(self) -> None:
        """Cancel pending and active provider work."""
        ...

    def close(self) -> None:
        """Close provider resources."""
        ...


class _AudioRenderer(Protocol):
    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        """Render one final sidecar."""
        ...


class PipelineTtsProgressSink(TtsProgressSink, AudioProgressSink, Protocol):
    """Observe TTS commits and coarse audio phases for one pipeline run."""

    def on_pipeline_terminal(
        self,
        scope_id: str,
        state: Literal["done", "failed", "cancelled", "not_processed"],
    ) -> None:
        """Report the terminal state of one queued source."""
        ...


class _SilentPipelineProgress:
    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        del state

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        del scope_id, phase

    def on_pipeline_terminal(
        self,
        scope_id: str,
        state: Literal["done", "failed", "cancelled", "not_processed"],
    ) -> None:
        del scope_id, state


class _FfmpegClipAdapter:
    """Validate and assemble provider-native clips through audio primitives."""

    def __init__(
        self,
        *,
        cancel: threading.Event,
        runner: CommandRunner,
        ffmpeg: Path,
        ffprobe: Path,
        timeout_s: float,
    ) -> None:
        """Store process boundaries shared with the TTS facade."""
        self._cancel: threading.Event = cancel
        self._runner: CommandRunner = runner
        self._ffmpeg: Path = ffmpeg
        self._ffprobe: Path = ffprobe
        self._timeout_s: float = timeout_s

    def validate_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
        """Return trusted metadata only for a fully decodable expected format."""
        expected: RenderAudioFormat = RenderAudioFormat(expectation.format.value)
        try:
            probe = probe_audio(
                path,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
            validate_decode(
                path,
                ffmpeg=self._ffmpeg,
                runner=self._runner,
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
        except AudioError:
            return None
        if not _matches_format(expected, probe.codec_name, probe.format_name):
            return None
        return ClipValidation(
            format=expectation.format,
            sample_rate=probe.sample_rate,
            channels=probe.channels,
            duration_ms=probe.duration_ms,
        )

    def join_clips(
        self,
        paths: tuple[Path, ...],
        destination: Path,
        expectation: ClipExpectation,
    ) -> None:
        """Join ordered parts with FFmpeg and leave validation to commit."""
        expected: RenderAudioFormat = RenderAudioFormat(expectation.format.value)
        try:
            self._runner.run(
                join_clips_command(
                    self._ffmpeg,
                    paths,
                    destination,
                    clip_format=expected,
                ),
                operation="join_tts_clips",
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
        except AudioError as error:
            message: str = "Provider-native clip assembly failed"
            raise RuntimeError(message) from error


class PipelineTtsRuntime:
    """Own one streamed TTS queue, one TTS facade, and one audio renderer."""

    def __init__(  # noqa: PLR0913 - composition root accepts explicit dependencies
        self,
        *,
        tts_config: TtsConfig,
        audio_config: AudioConfig,
        workspace_root: Path,
        discovery_order: tuple[Path, ...],
        cancel: threading.Event,
        post_process_tempo: float,
        max_active_batches: int = 4,
        callbacks: PipelineTtsProgressSink | None = None,
        tts_service: _TtsBatchService | None = None,
        audio_service: _AudioRenderer | None = None,
    ) -> None:
        """Start the consumer before extraction can publish Polish speech."""
        self._cancel: threading.Event = cancel
        self._post_process_tempo: float = post_process_tempo
        self._workspace_root: Path = workspace_root
        self._callbacks: PipelineTtsProgressSink = callbacks or _SilentPipelineProgress()
        self._input: TtsQueueInput = TtsQueueInput(discovery_order)
        self._closed_input: bool = False
        self._closed: bool = False
        if tts_service is None:
            runner = SubprocessRunner(shutdown_grace_s=audio_config.shutdown_grace_s)
            clip_adapter = _FfmpegClipAdapter(
                cancel=cancel,
                runner=runner,
                ffmpeg=require_binary(Binary.FFMPEG),
                ffprobe=require_binary(Binary.FFPROBE),
                timeout_s=audio_config.operation_timeout_s,
            )
            resolved_tts: _TtsBatchService = TtsService(
                tts_config,
                resume_root=workspace_root / "tmp",
                validator=clip_adapter,
                assembler=clip_adapter,
            )
        else:
            resolved_tts = tts_service
        resolved_audio: _AudioRenderer = audio_service if audio_service is not None else AudioService(audio_config)
        self._tts: _TtsBatchService = resolved_tts
        self._audio: _AudioRenderer = resolved_audio
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._future: Future[dict[Path, TtsQueueOutcome]] = self._executor.submit(
            run_tts_queue,
            self._input,
            worker=self._process,
            config=TtsQueueConfig(
                max_active_batches=max_active_batches,
                cancel=cancel,
                terminal_factory=_cancelled_outcome,
                on_result=self._on_result,
            ),
        )

    @classmethod
    def from_context(
        cls,
        context: AppContext,
        *,
        discovery_order: tuple[Path, ...],
        cancel: threading.Event,
        callbacks: PipelineTtsProgressSink | None = None,
    ) -> PipelineTtsRuntime:
        """Resolve persisted and secret settings at the pipeline boundary."""
        preferences = context.user_settings
        profile = preferences.active_tts_profile
        concurrency: int = profile.concurrency or _DEFAULT_ENGINE_CONCURRENCY.get(
            preferences.tts_engine,
            1,
        )
        return cls(
            tts_config=TtsConfig(
                engine_id=preferences.tts_engine,
                provider_model_id=preferences.tts_provider_model_id,
                voice_id=preferences.resolved_tts_voice_id,
                max_concurrency=concurrency,
                queue_capacity=max(2, 2 * concurrency),
                max_retries=preferences.tts_max_retries,
                native_rate=profile.native_rate,
                native_volume=profile.native_volume,
                native_pitch=profile.native_pitch,
                engine_options=profile.engine_options,
                elevenlabs_api_key=context.settings.elevenlabs_api_key,
                metadata_cache_root=config_path().parent,
            ),
            audio_config=AudioConfig(
                codec_profile=AudioCodecProfile(preferences.tts_output_profile),
                bitrate=preferences.tts_output_bitrate,
                narrator_mix_base_gain_db=preferences.narrator_mix_base_gain_db,
                voice_mix_offset_db=profile.voice_mix_offset_db,
                original_gain_db=preferences.original_gain_db,
                timeline_policy=TimelinePolicy(preferences.tts_timeline_policy),
            ),
            workspace_root=context.workspace_root,
            discovery_order=discovery_order,
            cancel=cancel,
            post_process_tempo=profile.postprocess_tempo,
            max_active_batches=min(4, concurrency),
            callbacks=callbacks,
        )

    def put(
        self,
        source: Path,
        narration: NarrationBatch,
        *,
        source_audio_path: Path | None,
    ) -> None:
        """Publish one ready narration without waiting for other files."""
        scope_id: str = narration.speech.scope_id
        self._input.put(
            TtsQueueJob(
                source=source,
                narration=narration,
                source_audio_path=source_audio_path,
                temporary_root=self._workspace_root / "tmp" / scope_id / "audio",
                post_process_tempo=self._post_process_tempo,
            ),
        )

    def close_input(self) -> None:
        """Close producer admission exactly once."""
        if self._closed_input:
            return
        self._closed_input = True
        self._input.close()

    def wait(self) -> dict[Path, TtsQueueOutcome]:
        """Wait for active synthesis, retries, and audio rendering."""
        self.close_input()
        return self._future.result()

    def cancel(self) -> None:
        """Cancel queue admission, TTS, and active FFmpeg operations."""
        self._cancel.set()
        self.close_input()
        self._tts.cancel()

    def close(self) -> None:
        """Close every owned lifecycle without discarding committed results."""
        if self._closed:
            return
        self._closed = True
        self.close_input()
        try:
            self._future.result()
        finally:
            self._tts.close()
            self._executor.shutdown(wait=True, cancel_futures=False)

    def __enter__(self) -> Self:
        """Return the already-started run-scoped runtime."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Cancel on exceptional exit and always close resources."""
        if exc_type is not None:
            self.cancel()
        self.close()

    def _process(self, job: TtsQueueJob) -> TtsQueueOutcome:  # noqa: PLR0911 - explicit terminal boundaries
        try:
            speech: SpeechBatchResult = self._tts.synthesize(
                job.narration.speech,
                callbacks=self._callbacks,
            )
        except TtsError as error:
            return _failed_outcome(job, step="tts", context=error.context)
        except (OSError, RuntimeError, ValueError) as error:
            return _failed_outcome(
                job,
                step="tts",
                context=_unexpected_step_context("TTS", error),
            )
        if speech.status is not SpeechBatchStatus.COMPLETED:
            context: ErrorContext = speech.failure or ErrorContext(
                code=ErrorCode.TTS_FAILED,
                message="TTS did not complete every required speech request",
                suggestion="Retry synthesis or change the selected TTS engine.",
            )
            return _failed_outcome(job, step="tts", context=context, speech=speech)
        try:
            clips: tuple[TimedClip, ...] = _timed_clips(job.narration, speech)
        except ValueError as error:
            context = ErrorContext(
                code=ErrorCode.PIPELINE_STEP_FAILED,
                message=str(error),
                suggestion="Regenerate the narration batch before retrying TTS.",
            )
            return _failed_outcome(job, step="tts", context=context, speech=speech)
        try:
            audio_started_at: float = time.monotonic()
            audio: AudioRenderResult = self._audio.render(
                AudioRenderRequest(
                    scope_id=job.narration.speech.scope_id,
                    source_path=job.source,
                    source_audio_path=job.source_audio_path,
                    clips=clips,
                    temporary_root=job.temporary_root,
                    post_process_tempo=job.post_process_tempo,
                ),
                callbacks=self._callbacks,
                cancel=self._cancel,
            )
        except AudioError as error:
            return _failed_outcome(job, step="audio", context=error.context, speech=speech)
        except (OSError, RuntimeError, ValueError) as error:
            return _failed_outcome(
                job,
                step="audio",
                context=_unexpected_step_context("Audio rendering", error),
                speech=speech,
            )
        return TtsQueueOutcome(
            job=job,
            speech=speech,
            audio=audio,
            failure=None,
            audio_time_ms=(time.monotonic() - audio_started_at) * 1000,
        )

    def _on_result(self, outcome: TtsQueueOutcome) -> None:
        """Forward one queue terminal state without exposing queue internals."""
        state: Literal["done", "failed", "cancelled", "not_processed"] = "done"
        if outcome.failure is not None:
            state = "cancelled" if outcome.failure.context.code is ErrorCode.CANCELLED else "failed"
        try:
            self._callbacks.on_pipeline_terminal(
                outcome.job.narration.speech.scope_id,
                state,
            )
        except Exception:  # noqa: BLE001 - observers cannot own queue execution
            return


def _timed_clips(
    narration: NarrationBatch,
    speech: SpeechBatchResult,
) -> tuple[TimedClip, ...]:
    if speech.scope_id != narration.speech.scope_id:
        message: str = f"TTS result scope mismatch: expected {narration.speech.scope_id}, received {speech.scope_id}"
        raise ValueError(message)
    items: dict[str, NarrationItem] = {item.request.request_id: item for item in narration.items}
    expected_ids: set[str] = {request.request_id for request in narration.speech.requests}
    returned_ids: list[str] = [result.request.request_id for result in speech.requests]
    if len(returned_ids) != len(set(returned_ids)):
        message = "TTS result contains duplicate request ids"
        raise ValueError(message)
    returned_id_set: set[str] = set(returned_ids)
    if returned_id_set != expected_ids:
        missing: list[str] = sorted(expected_ids - returned_id_set)
        unknown: list[str] = sorted(returned_id_set - expected_ids)
        message = f"TTS result request ids do not match the batch: missing={missing}, unknown={unknown}"
        raise ValueError(message)
    clips: list[TimedClip] = []
    seen: set[str] = set()
    for result in speech.requests:
        clip = result.speech_clip
        if clip is None:
            continue
        if clip.request_id != result.request.request_id:
            message = f"TTS clip id {clip.request_id} does not match result id {result.request.request_id}"
            raise ValueError(message)
        if clip.request_id in seen:
            duplicate_message: str = f"Duplicate TTS result id: {clip.request_id}"
            raise ValueError(duplicate_message)
        item: NarrationItem | None = items.get(clip.request_id)
        if item is None:
            message = f"Unknown TTS result id: {clip.request_id}"
            raise ValueError(message)
        seen.add(clip.request_id)
        clips.append(
            TimedClip(
                request_id=clip.request_id,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                source_order=item.source_order,
                clip_path=clip.path,
                clip_format=RenderAudioFormat(clip.format.value),
                sample_rate=clip.sample_rate,
                channels=clip.channels,
                duration_ms=clip.duration_ms,
            ),
        )
    return tuple(clips)


def _unexpected_step_context(
    operation: str,
    error: OSError | RuntimeError | ValueError,
) -> ErrorContext:
    code: ErrorCode = ErrorCode.IO_ERROR if isinstance(error, OSError) else ErrorCode.PIPELINE_STEP_FAILED
    suggestion: str = (
        "Check file permissions and free disk space, then retry this file."
        if isinstance(error, OSError)
        else "Retry this file; completed results for other files were preserved."
    )
    return ErrorContext(
        code=code,
        message=f"{operation} failed: {error}",
        suggestion=suggestion,
    )


def _matches_format(
    expected: RenderAudioFormat,
    codec_name: str,
    format_name: str,
) -> bool:
    formats: set[str] = set(format_name.split(","))
    if expected is RenderAudioFormat.WAV:
        return codec_name.startswith("pcm_") and "wav" in formats
    expected_identity: dict[RenderAudioFormat, tuple[str, str | None]] = {
        RenderAudioFormat.AAC: ("aac", None),
        RenderAudioFormat.FLAC: ("flac", "flac"),
        RenderAudioFormat.MP3: ("mp3", "mp3"),
        RenderAudioFormat.OGG: ("vorbis", "ogg"),
        RenderAudioFormat.OPUS: ("opus", "ogg"),
    }
    identity: tuple[str, str | None] | None = expected_identity.get(expected)
    if identity is None:
        return False
    expected_codec, expected_container = identity
    return codec_name == expected_codec and (expected_container is None or expected_container in formats)


def _failed_outcome(
    job: TtsQueueJob,
    *,
    step: Literal["tts", "audio"],
    context: ErrorContext,
    speech: SpeechBatchResult | None = None,
) -> TtsQueueOutcome:
    return TtsQueueOutcome(
        job=job,
        speech=speech,
        audio=None,
        failure=TtsQueueFailure(step=step, context=context),
    )


def _cancelled_outcome(job: TtsQueueJob) -> TtsQueueOutcome:
    context = ErrorContext(
        code=ErrorCode.CANCELLED,
        message="TTS job was not submitted after cancellation",
        suggestion="Run the file again to resume validated clips.",
    )
    return _failed_outcome(job, step="tts", context=context)
