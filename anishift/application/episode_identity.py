"""Assess selected-file identity with H1 v10.7 without inspecting media or performing I/O."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from difflib import SequenceMatcher
from enum import StrEnum
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Final, Literal, cast

# ── Constants ─────────────────────────────────────────────────────────────────

type Metadata = Mapping[str, Any]
"""Accept runtime metadata without requiring corpus labels or identifiers."""
type NumberMode = Literal["missing", "plain", "mapped"]
"""Preserve the explicit namespace of a parsed episode number."""
type MediaKind = Literal["TV", "TV_SHORT", "MOVIE", "OVA", "ONA", "SPECIAL", "MUSIC", "UNKNOWN"]
"""Represent supported catalogue formats without inferring a missing format."""
MEDIA_KINDS: Final[frozenset[str]] = frozenset(("TV", "TV_SHORT", "MOVIE", "OVA", "ONA", "SPECIAL", "MUSIC"))
"""Allow known catalogue format values at the runtime boundary."""
SEASON_PREFIX: Final[str] = r"(?:season\s*|s)"
"""Recognize textual and abbreviated season markers."""
PART_PREFIX: Final[str] = r"(?:part\s*|cour\s*|p)"
"""Recognize textual and abbreviated part markers."""
MAPPED_SEASON: Final[re.Pattern[str]] = re.compile(r"(?i)\bs\d{1,2}\s*(e\d{1,4})")
"""Match the season half of an SxxEyy token so it can be dropped when the target has no numbering."""
MEDIA_MARKER: Final[re.Pattern[str]] = re.compile(r"\b(?:ova|oad|specials?|movies?)\b")
"""Detect explicit media format qualifiers."""
FIRST_BRACKET: Final[re.Pattern[str]] = re.compile(r"^\s*\[([^\]]+)\]\s*")
"""Capture a potential release group without assuming its content is disposable."""
TEXT_CACHE_SIZE: Final[int] = 8192
"""Bound reusable pure title normalization across candidates of the same episode."""
VIDEO_EXTENSIONS: Final[frozenset[str]] = frozenset(
    ("mkv", "mp4", "avi", "ts", "m2ts", "webm", "m4v", "wmv", "flv", "ogm")
)
"""Allow video containers at the selected-file boundary."""
TECHNICAL: Final[re.Pattern[str]] = re.compile(
    r"(?:\d{3,4}p|\d{3,4}i|\d{3,4}x\d{3,4}p?|[xh] ?26[45]|hevc|avc|av1|vp9|xvid|divx|"
    r"(?:hi|ma|main)?(?:8|10|12)(?:bit|p)|8bits|(?:8|10|12) bits?|yuv\d+p\d*|"
    r"bd(?:rip|remux|mux|mv|\d{3,4}p)?|blu ?ray|dvd(?:rip|remux)?|web(?: ?dl| ?rip)?|hdtv|hdrip|remux|"
    r"aac\d?(?:\.\d)?|flac\d?(?:\.\d)?|opus(?:\d\.\d)?|ac3|eac3|ddp?(?:\d\.\d)?|dts(?: ?hd)?|truehd|lpcm|pcm|"
    r"(?:1|2|5|7)\.\d(?:ch)?|stereo|mono|atmos|hd|ma|"
    r"dual(?: ?audio)?|tri ?audio|multi(?:ple)?(?: ?audio| ?subs?| ?subtitles?)?|m?sub(?:s|bed|titles?)?|dub(?:bed)?|"
    r"eng(?:lish)?|jpn|jap(?:anese)?|rus(?:sian)?|ger(?:man)?|fre(?:nch)?|ita(?:lian)?|spa(?:nish)?|"
    r"por(?:tuguese)?|pol(?:ish)?|ara(?:bic)?|chi(?:nese)?|kor(?:ean)?|latino|pt br|es la|br|la|vostfr|engsubs|"
    r"nf|cr|amzn|dsnp|hidi|b global|netflix|crunchyroll|amazon|bilibili|hidive|"
    r"hdr\d*|sdr|dv|dolby vision|uhd|repack\d*|proper|v\d+|[0-9a-f]{8}|"
    r"mkv|mp4|avi|nvenc|bs\d+|laserdisc|tv|complete|batch|end|fin|uncensored|uncut)\b"
)
"""Consume closed technical metadata without discarding arbitrary title words."""
EXTRAS: Final[re.Pattern[str]] = re.compile(
    r"\b(?:nc(?:op|ed)?\d*|op\d*|ed\d*|pv\d*|sp\d*|cm\d*|omake|yokoku|bonus|extras?|"
    r"opening|ending|teaser|trailers?|menus?|recap|compilation|picture drama|mini anime|"
    r"audio commentary|creditless|sample|featurettes?|behind ?the ?scenes|deleted scenes|"
    r"interviews?|making of|music video)\b"
)
"""Recognize explicit non-episode material after the work anchor."""
PLEX_FOLDERS: Final[frozenset[str]] = frozenset(
    ("featurettes", "behind the scenes", "deleted scenes", "interviews", "scenes", "shorts", "other", "trailers")
)
"""Recognize complete Plex extra-directory names without matching episode-title words."""
PLEX_SUFFIX: Final[re.Pattern[str]] = re.compile(
    r"-(?:featurette|behindthescenes|deleted|interview|scene|short|other|trailer)$", re.IGNORECASE
)
"""Recognize explicit Plex extra suffixes before the filename extension."""
EXTRA_FOLDERS: Final[frozenset[str]] = PLEX_FOLDERS | {"extras"}
"""Recognize complete extra-directory names counted apart from episode videos."""
EXTRA_MARKER: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?<![^\W_])(?:nc[ ._-]?(?:op|ed)|creditless(?:[ ._-]+(?:op|ed|opening|ending))?)"
    r"(?:[ ._-]*\d{1,2})?(?:[ ._-]*v\d)?(?![^\W_])"
)
"""Find an NCOP, NCED or creditless marker with its own optional number and version."""
BRACKET_TAG: Final[re.Pattern[str]] = re.compile(r"\[([^\]]*)\]|\(([^)]*)\)")
"""Find one bracketed tag, dropped only when its content is technical or a checksum."""
LANGUAGE_FORMATS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"剧场版|劇場版|\bфильм\b"), "MOVIE"),
    (re.compile(r"特典|番外|総集編|总集篇|特別編|特别篇|\bспешл\b"), "SPECIAL"),  # noqa: RUF001
    (re.compile(r"\bова\b"), "OVA"),  # noqa: RUF001
)
"""Recognize general CJK and Russian format declarations in package context."""
SEASON_WORDS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "first": 1,
        "one": 1,
        "second": 2,
        "two": 2,
        "third": 3,
        "three": 3,
        "fourth": 4,
        "four": 4,
        "fifth": 5,
        "five": 5,
        "sixth": 6,
        "six": 6,
        "seventh": 7,
        "seven": 7,
        "eighth": 8,
        "eight": 8,
        "ninth": 9,
        "nine": 9,
        "tenth": 10,
        "ten": 10,
    }
)
"""Resolve spelled English season numbers without treating them as technical words."""
CJK_SEASONS: Final[Mapping[str, int]] = MappingProxyType(
    {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
)
"""Resolve common CJK season ordinals while leaving unknown forms uncertain."""
CONTEXT_NUMBER: Final[str] = r"(?:\d{1,2}|[ivxlcdm]+|[一二三四五六七八九十]+)"
"""Recognize explicit decimal, Roman and common CJK ordinal tokens."""
LOCAL_SEASON: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:saison|staffel|temporada|stagione)\s*(" + CONTEXT_NUMBER + r")\b|"
    r"시즌\s*(\d{1,2})(?!\d)|(?:第\s*)?(" + CONTEXT_NUMBER + r")\s*[期季])"
)
"""Recognize localized season declarations without a work-title lookup table."""
ROMAN_CONTEXT: Final[re.Pattern[str]] = re.compile(r"\b(season|part|cour)\s+([ivxlcdm]+)\b")
"""Recognize Roman season and part declarations independently of a work anchor."""
ORDINAL_PART: Final[re.Pattern[str]] = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:part|cour)\b")
"""Recognize English ordinal part and cour declarations."""
LOCAL_MOVIE: Final[re.Pattern[str]] = re.compile(r"극장판|\bgekij(?:ou|o|ō)ban\b")
"""Recognize Korean and romanized Japanese movie declarations."""
SEQUEL_CONTEXT: Final[re.Pattern[str]] = re.compile(r"(?:^|\s)続(?=\s|$)")
"""Treat unconsumed continuation markers as unresolved work identity."""
EDITING_VARIANT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:directors? cut|extended (?:cut|edition|version)|theatrical (?:cut|edition|version)|"
    r"broadcast (?:cut|edition|version)|original (?:cut|edition)|recut)\b"
)
"""Recognize explicit editing variants independently of encoding and remaster quality."""
DIRECTORY_NUMBER: Final[re.Pattern[str]] = re.compile(r"(\d{1,2})\b")
"""Read a trailing directory number without conflating it with a numbered work title."""
MIN_CANONICAL: Final[int] = 6
"""Require six characters for title separator and long-vowel equivalence."""
MIN_SUFFIX_WORDS: Final[int] = 2
"""Require a descriptive subtitle for a short first-season alias."""
EPISODE_SIMILARITY: Final[float] = 0.94
"""Require close spelling and matching numeric tokens for episode titles."""
FIRST_YEAR: Final[int] = 1900
"""Separate calendar years from bare episode numbers."""
REASONS: Final[frozenset[str]] = frozenset(
    {
        "Mapped absolute number exceeds the local episode range under a specific title.",
        "Named season, local episode and catalog episode title agree.",
        "Season marker conflicts with the target numbering system.",
        "Part/cour marker conflicts with the target.",
        "A franchise alias does not identify this installment.",
        "The required part/cour is not established.",
        "Explicit mapped episode differs from target.",
        "Work anchor and exact mapped season/episode match; residual is technical or catalogued.",
        "Movie segment or numbering requires a more specific identity anchor.",
        "Movie title matches with compatible year and no unidentified residual.",
        "OVA/special needs a mapped episode or catalog episode title.",
        "No unambiguous selected episode number.",
        "Bare number is not the local episode; absolute numbering is not established.",
        "Local and mapped numbering conflict.",
        "Specific work title and local episode match; residual is technical or catalogued.",
        "Package directory explicitly identifies Plex extra material.",
        "Package explicitly identifies a neighboring work.",
        "Package explicitly identifies a different season.",
        "Package explicitly identifies a different part/cour.",
        "Package explicitly identifies a different final season.",
        "Package contains an unresolved sequel qualifier.",
        "Package localized season conflicts with the target or is unresolved.",
        "Package Roman season/part conflicts with the target or is unresolved.",
        "Package ordinal part/cour conflicts with the target.",
        "Package localized movie format conflicts with the target.",
        "Package contains an unresolved continuation marker.",
        "Package contains an uncatalogued title suffix.",
        "Package explicitly identifies a different language-specific media format.",
        "Package season declaration conflicts with the target or is unresolved.",
        "Package Russian season declaration is unresolved.",
        "Package explicitly identifies non-episode material.",
        "Package explicitly identifies a different media type.",
        "Package year conflicts with target metadata.",
        "Package explicitly identifies a numbered sequel.",
        "Titleless file lacks an unambiguous nearest work directory or single-work release.",
        "Selected file or work directory identifies a neighboring catalogue work.",
        "Selected directory has a numbered season conflicting with the target.",
        "Selected TV variant conflicts with the target editing variant.",
        "Release editing variant is not established for the target episode.",
        "Malformed candidate metadata.",
        "No selected file.",
        "Selected file has no allowed video extension.",
        "Malformed target or archived identity metadata.",
        "Selected filename has an explicit Plex extra suffix.",
        "Selected residual explicitly identifies non-episode material.",
        "Unresolved leading bracket is the nearest identity context.",
        "Selected filename more specifically identifies a neighboring work.",
        "Filename year is missing from or conflicts with runtime target metadata.",
        "Unconsumed filename text is neither technical metadata nor a catalog episode title.",
        "Mapped numbering cannot be checked without target numbering.",
        "Mapped number equals the target absolute number; numbering is ambiguous.",
    }
)
"""Enumerate every identity explanation, including reasons returned by context-conflict helpers."""
CONFLICT_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "Season marker conflicts with the target numbering system.": "inny sezon",
        "Part/cour marker conflicts with the target.": "inna część",
        "Local and mapped numbering conflict.": "inny numer",
        "Package directory explicitly identifies Plex extra material.": "dodatek",
        "Package explicitly identifies a neighboring work.": "inne dzieło",
        "Package explicitly identifies a different season.": "inny sezon",
        "Package explicitly identifies a different part/cour.": "inna część",
        "Package explicitly identifies a different final season.": "inny sezon",
        "Package ordinal part/cour conflicts with the target.": "inna część",
        "Package localized movie format conflicts with the target.": "inny rodzaj (film)",
        "Package explicitly identifies a different language-specific media format.": "inny rodzaj materiału",
        "Package explicitly identifies non-episode material.": "nie odcinek",
        "Package explicitly identifies a different media type.": "inny rodzaj materiału",
        "Package year conflicts with target metadata.": "inne dzieło (rok)",
        "Package explicitly identifies a numbered sequel.": "kontynuacja",
        "Selected file or work directory identifies a neighboring catalogue work.": "inne dzieło",
        "Selected directory has a numbered season conflicting with the target.": "inny sezon",
        "Selected TV variant conflicts with the target editing variant.": "inny wariant montażu",
        "Selected filename more specifically identifies a neighboring work.": "inne dzieło",
    }
)
"""Label each uncertain reason that declares an explicit contradiction with the target."""
MISMATCH_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "Explicit mapped episode differs from target.": "inny odcinek",
        "Selected file has no allowed video extension.": "nie wideo",
        "Selected filename has an explicit Plex extra suffix.": "dodatek",
        "Selected residual explicitly identifies non-episode material.": "nie odcinek",
    }
)
"""Label every mismatch reason; each mismatch is a conflict."""
CONFLICT_REASONS: Final[frozenset[str]] = frozenset(CONFLICT_LABELS)
"""Close the list of uncertain reasons that count as a conflict with the target."""


class IdentityVerdict(StrEnum):
    """Represent filename evidence rather than verified media identity."""

    MATCH = "match"
    INSUFFICIENT = "insufficient_evidence"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class IdentityAssessment:
    """Return the filename verdict and its explanation without claiming media verification."""

    verdict: IdentityVerdict
    reason: str


@dataclass(frozen=True, slots=True)
class IdentityEvidence:
    """H1 evidence required by the frozen model, independently of source quality and research vetoes."""

    assessment: IdentityAssessment
    kind: str
    mode: str
    selected: str
    path: str
    release: str
    anchor: bool
    broad: bool
    number: Decimal | None
    season: int | None
    part: int | None
    local: int | None
    episode: int | None
    absolute: int | None
    target_season: int | None
    target_part: int | None
    named_season: int | None
    residual: str
    residual_ok: bool
    episode_anchor: bool
    year_ok: bool
    multiple_works: bool


@dataclass(frozen=True)
class _Target:
    """Contain runtime identity metadata without labels or record identifiers."""

    titles: tuple[str, ...]
    broad: tuple[str, ...]
    neighbors: tuple[str, ...]
    episode_titles: tuple[str, ...]
    other_episodes: tuple[str, ...]
    kind: MediaKind
    local: int | None
    episode: int | None
    season: int | None
    absolute: int | None
    year: int | None
    named_season: int | None
    part: int | None
    count: int | None
    neighbor_years: frozenset[int]
    canonical_episodes: tuple[tuple[str, tuple[str, ...]], ...]
    canonical_others: tuple[str, ...]


@dataclass(frozen=True)
class _Parsed:
    """Preserve the selected title anchor and explicit number namespace."""

    anchor: str = ""
    broad: bool = False
    season: int | None = None
    part: int | None = None
    number: int | None = None
    mode: NumberMode = "missing"
    remainder: str = ""
    episode_title: bool = False


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _normalize(value: str) -> str:
    text: str = unicodedata.normalize("NFC", value.casefold()).replace("\u2019", "'")
    text = "".join(chr(ord(char) - 0xFEE0) if "\uff01" <= char <= "\uff5e" else char for char in text)
    text = re.sub(r"(?<=\w)'(?=\w)", "", text)
    text = re.sub(r"!(?!!)|\?(?!\?)", " ", text) if "!!" not in text else text
    text = re.sub(r"((?:aac|flac|ddp?|dts|ac3)?[1257])\.([01])\b", r"\1decimalpoint\2", text)
    text = text.replace(".", " ")
    text = re.sub(r"[^\w.'°²³!]+|_", " ", text)
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\s+season\b", r"season \1", text)
    return " ".join(text.split()).replace("decimalpoint", ".")


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _canonical(text: str) -> str:
    return re.sub(r"[\s.-]", "", text).replace("ou", "o").replace("oo", "o").replace("uu", "u")


def _names(value: Any) -> tuple[str, ...]:
    values: Any = list(value.values()) if isinstance(value, dict) else value
    if not isinstance(values, (list, tuple)):
        return ()
    return tuple(sorted({_normalize(item) for item in values if isinstance(item, str) and item}))


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _metadata_names(value: Any) -> set[str]:
    if isinstance(value, str):
        return {_normalize(value)} if value.strip() else set()
    if isinstance(value, dict):
        return set().union(*(_metadata_names(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_metadata_names(item) for item in value))
    return set()


def _work_names(source: Metadata) -> set[str]:
    return set().union(*(_metadata_names(source.get(key)) for key in ("title", "titles", "synonyms", "aliases")))


def _metadata_year(value: Metadata) -> int | None:
    date: Any = value.get("startDate")
    year: int | None = _integer(value.get("seasonYear") or value.get("year"))
    if year is not None:
        return year
    if isinstance(date, dict):
        return _integer(date.get("year"))
    date = date or value.get("airDate")
    if isinstance(date, str) and re.match(r"^(?:19|20)\d{2}-", date):
        return int(date[:4])
    return None


def _mapping_episode_titles(mapping: Metadata, season: int | None, episode: int | None) -> tuple[set[str], set[str]]:
    own: set[str] = set()
    others: set[str] = set()
    for item in mapping.get("episodes") or []:
        if not isinstance(item, dict):
            continue
        titles: set[str] = _metadata_names(item.get("title")) | _metadata_names(item.get("titles"))
        matched: bool = (
            season is not None
            and episode is not None
            and item.get("seasonNumber") == season
            and item.get("episodeNumber") == episode
        )
        (own if matched else others).update(titles)
    return own, others


def _marker(text: str, kind: str) -> int | None:
    prefix: str = SEASON_PREFIX if kind == "season" else PART_PREFIX
    match: re.Match[str] | None = re.search(r"\b" + prefix + r"(\d{1,2})(?!\d|\w)", text)
    return int(match.group(1)) if match else None


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _prefix(text: str, title: str) -> str | None:
    if text == title:
        return ""
    if text.startswith(title + " "):
        return text[len(title) :].strip()
    if len(_canonical(title)) < MIN_CANONICAL:
        return None
    words: list[str] = text.split()
    for stop in range(1, len(words) + 1):
        if _canonical(" ".join(words[:stop])) == _canonical(title):
            return " ".join(words[stop:])
    return None


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _match(text: str, titles: tuple[str, ...]) -> tuple[str, str]:
    for title in sorted(titles, key=lambda item: (-len(item), item)):
        remainder: str | None = _prefix(text, title)
        if remainder is not None:
            return title, remainder
    return "", text


def _title_variants(titles: tuple[str, ...]) -> tuple[str, ...]:
    variants: set[str] = set(titles)
    for title in titles:
        match: re.Match[str] | None = re.search(r"\bseason (\d+)|\s(\d{1,2})$", title)
        if not match:
            continue
        number: int = int(match.group(1) or match.group(2))
        base: str = title[: match.start()].strip()
        suffix: str = title[match.end() :]
        variants.update(
            (f"{base} s{number}{suffix}", f"{base} s{number:02}{suffix}", f"{base} season {number}{suffix}")
        )
    return tuple(sorted(variants))


def _specific_titles(candidates: tuple[str, ...], neighbors: set[str], *, first_local: bool) -> tuple[str, ...]:
    titles: set[str] = set()
    for title in candidates:
        longer: list[str] = [other[len(title) :].strip() for other in candidates if other.startswith(title + " ")]
        short_allowed: bool = first_local and all(
            len(suffix.split()) >= MIN_SUFFIX_WORDS
            and not re.match(r"(?:\d|[ivx]+\b|season\b|part\b|the\b|movie\b|ova\b|special\b|final\b)", suffix)
            for suffix in longer
        )
        if title not in neighbors and (not longer or short_allowed):
            titles.add(title)
    return _title_variants(tuple(titles))


def _target(target: Metadata, evidence: Metadata) -> _Target:
    catalog: Metadata = evidence.get("target_catalog") or {}
    mapping: Metadata = evidence.get("target_episode") or {}
    mappings: Metadata = evidence.get("target_mappings") or {}
    aliases: tuple[str, ...] = _names(target.get("aliases"))
    neighbors: set[str] = set(_names(target.get("other_series")))
    related: list[Metadata] = [
        entry
        for entry in evidence.get("related_catalog_entries") or []
        if not (
            _work_names(catalog)
            and _work_names(entry) == _work_names(catalog)
            and entry.get("format") == catalog.get("format")
            and _metadata_year(entry) == _metadata_year(catalog)
        )
    ]
    for entry in related:
        neighbors.update(_work_names(entry))
    local: int | None = _integer(target.get("local_episode"))
    season: int | None = _integer(
        target.get("season") if target.get("season") is not None else mapping.get("seasonNumber")
    )
    absolute: int | None = _integer(
        target.get("absolute") if target.get("absolute") is not None else mapping.get("absoluteEpisodeNumber")
    )
    episode: int | None = _integer(
        target.get("episode") if target.get("episode") is not None else mapping.get("episodeNumber")
    )
    candidates: tuple[str, ...] = tuple(
        sorted((set(aliases) | _work_names(catalog) | _work_names(mappings)) - neighbors)
    )
    own: set[str]
    others: set[str]
    own, others = _mapping_episode_titles(mappings, season, episode)
    episode_titles: set[str] = (
        set(_names([target.get("episode_title")]))
        | own
        | _metadata_names(mapping.get("title"))
        | _metadata_names(mapping.get("titles"))
    )
    raw_kind: str = str(target.get("type") or catalog.get("format") or "")
    kind: MediaKind = cast("MediaKind", raw_kind) if raw_kind in MEDIA_KINDS else "UNKNOWN"
    year: int | None = (
        _integer(catalog.get("seasonYear") or target.get("year")) or _metadata_year(catalog) or _metadata_year(mappings)
    )
    if kind == "MOVIE":
        year = year or _metadata_year(mapping)
    named: list[int] = [number for title in candidates if (number := _marker(title, "season")) is not None]
    parts: list[int] = [number for title in candidates if (number := _marker(title, "part")) is not None]
    other_episodes: tuple[str, ...] = tuple(sorted(set(_names(target.get("other_episode_titles"))) | others))
    return _Target(
        titles=_specific_titles(candidates, neighbors, first_local=season == 1 and local == absolute),
        broad=aliases,
        neighbors=tuple(sorted(neighbors)),
        episode_titles=tuple(sorted(episode_titles)),
        other_episodes=other_episodes,
        kind=kind,
        local=local,
        episode=episode,
        season=season,
        absolute=absolute,
        year=year,
        named_season=max(named) if named else season,
        part=max(parts) if parts else None,
        count=_integer(catalog.get("episodes")),
        neighbor_years=frozenset(value for entry in related if (value := _metadata_year(entry)) is not None),
        canonical_episodes=tuple(
            (_canonical(title), tuple(re.findall(r"\d+", title)))
            for title in sorted(episode_titles)
            if len(title) >= MIN_CANONICAL
        ),
        canonical_others=tuple(_canonical(title) for title in other_episodes),
    )


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _prepare(value: str) -> str:
    text: str = value
    semantic: bool = bool(
        EXTRAS.search(_normalize(text))
        or MEDIA_MARKER.search(_normalize(text))
        or re.search(r"\bcd\d+\b", _normalize(text))
    )
    if not semantic:
        text = re.sub(
            r"(?i)(\b(?:x26[45]|h[ .]?26[45]|av1|hevc|aac|flac|msubs|(?<!-)(?:dual|multi)))"
            r"-(?:[a-z][a-z0-9]*|[a-z]+(?:-[a-z]+)+)(?=\[[^\]]*\]$|$)",
            r"\1",
            text,
        )
        text = re.sub(r"\[(?:[\w-]+\.)+[a-z]{2,}\]$", "", text, flags=re.IGNORECASE)
        prefix: re.Match[str] | None = FIRST_BRACKET.match(text)
        if prefix:
            text = text[: prefix.end()] + re.sub(
                r"[\[(]" + re.escape(prefix.group(1)) + r"[\])]", " ", text[prefix.end() :]
            )
    text = re.sub(r"(?i)\b(ddp|aac|flac|opus)(\d) (\d)\b", r"\1\2.\3", text)
    text = re.sub(r"(?i)\b(h|x)[ ._-]+(26[45])\b", r"\1\2", text)
    text = re.sub(r"(?i)\b(?:u-next|adn|at x|at-x|dsny|dsnp|abema|baha)\b", "web", text)
    text = re.sub(r"(?i)\b(?:dovi|dv hdr|hdr10\+|dolbyvision)\b", "hdr", text)
    return re.sub(r"(?i)\b(?:10bits|10-bit|hi10)\b", "10bit", text)


@lru_cache(maxsize=TEXT_CACHE_SIZE)
def _technical(text: str) -> bool:
    remainder: str = text.strip()
    while remainder:
        token: re.Match[str] | None = TECHNICAL.match(remainder)
        if not token:
            return False
        remainder = remainder[token.end() :].strip()
    return True


def _strip_group(text: str) -> str:
    match: re.Match[str] | None = FIRST_BRACKET.match(text)
    return text[match.end() :] if match and not EXTRAS.search(_normalize(match.group(1))) else text


def _without_episode_title(text: str, target: _Target) -> tuple[str, bool]:
    remainder: str = text.strip()
    for title in sorted(target.episode_titles, key=len, reverse=True):
        if title not in ("complete movie", "movie", "tv special") and (
            remainder == title or remainder.startswith(title + " ")
        ):
            return remainder[len(title) :].strip(), True
    return remainder, False


def _residual(text: str, target: _Target) -> tuple[bool, bool]:
    remainder: str
    anchored: bool
    remainder, anchored = _without_episode_title(text, target)
    for title in sorted(target.titles, key=len, reverse=True):
        if remainder.endswith(" " + title):
            remainder = remainder[: -len(title)].strip()
            break
    return _technical(remainder), anchored


def _episode_residual(text: str, target: _Target) -> tuple[bool, bool]:
    exact: tuple[bool, bool] = _residual(text, target)
    if exact[0]:
        return exact
    words: list[str] = text.split()
    for stop in range(len(words), 0, -1):
        prefix: str = " ".join(words[:stop])
        if not _technical(" ".join(words[stop:])):
            continue
        canonical: str = _canonical(prefix)
        numbers: tuple[str, ...] = tuple(re.findall(r"\d+", prefix))
        best: float = max(
            (
                _similarity(canonical, title, EPISODE_SIMILARITY)
                for title, digits in target.canonical_episodes
                if digits == numbers
            ),
            default=0.0,
        )
        if best < EPISODE_SIMILARITY or EXTRAS.search(prefix):
            continue
        if not any(_similarity(canonical, title, best) >= best for title in target.canonical_others):
            return True, True
    return exact


def _absolute_echo(stem: str, parsed: _Parsed, target: _Target) -> _Parsed:
    if parsed.mode != "plain" or target.absolute is None or parsed.number != target.local:
        return parsed
    if target.absolute == target.local or not re.search(rf"\b0*{target.local}\s*\(0*{target.absolute}\)", stem):
        return parsed
    echo: re.Match[str] | None = re.match(rf"0*{target.absolute}\b", parsed.remainder)
    return replace(parsed, remainder=parsed.remainder[echo.end() :].strip()) if echo else parsed


def _similarity(text: str, title: str, threshold: float) -> float:
    matcher: SequenceMatcher[str] = SequenceMatcher(None, text, title)
    if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
        return 0.0
    return matcher.ratio()


def _year(text: str, target: _Target) -> tuple[str, bool]:
    years: set[int] = {int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", text)}
    if not years:
        return text, True
    allowed: bool = (
        years == {target.year}
        if target.year is not None
        else (target.kind == "MOVIE" and len(years) == 1 and not years & target.neighbor_years)
    )
    return (re.sub(r"\b(?:19|20)\d{2}\b", " ", text).strip(), True) if allowed else (text, False)


def _parse(text: str, target: _Target) -> _Parsed:
    name: str = _normalize(_strip_group(text))
    anchor: str
    remainder: str
    anchor, remainder = _match(name, target.titles)
    broad: bool = False
    if not anchor:
        anchor, remainder = _match(name, target.broad)
        broad = bool(anchor)
    if anchor:
        alias: str
        tail: str
        alias, tail = _match(remainder, target.titles)
        remainder = tail if alias else remainder
    yearless: str
    valid: bool
    yearless, valid = _year(remainder, target)
    remainder = yearless if valid else remainder
    remainder = re.sub(r"^第\s*(\d{1,4})\s*[话話集](?=\s|$)", r"\1", remainder)
    remainder = re.sub(r"^e\s+(\d{1,4})\b", r"e\1", remainder)
    season: int | None = None
    part: int | None = None
    season_match: re.Match[str] | None = re.match(SEASON_PREFIX + r"(\d{1,2})\b", remainder)
    if season_match:
        season = int(season_match.group(1))
        remainder = remainder[season_match.end() :].strip()
        if anchor and not broad and season > 1 and _marker(anchor, "season") is None:
            return _Parsed(anchor, broad, season, None, None, "missing", "unresolved season " + remainder)
    part_match: re.Match[str] | None = re.match(PART_PREFIX + r"(\d{1,2})\b", remainder)
    if part_match:
        part = int(part_match.group(1))
        remainder = remainder[part_match.end() :].strip()
    match: re.Match[str] | None = re.match(r"s(\d{1,2})\s*e(\d{1,4})(?:v\d+)?\b", remainder)
    if match:
        return _Parsed(
            anchor, broad, int(match.group(1)), part, int(match.group(2)), "mapped", remainder[match.end() :].strip()
        )
    match = re.match(r"(?:ep(?:isode)?\s*|e)?(\d{1,4})(?:v\d+)?\b", remainder)
    if match and int(match.group(1)) < FIRST_YEAR:
        return _Parsed(anchor, broad, season, part, int(match.group(1)), "plain", remainder[match.end() :].strip())
    return _Parsed(anchor, broad, season, part, None, "missing", remainder)


def _numbering_extension(parsed: _Parsed, target: _Target) -> IdentityAssessment | None:
    if target.kind != "TV" or parsed.broad:
        return None
    if (
        parsed.mode == "plain"
        and parsed.number == target.absolute
        and parsed.number != target.local
        and target.count
        and parsed.number is not None
        and parsed.number > target.count
    ):
        return IdentityAssessment(
            IdentityVerdict.MATCH, "Mapped absolute number exceeds the local episode range under a specific title."
        )
    if (
        parsed.mode == "mapped"
        and parsed.season == target.named_season
        and parsed.number == target.local
        and parsed.episode_title
    ):
        return IdentityAssessment(IdentityVerdict.MATCH, "Named season, local episode and catalog episode title agree.")
    return None


def _season_conflict(parsed: _Parsed, target: _Target) -> IdentityAssessment | None:
    if parsed.mode == "mapped" and target.season is None:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Mapped numbering cannot be checked without target numbering."
        )
    expected_season: int | None = target.season if parsed.mode == "mapped" else target.named_season
    if parsed.season is not None and parsed.season != expected_season:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Season marker conflicts with the target numbering system."
        )
    return None


def _identity_conflict(parsed: _Parsed, target: _Target) -> IdentityAssessment | None:
    season: IdentityAssessment | None = _season_conflict(parsed, target)
    if season is not None:
        return season
    if parsed.part is not None and parsed.part != target.part:
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "Part/cour marker conflicts with the target.")
    named: bool = parsed.mode == "plain" and parsed.season == target.season and target.episode == target.local
    if parsed.broad and not ((parsed.mode == "mapped" or named) and target.season and target.season > 1):
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "A franchise alias does not identify this installment.")
    mapped_part: bool = (
        parsed.mode == "mapped"
        and parsed.season == target.season
        and parsed.number == target.episode
        and parsed.part is None
    )
    if target.part is not None and parsed.broad and parsed.part != target.part and not mapped_part:
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "The required part/cour is not established.")
    return None


def _decision(parsed: _Parsed, target: _Target) -> IdentityAssessment:
    conflict: IdentityAssessment | None = _identity_conflict(parsed, target)
    if conflict is not None:
        return conflict
    extra: IdentityAssessment | None = _numbering_extension(parsed, target)
    if extra is not None:
        return extra
    if parsed.mode == "mapped" and parsed.number != target.episode and parsed.number == target.absolute:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Mapped number equals the target absolute number; numbering is ambiguous."
        )
    if parsed.mode == "mapped":
        return (
            IdentityAssessment(IdentityVerdict.MISMATCH, "Explicit mapped episode differs from target.")
            if parsed.number != target.episode
            else IdentityAssessment(
                IdentityVerdict.MATCH,
                "Work anchor and exact mapped season/episode match; residual is technical or catalogued.",
            )
        )
    if target.kind == "MOVIE":
        return _movie_decision(parsed, target)
    return _local_decision(parsed, target)


def _movie_decision(parsed: _Parsed, target: _Target) -> IdentityAssessment:
    if parsed.number is not None or any(title not in ("complete movie", "movie") for title in target.episode_titles):
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Movie segment or numbering requires a more specific identity anchor."
        )
    return IdentityAssessment(
        IdentityVerdict.MATCH, "Movie title matches with compatible year and no unidentified residual."
    )


def _local_decision(parsed: _Parsed, target: _Target) -> IdentityAssessment:
    if target.kind in ("OVA", "SPECIAL") and not parsed.episode_title:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "OVA/special needs a mapped episode or catalog episode title."
        )
    if parsed.number is None or target.local is None:
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "No unambiguous selected episode number.")
    if parsed.number != target.local:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Bare number is not the local episode; absolute numbering is not established."
        )
    if target.season == 0 or (target.season == 1 and target.episode is not None and target.episode != target.local):
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "Local and mapped numbering conflict.")
    return IdentityAssessment(
        IdentityVerdict.MATCH, "Specific work title and local episode match; residual is technical or catalogued."
    )


def _context_seasons(text: str, *, ranges: bool = True) -> set[int]:
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\s+season\b", r"s\1", text)
    seasons: set[int] = {int(number) for number in re.findall(r"\b" + SEASON_PREFIX + r"(\d{1,2})(?!\d)", text)}
    if not ranges:
        return seasons
    for match in re.finditer(r"\b(?:s|season\s+)(\d{1,2})\s*[-~]\s*s?(\d{1,2})\b", text, re.IGNORECASE):
        start: int = int(match.group(1))
        end: int = int(match.group(2))
        if start <= end:
            seasons.update(range(start, end + 1))
    for match in re.finditer(r"\bseason\s+(\d{1,2}(?:\s+\d{1,2})+)\b", text):
        numbers: list[int] = [int(number) for number in match.group(1).split()]
        if numbers == list(range(numbers[0], numbers[0] + len(numbers))):
            seasons.update(numbers)
    return seasons


def _multiple_works(text: str, target: _Target) -> bool:
    text = _strip_group(text)
    name: str = _normalize(text)
    if len(_context_seasons(text.casefold()) | _context_seasons(name, ranges=False)) > 1:
        return True
    localized: set[int | None] = {
        _context_number(next(token for token in match.groups() if token)) for match in LOCAL_SEASON.finditer(name)
    }
    roman: set[int | None] = {
        _context_number(match.group(2)) for match in ROMAN_CONTEXT.finditer(name) if match.group(1) == "season"
    }
    declared: set[int | None] = localized | roman
    if (len(declared - {None}) > 1 and bool(declared & {target.named_season, target.season})) or re.search(
        r"\br\d{1,2}\s*\+\s*r\d{1,2}\b", text, re.IGNORECASE
    ):
        return True
    if name != "movies" and re.search(r"\b(?:movies|seasons)\b", name):
        return True
    if re.search(
        r"[+&]\s*(?:(?:ova|oad|sp|specials?|movies?|recaps?|extras?|спешл|ова|фильм)\b|"
        r"特典|番外|総集編|总集篇|特別編|特别篇|剧场版|劇場版|극장판|gekij(?:ou|o|ō)ban\b)",
        text,
        re.IGNORECASE,
    ):
        return True
    if not re.search(r"\b(?:collection|complete series|series complete|series intégrale)\b", name):
        return False
    return any(re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", name) for title in target.neighbors)


def _context_conflict(text: str, target: _Target, *, multiple: bool | None = None) -> str:
    if _normalize(text) in PLEX_FOLDERS:
        return "Package directory explicitly identifies Plex extra material."
    prepared: str = _prepare(text)
    name: str = _normalize(_strip_group(prepared))
    anchor: str
    rest: str
    anchor, rest = _match(name, target.titles)
    if not anchor:
        anchor, rest = _match(name, target.broad)
    raw_tail: str = _anchored_context_tail(_strip_group(prepared), anchor) if anchor else ""
    original_rest: str = rest
    rest = _without_context_episode_title(rest, target)
    multiple = _multiple_works(prepared, target) if multiple is None else multiple
    neighbor: str = _match(name, target.neighbors)[0]
    if neighbor and len(neighbor) > len(anchor) and not multiple:
        return "Package explicitly identifies a neighboring work."
    seasons: set[int] = (
        _context_seasons(prepared.casefold()) | _context_seasons(name, ranges=False)
        if rest == original_rest
        else _context_seasons(rest, ranges=False)
    )
    if seasons and target.named_season not in seasons and target.season not in seasons:
        return "Package explicitly identifies a different season."
    part: int | None = _marker(rest, "part")
    if part is not None and part != target.part and not multiple:
        return "Package explicitly identifies a different part/cour."
    if re.search(r"\bfinal season\b", rest) and not any("final" in title for title in target.titles):
        return "Package explicitly identifies a different final season."
    qualifier_conflict: str = _context_qualifier_conflict(rest, target, anchor=anchor, multiple=multiple)
    return (
        qualifier_conflict
        or ("" if multiple else _language_context_conflict(rest, target))
        or (
            "Package contains an unresolved sequel qualifier."
            if anchor and not multiple and re.match(r"(?:ii|iii|iv|v|vi|vii|viii|ix|x|zoku|kan)\b", rest)
            else ""
        )
        or ("" if multiple else _p5_context_conflict(rest, target, anchor=anchor, raw_tail=raw_tail))
    )


def _anchored_context_tail(text: str, anchor: str) -> str:
    for boundary in re.finditer(r"[:\uff1a]|\s+|$", text):
        prefix: str = _normalize(text[: boundary.start()])
        if _prefix(prefix, anchor) == "":
            return text[boundary.start() :].lstrip()
    return ""


def _without_context_episode_title(text: str, target: _Target) -> str:
    number: re.Match[str] | None = re.match(r"^(?:s\d{1,2}\s*e|episode\s*|ep\s*|e)?\d{1,4}(?:v\d+)?\b", text)
    if number is None:
        return text
    rest: str
    matched: bool
    rest, matched = _without_episode_title(text[number.end() :].strip(), target)
    return text[: number.end()] + " " + rest if matched else text


def _context_number(token: str) -> int | None:
    if token.isdecimal():
        return int(token)
    if token in CJK_SEASONS:
        return CJK_SEASONS[token]
    if not token or not re.fullmatch(r"x{0,3}(?:ix|iv|v?i{0,3})", token):
        return None
    values: dict[str, int] = {"i": 1, "v": 5, "x": 10}
    return sum(
        -values[char] if index + 1 < len(token) and values[char] < values[token[index + 1]] else values[char]
        for index, char in enumerate(token)
    )


def _localized_season_conflict(text: str, target: _Target) -> str:
    numbers: list[int | None] = [
        _context_number(next(token for token in match.groups() if token)) for match in LOCAL_SEASON.finditer(text)
    ]
    if any(number is None or number not in (target.named_season, target.season) for number in numbers):
        return "Package localized season conflicts with the target or is unresolved."
    return ""


def _roman_part_conflict(text: str, target: _Target) -> str:
    for match in ROMAN_CONTEXT.finditer(text):
        number: int | None = _context_number(match.group(2))
        expected: tuple[int | None, ...] = (
            (target.named_season, target.season) if match.group(1) == "season" else (target.part,)
        )
        if number is None or number not in expected:
            return "Package Roman season/part conflicts with the target or is unresolved."
    return ""


def _ordinal_part_conflict(text: str, target: _Target) -> str:
    if any(int(match.group(1)) != target.part for match in ORDINAL_PART.finditer(text)):
        return "Package ordinal part/cour conflicts with the target."
    return ""


def _localized_format_conflict(text: str, target: _Target) -> str:
    return (
        "Package localized movie format conflicts with the target."
        if (LOCAL_MOVIE.search(text) and target.kind != "MOVIE")
        else ""
    )


def _sequel_context_conflict(text: str, target: _Target, *, raw_tail: str = "") -> str:
    if SEQUEL_CONTEXT.search(text) or re.fullmatch(r"r\d{1,2}", text):
        return "Package contains an unresolved continuation marker."
    if re.match(r"^(?:(?:[:\uff1a]|[-–—])\s*)?r\d{1,2}\b", raw_tail, re.IGNORECASE):
        return "Package contains an unresolved continuation marker."
    return ""


def _subtitle_context_conflict(text: str, target: _Target) -> str:
    field: re.Match[str] | None = re.match(r"^(?:[:\uff1a]\s*|[-–—]\s+)([^\[\]()]+)", text)
    if field is None:
        return ""
    rest: str = _normalize(field.group(1))
    if (
        not rest
        or TECHNICAL.match(rest)
        or re.match(r"(?:s\d{1,2}\s*e|episode\s*|ep\s*|e)?\d{1,4}(?:v\d+)?\b", rest)
        or _match(rest, target.titles)[0]
        or LOCAL_SEASON.match(rest)
        or ROMAN_CONTEXT.match(rest)
        or ORDINAL_PART.match(rest)
        or _marker(rest, "season") is not None
        or _marker(rest, "part") is not None
    ):
        return ""
    return "Package contains an uncatalogued title suffix."


def _p5_context_conflict(text: str, target: _Target, *, anchor: str, raw_tail: str) -> str:
    return (
        _localized_season_conflict(text, target)
        or _roman_part_conflict(text, target)
        or _ordinal_part_conflict(text, target)
        or _localized_format_conflict(text, target)
        or _sequel_context_conflict(text, target, raw_tail=raw_tail)
        or (_subtitle_context_conflict(raw_tail, target) if anchor else "")
    )


def _language_context_conflict(text: str, target: _Target) -> str:
    for pattern, kind in LANGUAGE_FORMATS:
        if pattern.search(text) and kind != target.kind:
            return "Package explicitly identifies a different language-specific media format."
    seasons: list[int | None] = [int(match.group(1)) for match in re.finditer(r"\b(?:тв|сезон)\s*(\d+)\b", text)]
    seasons.extend(
        int(token) if token.isdigit() else CJK_SEASONS.get(token) for token in re.findall(r"第(.{1,3}?)[期季]", text)
    )
    for word in re.findall(r"\b(\w+) season\b|\bseason (\w+)\b", text):
        token: str = word[0] or word[1]
        if token in SEASON_WORDS:
            seasons.append(SEASON_WORDS[token])
    if any(number is None or number not in (target.named_season, target.season) for number in seasons):
        return "Package season declaration conflicts with the target or is unresolved."
    if re.search(r"\b(?:тв|сезон)\b", text) and not seasons:
        return "Package Russian season declaration is unresolved."
    return ""


def _context_qualifier_conflict(rest: str, target: _Target, *, anchor: str, multiple: bool) -> str:
    episode_rest: str = re.sub(r"^(?:s\d{1,2}\s*e|episode\s*|ep\s*|e)?\d{1,4}(?:v\d+)?\b", "", rest).strip()
    if not multiple and EXTRAS.search(_without_episode_title(episode_rest, target)[0]):
        return "Package explicitly identifies non-episode material."
    if not multiple and MEDIA_MARKER.search(rest):
        kind: MediaKind = (
            "MOVIE" if re.search(r"\bmovies?\b", rest) else "OVA" if re.search(r"\b(?:ova|oad)\b", rest) else "SPECIAL"
        )
        if target.kind != kind:
            return "Package explicitly identifies a different media type."
    if not multiple and target.year is not None and not _year(rest, target)[1]:
        return "Package year conflicts with target metadata."
    if anchor and re.fullmatch(r"\d{1,2}", rest) and int(rest) != target.named_season:
        return "Package explicitly identifies a numbered sequel."
    return ""


def _context_anchor_valid(text: str, target: _Target, anchor: str, rest: str, *, strong: bool) -> bool:
    if anchor and _marker(anchor, "season") is None and _marker(rest, "season") not in (None, 1) and strong:
        return False
    if _marker(rest, "season") not in (None, target.named_season) or _marker(rest, "part") not in (None, target.part):
        return False
    if "final season" in rest or MEDIA_MARKER.search(rest) or EXTRAS.search(rest):
        return False
    neighbor: str = _match(_normalize(_strip_group(text)), target.neighbors)[0]
    if neighbor and (not anchor or len(neighbor) > len(anchor)):
        return False
    if anchor and re.match(r"\d{1,2}(?:\s|$)", rest):
        number: int = int(rest.split(maxsplit=1)[0])
        return number in (target.named_season, target.local) or bool(re.search(r"\d\s*[-~]\s*\d", text))
    return True


def _context(text: str, target: _Target) -> tuple[bool, bool]:
    stem: str
    dot: str
    extension: str
    stem, dot, extension = text.rpartition(".")
    text = stem if dot and extension.casefold() in VIDEO_EXTENSIONS else text
    name: str = _normalize(_strip_group(text))
    anchor: str
    rest: str
    anchor, rest = _match(name, target.titles)
    strong: bool = bool(anchor)
    if not anchor:
        anchor, rest = _match(name, target.broad)
    if not _context_anchor_valid(text, target, anchor, rest, strong=strong):
        return False, False
    valid_year: bool
    rest, valid_year = _year(rest, target)
    if not valid_year:
        return False, False
    rest = _remove_markers(rest)
    for alias in sorted(target.titles, key=len, reverse=True):
        rest = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", " ", rest)
    if re.search(r"\d\s*[-~]\s*\d", text):
        rest = re.sub(r"\b\d{1,4}\s+\d{1,4}\b", " ", rest)
    if _technical(" ".join(rest.split())):
        return True, strong
    parsed: _Parsed = _parse(text, target)
    remainder: str
    year_ok: bool
    remainder, year_ok = _year(parsed.remainder, target)
    expected: int | None = target.episode if parsed.mode == "mapped" else target.local
    return bool(
        parsed.anchor
        and parsed.number is not None
        and parsed.number == expected
        and year_ok
        and _residual(remainder, target)[0]
    ), strong


def _inherited_identity(parsed: _Parsed, contexts: list[str], target: _Target) -> _Parsed | None:
    inherited_season: int | None = parsed.season
    inherited_part: int | None = parsed.part
    for text in contexts:
        if _multiple_works(text, target):
            return None
        prepared: str = _prepare(text)
        name: str = _normalize(_strip_group(prepared))
        anchor: str = _match(name, target.titles)[0]
        season: int | None = _marker(name, "season")
        part: int | None = _marker(name, "part")
        if inherited_season is not None and season is not None and inherited_season != season:
            return None
        if inherited_part is not None and part is not None and inherited_part != part:
            return None
        inherited_season = inherited_season if inherited_season is not None else season
        inherited_part = inherited_part if inherited_part is not None else part
        if anchor and _context(prepared, target)[0]:
            return replace(parsed, anchor=anchor, season=inherited_season, part=inherited_part)
        qualifier: str = _remove_markers(name)
        if not _technical(" ".join(qualifier.split())):
            return None
    return None


def _structural_decision(parsed: _Parsed, target: _Target, candidate: Metadata, path: str) -> IdentityAssessment:
    path_parts: list[str] = path.split("/")
    directories: list[str] = _local_directories(
        list(reversed([part for part in path_parts[:-1] if part])), parsed, target
    )
    release: str = str(candidate.get("release") or "")
    selected: str = str(candidate.get("filename") or path_parts[-1])
    local_names: list[str] = list(dict.fromkeys((selected, path_parts[-1])))
    contexts: list[str] = [*directories, release]
    multiple: dict[str, bool] = {text: _multiple_works(text, target) for text in contexts}
    conflict: str = (
        _selected_work_conflict(local_names, [text for text in directories if not multiple[text]], target)
        or _directory_season_conflict(directories, target, parsed, allow_episode=not multiple[release])
        or _editing_variant_conflict([*local_names, *contexts], target)
    )
    if conflict:
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, conflict)
    unnumbered: bool = target.season is None
    for text in contexts:
        context: str = (
            _episode_directory_context(text, target, parsed) if text in directories and not multiple[release] else text
        )
        if unnumbered:
            context = MAPPED_SEASON.sub(r"\1", context)
        conflict = _context_conflict(context, target, multiple=multiple[text])
        if conflict:
            return IdentityAssessment(IdentityVerdict.INSUFFICIENT, conflict)
    if parsed.anchor:
        return _decision(parsed, target)
    identity_contexts: list[str] = directories if multiple[release] else contexts
    inherited: _Parsed | None = _inherited_identity(parsed, identity_contexts, target)
    if inherited is None:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT,
            "Titleless file lacks an unambiguous nearest work directory or single-work release.",
        )
    return _decision(inherited, target)


def _selected_work_conflict(files: list[str], directories: list[str], target: _Target) -> str:
    contexts: list[str] = [*files, *directories]
    for text in contexts:
        prepared: str = _prepare(text)
        bracket: re.Match[str] | None = FIRST_BRACKET.match(prepared)
        names: list[str] = [_normalize(_strip_group(prepared))]
        if bracket:
            names.append(_normalize(bracket.group(1)))
        if any(_neighbor_owns_name(name, target) for name in names):
            return "Selected file or work directory identifies a neighboring catalogue work."
    return ""


def _neighbor_owns_name(name: str, target: _Target) -> bool:
    neighbor: str = _match(name, target.neighbors)[0]
    own: str = _match(name, target.titles)[0]
    return bool(neighbor and len(neighbor) > len(own))


def _local_directories(directories: list[str], parsed: _Parsed, target: _Target) -> list[str]:
    local: list[str] = []
    for text in directories:
        name: str = _normalize(_strip_group(_prepare(text)))
        if parsed.anchor in target.titles and _prefix(parsed.anchor, name) not in (None, ""):
            continue
        local.append(text)
    return local


def _directory_number(text: str, target: _Target) -> tuple[str, str, str]:
    name: str = _normalize(_strip_group(_prepare(text)))
    anchor: str
    rest: str
    anchor, rest = _match(name, (*target.titles, *target.broad))
    number: re.Match[str] | None = DIRECTORY_NUMBER.match(rest)
    if not anchor or number is None:
        return "", "", ""
    tail: str = rest[number.end() :].strip()
    technical: str = re.sub(r"\b(?:19|20)\d{2}\b", " ", tail)
    if not _technical(technical):
        return "", "", ""
    return anchor, number.group(1), tail


def _episode_directory_context(text: str, target: _Target, parsed: _Parsed) -> str:
    anchor: str
    number: str
    tail: str
    anchor, number, tail = _directory_number(text, target)
    if number.startswith("0") and int(number) == parsed.number:
        return f"{anchor} {tail}".strip()
    return text


def _directory_season_conflict(directories: list[str], target: _Target, parsed: _Parsed, *, allow_episode: bool) -> str:
    if target.named_season is None and target.season is None:
        return ""
    for text in directories:
        number: str = _directory_number(text, target)[1]
        if not number or (allow_episode and number.startswith("0") and int(number) == parsed.number):
            continue
        if int(number) not in (target.named_season, target.season):
            return "Selected directory has a numbered season conflicting with the target."
    return ""


def _editing_variant_conflict(contexts: list[str], target: _Target) -> str:
    expected: set[str] = {
        match.group() for title in (*target.titles, *target.episode_titles) for match in EDITING_VARIANT.finditer(title)
    }
    selected_tv: bool = False
    selected_edition: bool = False
    for text in contexts:
        prepared: str = _prepare(text)
        name: str = _normalize(prepared)
        if expected and (name == "tv" or re.search(r"\[tv\]", prepared, re.IGNORECASE)):
            return "Selected TV variant conflicts with the target editing variant."
        if (
            not expected
            and target.kind in ("TV", "TV_SHORT")
            and (name == "tv" or re.search(r"\[tv\]", prepared, re.IGNORECASE))
        ):
            selected_tv = True
        if not EDITING_VARIANT.search(name):
            continue
        if selected_tv and re.search(r"\btv\s*[+&]", prepared, re.IGNORECASE):
            continue
        editions: set[str] = {match.group() for match in EDITING_VARIANT.finditer(name)}
        mixed: bool = bool(re.search(r"[+&]", prepared)) and (len(editions) > 1 or bool(re.search(r"\btv\b", name)))
        if selected_edition and mixed and expected <= editions:
            continue
        if editions and editions <= expected and not mixed:
            selected_edition = True
        anchor: str
        rest: str
        anchor, rest = _match(_normalize(_strip_group(prepared)), (*target.titles, *target.broad))
        rest = _without_context_episode_title(rest, target) if anchor else name
        bracket: re.Match[str] | None = FIRST_BRACKET.match(prepared)
        if anchor and bracket:
            rest += " " + _normalize(bracket.group(1))
        found: set[str] = {match.group() for match in EDITING_VARIANT.finditer(rest)}
        if found - expected:
            return "Release editing variant is not established for the target episode."
    return ""


def _remove_markers(text: str) -> str:
    return re.sub(r"\b(?:" + SEASON_PREFIX + "|" + PART_PREFIX + r")\d{1,2}\b", " ", text)


def _valid_evidence(target: Metadata, evidence: Metadata) -> bool:
    if not isinstance(target, Mapping) or not isinstance(evidence, Mapping):
        return False
    nodes: tuple[Any, ...] = tuple(evidence.get(key) for key in ("target_catalog", "target_episode", "target_mappings"))
    if any(node is not None and not isinstance(node, Mapping) for node in nodes):
        return False
    related: Any = evidence.get("related_catalog_entries")
    if related is not None and (
        not isinstance(related, (list, tuple)) or any(not isinstance(item, Mapping) for item in related)
    ):
        return False
    mappings: Metadata = evidence.get("target_mappings") or {}
    episodes: Any = mappings.get("episodes")
    return episodes is None or (
        isinstance(episodes, (list, tuple)) and all(isinstance(item, Mapping) for item in episodes)
    )


def classify(target: Metadata, candidate: Metadata, archived_evidence: Metadata | None = None) -> IdentityAssessment:
    """Assess one selected video using runtime identity metadata without inspecting media or labels."""
    evidence: Metadata = archived_evidence if archived_evidence is not None else {}
    if not _valid_evidence(target, evidence):
        return _invalid_evidence_assessment(candidate)
    return _classify(_target(target, evidence), candidate)


def classify_many(target: Metadata, candidates: Sequence[Metadata]) -> tuple[IdentityAssessment, ...]:
    """Assess candidates in input order with one target preparation and no archived evidence."""
    evidence: Metadata = {}
    if not _valid_evidence(target, evidence):
        return tuple(_invalid_evidence_assessment(candidate) for candidate in candidates)
    identity: _Target = _target(target, evidence)
    return tuple(_classify(identity, candidate) for candidate in candidates)


def identity_evidence(target: Mapping[str, object], candidate: Mapping[str, object]) -> IdentityEvidence:
    """Project research features through H1's parser even when classification stops before parsing the file."""
    identity: _Target = _target(target, {})
    assessment: IdentityAssessment = classify(target, candidate)
    path: str = str(candidate.get("path") or "").replace("\\", "/")
    selected: str = str(candidate.get("filename") or path.rsplit("/", 1)[-1])
    release: str = str(candidate.get("release") or "")
    text: str = selected or release
    stem: str = text.rpartition(".")[0] if text.rpartition(".")[2].casefold() in VIDEO_EXTENSIONS else text
    stem = _prepare(stem)
    parsed: _Parsed = _absolute_echo(stem, _parse(stem, identity), identity)
    residual: str
    year_ok: bool
    residual, year_ok = _year(parsed.remainder, identity)
    residual_ok: bool
    episode_anchor: bool
    residual_ok, episode_anchor = _episode_residual(residual, identity)
    return IdentityEvidence(
        assessment=assessment,
        kind=identity.kind,
        mode=parsed.mode,
        selected=selected,
        path=path,
        release=release,
        anchor=bool(parsed.anchor),
        broad=parsed.broad,
        number=Decimal(parsed.number) if parsed.number is not None else None,
        season=parsed.season,
        part=parsed.part,
        local=identity.local,
        episode=identity.episode,
        absolute=identity.absolute,
        target_season=identity.season,
        target_part=identity.part,
        named_season=identity.named_season,
        residual=residual,
        residual_ok=residual_ok,
        episode_anchor=episode_anchor,
        year_ok=year_ok,
        multiple_works=_multiple_works(release, identity),
    )


