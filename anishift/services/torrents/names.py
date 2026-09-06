"""Pure recognition of the fields carried by an anime release title."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from anishift.services.torrents.types import ReleaseName

__all__ = ["base_title", "parse_release_name", "season_hint", "strip_season", "title_forms"]

# ── Constants ─────────────────────────────────────────────────────────────────

SERIES_SEPARATOR: Final[str] = " - "
"""Marker splitting the series text from the episode part of a title."""

_TECHNICAL_TAGS: Final[tuple[str, ...]] = (
    "1080p", "720p", "2160p", "WEB-DL", "WEBRip", "WEBRiP", "BDRip", "BD", "BILI",
    "CR", "NF", "AMZN", "AAC", "AAC2.0", "DDP", "DDP2.0", "DD+", "H.264", "H.265",
    "x264", "x265", "HEVC", "AVC", "10bit", "Dual-Audio", "DUAL", "MULTi", "MultiSub",
    "Multi-Subs", "SUBFRENCH", "VOSTFR", "VF", "FRENCH", "READNFO",
)  # fmt: skip
"""Source, codec, and language markers that never belong to the series text."""

_TAG_ALTERNATION: Final[str] = "|".join(re.escape(tag) for tag in sorted(_TECHNICAL_TAGS, key=len, reverse=True))
"""Technical tags as one regex branch, longest first so ``AAC2.0`` wins over ``AAC``."""

_GROUP_RE: Final[re.Pattern[str]] = re.compile(r"^\[([^\]]+)\]\s*")
"""Leading bracket carrying the release group."""

_TRAILING_BLOCKS_RE: Final[re.Pattern[str]] = re.compile(r"(?:\s*[(\[][^)\]]*[)\]])+$")
"""Parenthesised or bracketed blocks appended after the release group."""

_TRAILING_GROUP_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?<!\w)(?:{_TAG_ALTERNATION})\s*-([A-Za-z0-9][A-Za-z0-9.\-]*)$", re.IGNORECASE
)
"""Scene-style group written after a technical tag and a dash, as in ``H.264-Tsundere-Raws``."""

_EXTENSION_RE: Final[re.Pattern[str]] = re.compile(r"\.(?:mkv|mp4)$", re.IGNORECASE)
"""Container extension some indexes keep in the title."""

_HASH_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(r"\s*\[[0-9A-Fa-f]{8}\]$")
"""Trailing CRC32 bracket appended by several release groups."""

_DOTTED_RE: Final[re.Pattern[str]] = re.compile(r"^\S+$")
"""Whole title written without a single space, so dots stand for the word separator."""

_TAG_START_RE: Final[re.Pattern[str]] = re.compile(r"[(\[]")
"""First tag block that ends the series text when no separator is present."""

_SERIES_TAIL_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s(?:{_TAG_ALTERNATION}|19\d{{2}}|20\d{{2}}|2100)(?!\w)$", re.IGNORECASE
)
"""Technical tag or release year closing the series text."""

_SERIES_EDGE: Final[str] = " -–—"
"""Characters left dangling at the end of the series text once a marker is cut off."""

_RESOLUTION_RE: Final[re.Pattern[str]] = re.compile(r"(\d{3,4})p", re.IGNORECASE)
"""Vertical resolution class such as ``1080p``."""

_SEASON_EPISODE_RE: Final[re.Pattern[str]] = re.compile(r"\bS(\d{1,2})E(\d{1,3})(?:v(\d+))?\b", re.IGNORECASE)
"""Combined ``SxxEyy`` season and episode form, with an optional version."""

_SEASON_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?<!\w)S(\d{{1,2}})(?!\w)(?=\s+(?:{_TAG_ALTERNATION})(?!\w)|$)", re.IGNORECASE
)
"""Season marker without an episode, recognized only when a technical tag or the title end follows."""

_EPISODE_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{1,4}(?:\.\d+)?)(?:v(\d+))?\b", re.IGNORECASE)
"""Episode number opening the text after the separator, with an optional version."""

_BATCH_RANGE_RE: Final[re.Pattern[str]] = re.compile(r"\(\s*\d+\s*-\s*\d+\s*\)")
"""Episode range marking a multi-episode pack."""

_BATCH_TAG_RE: Final[re.Pattern[str]] = re.compile(r"[(\[][^)\]]*\bbatch\b[^)\]]*[)\]]", re.IGNORECASE)
"""Bracket or parenthesis tag marking a multi-episode pack."""

_FRENCH_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)(?:VOSTFR|SUBFRENCH|FRENCH|VF)(?!\w)", re.IGNORECASE)
"""Markers of a French subtitle track."""

_MULTI_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)(?:MultiSub|Multi-Subs|Multi Sub|MULTi)(?!\w)", re.IGNORECASE)
"""Markers of a release carrying several subtitle languages."""

_DUBBED_RE: Final[re.Pattern[str]] = re.compile(r"\[Dub\]|(?<!\w)(?:(?:English|Eng)\s+Dub|Dubbed)(?!\w)", re.IGNORECASE)
"""Markers of a dubbed audio track; ``Dual-Audio`` alone does not qualify."""

_FRENCH_SUBTITLES: Final[str] = "fr"
"""Subtitle language reported for a French release."""

_MULTI_SUBTITLES: Final[str] = "multi"
"""Subtitle language reported for a release carrying several languages."""

_ROMAN_SEASONS: Final[dict[str, int]] = {
    "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
}  # fmt: skip
"""Roman numerals read as a season; a lone ``I`` is too ambiguous to count."""

_SEASON_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:S(?P<compact>\d{1,2})"
    r"|(?P<ordinal>\d{1,2})(?:st|nd|rd|th)\s+Season"
    r"|Season\s+(?P<numbered>\d{1,2})"
    r"|(?P<roman>VIII|VII|VI|IV|IX|III|II|V|X)(?=\s*[:\-]|$))"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
"""Season marker inside a series text; ``Part`` numbers a cour, not a season, and never matches."""

_SUBTITLE_SEPARATORS: Final[tuple[str, ...]] = (" - ", " -", ": ", " –")
"""Marks opening the subtitle that release names and catalog names drop or keep at will."""


def parse_release_name(title: str) -> ReleaseName:
    """Recognize group, series, episode, season, resolution, batch, version, and language in *title*.

    Reads the group from a leading ``[Group]`` bracket or from a scene-style ``-Group`` suffix, and the
    season and episode from ``SxxEyy``, a lone ``Sxx`` season pack, or the number after the separator.
    Unknown patterns keep the whole cleaned title as the series and leave the rest empty.
    """
    cleaned: str = _clean(title)
    group_match: re.Match[str] | None = _GROUP_RE.match(cleaned)
    remainder: str = cleaned[group_match.end() :] if group_match is not None else cleaned
    if group_match is not None:
        group: str | None = group_match.group(1).strip()
        body: str = remainder
    else:
        group, body = _trailing_group(remainder)
    season, episode, version, series = _name_fields(body)
    return ReleaseName(
        group=group,
        series=series,
        episode=episode,
        season=season,
        resolution=_resolution(remainder),
        batch=_is_batch(remainder),
        version=version,
        subtitle_language=_subtitle_language(remainder),
        dubbed=_DUBBED_RE.search(remainder) is not None,
    )


def season_hint(series: str) -> int | None:
    """Return the season *series* names, or ``None`` when it names none or several.

    Two markers mean a pack spanning seasons, which no single number describes.
    """
    marker: re.Match[str] | None = _season_marker(series)
    return None if marker is None else _marker_season(marker)


def strip_season(series: str) -> str:
    """Return *series* without the marker :func:`season_hint` reads, with spaces collapsed."""
    marker: re.Match[str] | None = _season_marker(series)
    if marker is None:
        return " ".join(series.split())
    return " ".join(f"{series[: marker.start()]} {series[marker.end() :]}".split())


def base_title(text: str) -> str:
    """Return *text* without its season marker and without the subtitle that follows it.

    Release names and catalog names disagree on how much of a subtitle they keep, so the
    shortest shared form is the one both sides can be compared on.
    """
    stripped: str = strip_season(text)
    cuts: list[int] = [at for separator in _SUBTITLE_SEPARATORS if (at := stripped.find(separator)) >= 0]
    head: str = stripped[: min(cuts)] if cuts else stripped
    return " ".join(head.rstrip("- ").split())


def title_forms(text: str) -> frozenset[str]:
    """Return every spelling *text* may be recognized by: as written, without the season, and its base."""
    forms: set[str] = {" ".join(text.split()), strip_season(text), base_title(text)}
    return frozenset(form for form in forms if form)


def _season_marker(series: str) -> re.Match[str] | None:
    """Return the only season marker of *series*, or ``None`` for none or several."""
    markers: list[re.Match[str]] = list(_SEASON_MARKER_RE.finditer(series))
    return markers[0] if len(markers) == 1 else None


def _marker_season(marker: re.Match[str]) -> int:
    """Return the season number one marker carries."""
    roman: str | None = marker.group("roman")
    if roman is not None:
        return _ROMAN_SEASONS[roman.upper()]
    number: str = marker.group("compact") or marker.group("ordinal") or marker.group("numbered")
    return int(number)


def _clean(title: str) -> str:
    """Collapse whitespace, restore dotted names, and drop the extension and trailing CRC bracket."""
    collapsed: str = " ".join(title.split())
    without_extension: str = _EXTENSION_RE.sub("", collapsed)
    bare: str = _HASH_SUFFIX_RE.sub("", without_extension).strip()
    return bare.replace(".", " ") if _DOTTED_RE.fullmatch(bare) else bare


def _trailing_group(remainder: str) -> tuple[str | None, str]:
    """Split a scene-style ``-Group`` suffix off the text, ignoring the blocks appended after it."""
    stripped: str = _TRAILING_BLOCKS_RE.sub("", remainder).rstrip()
    match: re.Match[str] | None = _TRAILING_GROUP_RE.search(stripped)
    if match is None:
        return None, remainder
    return match.group(1).strip(), remainder[: match.start()].rstrip()


def _name_fields(body: str) -> tuple[int | None, Decimal | None, int | None, str]:
    """Return season, episode, version, and series read from the text left after the group."""
    season_episode: re.Match[str] | None = _SEASON_EPISODE_RE.search(body)
    marker: re.Match[str] | None = season_episode if season_episode is not None else _SEASON_ONLY_RE.search(body)
    series, tail = _split_series(body, marker)
    if season_episode is not None:
        return (
            int(season_episode.group(1)),
            Decimal(season_episode.group(2)),
            _optional_int(season_episode.group(3)),
            series,
        )
    season: int | None = int(marker.group(1)) if marker is not None else None
    episode: re.Match[str] | None = _EPISODE_RE.match(tail)
    if episode is None:
        return season, None, None, series
    return season, Decimal(episode.group(1)), _optional_int(episode.group(2)), series


def _split_series(body: str, marker: re.Match[str] | None) -> tuple[str, str]:
    """Split the text after the group into the series and the trailing episode part."""
    separator_at: int = body.find(SERIES_SEPARATOR)
    if separator_at >= 0:
        return _trim_series(body[:separator_at]), body[separator_at + len(SERIES_SEPARATOR) :].strip()
    if marker is not None:
        return _trim_series(body[: marker.start()]), ""
    tag_match: re.Match[str] | None = _TAG_START_RE.search(body)
    if tag_match is not None:
        return _trim_series(body[: tag_match.start()]), ""
    return _trim_series(body), ""


def _trim_series(text: str) -> str:
    """Drop the dangling separator, technical tags, and release year closing the series text."""
    trimmed: str = text.strip().rstrip(_SERIES_EDGE)
    tail: re.Match[str] | None = _SERIES_TAIL_RE.search(trimmed)
    while tail is not None:
        trimmed = trimmed[: tail.start()].rstrip(_SERIES_EDGE)
        tail = _SERIES_TAIL_RE.search(trimmed)
    return trimmed


def _subtitle_language(remainder: str) -> str | None:
    """Return the subtitle language advertised in the title; French wins over a multi-language pack."""
    if _FRENCH_RE.search(remainder) is not None:
        return _FRENCH_SUBTITLES
    if _MULTI_RE.search(remainder) is not None:
        return _MULTI_SUBTITLES
    return None


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
