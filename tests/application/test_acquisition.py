from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from pydantic import ValidationError
from test_episode_selection import (
    _diaries_own_releases,
    _edge,
    _fixture_graph,
    _fixture_mapping,
    _fixture_streams,
    _graph,
    _node,
    _stream,
)

from anishift.application import acquisition as acquisition_module
from anishift.application.acquisition import (
    MAX_GROUP_QUERIES,
    MAX_REQUESTS,
    AcquisitionService,
    CatalogOrder,
    ClientStatus,
    DownloadReceipt,
    EpisodeReading,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    catalog_releases,
    read_episode,
    series_directory_name,
)
from anishift.application.cancellation import CancellationToken
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_selection import (
    AniZipMapping,
    EntryGroup,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    Franchise,
    FranchiseGraph,
    ListedEpisode,
    RankedCandidate,
    StreamCandidate,
    identity_target,
    rank_candidates,
    suggestion,
)
from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.services.catalog import (
    EpisodeAiring,
    PrequelEntry,
    SeasonAiring,
    TitleCandidate,
    TitleCatalogError,
    TitleStatus,
)
from anishift.services.http_requests import RequestControl
from anishift.services.torrents import Release, ReleaseName, TorrentFile, TorrentInfo
from anishift.services.torrents.categories import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    SEARCH_CATEGORIES,
)
from anishift.services.torrents.query import EpisodeRange


class _ClientDownError(FatalError):
    pass


class _Source:
    def __init__(
        self,
        releases: tuple[Release, ...] = (),
        answers: Mapping[str, tuple[Release, ...]] | None = None,
    ) -> None:
        self.releases: tuple[Release, ...] = releases
        self.answers: dict[str, tuple[Release, ...]] = dict(answers or {})
        self.queries: list[str] = []
        self.requests: list[tuple[str, str]] = []

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        self.queries.append(query)
        self.requests.extend((query, category) for category in categories)
        if self.answers:
            return self.answers.get(query, ())
        return self.releases


class _TitleCatalog:
    def __init__(
        self,
        candidates: tuple[TitleCandidate, ...] = (),
        prequels: tuple[PrequelEntry, ...] = (),
        graphs: Mapping[int, FranchiseGraph] | None = None,
        schedules: Mapping[int, SeasonAiring] | None = None,
    ) -> None:
        self.candidates: tuple[TitleCandidate, ...] = candidates
        self.prequels: tuple[PrequelEntry, ...] = prequels
        self.graphs: dict[int, FranchiseGraph] = dict(graphs or {})
        self.schedules: dict[int, SeasonAiring] = dict(schedules or {})
        self.searched: list[str] = []
        self.franchised: list[int] = []
        self.scheduled: list[int] = []
        self.schedule_fails: bool = False

    def search(self, text: str, *, limit: int = 7) -> tuple[TitleCandidate, ...]:
        self.searched.append(text)
        return self.candidates[:limit]

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        return self.prequels

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        self.scheduled.append(anilist_id)
        if self.schedule_fails:
            raise TitleCatalogError(
                context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="AniList rejected the request")
            )
        return self.schedules.get(anilist_id, SeasonAiring(anilist_id, TitleStatus.UNKNOWN, None, ()))

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> FranchiseGraph:
        self.franchised.append(anilist_id)
        return self.graphs[anilist_id]


class _EpisodeCatalog:
    def __init__(self, mappings: Mapping[int, AniZipMapping]) -> None:
        self.mappings: dict[int, AniZipMapping] = dict(mappings)
        self.asked: list[int] = []

    def mapping(self, anilist_id: int) -> AniZipMapping:
        self.asked.append(anilist_id)
        return self.mappings[anilist_id]


class _StreamSource:
    def __init__(self, answers: Mapping[tuple[int, int | None], tuple[StreamCandidate, ...]] | None = None) -> None:
        self.answers: dict[tuple[int, int | None], tuple[StreamCandidate, ...]] = dict(answers or {})
        self.asked: list[tuple[int, int | None]] = []

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        self.asked.append((kitsu_id, number))
        return self.answers.get((kitsu_id, number), ())

    def movie_streams(self, kitsu_id: int) -> tuple[StreamCandidate, ...]:
        self.asked.append((kitsu_id, None))
        return self.answers.get((kitsu_id, None), ())


class _FailingStreams(_StreamSource):
    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        raise ValueError(kitsu_id, number)


class _Client:
    def __init__(self, *, reachable: bool = True, extension: bool = False) -> None:
        self.reachable: bool = reachable
        self.preference_values: dict[str, object] = {"incomplete_files_ext": extension}
        self.added: list[tuple[str, Path, str]] = []
        self.stopped: list[bool] = []
        self.renamed: list[tuple[str, str, str]] = []
        self.started: list[str] = []
        self.tracked: list[TorrentInfo] = []

    def version(self) -> str:
        self._require()
        return "5.2.3"

    def preferences(self) -> dict[str, object]:
        self._require()
        return dict(self.preference_values)

    def set_preferences(self, values: Mapping[str, object]) -> None:
        self._require()
        self.preference_values.update(values)

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str, stopped: bool = False) -> None:
        self._require()
        self.added.append((torrent_url, save_path, category))
        self.stopped.append(stopped)

    def rename_file(self, info_hash: str, old_path: str, new_path: str) -> None:
        self._require()
        self.renamed.append((info_hash, old_path, new_path))

    def resume(self, info_hash: str) -> None:
        self._require()
        self.started.append(info_hash)

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        self._require()
        return tuple(self.tracked)

    def files(self, info_hash: str) -> tuple[TorrentFile, ...]:
        del info_hash
        return ()

    def _require(self) -> None:
        if not self.reachable:
            raise _ClientDownError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                    message="qBittorrent Web UI is not reachable",
                    suggestion="Enable the Web UI",
                )
            )


_MOMENT: Final[datetime] = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _title(romaji: str, english: str | None = None) -> TitleCandidate:
    return TitleCandidate(
        anilist_id=1,
        romaji=romaji,
        english=english,
        native="猫と竜",
        synonyms=(),
        year=2026,
        season="SPRING",
        format="TV",
        episodes=13,
        status=TitleStatus.RELEASING,
        prequel_ids=(),
    )


_CANDIDATE: Final[TitleCandidate] = _title("Neko to Ryuu", "The Cat and the Dragon")

_SOLO: Final[TitleCandidate] = _title(
    "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
    "Solo Leveling Season 2 -Arise from the Shadow-",
)

_SEASON: Final[PrequelEntry] = PrequelEntry(episodes=12, cour=False)

_COUR: Final[PrequelEntry] = PrequelEntry(episodes=12, cour=True)


