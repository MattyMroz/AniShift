from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import httpx
import pytest

from anishift.services.http_requests import RequestControl
from anishift.services.torrents.qbittorrent import QBittorrentClient


def test_provider_cooldown_is_shared_restored_and_does_not_block_another_provider() -> None:
    now: list[float] = [1000.0]
    sent: list[str] = []
    saved: dict[str, float] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.host)
        return (
            httpx.Response(429, headers={"Retry-After": "120"})
            if request.url.host == "nyaa.si"
            else httpx.Response(200)
        )

    control: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: now[0])
    control.restore({}, lambda provider, until: saved.update({provider: until}))
    with httpx.Client(transport=control) as client:
        assert client.get("https://nyaa.si/").status_code == 429
        with pytest.raises(httpx.TransportError, match="cooldown"):
            client.get("https://nyaa.si/", params={"q": "another query"})
        assert client.get("http://localhost/api/v2/app/version").status_code == 200
    assert sent == ["nyaa.si", "localhost"]
    assert saved == {"nyaa": 1120.0}
    restored: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: now[0])
    restored.restore(saved, lambda _provider, _until: None)
    with httpx.Client(transport=restored) as client:
        with pytest.raises(httpx.TransportError, match="cooldown"):
            client.get("https://nyaa.si/")
        now[0] = 1120.0
        assert client.get("https://nyaa.si/").status_code == 429


def test_actual_login_retry_and_not_modified_responses_are_counted() -> None:
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if len(paths) == 1:
            return httpx.Response(403)
        if request.url.path.endswith("login"):
            return httpx.Response(200, text="Ok.")
        return httpx.Response(304) if request.url.host == "nyaa.si" else httpx.Response(200, text="v5.1.0")

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as http, control.scope("user", {"nyaa": 2}):
        assert QBittorrentClient("http://localhost", http=http).version() == "5.1.0"
        assert http.get("https://nyaa.si/").status_code == 304
    assert paths == ["/api/v2/app/version", "/api/v2/auth/login", "/api/v2/app/version", "/"]
    assert sum(int(str(row["count"])) for row in control.counts()) == 4
    assert {row["result"] for row in control.counts()} == {"403", "200", "304"}


def test_nested_scopes_share_one_actual_request_budget() -> None:
    now: list[float] = [1000.0]
    sent: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(200)

    control: RequestControl = RequestControl(
        httpx.MockTransport(respond),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as client, control.scope("subscription", {"nyaa": 2}):
        client.get("https://nyaa.si/", params={"c": "1_2"})
        with control.scope("nested", {"nyaa": 100}):
            client.get("https://nyaa.si/", params={"c": "1_3"})
            with pytest.raises(httpx.TransportError, match="budget"):
                client.get("https://nyaa.si/", params={"q": "catch-up"})
    assert len(sent) == 2
    assert {row["reason"] for row in control.counts()} == {"subscription"}


def test_concurrent_equivalent_reads_share_only_the_active_response() -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    sent: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json={"value": len(sent)})

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client, ThreadPoolExecutor(2) as pool:
        first: Future[httpx.Response] = pool.submit(client.get, "http://localhost/api/v2/torrents/info")
        assert entered.wait(2)
        second: Future[httpx.Response] = pool.submit(client.get, "http://localhost/api/v2/torrents/info")
        time.sleep(0.05)
        release.set()
        assert first.result().json() == second.result().json() == {"value": 1}
        assert client.get("http://localhost/api/v2/torrents/info").json() == {"value": 2}
    assert len(sent) == 2


@pytest.mark.parametrize(
    "header",
    [{"Retry-After": "Thu, 01 Jan 1970 00:20:00 GMT"}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1200"}],
)
def test_retry_dates_and_provider_resets_set_shared_deadlines(header: dict[str, str]) -> None:
    control: RequestControl = RequestControl(
        httpx.MockTransport(lambda _: httpx.Response(200, headers=header)),
        clock=lambda: 1000.0,
    )
    with httpx.Client(transport=control) as client:
        assert client.post("https://graphql.anilist.co/", json={"query": "query"}).status_code == 200
    assert control.blocked_until(("anilist",)) == 1200.0
