from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.torrents.errors import TorrentClientError
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.torrents.types import TorrentFile, TorrentInfo

BASE_URL = "http://127.0.0.1:8080"
CREDENTIAL = "s3cr3t"


def test_current_login_cookies_stay_with_their_instance() -> None:
    calls: list[tuple[int | None, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        port: int | None = request.url.port
        cookie: str = f"QBT_SID_{port}=session-{port}"
        calls.append((port, request.headers.get("cookie", "")))
        if request.url.path.endswith("/login"):
            return httpx.Response(204, headers={"Set-Cookie": cookie + "; Path=/; HttpOnly"})
        if request.headers.get("cookie") != cookie:
            return httpx.Response(403)
        return httpx.Response(200, text="v5.2.3")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        first: QBittorrentClient = QBittorrentClient("http://127.0.0.1:18081", http=http)
        second: QBittorrentClient = QBittorrentClient("http://127.0.0.1:18082", http=http)
        assert first.version() == second.version() == first.version() == "5.2.3"
    assert calls[-1] == (18081, "QBT_SID_18081=session-18081")
    assert all(not cookie or str(port) in cookie for port, cookie in calls)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    username: str = "admin",
    password: str = CREDENTIAL,
) -> tuple[QBittorrentClient, httpx.Client]:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return QBittorrentClient(BASE_URL, username=username, password=password, http=http), http


def _form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode("utf-8"))


def test_version_returns_the_trimmed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/app/version"
        return httpx.Response(200, text="v5.2.3\n")

    client, http = _client(handler)
    with http:
        assert client.version() == "5.2.3"


def test_preferences_returns_the_decoded_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"incomplete_files_ext": True, "save_path": "C:/downloads"})

    client, http = _client(handler)
    with http:
        assert client.preferences()["incomplete_files_ext"] is True


def test_set_preferences_sends_the_values_in_a_json_form_field() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="")

    client, http = _client(handler)
    with http:
        client.set_preferences({"incomplete_files_ext": True})

    assert seen[0].url.path == "/api/v2/app/setPreferences"
    assert json.loads(_form(seen[0])["json"][0]) == {"incomplete_files_ext": True}


def test_add_torrent_sends_the_save_path_and_category() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="Ok.")

    client, http = _client(handler)
    with http:
        client.add_torrent(
            "https://nyaa.si/download/2156981.torrent",
            save_path=Path("C:/workspace/Neko to Ryuu"),
            category="AniShift",
        )

    form = _form(seen[0])
    assert seen[0].url.path == "/api/v2/torrents/add"
    assert form["urls"] == ["https://nyaa.si/download/2156981.torrent"]
    assert form["savepath"] == [str(Path("C:/workspace/Neko to Ryuu"))]
    assert form["category"] == ["AniShift"]


def test_add_torrent_accepts_the_pending_report_of_a_newer_web_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        report = {"added_torrent_ids": [], "failure_count": 0, "pending_count": 1, "success_count": 0}
        return httpx.Response(202, json=report)

    client, http = _client(handler)
    with http:
        client.add_torrent("https://nyaa.si/download/1.torrent", save_path=Path("C:/w"), category="AniShift")


def test_add_torrent_reports_a_failed_pending_report() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        report = {"added_torrent_ids": [], "failure_count": 1, "pending_count": 0, "success_count": 0}
        return httpx.Response(202, json=report)

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.add_torrent("https://nyaa.si/download/1.torrent", save_path=Path("C:/w"), category="AniShift")

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED


def test_add_torrent_reports_a_refusal_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Fails.")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.add_torrent("https://nyaa.si/download/1.torrent", save_path=Path("C:/w"), category="AniShift")

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED
    assert error.value.context.message == "qBittorrent refused the torrent"
    assert error.value.context.suggestion == "It may already be in the client"


def test_add_torrent_reports_an_unsupported_media_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(415, text="")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.add_torrent("https://nyaa.si/download/1.torrent", save_path=Path("C:/w"), category="AniShift")

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED


def test_request_logs_in_once_after_forbidden_and_retries() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/v2/auth/login":
            assert _form(request)["username"] == ["admin"]
            assert request.headers["referer"] == BASE_URL
            return httpx.Response(200, text="Ok.")
        if seen.count("/api/v2/app/version") == 1:
            return httpx.Response(403, text="Forbidden")
        return httpx.Response(200, text="v5.2.3")

    client, http = _client(handler)
    with http:
        assert client.version() == "5.2.3"

    assert seen == ["/api/v2/app/version", "/api/v2/auth/login", "/api/v2/app/version"]


def test_request_reports_unauthorized_when_the_login_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Fails.")
        return httpx.Response(403, text="Forbidden")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.version()

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_UNAUTHORIZED
    assert "ANISHIFT_QBITTORRENT_USERNAME" in error.value.context.suggestion


def test_request_reports_unauthorized_on_a_second_forbidden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        return httpx.Response(403, text="Forbidden")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.version()

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_UNAUTHORIZED


def test_request_reports_an_unreachable_web_ui() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.version()

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_UNAVAILABLE
    assert error.value.context.message == "qBittorrent Web UI is not reachable"


def test_request_reports_a_refusal_for_an_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.version()

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED


def test_torrents_maps_progress_state_and_save_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "name": "[DKB] Neko to Ryuu - S01E11",
                    "hash": "b456eb3845297c1c99cd359274981ae904328084",
                    "progress": 0.42,
                    "state": "downloading",
                    "save_path": "C:\\workspace\\Neko to Ryuu",
                },
                "not a torrent",
            ],
        )

    client, http = _client(handler)
    with http:
        torrents: tuple[TorrentInfo, ...] = client.torrents("AniShift")

    assert seen[0].url.params["category"] == "AniShift"
    assert torrents == (
        TorrentInfo(
            name="[DKB] Neko to Ryuu - S01E11",
            info_hash="b456eb3845297c1c99cd359274981ae904328084",
            progress=0.42,
            state="downloading",
            save_path="C:\\workspace\\Neko to Ryuu",
        ),
    )


def test_torrent_files_preserve_selection_and_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/torrents/files"
        assert request.url.params["hash"] == "abc"
        return httpx.Response(
            200,
            json=[
                {"index": 0, "name": "Folder/Episode.mkv", "size": 4, "progress": 1.0, "priority": 1, "is_seed": True}
            ],
        )

    client, http = _client(handler)
    with http:
        assert client.files("abc") == (TorrentFile(0, "Folder/Episode.mkv", 4, 1.0, 1, True),)


@pytest.mark.parametrize(
    ("key", "value"), [("size", -1), ("size", True), ("progress", "1"), ("progress", 1.1), ("is_seed", "true")]
)
def test_invalid_file_metadata_cannot_prove_completion(key: str, value: object) -> None:
    entry: dict[str, object] = {
        "index": 0,
        "name": "Episode.mkv",
        "size": 4,
        "progress": 1.0,
        "priority": 1,
        "is_seed": True,
    }
    entry[key] = value

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[entry])

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError):
        client.files("abc")


@pytest.mark.parametrize("remaining", [None, 0, 3, -1, True, "0"])
def test_only_valid_remaining_byte_counts_can_prove_completion(remaining: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"hash": "abc", "amount_left": remaining, "completed": 4}])

    client, http = _client(handler)
    with http:
        transfer: TorrentInfo = client.torrents("AniShift")[0]
    assert transfer.amount_left == (remaining if type(remaining) is int and remaining >= 0 else None)
    assert transfer.completed == 4


def test_torrents_rejects_an_unreadable_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError) as error:
        client.torrents("AniShift")

    assert error.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED
