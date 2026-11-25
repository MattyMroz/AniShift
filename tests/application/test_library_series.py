from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest
from test_acquisition import _S1, _episode_service, _slime_titles
from test_automation import _TIMEOUT_S, _completed_library, _owner, _real_service, _request, _serving
from test_episode_selection import _fixture_graph

from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    EpisodeAssignment,
    EpisodeChoice,
    LegacyScope,
    ReadyGroup,
    TorrentioReference,
    WatchState,
)
from anishift.application.control_views import LibrarySet, TitleSource
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import AniZipMapping, JsonObject, LibraryGraph, ListedEpisode
from anishift.application.intents import RequestOrigin
from anishift.application.library import LibrarySeries, library_series, name_series, series_title
from anishift.application.subscription_targets import SubscriptionRecord
from anishift.application.workflows import WorkflowTarget

_MOMENT: Final[str] = "2026-10-11T09:00:00+00:00"
_BLUE_BOX: Final[int] = 189123
_TOONSHUB: Final[str] = "Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264.MSubs-ToonsHub"
_JUDAS: Final[str] = "[Judas] Ao no Hako - S02E02"
_SLIME: Final[str] = "That Time I Got Reincarnated as a Slime"
_SLIME_S2: Final[int] = 108511
_SLIME_S3: Final[int] = 156822
_SLIME_S4: Final[int] = 182205
_SLIME_FILM: Final[int] = 182206
_SLIME_OAD: Final[int] = 106509
_DIARIES: Final[int] = 116741
_SOLO: Final[int] = 151807
_SOLO_S2: Final[int] = 176496

type _Named = dict[str, tuple[str | None, int | None, int | None]]


def _ready(set_id: str, stem: str) -> ReadyGroup:
    return ReadyGroup(
        set_id,
        f"moved-{set_id}",
        stem,
        ".",
        stem,
        WorkflowTarget.VIDEO,
        (f"ready/{stem}.mkv",),
        (),
        f"ready/{stem}.mkv",
    )


def _downloaded(
    set_id: str, anilist_id: int, number: int, *, subscription: str | None = None
) -> AcquisitionConfirmation:
    info_hash: str = f"{anilist_id:020}{number:020}"
    choice: EpisodeChoice = EpisodeChoice(
        anilist_id, number, TorrentioReference(info_hash), {}, IdentityVerdict.MATCH, "match"
    )
    assignment: EpisodeAssignment = EpisodeAssignment(
        f"admission-{set_id}",
        _MOMENT,
        AdmissionSource.MANUAL if subscription is None else AdmissionSource.SUBSCRIPTION,
        choice,
        group_id=set_id,
        subscription_id=subscription,
        attempt=None if subscription is None else 1,
    )
    return AcquisitionConfirmation(
        operation_id=f"operation-{set_id}",
        info_hash=info_hash,
        directory=f"tmp/.acquisition/{set_id}/data",
        required_files=(),
        state=AcquisitionState.COMPLETE,
        origin=RequestOrigin.USER if subscription is None else RequestOrigin.BACKGROUND,
        subscription_id=None,
        episode=str(number),
        updated_at=_MOMENT,
        assignments=(assignment,),
        selection_revision=1,
        applied_revision=1,
    )


def _legacy(stem: str, scope: LegacyScope) -> AcquisitionConfirmation:
    return AcquisitionConfirmation(
        operation_id=f"legacy-{stem}",
        info_hash="f" * 40,
        directory="",
        required_files=(f"ready/{stem}.mkv",),
        state=AcquisitionState.COMPLETE,
        origin=RequestOrigin.USER,
        subscription_id=None,
        episode="1",
        updated_at=_MOMENT,
        legacy_scope=scope,
    )


def _followed(anilist_id: int, title: str, mapping: AniZipMapping | None = None) -> SubscriptionRecord:
    return SubscriptionRecord(
        f"subscription-{anilist_id}",
        anilist_id,
        title,
        _MOMENT,
        0,
        kitsu_id=None if mapping is None else 1,
        mapping=mapping,
    )


