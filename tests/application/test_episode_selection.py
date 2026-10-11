from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.application.episode_confidence import confidence
from anishift.application.episode_identity import IdentityEvidence, IdentityVerdict, classify, identity_evidence
from anishift.application.episode_releases import (
    EpisodeRelease,
    ListedFile,
    ReleaseFile,
    TsukiHimeFiles,
    merge_releases,
)
from anishift.application.episode_selection import (
    GROUP_NUMBERING_REASON,
    AniZipMapping,
    EntryGroup,
    EpisodeListing,
    FranchiseEntry,
    FranchiseGraph,
    ListedEpisode,
    ListedSpecial,
    RankedCandidate,
    StreamCandidate,
    confidence_text,
    episode_listing,
    franchise_traversal,
    franchise_view,
    identity_target,
    list_order,
    numbering_gap,
    premiere_order,
    quality_text,
    rank_candidates,
    representative,
    streams_releases,
    suggestion,
    visible,
)
from anishift.application.release_quality import ReleaseTraits
from anishift.services.catalog.anilist import parse_franchise_page
from anishift.services.catalog.anizip import parse_mapping
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.torrentio import parse_streams

pytestmark = pytest.mark.unit

_FIXTURES: Final[Path] = Path(__file__).parents[1] / "fixtures"

_SEARCH: Final[Path] = _FIXTURES / "search"

_REGRESSIONS: Final[Path] = _FIXTURES / "acquisition" / "identity-regressions.json"

_NOW: Final[datetime] = datetime(2026, 9, 29, 12, tzinfo=UTC)

_TARGET_KEYS: Final[frozenset[str]] = frozenset(
    {
        "absolute",
        "aliases",
        "episode",
        "episode_title",
        "local_episode",
        "other_episode_titles",
        "other_series",
        "season",
        "type",
    }
)

_SLIME_S1: Final[int] = 101280

_SLIME_S4: Final[int] = 182205

_SLIME_DIARIES: Final[int] = 116741

_SLIME_OAD: Final[int] = 106509

_SLIME_NEIGHBOR_FILES: Final[frozenset[str]] = frozenset(
    {
        "[Trix] Tensura Nikki Tensei Shitara Slime Datta Ken - S01E04 (BD 1080p AV1).mkv",
        "The Slime Diaries That Time I Got Reincarnated as a Slime - S01E04 - "
        "(BD 1080p NVENC AV1 10-bit Dual Audio TrueHD 5.1)-Anon.mkv",
        "[Yameii] The Slime Diaries - That Time I Got Reincarnated as a Slime - 04 "
        "[English Dub] [WEB-DL 720p] [F2BF84B5].mkv",
        "[Asakura] Tensei Shitara Slime Datta Ken OAD 04 [BDRip 1920x1080 x265 10bit FLAC] [4BC5BF28].mkv",
        "Tensei Shitara Slime Datta Ken - OAD 04.mkv",
        "[JAM_CLUB]_Tensei_Shitara_Slime_Datta_Ken_OVA_04_[1080p][RUS][DUB].mp4",
        "[Erai-raws] Tensei shitara Slime Datta Ken - 04 [1080p][Multiple Subtitle][10319520].mkv",
        "[Erai-raws] Tensei shitara Slime Datta Ken - 04 [480p][Multiple Subtitle][52043081].mkv",
    }
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_graph(root_id: int) -> FranchiseGraph:
    recorded: dict[str, Any] = _read(_SEARCH / f"anilist__franchise__{root_id}.json")
    graph: FranchiseGraph = FranchiseGraph(root_id, {}, frozenset(), False)
    for request in recorded["requests"]:
        graph = parse_franchise_page(request["body"]["data"], root_id, frozenset(request["ids"]), graph)
    return graph


def _mapping(raw_episodes: dict[str, Any], *, episodes: tuple[ListedEpisode, ...] = ()) -> AniZipMapping:
    return AniZipMapping(
        kitsu_id=None,
        catalog_type=None,
        episode_count=None,
        episodes=episodes,
        specials=(),
        max_age_s=None,
        raw_episodes=raw_episodes,
    )


def _fixture_mapping(anilist_id: int) -> AniZipMapping:
    return parse_mapping(_read(_SEARCH / f"anizip__{anilist_id}.json"))


def _fixture_streams(name: str) -> list[StreamCandidate]:
    return list(parse_streams(_read(_SEARCH / name)))


def _stream(file_name: str | None = "Star Garden - 05.mkv", **changes: Any) -> StreamCandidate:
    stream: StreamCandidate = StreamCandidate(
        info_hash=hashlib.sha256(repr((file_name, sorted(changes.items()))).encode()).hexdigest()[:40],
        name=None,
        file_index=None,
        file_name=file_name,
        release="",
        path=None,
        seeders=None,
        size_text=None,
        provider=None,
        tags=(),
        trackers=(),
    )
    return replace(stream, **changes)


def _target(**changes: Any) -> dict[str, object]:
    target: dict[str, object] = {
        "aliases": ["Star Garden"],
        "type": "TV",
        "season": 1,
        "episode": 5,
        "local_episode": 5,
        "absolute": 5,
        "episode_title": "A Journey Through Clouds",
        "other_episode_titles": ["The Silent Winter Night"],
        "other_series": [],
    }
    target.update(changes)
    return target


def _edge(relation: str, target_id: int, media_type: str = "ANIME") -> dict[str, Any]:
    return {"relationType": relation, "node": {"id": target_id, "type": media_type}}


def _node(
    identifier: int,
    media_format: str,
    title: dict[str, str | None],
    *,
    year: int | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": identifier,
        "type": "ANIME",
        "format": media_format,
        "status": "FINISHED",
        "seasonYear": year,
        "startDate": {"year": year, "month": 1, "day": 1} if year is not None else {},
        "title": title,
    }
    if edges is not None:
        node["relations"] = {"edges": edges}
    return node


def _graph(*nodes: Mapping[str, Any], root_id: int = 1) -> FranchiseGraph:
    by_id: dict[int, Mapping[str, Any]] = {node["id"]: node for node in nodes}
    queried: frozenset[int] = frozenset(identifier for identifier, node in by_id.items() if "relations" in node)
    _, _, missing = franchise_traversal(root_id, by_id, queried)
    return FranchiseGraph(root_id=root_id, nodes=by_id, queried=queried, complete=not missing)


def _star_garden_graph(*, s1_expanded: bool = True) -> FranchiseGraph:
    s1_edges: list[dict[str, Any]] | None = [_edge("SEQUEL", 2)] if s1_expanded else None
    return _graph(
        _node(
            2,
            "TV",
            {"romaji": "Hoshi no Niwa 2", "english": "Star Garden Season 2", "native": "星の庭 2"},
            year=2020,
            edges=[_edge("PREQUEL", 1), _edge("SIDE_STORY", 3), _edge("SPIN_OFF", 4), _edge("ADAPTATION", 9, "MANGA")],
        ),
        _node(
            1,
            "TV",
            {"romaji": "Hoshi no Niwa", "english": "Star Garden", "native": "星の庭"},
            year=2018,
            edges=s1_edges,
        ),
        _node(3, "OVA", {"romaji": "Hoshi no Niwa OVA", "english": None, "native": None}, year=2019),
        _node(4, "TV", {"romaji": "Hoshi no Niwa Nikki", "english": "Star Garden Diaries", "native": None}, year=2021),
        root_id=2,
    )


def _pack_name(name: str) -> bool:
    return parse_release_name(name).is_pack


def _rank(target: dict[str, object], streams: list[StreamCandidate]) -> tuple[RankedCandidate, ...]:
    return rank_candidates(target, streams_releases(streams, pack_name=_pack_name), donghua=False)


def _ranked(target: dict[str, object], streams: list[StreamCandidate]) -> list[StreamCandidate]:
    return [candidate.stream for candidate in _rank(target, streams)]


def _regression_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = _read(_REGRESSIONS)
    return cases


def _solo_leveling_s2e1() -> dict[str, object]:
    target: dict[str, object] = next(
        case["target"]
        for case in _regression_cases()
        if "Solo Leveling" in case["target"]["aliases"] and case["target"].get("other_episode_titles")
    )
    return target


def test_identity_target_slime_s1e4_has_exactly_the_corpus_keys_and_mapping_values() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4)
    assert set(target) == _TARGET_KEYS
    assert target["aliases"] == [
        "That Time I Got Reincarnated as a Slime",
        "転生したらスライムだった件",
        "Tensei Shitara Slime Datta Ken",
    ]
    assert (target["type"], target["local_episode"], target["season"], target["episode"], target["absolute"]) == (
        "TV",
        4,
        1,
        4,
        4,
    )
    assert target["episode_title"] == "In the Kingdom of the Dwarves"
    other_titles: object = target["other_episode_titles"]
    assert isinstance(other_titles, list)
    assert "In the Kingdom of the Dwarves" not in other_titles
    assert "Tales: Veldora's Journal" in other_titles
    other_series: object = target["other_series"]
    assert isinstance(other_series, list)
    assert "The Slime Diaries" in other_series
    assert "Attack on Titan" in other_series


