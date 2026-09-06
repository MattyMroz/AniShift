from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs
from xml.etree import ElementTree

import httpx
import pytest

from anishift.application.acquisition import AcquisitionService, CatalogOrder
from anishift.application.subscriptions import SUBSCRIPTIONS_FILE_NAME, SubscriptionService, SubscriptionStore
from anishift.services.catalog import AniListCatalog
from anishift.services.torrents import QBittorrentClient, parse_release_name, search_releases
from anishift.services.torrents.nyaa import NYAA_NAMESPACE
from anishift.services.torrents.query import parse_query

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from anishift.application.acquisition import ReleaseCatalog, SeasonContext, SeriesGroup
    from anishift.services.catalog import TitleCandidate
    from anishift.services.torrents import Release

FIXTURES: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "search"

QBITTORRENT_URL: Final[str] = "http://127.0.0.1:8080"

QBITTORRENT_HOST: Final[str] = "127.0.0.1"

NYAA_HOST: Final[str] = "nyaa.si"

ANILIST_HOST: Final[str] = "graphql.anilist.co"

XML_CONTENT_TYPE: Final[str] = "application/xml; charset=utf-8"

JSON_CONTENT_TYPE: Final[str] = "application/json; charset=utf-8"

ADD_ACCEPTED: Final[dict[str, object]] = {
    "added_torrent_ids": [],
    "failure_count": 0,
    "pending_count": 1,
    "success_count": 0,
}

ADD_REFUSED: Final[dict[str, object]] = {
    "added_torrent_ids": [],
    "failure_count": 1,
    "pending_count": 0,
    "success_count": 0,
}


def _manifest() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    return document