def _set(record: ReadyGroup) -> LibrarySet:
    return LibrarySet(record.set_id, record.group_id, record.stem, record.target, record.main_result, (), True)


def _sets(state: WatchState, series: dict[int, LibrarySeries] | None = None) -> dict[str, LibrarySet]:
    sets: tuple[LibrarySet, ...] = tuple(_set(item) for item in state.ready_groups)
    return {item.name: item for item in name_series(sets, state, series or {})}


def _named(state: WatchState, series: dict[int, LibrarySeries] | None = None) -> _Named:
    return {name: (item.series, item.season, item.episode) for name, item in _sets(state, series).items()}


def _graph(*roots: int) -> LibraryGraph:
    nodes: dict[int, JsonObject] = {}
    queried: set[int] = set()
    for root in roots:
        graph = _fixture_graph(root)
        nodes.update(graph.nodes)
        queried |= graph.queried
    return LibraryGraph(nodes, frozenset(queried))


def _node(identifier: int, year: int | None, edges: list[tuple[str, int]] | None) -> JsonObject:
    node: dict[str, object] = {
        "id": identifier,
        "type": "ANIME",
        "format": "TV",
        "title": {"romaji": f"Entry {identifier}"},
        "startDate": {"year": year},
    }
    if edges is not None:
        node["relations"] = {
            "edges": [
                {"relationType": relation, "node": {"id": target, "type": "ANIME", "format": "TV"}}
                for relation, target in edges
            ]
        }
    return node


@pytest.mark.unit
def test_seasons_of_one_chain_share_one_series_whatever_their_titles() -> None:
    entries: tuple[int, ...] = (_SLIME_S2, _SLIME_S3, _SLIME_S4, _S1)

    found: dict[int, LibrarySeries] = library_series(_graph(_S1), entries)

    assert {item.series_id for item in found.values()} == {_S1}
    assert {item.title for item in found.values()} == {_SLIME}
    assert found[_SLIME_S4].entry_title == "That Time I Got Reincarnated as a Slime Season 4"


@pytest.mark.unit
def test_series_title_comes_from_the_earliest_season_entry() -> None:
    found: dict[int, LibrarySeries] = library_series(_graph(_SOLO), (_SOLO_S2,))

    assert found == {_SOLO_S2: LibrarySeries(_SOLO, "Solo Leveling", "Solo Leveling Season 2 -Arise from the Shadow-")}


@pytest.mark.unit
def test_chains_joined_by_a_shared_node_form_one_series() -> None:
    graph: LibraryGraph = LibraryGraph(
        {
            1: _node(1, 2020, [("SEQUEL", 2)]),
            2: _node(2, None, None),
            3: _node(3, 2023, [("PREQUEL", 2)]),
            4: _node(4, 2019, []),
        },
        frozenset({1, 3, 4}),
    )

    found: dict[int, LibrarySeries] = library_series(graph, (3, 1, 4))

    assert {key: item.series_id for key, item in found.items()} == {3: 1, 1: 1, 4: 4}
    assert found[3].title == "Entry 1"


@pytest.mark.unit
def test_a_film_in_the_chain_joins_its_series() -> None:
    found: dict[int, LibrarySeries] = library_series(_graph(_S1, _DIARIES, _SLIME_OAD), (_SLIME_FILM, _DIARIES))

    assert found[_SLIME_FILM].series_id == _S1
    assert found[_SLIME_FILM].title == _SLIME
    assert found[_DIARIES].series_id == _DIARIES


@pytest.mark.unit
def test_entry_missing_from_the_graph_gets_no_series() -> None:
    assert library_series(_graph(_S1), (999,)) == {}


@pytest.mark.unit
def test_downloaded_set_carries_its_entry_series_and_key_source() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("third", _SLIME_S3, 5),),
        ready_groups=(_ready("third", "[SubsPlease] Tensura S3 - 05 [1080p]"),),
    )

    named: LibrarySet = _sets(state, library_series(_graph(_S1), (_SLIME_S3,)))["[SubsPlease] Tensura S3 - 05 [1080p]"]

    assert (named.anilist_id, named.series_id, named.title_source) == (_SLIME_S3, _S1, TitleSource.KEY)
    assert (named.series, named.season, named.episode) == (_SLIME, 3, 5)


