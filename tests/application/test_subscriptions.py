from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

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
from anishift.application.control import AcquisitionConfirmation, AcquisitionState, AutomationPolicy
from anishift.application.intents import RequestOrigin
from anishift.application.subscriptions import (
    MAX_DELAY_SAMPLES,
    SCHEMA_VERSION,
    AiringSource,
    CheckOutcome,
    EpisodeOrder,
    EpisodeState,
    Subscription,
    SubscriptionEnd,
    SubscriptionOrder,
    SubscriptionService,
    SubscriptionStore,
    in_range,
    selectable_episodes,
    subscription_id,
)
from anishift.errors import ConfigError, ErrorCode, ErrorContext, TransientError
from anishift.services.catalog import EpisodeAiring, SeasonAiring, TitleCatalogError, TitleStatus
from anishift.services.torrents import Release, ReleaseName
from anishift.services.torrents.categories import SEARCH_CATEGORIES

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
        self.request_control = None
        self._title_catalog = None
        self.catalogs: dict[str, ReleaseCatalog] = dict(catalogs or {})
        self.failing: frozenset[str] = frozenset(failing)
        self.queries: list[str] = []
        self.downloaded: list[tuple[ReleaseChoice, ...]] = []
        self.queued: set[str] = set()
        self.dropped: set[str] = set()

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> ReleaseCatalog:
        del categories
        self.queries.append(query)
        key: str = query if query in self.catalogs or query in self.failing else query.rsplit(" ", 1)[0]
        if key in self.failing:
            raise _SourceDownError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_SOURCE_FAILED,
                    message="nyaa did not answer",
                    suggestion="Try again later",
                )
            )
        return self.catalogs.get(key, _catalog())

    def download(self, choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        self.downloaded.append(tuple(choices))
        self.queued.update(
            choice.release.info_hash.casefold() for choice in choices if choice.release.info_hash not in self.dropped
        )
        return DownloadReceipt(len(choices), Path("library"))

    def queued_hashes(self) -> frozenset[str]:
        return frozenset(self.queued)


class _CalendarAcquisition(_Acquisition):
    def __init__(self, episodes: tuple[EpisodeAiring, ...], *, count: int | None = 10) -> None:
        super().__init__()
        self.schedule: SeasonAiring = SeasonAiring(1, TitleStatus.RELEASING, count, episodes)
        self.calendar_calls: int = 0
        self.calendar_fails: bool = False

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        assert anilist_id == 1
        self.calendar_calls += 1
        if self.calendar_fails:
            raise TitleCatalogError(
                context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="Calendar unavailable")
            )
        return self.schedule


def _store(tmp_path: Path) -> SubscriptionStore:
    return SubscriptionStore(tmp_path / "subscriptions.json")


def _service(tmp_path: Path, acquisition: _Acquisition, clock: Callable[[], datetime] = _clock) -> SubscriptionService:
    return SubscriptionService(store=_store(tmp_path), acquisition=acquisition, clock=clock, sleep=lambda _: None)


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
        future_from=Decimal(next_episode),
    )


def test_a_future_episode_schedules_calendar_refresh_without_release_search(tmp_path: Path) -> None:
    airing: datetime = _clock() + timedelta(days=1)
    acquisition: _CalendarAcquisition = _CalendarAcquisition((EpisodeAiring(9, airing),))
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()

    assert service.check_due(policy)[0].downloaded == 0
    assert service.next_check_at(policy) == _clock() + timedelta(hours=1)
    assert service.list()[0].episodes[0].due_at == (airing + timedelta(hours=3)).isoformat()
    assert service.check_due(policy) == ()
    assert acquisition.calendar_calls == 1
    assert acquisition.queries == []


def test_unknown_calendar_dates_schedule_bounded_refresh_without_release_queries(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(())
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)

    service.check_due(AutomationPolicy())
    assert service.check_due(AutomationPolicy()) == ()
    assert service.next_check_at(AutomationPolicy()) == _clock() + timedelta(hours=1)
    assert acquisition.calendar_calls == 1
    assert acquisition.queries == []
    moments[0] += timedelta(hours=1)
    airing: datetime = moments[0] + timedelta(days=1)
    acquisition.schedule = replace(acquisition.schedule, episodes=(EpisodeAiring(9, airing),))
    service.check_due(AutomationPolicy())
    assert service.list()[0].episodes[0].airing_at == airing.isoformat()
    assert acquisition.calendar_calls == 2
    assert acquisition.queries == []


@pytest.mark.parametrize("count", [10, None])
def test_confirmed_download_waits_for_bounded_calendar_refresh(tmp_path: Path, count: int | None) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() - timedelta(hours=4)),),
        count=count,
    )
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(9)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()

    assert service.check_due(policy)[0].downloaded == 1
    assert service.next_check_at(policy) == _clock() + timedelta(hours=1)
    assert service.check_due(policy) == ()
    moments[0] += timedelta(hours=1)
    assert service.check_due(policy)[0].downloaded == 0
    assert service.next_check_at(policy) == moments[0] + timedelta(hours=1)
    assert acquisition.calendar_calls == 2
    assert acquisition.queries == ["neko SubsPlease"]


def test_complete_source_finishes_the_order_without_repeating_translation_or_download(tmp_path: Path) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() - timedelta(hours=4)),), count=9
    )
    choice: ReleaseChoice = _choice(Decimal(9))
    acquisition.catalogs["neko"] = _catalog(choice)
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.add(
        "Neko to Ryuu",
        "SubsPlease",
        query="neko",
        first_episode=Decimal(9),
        anilist_id=1,
    )
    service.check_due(AutomationPolicy())
    assert service.list()[0].end_state is SubscriptionEnd.UNCERTAIN
    confirmation: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation",
        choice.release.info_hash,
        "",
        ("episode.mkv",),
        AcquisitionState.COMPLETE,
        RequestOrigin.BACKGROUND,
        subscription.subscription_id,
        "9",
        _TIMESTAMP,
    )

    service.reconcile_sources((confirmation,))
    first: bytes = (tmp_path / "subscriptions.json").read_bytes()
    service.reconcile_sources((confirmation,))

    assert service.list()[0].end_state is SubscriptionEnd.COMPLETE
    assert service.list()[0].episodes[0].state is EpisodeState.COMPLETE
    assert service.check_due(AutomationPolicy()) == ()
    assert len(acquisition.downloaded) == 1
    assert (tmp_path / "subscriptions.json").read_bytes() == first


