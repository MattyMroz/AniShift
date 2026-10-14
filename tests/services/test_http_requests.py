from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextvars import copy_context

import httpx
import pytest

from anishift.services import http_requests
from anishift.services.http_requests import BudgetExhausted, DeadlineExceeded, ProviderCooldown, RequestControl
from anishift.services.torrents.qbittorrent import QBittorrentClient


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "provider"),
    [
        ("api.ani.zip", "anizip"),
        ("torrentio.strem.fun", "torrentio"),
        ("api.tsukihime.org", "tsukihime"),
        ("api.knaben.org", "knaben"),
        ("nekobt.to", "nekobt"),
    ],
)
def test_episode_providers_charge_their_own_budget(host: str, provider: str) -> None:
    now: list[float] = [1000.0]
    control: RequestControl = RequestControl(
        httpx.MockTransport(lambda _: httpx.Response(200)),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as http, control.scope("user", {provider: 1}):
        assert http.get(f"https://{host}/").status_code == 200
        with pytest.raises(httpx.TransportError, match="budget"):
            http.get(f"https://{host}/")
    assert control.counts() == [
        {"provider": provider, "operation": "metadata", "reason": "user", "result": "200", "count": 1}
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("host", "provider"),
    [
        ("api.ani.zip", "anizip"),
        ("torrentio.strem.fun", "torrentio"),
        ("api.tsukihime.org", "tsukihime"),
        ("api.knaben.org", "knaben"),
        ("nekobt.to", "nekobt"),
    ],
)
def test_episode_providers_send_bursts_without_sleep_but_honor_429(host: str, provider: str) -> None:
    now: list[float] = [1000.0]
    sleeps: list[float] = []
    sent: list[str] = []
    saved: dict[str, float] = {}

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        if request.url.path == "/limited":
            return httpx.Response(429, headers={"Retry-After": "60"})
        return httpx.Response(200)

    control: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: now[0], sleep=sleep)
    control.restore({}, lambda name, until: saved.update({name: until}))
    with httpx.Client(transport=control) as http:
        for number in range(12):
            assert http.get(f"https://{host}/{number}").status_code == 200
        assert sleeps == []
        assert now[0] == 1000.0
        assert len(sent) == 12
        assert http.get(f"https://{host}/limited").status_code == 429
        assert saved == {provider: 1060.0}
        assert control.blocked_until((provider,)) == 1060.0
        with pytest.raises(httpx.TransportError, match="cooldown"):
            http.get(f"https://{host}/blocked")
        assert len(sent) == 13
        now[0] = 1060.0
        assert http.get(f"https://{host}/resumed").status_code == 200
        assert http.get(f"https://{host}/next").status_code == 200
    assert sleeps == []
    assert len(sent) == 15


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


def test_concurrent_equivalent_reads_share_only_the_active_response(monkeypatch: pytest.MonkeyPatch) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    sent: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json={"value": len(sent)})

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = http_requests._wait_response

    def join(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
        release.set()
        return original_wait(future, request)

    monkeypatch.setattr(http_requests, "_wait_response", join)
    with httpx.Client(transport=control) as client, ThreadPoolExecutor(2) as pool:
        first: Future[httpx.Response] = pool.submit(client.get, "http://localhost/api/v2/torrents/info")
        assert entered.wait(2)
        second: Future[httpx.Response] = pool.submit(client.get, "http://localhost/api/v2/torrents/info")
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


def _get_with_deadline(client: httpx.Client, control: RequestControl, deadline: float) -> httpx.Response:
    with control.scope("subscription", {"torrentio": 1}, deadline_s=deadline):
        return client.get("https://torrentio.strem.fun/shared")


@pytest.mark.unit
def test_deadline_caller_times_out_while_transport_hangs() -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    finished: threading.Event = threading.Event()

    def respond(_: httpx.Request) -> httpx.Response:
        entered.set()
        try:
            assert release.wait(5)
            return httpx.Response(200)
        finally:
            finished.set()

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client:
        try:
            start: float = time.monotonic()
            with pytest.raises(DeadlineExceeded):
                _get_with_deadline(client, control, 0.2)
            elapsed: float = time.monotonic() - start
            assert elapsed <= 0.45
            assert entered.is_set()
            assert not finished.is_set()
        finally:
            release.set()
            assert finished.wait(5)


@pytest.mark.unit
def test_deadline_follower_shorter_ends_alone() -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, text="shared")

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client, ThreadPoolExecutor(1) as pool:
        leader: Future[httpx.Response] = pool.submit(_get_with_deadline, client, control, 2.0)
        try:
            assert entered.wait(2)
            with pytest.raises(DeadlineExceeded):
                _get_with_deadline(client, control, 0.2)
            assert not leader.done()
        finally:
            release.set()
        assert leader.result(3).text == "shared"
    assert calls == ["/shared"]


