from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import httpx
import pytest
from test_acquisition import _S4, _episode_service
from test_automation import _real_service, _request
from test_episode_admission import _choice
from test_episode_commands import _batch, _choose, _offer, _running, _stream, _Streams
from test_selective_lifecycle import _until
from test_subscription_owner import _UNNUMBERED, _active, _checked, _followed, _following, _renumbered, _World

from anishift.application import acquisition_decisions
from anishift.application.acquisition import AcquisitionService
from anishift.application.automation import AutomationOwner
from anishift.application.control import (
    AcquisitionConfirmation,
    AcquisitionState,
    AdmissionSource,
    EpisodeAssignment,
    EpisodeChoice,
    compact_acquisition,
)
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_commands import EpisodeOfferView
from anishift.application.episode_selection import (
    RankedCandidate,
    StreamCandidate,
    rank_candidates,
    streams_releases,
    suggestion,
)
from anishift.application.intents import RequestOrigin
from anishift.application.service import AppService
from anishift.application.subscription_targets import SubscriptionRecord
from anishift.application.watch_state import WatchStateStore
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.torrentio import TorrentioSource


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.unit
def test_owner_records_live_checks_cache_hits_selection_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    streams: _Streams = _Streams()
    second_file: StreamCandidate = replace(_stream(4, "a"), file_index=5)
    streams.answers = {(41024, 4): (_stream(4, "a", uncertain=True), second_file, _stream(4, "b"))}
    writers: list[str] = []
    append: Callable[..., None] = acquisition_decisions.append_decision

    def recorded(path: Path, kind: str, payload: Mapping[str, object], *, entry: str = "manual") -> None:
        writers.append(threading.current_thread().name)
        append(path, kind, payload, entry=entry)

    monkeypatch.setattr("anishift.application.automation.append_decision", recorded)
    path: Path = tmp_path / "decisions.jsonl"
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        _offer(owner)
        view: EpisodeOfferView = _offer(owner)
        assert _choose(owner, view).ok
        assert _choose(owner, view).ok
    records: list[dict[str, object]] = _records(path)
    assert [row.get("source") for row in records if row["kind"] == "check"] == ["ani.zip", "torrentio", "torrentio"]
    assert len([row for row in records if row["kind"] == "selection"]) == 1
    assert set(writers) == {"anishift-owner"}
    check: dict[str, object] = next(row for row in records if row.get("source") == "torrentio")
    candidates: list[dict[str, object]] = cast("list[dict[str, object]]", check["candidates"])
    restored: tuple[StreamCandidate, ...] = tuple(
        decode_view(StreamCandidate, {**row, "trackers": []})
        for row in cast("list[dict[str, object]]", check["streams"])
    )
    ranked: tuple[RankedCandidate, ...] = rank_candidates(
        cast("dict[str, object]", check["target"]),
        streams_releases(restored, pack_name=lambda name: parse_release_name(name).is_pack),
        donghua=check["donghua"] is True,
    )
    assert len(restored) == 3
    assert ranked[0].files == ("mystery.mkv", second_file.file_name)
    assert [encode_view(item.identity) for item in ranked] == [row["identity"] for row in candidates]
    assert [encode_view(item.traits) for item in ranked] == [row["traits"] for row in candidates]
    assert [(item.quality, item.confidence, item.conflict, item.supported) for item in ranked] == [
        (row["quality"], row["confidence"], row["conflict"], row["supported"]) for row in candidates
    ]
    assert [item.stream for item in ranked] == [
        decode_view(StreamCandidate, {**cast("dict[str, object]", row["stream"]), "trackers": []}) for row in candidates
    ]
    assert suggestion(ranked, numbering=True)[0] == check["suggestion"]


@pytest.mark.unit
def test_source_429_is_recorded_without_private_http_context(tmp_path: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, headers={"Secret": "hidden"}, text="private-body")

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        service: AcquisitionService = _episode_service(tmp_path)
        service._stream_source = TorrentioSource(http)
        with _running(service, WatchStateStore(tmp_path / "state.json")) as owner:
            _batch(owner, (4,))
            _until(lambda: _batch(owner, (4,)).state == "completed")
    records: list[dict[str, object]] = _records(tmp_path / "decisions.jsonl")
    failed: dict[str, object] = records[-1]
    assert failed["source"] == "torrentio"
    assert failed["http_status"] == 429
    assert failed["error"] == "TORRENT_SOURCE_FAILED"
    assert "hidden" not in json.dumps(records)
    assert "private-body" not in json.dumps(records)


