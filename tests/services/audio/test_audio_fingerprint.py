from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from anishift.services.audio import fingerprint
from anishift.services.audio.channels import build_channel_plan
from anishift.services.audio.config import AudioConfig
from anishift.services.audio.fingerprint import (
    mix_fingerprint,
    narration_fingerprint,
    normalization_fingerprint,
)
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
        paragraph_pauses=False,
        config=config,
    )
    mix_changed = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.0,
        paragraph_pauses=False,
        config=replace(
            config,
            narrator_over_source_lu=9,
            codec_profile=AudioCodecProfile.FLAC,
        ),
    )
    tempo_changed = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.25,
        paragraph_pauses=False,
        config=config,
    )
    timing_changed = narration_fingerprint(
        scope_id="scope",
        clips=(replace(clip, start_ms=500),),
        post_process_tempo=1.0,
        paragraph_pauses=False,
        config=config,
    )

    paragraphs_changed = narration_fingerprint(
        scope_id="scope",
        clips=(clip,),
        post_process_tempo=1.0,
        paragraph_pauses=True,
        config=config,
    )

    assert baseline == mix_changed
    assert baseline != tempo_changed
    assert baseline != timing_changed
    assert baseline != paragraphs_changed


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
    offset_changed: str = mix_fingerprint(
        narration_fingerprint_value="sha256:narration",
        narrator_path=narrator,
        original_audio_path=original,
        channel_plan=plan,
        config=config,
        source_offset_us=5_005_000,
    )
    assert baseline != offset_changed


def test_normalization_fingerprint_reuses_timing_changes_but_tracks_audio_inputs(
    tmp_path: Path,
) -> None:
    clip_path = tmp_path / "clip.wav"
    clip_path.write_bytes(b"clip")
    clip = _clip(clip_path)
    config = AudioConfig()

    baseline = normalization_fingerprint(
        clip,
        post_process_tempo=1.0,
        config=config,
    )
    timing_changed = normalization_fingerprint(
        replace(clip, start_ms=900, end_ms=1_400, source_order=8),
        post_process_tempo=1.0,
        config=config,
    )
    tempo_changed = normalization_fingerprint(
        clip,
        post_process_tempo=1.25,
        config=config,
    )
    target_changed = normalization_fingerprint(
        clip,
        post_process_tempo=1.0,
        config=replace(config, narrator_sample_rate=44_100),
    )
    clip_path.write_bytes(b"changed")
    content_changed = normalization_fingerprint(
        clip,
        post_process_tempo=1.0,
        config=config,
    )

    assert baseline == timing_changed
    assert baseline != tempo_changed
    assert baseline != target_changed
    assert baseline != content_changed


@pytest.mark.unit
@pytest.mark.parametrize(("name", "value"), [("EDGE_TRIM_DBFS", -40.0), ("EDGE_TRIM_MARGIN_MS", 20.0)])
def test_normalization_fingerprint_edge_trim_change_changes_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: float,
) -> None:
    clip_path = tmp_path / "clip.wav"
    clip_path.write_bytes(b"clip")
    clip = _clip(clip_path)
    baseline = normalization_fingerprint(clip, post_process_tempo=1.0, config=AudioConfig())

    monkeypatch.setattr(fingerprint, name, value)

    assert normalization_fingerprint(clip, post_process_tempo=1.0, config=AudioConfig()) != baseline


@pytest.mark.unit
def test_mix_fingerprint_algorithm_version_is_five() -> None:
    assert fingerprint._MIX_ALGORITHM_VERSION == 5


@pytest.mark.unit
def test_mix_fingerprint_narrator_loudness_target_change_changes_identity(tmp_path: Path) -> None:
    narrator = tmp_path / "narrator.wav"
    narrator.write_bytes(b"narrator")
    original = tmp_path / "original.aac"
    original.write_bytes(b"original")
    plan = build_channel_plan(AudioCodecProfile.EAC3, "stereo")

    def identity(config: AudioConfig) -> str:
        return mix_fingerprint(
            narration_fingerprint_value="sha256:narration",
            narrator_path=narrator,
            original_audio_path=original,
            channel_plan=plan,
            config=config,
        )

    assert identity(AudioConfig(narrator_over_source_lu=7.5)) != identity(AudioConfig(narrator_over_source_lu=8.0))


@pytest.mark.unit
def test_mix_fingerprint_limiter_change_changes_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    narrator = tmp_path / "narrator.wav"
    narrator.write_bytes(b"narrator")
    plan = build_channel_plan(AudioCodecProfile.EAC3, "mono")
    baseline = mix_fingerprint(
        narration_fingerprint_value="sha256:narration",
        narrator_path=narrator,
        original_audio_path=None,
        channel_plan=plan,
        config=AudioConfig(),
    )

    monkeypatch.setattr(fingerprint, "MIX_LIMITER", "alimiter=limit=0.5:level=0")

    assert (
        mix_fingerprint(
            narration_fingerprint_value="sha256:narration",
            narrator_path=narrator,
            original_audio_path=None,
            channel_plan=plan,
            config=AudioConfig(),
        )
        != baseline
    )


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