@pytest.mark.unit
def test_follower_joins_after_leader_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, text="survived")

    original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = http_requests._wait_response

    def join(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
        release.set()
        return original_wait(future, request)

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client:
        try:
            with pytest.raises(DeadlineExceeded):
                _get_with_deadline(client, control, 0.2)
            assert entered.is_set()
            monkeypatch.setattr(http_requests, "_wait_response", join)
            assert _get_with_deadline(client, control, 2.0).text == "survived"
        finally:
            release.set()
    assert calls == ["/shared"]


@pytest.mark.unit
def test_deadline_expired_before_request_not_sent() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200)

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with (
        httpx.Client(transport=control) as client,
        control.scope("subscription", {}, deadline_s=0),
        pytest.raises(DeadlineExceeded),
    ):
        client.get("https://api.tsukihime.org/expired")
    assert calls == []
    assert control.counts() == []


@pytest.mark.unit
def test_budget_through_both_pools() -> None:
    control: RequestControl = RequestControl(httpx.MockTransport(lambda _: httpx.Response(200)))
    with (
        httpx.Client(transport=control) as client,
        ThreadPoolExecutor(2) as search_pool,
        control.scope("subscription", {"tsukihime": 1}, deadline_s=5),
    ):
        first: Future[httpx.Response] = search_pool.submit(
            copy_context().run, client.get, "https://api.tsukihime.org/1"
        )
        assert first.result(3).status_code == 200
        second: Future[httpx.Response] = search_pool.submit(
            copy_context().run, client.get, "https://api.tsukihime.org/2"
        )
        with pytest.raises(BudgetExhausted):
            second.result(3)
    assert control.counts() == [
        {"provider": "tsukihime", "operation": "metadata", "reason": "subscription", "result": "200", "count": 1}
    ]