def test_identity_target_later_season_inherits_first_season_after_own_sorted_titles() -> None:
    target: dict[str, object] = identity_target(_star_garden_graph(), 2, _mapping({}), 5)
    assert target["aliases"] == [
        "Star Garden Season 2",
        "星の庭 2",
        "Hoshi no Niwa 2",
        "Hoshi no Niwa",
        "Star Garden",
        "星の庭",
    ]
    assert target["other_series"] == ["Hoshi no Niwa OVA", "Hoshi no Niwa Nikki", "Star Garden Diaries"]


def test_identity_target_incomplete_chain_keeps_only_own_aliases() -> None:
    target: dict[str, object] = identity_target(_star_garden_graph(s1_expanded=False), 2, _mapping({}), 5)
    assert target["aliases"] == ["Star Garden Season 2", "星の庭 2", "Hoshi no Niwa 2"]


def test_identity_target_complete_root_with_incomplete_selected_leaf_keeps_only_leaf_aliases() -> None:
    root: dict[str, Any] = _node(10, "TV", {"romaji": "Hoshi Gaiden"}, year=2024, edges=[_edge("SPIN_OFF", 2)])
    graph: FranchiseGraph = _graph(root, *_star_garden_graph(s1_expanded=False).nodes.values(), root_id=10)
    assert graph.complete
    assert not franchise_view(graph, 2).complete
    target: dict[str, object] = identity_target(graph, 2, _mapping({}), 5)
    assert target["aliases"] == ["Star Garden Season 2", "星の庭 2", "Hoshi no Niwa 2"]
    other_series: object = target["other_series"]
    assert isinstance(other_series, list)
    assert "Hoshi Gaiden" in other_series


def test_identity_target_missing_mapping_entry_leaves_episode_fields_empty() -> None:
    raw: dict[str, Any] = {
        "1": {"seasonNumber": 1, "episodeNumber": 1, "title": {"en": "First Light"}},
        "S1": {"seasonNumber": 0, "episodeNumber": 1, "title": {"x-jat": "Extra: Recap `One`"}},
        "2": {"title": {"en": ""}},
    }
    target: dict[str, object] = identity_target(_star_garden_graph(), 2, _mapping(raw), 3)
    assert (target["season"], target["episode"], target["absolute"], target["episode_title"]) == (
        None,
        None,
        None,
        None,
    )
    assert target["other_episode_titles"] == ["First Light", "Recap 'One'"]


def test_identity_target_without_numbering() -> None:
    raw: dict[str, Any] = {
        "1": {"seasonNumber": 2, "episodeNumber": 1, "absoluteEpisodeNumber": 13, "title": {"en": "First Light"}},
        "2": {"seasonNumber": 2, "episodeNumber": 2, "absoluteEpisodeNumber": 14, "title": {"en": "Second Light"}},
    }
    numbered: dict[str, object] = identity_target(_star_garden_graph(), 2, _mapping(raw), 1)
    target: dict[str, object] = identity_target(_star_garden_graph(), 2, _mapping(raw), 1, numbering=False)
    assert numbered["episode_title"] == "First Light"
    assert target == numbered | {"season": None, "episode": None, "absolute": None, "episode_title": None}
    assert target["other_episode_titles"] == ["Second Light"]


def test_numbering_gap_missing_key() -> None:
    mapping: AniZipMapping = _mapping({"1": {"seasonNumber": 1, "episodeNumber": 1}})
    assert numbering_gap(mapping, 2, None, movie=False) == "none"
    assert numbering_gap(mapping, 1, None, movie=False) is None


def test_numbering_gap_without_season_episode() -> None:
    mapping: AniZipMapping = _mapping({"1": {"title": {"en": "Episode 1"}}, "2": {"seasonNumber": 1}})
    assert numbering_gap(mapping, 1, 2, movie=False) == "none"
    assert numbering_gap(mapping, 2, 2, movie=False) == "none"


def test_numbering_gap_duplicate_keeps_lowest() -> None:
    mapping: AniZipMapping = _mapping(
        {
            "1": {"seasonNumber": 2, "episodeNumber": 1, "absoluteEpisodeNumber": 13},
            "2": {"seasonNumber": 2, "episodeNumber": 1, "absoluteEpisodeNumber": 13},
            "3": {"seasonNumber": 2, "episodeNumber": 2, "absoluteEpisodeNumber": 14},
        }
    )
    assert [numbering_gap(mapping, number, None, movie=False) for number in (1, 2, 3)] == [None, "duplicate", None]


def test_numbering_gap_tvdb_season() -> None:
    mapping: AniZipMapping = _mapping({"1": {"seasonNumber": 1, "episodeNumber": 1}})
    assert numbering_gap(mapping, 1, 2, movie=False) == "tvdb_season"
    assert numbering_gap(mapping, 1, 1, movie=False) is None
    assert numbering_gap(mapping, 1, None, movie=False) is None


def test_numbering_gap_skips_movie() -> None:
    mapping: AniZipMapping = _mapping({"1": {"title": {"en": "Complete Movie"}}, "S1": {"title": {"en": "Making of"}}})
    assert numbering_gap(mapping, 1, None, movie=True) is None
    assert numbering_gap(mapping, 1, None, movie=False) == "none"


def test_identity_target_special_key_is_excluded_only_for_its_own_number() -> None:
    raw: dict[str, Any] = {
        "1": {"seasonNumber": 1, "episodeNumber": 1, "absoluteEpisodeNumber": 13, "title": {"en": "First Light"}},
        "S1": {"title": {"en": "Recap"}},
    }
    target: dict[str, object] = identity_target(_star_garden_graph(), 2, _mapping(raw), 1)
    assert (target["season"], target["episode"], target["absolute"], target["episode_title"]) == (
        1,
        1,
        13,
        "First Light",
    )
    assert target["other_episode_titles"] == ["Recap"]


def test_identity_target_movie_uses_first_local_episode_and_movie_type() -> None:
    graph: FranchiseGraph = _graph(
        _node(7, "MOVIE", {"romaji": "Hoshi no Niwa Gekijouban", "english": "Star Garden Movie"}, year=2022, edges=[]),
        root_id=7,
    )
    target: dict[str, object] = identity_target(graph, 7, _mapping({"1": {"title": {"en": "Star Garden Movie"}}}), 1)
    assert (target["type"], target["local_episode"], target["aliases"]) == (
        "MOVIE",
        1,
        ["Star Garden Movie", "Hoshi no Niwa Gekijouban"],
    )


