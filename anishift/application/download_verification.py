"""Structural check of one downloaded episode file against its catalogue runtime, without asserting its identity."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from anishift.services.media.types import MediaTrackKind

if TYPE_CHECKING:
    from anishift.services.media.types import MediaCatalog

__all__ = [
    "ExpectedEpisode",
    "MeasuredMedia",
    "Verification",
    "expected_episode",
    "measured_media",
    "verify",
]

# ── Constants ─────────────────────────────────────────────────────────────────

type DurationSource = Literal["anizip.length", "anizip.runtime"]
"""Identify the ani.zip runtime field the expected duration came from."""

type Verdict = Literal["no_contradiction", "reject", "inconclusive"]
"""Structural evidence only; no result establishes episode identity."""

type VerificationMode = Literal["enforce", "record_only"]
"""Control whether duration evidence may reject a download."""

SHORT_MINUTES: Final[float] = 10.0
"""Use a narrower tolerance below ten catalogue minutes."""

REGULAR_RELATIVE_TOLERANCE: Final[float] = 0.35
"""Allow ordinary opening, ending and catalogue runtime differences."""

SHORT_RELATIVE_TOLERANCE: Final[float] = 0.25
"""Limit proportional drift for short episodes."""

ABSOLUTE_TOLERANCE_SECONDS: Final[float] = 30.0
"""Allow rounding of catalogue runtimes to whole minutes."""

SHORT_MAX_RELATIVE_TOLERANCE: Final[float] = 0.40
"""Prevent the absolute allowance from accepting pairs of very short episodes."""

FRAGMENT_RATIO: Final[float] = 0.50
"""Reject runtimes strictly below half of the expected duration."""

COMPILATION_RATIO: Final[float] = 1.65
"""Reject clear excess runtime, including pairs with shared credits removed."""

SECONDS_PER_MINUTE: Final[int] = 60
"""Convert catalogue minutes to seconds."""

MICROSECONDS_PER_SECOND: Final[float] = 1_000_000.0
"""Convert a container duration to seconds."""

NO_VIDEO_STREAM: Final[str] = "no_video_stream"
"""Reason of the only rejection the record-only mode keeps."""


@dataclass(frozen=True, slots=True)
class ExpectedEpisode:
    """Carry the target runtime in minutes and evidence about its catalogue boundaries."""

    duration_minutes: float | None
    duration_source: DurationSource | None = None
    boundary_conflict: bool = False


@dataclass(frozen=True, slots=True)
class MeasuredMedia:
    """Carry the measured runtime and stream counts of one file."""

    duration_seconds: float | None
    video_streams: int
    audio_streams: int = 0

    def __post_init__(self) -> None:
        counts: tuple[int, ...] = (self.video_streams, self.audio_streams)
        if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts):
            msg: str = "Stream counts must be nonnegative integers"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Verification:
    """Carry effective and observed results without asserting identity or subtitle usability."""

    verdict: Verdict
    reason: str
    mode: VerificationMode = "enforce"
    observed_verdict: Verdict | None = None
    expected_seconds: float | None = None
    measured_seconds: float | None = None
    duration_source: DurationSource | None = None
    boundary_conflict: bool = False


def expected_episode(episodes: Mapping[str, object], episode_key: str) -> ExpectedEpisode:
    """Build the expectation from raw ani.zip episodes using the exact local episode key.

    Prefer a positive numeric ``length``, then ``runtime``; conflicting values are never averaged.

    Raises:
        ValueError: The key is empty or padded.
    """
    if not episode_key or episode_key.strip() != episode_key:
        msg: str = "An exact nonempty local episode key is required"
        raise ValueError(msg)
    episode: Mapping[str, object] = _metadata_object(episodes.get(episode_key))
    duration: float | None
    source: DurationSource | None
    duration, source = _catalog_duration(episode)
    return ExpectedEpisode(
        duration, duration_source=source, boundary_conflict=_boundary_conflict(episodes, episode_key)
    )


def measured_media(catalog: MediaCatalog) -> MeasuredMedia:
    """Measure the container duration and stream counts an identified file reports."""
    duration: float = catalog.duration_us / MICROSECONDS_PER_SECOND
    return MeasuredMedia(
        duration_seconds=duration if _positive_finite(duration) else None,
        video_streams=sum(1 for track in catalog.tracks if track.kind is MediaTrackKind.VIDEO),
        audio_streams=sum(1 for track in catalog.tracks if track.kind is MediaTrackKind.AUDIO),
    )


def verify(expected: ExpectedEpisode, media: MeasuredMedia, *, mode: VerificationMode = "enforce") -> Verification:
    """Check video presence and runtime without I/O or asserting episode identity."""
    result: Verification = _verify(expected, media)
    if mode == "record_only" and result.verdict == "reject" and result.reason != NO_VIDEO_STREAM:
        return replace(result, verdict="inconclusive", mode=mode, observed_verdict=result.verdict)
    return replace(result, mode=mode)


def _identifier(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return str(int(value))
    return None


def _same_tvdb_episode(target: Mapping[str, object], other: Mapping[str, object]) -> bool:
    target_id: str | None = _identifier(target.get("tvdbId"))
    if target_id not in (None, "0") and target_id == _identifier(other.get("tvdbId")):
        return True
    number: str | None = _identifier(target.get("episodeNumber"))
    if number is None or number != _identifier(other.get("episodeNumber")):
        return False
    season: str | None = _identifier(target.get("seasonNumber"))
    other_season: str | None = _identifier(other.get("seasonNumber"))
    return season is None or other_season is None or season == other_season


def _boundary_conflict(episodes: Mapping[str, object], episode_key: str) -> bool:
    target: Mapping[str, object] = _metadata_object(episodes.get(episode_key))
    return any(
        key != episode_key and _same_tvdb_episode(target, _metadata_object(value)) for key, value in episodes.items()
    )


def _metadata_object(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _catalog_duration(episode: Mapping[str, object]) -> tuple[float | None, DurationSource | None]:
    candidates: tuple[tuple[object, DurationSource], ...] = (
        (episode.get("length"), "anizip.length"),
        (episode.get("runtime"), "anizip.runtime"),
    )
    value: object
    source: DurationSource
    for value, source in candidates:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        try:
            minutes: float = float(value)
        except OverflowError:
            continue
        if _positive_finite(minutes) and math.isfinite(minutes * SECONDS_PER_MINUTE):
            return minutes, source
    return None, None


def _verify(expected: ExpectedEpisode, media: MeasuredMedia) -> Verification:
    duration: float | None = _expected_seconds(expected)
    seconds: float | None = media.duration_seconds if _positive_finite(media.duration_seconds) else None
    evidence: Verification = Verification(
        "inconclusive",
        "expected_duration_unavailable",
        expected_seconds=duration,
        measured_seconds=seconds,
        duration_source=expected.duration_source,
        boundary_conflict=expected.boundary_conflict,
    )
    if media.video_streams == 0:
        return replace(evidence, verdict="reject", reason=NO_VIDEO_STREAM)
    if duration is None:
        return evidence
    if seconds is None:
        return replace(evidence, reason="media_duration_unavailable")
    observed: Verification = _verify_duration(duration / SECONDS_PER_MINUTE, duration, seconds)
    result: Verification = replace(evidence, verdict=observed.verdict, reason=observed.reason)
    if result.verdict == "reject" and (expected.boundary_conflict or expected.duration_source != "anizip.length"):
        return replace(result, verdict="inconclusive", observed_verdict=result.verdict)
    return result


def _expected_seconds(expected: ExpectedEpisode) -> float | None:
    minutes: float | None = expected.duration_minutes
    if minutes is None or not _positive_finite(minutes):
        return None
    seconds: float = minutes * SECONDS_PER_MINUTE
    return seconds if math.isfinite(seconds) else None


def _verify_duration(minutes: float, duration: float, seconds: float) -> Verification:
    if seconds < duration * FRAGMENT_RATIO:
        return Verification("reject", "fragment_duration")
    if seconds >= duration * COMPILATION_RATIO:
        return Verification("reject", "compilation_or_extended_duration")
    relative: float = SHORT_RELATIVE_TOLERANCE if minutes < SHORT_MINUTES else REGULAR_RELATIVE_TOLERANCE
    tolerance: float = max(duration * relative, ABSOLUTE_TOLERANCE_SECONDS)
    if minutes < SHORT_MINUTES:
        tolerance = min(tolerance, duration * SHORT_MAX_RELATIVE_TOLERANCE)
    if duration - tolerance <= seconds <= duration + tolerance:
        return Verification("no_contradiction", "duration_within_tolerance")
    return Verification("inconclusive", "duration_outside_tolerance")


def _positive_finite(value: float | None) -> bool:
    return value is not None and not isinstance(value, bool) and math.isfinite(value) and value > 0
