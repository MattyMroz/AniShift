"""Select original audio and processable text subtitle tracks from metadata."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from anishift.services.extraction.types import TrackInfo, TrackSelection, is_text_subtitle_codec

__all__ = [
    "is_polish_language",
    "score_audio_track",
    "score_subtitle_track",
    "select_audio_track",
    "select_subtitle_track",
    "select_tracks",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_SUB_LANG_WEIGHT: Final[dict[str, int]] = {"pol": 100, "pl": 100, "eng": 50, "en": 50}
"""Subtitle language weights."""

_SUB_LANG_DEFAULT: Final[int] = 10
"""Weight for an unlisted subtitle language."""

_AUDIO_LANG_WEIGHT: Final[dict[str, int]] = {
    "jpn": 100,
    "ja": 100,
    "eng": 40,
    "en": 40,
    "chi": 30,
    "zho": 30,
    "chs": 30,
    "cht": 30,
}
"""Audio language weights."""

_AUDIO_LANG_DEFAULT: Final[int] = 20
"""Weight for an unlisted audio language."""

_SIGNS_PENALTY: Final[int] = -200
"""Penalty for signs, songs, or forced subtitle tracks."""

_DEFAULT_BONUS: Final[int] = 10
"""Bonus for an audio track marked as the container default."""

_LINES_DIVISOR: Final[float] = 1000.0
"""Scale for the subtitle line-count tie-breaker."""

_RE_SIGNS: Final[re.Pattern[str]] = re.compile(r"sign|song|forced", re.I)
"""Pattern identifying signs-only subtitle names."""

_POLISH_LANGS: Final[frozenset[str]] = frozenset({"pol", "pl"})
"""Subtitle language tags meaning the track is already Polish."""


def is_polish_language(language: str) -> bool:
    """Tell whether a subtitle language tag means the track is already Polish."""
    return language.lower() in _POLISH_LANGS


def _track_name(track: dict[str, Any]) -> str:
    """Return a track display name from flat or nested metadata."""
    value = track.get("track_name") or track.get("name") or track.get("properties", {}).get("track_name") or ""
    return str(value)


def _track_language(track: dict[str, Any]) -> str:
    """Return a lowercased track language from flat or nested metadata."""
    value = track.get("language") or track.get("lang") or track.get("properties", {}).get("language") or ""
    return str(value).lower()


def _track_default(track: dict[str, Any]) -> bool:
    """Return whether a track is marked as the container default."""
    return bool(track.get("default_track") or track.get("default") or track.get("properties", {}).get("default_track"))


def _is_signs_only(track: dict[str, Any]) -> bool:
    """Tell whether a subtitle track is marked as signs-only."""
    return bool(_RE_SIGNS.search(_track_name(track)))


def _lines_bonus(track: dict[str, Any]) -> float:
    """Return the line-count tie-breaker for a subtitle track."""
    lines = track.get("num_lines")
    if lines is None:
        lines = track.get("lines")
    if lines is None:
        lines = track.get("properties", {}).get("num_index_entries")
    if lines is None:
        return 0.0
    return float(lines) / _LINES_DIVISOR


def score_subtitle_track(track: dict[str, Any]) -> float:
    """Score a subtitle track for translation and narration."""
    score = float(_SUB_LANG_WEIGHT.get(_track_language(track), _SUB_LANG_DEFAULT))
    if _is_signs_only(track):
        score += _SIGNS_PENALTY
    return score + _lines_bonus(track)


def score_audio_track(track: dict[str, Any]) -> float:
    """Score an audio track for use under the narrator."""
    score = float(_AUDIO_LANG_WEIGHT.get(_track_language(track), _AUDIO_LANG_DEFAULT))
    if _track_default(track):
        score += _DEFAULT_BONUS
    return score


def select_subtitle_track(tracks: list[dict[str, Any]]) -> int | None:
    """Pick the highest-scoring subtitle track, preferring lower ids on ties."""
    subtitles = [track for track in tracks if track.get("type") == "subtitles"]
    if not subtitles:
        return None
    best = max(subtitles, key=lambda track: (score_subtitle_track(track), -int(track["id"])))
    return int(best["id"])


def select_audio_track(tracks: list[dict[str, Any]]) -> int | None:
    """Pick the highest-scoring audio track, preferring lower ids on ties."""
    audio = [track for track in tracks if track.get("type") == "audio"]
    if not audio:
        return None
    best = max(audio, key=lambda track: (score_audio_track(track), -int(track["id"])))
    return int(best["id"])


def _selector_shape(track: TrackInfo) -> dict[str, Any]:
    """Return the flat dictionary shape accepted by the ported selectors."""
    return {
        "id": track.id,
        "type": track.type,
        "language": track.language,
        "name": track.name,
        "default": track.default,
        "num_lines": track.num_entries,
    }


def select_tracks(tracks: Sequence[TrackInfo]) -> TrackSelection:
    """Pick one audio track and one processable text subtitle track."""
    audio_shaped = [_selector_shape(track) for track in tracks if track.type == "audio"]
    text_shaped = [
        _selector_shape(track)
        for track in tracks
        if track.type == "subtitles" and is_text_subtitle_codec(track.codec_id)
    ]
    audio_id = select_audio_track(audio_shaped)
    subtitle_id = select_subtitle_track(text_shaped)
    subtitle = next((track for track in tracks if track.id == subtitle_id), None)
    already_polish = subtitle is not None and is_polish_language(subtitle.language)
    return TrackSelection(audio_id=audio_id, subtitle_id=subtitle_id, already_polish=already_polish)
