from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest
from test_acquisition import _S1, _episode_service, _slime_titles
from test_automation import _TIMEOUT_S, _completed_library, _owner, _real_service, _request, _serving

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
from anishift.application.control_views import LibrarySet
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import AniZipMapping, ListedEpisode
from anishift.application.intents import RequestOrigin
from anishift.application.library import name_series, series_title, untitled_series
from anishift.application.subscription_targets import SubscriptionRecord
from anishift.application.workflows import WorkflowTarget

_MOMENT: Final[str] = "2026-10-11T09:00:00+00:00"
_BLUE_BOX: Final[int] = 189123
_TOONSHUB: Final[str] = "Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264.MSubs-ToonsHub"
_JUDAS: Final[str] = "[Judas] Ao no Hako - S02E02"

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


def _named(state: WatchState, titles: dict[int, str] | None = None) -> _Named:
    sets: tuple[LibrarySet, ...] = tuple(_set(item) for item in state.ready_groups)
    return {item.name: (item.series, item.season, item.episode) for item in name_series(sets, state, titles or {})}


@pytest.mark.unit
def test_name_series_gives_releases_of_different_groups_the_subscription_series_and_catalogue_episode() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("toonshub", _BLUE_BOX, 1), _downloaded("judas", _BLUE_BOX, 2, subscription="blue")),
        ready_groups=(_ready("toonshub", _TOONSHUB), _ready("judas", _JUDAS)),
        subscriptions=(_followed(_BLUE_BOX, "Blue Box Season 2"),),
    )

    assert _named(state) == {_TOONSHUB: ("Blue Box", 2, 1), _JUDAS: ("Blue Box", 2, 2)}


@pytest.mark.unit
def test_name_series_reads_an_unsubscribed_download_from_catalogue_titles_once_they_are_known() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("mushoku", 178789, 14),),
        ready_groups=(_ready("mushoku", "[Erai-raws] Mushoku Tensei III - Isekai Ittara Honki Dasu - 14 [1080p]"),),
    )
    titles: dict[int, str] = {178789: "Mushoku Tensei: Jobless Reincarnation Season 3"}

    assert untitled_series(state, {}) == frozenset({178789})
    assert untitled_series(state, titles) == frozenset()
    assert set(_named(state).values()) == {(None, None, None)}
    assert set(_named(state, titles).values()) == {("Mushoku Tensei: Jobless Reincarnation", 3, 14)}


@pytest.mark.unit
def test_name_series_gives_seasons_of_one_franchise_one_base_name() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("first", 186497, 14), _downloaded("second", 213805, 1)),
        ready_groups=(
            _ready("first", "The.Ramparts.of.Ice.S01E14.Bombshell.1080p.NF.WEB-DL"),
            _ready("second", "[Erai-raws] Koori no Jouheki 2nd Season - 01 [1080p]"),
        ),
        subscriptions=(_followed(213805, "The Ramparts of Ice Season 2"),),
    )

    named: _Named = _named(state, {186497: "The Ramparts of Ice"})

    assert named == {
        "The.Ramparts.of.Ice.S01E14.Bombshell.1080p.NF.WEB-DL": ("The Ramparts of Ice", None, None),
        "[Erai-raws] Koori no Jouheki 2nd Season - 01 [1080p]": ("The Ramparts of Ice", 2, 1),
    }
    assert untitled_series(state, {}) == frozenset({186497})


@pytest.mark.unit
def test_name_series_takes_the_season_from_the_subscription_mapping_when_the_title_names_none() -> None:
    mapping: AniZipMapping = AniZipMapping(1, "TV", 4, (ListedEpisode(3, season=1, episode=3),), (), None, {})
    state: WatchState = WatchState(
        acquisitions=(_downloaded("explorer", 169581, 3),),
        ready_groups=(_ready("explorer", "[Erai-raws] Magical Explorer - 03 [1080p]"),),
        subscriptions=(_followed(169581, "Magical Explorer", mapping),),
    )

    assert set(_named(state).values()) == {("Magical Explorer", 1, 3)}


@pytest.mark.unit
def test_name_series_links_a_legacy_order_through_its_files_and_keeps_an_unknown_episode_from_the_file() -> None:
    stem: str = "Overgeared.S01E01.Legendary.Class.1080p.CR.WEB-DL"
    state: WatchState = WatchState(
        acquisitions=(_legacy(stem, LegacyScope(212888, None)),),
        ready_groups=(_ready("overgeared", stem),),
        subscriptions=(_followed(212888, "Overgeared"),),
    )

    assert _named(state) == {stem: ("Overgeared", None, None)}


@pytest.mark.unit
def test_name_series_leaves_a_set_added_by_hand_to_its_file_name() -> None:
    state: WatchState = WatchState(
        acquisitions=(_downloaded("other", _BLUE_BOX, 1),),
        ready_groups=(_ready("film", "Some.Cartoon.1999.1080p.BluRay"),),
        subscriptions=(_followed(_BLUE_BOX, "Blue Box Season 2"),),
    )

    assert _named(state) == {"Some.Cartoon.1999.1080p.BluRay": (None, None, None)}
    assert untitled_series(state, {}) == frozenset()


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
def test_owner_names_a_downloaded_set_after_a_catalogue_title_read_once_in_the_pool(tmp_path: Path) -> None:
    _, store, state = _completed_library(tmp_path)
    store.save(replace(state, acquisitions=(_downloaded("set-01", _S1, 4),)))
    titles = _slime_titles()
    service = _real_service(tmp_path, acquisition=_episode_service(tmp_path, titles))
    owner: AutomationOwner = _owner(service, store)
    thread: threading.Thread = _serving(owner)
    try:
        assert owner.handle(_request("library_refresh")).ok
        row: dict[str, object] = _named_row(owner)
        details: object = owner.handle(_request("library_details", {"set_id": "set-01"})).result
        owner.handle(_request("status"))
    finally:
        owner.request_shutdown()
        thread.join(_TIMEOUT_S)
    assert (row["series"], row["season"], row["episode"]) == ("That Time I Got Reincarnated as a Slime", None, None)
    assert isinstance(details, dict)
    assert details["series"] == "That Time I Got Reincarnated as a Slime"
    assert titles.franchised == [_S1]


def _named_row(owner: AutomationOwner) -> dict[str, object]:
    deadline: float = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        rows: object = owner.handle(_request("status")).result["library"]
        if isinstance(rows, list) and rows and rows[0].get("series") is not None:
            return dict(rows[0])
        time.sleep(0.01)
    pytest.fail("The owner did not name the downloaded set")
