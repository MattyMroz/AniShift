from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.nyaa import (
    CATEGORY_ENGLISH_TRANSLATED,
    CATEGORY_NON_ENGLISH_TRANSLATED,
    MAX_BODY_BYTES,
    USER_AGENT,
    parse_feed,
    search_releases,
)
from anishift.services.torrents.types import Release

_FEED: Final[str] = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
<channel>
<title>Nyaa - Home - Torrent File RSS</title>
<link>https://nyaa.si/</link>
<item>
<title>[DKB] Neko to Ryuu - S01E11 [1080p][HEVC x265 10bit][Multi-Subs][weekly]</title>
<link>https://nyaa.si/download/2156981.torrent</link>
<guid isPermaLink="true">https://nyaa.si/view/2156981</guid>
<pubDate>Sat, 05 Sep 2026 19:51:11 -0000</pubDate>
<nyaa:seeders>66</nyaa:seeders>
<nyaa:leechers>6</nyaa:leechers>
<nyaa:downloads>144</nyaa:downloads>
<nyaa:infoHash>b456eb3845297c1c99cd359274981ae904328084</nyaa:infoHash>
<nyaa:categoryId>1_2</nyaa:categoryId>
<nyaa:category>Anime - English-translated</nyaa:category>
<nyaa:size>261.2 MiB</nyaa:size>
<nyaa:comments>0</nyaa:comments>
<nyaa:trusted>No</nyaa:trusted>
<nyaa:remake>No</nyaa:remake>
<description><![CDATA[<a href="https://nyaa.si/view/2156981">#2156981</a> | 261.2 MiB]]></description>
</item>
<item>
<title>[NoHash] Neko to Ryuu - 12 (1080p)</title>
<link>https://nyaa.si/download/2156982.torrent</link>
<pubDate>Sat, 05 Sep 2026 20:00:00 -0000</pubDate>
<nyaa:seeders>12</nyaa:seeders>
<nyaa:size>300.0 MiB</nyaa:size>
</item>
<item>
<title>[NoLink] Neko to Ryuu - 13 (1080p)</title>
<pubDate>Sat, 05 Sep 2026 21:00:00 -0000</pubDate>
<nyaa:seeders>3</nyaa:seeders>
<nyaa:infoHash>aaaaeb3845297c1c99cd359274981ae904328084</nyaa:infoHash>
<nyaa:size>310.0 MiB</nyaa:size>
</item>
<item>
<title>[SubsPlease] Oshi no Ko S3 (01-11) (1080p) [Batch]</title>
<link>https://nyaa.si/download/2156983.torrent</link>
<pubDate>not a date</pubDate>
<nyaa:seeders>unknown</nyaa:seeders>
<nyaa:infoHash>c789eb3845297c1c99cd359274981ae904328084</nyaa:infoHash>
<nyaa:size>3.4 GiB</nyaa:size>
</item>
</channel>
</rss>
"""


_FRENCH_FEED: Final[str] = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
<channel>
<item>
<title>[DKB] Neko to Ryuu - S01E11 [1080p][HEVC x265 10bit][Multi-Subs][weekly]</title>
<link>https://nyaa.si/download/2156981.torrent</link>
<pubDate>Sat, 05 Sep 2026 19:51:11 -0000</pubDate>
<nyaa:seeders>4</nyaa:seeders>
<nyaa:infoHash>B456EB3845297C1C99CD359274981AE904328084</nyaa:infoHash>
<nyaa:size>261.2 MiB</nyaa:size>
</item>
<item>
<title>Neko to Ryuu S01E12 SUBFRENCH 1080p CR WEB-DL AAC2.0 H.264-Tsundere-Raws</title>
<link>https://nyaa.si/download/2156990.torrent</link>
<pubDate>Sat, 05 Sep 2026 22:00:00 -0000</pubDate>
<nyaa:seeders>9</nyaa:seeders>
<nyaa:infoHash>d123eb3845297c1c99cd359274981ae904328084</nyaa:infoHash>
<nyaa:size>1.2 GiB</nyaa:size>
</item>
<item>
<title>Neko to Ryuu S01E13 1080p WEB-DL H.264-Anon</title>
<link>https://nyaa.si/download/2156991.torrent</link>
<pubDate>Sat, 05 Sep 2026 23:00:00 -0000</pubDate>
<nyaa:seeders>2</nyaa:seeders>
<nyaa:infoHash>e456eb3845297c1c99cd359274981ae904328084</nyaa:infoHash>
<nyaa:size>1.3 GiB</nyaa:size>
</item>
</channel>
</rss>
"""


def _category_handler(request: httpx.Request) -> httpx.Response:
    body: str = _FEED if request.url.params["c"] == CATEGORY_ENGLISH_TRANSLATED else _FRENCH_FEED
    return httpx.Response(200, text=body, headers={"content-type": "application/xml; charset=UTF-8"})


def _feed_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _xml_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=_FEED, headers={"content-type": "application/xml; charset=UTF-8"})


def test_parse_feed_reads_every_field_of_a_complete_item() -> None:
    releases: tuple[Release, ...] = parse_feed(_FEED)
    first: Release = releases[0]
    assert first.title == "[DKB] Neko to Ryuu - S01E11 [1080p][HEVC x265 10bit][Multi-Subs][weekly]"
    assert first.torrent_url == "https://nyaa.si/download/2156981.torrent"
    assert first.info_hash == "b456eb3845297c1c99cd359274981ae904328084"
    assert first.seeders == 66
    assert first.size_text == "261.2 MiB"
    assert first.published == datetime(2026, 9, 5, 19, 51, 11, tzinfo=UTC)


def test_parse_feed_skips_items_without_info_hash_or_link() -> None:
    releases: tuple[Release, ...] = parse_feed(_FEED)
    assert [release.info_hash for release in releases] == [
        "b456eb3845297c1c99cd359274981ae904328084",
        "c789eb3845297c1c99cd359274981ae904328084",
    ]


def test_parse_feed_defaults_unreadable_seeders_and_date() -> None:
    last: Release = parse_feed(_FEED)[-1]
    assert last.seeders == 0
    assert last.published is None


def test_parse_feed_returns_no_release_for_an_empty_channel() -> None:
    assert parse_feed('<rss version="2.0"><channel></channel></rss>') == ()


def test_parse_feed_rejects_malformed_xml() -> None:
    with pytest.raises(TorrentSourceError) as error:
        parse_feed("<rss><channel><item>")
    assert error.value.context.code is ErrorCode.TORRENT_SOURCE_FAILED


def test_search_releases_sends_the_rss_query_and_anime_category() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _xml_response(request)

    with _feed_client(handler) as http:
        releases = search_releases("neko to ryuu", http=http)

    assert len(releases) == 2
    request: httpx.Request = seen[0]
    assert request.url.params["page"] == "rss"
    assert request.url.params["q"] == "neko to ryuu"
    assert request.url.params["c"] == CATEGORY_ENGLISH_TRANSLATED
    assert request.url.params["f"] == "0"
    assert request.headers["user-agent"] == USER_AGENT


def test_search_releases_rejects_a_non_feed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>challenge</html>", headers={"content-type": "text/html"})

    with _feed_client(handler) as http, pytest.raises(TorrentSourceError) as error:
        search_releases("neko", http=http)
    assert error.value.context.message == "Nyaa did not answer with a feed"


def test_search_releases_rejects_an_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=_FEED, headers={"content-type": "application/xml"})

    with _feed_client(handler) as http, pytest.raises(TorrentSourceError) as error:
        search_releases("neko", http=http)
    assert error.value.context.code is ErrorCode.TORRENT_SOURCE_FAILED