def _nyaa_bodies(manifest: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {
        (entry["query"], entry["category"]): (FIXTURES / entry["file"]).read_text(encoding="utf-8")
        for entry in manifest["nyaa"]
    }


def _anilist_bodies(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        json.dumps(entry["variables"], sort_keys=True): (FIXTURES / entry["file"]).read_text(encoding="utf-8")
        for entry in manifest["anilist"]
    }


def _feed_index(bodies: dict[tuple[str, str], str]) -> tuple[dict[str, str], dict[str, str]]:
    hashes: dict[str, str] = {}
    titles: dict[str, str] = {}
    for body in bodies.values():
        root = ElementTree.fromstring(body)  # noqa: S314
        for item in root.iter("item"):
            link = item.find("link")
            info_hash = item.find(f"{{{NYAA_NAMESPACE}}}infoHash")
            title = item.find("title")
            if link is None or not link.text or info_hash is None or not info_hash.text:
                continue
            hashes[link.text.strip()] = info_hash.text.strip()
            titles[link.text.strip()] = title.text.strip() if title is not None and title.text else ""
    return hashes, titles


MANIFEST: Final[dict[str, Any]] = _manifest()

NYAA_BODIES: Final[dict[tuple[str, str], str]] = _nyaa_bodies(MANIFEST)

ANILIST_BODIES: Final[dict[str, str]] = _anilist_bodies(MANIFEST)

INFO_HASHES, TORRENT_TITLES = _feed_index(NYAA_BODIES)


@dataclass(frozen=True, slots=True)
class AddedTorrent:
    url: str
    save_path: str
    category: str
    info_hash: str

    @property
    def title(self) -> str:
        return TORRENT_TITLES.get(self.url, self.url)


@dataclass(slots=True)
class FakeQBittorrent:
    refuse: bool = False
    logins: int = 0
    added: list[AddedTorrent] = field(default_factory=list)
    settings: dict[str, object] = field(
        default_factory=lambda: {"incomplete_files_ext": False, "save_path": "C:/downloads"}
    )

    def handle(self, request: httpx.Request) -> httpx.Response:
        routes: dict[str, Callable[[httpx.Request], httpx.Response]] = {
            "/auth/login": self._login,
            "/app/version": self._version,
            "/app/preferences": self._preferences,
            "/app/setPreferences": self._set_preferences,
            "/torrents/add": self._add,
            "/torrents/info": self._info,
        }
        route = routes.get(request.url.path.removeprefix("/api/v2"))
        if route is None:
            return httpx.Response(HTTPStatus.NOT_FOUND, text="")
        return route(request)

    def _login(self, request: httpx.Request) -> httpx.Response:
        self.logins += 1
        return httpx.Response(HTTPStatus.OK, text="Ok.")

    def _version(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.OK, text="v5.2.3\n")

    def _preferences(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.OK, json=self.settings)

    def _set_preferences(self, request: httpx.Request) -> httpx.Response:
        self.settings.update(json.loads(_form(request)["json"][0]))
        return httpx.Response(HTTPStatus.OK, text="Ok.")

    def _add(self, request: httpx.Request) -> httpx.Response:
        if self.refuse:
            return httpx.Response(HTTPStatus.ACCEPTED, json=ADD_REFUSED)
        form: dict[str, list[str]] = _form(request)
        url: str = form["urls"][0]
        self.added.append(
            AddedTorrent(
                url=url,
                save_path=form["savepath"][0],
                category=form["category"][0],
                info_hash=INFO_HASHES.get(url, ""),
            )
        )
        return httpx.Response(HTTPStatus.ACCEPTED, json=ADD_ACCEPTED)

    def _info(self, request: httpx.Request) -> httpx.Response:
        category: str = request.url.params.get("category", "")
        return httpx.Response(
            HTTPStatus.OK,
            json=[
                {
                    "name": torrent.title,
                    "hash": torrent.info_hash,
                    "progress": 0.0,
                    "state": "downloading",
                    "save_path": torrent.save_path,
                }
                for torrent in self.added
                if torrent.category == category
            ],
        )


@dataclass(frozen=True, slots=True)
class Composed:
    acquisition: AcquisitionService
    subscriptions: SubscriptionService
    client: FakeQBittorrent
    store: SubscriptionStore
    workspace_root: Path
    nyaa_queries: list[tuple[str, str]]

    def resolve(self, phrase: str, prefer: str) -> Resolved:
        query = parse_query(phrase)
        candidates: tuple[TitleCandidate, ...] = self.acquisition.find_titles(query.title)
        candidate: TitleCandidate = next(
            item for item in candidates if prefer.casefold() in f"{item.romaji} {item.english or ''}".casefold()
        )
        context: SeasonContext = self.acquisition.season_context(candidate)
        self.nyaa_queries.clear()
        catalog: ReleaseCatalog = self.acquisition.search_title(
            candidate, episodes=query.episodes, order=CatalogOrder.NEWEST, context=context
        )
        return Resolved(candidates=candidates, candidate=candidate, context=context, catalog=catalog)


@dataclass(frozen=True, slots=True)
class Resolved:
    candidates: tuple[TitleCandidate, ...]
    candidate: TitleCandidate
    context: SeasonContext
    catalog: ReleaseCatalog

    def groups_of(self, group: str) -> tuple[SeriesGroup, ...]:
        return tuple(item for item in self.catalog.groups if item.group.casefold() == group.casefold())


@pytest.fixture(name="composed")
def composed_fixture(tmp_path: Path) -> Iterator[Composed]:
    client: FakeQBittorrent = FakeQBittorrent()
    queries: list[tuple[str, str]] = []
    http: httpx.Client = httpx.Client(transport=httpx.MockTransport(handler(client, queries)), follow_redirects=True)
    with http:
        yield _build(client, http, tmp_path, queries)


def _build(client: FakeQBittorrent, http: httpx.Client, tmp_path: Path, queries: list[tuple[str, str]]) -> Composed:
    class NyaaSource:
        def search(self, query: str) -> tuple[Release, ...]:
            return search_releases(query, http=http)

    workspace_root: Path = tmp_path / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    acquisition: AcquisitionService = AcquisitionService(
        source=NyaaSource(),
        client=QBittorrentClient(QBITTORRENT_URL, http=http),
        workspace_root=workspace_root,
        parse_name=parse_release_name,
        title_catalog=AniListCatalog(http),
    )
    store: SubscriptionStore = SubscriptionStore(tmp_path / "config" / SUBSCRIPTIONS_FILE_NAME)
    return Composed(
        acquisition=acquisition,
        subscriptions=SubscriptionService(store=store, acquisition=acquisition),
        client=client,
        store=store,
        workspace_root=workspace_root,
        nyaa_queries=queries,
    )


def handler(client: FakeQBittorrent, queries: list[tuple[str, str]]) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        host: str | None = request.url.host
        if host == NYAA_HOST:
            key: tuple[str, str] = (request.url.params.get("q", ""), request.url.params.get("c", ""))
            queries.append(key)
            body: str | None = NYAA_BODIES.get(key)
            if body is None:
                return httpx.Response(HTTPStatus.NOT_FOUND, text="")
            return httpx.Response(
                HTTPStatus.OK, content=body.encode("utf-8"), headers={"content-type": XML_CONTENT_TYPE}
            )
        if host == ANILIST_HOST:
            variables: object = json.loads(request.content.decode("utf-8"))["variables"]
            payload: str | None = ANILIST_BODIES.get(json.dumps(variables, sort_keys=True))
            if payload is None:
                return httpx.Response(HTTPStatus.NOT_FOUND, text="")
            return httpx.Response(
                HTTPStatus.OK, content=payload.encode("utf-8"), headers={"content-type": JSON_CONTENT_TYPE}
            )
        if host == QBITTORRENT_HOST:
            return client.handle(request)
        return httpx.Response(HTTPStatus.NOT_FOUND, text="")

    return handle


def _form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode("utf-8"))
