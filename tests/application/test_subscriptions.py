from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from anishift.application.acquisition import (
    MIN_RESOLUTION,
    AcquisitionService,
    DownloadReceipt,
    EpisodeReading,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    SeriesGroup,
)
from anishift.application.subscriptions import (
    MAX_DELAY_SAMPLES,
    SCHEMA_VERSION,
    AiringSource,
    CheckOutcome,
    EpisodeOrder,
    EpisodeState,
    Subscription,
    SubscriptionEnd,
    SubscriptionService,
    SubscriptionStore,
    subscription_id,
)
from anishift.errors import ConfigError, ErrorCode, ErrorContext, TransientError
from anishift.services.torrents import Release, ReleaseName

_TIMESTAMP: str = "2026-09-06T12:00:00+00:00"

_BASE_NAME: ReleaseName = ReleaseName(
    group="SubsPlease",
    series="Neko to Ryuu",
    episode=None,
    season=None,
    resolution=1080,
    batch=False,
    version=None,
)


class _SourceDownError(TransientError):
    pass


def _clock() -> datetime:
    return datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def _choice(  # noqa: PLR0913
    episode: Decimal | None,
    *,
    series: str = "Neko to Ryuu",
    fraction: bool = False,
    group: str = "SubsPlease",
    version: int | None = None,
    seeders: int = 10,
    season: int | None = None,
    reading: EpisodeReading | None = None,
) -> ReleaseChoice:
    name: ReleaseName = replace(_BASE_NAME, series=series, group=group, episode=episode, version=version, season=season)
    label: str = f"{group}-{series}-{episode}-v{version or 1}{'-frac' if fraction else ''}"
    release: Release = Release(
        title=f"[{group}] {series} - {episode}",
        torrent_url=f"https://nyaa.si/download/{label}.torrent",
        info_hash=label,
        seeders=seeders,
        size_text="1.0 GiB",
        published=None,
    )
    return ReleaseChoice(release, name, reading)


def _batch(episode: Decimal) -> ReleaseChoice:
    choice: ReleaseChoice = _choice(episode)
    return ReleaseChoice(choice.release, replace(choice.name, batch=True))


def _catalog(*choices: ReleaseChoice) -> ReleaseCatalog:
    buckets: dict[tuple[str, str], list[ReleaseChoice]] = {}
    for choice in choices:
        buckets.setdefault((choice.name.series, choice.name.group or "?"), []).append(choice)
    groups: tuple[SeriesGroup, ...] = tuple(
        SeriesGroup(series, group, tuple(items)) for (series, group), items in buckets.items()
    )
    return ReleaseCatalog(groups, 0)