def test_unbound_subscription_keeps_hourly_checks_without_calendar(tmp_path: Path) -> None:
    now: list[datetime] = [_clock()]
    acquisition: _Acquisition = _Acquisition()
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: now[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9))
    policy: AutomationPolicy = AutomationPolicy()

    assert len(service.check_due(policy)) == 1
    assert service.check_due(policy) == ()
    assert service.next_check_at(policy) == _clock() + timedelta(seconds=60)
    now[0] += timedelta(seconds=60)
    assert len(service.check_due(policy)) == 1
    assert len(acquisition.queries) == 2
    now[0] += timedelta(seconds=300)
    assert len(service.check_due(policy)) == 1
    assert len(acquisition.queries) == 2
    assert service.next_check_at(policy) == _clock() + timedelta(hours=1)
    now[0] += timedelta(hours=8)
    assert len(service.check_due(policy)) == 1
    assert len(acquisition.queries) == 4
    assert service.list()[0].end_state is SubscriptionEnd.ACTIVE


def test_a_postponed_airing_cancels_the_old_release_search(tmp_path: Path) -> None:
    past: datetime = _clock() - timedelta(hours=4)
    future: datetime = _clock() + timedelta(days=7)
    acquisition: _CalendarAcquisition = _CalendarAcquisition((EpisodeAiring(9, future),), count=9)
    service: SubscriptionService = _service(tmp_path, acquisition)
    original: Subscription = replace(
        _subscription(),
        anilist_id=1,
        episodes=(
            EpisodeOrder(
                Decimal(9),
                airing_at=past.isoformat(),
                airing_source=AiringSource.ANILIST,
                due_at=(past + timedelta(hours=3)).isoformat(),
                window_until=(_clock() + timedelta(days=3)).isoformat(),
            ),
        ),
    )
    _store(tmp_path).save((original,))

    service.check_due(AutomationPolicy())

    assert service.next_check_at(AutomationPolicy()) == _clock() + timedelta(days=1)
    assert service.list()[0].episodes[0].due_at == (future + timedelta(hours=3)).isoformat()
    assert acquisition.queries == []


def test_an_expired_episode_does_not_block_a_later_due_episode(tmp_path: Path) -> None:
    now: datetime = _clock()
    moments: list[datetime] = [now - timedelta(days=7)]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (
            EpisodeAiring(9, now - timedelta(days=7)),
            EpisodeAiring(10, now - timedelta(hours=4)),
        )
    )
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(9)), _choice(Decimal(10)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    assert service.check_due(AutomationPolicy())[0].downloaded == 0
    moments[0] = now

    outcome: CheckOutcome = service.check_due(AutomationPolicy())[0]

    assert outcome.downloaded == 1
    assert [choice.episode for batch in acquisition.downloaded for choice in batch] == [Decimal(10)]
    assert [(episode.number, episode.state) for episode in service.list()[0].episodes] == [
        (Decimal(9), EpisodeState.EXPIRED),
        (Decimal(10), EpisodeState.ORDERED),
    ]
    assert acquisition.queries == ["neko SubsPlease"]


def test_an_empty_due_search_waits_an_hour_and_does_not_replay_missed_hours(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() - timedelta(hours=4)),), count=9
    )
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()

    service.check_due(policy)
    assert service.next_check_at(policy) == moments[0] + timedelta(hours=1)
    calls: int = len(acquisition.queries)
    assert service.check_due(policy) == ()
    assert len(acquisition.queries) == calls
    moments[0] += timedelta(hours=8)
    assert len(service.check_due(policy)) == 1
    assert len(acquisition.queries) == calls + 2
    assert service.next_check_at(policy) == moments[0] + timedelta(hours=1)


def test_a_finished_episode_window_stays_finished_after_reload(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock() - timedelta(days=8)]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((EpisodeAiring(9, _clock() - timedelta(days=8)),), count=9)
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)

    service.check_due(AutomationPolicy())
    moments[0] = _clock()
    service.check_due(AutomationPolicy())
    resumed: SubscriptionService = _service(tmp_path, acquisition)

    assert resumed.check_due(AutomationPolicy()) == ()
    assert resumed.next_check_at(AutomationPolicy()) is None
    assert resumed.list()[0].end_state is SubscriptionEnd.MISSING
    assert acquisition.calendar_calls == 2
    assert acquisition.queries == []


def test_calendar_retry_budget_and_deadlines_survive_reload(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=9)
    acquisition.calendar_fails = True
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()

    for delay in (60, 300):
        assert service.check_due(policy)[0].problem
        assert service.next_check_at(policy) == moments[0] + timedelta(seconds=delay)
        assert service.check_due(policy) == ()
        moments[0] += timedelta(seconds=delay)
        service = _service(tmp_path, acquisition, lambda: moments[0])
    assert service.check_due(policy)[0].problem
    assert service.next_check_at(policy) is None
    assert acquisition.calendar_calls == 3
    assert acquisition.queries == []
    assert _store(tmp_path).load()[0].episodes == ()
    assert _store(tmp_path).load()[0].calendar_attempts == 3
    assert _store(tmp_path).load()[0].calendar_problem == ErrorCode.TITLE_CATALOG_FAILED


def test_schema_two_migration_preserves_episode_windows_and_keeps_a_backup(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    original: Subscription = replace(_subscription(), episodes=(EpisodeOrder(Decimal(9), state=EpisodeState.EXPIRED),))
    store.save((original,))
    path: Path = tmp_path / "subscriptions.json"
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    previous: str = path.read_text(encoding="utf-8")

    assert store.load() == (original,)
    assert (tmp_path / "subscriptions.json.v2.bak").read_text(encoding="utf-8") == previous
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


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


def test_adding_the_identified_season_again_keeps_the_switch_and_the_delay_history(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    service.disable(first.subscription_id)
    bound: Subscription = service.set_anilist_id(first.subscription_id, 4242)
    _store(tmp_path).save([replace(bound, release_delay_s=1800, delay_samples_s=(1500, 2100))])

    second: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(12), anilist_id=4242
    )

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

    assert [choice.release.info_hash for batch in acquisition.downloaded for choice in batch] == [
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


def test_check_does_not_replace_a_taken_episode_while_an_earlier_gap_remains(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(10)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))
    service.check(service.list()[0])
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(10), version=2, seeders=100))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 0
    assert len(acquisition.downloaded) == 1
    assert service.list()[0].next_episode == Decimal(9)
    assert service.list()[0].taken_episodes == ("10",)