def _release(
    title: str,
    *,
    seeders: int = 10,
    language: str | None = "en",
    published: datetime | None = None,
) -> Release:
    return Release(
        title=title,
        torrent_url=f"https://nyaa.si/download/{title}.torrent",
        info_hash=title,
        seeders=seeders,
        size_text="1.0 GiB",
        published=published,
        subtitle_language=language,
    )


_BASE_NAME: ReleaseName = ReleaseName(
    group="SubsPlease",
    series="Neko to Ryuu",
    episode=None,
    season=None,
    resolution=1080,
    batch=False,
    version=None,
)


_NAMES: dict[str, ReleaseName] = {
    "sp-10": replace(_BASE_NAME, episode=Decimal(10)),
    "sp-11": replace(_BASE_NAME, episode=Decimal(11)),
    "sp-11v2": replace(_BASE_NAME, episode=Decimal(11), version=2),
    "dkb-11": replace(_BASE_NAME, group="DKB", episode=Decimal(11)),
    "sp-720": replace(_BASE_NAME, episode=Decimal(9), resolution=720),
    "unknown": replace(_BASE_NAME, episode=Decimal(8), resolution=None),
    "batch": replace(_BASE_NAME, batch=True),
    "dub": replace(_BASE_NAME, episode=Decimal(7), dubbed=True),
    "sp-3": replace(_BASE_NAME, episode=Decimal(3)),
    "sp-5": replace(_BASE_NAME, episode=Decimal(5)),
    "sp-13": replace(_BASE_NAME, episode=Decimal(13)),
    "sp-s1-4": replace(_BASE_NAME, episode=Decimal(4), season=1),
    "dkb-s1-4": replace(_BASE_NAME, group="DKB", episode=Decimal(4), season=1),
    "mt-colon": replace(_BASE_NAME, series="Mushoku Tensei: Jobless Reincarnation", episode=Decimal(10)),
    "mt-plain": replace(_BASE_NAME, series="Mushoku Tensei Jobless Reincarnation", episode=Decimal(9)),
    "other-9": replace(_BASE_NAME, series="Zombie Land", group="DKB", episode=Decimal(9)),
    "dkb-s2-11": replace(_BASE_NAME, group="DKB", episode=Decimal(11), season=2),
    "sl-plain": replace(_BASE_NAME, series="Solo Leveling", group="Tsundere-Raws", episode=Decimal(13)),
    "sl-romaji": replace(
        _BASE_NAME,
        series="Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        group="Erai-raws",
        episode=Decimal(1),
    ),
    **{f"g{index}-1": replace(_BASE_NAME, group=f"G{index}", episode=Decimal(1)) for index in range(1, 7)},
}


def _parse(title: str) -> ReleaseName:
    return _NAMES[title]


def _service(
    client: _Client,
    tmp_path: Path,
    releases: tuple[Release, ...] = (),
    *,
    source: _Source | None = None,
    title_catalog: _TitleCatalog | None = None,
) -> AcquisitionService:
    return AcquisitionService(
        source=source if source is not None else _Source(releases),
        client=client,
        workspace_root=tmp_path,
        parse_name=_parse,
        title_catalog=title_catalog,
    )


def test_catalog_hides_low_and_unknown_quality_and_counts_them() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10"), _release("sp-720"), _release("unknown")),
        _parse,
    )

    assert catalog.hidden == 2
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-10"]


def test_catalog_groups_by_series_and_group_with_ascending_episodes_and_latest_version_first() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10", seeders=5), _release("dkb-11", seeders=50), _release("sp-11v2"), _release("sp-11")),
        _parse,
    )

    assert [(group.series, group.group) for group in catalog.groups] == [
        ("Neko to Ryuu", "DKB"),
        ("Neko to Ryuu", "SubsPlease"),
    ]
    assert [choice.release.title for choice in catalog.groups[1].choices] == ["sp-10", "sp-11v2", "sp-11"]


def test_catalog_lists_a_batch_after_numbered_episodes() -> None:
    catalog: ReleaseCatalog = catalog_releases((_release("batch"), _release("sp-10")), _parse)

    assert [choice.release.title for choice in catalog.groups[0].choices] == ["sp-10", "batch"]


def test_catalog_orders_fractional_episodes_stably_without_changing_season_or_pack_classification() -> None:
    names: dict[str, ReleaseName] = {
        "eight": replace(_BASE_NAME, episode=Decimal(8), season=2),
        "half-v2-a": replace(_BASE_NAME, episode=Decimal("7.5"), version=2, season=2),
        "seven": replace(_BASE_NAME, episode=Decimal(7), season=2),
        "half": replace(_BASE_NAME, episode=Decimal("7.5"), season=2),
        "half-v2-b": replace(_BASE_NAME, episode=Decimal("7.5"), version=2, season=2),
        "foreign": replace(_BASE_NAME, episode=Decimal(1), season=1),
        "pack": replace(_BASE_NAME, batch=True, season=2),
    }
    catalog: ReleaseCatalog = catalog_releases(
        tuple(_release(title) for title in names), names.__getitem__, context=SeasonContext(2, 12, 12)
    )
    choices: tuple[ReleaseChoice, ...] = catalog.groups[0].choices
    assert [choice.release.title for choice in choices] == [
        "seven",
        "half-v2-a",
        "half-v2-b",
        "half",
        "eight",
        "pack",
        "foreign",
    ]
    assert [choice.release.title for choice in choices if choice.other_season] == ["foreign"]
    assert [choice.release.title for choice in choices if choice.name.is_pack] == ["pack"]


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ("Neko to Ryuu", "Neko to Ryuu"),
        ('Re:Zero <Season 2> "Final"', "ReZero Season 2 Final"),
        ("  Oshi   no Ko S3 ...", "Oshi no Ko S3"),
        ("CON", "_CON"),
        ("aux.mkv", "_aux.mkv"),
        ("***", "Nieznana seria"),
    ],
)
def test_series_directory_name_is_safe_on_windows(series: str, expected: str) -> None:
    assert series_directory_name(series) == expected


def test_search_returns_the_catalog_of_the_source_answer(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path, (_release("sp-11"), _release("sp-720")))

    catalog: ReleaseCatalog = service.search("neko")

    assert catalog.hidden == 1
    assert catalog.groups[0].choices[0].release.title == "sp-11"


