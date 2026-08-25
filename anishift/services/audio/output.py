"""Final codec mapping, FFmpeg command construction, and result validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioDecodeError
from anishift.services.audio.types import AudioCodecProfile, AudioProbe, ChannelPlan

__all__ = [
    "CodecSpec",
    "RenderInputs",
    "codec_spec",
    "mixed_audio_path",
    "render_command",
    "validate_output_probe",
]

# ── Constants ────────────────────────────────────────────────────────────────

_EXPECTED_CODEC: Final[dict[AudioCodecProfile, str]] = {
    AudioCodecProfile.AAC: "aac",
    AudioCodecProfile.EAC3: "eac3",
    AudioCodecProfile.FLAC: "flac",
    AudioCodecProfile.MP3: "mp3",
    AudioCodecProfile.OPUS: "opus",
    AudioCodecProfile.WAV: "pcm_s16le",
}
"""FFprobe codec names expected for each final profile."""

_DEFAULT_BITRATE: Final[dict[AudioCodecProfile, dict[int, str]]] = {
    AudioCodecProfile.AAC: {1: "128k", 2: "256k", 6: "512k", 8: "768k"},
    AudioCodecProfile.EAC3: {1: "192k", 2: "384k", 6: "640k"},
    AudioCodecProfile.MP3: {1: "192k", 2: "320k"},
    AudioCodecProfile.OPUS: {1: "96k", 2: "192k", 6: "384k", 8: "512k"},
}
"""Locally validated default bitrates by profile and channel count."""

_EAC3_DURATION_TOLERANCE_MS: Final[int] = 64
"""Two E-AC-3 frames: the encoder pads to a whole 1536-sample frame, 32 ms at 48 kHz.

