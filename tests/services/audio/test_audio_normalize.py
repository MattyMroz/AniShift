from __future__ import annotations

import math
import threading
from array import array
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
from anishift.services.audio.types import AudioFormat, TimedClip


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


def _tone(amplitude: int, count: int, sample_rate: int) -> array[int]:
    return array("h", (round(amplitude * math.sin(2 * math.pi * 1000 * n / sample_rate)) for n in range(count)))


def _ffmpeg_writing(pcm: bytes) -> RecordingRunner:
    def handler(command: tuple[str, ...], operation: str) -> CommandResult:
        Path(command[-1]).write_bytes(pcm)
        return command_result(command)

    return RecordingRunner(handler)


def _context(runner: RecordingRunner) -> NormalizationContext:
    return NormalizationContext(config=AudioConfig(), ffmpeg=Path("ffmpeg"), runner=runner)


@pytest.mark.unit
def test_normalize_clip_silent_edges_are_trimmed_to_speech_and_margins(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    write_wav(source, frames=48_000)
    silence = array("h", [0] * 14_400)
    runner = _ffmpeg_writing((silence + _tone(8_000, 24_000, 48_000) + silence).tobytes())

    normalized = normalize_clip(_timed_clip(source), tmp_path / "clip.pcm", tempo=1.0, context=_context(runner))

    assert len(runner.calls) == 1
    assert normalized.frame_count == pytest.approx(26_880, abs=1)
    assert normalized.path.stat().st_size == normalized.frame_count * 2


@pytest.mark.unit
def test_normalize_clip_without_speech_keeps_whole_clip(tmp_path: Path) -> None:
    source = tmp_path / "clip.wav"
    write_wav(source, frames=48_000)
    pcm = array("h", [2] * 28_800).tobytes()

    normalized = normalize_clip(
        _timed_clip(source), tmp_path / "clip.pcm", tempo=1.0, context=_context(_ffmpeg_writing(pcm))
    )

    assert normalized.frame_count == 28_800
    assert normalized.path.read_bytes() == pcm


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
