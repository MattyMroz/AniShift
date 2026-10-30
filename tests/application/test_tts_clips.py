from __future__ import annotations

import threading
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from loguru import logger as loguru_logger

from anishift.application.tts_clips import FfmpegClipService
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import CommandResult, SubprocessRunner
from anishift.services.audio.errors import AudioProcessError
from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    ClipExpectation,
    ClipSpan,
    DocumentPart,
    DocumentSynthesisRequest,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchStatus,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
    SynthesisProfile,
    SynthesisRequest,
    TtsConfig,
    TtsService,
    TtsUnsupportedError,
    VoiceInfo,
)
from anishift.utils.mp3_frames import iter_frames

if TYPE_CHECKING:
    from collections.abc import Callable

    from loguru import Message

FFMPEG: Final[Path | None] = resolve_binary(Binary.FFMPEG)
TONES: Final[str] = "if(lt(t,1)+between(t,1.6,2.6)+between(t,3.2,4.2),0.5*sin(2*PI*440*t),0)"
SPLICE_AFTER_FRAME: Final[int] = 83
STREAM_TAG: Final[bytes] = bytes.fromhex(
    "49443304000000000022545353450000000e0000034c61766636332e312e3130320000000000000000000000"
)
SERVER_SPANS: Final[tuple[tuple[float, float], ...]] = ((0.0, 1000.0), (1600.0, 2624.0), (3224.0, 4224.0))
CLIP_MS: Final[tuple[float, ...]] = (1325.0, 1570.0, 1615.0)
WAV: Final[ClipExpectation] = ClipExpectation(AudioFormat.WAV)


class _FailingRunner:
    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        del command, operation, timeout_s, cancel, on_stdout_line
        raise AudioProcessError(context=ErrorContext(code=ErrorCode.AUDIO_FAILED, message="decode failed"))


class _Progress:
    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        del state

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        del update


class _RecordingEngine:
    engine_id = "document"
    is_available = True
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=False,
        supports_native_rate=False,
        supports_native_volume=False,
        supports_pitch=False,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=200,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.CONFIG,
        max_document_chars=200,
    )
    synthesis_profile = SynthesisProfile(
        engine_id="document",
        endpoint_id="document-v1",
        provider_model_id="document-model",
        resolved_voice_id="document-voice",
        provider_output_id="pcm-cut",
        provider_source_format=AudioFormat.WAV,
        adapter_version="document:v1",
    )

    def __init__(self, recording: Path) -> None:
        self._recording: Path = recording

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

    async def synthesize(self, request: SynthesisRequest, *, cancel: CancellationToken) -> EngineClipResult:
        del request, cancel
        raise TtsUnsupportedError("document engine")

    def document_chars(self, parts: tuple[DocumentPart, ...]) -> int:
        return sum(len(part.text) for part in parts)

    async def synthesize_document(
        self,
        request: DocumentSynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineDocumentResult:
        del cancel
        request.recording.write_bytes(self._recording.read_bytes())
        return EngineDocumentResult(
            request_id=request.request_id,
            recording=request.recording,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id="document-model",
            voice_id="document-voice",
            request_time_ms=5.0,
            parts=tuple(
                PartTiming(request_id=part.request_id, start_ms=start, end_ms=end)
                for part, (start, end) in zip(request.parts, SERVER_SPANS, strict=True)
            ),
        )

    async def close(self) -> None:
        return None


def _recording(directory: Path) -> Path:
    if FFMPEG is None:
        pytest.skip("FFmpeg is not available")
    tones: Path = directory / "tones.mp3"
    command: tuple[str, ...] = (str(FFMPEG), "-v", "error", "-nostdin", "-f", "lavfi", "-i")
    command += (f"aevalsrc='{TONES}':s=48000:d=4.5", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k")
    command += ("-write_xing", "0", "-y", str(tones))
    SubprocessRunner().run(command, operation="test_tone_recording", timeout_s=60.0)
    data: bytes = tones.read_bytes()
    splice: int = list(iter_frames(data))[SPLICE_AFTER_FRAME + 1].offset
    recording: Path = directory / "recording.mp3"
    recording.write_bytes(data[:splice] + STREAM_TAG + data[splice:])
    return recording


def _clips(*, runner: SubprocessRunner | _FailingRunner | None = None) -> FfmpegClipService:
    return FfmpegClipService(
        cancel=threading.Event(),
        runner=runner if runner is not None else SubprocessRunner(),
        ffmpeg=FFMPEG if FFMPEG is not None else Path("ffmpeg"),
        ffprobe=Path("ffprobe"),
        timeout_s=30.0,
        recording_timeout_s=60.0,
    )


def _spans(directory: Path) -> tuple[ClipSpan, ...]:
    return tuple(
        ClipSpan(
            request_id=f"line-{index}",
            start_ms=start,
            end_ms=end,
            open_end=False,
            destination=directory / f"{index}.wav",
        )
        for index, (start, end) in enumerate(SERVER_SPANS)
    )


def _wav_ms(path: Path) -> tuple[int, int, float]:
    with wave.open(str(path), "rb") as stream:
        return stream.getframerate(), stream.getnchannels(), stream.getnframes() * 1000 / stream.getframerate()


@pytest.mark.integration
def test_split_clip_spliced_tone_recording_writes_one_wav_per_line(tmp_path: Path) -> None:
    recording: Path = _recording(tmp_path)
    spans: tuple[ClipSpan, ...] = _spans(tmp_path)

    result = _clips().split_clip(recording, spans, WAV)

    assert result.written == ("line-0", "line-1", "line-2")
    assert result.uncertain_boundaries == 0
    clips: list[tuple[int, int, float]] = [_wav_ms(span.destination) for span in spans]
    assert [(rate, channels) for rate, channels, _ in clips] == [(48_000, 1)] * 3
    assert [duration for _, _, duration in clips] == pytest.approx(CLIP_MS, abs=10.0)


@pytest.mark.integration
def test_split_clip_boundaries_inside_one_tone_warn_with_uncertain_count(tmp_path: Path) -> None:
    recording: Path = _recording(tmp_path)
    spans: tuple[ClipSpan, ...] = tuple(
        ClipSpan(
            request_id=f"line-{index}",
            start_ms=index * 300.0,
            end_ms=(index + 1) * 300.0,
            open_end=False,
            destination=tmp_path / f"{index}.wav",
        )
        for index in range(3)
    )
    captured: list[Message] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="WARNING")

    try:
        result = _clips().split_clip(recording, spans, WAV)
    finally:
        loguru_logger.remove(handler_id)

    assert result.uncertain_boundaries == 2
    assert [message.record["extra"]["uncertain_boundaries"] for message in captured] == [2]


@pytest.mark.unit
def test_split_clip_bytes_without_mpeg_frames_raises_value_error(tmp_path: Path) -> None:
    source: Path = tmp_path / "recording.mp3"
    source.write_bytes(b"not an mp3 recording")

    with pytest.raises(ValueError, match="MPEG"):
        _clips().split_clip(source, _spans(tmp_path), WAV)


@pytest.mark.unit
def test_split_clip_without_spans_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="span"):
        _clips().split_clip(tmp_path / "recording.mp3", (), WAV)


