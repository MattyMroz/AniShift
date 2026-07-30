from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from anishift.services.audio.commands import (
    SubprocessRunner,
    decode_command,
    decode_duration_command,
    join_clips_command,
    scan_duration_command,
)
from anishift.services.audio.errors import AudioCancelledError, AudioProcessError
from anishift.services.audio.types import AudioFormat


class _StuckProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminate_calls: int = 0
        self.kill_calls: int = 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def communicate(self, timeout: float) -> tuple[str, str]:
        if self.returncode is not None:
            return "", ""
        raise subprocess.TimeoutExpired("ffmpeg", timeout)


def test_subprocess_runner_times_out_then_hard_kills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _StuckProcess()

    def factory(*args: object, **kwargs: object) -> _StuckProcess:
        return process

    monkeypatch.setattr("anishift.services.audio.commands.subprocess.Popen", factory)
    runner = SubprocessRunner(shutdown_grace_s=0.001)

    with pytest.raises(AudioProcessError) as caught:
        runner.run(
            ("ffmpeg", "-version"),
            operation="timeout_test",
            timeout_s=0.001,
        )

    assert caught.value.context.code.value == "TIMEOUT"
    assert process.terminate_calls == 1
    assert process.kill_calls == 1


def test_subprocess_runner_cancel_terminates_and_kills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _StuckProcess()

    def factory(*args: object, **kwargs: object) -> _StuckProcess:
        return process

    monkeypatch.setattr("anishift.services.audio.commands.subprocess.Popen", factory)
    cancel = threading.Event()
    cancel.set()
    runner = SubprocessRunner(shutdown_grace_s=0.001)

    with pytest.raises(AudioCancelledError):
        runner.run(
            ("ffmpeg", "-version"),
            operation="cancel_test",
            timeout_s=1,
            cancel=cancel,
        )

    assert process.terminate_calls == 1
    assert process.kill_calls == 1


def test_decode_command_maps_exactly_one_audio_stream() -> None:
    command = decode_command(Path("ffmpeg"), Path("voice clip.wav"))

    assert command == (
        "ffmpeg",
        "-v",
        "error",
        "-i",
        "voice clip.wav",
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
    )


def test_decode_duration_command_reports_progress_for_exact_audio_stream() -> None:
    command = decode_duration_command(Path("ffmpeg"), Path("voice clip.aac"))

    assert command == (
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        "voice clip.aac",
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "null",
        "-",
    )


def test_scan_duration_command_copies_exact_audio_stream() -> None:
    command = scan_duration_command(Path("ffmpeg"), Path("voice clip.aac"))

    assert command == (
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        "voice clip.aac",
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "copy",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "null",
        "-",
    )


@pytest.mark.parametrize(
    ("clip_format", "encoder", "muxer"),
    [
        (AudioFormat.MP3, "libmp3lame", "mp3"),
        (AudioFormat.WAV, "pcm_s16le", "wav"),
        (AudioFormat.OPUS, "libopus", "ogg"),
    ],
)
def test_join_clips_command_uses_gapless_filter_and_explicit_muxer(
    clip_format: AudioFormat,
    encoder: str,
    muxer: str,
) -> None:
    command = join_clips_command(
        Path("ffmpeg"),
        (Path("part one.audio"), Path("part two.audio")),
        Path("joined.audio.tmp"),
        clip_format=clip_format,
    )

    assert command[:9] == (
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        "part one.audio",
        "-i",
        "part two.audio",
        "-filter_complex",
    )
    assert "concat=n=2:v=0:a=1[out]" in command
    assert ("-c:a", encoder) == command[command.index("-c:a") : command.index("-c:a") + 2]
    assert ("-f", muxer) == command[command.index("-f") : command.index("-f") + 2]
    assert command[-2:] == ("-y", "joined.audio.tmp")


def test_join_clips_command_rejects_single_source() -> None:
    with pytest.raises(ValueError, match="at least two"):
        join_clips_command(
            Path("ffmpeg"),
            (Path("one.mp3"),),
            Path("joined.mp3.tmp"),
            clip_format=AudioFormat.MP3,
        )