def test_identity_target_does_not_depend_on_graph_root_or_root_completeness() -> None:
    graph: FranchiseGraph = _fixture_graph(_SLIME_S1)
    mapping: AniZipMapping = _fixture_mapping(_SLIME_S1)
    expected: dict[str, object] = identity_target(graph, _SLIME_DIARIES, mapping, 4)
    for root_id in (_SLIME_DIARIES, _SLIME_OAD):
        moved: FranchiseGraph = replace(graph, root_id=root_id, complete=False)
        assert identity_target(moved, _SLIME_DIARIES, mapping, 4) == expected


def test_identity_target_returns_a_new_json_object_per_call() -> None:
    graph: FranchiseGraph = _star_garden_graph()
    first: dict[str, object] = identity_target(graph, 2, _mapping({}), 5)
    aliases: object = first["aliases"]
    assert isinstance(aliases, list)
    aliases.clear()
    assert identity_target(graph, 2, _mapping({}), 5)["aliases"]


def test_identity_target_node_outside_view_joins_other_series_and_changes_verdict() -> None:
    mapping: AniZipMapping = _mapping(
        {"5": {"seasonNumber": 1, "episodeNumber": 5, "absoluteEpisodeNumber": 5, "title": {"en": "Clouds"}}}
    )
    selected: dict[str, Any] = _node(1, "TV", {"romaji": "Star Garden"}, year=2018, edges=[_edge("SPIN_OFF", 2)])
    leaf: dict[str, Any] = _node(2, "TV", {"romaji": "Star Garden Moon"}, year=2020, edges=[_edge("CHARACTER", 3)])
    hidden: dict[str, Any] = _node(3, "TV", {"romaji": "Star Garden Zero"}, year=2022)
    with_hidden: FranchiseGraph = _graph(selected, leaf, hidden)
    without_hidden: FranchiseGraph = _graph(selected, leaf)
    assert 3 not in {entry.anilist_id for entry in franchise_view(with_hidden, 1).entries}
    target: dict[str, object] = identity_target(with_hidden, 1, mapping, 5)
    assert target["other_series"] == ["Star Garden Moon", "Star Garden Zero"]
    candidate: dict[str, str | None] = {"release": "Star Garden Zero", "path": None, "filename": "Star Garden - 05.mkv"}
    assert classify(identity_target(without_hidden, 1, mapping, 5), candidate).verdict is IdentityVerdict.MATCH
    assert classify(target, candidate).verdict is not IdentityVerdict.MATCH


def test_franchise_view_slime_projects_ten_entries_from_twenty_five_nodes() -> None:
    graph: FranchiseGraph = _fixture_graph(_SLIME_S1)
    view = franchise_view(graph, _SLIME_S1)
    assert (len(graph.nodes), len(view.entries), view.complete) == (25, 10, True)
    assert view.entries[0].anilist_id == _SLIME_S4
    assert next(entry for entry in view.entries if entry.anilist_id == _SLIME_S1).relation == "SELF"
    starts: list[tuple[bool, int, int, int]] = [premiere_order(entry.year, entry.start) for entry in view.entries]
    assert starts == sorted(starts, reverse=True)
    by_id: dict[int, EntryGroup] = {entry.anilist_id: entry.group for entry in view.entries}
    assert (by_id[_SLIME_S4], by_id[_SLIME_OAD], by_id[_SLIME_DIARIES]) == (
        EntryGroup.SEASON,
        EntryGroup.EXTRA,
        EntryGroup.OTHER,
    )


def test_franchise_view_diaries_projects_two_entries_from_eight_nodes() -> None:
    graph: FranchiseGraph = _fixture_graph(_SLIME_DIARIES)
    assert (len(graph.nodes), len(franchise_view(graph, _SLIME_DIARIES).entries)) == (8, 2)


def test_franchise_view_orders_every_entry_newest_first_and_keeps_every_anime_relation() -> None:
    view = franchise_view(_star_garden_graph(), 2)
    entries: dict[int, FranchiseEntry] = {entry.anilist_id: entry for entry in view.entries}
    assert [(entry.anilist_id, entry.group, entry.relation) for entry in view.entries] == sorted(
        [
            (1, EntryGroup.SEASON, "PREQUEL"),
            (2, EntryGroup.SEASON, "SELF"),
            (3, EntryGroup.EXTRA, "SIDE_STORY"),
            (4, EntryGroup.OTHER, "SPIN_OFF"),
        ],
        key=lambda item: (premiere_order(entries[item[0]].year, entries[item[0]].start), item[0]),
        reverse=True,
    )
    assert entries[2].start == date(2020, 1, 1)
    assert entries[2].year == 2020
    assert [(relation.source_id, relation.target_id, relation.relation) for relation in view.relations] == [
        (1, 2, "SEQUEL"),
        (2, 1, "PREQUEL"),
        (2, 3, "SIDE_STORY"),
        (2, 4, "SPIN_OFF"),
    ]
    assert view.complete


def test_franchise_view_undated_entry_leads_and_newest_premiere_follows() -> None:
    year_only: dict[str, Any] = {**_node(4, "OVA", {"romaji": "D"}, year=2030), "startDate": {"year": 2030}}
    graph: FranchiseGraph = _graph(
        _node(
            1,
            "TV",
            {"romaji": "A"},
            year=2018,
            edges=[_edge("SIDE_STORY", 2), _edge("SIDE_STORY", 3), _edge("SIDE_STORY", 4), _edge("SIDE_STORY", 5)],
        ),
        _node(2, "OVA", {"romaji": "B"}),
        _node(3, "OVA", {"romaji": "C"}, year=2030),
        year_only,
        {**_node(5, "OVA", {"romaji": "E"}), "startDate": {"year": 2031, "month": 2, "day": 3}, "seasonYear": 2030},
    )
    entries: tuple[FranchiseEntry, ...] = franchise_view(graph, 1).entries
    assert [entry.anilist_id for entry in entries] == [2, 5, 4, 3, 1]
    assert entries[0].status == "FINISHED"
    assert (entries[2].year, entries[2].start, entries[1].year) == (2030, None, 2031)


def test_franchise_view_unexpanded_chain_is_incomplete() -> None:
    assert not franchise_view(_star_garden_graph(s1_expanded=False), 2).complete


def test_episode_listing_known_count_without_sources_lists_bare_numbers() -> None:
    upcoming = episode_listing(5, _mapping({}), "NOT_YET_RELEASED", 12, (), _NOW)
    assert upcoming.episodes == tuple(ListedEpisode(number=number) for number in range(1, 13))
    assert upcoming.aired is None
    finished = episode_listing(5, _mapping({}), "FINISHED", 12, (), _NOW)
    assert finished.aired == 12
    assert all(episode.aired for episode in finished.episodes)


def _aired_numbers(status: str, count: int | None, schedule: tuple[ListedEpisode, ...]) -> list[int]:
    past: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    mapping: AniZipMapping = _mapping({}, episodes=tuple(ListedEpisode(n, airs_at=past) for n in range(1, 7)))
    listing = episode_listing(5, mapping, status, count, schedule, _NOW)
    return [episode.number for episode in listing.episodes if episode.aired]


def test_hiatus_episode_with_a_past_anilist_date_is_aired_while_undated_numbers_are_not() -> None:
    schedule: tuple[ListedEpisode, ...] = (ListedEpisode(1, airs_at=datetime(2026, 1, 1, tzinfo=UTC)),)
    assert _aired_numbers("HIATUS", 6, schedule) == [1]


def test_schedule_gap_airs_its_dated_episode_and_confirms_undated_numbers_only_up_to_the_aired_count() -> None:
    schedule: tuple[ListedEpisode, ...] = (ListedEpisode(5, airs_at=datetime(2026, 1, 1, tzinfo=UTC)),)
    assert _aired_numbers("RELEASING", 6, schedule) == [1, 5]