class _Acquisition(AcquisitionService):
    def __init__(
        self,
        catalogs: Mapping[str, ReleaseCatalog] | None = None,
        failing: Sequence[str] = (),
    ) -> None:
        self.catalogs: dict[str, ReleaseCatalog] = dict(catalogs or {})
        self.failing: frozenset[str] = frozenset(failing)
        self.queries: list[str] = []
        self.downloaded: list[tuple[ReleaseChoice, ...]] = []
        self.directories: list[str | None] = []
        self.queued: set[str] = set()
        self.dropped: set[str] = set()

    def search(self, query: str) -> ReleaseCatalog:
        self.queries.append(query)
        if query in self.failing:
            raise _SourceDownError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_SOURCE_FAILED,
                    message="nyaa did not answer",
                    suggestion="Try again later",
                )
            )
        return self.catalogs.get(query, _catalog())

    def download(self, choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        self.downloaded.append(tuple(choices))
        self.directories.append(directory_name)
        self.queued.update(
            choice.release.info_hash.casefold() for choice in choices if choice.release.info_hash not in self.dropped
        )
        return DownloadReceipt(len(choices), Path("library"))

    def queued_hashes(self) -> frozenset[str]:
        return frozenset(self.queued)


def _store(tmp_path: Path) -> SubscriptionStore:
    return SubscriptionStore(tmp_path / "subscriptions.json")


def _service(tmp_path: Path, acquisition: _Acquisition) -> SubscriptionService:
    return SubscriptionService(store=_store(tmp_path), acquisition=acquisition, clock=_clock, sleep=lambda _: None)


def _subscription(  # noqa: PLR0913
    *,
    series: str = "Neko to Ryuu",
    group: str = "SubsPlease",
    query: str = "neko",
    next_episode: str = "9",
    taken: Sequence[str] = (),
    directory: str | None = None,
    season_index: int = 1,
    episode_offset: int = 0,
    season_episodes: int | None = None,
    taken_episodes: Sequence[str] = (),
) -> Subscription:
    return Subscription(
        subscription_id=subscription_id(series, group),
        query=query,
        series=series,
        group=group,
        next_episode=Decimal(next_episode),
        min_resolution=MIN_RESOLUTION,
        taken=frozenset(taken),
        added_at=_TIMESTAMP,
        checked_at=None,
        directory=directory,
        season_index=season_index,
        episode_offset=episode_offset,
        season_episodes=season_episodes,
        taken_episodes=tuple(taken_episodes),
    )


def test_store_round_trip_keeps_fractional_episodes_and_taken_hashes(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    subscription: Subscription = _subscription(next_episode="7.5", taken=("aaa", "bbb"), taken_episodes=("7", "7.5"))

    store.save((subscription,))

    assert store.load() == (subscription,)
    assert store.load()[0].next_episode == Decimal("7.5")


def test_store_returns_nothing_when_the_file_was_never_written(tmp_path: Path) -> None:
    assert _store(tmp_path).load() == ()


def test_store_rejects_a_corrupt_document(tmp_path: Path) -> None:
    (tmp_path / "subscriptions.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(ConfigError, match="Subscriptions file is invalid"):
        _store(tmp_path).load()


def test_store_rejects_an_unsupported_schema_version(tmp_path: Path) -> None:
    (tmp_path / "subscriptions.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION + 1, "subscriptions": []}), encoding="utf-8"
    )

    with pytest.raises(ConfigError) as failure:
        _store(tmp_path).load()

    assert failure.value.context.code is ErrorCode.CONFIG_INVALID
    assert failure.value.context.suggestion == "Fix or delete config/subscriptions.json"


def test_store_writes_sorted_entries_ending_with_a_newline(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)

    store.save(
        (
            _subscription(series="Zombie Land", group="SubsPlease"),
            _subscription(series="Neko to Ryuu", group="Zebra"),
            _subscription(series="Neko to Ryuu", group="DKB"),
        )
    )

    payload: str = (tmp_path / "subscriptions.json").read_text(encoding="utf-8")
    stored: tuple[Subscription, ...] = store.load()
    assert [(item.series, item.group) for item in stored] == [
        ("Neko to Ryuu", "DKB"),
        ("Neko to Ryuu", "Zebra"),
        ("Zombie Land", "SubsPlease"),
    ]
    assert payload.endswith("\n")


def test_subscribe_creates_an_entry_identified_by_series_and_group(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())

    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))

    assert subscription == _subscription()
    assert subscription.subscription_id == subscription_id("neko to ryuu", "subsplease")
    assert service.list() == (subscription,)


def test_subscribe_again_moves_the_start_and_keeps_the_taken_hashes(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)), _choice(Decimal(10)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    first: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    service.check(first)

    second: Subscription = service.subscribe("neko", _choice(Decimal(12)))

    assert second.subscription_id == first.subscription_id
    assert second.next_episode == Decimal(12)
    assert second.added_at == first.added_at
    assert second.taken == frozenset({"SubsPlease-Neko to Ryuu-9-v1", "SubsPlease-Neko to Ryuu-10-v1"})
    assert len(service.list()) == 1


def test_subscribe_again_keeps_the_switch_the_catalog_binding_and_the_delay_history(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    service.disable(first.subscription_id)
    bound: Subscription = service.set_anilist_id(first.subscription_id, 4242)
    _store(tmp_path).save([replace(bound, release_delay_s=1800, delay_samples_s=(1500, 2100))])

    second: Subscription = service.subscribe("neko", _choice(Decimal(12)))

    assert second.enabled is False
    assert second.anilist_id == 4242
    assert second.release_delay_s == 1800
    assert second.delay_samples_s == (1500, 2100)
    assert second.generation == bound.generation + 1


def test_subscribe_refuses_a_batch(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())

    with pytest.raises(ValueError, match="numbered episode"):
        service.subscribe("neko", _batch(Decimal(1)))


def test_subscribe_refuses_a_release_without_an_episode_number(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())

    with pytest.raises(ValueError, match="numbered episode"):
        service.subscribe("neko", _choice(None))


def test_check_takes_the_best_version_of_every_new_episode(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {
            "neko": _catalog(
                _choice(Decimal(8)),
                _choice(Decimal(9)),
                _choice(Decimal(10), version=1, seeders=900),
                _choice(Decimal(10), version=2, seeders=3),
                _batch(Decimal(11)),
            )
        }
    )
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == [
        "SubsPlease-Neko to Ryuu-9-v1",
        "SubsPlease-Neko to Ryuu-10-v2",
    ]
    assert outcome.downloaded == 2
    assert outcome.problem == ""
    assert service.list()[0].next_episode == Decimal(11)
    assert service.list()[0].taken == frozenset({"SubsPlease-Neko to Ryuu-9-v1", "SubsPlease-Neko to Ryuu-10-v2"})
    assert service.list()[0].checked_at == _TIMESTAMP


def test_check_skips_releases_already_handed_to_the_client(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)), _choice(Decimal(10)))})
    store: SubscriptionStore = _store(tmp_path)
    stored: Subscription = _subscription(taken=("SubsPlease-Neko to Ryuu-9-v1",))
    store.save((stored,))
    service: SubscriptionService = _service(tmp_path, acquisition)

    outcome: CheckOutcome = service.check(stored)

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == ["SubsPlease-Neko to Ryuu-10-v1"]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(11)


