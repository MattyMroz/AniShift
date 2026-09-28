from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import httpx
import pytest

from anishift.application.episode_selection import StreamCandidate
from anishift.services.http_requests import USER_AGENT, RequestControl
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.torrentio import TorrentioSource, parse_streams

pytestmark = pytest.mark.unit

_FIXTURE: Final[Path] = Path(__file__).parents[2] / "fixtures/search/torrentio__kitsu-41024-4.json"


def test_streams_fixture_preserves_files_and_parses_presentation() -> None:
    body: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://torrentio.strem.fun/stream/series/kitsu:41024:4.json"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        streams: tuple[StreamCandidate, ...] = TorrentioSource(http).streams(41024, 4)
    assert len(streams) == len(body["streams"])
    first: StreamCandidate = streams[0]
    assert first.file_index == 3
    assert first.name == "Torrentio\n1080p"
    assert first.path == "01. Season 1 + Special/S01E04-In the Kingdom of the Dwarves [D1DC0293].mkv"
    assert first.file_name == "S01E04-In the Kingdom of the Dwarves [D1DC0293].mkv"
    assert first.seeders == 320
    assert first.size_text == "592.94 MB"
    assert first.provider == "NyaaSi"
    assert first.tags == ("Dubbed", "Dual Audio")
    assert first.trackers[0] == "http://tracker.opentrackr.org:1337/announce"
    assert all(not tracker.startswith("dht:") for tracker in first.trackers)


def test_movie_streams_uses_movie_url_without_episode_suffix() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://torrentio.strem.fun/stream/movie/kitsu:123.json"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, json={"streams": []})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert TorrentioSource(http).movie_streams(123) == ()


def test_streams_absent_metadata_and_same_hash_files_remain_distinct() -> None:
    streams: tuple[StreamCandidate, ...] = parse_streams(
        {
            "streams": [
                {"infoHash": "A" * 40, "title": "Release"},
                {"infoHash": "A" * 40, "title": "Release\n👤 0", "fileIdx": 0},
                {"infoHash": "A" * 40, "title": "Release\n👤 1", "fileIdx": 1},
            ]
        }
    )
    assert len(streams) == 3
    assert [stream.file_index for stream in streams] == [None, 0, 1]
    assert [stream.seeders for stream in streams] == [None, 0, 1]
    assert all(stream.info_hash == "a" * 40 for stream in streams)
    assert all(stream.file_name is None and stream.name is None and stream.path is None for stream in streams)


def test_streams_explicit_retry_keeps_user_agent_and_respects_shared_cooldown() -> None:
    sent: list[str] = []
    now: list[float] = [1000.0]

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["User-Agent"])
        return (
            httpx.Response(429, headers={"Retry-After": "60"})
            if len(sent) == 1
            else httpx.Response(200, json={"streams": []})
        )

    control: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: now[0])
    with httpx.Client(transport=control) as http:
        source: TorrentioSource = TorrentioSource(http)
        with pytest.raises(TorrentSourceError):
            source.streams(41024, 4)
        assert control.blocked_until(("torrentio",)) == 1060.0
        with pytest.raises(TorrentSourceError):
            source.streams(41024, 4)
        assert len(sent) == 1
        now[0] = 1060.0
        assert source.streams(41024, 4) == ()
    assert sent == [USER_AGENT, USER_AGENT]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"streams": None},
        {"streams": [{}]},
        {"streams": [{"infoHash": "a" * 40, "title": "Title", "fileIdx": True}]},
    ],
)
def test_streams_malformed_body_is_a_source_failure(body: object) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as http,
        pytest.raises(TorrentSourceError),
    ):
        TorrentioSource(http).streams(1, 1)


@pytest.mark.parametrize("status", [403, 429, 500])
def test_streams_http_failure_is_not_an_empty_offer_or_automatic_retry(status: int) -> None:
    calls: list[int] = []

    def respond(_: httpx.Request) -> httpx.Response:
        calls.append(status)
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http, pytest.raises(TorrentSourceError):
        TorrentioSource(http).streams(1, 1)
    assert calls == [status]


def test_streams_transport_failure_is_a_source_failure() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http, pytest.raises(TorrentSourceError):
        TorrentioSource(http).streams(1, 1)