def _candidate_boundary(candidate: Metadata) -> IdentityAssessment | None:
    if not isinstance(candidate, Mapping) or any(
        candidate.get(key) is not None and not isinstance(candidate.get(key), str)
        for key in ("path", "filename", "release")
    ):
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "Malformed candidate metadata.")
    path: str = str(candidate.get("path") or "").replace("\\", "/")
    selected: str = str(candidate.get("filename") or path.rsplit("/", 1)[-1])
    if not selected:
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "No selected file.")
    dot: str
    extension: str
    _, dot, extension = selected.rpartition(".")
    if not dot or extension.casefold() not in VIDEO_EXTENSIONS:
        return IdentityAssessment(IdentityVerdict.MISMATCH, "Selected file has no allowed video extension.")
    return None


def _invalid_evidence_assessment(candidate: Metadata) -> IdentityAssessment:
    return _candidate_boundary(candidate) or IdentityAssessment(
        IdentityVerdict.INSUFFICIENT, "Malformed target or archived identity metadata."
    )


def classify_release_name(target: Metadata, name: str) -> IdentityAssessment:
    """Assess a release name as text with the H1 parser, without requiring a video extension."""
    if not isinstance(name, str):
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "Malformed candidate metadata.")
    if not name.strip():
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "No selected file.")
    if not _valid_evidence(target, {}):
        return IdentityAssessment(IdentityVerdict.INSUFFICIENT, "Malformed target or archived identity metadata.")
    stem: str
    dot: str
    extension: str
    stem, dot, extension = name.rpartition(".")
    text: str = stem if dot and extension.casefold() in VIDEO_EXTENSIONS else name
    return _assess(_target(target, {}), {"release": name, "filename": name}, "", text)


