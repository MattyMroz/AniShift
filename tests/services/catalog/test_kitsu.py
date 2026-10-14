from __future__ import annotations

from typing import Final

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.kitsu import KitsuCatalog

pytestmark = pytest.mark.unit


def _links(*, more: bool) -> dict[str, str]:
    return {"first": "https://kitsu.io/first", **({"next": "https://kitsu.io/next"} if more else {})}


def _forward(*items: str, more: bool = False) -> dict[str, object]:
    return {
        "data": [
            {
                "type": "mappings",
                "attributes": {"externalSite": "anilist/anime", "externalId": "210031"},
                "relationships": {"item": {"data": {"type": "anime", "id": item}}},
            }
            for item in items
        ],
        "links": _links(more=more),
    }


def _reverse(*pairs: tuple[str, str], more: bool = False) -> dict[str, object]:
    return {
        "data": [
            {"type": "mappings", "attributes": {"externalSite": site, "externalId": identifier}}
            for site, identifier in pairs
        ],
        "links": _links(more=more),
    }


_CONFIRMED: Final[dict[str, object]] = _reverse(("anilist/anime", "210031"), ("myanimelist/anime", "63832"))


def _resolve(forward: dict[str, object], reverse: dict[str, object], seen: list[httpx.URL]) -> int | None:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=forward if request.url.path == "/api/edge/mappings" else reverse)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        return KitsuCatalog(http).kitsu_id(210031)


def test_kitsu_from_mappings_with_reverse_check() -> None:
    seen: list[httpx.URL] = []
    assert _resolve(_forward("50634"), _CONFIRMED, seen) == 50634
    assert [(url.host, url.path, dict(url.params)) for url in seen] == [
        (
            "kitsu.io",
            "/api/edge/mappings",
            {
                "filter[externalSite]": "anilist/anime",
                "filter[externalId]": "210031",
                "include": "item",
                "page[limit]": "20",
            },
        ),
        ("kitsu.io", "/api/edge/anime/50634/mappings", {"page[limit]": "20"}),
    ]


def test_kitsu_candidate_with_next_link_is_unresolved() -> None:
    seen: list[httpx.URL] = []
    assert _resolve(_forward("50634", more=True), _CONFIRMED, seen) is None
    assert len(seen) == 1


@pytest.mark.parametrize(
    "reverse",
    [
        _reverse(("anilist/anime", "210031"), more=True),
        _reverse(("myanimelist/anime", "63832")),
        _reverse(("anilist/anime", "1")),
    ],
)
def test_kitsu_incomplete_reverse_is_unresolved(reverse: dict[str, object]) -> None:
    assert _resolve(_forward("50634"), reverse, []) is None


@pytest.mark.parametrize("forward", [_forward(), _forward("50634", "50635"), _forward("x1")])
def test_kitsu_ambiguous_is_unresolved(forward: dict[str, object]) -> None:
    seen: list[httpx.URL] = []
    assert _resolve(forward, _CONFIRMED, seen) is None
    assert len(seen) == 1


@pytest.mark.parametrize("reverse", [_CONFIRMED, _reverse(("anilist/anime", "210031"), more=True)])
def test_kitsu_request_count(reverse: dict[str, object]) -> None:
    seen: list[httpx.URL] = []
    _resolve(_forward("50634"), reverse, seen)
    assert len(seen) == 2


@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.Response(500), httpx.Response(200, text="not json"), httpx.Response(200, json={})],
)
def test_kitsu_invalid_response_has_episode_catalog_code(response: httpx.Response) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as http,
        pytest.raises(TitleCatalogError) as caught,
    ):
        KitsuCatalog(http).kitsu_id(210031)
    assert caught.value.context.code is ErrorCode.EPISODE_CATALOG_FAILED
