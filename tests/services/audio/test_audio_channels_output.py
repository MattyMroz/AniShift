from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.audio.channels import build_channel_plan
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.errors import AudioDecodeError
from anishift.services.audio.output import (
    RenderInputs,
    codec_spec,
    mixed_audio_path,
    render_command,
    validate_output_probe,
)
from anishift.services.audio.types import AudioCodecProfile, AudioProbe


@pytest.mark.parametrize(
    ("profile", "layout", "output_layout", "channels", "has_warning"),
    [
        (AudioCodecProfile.EAC3, "mono", "mono", 1, False),
        (AudioCodecProfile.FLAC, "stereo", "stereo", 2, False),
        (AudioCodecProfile.AAC, "5.1(side)", "5.1(side)", 6, False),
        (AudioCodecProfile.OPUS, "7.1", "7.1", 8, False),
        (AudioCodecProfile.EAC3, "7.1", "5.1(side)", 6, True),
        (AudioCodecProfile.MP3, "5.1(side)", "stereo", 2, True),
    ],
)
def test_channel_plan_is_explicit(
    profile: AudioCodecProfile,
    layout: str,
    output_layout: str,
    channels: int,
    has_warning: bool,
) -> None:
    plan = build_channel_plan(profile, layout)

    assert plan.output_layout == output_layout
    assert plan.output_channels == channels
    assert (plan.warning is not None) is has_warning
    assert plan.narrator_filter.startswith("pan=")
    if plan.warning is not None:
        assert plan.source_filter is not None


def test_eac3_7_1_matrix_preserves_front_and_folds_back_into_side() -> None:
    plan = build_channel_plan(AudioCodecProfile.EAC3, "7.1")

    assert plan.source_filter is not None
    assert "FL=FL|FR=FR|FC=FC|LFE=LFE" in plan.source_filter
    assert "SL=0.70710678*SL+0.70710678*BL" in plan.source_filter
    assert "SR=0.70710678*SR+0.70710678*BR" in plan.source_filter
    assert "|FC=c0|" in plan.narrator_filter


def test_mix_command_has_explicit_gain_longest_and_normalization() -> None:
    config = AudioConfig(
        codec_profile=AudioCodecProfile.EAC3,
        narrator_mix_base_gain_db=7,
        voice_mix_offset_db=-2,
        original_gain_db=0,
    )
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")

    command = render_command(
        Path("ffmpeg"),
        Path("Episode.tmp.eac3"),
        inputs=RenderInputs(
            narrator=Path("narrator.wav"),
            original_audio=Path("anime.aac"),
            config=config,
            channel_plan=plan,
        ),
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "volume=0dB" in filter_complex
    assert "volume=5dB" in filter_complex
    assert "duration=longest" in filter_complex
    assert "dropout_transition=2" in filter_complex
    assert "normalize=true" in filter_complex
    assert "-shortest" not in command


def test_narrator_only_command_has_no_mix_gain() -> None:
    config = AudioConfig(codec_profile=AudioCodecProfile.FLAC)
    plan = build_channel_plan(AudioCodecProfile.FLAC, "mono")

    command = render_command(
        Path("ffmpeg"),
        Path("Episode.tmp.flac"),
        inputs=RenderInputs(
            narrator=Path("narrator.wav"),
            original_audio=None,
            config=config,
            channel_plan=plan,
        ),
    )

    assert "-filter_complex" not in command
    assert "volume=7dB" not in command
    assert "amix=" not in " ".join(command)


@pytest.mark.parametrize(
    ("profile", "extension", "encoder"),
    [
        (AudioCodecProfile.MP3, ".mp3", "libmp3lame"),
        (AudioCodecProfile.WAV, ".wav", "pcm_s16le"),
        (AudioCodecProfile.EAC3, ".eac3", "eac3"),
        (AudioCodecProfile.OPUS, ".opus", "libopus"),
        (AudioCodecProfile.FLAC, ".flac", "flac"),
        (AudioCodecProfile.AAC, ".m4a", "aac"),
    ],
)
def test_codec_mapping(
    profile: AudioCodecProfile,
    extension: str,
    encoder: str,
) -> None:
    config = AudioConfig(codec_profile=profile)

    spec = codec_spec(config, channels=1)

    assert spec.extension == extension
    assert spec.encoder == encoder
    assert mixed_audio_path(Path("Episode.mkv"), profile) == Path(f"Episode{extension}")


def test_eac3_validation_accepts_one_frame_rounding_at_48_khz() -> None:
    config = AudioConfig(codec_profile=AudioCodecProfile.EAC3)
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")
    probe = AudioProbe(
        path=Path("Episode.eac3"),
        codec_name="eac3",
        format_name="eac3",
        sample_rate=48_000,
        channels=2,
        channel_layout="stereo",
        duration_ms=1_420_096,
        bit_rate=384_000,
    )

    validate_output_probe(
        probe,
        config=config,
        channel_plan=plan,
        expected_duration_ms=1_420_063,
    )


def test_eac3_validation_accepts_frame_padding_plus_millisecond_rounding() -> None:
    config = AudioConfig(codec_profile=AudioCodecProfile.EAC3)
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")
    probe = AudioProbe(
        path=Path("Episode.eac3"),
        codec_name="eac3",
        format_name="eac3",
        sample_rate=48_000,
        channels=2,
        channel_layout="stereo",
        duration_ms=1_440_160,
        bit_rate=384_000,
    )

    validate_output_probe(
        probe,
        config=config,
        channel_plan=plan,
        expected_duration_ms=1_440_125,
    )


def test_eac3_validation_still_rejects_a_render_cut_short() -> None:
    config = AudioConfig(codec_profile=AudioCodecProfile.EAC3)
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")
    probe = AudioProbe(
        path=Path("Episode.eac3"),
        codec_name="eac3",
        format_name="eac3",
        sample_rate=48_000,
        channels=2,
        channel_layout="stereo",
        duration_ms=1_439_125,
        bit_rate=384_000,
    )

    with pytest.raises(AudioDecodeError):
        validate_output_probe(
            probe,
            config=config,
            channel_plan=plan,
            expected_duration_ms=1_440_125,
        )