def test_download_queues_every_choice_stopped_in_the_flat_workspace(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    choices: tuple[ReleaseChoice, ...] = (
        ReleaseChoice(_release("sp-10"), _NAMES["sp-10"]),
        ReleaseChoice(_release("sp-11"), _NAMES["sp-11"]),
    )

    receipt: DownloadReceipt = service.download(choices)

    assert receipt == DownloadReceipt(2, tmp_path)
    assert [entry[1:] for entry in client.added] == [(tmp_path, "AniShift")] * 2
    assert client.stopped == [True, True]
    assert client.added[0][0].startswith("https://nyaa.si/download/")


def test_queued_hashes_lists_the_tracked_torrents_in_lowercase(tmp_path: Path) -> None:
    client: _Client = _Client()
    client.tracked.append(TorrentInfo(name="ep", info_hash="ABCDEF", progress=0.5, state="downloading", save_path="x"))

    assert _service(client, tmp_path).queued_hashes() == frozenset({"abcdef"})


@pytest.mark.parametrize("stop", [False, True])
def test_add_observation_preserves_seen_hashes_and_checks_admission_after_waiting(
    tmp_path: Path, *, stop: bool
) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    client.tracked = [TorrentInfo("first", "FIRST", 0.0, "stoppedDL", "x")]
    allowed: bool = True
    delays: list[float] = []

    def wait(delay: float) -> None:
        nonlocal allowed
        delays.append(delay)
        allowed = not stop
        client.tracked = [TorrentInfo("second", "SECOND", 0.0, "stoppedDL", "x")]

    observations: Iterator[frozenset[str]] = service.observe_added(
        frozenset({"first", "second"}), sleep=wait, may_observe=lambda: allowed
    )
    assert next(observations) == frozenset({"first"})
    assert list(observations) == ([] if stop else [frozenset({"second"})])
    assert delays == [1.0]
    assert client.added == []
    assert client.started == []


def test_download_refuses_an_empty_choice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one release"):
        _service(_Client(), tmp_path).download(())


def test_client_status_reports_version_and_incomplete_extension(tmp_path: Path) -> None:
    status: ClientStatus = _service(_Client(extension=True), tmp_path).client_status()

    assert status == ClientStatus(reachable=True, version="5.2.3", incomplete_extension=True)


def test_client_status_turns_an_unreachable_client_into_a_sentence(tmp_path: Path) -> None:
    status: ClientStatus = _service(_Client(reachable=False), tmp_path).client_status()

    assert status.reachable is False
    assert "not reachable" in status.problem
    assert status.suggestion == "Enable the Web UI"


def test_setup_client_switches_the_incomplete_extension_on(tmp_path: Path) -> None:
    client: _Client = _Client(extension=False)

    status: ClientStatus = _service(client, tmp_path).setup_client()

    assert client.preference_values["incomplete_files_ext"] is True
    assert client.preference_values["max_ratio"] == 0
    assert client.preference_values["max_seeding_time"] == 0
    assert status.incomplete_extension is True
    assert status.seeding_stops is True


def test_setup_client_does_not_touch_an_unreachable_client(tmp_path: Path) -> None:
    client: _Client = _Client(reachable=False)

    status: ClientStatus = _service(client, tmp_path).setup_client()

    assert status.reachable is False
    assert client.preference_values["incomplete_files_ext"] is False


_READING_CASES: tuple[tuple[str, ReleaseName, SeasonContext | None, EpisodeReading], ...] = (
    ("no context", _NAMES["sp-13"], None, EpisodeReading(Decimal(13))),
    (
        "marker equal to the chosen season",
        replace(_BASE_NAME, episode=Decimal(13), season=2),
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(Decimal(13)),
    ),
    (
        "marker naming another season",
        replace(_BASE_NAME, series="Neko to Ryuu S1", episode=Decimal(4)),
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(Decimal(4), other_season=True),
    ),
    (
        "absolute thirteen read as one",
        _NAMES["sp-13"],
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(Decimal(1), absolute=Decimal(13)),
    ),
    (
        "absolute twenty five read as thirteen",
        replace(_BASE_NAME, episode=Decimal(25)),
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(Decimal(13), absolute=Decimal(25)),
    ),
    (
        "unmarked number below the offset",
        _NAMES["sp-5"],
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(Decimal(5), other_season=True),
    ),
    (
        "first season without a marker",
        _NAMES["sp-5"],
        SeasonContext(index=1, offset=0, episodes=13),
        EpisodeReading(Decimal(5)),
    ),
    (
        "pack without a number",
        _NAMES["batch"],
        SeasonContext(index=2, offset=12, episodes=13),
        EpisodeReading(None),
    ),
)


@pytest.mark.parametrize(
    ("name", "context", "expected"),
    [(name, context, expected) for _, name, context, expected in _READING_CASES],
    ids=[label for label, _, _, _ in _READING_CASES],
)
def test_read_episode_interprets_the_number_in_the_chosen_season(
    name: ReleaseName,
    context: SeasonContext | None,
    expected: EpisodeReading,
) -> None:
    assert read_episode(name, context) == expected


def test_catalog_groups_one_series_written_with_and_without_punctuation() -> None:
    catalog: ReleaseCatalog = catalog_releases((_release("mt-colon"), _release("mt-plain")), _parse)

    assert len(catalog.groups) == 1
    assert catalog.groups[0].series == "Mushoku Tensei: Jobless Reincarnation"
    assert [choice.release.title for choice in catalog.groups[0].choices] == ["mt-plain", "mt-colon"]


def test_catalog_excludes_a_dubbed_release_and_one_without_a_stated_language() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10"), _release("dub"), _release("sp-11", language=None)),
        _parse,
    )

    assert (catalog.hidden, catalog.excluded) == (0, 2)
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-10"]


def test_catalog_counts_quality_and_language_apart() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10"), _release("sp-720"), _release("dub")),
        _parse,
    )

    assert (catalog.hidden, catalog.excluded) == (1, 1)


def test_catalog_reports_the_language_most_of_a_group_carries() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10", language="fr"), _release("sp-11"), _release("sp-11v2")),
        _parse,
    )

    assert catalog.groups[0].subtitle_language == "en"


def test_catalog_filters_episodes_outside_the_range_and_every_pack() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-3"), _release("sp-5"), _release("batch")),
        _parse,
        episodes=EpisodeRange(Decimal(4), Decimal(10)),
    )

    assert catalog.filtered == 2
    assert catalog.hidden == 0
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-5"]


def test_catalog_orders_groups_by_newest_publication_or_by_seeders() -> None:
    releases: tuple[Release, ...] = (
        _release("sp-10", seeders=5, published=_MOMENT),
        _release("dkb-11", seeders=50, published=_MOMENT - timedelta(days=1)),
    )

    newest: ReleaseCatalog = catalog_releases(releases, _parse, order=CatalogOrder.NEWEST)
    seeded: ReleaseCatalog = catalog_releases(releases, _parse, order=CatalogOrder.SEEDERS)

    assert [group.group for group in newest.groups] == ["SubsPlease", "DKB"]
    assert [group.group for group in seeded.groups] == ["DKB", "SubsPlease"]
    assert newest.groups[0].newest == _MOMENT


def test_catalog_lists_the_groups_matching_the_title_before_the_rest() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("other-9", seeders=900), _release("sp-10", seeders=1)),
        _parse,
        aliases=("Neko to Ryuu",),
    )

    assert [(group.series, group.matches_title) for group in catalog.groups] == [
        ("Neko to Ryuu", True),
        ("Zombie Land", False),
    ]


