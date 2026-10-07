"""Project catalogue facts into E1 episode lists, H1 targets and owner-ranked stream offers without I/O."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from anishift.application.discovery import VIDEO_SOURCE_SUFFIXES
from anishift.application.episode_identity import IdentityAssessment, IdentityVerdict, classify_many
from anishift.application.release_quality import resolution, resolution_class

__all__ = [
    "AniZipMapping",
    "EntryGroup",
    "EpisodeKey",
    "EpisodeListing",
    "EpisodeOffer",
    "Franchise",
    "FranchiseEntry",
    "FranchiseGraph",
    "FranchiseRelation",
    "IdentityAssessment",
    "IdentityVerdict",
    "JsonObject",
    "ListedEpisode",
    "ListedSpecial",
    "RankedCandidate",
    "ReleaseFacts",
    "StreamCandidate",
    "episode_listing",
    "franchise_traversal",
    "franchise_view",
    "identity_target",
    "premiere_order",
    "rank_candidates",
    "release_facts",
    "suggestion",
]

# ── Constants ─────────────────────────────────────────────────────────────────

type JsonObject = Mapping[str, Any]
"""Raw JSON object of a catalogue response, kept exactly as the provider returned it."""

_CHAIN_RELATIONS: Final[frozenset[str]] = frozenset({"PREQUEL", "SEQUEL"})
"""AniList relations that extend the identity chain of the selected entry."""

_LEAF_RELATIONS: Final[frozenset[str]] = frozenset({"SIDE_STORY", "SPIN_OFF", "ALTERNATIVE", "SUMMARY", "PARENT"})
"""AniList relations that attach an entry without expanding its own chain."""

_PARENT_RELATION: Final[str] = "PARENT"
"""Relation through which a directly selected extra reaches its parent chain."""

_SELF_RELATION: Final[str] = "SELF"
"""Relation label of the selected entry in its own franchise view."""

_ANIME_TYPE: Final[str] = "ANIME"
"""AniList media type of every node the franchise graph keeps."""

_SEASON_FORMATS: Final[frozenset[str]] = frozenset({"TV", "TV_SHORT", "ONA"})
"""AniList formats that count as a season of the identity chain."""

_EXTRA_FORMATS: Final[frozenset[str]] = frozenset({"OVA", "SPECIAL"})
"""AniList formats shown as extras of a franchise."""

_UNKNOWN_YEAR: Final[int] = 9999
"""Sort year of a season without a start year, placing it after every dated season."""

_UNKNOWN_STATUS: Final[str] = "UNKNOWN"
"""Status value of an entry whose AniList status is absent."""

_YEAR_END_MONTH: Final[int] = 13
"""Sort month placing a premiere known only by its year after every full date of that year."""

_RELEASING: Final[str] = "RELEASING"
"""AniList status whose aired count comes from past schedule dates."""

_FINISHED: Final[str] = "FINISHED"
"""AniList status whose aired count is the AniList episode count."""

_EXTRA_PREFIX: Final[str] = "Extra: "
"""Prefix ani.zip puts before titles of extra episodes."""

_VERDICT_ORDER: Final[Mapping[IdentityVerdict, int]] = MappingProxyType(
    {IdentityVerdict.MATCH: 0, IdentityVerdict.INSUFFICIENT: 1, IdentityVerdict.MISMATCH: 2}
)
"""Rank position of each identity verdict, ahead of every owner preference."""

_SUGGESTED_VERDICTS: Final[tuple[IdentityVerdict, ...]] = (IdentityVerdict.MATCH, IdentityVerdict.INSUFFICIENT)
"""Verdicts that may become a suggestion, in order of preference."""

_POLISH: Final[re.Pattern[str]] = re.compile(r"(?i)\b(?:polish|polski|polskie|polska|pol|pl)\b")
"""Polish language token in a release name, path or tag."""

_POLISH_FLAG: Final[str] = "\U0001f1f5\U0001f1f1"
"""Torrentio tag marking Polish language."""

_MULTISUB: Final[re.Pattern[str]] = re.compile(r"(?i)\bmulti(?:ple)?[ .-]?sub(?:s|titles?)?\b")
"""Declaration of several subtitle languages."""

_PLATFORMS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\b(?:NF|(?i:netflix))\b"), "Netflix"),
    (re.compile(r"\b(?:CR|(?i:crunchyroll))\b"), "Crunchyroll"),
)
"""Whole tokens naming a streaming platform and the platform they name."""

_DUBBED_TAG: Final[str] = "Dubbed"
"""Torrentio tag of a dubbed release."""

_DUAL_AUDIO: Final[re.Pattern[str]] = re.compile(r"(?i)\b(?:dual|multi)[ .-]?audio\b")
"""Declaration that original audio accompanies a dub."""

_CONTAINER: Final[re.Pattern[str]] = re.compile(r"[^/\\]\.([^\s./\\()\[\]{}]+)$")
"""Final suffix of the selected file name; a dot followed by spaces or brackets, as in ``(TrueHD 5.1)``, is not one."""


class EntryGroup(StrEnum):
    """Group of a franchise entry in the view, in display order."""

    SEASON = "season"
    EXTRA = "extra"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FranchiseEntry:
    """One AniList entry of a franchise view."""

    anilist_id: int
    romaji: str
    english: str | None
    native: str | None
    format: str | None
    status: str
    year: int | None
    start: date | None
    relation: str
    group: EntryGroup


@dataclass(frozen=True, slots=True)
class FranchiseRelation:
    """One fetched AniList relation between two anime entries."""

    source_id: int
    target_id: int
    relation: str


@dataclass(frozen=True, slots=True)
class Franchise:
    """Franchise view of the selected entry with its real relations."""

    selected_id: int
    entries: tuple[FranchiseEntry, ...]
    relations: tuple[FranchiseRelation, ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class FranchiseGraph:
    """Every fetched franchise node as raw AniList JSON, internal to the service and the H1 target builder."""

    root_id: int
    nodes: Mapping[int, JsonObject]
    queried: frozenset[int]
    complete: bool


@dataclass(frozen=True, slots=True)
class ListedEpisode:
    """One numbered episode of an entry."""

    number: int
    title: str | None = None
    airs_at: datetime | None = None
    season: int | None = None
    episode: int | None = None
    absolute: int | None = None
    aired: bool = False
    airs_at_fallback: bool = False


@dataclass(frozen=True, slots=True)
class ListedSpecial:
    """One ani.zip special keyed ``S1``, ``S2`` and so on."""

    key: str
    title: str | None
    airs_on: date | None


@dataclass(frozen=True, slots=True)
class AniZipMapping:
    """Parsed ani.zip mapping of one entry together with its raw ``episodes`` object."""

    kitsu_id: int | None
    catalog_type: str | None
    episode_count: int | None
    episodes: tuple[ListedEpisode, ...]
    specials: tuple[ListedSpecial, ...]
    max_age_s: int | None
    raw_episodes: Mapping[str, JsonObject]


@dataclass(frozen=True, slots=True)
class EpisodeListing:
    """Episode list of one entry joined from ani.zip, the AniList schedule and the episode count."""

    anilist_id: int
    kitsu_id: int | None
    catalog_type: str | None
    status: str
    episode_count: int | None
    episodes: tuple[ListedEpisode, ...]
    specials: tuple[ListedSpecial, ...]
    aired: int | None
    schedule_warning: str | None
    schedule_retry_at: datetime | None


@dataclass(frozen=True, slots=True)
class StreamCandidate:
    """One release stream as its source returned it, with the language declarations that source made."""

    info_hash: str
    name: str | None
    file_index: int | None
    file_name: str | None
    release: str
    path: str | None
    seeders: int | None
    size_text: str | None
    provider: str | None
    tags: tuple[str, ...]
    trackers: tuple[str, ...]
    source: str = "torrentio"
    subtitle_languages: tuple[str, ...] = ()
    audio_languages: tuple[str, ...] = ()
    language_tags: tuple[str, ...] = ()
    file_count: int | None = None
    torrent_id: int | None = None


@dataclass(frozen=True, slots=True)
class EpisodeKey:
    """One episode of one AniList entry."""

    anilist_id: int
    number: int


@dataclass(frozen=True, slots=True)
class ReleaseFacts:
    """Owner-relevant facts declared by a stream's names and tags."""

    resolution: int | None
    polish: bool
    multisub: bool
    platform: str | None
    dub_only: bool
    container: str | None
    supported: bool | None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One stream with its identity assessment and release facts."""

    stream: StreamCandidate
    identity: IdentityAssessment
    facts: ReleaseFacts


@dataclass(frozen=True, slots=True)
class EpisodeOffer:
    """Ranked streams of one episode with the index of the suggested one."""

    key: EpisodeKey
    candidates: tuple[RankedCandidate, ...]
    suggestion: int | None
    checked_at: datetime
    counts: dict[str, int]


def franchise_traversal(
    selected_id: int, nodes: Mapping[int, JsonObject], queried: frozenset[int]
) -> tuple[frozenset[int], frozenset[int], frozenset[int]]:
    """Return the identity chain, the displayed entries and the unexpanded chain nodes of *selected_id*."""
    chain, attached, missing = _walk(selected_id, nodes, queried)
    return frozenset(chain), frozenset(attached), missing


def franchise_view(graph: FranchiseGraph, selected_id: int) -> Franchise:
    """Project the franchise view of *selected_id* from the fetched graph."""
    chain, attached, missing = _walk(selected_id, graph.nodes, graph.queried)
    members: frozenset[int] = frozenset(chain)
    entries: list[FranchiseEntry] = [
        _entry(graph.nodes[identifier], relation, in_chain=identifier in members)
        for identifier, relation in attached.items()
    ]
    entries.sort(key=_entry_order, reverse=True)
    return Franchise(
        selected_id=selected_id,
        entries=tuple(entries),
        relations=_relations(graph.nodes),
        complete=not missing,
    )


def identity_target(graph: FranchiseGraph, selected_id: int, mapping: AniZipMapping, number: int) -> dict[str, object]:
    """Build the H1 target of one local episode with exactly the keys and values of the frozen corpus projection."""
    nodes: Mapping[int, JsonObject] = graph.nodes
    chain, _, missing = _walk(selected_id, nodes, graph.queried)
    members: frozenset[int] = frozenset(chain)
    titles: list[str] = _titles(nodes[selected_id], sort_keys=True)
    first_season: JsonObject | None = None if missing else _first_season(chain, nodes)
    if first_season is not None:
        titles.extend(_titles(first_season))
    key: str = str(number)
    episode: JsonObject = mapping.raw_episodes.get(key) or {}
    return {
        "aliases": list(dict.fromkeys(titles)),
        "type": nodes[selected_id]["format"],
        "local_episode": number,
        "season": episode.get("seasonNumber"),
        "episode": episode.get("episodeNumber"),
        "absolute": episode.get("absoluteEpisodeNumber"),
        "episode_title": _episode_title(episode),
        "other_series": list(
            dict.fromkeys(
                title for identifier, node in nodes.items() if identifier not in members for title in _titles(node)
            )
        ),
        "other_episode_titles": [
            title for other, value in mapping.raw_episodes.items() if other != key and (title := _episode_title(value))
        ],
    }


def episode_listing(  # noqa: PLR0913
    anilist_id: int,
    mapping: AniZipMapping,
    status: str,
    episode_count: int | None,
    schedule: Sequence[ListedEpisode],
    now: datetime,
    *,
    schedule_warning: str | None = None,
    schedule_retry_at: datetime | None = None,
) -> EpisodeListing:
    """Join ani.zip episodes with the AniList schedule and fill numbers up to the known episode count.

    Without an AniList count the ani.zip count stands, raised to the highest AniList schedule number.
    An episode is aired when its AniList date has passed; without an AniList date, when U-15 confirms
    its number against the AniList aired count. An ani.zip date never confirms airing and marks
    the episode with ``airs_at_fallback``.
    """
    count: int | None = episode_count
    if count is None and mapping.episode_count is not None:
        count = max((mapping.episode_count, *(planned.number for planned in schedule)))
    aired: int | None = _aired(status, episode_count, schedule, now)
    dated: dict[int, datetime] = {
        planned.number: planned.airs_at for planned in schedule if planned.airs_at is not None
    }
    listed: dict[int, ListedEpisode] = {episode.number: episode for episode in mapping.episodes}
    for planned in schedule:
        known: ListedEpisode | None = listed.get(planned.number)
        listed[planned.number] = planned if known is None else replace(known, airs_at=planned.airs_at or known.airs_at)
    for number in range(1, (count or 0) + 1):
        listed.setdefault(number, ListedEpisode(number=number))
    return EpisodeListing(
        anilist_id=anilist_id,
        kitsu_id=mapping.kitsu_id,
        catalog_type=mapping.catalog_type,
        status=status,
        episode_count=count,
        episodes=tuple(
            replace(
                listed[number],
                aired=_episode_aired(number, dated.get(number), aired, now),
                airs_at_fallback=listed[number].airs_at is not None and number not in dated,
            )
            for number in sorted(listed)
        ),
        specials=mapping.specials,
        aired=aired,
        schedule_warning=schedule_warning,
        schedule_retry_at=schedule_retry_at,
    )


def release_facts(stream: StreamCandidate) -> ReleaseFacts:
    """Read resolution, language, platform, dub and container declarations of one stream."""
    raw_names: tuple[str, ...] = tuple(text for text in (stream.release, stream.path, stream.file_name) if text)
    names: tuple[str, ...] = tuple(text.replace("_", " ") for text in raw_names)
    labels: tuple[str, ...] = (*names, *stream.tags)
    container: str | None = _container(stream.file_name)
    return ReleaseFacts(
        resolution=resolution((*raw_names, stream.name or "")),
        polish=_POLISH_FLAG in stream.tags or any(_POLISH.search(text) for text in labels),
        multisub=any(_MULTISUB.search(text) for text in labels),
        platform=next(
            (platform for pattern, platform in _PLATFORMS if any(pattern.search(text) for text in labels)), None
        ),
        dub_only=_DUBBED_TAG in stream.tags and not any(_DUAL_AUDIO.search(text) for text in labels),
        container=container,
        supported=None if container is None else container in VIDEO_SOURCE_SUFFIXES,
    )


def rank_candidates(target: Mapping[str, object], streams: Sequence[StreamCandidate]) -> tuple[RankedCandidate, ...]:
    """Assess every stream with H1 and stably order them by verdict, then by the owner preference key."""
    assessments: tuple[IdentityAssessment, ...] = classify_many(
        target,
        [{"release": stream.release, "path": stream.path, "filename": stream.file_name} for stream in streams],
    )
    ranked: list[RankedCandidate] = [
        RankedCandidate(stream=stream, identity=identity, facts=release_facts(stream))
        for stream, identity in zip(streams, assessments, strict=True)
    ]
    ranked.sort(key=_rank_key)
    return tuple(ranked)


def suggestion(candidates: Sequence[RankedCandidate]) -> int | None:
    """Return the index of the best ranked usable match, else of the best usable uncertain stream."""
    for verdict in _SUGGESTED_VERDICTS:
        found: int | None = next(
            (
                index
                for index, candidate in enumerate(candidates)
                if candidate.identity.verdict is verdict and candidate.facts.supported is not False
            ),
            None,
        )
        if found is not None:
            return found
    return None


def _walk(
    selected_id: int, nodes: Mapping[int, JsonObject], queried: frozenset[int]
) -> tuple[tuple[int, ...], dict[int, str], frozenset[int]]:
    pending: list[int] = [selected_id]
    chain: dict[int, None] = {}
    attached: dict[int, str] = {selected_id: _SELF_RELATION}
    missing: set[int] = set()
    while pending:
        identifier: int = pending.pop()
        if identifier in chain:
            continue
        chain[identifier] = None
        node: JsonObject = nodes[identifier]
        if "relations" not in node or (not node["relations"]["edges"] and identifier not in queried):
            missing.add(identifier)
            continue
        parent_entry: bool = identifier == selected_id and node["format"] in _EXTRA_FORMATS
        edges: list[tuple[str, int]] = list(_followed_edges(node))
        for relation, target_id in edges:
            attached.setdefault(target_id, relation)
        pending.extend(
            target_id
            for relation, target_id in edges
            if relation in _CHAIN_RELATIONS or (parent_entry and relation == _PARENT_RELATION)
        )
    return tuple(chain), attached, frozenset(missing)


def _followed_edges(node: JsonObject) -> Iterator[tuple[str, int]]:
    for edge in node["relations"]["edges"]:
        relation: str = edge["relationType"]
        if edge["node"]["type"] == _ANIME_TYPE and relation in _CHAIN_RELATIONS | _LEAF_RELATIONS:
            yield relation, edge["node"]["id"]


def _anime_edges(node: JsonObject) -> Iterator[tuple[str, int]]:
    for edge in (node.get("relations") or {}).get("edges") or ():
        if edge["node"]["type"] == _ANIME_TYPE:
            yield edge["relationType"], edge["node"]["id"]


def _relations(nodes: Mapping[int, JsonObject]) -> tuple[FranchiseRelation, ...]:
    edges: set[tuple[int, int, str]] = {
        (identifier, target_id, relation)
        for identifier, node in nodes.items()
        for relation, target_id in _anime_edges(node)
    }
    return tuple(FranchiseRelation(source, target, relation) for source, target, relation in sorted(edges))


def _entry(node: JsonObject, relation: str, *, in_chain: bool) -> FranchiseEntry:
    title: JsonObject = node.get("title") or {}
    start: JsonObject = node.get("startDate") or {}
    status: object = node.get("status")
    return FranchiseEntry(
        anilist_id=node["id"],
        romaji=str(title.get("romaji") or ""),
        english=title.get("english"),
        native=title.get("native"),
        format=node.get("format"),
        status=status if isinstance(status, str) else _UNKNOWN_STATUS,
        year=start.get("year") or node.get("seasonYear"),
        start=_start_date(start),
        relation=relation,
        group=_group(node.get("format"), in_chain=in_chain),
    )


def _group(media_format: str | None, *, in_chain: bool) -> EntryGroup:
    if media_format in _EXTRA_FORMATS:
        return EntryGroup.EXTRA
    if media_format in _SEASON_FORMATS and in_chain:
        return EntryGroup.SEASON
    return EntryGroup.OTHER


def _start_date(start: JsonObject) -> date | None:
    parts: tuple[object, ...] = (start.get("year"), start.get("month"), start.get("day"))
    if not all(isinstance(part, int) for part in parts):
        return None
    return date(start["year"], start["month"], start["day"])


def premiere_order(year: int | None, start: date | None) -> tuple[bool, int, int, int]:
    """Order premieres ascending with undated entries first; a year without a full date closes its year."""
    if year is None:
        return False, 0, 0, 0
    if start is None:
        return True, year, _YEAR_END_MONTH, 0
    return True, year, start.month, start.day


def _entry_order(entry: FranchiseEntry) -> tuple[bool, int, int, int, int]:
    dated, year, month, day = premiere_order(entry.year, entry.start)
    return not dated, year, month, day, entry.anilist_id


def _titles(node: JsonObject, *, sort_keys: bool = False) -> list[str]:
    title: JsonObject = node.get("title") or {}
    keys: list[str] = sorted(title) if sort_keys else list(title)
    return [title[key] for key in keys if title[key]]


def _first_season(chain: Sequence[int], nodes: Mapping[int, JsonObject]) -> JsonObject | None:
    seasons: list[JsonObject] = [
        nodes[identifier]
        for identifier in chain
        if identifier in nodes and nodes[identifier]["format"] in _SEASON_FORMATS
    ]
    return min(seasons, key=_season_order, default=None)


def _season_order(node: JsonObject) -> tuple[int, int]:
    return (node.get("startDate") or {}).get("year") or _UNKNOWN_YEAR, node["id"]


def _episode_title(episode: JsonObject) -> str | None:
    value: object = episode.get("title")
    if isinstance(value, Mapping):
        value = value.get("en") or value.get("x-jat")
    return value.removeprefix(_EXTRA_PREFIX).replace("`", "'") if isinstance(value, str) and value else None


def _aired(status: str, episode_count: int | None, schedule: Sequence[ListedEpisode], now: datetime) -> int | None:
    if status == _FINISHED:
        return episode_count
    if status != _RELEASING or not schedule:
        return None
    return sum(1 for planned in schedule if planned.airs_at is not None and planned.airs_at <= now)


def _episode_aired(number: int, anilist_date: datetime | None, aired: int | None, now: datetime) -> bool:
    if anilist_date is not None:
        return anilist_date <= now
    return aired is not None and number <= aired


def _container(file_name: str | None) -> str | None:
    found: re.Match[str] | None = _CONTAINER.search(file_name or "")
    return f".{found.group(1).casefold()}" if found else None


def _rank_key(candidate: RankedCandidate) -> tuple[int, bool, bool, tuple[int, int], bool, bool, bool, bool, int]:
    facts: ReleaseFacts = candidate.facts
    seeders: int | None = candidate.stream.seeders
    return (
        _VERDICT_ORDER[candidate.identity.verdict],
        facts.supported is False,
        facts.dub_only,
        resolution_class(facts.resolution),
        not facts.polish,
        not facts.multisub,
        facts.platform is None,
        seeders is None,
        -(seeders or 0),
    )
