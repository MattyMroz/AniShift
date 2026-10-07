from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, wait
from dataclasses import replace
from typing import Final

import httpx
import pytest
from test_episode_selection import _target

from anishift.application.acquisition import SeasonContext, graph_candidate, graph_season_context
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.episode_releases import NAME_PRIORITY
from anishift.application.episode_search import (
    FIRST_SNAPSHOT_S,
    EpisodeRequest,
    EpisodeSearch,
    FailureKind,
    ReadOutcome,
    SearchOutcome,
    SearchSnapshot,
    SourceResult,
    SourceState,
    SourceSwitches,
    episode_phrases,
    offer_status,
    source_line,
)
from anishift.application.episode_selection import EpisodeKey, FranchiseGraph, RankedCandidate, StreamCandidate
from anishift.application.release_quality import PolishClass
from anishift.services.catalog.types import TitleCandidate, TitleStatus
from anishift.services.http_requests import RequestControl
from anishift.services.torrents.categories import SEARCH_CATEGORIES
from anishift.services.torrents.knaben import KnabenSource
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.nekobt import NekoBTSource
from anishift.services.torrents.nyaa import search_releases
from anishift.services.torrents.torrentio import TorrentioSource
from anishift.services.torrents.tsukihime import TsukiHimeSource
from anishift.services.torrents.types import Release

pytestmark = pytest.mark.integration

_HASH: Final[str] = "a" * 40
_REQUEST: Final[EpisodeRequest] = EpisodeRequest(
    EpisodeKey(1, 5), 5, False, False, 1, None, ("Star Garden - 05",), _target(), True
)
_NYAA: Final[SourceSwitches] = SourceSwitches(False, False, True, False, False)
_COMPLETION: Final[SourceSwitches] = SourceSwitches(True, False, True, False, False)


class NyaaSource:
    def __init__(self, http: httpx.Client) -> None:
        self.http: httpx.Client = http

    def search(self, query: str, *, categories: Sequence[str] = SEARCH_CATEGORIES) -> tuple[Release, ...]:
        return search_releases(query, http=self.http, categories=categories)


def search_service(http: httpx.Client, control: RequestControl) -> EpisodeSearch:
    return EpisodeSearch(
        torrentio=TorrentioSource(http),
        nyaa=NyaaSource(http),
        knaben=KnabenSource(http),
        nekobt=NekoBTSource(http),
        tsukihime=TsukiHimeSource(http),
        request_control=control,
        pack_name=lambda name: parse_release_name(name).is_pack,
    )


def controlled(respond: Callable[[httpx.Request], httpx.Response]) -> RequestControl:
    now: list[float] = [1000.0]
    return RequestControl(
        httpx.MockTransport(respond), clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay)
    )


def feed(hashes: Sequence[str] = (_HASH,)) -> httpx.Response:
    items: str = "".join(
        f"<item><title>Star Garden - 05 [1080p]</title><link>https://nyaa.si/download/1.torrent</link>"
        f"<nyaa:infoHash>{info_hash}</nyaa:infoHash><nyaa:seeders>12</nyaa:seeders>"
        "<nyaa:size>1 GiB</nyaa:size></item>"
        for info_hash in hashes
    )
    return httpx.Response(
        200,
        text=f'<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa"><channel>{items}</channel></rss>',
        headers={"content-type": "application/xml"},
    )


def empty_response(request: httpx.Request) -> httpx.Response:
    if request.url.host == "nyaa.si":
        return feed()
    if request.url.host == "torrentio.strem.fun":
        return httpx.Response(200, json={"streams": []})
    if request.url.host == "api.knaben.org":
        return httpx.Response(200, json={"hits": [], "total": {"value": 0}})
    if request.url.host == "nekobt.to":
        return httpx.Response(200, text="<rss><channel/></rss>", headers={"content-type": "application/xml"})
    if "/anilist/" in request.url.path:
        return httpx.Response(404)
    return httpx.Response(404)


def test_nyaa_queries_both_categories() -> None:
    seen: list[tuple[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.params["q"], request.url.params["c"]))
        return feed()

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = search_service(http, control).manual_offer(_REQUEST, _NYAA)
    assert seen == [("Star Garden - 05", category) for category in SEARCH_CATEGORIES]
    assert len(outcome.snapshot.candidates) == 1
    assert next(row for row in outcome.snapshot.sources if row.source == "nyaa").state is SourceState.DONE


