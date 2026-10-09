from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, cast

import httpx
import pytest
from loguru import logger as loguru_logger
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.cells import cell_len
from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    AutomationOwner,
    EntryGroup,
    EpisodeBatch,
    EpisodeFile,
    EpisodeFiles,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeOfferView,
    EpisodeRange,
    EpisodeReason,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    IdentityAssessment,
    IdentityVerdict,
    InspectedSourceGroup,
    ListedEpisode,
    ListedSpecial,
    PolishClass,
    RankedCandidate,
    ReleaseCatalog,
    ReleaseTraits,
    SeasonContext,
    StreamCandidate,
    TitleCandidate,
    TitleStatus,
    WorkspaceInspector,
)
from anishift.application.acquisition import catalog_releases
from anishift.application.cancellation import EventCancellationToken
from anishift.application.control import AcquisitionConfirmation
from anishift.application.control_views import decode_view, encode_view
from anishift.application.episode_commands import EpisodeResult
from anishift.application.episode_identity import REASONS
from anishift.application.episode_search import EpisodeSearch
from anishift.application.episode_selection import AniZipMapping, episode_listing, rank_candidates, streams_releases
from anishift.application.planning import ExecutionPlan
from anishift.application.release_quality import AudioClass
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.watch_state import WatchStateStore
from anishift.cli.interactive import anime as anime_module
from anishift.cli.interactive import anime_view
from anishift.cli.interactive.anime import _REASON_TEXTS, EPISODE_REASON_LABELS, AnimeController, _Screen
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode
from anishift.platform.local_control import (
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlServer,
    control_endpoint,
)
from anishift.services.catalog import AniListCatalog, AniZipCatalog
from anishift.services.http_requests import RequestControl
from anishift.services.media import DefaultMediaProbe
from anishift.services.torrents.knaben import KnabenSource
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.nekobt import NekoBTSource
from anishift.services.torrents.nyaa import search_releases
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.torrents.torrentio import TorrentioSource
from anishift.services.torrents.tsukihime import TsukiHimeSource
from anishift.services.torrents.types import Release


def _entry(identifier: int = 1, *, format: str = "TV") -> FranchiseEntry:
    return FranchiseEntry(identifier, "Slime", "Slime", None, format, "FINISHED", 2018, None, "SELF", EntryGroup.SEASON)


def _title() -> TitleCandidate:
    return TitleCandidate(1, "Slime", "Slime", None, (), 2018, None, "TV", 6, TitleStatus.FINISHED, ())


def _listing() -> EpisodeListing:
    return EpisodeListing(
        1,
        10,
        "TV",
        "FINISHED",
        6,
        tuple(ListedEpisode(n, f"Episode {n}", aired=True) for n in range(1, 7)),
        (ListedSpecial("S1", "Extra", None),),
        6,
        None,
        None,
    )


def _candidate(verdict: IdentityVerdict = IdentityVerdict.MATCH, resolution: int | None = 1080) -> RankedCandidate:
    return RankedCandidate(
        StreamCandidate("a" * 40, None, None, "Slime - 04.mkv", "[Group] Slime - 04", None, None, None, None, (), ()),
        IdentityAssessment(
            verdict,
            "Explicit mapped episode differs from target."
            if verdict is IdentityVerdict.MISMATCH
            else "No selected file.",
        ),
        ReleaseTraits(
            PolishClass.NONE,
            False,
            False,
            AudioClass.ORIGINAL,
            False,
            False,
            False,
            resolution,
            False,
            False,
            None,
            False,
        ),
        quality=0.0,
        confidence=None if verdict is IdentityVerdict.MISMATCH else 0.954,
        conflict=verdict is IdentityVerdict.MISMATCH,
        ambiguous=False,
        release_name_only=False,
        supported=True,
        files=("Slime - 04.mkv",),
    )


def _offer(key: EpisodeKey, candidates: tuple[RankedCandidate, ...] | None = None) -> EpisodeOffer:
    candidates = (_candidate(),) if candidates is None else candidates
    suggested: int | None = next(
        (i for i, item in enumerate(candidates) if item.identity.verdict is not IdentityVerdict.MISMATCH), None
    )
    return EpisodeOffer(
        key,
        candidates,
        suggested,
        datetime(2026, 9, 29, tzinfo=UTC),
        {verdict.value: sum(item.identity.verdict is verdict for item in candidates) for verdict in IdentityVerdict},
    )


class _Catalog:
    def __init__(self) -> None:
        self.view: Franchise = Franchise(1, (_entry(), _entry(2)), (), True)
        self.titles: tuple[TitleCandidate, ...] = (_title(),)
        self.listing: EpisodeListing = _listing()
        self.calls: list[tuple[str, int]] = []
        self.offer_read: Callable[[EpisodeKey], EpisodeOffer] = _offer
        self.franchise_read: Callable[[int], Franchise] = lambda identifier: self.view
        self.cancel: object = None

    def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
        self.calls.append(("titles", len(query)))
        return self.titles

    def franchise(self, identifier: int, *, cancel: object = None) -> Franchise:
        self.calls.append(("franchise", identifier))
        self.cancel = cancel
        return self.franchise_read(identifier)

    def season_context(self, candidate: TitleCandidate) -> SeasonContext | None:
        self.calls.append(("season", candidate.anilist_id))
        return None

    def search_title(self, candidate: TitleCandidate, **options: object) -> object:
        self.calls.append(("releases", candidate.anilist_id))
        raise OSError("offline")

    def episodes(self, identifier: int) -> EpisodeListing:
        self.calls.append(("episodes", identifier))
        return self.listing

    def offer(self, key: EpisodeKey) -> EpisodeOffer:
        self.calls.append(("offer", key.number))
        return self.offer_read(key)


def _controller(catalog: _Catalog) -> AnimeController:
    return AnimeController(cast("AppService", SimpleNamespace(acquisition=catalog)), lambda: None)


def _settle(controller: AnimeController) -> None:
    deadline: float = time.monotonic() + 10
    while time.monotonic() < deadline:
        with controller._lock:
            worker: threading.Thread | None = controller._worker
            searching: bool = controller._offers_running and not controller._stale
        if worker is not None:
            worker.join(10)
            assert not worker.is_alive()
        if worker is None and not searching:
            return
        time.sleep(0.001)
    pytest.fail("Anime work did not settle")


def _key(controller: AnimeController, key: str) -> None:
    controller.handle_key(key)
    _settle(controller)


def _open(controller: AnimeController) -> None:
    for key in ("text:/", "text:slime", "enter"):
        _key(controller, key)
    if controller._screen is _Screen.ENTRIES:
        _key(controller, "enter")
    assert controller._screen is _Screen.EPISODES


def _frame(controller: AnimeController) -> str:
    return controller.render(120, 40).plain


def _at(controller: AnimeController) -> _Screen:
    return controller._screen


@pytest.mark.unit
def test_all_frozen_identity_reasons_have_polish_texts() -> None:
    assert set(_REASON_TEXTS) == REASONS
    assert all(text and text != reason for reason, text in _REASON_TEXTS.items())


@pytest.mark.unit
@pytest.mark.parametrize("source", ["torrentio", "tsukihime", "nyaa", "knaben", "nekobt"])
def test_offer_row_has_no_source_column(source: str) -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = replace(_candidate(), quality=68.7, stream=replace(_candidate().stream, source=source))
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
        frame: str = _frame(controller)
        assert "Źródło" not in frame
        assert source not in frame.casefold()
        assert controller._view.items[0].quality == "69"
        assert controller._view.items[0].confidence == "95%"


@pytest.mark.unit
def test_uncertain_mark() -> None:
    catalog: _Catalog = _Catalog()
    other: RankedCandidate = replace(
        _candidate(IdentityVerdict.INSUFFICIENT), stream=replace(_candidate().stream, info_hash="b" * 40)
    )
    catalog.offer_read = lambda key: _offer(key, (_candidate(IdentityVerdict.INSUFFICIENT), other, _candidate()))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
        frame: str = _frame(controller)
        assert "*!" in frame
        assert "95% · niepewne" in frame
        assert controller._view.items[0].suggested
    assert [item.confidence for item in controller._view.items] == ["95% · niepewne", "95%", "95%"]


@pytest.mark.unit
@pytest.mark.parametrize(("name", "label"), [("Slime S01E04.mkv", "inny sezon"), ("Slime S02E05.mkv", "inny odcinek")])
def test_conflict_row_shows_reason(name: str, label: str) -> None:
    target: dict[str, object] = {
        "aliases": ["Slime"],
        "type": "TV",
        "local_episode": 4,
        "season": 2,
        "episode": 4,
        "absolute": 28,
    }
    stream: StreamCandidate = replace(_candidate().stream, file_name=name, release=name)
    item: RankedCandidate = rank_candidates(
        target,
        streams_releases((stream,), pack_name=lambda name: parse_release_name(name).is_pack),
        donghua=False,
    )[0]
    assert item.conflict
    offer: EpisodeOffer = _offer(EpisodeKey(1, 4), (item,))
    offer = decode_view(EpisodeOffer, encode_view(offer))
    assert offer.candidates[0].numbering == item.numbering
    assert set(encode_view(item.numbering)) == {
        "mode",
        "season",
        "number",
        "part",
        "local",
        "episode",
        "absolute",
        "target_season",
        "named_season",
        "target_part",
    }
    assert "evidence" not in encode_view(offer.candidates[0])
    catalog: _Catalog = _Catalog()
    catalog.offer_read = lambda _: offer
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
    frame: str = _frame(controller)
    assert label in frame
    assert "%" not in frame
    assert controller._view.items[0].confidence == label
    _key(controller, "text:?")
    details: str = " ".join(_frame(controller).split())
    assert "Odczyt H1 (S/E): sezon" in details
    assert "Cel: lokalny 4; S/E: sezon 2, odcinek 4; absolutny 28" in details
    assert ("sezon 1, odcinek 4" if label == "inny sezon" else "sezon 2, odcinek 5") in details


@pytest.mark.unit
@pytest.mark.parametrize("release_only", [False, True])
def test_details_confidence_uncalibrated_note(release_only: bool) -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = replace(
        _candidate(),
        release_name_only=release_only,
        stream=replace(_candidate().stream, file_name=None if release_only else "Slime - 04.mkv"),
    )
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i", "text:?"):
        _key(controller, key)
    frames: list[str] = []
    for _ in range(30):
        frames.append(" ".join(controller.render(50, 12).plain.split()))
        _key(controller, "down")
    text: str = " ".join(" ".join(item.title for item in controller._view.items).split())
    assert "Kalibracja pewności potwierdzona tylko dla korpusu E1." in text
    assert "Dla nowych źródeł i ocen bez nazwy pliku: estymata bez potwierdzonej kalibracji." in text
    assert any("kalibracji." in frame for frame in frames)
    assert ("· bez nazwy pliku ·" in text) is release_only


@pytest.mark.unit
def test_offer_without_numbering_shows_reason_on_both_release_screens() -> None:
    catalog: _Catalog = _Catalog()
    catalog.offer_read = lambda key: replace(_offer(key), numbering=False, suggestion=None, status="brak numeracji")
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
        assert "brak numeracji" in controller.render(50, 12).plain
        assert not any(item.suggested for item in controller._view.items)


@pytest.mark.unit
def test_episode_flow_keeps_noncontiguous_selection_and_rereads_episodes_only_on_explicit_entry() -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("space", "down", "down", "space", "text:i"):
        _key(controller, key)
    assert catalog.calls[-1] == ("offer", 3)
    assert "Pobierz (" not in _frame(controller)
    calls: list[tuple[str, int]] = catalog.calls.copy()
    for key in ("text:i", "enter", "escape", "escape"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert controller._episode_marks == {1, 3}
    assert controller._positions[_Screen.EPISODES] == 2
    assert catalog.calls == calls
    for key in ("escape", "enter", "escape"):
        _key(controller, key)
    assert _at(controller) is _Screen.ENTRIES
    assert catalog.calls == [*calls, ("episodes", 1)]
    _key(controller, "escape")
    assert _at(controller) is _Screen.QUERY


@pytest.mark.unit
def test_search_opens_entries_directly_when_every_result_is_a_displayed_franchise_entry() -> None:
    catalog: _Catalog = _Catalog()
    catalog.titles = (replace(_title(), anilist_id=2, year=2021), _title())
    catalog.view = Franchise(2, (_entry(1), _entry(2)), (), True)
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.ENTRIES
    assert controller._positions[_Screen.ENTRIES] == 0
    assert catalog.calls == [("titles", 5), ("franchise", 2)]
    assert "Esc" in _frame(controller)
    _key(controller, "escape")
    assert _at(controller) is _Screen.QUERY


@pytest.mark.unit
def test_franchise_status_names_every_entry_and_starts_on_the_first_released_one() -> None:
    catalog: _Catalog = _Catalog()
    catalog.titles = (replace(_title(), anilist_id=3), _title())
    catalog.view = Franchise(
        3,
        (
            replace(_entry(3), status="NOT_YET_RELEASED"),
            replace(_entry(2), status="RELEASING"),
            _entry(1),
        ),
        (),
        True,
    )
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.ENTRIES
    frame: str = _frame(controller)
    assert all(label in frame for label in ("zapowiedź", "w emisji", "zakończone"))
    assert [item.status for item in controller._view.items] == ["zapowiedź", "w emisji", "zakończone"]
    assert [item.navigable for item in controller._view.items] == [True, True, True]
    assert controller._view.cursor == 1


@pytest.mark.unit
@pytest.mark.parametrize("first", ["text:slime", "paste:slime"])
@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.parametrize("extras", [True, False])
def test_single_complete_entry_skips_entries_even_with_extras(first: str, complete: bool, extras: bool) -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(),), (), complete)
    catalog.listing = replace(catalog.listing, specials=catalog.listing.specials if extras else ())
    controller: AnimeController = _controller(catalog)
    _key(controller, first)
    assert controller.input_focused
    assert controller._query == "slime"
    assert catalog.calls == []
    _key(controller, "enter")
    skipped: bool = complete
    assert _at(controller) is (_Screen.EPISODES if skipped else _Screen.ENTRIES)
    assert "Dodatki" not in _frame(controller)
    if skipped:
        assert not controller._episode_marks
        assert not controller._offers
    else:
        assert "SEZONY I CZĘŚCI" not in _frame(controller)
        assert ("Lista niepełna" in _frame(controller)) is (not complete)
    _key(controller, "escape")
    assert _at(controller) is _Screen.QUERY


