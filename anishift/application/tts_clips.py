"""Application adapter for provider-native TTS clip validation and assembly."""

from __future__ import annotations

import threading
import wave
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from anishift.services.audio.commands import CommandRunner, join_clips_command, recording_pcm_command
from anishift.services.audio.errors import AudioError
from anishift.services.audio.levels import frame_levels
from anishift.services.audio.probe import probe_audio, probe_decoded_mp3, probe_pcm_wav, validate_decode
from anishift.services.audio.segmentation import (
    ENVELOPE_RATE,
    CutDecision,
    LineSpan,
    clip_ranges,
    cut_points,
    server_frame_times,
)
from anishift.services.audio.types import AudioFormat as RenderAudioFormat
from anishift.services.tts.types import ClipExpectation, ClipSpan, ClipValidation, SplitResult
from anishift.utils.logger import get_logger
from anishift.utils.mp3_frames import FrameHeader, iter_frames, splice_times, to_decoded

__all__ = ["FfmpegClipService"]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_CLIP_RATE: Final[int] = 48_000
"""Sample rate of every mono PCM S16LE clip cut from a recording."""

_SAMPLE_BYTES: Final[int] = 2
"""Bytes in one signed 16-bit PCM sample."""

_MS_PER_SECOND: Final[int] = 1000
"""Milliseconds in one second."""