def test_release_stream_fields() -> None:
    control: RequestControl = controlled(empty_response)
    with httpx.Client(transport=control) as http:
        result: SearchOutcome = search_service(http, control).manual_offer(_REQUEST, _NYAA)
    stream: StreamCandidate = next(row for row in result.snapshot.sources if row.source == "nyaa").streams[0]
    assert (stream.info_hash, stream.release, stream.seeders, stream.size_text, stream.subtitle_languages) == (
        _HASH,
        "Star Garden - 05 [1080p]",
        12,
        "1 GiB",
        ("en",),
    )
    assert stream.file_name is None
    assert stream.path is None
    assert stream.source == "nyaa"
    assert result.snapshot.candidates[0].traits.english_subtitles


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("PL sub", PolishClass.POLISH),
        ("Napisy PL", PolishClass.POLISH),
        ("PL", PolishClass.BARE),
        ("Polish subs", PolishClass.POLISH),
    ],
)
def test_nyaa_english_category_preserves_polish_name_evidence(token: str, expected: PolishClass) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.params["c"] != "1_2":
            return feed(())
        response: httpx.Response = feed()
        return httpx.Response(
            200,
            text=response.text.replace("[1080p]", f"[1080p] [{token}]"),
            headers={"content-type": "application/xml"},
        )

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        result: SearchOutcome = search_service(http, control).manual_offer(_REQUEST, _NYAA)
    candidate: RankedCandidate = result.snapshot.candidates[0]
    assert candidate.traits.polish is expected
    assert candidate.traits.english_subtitles


@pytest.mark.parametrize("scenario", ["timeout", "second_timeout", "429", "cooldown", "403", "empty"])
def test_source_outcome_end_to_end(scenario: str) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if scenario == "timeout" or (scenario == "second_timeout" and request.url.params.get("c") == "1_3"):
            raise httpx.ReadTimeout("blocked", request=request)
        if scenario in {"429", "403"}:
            return httpx.Response(int(scenario))
        return feed(()) if scenario == "empty" else feed()

    control: RequestControl = controlled(respond)
    if scenario == "cooldown":
        control.restore({"nyaa": 2000}, lambda provider, until: None)
    switches: SourceSwitches = SourceSwitches(False, True, False, False, False) if scenario == "timeout" else _NYAA
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = search_service(http, control).manual_offer(_REQUEST, switches)
    result: SourceResult = next(row for row in outcome.snapshot.sources if row.state is not SourceState.DISABLED)
    expected: dict[str, tuple[SourceState, FailureKind | None, int]] = {
        "timeout": (SourceState.FAILED, FailureKind.TIMEOUT, 0),
        "second_timeout": (SourceState.UNFINISHED, FailureKind.TIMEOUT, 1),
        "429": (SourceState.FAILED, FailureKind.RATE_LIMITED, 0),
        "cooldown": (SourceState.FAILED, FailureKind.RATE_LIMITED, 0),
        "403": (SourceState.FAILED, FailureKind.ERROR, 0),
        "empty": (SourceState.DONE, None, 0),
    }
    assert (result.state, result.failure, len(result.streams)) == expected[scenario]
    if scenario == "cooldown":
        assert not seen


@pytest.mark.parametrize(
    ("status", "count", "expected"),
    [
        (202, 0, ReadOutcome.PENDING),
        (200, 0, ReadOutcome.EMPTY),
        (200, 2, ReadOutcome.EMPTY),
        (200, 1, ReadOutcome.LISTED),
        (404, 0, ReadOutcome.NO_HASH),
        (429, 0, ReadOutcome.RATE_LIMITED),
        (0, 0, ReadOutcome.TIMEOUT),
        (500, 0, ReadOutcome.FAILED),
    ],
)
def test_listing_outcome_end_to_end(status: int, count: int, expected: ReadOutcome) -> None:
    visits: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if "/torrents/" not in request.url.path:
            return empty_response(request)
        visits.append(request.url.path)
        if "/btih/" in request.url.path and status not in {404, 429}:
            return httpx.Response(200, json={"id": 42, "filecount": 2, "files": []})
        if not status:
            raise httpx.ReadTimeout("blocked", request=request)
        files: list[dict[str, object]] = [{"filename": "Star Garden - 05.mkv", "size": 12}] if count else []
        return httpx.Response(status, json={"id": 42, "filecount": count, "files": files})

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = search_service(http, control)
        outcome: SearchOutcome = service.manual_offer(_REQUEST, _COMPLETION)
        assert outcome.outcomes == {_HASH: expected}
        assert len(visits) == (1 if status in {404, 429} else 2)
        visits.clear()
        if status != 429:
            service.manual_offer(_REQUEST, _COMPLETION)
            assert bool(visits) is (expected is not ReadOutcome.LISTED)


