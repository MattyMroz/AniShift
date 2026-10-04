from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

import pytest

from anishift.application.episode_identity import IdentityVerdict, classify
from anishift.application.episode_selection import (
    AniZipMapping,
    EntryGroup,
    EpisodeListing,
    FranchiseEntry,
    FranchiseGraph,
    ListedEpisode,
    ListedSpecial,
    RankedCandidate,
    StreamCandidate,
    episode_listing,
    franchise_traversal,
    franchise_view,
    identity_target,
    premiere_order,
    rank_candidates,
    release_facts,
    suggestion,
)
from anishift.services.catalog.anilist import parse_franchise_page
from anishift.services.catalog.anizip import parse_mapping
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
        info_hash="0" * 40,
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


def _ranked(target: dict[str, object], streams: list[StreamCandidate]) -> list[StreamCandidate]:
    return [candidate.stream for candidate in rank_candidates(target, streams)]


def _regression_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = _read(_REGRESSIONS)
    return cases


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
    assert starts == sorted(starts, key=lambda start: (not start[0], *start[1:]), reverse=True)
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
    ("stream", "expected"),
    [
        (_stream(None, name="Torrentio\n1080p"), 1080),
        (_stream("Star Garden - 05 [1080i].mkv"), 1080),
        (_stream("Star Garden - 05 [1440x1080].mkv"), 1080),
        (_stream("Star Garden - 05 [1440×1080].mkv"), 1080),
        (_stream(None, release="Star Garden - 05 [1920×1080]"), 1080),
        (_stream("Star Garden - 05 [4K].mkv"), 2160),
        (_stream("Star Garden - 05 [11080p].mkv"), None),
        (_stream("Star Garden - 05 [1080p].mkv", name="Torrentio\n2160p"), None),
        (_stream("Star Garden - 05.mkv", release="Star Garden 720p", name="Torrentio\n720p"), 720),
    ],
)
def test_release_facts_resolution_needs_one_declared_height(stream: StreamCandidate, expected: int | None) -> None:
    assert release_facts(stream).resolution == expected


def test_release_facts_language_platform_and_dub_declarations() -> None:
    assert release_facts(_stream(tags=("\U0001f1f5\U0001f1f1",))).polish
    assert release_facts(_stream("Star Garden - 05 [PL].mkv")).polish
    assert release_facts(_stream(release="Star_Garden_Polish_Subs")).polish
    assert not release_facts(_stream("Star Garden - 05 [Plus].mkv")).polish
    for declaration in ("Multi Subs", "MultiSub", "Multi-Subs", "Multiple Subtitle"):
        assert release_facts(_stream(release=f"Star Garden [{declaration}]")).multisub
    assert release_facts(_stream(tags=("Multi Subs",))).multisub
    assert release_facts(_stream(release="Star Garden 1080p NF WEB-DL")).platform == "Netflix"
    assert release_facts(_stream(release="[Group] Star Garden (Netflix)")).platform == "Netflix"
    assert release_facts(_stream(release="Star Garden [CR]")).platform == "Crunchyroll"
    assert release_facts(_stream(release="Star Garden NFO")).platform is None
    assert release_facts(_stream(tags=("NF",))).platform == "Netflix"
    assert release_facts(_stream(tags=("Netflix",))).platform == "Netflix"
    assert release_facts(_stream(tags=("CR",))).platform == "Crunchyroll"
    assert release_facts(_stream(tags=("crunchyroll",))).platform == "Crunchyroll"
    assert release_facts(_stream(tags=("NFO", "cr"))).platform is None
    assert release_facts(_stream(tags=("Dubbed",))).dub_only
    assert not release_facts(_stream(release="Star Garden [Dual Audio]", tags=("Dubbed",))).dub_only
    assert not release_facts(_stream(release="Star Garden Multi-Audio", tags=("Dubbed", "Multi Subs"))).dub_only


@pytest.mark.parametrize(
    ("file_name", "container", "supported"),
    [
        ("Star Garden - 05.mkv", ".mkv", True),
        ("Star Garden - 05.MP4", ".mp4", True),
        ("Star Garden - 05.avi", ".avi", False),
        ("Star Garden - 05.ts", ".ts", False),
        ("Star Garden - 05.mpegts", ".mpegts", False),
        ("Star Garden - 05.x", ".x", False),
        ("Star Garden - 05.123", ".123", False),
        ("Star Garden - 05 (TrueHD 5.1)", None, None),
        ("Star Garden - 05. Final", None, None),
        (".mkv", None, None),
        (None, None, None),
        ("Star Garden - 05", None, None),
    ],
)
def test_release_facts_container_support_leaves_unknown_containers_unpenalized(
    file_name: str | None, container: str | None, supported: bool | None
) -> None:
    facts = release_facts(_stream(file_name))
    assert (facts.container, facts.supported) == (container, supported)


