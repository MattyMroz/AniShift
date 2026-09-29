from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from anishift.errors import ErrorCode
from anishift.services.torrents.errors import TorrentClientError
from anishift.services.torrents.qbittorrent import QBittorrentClient, magnet_url
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
                {
                    "index": 0,
                    "name": "Folder/Episode.mkv",
                    "size": 4,
                    "progress": 1.0,
                    "priority": 1,
                    "is_seed": True,
                    "availability": 1.0,
                    "piece_range": [0, 3],
                },
                {
                    "index": 1,
                    "name": "Folder/Episode.ass",
                    "size": 2,
                    "progress": 1.0,
                    "priority": 1,
                    "availability": 1.0,
                    "piece_range": [4, 4],
                },
            ],
        )

    client, http = _client(handler)
    with http:
        assert client.files("abc") == (
            TorrentFile(0, "Folder/Episode.mkv", 4, 1.0, 1),
            TorrentFile(1, "Folder/Episode.ass", 2, 1.0, 1),
        )


@pytest.mark.parametrize(("key", "value"), [("size", -1), ("size", True), ("progress", "1"), ("progress", 1.1)])
def test_invalid_file_metadata_cannot_prove_completion(key: str, value: object) -> None:
    entry: dict[str, object] = {"index": 0, "name": "Episode.mkv", "size": 4, "progress": 1.0, "priority": 1}
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


@pytest.mark.unit
@pytest.mark.parametrize("status", [200, 202])
def test_metadata_add_sends_exact_stop_condition_and_never_starts_content(status: int) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"failure_count": 0, "pending_count": 1})

    client, http = _client(handler)
    with http:
        client.add_metadata("A" * 40, save_path=Path("staging/data"), category="AniShift")
    assert len(seen) == 1
    assert seen[0].url.path == "/api/v2/torrents/add"
    assert _form(seen[0]) == {
        "urls": [magnet_url("a" * 40)],
        "savepath": [str(Path("staging/data"))],
        "category": ["AniShift"],
        "stopped": ["false"],
        "stopCondition": ["MetadataReceived"],
        "autoTMM": ["false"],
        "contentLayout": ["Original"],
        "useDownloadPath": ["false"],
    }


@pytest.mark.unit
def test_priority_request_uses_actual_indexes_and_form_fields() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    client, http = _client(handler)
    with http:
        client.set_file_priority("a" * 40, frozenset({0, 3, 9}), 0)
        client.set_file_priority("a" * 40, frozenset({3, 9}), 1)
    assert [_form(item) for item in seen] == [
        {"hash": ["a" * 40], "id": ["0|3|9"], "priority": ["0"]},
        {"hash": ["a" * 40], "id": ["3|9"], "priority": ["1"]},
    ]
    assert all(item.url.path == "/api/v2/torrents/filePrio" for item in seen)


@pytest.mark.unit
@pytest.mark.parametrize(
    "tracker",
    [
        "http://localhost/announce",
        "udp://127.0.0.1:123/announce",
        "http://192.168.0.1/announce",
        "https://user:password@example.org/announce",
        "https://example.org/announce?token=secret",
        "https://example.org/announce#secret",
        "file:///announce",
        "https://example.org/\nannounce",
    ],
)
def test_magnet_refuses_nonpublic_or_credential_bearing_trackers(tracker: str) -> None:
    with pytest.raises(ValueError, match="public address"):
        magnet_url("a" * 40, (tracker,))


@pytest.mark.unit
def test_magnet_encodes_trackers_and_rejects_hash_injection() -> None:
    tracker: str = "udp://tracker.example.org:6969/announce"
    assert parse_qs(magnet_url("A" * 40, (tracker, tracker)).split("?", 1)[1]) == {
        "xt": ["urn:btih:" + "a" * 40],
        "tr": [tracker],
    }
    with pytest.raises(ValueError, match="hexadecimal v1 info hash"):
        magnet_url("a" * 40 + "&tr=evil")


@pytest.mark.unit
def test_legacy_stopped_add_keeps_both_flags_without_metadata_stop_condition() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="Ok.")

    client, http = _client(handler)
    with http:
        client.add_torrent("https://example.org/1.torrent", save_path=Path("legacy"), category="AniShift", stopped=True)
    assert _form(seen[0]) == {
        "urls": ["https://example.org/1.torrent"],
        "savepath": ["legacy"],
        "category": ["AniShift"],
        "stopped": ["true"],
        "paused": ["true"],
    }


@pytest.mark.unit
@pytest.mark.parametrize("host", ["127.1", "0x7f.1", "0177.1", "tracker.123"])
def test_tracker_host_rejects_noncanonical_numeric_addresses(host: str) -> None:
    with pytest.raises(ValueError, match="public address"):
        magnet_url("a" * 40, (f"http://{host}/announce",))


@pytest.mark.unit
@pytest.mark.parametrize(
    "report",
    [
        {"failure_count": 0},
        {"failure_count": 0, "success_count": 0, "pending_count": 0},
        {"failure_count": 0, "success_count": True},
        {"failure_count": 0, "pending_count": -1},
        {"failure_count": False, "success_count": 1},
    ],
)
def test_add_report_requires_at_least_one_real_accepted_or_pending_torrent(report: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=report)

    client, http = _client(handler)
    with http, pytest.raises(TorrentClientError):
        client.add_metadata("a" * 40, save_path=Path("staging"), category="AniShift")