def test_future_anilist_date_blocks_its_episode_even_below_the_aired_count() -> None:
    schedule: tuple[ListedEpisode, ...] = (
        ListedEpisode(1, airs_at=datetime(2026, 12, 1, tzinfo=UTC)),
        ListedEpisode(2, airs_at=datetime(2026, 1, 1, tzinfo=UTC)),
    )
    assert _aired_numbers("RELEASING", 6, schedule) == [2]


@pytest.mark.parametrize("status", ["UNKNOWN", "RELEASING", "FINISHED", "HIATUS"])
def test_past_ani_zip_dates_never_confirm_airing_without_anilist_schedule_or_count(status: str) -> None:
    assert _aired_numbers(status, None, ()) == []


def test_episode_listing_partial_sources_fill_gaps_without_losing_metadata() -> None:
    mapping: AniZipMapping = _mapping(
        {},
        episodes=(
            ListedEpisode(1, "First", datetime(2026, 1, 1, tzinfo=UTC), 1, 1, 1),
            ListedEpisode(2, "Second", datetime(2026, 1, 8, tzinfo=UTC), 1, 2, 2),
        ),
    )
    schedule: tuple[ListedEpisode, ...] = (
        ListedEpisode(2, airs_at=datetime(2026, 1, 9, tzinfo=UTC)),
        ListedEpisode(3, airs_at=datetime(2026, 1, 16, tzinfo=UTC)),
        ListedEpisode(1),
    )
    listing = episode_listing(5, mapping, "RELEASING", 4, schedule, _NOW)
    assert listing.episodes == (
        ListedEpisode(1, "First", datetime(2026, 1, 1, tzinfo=UTC), 1, 1, 1, aired=True, airs_at_fallback=True),
        ListedEpisode(2, "Second", datetime(2026, 1, 9, tzinfo=UTC), 1, 2, 2, aired=True),
        ListedEpisode(3, airs_at=datetime(2026, 1, 16, tzinfo=UTC), aired=True),
        ListedEpisode(4),
    )
    assert listing.aired == 2


def test_valid_empty_schedule_marks_every_ani_zip_date_as_fallback() -> None:
    mapping: AniZipMapping = _mapping(
        {}, episodes=(ListedEpisode(1, airs_at=datetime(2026, 1, 1, tzinfo=UTC)), ListedEpisode(2))
    )
    listing = episode_listing(5, mapping, "FINISHED", 2, (), _NOW)
    assert listing.schedule_warning is None
    assert [episode.airs_at_fallback for episode in listing.episodes] == [True, False]


def test_episode_listing_unknown_count_and_empty_sources_invent_nothing() -> None:
    listing = episode_listing(5, _mapping({}), "UNKNOWN", None, (), _NOW)
    assert (listing.episodes, listing.episode_count, listing.aired) == ((), None, None)


def test_episode_listing_unknown_count_keeps_only_four_scheduled_rows_out_of_twelve() -> None:
    schedule: tuple[ListedEpisode, ...] = tuple(ListedEpisode(number, airs_at=_NOW) for number in (1, 2, 11, 12))
    listing: EpisodeListing = episode_listing(5, _mapping({}), "RELEASING", None, schedule, _NOW)
    assert listing.episode_count is None
    assert [episode.number for episode in listing.episodes] == [1, 2, 11, 12]
    assert all(episode.title is None and episode.airs_at == _NOW for episode in listing.episodes)


def test_episode_listing_falls_back_to_mapping_count_and_keeps_source_fields() -> None:
    special: ListedSpecial = ListedSpecial("S1", "Recap", date(2026, 2, 1))
    mapping: AniZipMapping = replace(
        _mapping({}), kitsu_id=41024, catalog_type="TV", episode_count=3, specials=(special,)
    )
    retry_at: datetime = datetime(2026, 9, 29, 12, 5, tzinfo=UTC)
    listing = episode_listing(
        5, mapping, "RELEASING", None, (), _NOW, schedule_warning="TITLE_CATALOG_FAILED", schedule_retry_at=retry_at
    )
    assert [episode.number for episode in listing.episodes] == [1, 2, 3]
    assert (listing.anilist_id, listing.kitsu_id, listing.catalog_type, listing.episode_count) == (5, 41024, "TV", 3)
    assert (listing.specials, listing.aired) == ((special,), None)
    assert (listing.schedule_warning, listing.schedule_retry_at) == ("TITLE_CATALOG_FAILED", retry_at)


@pytest.mark.parametrize(("anilist", "expected"), [(None, 12), (13, 13)], ids=["unknown", "anilist-wins"])
def test_a_stale_mapping_count_grows_to_the_anilist_schedule_but_never_overrides_the_anilist_count(
    anilist: int | None, expected: int
) -> None:
    mapping: AniZipMapping = replace(_mapping({}), episode_count=4)
    schedule: tuple[ListedEpisode, ...] = tuple(ListedEpisode(number, airs_at=_NOW) for number in range(1, 13))

    listing: EpisodeListing = episode_listing(5, mapping, "RELEASING", anilist, schedule, _NOW)

    assert listing.episode_count == expected
    assert [episode.number for episode in listing.episodes] == list(range(1, expected + 1))


@pytest.mark.parametrize(
    ("file_name", "supported"),
    [
        ("Star Garden - 05.mkv", True),
        ("Star Garden - 05.MP4", True),
        ("Star Garden - 05.avi", False),
        ("Star Garden - 05.ts", False),
        ("Star Garden - 05.mpegts", False),
        ("Star Garden - 05.x", False),
        ("Star Garden - 05.123", False),
        ("Star Garden - 05 (TrueHD 5.1)", None),
        ("Star Garden - 05. Final", None),
        (".mkv", None),
        (None, None),
        ("Star Garden - 05", None),
    ],
)
def test_rank_container_support_leaves_unknown_containers_unpenalized(
    file_name: str | None, supported: bool | None
) -> None:
    assert _rank(_target(), [_stream(file_name)])[0].supported is supported


def test_rank_container_falls_back_to_the_path_but_never_reads_the_release() -> None:
    stream: StreamCandidate = _stream(None, release="Star Garden - 05 AAC 5.1", path="Star Garden/Star Garden - 05.avi")
    assert _rank(_target(), [stream])[0].supported is False
    assert _rank(_target(), [_stream(None, release="Star Garden - 05.avi")])[0].supported is None


def test_rank_container_prefers_the_file_name_over_the_path() -> None:
    stream: StreamCandidate = _stream("Star Garden - 05.mkv", path="Star Garden/Star Garden - 05.avi")
    assert _rank(_target(), [stream])[0].supported is True


@pytest.mark.parametrize(("path", "supported"), [("Star Garden - 05.avi", False), ("Star Garden - 05.ts", False)])
def test_rank_listed_file_without_torrentio_hint_knows_its_container(path: str, supported: bool) -> None:
    stream: StreamCandidate = _stream(None, release="Star Garden - 05")
    releases: tuple[EpisodeRelease, ...] = merge_releases(
        (stream,), {stream.info_hash: TsukiHimeFiles((ListedFile(path, 100),))}, pack_name=_pack_name
    )
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), releases, donghua=False)
    assert ranked[0].stream.file_name is None
    assert ranked[0].supported is supported
    assert suggestion(ranked, numbering=True) == (None, False)


def test_rank_traits_read_both_the_file_name_and_the_path() -> None:
    stream: StreamCandidate = _stream(
        "Star Garden - 05 [1080p] [English Dub] [CR WEB-DL] [BluRay] [HardSub].mkv",
        release="Star Garden",
        path="Star Garden - 05.mkv",
    )
    traits: ReleaseTraits = _rank(_target(), [stream])[0].traits
    assert traits.resolution == 1080
    assert traits.dub_only
    assert traits.platform
    assert traits.bluray
    assert traits.hardsub
    assert suggestion(_rank(_target(), [stream]), numbering=True) == (None, False)