def test_check_of_a_first_season_rejects_an_explicit_second_season(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9), season=2))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 0
    assert acquisition.downloaded == []


def test_check_rejects_episodes_beyond_the_known_season_length(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(12)), _choice(Decimal(13)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(12)), context=SeasonContext(index=1, offset=0, episodes=12))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 1
    assert [choice.episode for choice in acquisition.downloaded[0]] == [Decimal(12)]


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


def test_check_confirms_an_async_add_without_sending_it_again(tmp_path: Path) -> None:
    choice: ReleaseChoice = _choice(Decimal(9))
    previous: ReleaseChoice = _choice(Decimal(10))
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(choice, previous)})
    acquisition.queued.add(previous.release.info_hash.casefold())
    acquisition.dropped = {choice.release.info_hash}
    delays: list[float] = []

    def wait(delay: float) -> None:
        delays.append(delay)
        acquisition.queued = {choice.release.info_hash.casefold()}

    service: SubscriptionService = SubscriptionService(
        store=_store(tmp_path), acquisition=acquisition, clock=_clock, sleep=wait
    )
    service.subscribe("neko", choice)
    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 1
    assert acquisition.downloaded == [(choice,)]
    assert service.list()[0].taken == frozenset({choice.release.info_hash})
    assert delays == [1.0, 1.0]


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

    assert acquisition.queries == ["neko SubsPlease", "neko 09 SubsPlease"]
    assert outcome.downloaded == 2
    assert service.list()[0].next_episode == Decimal(10)


