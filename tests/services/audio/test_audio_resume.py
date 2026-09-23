from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.services.audio.errors import AudioResumeError
from anishift.services.audio.resume import AudioResumeRepository
from anishift.services.audio.types import PlacementReason, TimelinePlacement


def _placement(*, request_id: str = "spoken-1", start: int = 0) -> TimelinePlacement:
    return TimelinePlacement(
        request_id=request_id,
        source_order=0,
        planned_start_ms=start,
        planned_end_ms=start + 400,
        actual_start_ms=start,
        actual_end_ms=start + 400,
        drift_ms=0,
        reason=PlacementReason.ON_TIME,
        overlap_group_id=None,
        clip_duration_ms=400,
        window_duration_ms=400,
        start_frame=start * 48,
        end_frame=(start + 400) * 48,
    )


def test_resume_tracks_narrator_and_multiple_output_formats(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    eac3 = tmp_path / "Episode.eac3"
    eac3.write_bytes(b"eac3")
    flac = tmp_path / "Episode.flac"
    flac.write_bytes(b"flac")

    repository.commit_narration("narration-a", narrator, (_placement(),))
    repository.commit_output("mix-a", eac3)
    repository.commit_output("mix-b", flac)

    reloaded = AudioResumeRepository(root, "scope")
    hit = reloaded.narration_hit("narration-a", frozenset({"spoken-1"}))
    assert hit is not None
    assert hit.path == narrator
    assert hit.placements == (_placement(),)
    assert reloaded.output_hit(eac3, "mix-a")
    assert reloaded.output_hit(flac, "mix-b")


def test_a_recovered_narrator_carries_the_timeline_it_was_really_built_on(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    placements = (_placement(), _placement(request_id="spoken-2", start=2_000))
    repository.commit_narration("narration-a", narrator, placements)

    hit = AudioResumeRepository(root, "scope").narration_hit("narration-a", frozenset({"spoken-1", "spoken-2"}))

    assert hit is not None
    assert hit.placements == placements


def test_a_narration_manifest_with_a_broken_placement_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    repository.commit_narration("narration-a", narrator, (_placement(),))
    manifest = root / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["narration"]["placements"][0]["actual_start_ms"] = "0"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    assert AudioResumeRepository(root, "scope").narration_hit("narration-a", frozenset({"spoken-1"})) is None
    assert len(tuple(root.glob("manifest.corrupt.*.json"))) == 1


def test_a_timeline_that_repeats_one_clip_and_forgets_another_is_never_resumed(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    repository.commit_narration("narration-a", narrator, (_placement(), _placement(request_id="spoken-2", start=2_000)))
    manifest = root / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["narration"]["placements"][1] = payload["narration"]["placements"][0]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    hit = AudioResumeRepository(root, "scope").narration_hit("narration-a", frozenset({"spoken-1", "spoken-2"}))

    assert hit is None
    assert len(tuple(root.glob("manifest.corrupt.*.json"))) == 1


def test_a_timeline_naming_a_clip_this_render_never_had_is_never_resumed(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    repository = AudioResumeRepository(root, "scope")
    narrator = repository.narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    repository.commit_narration("narration-a", narrator, (_placement(), _placement(request_id="spoken-9", start=2_000)))

    hit = AudioResumeRepository(root, "scope").narration_hit("narration-a", frozenset({"spoken-1", "spoken-2"}))

    assert hit is None
    assert not tuple(root.glob("manifest.corrupt.*.json"))


def test_a_narrator_recorded_before_timelines_were_stored_is_quarantined_and_rebuilt(tmp_path: Path) -> None:
    root = tmp_path / "audio"
    root.mkdir()
    narration_dir = root / "narration"
    narration_dir.mkdir()
    narrator = narration_dir / "narrator.wav"
    narrator.write_bytes(b"narrator")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope_id": "scope",
                "narration": {"fingerprint": "narration-a", "path": "narration/narrator.wav", "file_hash": "0" * 64},
                "outputs": {},
            }
        ),
        encoding="utf-8",
    )

    repository = AudioResumeRepository(root, "scope")
    missed = repository.narration_hit("narration-a", frozenset({"spoken-1"}))
    repository.commit_narration("narration-a", narrator, (_placement(),))

    assert missed is None
    assert len(tuple(root.glob("manifest.corrupt.*.json"))) == 1
    assert repository.narration_hit("narration-a", frozenset({"spoken-1"})) is not None


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