@pytest.mark.unit
def test_single_extra_entry_opens_its_episodes_directly() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (replace(_entry(), group=EntryGroup.EXTRA),), (), True)
    catalog.listing = replace(catalog.listing, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert catalog.calls == [("titles", 5), ("franchise", 1), ("episodes", 1)]


class _GroupCatalog(_Catalog):
    def __init__(self) -> None:
        super().__init__()
        self.filters: list[object] = []

    def search_title(self, candidate: TitleCandidate, **options: object) -> ReleaseCatalog:
        self.filters.append(options.get("episodes"))
        self.calls.append(("releases", candidate.anilist_id))
        return ReleaseCatalog((), 0)


@pytest.mark.unit
@pytest.mark.parametrize("movie", [False, True])
def test_unmapped_skipped_entry_keeps_its_known_episode_list(movie: bool) -> None:
    class Releases(_GroupCatalog):
        def search_title(self, candidate: TitleCandidate, **options: object) -> ReleaseCatalog:
            super().search_title(candidate, **options)
            span: object = options["episodes"]
            assert span is None or isinstance(span, EpisodeRange)
            title: str = "[Group] Slime [1080p].mkv" if movie else "[Group] Slime - 01 [1080p].mkv"
            release: Release = Release(title, "https://example.test/1", "1", 10, "1 GB", None, "en")
            return catalog_releases((release,), parse_release_name, episodes=span)

    catalog: Releases = Releases()
    catalog.view = Franchise(1, (_entry(format="MOVIE") if movie else _entry(),), (), True)
    catalog.listing = replace(catalog.listing, specials=(), kitsu_id=None)
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert catalog.calls[-1] == ("episodes", 1)
    assert "Brak mapowania" not in _frame(controller)
    _key(controller, "text:d")
    assert _at(controller) is _Screen.EPISODES
    assert not catalog.filters
    _key(controller, "text:i")
    assert _at(controller) is _Screen.OFFER
    assert catalog.calls[-1] == ("offer", 1)
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
@pytest.mark.parametrize("width", [80, 120])
def test_overgeared_without_mapping_uses_anilist_rows_and_explicit_nyaa_preview(width: int) -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    premiere: datetime = datetime(2026, 9, 27, 12, tzinfo=UTC)
    catalog.view = Franchise(
        1, (replace(_entry(format="ONA"), romaji="Overgeared", english="Overgeared", year=2026),), (), True
    )
    catalog.titles = (
        replace(_title(), romaji="Overgeared", english="Overgeared", format="ONA", year=2026, episodes=12),
    )
    catalog.listing = episode_listing(
        1,
        AniZipMapping(None, None, None, (), (), None, {}),
        "RELEASING",
        12,
        tuple(ListedEpisode(number, airs_at=premiere + timedelta(weeks=number - 1)) for number in range(1, 13)),
        datetime(2026, 9, 29, tzinfo=UTC),
    )
    controller: AnimeController = _controller(catalog)
    for key in ("paste:Overgeared", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert controller._episode_screen_count() == 12
    frame: str = controller.render(width, 40).plain
    assert "Overgeared" in frame
    assert "Nie zamówiono" not in frame
    assert "Nie wyemitowano" in frame
    assert "Odcinek 1" in frame
    assert "Odcinek 12" in frame
    assert all(episode.title is None for episode in catalog.listing.episodes)
    assert "27.09" in frame
    assert not catalog.filters
    for key in ("down", "text:d"):
        _key(controller, key)
    assert not catalog.filters
    for key in ("home", "text:d"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert not catalog.filters
    _key(controller, "text:i")
    assert catalog.calls[-1] == ("offer", 1)
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
def test_unmapped_entry_without_any_episode_data_refuses_actions_without_fallback() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, kitsu_id=None, episodes=(), specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    for key in ("text:d", "text:i", "text:p", "text:g"):
        _key(controller, key)
    assert "Nie znam odcinków tego wpisu" in _frame(controller)
    assert catalog.filters == []


@pytest.mark.unit
@pytest.mark.parametrize("related", [False, True])
def test_unmapped_preview_filters_exact_selected_numbers_and_returns_to_episode_draft(related: bool) -> None:
    class Releases(_GroupCatalog):
        def search_title(self, candidate: TitleCandidate, **options: object) -> ReleaseCatalog:
            super().search_title(candidate, **options)
            span: object = options["episodes"]
            assert isinstance(span, EpisodeRange)
            releases: tuple[Release, ...] = tuple(
                Release(
                    f"[Group] Slime - {number:02d} [1080p].mkv",
                    "https://example.test/1",
                    str(number),
                    10,
                    "1 GB",
                    None,
                    "en",
                )
                for number in range(1, 7)
            )
            return catalog_releases(releases, parse_release_name, episodes=span)

    catalog: Releases = Releases()
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    if related:
        _key(controller, "down")
        catalog.titles = (replace(_title(), anilist_id=2),)
    _key(controller, "enter")
    for key in ("space", "down", "down", "space", "text:i"):
        _key(controller, key)
    assert _at(controller) is _Screen.OFFER
    assert catalog.calls[-1] == ("offer", 3)
    assert not catalog.filters
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES
    assert controller._episode_marks == {1, 3}
    for key in ("text:a", "text:a", "home", "text:i"):
        _key(controller, key)
    assert catalog.calls[-1] == ("offer", 1)
    assert not catalog.filters


@pytest.mark.unit
def test_unmapped_sequel_inspects_its_episode_without_legacy_title_resolution() -> None:
    sequel: TitleCandidate = replace(
        _title(), anilist_id=2, romaji="Slime 2", episodes=12, prequel_ids=(1,), synonyms=("Slime Second Season",)
    )

    class Releases(_GroupCatalog):
        def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
            super().find_titles(query)
            return (_title(), sequel) if query == sequel.romaji else (_title(),)

        def season_context(self, candidate: TitleCandidate) -> SeasonContext:
            assert candidate == sequel
            return SeasonContext(2, 12, candidate.episodes)

        def search_title(self, candidate: TitleCandidate, **options: object) -> ReleaseCatalog:
            super().search_title(candidate, **options)
            span: object = options["episodes"]
            context: object = options["context"]
            assert isinstance(span, EpisodeRange)
            assert isinstance(context, SeasonContext)
            releases: tuple[Release, ...] = (
                Release("[Group] Slime - 13 [1080p].mkv", "https://example.test/13", "13", 10, "1 GB", None, "en"),
                Release("[Group] Slime - 14 [1080p].mkv", "https://example.test/14", "14", 10, "1 GB", None, "en"),
            )
            return catalog_releases(releases, parse_release_name, episodes=span, context=context)

    catalog: Releases = Releases()
    catalog.view = Franchise(1, (_entry(), replace(_entry(2), romaji=sequel.romaji)), (), True)
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter", "down", "enter", "text:i"):
        _key(controller, key)
    assert _at(controller) is _Screen.OFFER
    assert catalog.calls[-2:] == [("episodes", 2), ("offer", 1)]
    assert not catalog.filters
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
@pytest.mark.parametrize("unavailable", ["missing", "failed", "entry"])
def test_unmapped_preview_does_not_depend_on_legacy_title_resolution(unavailable: str) -> None:
    class Titles(_GroupCatalog):
        def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
            if unavailable == "failed" and self.calls:
                raise OSError("offline")
            return super().find_titles(query)

    catalog: Titles = Titles()
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter", "down", "enter"):
        _key(controller, key)
    if unavailable == "entry":
        controller._entry = None
    _key(controller, "text:i")
    assert not catalog.filters
    assert _at(controller) is _Screen.OFFER
    assert catalog.calls[-1] == ("offer", 1)


@pytest.mark.unit
def test_unmapped_preview_return_preserves_draft_and_group_shortcut_is_absent() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime 4-6", "enter", "space", "text:i", "escape", "text:g"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert controller._episode_marks == {1}
    assert not catalog.filters


@pytest.mark.unit
def test_cancelled_unmapped_offer_read_does_not_start_release_search() -> None:
    started: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    class Titles(_GroupCatalog):
        def offer(self, key: EpisodeKey) -> EpisodeOffer:
            started.set()
            assert release.wait(10)
            return _offer(key)

    catalog: Titles = Titles()
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter", "down", "enter"):
        _key(controller, key)
    controller.handle_key("text:i")
    worker: threading.Thread | None = controller._worker
    assert worker is not None
    try:
        assert started.wait(10)
        controller.handle_key("escape")
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert _at(controller) is _Screen.EPISODES
    assert not catalog.filters


@pytest.mark.unit
def test_skipped_entry_has_no_groups_or_subscription_creation_route() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, specials=(), kitsu_id=10)
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    for key in ("text:s", "text:g", "text:o"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert not catalog.filters
    assert "G grupy" not in _frame(controller)
    assert "O subskrybuj" not in _frame(controller)


@pytest.mark.unit
@pytest.mark.parametrize("back", ["escape", "enter"])
def test_skipped_entry_catalogue_failure_returns_to_entries_and_allows_retry(back: str) -> None:
    class FailingCatalog(_Catalog):
        def episodes(self, identifier: int) -> EpisodeListing:
            listing: EpisodeListing = super().episodes(identifier)
            if self.calls.count(("episodes", identifier)) == 1:
                raise ControlError("offline", reason=ErrorCode.EPISODE_CATALOG_FAILED.value, answered=True)
            return listing

    catalog: FailingCatalog = FailingCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.PROBLEM
    assert "Lista odcinków niedostępna" in _frame(controller)
    assert controller.handle_key(back).value == "continue"
    assert _at(controller) is _Screen.ENTRIES
    assert "G grupy" not in _frame(controller)
    _key(controller, "enter")
    assert _at(controller) is _Screen.EPISODES
    _key(controller, "escape")
    assert _at(controller) is _Screen.ENTRIES
    assert catalog.calls.count(("episodes", 1)) == 2


@pytest.mark.unit
def test_new_search_resets_skipped_entry_navigation() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter", "escape"):
        _key(controller, key)
    assert _at(controller) is _Screen.QUERY
    catalog.view = Franchise(1, (_entry(), _entry(2)), (), True)
    for key in ("text:/", "enter", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert "G grupy" not in _frame(controller)
    _key(controller, "escape")
    assert _at(controller) is _Screen.ENTRIES


@pytest.mark.unit
def test_single_unrelated_franchise_entry_keeps_title_selection_then_opens_episodes() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(9),), (), True)
    catalog.listing = replace(catalog.listing, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.TITLES
    assert catalog.calls == [("titles", 5), ("franchise", 1)]
    _key(controller, "enter")
    assert _at(controller) is _Screen.EPISODES
    _key(controller, "escape")
    assert _at(controller) is _Screen.TITLES


@pytest.mark.unit
def test_episode_range_escape_discards_input_and_keeps_marks() -> None:
    controller: AnimeController = _controller(_Catalog())
    _open(controller)
    for key in ("space", "text:z", "text:2-4", "escape"):
        _key(controller, key)
    assert controller._range_input is None
    assert not controller.input_focused
    assert controller._episode_marks == {1}
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
def test_episode_range_interrupt_copies_selected_text_before_closing() -> None:
    controller: AnimeController = _controller(_Catalog())
    _open(controller)
    app: Application[None] = Application(input=DummyInput(), output=DummyOutput())
    copied: list[str] = []

    def copy(text: str) -> bool:
        copied.append(text)
        return True

    controller._panel._clipboard = copy
    with set_app(app):
        for key in ("text:z", "text:1-3", "select-all", "interrupt"):
            _key(controller, key)
        assert copied == ["1-3"]
        assert controller._range == "1-3"
        assert controller.input_focused
        assert not controller._episode_marks
        _key(controller, "escape")
        assert controller._range_input is None


@pytest.mark.unit
def test_skipped_entry_drops_late_episode_results_after_escape() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    class SlowCatalog(_Catalog):
        def episodes(self, identifier: int) -> EpisodeListing:
            entered.set()
            assert release.wait(5)
            return replace(super().episodes(identifier), specials=())

    slow: SlowCatalog = SlowCatalog()
    slow.view = catalog.view
    controller: AnimeController = _controller(slow)
    _key(controller, "paste:slime")
    controller.handle_key("enter")
    worker: threading.Thread | None = controller._worker
    try:
        assert entered.wait(5)
        controller.handle_key("escape")
        assert _at(controller) is _Screen.QUERY
    finally:
        release.set()
        assert worker is not None
        worker.join(5)
    assert not worker.is_alive()
    assert _at(controller) is _Screen.QUERY
    assert controller._listing is None


@pytest.mark.unit
def test_episode_marks_compress_only_contiguous_numbers() -> None:
    controller: AnimeController = _controller(_Catalog())
    _open(controller)
    for key in ("text:z", "text:1-3,6", "enter"):
        _key(controller, key)
    assert "Zaznaczone: 4 (1-3, 6)" in _frame(controller)


@pytest.mark.unit
def test_search_lists_titles_when_a_result_is_outside_the_displayed_franchise() -> None:
    catalog: _Catalog = _Catalog()
    catalog.titles = (_title(), replace(_title(), anilist_id=9, romaji="Other", english="Other", year=2010))
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.TITLES
    assert controller._candidates[controller._highlighted].anilist_id == 1
    _key(controller, "enter")
    assert _at(controller) is _Screen.ENTRIES
    assert catalog.calls == [("titles", 5), ("franchise", 1)]
    assert "Esc" in _frame(controller)
    _key(controller, "escape")
    assert _at(controller) is _Screen.TITLES


@pytest.mark.unit
def test_franchise_failure_after_search_keeps_the_titles_reachable() -> None:
    catalog: _Catalog = _Catalog()

    def refused(identifier: int) -> Franchise:
        raise ControlError("private-payload", code=ControlErrorCode.REFUSED, reason="command_failed", answered=True)

    catalog.franchise_read = refused
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.PROBLEM
    assert "private-payload" not in _frame(controller)
    _key(controller, "enter")
    assert _at(controller) is _Screen.TITLES
    assert [item.anilist_id for item in controller._candidates] == [1]


@pytest.mark.unit
def test_titles_kept_after_search_open_entries_on_the_selected_entry() -> None:
    catalog: _Catalog = _Catalog()
    catalog.titles = (_title(), replace(_title(), anilist_id=9, romaji="Other", english="Other", year=2010))
    catalog.view = Franchise(1, (_entry(2), _entry(1)), (), True)
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.ENTRIES
    assert controller._positions[_Screen.ENTRIES] == 0
    assert catalog.calls == [("titles", 5), ("franchise", 1)]


@pytest.mark.unit
def test_a_new_search_with_a_shorter_franchise_resets_the_entry_cursor() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(1), _entry(2), _entry(3)), (), True)
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter", "end", "escape"):
        _key(controller, key)
    assert _at(controller) is _Screen.QUERY
    catalog.view = Franchise(1, (_entry(1),), (), True)
    catalog.titles = (_title(), replace(_title(), anilist_id=9, romaji="Other", english="Other", year=2010))
    for key in ("text:/", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.TITLES
    for key in ("enter", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert catalog.calls[-1] == ("episodes", 1)


@pytest.mark.unit
def test_escape_while_the_franchise_loads_cancels_its_expansion() -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    catalog: _Catalog = _Catalog()

    def slow(identifier: int) -> Franchise:
        entered.set()
        assert release.wait(5)
        return catalog.view

    catalog.franchise_read = slow
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime"):
        _key(controller, key)
    controller.handle_key("enter")
    worker: threading.Thread | None = controller._worker
    try:
        assert entered.wait(5)
        assert isinstance(catalog.cancel, EventCancellationToken)
        assert not catalog.cancel.is_cancelled()
        controller.handle_key("escape")
        assert catalog.cancel.is_cancelled()
    finally:
        release.set()
        assert worker is not None
        worker.join(5)
    assert _at(controller) is _Screen.QUERY


@pytest.mark.unit
@pytest.mark.parametrize(("moves", "searched"), [((), True), (("down",), False)])
def test_entry_group_shortcut_never_opens_legacy_catalog(moves: tuple[str, ...], searched: bool) -> None:
    del searched
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(1), _entry(7)), (), True)
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter", *moves, "text:g"):
        _key(controller, key)
    assert not any(operation == "releases" for operation, _ in catalog.calls)
    assert _at(controller) is _Screen.ENTRIES


@pytest.mark.unit
def test_entry_group_shortcut_is_absent_for_all_search_results() -> None:
    controller: AnimeController = _controller(_Catalog())
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert "G grupy" not in _frame(controller)
    _key(controller, "down")
    assert "G grupy" not in _frame(controller)


@pytest.mark.unit
def test_a_toggles_every_aired_episode_and_the_label_counts_marks() -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing,
        episodes=tuple(replace(item, aired=item.number <= 4) for item in catalog.listing.episodes),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    assert "Zaznaczone" not in _frame(controller)
    _key(controller, "text:a")
    assert controller._episode_marks == {1, 2, 3, 4}
    assert "Zaznaczone: 4 (1-4)" in _frame(controller)
    _key(controller, "text:A")
    assert controller._episode_marks == set()
    for key in ("down", "space", "text:a"):
        _key(controller, key)
    assert controller._episode_marks == {1, 2, 3, 4}


@pytest.mark.unit
@pytest.mark.parametrize("unsupported", [False, True])
@pytest.mark.parametrize("width", [50, 80, 100, 120])
def test_other_releases_always_show_aligned_seeds(width: int, unsupported: bool) -> None:
    catalog: _Catalog = _Catalog()
    first: RankedCandidate = _candidate()
    seeded: RankedCandidate = replace(first, stream=replace(first.stream, seeders=321))
    if unsupported:
        seeded = replace(
            seeded,
            traits=replace(seeded.traits, polish=PolishClass.POLISH, english_subtitles=True),
            supported=False,
        )
    catalog.offer_read = lambda key: _offer(key, (seeded, first))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
    lines: list[str] = controller.render(width, 40).plain.splitlines()
    header: str = next(line for line in lines if "Wydanie" in line and "Seedy" in line)
    known: str = next(line for line in lines if "321" in line)
    unknown: str = lines[lines.index(known) + 1]
    assert header.index("Seedy") + 5 == known.index("321") + 3
    assert unknown[header.index("Seedy") + 4] == "?"
    if unsupported:
        assert "PL · EN" in " ".join(lines)
        assert "1080p" in " ".join(lines)
        assert "format nieobsługiwany" in controller._view.items[0].detail
    assert all(Text(line).cell_len <= width for line in lines)


@pytest.mark.unit
@pytest.mark.parametrize("width", [50, 80, 120])
@pytest.mark.parametrize("verdict", list(IdentityVerdict))
def test_release_views_keep_decision_columns_and_put_size_in_details(width: int, verdict: IdentityVerdict) -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = _candidate(verdict)
    item = replace(
        item,
        traits=replace(item.traits, polish=PolishClass.POLISH, english_subtitles=True),
        stream=replace(item.stream, seeders=321, size_text="1.4 GB"),
    )
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:i", "text:i"):
        _key(controller, key)
        lines: list[str] = controller.render(width, 24).plain.splitlines()
        header: str = next(line for line in lines if "Wydanie" in line)
        assert "Jakość" in header
        assert "Pewność" in header
        assert "Rozm" not in header
        assert "Tożsamość" not in header
        if controller._screen is _Screen.OFFER and verdict is IdentityVerdict.MISMATCH:
            continue
        row: str = lines[lines.index(header) + 1]
        assert controller._view.items[0].image == "1080p"
        assert controller._view.items[0].language == "PL · EN"
        assert controller._view.items[0].seeds == "321"
        displayed: str = " ".join(" ".join(lines).split())
        assert "321" in displayed
        assert "1080p" in displayed
        assert "PL · EN" in displayed
        assert "Rozmiar: 1.4 GB" in controller._view.items[0].detail
        assert "indeks:" not in " ".join(lines)
        assert "platforma: —" not in " ".join(lines)
        if verdict is IdentityVerdict.INSUFFICIENT:
            assert "!" in row
        if verdict is IdentityVerdict.MISMATCH:
            assert "!" in row


@pytest.mark.unit
def test_offer_columns_remain_fixed_when_language_changes() -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = replace(_candidate(), stream=replace(_candidate().stream, seeders=321))
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    lines: list[str] = controller.render(50, 24).plain.splitlines()
    compact: str = next(line for line in lines if "Wydanie" in line)
    assert "obraz 1080p · język —" in " ".join(lines)
    _key(controller, "text:?")
    assert "zgodny:" in controller.render(50, 24).plain
    _key(controller, "escape")
    _key(controller, "text:i")
    _key(controller, "text:?")
    assert "zgodny:" in controller.render(50, 24).plain
    _key(controller, "escape")
    for key in ("escape", "escape"):
        _key(controller, key)
    item = replace(item, traits=replace(item.traits, polish=PolishClass.POLISH, english_subtitles=True))
    _key(controller, "text:i")
    lines = controller.render(50, 24).plain.splitlines()
    expanded: str = next(line for line in lines if "Wydanie" in line)
    assert expanded == compact
    assert "obraz 1080p · język PL · EN" in " ".join(lines)
    assert "PL" in "\n".join(lines)
    assert "321" in "\n".join(lines)


@pytest.mark.unit
def test_entries_and_episodes_show_no_group_or_special_headings() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = replace(catalog.view, entries=(_entry(), replace(_entry(2), group=EntryGroup.EXTRA)))
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert all(heading not in _frame(controller) for heading in ("Dodatki", "SEZONY", "FILMY"))
    _key(controller, "enter")
    assert "Dodatki" not in _frame(controller)


@pytest.mark.unit
@pytest.mark.parametrize(("typed", "expected"), [("1,3,5-6", {1, 3, 5, 6}), ("5-", {5, 6})])
def test_episode_range_replaces_marks_without_selecting_intermediate_numbers(typed: str, expected: set[int]) -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:a", "text:z", f"text:{typed}", "enter"):
        _key(controller, key)
    assert controller._episode_marks == expected
    assert len(catalog.calls) == 3


@pytest.mark.unit
@pytest.mark.parametrize("typed", ["30", "1,3,30", "2.5", "-2", "0", "4-2", "daz"])
def test_invalid_episode_range_preserves_selection_and_command_letters_only_edit(typed: str) -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("space", "text:z", *(f"text:{character}" for character in typed)):
        _key(controller, key)
    assert controller._range_input is not None
    assert controller._range_input.text == typed
    assert controller._episode_marks == {1}
    _key(controller, "enter")
    assert controller._episode_marks == {1}
    assert len(catalog.calls) == 3
    assert "Zakres:" in _frame(controller)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "aired", "warning"), [("UNKNOWN", None, "TITLE_CATALOG_FAILED"), ("RELEASING", 0, None)]
)
def test_past_mapping_dates_do_not_make_unconfirmed_episodes_selectable(
    status: str, aired: int | None, warning: str | None
) -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing,
        status=status,
        aired=aired,
        schedule_warning=warning,
        episodes=(ListedEpisode(1, "Episode 1", datetime(2020, 1, 1, tzinfo=UTC)),),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    assert "Nie wyemitowano" in _frame(controller)
    for key in ("space", "enter", "text:a", "text:z", "text:1", "enter", "text:d"):
        _key(controller, key)
    assert controller._episode_marks == set()
    assert not any(call[0] == "offer" for call in catalog.calls)


