from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
from recorded_sources import CASES, RecordedResponse, recorded_response, responses

from anishift.application.episode_releases import info_hash_hex
from anishift.application.episode_search import PagedSource, TextPage
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.knaben import KnabenSource


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES)
def test_search_get_params_as_recorded(case: str) -> None:
    for row in responses(case, "api.knaben.org"):
        seen: list[httpx.Request] = []

        def respond(
            request: httpx.Request, row: RecordedResponse = row, seen: list[httpx.Request] = seen
        ) -> httpx.Response:
            seen.append(request)
            return recorded_response(row, request)

        url: httpx.URL = httpx.URL(row["url"])
        raw: dict[str, object] = json.loads(row["body"])
        with httpx.Client(transport=RequestControl(httpx.MockTransport(respond))) as client:
            source: PagedSource = KnabenSource(client)
            result: TextPage = source.search(url.params["q"], int(url.params["f"]) // 300)
        hits: list[dict[str, object]] = cast("list[dict[str, object]]", raw["hits"])
        assert result.total == cast("dict[str, object]", raw["total"])["value"]
        assert [stream.release for stream in result.streams] == [hit["title"] for hit in hits]
        assert [stream.seeders for stream in result.streams] == [hit["seeders"] for hit in hits]
        assert [stream.info_hash for stream in result.streams] == [info_hash_hex(str(hit["hash"])) for hit in hits]
        assert all(stream.source == "knaben" for stream in result.streams)
        assert len(seen) == 1


@pytest.mark.unit
@pytest.mark.parametrize("hash_value", ["A" * 40, "G5J35LYACERDGRCVMZ3YRGNKXPGN33X7"])
def test_hash_lowercased(hash_value: str) -> None:
    body: dict[str, object] = {"hits": [{"hash": hash_value, "title": "Example", "seeders": 0}], "total": {"value": 1}}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
        page: TextPage = KnabenSource(client).search("Example", 0)
    assert page.streams[0].info_hash == info_hash_hex(hash_value)


@pytest.mark.unit
def test_magnet_fallback_keeps_trackers_without_webseeds() -> None:
    body: dict[str, object] = {
        "hits": [
            {
                "title": "Example",
                "magnetUrl": "magnet:?xt=urn:btih:"
                + "a" * 40
                + "&tr=udp%3A%2F%2Ftracker.example%3A80&ws=https%3A%2F%2Fexample.com",
            }
        ]
    }
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
        page: TextPage = KnabenSource(client).search("Example", 0)
    assert page.total is None
    assert page.streams[0].seeders is None
    assert page.streams[0].trackers == ("udp://tracker.example:80",)


@pytest.mark.unit
def test_search_empty_and_duplicate_hashes() -> None:
    row: dict[str, object] = {"hash": "a" * 40, "title": "Example"}
    bodies: list[dict[str, object]] = [{"hits": [], "total": {"value": 0}}, {"hits": [row, row]}]
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=bodies.pop(0)))) as client:
        source: KnabenSource = KnabenSource(client)
        assert source.search("Example", 0) == TextPage((), 0)
        assert len(source.search("Example", 1).streams) == 2
