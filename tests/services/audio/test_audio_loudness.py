from __future__ import annotations

import re
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from audio_test_helpers import command_result, write_tone_wav

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import CommandResult, SubprocessRunner
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.probe import measure_integrated_loudness
from anishift.services.audio.service import AudioService
from anishift.services.audio.types import (
    AudioCodecProfile,
    AudioFormat,
    AudioRenderRequest,
    AudioRenderResult,
    AudioRenderStatus,
    TimedClip,
)

FFMPEG: Path | None = resolve_binary(Binary.FFMPEG)
FFPROBE: Path | None = resolve_binary(Binary.FFPROBE)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable"),
]

_TRUE_PEAK: re.Pattern[str] = re.compile(r"True peak:\s+Peak:\s+(\S+)\s+dBFS")
_NARRATOR_GAIN: re.Pattern[str] = re.compile(r"volume=(-?[\d.]+)dB\[narrator\]")
_SURROUND_SOURCE: str = (
    "anoisesrc=color=pink:r=48000:a=0.2:d=4:seed=7,asplit=3[front_left][front_right][center];"
    "anoisesrc=color=pink:r=48000:a=0.1:d=4:seed=9[surround_left];"
    "anoisesrc=color=pink:r=48000:a=0.1:d=4:seed=11[surround_right];"
    "sine=frequency=60:sample_rate=48000:duration=4[lfe];"
    "[front_left][front_right][center][lfe][surround_left][surround_right]join=inputs=6:channel_layout=5.1"
)
_LIMITER_CEILING_DBTP: float = -1.0
_TRUE_PEAK_TOLERANCE_DB: float = 0.1


class _MeasuringRunner:
    def __init__(self, loudness: dict[str, float] | None = None) -> None:
        self._delegate: SubprocessRunner = SubprocessRunner()
        self._loudness: dict[str, float] | None = loudness
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        self.calls.append((command, operation))
        if operation == "measure_loudness" and self._loudness is not None:
            measured: float = self._loudness[Path(command[command.index("-i") + 1]).name]
            return command_result(command, stderr=f"Summary:\n  Integrated loudness:\n    I:  {measured} LUFS\n")
        return self._delegate.run(
            command, operation=operation, timeout_s=timeout_s, cancel=cancel, on_stdout_line=on_stdout_line
        )

    def operations(self, operation: str) -> list[tuple[str, ...]]:
        return [command for command, name in self.calls if name == operation]


def _lavfi(destination: Path, source: str, *, audio_filter: str = "anull") -> Path:
    assert FFMPEG is not None
    SubprocessRunner().run(
        (
            str(FFMPEG),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            source,
            "-af",
            audio_filter,
            "-c:a",
            "pcm_s16le",
            "-y",
            str(destination),
        ),
        operation="fixture",
        timeout_s=30.0,
    )
    return destination


def _true_peak_dbtp(path: Path) -> float:
    assert FFMPEG is not None
    result: CommandResult = SubprocessRunner().run(
        (
            str(FFMPEG),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true:framelog=quiet",
            "-f",
            "null",
            "-",
        ),
        operation="true_peak",
        timeout_s=30.0,
    )
    match: re.Match[str] | None = _TRUE_PEAK.search(result.stderr)
    assert match is not None
    return float(match.group(1))


def _service(runner: _MeasuringRunner, config: AudioConfig) -> AudioService:
    return AudioService(config, runner=runner, ffmpeg=FFMPEG, ffprobe=FFPROBE)


def _request(tmp_path: Path, source: Path, clip: Path) -> AudioRenderRequest:
    timed: TimedClip = TimedClip("spoken-1", 200, 1_800, 0, clip, AudioFormat.WAV, 48_000, 1, 1_500)
    return AudioRenderRequest(
        "loudness", tmp_path / "Episode.mkv", source, (timed,), tmp_path / "tmp", tmp_path / "Episode.wav"
    )


@pytest.mark.parametrize(
    ("source", "attenuation_db"),
    [("anoisesrc=color=pink:r=48000:a=0.3:d=6:seed=7", 6.0), ("sine=frequency=1000:sample_rate=48000:duration=6", 9.0)],
)
def test_measure_integrated_loudness_attenuated_signal_drops_by_known_lu(
    tmp_path: Path, source: str, attenuation_db: float
) -> None:
    assert FFMPEG is not None
    loud: Path = _lavfi(tmp_path / "loud.wav", source)
    quiet: Path = _lavfi(tmp_path / "quiet.wav", source, audio_filter=f"volume=-{attenuation_db}dB")
    runner: SubprocessRunner = SubprocessRunner()

    loud_lufs: float = measure_integrated_loudness(loud, ffmpeg=FFMPEG, runner=runner, timeout_s=30.0)
    quiet_lufs: float = measure_integrated_loudness(quiet, ffmpeg=FFMPEG, runner=runner, timeout_s=30.0)

    assert loud_lufs - quiet_lufs == pytest.approx(attenuation_db, abs=0.2)


