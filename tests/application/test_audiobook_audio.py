from __future__ import annotations

import threading
import wave
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.audio_handler import AudioTaskHandler
from anishift.application.cancellation import NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.tts_handler import TtsProgressObserver, TtsTaskHandler
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.probe import measure_decoded_duration, probe_audio
from anishift.services.audio.service import AudioProgressSink, AudioService
from anishift.services.audio.transcode import AudioTranscodeService
from anishift.services.audio.types import AudioCodecProfile, AudioProbe, AudioRenderRequest, AudioRenderResult
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SynthesisStatus,
    SynthesizedRequest,
)

FFMPEG = resolve_binary(Binary.FFMPEG)
FFPROBE = resolve_binary(Binary.FFPROBE)

_SAMPLE_RATE = 48_000
_CLIP_MS = (400, 1500, 250)
_SECOND_START_MS = 300_000
_THIRD_START_MS = 301_000
_TOLERANCE_MS = 60
_PARAGRAPH_GAP_MS = 300
_PROBE_TIMEOUT_S = 30.0
_DECODE_TIMEOUT_S = 120.0
_CODECS = {"wav": "pcm_s16le", "eac3": "eac3", "mp3": "mp3", "opus": "opus"}


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _RealVoice:
    def __init__(self, root: Path) -> None:
        self.root: Path = root

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        del callbacks
        executions: list[SynthesizedRequest] = []
        for request in batch.requests:
            path: Path = self.root / f"{request.request_id}.wav"
            duration_ms: int = _CLIP_MS[request.request_rank]
            _write_tone(path, duration_ms)
            clip: SpeechClip = SpeechClip(
                request.request_id,
                path,
                AudioFormat.WAV,
                _SAMPLE_RATE,
                1,
                duration_ms,
                "edge",
                "edge-default",
                "voice",
                1,
                1.0,
                False,
            )
            executions.append(SynthesizedRequest(request, SynthesisStatus.SYNTHESIZED, clip, "", 0))
        stats: SpeechBatchStats = SpeechBatchStats(
            len(executions), len(executions), 0, 0, 0, len(executions), 0, 1.0, "edge", "edge-default", "voice"
        )
        return SpeechBatchResult(batch.scope_id, SpeechBatchStatus.COMPLETED, tuple(executions), stats, None)

    def cancel(self) -> None:
        raise AssertionError

    def close(self) -> None:
        return


class _PacedMixer:
    def __init__(self, service: AudioService, tempo: float) -> None:
        self._service: AudioService = service
        self._tempo: float = tempo

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressSink | None = None,
        on_percent: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        paced: AudioRenderRequest = replace(request, post_process_tempo=self._tempo)
        return self._service.render(paced, callbacks=callbacks, on_percent=on_percent, cancel=cancel)


def _write_tone(path: Path, duration_ms: int) -> None:
    frames: int = _SAMPLE_RATE * duration_ms // 1_000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(_SAMPLE_RATE)
        stream.writeframes(b"\x01\x00" * frames)


def _book(tmp_path: Path, *, newline: str = "\n", prefix: bytes = b"") -> Path:
    path: Path = tmp_path / "book.pl.srt"
    lines: str = newline.join(
        (
            "1",
            "00:00:00,000 --> 00:00:02,000",
            "Pierwsze zdanie",
            "",
            "2",
            "00:05:00,000 --> 00:05:02,000",
            "Drugie zdanie",
            "",
            "3",
            "00:05:01,000 --> 00:05:03,000",
            "Trzecie zdanie",
            "",
        )
    )
    path.write_bytes(prefix + lines.encode("utf-8"))
    return path


def _paced(duration_ms: int, tempo: float) -> int:
    return round(duration_ms / tempo)


def _continuous_ms(tempo: float) -> int:
    spoken: int = sum(_paced(duration_ms, tempo) for duration_ms in _CLIP_MS)
    return spoken + (len(_CLIP_MS) - 1) * _PARAGRAPH_GAP_MS


def _timed_ms(tempo: float) -> int:
    second_end: int = _SECOND_START_MS + _paced(_CLIP_MS[1], tempo)
    third_start: int = max(second_end, _THIRD_START_MS)
    return third_start + _paced(_CLIP_MS[2], tempo)


def _script(path: Path) -> Artifact:
    return Artifact("script", "group-1", ArtifactKind.FULL_PL, path, ArtifactState.READY, ArtifactLifetime.SOURCE, path)


def _manifest_slot() -> Artifact:
    return Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )


def _audio_slot(profile: str) -> Artifact:
    return Artifact(
        "narration",
        "group-1",
        ArtifactKind.NARRATION_AUDIO,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.INTERMEDIATE,
        audio_codec=profile,
    )


