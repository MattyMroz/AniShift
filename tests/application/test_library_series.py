from __future__ import annotations

import threading
import time
from collections.abc import Collection, Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Final, cast

import pytest
from PIL import Image
from test_acquisition import _S1, _episode_service, _slime_titles, _TitleCatalog
from test_automation import (
    _INSTANCE,
    _TIMEOUT_S,
    _completed_library,
    _owner,
    _real_service,
    _request,
    _serving,
)
from test_episode_selection import _fixture_graph

from anishift.application.acquisition import AcquisitionService
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
from anishift.application.library import (
    LibrarySeries,
    episode_numbering,
    hand_titles,
    library_entries,
    library_series,
    name_series,
    recognize,
    series_title,
)
from anishift.application.subscription_targets import SubscriptionRecord
from anishift.application.workflows import WorkflowTarget
from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.local_control import ControlResponse
from anishift.services.catalog import TitleCandidate, TitleCatalogError, TitleStatus
from anishift.services.http_requests import RequestControl

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


def _sets(
    state: WatchState,
    series: dict[int, LibrarySeries] | None = None,
    recognized: dict[tuple[str, int], int | None] | None = None,
) -> dict[str, LibrarySet]:
    sets: tuple[LibrarySet, ...] = tuple(_set(item) for item in state.ready_groups)
    return {item.name: item for item in name_series(sets, state, series or {}, recognized or {})}


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
def test_library_entries_include_downloads_still_in_progress() -> None:
    state: WatchState = WatchState(
        acquisitions=(
            replace(_downloaded("set-a", _BLUE_BOX, 2), state=AcquisitionState.ACCEPTED),
            _legacy("Solo - 01", LegacyScope(_SOLO, 1)),
        )
    )

    assert library_entries(state) == {_BLUE_BOX, _SOLO}


@pytest.mark.unit
def test_downloaded_set_carries_its_entry_series_and_key_source() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("third", _SLIME_S3, 5),),
        ready_groups=(_ready("third", "[SubsPlease] Tensura S3 - 05 [1080p]"),),
    )

    named: LibrarySet = _sets(state, library_series(_graph(_S1), (_SLIME_S3,)))["[SubsPlease] Tensura S3 - 05 [1080p]"]

    assert (named.anilist_id, named.entry_title, named.title_source) == (
        _SLIME_S3,
        "That Time I Got Reincarnated as a Slime Season 3",
        TitleSource.KEY,
    )
    assert (named.series, named.season, named.episode) == (_SLIME, 3, 5)


@pytest.mark.unit
def test_set_of_an_unknown_series_keeps_its_entry_and_file_label() -> None:
    stem: str = "[Erai-raws] Mushoku Tensei III - Isekai Ittara Honki Dasu - 14 [1080p]"
    state: WatchState = WatchState(
        acquisitions=(_downloaded("mushoku", 178789, 14),), ready_groups=(_ready("mushoku", stem),)
    )

    named: LibrarySet = _sets(state)[stem]

    assert (named.anilist_id, named.entry_title, named.title_source) == (178789, None, TitleSource.KEY)
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

    assert (named.anilist_id, named.entry_title, named.title_source) == (None, None, TitleSource.NAME)
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
def test_name_series_numbers_a_split_cour_episode_like_its_file_name() -> None:
    mapping: AniZipMapping = AniZipMapping(1, "TV", 24, (ListedEpisode(13, season=2, episode=1),), (), None, {})
    state: WatchState = WatchState(
        acquisitions=(_downloaded("kaiju", 178754, 13),),
        ready_groups=(_ready("kaiju", "Kaiju No. 8 - S02E01 - Fear"),),
        subscriptions=(_followed(178754, "Kaiju No. 8", mapping),),
    )

    series: dict[int, LibrarySeries] = {178754: LibrarySeries(178754, "Kaiju No. 8", "Kaiju No. 8")}

    assert _named(state, series) == {"Kaiju No. 8 - S02E01 - Fear": ("Kaiju No. 8", 2, 1)}


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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("listed", "title", "film", "expected"),
    [
        (ListedEpisode(13, season=1, episode=13), "Blue Box", False, (1, 13)),
        (ListedEpisode(1, season=2, episode=1), "Blue Box Season 2", False, (2, 1)),
        (ListedEpisode(13, season=2, episode=1), "Kaiju No. 8", False, (2, 1)),
        (ListedEpisode(2, season=0, episode=2), "Bocchi the Rock!", False, (0, 2)),
        (ListedEpisode(4), "Ao no Hako 2nd Season", False, (2, 4)),
        (ListedEpisode(4, season=2), "Overgeared", False, (1, 4)),
        (ListedEpisode(1, season=1, episode=1), "Your Name.", True, None),
    ],
)
def test_episode_numbering_prefers_the_catalogue_pair_then_the_title_season(
    listed: ListedEpisode, title: str, film: bool, expected: tuple[int, int] | None
) -> None:
    assert episode_numbering(listed, title, film=film) == expected


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
    assert [(row["series"], row["entry_title"]) for row in rows] == [
        (_SLIME, _SLIME),
        ("The Slime Diaries", "The Slime Diaries"),
    ]
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
    assert [(row["anilist_id"], row["entry_title"], row["title_source"]) for row in rows] == [
        (_S1, _SLIME, "key"),
        (None, None, "name"),
    ]