def test_source_timeout_keeps_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    now: list[float] = [10.0]
    seen: list[httpx.Request] = []
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        now[0] = 41.0
        return feed()

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = search_service(http, control).manual_offer(_REQUEST, _NYAA)
    row: SourceResult = next(row for row in outcome.snapshot.sources if row.source == "nyaa")
    assert (row.state, row.failure, len(row.streams)) == (SourceState.UNFINISHED, FailureKind.TIMEOUT, 1)
    assert len(seen) == 1


def test_manual_offer_snapshot_at_3s_without_results() -> None:
    entered: threading.Barrier = threading.Barrier(6)
    release: threading.Event = threading.Event()
    now: list[float] = [0.0]
    snapshots: list[SearchSnapshot] = []
    seen: set[str] = set()
    lock: threading.Lock = threading.Lock()

    def respond(request: httpx.Request) -> httpx.Response:
        with lock:
            first: bool = request.url.host not in seen
            seen.add(request.url.host)
        if first:
            entered.wait(10)
        assert release.wait(10)
        return empty_response(request)

    def waiting(futures: Sequence[Future[SourceResult]], timeout: float | None) -> set[Future[SourceResult]]:
        if not snapshots:
            entered.wait(10)
            assert timeout == FIRST_SNAPSHOT_S
            now[0] = FIRST_SNAPSHOT_S
            return set()
        return wait(futures, timeout=10, return_when=FIRST_COMPLETED)[0]

    def partial(snapshot: SearchSnapshot) -> None:
        snapshots.append(snapshot)
        release.set()

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = EpisodeSearch(
            torrentio=TorrentioSource(http),
            nyaa=NyaaSource(http),
            knaben=KnabenSource(http),
            nekobt=NekoBTSource(http),
            tsukihime=TsukiHimeSource(http),
            request_control=control,
            pack_name=lambda _: False,
            clock=lambda: now[0],
            wait_sources=waiting,
        )
        service.manual_offer(_REQUEST, SourceSwitches(), partial)
    assert snapshots[0].candidates == ()
    assert snapshots[0].pending == NAME_PRIORITY


@pytest.mark.parametrize("movie", [False, True])
def test_torrentio_answer_movie_and_series(*, movie: bool) -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        search_service(http, control).manual_offer(
            replace(_REQUEST, movie=movie), SourceSwitches(False, True, False, False, False)
        )
    assert seen == (["/stream/movie/kitsu:1.json"] if movie else ["/stream/series/kitsu:1:5.json"])


@pytest.mark.parametrize(
    ("media_format", "index", "expected"),
    [
        ("TV", 1, ("Star Garden - 05", "Star Garden S01E05")),
        ("TV", 2, ("Star Garden - 05", "Star Garden S02E05")),
        ("ONA", 1, ("Star Garden - 05",)),
        ("OVA", 2, ("Star Garden: Moonlight - 05",)),
        ("SPECIAL", 2, ("Star Garden: Moonlight - 05",)),
        ("MOVIE", 1, ("Star Garden",)),
    ],
)
def test_episode_phrases_formats(media_format: str, index: int, expected: tuple[str, ...]) -> None:
    candidate: TitleCandidate = TitleCandidate(
        1, "Star Garden: Moonlight", None, None, (), None, None, media_format, 12, TitleStatus.FINISHED, ()
    )
    assert episode_phrases(candidate, SeasonContext(index, 12, 12), 5, manual=False, absolute=17) == expected


def test_episode_phrases_manual_absolute_and_subscription_limit() -> None:
    candidate: TitleCandidate = TitleCandidate(
        1, "Star Garden", "Hoshi no Niwa", None, (), None, None, "TV", 12, TitleStatus.FINISHED, ()
    )
    local: tuple[str, ...] = episode_phrases(candidate, SeasonContext(2, 12, 12), 5, manual=False, absolute=17)
    manual: tuple[str, ...] = episode_phrases(candidate, SeasonContext(2, 12, 12), 5, manual=True, absolute=17)
    assert len(local) == 4
    assert len(set(local)) == 4
    assert manual == (*local, "Star Garden - 17", "Hoshi no Niwa - 17")


@pytest.mark.parametrize(("title", "index"), [("Star Garden 2nd Season", 2), ("Star Garden Part 2", 1)])
def test_season_index_from_graph_no_anilist_requests(title: str, index: int) -> None:
    graph: FranchiseGraph = FranchiseGraph(
        2,
        {
            1: {"id": 1, "title": {"romaji": "Star Garden"}, "format": "TV", "episodes": 12},
            2: {
                "id": 2,
                "title": {"romaji": title},
                "format": "TV",
                "episodes": 10,
                "relations": {"edges": [{"relationType": "PREQUEL", "node": {"id": 1, "format": "TV"}}]},
            },
        },
        frozenset({1, 2}),
        True,
    )
    candidate: TitleCandidate = graph_candidate(graph, 2)
    assert graph_season_context(graph, candidate) == SeasonContext(index, 12, 10)


