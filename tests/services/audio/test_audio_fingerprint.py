from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from anishift.services.audio.channels import build_channel_plan
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.fingerprint import mix_fingerprint, narration_fingerprint
from anishift.services.audio.types import AudioCodecProfile, AudioFormat, TimedClip


def test_narration_fingerprint_ignores_mix_settings_but_tracks_tempo_and_timing(
    tmp_path: Path,
) -> None:
    clip_path = tmp_path / "clip.wav"
    clip_path.write_bytes(b"clip")
    clip = _clip(clip_path)
    config = AudioConfig()

    baseline = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.0,
        config=config,
    )
    mix_changed = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.0,
        config=replace(
            config,
            narrator_mix_base_gain_db=9,
            codec_profile=AudioCodecProfile.FLAC,
        ),
    )
    tempo_changed = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.25,
        config=config,
    )
    timing_changed = narration_fingerprint(
        scope_id="scope",
        clips=(replace(clip, start_ms=500),),
        post_process_tempo=1.0,
        config=config,
    )

    assert baseline == mix_changed
    assert baseline != tempo_changed
    assert baseline != timing_changed


def test_mix_fingerprint_tracks_original_gain_and_codec(tmp_path: Path) -> None:
    narrator = tmp_path / "narrator.wav"
    narrator.write_bytes(b"narrator")
    original = tmp_path / "original.aac"
    original.write_bytes(b"original")
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")
    config = AudioConfig()

    baseline = mix_fingerprint(
        narration_fingerprint_value="sha256:narration",
        narrator_path=narrator,
        original_audio_path=original,
        channel_plan=plan,
        config=config,
    )
    gain_changed = mix_fingerprint(
        narration_fingerprint_value="sha256:narration",
        narrator_path=narrator,
        original_audio_path=original,
        channel_plan=plan,
        config=replace(config, voice_mix_offset_db=-2),
    )
    codec_config = replace(config, codec_profile=AudioCodecProfile.FLAC)
    codec_changed = mix_fingerprint(
        narration_fingerprint_value="sha256:narration",
        narrator_path=narrator,
        original_audio_path=original,
        channel_plan=build_channel_plan(AudioCodecProfile.FLAC, "stereo"),
        config=codec_config,
    )

    assert baseline != gain_changed
    assert baseline != codec_changed


def _clip(path: Path) -> TimedClip:
    return TimedClip(
        request_id="spoken-1",
        start_ms=100,
        end_ms=500,
        source_order=0,
        clip_path=path,
        clip_format=AudioFormat.WAV,
        sample_rate=48_000,
        channels=1,
        duration_ms=200,
    )
