"""Validated single-stream audio transcoding through the configured profile."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, require_binary
from anishift.services.audio.channels import build_channel_plan
from anishift.services.audio.commands import CommandRunner, SubprocessRunner, ffmpeg_progress_reader, transcode_command
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioCancelledError
from anishift.services.audio.output import CodecSpec, codec_spec, validate_output_probe
from anishift.services.audio.probe import probe_audio
from anishift.services.audio.types import AudioProbe, ChannelPlan

__all__ = ["AudioTranscodeService"]


class AudioTranscodeService:
    """Transcode one ready audio stream and fully validate its staging output."""

    __slots__ = ("_config", "_ffmpeg", "_ffprobe", "_runner")

    def __init__(
        self,
        config: AudioConfig,
        *,
        runner: CommandRunner | None = None,
        ffmpeg: Path | None = None,
        ffprobe: Path | None = None,
    ) -> None:
        self._config: AudioConfig = config
        self._runner: CommandRunner = runner or SubprocessRunner(shutdown_grace_s=config.shutdown_grace_s)
        self._ffmpeg: Path = ffmpeg or require_binary(Binary.FFMPEG)
        self._ffprobe: Path = ffprobe or require_binary(Binary.FFPROBE)

    def transcode(
        self,
        source: Path,
        destination: Path,
        *,
        cancel: threading.Event,
        on_percent: Callable[[int], None] | None = None,
    ) -> Path:
        """Transcode one stream atomically into the configured output profile."""
        source_probe: AudioProbe = probe_audio(
            source,
            ffprobe=self._ffprobe,
            runner=self._runner,
            timeout_s=self._config.operation_timeout_s,
            cancel=cancel,
        )
        channel_plan: ChannelPlan = build_channel_plan(self._config.codec_profile, source_probe.channel_layout)
        spec: CodecSpec = codec_spec(self._config, channels=channel_plan.output_channels)
        temporary: Path = destination.with_name(f"{destination.name}.tmp")
        temporary.unlink(missing_ok=True)
        try:
            self._runner.run(
                transcode_command(
                    self._ffmpeg,
                    source,
                    temporary,
                    encoder=spec.encoder,
                    output_arguments=spec.arguments,
                    container=spec.container,
                    output_layout=channel_plan.output_layout,
                    output_channels=channel_plan.output_channels,
                    sample_rate=self._config.narrator_sample_rate,
                    source_filter=channel_plan.source_filter,
                ),
                operation="transcode_audio",
                timeout_s=self._config.render_timeout_s,
                cancel=cancel,
                on_stdout_line=ffmpeg_progress_reader(on_percent, duration_ms=source_probe.duration_ms),
            )
            output_probe: AudioProbe = probe_audio(
                temporary,
                ffprobe=self._ffprobe,
                runner=self._runner,
                timeout_s=self._config.operation_timeout_s,
                cancel=cancel,
            )
            validate_output_probe(
                output_probe,
                config=self._config,
                channel_plan=channel_plan,
                expected_duration_ms=source_probe.duration_ms,
            )
            if cancel.is_set():
                context = ErrorContext(code=ErrorCode.CANCELLED, message="Audio transcoding was cancelled")
                raise AudioCancelledError(context=context)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
