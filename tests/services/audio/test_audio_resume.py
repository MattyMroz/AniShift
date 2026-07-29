from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.services.audio.errors import AudioResumeError
from anishift.services.audio.resume import AudioResumeRepository


def test_resume_tracks_narrator_and_multiple_output_formats(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    eac3 = tmp_path / "Episode.eac3"
    eac3.write_bytes(b"eac3")
    flac = tmp_path / "Episode.flac"
    flac.write_bytes(b"flac")

    repository.commit_narration("narration-a", narrator)
    repository.commit_output("mix-a", eac3)
    repository.commit_output("mix-b", flac)

    reloaded = AudioResumeRepository(root, "scope")
    assert reloaded.narration_hit("narration-a") == narrator
    assert reloaded.output_hit(eac3, "mix-a")
    assert reloaded.output_hit(flac, "mix-b")


def test_resume_invalidates_replaced_output(tmp_path: Path) -> None:
    repository = AudioResumeRepository(tmp_path / "audio", "scope")
    output = tmp_path / "Episode.eac3"
    output.write_bytes(b"owned")
    repository.commit_output("mix", output)
    output.write_bytes(b"foreign")

    assert not repository.output_hit(output, "mix")


def test_corrupt_audio_manifest_does_not_touch_tts_directory(tmp_path: Path) -> None:
    audio_root = tmp_path / "scope" / "audio"
    audio_root.mkdir(parents=True)
    (audio_root / "manifest.json").write_text("{", encoding="utf-8")
    tts_root = tmp_path / "scope" / "tts"
    tts_root.mkdir()
    tts_manifest = tts_root / "manifest.json"
    tts_manifest.write_text(json.dumps({"tts": True}), encoding="utf-8")

    AudioResumeRepository(audio_root, "scope")

    assert tts_manifest.read_text(encoding="utf-8") == '{"tts": true}'
    assert len(tuple(audio_root.glob("manifest.corrupt.*.json"))) == 1


def test_future_audio_manifest_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    root.mkdir()
    manifest = root / "manifest.json"
    payload = '{"schema_version":999,"future_shape":true}'
    manifest.write_text(payload, encoding="utf-8")

    with pytest.raises(AudioResumeError):
        AudioResumeRepository(root, "scope")

    assert manifest.read_text(encoding="utf-8") == payload
    assert not tuple(root.glob("manifest.corrupt.*.json"))