@pytest.mark.unit
def test_ani_zip_label_follows_each_episode_date_origin_without_a_schedule_warning() -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing,
        schedule_warning=None,
        episodes=(
            ListedEpisode(1, "Episode 1", datetime(2020, 1, 1, tzinfo=UTC), aired=True, airs_at_fallback=True),
            ListedEpisode(2, "Episode 2", datetime(2020, 1, 8, tzinfo=UTC), aired=True),
        ),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    rows: dict[str, str] = {
        name: line for line in _frame(controller).splitlines() for name in ("Episode 1", "Episode 2") if name in line
    }
    assert "(ani.zip)" not in rows["Episode 1"]
    assert "(ani.zip)" not in rows["Episode 2"]
    assert "E1: termin emisji niepotwierdzony (ani.zip)" in _frame(controller)
    _key(controller, "down")
    assert "termin emisji niepotwierdzony" not in _frame(controller)


@pytest.mark.unit
def test_episode_selectability_follows_only_the_domain_aired_flag_of_each_episode() -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing,
        status="HIATUS",
        aired=None,
        episodes=(ListedEpisode(1, "Episode 1", aired=False), ListedEpisode(2, "Episode 2", aired=True)),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:a", "space", "down", "space", "space"):
        _key(controller, key)
    assert controller._episode_marks == {2}
    assert "E1 jeszcze nie wyemitowano" not in _frame(controller)
    _key(controller, "home")
    _key(controller, "space")
    assert "E1 jeszcze nie wyemitowano" in _frame(controller)
    assert controller._episode_marks == {2}