@pytest.mark.unit
def test_decision_projection_excludes_unlisted_metadata() -> None:
    target: dict[str, object] = {"aliases": ["Show"], "headers": {"Authorization": "secret"}, "media": b"secret"}
    assert acquisition_decisions.target_view(target) == {"aliases": ["Show"]}
    stream: StreamCandidate = replace(_stream(4), trackers=("https://secret/?signature=hidden",))
    assert "trackers" not in acquisition_decisions.stream_view(stream)


@pytest.mark.unit
@pytest.mark.parametrize("field", ["path", "file_name"])
@pytest.mark.parametrize(
    "value",
    [r"C:\private\video.mkv", r"\\server\share\video.mkv", "/private/video.mkv", "https://host/?signature=hidden"],
)
def test_append_refuses_absolute_paths_and_urls_in_path_fields(tmp_path: Path, field: str, value: str) -> None:
    path: Path = tmp_path / "decisions.jsonl"
    stream: dict[str, object] = {**acquisition_decisions.stream_view(_stream(4)), field: value}
    acquisition_decisions.append_decision(path, "check", {"stream": stream})
    assert not path.exists()


@pytest.mark.unit
def test_owner_records_release_with_slash_between_titles(tmp_path: Path) -> None:
    title: str = "[LoliHouse] 葬送的芙莉莲 / Sousou no Frieren - 01"
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (replace(_stream(4), release=title, file_name=f"{title}.mkv", path=f"{title}.mkv"),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        _offer(owner)
    check: dict[str, object] = next(
        row for row in _records(tmp_path / "decisions.jsonl") if row.get("source") == "torrentio"
    )
    candidates: list[dict[str, object]] = cast("list[dict[str, object]]", check["candidates"])
    assert cast("dict[str, object]", candidates[0]["stream"])["release"] == title


@pytest.mark.unit
@pytest.mark.parametrize("field", ["release", "name", "episode_title"])
def test_append_checks_urls_but_not_absolute_paths_in_title_fields(tmp_path: Path, field: str) -> None:
    path: Path = tmp_path / "decisions.jsonl"
    acquisition_decisions.append_decision(path, "check", {field: "https://host/?signature=hidden"})
    assert not path.exists()
    acquisition_decisions.append_decision(path, "check", {field: "/Title"})
    assert _records(path)[0][field] == "/Title"


@pytest.mark.unit
@pytest.mark.parametrize("broken", ["directory", "corrupt"])
def test_bad_journal_does_not_repeat_admission_after_restart(tmp_path: Path, broken: str) -> None:
    path: Path = tmp_path / "decisions.jsonl"
    if broken == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"broken\n")
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        view: EpisodeOfferView = _offer(owner)
        assert _choose(owner, view).ok
        assert _choose(owner, view).ok
        assert len(owner.state.acquisitions) == 1
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        assert _choose(owner, view).ok
        new_view: EpisodeOfferView = _offer(owner)
        assert _choose(owner, new_view, command="new-duplicate").reason == "episode_admitted"
        assert len(owner.state.acquisitions) == 1