def test_catalog_lists_a_release_of_another_season_after_the_chosen_one() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-s1-4"), _release("sp-13")),
        _parse,
        context=SeasonContext(index=2, offset=12, episodes=13),
    )

    choices: tuple[ReleaseChoice, ...] = catalog.groups[0].choices
    assert [choice.release.title for choice in choices] == ["sp-13", "sp-s1-4"]
    assert [choice.episode for choice in choices] == [Decimal(1), Decimal(4)]
    assert choices[0].absolute == Decimal(13)
    assert choices[1].other_season is True


def test_catalog_sinks_a_group_that_only_carries_another_season() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("dkb-s1-4", seeders=900, published=_MOMENT), _release("sp-13", seeders=1)),
        _parse,
        order=CatalogOrder.NEWEST,
        context=SeasonContext(index=2, offset=12, episodes=13),
    )

    assert [group.group for group in catalog.groups] == ["SubsPlease", "DKB"]
    assert catalog.groups[1].choices[0].other_season is True


def test_find_titles_returns_nothing_without_a_composed_catalog(tmp_path: Path) -> None:
    assert _service(_Client(), tmp_path).find_titles("neko") == ()


def test_find_titles_hands_the_phrase_to_the_catalog(tmp_path: Path) -> None:
    titles: _TitleCatalog = _TitleCatalog(candidates=(_CANDIDATE,))

    found: tuple[TitleCandidate, ...] = _service(_Client(), tmp_path, title_catalog=titles).find_titles("neko")

    assert found == (_CANDIDATE,)
    assert titles.searched == ["neko"]


_CONTEXT_CASES: tuple[tuple[str, TitleCandidate, tuple[PrequelEntry, ...], int, int], ...] = (
    (
        "third season after two cours",
        _title("Mushoku Tensei III: Isekai Ittara Honki Dasu"),
        (_COUR, _SEASON, _COUR, _SEASON),
        3,
        48,
    ),
    (
        "second season second cour",
        _title("Mushoku Tensei II: Isekai Ittara Honki Dasu Part 2"),
        (_SEASON, _COUR, _SEASON),
        2,
        36,
    ),
    ("first season second cour", _title("Mushoku Tensei: Isekai Ittara Honki Dasu Part 2"), (_SEASON,), 1, 12),
    ("first season", _title("Mushoku Tensei: Isekai Ittara Honki Dasu"), (), 1, 0),
    ("second season", _title("Ore dake Level Up na Ken Season 2"), (_SEASON,), 2, 12),
)


@pytest.mark.parametrize(
    ("candidate", "prequels", "index", "offset"),
    [(candidate, prequels, index, offset) for _, candidate, prequels, index, offset in _CONTEXT_CASES],
    ids=[label for label, _, _, _, _ in _CONTEXT_CASES],
)
def test_season_context_counts_seasons_without_counting_cours(
    candidate: TitleCandidate,
    prequels: tuple[PrequelEntry, ...],
    index: int,
    offset: int,
    tmp_path: Path,
) -> None:
    service: AcquisitionService = _service(_Client(), tmp_path, title_catalog=_TitleCatalog(prequels=prequels))

    assert service.season_context(candidate) == SeasonContext(index=index, offset=offset, episodes=13)


def test_catalog_matches_a_title_whichever_part_of_its_subtitle_a_release_keeps() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sl-plain"), _release("sl-romaji"), _release("other-9")),
        _parse,
        aliases=_SOLO.aliases(),
    )

    assert {(group.series, group.matches_title) for group in catalog.groups} == {
        ("Solo Leveling", True),
        ("Ore dake Level Up na Ken Season 2: Arise from the Shadow", True),
        ("Zombie Land", False),
    }


def test_search_title_asks_for_a_numbered_episode_in_both_numberings(tmp_path: Path) -> None:
    source: _Source = _Source()
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(
        _SOLO,
        episodes=EpisodeRange(Decimal(1), Decimal(1)),
        context=SeasonContext(index=2, offset=12, episodes=13),
    )

    assert source.queries == [
        "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        "Solo Leveling Season 2 -Arise from the Shadow-",
        "Solo Leveling - 01",
        "Solo Leveling S02E01",
        "Solo Leveling - 13",
    ]
    assert len(source.requests) <= MAX_REQUESTS


def test_search_title_does_not_number_a_range_wider_than_three_episodes(tmp_path: Path) -> None:
    source: _Source = _Source()
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_SOLO, episodes=EpisodeRange(Decimal(1), Decimal(12)))

    assert source.queries == [
        "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        "Solo Leveling Season 2 -Arise from the Shadow-",
    ]


def test_search_title_asks_a_group_only_in_the_category_its_releases_came_from(tmp_path: Path) -> None:
    source: _Source = _Source(
        answers={"Neko to Ryuu": (_release("sp-10"), _release("dkb-11", language="fr"))},
    )
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_CANDIDATE)

    assert dict(source.requests[-2:]) == {
        "Neko to Ryuu SubsPlease": CATEGORY_ENGLISH_TRANSLATED,
        "Neko to Ryuu DKB": CATEGORY_NON_ENGLISH_TRANSLATED,
    }


def test_search_title_never_spends_more_requests_than_the_budget(tmp_path: Path) -> None:
    source: _Source = _Source(answers={"Neko to Ryuu": tuple(_release(f"g{index}-1") for index in range(1, 7))})
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(
        _SOLO,
        episodes=EpisodeRange(Decimal(1), Decimal(3)),
        context=SeasonContext(index=2, offset=12, episodes=13),
    )

    assert len(source.requests) <= MAX_REQUESTS


def test_search_title_refines_the_best_seeded_matching_groups_first(tmp_path: Path) -> None:
    source: _Source = _Source(
        answers={
            "Neko to Ryuu": (
                _release("dkb-11", seeders=5, published=_MOMENT),
                _release("sp-10", seeders=500, published=_MOMENT - timedelta(days=200)),
            )
        }
    )
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_CANDIDATE)

    assert source.queries[2:] == ["Neko to Ryuu SubsPlease", "Neko to Ryuu DKB"]


def test_search_title_skips_a_group_without_an_episode_of_the_chosen_season(tmp_path: Path) -> None:
    source: _Source = _Source(answers={"Neko to Ryuu": (_release("sp-s1-4"), _release("dkb-s2-11"))})
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_CANDIDATE, context=SeasonContext(index=2, offset=12, episodes=13))

    assert source.queries[2:] == ["Neko to Ryuu DKB"]