@pytest.mark.unit
def test_preview_without_marks_uses_highlighted_episode_and_future_episode_is_not_selectable() -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing,
        status="RELEASING",
        aired=3,
        episodes=tuple(replace(item, aired=item.number <= 3) for item in catalog.listing.episodes),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("end", "space", "text:d"):
        _key(controller, key)
    assert controller._episode_marks == set()
    assert "E6 jeszcze nie wyemitowano" in _frame(controller)
    for key in ("home", "down", "text:i"):
        _key(controller, key)
    assert catalog.calls[-1] == ("offer", 2)
    assert controller._offer_numbers == (2,)


@pytest.mark.unit
def test_movie_has_one_film_row_and_only_previews_its_first_episode_when_mapped() -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = replace(catalog.view, entries=(_entry(format="MOVIE"),))
    catalog.listing = replace(catalog.listing, kitsu_id=10, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert controller._entries_skipped
    assert catalog.calls.count(("episodes", 1)) == 1
    assert controller._listing is not None
    assert [item.number for item in controller._listing.episodes] == [1]
    assert "Film" in _frame(controller)
    _key(controller, "text:i")
    assert [call for call in catalog.calls if call[0] == "offer"] == [("offer", 1)]
    _key(controller, "escape")
    _key(controller, "escape")
    assert _at(controller) is _Screen.QUERY


@pytest.mark.unit
@pytest.mark.parametrize("leave", ["escape", "cancel"])
def test_leaving_incremental_offer_drops_late_result_and_sends_no_remaining_requests(leave: str) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    catalog: _Catalog = _Catalog()

    def offer(key: EpisodeKey) -> EpisodeOffer:
        if key.number == 2:
            entered.set()
            assert release.wait(5)
        return _offer(key)

    catalog.offer_read = offer
    controller: AnimeController = _controller(catalog)
    _open(controller)
    controller.handle_key("text:a")
    controller.handle_key("down")
    controller.handle_key("text:i")
    worker: threading.Thread | None = controller._worker
    try:
        assert entered.wait(5)
        assert "Szukam…" in _frame(controller)
        controller.cancel() if leave == "cancel" else controller.handle_key(leave)
        before: str = _frame(controller)
    finally:
        release.set()
        assert worker is not None
        worker.join(5)
    assert _frame(controller) == before
    assert catalog.calls[-1] == ("offer", 2)
    assert 2 not in controller._offers


@pytest.mark.unit
@pytest.mark.parametrize("verdict", list(IdentityVerdict))
def test_offer_verdict_labels_uncertainty_and_empty_suggestion_are_explicit(verdict: IdentityVerdict) -> None:
    catalog: _Catalog = _Catalog()
    catalog.offer_read = lambda key: _offer(key, (_candidate(verdict),))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    frame: str = _frame(controller)
    assert ("!" in frame) is (verdict is IdentityVerdict.INSUFFICIENT)
    assert ("Brak wydania" in frame) is (verdict is IdentityVerdict.MISMATCH)
    reason: str = "niepewny: Brak wskazanego pliku."
    if verdict is IdentityVerdict.INSUFFICIENT:
        assert reason in frame
    _key(controller, "text:i")
    if verdict is IdentityVerdict.INSUFFICIENT:
        assert reason in _frame(controller)
    assert ("inny odcinek" if verdict is IdentityVerdict.MISMATCH else "Brak wskazanego pliku.") in _frame(controller)
    assert "indeks:" not in _frame(controller)


@pytest.mark.unit
@pytest.mark.parametrize("high_verdict", list(IdentityVerdict))
def test_other_releases_hide_low_resolutions_only_with_a_matching_high_release(high_verdict: IdentityVerdict) -> None:
    catalog: _Catalog = _Catalog()
    catalog.offer_read = lambda key: _offer(
        key,
        (
            _candidate(high_verdict, 2160),
            _candidate(resolution=720),
            _candidate(resolution=480),
            _candidate(resolution=1440),
            _candidate(resolution=None),
        ),
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    _key(controller, "text:i")
    assert [item.traits.resolution for item in controller._release_candidates] == (
        [2160, 1440, None] if high_verdict is IdentityVerdict.MATCH else [2160, 720, 480, 1440, None]
    )


@pytest.mark.unit
def test_unsupported_high_resolution_match_does_not_hide_a_supported_lower_match() -> None:
    catalog: _Catalog = _Catalog()
    avi: RankedCandidate = replace(_candidate(), supported=False)
    catalog.offer_read = lambda key: _offer(key, (avi, _candidate(resolution=720)))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    _key(controller, "text:i")
    assert [item.traits.resolution for item in controller._release_candidates] == [1080, 720]


@pytest.mark.unit
@pytest.mark.parametrize("size", [(120, 40), (50, 24), (40, 12), (20, 5)])
def test_all_episode_views_fit_without_rendering_network_or_mutating_selection(size: tuple[int, int]) -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("escape", "enter", "text:d", "text:i"):
        _key(controller, key)
        calls: list[tuple[str, int]] = catalog.calls.copy()
        for _ in range(3):
            frame: Text = controller.render(*size)
            assert len(frame.plain.splitlines()) <= size[1]
            assert all(Text(line).cell_len <= size[0] for line in frame.plain.splitlines())
        assert catalog.calls == calls


@pytest.mark.unit
def test_episode_scroll_preserves_selection_and_keyboard_follows_cursor() -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing, episodes=tuple(ListedEpisode(n, aired=True) for n in range(1, 51)), aired=50
    )
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "space")
    controller.render(50, 12)
    controller.scroll(3)
    controller.render(50, 12)
    assert controller._offsets[_Screen.EPISODES] > 0
    assert controller._positions[_Screen.EPISODES] == 0
    assert controller._episode_marks == {1}
    _key(controller, "down")
    frame: str = controller.render(50, 12).plain
    assert "\u276f [ ] 2" in frame
    assert controller._positions[_Screen.EPISODES] == 1
    assert len(catalog.calls) == 3


@pytest.mark.unit
@pytest.mark.parametrize("width", [50, 120])
def test_catalogue_headers_name_the_work_and_columns_align_at_both_widths(width: int) -> None:
    catalog: _Catalog = _Catalog()
    first: RankedCandidate = _candidate()
    second: RankedCandidate = replace(first, stream=replace(first.stream, release="[Group] 界界 longer title"))
    catalog.offer_read = lambda key: _offer(key, (first, second))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "escape")
    entries: str = controller.render(width, 40).plain
    assert "\u203a" not in entries
    assert "ANIME" in (line.strip() for line in entries.splitlines())
    assert all(label in entries for label in ("Premiera", "Tytuł", "Typ", "Status"))
    _key(controller, "enter")
    episodes: list[str] = controller.render(width, 40).plain.splitlines()
    header: str = next(line for line in episodes if "Stan" in line)
    episode: str = next(line for line in episodes if "Episode 1" in line)
    assert episode[header.index("Stan") :].strip() == "Do pobrania"
    _key(controller, "text:i")
    offers: list[str] = controller.render(width, 40).plain.splitlines()
    assert "Plik:" in controller._view.items[0].detail
    header = next(line for line in offers if "Wydanie" in line)
    offered: str = offers[offers.index(header) + 1]
    assert "1080p" in " ".join(offers)
    assert offered[header.index("Pewność") :].strip() == "95%"
    _key(controller, "text:i")
    candidates: list[str] = controller.render(width, 40).plain.splitlines()
    title: str = next(line for line in candidates if line.strip())
    assert "ANIME \u203a Slime" in title
    header = next(line for line in candidates if "Wydanie" in line and "Seedy" in line)
    quality_column: int = Text(header[: header.index("Jakość")]).cell_len
    release_rows: list[str] = candidates[candidates.index(header) + 1 : candidates.index(header) + 3]
    assert len(release_rows) == 2
    assert all(Text(line[: line.index("95%")]).cell_len == quality_column + 8 for line in release_rows)
    assert all(Text(line).cell_len <= width for line in candidates)


