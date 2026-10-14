from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
import pytest

from anishift.application.episode_selection import AniZipMapping
from anishift.errors import ErrorCode
from anishift.services.catalog.anizip import AniZipCatalog, parse_mapping
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT

pytestmark = pytest.mark.unit

_FIXTURE: Final[Path] = Path(__file__).parents[2] / "fixtures/search/anizip__101280.json"


def test_mapping_fixture_keeps_raw_order_and_parses_metadata() -> None:
    body: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.ani.zip/mappings?anilist_id=101280"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, json=body, headers={"Cache-Control": "public, max-age=900"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result: AniZipMapping = AniZipCatalog(http).mapping(101280)
    assert result.kitsu_id == 41024
    assert result.max_age_s == 900
    assert result.raw_episodes == body["episodes"]
    assert list(result.raw_episodes) == list(body["episodes"])
    assert result.episodes[0].airs_at == datetime(2018, 10, 2, 14, tzinfo=UTC)
    assert result.episodes[0].title == "The Storm Dragon, Veldora"
    body["episodes"]["1"]["title"]["en"] = "Changed"
    assert result.raw_episodes["1"]["title"]["en"] == "The Storm Dragon, Veldora"


def test_mapping_404_returns_empty_mapping() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as http:
        assert AniZipCatalog(http).mapping(1) == AniZipMapping(None, None, None, (), (), None, {})


def test_mapping_missing_dates_never_use_local_date_fields() -> None:
    result: AniZipMapping = parse_mapping(
        {
            "mappings": {},
            "episodes": {
                "2": {"airDate": "2020-01-01", "airdate": "2020-01-02", "title": {"x-jat": "Second"}},
                "1": {},
                "S1": {"airDateUtc": "2020-01-03T01:00:00Z", "title": {"en": "Extra"}},
                "1.5": {},
            },
        }
    )
    assert [episode.number for episode in result.episodes] == [1, 2]
    assert all(episode.airs_at is None for episode in result.episodes)
    assert result.episodes[1].title == "Second"
    assert result.specials[0].key == "S1"
    assert str(result.specials[0].airs_on) == "2020-01-03"
    assert "1.5" in result.raw_episodes


@pytest.mark.parametrize(
    "response",
    [httpx.Response(429), httpx.Response(500), httpx.Response(200, text="not json"), httpx.Response(200, json={})],
)
def test_mapping_invalid_response_has_episode_catalog_code(response: httpx.Response) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as http,
        pytest.raises(TitleCatalogError) as caught,
    ):
        AniZipCatalog(http).mapping(1)
    assert caught.value.context.code is ErrorCode.EPISODE_CATALOG_FAILED


def test_mapping_by_anidb() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.ani.zip/mappings?anidb_id=20168"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(
            200,
            json={
                "episodes": {
                    "1": {
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "absoluteEpisodeNumber": 15,
                        "title": {"en": "Clouds and Rain"},
                    }
                },
                "mappings": {"kitsu_id": None, "type": "TV", "anidb_id": 20168},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result: AniZipMapping = AniZipCatalog(http).mapping_by_anidb(20168)
    assert (result.kitsu_id, result.catalog_type) == (None, "TV")
    assert result.episodes[0].title == "Clouds and Rain"
    assert result.raw_episodes["1"]["seasonNumber"] == 2


def test_mapping_transport_failure_has_episode_catalog_code() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http, pytest.raises(TitleCatalogError) as caught:
        AniZipCatalog(http).mapping(1)
    assert caught.value.context.code is ErrorCode.EPISODE_CATALOG_FAILED