def test_rank_traits_of_a_pack_file_ignore_the_names_of_other_files() -> None:
    stream: StreamCandidate = _stream(None, release="Star Garden S01 [Batch]")
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (ListedFile("Star Garden - 04 [720p] [English Dub].mkv", 100), ListedFile("Star Garden - 05 [1080p].mkv", 100))
    )
    releases: tuple[EpisodeRelease, ...] = merge_releases((stream,), {stream.info_hash: listing}, pack_name=_pack_name)
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), releases, donghua=False)
    assert ranked[0].stream.path == "Star Garden - 05 [1080p].mkv"
    assert ranked[0].traits.resolution == 1080
    assert not ranked[0].traits.dub_only


def test_rank_pack_row_carries_the_size_of_its_representative_file_not_of_the_pack() -> None:
    stream: StreamCandidate = replace(_stream(None, release="Star Garden S01 [Batch]"), size_text="16.80 GB")
    listing: TsukiHimeFiles = TsukiHimeFiles(
        (
            ListedFile("Star Garden - 04 [1080p].mkv", 1_300_000_000),
            ListedFile("Star Garden - 05 [1080p].mkv", 1_400_000_000),
        )
    )
    listed: tuple[EpisodeRelease, ...] = merge_releases((stream,), {stream.info_hash: listing}, pack_name=_pack_name)
    ranked: RankedCandidate = rank_candidates(_target(), listed, donghua=False)[0]
    unlisted: RankedCandidate = _rank(_target(), [stream])[0]
    assert ranked.stream.path == "Star Garden - 05 [1080p].mkv"
    assert ranked.stream.file_size == 1_400_000_000
    assert ranked.stream.size_text == "16.80 GB"
    assert unlisted.stream.file_size is None


def test_rank_torrentio_equivalent_to_conf_model() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4)
    streams: list[StreamCandidate] = _fixture_streams("torrentio__kitsu-41024-4.json")
    renamed: int = next(
        index
        for index, stream in enumerate(streams)
        if stream.path is not None and sum(item.info_hash == stream.info_hash for item in streams) == 1
    )
    original: StreamCandidate = streams[renamed]
    streams[renamed] = replace(original, file_name="[Trix] Tensei Shitara Slime Datta Ken - 04.mkv")
    by_file: dict[tuple[str, int | None, str | None, str | None], StreamCandidate] = {
        (stream.info_hash, stream.file_index, stream.file_name, stream.path): stream for stream in streams
    }
    ranked: tuple[RankedCandidate, ...] = _rank(target, streams)
    assert len(ranked) == len({stream.info_hash for stream in streams})
    for row in ranked:
        source: StreamCandidate = by_file[
            row.stream.info_hash, row.stream.file_index, row.stream.file_name, row.stream.path
        ]
        candidate: dict[str, object] = {"release": source.release, "path": source.path, "filename": source.file_name}
        assert row.identity == classify(target, candidate)
        assert row.confidence == (None if row.conflict else confidence(identity_evidence(target, candidate)))
    renamed_row: RankedCandidate = next(
        row
        for row in ranked
        if row.stream.file_name == "[Trix] Tensei Shitara Slime Datta Ken - 04.mkv"
        and row.stream.path == streams[renamed].path
    )
    assert renamed_row.traits == _rank(target, [original])[0].traits
    assert renamed_row.traits.resolution == 1080


def test_list_order_puts_dub_only_rows_then_conflicts_after_the_other_rows() -> None:
    good: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    uncertain: StreamCandidate = _stream("Moon Garden - 05 [1080p].mkv", seeders=9999)
    dubbed: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("Dubbed",))
    bad: StreamCandidate = _stream("Star Garden - 05 [1080p].rar", tags=("\U0001f1f5\U0001f1f1",))
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [bad, dubbed, uncertain, good])
    assert [candidate.stream for candidate in ranked] == [uncertain, good, dubbed, bad]
    assert [(candidate.conflict, candidate.traits.dub_only) for candidate in ranked] == [
        (False, False),
        (False, False),
        (False, True),
        (True, False),
    ]
    assert ranked[3].confidence is None
    assert list_order(tuple(reversed(ranked))) == ranked
    assert _rank(_target(), []) == ()


def test_rank_candidates_context_conflicts_follow_every_other_row() -> None:
    good: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    for context in ("Star Garden Season 2", "극장판"):
        bad: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", release=context, seeders=9999)
        ranked: tuple[RankedCandidate, ...] = _rank(_target(), [bad, good])
        assert [candidate.stream for candidate in ranked] == [good, bad]
        assert ranked[1].conflict


def test_rank_candidates_resolution_classes_follow_owner_order() -> None:
    heights: list[str] = [
        "",
        " [480p]",
        " [576p]",
        " [720p]",
        " [2160p]",
        " [1080p]",
        " [1440x1080]",
        " [1440p]",
    ]
    streams: list[StreamCandidate] = [_stream(f"Star Garden - 05{height}.mkv") for height in heights]
    streams.append(_stream("Star Garden - 05.mkv", release="Star Garden - 05 [1440×1080]"))
    assert [candidate.traits.resolution for candidate in _rank(_target(), streams)] == [
        1080,
        1080,
        1080,
        2160,
        720,
        1440,
        576,
        480,
        None,
    ]


def test_list_order_class_precedes_weighted_quality() -> None:
    base: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv")
    polish_720: StreamCandidate = _stream("Star Garden - 05 [720p].mkv", tags=("\U0001f1f5\U0001f1f1",))
    polish: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("\U0001f1f5\U0001f1f1",))
    english: StreamCandidate = _stream("Star Garden - 05 [1080p][Multi-Subs].mkv")
    dubbed: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("Dubbed",))
    streams: list[StreamCandidate] = [dubbed, polish_720, base, english, polish]
    assert _ranked(_target(), streams) == [polish, english, base, polish_720, dubbed]


def test_list_order_seed_points_then_hash_break_ties() -> None:
    unknown: StreamCandidate = _stream()
    zero: StreamCandidate = _stream(seeders=0)
    two: StreamCandidate = _stream(seeders=2)
    assert _ranked(_target(), [zero, two, unknown]) == [unknown, two, zero]
    first: StreamCandidate = _stream(info_hash="1" * 40)
    second: StreamCandidate = _stream(info_hash="2" * 40)
    assert _ranked(_target(), [second, first]) == [first, second]


def _shown(
    digit: str,
    *,
    quality: float,
    certainty: float | None,
    seeders: int | None,
    verdict: IdentityVerdict = IdentityVerdict.MATCH,
) -> RankedCandidate:
    base: RankedCandidate = _rank(_target(), [_stream()])[0]
    return replace(
        base,
        stream=replace(base.stream, info_hash=digit * 40),
        traits=replace(base.traits, seeders=seeders),
        quality=quality,
        confidence=certainty,
        identity=replace(base.identity, verdict=verdict),
    )


def test_list_order_rows_showing_equal_quality_and_confidence_go_by_seeds() -> None:
    hidden_edge: RankedCandidate = _shown("1", quality=75.0, certainty=0.9999, seeders=60)
    seeded: RankedCandidate = _shown("2", quality=75.0, certainty=0.9996, seeders=192)
    assert (quality_text(hidden_edge), confidence_text(hidden_edge)) == (quality_text(seeded), confidence_text(seeded))
    ranked: tuple[RankedCandidate, ...] = list_order((hidden_edge, seeded))
    assert ranked == (seeded, hidden_edge)
    assert suggestion(ranked, numbering=True) == (0, False)