@pytest.mark.unit
def test_candidate_reason_and_file_details_remain_complete_at_fifty_columns() -> None:
    catalog: _Catalog = _Catalog()
    reason: str = "Work anchor and exact mapped season/episode match; residual is technical or catalogued."
    filename: str = "[Group] Slime 界界 episode four with a long descriptive filename.mkv"
    candidate: RankedCandidate = replace(
        _candidate(),
        identity=IdentityAssessment(IdentityVerdict.MATCH, reason),
        stream=replace(_candidate().stream, file_name=filename),
    )
    catalog.offer_read = lambda key: _offer(key, (candidate,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    _key(controller, "text:i")
    frame: str = controller.render(50, 24).plain
    normalized: str = " ".join(frame.split())
    assert _REASON_TEXTS[reason] not in normalized
    assert f"Plik: {filename} · Rozmiar: ?" in controller._view.items[0].detail
    _key(controller, "text:?")
    assert _REASON_TEXTS[reason] in " ".join(controller.render(50, 24).plain.split())
    _key(controller, "escape")
    assert _at(controller) is _Screen.CANDIDATES
    assert all(Text(line).cell_len <= 50 for line in frame.splitlines())
    assert "Esc" in frame


class _Owner(_Catalog):
    def __init__(self) -> None:
        super().__init__()
        self.release: threading.Event = threading.Event()
        self.batches: list[tuple[tuple[EpisodeKey, ...], str]] = []
        self.admitted: set[int] = {2}
        self.refused_reason: str = "no_suggestion"
        self.offer_view: EpisodeOfferView | None = None

    def episode_states(self, anilist_id: int, numbers: Sequence[int]) -> tuple[EpisodeStatus, ...]:
        return tuple(
            EpisodeStatus(EpisodeKey(anilist_id, number), "ordered" if number in self.admitted else "not_ordered")
            for number in numbers
        )

    def episode_offer_start(self, key: EpisodeKey, *, repeat: bool = False, command_id: str) -> Mapping[str, object]:
        del command_id
        self.calls.append(("repeat" if repeat else "offer", key.number))
        self.offer_view = EpisodeOfferView("offer", "fixture", self.offer_read(key))
        return {"offer_id": "offer", "instance_id": "fixture"}

    def episode_offer_get(self, offer_id: str) -> Mapping[str, object]:
        assert offer_id == "offer"
        assert self.offer_view is not None
        return {
            "state": "ready",
            "revision": self.offer_view.revision,
            "final": True,
            "view": encode_view(self.offer_view),
        }

    def interrupt_reads(self) -> None:
        self.calls.append(("interrupt", 0))

    def episode_download(self, keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch:
        self.batches.append((tuple(keys), command_id))
        if len(self.batches) == 1:
            assert self.release.wait(10)
            return EpisodeBatch(command_id, "fixture", tuple(keys), "accepted")
        results: tuple[EpisodeResult, ...] = (
            EpisodeResult(keys[0], "admitted", "a1", "o1"),
            *(EpisodeResult(key, self.refused_reason) for key in keys[1:]),
        )
        self.admitted.add(keys[0].number)
        return EpisodeBatch(command_id, "fixture", tuple(keys), "completed", results)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("state", "label"),
    [
        ("ordered", "Zlecono"),
        ("downloading", "Pobieram"),
        ("downloaded", "Pobrano"),
        ("processing", "Przetwarzam"),
        ("processing_failed", "Błąd"),
        ("ready", "Gotowe"),
        ("possibly_admitted", "Już zlecone?"),
        ("future_state", "Zlecono"),
        ("not_ordered", "Do pobrania"),
    ],
)
def test_owner_episode_states_have_explicit_labels(monkeypatch: pytest.MonkeyPatch, state: str, label: str) -> None:
    owner: _Owner = _Owner()
    monkeypatch.setattr(
        owner,
        "episode_states",
        lambda anilist_id, numbers: tuple(EpisodeStatus(EpisodeKey(anilist_id, n), state) for n in numbers),
    )
    controller: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    _open(controller)

    lines: list[str] = _frame(controller).splitlines()
    header: str = next(line for line in lines if "Stan" in line)
    row: str = next(line for line in lines if "Episode 1 " in line)
    assert row[header.index("Stan") :].strip() == label
    assert "Nie zamówiono" not in "\n".join(lines)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reason", "status", "cause"),
    [
        ("no_suggestion", "Brak wydania", "Brak wydania"),
        ("TORRENT_SOURCE_FAILED", "Błąd źródła", "Źródło wydań nie odpowiada"),
        ("shutting_down", "Nie zlecono", "AniShift się kończy"),
        ("acquisition_unavailable", "Niedostępne", "Pobieranie jest niedostępne w tej sesji"),
    ],
)
def test_download_orders_marked_episodes_through_the_owner_and_stays_on_the_list(
    monkeypatch: pytest.MonkeyPatch, reason: str, status: str, cause: str
) -> None:
    monkeypatch.setattr(anime_module, "_BATCH_POLL_S", 0.0)
    owner: _Owner = _Owner()
    owner.refused_reason = reason
    controller: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    _open(controller)
    assert re.search(r"2\s+Episode 2\s+.*Zlecono", _frame(controller))
    for key in ("space", "down", "down", "space", "text:d"):
        _key(controller, key)
    pending: str = _frame(controller)
    assert _at(controller) is _Screen.EPISODES
    assert "szukam" in pending
    assert re.search(r"\[x\]\s+1\s+Episode 1", pending)
    assert re.search(r"\[x\]\s+3\s+Episode 3", pending)
    assert controller._episode_marks == {1, 3}
    owner.release.set()
    deadline: float = time.monotonic() + 10
    while controller._sending and time.monotonic() < deadline:
        time.sleep(0.01)
    frame: str = _frame(controller)
    assert _at(controller) is _Screen.EPISODES
    assert "Zlecono 1" in frame
    assert re.search(r"1\s+Episode 1\s+.*Zlecono", frame)
    assert not re.search(r"\[x\]\s+1\s+Episode 1", frame)
    assert re.search(rf"\[x\]\s+3\s+Episode 3\s+.*{status}", frame)
    assert f"nie zlecono 3: {cause}" in frame
    assert [keys for keys, _ in owner.batches] == [(EpisodeKey(1, 1), EpisodeKey(1, 3))] * 2
    assert len({command_id for _, command_id in owner.batches}) == 1
    assert controller._episode_marks == {3}
    assert not any(operation == "offer" for operation, _ in owner.calls)
    _key(controller, "text:i")
    assert _at(controller) is _Screen.OFFER


class _ChoiceOwner(_Owner):
    def __init__(self) -> None:
        super().__init__()
        self.statuses: dict[int, EpisodeStatus] = {
            1: EpisodeStatus(EpisodeKey(1, 1), "possibly_admitted", "episode_possibly_admitted"),
            2: EpisodeStatus(EpisodeKey(1, 2), "ordered", "episode_file_unresolved", "admission"),
        }
        self.choices: list[tuple[EpisodeOfferView, StreamCandidate, str, bool, bool]] = []
        self.file_choices: list[tuple[EpisodeFiles, EpisodeFile, str]] = []
        self.files: EpisodeFiles = EpisodeFiles(
            "admission", "revision-1", (EpisodeFile(7, "Season 1/Slime - 02.mkv", 1000),)
        )
        self.refusal: ControlError | None = None

    def episode_states(self, anilist_id: int, numbers: Sequence[int]) -> tuple[EpisodeStatus, ...]:
        self.calls.append(("states", len(numbers)))
        return tuple(
            self.statuses.get(number, EpisodeStatus(EpisodeKey(anilist_id, number), "not_ordered"))
            for number in numbers
        )

    def episode_offer_start(self, key: EpisodeKey, *, repeat: bool = False, command_id: str) -> Mapping[str, object]:
        result: Mapping[str, object] = super().episode_offer_start(key, repeat=repeat, command_id=command_id)
        assert self.offer_view is not None
        if repeat:
            self.offer_view = replace(self.offer_view, conflict=("legacy:1",), unknown_previous=True)
        return result

    def episode_choose(
        self,
        offer: EpisodeOfferView,
        candidate: StreamCandidate,
        *,
        command_id: str,
        deviation_confirmed: bool = False,
        conflict_confirmed: bool = False,
    ) -> Mapping[str, object]:
        self.choices.append((offer, candidate, command_id, deviation_confirmed, conflict_confirmed))
        if self.refusal is not None:
            raise self.refusal
        self.statuses[offer.offer.key.number] = EpisodeStatus(offer.offer.key, "ordered")
        return {"admission_id": "new"}

    def episode_files(self, admission_id: str) -> EpisodeFiles:
        self.calls.append(("files", 1))
        assert admission_id == self.files.admission_id
        return self.files

    def episode_file_choose(
        self, files: EpisodeFiles, selected: EpisodeFile, *, command_id: str
    ) -> Mapping[str, object]:
        self.file_choices.append((files, selected, command_id))
        if self.refusal is not None:
            self.files = replace(self.files, revision="revision-2", files=(EpisodeFile(9, "New/02.mkv", 2000),))
            raise self.refusal
        self.statuses[2] = EpisodeStatus(EpisodeKey(1, 2), "ordered", admission_id="admission")
        return {"admission_id": "admission"}


def _owner_controller(owner: _Owner) -> AnimeController:
    controller: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    _open(controller)
    return controller


class _PartialOwner(_ChoiceOwner):
    def __init__(self) -> None:
        super().__init__()
        self.final: bool = False
        self.failure: str | None = None
        self.gets: int = 0

    def episode_offer_get(self, offer_id: str) -> Mapping[str, object]:
        self.gets += 1
        if self.failure is not None:
            return {"state": "failed", "message": self.failure}
        return {**super().episode_offer_get(offer_id), "final": self.final}


def _refresh_partial(controller: AnimeController) -> None:
    controller.receive("episode_offer_partial", {"offer_id": "offer"})
    deadline: float = time.monotonic() + 5
    while controller._offer_refreshing and time.monotonic() < deadline:
        time.sleep(0.001)
    assert not controller._offer_refreshing


def _open_partial(owner: _PartialOwner) -> AnimeController:
    controller: AnimeController = _owner_controller(owner)
    controller.handle_key("text:i")
    deadline: float = time.monotonic() + 5
    while controller._offer_view is None and time.monotonic() < deadline:
        time.sleep(0.001)
    assert controller._offer_view is not None
    return controller


@pytest.mark.unit
@pytest.mark.parametrize("after_partial", [False, True])
def test_offer_failed_shows_error(after_partial: bool) -> None:
    owner: _PartialOwner = _PartialOwner()
    controller: AnimeController = _owner_controller(owner)
    if after_partial:
        controller.handle_key("text:i")
        deadline: float = time.monotonic() + 5
        while controller._offer_view is None and time.monotonic() < deadline:
            time.sleep(0.001)
        assert controller._offer_view is not None
    owner.failure = "TORRENT_SOURCE_FAILED"
    if after_partial:
        _refresh_partial(controller)
    else:
        _key(controller, "text:i")
    assert controller._screen is _Screen.PROBLEM
    assert "Źródło wydań nie odpowiada" in _frame(controller)
    assert not controller._offers
    gets: int = owner.gets
    _refresh_partial(controller)
    assert owner.gets == gets


@pytest.mark.unit
def test_final_revision_without_new_candidates() -> None:
    owner: _PartialOwner = _PartialOwner()
    controller: AnimeController = _open_partial(owner)
    assert "szukam jeszcze" in _frame(controller)
    assert owner.offer_view is not None
    owner.offer_view = replace(owner.offer_view, revision=2)
    owner.final = True
    _refresh_partial(controller)
    assert controller._offer_view is not None
    assert controller._offer_view.revision == 2
    assert "szukam jeszcze" not in _frame(controller)


@pytest.mark.unit
def test_lower_revision_ignored() -> None:
    owner: _PartialOwner = _PartialOwner()
    controller: AnimeController = _open_partial(owner)
    assert owner.offer_view is not None
    original: EpisodeOfferView = owner.offer_view
    owner.offer_view = replace(original, revision=3)
    _refresh_partial(controller)
    owner.offer_view = replace(original, revision=2, offer=replace(original.offer, candidates=()))
    _refresh_partial(controller)
    assert controller._offer_view is not None
    assert controller._offer_view.revision == 3
    assert controller._offer_view.offer.candidates == original.offer.candidates


@pytest.mark.unit
def test_partial_offer_keeps_cursor_on_hash() -> None:
    owner: _PartialOwner = _PartialOwner()
    first: RankedCandidate = _candidate()
    second: RankedCandidate = replace(first, stream=replace(first.stream, info_hash="b" * 40))
    owner.offer_read = lambda key: _offer(key, (first, second))
    controller: AnimeController = _open_partial(owner)
    for key in ("text:i", "down", "space"):
        controller.handle_key(key)
    assert owner.offer_view is not None
    owner.offer_view = replace(
        owner.offer_view, revision=2, offer=replace(owner.offer_view.offer, candidates=(second, first))
    )
    _refresh_partial(controller)
    controller.render(80, 24)
    assert controller._view.items[controller._view.cursor].key == second.stream.info_hash
    assert controller._view.selected == {second.stream.info_hash}


@pytest.mark.unit
@pytest.mark.parametrize("columns", [50, 80])
def test_offer_after_3s_pending_line_without_rows(columns: int) -> None:
    owner: _PartialOwner = _PartialOwner()
    owner.offer_read = lambda key: replace(_offer(key, ()), pending=("Knaben", "nekoBT"))
    controller: AnimeController = _open_partial(owner)
    frame: str = controller.render(columns, 24).plain
    assert "szukam jeszcze: Knaben, nekoBT" in frame
    assert "Szukam…" not in frame
    assert all(cell_len(line) <= columns for line in frame.splitlines())


@pytest.mark.unit
def test_final_event_before_start_response(monkeypatch: pytest.MonkeyPatch) -> None:
    owner: _PartialOwner = _PartialOwner()
    owner.final = True
    controller: AnimeController = _owner_controller(owner)
    start: Callable[..., Mapping[str, object]] = owner.episode_offer_start

    def early(key: EpisodeKey, *, repeat: bool, command_id: str) -> Mapping[str, object]:
        result: Mapping[str, object] = start(key, repeat=repeat, command_id=command_id)
        controller.receive("episode_offer_partial", {"offer_id": "offer"})
        assert owner.gets == 0
        return result

    monkeypatch.setattr(owner, "episode_offer_start", early)
    _key(controller, "text:i")
    assert owner.gets == 1
    assert controller._offer_view is not None
    assert not controller._offers_running


class _HttpNyaa:
    def __init__(self, http: httpx.Client) -> None:
        self.http: httpx.Client = http

    def search(self, query: str, *, categories: Sequence[str] = ()) -> tuple[Release, ...]:
        return search_releases(query, http=self.http, categories=categories)


@contextmanager
def _searching_panel(
    tmp_path: Path,
) -> Iterator[tuple[AnimeController, StateController, ResidentSession, threading.Event, AutomationOwner]]:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()
    owners: list[AutomationOwner] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.knaben.org":
            entered.set()
            assert release.wait(15)
            return httpx.Response(200, json={"hits": [], "total": {"value": 0}})
        if request.url.host == "torrentio.strem.fun":
            return httpx.Response(
                200,
                json={
                    "streams": [
                        {
                            "infoHash": "a" * 40,
                            "fileIdx": 0,
                            "title": "[Group] Tensei shitara Slime Datta Ken - 01 [1080p].mkv",
                            "behaviorHints": {"filename": "[Group] Tensei shitara Slime Datta Ken - 01 [1080p].mkv"},
                        }
                    ]
                },
            )
        if request.url.host in {"nyaa.si", "nekobt.to"}:
            return httpx.Response(200, text="<rss><channel/></rss>", headers={"content-type": "application/xml"})
        return httpx.Response(404)

    now: list[float] = [time.time()]
    control: RequestControl = RequestControl(
        httpx.MockTransport(respond), clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay)
    )
    with (
        httpx.Client(transport=control) as http,
        _running_panel(
            tmp_path,
            ["ok"],
            [],
            [datetime(2026, 9, 29, tzinfo=UTC).timestamp()],
            remote=True,
            admissions=True,
            owner_ready=owners.append,
        ) as (controller, panel, acquisition),
    ):
        assert panel is not None
        acquisition._episode_search = EpisodeSearch(
            torrentio=TorrentioSource(http),
            nyaa=_HttpNyaa(http),
            knaben=KnabenSource(http),
            nekobt=NekoBTSource(http),
            tsukihime=TsukiHimeSource(http),
            request_control=control,
            pack_name=lambda name: parse_release_name(name).is_pack,
        )
        _open(controller)
        controller.handle_key("text:i")
        try:
            assert entered.wait(5)
            deadline: float = time.monotonic() + 5
            while (
                controller._offer_view is None or not controller._offer_view.offer.candidates
            ) and time.monotonic() < deadline:
                time.sleep(0.01)
            assert controller._offer_view is not None
            assert controller._offer_view.offer.candidates
            assert controller._resident is not None
            yield controller, panel, controller._resident, release, owners[0]
        finally:
            release.set()


@pytest.mark.integration
def test_choose_during_search_before_slow_source(tmp_path: Path) -> None:
    with _searching_panel(tmp_path) as (controller, _panel, session, release, owner):
        assert controller._offers_running
        assert controller._offer_view is not None
        key: EpisodeKey = controller._offer_view.offer.key
        controller.handle_key("text:d")
        if controller._confirm_choice is not None:
            controller.handle_key("enter")
        deadline: float = time.monotonic() + 5
        while controller._screen is not _Screen.EPISODES and time.monotonic() < deadline:
            time.sleep(0.01)
        assert controller._screen is _Screen.EPISODES
        assert not release.is_set()
        admission_id: str | None = session.episode_states(key.anilist_id, (key.number,))[0].admission_id
        assert admission_id is not None
        notice: str = controller._notice
        acquisitions: tuple[AcquisitionConfirmation, ...] = owner.state.acquisitions
        assert owner._on_owner(lambda: owner._active_io) > 0
        release.set()
        deadline = time.monotonic() + 5
        while owner._on_owner(lambda: owner._active_io) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert owner._on_owner(lambda: owner._active_io) == 0
        assert controller._screen is _Screen.EPISODES
        assert controller._notice == notice
        assert session.episode_states(key.anilist_id, (key.number,))[0].admission_id == admission_id
        assert owner.state.acquisitions == acquisitions


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reason", "label"),
    [
        ("transfer_failed", "Błąd pobierania"),
        ("publication_failed", "Błąd eksportu"),
        ("waiting_previous_transfer", "Czeka na stare"),
        ("publication_missing", "Brak pliku"),
        ("transfer_recorded", "Konflikt hasha"),
        ("source_failed", "Błąd źródła"),
        ("legacy_unreadable", "Błąd zleceń"),
        ("subscription_checking", "Kontrola"),
        ("subscription_check_skipped", "Bez kontroli"),
        ("subscription_awaiting_airing", "Czeka na emisję"),
        ("subscription_awaiting_release", "Czeka na wydanie"),
        ("subscription_exhausted", "Wyczerpano próby"),
    ],
)
def test_episode_problem_reason_overrides_ordinary_state_label(reason: str, label: str) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.statuses[1] = EpisodeStatus(EpisodeKey(1, 1), "downloading", reason)
    controller: AnimeController = _owner_controller(owner)
    assert label in _frame(controller)