class FfmpegClipService:
    """Validate and assemble provider-native clips through audio primitives."""

    __slots__ = ("_cancel", "_ffmpeg", "_ffprobe", "_recording_timeout_s", "_runner", "_timeout_s")

    def __init__(  # noqa: PLR0913 - one adapter binds every FFmpeg collaborator and limit
        self,
        *,
        cancel: threading.Event,
        runner: CommandRunner,
        ffmpeg: Path,
        ffprobe: Path,
        timeout_s: float,
        recording_timeout_s: float,
    ) -> None:
        self._cancel: threading.Event = cancel
        self._runner: CommandRunner = runner
        self._ffmpeg: Path = ffmpeg
        self._ffprobe: Path = ffprobe
        self._timeout_s: float = timeout_s
        self._recording_timeout_s: float = recording_timeout_s

    def validate_clip(self, path: Path, expectation: ClipExpectation) -> ClipValidation | None:
        """Return trusted metadata only for a fully decodable expected format."""
        expected: RenderAudioFormat = RenderAudioFormat(expectation.format.value)
        if expected is RenderAudioFormat.MP3:
            return self._validate_mp3(path, expectation)
        if expected is RenderAudioFormat.WAV:
            pcm_probe = probe_pcm_wav(path, cancel=self._cancel)
            if pcm_probe is not None:
                return ClipValidation(
                    format=expectation.format,
                    sample_rate=pcm_probe.sample_rate,
                    channels=pcm_probe.channels,
                    duration_ms=pcm_probe.duration_ms,
                )
            if self._cancel.is_set():
                return None
        try:
            probe = probe_audio(
                path,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
            validate_decode(
                path,
                ffmpeg=self._ffmpeg,
                runner=self._runner,
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
        except AudioError:
            return None
        if not _matches_format(expected, probe.codec_name, probe.format_name):
            return None
        return ClipValidation(
            format=expectation.format,
            sample_rate=probe.sample_rate,
            channels=probe.channels,
            duration_ms=probe.duration_ms,
        )

    def join_clips(
        self,
        paths: tuple[Path, ...],
        destination: Path,
        expectation: ClipExpectation,
    ) -> None:
        """Join ordered parts with FFmpeg and leave validation to commit."""
        try:
            self._runner.run(
                join_clips_command(
                    self._ffmpeg,
                    paths,
                    destination,
                    clip_format=RenderAudioFormat(expectation.format.value),
                ),
                operation="join_tts_clips",
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
        except AudioError as error:
            message: str = "Provider-native clip assembly failed"
            raise RuntimeError(message) from error

    def split_clip(self, source: Path, spans: tuple[ClipSpan, ...], expectation: ClipExpectation) -> SplitResult:
        """Cut one MP3 recording at the pauses between lines into a mono 48 kHz PCM WAV per span."""
        if not spans:
            message: str = "A recording split needs at least one span"
            raise ValueError(message)
        if RenderAudioFormat(expectation.format.value) is not RenderAudioFormat.WAV:
            message = "A recording split writes only WAV clips"
            raise ValueError(message)
        data: bytes = source.read_bytes()
        first: FrameHeader | None = next(iter_frames(data), None)
        if first is None:
            message = "The recording holds no MPEG audio frame"
            raise ValueError(message)
        splices: tuple[float, ...] = splice_times(data)
        with TemporaryDirectory(prefix="anishift-split-") as scratch:
            envelope: array[int] = self._decode(source, Path(scratch) / "envelope.pcm", ENVELOPE_RATE)
            samples: array[int] = self._decode(source, Path(scratch) / "clips.pcm", _CLIP_RATE)
        levels: list[float] = frame_levels(envelope, ENVELOPE_RATE)
        times: list[float] = server_frame_times(len(levels), splices, first.duration_ms)
        lines: list[LineSpan] = [LineSpan(span.start_ms, span.end_ms, span.open_end) for span in spans]
        cuts: list[CutDecision] = cut_points(levels, times, lines)
        for span, (start_ms, end_ms) in zip(spans, clip_ranges(cuts, times), strict=True):
            start: int = _sample_index(to_decoded(start_ms, splices, first.duration_ms))
            end: int = _sample_index(to_decoded(end_ms, splices, first.duration_ms))
            _write_wav(span.destination, samples[start:end])
        uncertain: int = sum(cut.uncertain for cut in cuts)
        logger.info(
            "TTS recording split into line clips",
            spans=len(spans),
            uncertain_boundaries=uncertain,
            duration_ms=round(len(samples) * _MS_PER_SECOND / _CLIP_RATE),
        )
        if uncertain:
            logger.warning("TTS recording boundaries cut without a pause", uncertain_boundaries=uncertain)
        return SplitResult(written=tuple(span.request_id for span in spans), uncertain_boundaries=uncertain)

    def _decode(self, source: Path, destination: Path, sample_rate: int) -> array[int]:
        try:
            self._runner.run(
                recording_pcm_command(self._ffmpeg, source, destination, sample_rate=sample_rate),
                operation="decode_tts_recording",
                timeout_s=self._recording_timeout_s,
                cancel=self._cancel,
            )
        except AudioError as error:
            message: str = "TTS recording decode failed"
            raise RuntimeError(message) from error
        return array("h", destination.read_bytes())

    def _validate_mp3(self, path: Path, expectation: ClipExpectation) -> ClipValidation | None:
        try:
            probe = probe_decoded_mp3(
                path,
                ffmpeg=self._ffmpeg,
                runner=self._runner,
                timeout_s=self._timeout_s,
                cancel=self._cancel,
            )
        except AudioError:
            return None
        return ClipValidation(
            format=expectation.format,
            sample_rate=probe.sample_rate,
            channels=probe.channels,
            duration_ms=probe.duration_ms,
        )


def _sample_index(decoded_ms: float) -> int:
    return max(round(decoded_ms * _CLIP_RATE / _MS_PER_SECOND), 0)


def _write_wav(destination: Path, samples: array[int]) -> None:
    with wave.open(str(destination), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(_SAMPLE_BYTES)
        stream.setframerate(_CLIP_RATE)
        stream.writeframes(samples.tobytes())


def _matches_format(expected: RenderAudioFormat, codec_name: str, format_name: str) -> bool:
    formats: set[str] = set(format_name.split(","))
    if expected is RenderAudioFormat.WAV:
        return codec_name.startswith("pcm_") and "wav" in formats
    expected_identity: dict[RenderAudioFormat, tuple[str, str | None]] = {
        RenderAudioFormat.AAC: ("aac", None),
        RenderAudioFormat.FLAC: ("flac", "flac"),
        RenderAudioFormat.MP3: ("mp3", "mp3"),
        RenderAudioFormat.OGG: ("vorbis", "ogg"),
        RenderAudioFormat.OPUS: ("opus", "ogg"),
    }
    identity: tuple[str, str | None] | None = expected_identity.get(expected)
    if identity is None:
        return False
    expected_codec, expected_container = identity
    return codec_name == expected_codec and (expected_container is None or expected_container in formats)