@pytest.mark.unit
def test_set_of_an_unknown_series_keeps_its_entry_and_file_label() -> None:
    stem: str = "[Erai-raws] Mushoku Tensei III - Isekai Ittara Honki Dasu - 14 [1080p]"
    state: WatchState = WatchState(
        acquisitions=(_downloaded("mushoku", 178789, 14),), ready_groups=(_ready("mushoku", stem),)
    )

    named: LibrarySet = _sets(state)[stem]

    assert (named.anilist_id, named.series_id, named.title_source) == (178789, None, TitleSource.KEY)
    assert (named.series, named.season, named.episode) == (None, None, None)


@pytest.mark.unit
def test_hand_added_set_stays_with_name_source() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("other", _BLUE_BOX, 1),),
        ready_groups=(_ready("film", "Some.Cartoon.1999.1080p.BluRay"),),
        subscriptions=(_followed(_BLUE_BOX, "Blue Box Season 2"),),
    )

    named: LibrarySet = _sets(state, {_BLUE_BOX: LibrarySeries(1, "Blue Box", "Blue Box Season 2")})[
        "Some.Cartoon.1999.1080p.BluRay"
    ]

    assert (named.anilist_id, named.series_id, named.title_source) == (None, None, TitleSource.NAME)
    assert (named.series, named.season, named.episode) == (None, None, None)


@pytest.mark.unit
def test_name_series_gives_releases_of_different_groups_the_series_and_catalogue_episode() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("toonshub", _BLUE_BOX, 1), _downloaded("judas", _BLUE_BOX, 2, subscription="blue")),
        ready_groups=(_ready("toonshub", _TOONSHUB), _ready("judas", _JUDAS)),
        subscriptions=(_followed(_BLUE_BOX, "Blue Box Season 2"),),
    )
    series: dict[int, LibrarySeries] = {_BLUE_BOX: LibrarySeries(1, "Blue Box", "Blue Box Season 2")}

    assert _named(state, series) == {_TOONSHUB: ("Blue Box", 2, 1), _JUDAS: ("Blue Box", 2, 2)}


@pytest.mark.unit
def test_name_series_numbers_the_first_entry_of_a_series_as_season_one() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("first", 186497, 14),),
        ready_groups=(_ready("first", "The.Ramparts.of.Ice.S01E14.Bombshell.1080p.NF.WEB-DL"),),
    )
    series: dict[int, LibrarySeries] = {186497: LibrarySeries(186497, "The Ramparts of Ice", "The Ramparts of Ice")}

    assert _named(state, series) == {
        "The.Ramparts.of.Ice.S01E14.Bombshell.1080p.NF.WEB-DL": ("The Ramparts of Ice", 1, 14)
    }


@pytest.mark.unit
def test_name_series_leaves_the_season_unknown_for_a_later_entry_whose_title_names_none() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("later", 999, 3),),
        ready_groups=(_ready("later", "[Grp] Later Story - 03 [1080p]"),),
    )
    series: dict[int, LibrarySeries] = {999: LibrarySeries(1, "First Story", "Later Story")}

    assert _named(state, series) == {"[Grp] Later Story - 03 [1080p]": ("First Story", None, None)}


@pytest.mark.unit
def test_name_series_takes_the_season_from_the_subscription_mapping_when_the_title_names_none() -> None:
    mapping: AniZipMapping = AniZipMapping(1, "TV", 4, (ListedEpisode(3, season=1, episode=3),), (), None, {})
    state: WatchState = WatchState(
        acquisitions=(_downloaded("explorer", 169581, 3),),
        ready_groups=(_ready("explorer", "[Erai-raws] Magical Explorer - 03 [1080p]"),),
        subscriptions=(_followed(169581, "Magical Explorer", mapping),),
    )
    series: dict[int, LibrarySeries] = {169581: LibrarySeries(169581, "Magical Explorer", "Magical Explorer")}

    assert set(_named(state, series).values()) == {("Magical Explorer", 1, 3)}