def test_check_asks_no_second_query_when_the_feed_already_carries_the_episode(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.subscribe("neko", _choice(Decimal(9)))

    service.check(service.list()[0])

    assert acquisition.queries == ["neko SubsPlease"]


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
    assert outcome.downloaded == 1
    assert service.list()[0].next_episode == Decimal(2)


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
    assert subscription.subscription_id != subscription_id("Neko to Ryuu", "SubsPlease")
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


def test_an_older_check_snapshot_cannot_erase_confirmed_episode_history(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(_choice(Decimal(9)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    original: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    assert service.check(original).downloaded == 1
    expected: tuple[Subscription, ...] = service.list()
    acquisition.catalogs.clear()

    stale: CheckOutcome = service.check(original)

    assert stale.downloaded == 0
    assert stale.problem == "Subscription changed during the check"
    assert service.list() == expected


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


@pytest.mark.parametrize("action", ["disable", "remove", "replace", "remove_and_add"])
@pytest.mark.parametrize("has_release", [False, True])
def test_late_search_cannot_override_a_disabled_or_removed_subscription(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    has_release: bool,
) -> None:
    acquisition: _Acquisition = _Acquisition()
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.subscribe("neko", _choice(Decimal(9)))
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    outcomes: list[CheckOutcome] = []

    def search(query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> ReleaseCatalog:
        del query, categories
        entered.set()
        assert release.wait(timeout=5.0)
        return _catalog(_choice(Decimal(9))) if has_release else _catalog()

    monkeypatch.setattr(acquisition, "search", search)
    worker: threading.Thread = threading.Thread(target=lambda: outcomes.append(service.check(subscription)))
    worker.start()
    try:
        assert entered.wait(timeout=2.0)
        if action == "disable":
            service.disable(subscription.subscription_id)
        elif action == "remove":
            service.remove(subscription.subscription_id)
        elif action == "replace":
            service.subscribe("neko", _choice(Decimal(10)))
        else:
            service.remove(subscription.subscription_id)
            service.subscribe("neko", _choice(Decimal(9)))
        expected: tuple[Subscription, ...] = service.list()
    finally:
        release.set()
        worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert service.list() == expected
    assert not acquisition.downloaded
    assert len(outcomes) == 1
    assert outcomes[0].downloaded == 0


@pytest.mark.parametrize("action", ["disable", "remove"])
def test_stopping_a_subscription_during_an_add_prevents_the_next_add(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    first: ReleaseChoice = _choice(Decimal(9))
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(first, _choice(Decimal(10)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    subscription: Subscription = service.subscribe("neko", first)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    outcomes: list[CheckOutcome] = []

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        entered.set()
        assert release.wait(timeout=5.0)
        return _Acquisition.download(acquisition, choices)

    monkeypatch.setattr(acquisition, "download", download)
    worker: threading.Thread = threading.Thread(target=lambda: outcomes.append(service.check(subscription)))
    worker.start()
    try:
        assert entered.wait(timeout=2.0)
        duplicate: CheckOutcome = service.check(subscription)
        if action == "disable":
            service.disable(subscription.subscription_id)
        else:
            service.remove(subscription.subscription_id)
        expected: tuple[Subscription, ...] = service.list()
    finally:
        release.set()
        worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert service.list() == expected
    assert acquisition.downloaded == [(first,)]
    assert duplicate.downloaded == 0
    assert duplicate.problem == "Subscription is already being checked"
    assert len(outcomes) == 1
    assert outcomes[0].downloaded == 1


def _followed(tmp_path: Path, acquisition: _Acquisition, first: Decimal = Decimal(1)) -> SubscriptionService:
    service: SubscriptionService = _service(tmp_path, acquisition)
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=first)
    return service


def _sent(acquisition: _Acquisition) -> list[str]:
    return sorted(str(choice.episode) for call in acquisition.downloaded for choice in call)


def _episodes(service: SubscriptionService) -> dict[Decimal, EpisodeOrder]:
    return {item.number: item for item in service.list()[0].episodes}


def test_a_stored_range_of_two_numbers_downloads_nothing_else(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(*(_choice(Decimal(number)) for number in (3, 4, 8, 9)))})
    service: SubscriptionService = _followed(tmp_path, acquisition)

    service.set_range(service.list()[0].subscription_id, selected=(Decimal(3), Decimal(8)), future_from=None)
    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 2
    assert _sent(acquisition) == ["3", "8"]


def test_a_range_that_starts_in_the_middle_of_the_season_leaves_earlier_episodes_alone(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(*(_choice(Decimal(number)) for number in (5, 6, 7, 8)))})
    service: SubscriptionService = _followed(tmp_path, acquisition)

    service.set_range(service.list()[0].subscription_id, selected=(), future_from=Decimal(7))
    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 2
    assert _sent(acquisition) == ["7", "8"]


def test_every_known_and_future_episode_stays_ordered_when_the_range_is_open(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(*(_choice(Decimal(number)) for number in (1, 2, 3)))})
    service: SubscriptionService = _followed(tmp_path, acquisition)
    identifier: str = service.list()[0].subscription_id

    stored: Subscription = service.set_range(
        identifier, selected=(Decimal(1), Decimal(2), Decimal(3)), future_from=Decimal(1)
    )

    assert in_range(stored, Decimal(2))
    assert in_range(stored, Decimal(40))
    assert service.check(service.list()[0]).downloaded == 3


def test_a_range_that_begins_past_the_season_count_finishes_the_subscription(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition()
    service: SubscriptionService = _service(tmp_path, acquisition)
    stored: Subscription = replace(
        _subscription(next_episode="1", season_episodes=2),
        episodes=(
            EpisodeOrder(Decimal(1), state=EpisodeState.COMPLETE),
            EpisodeOrder(Decimal(2), state=EpisodeState.COMPLETE),
        ),
    )
    _store(tmp_path).save((stored,))

    service.set_range(stored.subscription_id, selected=(Decimal(1), Decimal(2)), future_from=Decimal(3))
    service.reconcile_sources(())

    assert service.list()[0].end_state is SubscriptionEnd.COMPLETE


def test_a_half_episode_keeps_its_own_number_inside_an_open_range(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {"neko": _catalog(_choice(Decimal(7)), _choice(Decimal("7.5"), fraction=True))}
    )
    service: SubscriptionService = _followed(tmp_path, acquisition, Decimal(7))

    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 2
    assert service.list()[0].taken_episodes == ("7", "7.5")
    assert service.list()[0].next_episode == Decimal(8)


def test_a_half_episode_outside_the_range_is_never_ordered(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition(
        {"neko": _catalog(_choice(Decimal(7)), _choice(Decimal("7.5"), fraction=True))}
    )
    service: SubscriptionService = _followed(tmp_path, acquisition, Decimal(7))

    service.set_range(service.list()[0].subscription_id, selected=(Decimal(7),), future_from=None)
    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 1
    assert _sent(acquisition) == ["7"]


def test_deselecting_early_episodes_keeps_their_completion_and_orders_nothing(tmp_path: Path) -> None:
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(*(_choice(Decimal(number)) for number in (1, 7)))})
    service: SubscriptionService = _service(tmp_path, acquisition)
    stored: Subscription = replace(
        _subscription(next_episode="1"),
        episodes=tuple(EpisodeOrder(Decimal(number), state=EpisodeState.COMPLETE) for number in range(1, 7)),
        taken_episodes=tuple(str(number) for number in range(1, 7)),
    )
    _store(tmp_path).save((stored,))

    service.set_range(stored.subscription_id, selected=(), future_from=Decimal(7))
    outcome: CheckOutcome = service.check(service.list()[0])

    assert outcome.downloaded == 1
    assert _sent(acquisition) == ["7"]
    assert all(item.state is EpisodeState.COMPLETE for item in _episodes(service).values() if item.number < 7)
    assert service.list()[0].taken_episodes == tuple(str(number) for number in range(1, 8))


def test_storing_the_same_range_twice_changes_neither_bytes_nor_generation(tmp_path: Path) -> None:
    service: SubscriptionService = _followed(tmp_path, _Acquisition())
    identifier: str = service.list()[0].subscription_id
    first: Subscription = service.set_range(identifier, selected=(Decimal(3),), future_from=None)
    written: bytes = (tmp_path / "subscriptions.json").read_bytes()

    second: Subscription = service.set_range(identifier, selected=(Decimal(3),), future_from=None)

    assert second == first
    assert (tmp_path / "subscriptions.json").read_bytes() == written


def test_a_stored_range_makes_an_older_check_of_the_same_order_stale(tmp_path: Path) -> None:
    service: SubscriptionService = _followed(tmp_path, _Acquisition())
    earlier: Subscription = service.list()[0]

    service.set_range(earlier.subscription_id, selected=(Decimal(3),), future_from=None)

    assert not service.is_current(earlier)
    assert service.is_current(service.list()[0])


def test_an_explicit_repeat_orders_a_finished_number_again_without_erasing_its_history(tmp_path: Path) -> None:
    choice: ReleaseChoice = _choice(Decimal(9))
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(choice)})
    service: SubscriptionService = _service(tmp_path, acquisition)
    stored: Subscription = replace(
        _subscription(next_episode="9", taken=(choice.release.info_hash,), taken_episodes=("9",)),
        episodes=(
            EpisodeOrder(
                Decimal(9),
                state=EpisodeState.COMPLETE,
                info_hash=choice.release.info_hash,
                acquisition_id="operation-1",
            ),
        ),
    )
    _store(tmp_path).save((stored,))

    repeated: Subscription = service.repeat(stored.subscription_id, (Decimal(9),))
    outcome: CheckOutcome = service.check(service.list()[0])

    assert repeated.repeats[0].previous_acquisition_id == "operation-1"
    assert repeated.repeats[0].previous_info_hash == choice.release.info_hash
    assert repeated.episodes[0].repeat_id == repeated.repeats[0].repeat_id
    assert outcome.downloaded == 1
    assert _sent(acquisition) == ["9"]


def test_a_repeat_takes_the_new_confirmation_and_leaves_the_older_one_alone(tmp_path: Path) -> None:
    service: SubscriptionService = _followed(tmp_path, _Acquisition(), Decimal(9))
    identifier: str = service.list()[0].subscription_id
    first: AcquisitionConfirmation = AcquisitionConfirmation(
        "operation-1", "hash-1", "", ("09.mkv",), AcquisitionState.COMPLETE, RequestOrigin.USER, identifier, "9", "old"
    )
    service.reconcile_sources((first,))
    repeated: Subscription = service.repeat(identifier, (Decimal(9),))
    identity: str = repeated.repeats[0].repeat_id
    second: AcquisitionConfirmation = replace(
        first, operation_id="operation-2", info_hash="hash-2", state=AcquisitionState.ACCEPTED, repeat_id=identity
    )

    service.reconcile_sources((first, second))

    episode: EpisodeOrder = _episodes(service)[Decimal(9)]
    assert (episode.acquisition_id, episode.info_hash) == ("operation-2", "hash-2")
    assert episode.state is EpisodeState.ORDERED
    assert episode.repeat_id == identity


def test_a_repeat_keeps_the_same_release_admissible_once_more(tmp_path: Path) -> None:
    choice: ReleaseChoice = _choice(Decimal(9))
    acquisition: _Acquisition = _Acquisition({"neko": _catalog(choice)})
    service: SubscriptionService = _followed(tmp_path, acquisition, Decimal(9))
    identifier: str = service.list()[0].subscription_id
    assert service.check(service.list()[0]).downloaded == 1
    assert service.check(service.list()[0]).downloaded == 0
    acquisition.queued.clear()

    service.repeat(identifier, (Decimal(9),))

    assert service.check(service.list()[0]).downloaded == 1
    assert len(acquisition.downloaded) == 2


def test_selectable_episodes_offers_ordinary_unfinished_numbers_only(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    stored: Subscription = replace(
        _subscription(next_episode="1"),
        episodes=(
            EpisodeOrder(Decimal(1), state=EpisodeState.COMPLETE),
            EpisodeOrder(Decimal(2), state=EpisodeState.PENDING),
            EpisodeOrder(Decimal("2.5"), state=EpisodeState.PENDING),
            EpisodeOrder(Decimal(3), state=EpisodeState.MISSING),
        ),
    )
    _store(tmp_path).save((stored,))

    assert selectable_episodes(service.list()[0]) == (Decimal(2), Decimal(3))


def test_a_schema_three_entry_gains_an_open_range_from_its_cursor(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 3,
        "subscriptions": [
            {
                "subscription_id": subscription_id("Neko to Ryuu", "SubsPlease"),
                "query": "neko",
                "series": "Neko to Ryuu",
                "group": "SubsPlease",
                "next_episode": "9",
                "min_resolution": 1080,
                "taken": ["SubsPlease-Neko to Ryuu-8-v1"],
                "added_at": _TIMESTAMP,
                "checked_at": None,
                "taken_episodes": ["8"],
                "episodes": [
                    {
                        "number": "8",
                        "airing_at": None,
                        "airing_source": None,
                        "due_at": None,
                        "window_until": None,
                        "state": "complete",
                        "info_hash": "SubsPlease-Neko to Ryuu-8-v1",
                        "acquisition_id": "operation-1",
                    }
                ],
            }
        ],
    }
    (tmp_path / "subscriptions.json").write_text(json.dumps(document), encoding="utf-8")
    store: SubscriptionStore = _store(tmp_path)

    stored: Subscription = store.load()[0]

    assert stored.future_from == Decimal(9)
    assert stored.repeats == ()
    assert stored.episodes[0].selected is True
    assert stored.episodes[0].state is EpisodeState.COMPLETE
    assert json.loads((tmp_path / "subscriptions.json").read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION
    assert (tmp_path / "subscriptions.json.v3.bak").is_file()
    assert store.load() == (stored,)


def test_the_stored_range_and_repeats_survive_a_reload(tmp_path: Path) -> None:
    service: SubscriptionService = _followed(tmp_path, _Acquisition(), Decimal(9))
    identifier: str = service.list()[0].subscription_id
    service.set_range(identifier, selected=(Decimal(3), Decimal(9)), future_from=Decimal(12))

    stored: Subscription = service.repeat(identifier, (Decimal(3),))

    assert _store(tmp_path).load() == (stored,)
    assert stored.future_from == Decimal(12)
    assert len(stored.repeats) == 1


def test_fresh_selected_backlog_downloads_before_future_episodes(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        tuple(EpisodeAiring(number, _clock() + timedelta(days=(number - 8) * 7 + 1)) for number in range(1, 13)),
        count=12,
    )
    acquisition.catalogs["neko"] = _catalog(*(_choice(Decimal(number)) for number in range(1, 13)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(2), anilist_id=1)
    service.set_range(
        item.subscription_id, selected=tuple(Decimal(number) for number in range(2, 13)), future_from=None
    )

    assert service.check_due(AutomationPolicy())[0].downloaded == 6
    assert _sent(acquisition) == ["2", "3", "4", "5", "6", "7"]
    service = _service(tmp_path, acquisition, lambda: moments[0])
    assert service.check_due(AutomationPolicy()) == ()
    moments[0] += timedelta(days=1, hours=3)
    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    assert _sent(acquisition) == ["2", "3", "4", "5", "6", "7", "8"]


@pytest.mark.parametrize("excluded", [False, True])
@pytest.mark.parametrize("count", [None, 12])
def test_a_closed_range_never_creates_the_next_episode(tmp_path: Path, count: int | None, *, excluded: bool) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(7, _clock() - timedelta(hours=4)),), count=count
    )
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(7)), _choice(Decimal(8)))
    service: SubscriptionService = _service(tmp_path, acquisition)
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(7), anilist_id=1)
    if excluded:
        service.set_range(item.subscription_id, selected=(Decimal(7), Decimal(8)), future_from=None)
    service.set_range(item.subscription_id, selected=(Decimal(7),), future_from=None)

    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    stored: Subscription = service.list()[0]
    assert not in_range(stored, Decimal(8))
    assert len(stored.episodes) == len({entry.number for entry in stored.episodes})
    assert service.next_check_at(AutomationPolicy()) is None


