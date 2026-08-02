from __future__ import annotations

import threading
from pathlib import Path

import pytest
from audio_test_helpers import write_wav

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import CommandResult, SubprocessRunner
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioProcessError
from anishift.services.audio.probe import measure_decoded_duration, probe_audio
from anishift.services.audio.service import AudioService, _notify, _replace_output
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


class _RecordingRunner:
    def __init__(
        self,
        *,
        fail_operation: str = "",
        fail_occurrence: int = 1,
    ) -> None:
        self._delegate = SubprocessRunner()
        self._fail_operation = fail_operation
        self._fail_occurrence = fail_occurrence
        self._operation_counts: dict[str, int] = {}
        self.operations: list[str] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
    ) -> CommandResult:
        self.operations.append(operation)
        occurrence: int = self._operation_counts.get(operation, 0) + 1
        self._operation_counts[operation] = occurrence
        if operation == self._fail_operation and occurrence == self._fail_occurrence:
            raise AudioProcessError(
                context=ErrorContext(
                    code=ErrorCode.AUDIO_FAILED,
                    message="forced audio failure",
                ),
            )
        return self._delegate.run(
            command,
            operation=operation,
            timeout_s=timeout_s,
            cancel=cancel,
        )


def test_audio_progress_observer_cannot_fail_audio_execution() -> None:
    _notify(_ThrowingProgress(), "scope", "mixing")


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
def test_audio_service_renders_and_resumes_real_eac3(tmp_path: Path) -> None:
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=9_600)
    output_path = tmp_path / "Episode.eac3"
    output_path.write_bytes(b"foreign sidecar")
    request = AudioRenderRequest(
        scope_id="episode-scope",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=(_timed_clip(clip_path),),
        temporary_root=tmp_path / "tmp" / "episode-scope" / "audio",
    )
    runner = _RecordingRunner()
    service = AudioService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        runner=runner,
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    first = service.render(request)
    assert runner.operations.count("decode") == 0
    second = service.render(request)

    assert first.status is AudioRenderStatus.COMPLETED
    assert first.output_path == output_path
    assert output_path.read_bytes() != b"foreign sidecar"
    assert first.output_probe is not None
    assert first.output_probe.codec_name == "eac3"
    assert first.output_probe.sample_rate == 48_000
    assert first.output_probe.channel_layout == "mono"
    assert first.output_probe.duration_ms >= 300
    assert first.narrator_path is not None
    assert first.narrator_path.is_file()
    assert runner.operations.count("decode") == 2
    assert second.status is AudioRenderStatus.RESUME_HIT
    assert second.output_path == first.output_path


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
def test_stream_preparation_is_reused_without_second_normalization(
    tmp_path: Path,
) -> None:
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=9_600)
    clip = _timed_clip(clip_path)
    request = AudioRenderRequest(
        scope_id="stream-reuse",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=(clip,),
        temporary_root=tmp_path / "tmp" / "stream-reuse" / "audio",
        post_process_tempo=1.25,
    )
    runner = _RecordingRunner()
    service = AudioService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        runner=runner,
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    service.prepare_clip(
        clip,
        temporary_root=request.temporary_root,
        tempo=request.post_process_tempo,
        cancel=None,
    )
    result = service.render(request)

    assert result.status is AudioRenderStatus.COMPLETED
    assert runner.operations.count("normalize_clip") == 1


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
def test_failed_output_validation_preserves_existing_sidecar_bit_for_bit(
    tmp_path: Path,
) -> None:
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=9_600)
    output_path = tmp_path / "Episode.eac3"
    original_bytes = b"user-owned sidecar"
    output_path.write_bytes(original_bytes)
    request = AudioRenderRequest(
        scope_id="failed-replacement",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=(_timed_clip(clip_path),),
        temporary_root=tmp_path / "tmp" / "failed-replacement" / "audio",
    )
    service = AudioService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        runner=_RecordingRunner(fail_operation="probe", fail_occurrence=2),
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    with pytest.raises(AudioProcessError, match="forced audio failure"):
        service.render(request)

    assert output_path.read_bytes() == original_bytes


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


def test_replace_output_retries_transient_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "out.tmp.eac3"
    destination = tmp_path / "out.eac3"
    source.write_bytes(b"payload")
    attempts: list[int] = []
    original_replace = Path.replace

    def flaky_replace(self: Path, target: str | Path) -> Path:
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError(13, "Access is denied")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr("anishift.services.audio.service.time.sleep", lambda _delay: None)

    _replace_output(source, destination)

    assert destination.read_bytes() == b"payload"
    assert len(attempts) == 3


def test_replace_output_raises_when_lock_persists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def locked_replace(self: Path, target: str | Path) -> Path:
        attempts.append(1)
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr("anishift.services.audio.service.time.sleep", lambda _delay: None)

    with pytest.raises(PermissionError):
        _replace_output(tmp_path / "out.tmp.eac3", tmp_path / "out.eac3")

    assert len(attempts) == 4


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


@pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None,
    reason="bundled FFmpeg is unavailable",
)
def test_audio_service_uses_decoded_duration_for_vbr_adts_aac(
    tmp_path: Path,
) -> None:
    assert FFMPEG is not None
    assert FFPROBE is not None
    original_path = tmp_path / "variable.aac"
    runner = SubprocessRunner()
    fixture_command = (
        str(FFMPEG),
        "-v",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo:d=10",
        "-f",
        "lavfi",
        "-i",
        "anoisesrc=r=48000:d=10:a=0.5",
        "-filter_complex",
        "[1:a]pan=stereo|c0=c0|c1=c0[noise];[0:a][noise]concat=n=2:v=0:a=1[out]",
        "-map",
        "[out]",
        "-c:a",
        "aac",
        "-q:a",
        "5",
        "-f",
        "adts",
        "-y",
        str(original_path),
    )
    runner.run(fixture_command, operation="fixture", timeout_s=10)
    metadata_probe = probe_audio(
        original_path,
        ffprobe=FFPROBE,
        runner=runner,
        timeout_s=10,
    )
    decoded_duration_ms = measure_decoded_duration(
        original_path,
        ffmpeg=FFMPEG,
        runner=runner,
        timeout_s=10,
    )
    clip_path = tmp_path / "clip.wav"
    write_wav(clip_path, frames=4_800)
    request = AudioRenderRequest(
        scope_id="scope-vbr-aac",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=original_path,
        clips=(_timed_clip(clip_path),),
        temporary_root=tmp_path / "tmp" / "vbr-aac" / "audio",
    )
    service = AudioService(
        AudioConfig(codec_profile=AudioCodecProfile.EAC3),
        ffmpeg=FFMPEG,
        ffprobe=FFPROBE,
    )

    result = service.render(request)

    assert abs(metadata_probe.duration_ms - decoded_duration_ms) > 1_000
    assert result.output_probe is not None
    assert abs(result.output_probe.duration_ms - decoded_duration_ms) <= 33


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