def _candidate(anilist_id: int, romaji: str, english: str | None = None, *, episodes: int = 12) -> TitleCandidate:
    return TitleCandidate(anilist_id, romaji, english, None, (), None, None, "TV", episodes, TitleStatus.FINISHED, ())


@pytest.mark.unit
def test_one_alias_with_matching_title_and_season_is_recognized() -> None:
    candidates: tuple[TitleCandidate, ...] = (
        _candidate(1, "Ao no Hako", "Blue Box"),
        _candidate(2, "Ao no Hako 2nd Season", "Blue Box Season 2"),
    )

    assert recognize(candidates, "Blue Box", 2, 3) == 2
    assert recognize(candidates, "BLUE  box", 1, 3) == 1


@pytest.mark.unit
def test_a_remake_with_a_year_keeps_a_yearless_name_from_name() -> None:
    candidates: tuple[TitleCandidate, ...] = (
        _candidate(136, "HUNTER×HUNTER", "Hunter x Hunter"),
        _candidate(11061, "HUNTER×HUNTER (2011)", "Hunter x Hunter (2011)"),
    )

    assert recognize(candidates, "Hunter x Hunter", 1, 5) is None
    assert recognize(candidates[:1], "Hunter x Hunter", 1, 5) == 136


@pytest.mark.unit
def test_a_name_with_the_remake_year_recognizes_the_remake() -> None:
    candidates: tuple[TitleCandidate, ...] = (
        _candidate(136, "HUNTER×HUNTER", "Hunter x Hunter"),
        _candidate(11061, "HUNTER×HUNTER (2011)", "Hunter x Hunter (2011)"),
    )

    assert recognize(candidates, "Hunter x Hunter (2011)", 1, 5) == 11061


@pytest.mark.unit
def test_an_episode_beyond_the_entry_count_stays_from_name() -> None:
    candidates: tuple[TitleCandidate, ...] = (
        _candidate(113415, "Jujutsu Kaisen", episodes=24),
        _candidate(145064, "Jujutsu Kaisen 2nd Season", episodes=23),
    )

    assert recognize(candidates, "Jujutsu Kaisen", 1, 25) is None
    assert recognize(candidates, "Jujutsu Kaisen", 1, 24) == 113415


@pytest.mark.unit
def test_hand_titles_keep_the_highest_episode_of_each_title() -> None:
    state: WatchState = WatchState(
        ready_groups=(_ready("a", "[Grp] Jujutsu Kaisen - 25"), _ready("b", "[Grp] Jujutsu Kaisen - 03"))
    )

    titles = hand_titles(tuple(_set(item) for item in state.ready_groups), state)

    assert titles == {("jujutsu kaisen", 1): ("Jujutsu Kaisen", 25)}


@pytest.mark.unit
def test_two_matching_candidates_stay_from_name() -> None:
    candidates: tuple[TitleCandidate, ...] = (_candidate(1, "Blue Box"), _candidate(2, "Blue Box", "Blue Box"))

    assert recognize(candidates, "Blue Box", 1, 3) is None


