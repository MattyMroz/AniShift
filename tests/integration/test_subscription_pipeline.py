from __future__ import annotations

from decimal import Decimal

import pytest
from harness import Composed, composed_fixture  # noqa: F401

from anishift.application.acquisition import DOWNLOAD_CATEGORY, INCOMPLETE_EXTENSION_PREFERENCE, ReleaseChoice
from anishift.errors import ErrorCode
from anishift.services.torrents import TorrentClientError, parse_release_name
from anishift.services.torrents.categories import CATEGORY_ENGLISH_TRANSLATED

FOLLOWED_QUERY = "Solo Leveling SubsPlease"
LIBRARY_DIRECTORY = "Solo Leveling"
LISTED_FIRST_SEASON_EPISODES = 25
LISTED_SECOND_SEASON_EPISODES = 13


def _first_season_choice(composed: Composed) -> ReleaseChoice:
    found = composed.resolve("solo leveling 1", "Ore dake Level Up na Ken")
    (subsplease,) = found.groups_of("SubsPlease")
    return subsplease.choices[0]


def test_the_client_reports_its_version_and_takes_the_incomplete_extension_preference(composed: Composed) -> None:
    status = composed.acquisition.setup_client()

    assert status.reachable
    assert status.version == "5.2.3"
    assert status.incomplete_extension
    assert composed.client.settings[INCOMPLETE_EXTENSION_PREFERENCE] is True


def test_following_the_first_season_downloads_every_listed_episode_into_the_library_folder(
    composed: Composed,
) -> None:
    subscription = composed.subscriptions.subscribe(
        FOLLOWED_QUERY, _first_season_choice(composed), directory_name=LIBRARY_DIRECTORY
    )

    outcome = composed.subscriptions.check(subscription)

    assert outcome.problem == ""
    assert outcome.downloaded == LISTED_FIRST_SEASON_EPISODES
    assert outcome.subscription.taken == {torrent.info_hash for torrent in composed.client.added}
    assert {torrent.category for torrent in composed.client.added} == {DOWNLOAD_CATEGORY}
    assert all(torrent.save_path.endswith(LIBRARY_DIRECTORY) for torrent in composed.client.added)
    assert all(torrent.title.startswith("[SubsPlease] Solo Leveling - ") for torrent in composed.client.added)


def test_following_a_series_waits_for_an_episode_the_feed_of_the_group_never_listed(composed: Composed) -> None:
    subscription = composed.subscriptions.subscribe(
        FOLLOWED_QUERY, _first_season_choice(composed), directory_name=LIBRARY_DIRECTORY
    )

    outcome = composed.subscriptions.check(subscription)

    printed = [parse_release_name(torrent.title).episode for torrent in composed.client.added]
    assert Decimal(1) not in printed
    assert Decimal("7.5") in printed
    assert outcome.subscription.next_episode == Decimal(1)
    assert (FOLLOWED_QUERY + " 01", CATEGORY_ENGLISH_TRANSLATED) in composed.nyaa_queries


def test_a_second_check_of_a_followed_series_downloads_nothing_more(composed: Composed) -> None:
    subscription = composed.subscriptions.subscribe(
        FOLLOWED_QUERY, _first_season_choice(composed), directory_name=LIBRARY_DIRECTORY
    )
    first = composed.subscriptions.check(subscription)

    second = composed.subscriptions.check(first.subscription)

    assert second.downloaded == 0
    assert second.problem == ""
    assert second.subscription.next_episode == first.subscription.next_episode
    assert len(composed.client.added) == LISTED_FIRST_SEASON_EPISODES


def test_following_the_second_season_never_downloads_a_first_season_episode(composed: Composed) -> None:
    found = composed.resolve("solo leveling season 2 1", "Arise from the Shadow")
    (subsplease,) = found.groups_of("SubsPlease")
    subscription = composed.subscriptions.subscribe(
        FOLLOWED_QUERY, subsplease.choices[0], directory_name=LIBRARY_DIRECTORY, context=found.context
    )

    outcome = composed.subscriptions.check(subscription)

    assert outcome.downloaded == LISTED_SECOND_SEASON_EPISODES
    assert outcome.subscription.next_episode == Decimal(14)
    printed = [parse_release_name(torrent.title).episode for torrent in composed.client.added]
    assert printed
    assert min(number for number in printed if number is not None) == Decimal(13)


def test_a_refused_torrent_reports_the_client_refusal_code(composed: Composed) -> None:
    choice = _first_season_choice(composed)
    composed.client.refuse = True

    with pytest.raises(TorrentClientError) as refusal:
        composed.acquisition.download((choice,), directory_name=LIBRARY_DIRECTORY)

    assert refusal.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED


def test_a_refused_torrent_leaves_the_stored_subscription_untouched(composed: Composed) -> None:
    subscription = composed.subscriptions.subscribe(
        FOLLOWED_QUERY, _first_season_choice(composed), directory_name=LIBRARY_DIRECTORY
    )
    composed.client.refuse = True

    outcome = composed.subscriptions.check(subscription)

    assert outcome.downloaded == 0
    assert outcome.problem == "qBittorrent refused the torrent"
    assert composed.client.added == []
    assert composed.store.load() == (subscription,)
