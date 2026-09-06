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
    ReleaseCatalog,
    ReleaseChoice,
    SeriesGroup,
)
from anishift.application.subscriptions import (
    CheckOutcome,
    Subscription,
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


def _choice(
    episode: Decimal | None,
    *,
    series: str = "Neko to Ryuu",
    group: str = "SubsPlease",
    version: int | None = None,
    seeders: int = 10,
) -> ReleaseChoice:
    name: ReleaseName = replace(_BASE_NAME, series=series, group=group, episode=episode, version=version)
    label: str = f"{group}-{series}-{episode}-v{version or 1}"
    release: Release = Release(
        title=f"[{group}] {series} - {episode}",
        torrent_url=f"https://nyaa.si/download/{label}.torrent",
        info_hash=label,
        seeders=seeders,
        size_text="1.0 GiB",
        published=None,
    )
    return ReleaseChoice(release, name)


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

    def download(self, choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        self.downloaded.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("library"))


def _store(tmp_path: Path) -> SubscriptionStore:
    return SubscriptionStore(tmp_path / "subscriptions.json")


def _service(tmp_path: Path, acquisition: _Acquisition) -> SubscriptionService:
    return SubscriptionService(store=_store(tmp_path), acquisition=acquisition, clock=_clock)


def _subscription(
    *,
    series: str = "Neko to Ryuu",
    group: str = "SubsPlease",
    query: str = "neko",
    next_episode: str = "9",
    taken: Sequence[str] = (),
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
    )


def test_store_round_trip_keeps_fractional_episodes_and_taken_hashes(tmp_path: Path) -> None:
    store: SubscriptionStore = _store(tmp_path)
    subscription: Subscription = _subscription(next_episode="7.5", taken=("aaa", "bbb"))

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
        json.dumps({"schema_version": 2, "subscriptions": []}), encoding="utf-8"
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
