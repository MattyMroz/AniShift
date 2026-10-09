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
from anishift.application.subscription_choice import ReadOutcome
from anishift.application.subscription_targets import PolishState, ReleaseFailure
from anishift.services.catalog.types import TitleCandidate, TitleStatus
from anishift.services.http_requests import DeadlineExceeded, RequestControl
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
        service: EpisodeSearch = search_service(http, control)
        service.manual_offer(_REQUEST, _NYAA)
        history: PolishState | None = service.previous_history(_REQUEST, _NYAA, settled=True)
    assert set(seen) == {"nyaa.si"}
    assert history is PolishState.UNKNOWN


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


_TSUKIHIME_ONLY: Final[SourceSwitches] = SourceSwitches(True, False, False, False, False)
_KNABEN_ONLY: Final[SourceSwitches] = SourceSwitches(False, False, False, True, False)


def clocked(http: httpx.Client, control: RequestControl, now: list[float]) -> EpisodeSearch:
    return EpisodeSearch(
        torrentio=TorrentioSource(http),
        nyaa=NyaaSource(http),
        knaben=KnabenSource(http),
        nekobt=NekoBTSource(http),
        tsukihime=TsukiHimeSource(http),
        request_control=control,
        pack_name=lambda name: parse_release_name(name).is_pack,
        clock=lambda: now[0],
    )


def checked(service: EpisodeSearch, switches: SourceSwitches, *failures: ReleaseFailure) -> SearchOutcome:
    return service.subscription_check(_REQUEST, switches, failures, frozenset())


def source_row(outcome: SearchOutcome, source: str) -> SourceResult:
    return next(row for row in outcome.snapshot.sources if row.source == source)


def knaben_hit(info_hash: str = _HASH) -> httpx.Response:
    return httpx.Response(
        200,
        json={"hits": [{"hash": info_hash, "title": "Star Garden - 05 [1080p]", "seeders": 3}], "total": {"value": 1}},
    )


def tsukihime_rows(start: int, count: int) -> list[dict[str, object]]:
    return [
        {"id": number + 1, "btih": f"{number:040x}", "name": "Star Garden - 05 [1080p]", "filecount": 1}
        for number in range(start, start + count)
    ]


def test_subscription_check_tsukihime_budget_14() -> None:
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        if "/episodes/" in request.url.path:
            start: int = int(request.url.params["offset"])
            return httpx.Response(
                200, json={"results": tsukihime_rows(start, 20), "total": 60, "start": start, "limit": 20}
            )
        return httpx.Response(202, json={"id": 5})

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, [0.0])
        first: SearchOutcome = checked(service, _TSUKIHIME_ONLY)
        first_count: int = len(paths)
        paths.clear()
        checked(service, _TSUKIHIME_ONLY)

    assert first_count <= 14
    assert first_count == 1 + 2 + 10
    assert sum("/episodes/" in path for path in paths) == 2
    assert not any(path.endswith("/animes/anilist/1") for path in paths)
    assert first.tsukihime_id == 77
    assert source_row(first, "tsukihime").state is SourceState.UNFINISHED


def _history(total: int, languages: Sequence[Sequence[str]], *, settled: bool = True) -> PolishState | None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        start: int = int(request.url.params["offset"])
        rows: list[dict[str, object]] = [
            {**row, "sublangs": list(languages[(start + index) % len(languages)])}
            for index, row in enumerate(tsukihime_rows(start, min(20, total - start)))
        ]
        return httpx.Response(200, json={"results": rows, "total": total, "start": start, "limit": 20})

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        return clocked(http, control, [0.0]).previous_history(_REQUEST, _TSUKIHIME_ONLY, settled=settled)


def test_previous_history_truncated_with_polish_is_present() -> None:
    assert _history(60, [["en"], ["pl", "en"]]) is PolishState.PRESENT


def test_previous_history_truncated_without_polish_keeps_the_last_observation() -> None:
    assert _history(60, [["en"]]) is None


@pytest.mark.parametrize(
    ("languages", "settled", "expected"),
    [
        ([["en"]], True, PolishState.ABSENT),
        ([["en"]], False, PolishState.UNKNOWN),
        ([[]], True, PolishState.UNKNOWN),
    ],
    ids=["absent", "too-early", "no-sublangs"],
)
def test_previous_history_of_a_complete_list(
    languages: list[list[str]], *, settled: bool, expected: PolishState
) -> None:
    assert _history(5, languages, settled=settled) is expected