def test_search_title_asks_the_index_per_matching_group_and_merges_by_hash(tmp_path: Path) -> None:
    source: _Source = _Source(
        answers={
            "Neko to Ryuu": (_release("sp-10"), _release("other-9")),
            "The Cat and the Dragon": (_release("sp-10"), _release("sp-11")),
            "Neko to Ryuu SubsPlease": (_release("sp-11v2"),),
        }
    )
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    catalog: ReleaseCatalog = service.search_title(_CANDIDATE)

    assert source.queries == ["Neko to Ryuu", "The Cat and the Dragon", "Neko to Ryuu SubsPlease"]
    assert [group.group for group in catalog.groups] == ["SubsPlease", "DKB"]
    assert [choice.release.title for choice in catalog.groups[0].choices] == ["sp-10", "sp-11v2", "sp-11"]


def test_search_title_asks_at_most_five_groups_for_their_own_listing(tmp_path: Path) -> None:
    source: _Source = _Source(answers={"Neko to Ryuu": tuple(_release(f"g{index}-1") for index in range(1, 7))})
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_CANDIDATE)

    assert source.queries[:2] == ["Neko to Ryuu", "The Cat and the Dragon"]
    assert len(source.queries) == 2 + MAX_GROUP_QUERIES


def test_search_title_keeps_only_the_asked_episodes(tmp_path: Path) -> None:
    source: _Source = _Source(answers={"Neko to Ryuu": (_release("sp-3"), _release("sp-5"))})
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    catalog: ReleaseCatalog = service.search_title(_CANDIDATE, episodes=EpisodeRange(Decimal(5), Decimal(5)))

    assert catalog.filtered == 1
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-5"]