def _read_and_render(tmp_path: Path, timeline: str, profile: str, tempo: float, book: Path | None = None) -> Path:
    assert FFMPEG is not None
    assert FFPROBE is not None
    run_root: Path = tmp_path / f"{timeline}-{profile}"
    clips_root: Path = run_root / "clips"
    clips_root.mkdir(parents=True)
    speech: PlanTask = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("script",),
        ("manifest",),
        (),
        "tts:edge",
        (("narration_timeline", timeline), ("script_kind", "full_pl")),
    )
    spoken: TaskResult = TtsTaskHandler(
        _RealVoice(clips_root),
        run_root=run_root,
        group_ranks={"group-1": 0},
    ).execute(
        speech,
        ArtifactSnapshot(
            {"script": _script(book if book is not None else _book(tmp_path))},
            {"manifest": _manifest_slot()},
        ),
        NeverCancelledToken(),
        _Progress(),
    )
    manifest: Artifact = Artifact(
        "manifest",
        "group-1",
        ArtifactKind.TTS_MANIFEST,
        spoken.outputs[0].path,
        ArtifactState.READY,
        ArtifactLifetime.INTERMEDIATE,
    )
    mix: PlanTask = PlanTask(
        "mix",
        "group-1",
        TaskKind.MIX_NARRATION,
        ("manifest",),
        ("narration",),
        (),
        "audio:default",
        (("mix_source", "standalone"), ("output_profile", profile)),
    )
    config: AudioConfig = AudioConfig(codec_profile=AudioCodecProfile(profile))
    rendered: TaskResult = AudioTaskHandler(
        _PacedMixer(AudioService(config, ffmpeg=FFMPEG, ffprobe=FFPROBE), tempo),
        AudioTranscodeService(config, ffmpeg=FFMPEG, ffprobe=FFPROBE),
        run_root=run_root,
    ).execute(
        mix,
        ArtifactSnapshot({"manifest": manifest}, {"narration": _audio_slot(profile)}),
        NeverCancelledToken(),
        _Progress(),
    )
    return rendered.outputs[0].path


def _measured(path: Path) -> tuple[str, int]:
    assert FFMPEG is not None
    assert FFPROBE is not None
    runner: SubprocessRunner = SubprocessRunner()
    probed: AudioProbe = probe_audio(path, ffprobe=FFPROBE, runner=runner, timeout_s=_PROBE_TIMEOUT_S)
    decoded: int = measure_decoded_duration(path, ffmpeg=FFMPEG, runner=runner, timeout_s=_DECODE_TIMEOUT_S)
    return probed.codec_name, decoded


@pytest.mark.integration
@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
@pytest.mark.parametrize(("profile", "tempo"), [("wav", 1.0), ("eac3", 1.0), ("mp3", 1.25), ("opus", 0.75)])
def test_a_continuous_reading_lasts_the_words_it_read_in_every_format_and_at_every_speed(
    tmp_path: Path,
    profile: str,
    tempo: float,
) -> None:
    path: Path = _read_and_render(tmp_path, "continuous", profile, tempo)

    codec, decoded_ms = _measured(path)
    expected_ms: int = _continuous_ms(tempo)

    assert path.suffix == f".{profile}"
    assert codec == _CODECS[profile]
    assert expected_ms == sum(_paced(clip_ms, tempo) for clip_ms in _CLIP_MS) + 2 * _PARAGRAPH_GAP_MS
    assert expected_ms - _TOLERANCE_MS <= decoded_ms <= expected_ms + _TOLERANCE_MS


@pytest.mark.integration
@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
@pytest.mark.parametrize(("profile", "tempo"), [("wav", 1.0), ("eac3", 1.25)])
def test_a_reading_that_keeps_the_book_times_holds_the_long_silence_and_serializes_the_overlap(
    tmp_path: Path,
    profile: str,
    tempo: float,
) -> None:
    path: Path = _read_and_render(tmp_path, "source_times", profile, tempo)

    codec, decoded_ms = _measured(path)
    expected_ms: int = _timed_ms(tempo)

    assert codec == _CODECS[profile]
    assert expected_ms > _THIRD_START_MS + _paced(_CLIP_MS[2], tempo)
    assert expected_ms - _TOLERANCE_MS <= decoded_ms <= expected_ms + _TOLERANCE_MS


@pytest.mark.integration
@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
def test_a_complete_reading_leaves_every_byte_of_the_book_where_it_was(tmp_path: Path) -> None:
    book: Path = _book(tmp_path, newline="\r\n", prefix=b"\xef\xbb\xbf")
    before: bytes = book.read_bytes()

    path: Path = _read_and_render(tmp_path, "source_times", "wav", 1.0, book)

    codec, decoded_ms = _measured(path)
    assert codec == _CODECS["wav"]
    assert decoded_ms >= _timed_ms(1.0) - _TOLERANCE_MS
    assert book.read_bytes() == before