@pytest.mark.parametrize(
    ("name", "files", "expected"),
    [
        ("Star Garden - 05 [1080p]", [("Star Garden - 05 [1080p].mkv", ["en"])], PolishState.ABSENT),
        (
            "Star Garden (01-12) [1080p]",
            [("Star Garden - 05 [1080p].mkv", ["en"]), ("Star Garden - 06 [1080p].mkv", ["pl"])],
            PolishState.ABSENT,
        ),
        (
            "Star Garden (01-12) [1080p]",
            [("Star Garden - 05 [1080p].mkv", ["pl"]), ("Star Garden - 06 [1080p].mkv", ["en"])],
            PolishState.PRESENT,
        ),
    ],
    ids=["file-languages", "pack-without-polish", "pack-with-polish"],
)
def test_previous_history_reads_the_subtitles_listed_for_the_episode_file(
    name: str, files: list[tuple[str, list[str]]], expected: PolishState
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        if "/episodes/" in request.url.path:
            row: dict[str, object] = {"id": 9, "btih": _HASH, "name": name, "filecount": len(files), "sublangs": []}
            return httpx.Response(200, json={"results": [row], "total": 1, "start": 0, "limit": 100})
        listed: list[dict[str, object]] = [
            {"filename": filename, "size": 12, "sublangs": languages} for filename, languages in files
        ]
        return httpx.Response(200, json={"id": 9, "filecount": len(files), "files": listed})

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, [0.0])
        before: PolishState | None = service.previous_history(_REQUEST, _TSUKIHIME_ONLY, settled=True)
        service.manual_offer(_REQUEST, _TSUKIHIME_ONLY)
        history: PolishState | None = service.previous_history(_REQUEST, _TSUKIHIME_ONLY, settled=True)

    assert before is PolishState.UNKNOWN
    assert history is expected


def test_previous_history_reads_only_the_pages_left_in_the_budget() -> None:
    pages: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        pages.append(request.url.params["offset"])
        start: int = int(request.url.params["offset"])
        rows: list[dict[str, object]] = [{**row, "sublangs": ["en"]} for row in tsukihime_rows(start, 20)]
        return httpx.Response(200, json={"results": rows, "total": 40, "start": start, "limit": 20})

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        history: PolishState | None = clocked(http, control, [0.0]).previous_history(
            _REQUEST, _TSUKIHIME_ONLY, settled=True, pages=1
        )

    assert pages == ["0"]
    assert history is None


def test_previous_history_without_a_tsukihime_title_is_unknown() -> None:
    control: RequestControl = controlled(lambda request: httpx.Response(404))
    with httpx.Client(transport=control) as http:
        history: PolishState | None = clocked(http, control, [0.0]).previous_history(
            _REQUEST, _TSUKIHIME_ONLY, settled=True
        )
    assert history is PolishState.UNKNOWN


def test_previous_history_failed_list_keeps_the_last_observation() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        return httpx.Response(500)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        history: PolishState | None = clocked(http, control, [0.0]).previous_history(
            _REQUEST, _TSUKIHIME_ONLY, settled=True
        )
    assert history is None


def test_pulled_source_read_once_per_hour() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return knaben_hit()

    now: list[float] = [0.0]
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, now)
        checked(service, _KNABEN_ONLY)
        now[0] = 3599.0
        between: SearchOutcome = checked(service, _KNABEN_ONLY)
        reads: int = len(seen)
        now[0] = 3601.0
        checked(service, _KNABEN_ONLY)

    assert reads == 1
    assert len(seen) == 2
    assert (source_row(between, "knaben").state, len(source_row(between, "knaben").streams)) == (SourceState.DONE, 1)


def test_pulled_failure_keeps_last_result() -> None:
    failing: list[bool] = [False]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500) if failing[0] else knaben_hit()

    now: list[float] = [0.0]
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, now)
        checked(service, _KNABEN_ONLY)
        failing[0] = True
        now[0] = 3601.0
        kept: SearchOutcome = checked(service, _KNABEN_ONLY)

    row: SourceResult = source_row(kept, "knaben")
    assert (row.state, [item.info_hash for item in row.streams]) == (SourceState.UNFINISHED, [_HASH])
    assert kept.snapshot.candidates


def test_pulled_disable_and_restart_drop_memory() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return knaben_hit()

    now: list[float] = [0.0]
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, now)
        checked(service, _KNABEN_ONLY)
        checked(service, SourceSwitches(False, False, False, False, False))
        checked(service, _KNABEN_ONLY)
        disabled: int = len(seen)
        checked(clocked(http, control, now), _KNABEN_ONLY)

    assert disabled == 2
    assert len(seen) == 3