def test_explicit_fractional_release_without_airing_is_discovered_by_check_due(tmp_path: Path) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal("7.5")), _choice(Decimal(8)))
    service: SubscriptionService = _service(tmp_path, acquisition)
    item: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal("7.5"), anilist_id=1
    )
    service.set_range(item.subscription_id, selected=(Decimal("7.5"),), future_from=None)

    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    assert _sent(acquisition) == ["7.5"]
    assert service.list()[0].episodes[0].airing_at is None
    assert not in_range(service.list()[0], Decimal(8))


def test_calendar_refresh_detects_an_earlier_airing_without_early_release_search(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() + timedelta(days=30)),), count=9
    )
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(9)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()
    service.check_due(policy)
    moments[0] += timedelta(seconds=policy.recheck_interval_s)
    assert service.check_due(policy) == ()
    assert acquisition.calendar_calls == 1
    moments[0] = _clock() + timedelta(days=1)
    changed: datetime = moments[0] + timedelta(hours=1)
    acquisition.schedule = replace(acquisition.schedule, episodes=(EpisodeAiring(9, changed),))

    assert service.check_due(policy)[0].downloaded == 0
    assert service.list()[0].episodes[0].airing_at == changed.isoformat()
    assert acquisition.queries == []
    moments[0] = changed + timedelta(hours=3)
    assert service.check_due(policy)[0].downloaded == 1


