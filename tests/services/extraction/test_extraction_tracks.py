from __future__ import annotations

from anishift.services.extraction.tracks import select_tracks
from anishift.services.extraction.types import TrackInfo


def _sub(track_id: int, language: str, *, name: str = "", lines: int = 100) -> TrackInfo:
    return TrackInfo(track_id, "subtitles", "S_TEXT/ASS", language, "", name, False, lines)


def _aud(track_id: int, language: str, *, default: bool = False) -> TrackInfo:
    return TrackInfo(track_id, "audio", "A_AAC", language, "", "", default, None)


def test_audio_prefers_japanese_over_english() -> None:
    result = select_tracks((_aud(2, "eng"), _aud(1, "jpn")))
    assert result.audio_id == 1


def test_audio_default_bonus_breaks_ties_within_language_only() -> None:
    result = select_tracks((_aud(1, "kor", default=True), _aud(2, "eng")))
    assert result.audio_id == 2


def test_subtitle_prefers_polish_over_english() -> None:
    result = select_tracks((_sub(1, "eng"), _sub(2, "pol")))
    assert result.subtitle_id == 2


def test_signs_only_polish_loses_to_full_english() -> None:
    result = select_tracks((_sub(1, "pol", name="Signs"), _sub(2, "eng")))
    assert result.subtitle_id == 2


def test_line_count_breaks_tie_within_language() -> None:
    result = select_tracks((_sub(1, "fra", lines=10), _sub(2, "fra", lines=20)))
    assert result.subtitle_id == 2


def test_tie_resolves_toward_lower_id() -> None:
    result = select_tracks((_sub(2, "fra"), _sub(1, "fra")))
    assert result.subtitle_id == 1


def test_select_tracks_returns_none_ids_without_audio_or_subtitles() -> None:
    result = select_tracks(())
    assert result.audio_id is None
    assert result.subtitle_id is None


def test_already_polish_flag_follows_chosen_subtitle_language() -> None:
    assert select_tracks((_sub(1, "pol"),)).already_polish is True
    assert select_tracks((_sub(1, "eng"),)).already_polish is False
    assert select_tracks(()).already_polish is False


def test_select_tracks_prefers_text_over_picture() -> None:
    picture = TrackInfo(2, "subtitles", "S_HDMV/PGS", "pol", "", "", False, 100)
    text = _sub(3, "eng")
    result = select_tracks((picture, text))
    assert result.subtitle_id == 3
    assert result.already_polish is False


def test_default_priorities_keep_the_original_ordering() -> None:
    result = select_tracks((_aud(1, "eng", default=True), _aud(2, "jpn"), _aud(3, "chi")))
    assert result.audio_id == 2


def test_audio_priority_override_selects_another_language() -> None:
    tracks = (_aud(1, "jpn"), _aud(2, "eng"))
    assert select_tracks(tracks).audio_id == 1
    assert select_tracks(tracks, audio_priority=("eng", "jpn")).audio_id == 2


def test_subtitle_priority_override_selects_another_language() -> None:
    tracks = (_sub(1, "pol"), _sub(2, "eng"))
    assert select_tracks(tracks).subtitle_id == 1
    assert select_tracks(tracks, subtitle_priority=("eng", "pol")).subtitle_id == 2


def test_two_letter_tags_match_three_letter_priorities() -> None:
    assert select_tracks((_aud(1, "en"), _aud(2, "ja"))).audio_id == 2
    assert select_tracks((_sub(1, "en"), _sub(2, "pl"))).subtitle_id == 2