def test_list_order_shown_tie_puts_a_match_before_a_more_seeded_uncertain_row_and_suggests_it() -> None:
    uncertain: RankedCandidate = _shown(
        "1", quality=35.0, certainty=1.0, seeders=200, verdict=IdentityVerdict.INSUFFICIENT
    )
    match: RankedCandidate = _shown("2", quality=35.0, certainty=1.0, seeders=120)
    ranked: tuple[RankedCandidate, ...] = list_order((uncertain, match))
    assert ranked == (match, uncertain)
    assert suggestion(ranked, numbering=True) == (0, False)


def test_list_order_visibly_higher_quality_keeps_an_uncertain_row_before_a_match() -> None:
    uncertain: RankedCandidate = _shown(
        "1", quality=36.0, certainty=1.0, seeders=0, verdict=IdentityVerdict.INSUFFICIENT
    )
    match: RankedCandidate = _shown("2", quality=35.0, certainty=1.0, seeders=500)
    ranked: tuple[RankedCandidate, ...] = list_order((match, uncertain))
    assert ranked == (uncertain, match)
    assert suggestion(ranked, numbering=True) == (0, True)


def test_list_order_visibly_higher_confidence_keeps_an_uncertain_row_before_a_match() -> None:
    uncertain: RankedCandidate = _shown(
        "1", quality=35.0, certainty=0.99, seeders=0, verdict=IdentityVerdict.INSUFFICIENT
    )
    match: RankedCandidate = _shown("2", quality=35.0, certainty=0.98, seeders=500)
    assert list_order((match, uncertain)) == (uncertain, match)


def test_list_order_known_zero_seeds_precede_unknown_seeds_in_a_shown_tie() -> None:
    unknown: RankedCandidate = _shown("1", quality=75.0, certainty=0.99, seeders=None)
    zero: RankedCandidate = _shown("2", quality=75.0, certainty=0.99, seeders=0)
    assert list_order((unknown, zero)) == (zero, unknown)


def test_list_order_seeds_never_beat_a_visibly_higher_confidence() -> None:
    surer: RankedCandidate = _shown("1", quality=75.0, certainty=0.95, seeders=1)
    seeded: RankedCandidate = _shown("2", quality=75.0, certainty=0.80, seeders=500)
    assert list_order((seeded, surer)) == (surer, seeded)


def test_list_order_equal_shown_rows_split_by_another_row_stay_apart() -> None:
    first: RankedCandidate = _shown("1", quality=76.4, certainty=1.0, seeders=1)
    between: RankedCandidate = _shown("2", quality=76.9, certainty=0.99, seeders=0)
    last: RankedCandidate = _shown("3", quality=75.6, certainty=1.0, seeders=999)
    assert (quality_text(first), confidence_text(first)) == (quality_text(last), confidence_text(last))
    assert list_order((last, between, first)) == (first, between, last)


def test_list_order_equal_shown_rows_without_confidence_go_by_seeds_then_quality() -> None:
    lower: RankedCandidate = _shown("1", quality=40.2, certainty=None, seeders=5)
    higher: RankedCandidate = _shown("2", quality=40.4, certainty=None, seeders=5)
    seeded: RankedCandidate = _shown("3", quality=39.6, certainty=None, seeders=6)
    assert list_order((lower, higher, seeded)) == (seeded, higher, lower)


def test_representative_prefers_match_then_uncertain_then_conflict_then_path() -> None:
    files: dict[str, ReleaseFile] = {
        path: ReleaseFile(path, None, None, from_listing=False, file_index=None)
        for path in (
            "B/Star Garden - 05.mkv",
            "A/Star Garden - 05.mkv",
            "A/Moon Garden - 05.mkv",
            "A/Star Garden - 05.rar",
        )
    }
    assessed: dict[str, tuple[ReleaseFile, IdentityEvidence]] = {
        path: (file, identity_evidence(_target(), file.identity_candidate(""))) for path, file in files.items()
    }
    assert representative(list(assessed.values()))[0].path == "A/Star Garden - 05.mkv"
    assert representative([assessed["A/Star Garden - 05.rar"], assessed["A/Moon Garden - 05.mkv"]])[0].path == (
        "A/Moon Garden - 05.mkv"
    )


def test_rank_candidates_two_matching_files_of_one_release_make_an_ambiguous_row() -> None:
    first: StreamCandidate = _stream(path="A/Star Garden - 05.mkv", info_hash="c" * 40, file_index=0)
    second: StreamCandidate = _stream(path="B/Star Garden - 05.mkv", info_hash="c" * 40, file_index=1)
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [second, first])
    assert len(ranked) == 1
    assert (ranked[0].ambiguous, ranked[0].stream.path, ranked[0].stream.file_index) == (
        True,
        "A/Star Garden - 05.mkv",
        0,
    )
    assert ranked[0].files == ("B/Star Garden - 05.mkv", "A/Star Garden - 05.mkv")


def test_rank_candidates_release_without_files_is_assessed_on_its_name() -> None:
    named: StreamCandidate = _stream(None, release="Star Garden - 05 [1080p]")
    other: StreamCandidate = _stream(None, release="Star Garden S02E05 [1080p]")
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [other, named])
    assert [candidate.stream for candidate in ranked] == [named, other]
    assert [candidate.release_name_only for candidate in ranked] == [True, True]
    assert ranked[0].identity.verdict is IdentityVerdict.MATCH
    assert ranked[0].confidence is not None
    assert (ranked[1].conflict, ranked[1].confidence) == (True, None)


def test_rank_candidates_blue_box_s2e1_suggests_the_polish_match_over_more_seeded_multisub_matches() -> None:
    target: dict[str, object] = next(
        case["target"] for case in _regression_cases() if "Blue Box" in case["target"]["aliases"]
    )
    polish_flag: tuple[str, ...] = ("Multi Subs", "\U0001f1f5\U0001f1f1")
    trix: StreamCandidate = _stream(
        "[Trix] Blue Box S02E01 [WEB-DL 1080p AV1 Opus] (Tri Audio, Multi Subs).mkv", seeders=12, tags=polish_flag
    )
    dkb: StreamCandidate = _stream(
        "[DKB] Ao no Hako - S02E01 [1080p][HEVC x265 10bit][Dual-Audio][Multi-Subs][B53BC902].mkv",
        seeders=285,
        tags=("Multi Subs",),
    )
    tsundere: StreamCandidate = _stream(
        "Blue Box S02E01 MULTi 1080p NF WEB-DL DDP5.1 AV1-Tsundere-Raws.mkv", seeders=157
    )
    ranked: tuple[RankedCandidate, ...] = _rank(target, [tsundere, dkb, trix])
    assert [candidate.stream for candidate in ranked] == [trix, dkb, tsundere]
    assert {candidate.identity.verdict for candidate in ranked} == {IdentityVerdict.MATCH}
    assert suggestion(ranked, numbering=True) == (0, False)


def test_list_order_unsupported_container_follows_supported_rows_of_its_group() -> None:
    avi: StreamCandidate = _stream("Star Garden - 05 [1080p].avi", seeders=500)
    unknown: StreamCandidate = _stream(None, release="Star Garden - 05 [720p]")
    mkv: StreamCandidate = _stream("Star Garden - 05 [480p].mkv", seeders=900)
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [avi, mkv, unknown])
    assert [candidate.stream for candidate in ranked] == [unknown, mkv, avi]
    assert [candidate.supported for candidate in ranked] == [None, True, False]


def test_rank_candidates_same_hash_files_form_one_row_on_the_matching_file() -> None:
    ranked: tuple[RankedCandidate, ...] = _rank(
        identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4),
        [
            stream
            for stream in _fixture_streams("torrentio__kitsu-41024-4.json")
            if stream.info_hash.startswith("21ff7425")
        ],
    )
    assert len(ranked) == 1
    assert (ranked[0].stream.file_index, ranked[0].identity.verdict, ranked[0].ambiguous) == (
        3,
        IdentityVerdict.MATCH,
        False,
    )
    assert len(ranked[0].files) == 2