def test_check_skips_a_taken_release_whatever_the_hash_case(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)), _choice(Decimal(10)))})
    store: SubscriptionStore = _store(tmp_path)
    stored: Subscription = _subscription(taken=("SUBSPLEASE-NEKO TO RYUU-9-V1",))
    store.save((stored,))
    service: SubscriptionService = _service(tmp_path, acquisition)

    service.check(stored)

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == ["SubsPlease-Neko to Ryuu-10-v1"]


def test_check_treats_a_torrent_already_in_the_client_as_taken(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)), _choice(Decimal(10)))})
    acquisition.queued = {"subsplease-neko to ryuu-9-v1"}
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == ["SubsPlease-Neko to Ryuu-10-v1"]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(11)
    assert service.list()[0].taken == frozenset({"SubsPlease-Neko to Ryuu-9-v1", "SubsPlease-Neko to Ryuu-10-v1"})


def test_check_does_not_record_a_release_the_client_dropped(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)), _choice(Decimal(10)))})
    acquisition.dropped = {"SubsPlease-Neko to Ryuu-10-v1"}
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 1
    assert service.list()[0].taken == frozenset({"SubsPlease-Neko to Ryuu-9-v1"})
    assert service.list()[0].next_episode == Decimal(10)


def test_check_moves_past_an_episode_already_taken_without_a_new_download(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    store: SubscriptionStore = _store(tmp_path)
    stored: Subscription = _subscription(taken=("SubsPlease-Neko to Ryuu-9-v1",))
    store.save((stored,))
    service: SubscriptionService = _service(tmp_path, acquisition)

    outcome: CheckOutcome = service.check(stored)

    assert acquisition.downloaded == []
    assert outcome.downloaded == 0
    assert service.list()[0].next_episode == Decimal(10)


def test_check_without_new_episodes_only_records_the_check_time(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(8)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert acquisition.downloaded == []
    assert outcome.downloaded == 0
    assert service.list()[0].next_episode == Decimal(9)
    assert service.list()[0].taken == frozenset()
    assert service.list()[0].checked_at == _TIMESTAMP


def test_check_ignores_another_season_of_the_same_series(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {
            "kanojo": _catalog(
                _choice(Decimal(11), series="100-nin no Kanojo S2"),
                _choice(Decimal(7), series="100-nin no Kanojo S3"),
            )
        }
    )
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("kanojo", _choice(Decimal(7), series="100-nin no Kanojo S3"))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert [choice.name.series for choice in acquisition.downloaded[0]] == ["100-nin no Kanojo S3"]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(8)


def test_check_ignores_other_groups_and_other_series(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {
            "neko": _catalog(
                _choice(Decimal(9), group="DKB"),
                _choice(Decimal(9), series="Zombie Land"),
            )
        }
    )
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert acquisition.downloaded == []
    assert outcome.downloaded == 0
    assert service.list()[0].next_episode == Decimal(9)


def test_one_series_keeps_one_identifier_whatever_punctuation_a_release_carries() -> None:
    assert subscription_id("Mushoku Tensei: Jobless Reincarnation", "SubsPlease") == subscription_id(
        "Mushoku Tensei Jobless Reincarnation", "SubsPlease"
    )


def test_check_follows_the_group_whose_label_spells_the_series_differently(tmp_path: Path) -> None:
    plain: ReleaseChoice = _choice(Decimal(11), series="Mushoku Tensei Jobless Reincarnation")
    labelled: ReleaseCatalog = ReleaseCatalog(
        (SeriesGroup("Mushoku Tensei: Jobless Reincarnation", "SubsPlease", (plain,)),), 0
    )
    acquisition: _Acquisition = _Acquisition({"mushoku": labelled})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("mushoku", plain)

    outcome: CheckOutcome = service.check(service.list()[0])

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == [plain.release.info_hash]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(12)


def test_check_lets_a_half_episode_pass_without_moving_the_counter_past_the_next_one(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {"neko": _catalog(_choice(Decimal(7)), _choice(Decimal("7.5"), fraction=True))}
    )
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(7)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 2
    assert service.list()[0].next_episode == Decimal(8)
    assert service.list()[0].taken_episodes == ("7", "7.5")


def test_check_stops_the_counter_at_the_episode_a_feed_gap_left_behind(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(26)), _choice(Decimal(28)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(26)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 2
    assert service.list()[0].next_episode == Decimal(27)


def test_check_passes_the_gap_once_the_missing_episode_arrives(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(26)), _choice(Decimal(28)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(26)))
    service.check(service.list()[0])
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(27)), _choice(Decimal(28)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert [choice.release.info_hash for choice in acquisition.downloaded[-1]] == ["SubsPlease-Neko to Ryuu-27-v1"]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(29)


def test_check_asks_for_the_missing_episode_by_number_when_the_feed_skips_it(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {"neko": _catalog(_choice(Decimal(12))), "neko 09": _catalog(_choice(Decimal(9)))}
    )
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert acquisition.queries == ["neko", "neko 09"]
    assert outcome.downloaded == 2
    assert service.list()[0].next_episode == Decimal(10)


def test_check_asks_no_second_query_when_the_feed_already_carries_the_episode(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    service.check(service.list()[0])

    assert acquisition.queries == ["neko"]


def test_check_survives_a_failing_catch_up_query(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(12)))}, failing=("neko 09",))
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.problem == ""
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(9)