@pytest.mark.parametrize("status", [TitleStatus.FINISHED, TitleStatus.CANCELLED])
def test_inactive_unknown_season_keeps_missing_selection_without_polling_a_hypothetical_tail(
    tmp_path: Path, status: TitleStatus
) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    acquisition.schedule = replace(acquisition.schedule, status=status)
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(7), anilist_id=1)
    service.set_range(item.subscription_id, selected=(Decimal(7),), future_from=Decimal(8))
    policy: AutomationPolicy = AutomationPolicy()

    service.check_due(policy)
    assert service.list()[0].end_state is SubscriptionEnd.ACTIVE
    assert service.list()[0].season_episodes is None
    assert set(_episodes(service)) == {Decimal(7)}
    moments[0] += timedelta(seconds=policy.search_window_s)
    service.check_due(policy)
    resumed: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    assert resumed.next_check_at(policy) is None
    assert resumed.list()[0].end_state is SubscriptionEnd.MISSING
    assert _episodes(resumed)[Decimal(7)].state is EpisodeState.EXPIRED
    assert _episodes(resumed)[Decimal(7)].airing_at is None
    assert resumed.check_due(policy) == ()
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(7)))
    resumed.repeat(item.subscription_id, (Decimal(7),))
    assert resumed.check_due(policy)[0].downloaded == 1


def test_an_open_tail_accepts_new_calendar_rows_but_keeps_an_explicit_exclusion(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(7, _clock() - timedelta(hours=4)),), count=None
    )
    acquisition.catalogs["neko"] = _catalog(*(_choice(Decimal(number)) for number in (7, 8, 9)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(7), anilist_id=1)
    service.set_range(item.subscription_id, selected=(Decimal(7), Decimal(8)), future_from=Decimal(8))
    service.set_range(item.subscription_id, selected=(Decimal(7),), future_from=Decimal(8))
    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    moments[0] += timedelta(hours=1)
    acquisition.schedule = replace(
        acquisition.schedule,
        episodes=tuple(EpisodeAiring(number, _clock() - timedelta(hours=4)) for number in (7, 8, 9)),
    )

    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    assert _sent(acquisition) == ["7", "9"]
    assert not _episodes(service)[Decimal(8)].selected


def test_a_repeat_opens_one_fresh_window_and_replaying_its_command_preserves_consumed_attempts(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() - timedelta(days=30)),), count=9
    )
    acquisition.failing = frozenset({"neko"})
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    policy: AutomationPolicy = AutomationPolicy()
    for delay in (60, 300, 0):
        assert service.check_due(policy)[0].problem
        moments[0] += timedelta(seconds=delay)
    assert service.next_check_at(policy) is None
    assert _episodes(service)[Decimal(9)].attempts == 3
    service = _service(tmp_path, acquisition, lambda: moments[0])
    assert service.check_due(policy) == ()
    repeated: Subscription = service.repeat(item.subscription_id, (Decimal(9),), command_id="repeat-command")
    assert service.check_due(policy)[0].problem
    failed: Subscription = service.list()[0]

    assert service.repeat(item.subscription_id, (Decimal(9),), command_id="repeat-command") == failed
    assert _episodes(service)[Decimal(9)].attempts == 1
    assert len(failed.repeats) == 1
    assert (
        _episodes(service)[Decimal(9)].window_until
        == (
            datetime.fromisoformat(repeated.repeats[0].requested_at) + timedelta(seconds=policy.search_window_s)
        ).isoformat()
    )


def test_old_schema_four_records_do_not_gain_a_fresh_intent_or_reset_their_window(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    old: Subscription = replace(
        _subscription(),
        anilist_id=1,
        episodes=(EpisodeOrder(Decimal(9), state=EpisodeState.EXPIRED, attempts=3),),
    )
    store.save((old,))
    path: Path = tmp_path / "subscriptions.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    entry: dict[str, Any] = document["subscriptions"][0]
    for key in ("calendar_checked_at", "calendar_attempts", "calendar_status"):
        del entry[key]
    del entry["episodes"][0]["requested_at"]
    path.write_text(json.dumps(document), encoding="utf-8")

    assert store.load() == (old,)
    assert store.load()[0].episodes[0].requested_at is None
    assert store.load()[0].episodes[0].attempts == 3


@pytest.mark.parametrize("value", ["2026-09-06T12:00:00", "invalid", 42])
def test_fresh_intent_timestamps_require_an_aware_valid_date(tmp_path: Path, value: object) -> None:
    store: SubscriptionStore = _store(tmp_path)
    store.save((replace(_subscription(), episodes=(EpisodeOrder(Decimal(9)),)),))
    path: Path = tmp_path / "subscriptions.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    document["subscriptions"][0]["episodes"][0]["requested_at"] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ConfigError):
        store.load()


def test_another_explicit_season_cannot_overwrite_the_first_alias_and_group(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.add(
        "Neko to Ryuu",
        "SubsPlease",
        query="first",
        first_episode=Decimal(1),
        context=SeasonContext(1, 0, 12),
        anilist_id=101,
    )
    second: Subscription = service.add(
        "Neko to Ryuu",
        "SubsPlease",
        query="second",
        first_episode=Decimal(1),
        context=SeasonContext(2, 12, 12),
        anilist_id=202,
    )
    assert len(service.list()) == 2
    assert first in service.list()
    assert second.subscription_id != first.subscription_id
    assert second.season_index == 2
    assert second.episode_offset == 12


def test_a_first_calendar_failure_does_not_expire_the_fresh_backlog_after_recovery(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        (EpisodeAiring(9, _clock() - timedelta(days=30)),), count=9
    )
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(9)))
    acquisition.calendar_fails = True
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(9), anilist_id=1)
    assert service.check_due(AutomationPolicy())[0].problem
    moments[0] += timedelta(seconds=60)
    acquisition.calendar_fails = False

    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    assert _sent(acquisition) == ["9"]


