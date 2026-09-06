from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Final

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.catalog.anilist import ANILIST_URL, AniListCatalog
from anishift.services.catalog.errors import TitleCatalogError
from anishift.services.catalog.types import PrequelEntry, TitleCandidate, TitleStatus

_SOLO_LEVELING: Final[dict[str, Any]] = {
    "id": 176496,
    "title": {
        "romaji": "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        "english": "Solo Leveling Season 2: Arise from the Shadow",
        "native": "俺だけレベルアップな件 -Arise from the Shadow-",
    },
    "synonyms": ["Solo Leveling 2nd Season", "โซโลเลเวลลิ่ง", "", "solo leveling 2nd season"],
    "seasonYear": 2025,
    "season": "WINTER",
    "format": "TV",
    "episodes": 13,
    "status": "FINISHED",
    "relations": {
        "edges": [
            {"relationType": "PREQUEL", "node": {"id": 151807, "episodes": 12, "format": "TV"}},
            {"relationType": "PREQUEL", "node": {"id": 178025, "episodes": 1, "format": "MOVIE"}},
            {"relationType": "SEQUEL", "node": {"id": 200000, "episodes": None, "format": "TV"}},
        ]
    },
}

_MUSHOKU: Final[dict[str, Any]] = {
    "id": 166873,
    "title": {"romaji": "Mushoku Tensei III", "english": None, "native": "無職転生 III"},
    "synonyms": [],
    "seasonYear": 2026,
    "season": "SPRING",
    "format": "TV",
    "episodes": None,
    "status": "AIRING_SOON",
    "relations": {"edges": []},
}


def _page(media: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": {"Page": {"media": media}}}


def _catalog(handler: Callable[[httpx.Request], httpx.Response]) -> tuple[AniListCatalog, httpx.Client]:
    http: httpx.Client = httpx.Client(transport=httpx.MockTransport(handler))
    return AniListCatalog(http), http


def _searched(request: httpx.Request) -> str:
    body: Any = json.loads(request.content)
    return str(body["variables"]["search"])


def test_search_reads_every_candidate_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(ANILIST_URL)
        return httpx.Response(200, json=_page([_SOLO_LEVELING]))

    catalog, http = _catalog(handler)
    with http:
        candidates: tuple[TitleCandidate, ...] = catalog.search("solo leveling")

    first: TitleCandidate = candidates[0]
    assert first.anilist_id == 176496
    assert first.romaji == "Ore dake Level Up na Ken Season 2: Arise from the Shadow"
    assert first.english == "Solo Leveling Season 2: Arise from the Shadow"
    assert first.native == "俺だけレベルアップな件 -Arise from the Shadow-"
    assert first.synonyms == ("Solo Leveling 2nd Season", "โซโลเลเวลลิ่ง", "solo leveling 2nd season")
    assert first.year == 2025
    assert first.season == "WINTER"
    assert first.format == "TV"
    assert first.episodes == 13
    assert first.status is TitleStatus.FINISHED
    assert first.prequel_ids == (151807,)


def test_search_sends_the_requested_limit() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_page([_SOLO_LEVELING]))

    catalog, http = _catalog(handler)
    with http:
        catalog.search("solo leveling", limit=3)

    assert json.loads(seen[0].content)["variables"]["limit"] == 3


def test_search_maps_an_unknown_status_and_missing_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([_MUSHOKU]))

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("mushoku tensei")[0]

    assert candidate.status is TitleStatus.UNKNOWN
    assert candidate.english is None
    assert candidate.episodes is None
    assert candidate.prequel_ids == ()


def test_search_skips_nodes_without_an_id_or_a_romaji_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        broken: list[dict[str, Any]] = [
            {"id": None, "title": {"romaji": "No Id"}},
            {"id": 7, "title": {"romaji": ""}},
            _MUSHOKU,
        ]
        return httpx.Response(200, json=_page(broken))

    catalog, http = _catalog(handler)
    with http:
        candidates = catalog.search("mushoku")

    assert [candidate.anilist_id for candidate in candidates] == [166873]


def test_search_retries_once_with_shortened_words_when_nothing_is_found() -> None:
    searched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        searched.append(_searched(request))
        if len(searched) == 1:
            return httpx.Response(200, json=_page([]))
        return httpx.Response(200, json=_page([_SOLO_LEVELING]))

    catalog, http = _catalog(handler)
    with http:
        candidates = catalog.search("solo levelling")

    assert searched == ["solo levelling", "sol level"]
    assert len(candidates) == 1


def test_search_does_not_retry_when_no_word_can_be_shortened() -> None:
    searched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        searched.append(_searched(request))
        return httpx.Response(200, json=_page([]))

    catalog, http = _catalog(handler)
    with http:
        assert catalog.search("one") == ()

    assert searched == ["one"]


def test_search_rejects_a_rate_limited_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"errors": [{"message": "Too Many Requests"}]})

    catalog, http = _catalog(handler)
    with http, pytest.raises(TitleCatalogError) as error:
        catalog.search("solo leveling")

    assert error.value.context.code is ErrorCode.TITLE_CATALOG_FAILED
    assert error.value.context.message == "AniList rejected the title search"
    assert error.value.context.suggestion == "Search again in a minute or type the title exactly"