def test_release_facts_container_is_read_from_the_file_name_never_the_release_or_path() -> None:
    facts = release_facts(_stream(None, release="Star Garden - 05 AAC 5.1", path="Star Garden/Star Garden - 05.avi"))
    assert (facts.container, facts.supported) == (None, None)


def test_rank_candidates_verdict_precedes_owner_preferences_and_keeps_streams() -> None:
    good: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    uncertain: StreamCandidate = _stream("Moon Garden - 05 [1080p].mkv", seeders=9999)
    bad: StreamCandidate = _stream("Star Garden - 05 [1080p].rar", tags=("\U0001f1f5\U0001f1f1",))
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), [bad, uncertain, good])
    assert [candidate.stream for candidate in ranked] == [good, uncertain, bad]
    assert [candidate.identity.verdict for candidate in ranked] == [
        IdentityVerdict.MATCH,
        IdentityVerdict.INSUFFICIENT,
        IdentityVerdict.MISMATCH,
    ]
    assert rank_candidates(_target(), []) == ()


def test_rank_candidates_context_conflicts_precede_release_preferences() -> None:
    good: StreamCandidate = _stream("Star Garden - 05 [720p].mkv")
    for context in ("Star Garden Saison 2", "Star Garden: Next Horizon", "극장판", "Part II"):
        bad: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", release=context, seeders=9999)
        assert _ranked(_target(), [bad, good])[0] is good


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
    assert _ranked(_target(), streams) == [
        streams[5],
        streams[6],
        streams[8],
        streams[4],
        streams[3],
        streams[7],
        streams[2],
        streams[1],
        streams[0],
    ]


def test_rank_candidates_owner_preferences_break_ties_in_order() -> None:
    base: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv")
    plain_720_polish: StreamCandidate = _stream("Star Garden - 05 [720p].mkv", tags=("\U0001f1f5\U0001f1f1",))
    polish: StreamCandidate = replace(base, tags=("\U0001f1f5\U0001f1f1",))
    multisub: StreamCandidate = replace(base, tags=("Multi Subs",))
    netflix: StreamCandidate = replace(base, release="Star Garden S01 1080p NF WEB-DL")
    dubbed: StreamCandidate = replace(base, tags=("Dubbed",))
    low: StreamCandidate = _stream("Star Garden - 05 [480p].mkv")
    streams: list[StreamCandidate] = [dubbed, low, plain_720_polish, base, netflix, multisub, polish]
    assert _ranked(_target(), streams) == [polish, multisub, netflix, base, plain_720_polish, low, dubbed]


@pytest.mark.parametrize("tag", ["NF", "Crunchyroll"])
def test_rank_candidates_platform_tag_breaks_a_tie_before_seeders(tag: str) -> None:
    base: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", seeders=900)
    tagged: StreamCandidate = _stream("Star Garden - 05 [1080p].mkv", tags=(tag,), seeders=1)
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), [base, tagged])
    assert [candidate.stream for candidate in ranked] == [tagged, base]
    assert ranked[0].facts.platform is not None


def test_rank_candidates_known_seeders_precede_unknown_and_ties_stay_stable() -> None:
    unknown: StreamCandidate = _stream()
    zero: StreamCandidate = _stream(seeders=0)
    two: StreamCandidate = _stream(seeders=2)
    assert _ranked(_target(), [unknown, zero, two]) == [two, zero, unknown]
    first: StreamCandidate = _stream(info_hash="1" * 40)
    second: StreamCandidate = _stream(info_hash="2" * 40)
    assert _ranked(_target(), [second, first]) == [second, first]


def test_rank_candidates_unsupported_container_follows_supported_and_unknown_is_not_penalized() -> None:
    avi: StreamCandidate = _stream("Moon Garden - 05 [1080p].avi", seeders=500)
    unknown: StreamCandidate = _stream(None, release="Star Garden - 05 [1080p]")
    mkv: StreamCandidate = _stream("Moon Garden - 05 [720p].mkv", seeders=900)
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), [avi, mkv, unknown])
    assert [candidate.stream for candidate in ranked] == [unknown, mkv, avi]
    assert {candidate.identity.verdict for candidate in ranked} == {IdentityVerdict.INSUFFICIENT}


def test_rank_candidates_same_hash_files_are_assessed_separately() -> None:
    ranked: tuple[RankedCandidate, ...] = rank_candidates(
        identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4),
        [
            stream
            for stream in _fixture_streams("torrentio__kitsu-41024-4.json")
            if stream.info_hash.startswith("21ff7425")
        ],
    )
    verdicts: dict[int | None, IdentityVerdict] = {
        candidate.stream.file_index: candidate.identity.verdict for candidate in ranked
    }
    assert verdicts == {3: IdentityVerdict.MATCH, 56: IdentityVerdict.INSUFFICIENT}


