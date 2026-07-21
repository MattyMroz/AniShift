from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import TRACKS_DATASET

from anishift.services.extraction.tracks import select_audio_track, select_subtitle_track, select_tracks
from anishift.services.extraction.types import TrackInfo

pytestmark = pytest.mark.skipif(not TRACKS_DATASET.is_file(), reason="track dataset not available")


def _codec_id(codec: str) -> str:
    if codec == "SubStationAlpha":
        return "S_TEXT/ASS"
    if codec == "SubRip/SRT":
        return "S_TEXT/UTF8"
    return codec


def _tracks(entry: dict[str, Any]) -> tuple[TrackInfo, ...]:
    result = [
        TrackInfo(
            id=int(track["id"]),
            type=track_type,
            codec_id=_codec_id(str(track["codec"])),
            language=str(track["lang"]),
            language_ietf="",
            name=str(track["name"]),
            default=bool(track["default"]),
            num_entries=int(track["lines"]),
        )
        for raw, track_type in ((entry["subs"], "subtitles"), (entry["auds"], "audio"))
        for track in raw
    ]
    return tuple(result)


def _flat_tracks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw, track_type in ((entry["subs"], "subtitles"), (entry["auds"], "audio")):
        result.extend({**track, "type": track_type} for track in raw)
    return result


def test_track_selection_matches_dataset() -> None:
    data = json.loads(TRACKS_DATASET.read_text(encoding="utf-8"))
    entries = data["mkv"]
    audio_correct = 0
    subtitle_correct = 0
    for entry in entries:
        typed = _tracks(entry)
        flat = _flat_tracks(entry)
        result = select_tracks(typed)
        assert result.audio_id == select_audio_track(flat)
        assert result.subtitle_id == select_subtitle_track(flat)
        audio_correct += result.audio_id == entry["pick_aud"]
        subtitle_correct += result.subtitle_id == entry["pick_sub"]
    audio_accuracy = audio_correct / len(entries)
    subtitle_accuracy = subtitle_correct / len(entries)
    assert audio_accuracy >= 0.95
    assert subtitle_accuracy >= 0.95