def test_old_unknown_season_retry_exhaustion_does_not_gain_a_new_calendar_budget(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    store.save(
        (
            replace(
                _subscription(),
                anilist_id=1,
                episodes=(EpisodeOrder(Decimal(9), state=EpisodeState.MISSING, attempts=3),),
            ),
        )
    )
    path: Path = tmp_path / "subscriptions.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    entry: dict[str, Any] = document["subscriptions"][0]
    for key in ("calendar_checked_at", "calendar_attempts", "calendar_status"):
        del entry[key]
    path.write_text(json.dumps(document), encoding="utf-8")
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    service: SubscriptionService = _service(tmp_path, acquisition)

    assert service.list()[0].calendar_attempts == 3
    assert service.next_check_at(AutomationPolicy()) is None
    assert service.check_due(AutomationPolicy()) == ()
    assert acquisition.calendar_calls == 0


def test_an_upcoming_full_card_waits_for_individual_airings_before_opening_windows(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    start: datetime = _clock() + timedelta(days=40)
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=12)
    acquisition.schedule = replace(acquisition.schedule, status=TitleStatus.NOT_YET_RELEASED, start_date=start.date())
    acquisition.catalogs["neko"] = _catalog(*(_choice(Decimal(number)) for number in range(1, 13)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(1), anilist_id=1)
    service.set_range(
        item.subscription_id, selected=tuple(Decimal(number) for number in range(1, 13)), future_from=None
    )
    service.check_due(AutomationPolicy())
    assert acquisition.queries == []
    moments[0] += timedelta(hours=73)
    service.check_due(AutomationPolicy())
    assert all(entry.state is EpisodeState.PENDING for entry in service.list()[0].episodes)
    moments[0] = start
    acquisition.schedule = replace(acquisition.schedule, status=TitleStatus.RELEASING)
    service.check_due(AutomationPolicy())
    assert acquisition.queries == []
    moments[0] += timedelta(hours=4)
    acquisition.schedule = replace(acquisition.schedule, episodes=(EpisodeAiring(1, start),))
    assert service.check_due(AutomationPolicy())[0].downloaded == 1
    assert _sent(acquisition) == ["1"]
    assert all(entry.window_until is None for entry in service.list()[0].episodes if entry.number > 1)


def test_calendar_failures_do_not_spend_release_attempts_or_block_verified_backlog(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition(
        tuple(EpisodeAiring(number, _clock() - timedelta(days=30)) for number in range(2, 8)), count=12
    )
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(2), anilist_id=1)
    service.set_range(item.subscription_id, selected=tuple(Decimal(number) for number in range(2, 9)), future_from=None)
    service.check_due(AutomationPolicy())
    acquisition.calendar_fails = True
    acquisition.catalogs["neko"] = _catalog(*(_choice(Decimal(number)) for number in range(2, 8)))
    moments[0] += timedelta(hours=1)
    assert service.check_due(AutomationPolicy())[0].downloaded == 6
    for delay in (60, 300):
        moments[0] += timedelta(seconds=delay)
        service.check_due(AutomationPolicy())
    assert service.list()[0].calendar_attempts == 3
    assert all(entry.attempts == 0 for entry in service.list()[0].episodes)
    assert _sent(acquisition) == ["2", "3", "4", "5", "6", "7"]


def test_reincluding_a_known_pending_number_rearms_calendar_recovery_once(tmp_path: Path) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition((EpisodeAiring(5, _clock() - timedelta(days=7)),), count=5)
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(5)))
    service: SubscriptionService = _service(tmp_path, acquisition)
    item: Subscription = replace(
        _subscription(next_episode="5"),
        anilist_id=1,
        future_from=None,
        calendar_attempts=3,
        episodes=(EpisodeOrder(Decimal(5), selected=False),),
    )
    _store(tmp_path).save((item,))
    unchanged: Subscription = service.set_range(item.subscription_id, selected=(), future_from=None)
    assert unchanged.calendar_attempts == 3
    included: Subscription = service.set_range(item.subscription_id, selected=(Decimal(5),), future_from=None)
    assert included.calendar_attempts == 0
    assert service.set_range(item.subscription_id, selected=(Decimal(5),), future_from=None) == included
    assert service.check_due(AutomationPolicy())[0].downloaded == 1


def test_manual_calendar_recovery_performs_one_attempt_without_rearming_automatic_failures(tmp_path: Path) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    acquisition.calendar_fails = True
    item: Subscription = replace(
        _subscription(),
        anilist_id=1,
        calendar_attempts=3,
        episodes=(EpisodeOrder(Decimal(9), checked_at=_TIMESTAMP),),
    )
    _store(tmp_path).save((item,))
    service: SubscriptionService = _service(tmp_path, acquisition)

    assert service.check_due(AutomationPolicy(), refresh_calendar=True)[0].problem
    assert acquisition.calendar_calls == 1
    assert service.list()[0].calendar_attempts == 4
    assert service.check_due(AutomationPolicy()) == ()


def test_distinct_catalog_seasons_share_an_alias_without_sharing_history(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="first", first_episode=Decimal(1), anilist_id=101
    )
    _store(tmp_path).save((replace(first, taken=frozenset({"first-hash"}), taken_episodes=("1",)),))
    second: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="second", first_episode=Decimal(1), anilist_id=202
    )

    assert second.subscription_id != first.subscription_id
    assert len(service.list()) == 2
    assert second.taken == frozenset()
    assert next(entry for entry in service.list() if entry.anilist_id == 101).taken == frozenset({"first-hash"})


def test_raw_fallback_cannot_replace_an_identified_season(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    first: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="first", first_episode=Decimal(1), anilist_id=101
    )

    with pytest.raises(ValueError, match="ambiguous"):
        service.add("Neko to Ryuu", "SubsPlease", query="second season", first_episode=Decimal(1))
    assert service.list() == (first,)


@pytest.mark.parametrize("count", [12, None])
def test_hiatus_keeps_future_intent_and_observes_resumption_without_reviving_expired_work(
    tmp_path: Path, count: int | None
) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=count)
    acquisition.schedule = replace(acquisition.schedule, status=TitleStatus.HIATUS)
    expired: EpisodeOrder = EpisodeOrder(Decimal(6), state=EpisodeState.EXPIRED, attempts=3)
    stored: Subscription = replace(
        _subscription(next_episode="7"),
        anilist_id=1,
        episodes=(expired, EpisodeOrder(Decimal(7), requested_at=_TIMESTAMP)),
        future_from=Decimal(8),
    )
    _store(tmp_path).save((stored,))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    policy: AutomationPolicy = AutomationPolicy()

    service.check_due(policy)
    assert acquisition.queries == []
    assert service.list()[0].future_from == Decimal(8)
    assert service.next_check_at(policy) == _clock() + timedelta(days=1)
    moments[0] += timedelta(days=4)
    service = _service(tmp_path, acquisition, lambda: moments[0])
    service.check_due(policy)
    assert _episodes(service)[Decimal(7)].state is EpisodeState.PENDING
    assert _episodes(service)[Decimal(7)].window_until is None
    assert _episodes(service)[Decimal(6)] == expired
    acquisition.schedule = replace(
        acquisition.schedule,
        status=TitleStatus.RELEASING,
        episodes=tuple(EpisodeAiring(number, moments[0] - timedelta(hours=4)) for number in (6, 7, 8)),
    )
    acquisition.catalogs["neko"] = _catalog(*(_choice(Decimal(number)) for number in (6, 7, 8)))
    moments[0] += timedelta(days=1)
    assert service.check_due(policy)[0].downloaded == 2
    assert _sent(acquisition) == ["7", "8"]
    assert _episodes(service)[Decimal(6)] == expired


