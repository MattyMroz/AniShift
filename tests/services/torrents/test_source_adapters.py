from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from anishift.services.http_requests import BudgetExhausted, ProviderCooldown, RequestControl
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.knaben import KnabenSource
from anishift.services.torrents.nekobt import NekoBTSource
from anishift.services.torrents.nyaa import MAX_BODY_BYTES, search_releases
from anishift.services.torrents.tsukihime import TsukiHimeSource


def _calls(client: httpx.Client) -> dict[str, Callable[[], object]]:
    return {
        "tsukihime": lambda: TsukiHimeSource(client).episode_page(1, 1, 0),
        "knaben": lambda: KnabenSource(client).search("Example", 0),
        "nekobt": lambda: NekoBTSource(client).search("Example", 0),
        "nyaa": lambda: search_releases("Example", http=client, categories=("1_2",)),
    }


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["tsukihime", "knaben", "nekobt", "nyaa"])
@pytest.mark.parametrize("status", [201, 403, 429, 503])
def test_source_status_error_retains_http_cause(provider: str, status: int) -> None:
    with (
        httpx.Client(transport=RequestControl(httpx.MockTransport(lambda _: httpx.Response(status)))) as client,
        pytest.raises(TorrentSourceError) as caught,
    ):
        _calls(client)[provider]()
    assert isinstance(caught.value.__cause__, httpx.HTTPStatusError)
    assert caught.value.__cause__.response.status_code == status


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["tsukihime", "knaben", "nekobt", "nyaa"])
def test_source_timeout_retains_http_cause(provider: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Stopped", request=request)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client, pytest.raises(TorrentSourceError) as caught:
        _calls(client)[provider]()
    assert isinstance(caught.value.__cause__, httpx.ReadTimeout)


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["tsukihime", "knaben", "nekobt"])
def test_source_uses_request_control_cooldown_and_budget(provider: str) -> None:
    control: RequestControl = RequestControl(httpx.MockTransport(lambda _: httpx.Response(200)), clock=lambda: 1000)
    with httpx.Client(transport=control) as client:
        with control.scope("budget", {provider: 0}), pytest.raises(TorrentSourceError) as budget:
            _calls(client)[provider]()
        assert isinstance(budget.value.__cause__, BudgetExhausted)
        control.restore({provider: 2000}, lambda _provider, _until: None)
        with pytest.raises(TorrentSourceError) as cooldown:
            _calls(client)[provider]()
        assert isinstance(cooldown.value.__cause__, ProviderCooldown)
    assert control.counts() == []


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["tsukihime", "knaben", "nekobt"])
@pytest.mark.parametrize("body", ["not valid data", "[]", "{}", "<html>blocked</html>"])
def test_source_rejects_malformed_response(provider: str, body: str) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, text=body, headers={"content-type": "application/xml"})
            )
        ) as client,
        pytest.raises(TorrentSourceError) as caught,
    ):
        _calls(client)[provider]()
    assert caught.value.__cause__ is not None


@pytest.mark.unit
@pytest.mark.parametrize("provider", ["tsukihime", "knaben", "nekobt"])
def test_source_rejects_oversized_response(provider: str) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * (MAX_BODY_BYTES + 1)))
        ) as client,
        pytest.raises(TorrentSourceError),
    ):
        _calls(client)[provider]()