@pytest.mark.unit
def test_follower_not_charged(monkeypatch: pytest.MonkeyPatch) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def respond(_: httpx.Request) -> httpx.Response:
        entered.set()
        assert release.wait(5)
        return httpx.Response(200)

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client, ThreadPoolExecutor(1) as pool:
        leader: Future[httpx.Response] = pool.submit(_get_with_deadline, client, control, 3.0)
        try:
            assert entered.wait(2)
            original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = (
                http_requests._wait_response
            )

            def join(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
                release.set()
                return original_wait(future, request)

            monkeypatch.setattr(http_requests, "_wait_response", join)
            with control.scope("follower", {"torrentio": 0}, deadline_s=2):
                assert client.get("https://torrentio.strem.fun/shared").status_code == 200
            assert leader.result(3).status_code == 200
        finally:
            release.set()
    assert control.counts() == [
        {"provider": "torrentio", "operation": "metadata", "reason": "subscription", "result": "200", "count": 1}
    ]


@pytest.mark.unit
def test_cooldown_and_budget_error_types() -> None:
    control: RequestControl = RequestControl(httpx.MockTransport(lambda _: httpx.Response(429)))
    with httpx.Client(transport=control) as client:
        with control.scope("budget", {"knaben": 0}), pytest.raises(BudgetExhausted) as budget:
            client.get("https://api.knaben.org/blocked")
        assert isinstance(budget.value, httpx.TransportError)
        assert client.get("https://api.knaben.org/limited").status_code == 429
        with pytest.raises(ProviderCooldown) as cooldown:
            client.get("https://api.knaben.org/blocked")
        assert isinstance(cooldown.value, httpx.TransportError)
        assert client.get("https://nekobt.to/independent").status_code == 429
    assert issubclass(DeadlineExceeded, httpx.TimeoutException)


@pytest.mark.unit
def test_nested_scope_cannot_extend_expired_parent_deadline() -> None:
    control: RequestControl = RequestControl(httpx.MockTransport(lambda _: httpx.Response(200)))
    with (
        httpx.Client(transport=control) as client,
        control.scope("parent", {}, deadline_s=0),
        control.scope("nested", {}, deadline_s=30),
        pytest.raises(DeadlineExceeded),
    ):
        client.get("https://api.tsukihime.org/expired")


@pytest.mark.unit
def test_tsukihime_sliding_windows_allow_bursts_and_enforce_all_three_limits() -> None:
    now: list[float] = [1000.0]
    sent: list[float] = []

    def respond(_: httpx.Request) -> httpx.Response:
        sent.append(now[0])
        return httpx.Response(200)

    control: RequestControl = RequestControl(
        httpx.MockTransport(respond),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as client:
        for number in range(101):
            assert client.get(f"https://api.tsukihime.org/{number}").status_code == 200
    assert sent[:25] == [1000.0] * 25
    assert sent[25] == 1010.0
    assert sent[60] == 1030.0
    assert sent[100] == 1060.0
    for timestamp in sent:
        for limit, window in ((25, 10), (60, 30), (100, 60)):
            assert sum(timestamp - window < item <= timestamp for item in sent) <= limit


@pytest.mark.unit
def test_without_deadline_transport_runs_on_caller_thread() -> None:
    threads: list[int] = []

    def respond(_: httpx.Request) -> httpx.Response:
        threads.append(threading.get_ident())
        return httpx.Response(200)

    with httpx.Client(transport=RequestControl(httpx.MockTransport(respond))) as client:
        assert client.get("http://localhost/api/v2/app/version").status_code == 200
    assert threads == [threading.get_ident()]


@pytest.mark.unit
def test_deadline_expires_while_waiting_for_admission_without_sending() -> None:
    waiting: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    finished: threading.Event = threading.Event()
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200)

    def sleep(_: float) -> None:
        waiting.set()
        assert release.wait(5)
        finished.set()

    control: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: 1000.0, sleep=sleep)
    with httpx.Client(transport=control) as client:
        assert client.get("https://nyaa.si/first").status_code == 200
        try:
            with control.scope("subscription", {}, deadline_s=0.2), pytest.raises(DeadlineExceeded):
                client.get("https://nyaa.si/second")
            assert waiting.is_set()
        finally:
            release.set()
            assert finished.wait(5)
    assert paths == ["/first"]