@pytest.mark.unit
def test_name_series_links_a_legacy_order_through_its_files_and_keeps_an_unknown_episode_from_the_file() -> None:
    stem: str = "Overgeared.S01E01.Legendary.Class.1080p.CR.WEB-DL"
    state: WatchState = WatchState(
        acquisitions=(_legacy(stem, LegacyScope(212888, None)),),
        ready_groups=(_ready("overgeared", stem),),
        subscriptions=(_followed(212888, "Overgeared"),),
    )
    series: dict[int, LibrarySeries] = {212888: LibrarySeries(212888, "Overgeared", "Overgeared")}

    assert _named(state, series) == {stem: ("Overgeared", None, None)}
    assert _sets(state, series)[stem].anilist_id == 212888


@pytest.mark.unit
@pytest.mark.parametrize(
    ("title", "series"),
    [
        ("Blue Box Season 2", "Blue Box"),
        ("Solo Leveling Season 2 -Arise from the Shadow-", "Solo Leveling"),
        ("SPY x FAMILY Part 2", "SPY x FAMILY"),
        ("Hunter x Hunter (2011)", "Hunter x Hunter"),
        ("Ao no Hako 2nd Season", "Ao no Hako"),
        ("Overgeared", "Overgeared"),
        ("Nia Liston: The Merciless Maiden", "Nia Liston: The Merciless Maiden"),
        ("Mushoku Tensei: Jobless Reincarnation Season 2", "Mushoku Tensei: Jobless Reincarnation"),
        ("Re:ZERO -Starting Life in Another World- Season 3", "Re:ZERO -Starting Life in Another World-"),
        ("Futari Solo Camp - Season 2", "Futari Solo Camp"),
    ],
)
def test_series_title_keeps_the_subtitle_and_drops_the_season_part_and_year(title: str, series: str) -> None:
    assert series_title(title) == series


@pytest.mark.integration
def test_owner_reads_every_library_series_in_one_batch_once(tmp_path: Path) -> None:
    _, store, state = _completed_library(tmp_path, ("01", "02"))
    store.save(
        replace(
            state,
            acquisitions=(_downloaded("set-01", _S1, 4), _downloaded("set-02", _DIARIES, 2)),
            subscriptions=(_followed(_SLIME_OAD, "That Time I Got Reincarnated as a Slime OAD"),),
        )
    )
    titles = _slime_titles()
    service = _real_service(tmp_path, acquisition=_episode_service(tmp_path, titles))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        rows: list[dict[str, object]] = _named_rows(owner, 2)
        details: object = owner.handle(_request("library_details", {"set_id": "set-01"})).result
        owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert [(row["series"], row["series_id"]) for row in rows] == [(_SLIME, _S1), ("The Slime Diaries", _DIARIES)]
    assert isinstance(details, dict)
    assert details["series"] == _SLIME
    assert titles.library_reads == [sorted((_S1, _DIARIES, _SLIME_OAD))]
    assert titles.franchised == []


@pytest.mark.integration
def test_snapshot_library_rows_carry_entry_series_and_source(tmp_path: Path) -> None:
    _, store, state = _completed_library(tmp_path, ("01", "02"))
    store.save(replace(state, acquisitions=(_downloaded("set-01", _S1, 4),)))
    service = _real_service(tmp_path, acquisition=_episode_service(tmp_path, _slime_titles()))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        rows: list[dict[str, object]] = _named_rows(owner, 1)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert [(row["anilist_id"], row["series_id"], row["title_source"]) for row in rows] == [
        (_S1, _S1, "key"),
        (None, None, "name"),
    ]


def _named_rows(owner: AutomationOwner, count: int) -> list[dict[str, object]]:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        rows: object = owner.handle(_request("status")).result["library"]
        if isinstance(rows, list) and sum(row.get("series") is not None for row in rows) == count:
            return [dict(row) for row in rows]
        time.sleep(0.01)
    pytest.fail("The owner did not name the downloaded sets")