@pytest.mark.unit
def test_split_clip_mp3_expectation_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="WAV"):
        _clips().split_clip(tmp_path / "recording.mp3", _spans(tmp_path), ClipExpectation(AudioFormat.MP3))


@pytest.mark.unit
def test_split_clip_decode_failure_raises_runtime_error(tmp_path: Path) -> None:
    source: Path = tmp_path / "recording.mp3"
    source.write_bytes(bytes.fromhex("fffb90c4") + bytes(413) + bytes.fromhex("fffb90c4") + bytes(413))

    with pytest.raises(RuntimeError, match="decode"):
        _clips(runner=_FailingRunner()).split_clip(source, _spans(tmp_path), WAV)


@pytest.mark.integration
def test_tts_service_document_batch_real_splitter_commits_line_clips(tmp_path: Path) -> None:
    recording: Path = _recording(tmp_path)
    clips: FfmpegClipService = _clips()
    config = TtsConfig(
        engine_id="document",
        provider_model_id="document-model",
        voice_id="document-voice",
        max_concurrency=1,
        queue_capacity=2,
        retry_backoff_seconds=(0.0,),
        request_timeout_s=30.0,
    )
    batch = SpeechBatch(
        scope_id="episode",
        batch_rank=0,
        requests=tuple(
            SpeechRequest(request_id=f"line-{index}", text=text, request_rank=index)
            for index, text in enumerate(("Raz dwa.", "Trzy cztery.", "Pięć sześć."))
        ),
    )

    with TtsService(
        config,
        resume_root=tmp_path / "tts",
        validator=clips,
        splitter=clips,
        engine_factory=lambda _config: _RecordingEngine(recording),
    ) as service:
        result = service.synthesize(batch, callbacks=_Progress())

    assert result.status is SpeechBatchStatus.COMPLETED
    committed = [item.speech_clip for item in result.requests]
    assert all(clip is not None and clip.format is AudioFormat.WAV for clip in committed)
    durations: list[float] = [_wav_ms(clip.path)[2] for clip in committed if clip is not None]
    assert durations == pytest.approx(CLIP_MS, abs=10.0)