@pytest.mark.unit
def test_repeat_records_correction_only_after_durable_admission(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        original: EpisodeOfferView = _offer(owner)
        assert _choose(owner, original).ok
        streams.answers = {(41024, 4): (_stream(4, "b"),)}
        repeated: EpisodeOfferView = _offer(owner, repeat=True)
        assert _choose(owner, repeated, command="repeat").ok
        assert _choose(owner, repeated, command="repeat").ok
    corrections: list[dict[str, object]] = [
        row for row in _records(tmp_path / "decisions.jsonl") if row["kind"] == "correction"
    ]
    assert len(corrections) == 1
    assert corrections[0]["previous_admission_id"] == repeated.previous_admission_id
    assert corrections[0]["reason"] == "replacement"


@pytest.mark.unit
def test_repeat_recognizes_a_compacted_previous_video_after_restart(tmp_path: Path) -> None:
    streams: _Streams = _Streams()
    streams.answers = {(41024, 4): (_stream(4),)}
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    with _running(_episode_service(tmp_path, streams=streams), store) as owner:
        assert _choose(owner, _offer(owner)).ok
        original: AcquisitionConfirmation = owner.state.acquisitions[0]
    video: str = "Pack/episode-04.mkv"
    completed: AcquisitionConfirmation = compact_acquisition(
        replace(
            original,
            state=AcquisitionState.COMPLETE,
            cleaned=True,
            assignments=(replace(original.assignments[0], file_map="map", files=((0, video, 100),), video_path=video),),
        )
    )
    assert not completed.assignments[0].files
    store.save(replace(store.load(), acquisitions=(completed,)))
    streams.answers = {(41024, 4): (_stream(4, "b"),)}
    with _running(_episode_service(tmp_path, streams=streams), WatchStateStore(tmp_path / "state.json")) as owner:
        repeated: EpisodeOfferView = _offer(owner, repeat=True)
        assert repeated.previous_admission_id == original.assignments[0].admission_id
        assert not repeated.unknown_previous
        assert len(repeated.offer.candidates) == 1


@pytest.mark.unit
def test_append_refuses_forbidden_fields_at_any_depth(tmp_path: Path) -> None:
    path: Path = tmp_path / "decisions.jsonl"
    for payload in ({"headers": {"token": "secret"}}, {"target": {"aliases": [{"password": "secret"}]}}):
        acquisition_decisions.append_decision(path, "check", payload)
    assert not path.exists()


@pytest.mark.unit
def test_ten_thousand_completed_admissions_do_not_expand_status(tmp_path: Path) -> None:
    store: WatchStateStore = WatchStateStore(tmp_path / "state.json")
    service: AppService = _real_service(tmp_path)
    owner: AutomationOwner = AutomationOwner(service, store, instance_id="large-ledger")
    choice: EpisodeChoice = _choice(1)
    completed: AcquisitionConfirmation = compact_acquisition(
        AcquisitionConfirmation(
            "finished",
            choice.reference.info_hash,
            "",
            (),
            AcquisitionState.COMPLETE,
            RequestOrigin.USER,
            None,
            "1",
            "2026-09-30T00:00:00+00:00",
            assignments=(EpisodeAssignment("admission", "2026-09-30T00:00:00+00:00", AdmissionSource.MANUAL, choice),),
            cleaned=True,
        )
    )
    try:
        small: dict[str, object] = owner._status()
        owner._state = replace(
            owner.state,
            acquisitions=tuple(replace(completed, operation_id=f"finished-{index}") for index in range(10_000)),
        )
        large: dict[str, object] = owner._status()
        small.pop("updated_at")
        large.pop("updated_at")
        assert large == small
        assert owner._perform(_request("acquisition_states", {"hashes": [choice.reference.info_hash]})).ok
    finally:
        owner._pool.shutdown(wait=True)
        service.close()


def _target_check(tmp_path: Path, world: _World, record: SubscriptionRecord | None = None) -> dict[str, object]:
    with _following(tmp_path, _active(record or _followed()), world) as (owner, store):
        _checked(owner, store)
    return next(
        row
        for row in _records(tmp_path / "decisions.jsonl")
        if row["kind"] == "check" and row.get("key") == {"anilist_id": _S4, "number": 23}
    )


@pytest.mark.unit
@pytest.mark.parametrize(("wait_h", "blocker"), [(0, "none"), (2, "waiting_polish")])
def test_selection_fields_a1(tmp_path: Path, wait_h: int, blocker: str) -> None:
    check: dict[str, object] = _target_check(tmp_path, _World(polish_wait_h=wait_h))

    assert check["sources"] == [{"source": "torrentio", "result": "done"}]
    assert check["blocker"] == blocker


@pytest.mark.unit
def test_selection_candidates_quality_confidence(tmp_path: Path) -> None:
    check: dict[str, object] = _target_check(tmp_path, _World())
    candidates: list[dict[str, object]] = cast("list[dict[str, object]]", check["candidates"])
    record: SubscriptionRecord = _checked_record(tmp_path)

    assert record.last_check is not None
    assert len(candidates) == record.last_check.matching + record.last_check.uncertain + record.last_check.mismatched
    assert {frozenset(row) for row in candidates} == {
        frozenset({"info_hash", "verdict", "quality", "confidence", "conflict", "pack", "after_metadata"})
    }
    assert all(isinstance(row["quality"], float) for row in candidates)
    assert all(row["confidence"] is None or isinstance(row["confidence"], float) for row in candidates)
    assert "match" in {row["verdict"] for row in candidates}


def _checked_record(tmp_path: Path) -> SubscriptionRecord:
    return WatchStateStore(tmp_path / "state.json").load().subscriptions[0]


@pytest.mark.unit
@pytest.mark.parametrize(("unnumbered", "numbering"), [(False, "anilist"), (True, "none")])
def test_numbering_field(tmp_path: Path, *, unnumbered: bool, numbering: str) -> None:
    record: SubscriptionRecord = _followed(mapping=_renumbered(_UNNUMBERED)) if unnumbered else _followed()
    world: _World = _World()
    if unnumbered:
        world.episodes.mappings[_S4] = replace(_renumbered(_UNNUMBERED), max_age_s=0)

    assert _target_check(tmp_path, world, record)["numbering"] == numbering
