"""Application adapter for provider-native TTS clip validation and assembly."""

from __future__ import annotations

import threading
from pathlib import Path

from anishift.services.audio.commands import CommandRunner, join_clips_command
from anishift.services.audio.errors import AudioError
from anishift.services.audio.probe import probe_audio, probe_decoded_mp3, probe_pcm_wav, validate_decode
from anishift.services.audio.types import AudioFormat as RenderAudioFormat
from anishift.services.tts.types import ClipExpectation, ClipValidation

__all__ = ["FfmpegClipService"]


class FfmpegClipService:
    """Validate and assemble provider-native clips through audio primitives."""

    __slots__ = ("_cancel", "_ffmpeg", "_ffprobe", "_runner", "_timeout_s")

    def __init__(
        self,
        *,
        cancel: threading.Event,
        runner: CommandRunner,
        ffmpeg: Path,
        ffprobe: Path,
        timeout_s: float,
    ) -> None:
        self._cancel: threading.Event = cancel
        self._runner: CommandRunner = runner
        self._ffmpeg: Path = ffmpeg
        self._ffprobe: Path = ffprobe
        self._timeout_s: float = timeout_s

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