def test_store_loads_an_entry_written_before_taken_episodes_were_recorded(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 1,
        "subscriptions": [
            {
                "subscription_id": subscription_id("Neko to Ryuu", "SubsPlease"),
                "query": "neko",
                "series": "Neko to Ryuu",
                "group": "SubsPlease",
                "next_episode": "9",
                "min_resolution": MIN_RESOLUTION,
                "taken": ["aaa"],
                "added_at": _TIMESTAMP,
                "checked_at": None,
                "directory": None,
                "season_index": 1,
                "episode_offset": 0,
                "season_episodes": None,
            }
        ],
    }
    (tmp_path / "subscriptions.json").write_text(json.dumps(document), encoding="utf-8")

    assert _store(tmp_path).load() == (_subscription(taken=("aaa",)),)


def test_check_reports_a_failing_search_and_leaves_the_file_untouched(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition(failing=("neko",)))
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    before: str = (tmp_path / "subscriptions.json").read_text(encoding="utf-8")

    outcome: CheckOutcome = service.check(subscription)

    assert outcome == CheckOutcome(subscription, 0, problem="nyaa did not answer")
    assert (tmp_path / "subscriptions.json").read_text(encoding="utf-8") == before
    assert service.list()[0].checked_at is None


def test_check_all_continues_after_a_failing_subscription(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {"zombie": _catalog(_choice(Decimal(9), series="Zombie Land"))},
        failing=("neko",),
    )
    store: SubscriptionStore = _store(tmp_path)
    store.save(
        (
            _subscription(),
            _subscription(series="Zombie Land", query="zombie"),
        )
    )
    service: SubscriptionService = _service(tmp_path, acquisition)

    outcomes: tuple[CheckOutcome, ...] = service.check_all()

    assert [outcome.subscription.series for outcome in outcomes] == ["Neko to Ryuu", "Zombie Land"]
    assert [outcome.downloaded for outcome in outcomes] == [0, 1]
    assert outcomes[0].problem == "nyaa did not answer"
    assert outcomes[1].problem == ""