def test_pulled_without_success_is_unfinished() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(500)

    now: list[float] = [0.0]
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, now)
        failed: SearchOutcome = checked(service, _KNABEN_ONLY)
        reads: int = len(seen)
        now[0] = 60.0
        waiting: SearchOutcome = checked(service, _KNABEN_ONLY)

    assert source_row(failed, "knaben").state is SourceState.FAILED
    assert (source_row(waiting, "knaben").state, source_row(waiting, "knaben").streams) == (SourceState.UNFINISHED, ())
    assert len(seen) == reads


def test_skipped_fast_source_uses_last_result_30_min() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return feed()

    now: list[float] = [0.0]
    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, now)
        first: SearchOutcome = checked(service, _NYAA)
        reads: int = len(seen)
        control.restore({"nyaa": 1_000_000.0}, lambda provider, until: None)
        now[0] = 1800.0
        remembered: SearchOutcome = checked(service, _NYAA)
        now[0] = 1801.0
        expired: SearchOutcome = checked(service, _NYAA)

    assert len(seen) == reads
    assert source_row(remembered, "nyaa").state is SourceState.SKIPPED
    assert source_row(remembered, "nyaa").streams == source_row(first, "nyaa").streams
    assert remembered.snapshot.candidates
    assert (source_row(expired, "nyaa").state, source_row(expired, "nyaa").streams) == (SourceState.SKIPPED, ())


def test_skipped_source_not_counted_as_failure() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    control.restore({"tsukihime": 1_000_000.0}, lambda provider, until: None)
    failures: tuple[ReleaseFailure, ...] = (ReleaseFailure(_HASH, transient=1),)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = checked(clocked(http, control, [0.0]), _COMPLETION, *failures)

    assert source_row(outcome, "tsukihime").state is SourceState.SKIPPED
    assert "api.tsukihime.org" not in seen
    assert outcome.failures == failures
    assert outcome.outcomes == {}


def test_failed_tsukihime_counts_pending_release_once() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.tsukihime.org":
            return httpx.Response(500)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = checked(clocked(http, control, [0.0]), _COMPLETION)

    assert source_row(outcome, "tsukihime").state is SourceState.FAILED
    assert outcome.failures == (ReleaseFailure(_HASH, transient=1),)


def test_ended_release_waits_while_blocking_releases_remain() -> None:
    hashes: tuple[str, ...] = tuple(f"{number:040x}" for number in range(11))
    visited: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nyaa.si":
            return feed(hashes)
        if "/torrents/btih/" in request.url.path:
            visited.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(202, json={"id": 5})
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, [0.0])
        first: SearchOutcome = checked(service, _COMPLETION, ReleaseFailure(hashes[0], decisive=True))
        checked(service, _COMPLETION, *first.failures)

    assert len(visited) == 20
    assert hashes[0] not in visited


def test_tsukihime_deadline_counts_every_pending_release_each_check() -> None:
    hashes: tuple[str, ...] = tuple(f"{number:040x}" for number in range(15))

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.tsukihime.org":
            message: str = "Operation deadline exceeded"
            raise DeadlineExceeded(message, request=request)
        if request.url.host == "nyaa.si":
            return feed(hashes)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    failures: tuple[ReleaseFailure, ...] = ()
    with httpx.Client(transport=control) as http:
        service: EpisodeSearch = clocked(http, control, [0.0])
        for _ in range(3):
            outcome: SearchOutcome = checked(service, _COMPLETION, *failures)
            failures = outcome.failures

    assert source_row(outcome, "tsukihime").failure is FailureKind.TIMEOUT
    assert set(failures) == {ReleaseFailure(info_hash, transient=3) for info_hash in hashes}


def test_tsukihime_rate_limit_during_completion_counts_releases_beyond_budget() -> None:
    hashes: tuple[str, ...] = tuple(f"{number:040x}" for number in range(15))

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nyaa.si":
            return feed(hashes)
        if request.url.path.endswith("/animes/anilist/1"):
            return httpx.Response(200, json={"id": 77})
        if "/episodes/" in request.url.path:
            return httpx.Response(200, json={"results": [], "total": 0, "start": 0, "limit": 20})
        if "/torrents/btih/" in request.url.path:
            return httpx.Response(429)
        return empty_response(request)

    control: RequestControl = controlled(respond)
    with httpx.Client(transport=control) as http:
        outcome: SearchOutcome = checked(clocked(http, control, [0.0]), _COMPLETION)

    assert source_row(outcome, "tsukihime").state is SourceState.DONE
    assert ReadOutcome.RATE_LIMITED in outcome.outcomes.values()
    assert set(outcome.failures) == {ReleaseFailure(info_hash, transient=1) for info_hash in hashes}


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