Expected and probed durations are each rounded to whole milliseconds, so one frame
alone leaves no room for that rounding and rejects renders that are in fact correct.
"""


@dataclass(frozen=True, slots=True)
class CodecSpec:
    """Concrete FFmpeg output mapping for one user-facing profile."""

    encoder: str
    container: str
    extension: str
    arguments: tuple[str, ...]
    duration_tolerance_ms: int


@dataclass(frozen=True, slots=True)
class RenderInputs:
    """Inputs and settings required to build one final FFmpeg command."""

    narrator: Path
    original_audio: Path | None
    config: AudioConfig
    channel_plan: ChannelPlan


def codec_spec(
    config: AudioConfig,
    *,
    channels: int,
) -> CodecSpec:
    """Resolve codec, container, bitrate, and profile-specific arguments."""
    profile: AudioCodecProfile = config.codec_profile
    if profile is AudioCodecProfile.WAV:
        return CodecSpec("pcm_s16le", "wav", ".wav", ("-rf64", "auto"), 2)
    if profile is AudioCodecProfile.FLAC:
        return CodecSpec(
            "flac",
            "flac",
            ".flac",
            ("-compression_level", str(config.flac_compression_level)),
            2,
        )
    bitrate: str = config.bitrate or _DEFAULT_BITRATE[profile][channels]
    if profile is AudioCodecProfile.EAC3:
        return CodecSpec("eac3", "eac3", ".eac3", ("-b:a", bitrate), _EAC3_DURATION_TOLERANCE_MS)
    if profile is AudioCodecProfile.MP3:
        return CodecSpec("libmp3lame", "mp3", ".mp3", ("-b:a", bitrate), 80)
    if profile is AudioCodecProfile.OPUS:
        return CodecSpec("libopus", "ogg", ".opus", ("-b:a", bitrate), 40)
    return CodecSpec(
        "aac",
        "mp4",
        ".m4a",
        ("-profile:a", "aac_low", "-b:a", bitrate, "-movflags", "+faststart"),
        50,
    )


def mixed_audio_path(source: Path, profile: AudioCodecProfile) -> Path:
    """Return the one final sidecar path for a source media file."""
    extension: str = ".m4a" if profile is AudioCodecProfile.AAC else f".{profile.value}"
    return source.with_suffix(extension)


def render_command(
    ffmpeg: Path,
    destination: Path,
    *,
    inputs: RenderInputs,
) -> tuple[str, ...]:
    """Build an explicit final encode or original-plus-narrator mix command."""
    config: AudioConfig = inputs.config
    channel_plan: ChannelPlan = inputs.channel_plan
    spec: CodecSpec = codec_spec(config, channels=channel_plan.output_channels)
    command: list[str] = [
        str(ffmpeg),
        "-v",
        "error",
        "-nostdin",
    ]
    if inputs.original_audio is None:
        command.extend(("-i", str(inputs.narrator), "-map", "0:a:0"))
    else:
        command.extend(
            ("-i", str(inputs.original_audio), "-i", str(inputs.narrator)),
        )
        source_chain: str = _source_chain(
            channel_plan,
            gain_db=config.original_gain_db,
        )
        narrator_gain_db: float = config.narrator_mix_base_gain_db + config.voice_mix_offset_db
        filter_complex: str = (
            f"[0:a:0]{source_chain}[source];"
            f"[1:a:0]{channel_plan.narrator_filter},"
            f"volume={_db(narrator_gain_db)}[narrator];"
            "[source][narrator]"
            "amix=inputs=2:duration=longest:dropout_transition=2:normalize=true[mixed]"
        )
        command.extend(("-filter_complex", filter_complex, "-map", "[mixed]"))
    command.extend(
        (
            "-c:a",
            spec.encoder,
            *spec.arguments,
            "-ac",
            str(channel_plan.output_channels),
            "-channel_layout",
            channel_plan.output_layout,
            "-ar",
            str(config.narrator_sample_rate),
            "-f",
            spec.container,
            "-y",
            str(destination),
        ),
    )
    return tuple(command)


def validate_output_probe(
    probe: AudioProbe,
    *,
    config: AudioConfig,
    channel_plan: ChannelPlan,
    expected_duration_ms: int,
) -> None:
    """Require final codec, layout, channels, and longest-input duration."""
    expected_codec: str = _EXPECTED_CODEC[config.codec_profile]
    spec: CodecSpec = codec_spec(config, channels=channel_plan.output_channels)
    is_valid: bool = (
        probe.codec_name == expected_codec
        and _matches_container(config.codec_profile, probe.format_name)
        and probe.channels == channel_plan.output_channels
        and probe.channel_layout.casefold() == channel_plan.output_layout.casefold()
        and probe.sample_rate == config.narrator_sample_rate
        and abs(probe.duration_ms - expected_duration_ms) <= spec.duration_tolerance_ms
    )
    if is_valid:
        return
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message="Final audio metadata does not match the requested output",
        suggestion="Inspect FFmpeg encoder support and channel mapping.",
        details={
            "expected_codec": expected_codec,
            "actual_codec": probe.codec_name,
            "actual_container": probe.format_name,
            "expected_layout": channel_plan.output_layout,
            "actual_layout": probe.channel_layout,
            "expected_sample_rate": config.narrator_sample_rate,
            "actual_sample_rate": probe.sample_rate,
            "expected_duration_ms": expected_duration_ms,
            "actual_duration_ms": probe.duration_ms,
        },
    )
    raise AudioDecodeError(context=context)


def _source_chain(plan: ChannelPlan, *, gain_db: float) -> str:
    mapping: str = (
        plan.source_filter if plan.source_filter is not None else f"aformat=channel_layouts={plan.output_layout}"
    )
    return f"{mapping},volume={_db(gain_db)}"


def _matches_container(profile: AudioCodecProfile, format_name: str) -> bool:
    names: frozenset[str] = frozenset(format_name.casefold().split(","))
    if profile is AudioCodecProfile.AAC:
        return bool(names & {"m4a", "mov", "mp4"})
    expected: str = "ogg" if profile is AudioCodecProfile.OPUS else profile.value
    return expected in names


def _db(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".") + "dB"
