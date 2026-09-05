"""Pure recognition of the fields carried by an anime release title."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from anishift.services.torrents.types import ReleaseName

__all__ = ["parse_release_name"]

# ── Constants ─────────────────────────────────────────────────────────────────

SERIES_SEPARATOR: Final[str] = " - "
"""Marker splitting the series text from the episode part of a title."""

_GROUP_RE: Final[re.Pattern[str]] = re.compile(r"^\[([^\]]+)\]\s*")
"""Leading bracket carrying the release group."""

_EXTENSION_RE: Final[re.Pattern[str]] = re.compile(r"\.(?:mkv|mp4)$", re.IGNORECASE)
"""Container extension some indexes keep in the title."""

_HASH_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(r"\s*\[[0-9A-Fa-f]{8}\]$")
"""Trailing CRC32 bracket appended by several release groups."""

_TAG_START_RE: Final[re.Pattern[str]] = re.compile(r"[(\[]")
"""First tag block that ends the series text when no separator is present."""

_RESOLUTION_RE: Final[re.Pattern[str]] = re.compile(r"(\d{3,4})p", re.IGNORECASE)
"""Vertical resolution class such as ``1080p``."""

_SEASON_EPISODE_RE: Final[re.Pattern[str]] = re.compile(r"\bS(\d{1,2})E(\d{1,3})(?:v(\d+))?\b", re.IGNORECASE)
"""Combined ``SxxEyy`` season and episode form, with an optional version."""

_EPISODE_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{1,4}(?:\.\d+)?)(?:v(\d+))?\b", re.IGNORECASE)
"""Episode number opening the text after the separator, with an optional version."""

_BATCH_RANGE_RE: Final[re.Pattern[str]] = re.compile(r"\(\s*\d+\s*-\s*\d+\s*\)")
"""Episode range marking a multi-episode pack."""

_BATCH_TAG_RE: Final[re.Pattern[str]] = re.compile(r"\[[^\]]*\bbatch\b[^\]]*\]", re.IGNORECASE)
"""Bracket tag marking a multi-episode pack."""


def parse_release_name(title: str) -> ReleaseName:
    """Recognize group, series, episode, season, resolution, batch, and version in *title*.

    Unknown patterns keep the whole cleaned title as the series and leave the rest empty.
    """
    cleaned: str = _clean(title)
    group_match: re.Match[str] | None = _GROUP_RE.match(cleaned)
    group: str | None = group_match.group(1).strip() if group_match is not None else None
    remainder: str = cleaned[group_match.end() :] if group_match is not None else cleaned
    series, tail = _split_series(remainder)
    season, episode, version = _episode_fields(remainder, tail)
    return ReleaseName(
        group=group,
        series=series,
        episode=episode,
        season=season,
        resolution=_resolution(remainder),
        batch=_is_batch(remainder),
        version=version,
    )


def _clean(title: str) -> str:
    """Collapse whitespace and drop the container extension and trailing CRC bracket."""
    collapsed: str = " ".join(title.split())
    without_extension: str = _EXTENSION_RE.sub("", collapsed)
    return _HASH_SUFFIX_RE.sub("", without_extension).strip()


def _split_series(remainder: str) -> tuple[str, str]:
    """Split the text after the group into the series and the trailing episode part."""
    separator_at: int = remainder.find(SERIES_SEPARATOR)
    if separator_at >= 0:
        return remainder[:separator_at].strip(), remainder[separator_at + len(SERIES_SEPARATOR) :].strip()
    tag_match: re.Match[str] | None = _TAG_START_RE.search(remainder)
    if tag_match is not None:
        return remainder[: tag_match.start()].strip(), ""
    return remainder.strip(), ""


def _episode_fields(remainder: str, tail: str) -> tuple[int | None, Decimal | None, int | None]:
    """Return season, episode, and version from the ``SxxEyy`` form or the trailing part."""
    season_episode: re.Match[str] | None = _SEASON_EPISODE_RE.search(remainder)
    if season_episode is not None:
        return (
            int(season_episode.group(1)),
            Decimal(season_episode.group(2)),
            _optional_int(season_episode.group(3)),
        )
    episode: re.Match[str] | None = _EPISODE_RE.match(tail)
    if episode is None:
        return None, None, None
    return None, Decimal(episode.group(1)), _optional_int(episode.group(2))


def _resolution(remainder: str) -> int | None:
    """Return the first declared vertical resolution."""
    match: re.Match[str] | None = _RESOLUTION_RE.search(remainder)
    return int(match.group(1)) if match is not None else None


def _is_batch(remainder: str) -> bool:
    """Whether the title advertises a multi-episode pack."""
    return _BATCH_RANGE_RE.search(remainder) is not None or _BATCH_TAG_RE.search(remainder) is not None


def _optional_int(value: str | None) -> int | None:
    """Convert a matched numeric group, keeping ``None`` when the group is absent."""
    return int(value) if value else None
