from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from anishift.application.tts_clips import FfmpegClipService
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStatus,
    SpeechClip,
    SpeechRequest,
    SynthesisStatus,
    TtsConfig,
    TtsProgressSink,
    TtsService,
)


@pytest.mark.network
def test_edge_polish_speech_commits_a_decodable_mp3(
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    ffmpeg: Path | None = resolve_binary(Binary.FFMPEG)
    ffprobe: Path | None = resolve_binary(Binary.FFPROBE)
    if ffmpeg is None or ffprobe is None:
        pytest.skip("FFmpeg and ffprobe are required for the live Edge acceptance test")
    clips: FfmpegClipService = FfmpegClipService(
        cancel=threading.Event(),
        runner=SubprocessRunner(),
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        timeout_s=30.0,
    )
    config: TtsConfig = TtsConfig(
        engine_id="edge",
        provider_model_id="edge-default",
        voice_id="pl-PL-ZofiaNeural",
        max_concurrency=1,
        queue_capacity=1,
        max_retries=0,
        request_timeout_s=30.0,
    )
    batch: SpeechBatch = SpeechBatch(
        scope_id="edge-polish-acceptance",
        batch_rank=0,
        requests=(
            SpeechRequest(
                request_id="polish-phrase",
                text="Dzień dobry. To krótki test polskiego lektora AniShift.",
                request_rank=0,
            ),
        ),
    )
    callbacks: Mock = Mock(spec=TtsProgressSink)

    with TtsService(config, resume_root=tmp_path, validator=clips, assembler=clips) as service:
        result: SpeechBatchResult = service.synthesize(batch, callbacks=callbacks)

    record_property("status", result.status.value)
    record_property("error_code", result.failure.code.value if result.failure is not None else "")
    assert result.status is SpeechBatchStatus.COMPLETED
    assert result.failure is None
    assert result.stats.provider_calls == 1
    assert result.stats.retries == 0
    assert result.stats.resume_hits == 0
    assert result.requests[0].status is SynthesisStatus.SYNTHESIZED
    clip: SpeechClip | None = result.requests[0].speech_clip
    assert clip is not None
    assert clip.format is AudioFormat.MP3
    assert clip.voice_id == "pl-PL-ZofiaNeural"
    assert clip.attempts == 1
    assert clip.sample_rate == 24000
    assert clip.channels == 1
    assert clip.duration_ms > 0
    assert clip.path.stat().st_size > 0
    callbacks.on_request_retry.assert_not_called()
    record_property("audio_path", str(clip.path))
    record_property("request_time_ms", clip.request_time_ms)
    record_property("duration_ms", clip.duration_ms)
    record_property("size_bytes", clip.path.stat().st_size)
