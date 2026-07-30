from __future__ import annotations

import json
import threading
import wave
from pathlib import Path

import pytest
from audio_test_helpers import RecordingRunner, command_result, probe_payload, write_wav

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.commands import CommandResult
from anishift.services.audio.errors import AudioDecodeError, AudioProbeError, AudioProcessError
from anishift.services.audio.probe import (
    measure_audio_duration,
    measure_decoded_duration,
    parse_probe_json,
    probe_audio,
    probe_decoded_mp3,
    probe_pcm_wav,
)


def test_parse_probe_json_selects_first_audio_and_rounds_duration() -> None:
    payload = json.dumps(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "duration": "1.2345",
                    "bit_rate": "256000",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "opus",
                    "sample_rate": "48000",
                    "channels": 1,
                    "channel_layout": "mono",
                    "duration": "9",
                },
            ],
            "format": {"format_name": "mov,mp4,m4a", "duration": "10"},
        },
    )

    probe = parse_probe_json(Path("track.m4a"), payload)

    assert probe.codec_name == "aac"
    assert probe.format_name == "mov,mp4,m4a"
    assert probe.duration_ms == 1235
    assert probe.bit_rate == 256000
    assert probe.channel_layout == "stereo"


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"streams":[],"format":{"format_name":"wav","duration":"1"}}',
        probe_payload(duration=None),
        "not json",
    ],
)
def test_parse_probe_json_rejects_missing_audio_or_duration(payload: str) -> None:
    with pytest.raises(AudioProbeError):
        parse_probe_json(Path("bad.audio"), payload)