@pytest.mark.unit
def test_matching_title_with_another_season_stays_from_name() -> None:
    assert recognize((_candidate(2, "Ao no Hako 2nd Season", "Blue Box Season 2"),), "Blue Box", 3, 3) is None


@pytest.mark.unit
def test_seasonless_name_matches_only_a_first_season() -> None:
    candidates: tuple[TitleCandidate, ...] = (_candidate(2, "Ao no Hako 2nd Season", "Blue Box Season 2"),)

    assert recognize(candidates, "Blue Box", 1, 3) is None
    assert recognize((_candidate(1, "Ao no Hako", "Blue Box"),), "Blue Box", 1, 3) == 1


@pytest.mark.unit
def test_recognized_hand_set_takes_its_entry_and_series() -> None:
    stem: str = "[Grp] Ao no Hako S2 - 03 [1080p]"
    state: WatchState = WatchState(ready_groups=(_ready("hand", stem),))
    series: dict[int, LibrarySeries] = {2: LibrarySeries(1, "Blue Box", "Blue Box Season 2")}

    named: LibrarySet = _sets(state, series, {("ao no hako", 2): 2})[stem]
    unknown: LibrarySet = _sets(state, series, {("ao no hako", 2): None})[stem]

    assert (named.anilist_id, named.entry_title, named.title_source) == (2, "Blue Box Season 2", TitleSource.RECOGNIZED)
    assert (named.series, named.season, named.episode) == ("Blue Box", 2, 3)
    assert (unknown.anilist_id, unknown.title_source) == (None, TitleSource.NAME)


class _Searching(_TitleCatalog):
    def __init__(self, *, refuse: bool = False) -> None:
        super().__init__(
            candidates=(_candidate(_S1, "Tensei Shitara Slime Datta Ken", _SLIME),),
            graphs=_slime_titles().graphs,
        )
        self.refuse: bool = refuse
        self.batches: list[tuple[str, ...]] = []

    def search_many(self, texts: Collection[str], *, limit: int = 7) -> dict[str, tuple[TitleCandidate, ...]]:
        self.batches.append(tuple(texts))
        if self.refuse:
            raise TitleCatalogError(
                context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="AniList rejected the request")
            )
        return super().search_many(texts, limit=limit)


_HAND: Final[tuple[str, ...]] = (
    "[Grp] Tensei Shitara Slime Datta Ken - 05 [1080p]",
    "[Other] Tensei.Shitara.Slime.Datta.Ken.S01E06.1080p",
    "[Grp] Unknown Show - 01 [1080p]",
)


def _hand_owner(tmp_path: Path, titles: _Searching, control: RequestControl | None = None) -> AutomationOwner:
    _, store, _state = _completed_library(tmp_path, _HAND)
    owner: AutomationOwner = _owner(
        _real_service(tmp_path, acquisition=_episode_service(tmp_path, titles, request_control=control)), store
    )
    owner._recognition_retry_s = 0.0
    return owner


class _CoolingControl:
    def __init__(self, cooling: int) -> None:
        self.cooling_answers: int = cooling
        self.asked: int = 0

    def scope(self, reason: str, limits: Mapping[str, int]) -> AbstractContextManager[None]:
        return nullcontext()

    def cooling(self, provider: str) -> bool:
        assert provider == "anilist"
        self.asked += 1
        return self.asked <= self.cooling_answers

    def blocked_until(self, providers: tuple[str, ...]) -> float:
        return 0.0

    def counts(self) -> list[dict[str, object]]:
        return []

    def restore(self, *args: object, **kwargs: object) -> None:
        return

    def close(self) -> None:
        return


class _ThreadSearching(_Searching):
    def __init__(self, control: _CoolingControl, *, refuse_first: bool = False) -> None:
        super().__init__()
        self.control: _CoolingControl = control
        self.refuse_first: bool = refuse_first
        self.threads: list[str] = []
        self.cooling_seen: list[int] = []

    def search_many(self, texts: Collection[str], *, limit: int = 7) -> dict[str, tuple[TitleCandidate, ...]]:
        self.threads.append(threading.current_thread().name)
        self.cooling_seen.append(self.control.asked)
        if self.refuse_first:
            self.refuse_first = False
            self.control.cooling_answers = self.control.asked + 1
            raise TitleCatalogError(context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="429"))
        return super().search_many(texts, limit=limit)