def test_suggestion_prefers_usable_match_then_usable_uncertain_and_never_mismatch() -> None:
    avi_match: StreamCandidate = _stream("Star Garden - 05 [1080p].avi")
    mkv_match: StreamCandidate = _stream("Star Garden - 05 [480p].mkv")
    uncertain: StreamCandidate = _stream("Moon Garden - 05 [1080p].mkv")
    mismatch: StreamCandidate = _stream("Star Garden - 05.rar")
    ranked: tuple[RankedCandidate, ...] = rank_candidates(_target(), [avi_match, uncertain, mkv_match])
    assert [candidate.stream for candidate in ranked] == [mkv_match, avi_match, uncertain]
    assert suggestion(ranked) == 0
    fallback: tuple[RankedCandidate, ...] = rank_candidates(_target(), [avi_match, mismatch, uncertain])
    assert [candidate.stream for candidate in fallback] == [avi_match, uncertain, mismatch]
    assert suggestion(fallback) == 1
    assert suggestion(rank_candidates(_target(), [avi_match, mismatch])) is None
    assert suggestion(rank_candidates(_target(), [mismatch])) is None
    assert suggestion(()) is None


def test_suggestion_slime_s4e23_stream_without_file_is_uncertain_and_may_be_suggested() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S4, _fixture_mapping(_SLIME_S4), 23)
    streams: list[StreamCandidate] = _fixture_streams("torrentio__kitsu-49235-23.json")
    shincaps: StreamCandidate = streams[11]
    transport_stream: StreamCandidate = streams[37]
    assert (shincaps.file_name, shincaps.path) == (None, None)
    ranked: tuple[RankedCandidate, ...] = rank_candidates(target, [transport_stream, shincaps])
    assert ranked[0].stream is shincaps
    assert (ranked[0].identity.verdict, ranked[0].identity.reason) == (
        IdentityVerdict.INSUFFICIENT,
        "No selected file.",
    )
    assert (ranked[0].facts.container, ranked[0].facts.supported, ranked[0].facts.resolution) == (None, None, 1080)
    assert (ranked[1].facts.container, ranked[1].facts.supported, ranked[1].facts.resolution) == (".ts", False, 1080)
    assert suggestion(ranked) == 0


def test_rank_candidates_slime_s1e4_suggests_main_series_and_never_matches_diaries_or_oad() -> None:
    target: dict[str, object] = identity_target(_fixture_graph(_SLIME_S1), _SLIME_S1, _fixture_mapping(_SLIME_S1), 4)
    ranked: tuple[RankedCandidate, ...] = rank_candidates(target, _fixture_streams("torrentio__kitsu-41024-4.json"))
    neighbors: list[RankedCandidate] = [
        candidate for candidate in ranked if candidate.stream.file_name in _SLIME_NEIGHBOR_FILES
    ]
    assert len(neighbors) == len(_SLIME_NEIGHBOR_FILES)
    assert all(candidate.identity.verdict is not IdentityVerdict.MATCH for candidate in neighbors)
    index: int | None = suggestion(ranked)
    assert index is not None
    suggested: RankedCandidate = ranked[index]
    assert suggested.identity.verdict is IdentityVerdict.MATCH
    assert suggested.stream.file_name == "[Trix] Tensei Shitara Slime Datta Ken - S01E04 (BD 1080p AV1).mkv"


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
    ranked: tuple[RankedCandidate, ...] = rank_candidates(
        target, [*_fixture_streams("torrentio__kitsu-41024-4.json"), *own]
    )
    matches: list[StreamCandidate] = [
        candidate.stream for candidate in ranked if candidate.identity.verdict is IdentityVerdict.MATCH
    ]
    assert matches == own
    main: RankedCandidate = next(
        candidate
        for candidate in ranked
        if candidate.stream.file_name == "[Trix] Tensei Shitara Slime Datta Ken - S01E04 (BD 1080p AV1).mkv"
    )
    assert main.identity.verdict is not IdentityVerdict.MATCH
    index: int | None = suggestion(ranked)
    assert index is not None
    assert ranked[index].stream in own


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
    ranked: tuple[RankedCandidate, ...] = rank_candidates(target, [*package, batch])
    assert [candidate.identity.verdict for candidate in ranked] == [IdentityVerdict.INSUFFICIENT] * 3


@pytest.mark.parametrize("case", _regression_cases(), ids=lambda case: case["cause"])
def test_identity_regression_case_keeps_expected_verdict(case: dict[str, Any]) -> None:
    assert classify(case["target"], case["candidate"]).verdict == case["expected_verdict"]