def test_search_rejects_a_body_without_media() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"Page": {}}})

    catalog, http = _catalog(handler)
    with http, pytest.raises(TitleCatalogError) as error:
        catalog.search("solo leveling")

    assert error.value.context.message == "AniList returned an unreadable answer"


def test_search_rejects_a_body_without_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "Internal Error"}]})

    catalog, http = _catalog(handler)
    with http, pytest.raises(TitleCatalogError) as error:
        catalog.search("solo leveling")

    assert error.value.context.code is ErrorCode.TITLE_CATALOG_FAILED


def test_search_maps_a_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    catalog, http = _catalog(handler)
    with http, pytest.raises(TitleCatalogError) as error:
        catalog.search("solo leveling")

    assert error.value.context.message == "AniList could not be reached"


def test_aliases_keep_latin_names_without_repeats() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([_SOLO_LEVELING]))

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("solo leveling")[0]

    assert candidate.aliases() == (
        "Ore dake Level Up na Ken Season 2: Arise from the Shadow",
        "Solo Leveling Season 2: Arise from the Shadow",
        "Solo Leveling 2nd Season",
    )


def test_folder_title_prefers_english_and_falls_back_to_romaji() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([_SOLO_LEVELING, _MUSHOKU]))

    catalog, http = _catalog(handler)
    with http:
        candidates = catalog.search("anything")

    assert candidates[0].folder_title() == "Solo Leveling Season 2: Arise from the Shadow"
    assert candidates[1].folder_title() == "Mushoku Tensei III"


def test_episode_offset_sums_the_prequel_chain_and_ignores_movies_and_cycles() -> None:
    relations: dict[int, dict[str, Any]] = {
        151807: {
            "id": 151807,
            "episodes": 12,
            "format": "TV",
            "relations": {
                "edges": [
                    {"relationType": "PREQUEL", "node": {"id": 140501, "episodes": 11, "format": "TV"}},
                    {"relationType": "PREQUEL", "node": {"id": 178025, "episodes": 1, "format": "MOVIE"}},
                ]
            },
        },
        140501: {
            "id": 140501,
            "episodes": 11,
            "format": "TV",
            "relations": {
                "edges": [{"relationType": "PREQUEL", "node": {"id": 151807, "episodes": 12, "format": "TV"}}]
            },
        },
    }
    asked: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body: Any = json.loads(request.content)
        variables: dict[str, Any] = body["variables"]
        if "search" in variables:
            return httpx.Response(200, json=_page([_SOLO_LEVELING]))
        asked.append(int(variables["id"]))
        return httpx.Response(200, json={"data": {"Media": relations[int(variables["id"])]}})

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("solo leveling")[0]
        per_hop: tuple[PrequelEntry, ...] = catalog.prequel_episodes(candidate)
        offset: int = catalog.episode_offset(candidate)

    assert per_hop == (PrequelEntry(episodes=12, cour=False), PrequelEntry(episodes=11, cour=False))
    assert offset == 23
    assert asked == [151807, 140501, 151807, 140501]


def test_episode_offset_counts_an_unknown_episode_count_as_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body: Any = json.loads(request.content)
        if "search" in body["variables"]:
            return httpx.Response(200, json=_page([_SOLO_LEVELING]))
        media: dict[str, Any] = {"id": 151807, "episodes": None, "format": "TV", "relations": {"edges": []}}
        return httpx.Response(200, json={"data": {"Media": media}})

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("solo leveling")[0]
        assert catalog.episode_offset(candidate) == 0


def test_episode_offset_is_zero_without_a_prequel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([_MUSHOKU]))

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("mushoku tensei")[0]
        assert catalog.episode_offset(candidate) == 0


def test_prequel_episodes_is_empty_without_a_prequel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([_MUSHOKU]))

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("mushoku tensei")[0]
        assert catalog.prequel_episodes(candidate) == ()


def test_prequel_episodes_marks_an_entry_whose_title_names_a_cour() -> None:
    relations: dict[int, dict[str, Any]] = {
        151807: {
            "id": 151807,
            "episodes": 12,
            "format": "TV",
            "title": {"romaji": "Mushoku Tensei II: Isekai Ittara Honki Dasu Part 2", "english": None},
            "relations": {
                "edges": [{"relationType": "PREQUEL", "node": {"id": 140501, "episodes": 12, "format": "TV"}}]
            },
        },
        140501: {
            "id": 140501,
            "episodes": 12,
            "format": "TV",
            "title": {"romaji": "Mushoku Tensei II: Isekai Ittara Honki Dasu", "english": None},
            "relations": {"edges": []},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        variables: dict[str, Any] = json.loads(request.content)["variables"]
        if "search" in variables:
            return httpx.Response(200, json=_page([_SOLO_LEVELING]))
        return httpx.Response(200, json={"data": {"Media": relations[int(variables["id"])]}})

    catalog, http = _catalog(handler)
    with http:
        candidate: TitleCandidate = catalog.search("mushoku tensei")[0]
        entries: tuple[PrequelEntry, ...] = catalog.prequel_episodes(candidate)
        offset: int = catalog.episode_offset(candidate)

    assert entries == (PrequelEntry(episodes=12, cour=True), PrequelEntry(episodes=12, cour=False))
    assert offset == 24
