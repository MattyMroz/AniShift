from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.download_verification import (
    NO_VIDEO_STREAM,
    ExpectedEpisode,
    MeasuredMedia,
    Verification,
    expected_episode,
    measured_media,
    verify,
)
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind

_EPISODE: ExpectedEpisode = ExpectedEpisode(24.0, "anizip.length")


@pytest.mark.parametrize(
    ("seconds", "verdict", "reason"),
    [
        (24 * 60, "no_contradiction", "duration_within_tolerance"),
        (24 * 60 * 0.49, "reject", "fragment_duration"),
        (24 * 60 * 1.65, "reject", "compilation_or_extended_duration"),
        (24 * 60 * 1.5, "inconclusive", "duration_outside_tolerance"),
        (None, "inconclusive", "media_duration_unavailable"),
    ],
    ids=["regular", "fragment", "compilation", "outside", "unmeasured"],
)
def test_a_measured_runtime_is_judged_against_the_catalogue_runtime(
    seconds: float | None, verdict: str, reason: str
) -> None:
    result: Verification = verify(_EPISODE, MeasuredMedia(seconds, 1, 1))

    assert (result.verdict, result.reason) == (verdict, reason)
    assert (result.expected_seconds, result.duration_source) == (24 * 60, "anizip.length")


def test_record_only_keeps_only_the_missing_video_rejection() -> None:
    fragment: Verification = verify(_EPISODE, MeasuredMedia(60.0, 1), mode="record_only")
    silent: Verification = verify(_EPISODE, MeasuredMedia(24 * 60.0, 0), mode="record_only")

    assert (fragment.verdict, fragment.observed_verdict, fragment.reason) == (
        "inconclusive",
        "reject",
        "fragment_duration",
    )
    assert (silent.verdict, silent.reason) == ("reject", NO_VIDEO_STREAM)


@pytest.mark.parametrize(
    "expected",
    [ExpectedEpisode(24.0, "anizip.runtime"), ExpectedEpisode(24.0, "anizip.length", boundary_conflict=True)],
    ids=["runtime-field", "boundary-conflict"],
)
def test_weak_catalogue_evidence_never_rejects_a_runtime(expected: ExpectedEpisode) -> None:
    result: Verification = verify(expected, MeasuredMedia(60.0, 1))

    assert (result.verdict, result.observed_verdict) == ("inconclusive", "reject")


def test_an_unknown_catalogue_runtime_is_inconclusive_but_a_missing_video_still_rejects() -> None:
    assert verify(ExpectedEpisode(None), MeasuredMedia(60.0, 1)).reason == "expected_duration_unavailable"
    assert verify(ExpectedEpisode(None), MeasuredMedia(60.0, 0)).verdict == "reject"


@pytest.mark.parametrize(
    ("episode", "expected"),
    [
        ({"length": 23, "runtime": 30}, ExpectedEpisode(23.0, "anizip.length")),
        ({"length": 0, "runtime": 30}, ExpectedEpisode(30.0, "anizip.runtime")),
        ({"length": True, "runtime": "24"}, ExpectedEpisode(None)),
    ],
    ids=["length", "runtime", "unusable"],
)
def test_the_expectation_prefers_a_positive_length_over_the_runtime(
    episode: dict[str, object], expected: ExpectedEpisode
) -> None:
    assert expected_episode({"3": episode}, "3") == expected


def test_an_episode_sharing_a_tvdb_episode_marks_a_boundary_conflict() -> None:
    episodes: dict[str, object] = {"3": {"length": 24, "tvdbId": 9}, "4": {"length": 24, "tvdbId": 9}}

    assert expected_episode(episodes, "3").boundary_conflict


@pytest.mark.parametrize("key", ["", " 3"])
def test_the_expectation_requires_an_exact_episode_key(key: str) -> None:
    with pytest.raises(ValueError, match="exact nonempty"):
        expected_episode({}, key)


def test_a_catalog_is_measured_by_its_container_duration_and_stream_counts() -> None:
    catalog: MediaCatalog = MediaCatalog(
        path=Path("episode.mkv"),
        container=ContainerKind.MKV,
        duration_us=1_440_000_000,
        tracks=(
            MediaTrack(0, MediaTrackKind.VIDEO, "h264", None, None, True, False),
            MediaTrack(1, MediaTrackKind.AUDIO, "aac", "jpn", None, True, False),
            MediaTrack(2, MediaTrackKind.AUDIO, "aac", "eng", None, False, False),
            MediaTrack(3, MediaTrackKind.SUBTITLES, "ass", "pol", None, True, False),
        ),
    )

    assert measured_media(catalog) == MeasuredMedia(1440.0, 1, 2)
    assert measured_media(MediaCatalog(Path("x.mkv"), ContainerKind.MKV, 0, ())).duration_seconds is None
