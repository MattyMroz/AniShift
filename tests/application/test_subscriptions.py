from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from anishift.application.acquisition import (
    MIN_RESOLUTION,
)
from anishift.application.subscriptions import (
    MAX_DELAY_SAMPLES,
    SCHEMA_VERSION,
    AiringSource,
    EpisodeOrder,
    EpisodeState,
    Subscription,
    SubscriptionEnd,
    SubscriptionStore,
)
from anishift.errors import ConfigError, ErrorCode

_TIMESTAMP: str = "2026-09-06T12:00:00+00:00"
_NEKO_ID: str = "Neko to Ryuu|SubsPlease"


def _store(tmp_path: Path) -> SubscriptionStore:
    return SubscriptionStore(tmp_path / "subscriptions.json")


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
        subscription_id=f"{series}|{group}",
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


def test_store_loads_an_entry_written_before_taken_episodes_were_recorded(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 1,
        "subscriptions": [
            {
                "subscription_id": _NEKO_ID,
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


def test_store_loads_an_entry_written_before_seasons_were_numbered(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 1,
        "subscriptions": [
            {
                "subscription_id": _NEKO_ID,
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
        "subscription_id": _NEKO_ID,
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


def test_a_schema_three_entry_gains_an_open_range_from_its_cursor(tmp_path: Path) -> None:
    document: dict[str, object] = {
        "schema_version": 3,
        "subscriptions": [
            {
                "subscription_id": _NEKO_ID,
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