def test_episode_phrases_do_not_repeat_identical_titles() -> None:
    candidate: TitleCandidate = TitleCandidate(
        1, "Star Garden", "Star Garden", None, (), None, None, "TV", 12, TitleStatus.FINISHED, ()
    )
    assert episode_phrases(candidate, SeasonContext(1, 0, 12), 5, manual=True, absolute=5) == (
        "Star Garden - 05",
        "Star Garden S01E05",
    )


def test_manual_offer_partial_after_first_source() -> None:
    release: threading.Event = threading.Event()
    snapshots: list[SearchSnapshot] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.knaben.org":
            assert release.wait(10)
        return empty_response(request)

    def partial(snapshot: SearchSnapshot) -> None:
        snapshots.append(snapshot)
        if snapshot.candidates:
            release.set()

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = search_service(http, control).manual_offer(
            _REQUEST,
            SourceSwitches(False, False, True, True, False),
            partial,
        )
    assert snapshots[0].candidates
    assert snapshots[0].pending == ("knaben",)
    assert not outcome.snapshot.pending


def test_disabled_tsukihime_no_listing_no_history() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        search_service(http, control).manual_offer(_REQUEST, _NYAA)
    assert set(seen) == {"nyaa.si"}


def test_completion_queue_budget_retry_and_inline_inventory() -> None:
    hashes: tuple[str, ...] = tuple(f"{number:040x}" for number in range(15))
    visits: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nyaa.si":
            return feed(hashes)
        if "/btih/" in request.url.path:
            visits.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(202, json={"id": 42})
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = search_service(http, control)
        service.manual_offer(_REQUEST, _COMPLETION)
        first: tuple[str, ...] = tuple(visits)
        assert len(first) == len(set(first)) == 10
        visits.clear()
        service.manual_offer(_REQUEST, _COMPLETION)
        assert len(visits) == len(set(visits)) == 10
        assert set(visits[:5]) == set(hashes) - set(first)
        visits.clear()
        service.manual_offer(_REQUEST, _COMPLETION)
        visits.clear()
        service.manual_offer(_REQUEST, _COMPLETION)
        third: set[str] = set(visits)
        visits.clear()
        service.manual_offer(_REQUEST, _COMPLETION)
    assert set(hashes) == third | set(visits)


def test_unresolved_season_stays_in_completion_queue() -> None:
    visits: list[str] = []
    snapshots: list[SearchSnapshot] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if "/btih/" in request.url.path:
            visits.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "filecount": 1,
                    "files": [{"filename": "Star Garden 2nd Season - 05 [1080p].mkv", "size": 12}],
                },
            )
        return empty_response(request)

    request: EpisodeRequest = replace(
        _REQUEST,
        target=_target(
            aliases=["Star Garden 2nd Season"],
            season=2,
            absolute=17,
            other_series=[{"aliases": ["Star Garden"], "type": "TV", "relation": "PREQUEL"}],
        ),
    )
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        result: SearchOutcome = search_service(http, control).manual_offer(request, _COMPLETION, snapshots.append)
    before: RankedCandidate = next(snapshot.candidates[0] for snapshot in snapshots if snapshot.candidates)
    assert before.identity.verdict is IdentityVerdict.INSUFFICIENT
    assert not before.conflict
    assert visits == [_HASH]
    assert result.outcomes == {_HASH: ReadOutcome.LISTED}
    assert result.snapshot.candidates[0].identity.verdict is IdentityVerdict.MATCH


def test_offer_status_all_failed() -> None:
    assert offer_status((SourceResult("nyaa", SourceState.FAILED),)) == "Brak wyników — źródła niedostępne"
    assert offer_status((SourceResult("nyaa", SourceState.DONE),)) is None


def test_offer_status_all_disabled() -> None:
    assert (
        offer_status(tuple(SourceResult(source, SourceState.DISABLED) for source in NAME_PRIORITY))
        == "Wszystkie źródła wyłączone (Ustawienia)"
    )


@pytest.mark.parametrize(
    ("failure", "detail", "expected"),
    [
        (FailureKind.TIMEOUT, None, "limit czasu"),
        (FailureKind.RATE_LIMITED, None, "limit dostawcy"),
        (FailureKind.ERROR, "403", "403"),
    ],
)
def test_source_line_failure(failure: FailureKind, detail: str | None, expected: str) -> None:
    assert (
        source_line(SourceResult("nyaa", SourceState.FAILED, failure=failure, detail=detail))
        == f"Nyaa: niedostępne ({expected})"
    )
