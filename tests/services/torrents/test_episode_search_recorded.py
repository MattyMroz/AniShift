from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
from recorded_sources import RecordedResponse, recorded_response, responses

from anishift.application.episode_search import EpisodeRequest, EpisodeSearch, SearchOutcome, SourceSwitches
from anishift.application.episode_selection import EpisodeKey
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.categories import SEARCH_CATEGORIES
from anishift.services.torrents.knaben import KnabenSource
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.nekobt import NekoBTSource
from anishift.services.torrents.nyaa import search_releases
from anishift.services.torrents.torrentio import TorrentioSource
from anishift.services.torrents.tsukihime import TsukiHimeSource
from anishift.services.torrents.types import Release


class _Nyaa:
    def __init__(self, http: httpx.Client) -> None:
        self.http: httpx.Client = http

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        return search_releases(query, http=self.http, categories=categories)


@pytest.mark.integration
@pytest.mark.parametrize("source", ["nyaa", "knaben", "nekobt", "torrentio", "tsukihime"])
def test_recorded_sources_through_search_and_ranking(source: str) -> None:
    hosts: dict[str, str] = {
        "nyaa": "nyaa.si",
        "knaben": "api.knaben.org",
        "nekobt": "nekobt.to",
        "torrentio": "torrentio.strem.fun",
        "tsukihime": "api.tsukihime.org",
    }
    rows: list[RecordedResponse] = responses("130003-1", hosts[source])
    query: str = next((httpx.URL(row["url"]).params["q"] for row in rows if "q" in httpx.URL(row["url"]).params), "")
    kitsu: int | None = int(httpx.URL(rows[0]["url"]).path.split(":")[1]) if source == "torrentio" else None

    def respond(request: httpx.Request) -> httpx.Response:
        row: RecordedResponse = next(
            row
            for row in rows
            if httpx.URL(row["url"]).path == request.url.path
            and dict(httpx.URL(row["url"]).params) == dict(request.url.params)
        )
        response: httpx.Response = recorded_response(row, request)
        if source == "nyaa":
            response.headers["content-type"] = "application/xml"
        return response

    now: list[float] = [1000.0]
    control: RequestControl = RequestControl(
        httpx.MockTransport(respond), clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay)
    )
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = EpisodeSearch(
            torrentio=TorrentioSource(http),
            nyaa=_Nyaa(http),
            knaben=KnabenSource(http),
            nekobt=NekoBTSource(http),
            tsukihime=TsukiHimeSource(http),
            request_control=control,
            pack_name=lambda name: parse_release_name(name).is_pack,
        )
        request: EpisodeRequest = EpisodeRequest(
            EpisodeKey(130003, 1),
            1,
            False,
            False,
            kitsu,
            None,
            (query,),
            {
                "aliases": ["Bocchi the Rock!"],
                "type": "TV",
                "season": 1,
                "episode": 1,
                "local_episode": 1,
                "absolute": 1,
                "episode_title": None,
                "other_series": [],
                "other_episode_titles": [],
            },
            True,
        )
        switches: SourceSwitches = SourceSwitches(
            source == "tsukihime", source == "torrentio", source == "nyaa", source == "knaben", source == "nekobt"
        )
        outcome: SearchOutcome = service.manual_offer(request, switches)
    result = next(row for row in outcome.snapshot.sources if row.source == source)
    assert result.failure is None
    assert all(row.stream.source == source for row in outcome.snapshot.candidates)
    if source != "tsukihime":
        assert outcome.snapshot.candidates