def test_unknown_calendar_failure_keeps_visible_independent_bounded_discovery_across_restart(tmp_path: Path) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    acquisition.calendar_fails = True
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(7), anilist_id=1)
    service.set_range(item.subscription_id, selected=(Decimal("7.5"),), future_from=None)
    policy: AutomationPolicy = AutomationPolicy()

    for delay in (60, 300, 0):
        assert service.check_due(policy)[0].problem == ErrorCode.TITLE_CATALOG_FAILED
        moments[0] += timedelta(seconds=delay)
    service = _service(tmp_path, acquisition, lambda: moments[0])
    assert service.list()[0].calendar_attempts == 3
    assert service.list()[0].calendar_problem == ErrorCode.TITLE_CATALOG_FAILED
    assert service.list()[0].episodes[0].attempts == 0
    assert service.list()[0].episodes[0].airing_at is None
    assert acquisition.queries == ["neko SubsPlease"]
    moments[0] = _clock() + timedelta(hours=72)
    service.check_due(policy)
    assert service.list()[0].episodes[0].state is EpisodeState.EXPIRED
    assert service.next_check_at(policy) is None
    assert acquisition.calendar_calls == 3


@pytest.mark.parametrize("prior_problem", [None, ErrorCode.TITLE_CATALOG_FAILED])
def test_manual_calendar_recovery_respects_provider_cooldown_without_spending_a_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior_problem: str | None
) -> None:
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=None)
    service: SubscriptionService = _service(tmp_path, acquisition)
    item: Subscription = replace(
        _subscription(),
        anilist_id=1,
        calendar_attempts=3,
        calendar_problem=prior_problem,
        episodes=(EpisodeOrder(Decimal(9), checked_at=_TIMESTAMP),),
    )
    _store(tmp_path).save((item,))
    monkeypatch.setattr(acquisition, "blocked_until", lambda _providers: (_clock() + timedelta(hours=1)).timestamp())

    assert service.check_due(AutomationPolicy(), refresh_calendar=True)[0].problem == "calendar_cooldown"
    assert service.list()[0].calendar_attempts == 3
    assert service.list()[0].calendar_problem == prior_problem
    assert acquisition.calendar_calls == 0
    assert acquisition.queries == []


def test_new_catalog_season_ids_are_independent_of_admission_order(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path / "first", _Acquisition())
    other: SubscriptionService = _service(tmp_path / "second", _Acquisition())
    for identifier in (101, 202):
        service.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(1), anilist_id=identifier)
    for identifier in (202, 101):
        other.add("Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(1), anilist_id=identifier)

    assert {item.anilist_id: item.subscription_id for item in service.list()} == {
        item.anilist_id: item.subscription_id for item in other.list()
    }
    assert all(item.subscription_id != subscription_id(item.series, item.group) for item in service.list())


def test_late_binding_keeps_the_accepted_identity_and_replay_does_not_overwrite_its_history(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    raw: SubscriptionOrder = SubscriptionOrder("Neko to Ryuu", "SubsPlease", "neko", Decimal(1))
    first: Subscription = service.add_order(raw, "accepted-raw")
    bound: Subscription = service.set_anilist_id(first.subscription_id, 101)
    stored: Subscription = replace(bound, taken=frozenset({"kept-hash"}), taken_episodes=("1",))
    _store(tmp_path).save((stored,))

    assert service.add_order(raw, "accepted-raw", accepted_id=first.subscription_id) == stored
    matching: Subscription = service.add_order(replace(raw, anilist_id=101), "new-known")
    assert matching.subscription_id == first.subscription_id
    assert matching.taken == stored.taken
    assert matching.taken_episodes == stored.taken_episodes
    assert len(service.list()) == 1


def test_an_older_unapplied_receipt_keeps_its_reserved_catalog_identity(tmp_path: Path) -> None:
    service: SubscriptionService = _service(tmp_path, _Acquisition())
    order: SubscriptionOrder = SubscriptionOrder("Neko to Ryuu", "SubsPlease", "neko", Decimal(1), anilist_id=101)
    reserved: str = subscription_id(order.series, order.group)

    applied: Subscription = service.add_order(order, "older-receipt", accepted_id=reserved)
    assert applied.subscription_id == reserved
    assert service.add_order(order, "older-receipt", accepted_id=reserved) == applied


@pytest.mark.parametrize("status", [TitleStatus.CANCELLED, TitleStatus.FINISHED])
def test_an_ended_calendar_does_not_admit_previously_unreleased_numbers(tmp_path: Path, status: TitleStatus) -> None:
    moments: list[datetime] = [_clock()]
    acquisition: _CalendarAcquisition = _CalendarAcquisition((), count=12)
    acquisition.schedule = replace(acquisition.schedule, status=TitleStatus.NOT_YET_RELEASED)
    acquisition.catalogs["neko"] = _catalog(_choice(Decimal(12)))
    service: SubscriptionService = _service(tmp_path, acquisition, lambda: moments[0])
    item: Subscription = service.add(
        "Neko to Ryuu", "SubsPlease", query="neko", first_episode=Decimal(12), anilist_id=1
    )
    service.set_range(item.subscription_id, selected=(Decimal(12),), future_from=None)
    service.check_due(AutomationPolicy())
    moments[0] += timedelta(days=1)
    acquisition.schedule = replace(acquisition.schedule, status=status)

    service.check_due(AutomationPolicy())
    assert acquisition.queries == []
    assert service.list()[0].episodes[0].state is EpisodeState.MISSING
    assert service.list()[0].episodes[0].window_until is None
    assert service.next_check_at(AutomationPolicy()) is None
