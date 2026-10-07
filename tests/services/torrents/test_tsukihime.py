from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import httpx
import pytest
from recorded_sources import CASES, RecordedResponse, recorded_response, responses

from anishift.application.episode_search import TsukiHimeApi, TsukiHimeLookup, TsukiHimePage
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.errors import TorrentSourceError
from anishift.services.torrents.tsukihime import TsukiHimeSource


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES)
def test_recorded_tsukihime_responses(case: str) -> None:
    for row in responses(case, "api.tsukihime.org"):
        seen: list[httpx.Request] = []

        def respond(
            request: httpx.Request, row: RecordedResponse = row, seen: list[httpx.Request] = seen
        ) -> httpx.Response:
            seen.append(request)
            return recorded_response(row, request)

        url: httpx.URL = httpx.URL(row["url"])
        parts: list[str] = url.path.split("/")
        raw: dict[str, object] = json.loads(row["body"])
        with httpx.Client(transport=RequestControl(httpx.MockTransport(respond))) as client:
            source: TsukiHimeApi = TsukiHimeSource(client)
            if "/anilist/" in url.path:
                assert source.anime_id(int(parts[-1])) == (raw["id"] if row["status"] == 200 else None)
            elif "/episodes/" in url.path:
                page: TsukiHimePage = source.episode_page(int(parts[-3]), int(parts[-1]), int(url.params["offset"]))
                assert (page.total, page.start, page.limit) == (raw["total"], raw["start"], raw["limit"])
                rows: list[dict[str, object]] = cast("list[dict[str, object]]", raw["results"])
                assert [stream.release for stream in page.streams] == [item["name"] for item in rows]
                assert all(stream.source == "tsukihime" and stream.file_name is None for stream in page.streams)
            else:
                lookup: TsukiHimeLookup = (
                    source.torrent_by_hash(parts[-1]) if "/btih/" in url.path else source.torrent_files(int(parts[-1]))
                )
                assert lookup.status == row["status"]
                files: list[dict[str, object]] = cast("list[dict[str, object]]", raw.get("files", []))
                if row["status"] == 200 and files and len(files) == raw.get("filecount"):
                    assert lookup.files is not None
                    assert [file.path for file in lookup.files.files] == [file["filename"] for file in files]
                    assert [file.size for file in lookup.files.files] == [file["size"] for file in files]
                else:
                    assert lookup.files is None
        assert len(seen) == 1


@pytest.mark.unit
def test_episode_page_offset_param_start_field() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"limit": "100", "offset": "100"}
        return httpx.Response(200, json={"start": 100, "limit": 100, "total": 101, "results": []})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert TsukiHimeSource(client).episode_page(42, 1, 100) == TsukiHimePage((), 101, 100, 100)


@pytest.mark.unit
def test_episode_page_and_anime_missing_title() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        source: TsukiHimeSource = TsukiHimeSource(client)
        assert source.anime_id(42) is None
        assert source.episode_page(42, 1, 0).streams == ()


@pytest.mark.unit
def test_torrent_by_hash_200_files_is_listing() -> None:
    body: dict[str, object] = {
        "id": 42,
        "filecount": 1,
        "files": [
            {
                "filename": "Original\\01.mkv",
                "size": 123,
                "sublangs": ["pl-PL"],
                "audiolangs": ["ja-JP"],
                "links": [],
                "links_audio": [],
            }
        ],
    }
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path.endswith("/" + "a" * 40)
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        lookup: TsukiHimeLookup = TsukiHimeSource(client).torrent_by_hash("A" * 40)
    assert lookup.files is not None
    assert lookup.files.files[0].path == "Original\\01.mkv"
    assert lookup.files.files[0].subtitle_languages == ("pl",)
    assert lookup.files.files[0].audio_languages == ("ja",)
    assert len(requests) == 1


@pytest.mark.unit
def test_btih_partial_files_reads_torrent() -> None:
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        files: list[dict[str, object]] = [{"filename": "01.mkv", "size": 12}]
        if "/btih/" not in request.url.path:
            files.append({"filename": "02.mkv", "size": 15})
        return httpx.Response(200, json={"id": 42, "filecount": 2, "files": files})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        source: TsukiHimeSource = TsukiHimeSource(client)
        first: TsukiHimeLookup = source.torrent_by_hash("a" * 40)
        assert first.files is None
        assert first.torrent_id == 42
        assert len(paths) == 1
        second: TsukiHimeLookup = source.torrent_files(first.torrent_id)
        assert second.files is not None
        assert len(second.files.files) == 2
    assert paths == ["/v1/torrents/btih/" + "a" * 40, "/v1/torrents/42"]


@pytest.mark.unit
@pytest.mark.parametrize("count", [None, 2, 0])
def test_torrent_files_partial_is_not_listing(count: int | None) -> None:
    body: dict[str, object] = {"id": 42, "filecount": count, "files": [{"filename": "01.mkv", "size": 12}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client:
        assert TsukiHimeSource(client).torrent_files(42).files is None


@pytest.mark.unit
@pytest.mark.parametrize("status", [202, 404, 429])
def test_torrent_by_hash_202_files_not_listing(status: int) -> None:
    body: dict[str, object] = {"id": 42, "filecount": 1, "files": [{"filename": "01.mkv", "size": 12}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))) as client:
        lookup: TsukiHimeLookup = TsukiHimeSource(client).torrent_by_hash("a" * 40)
    assert lookup.status == status
    assert lookup.files is None
    assert lookup.torrent_id == (42 if status == 202 else None)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body", [{}, {"id": True}, {"id": 1, "files": "wrong"}, {"id": 1, "filecount": 1, "files": [{}]}]
)
def test_torrent_files_rejects_malformed_metadata(body: Mapping[str, object]) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))) as client,
        pytest.raises(TorrentSourceError) as caught,
    ):
        TsukiHimeSource(client).torrent_files(1)
    assert isinstance(caught.value.__cause__, (TypeError, ValueError))


@pytest.mark.unit
@pytest.mark.parametrize("status", [200, 202, 404, 429])
def test_torrent_files_empty_and_statuses(status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"id": 42, "files": [], "filecount": 0}))
    ) as client:
        lookup: TsukiHimeLookup = TsukiHimeSource(client).torrent_files(42)
    assert lookup.status == status
    assert lookup.files is None


@pytest.mark.unit
def test_episode_page_preserves_languages_id_count_and_duplicate_hashes() -> None:
    row: dict[str, object] = {
        "id": 42,
        "name": "Example",
        "btih": "A" * 40,
        "filecount": 2,
        "totalsize": 1024,
        "sublangs": ["pl-PL"],
        "audiolangs": ["ja-JP", "PL"],
    }
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"total": 2, "start": 0, "limit": 100, "results": [row, row]})
        )
    ) as client:
        page: TsukiHimePage = TsukiHimeSource(client).episode_page(1, 1, 0)
    assert len(page.streams) == 2
    assert page.streams[0].info_hash == "a" * 40
    assert page.streams[0].subtitle_languages == ("pl",)
    assert page.streams[0].audio_languages == ("ja", "pl")
    assert page.streams[0].file_count == 2
    assert page.streams[0].torrent_id == 42
    assert page.streams[0].seeders is None