_UNLABELLED_REASONS: Final[frozenset[EpisodeReason]] = frozenset(
    {
        EpisodeReason.ACQUISITION_UNAVAILABLE,
        EpisodeReason.ADMISSION_FAILED,
        EpisodeReason.FINALIZATION_FAILED,
        EpisodeReason.EPISODE_CHANGED,
        EpisodeReason.COMMAND_REUSED,
    }
)


@pytest.mark.unit
def test_every_owner_reason_has_a_stan_label_or_an_explicit_fallback() -> None:
    assert {reason for reason in EpisodeReason if reason not in EPISODE_REASON_LABELS} == _UNLABELLED_REASONS


@pytest.mark.unit
@pytest.mark.parametrize("reason", [*EpisodeReason, *EPISODE_REASON_LABELS, "reason_from_a_newer_owner"])
def test_every_refused_stan_label_fits_its_column(reason: str) -> None:
    assert cell_len(anime_module._refused_result(reason)[0]) <= anime_view._EPISODE_STATUS_WIDTH


@pytest.mark.unit
def test_an_episode_in_progress_keeps_a_short_stan_and_names_cancellation_in_the_notice() -> None:
    assert anime_module._refused_result(EpisodeReason.EPISODE_IN_PROGRESS) == (
        "W toku",
        "W toku · C anuluj w Przetwarzaniu",
    )


class _LostBatchOwner(_Owner):
    def __init__(self, problem: ControlError) -> None:
        super().__init__()
        self.problem: ControlError = problem

    def episode_download(self, keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch:
        self.batches.append((tuple(keys), command_id))
        if len(self.batches) == 1:
            raise self.problem
        return EpisodeBatch(
            command_id, "fixture", tuple(keys), "completed", (EpisodeResult(keys[0], "admitted", "a1", "o1"),)
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("problem", "ended"),
    [
        (ControlError("closed", code=ControlErrorCode.REFUSED), False),
        (ControlError("timeout", code=ControlErrorCode.INTERNAL), False),
        (ControlError("foreign", code=ControlErrorCode.INVALID_PAYLOAD), False),
        (ControlError("failed", code=ControlErrorCode.INTERNAL, answered=True), False),
        (ControlError("refused", code=ControlErrorCode.REFUSED, answered=True), True),
    ],
)
def test_a_lost_batch_response_keeps_its_command_for_enter_while_a_refusal_ends_it(
    monkeypatch: pytest.MonkeyPatch, problem: ControlError, *, ended: bool
) -> None:
    monkeypatch.setattr(anime_module, "_BATCH_POLL_S", 0.0)
    owner: _LostBatchOwner = _LostBatchOwner(problem)
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:d")
    deadline: float = time.monotonic() + 10
    while controller._batch_running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not controller._batch_running
    if ended:
        assert controller._pending_batch is None
        assert controller._notice.startswith("Nie zlecono")
        return
    assert controller._pending_batch is not None
    assert controller._notice == "Wynik nieznany · Enter sprawdź wynik"
    _key(controller, "enter")
    while controller._pending_batch is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert [command for _keys, command in owner.batches] == [owner.batches[0][1]] * 2
    assert controller._pending_batch is None


@pytest.mark.unit
def test_ready_episode_with_a_missing_result_reads_as_downloadable_and_keeps_its_repeat_offer() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.statuses[1] = EpisodeStatus(EpisodeKey(1, 1), "not_ordered", "result_missing", "admission-1")
    controller: AnimeController = _owner_controller(owner)
    lines: list[str] = _frame(controller).splitlines()
    header: str = next(line for line in lines if "Stan" in line)
    row: str = next(line for line in lines if "Episode 1 " in line)
    assert row[header.index("Stan") :].strip() == "Do pobrania"
    _key(controller, "text:p")
    deadline: float = time.monotonic() + 10
    while ("repeat", 1) not in owner.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ("repeat", 1) in owner.calls


@pytest.mark.unit
@pytest.mark.parametrize("state", ["ordered", "downloading", "processing"])
@pytest.mark.parametrize("key", ["space", "text:d"])
def test_active_episode_does_not_submit_and_explains_where_to_cancel(state: str, key: str) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.statuses[1] = EpisodeStatus(EpisodeKey(1, 1), state)
    controller: AnimeController = _owner_controller(owner)
    _key(controller, key)
    assert controller._notice == "W toku · C anuluj w Przetwarzaniu"
    assert not owner.batches


@pytest.mark.unit
@pytest.mark.parametrize("state", ["ordered", "downloading"])
def test_an_active_subscription_attempt_is_still_ordered_by_d(state: str) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.statuses[1] = EpisodeStatus(EpisodeKey(1, 1), state, admission_id="attempt", attempt=True)
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:d")
    try:
        deadline: float = time.monotonic() + 10
        while not owner.batches and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [keys for keys, _command in owner.batches] == [(EpisodeKey(1, 1),)]
    finally:
        owner.release.set()
        finished: float = time.monotonic() + 10
        while controller._batch_running and time.monotonic() < finished:
            time.sleep(0.01)
    assert not controller._batch_running


@pytest.mark.unit
@pytest.mark.parametrize("verdict", [IdentityVerdict.MATCH, IdentityVerdict.INSUFFICIENT, IdentityVerdict.MISMATCH])
@pytest.mark.parametrize("cancel", [False, True])
def test_repeat_requires_inspected_conflict_and_separate_identity_consent(
    verdict: IdentityVerdict, cancel: bool
) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.offer_read = lambda key: _offer(key, (_candidate(verdict),))
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:p")
    assert _at(controller) is _Screen.OFFER
    frame: str = controller.render(50, 24).plain
    assert "Obecne pliki zostają" in frame
    assert "Nie można potwierdzić odmienności wydania" in frame
    assert all(Text(line).cell_len <= 50 for line in frame.splitlines())
    assert not owner.choices
    _key(controller, "enter")
    if cancel and verdict is IdentityVerdict.MATCH:
        _key(controller, "escape")
        _key(controller, "escape")
        assert not owner.choices
        return
    _key(controller, "text:d")
    if verdict is not IdentityVerdict.MATCH:
        assert _at(controller) is _Screen.PROBLEM
        assert not owner.choices
        assert "Enter pobierz mimo to" in controller.render(50, 24).plain
        _key(controller, "escape" if cancel else "enter")
    assert len(owner.choices) == (0 if cancel else 1)
    if not cancel:
        view, stream, command, deviation, conflict = owner.choices[0]
        assert view.conflict == ("legacy:1",)
        assert stream == _candidate(verdict).stream
        assert command
        assert deviation is (verdict is not IdentityVerdict.MATCH)
        assert conflict
        assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
def test_changed_repeat_conflict_is_refused_in_existing_problem_view() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.refusal = ControlError("changed", code=ControlErrorCode.STALE_PREVIEW, reason="episode_changed")
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:p")
    _key(controller, "text:d")
    assert _at(controller) is _Screen.PROBLEM
    assert "Wybór lub konflikt zmienił się" in controller.render(50, 24).plain
    assert len(owner.choices) == 1
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES
    assert owner.statuses[1].state == "possibly_admitted"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reason", "sentence"),
    [
        ("episode_admitted", "Odcinek już zlecony"),
        ("episode_possibly_admitted", "Już zlecone?"),
    ],
)
def test_choosing_an_already_ordered_episode_states_the_refusal_and_names_the_repeat(
    reason: str, sentence: str
) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.refusal = ControlError("refused", code=ControlErrorCode.REFUSED, reason=reason, answered=True)
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:i")
    _key(controller, "text:d")
    frame: str = controller.render(50, 24).plain
    assert _at(controller) is _Screen.PROBLEM
    assert sentence in frame
    assert "P pobierz ponownie" in frame
    assert "Rezydent nie wykonał polecenia" not in frame


@pytest.mark.unit
@pytest.mark.parametrize(
    ("reason", "result"),
    [
        ("episode_admitted", ("Zlecono", "Odcinek już zlecony · P pobierz ponownie")),
        ("episode_possibly_admitted", ("Już zlecone?", "Już zlecone? · P pobierz ponownie")),
        ("pack_in_progress", ("Czeka na paczkę", "Czeka na paczkę · P pobierz ponownie")),
    ],
)
def test_a_refused_repeatable_download_names_the_repeat_in_the_notice(reason: str, result: tuple[str, str]) -> None:
    assert anime_module._refused_result(reason) == result


@pytest.mark.unit
@pytest.mark.parametrize("cancel", [False, True])
def test_unresolved_episode_uses_offer_list_and_submits_exact_file_revision(cancel: bool) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "down")
    assert "Enter wskaż plik" in controller.render(50, 24).plain
    _key(controller, "enter")
    assert _at(controller) is _Screen.OFFER
    frame: str = controller.render(50, 24).plain
    assert "Season 1/Slime - 02.mkv" in frame
    assert "1,000 B" in frame
    assert all(Text(line).cell_len <= 50 for line in frame.splitlines())
    _key(controller, "escape" if cancel else "enter")
    assert _at(controller) is _Screen.EPISODES
    assert len(owner.file_choices) == (0 if cancel else 1)
    if not cancel:
        files, selected, command = owner.file_choices[0]
        assert files == owner.files
        assert selected == EpisodeFile(7, "Season 1/Slime - 02.mkv", 1000)
        assert command


@pytest.mark.unit
def test_stale_file_revision_refreshes_list_without_resubmitting() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.refusal = ControlError("changed", code=ControlErrorCode.STALE_PREVIEW, reason="file_map_changed")
    controller: AnimeController = _owner_controller(owner)
    for key in ("down", "enter", "enter"):
        _key(controller, key)
    frame: str = controller.render(50, 24).plain
    assert "Lista plików zmieniła się" in frame
    assert "New/02.mkv" in frame
    assert len(owner.file_choices) == 1
    assert owner.file_choices[0][0].revision == "revision-1"
    owner.refusal = None
    _key(controller, "enter")
    assert len(owner.file_choices) == 2
    assert owner.file_choices[1][0].revision == "revision-2"
    assert owner.file_choices[1][1] == EpisodeFile(9, "New/02.mkv", 2000)
    assert owner.file_choices[1][2] != owner.file_choices[0][2]


@pytest.mark.unit
def test_more_than_one_hundred_marks_refuses_before_ipc_and_preserves_selection() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.statuses.clear()
    owner.listing = replace(owner.listing, episodes=tuple(ListedEpisode(n, aired=True) for n in range(1, 102)))
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "text:a")
    calls: list[tuple[str, int]] = owner.calls.copy()
    _key(controller, "text:d")
    assert controller._episode_marks == set(range(1, 102))
    assert owner.calls == calls
    assert not owner.batches
    assert "Limit: 100 odcinków" in controller.render(50, 24).plain


@pytest.mark.unit
def test_fresh_panel_reads_admitted_and_unordered_states_beyond_first_hundred() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.listing = replace(owner.listing, episodes=tuple(ListedEpisode(n, aired=True) for n in range(1, 103)))
    owner.statuses[101] = EpisodeStatus(EpisodeKey(1, 101), "ordered")
    controller: AnimeController = _owner_controller(owner)
    _key(controller, "end")
    frame: str = controller.render(50, 24).plain
    assert "102" in frame
    assert "Nie zamówiono" not in frame
    assert controller._episode_states[EpisodeKey(1, 102)].state == "not_ordered"
    _key(controller, "up")
    assert "P ponownie" in controller.render(50, 24).plain
    _key(controller, "text:a")
    assert 101 not in controller._episode_marks
    assert 102 in controller._episode_marks
    assert ("states", 100) in owner.calls
    assert ("states", 2) in owner.calls


@pytest.mark.unit
@pytest.mark.parametrize("leave", ["escape", "tab"])
def test_episode_batch_survives_navigation_without_late_view_change(
    monkeypatch: pytest.MonkeyPatch,
    leave: str,
) -> None:
    monkeypatch.setattr(anime_module, "_BATCH_POLL_S", 0.0)
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    owner: _Owner = _Owner()
    controller: AnimeController = _owner_controller(owner)
    for key in ("space", "down", "down", "space", "text:d"):
        _key(controller, key)
    panel: StateController = StateController(cast("ResidentSession", owner), lambda: None)
    panel.attach_anime(controller)
    panel._tab = 0
    panel.handle_key(leave)
    screen: _Screen = controller._screen
    tab: int = panel._tab
    owner.release.set()
    deadline: float = time.monotonic() + 10
    while controller._sending and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not controller._sending
    assert controller._screen is screen
    assert panel._tab == tab
    assert len(owner.batches) == 2
    assert len({command for _, command in owner.batches}) == 1


@pytest.mark.unit
def test_inspection_uses_only_cursor_and_render_navigation_never_submit() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    controller: AnimeController = _owner_controller(owner)
    for key in ("down", "down", "space", "down", "space", "text:i"):
        _key(controller, key)
    assert owner.calls[-1] == ("offer", 4)
    calls: list[tuple[str, int]] = owner.calls.copy()
    for key in ("enter", "down", "up", "text:?", "escape", "escape", "escape"):
        controller.render(50, 24)
        _key(controller, key)
    assert owner.calls == [*calls, ("interrupt", 0)]
    assert not owner.choices
    assert not owner.file_choices
    assert not owner.batches
    assert controller._episode_marks == {3, 4}


@pytest.mark.unit
def test_owner_refresh_removes_newly_admitted_marks_and_retains_uncertain_file_problem() -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    controller: AnimeController = _owner_controller(owner)
    for key in ("down", "down", "space"):
        _key(controller, key)
    owner.statuses[3] = EpisodeStatus(
        EpisodeKey(1, 3),
        "ordered",
        "episode_file_unresolved",
        "another-panel",
        uncertain=True,
    )
    controller.refresh_episode_states()
    assert not controller._episode_marks
    frame: str = controller.render(50, 24).plain
    assert "Enter wskaż plik" in frame
    assert "P ponownie" in frame
    assert "Space zaznacz" in frame
    _key(controller, "text:d")
    assert not owner.batches
    assert not owner.choices


@pytest.mark.unit
def test_cursor_download_interrupted_batch_preserves_only_unaccepted_marks(monkeypatch: pytest.MonkeyPatch) -> None:
    owner: _ChoiceOwner = _ChoiceOwner()
    controller: AnimeController = _owner_controller(owner)
    finished: threading.Event = threading.Event()
    controller._invalidate = finished.set

    def download(keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch:
        owner.batches.append((tuple(keys), command_id))
        owner.statuses[keys[0].number] = EpisodeStatus(keys[0], "ordered")
        return EpisodeBatch(command_id, "fixture", tuple(keys), "interrupted", (EpisodeResult(keys[0], "admitted"),))

    monkeypatch.setattr(owner, "episode_download", download)
    for key in ("down", "down", "text:d"):
        _key(controller, key)
    assert finished.wait(10)
    assert owner.batches[0][0] == (EpisodeKey(1, 3),)
    assert len(owner.batches) == 1
    finished.clear()
    for key in ("down", "space", "down", "space", "text:d"):
        _key(controller, key)
    assert finished.wait(10)
    assert controller._episode_marks == {5}
    assert "Nie zlecono E5" in controller.render(50, 24).plain
    assert owner.batches[1][0] == (EpisodeKey(1, 4), EpisodeKey(1, 5))
    assert owner.batches[0][1] != owner.batches[1][1]


@pytest.mark.unit
@pytest.mark.parametrize("screen", list(_Screen))
@pytest.mark.parametrize("tab", [0, 2])
@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("following", [False, True])
def test_state_event_reads_only_one_visible_episode_page_when_active_and_changed(
    monkeypatch: pytest.MonkeyPatch,
    screen: _Screen,
    tab: int,
    changed: bool,
    following: bool,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    owner: _ChoiceOwner = _ChoiceOwner()
    owner.listing = replace(owner.listing, episodes=tuple(ListedEpisode(n, aired=True) for n in range(1, 1001)))
    controller: AnimeController = _owner_controller(owner)
    reads: list[tuple[int, ...]] = []

    def states(anilist_id: int, numbers: Sequence[int]) -> tuple[EpisodeStatus, ...]:
        assert anilist_id == 1
        reads.append(tuple(numbers))
        return tuple(EpisodeStatus(EpisodeKey(1, n), "not_ordered") for n in numbers)

    monkeypatch.setattr(owner, "episode_states", states)
    session: ResidentSession = cast(
        "ResidentSession",
        SimpleNamespace(command=lambda *args: {}, library=lambda: (), acquisition_states=lambda hashes: []),
    )
    panel: StateController = StateController(session, lambda: None)
    panel.attach_anime(controller)
    panel._tab = tab
    controller._screen = screen
    controller._positions[_Screen.EPISODES] = 750
    controller._offsets[_Screen.EPISODES] = 300
    controller._follow_cursor = following
    payload: dict[str, object] = {"auto_enabled": True}
    panel._snapshot = {} if changed else payload.copy()
    try:
        panel._receive(session, {"event": "state_changed", "payload": payload})
        expected: bool = screen is _Screen.EPISODES and tab == 0 and changed
        assert len(reads) == int(expected)
        if expected:
            assert len(reads[0]) <= 100
            assert (751 if following else 301) in reads[0]
        panel._receive(session, {"event": "state_changed", "payload": payload.copy()})
        assert len(reads) == int(expected)
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.unit
@pytest.mark.parametrize("sending", [False, True])
def test_escape_interrupts_reads_but_not_sending_independently_of_busy_label(sending: bool) -> None:
    owner: _Owner = _Owner()
    controller: AnimeController = _owner_controller(owner)
    controller._start_work("Same label", _Screen.EPISODES, sending=sending)
    _key(controller, "escape")
    assert (("interrupt", 0) in owner.calls) is (not sending)
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
def test_episode_footer_wraps_only_between_complete_shortcuts() -> None:
    controller: AnimeController = _controller(_Catalog())
    _open(controller)
    lines: list[str] = controller.render(50, 24).plain.splitlines()
    assert all(
        any(hint in line for line in lines)
        for hint in ("Space zaznacz", "D pobierz", "I wydania", "P ponownie", "? więcej", "Esc")
    )


@pytest.mark.unit
def test_local_offer_defect_logs_class_and_fails_the_entire_preview() -> None:
    catalog: _Catalog = _Catalog()

    def broken(key: EpisodeKey) -> EpisodeOffer:
        if key.number == 2:
            raise ValueError("private-payload")
        return _offer(key)

    catalog.offer_read = broken
    controller: AnimeController = _controller(catalog)
    captured: list[str] = []
    handler: int = loguru_logger.add(captured.append, format="{message} {extra}")
    try:
        _open(controller)
        _key(controller, "text:a")
        _key(controller, "down")
        _key(controller, "text:i")
        assert controller._screen is _Screen.PROBLEM
        assert "Rezydent nie wykonał polecenia." in _frame(controller)
        assert not controller._offers
        assert "error_class" in "".join(captured)
        assert "ValueError" in "".join(captured)
        assert "private-payload" not in _frame(controller) + "".join(captured)
    finally:
        loguru_logger.remove(handler)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "reason", "restart"),
    [
        (ControlErrorCode.INTERNAL, "command_failed", True),
        (ControlErrorCode.REFUSED, "command_failed", False),
        (ControlErrorCode.INTERNAL, "unknown_reason", False),
        (ControlErrorCode.INTERNAL, "TITLE_CATALOG_FAILED", False),
    ],
)
def test_only_internal_command_failed_on_new_operations_suggests_restart(
    code: ControlErrorCode,
    reason: str,
    restart: bool,
) -> None:
    catalog: _Catalog = _Catalog()

    def refused(key: EpisodeKey) -> EpisodeOffer:
        raise ControlError("private-payload", code=code, reason=reason, answered=True)

    catalog.offer_read = refused
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:i")
    assert ("Rezydent nie wykonał polecenia." in _frame(controller)) is restart
    assert "private-payload" not in _frame(controller)


@pytest.mark.unit
@pytest.mark.parametrize("before", [True, False])
@pytest.mark.parametrize(
    ("provider", "code"),
    [
        ("anilist", ErrorCode.TITLE_CATALOG_FAILED),
        ("anizip", ErrorCode.EPISODE_CATALOG_FAILED),
        ("torrentio", ErrorCode.TORRENT_SOURCE_FAILED),
        ("nyaa", ErrorCode.TORRENT_SOURCE_FAILED),
    ],
)
def test_retry_deadline_uses_the_failed_provider_in_both_snapshot_orders_without_reads(
    before: bool,
    provider: str,
    code: ErrorCode,
) -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    now: list[float] = [1000.0]
    controller._clock = lambda: now[0]
    locks: list[Mapping[str, object]] = [
        {"provider": provider, "until": datetime.fromtimestamp(1090, UTC).isoformat()},
        {
            "provider": "nyaa" if provider == "torrentio" else "torrentio",
            "until": datetime.fromtimestamp(1999, UTC).isoformat(),
        },
    ]
    if before:
        controller.refresh_provider_locks(locks)
    controller._report(
        0,
        ControlError("private", reason=code.value, answered=True),
        _Screen.EPISODES,
        provider=provider,
        catalog_command=True,
    )
    if not before:
        controller.refresh_provider_locks(locks)
    assert "spróbuj za 90 s" in _frame(controller)
    now[0] += 30
    assert "spróbuj za 60 s" in _frame(controller)
    now[0] += 60
    assert "Możesz spróbować ponownie" in _frame(controller)
    assert catalog.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("before", [True, False])
def test_schedule_warning_survives_navigation_and_explicit_reentry_refreshes_only_then(before: bool) -> None:
    catalog: _Catalog = _Catalog()
    catalog.listing = replace(
        catalog.listing, schedule_warning="TITLE_CATALOG_FAILED", schedule_retry_at=datetime.fromtimestamp(1090, UTC)
    )
    controller: AnimeController = _controller(catalog)
    now: list[float] = [1000.0]
    controller._clock = lambda: now[0]
    locks: list[Mapping[str, object]] = [
        {"provider": "anilist", "until": datetime.fromtimestamp(1120, UTC).isoformat()}
    ]
    if before:
        controller.refresh_provider_locks(locks)
    _open(controller)
    if not before:
        controller.refresh_provider_locks(locks)
    assert "ponów za 120 s" in _frame(controller)
    _key(controller, "down")
    assert "Brak terminów emisji (AniList)" in _frame(controller)
    now[0] = 1120
    assert "wróć i otwórz ponownie" in _frame(controller)
    assert len(catalog.calls) == 3
    catalog.listing = _listing()
    _key(controller, "escape")
    assert len(catalog.calls) == 3
    _key(controller, "enter")
    assert len(catalog.calls) == 4
    assert "Brak terminów emisji" not in _frame(controller)


@pytest.mark.unit
def test_provider_locks_reach_anime_at_attachment_and_later_state_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    session: ResidentSession = cast(
        "ResidentSession",
        SimpleNamespace(command=lambda *args: {}, library=lambda: (), acquisition_states=lambda hashes: []),
    )
    panel: StateController = StateController(session, lambda: None)
    controller: AnimeController = _controller(_Catalog())
    lock: dict[str, object] = {"provider": "anilist", "until": datetime.fromtimestamp(1090, UTC).isoformat()}
    try:
        panel._snapshot = {"provider_locks": [lock]}
        panel.attach_anime(controller)
        assert controller._provider_locks == {"anilist": 1090}
        lock = {**lock, "until": datetime.fromtimestamp(1120, UTC).isoformat()}
        panel._receive(session, {"event": "state_changed", "payload": {"provider_locks": [lock]}})
        assert controller._provider_locks == {"anilist": 1120}
    finally:
        panel.close()
        panel._thread.join(5)


class _NoSource:
    def search(self, query: str, *, categories: Sequence[str] = ()) -> tuple[Release, ...]:
        raise AssertionError((query, categories))


def _unused_handler(
    run_root: Path, plan: ExecutionPlan, source_groups: Mapping[str, InspectedSourceGroup]
) -> TaskHandler:
    raise AssertionError((run_root, plan, source_groups))


_START: Final[int] = int(datetime(2026, 9, 29, tzinfo=UTC).timestamp())


