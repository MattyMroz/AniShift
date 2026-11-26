from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.tvmaze import TvMazeCatalog
from anishift.services.http_requests import USER_AGENT

pytestmark = pytest.mark.unit

_FIXTURE: Final[Path] = Path(__file__).parents[2] / "fixtures/search/tvmaze__episodes__92844.json"

_LOOKUP: Final[str] = "https://api.tvmaze.com/lookup/shows?thetvdb=478752"

_SHOW: Final[str] = "https://api.tvmaze.com/shows/92844"

_EPISODES: Final[str] = "https://api.tvmaze.com/shows/92844/episodes"


def _recorded() -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return episodes


def _series(episodes: object, seen: list[httpx.Request] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        url: str = str(request.url)
        if url == _LOOKUP:
            return httpx.Response(301, headers={"Location": _SHOW})
        if url == _SHOW:
            return httpx.Response(
                200,
                json={
                    "id": 92844,
                    "name": "Overgeared",
                    "externals": {"tvrage": None, "thetvdb": 478752, "imdb": None},
                },
            )
        assert url == _EPISODES
        return httpx.Response(200, json=episodes)

    return respond


def _titles(episodes: object) -> dict[tuple[int, int], str]:
    with httpx.Client(transport=httpx.MockTransport(_series(episodes))) as http:
        return TvMazeCatalog(http).episode_titles(478752)


def test_episode_titles_follow_the_lookup_and_skip_placeholders() -> None:
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(_series(_recorded(), seen))) as http:
        titles: dict[tuple[int, int], str] = TvMazeCatalog(http).episode_titles(478752)
    assert titles[(1, 1)] == "Legendary Class"
    assert titles[(1, 8)] == "Yatan's High Priest"
    assert sorted(titles) == [(1, number) for number in range(1, 10)]
    assert [str(request.url) for request in seen] == [_LOOKUP, _SHOW, _EPISODES]
    assert all(request.headers["User-Agent"] == USER_AGENT for request in seen)
    assert all("specials" not in request.url.params for request in seen)


def test_episode_titles_keep_only_regular_numbered_episodes() -> None:
    episodes: list[dict[str, object]] = [
        {"id": 1, "name": "Kept", "season": 1, "number": 1, "type": "regular"},
        {"id": 2, "name": "Special", "season": 1, "number": None, "type": "insignificant_special"},
        {"id": 3, "name": "Significant", "season": 1, "number": 2, "type": "significant_special"},
        {"id": 4, "name": "No number", "season": 1, "number": None, "type": "regular"},
    ]
    assert _titles(episodes) == {(1, 1): "Kept"}


def test_episode_titles_drop_a_pair_listed_twice() -> None:
    episodes: list[dict[str, object]] = [
        {"id": 1, "name": "First", "season": 1, "number": 1, "type": "regular"},
        {"id": 2, "name": "Twin", "season": 1, "number": 2, "type": "regular"},
        {"id": 3, "name": "Episode 2", "season": 1, "number": 2, "type": "regular"},
    ]
    assert _titles(episodes) == {(1, 1): "First"}


@pytest.mark.parametrize("name", ["", "   ", "Episode 10", "episode 3", "\x00\t", None])
def test_episode_titles_skip_names_that_are_no_title(name: object) -> None:
    assert _titles([{"id": 1, "name": name, "season": 1, "number": 1, "type": "regular"}]) == {}


def test_episode_titles_clean_control_characters_and_keep_anthologies_whole() -> None:
    episodes: list[dict[str, object]] = [
        {"id": 1, "name": " Reunion\u0000 at\tthe  Gate\n", "season": 1, "number": 1, "type": "regular"},
        {
            "id": 3762207,
            "name": "Even High School Boys Have Their Holes… / Ume Takes Responsibility",
            "season": 1,
            "number": 2,
            "type": "regular",
        },
    ]
    assert _titles(episodes) == {
        (1, 1): "Reunion at the Gate",
        (1, 2): "Even High School Boys Have Their Holes… / Ume Takes Responsibility",
    }


def test_episode_titles_of_an_unknown_series_are_empty() -> None:
    sent: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert TvMazeCatalog(http).episode_titles(999999999) == {}
    assert sent == ["https://api.tvmaze.com/lookup/shows?thetvdb=999999999"]


def _failing_lookup(response: httpx.Response) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: response


def _failing_show(body: object) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _LOOKUP:
            return httpx.Response(301, headers={"Location": _SHOW})
        return httpx.Response(200, json=body)

    return respond


def _timeout(request: httpx.Request) -> httpx.Response:
    message: str = "slow"
    raise httpx.ReadTimeout(message, request=request)


@pytest.mark.parametrize(
    "respond",
    [
        _failing_lookup(httpx.Response(429)),
        _failing_lookup(httpx.Response(500)),
        _failing_lookup(httpx.Response(200, text="not json")),
        _timeout,
        _failing_show({"name": "Overgeared"}),
        _failing_show({"id": "92844"}),
        _failing_show([]),
        _series({"id": 1}),
        _series([1, 2]),
        _series(None),
    ],
)
def test_episode_titles_invalid_response_has_episode_catalog_code(
    respond: Callable[[httpx.Request], httpx.Response],
) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as http,
        pytest.raises(TitleCatalogError) as caught,
    ):
        TvMazeCatalog(http).episode_titles(478752)
    assert caught.value.context.code is ErrorCode.EPISODE_CATALOG_FAILED


def test_episode_titles_of_a_missing_episode_list_fail() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _EPISODES:
            return httpx.Response(404)
        return _series([])(request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http, pytest.raises(TitleCatalogError):
        TvMazeCatalog(http).episode_titles(478752)


@pytest.mark.network
def test_episode_titles_read_overgeared_from_tvmaze() -> None:
    with httpx.Client() as http:
        titles: dict[tuple[int, int], str] = TvMazeCatalog(http).episode_titles(478752)
    assert titles[(1, 1)] == "Legendary Class"