def test_download_sends_choices_of_two_series_into_the_same_flat_workspace(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    choices: tuple[ReleaseChoice, ...] = (
        ReleaseChoice(_release("sp-10"), _NAMES["sp-10"]),
        ReleaseChoice(_release("other-9"), _NAMES["other-9"]),
    )

    receipt: DownloadReceipt = service.download(choices)

    assert receipt == DownloadReceipt(2, tmp_path)
    assert [entry[1] for entry in client.added] == [tmp_path] * 2


def test_reserving_a_name_renames_that_file_through_the_client(tmp_path: Path) -> None:
    client: _Client = _Client()

    _service(client, tmp_path).rename_transfer_file("abc", "pack/01.mkv", "01.mkv")

    assert client.renamed == [("abc", "pack/01.mkv", "01.mkv")]


_S1: Final[int] = 101280

_S4: Final[int] = 182205

_DIARIES: Final[int] = 116741

_OAD: Final[int] = 106509

_HAIBANE: Final[int] = 387

_S1_KITSU: Final[int] = 41024

_DIARIES_MAPPING: Final[AniZipMapping] = AniZipMapping(_S1_KITSU, "TV", None, (), (), None, {})

_STREAM_FILES: Final[dict[tuple[int, int], str]] = {
    (41024, 4): "torrentio__kitsu-41024-4.json",
    (49235, 10): "torrentio__kitsu-49235-10.json",
    (49235, 23): "torrentio__kitsu-49235-23.json",
    (354, 1): "torrentio__kitsu-354-1.json",
    (42022, 4): "torrentio__kitsu-42022-4.json",
    (42022, 1): "torrentio__kitsu-42022-1.json",
}


class _Clock:
    def __init__(self, now: float = 1_790_000_000.0) -> None:
        self.now: float = now

    def __call__(self) -> float:
        return self.now


def _slime_titles() -> _TitleCatalog:
    return _TitleCatalog(graphs={root: _fixture_graph(root) for root in (_S1, _DIARIES, _OAD, _HAIBANE)})


def _slime_episodes() -> _EpisodeCatalog:
    mappings: dict[int, AniZipMapping] = {anilist: _fixture_mapping(anilist) for anilist in (_S1, _S4, _OAD, _HAIBANE)}
    return _EpisodeCatalog({**mappings, _DIARIES: _DIARIES_MAPPING})


def _slime_streams() -> _StreamSource:
    return _StreamSource({key: tuple(_fixture_streams(name)) for key, name in _STREAM_FILES.items()})


def _episode_service(  # noqa: PLR0913
    tmp_path: Path,
    titles: _TitleCatalog | None = None,
    episodes: _EpisodeCatalog | None = None,
    streams: _StreamSource | None = None,
    *,
    clock: _Clock | None = None,
    request_control: RequestControl | None = None,
) -> AcquisitionService:
    return AcquisitionService(
        source=_Source(),
        client=_Client(),
        workspace_root=tmp_path,
        parse_name=_parse,
        title_catalog=titles if titles is not None else _slime_titles(),
        episode_catalog=episodes if episodes is not None else _slime_episodes(),
        stream_source=streams if streams is not None else _slime_streams(),
        clock=clock if clock is not None else _Clock(),
        request_control=request_control,
    )


def _verdicts(offer: EpisodeOffer) -> list[tuple[str, int | None, IdentityVerdict]]:
    return [(item.stream.info_hash, item.stream.file_index, item.identity.verdict) for item in offer.candidates]


def _blocked_control(until: float) -> RequestControl:
    control: RequestControl = RequestControl(httpx.MockTransport(lambda request: httpx.Response(200)))
    control.restore({"anilist": until}, lambda provider, deadline: None)
    return control


def test_franchise_of_slime_lists_every_season_then_the_oad_as_extra_and_diaries_as_other(tmp_path: Path) -> None:
    view: Franchise = _episode_service(tmp_path).franchise(_S1)
    groups: dict[int, EntryGroup] = {entry.anilist_id: entry.group for entry in view.entries}
    assert [anilist for anilist, group in groups.items() if group is EntryGroup.SEASON] == [
        _S1,
        108511,
        116742,
        156822,
        _S4,
    ]
    assert groups[_OAD] is EntryGroup.EXTRA
    assert groups[_DIARIES] is EntryGroup.OTHER


def test_offer_s1e4_suggests_a_match_and_never_matches_diaries_or_oad_releases(tmp_path: Path) -> None:
    offer: EpisodeOffer = _episode_service(tmp_path).offer(EpisodeKey(_S1, 4))
    assert offer.suggestion is not None
    assert offer.candidates[offer.suggestion].identity.verdict is IdentityVerdict.MATCH
    neighbours: list[IdentityVerdict] = [
        item.identity.verdict
        for item in offer.candidates
        if re.search(r"Nikki|Diaries|OAD|OVA", item.stream.file_name or "")
    ]
    assert neighbours
    assert IdentityVerdict.MATCH not in neighbours
    assert offer.counts == {
        verdict.value: sum(1 for item in offer.candidates if item.identity.verdict is verdict)
        for verdict in IdentityVerdict
    }


@pytest.mark.parametrize(
    ("selected", "number", "kitsu", "fields"),
    [
        (_S1, 4, 41024, ("TV", 1, 4, 4, "In the Kingdom of the Dwarves")),
        (_S4, 23, 49235, ("TV", 4, 23, 95, "Granville's Hope")),
        (_S4, 10, 49235, ("TV", 4, 10, 82, "The Master of Greed")),
        (_HAIBANE, 1, 354, ("TV", 1, 1, 1, "Cocoon / Dream of Falling from the Sky / Old Home")),
        (_OAD, 4, 42022, ("OVA", 0, 5, None, "Rimuru's Glamorous Life as a Teacher, Part 2")),
        (_OAD, 1, 42022, ("OVA", None, None, None, "The Tragedy of M?")),
    ],
    ids=["slime-s1e4", "slime-s4e23", "slime-s4e10", "haibane-e1", "ova-4", "ova-1"],
)
def test_offer_through_the_franchise_ranks_recorded_streams_with_the_recorded_metadata_target(
    tmp_path: Path,
    selected: int,
    number: int,
    kitsu: int,
    fields: tuple[str, int | None, int | None, int | None, str],
) -> None:
    root: int = _HAIBANE if selected == _HAIBANE else _S1
    graph: FranchiseGraph = _fixture_graph(root)
    target: dict[str, object] = identity_target(graph, selected, _fixture_mapping(selected), number)
    assert (target["type"], target["season"], target["episode"], target["absolute"], target["episode_title"]) == fields
    service: AcquisitionService = _episode_service(tmp_path)
    service.franchise(root)
    offer: EpisodeOffer = service.offer(EpisodeKey(selected, number))
    expected: tuple[RankedCandidate, ...] = rank_candidates(target, _fixture_streams(_STREAM_FILES[kitsu, number]))
    assert offer.candidates == expected
    assert offer.suggestion == suggestion(expected)


@pytest.mark.parametrize(
    ("selected", "number"),
    [(_S1, 4), (_DIARIES, 4), (_OAD, 4)],
    ids=["s1", "diaries", "oad"],
)
@pytest.mark.parametrize(
    "warmed",
    [(), (_S1,), ("own",), (_S1, "own"), ("own", _S1)],
    ids=["cold", "through-s1", "direct", "s1-then-direct", "direct-then-s1"],
)
def test_offer_keeps_verdicts_and_suggestion_whatever_way_and_order_the_entry_was_reached(
    tmp_path: Path, selected: int, number: int, warmed: tuple[int | str, ...]
) -> None:
    baseline: EpisodeOffer = _episode_service(tmp_path).offer(EpisodeKey(selected, number))
    service: AcquisitionService = _episode_service(tmp_path)
    for root in warmed:
        service.franchise(selected if root == "own" else int(root))
    offer: EpisodeOffer = service.offer(EpisodeKey(selected, number))
    assert _verdicts(offer) == _verdicts(baseline)
    assert offer.suggestion == baseline.suggestion


def test_two_complete_graphs_holding_the_entry_give_the_same_target_and_reasons_in_either_warming_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected: dict[str, object] = _node(2, "TV", {"romaji": "Hoshi no Niwa"}, edges=[])
    graphs: dict[int, FranchiseGraph] = {
        root: _graph(_node(root, "TV", {"romaji": title}, edges=[_edge("SPIN_OFF", 2)]), selected, root_id=root)
        for root, title in ((10, "Hoshi no Niwa: Moonlight"), (20, "Gaiden 20"))
    }
    streams: _StreamSource = _StreamSource({(_S1_KITSU, 4): (_stream("Hoshi no Niwa Moonlight - 04.mkv"),)})
    targets: list[Mapping[str, object]] = []

    def spy(target: Mapping[str, object], candidates: Sequence[StreamCandidate]) -> tuple[RankedCandidate, ...]:
        targets.append(target)
        return rank_candidates(target, candidates)

    monkeypatch.setattr(acquisition_module, "rank_candidates", spy)
    offers: list[EpisodeOffer] = []
    for order in ((10, 20), (20, 10)):
        service: AcquisitionService = _episode_service(
            tmp_path, _TitleCatalog(graphs=graphs), _EpisodeCatalog({2: _DIARIES_MAPPING}), streams
        )
        for root in order:
            service.franchise(root)
        offers.append(service.offer(EpisodeKey(2, 4)))
    assert targets[0] == targets[1]
    assert [item.identity for item in offers[0].candidates] == [item.identity for item in offers[1].candidates]


def test_offer_refreshes_the_franchise_once_its_remembered_graph_has_expired(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    titles: _TitleCatalog = _slime_titles()
    service: AcquisitionService = _episode_service(tmp_path, titles, clock=clock)
    service.franchise(_S1)
    service.episodes(_S1)
    clock.now += 899
    service.offer(EpisodeKey(_S1, 4))
    assert titles.franchised == [_S1]
    clock.now += 2
    service.offer(EpisodeKey(_S1, 4))
    assert titles.franchised == [_S1, _S1]


def test_zero_max_age_still_serves_every_offer_and_listing_while_refetching_each_time(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    titles.schedules[_S1] = SeasonAiring(_S1, TitleStatus.FINISHED, 24, ())
    episodes: _EpisodeCatalog = _EpisodeCatalog({_S1: replace(_fixture_mapping(_S1), max_age_s=0)})
    streams: _StreamSource = _slime_streams()
    service: AcquisitionService = _episode_service(tmp_path, titles, episodes, streams)
    service.franchise(_S1)
    listings: list[EpisodeListing] = [service.episodes(_S1), service.episodes(_S1)]
    offers: list[EpisodeOffer] = [service.offer(EpisodeKey(_S1, 4)), service.offer(EpisodeKey(_S1, 4))]
    assert [listing.status for listing in listings] == ["FINISHED", "FINISHED"]
    assert offers[0].candidates == offers[1].candidates
    assert offers[0].candidates
    assert (titles.franchised, titles.scheduled) == ([_S1] * 3, [_S1] * 2)
    assert (episodes.asked, streams.asked) == ([_S1] * 4, [(_S1_KITSU, 4)] * 2)


def test_a_root_graph_used_by_its_leaf_stays_remembered_while_the_sixty_fifth_entry_evicts_the_oldest(
    tmp_path: Path,
) -> None:
    root: dict[str, object] = _node(10, "TV", {"romaji": "Hoshi Gaiden"}, edges=[_edge("SPIN_OFF", 2)])
    leaf: dict[str, object] = _node(2, "TV", {"romaji": "Hoshi no Niwa"}, edges=[])
    titles: _TitleCatalog = _TitleCatalog(graphs={10: _graph(root, leaf, root_id=10)})
    for other in range(100, 163):
        titles.graphs[other] = _graph(_node(other, "TV", {"romaji": f"Title {other}"}, edges=[]), root_id=other)
    service: AcquisitionService = _episode_service(tmp_path, titles, _EpisodeCatalog({2: _DIARIES_MAPPING}))
    service.franchise(10)
    service.offer(EpisodeKey(2, 4))
    for other in range(100, 162):
        service.franchise(other)
    service.offer(EpisodeKey(2, 4))
    service.franchise(162)
    service.offer(EpisodeKey(2, 4))
    service.franchise(101)
    service.franchise(100)
    assert titles.franchised == [10, *range(100, 163), 100]


def test_diaries_offer_matches_only_its_own_releases_and_never_a_main_series_release(tmp_path: Path) -> None:
    own: list[StreamCandidate] = _diaries_own_releases()
    streams: _StreamSource = _StreamSource({(_S1_KITSU, 4): (*_fixture_streams("torrentio__kitsu-41024-4.json"), *own)})
    offer: EpisodeOffer = _episode_service(tmp_path, streams=streams).offer(EpisodeKey(_DIARIES, 4))
    matches: list[StreamCandidate] = [
        item.stream for item in offer.candidates if item.identity.verdict is IdentityVerdict.MATCH
    ]
    assert matches == own
    assert offer.suggestion is not None
    assert offer.candidates[offer.suggestion].stream in own


def test_offer_on_an_incomplete_leaf_of_a_complete_root_asks_no_further_franchise_query(tmp_path: Path) -> None:
    root: dict[str, object] = _node(10, "TV", {"romaji": "Hoshi Gaiden"}, year=2024, edges=[_edge("SPIN_OFF", 2)])
    leaf: dict[str, object] = _node(2, "TV", {"romaji": "Hoshi no Niwa 2"}, year=2020, edges=[_edge("PREQUEL", 1)])
    first: dict[str, object] = _node(1, "TV", {"romaji": "Hoshi no Niwa"}, year=2018)
    graph: FranchiseGraph = _graph(root, leaf, first, root_id=10)
    assert graph.complete
    titles: _TitleCatalog = _TitleCatalog(graphs={10: graph})
    streams: _StreamSource = _StreamSource()
    service: AcquisitionService = _episode_service(
        tmp_path, titles, _EpisodeCatalog({2: replace(_DIARIES_MAPPING, kitsu_id=5)}), streams
    )
    service.franchise(10)
    service.offer(EpisodeKey(2, 5))
    assert titles.franchised == [10]
    assert streams.asked == [(5, 5)]


def test_twelve_offers_after_entering_an_entry_ask_only_the_stream_source(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    episodes: _EpisodeCatalog = _slime_episodes()
    streams: _StreamSource = _slime_streams()
    service: AcquisitionService = _episode_service(tmp_path, titles, episodes, streams)
    service.franchise(_S1)
    service.episodes(_S1)
    asked: tuple[int, int, int] = (len(titles.franchised), len(titles.scheduled), len(episodes.asked))
    for number in range(1, 13):
        service.offer(EpisodeKey(_S1, number))
    assert (len(titles.franchised), len(titles.scheduled), len(episodes.asked)) == asked
    assert streams.asked == [(_S1_KITSU, number) for number in range(1, 13)]


def test_movie_offer_asks_movie_streams_and_never_episode_streams(tmp_path: Path) -> None:
    movie: dict[str, object] = _node(7, "MOVIE", {"romaji": "Hoshi no Niwa Gekijouban"}, year=2022, edges=[])
    streams: _StreamSource = _StreamSource()
    service: AcquisitionService = _episode_service(
        tmp_path,
        _TitleCatalog(graphs={7: _graph(movie, root_id=7)}),
        _EpisodeCatalog({7: replace(_DIARIES_MAPPING, kitsu_id=70)}),
        streams,
    )
    service.offer(EpisodeKey(7, 1))
    assert streams.asked == [(70, None)]
    with pytest.raises(ValueError, match="only its first row"):
        service.offer(EpisodeKey(7, 2))


def test_offer_without_a_kitsu_mapping_ranks_nothing_and_asks_no_stream(tmp_path: Path) -> None:
    streams: _StreamSource = _slime_streams()
    service: AcquisitionService = _episode_service(
        tmp_path, episodes=_EpisodeCatalog({_S1: replace(_DIARIES_MAPPING, kitsu_id=None)}), streams=streams
    )
    offer: EpisodeOffer = service.offer(EpisodeKey(_S1, 4))
    assert (offer.candidates, offer.suggestion, streams.asked) == ((), None, [])


def test_a_stream_source_programming_error_propagates_out_of_offer(tmp_path: Path) -> None:
    service: AcquisitionService = _episode_service(tmp_path, streams=_FailingStreams())
    with pytest.raises(ValueError, match=str(_S1_KITSU)):
        service.offer(EpisodeKey(_S1, 4))


def test_episodes_use_the_airing_schedule_count_status_and_dates(tmp_path: Path) -> None:
    aired: datetime = datetime(2018, 10, 23, tzinfo=UTC)
    schedule: SeasonAiring = SeasonAiring(_S1, TitleStatus.FINISHED, 25, (EpisodeAiring(4, aired),))
    titles: _TitleCatalog = _TitleCatalog(graphs={_S1: _fixture_graph(_S1)}, schedules={_S1: schedule})
    listing: EpisodeListing = _episode_service(tmp_path, titles).episodes(_S1)
    assert (listing.status, listing.episode_count, listing.aired, listing.schedule_warning) == (
        "FINISHED",
        25,
        25,
        None,
    )
    assert [episode.number for episode in listing.episodes] == list(range(1, 26))
    assert listing.episodes[3].airs_at == aired
    assert all(episode.aired for episode in listing.episodes)


def test_failed_schedule_keeps_the_ani_zip_list_with_a_warning_and_the_anilist_retry_time(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    titles: _TitleCatalog = _TitleCatalog()
    titles.schedule_fails = True
    service: AcquisitionService = _episode_service(tmp_path, titles, clock=clock)
    listing: EpisodeListing = service.episodes(_S1)
    assert (listing.status, listing.episode_count, listing.aired) == ("UNKNOWN", 24, None)
    assert len(listing.episodes) == 24
    assert all(episode.airs_at is not None and not episode.aired for episode in listing.episodes)
    assert (listing.schedule_warning, listing.schedule_retry_at) == ("TITLE_CATALOG_FAILED", None)
    blocked: EpisodeListing = _episode_service(
        tmp_path, titles, clock=clock, request_control=_blocked_control(clock.now + 60)
    ).episodes(_S1)
    assert blocked.schedule_retry_at == datetime.fromtimestamp(clock.now + 60, UTC)
    assert titles.scheduled == [_S1]


def test_unmapped_new_ona_lists_twelve_anilist_episodes_without_invented_titles(tmp_path: Path) -> None:
    premiere: datetime = datetime(2026, 9, 27, 12, tzinfo=UTC)
    schedule: SeasonAiring = SeasonAiring(
        1,
        TitleStatus.RELEASING,
        12,
        tuple(EpisodeAiring(number, premiere + timedelta(weeks=number - 1)) for number in range(1, 13)),
    )
    titles: _TitleCatalog = _TitleCatalog(schedules={1: schedule})
    episodes: _EpisodeCatalog = _EpisodeCatalog({1: AniZipMapping(None, None, None, (), (), None, {})})
    streams: _StreamSource = _StreamSource()
    service: AcquisitionService = _episode_service(
        tmp_path,
        titles,
        episodes,
        streams,
        clock=_Clock(datetime(2026, 9, 29, tzinfo=UTC).timestamp()),
    )
    listing: EpisodeListing = service.episodes(1)
    assert listing.kitsu_id is None
    assert [episode.number for episode in listing.episodes] == list(range(1, 13))
    assert all(episode.title is None for episode in listing.episodes)
    assert [episode.airs_at for episode in listing.episodes] == [episode.airing_at for episode in schedule.episodes]
    assert [episode.number for episode in listing.episodes if episode.aired] == [1]
    assert not any(episode.airs_at_fallback for episode in listing.episodes)
    assert titles.scheduled == [1]
    assert episodes.asked == [1]
    assert not streams.asked


def test_failed_schedule_takes_the_remembered_franchise_status_without_inventing_aired(tmp_path: Path) -> None:
    titles: _TitleCatalog = _slime_titles()
    titles.schedule_fails = True
    service: AcquisitionService = _episode_service(tmp_path, titles)
    service.franchise(_S1)
    listing: EpisodeListing = service.episodes(_S4)
    assert (listing.status, listing.episode_count, listing.aired) == ("RELEASING", 24, None)
    assert not any(episode.aired for episode in listing.episodes)


def test_expired_schedule_is_not_a_fallback_after_a_later_failure(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    schedule: SeasonAiring = SeasonAiring(_S1, TitleStatus.FINISHED, 25, ())
    titles: _TitleCatalog = _TitleCatalog(schedules={_S1: schedule})
    service: AcquisitionService = _episode_service(tmp_path, titles, clock=clock)
    assert service.episodes(_S1).status == "FINISHED"
    clock.now += 901
    titles.schedule_fails = True
    listing: EpisodeListing = service.episodes(_S1)
    assert (listing.status, listing.episode_count, listing.schedule_warning) == ("UNKNOWN", 24, "TITLE_CATALOG_FAILED")


def test_retry_after_the_block_restores_the_schedule_without_asking_ani_zip_again(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    titles: _TitleCatalog = _TitleCatalog(schedules={_S1: SeasonAiring(_S1, TitleStatus.FINISHED, 24, ())})
    episodes: _EpisodeCatalog = _slime_episodes()
    service: AcquisitionService = _episode_service(
        tmp_path, titles, episodes, clock=clock, request_control=_blocked_control(clock.now + 60)
    )
    blocked: EpisodeListing = service.episodes(_S1)
    assert blocked.schedule_warning == "TITLE_CATALOG_FAILED"
    assert titles.scheduled == []
    clock.now += 61
    restored: EpisodeListing = service.episodes(_S1)
    assert (restored.schedule_warning, restored.schedule_retry_at, restored.status) == (None, None, "FINISHED")
    assert (titles.scheduled, episodes.asked) == ([_S1], [_S1])


def test_ani_zip_mapping_is_remembered_for_its_max_age_and_otherwise_fifteen_minutes(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    episodes: _EpisodeCatalog = _EpisodeCatalog(
        {_S1: _fixture_mapping(_S1), _S4: replace(_DIARIES_MAPPING, max_age_s=60)}
    )
    service: AcquisitionService = _episode_service(tmp_path, episodes=episodes, clock=clock)
    for anilist in (_S1, _S4):
        service.episodes(anilist)
    clock.now += 61
    for anilist in (_S1, _S4):
        service.episodes(anilist)
    clock.now += 840
    service.episodes(_S1)
    assert episodes.asked == [_S1, _S4, _S4, _S1]


def test_a_refetched_incomplete_graph_never_replaces_the_complete_one(tmp_path: Path) -> None:
    clock: _Clock = _Clock()
    titles: _TitleCatalog = _slime_titles()
    service: AcquisitionService = _episode_service(tmp_path, titles, clock=clock)
    assert service.franchise(_S1).complete
    titles.graphs[_S1] = replace(titles.graphs[_S1], complete=False, queried=frozenset({_S1}))
    clock.now += 901
    assert service.franchise(_S1).complete
    assert titles.franchised == [_S1, _S1]


def test_episode_selection_views_survive_a_strict_ipc_round_trip(tmp_path: Path) -> None:
    service: AcquisitionService = _episode_service(tmp_path)
    view: Franchise = service.franchise(_S1)
    listed: EpisodeListing = service.episodes(_S1)
    listing: EpisodeListing = replace(
        listed,
        episodes=(
            replace(listed.episodes[0], aired=True, airs_at_fallback=True),
            replace(listed.episodes[1], airs_at_fallback=False),
            *listed.episodes[2:],
        ),
        schedule_warning="TITLE_CATALOG_FAILED",
        schedule_retry_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    offer: EpisodeOffer = service.offer(EpisodeKey(_S1, 4))
    assert any(item.stream.file_index is None or item.stream.path is None for item in offer.candidates)
    assert decode_view(Franchise, encode_view(view)) == view
    assert decode_view(EpisodeListing, encode_view(listing)) == listing
    decoded: tuple[ListedEpisode, ...] = decode_view(EpisodeListing, encode_view(listing)).episodes
    assert {episode.aired for episode in decoded} == {True, False}
    assert {episode.airs_at_fallback for episode in decoded} == {True, False}
    for field in ("aired", "airs_at_fallback"):
        mistyped: dict[str, Any] = encode_view(listing)
        mistyped["episodes"][0][field] = "yes"
        with pytest.raises(ValidationError):
            decode_view(EpisodeListing, mistyped)
    assert decode_view(EpisodeOffer, encode_view(offer)) == offer
    choice: ReleaseChoice = ReleaseChoice(_release("sp-10"), _NAMES["sp-10"], EpisodeReading(Decimal(10)))
    assert decode_view(ReleaseChoice, encode_view(choice)) == choice


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [(EpisodeOffer, "suggestion", "0"), (EpisodeListing, "anilist_id", "101280"), (Franchise, "complete", "yes")],
)
def test_strict_ipc_decoding_refuses_a_mistyped_field(
    tmp_path: Path, model: type[object], field: str, value: object
) -> None:
    service: AcquisitionService = _episode_service(tmp_path)
    views: dict[type[object], object] = {
        EpisodeOffer: service.offer(EpisodeKey(_S1, 4)),
        EpisodeListing: service.episodes(_S1),
        Franchise: service.franchise(_S1),
    }
    payload: dict[str, object] = encode_view(views[model])
    payload[field] = value
    with pytest.raises(ValidationError):
        decode_view(model, payload)