@pytest.mark.unit
def test_deadline_expired_in_worker_queue_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_requests, "_REQUEST_WORKERS", 1)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    paths: list[str] = []
    queued_futures: list[Future[httpx.Response]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200)

    original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = http_requests._wait_response

    def observe_queue(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
        if request.url.path == "/queued":
            queued_futures.append(future)
        return original_wait(future, request)

    monkeypatch.setattr(http_requests, "_wait_response", observe_queue)
    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client, ThreadPoolExecutor(1) as pool:
        leader: Future[httpx.Response] = pool.submit(_get_with_deadline, client, control, 3.0)
        try:
            assert entered.wait(2)
            with control.scope("queued", {}, deadline_s=0.2), pytest.raises(DeadlineExceeded):
                client.get("https://torrentio.strem.fun/queued")
        finally:
            release.set()
        assert leader.result(3).status_code == 200
        with pytest.raises(DeadlineExceeded):
            queued_futures[0].result(3)
    assert paths == ["/shared"]


@pytest.mark.unit
def test_close_cancels_queued_requests_without_waiting_for_running_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_requests, "_REQUEST_WORKERS", 1)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    queued: threading.Event = threading.Event()
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200)

    original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = http_requests._wait_response

    def observe_queue(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
        if request.url.path == "/queued":
            queued.set()
        return original_wait(future, request)

    monkeypatch.setattr(http_requests, "_wait_response", observe_queue)
    control: RequestControl = RequestControl(httpx.MockTransport(respond))

    def request_queued(client: httpx.Client) -> httpx.Response:
        with control.scope("queued", {}, deadline_s=3):
            return client.get("https://torrentio.strem.fun/queued")

    with httpx.Client(transport=control) as client, ThreadPoolExecutor(2) as pool:
        leader: Future[httpx.Response] = pool.submit(_get_with_deadline, client, control, 3.0)
        try:
            assert entered.wait(2)
            follower: Future[httpx.Response] = pool.submit(request_queued, client)
            assert queued.wait(2)
            control.close()
            assert not leader.done()
            with pytest.raises(httpx.TransportError, match="closed"):
                follower.result(1)
        finally:
            release.set()
        assert leader.result(3).status_code == 200
    assert paths == ["/shared"]


@pytest.mark.unit
def test_failed_worker_releases_active_read_for_retry() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.ReadTimeout("Transport timeout", request=request)
        return httpx.Response(200)

    control: RequestControl = RequestControl(httpx.MockTransport(respond))
    with httpx.Client(transport=control) as client:
        with pytest.raises(httpx.ReadTimeout, match="Transport timeout"):
            _get_with_deadline(client, control, 2)
        assert _get_with_deadline(client, control, 2).status_code == 200
    assert calls == ["/shared", "/shared"]


@pytest.mark.unit
@pytest.mark.parametrize("leader_limit", [0, 1])
@pytest.mark.parametrize("follower_limit", [0, 1])
def test_follower_longer_survives_leader_admission_deadline(
    monkeypatch: pytest.MonkeyPatch, leader_limit: int, follower_limit: int
) -> None:
    now: list[float] = [1000.0]
    waiting: threading.Event = threading.Event()
    joined: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    leader_waiting: threading.Event = threading.Event()
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200)

    def sleep(_: float) -> None:
        waiting.set()
        assert release.wait(5)
        now[0] = 1001.0

    original_wait: Callable[[Future[httpx.Response], httpx.Request], httpx.Response] = http_requests._wait_response

    def observe_join(future: Future[httpx.Response], request: httpx.Request) -> httpx.Response:
        if request.url.path == "/target":
            (joined if leader_waiting.is_set() else leader_waiting).set()
        return original_wait(future, request)

    monkeypatch.setattr(http_requests, "_wait_response", observe_join)
    control: RequestControl = RequestControl(httpx.MockTransport(respond), clock=lambda: now[0], sleep=sleep)

    def get(client: httpx.Client, reason: str, limit: int, deadline: float) -> httpx.Response:
        with control.scope(reason, {"nyaa": limit}, deadline_s=deadline):
            return client.get("https://nyaa.si/target")

    with httpx.Client(transport=control) as client, ThreadPoolExecutor(2) as pool:
        assert client.get("https://nyaa.si/warm").status_code == 200
        leader: Future[httpx.Response] = pool.submit(get, client, "leader", leader_limit, 0.2 if leader_limit else 3)
        try:
            assert waiting.wait(2)
            assert leader_waiting.wait(2)
            follower: Future[httpx.Response] = pool.submit(get, client, "follower", follower_limit, 5)
            assert joined.wait(2)
            if leader_limit:
                with pytest.raises(DeadlineExceeded):
                    leader.result(2)
            release.set()
            if not leader_limit:
                with pytest.raises(BudgetExhausted):
                    leader.result(2)
            if follower_limit:
                assert follower.result(3).status_code == 200
            else:
                with pytest.raises(BudgetExhausted):
                    follower.result(3)
        finally:
            release.set()
    assert paths == (["/warm", "/target"] if follower_limit else ["/warm"])
    if follower_limit:
        assert any(row["reason"] == "follower" and row["count"] == 1 for row in control.counts())


@pytest.mark.unit
def test_wait_response_maps_cancellation_racing_with_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    future: Future[httpx.Response] = Future()
    original_result: Callable[[float | None], httpx.Response] = future.result
    calls: list[float | None] = []

    def timeout_then_cancel(timeout: float | None = None) -> httpx.Response:
        calls.append(timeout)
        if len(calls) == 1:
            assert future.cancel()
            raise TimeoutError
        return original_result(timeout)

    monkeypatch.setattr(future, "result", timeout_then_cancel)
    with pytest.raises(httpx.TransportError, match="closed") as caught:
        http_requests._wait_response(future, httpx.Request("GET", "https://nyaa.si/"))
    assert isinstance(caught.value.__cause__, CancelledError)
    assert len(calls) == 2