def test_probe_audio_rejects_zero_byte_before_process(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    path.touch()
    runner = RecordingRunner(lambda command, operation: command_result(command))

    with pytest.raises(AudioProbeError):
        probe_audio(
            path,
            ffprobe=Path("ffprobe"),
            runner=runner,
            timeout_s=1,
        )

    assert runner.calls == []


def test_probe_audio_uses_json_argument_list(tmp_path: Path) -> None:
    path = tmp_path / "voice clip.wav"
    path.write_bytes(b"audio")

    def handler(command: tuple[str, ...], operation: str) -> CommandResult:
        return command_result(command, stdout=probe_payload())

    runner = RecordingRunner(handler)

    probe_audio(
        path,
        ffprobe=Path("ffprobe.exe"),
        runner=runner,
        timeout_s=1,
    )

    command, operation = runner.calls[0]
    assert operation == "probe"
    assert command[:7] == (
        "ffprobe.exe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
    )
    assert command[-1] == str(path)


def test_probe_pcm_wav_reads_complete_payload_without_subprocess(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    write_wav(path, frames=48_000, sample_rate=48_000, channels=1)

    probe = probe_pcm_wav(path)

    assert probe is not None
    assert probe.codec_name == "pcm_s16le"
    assert probe.format_name == "wav"
    assert probe.sample_rate == 48_000
    assert probe.channels == 1
    assert probe.duration_ms == 1000
    assert probe.bit_rate == 768_000


def test_probe_pcm_wav_rejects_truncated_payload(tmp_path: Path) -> None:
    path = tmp_path / "truncated.wav"
    write_wav(path, frames=48_000, sample_rate=48_000, channels=1)
    path.write_bytes(path.read_bytes()[:-2])

    assert probe_pcm_wav(path) is None


def test_probe_pcm_wav_defers_compressed_wave(tmp_path: Path) -> None:
    path = tmp_path / "compressed.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48_000)
        stream.setcomptype("NONE", "not compressed")
        stream.writeframes(b"\0\0")
    payload = bytearray(path.read_bytes())
    payload[20:22] = (6).to_bytes(2, byteorder="little")
    path.write_bytes(payload)

    assert probe_pcm_wav(path) is None


def test_probe_pcm_wav_rejects_sample_rate_outside_ffmpeg_range(tmp_path: Path) -> None:
    path = tmp_path / "invalid-rate.wav"
    write_wav(path, frames=2_147_484, sample_rate=48_000, channels=1)
    payload = bytearray(path.read_bytes())
    payload[24:28] = (0xFFFFFFFF).to_bytes(4, byteorder="little")
    path.write_bytes(payload)

    assert probe_pcm_wav(path) is None


def test_probe_pcm_wav_rejects_duration_rounded_to_zero(tmp_path: Path) -> None:
    path = tmp_path / "too-short.wav"
    write_wav(path, frames=1, sample_rate=48_000, channels=1)

    assert probe_pcm_wav(path) is None


def test_probe_pcm_wav_stops_before_read_when_cancelled(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    write_wav(path, frames=48_000, sample_rate=48_000, channels=1)
    cancel = threading.Event()
    cancel.set()

    assert probe_pcm_wav(path, cancel=cancel) is None


def test_probe_decoded_mp3_uses_one_complete_decode(tmp_path: Path) -> None:
    path = tmp_path / "voice.mp3"
    header = (0x7FF << 21) | (0b11 << 19) | (0b01 << 17) | (1 << 16) | (9 << 12) | (0b11 << 6)
    frame_length = 144 * 128_000 // 44_100
    frame = header.to_bytes(4, byteorder="big") + bytes(frame_length - 4)
    path.write_bytes(frame + frame)
    runner = RecordingRunner(
        lambda command, operation: command_result(
            command,
            stdout="out_time_us=3854512\nprogress=end\n",
        ),
    )

    probe = probe_decoded_mp3(
        path,
        ffmpeg=Path("ffmpeg.exe"),
        runner=runner,
        timeout_s=1,
    )

    assert probe.codec_name == "mp3"
    assert probe.sample_rate == 44_100
    assert probe.channels == 1
    assert probe.duration_ms == 3855
    assert [operation for _, operation in runner.calls] == ["measure_duration"]


def test_measure_decoded_duration_uses_completed_ffmpeg_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "variable bitrate.aac"
    path.write_bytes(b"audio")
    progress = "\n".join(
        (
            "out_time_us=1094983401",
            "progress=continue",
            "out_time_us=1420109206",
            "progress=end",
        ),
    )
    runner = RecordingRunner(
        lambda command, operation: command_result(command, stdout=progress),
    )

    duration_ms = measure_decoded_duration(
        path,
        ffmpeg=Path("ffmpeg.exe"),
        runner=runner,
        timeout_s=1,
    )

    assert duration_ms == 1_420_109
    command, operation = runner.calls[0]
    assert operation == "measure_duration"
    assert command[0] == "ffmpeg.exe"
    assert command[-1] == "-"


def test_measure_decoded_duration_rejects_incomplete_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "truncated.aac"
    path.write_bytes(b"audio")
    runner = RecordingRunner(
        lambda command, operation: command_result(
            command,
            stdout="out_time_us=1000000\nprogress=continue\n",
        ),
    )

    with pytest.raises(AudioDecodeError, match="completed duration"):
        measure_decoded_duration(
            path,
            ffmpeg=Path("ffmpeg"),
            runner=runner,
            timeout_s=1,
        )


def test_measure_audio_duration_uses_packet_scan(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.aac"
    path.write_bytes(b"audio")
    progress = "out_time_us=1420053333\nprogress=end\n"
    runner = RecordingRunner(
        lambda command, operation: command_result(command, stdout=progress),
    )

    duration_ms = measure_audio_duration(
        path,
        ffmpeg=Path("ffmpeg"),
        runner=runner,
        timeout_s=1,
    )

    assert duration_ms == 1_420_053
    command, operation = runner.calls[0]
    assert operation == "scan_duration"
    assert "copy" in command


def test_measure_audio_duration_falls_back_to_complete_decode(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.aac"
    path.write_bytes(b"audio")
    progress = "out_time_us=1420053333\nprogress=end\n"

    def handle(command: tuple[str, ...], operation: str) -> CommandResult:
        if operation == "scan_duration":
            raise AudioProcessError(
                context=ErrorContext(
                    code=ErrorCode.AUDIO_FAILED,
                    message="packet copy unavailable",
                ),
            )
        return command_result(command, stdout=progress)

    runner = RecordingRunner(handle)

    duration_ms = measure_audio_duration(
        path,
        ffmpeg=Path("ffmpeg"),
        runner=runner,
        timeout_s=1,
    )

    assert duration_ms == 1_420_053
    assert [operation for _, operation in runner.calls] == [
        "scan_duration",
        "measure_duration",
    ]


def test_measure_audio_duration_does_not_retry_after_timeout(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.aac"
    path.write_bytes(b"audio")

    def handle(command: tuple[str, ...], operation: str) -> CommandResult:
        del command, operation
        raise AudioProcessError(
            context=ErrorContext(
                code=ErrorCode.TIMEOUT,
                message="scan timed out",
            ),
        )

    runner = RecordingRunner(handle)

    with pytest.raises(AudioProcessError) as captured:
        measure_audio_duration(
            path,
            ffmpeg=Path("ffmpeg"),
            runner=runner,
            timeout_s=1,
        )

    assert captured.value.context.code is ErrorCode.TIMEOUT
    assert len(runner.calls) == 1
