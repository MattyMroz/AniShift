from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from anishift.services.audio.commands import CommandResult
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioConfigError
from anishift.services.audio.service import AudioService
from anishift.services.audio.types import AudioFormat, AudioRenderRequest, TimedClip


class ConcurrentNormalizationRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
    ) -> CommandResult:
        del operation, timeout_s, cancel
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.05)
            Path(command[-1]).write_bytes(b"\x00" * 480)
        finally:
            with self._lock:
                self.active -= 1
        return CommandResult(command=command, stdout="", stderr="", returncode=0)


def test_audio_service_normalizes_clips_concurrently_in_source_order(tmp_path: Path) -> None:
    clips: list[TimedClip] = []
    for index in range(4):
        source = tmp_path / f"clip-{index}.mp3"
        source.write_bytes(b"provider audio")
        clips.append(
            TimedClip(
                request_id=f"speech-{index}",
                start_ms=index * 1_000,
                end_ms=index * 1_000 + 500,
                source_order=index,
                clip_path=source,
                clip_format=AudioFormat.MP3,
                sample_rate=24_000,
                channels=1,
                duration_ms=500,
            ),
        )
    request = AudioRenderRequest(
        scope_id="parallel-normalization",
        source_path=tmp_path / "Episode.mkv",
        source_audio_path=None,
        clips=tuple(clips),
        temporary_root=tmp_path / "audio",
    )
    runner = ConcurrentNormalizationRunner()
    service = AudioService(
        AudioConfig(normalization_concurrency=4),
        runner=runner,
        ffmpeg=Path("ffmpeg"),
        ffprobe=Path("ffprobe"),
    )

    normalized = service._normalize_many(
        request,
        cancel=None,
    )

    assert runner.peak == 4
    assert [clip.timed_clip.request_id for clip in normalized] == [
        "speech-0",
        "speech-1",
        "speech-2",
        "speech-3",
    ]


def test_audio_config_rejects_non_positive_normalization_concurrency() -> None:
    with pytest.raises(AudioConfigError, match="normalization_concurrency"):
        AudioConfig(normalization_concurrency=0)
