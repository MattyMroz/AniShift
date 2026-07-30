from __future__ import annotations

import threading
from pathlib import Path

import pytest
from audio_test_helpers import RecordingRunner, command_result, write_wav

from anishift.services.audio.commands import CommandResult
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioCancelledError
from anishift.services.audio.normalize import (
    NormalizationContext,
    atempo_chain,
    normalize_clip,
)
from anishift.services.audio.types import AudioFormat, PcmStorage, TimedClip


@pytest.mark.parametrize(
    ("tempo", "expected"),
    [
        (1.0, ()),
        (1.25, (1.25,)),
        (0.5, (0.5,)),
        (0.25, (0.5, 0.5)),
        (2.5, (2.0, 1.25)),
        (8.0, (2.0, 2.0, 2.0)),
    ],
)
def test_atempo_chain_is_deterministic(
    tempo: float,
    expected: tuple[float, ...],
) -> None:
    assert atempo_chain(tempo) == expected


def test_normalize_clip_reuses_neutral_pcm_wav(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    write_wav(source, frames=480)
    clip = _timed_clip(source)
    runner = RecordingRunner(lambda command, operation: command_result(command))

    normalized = normalize_clip(
        clip,
        tmp_path / "unused.pcm",
        tempo=1.0,
        context=NormalizationContext(
            config=AudioConfig(),
            ffmpeg=Path("ffmpeg"),
            runner=runner,
        ),
    )

    assert normalized.path == source
    assert normalized.storage is PcmStorage.WAV
    assert normalized.frame_count == 480
    assert normalized.from_fast_path
    assert runner.calls == []


def test_normalize_clip_writes_raw_pcm_atomically(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"source")
    destination = tmp_path / "normalized" / "clip.pcm"
    clip = _timed_clip(source, clip_format=AudioFormat.MP3)

    def handler(command: tuple[str, ...], operation: str) -> CommandResult:
        Path(command[-1]).write_bytes(b"\x01\x00" * 240)
        return command_result(command)

    runner = RecordingRunner(handler)

    normalized = normalize_clip(
        clip,
        destination,
        tempo=2.5,
        context=NormalizationContext(
            config=AudioConfig(),
            ffmpeg=Path("ffmpeg"),
            runner=runner,
        ),
    )

    assert normalized.path == destination
    assert normalized.storage is PcmStorage.RAW
    assert normalized.frame_count == 240
    assert destination.read_bytes() == b"\x01\x00" * 240
    command = runner.calls[0][0]
    assert command[command.index("-af") + 1] == "atempo=2,atempo=1.25"
    assert not tuple(destination.parent.glob("*.tmp"))


def test_normalize_clip_honors_pre_cancel(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    write_wav(source, frames=10)
    cancel = threading.Event()
    cancel.set()
    runner = RecordingRunner(lambda command, operation: command_result(command))

    with pytest.raises(AudioCancelledError):
        normalize_clip(
            _timed_clip(source),
            tmp_path / "clip.pcm",
            tempo=1.0,
            context=NormalizationContext(
                config=AudioConfig(),
                ffmpeg=Path("ffmpeg"),
                runner=runner,
                cancel=cancel,
            ),
        )


def _timed_clip(
    path: Path,
    *,
    clip_format: AudioFormat = AudioFormat.WAV,
) -> TimedClip:
    return TimedClip(
        request_id="spoken-1",
        start_ms=0,
        end_ms=1000,
        source_order=0,
        clip_path=path,
        clip_format=clip_format,
        sample_rate=48_000,
        channels=1,
        duration_ms=10,
    )