def _replay(scenario: list[str], sent: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    fixtures: Path = Path(__file__).parents[1] / "fixtures" / "search"
    recorded: dict[str, Any] = json.loads((fixtures / "anilist__franchise__101280.json").read_text(encoding="utf-8"))
    pages: dict[tuple[int, ...], object] = {tuple(sorted(page["ids"])): page["body"] for page in recorded["requests"]}

    def respond(request: httpx.Request) -> httpx.Response:  # noqa: PLR0911 - explicit provider response routes
        host: str = request.url.host
        sent.append(host + request.url.path)
        variables: dict[str, object] = json.loads(request.content)["variables"] if request.content else {}
        provider: str = {"graphql.anilist.co": "anilist", "api.ani.zip": "anizip", "torrentio.strem.fun": "torrentio"}[
            host
        ]
        if scenario[0] == provider or (scenario[0] == "schedule" and provider == "anilist" and "id" in variables):
            return httpx.Response(429, headers={"Retry-After": "90"})
        if provider == "anizip":
            if request.url.params.get("anilist_id") == "139498":
                return httpx.Response(
                    200,
                    json={
                        "mappings": {"kitsu_id": 99, "type": "MOVIE"},
                        "episodeCount": 1,
                        "episodes": {"1": {"title": {"en": "Scarlet Bond"}, "airDateUtc": "2022-11-25"}},
                    },
                )
            return httpx.Response(200, content=(fixtures / "anizip__101280.json").read_bytes())
        if provider == "torrentio":
            if request.url.path == "/stream/movie/kitsu:99.json":
                return httpx.Response(200, json={"streams": []})
            return httpx.Response(200, content=(fixtures / "torrentio__kitsu-41024-4.json").read_bytes())
        if "ids" in variables:
            if scenario[0] == "movie":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "Page": {
                                "media": [
                                    {
                                        "id": 139498,
                                        "type": "ANIME",
                                        "format": "MOVIE",
                                        "status": "FINISHED",
                                        "title": {"romaji": "Scarlet Bond", "english": "Scarlet Bond"},
                                        "relations": {"edges": []},
                                    }
                                ]
                            }
                        }
                    },
                )
            identifiers: object = variables["ids"]
            assert isinstance(identifiers, list)
            return httpx.Response(200, json=pages[tuple(sorted(identifiers))])
        if "id" in variables:
            releasing: bool = scenario[0] == "releasing"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "Media": {
                            "id": variables["id"],
                            "status": "RELEASING" if releasing else "FINISHED",
                            "episodes": 24,
                            "airingSchedule": {
                                "pageInfo": {"currentPage": 1, "hasNextPage": False},
                                "nodes": [
                                    {"episode": number, "airingAt": _START + (60 if number == 4 else -86400 * number)}
                                    for number in range(1, 5)
                                ]
                                if releasing
                                else [],
                            },
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "Page": {
                        "media": [
                            {
                                "id": 139498 if scenario[0] == "movie" else 101280,
                                "title": {"romaji": "Tensei Shitara Slime Datta Ken", "english": "Slime"},
                                "format": "MOVIE" if scenario[0] == "movie" else "TV",
                                "status": "FINISHED",
                                "seasonYear": 2018,
                                "episodes": 24,
                            }
                        ]
                    }
                }
            },
        )

    return respond


@contextmanager
def _running_panel(  # noqa: PLR0913
    tmp_path: Path,
    scenario: list[str],
    sent: list[str],
    now: list[float],
    *,
    remote: bool,
    admissions: bool = False,
    owner_ready: Callable[[AutomationOwner], None] | None = None,
) -> Iterator[tuple[AnimeController, StateController | None, AcquisitionService]]:
    control: RequestControl = RequestControl(
        httpx.MockTransport(_replay(scenario, sent)),
        clock=lambda: now[0],
        sleep=lambda delay: now.__setitem__(0, now[0] + delay),
    )
    with httpx.Client(transport=control) as http:
        acquisition: AcquisitionService = AcquisitionService(
            source=_NoSource(),
            client=QBittorrentClient("http://unused.test", http=http),
            workspace_root=tmp_path,
            parse_name=parse_release_name,
            title_catalog=AniListCatalog(http),
            episode_catalog=AniZipCatalog(http),
            stream_source=TorrentioSource(http),
            request_control=control,
            clock=lambda: now[0],
        )
        service: AppService = AppService(
            workspace_root=tmp_path,
            settings=Settings(_env_file=None),
            user_settings=UserSettings(),
            inspector=WorkspaceInspector(DefaultMediaProbe()),
            handler_factory=_unused_handler,
            preset_loader=default_preset_file,
            preset_saver=lambda value: None,
            settings_saver=lambda value: None,
            acquisition=acquisition,
        )
        if not remote:
            controller: AnimeController = AnimeController(service, lambda: None)
            controller._clock = lambda: now[0]
            try:
                yield controller, None, acquisition
            finally:
                service.close()
            return
        owner: AutomationOwner = AutomationOwner(
            service,
            WatchStateStore(tmp_path / "state.json"),
            instance_id="fixture",
            clock=lambda: datetime.fromtimestamp(now[0], UTC),
        )
        if owner_ready is not None:
            owner_ready(owner)
        thread: threading.Thread = threading.Thread(target=owner.serve, daemon=True)
        thread.start()
        key: bytes = os.urandom(32)
        endpoint: str = control_endpoint(tmp_path)
        server: ControlServer = ControlServer(endpoint, key, owner.handle, on_disconnect=owner.disconnect)
        owner.attach_broadcast(server.broadcast)
        session: ResidentSession = ResidentSession(tmp_path, lambda: ControlClient(endpoint, key))
        controller = AnimeController(service, lambda: None, resident=session)
        controller._clock = lambda: now[0]
        panel: StateController = StateController(session, lambda: None)
        panel.attach_anime(controller)
        try:
            yield controller, panel, acquisition
            if not admissions:
                assert not owner.state.acquisitions
            assert not owner.state.requests
        finally:
            panel.close()
            session.close()
            server.close()
            owner.request_shutdown()
            thread.join(10)
            panel._thread.join(10)
            service.close()
        assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
def test_slime_fixture_flows_from_query_to_s1e4_preview_without_admission(tmp_path: Path, remote: bool) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, ["ok"], sent, now, remote=remote) as (controller, _, _):
        _open(controller)
        _key(controller, "escape")
        assert controller._franchise is not None
        index: int = next(i for i, entry in enumerate(controller._franchise.entries) if entry.anilist_id == 101280)
        _key(controller, "home")
        for _ in range(index):
            _key(controller, "down")
        _key(controller, "enter")
        assert controller._listing is not None
        assert controller._listing.anilist_id == 101280
        for key in ("down", "down", "down", "text:i"):
            _key(controller, key)
        assert controller._offers[4].suggestion is not None
        offer: EpisodeOffer = controller._offers[4]
        assert offer.suggestion is not None
        assert offer.candidates[offer.suggestion].identity.verdict is IdentityVerdict.MATCH
        assert "Szukam…" not in _frame(controller)
        _key(controller, "text:i")
        _key(controller, "text:?")
        assert "zgodny" in _frame(controller)
        _key(controller, "escape")
        assert any("/stream/series/kitsu:41024:4.json" in url for url in sent)
        neighbours: list[IdentityVerdict] = [
            item.identity.verdict
            for item in offer.candidates
            if re.search(r"Nikki|Diaries|OAD|OVA", item.stream.file_name or "")
        ]
        assert neighbours
        assert IdentityVerdict.MATCH not in neighbours


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
def test_reentering_an_entry_after_an_airing_makes_that_episode_selectable_and_keeps_cursor_and_marks(
    tmp_path: Path, remote: bool
) -> None:
    sent: list[str] = []
    now: list[float] = [float(_START)]
    with _running_panel(tmp_path, ["releasing"], sent, now, remote=remote) as (controller, _, _):
        _open(controller)
        for key in ("space", "down", "down", "down", "space"):
            _key(controller, key)
        assert controller._episode_marks == {1}
        assert "E4 jeszcze nie wyemitowano" in _frame(controller)
        reads: int = len(sent)
        now[0] += 120
        _key(controller, "space")
        assert controller._episode_marks == {1}
        for key in ("escape", "enter"):
            _key(controller, key)
        assert controller._screen is _Screen.EPISODES
        assert controller._positions[_Screen.EPISODES] == 3
        _key(controller, "space")
        assert controller._episode_marks == {1, 4}
        assert len(sent) == reads


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
def test_movie_entry_previews_through_movie_endpoint_without_admission(tmp_path: Path, remote: bool) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, ["movie"], sent, now, remote=remote) as (controller, _, _):
        _open(controller)
        assert "Film" in _frame(controller)
        assert controller._listing is not None
        assert len(controller._listing.episodes) == 1
        _key(controller, "text:i")
        assert controller._offers[1].key == EpisodeKey(139498, 1)
        assert "Brak wydania" in _frame(controller)
        assert "torrentio.strem.fun/stream/movie/kitsu:99.json" in sent
        assert not any("/stream/series/" in url for url in sent)


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("provider", ["anilist", "torrentio"])
def test_http_429_reaches_panel_with_source_deadline_and_no_fallback(
    tmp_path: Path,
    remote: bool,
    provider: str,
) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, [provider], sent, now, remote=remote) as (controller, panel, _):
        for key in ("text:/", "text:slime", "enter", "enter", "enter", "down", "down", "down", "text:i"):
            _key(controller, key)
            if controller._screen is _Screen.PROBLEM:
                break
        if panel is not None:
            panel._receive(panel._parent, {"event": "state_changed", "payload": panel._parent.command("status")})
        assert controller._screen is _Screen.PROBLEM
        expected: str = {
            "anilist": "AniList nie odpowiada",
            "torrentio": "Źródło wydań nie odpowiada",
        }[provider]
        assert expected in _frame(controller)
        assert "spróbuj za 90 s" in _frame(controller)
        assert "uruchom go ponownie" not in _frame(controller)
        calls: int = len(sent)
        now[0] += 30
        assert "spróbuj za 60 s" in _frame(controller)
        now[0] += 60
        assert "Możesz spróbować ponownie" in _frame(controller)
        assert len(sent) == calls


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
def test_ani_zip_429_keeps_episode_listing_and_offer_without_numbering(tmp_path: Path, *, remote: bool) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, ["anizip"], sent, now, remote=remote) as (controller, panel, acquisition):
        _open(controller)
        assert controller._screen == _Screen.EPISODES
        assert controller._listing is not None
        assert len(controller._listing.episodes) == 24
        deadline: float = acquisition.blocked_until(("anizip",))
        assert now[0] < deadline <= now[0] + 90
        for key in ("down", "down", "down", "text:i"):
            _key(controller, key)
        assert controller._screen.value == "offer"
        offer: EpisodeOffer = controller._offers[4]
        assert not offer.numbering
        assert offer.suggestion is None
        assert offer.status == "brak numeracji"
        assert not any("torrentio.strem.fun" in url for url in sent)
        assert sum("api.ani.zip" in url for url in sent) == 1
        if panel is not None:
            panel._receive(panel._parent, {"event": "state_changed", "payload": panel._parent.command("status")})
            assert controller._provider_locks["anizip"] == deadline
        calls: int = len(sent)
        now[0] += 90
        _frame(controller)
        assert len(sent) == calls


@pytest.mark.integration
def test_owner_offer_defect_reaches_problem_with_error_class_and_without_suggestions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    captured: list[str] = []
    handler: int = loguru_logger.add(captured.append, format="{message} {extra}")
    try:
        with _running_panel(tmp_path, ["ok"], sent, now, remote=True) as (controller, _, acquisition):
            _open(controller)

            def broken(
                key: EpisodeKey, _switches: object, **_options: object
            ) -> tuple[EpisodeOffer, dict[str, object]]:
                raise ValueError("private-payload")

            monkeypatch.setattr(acquisition, "search_episode", broken)
            _key(controller, "text:i")
            assert controller._screen is _Screen.PROBLEM
            assert "Rezydent nie wykonał polecenia." in _frame(controller)
            assert not controller._offers
            assert "ValueError" in "".join(captured)
            assert "error_class" in "".join(captured)
            assert "private-payload" not in "".join(captured) + _frame(controller)
    finally:
        loguru_logger.remove(handler)


@pytest.mark.integration
def test_oversized_owner_offer_reports_problem_and_same_connection_remains_usable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, ["ok"], sent, now, remote=True) as (controller, _, acquisition):
        _open(controller)
        item: RankedCandidate = _candidate()
        item = replace(item, stream=replace(item.stream, release="x" * (1024 * 1024)))
        monkeypatch.setattr(
            acquisition, "search_episode", lambda key, _switches, **_options: (_offer(key, (item,)), {})
        )
        _key(controller, "text:i")
        assert "Widok nieaktualny: odpowiedź przekracza limit" in _frame(controller)
        assert not controller._offers
        assert controller._resident is not None
        assert "instance_id" in controller._resident.command("status")


@pytest.mark.integration
def test_partial_schedule_429_keeps_episode_list_until_explicit_reentry_after_deadline(tmp_path: Path) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    scenario: list[str] = ["schedule"]
    with _running_panel(tmp_path, scenario, sent, now, remote=True) as (controller, panel, _):
        _open(controller)
        assert panel is not None
        panel._receive(panel._parent, {"event": "state_changed", "payload": panel._parent.command("status")})
        assert "Brak terminów emisji (AniList)" in _frame(controller)
        assert "ponów za 90 s" in _frame(controller)
        assert controller._listing is not None
        assert len(controller._listing.episodes) == 24
        assert controller._listing.aired is None
        _key(controller, "space")
        _key(controller, "text:d")
        assert not controller._episode_marks
        assert not controller._offers
        assert "Nie wyemitowano" in _frame(controller)
        reads: int = len(sent)
        now[0] += 90
        _key(controller, "down")
        assert "wróć i otwórz ponownie" in _frame(controller)
        assert len(sent) == reads
        scenario[0] = "ok"
        _key(controller, "escape")
        _key(controller, "enter")
        assert "Brak terminów emisji" not in _frame(controller)
        assert len(sent) == reads + 1
