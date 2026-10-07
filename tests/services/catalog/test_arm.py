from __future__ import annotations

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.catalog.arm import ArmCatalog, ArmIds
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.http_requests import USER_AGENT

pytestmark = pytest.mark.unit


def test_ids_reads_anidb_and_tvdb_season() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://arm.haglund.dev/api/v2/ids?source=anilist&id=210031"
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(
            200,
            json={"anidb": 19983, "anilist": 210031, "kitsu": 50634, "thetvdb": 457078, "thetvdb-season": 2},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        assert ArmCatalog(http).ids(210031) == ArmIds(19983, 2)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.Response(200, json={"anidb": None, "thetvdb": None, "thetvdb-season": None})],
)
def test_ids_unknown_entry_has_no_ids(response: httpx.Response) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as http:
        assert ArmCatalog(http).ids(1) == ArmIds(None, None)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(429), httpx.Response(500), httpx.Response(200, text="not json"), httpx.Response(200, json=[])],
)
def test_ids_invalid_response_has_episode_catalog_code(response: httpx.Response) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as http,
        pytest.raises(TitleCatalogError) as caught,
    ):
        ArmCatalog(http).ids(1)
    assert caught.value.context.code is ErrorCode.EPISODE_CATALOG_FAILED
