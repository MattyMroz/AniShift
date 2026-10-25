from __future__ import annotations

from typing import Final

import pytest

from anishift.application.selection import (
    ContentJudgement,
    RoleJudgement,
    SubtitleRole,
    subtitle_content,
    subtitle_role,
)
from anishift.services.media.types import MediaTrack, MediaTrackKind

_MINUTE_US: Final[int] = 60_000_000

_EPISODE_US: Final[int] = 24 * _MINUTE_US


def _subtitle(
    track_id: int = 2,
    *,
    entries: int | None = 300,
    language: str | None = "eng",
    name: str | None = None,
    forced: bool = False,
) -> MediaTrack:
    return MediaTrack(
        track_id,
        MediaTrackKind.SUBTITLES,
        "S_TEXT/ASS",
        language,
        name,
        is_default=False,
        is_forced=forced,
        subtitle_format="ass",
        entries=entries,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entries", "duration_us", "forced", "name", "role"),
    [
        pytest.param(9, _EPISODE_US, True, "english", "signs", id="judas_forced_english_9"),
        pytest.param(36, 23 * _MINUTE_US + 42_000_000, False, "forced", "signs", id="forced_36"),
        pytest.param(188, 23 * _MINUTE_US + 36_000_000, False, None, "dialogue", id="thai_amzn_188"),
        pytest.param(251, _EPISODE_US, True, "english subs", "dialogue", id="subsplease_forced_251"),
        pytest.param(251, 12 * _MINUTE_US, False, None, "dialogue", id="short_episode_251_in_12_min"),
    ],
)
def test_role_by_event_rate(entries: int, duration_us: int, forced: bool, name: str | None, role: SubtitleRole) -> None:
    track: MediaTrack = _subtitle(entries=entries, name=name, forced=forced)
    assert subtitle_role(track, duration_us) == RoleJudgement(role)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "forced", "role"),
    [
        pytest.param("signs & songs", False, "signs", id="signs_title"),
        pytest.param(None, True, "signs", id="forced_flag"),
        pytest.param("english", False, "dialogue", id="plain"),
    ],
)
def test_role_between_thresholds_falls_back_to_title_and_flag(
    name: str | None, forced: bool, role: SubtitleRole
) -> None:
    track: MediaTrack = _subtitle(entries=72, name=name, forced=forced)
    assert subtitle_role(track, _EPISODE_US) == RoleJudgement(role, uncertain=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entries", "duration_us"),
    [
        pytest.param(None, _EPISODE_US, id="none"),
        pytest.param(0, _EPISODE_US, id="zero"),
        pytest.param(300, 0, id="no_duration"),
    ],
)
def test_role_without_a_count_falls_back_to_title_and_flag(entries: int | None, duration_us: int) -> None:
    signs: MediaTrack = _subtitle(entries=entries, name="Signs & Songs")
    flagged: MediaTrack = _subtitle(entries=entries, forced=True)
    plain: MediaTrack = _subtitle(entries=entries, name="English")
    assert subtitle_role(signs, duration_us) == RoleJudgement("signs", uncertain=True)
    assert subtitle_role(flagged, duration_us) == RoleJudgement("signs", uncertain=True)
    assert subtitle_role(plain, duration_us) == RoleJudgement("dialogue", uncertain=True)


@pytest.mark.unit
def test_content_is_polish_with_a_polish_dialogue_track() -> None:
    tracks: tuple[MediaTrack, ...] = (_subtitle(2), _subtitle(3, language="pol"))
    assert subtitle_content(tracks, _EPISODE_US, companion=False) == ContentJudgement("polish")


@pytest.mark.unit
def test_content_is_foreign_when_polish_is_only_signs() -> None:
    tracks: tuple[MediaTrack, ...] = (_subtitle(2), _subtitle(3, entries=10, language="pol", name="forced"))
    assert subtitle_content(tracks, _EPISODE_US, companion=False) == ContentJudgement("foreign")


@pytest.mark.unit
def test_content_is_foreign_for_a_language_outside_the_priorities() -> None:
    tracks: tuple[MediaTrack, ...] = (_subtitle(2, language="ara"),)
    assert subtitle_content(tracks, _EPISODE_US, companion=False) == ContentJudgement("foreign")


@pytest.mark.unit
def test_content_is_none_without_text_subtitles() -> None:
    picture: MediaTrack = MediaTrack(2, MediaTrackKind.SUBTITLES, "S_HDMV/PGS", "eng", None, False, False, entries=300)
    assert subtitle_content((), _EPISODE_US, companion=False) == ContentJudgement("none")
    assert subtitle_content((picture,), _EPISODE_US, companion=False) == ContentJudgement("none")


@pytest.mark.unit
def test_content_is_none_with_only_signs() -> None:
    tracks: tuple[MediaTrack, ...] = (_subtitle(2, entries=16, forced=True), _subtitle(3, entries=10, language="pol"))
    assert subtitle_content(tracks, _EPISODE_US, companion=False) == ContentJudgement("none")


@pytest.mark.unit
def test_content_is_foreign_with_a_companion_subtitle_file() -> None:
    signs: MediaTrack = _subtitle(2, entries=16, forced=True)
    assert subtitle_content((), _EPISODE_US, companion=True) == ContentJudgement("foreign")
    assert subtitle_content((signs,), _EPISODE_US, companion=True) == ContentJudgement("foreign")


@pytest.mark.unit
def test_content_is_uncertain_when_the_deciding_track_fell_back() -> None:
    unmeasured: MediaTrack = _subtitle(2, entries=None)
    flagged: MediaTrack = _subtitle(3, entries=None, forced=True)
    assert subtitle_content((unmeasured,), _EPISODE_US, companion=False) == ContentJudgement("foreign", uncertain=True)
    assert subtitle_content((flagged,), _EPISODE_US, companion=False) == ContentJudgement("none", uncertain=True)
    measured: tuple[MediaTrack, ...] = (unmeasured, _subtitle(4))
    assert subtitle_content(measured, _EPISODE_US, companion=False) == ContentJudgement("foreign")
