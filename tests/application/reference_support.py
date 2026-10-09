from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Final

import httpx
from test_acquisition import _Client
from test_episode_search import NyaaSource, controlled, search_service

from anishift.application.acquisition import AcquisitionService, ListingRead, SubscriptionSearch
from anishift.application.episode_search import SourceSwitches
from anishift.application.episode_selection import EpisodeKey, EpisodeOffer, visible
from anishift.application.subscription_choice import (
    ChoiceDecision,
    ChoiceState,
    choice_candidate,
    decide,
    polish_history,
    release_hash,
    wait_until,
)
from anishift.application.subscription_targets import (
    PolishObservation,
    PolishState,
    SubscriptionRecord,
    SubscriptionTarget,
    TargetState,
    merge_listing,
)
from anishift.config.user_settings import DEFAULT_POLISH_WAIT_H
from anishift.services.catalog import AniListCatalog, AniZipCatalog, ArmCatalog, KitsuCatalog
from anishift.services.http_requests import RequestControl
from anishift.services.torrents import TorrentioSource, parse_release_name

type Document = dict[str, Any]
type RequestKey = tuple[str, str, str, tuple[tuple[str, str], ...], str | None]

REFERENCE: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "acquisition" / "reference"
BASELINE_PAIRS: Final[int] = 640
GATE: Final[float] = 0.95
CASES: Final[tuple[str, ...]] = tuple(
    sorted(path.name.removesuffix(".json.gz") for path in REFERENCE.glob("[0-9]*-[0-9]*.json.gz"))
)
_XML_HOSTS: Final[frozenset[str]] = frozenset({"nyaa.si", "nekobt.to"})
_SUBSCRIBED_AT: Final[str] = "2000-01-01T00:00:00+00:00"
_KITSU_MAPPINGS: Final[str] = "/api/edge/mappings"


def _load(name: str) -> Document:
    document: Document = json.loads(gzip.decompress((REFERENCE / name).read_bytes()))
    return document


@cache
def fixture(case: str) -> Document:
    return _load(f"{case}.json.gz")


@cache
def expectations() -> Document:
    return _load("expectations.json.gz")


@cache
def baseline() -> Document:
    return _load("coverage-baseline.json.gz")


def research_cases() -> tuple[str, ...]:
    return tuple(name for name in baseline() if not name.startswith("_"))


def _shape(body: str) -> str:
    payload: dict[str, Any] = json.loads(body)
    query: str = payload["query"]
    root: str = "airingSchedule" if "airingSchedule" in query else "Page" if "Page(" in query else "Media"
    return root + json.dumps(payload.get("variables"), sort_keys=True)


def request_key(method: str, url: httpx.URL, body: str | None) -> RequestKey:
    params: httpx.QueryParams = url.params.remove("page[limit]") if url.path == _KITSU_MAPPINGS else url.params
    return (
        method,
        url.host,
        url.path,
        tuple(sorted(params.multi_items())),
        None if body is None else _shape(body),
    )


@dataclass(slots=True)
class Replay:
    rows: dict[RequestKey, dict[str, Any]]
    misses: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, document: Document, mode: str, dropped: frozenset[str] = frozenset()) -> Replay:
        allowed: set[int] = set(document["modes"][mode])
        appended: set[int] = set(document["notes"].get("appended_k16", {}).get("responses", ()))
        rows: dict[RequestKey, dict[str, Any]] = {}
        for index, row in enumerate(document["responses"]):
            url: httpx.URL = httpx.URL(row["url"])
            if index not in allowed or url.host in dropped:
                continue
            key: RequestKey = request_key(row["method"], url, row.get("request_body"))
            if key in rows and index not in appended:
                msg: str = f"{document['case']} {mode}: response {index} repeats a recorded request"
                raise ValueError(msg)
            rows[key] = row
        return cls(rows)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body: str | None = request.content.decode() if request.method == "POST" else None
        row: dict[str, Any] | None = self.rows.get(request_key(request.method, request.url, body))
        if row is None:
            self.misses.append(f"{request.method} {request.url}")
            raise httpx.ConnectError("not recorded", request=request)
        if "status" not in row:
            raise httpx.ConnectError(row["error"], request=request)
        kind: str = "application/xml" if request.url.host in _XML_HOSTS else "application/json"
        return httpx.Response(row["status"], text=row["body"], headers={"content-type": kind})


def captured_at(document: Document) -> datetime:
    return datetime.fromisoformat(document["captured_at"])


def case_key(document: Document) -> EpisodeKey:
    return EpisodeKey(document["anilist"]["id"], document["number"])


