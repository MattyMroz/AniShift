from __future__ import annotations

from pathlib import Path

import pytest
from audio_test_helpers import write_wav

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.service import AudioService, _notify
from anishift.services.audio.types import (
    AudioCodecProfile,
    AudioFormat,
    AudioRenderRequest,
    AudioRenderStatus,
    TimedClip,
)

FFMPEG = resolve_binary(Binary.FFMPEG)
FFPROBE = resolve_binary(Binary.FFPROBE)


class _ThrowingProgress:
    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        del scope_id, phase
        raise RuntimeError("renderer unavailable")


def test_audio_progress_observer_cannot_fail_audio_execution() -> None:
    _notify(_ThrowingProgress(), "scope", "mixing")


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
def test_audio_service_renders_and_resumes_real_eac3(tmp_path: Path) -> None:
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=9_600)
    request = AudioRenderRequest(
        scope_id="episode-scope",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=(_timed_clip(clip_path),),
        temporary_root=tmp_path / "tmp" / "episode-scope" / "audio",
    )
    service = AudioService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    first = service.render(request)
    second = service.render(request)

    assert first.status is AudioRenderStatus.COMPLETED
    assert first.output_path == tmp_path / "Episode.eac3"
    assert first.output_probe is not None
    assert first.output_probe.codec_name == "eac3"
    assert first.output_probe.sample_rate == 48_000
    assert first.output_probe.channel_layout == "mono"
    assert first.output_probe.duration_ms >= 300
    assert first.narrator_path is not None
    assert first.narrator_path.is_file()
    assert second.status is AudioRenderStatus.RESUME_HIT
    assert second.output_path == first.output_path


def test_audio_service_skips_empty_speech_without_sidecar(tmp_path: Path) -> None:
    service = AudioService(
        AudioConfig(),
        ffmpeg=Path("ffmpeg"),
        ffprobe=Path("ffprobe"),
    )
    request = AudioRenderRequest(
        scope_id="episode-scope",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=(),
        temporary_root=tmp_path / "audio",
    )

    result = service.render(request)

    assert result.status is AudioRenderStatus.SKIPPED_NO_SPOKEN
    assert result.output_path is None
    assert not (tmp_path / "Episode.eac3").exists()


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
@pytest.mark.parametrize(
    ("profile", "source_layout", "expected_layout", "expected_channels"),
    [
        (AudioCodecProfile.MP3, "5.1(side)", "stereo", 2),
        (AudioCodecProfile.EAC3, "7.1", "5.1(side)", 6),
        (AudioCodecProfile.AAC, "7.1", "7.1", 8),
        (AudioCodecProfile.OPUS, "7.1", "7.1", 8),
        (AudioCodecProfile.FLAC, "7.1", "7.1", 8),
        (AudioCodecProfile.WAV, "7.1", "7.1", 8),
    ],
)
def test_audio_service_real_codec_and_channel_matrix(
    tmp_path: Path,
    profile: AudioCodecProfile,
    source_layout: str,
    expected_layout: str,
    expected_channels: int,
) -> None:
    assert FFMPEG is not None
    assert FFPROBE is not None
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=4_800)
    original_path = tmp_path / "original.wav"
    runner = SubprocessRunner()
    command = (
        str(FFMPEG),
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=channel_layout={source_layout}:sample_rate=48000",
        "-t",
        "0.15",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-y",
        str(original_path),
    )
    runner.run(command, operation="fixture", timeout_s=10)
    request = AudioRenderRequest(
        scope_id=f"scope-{profile.value}",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=original_path,
        clips=(_timed_clip(clip_path),),
        temporary_root=tmp_path / "tmp" / profile.value / "audio",
    )
    service = AudioService(
        AudioConfig(codec_profile=profile),
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    result = service.render(request)

    assert result.output_probe is not None
    assert result.output_probe.channel_layout == expected_layout
    assert result.output_probe.channels == expected_channels


def _timed_clip(path: Path) -> TimedClip:
    return TimedClip(
        request_id="spoken-1",
        start_ms=100,
        end_ms=500,
        source_order=0,
        clip_path=path,
        clip_format=AudioFormat.WAV,
        sample_rate=48_000,
        channels=1,
        duration_ms=200,
    )