def test_suggestion_is_first_group_one_row() -> None:
    match_720: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    uncertain_1080: StreamCandidate = _stream("Moon Garden - 05 [1080p].mkv")
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [match_720, uncertain_1080])
    assert [candidate.stream for candidate in ranked] == [uncertain_1080, match_720]
    assert suggestion(ranked, numbering=True) == (0, True)


def test_suggestion_marks_uncertain() -> None:
    match: tuple[RankedCandidate, ...] = _rank(_target(), [_stream("Star Garden - 05 [1080p].mkv")])
    uncertain: tuple[RankedCandidate, ...] = _rank(_target(), [_stream("Moon Garden - 05 [1080p].mkv")])
    assert suggestion(match, numbering=True) == (0, False)
    assert suggestion(uncertain, numbering=True) == (0, True)


def test_suggestion_skips_conflict_dub_only_and_unsupported_rows() -> None:
    avi_match: StreamCandidate = _stream("Star Garden - 05 [1080p].avi")
    dubbed: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("Dubbed",))
    mismatch: StreamCandidate = _stream("Star Garden - 05 [1080p].rar")
    low: StreamCandidate = _stream("Star Garden - 05 [480p].mkv")
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [avi_match, dubbed, mismatch, low])
    assert [candidate.stream for candidate in ranked] == [low, avi_match, dubbed, mismatch]
    assert suggestion(ranked, numbering=True) == (0, False)


def test_suggestion_none_when_group_one_empty() -> None:
    dubbed: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("Dubbed",))
    mismatch: StreamCandidate = _stream("Star Garden - 05.rar")
    avi: StreamCandidate = _stream("Star Garden - 05 [1080p].avi")
    assert suggestion(_rank(_target(), [dubbed, mismatch, avi]), numbering=True) == (None, False)
    assert suggestion((), numbering=True) == (None, False)


def test_suggestion_without_target_numbering_is_none() -> None:
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [_stream("Star Garden - 05 [1080p].mkv")])
    assert suggestion(ranked, numbering=False) == (None, False)


def test_visible_hides_720p_and_lower_only_beside_a_usable_high_resolution_match() -> None:
    heights: tuple[str, ...] = ("2160p", "1440p", "720p", "480p")
    lower: list[StreamCandidate] = [_stream(f"Star Garden - 05 [{height}].mkv") for height in heights[1:]]
    unknown: StreamCandidate = _stream("Star Garden - 05.mkv")
    high: StreamCandidate = _stream("Star Garden - 05 [2160p].mkv")
    shown: tuple[RankedCandidate, ...] = visible(_rank(_target(), [*lower, unknown, high]))
    assert [candidate.traits.resolution for candidate in shown] == [2160, 1440, None]
    uncertain: StreamCandidate = _stream("Moon Garden - 05 [1080p].mkv")
    unsupported: StreamCandidate = _stream("Star Garden - 05 [1080p].avi")
    for candidates in ([*lower, uncertain], [*lower, unsupported]):
        assert len(visible(_rank(_target(), candidates))) == len(candidates)


def test_visible_keeps_the_suggestion_when_the_only_high_match_cannot_be_suggested() -> None:
    low: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    dubbed: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=("Dubbed",))
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [dubbed, low])
    assert [(row.traits.resolution, row.traits.dub_only, row.identity.verdict) for row in ranked] == [
        (720, False, IdentityVerdict.MATCH),
        (1080, True, IdentityVerdict.MATCH),
    ]
    assert suggestion(ranked, numbering=True) == (0, False)
    assert visible(ranked) == ranked


def test_visible_never_hides_the_suggestion_beside_a_suggestible_high_match() -> None:
    low: RankedCandidate = _rank(_target(), [_stream("Star Garden - 05 [720p].mkv")])[0]
    high: RankedCandidate = _rank(_target(), [_stream("Star Garden - 05 [1080p].mkv")])[0]
    other: RankedCandidate = _rank(_target(), [_stream("Star Garden - 05 [480p].mkv")])[0]
    rows: tuple[RankedCandidate, ...] = (low, high, other)
    assert visible(rows, 0) == (low, high)
    assert visible(rows) == (high,)


def test_visible_hides_mismatches_and_keeps_uncertain_conflicts_and_the_suggestion() -> None:
    kept: set[str] = {"Star Garden - 05 [1080p].mkv", "Moon Garden - 05 [1080p].mkv", "Star Garden S02E05 [1080p].mkv"}
    hidden: set[str] = {
        "Star Garden S01E06 [1080p].mkv",
        "Star Garden S01E07 The Silent Winter Night [1080p].mkv",
        "Star Garden - 05 Extra [1080p].mkv",
    }
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [_stream(name) for name in sorted(kept | hidden)])
    assert {row.stream.file_name for row in ranked if row.identity.verdict is IdentityVerdict.MISMATCH} == hidden
    index, uncertain = suggestion(ranked, numbering=True)
    assert index is not None
    assert not uncertain
    shown: tuple[RankedCandidate, ...] = visible(ranked, index)
    assert {row.stream.file_name for row in shown} == kept
    assert ranked[index] in shown
    assert [row.conflict for row in shown].count(True) == 1


def test_visible_keeps_an_uncertain_suggestion_beside_mismatches() -> None:
    names: list[str] = ["Moon Garden - 05 [1080p].mkv", "Star Garden S01E06 [1080p].mkv"]
    ranked: tuple[RankedCandidate, ...] = _rank(_target(), [_stream(name) for name in names])
    index, uncertain = suggestion(ranked, numbering=True)
    assert index is not None
    assert uncertain
    assert visible(ranked, index) == (ranked[index],)


_SOLO_LEVELING_ECHOES: Final[tuple[str, ...]] = (
    "[ToonsHub] Solo Leveling S02E13 1080p CR WEB-DL AAC2.0 H.264 (Ore dake Level Up na Ken, Multi-Audio, Multi-Subs)",
    "[PacMan] Solo.Leveling.S02E13.1080p.CR.WEB-DL.AAC2.0.H.264",
    "[DKB] Solo Leveling - S02E13 [1080p][HEVC x265 10bit][Dual-Audio][Multi-Subs]",
    "[Erai-raws] Ore dake Level Up na Ken Season 2: Arise from the Shadow - 13 [1080p CR WEB-DL AVC AAC][MultiSub]",
)

_SOLO_LEVELING_UNSCOPED: Final[tuple[str, ...]] = (
    "[ASW] Solo Leveling - 13 [1080p HEVC x265 10Bit][AAC]",
    "[SubsPlease] Solo Leveling - 13 (1080p) [9C5E3F5C]",
    "[Erai-raws] Ore dake Level Up na Ken - 13 [1080p][Multiple Subtitle]",
    "[EMBER] Ore dake Level Up na Ken S02E13 [1080p] [HEVC WEBRip DDP] (Solo Leveling Season 2)",
)


def _solo_leveling_local_matches() -> list[StreamCandidate]:
    return [
        _stream(
            "[ToonsHub] Solo Leveling S02E01 1080p CR WEB-DL AAC2.0 H.264 (Multi-Subs).mkv",
            release="[ToonsHub] Solo Leveling S02E01 1080p CR WEB-DL AAC2.0 H.264 (Multi-Subs)",
        ),
        _stream(None, release="[PacMan] Solo.Leveling.S02E01.1080p.CR.WEB-DL.AAC2.0.H.264"),
        _stream(None, release="[DKB] Solo Leveling - S02E01 [1080p][HEVC x265 10bit][Dual-Audio][Multi-Subs]"),
        _stream(
            None,
            release="[Erai-raws] Ore dake Level Up na Ken Season 2: Arise from the Shadow - 01 "
            "[1080p CR WEB-DL AVC AAC][MultiSub][55FBD905]",
        ),
    ]