def is_extra_path(path: str) -> bool:
    """Tell whether a path is an NCOP, NCED, creditless or Plex extra without any other possible episode number."""
    parts: list[str] = path.replace("\\", "/").split("/")
    stem: str = parts[-1].rpartition(".")[0] or parts[-1]
    plex: bool = PLEX_SUFFIX.search(stem) is not None or any(_normalize(part) in EXTRA_FOLDERS for part in parts[:-1])
    texts: list[str] = [
        BRACKET_TAG.sub(lambda tag: " " if _technical(_normalize(tag.group(1) or tag.group(2))) else tag[0], part)
        for part in (*parts[:-1], stem)
    ]
    marked: str = EXTRA_MARKER.sub(" ", texts[-1])
    return (plex or marked != texts[-1]) and not any(
        char.isnumeric() for text in (*texts[:-1], marked) for char in text
    )


def episode_video_count(paths: Sequence[str]) -> int:
    """Count episode videos among torrent paths; recognized extras count only when nothing else is a video."""
    videos: list[str] = [path for path in paths if path.rpartition(".")[2].casefold() in VIDEO_EXTENSIONS]
    episodes: list[str] = [path for path in videos if not is_extra_path(path)]
    return len(episodes or videos)


def is_conflict(assessment: IdentityAssessment) -> bool:
    """Tell whether the assessment declares an explicit contradiction with the target."""
    return assessment.verdict is IdentityVerdict.MISMATCH or (
        assessment.verdict is IdentityVerdict.INSUFFICIENT and assessment.reason in CONFLICT_REASONS
    )


