from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from anishift.services.audio.commands import SubprocessRunner, decode_command
from anishift.services.audio.errors import AudioCancelledError, AudioProcessError


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
