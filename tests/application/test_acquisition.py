from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest

from anishift.application.acquisition import (
    MAX_GROUP_QUERIES,
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
from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.services.catalog import PrequelEntry, TitleCandidate, TitleStatus
from anishift.services.torrents import Release, ReleaseName, TorrentInfo
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

    def search(self, query: str) -> tuple[Release, ...]:
        self.queries.append(query)
        if self.answers:
            return self.answers.get(query, ())
        return self.releases


class _TitleCatalog:
    def __init__(
        self,
        candidates: tuple[TitleCandidate, ...] = (),
        prequels: tuple[PrequelEntry, ...] = (),
    ) -> None:
        self.candidates: tuple[TitleCandidate, ...] = candidates
        self.prequels: tuple[PrequelEntry, ...] = prequels
        self.searched: list[str] = []

    def search(self, text: str, *, limit: int = 7) -> tuple[TitleCandidate, ...]:
        self.searched.append(text)
        return self.candidates[:limit]

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        return self.prequels


class _Client:
    def __init__(self, *, reachable: bool = True, extension: bool = False) -> None:
        self.reachable: bool = reachable
        self.preference_values: dict[str, object] = {"incomplete_files_ext": extension}
        self.added: list[tuple[str, Path, str]] = []
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

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        self._require()
        self.added.append((torrent_url, save_path, category))

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        self._require()
        return tuple(self.tracked)

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


def test_catalog_groups_by_series_and_group_with_newest_episode_first() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10", seeders=5), _release("dkb-11", seeders=50), _release("sp-11v2"), _release("sp-11")),
        _parse,
    )

    assert [(group.series, group.group) for group in catalog.groups] == [
        ("Neko to Ryuu", "DKB"),
        ("Neko to Ryuu", "SubsPlease"),
    ]
    assert [choice.release.title for choice in catalog.groups[1].choices] == ["sp-11v2", "sp-11", "sp-10"]


def test_catalog_lists_a_batch_after_numbered_episodes() -> None:
    catalog: ReleaseCatalog = catalog_releases((_release("batch"), _release("sp-10")), _parse)

    assert [choice.release.title for choice in catalog.groups[0].choices] == ["sp-10", "batch"]


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


def test_download_queues_every_choice_into_the_series_directory(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    choices: tuple[ReleaseChoice, ...] = (
        ReleaseChoice(_release("sp-10"), _NAMES["sp-10"]),
        ReleaseChoice(_release("sp-11"), _NAMES["sp-11"]),
    )

    receipt: DownloadReceipt = service.download(choices)

    assert receipt == DownloadReceipt(2, tmp_path / "Neko to Ryuu")
    assert [entry[1:] for entry in client.added] == [(tmp_path / "Neko to Ryuu", "AniShift")] * 2
    assert client.added[0][0].startswith("https://nyaa.si/download/")


def test_queued_hashes_lists_the_tracked_torrents_in_lowercase(tmp_path: Path) -> None:
    client: _Client = _Client()
    client.tracked.append(TorrentInfo(name="ep", info_hash="ABCDEF", progress=0.5, state="downloading", save_path="x"))

    assert _service(client, tmp_path).queued_hashes() == frozenset({"abcdef"})


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
    assert status.incomplete_extension is True


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
    assert [choice.release.title for choice in catalog.groups[0].choices] == ["mt-colon", "mt-plain"]


def test_catalog_hides_a_dubbed_release_and_one_without_a_stated_language() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10"), _release("dub"), _release("sp-11", language=None)),
        _parse,
    )

    assert catalog.hidden == 2
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-10"]


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
        "Ore dake Level Up na Ken - 01",
        "Ore dake Level Up na Ken S02E01",
        "Ore dake Level Up na Ken - 13",
        "Solo Leveling - 01",
        "Solo Leveling S02E01",
        "Solo Leveling - 13",
    ]


def test_search_title_does_not_number_a_range_wider_than_three_episodes(tmp_path: Path) -> None:
    source: _Source = _Source()
    service: AcquisitionService = _service(_Client(), tmp_path, source=source)

    service.search_title(_SOLO, episodes=EpisodeRange(Decimal(1), Decimal(12)))

    assert source.queries == [
        "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        "Solo Leveling Season 2 -Arise from the Shadow-",
    ]


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
    assert [choice.release.title for choice in catalog.groups[0].choices] == ["sp-11v2", "sp-11", "sp-10"]


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


def test_download_can_send_every_choice_into_one_named_directory(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    choices: tuple[ReleaseChoice, ...] = (
        ReleaseChoice(_release("sp-10"), _NAMES["sp-10"]),
        ReleaseChoice(_release("other-9"), _NAMES["other-9"]),
    )

    receipt: DownloadReceipt = service.download(choices, directory_name="Solo Leveling: Season 2")

    assert receipt == DownloadReceipt(2, tmp_path / "Solo Leveling Season 2")
    assert [entry[1] for entry in client.added] == [tmp_path / "Solo Leveling Season 2"] * 2