def test_remove_reports_whether_the_subscription_existed(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))

    assert service.remove(subscription.subscription_id) is True
    assert service.remove(subscription.subscription_id) is False
    assert service.list() == ()


def test_subscribe_stores_the_library_folder_and_the_season_numbers(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    context: SeasonContext = SeasonContext(index=2, offset=12, episodes=13)

    subscription: Subscription = service.subscribe(
        "solo leveling subsplease",
        _choice(Decimal(13), reading=EpisodeReading(Decimal(1), absolute=Decimal(13))),
        directory_name="Solo Leveling Season 2",
        context=context,
    )

    assert subscription.next_episode == Decimal(1)
    assert subscription.directory == "Solo Leveling Season 2"
    assert (subscription.season_index, subscription.episode_offset) == (2, 12)
    assert subscription.season_episodes == 13
    assert service.list()[0] == subscription


def test_subscribe_refuses_a_release_of_another_season(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())

    with pytest.raises(ValueError, match="season being followed"):
        service.subscribe("neko", _choice(Decimal(4), reading=EpisodeReading(Decimal(4), other_season=True)))


def test_check_reads_absolute_numbering_and_skips_another_season(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {
            "solo leveling subsplease": _catalog(
                _choice(Decimal(13)),
                _choice(Decimal(3), season=1),
                _choice(Decimal(5)),
            )
        }
    )
    store: SubscriptionStore = _store(tmp_path)
    stored: Subscription = _subscription(
        query="solo leveling subsplease",
        next_episode="1",
        directory="Solo Leveling Season 2",
        season_index=2,
        episode_offset=12,
        season_episodes=13,
    )
    store.save((stored,))
    service: SubscriptionService = _service(tmp_path, acquisition)

    outcome: CheckOutcome = service.check(stored)

    assert [choice.release.info_hash for choice in acquisition.downloaded[0]] == ["SubsPlease-Neko to Ryuu-13-v1"]
    assert acquisition.directories == ["Solo Leveling Season 2"]
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(2)


def test_check_of_a_first_season_still_sends_no_library_folder(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    service.check(service.list()[0])

    assert acquisition.directories == [None]


def test_store_loads_an_entry_written_before_seasons_were_numbered(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 1,
        "subscriptions": [
            {
                "subscription_id": subscription_id("Neko to Ryuu", "SubsPlease"),
                "query": "neko",
                "series": "Neko to Ryuu",
                "group": "SubsPlease",
                "next_episode": "9",
                "min_resolution": MIN_RESOLUTION,
                "taken": [],
                "added_at": _TIMESTAMP,
                "checked_at": None,
            }
        ],
    }
    (tmp_path / "subscriptions.json").write_text(json.dumps(document), encoding="utf-8")

    assert _store(tmp_path).load() == (_subscription(),)


def test_store_round_trip_keeps_the_library_folder_and_the_season_numbers(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    subscription: Subscription = _subscription(
        directory="Solo Leveling Season 2",
        season_index=2,
        episode_offset=12,
        season_episodes=13,
    )

    store.save((subscription,))

    assert store.load() == (subscription,)


def _v1_document(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "subscription_id": subscription_id("Neko to Ryuu", "SubsPlease"),
        "query": "neko",
        "series": "Neko to Ryuu",
        "group": "SubsPlease",
        "next_episode": "9",
        "min_resolution": MIN_RESOLUTION,
        "taken": ["aaa", "bbb"],
        "added_at": _TIMESTAMP,
        "checked_at": None,
        "directory": "Neko to Ryuu",
        "season_index": 1,
        "episode_offset": 0,
        "season_episodes": None,
        "taken_episodes": ["7", "8"],
    }
    entry.update(overrides)
    return {"schema_version": 1, "subscriptions": [entry]}


def _write_v1(tmp_path: Path, **overrides: object) -> Path:
    path: Path = tmp_path / "subscriptions.json"
    path.write_text(json.dumps(_v1_document(**overrides)), encoding="utf-8")
    return path


def test_loading_a_schema_one_file_records_its_taken_episodes_as_handed_over(tmp_path: Path) -> None:
    _write_v1(tmp_path)

    stored: tuple[Subscription, ...] = _store(tmp_path).load()

    assert stored[0].episodes == (
        EpisodeOrder(Decimal(7), state=EpisodeState.ORDERED),
        EpisodeOrder(Decimal(8), state=EpisodeState.ORDERED),
    )
    assert all(episode.info_hash is None for episode in stored[0].episodes)
    assert stored[0].taken_episodes == ("7", "8")
    assert stored[0].taken == frozenset({"aaa", "bbb"})


def test_loading_a_schema_one_file_keeps_a_copy_and_rewrites_it_in_the_current_schema(tmp_path: Path) -> None:
    path: Path = _write_v1(tmp_path)

    _store(tmp_path).load()

    backup: Path = tmp_path / "subscriptions.json.v1.bak"
    assert json.loads(backup.read_text(encoding="utf-8"))["schema_version"] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_loading_a_migrated_file_again_changes_neither_the_file_nor_the_copy(tmp_path: Path) -> None:
    path: Path = _write_v1(tmp_path)
    store: SubscriptionStore = _store(tmp_path)
    backup: Path = tmp_path / "subscriptions.json.v1.bak"
    first: tuple[Subscription, ...] = store.load()
    migrated: bytes = path.read_bytes()
    copied: bytes = backup.read_bytes()

    assert store.load() == first
    assert path.read_bytes() == migrated
    assert backup.read_bytes() == copied


def test_a_schema_one_entry_without_the_optional_fields_migrates_with_the_defaults(tmp_path: Path) -> None:
    document: dict[str, object] = _v1_document()
    entries: object = document["subscriptions"]
    assert isinstance(entries, list)
    entry: dict[str, object] = entries[0]
    for key in ("directory", "season_index", "episode_offset", "season_episodes", "taken_episodes"):
        del entry[key]
    (tmp_path / "subscriptions.json").write_text(json.dumps(document), encoding="utf-8")

    stored: tuple[Subscription, ...] = _store(tmp_path).load()

    assert stored[0] == _subscription(taken=("aaa", "bbb"))
    assert (stored[0].enabled, stored[0].generation, stored[0].anilist_id) == (True, 1, None)
    assert stored[0].end_state is SubscriptionEnd.ACTIVE
    assert stored[0].episodes == ()


def test_store_round_trip_keeps_the_control_fields_and_the_ordered_episodes(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    subscription: Subscription = replace(
        _subscription(taken_episodes=("7",)),
        enabled=False,
        generation=4,
        anilist_id=176496,
        end_state=SubscriptionEnd.COMPLETE,
        episodes=(
            EpisodeOrder(
                number=Decimal("7.5"),
                airing_at=_TIMESTAMP,
                airing_source=AiringSource.ANILIST,
                due_at=_TIMESTAMP,
                window_until=_TIMESTAMP,
                state=EpisodeState.COMPLETE,
                info_hash="aaa",
                acquisition_id="operation-1",
            ),
        ),
        release_delay_s=7200,
        delay_samples_s=(3600, 5400),
    )

    store.save((subscription,))

    assert store.load() == (subscription,)


def test_a_subscription_refuses_more_delay_samples_than_it_keeps() -> None:
    with pytest.raises(ValueError, match="release delays"):
        replace(_subscription(), delay_samples_s=tuple(range(MAX_DELAY_SAMPLES + 1)))


def test_add_orders_the_first_episode_it_is_given(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())

    subscription: Subscription = service.add(
        "Neko to Ryuu",
        "SubsPlease",
        query="neko",
        first_episode=Decimal(9),
        directory_name="Neko to Ryuu",
        anilist_id=176496,
    )

    assert subscription.next_episode == Decimal(9)
    assert subscription.anilist_id == 176496
    assert subscription.directory == "Neko to Ryuu"
    assert subscription.subscription_id == subscription_id("Neko to Ryuu", "SubsPlease")
    assert service.list() == (subscription,)


def test_binding_a_catalog_entry_raises_the_generation_once(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))

    bound: Subscription = service.set_anilist_id(subscription.subscription_id, 176496)
    repeated: Subscription = service.set_anilist_id(subscription.subscription_id, 176496)

    assert (bound.anilist_id, bound.generation) == (176496, 2)
    assert repeated == bound


def test_disabling_twice_writes_once_and_raises_the_generation_once(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))

    disabled: Subscription = service.disable(subscription.subscription_id)
    written: bytes = (tmp_path / "subscriptions.json").read_bytes()
    repeated: Subscription = service.disable(subscription.subscription_id)

    assert (disabled.enabled, disabled.generation) == (False, 2)
    assert repeated == disabled
    assert (tmp_path / "subscriptions.json").read_bytes() == written


def test_enabling_again_keeps_one_entry_with_everything_it_already_took(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    checked: Subscription = service.check(subscription).subscription
    service.disable(subscription.subscription_id)

    enabled: Subscription = service.enable(subscription.subscription_id)

    assert len(service.list()) == 1
    assert enabled.enabled is True
    assert enabled.generation == 3
    assert enabled.taken_episodes == checked.taken_episodes
    assert enabled.taken == checked.taken
    assert enabled.next_episode == checked.next_episode


def test_checking_a_disabled_subscription_reports_it_without_asking_the_source(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    disabled: Subscription = service.disable(subscription.subscription_id)
    acquisition.queries.clear()

    outcome: CheckOutcome = service.check(disabled)

    assert outcome == CheckOutcome(disabled, 0, problem="Subscription is disabled")
    assert acquisition.queries == []


def test_check_all_skips_a_disabled_subscription_without_asking_the_source(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    service.disable(subscription.subscription_id)
    acquisition.queries.clear()

    assert service.check_all() == ()
    assert acquisition.queries == []
    assert acquisition.downloaded == []


def test_check_all_skips_a_finished_subscription(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    store: SubscriptionStore = _store(tmp_path)
    store.save((replace(_subscription(), end_state=SubscriptionEnd.COMPLETE),))
    service: SubscriptionService = _service(tmp_path, acquisition)

    assert service.check_all() == ()
    assert acquisition.queries == []


def test_remove_leaves_every_other_subscription(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9))
    second: Subscription = service.add("Zombie Land", "SubsPlease", query="zombie", first_episode=Decimal(1))

    assert service.remove(first.subscription_id) is True
    assert service.list() == (second,)