def test_audio_service_mix_gain_comes_from_narrator_and_source_measurements(tmp_path: Path) -> None:
    source: Path = _lavfi(tmp_path / "source.wav", "anoisesrc=color=pink:r=48000:a=0.1:d=3:seed=7")
    clip: Path = tmp_path / "clip.wav"
    write_tone_wav(clip, frames=72_000)
    runner: _MeasuringRunner = _MeasuringRunner({"narrator.wav": -30.0, "source.wav": -20.0})
    service: AudioService = _service(runner, AudioConfig(codec_profile=AudioCodecProfile.WAV, voice_mix_offset_db=2.0))
    request: AudioRenderRequest = _request(tmp_path, source, clip)

    first: AudioRenderResult = service.render(request)
    measured: list[str] = [
        Path(command[command.index("-i") + 1]).name for command in runner.operations("measure_loudness")
    ]
    render: tuple[str, ...] = runner.operations("render_output")[0]
    second: AudioRenderResult = service.render(request)

    assert first.status is AudioRenderStatus.COMPLETED
    assert sorted(measured) == ["narrator.wav", "source.wav"]
    assert "volume=19.5dB[narrator]" in render[render.index("-filter_complex") + 1]
    assert second.status is AudioRenderStatus.RESUME_HIT
    assert len(runner.operations("measure_loudness")) == 2


def test_audio_service_narrator_only_render_skips_loudness_measurement(tmp_path: Path) -> None:
    clip: Path = tmp_path / "clip.wav"
    write_tone_wav(clip, frames=72_000)
    runner: _MeasuringRunner = _MeasuringRunner()
    service: AudioService = _service(runner, AudioConfig(codec_profile=AudioCodecProfile.WAV))
    request: AudioRenderRequest = AudioRenderRequest(
        "narrator-only",
        tmp_path / "Episode.mkv",
        None,
        _request(tmp_path, clip, clip).clips,
        tmp_path / "tmp",
        tmp_path / "out.wav",
    )

    result: AudioRenderResult = service.render(request)

    assert result.status is AudioRenderStatus.COMPLETED
    assert runner.operations("measure_loudness") == []


def test_audio_service_loud_narrator_mix_stays_below_limiter_ceiling(tmp_path: Path) -> None:
    source: Path = _lavfi(tmp_path / "source.wav", "anoisesrc=color=pink:r=48000:a=0.3:d=3:seed=7")
    clip: Path = _lavfi(
        tmp_path / "clip.wav",
        "sine=frequency=440:sample_rate=48000:duration=1.5",
        audio_filter="volume=-4dB,afade=t=in:d=0.05,afade=t=out:st=1.45:d=0.05",
    )
    runner: _MeasuringRunner = _MeasuringRunner()
    config: AudioConfig = AudioConfig(codec_profile=AudioCodecProfile.WAV, narrator_over_source_lu=32.0)

    result: AudioRenderResult = _service(runner, config).render(_request(tmp_path, source, clip))

    assert result.output_path is not None
    assert len(runner.operations("measure_loudness")) == 2
    assert _true_peak_dbtp(result.output_path) <= _LIMITER_CEILING_DBTP + _TRUE_PEAK_TOLERANCE_DB


def _ffmpeg(*arguments: str) -> None:
    assert FFMPEG is not None
    SubprocessRunner().run((str(FFMPEG), "-v", "error", "-y", *arguments), operation="fixture", timeout_s=30.0)


def _narrator_gain_db(tmp_path: Path, source: Path, clip: Path) -> float:
    runner: _MeasuringRunner = _MeasuringRunner()
    result: AudioRenderResult = _service(runner, AudioConfig(codec_profile=AudioCodecProfile.WAV)).render(
        _request(tmp_path, source, clip)
    )
    render: tuple[str, ...] = runner.operations("render_output")[0]
    match: re.Match[str] | None = _NARRATOR_GAIN.search(render[render.index("-filter_complex") + 1])
    assert result.status is AudioRenderStatus.COMPLETED
    assert match is not None
    return float(match.group(1))


def test_audio_service_surround_source_and_its_stereo_downmix_give_the_same_narrator_gain(tmp_path: Path) -> None:
    surround: Path = tmp_path / "surround.wav"
    stereo: Path = tmp_path / "stereo.wav"
    _ffmpeg("-f", "lavfi", "-i", _SURROUND_SOURCE, "-c:a", "pcm_s16le", str(surround))
    _ffmpeg("-i", str(surround), "-ac", "2", "-c:a", "pcm_f32le", str(stereo))
    clip: Path = _lavfi(tmp_path / "clip.wav", "sine=frequency=440:sample_rate=48000:duration=1.5")
    (tmp_path / "surround").mkdir()
    (tmp_path / "stereo").mkdir()

    surround_gain: float = _narrator_gain_db(tmp_path / "surround", surround, clip)
    stereo_gain: float = _narrator_gain_db(tmp_path / "stereo", stereo, clip)

    assert surround_gain == pytest.approx(stereo_gain, abs=0.5)
