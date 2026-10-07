from __future__ import annotations

from xml.etree import ElementTree

import httpx
import pytest
from recorded_sources import CASES, RecordedResponse, recorded_response, responses

from anishift.application.episode_search import PagedSource, TextPage
from anishift.application.episode_selection import StreamCandidate
from anishift.application.release_quality import PolishClass, ReleaseTraits, release_traits
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.nekobt import NekoBTSource, NekoTags, language_tags, parse_feed


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES)
def test_recorded_nekobt_responses(case: str) -> None:
    for row in responses(case, "nekobt.to"):
        seen: list[httpx.Request] = []

        def respond(
            request: httpx.Request, row: RecordedResponse = row, seen: list[httpx.Request] = seen
        ) -> httpx.Response:
            seen.append(request)
            return recorded_response(row, request)

        url: httpx.URL = httpx.URL(row["url"])
        with httpx.Client(transport=RequestControl(httpx.MockTransport(respond))) as client:
            source: PagedSource = NekoBTSource(client)
            page: TextPage = source.search(url.params["q"], int(url.params["offset"]) // 100)
        root: ElementTree.Element = ElementTree.fromstring(row["body"])  # noqa: S314
        assert len(page.streams) == len(root.findall(".//item"))
        assert all(stream.source == "nekobt" and "{Tags:" not in stream.release for stream in page.streams)
        assert len(seen) == 1


@pytest.mark.unit
def test_language_tags_regional_codes() -> None:
    tags: NekoTags = language_tags("Example {Tags:A=ja-JP,zhhans;F=pl-PL;S=es419,eses,frfr,ptbr,ptpt,zhhant,fil;}")
    assert tags.audio == frozenset({"ja", "zh"})
    assert tags.subtitles == frozenset({"pl", "es", "fr", "pt", "zh", "fil"})


@pytest.mark.unit
def test_language_tags_flags() -> None:
    assert language_tags("Example {Tags:L0;HS;A=ja;F=pl;S=en;}").flags == ("L0", "HS")
    assert language_tags("Example without tags") == NekoTags(frozenset(), frozenset(), ())


@pytest.mark.unit
def test_fansub_polish_and_hardsub_survive_quality_projection() -> None:
    xml: str = (
        '<rss xmlns:t="http://torznab.com/schemas/2015/feed"><channel><item>'
        "<title>Example {Tags:HS;A=ja;F=pl;S=en;}</title>"
        '<t:attr name="infohash" value="' + "a" * 40 + '"/><t:attr name="seeders" value="3"/>'
        "</item></channel></rss>"
    )
    page: TextPage = parse_feed(xml)
    stream: StreamCandidate = page.streams[0]
    traits: ReleaseTraits = release_traits(
        (stream.release,),
        (*stream.tags, *stream.language_tags),
        (),
        file=None,
        pack=False,
        donghua=False,
        seeders=stream.seeders,
    )
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert traits.hardsub
    assert not traits.dub_only


@pytest.mark.unit
def test_empty_feed_and_optional_total() -> None:
    assert parse_feed("<rss><channel/></rss>") == TextPage((), None)
    assert parse_feed(
        '<rss xmlns:t="http://torznab.com/schemas/2015/feed"><channel>'
        '<t:response offset="100" total="123"/></channel></rss>'
    ) == TextPage((), 123)