def test_search_releases_rejects_an_oversized_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<rss>" + "x" * (MAX_BODY_BYTES + 1),
            headers={"content-type": "application/xml"},
        )

    with _feed_client(handler) as http, pytest.raises(TorrentSourceError) as error:
        search_releases("neko", http=http)
    assert error.value.context.message == "Nyaa returned an oversized feed"


def test_search_releases_maps_a_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with _feed_client(handler) as http, pytest.raises(TorrentSourceError) as error:
        search_releases("neko", http=http)
    assert error.value.context.suggestion == "Check the connection and try again"


def test_search_releases_queries_both_anime_categories_with_the_same_query() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _category_handler(request)

    with _feed_client(handler) as http:
        search_releases("neko to ryuu", http=http)

    assert [request.url.params["c"] for request in seen] == [
        CATEGORY_ENGLISH_TRANSLATED,
        CATEGORY_NON_ENGLISH_TRANSLATED,
    ]
    assert {request.url.params["q"] for request in seen} == {"neko to ryuu"}


def test_search_releases_merges_a_shared_info_hash_keeping_the_english_entry() -> None:
    with _feed_client(_category_handler) as http:
        releases = search_releases("neko to ryuu", http=http)

    shared: list[Release] = [release for release in releases if release.info_hash.casefold().startswith("b456eb38")]
    assert len(shared) == 1
    assert shared[0].seeders == 66


def test_search_releases_returns_english_releases_before_non_english_ones() -> None:
    with _feed_client(_category_handler) as http:
        releases = search_releases("neko to ryuu", http=http)

    assert [release.info_hash.casefold()[:4] for release in releases] == ["b456", "c789", "d123", "e456"]


def test_search_releases_tags_the_subtitle_language_of_every_release() -> None:
    with _feed_client(_category_handler) as http:
        releases = search_releases("neko to ryuu", http=http)

    assert [release.subtitle_language for release in releases] == ["multi", "en", "fr", None]


def test_search_releases_fails_when_the_second_category_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["c"] == CATEGORY_ENGLISH_TRANSLATED:
            return _category_handler(request)
        return httpx.Response(503, text="", headers={"content-type": "application/xml"})

    with _feed_client(handler) as http, pytest.raises(TorrentSourceError) as error:
        search_releases("neko to ryuu", http=http)
    assert error.value.context.code is ErrorCode.TORRENT_SOURCE_FAILED
