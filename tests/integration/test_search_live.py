from __future__ import annotations

import httpx
import pytest

from anishift.services.catalog import AniListCatalog
from anishift.services.torrents import search_releases

pytestmark = pytest.mark.network


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