def test_rank_candidates_solo_leveling_s2e1_hides_season_marked_echoes_of_groups_numbering_from_one() -> None:
    matches: list[StreamCandidate] = _solo_leveling_local_matches()
    echoes: list[StreamCandidate] = [_stream(None, release=name) for name in _SOLO_LEVELING_ECHOES]
    unscoped: list[StreamCandidate] = [_stream(None, release=name) for name in _SOLO_LEVELING_UNSCOPED]
    ranked: tuple[RankedCandidate, ...] = _rank(_solo_leveling_s2e1(), [*echoes, *unscoped, *matches])
    by_stream: dict[StreamCandidate, RankedCandidate] = {row.stream: row for row in ranked}
    assert {by_stream[stream].identity.verdict for stream in matches} == {IdentityVerdict.MATCH}
    assert [(by_stream[stream].identity.verdict, by_stream[stream].identity.reason) for stream in echoes] == [
        (IdentityVerdict.MISMATCH, GROUP_NUMBERING_REASON)
    ] * len(echoes)
    assert [(by_stream[stream].conflict, by_stream[stream].confidence) for stream in echoes] == [(True, None)] * len(
        echoes
    )
    assert {by_stream[stream].identity.verdict for stream in unscoped} == {IdentityVerdict.INSUFFICIENT}
    index, uncertain = suggestion(ranked, numbering=True)
    assert index is not None
    assert not uncertain
    assert {row.stream for row in visible(ranked, index)} == {*matches, *unscoped}


def test_rank_candidates_echo_carrying_the_target_episode_title_stays_uncertain() -> None:
    titled: StreamCandidate = _stream(
        "Solo.Leveling.S02E13.You.Arent.E-Rank.Are.You.1080p.CR.WEB-DL.AAC2.0.H.264-ToonsHub.mkv",
        release="[ToonsHub] Solo Leveling S02E13 1080p CR WEB-DL AAC2.0 H.264 (Ore dake Level Up na Ken, Multi-Subs)",
    )
    ranked: tuple[RankedCandidate, ...] = _rank(_solo_leveling_s2e1(), [titled, *_solo_leveling_local_matches()])
    echo: RankedCandidate = next(row for row in ranked if row.stream == titled)
    assert echo.identity.verdict is IdentityVerdict.INSUFFICIENT
    assert echo in visible(ranked)


def test_rank_candidates_echo_without_a_local_match_of_its_group_stays_uncertain() -> None:
    echoes: list[StreamCandidate] = [_stream(None, release=name) for name in _SOLO_LEVELING_ECHOES]
    ranked: tuple[RankedCandidate, ...] = _rank(_solo_leveling_s2e1(), echoes)
    assert {row.identity.verdict for row in ranked} == {IdentityVerdict.INSUFFICIENT}
    assert len(visible(ranked)) == len(echoes)


def test_suggestion_slime_s4e23_stream_without_file_is_assessed_on_its_release_name() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S4, _fixture_mapping(_SLIME_S4), 23)
    streams: list[StreamCandidate] = _fixture_streams("torrentio__kitsu-49235-23.json")
    shincaps: StreamCandidate = streams[11]
    transport_stream: StreamCandidate = streams[37]
    assert (shincaps.file_name, shincaps.path) == (None, None)
    ranked: tuple[RankedCandidate, ...] = _rank(target, [transport_stream, shincaps])
    assert ranked[0].stream.info_hash == shincaps.info_hash
    assert (ranked[0].release_name_only, ranked[0].identity.verdict, ranked[0].conflict) == (
        True,
        IdentityVerdict.INSUFFICIENT,
        False,
    )
    assert (ranked[0].supported, ranked[0].traits.resolution) == (None, 1080)
    assert (ranked[1].supported, ranked[1].traits.resolution) == (False, 1080)
    assert suggestion(ranked, numbering=True) == (0, True)


def test_rank_candidates_slime_s1e4_suggests_main_series_and_never_matches_diaries_or_oad() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4)
    ranked: tuple[RankedCandidate, ...] = _rank(target, _fixture_streams("torrentio__kitsu-41024-4.json"))
    shown: set[str] = {Path(file).name for candidate in ranked for file in candidate.files}
    assert shown >= _SLIME_NEIGHBOR_FILES
    assert not any(candidate.ambiguous for candidate in ranked)
    assert all(
        candidate.identity.verdict is not IdentityVerdict.MATCH
        for candidate in ranked
        if candidate.stream.file_name in _SLIME_NEIGHBOR_FILES
    )
    index: int | None = suggestion(ranked, numbering=True)[0]
    assert index is not None
    suggested: RankedCandidate = ranked[index]
    assert suggested.identity.verdict is IdentityVerdict.MATCH
    assert suggested.stream.file_name not in _SLIME_NEIGHBOR_FILES


def _diaries_own_releases() -> list[StreamCandidate]:
    return [
        _stream(
            "[SubsPlease] Tensei Shitara Slime Datta Ken - Tensura Nikki - 04 (1080p) [ABCD1234].mkv",
            info_hash="a" * 40,
            release="[SubsPlease] Tensei Shitara Slime Datta Ken - Tensura Nikki - 04 (1080p) [ABCD1234]",
        ),
        _stream("The Slime Diaries - 04 [1080p].mkv", info_hash="b" * 40, release="The Slime Diaries - 04 [1080p]"),
    ]


@pytest.mark.parametrize("root_id", [_SLIME_S1, _SLIME_DIARIES])
def test_rank_candidates_diaries_target_rejects_main_series_and_keeps_own_releases(root_id: int) -> None:
    target: dict[str, object] = identity_target(_fixture_graph(root_id), _SLIME_DIARIES, _mapping({}), 4)
    own: list[StreamCandidate] = _diaries_own_releases()
    ranked: tuple[RankedCandidate, ...] = _rank(target, [*_fixture_streams("torrentio__kitsu-41024-4.json"), *own])
    matches: list[StreamCandidate] = [
        candidate.stream for candidate in ranked if candidate.identity.verdict is IdentityVerdict.MATCH
    ]
    assert sorted(matches, key=lambda stream: stream.info_hash) == own
    main: RankedCandidate = next(
        candidate
        for candidate in ranked
        if any(
            Path(file).name == "[Trix] Tensei Shitara Slime Datta Ken - S01E04 (BD 1080p AV1).mkv"
            for file in candidate.files
        )
    )
    assert main.identity.verdict is not IdentityVerdict.MATCH
    assert suggestion(ranked, numbering=True) == (0, True)


@pytest.mark.parametrize("root_id", [_SLIME_S1, _SLIME_DIARIES])
def test_rank_candidates_diaries_target_never_matches_a_shared_package_by_its_title(root_id: int) -> None:
    target: dict[str, object] = identity_target(_fixture_graph(root_id), _SLIME_DIARIES, _mapping({}), 4)
    package: list[StreamCandidate] = [
        stream
        for stream in _fixture_streams("torrentio__kitsu-41024-4.json")
        if stream.info_hash.startswith("21ff7425")
    ]
    assert all("Tensura Nikki" in stream.release for stream in package)
    batch: StreamCandidate = _stream(
        "Tensei Shitara Slime Datta Ken - 04.mkv",
        release="Tensei Shitara Slime Datta Ken S01 + The Slime Diaries [Batch]",
        path="Season 1/Tensei Shitara Slime Datta Ken - 04.mkv",
    )
    ranked: tuple[RankedCandidate, ...] = _rank(target, [*package, batch])
    assert [candidate.identity.verdict for candidate in ranked] == [IdentityVerdict.INSUFFICIENT] * 2


@pytest.mark.parametrize("case", _regression_cases(), ids=lambda case: case["cause"])
def test_identity_regression_case_keeps_expected_verdict(case: dict[str, Any]) -> None:
    assert classify(case["target"], case["candidate"]).verdict == case["expected_verdict"]