def conflict_label(assessment: IdentityAssessment) -> str:
    """Return the short Polish label of a conflict; raise ValueError for an assessment without one."""
    labels: Mapping[str, str] = MISMATCH_LABELS if assessment.verdict is IdentityVerdict.MISMATCH else CONFLICT_LABELS
    if not is_conflict(assessment) or assessment.reason not in labels:
        raise ValueError(assessment.reason)
    return labels[assessment.reason]


def _classify(identity: _Target, candidate: Metadata) -> IdentityAssessment:
    boundary: IdentityAssessment | None = _candidate_boundary(candidate)
    if boundary is not None:
        return boundary
    path: str = str(candidate.get("path") or "").replace("\\", "/")
    selected: str = str(candidate.get("filename") or path.rsplit("/", 1)[-1])
    return _assess(identity, candidate, path, selected.rpartition(".")[0])


def _assess(identity: _Target, candidate: Metadata, path: str, stem: str) -> IdentityAssessment:  # noqa: PLR0911
    if PLEX_SUFFIX.search(stem):
        return IdentityAssessment(IdentityVerdict.MISMATCH, "Selected filename has an explicit Plex extra suffix.")
    stem = _prepare(stem)
    parsed: _Parsed = _absolute_echo(stem, _parse(stem, identity), identity)
    if EXTRAS.search(_without_episode_title(parsed.remainder, identity)[0]):
        return IdentityAssessment(
            IdentityVerdict.MISMATCH, "Selected residual explicitly identifies non-episode material."
        )
    bracket: re.Match[str] | None = FIRST_BRACKET.match(stem)
    if not parsed.anchor and bracket and _strip_group(stem) != stem:
        inherited: _Parsed | None = _inherited_identity(parsed, [bracket.group(1)], identity)
        if inherited is not None:
            parsed = inherited
        elif not _technical(_normalize(bracket.group(1))):
            return IdentityAssessment(
                IdentityVerdict.INSUFFICIENT, "Unresolved leading bracket is the nearest identity context."
            )
    neighbor: str = _match(_normalize(_strip_group(stem)), identity.neighbors)[0]
    if neighbor and len(neighbor) > len(parsed.anchor):
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Selected filename more specifically identifies a neighboring work."
        )
    residual: str
    valid_year: bool
    residual, valid_year = _year(parsed.remainder, identity)
    if not valid_year:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT, "Filename year is missing from or conflicts with runtime target metadata."
        )
    residual_ok: bool
    episode_anchor: bool
    residual_ok, episode_anchor = _episode_residual(residual, identity)
    if not residual_ok:
        return IdentityAssessment(
            IdentityVerdict.INSUFFICIENT,
            "Unconsumed filename text is neither technical metadata nor a catalog episode title.",
        )
    return _structural_decision(
        replace(parsed, remainder=residual, episode_title=episode_anchor), identity, candidate, path
    )