@contextmanager
def _service(document: Document, replay: Replay) -> Iterator[AcquisitionService]:
    control: RequestControl = controlled(replay)
    moment: float = captured_at(document).timestamp()
    with httpx.Client(transport=control) as http:
        anizip: AniZipCatalog = AniZipCatalog(http)
        yield AcquisitionService(
            source=NyaaSource(http),
            client=_Client(),
            workspace_root=REFERENCE,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
            request_control=control,
            episode_catalog=anizip,
            id_catalog=ArmCatalog(http),
            anidb_catalog=anizip,
            kitsu_catalog=KitsuCatalog(http),
            stream_source=TorrentioSource(http),
            episode_search=search_service(http, control),
            clock=lambda: moment,
        )


@dataclass(frozen=True, slots=True)
class Manual:
    offer: EpisodeOffer
    misses: tuple[str, ...]

    def top3(self) -> list[str]:
        return [release_hash(row.stream.info_hash) for row in visible(self.offer.candidates)[:3]]

    def hashes(self) -> frozenset[str]:
        return frozenset(release_hash(row.stream.info_hash) for row in self.offer.candidates)


@cache
def manual(case: str, dropped: frozenset[str] = frozenset()) -> Manual:
    document: Document = fixture(case)
    replay: Replay = Replay.of(document, "manual", dropped)
    key: EpisodeKey = case_key(document)
    with _service(document, replay) as service, service.episode_requests():
        read: ListingRead = service.read_listing(key.anilist_id)
        offer, _target = service.search_episode(key, SourceSwitches(), read=read)
    return Manual(offer, tuple(replay.misses))


@dataclass(frozen=True, slots=True)
class Automatic:
    target: SubscriptionTarget
    misses: tuple[str, ...]
    search: SubscriptionSearch | None = None
    history: PolishState | None = None
    decision: ChoiceDecision | None = None
    after_wait: ChoiceDecision | None = None

    def hashes(self) -> frozenset[str]:
        if self.search is None:
            return frozenset()
        return frozenset(release_hash(row.stream.info_hash) for row in self.search.offer.candidates)


def _decide(search: SubscriptionSearch, due: datetime, history: PolishState, now: datetime) -> ChoiceDecision:
    state: ChoiceState = ChoiceState(
        excluded=frozenset(),
        threshold=None,
        failures=search.failures,
        tsukihime=search.tsukihime,
        wait_until=wait_until(due, history, DEFAULT_POLISH_WAIT_H),
    )
    return decide(tuple(choice_candidate(row) for row in search.offer.candidates), state, now)


@cache
def automatic(case: str) -> Automatic:
    document: Document = fixture(case)
    replay: Replay = Replay.of(document, "subscription")
    key: EpisodeKey = case_key(document)
    record: SubscriptionRecord = SubscriptionRecord("reference", key.anilist_id, case, _SUBSCRIBED_AT, 0)
    with _service(document, replay) as service:
        with service.episode_requests():
            read: ListingRead = service.read_listing(key.anilist_id, targets=(key.number,))
        target: SubscriptionTarget = next(
            item for item in merge_listing(record, read, captured_at(document)).targets if item.number == key.number
        )
        if target.state is not TargetState.DUE or target.due_at is None:
            return Automatic(target, tuple(replay.misses))
        due: datetime = datetime.fromisoformat(target.due_at)
        with service.episode_requests():
            search: SubscriptionSearch = service.subscription_check(
                key, read, SourceSwitches(), failures=(), excluded=(), tsukihime_id=None, history_at=due
            )
    observation: PolishObservation | None = (
        None if search.polish is None else PolishObservation(search.polish, target.due_at)
    )
    history: PolishState = polish_history(observation, local=False)
    decision: ChoiceDecision = _decide(search, due, history, due)
    after: ChoiceDecision | None = (
        _decide(search, due, history, decision.wait_until) if decision.wait_until is not None else None
    )
    return Automatic(target, tuple(replay.misses), search, history, decision, after)


def proven_gone(pairs: Mapping[str, Any], case: str) -> frozenset[str]:
    entry: Mapping[str, Any] = pairs[case]
    requery: Mapping[str, Any] = entry.get("requery", {})
    return frozenset(
        info_hash
        for info_hash, pair in entry.get("missing", {}).items()
        if pair["status"] == "gone"
        and all(source in requery and requery[source]["complete"] for source in pair["research_sources"])
    )


def covered(pairs: Mapping[str, Any], found: Mapping[str, frozenset[str]]) -> int:
    return sum(len(set(pairs[case]["union"]) & found[case]) for case in found)


def coverage(pairs: Mapping[str, Any], found: Mapping[str, frozenset[str]]) -> float:
    return covered(pairs, found) / BASELINE_PAIRS


def diagnostic_coverage(pairs: Mapping[str, Any], found: Mapping[str, frozenset[str]]) -> float:
    gone: int = sum(len(proven_gone(pairs, case)) for case in found)
    return covered(pairs, found) / (BASELINE_PAIRS - gone)


def case_coverage(pairs: Mapping[str, Any], case: str, found: frozenset[str]) -> float:
    union: set[str] = set(pairs[case]["union"])
    return len(union & found) / len(union)
