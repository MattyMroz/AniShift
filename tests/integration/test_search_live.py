from __future__ import annotations

import httpx
import pytest

from anishift.application.episode_selection import AniZipMapping, FranchiseGraph, StreamCandidate
from anishift.services.catalog import AniListCatalog, AniZipCatalog
from anishift.services.torrents import TorrentioSource, search_releases

pytestmark = pytest.mark.network


@pytest.mark.integration
def test_anizip_live_slime_mapping_has_local_episodes() -> None:
    with httpx.Client() as http:
        mapping: AniZipMapping = AniZipCatalog(http).mapping(101280)
    assert mapping.kitsu_id == 41024
    assert any(episode.number == 4 for episode in mapping.episodes)


@pytest.mark.integration
def test_torrentio_live_slime_episode_has_file_candidates() -> None:
    with httpx.Client() as http:
        streams: tuple[StreamCandidate, ...] = TorrentioSource(http).streams(41024, 4)
    assert streams
    assert all(len(stream.info_hash) == 40 for stream in streams)


@pytest.mark.integration
def test_anilist_live_slime_franchise_completes_in_budget() -> None:
    with httpx.Client() as http:
        graph: FranchiseGraph = AniListCatalog(http).franchise(101280)
    assert graph.complete
    assert {101280, 106509, 116741} <= set(graph.nodes)


def test_anilist_still_answers_the_title_search_with_usable_candidates() -> None:
    with httpx.Client(follow_redirects=True) as http:
        candidates = AniListCatalog(http).search("solo leveling")

    assert candidates
    assert all(candidate.anilist_id > 0 for candidate in candidates)
    assert all(candidate.romaji for candidate in candidates)


def test_nyaa_still_answers_the_release_search_with_usable_releases() -> None:
    with httpx.Client(follow_redirects=True) as http:
        releases = search_releases("Solo Leveling", http=http)

    assert releases
    assert all(release.title for release in releases)
    assert all(release.info_hash for release in releases)
    assert all(release.torrent_url.startswith("https://nyaa.si/") for release in releases)