@pytest.mark.integration
def test_recognition_runs_on_its_own_thread_after_the_anilist_cooldown(tmp_path: Path) -> None:
    control: _CoolingControl = _CoolingControl(cooling=3)
    titles: _ThreadSearching = _ThreadSearching(control)
    owner: AutomationOwner = _hand_owner(tmp_path, titles, cast("RequestControl", control))
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        _until_recognized(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert set(titles.threads) == {"anishift-owner-recognition"}
    assert titles.cooling_seen[0] > 3


@pytest.mark.integration
def test_recognition_waiting_for_anilist_never_shows_the_automation_pausing(tmp_path: Path) -> None:
    control: _CoolingControl = _CoolingControl(cooling=10**9)
    owner: AutomationOwner = _hand_owner(tmp_path, _ThreadSearching(control), cast("RequestControl", control))
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        deadline: float = time.monotonic() + _TIMEOUT_S
        while control.asked < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        status: ControlResponse = owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert control.asked >= 2
    assert status.result["pausing"] is False
    assert not thread.is_alive()


@pytest.mark.integration
def test_search_refused_in_a_cooldown_is_retried_after_it(tmp_path: Path) -> None:
    control: _CoolingControl = _CoolingControl(cooling=0)
    titles: _ThreadSearching = _ThreadSearching(control, refuse_first=True)
    owner: AutomationOwner = _hand_owner(tmp_path, titles, cast("RequestControl", control))
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        _until_recognized(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert len(titles.threads) == 2
    assert owner._recognized[("tensei shitara slime datta ken", 1)] == _S1


def _until_recognized(owner: AutomationOwner, count: int) -> None:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while len(owner._recognized) < count and time.monotonic() < deadline:
        owner.handle(_request("status"))
        time.sleep(0.01)
    assert len(owner._recognized) == count


@pytest.mark.integration
def test_owner_searches_all_hand_added_titles_in_one_batch_once(tmp_path: Path) -> None:
    titles: _Searching = _Searching()
    owner: AutomationOwner = _hand_owner(tmp_path, titles)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        _until_recognized(owner, 2)
        assert owner.handle(_request("library_refresh")).ok
        owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert [sorted(batch) for batch in titles.batches] == [["Tensei Shitara Slime Datta Ken", "Unknown Show"]]


class _OneAtATime(_Searching):
    def search_many(self, texts: Collection[str], *, limit: int = 7) -> dict[str, tuple[TitleCandidate, ...]]:
        first: str = next(iter(texts))
        return {first: super().search_many((first,), limit=limit)[first]}


@pytest.mark.integration
def test_title_left_out_of_a_search_is_not_recorded_and_is_searched_in_the_next_one(tmp_path: Path) -> None:
    titles: _OneAtATime = _OneAtATime()
    owner: AutomationOwner = _hand_owner(tmp_path, titles)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        _until_recognized(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert sorted(titles.batches) == [("Tensei Shitara Slime Datta Ken",), ("Unknown Show",)]
    assert owner._recognized == {("tensei shitara slime datta ken", 1): _S1, ("unknown show", 1): None}


@pytest.mark.integration
def test_failed_search_leaves_the_title_from_name_and_is_searched_again(tmp_path: Path) -> None:
    titles: _Searching = _Searching(refuse=True)
    owner: AutomationOwner = _hand_owner(tmp_path, titles)
    owner._recognition_retry_s = _TIMEOUT_S * 10
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        deadline: float = time.monotonic() + _TIMEOUT_S
        while not owner._on_owner(lambda: bool(titles.batches) and not owner._recognizing):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        rows: object = owner.handle(_request("status")).result["library"]
        assert owner._recognized == {}
        titles.refuse = False
        owner._on_owner(lambda: setattr(owner, "_recognition_retry_at", 0.0))
        _until_recognized(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert isinstance(rows, list)
    assert {row["title_source"] for row in rows} == {"name"}
    assert len(titles.batches) == 2
    assert owner._recognized[("tensei shitara slime datta ken", 1)] == _S1


@pytest.mark.integration
def test_recognition_survives_a_restart_without_searching_again(tmp_path: Path) -> None:
    titles: _Searching = _Searching()
    owner: AutomationOwner = _hand_owner(tmp_path, titles)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        _until_recognized(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    restarted: AutomationOwner = _owner(owner._service, owner._store)
    assert restarted._recognized == owner._recognized
    thread = _serving(restarted)
    try:
        rows: object = restarted.handle(_request("library_refresh")).result["sets"]
    finally:
        restarted.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert isinstance(rows, list)
    assert sorted(str(row["title_source"]) for row in rows) == ["name", "recognized", "recognized"]
    assert len(titles.batches) == 1


@pytest.mark.integration
def test_recognized_set_joins_its_series(tmp_path: Path) -> None:
    titles: _Searching = _Searching()
    owner: AutomationOwner = _hand_owner(tmp_path, titles)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        rows: list[dict[str, object]] = _named_rows(owner, 2)
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    named: list[tuple[object, ...]] = [
        (row["title_source"], row["anilist_id"], row["entry_title"], row["series"], row["season"], row["episode"])
        for row in rows
    ]
    assert sorted(named, key=str) == sorted(
        [
            ("recognized", _S1, _SLIME, _SLIME, 1, 5),
            ("recognized", _S1, _SLIME, _SLIME, 1, 6),
            ("name", None, None, None, None, None),
        ],
        key=str,
    )
    assert titles.library_reads == [[_S1]]


_COVER_A: Final[str] = "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx101280.jpg"
_COVER_B: Final[str] = "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx106509.jpg"


def _png() -> bytes:
    buffer: BytesIO = BytesIO()
    Image.new("RGB", (46, 64), (20, 90, 200)).save(buffer, "PNG")
    return buffer.getvalue()


def _cover_owner(tmp_path: Path, titles: _TitleCatalog) -> tuple[AutomationOwner, Path]:
    _, store, state = _completed_library(tmp_path)
    store.save(
        replace(
            state,
            acquisitions=(_downloaded("set-01", _S1, 4),),
            subscriptions=(_followed(_SLIME_OAD, "That Time I Got Reincarnated as a Slime OAD"),),
        )
    )
    titles.covers = {_S1: _COVER_A, _SLIME_OAD: _COVER_B}
    titles.files = {_COVER_A: _png(), _COVER_B: _png()}
    covers: Path = tmp_path / "config" / "covers"
    owner: AutomationOwner = AutomationOwner(
        _real_service(tmp_path, acquisition=_episode_service(tmp_path, titles)),
        store,
        instance_id=_INSTANCE,
        clock=lambda: datetime(2026, 10, 11, 9, 0, tzinfo=UTC),
        cover_directory=covers,
    )
    return owner, covers


def _cached(owner: AutomationOwner, expected: list[int]) -> list[int]:
    deadline: float = time.monotonic() + _TIMEOUT_S
    covers: object = None
    while time.monotonic() < deadline:
        covers = owner.handle(_request("status")).result["covers"]
        if covers == expected:
            break
        time.sleep(0.01)
    assert isinstance(covers, list)
    return covers


@pytest.mark.integration
def test_owner_fetches_only_missing_covers_once(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    owner, covers = _cover_owner(tmp_path, titles)
    covers.mkdir(parents=True)
    (covers / f"{_SLIME_OAD}.jpg").write_bytes(_png())
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        cached: list[int] = _cached(owner, [_S1, _SLIME_OAD])
        assert owner.handle(_request("library_refresh")).ok
        owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert cached == [_S1, _SLIME_OAD]
    assert titles.cover_reads == [[_S1]]
    assert titles.downloads == [_COVER_A]
    assert sorted(item.name for item in covers.iterdir()) == [f"{_S1}.jpg", f"{_SLIME_OAD}.jpg"]


@pytest.mark.integration
def test_owner_reads_existing_covers_at_start(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    owner, covers = _cover_owner(tmp_path, titles)
    covers.mkdir(parents=True)
    for anilist_id in (_S1, _SLIME_OAD):
        (covers / f"{anilist_id}.jpg").write_bytes(_png())
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        cached: list[int] = _cached(owner, [_S1, _SLIME_OAD])
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert cached == [_S1, _SLIME_OAD]
    assert titles.cover_reads == []
    assert titles.downloads == []


@pytest.mark.integration
def test_snapshot_lists_cached_covers(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    titles.files = {}
    owner, covers = _cover_owner(tmp_path, titles)
    titles.files = {_COVER_A: _png(), _COVER_B: b"<html>broken</html>"}
    thread: threading.Thread = _serving(owner)
    try:
        before: object = owner.handle(_request("status")).result["covers"]
        assert owner.handle(_request("library_refresh")).ok
        cached: list[int] = _cached(owner, [_S1])
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert before == []
    assert cached == [_S1]
    assert [item.name for item in covers.iterdir()] == [f"{_S1}.jpg"]


@pytest.mark.integration
def test_searched_titles_get_covers_from_the_search_addresses(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    owner, covers = _cover_owner(tmp_path, titles)
    covers.mkdir(parents=True)
    for anilist_id in (_S1, _SLIME_OAD):
        (covers / f"{anilist_id}.jpg").write_bytes(_png())
    searched: str = "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx7.jpg"
    titles.candidates = (
        TitleCandidate(
            7, "Searched", None, None, (), None, None, None, None, TitleStatus.UNKNOWN, (), cover_url=searched
        ),
    )
    titles.files = {searched: _png()}
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("acquisition", {"operation": "titles", "query": "searched"})).ok
        cached: list[int] = _cached(owner, [7, _S1, _SLIME_OAD])
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert cached == [7, _S1, _SLIME_OAD]
    assert titles.downloads == [searched]
    assert [7] not in titles.cover_reads


class _SlowTitles(_TitleCatalog):
    def __init__(self) -> None:
        super().__init__(graphs=_slime_titles().graphs)
        self.release: threading.Event = threading.Event()

    def cover_urls(self, anilist_ids: Collection[int]) -> dict[int, str]:
        assert self.release.wait(_TIMEOUT_S)
        return super().cover_urls(anilist_ids)


@pytest.mark.integration
def test_covers_on_disk_show_before_anilist_answers_for_the_missing_ones(tmp_path: Path) -> None:
    titles: _SlowTitles = _SlowTitles()
    owner, covers = _cover_owner(tmp_path, titles)
    covers.mkdir(parents=True)
    (covers / f"{_S1}.jpg").write_bytes(_png())
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        early: list[int] = _cached(owner, [_S1])
        titles.release.set()
        late: list[int] = _cached(owner, [_S1, _SLIME_OAD])
    finally:
        titles.release.set()
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert early == [_S1]
    assert late == [_S1, _SLIME_OAD]


class _StoppingTitles(_TitleCatalog):
    def __init__(self) -> None:
        super().__init__(graphs=_slime_titles().graphs)
        self.owner: AutomationOwner | None = None

    def cover_urls(self, anilist_ids: Collection[int]) -> dict[int, str]:
        assert self.owner is not None
        self.owner._shutting_down = True
        return super().cover_urls(anilist_ids)


@pytest.mark.unit
def test_cover_fetch_stops_when_shutting_down(tmp_path: Path) -> None:
    titles: _StoppingTitles = _StoppingTitles()
    owner, covers = _cover_owner(tmp_path, titles)
    titles.owner = owner
    acquisition: AcquisitionService | None = owner._service.acquisition
    assert acquisition is not None

    owner._read_covers(acquisition, covers, (_S1, _SLIME_OAD), {})

    assert titles.cover_reads == [[_S1, _SLIME_OAD]]
    assert titles.downloads == []
    assert not covers.exists()


def _named_rows(owner: AutomationOwner, count: int) -> list[dict[str, object]]:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        rows: object = owner.handle(_request("status")).result["library"]
        if isinstance(rows, list) and sum(row.get("series") is not None for row in rows) == count:
            return [dict(row) for row in rows]
        time.sleep(0.01)
    pytest.fail("The owner did not name the downloaded sets")
