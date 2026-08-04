"""Select original audio and processable text subtitle tracks from metadata."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from anishift.services.extraction.types import TrackInfo, TrackSelection, is_text_subtitle_codec

__all__ = [
    "DEFAULT_AUDIO_PRIORITY",
    "DEFAULT_SUBTITLE_PRIORITY",
    "is_polish_language",
    "score_audio_track",
    "score_subtitle_track",
    "select_audio_track",
    "select_subtitle_track",
    "select_tracks",
]

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_AUDIO_PRIORITY: Final[tuple[str, ...]] = ("jpn", "eng", "zho")
"""Audio languages preferred by the scorer, most wanted first."""

DEFAULT_SUBTITLE_PRIORITY: Final[tuple[str, ...]] = ("pol", "eng")
"""Subtitle languages preferred by the scorer, most wanted first."""

_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "ja": "jpn",
    "en": "eng",
    "pl": "pol",
    "zh": "zho",
    "chi": "zho",
    "chs": "zho",
    "cht": "zho",
}
"""Two-letter and legacy tags mapped to the form used in priority lists."""

_TOP_LANGUAGE_SCORE: Final[int] = 100
"""Score of the first language in a priority list."""

_LANGUAGE_STEP: Final[int] = 10
"""Score lost per position in a priority list."""

_UNRANKED_LANGUAGE_SCORE: Final[int] = 0
"""Score of a language absent from the priority list."""

_SIGNS_PENALTY: Final[int] = -200
"""Penalty for signs, songs, or forced subtitle tracks."""

_DEFAULT_BONUS: Final[int] = 1
"""Bonus for a default audio track, kept below one language-priority step so
it only breaks ties inside a language and never outranks a preferred one."""

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


def _language_score(language: str, priority: tuple[str, ...]) -> int:
    """Return a descending score based on position in the priority list."""
    normalized: str = language.casefold()
    canonical: str = _LANGUAGE_ALIASES.get(normalized, normalized)
    if canonical not in priority:
        return _UNRANKED_LANGUAGE_SCORE
    return _TOP_LANGUAGE_SCORE - priority.index(canonical) * _LANGUAGE_STEP


def score_subtitle_track(
    track: dict[str, Any],
    priority: tuple[str, ...] = DEFAULT_SUBTITLE_PRIORITY,
) -> float:
    """Score a subtitle track for translation and narration."""
    score = float(_language_score(_track_language(track), priority))
    if _is_signs_only(track):
        score += _SIGNS_PENALTY
    return score + _lines_bonus(track)


def score_audio_track(
    track: dict[str, Any],
    priority: tuple[str, ...] = DEFAULT_AUDIO_PRIORITY,
) -> float:
    """Score an audio track for use under the narrator."""
    score = float(_language_score(_track_language(track), priority))
    if _track_default(track):
        score += _DEFAULT_BONUS
    return score


def select_subtitle_track(
    tracks: list[dict[str, Any]],
    priority: tuple[str, ...] = DEFAULT_SUBTITLE_PRIORITY,
) -> int | None:
    """Pick the highest-scoring subtitle track, preferring lower ids on ties."""
    subtitles = [track for track in tracks if track.get("type") == "subtitles"]
    if not subtitles:
        return None
    best = max(subtitles, key=lambda track: (score_subtitle_track(track, priority), -int(track["id"])))
    return int(best["id"])


def select_audio_track(
    tracks: list[dict[str, Any]],
    priority: tuple[str, ...] = DEFAULT_AUDIO_PRIORITY,
) -> int | None:
    """Pick the highest-scoring audio track, preferring lower ids on ties."""
    audio = [track for track in tracks if track.get("type") == "audio"]
    if not audio:
        return None
    best = max(audio, key=lambda track: (score_audio_track(track, priority), -int(track["id"])))
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


def select_tracks(
    tracks: Sequence[TrackInfo],
    *,
    audio_priority: tuple[str, ...] = DEFAULT_AUDIO_PRIORITY,
    subtitle_priority: tuple[str, ...] = DEFAULT_SUBTITLE_PRIORITY,
) -> TrackSelection:
    """Pick one audio track and one processable text subtitle track."""
    audio_shaped = [_selector_shape(track) for track in tracks if track.type == "audio"]
    text_shaped = [
        _selector_shape(track)
        for track in tracks
        if track.type == "subtitles" and is_text_subtitle_codec(track.codec_id)
    ]
    audio_id = select_audio_track(audio_shaped, audio_priority)
    subtitle_id = select_subtitle_track(text_shaped, subtitle_priority)
    subtitle = next((track for track in tracks if track.id == subtitle_id), None)
    already_polish = subtitle is not None and is_polish_language(subtitle.language)
    return TrackSelection(audio_id=audio_id, subtitle_id=subtitle_id, already_polish=already_polish)
