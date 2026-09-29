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
from decimal import Decimal
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
from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    AutomationOwner,
    EntryGroup,
    EpisodeBatch,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeRange,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    IdentityAssessment,
    IdentityVerdict,
    InspectedSourceGroup,
    ListedEpisode,
    ListedSpecial,
    RankedCandidate,
    ReleaseCatalog,
    ReleaseFacts,
    SeasonContext,
    StreamCandidate,
    TitleCandidate,
    TitleStatus,
    WorkspaceInspector,
)
from anishift.application.acquisition import catalog_releases
from anishift.application.cancellation import EventCancellationToken
from anishift.application.episode_commands import EpisodeResult
from anishift.application.episode_identity import REASONS
from anishift.application.episode_selection import AniZipMapping, episode_listing
from anishift.application.planning import ExecutionPlan
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.watch_state import WatchStateStore
from anishift.cli.interactive import anime as anime_module
from anishift.cli.interactive.anime import _ENTRY_ONLY_RELEASES, _REASON_TEXTS, AnimeController, _Screen
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
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.torrents.torrentio import TorrentioSource
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
        IdentityAssessment(verdict, "No selected file."),
        ReleaseFacts(resolution, False, False, None, False, ".mkv", True),
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
    worker: threading.Thread | None = controller._worker
    while worker is not None:
        worker.join(10)
        assert not worker.is_alive()
        if controller._worker is worker:
            break
        worker = controller._worker


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
def test_episode_flow_keeps_noncontiguous_selection_and_rereads_episodes_only_on_explicit_entry() -> None:
    catalog: _Catalog = _Catalog()
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("space", "down", "down", "enter", "text:d"):
        _key(controller, key)
    assert catalog.calls[-2:] == [("offer", 1), ("offer", 3)]
    assert "Pobierz (" not in _frame(controller)
    calls: list[tuple[str, int]] = catalog.calls.copy()
    for key in ("down", "text:i", "enter", "escape", "escape"):
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
    assert controller._positions[_Screen.ENTRIES] == 1
    assert catalog.calls == [("titles", 5), ("franchise", 2)]
    assert "Esc wróć" in _frame(controller)
    _key(controller, "escape")
    assert _at(controller) is _Screen.QUERY


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
    assert _at(controller) is _Screen.RESULTS
    assert catalog.filters == [None if movie else EpisodeRange(Decimal(1), Decimal(1))]
    assert [choice.release.info_hash for group in controller._groups for choice in group.choices] == ["1"]
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
    assert "Nie zamówiono" in frame
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
    assert _at(controller) is _Screen.RESULTS
    assert catalog.filters == [EpisodeRange(Decimal(1), Decimal(1))]
    assert not any(operation == "offer" for operation, _ in catalog.calls)
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
def test_unmapped_entry_without_any_episode_data_retains_the_nyaa_escape_route() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, kitsu_id=None, episodes=(), specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.RESULTS
    assert catalog.filters == [None]


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
    for key in ("space", "down", "down", "space", "text:d"):
        _key(controller, key)
    assert _at(controller) is _Screen.RESULTS
    assert {choice.episode for group in controller._groups for choice in group.choices} == {Decimal(1), Decimal(3)}
    assert catalog.calls[-1] == ("releases", 2 if related else 1)
    assert catalog.filters == [EpisodeRange(Decimal(1), Decimal(3))]
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES
    assert controller._episode_marks == {1, 3}
    for key in ("text:a", "text:a", "home", "text:d"):
        _key(controller, key)
    assert {choice.episode for group in controller._groups for choice in group.choices} == {Decimal(1)}
    assert len(catalog.filters) == 2


@pytest.mark.unit
def test_unmapped_sequel_looks_up_full_title_before_reading_absolute_episode_numbers() -> None:
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
    for key in ("paste:slime", "enter", "down", "enter", "text:d"):
        _key(controller, key)
    assert _at(controller) is _Screen.RESULTS
    assert catalog.calls[-2:] == [("titles", len(sequel.romaji)), ("releases", 2)]
    assert [choice.release.info_hash for group in controller._groups for choice in group.choices] == ["13"]
    assert controller._context == SeasonContext(2, 12, 12)
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES


@pytest.mark.unit
@pytest.mark.parametrize("unavailable", ["missing", "failed", "entry"])
def test_unmapped_preview_without_a_resolved_title_shows_a_notice(unavailable: str) -> None:
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
    _key(controller, "text:d")
    assert not catalog.filters
    if unavailable == "failed":
        assert _at(controller) is _Screen.PROBLEM
        assert controller._problem_return is _Screen.EPISODES
        assert _ENTRY_ONLY_RELEASES not in _frame(controller)
        _key(controller, "escape")
        assert _at(controller) is _Screen.EPISODES
    else:
        assert _at(controller) is _Screen.EPISODES
        assert _ENTRY_ONLY_RELEASES in _frame(controller)


@pytest.mark.unit
def test_unmapped_preview_then_groups_restores_the_search_phrase_episode_range() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime 4-6", "enter", "text:d", "escape", "text:g"):
        _key(controller, key)
    assert _at(controller) is _Screen.RESULTS
    assert catalog.filters == [EpisodeRange(Decimal(1), Decimal(1)), EpisodeRange(Decimal(4), Decimal(6))]


@pytest.mark.unit
def test_cancelled_unmapped_title_lookup_does_not_start_release_search() -> None:
    started: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    class Titles(_GroupCatalog):
        def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
            if self.calls:
                started.set()
                assert release.wait(10)
                return (replace(_title(), anilist_id=2),)
            return super().find_titles(query)

    catalog: Titles = Titles()
    catalog.listing = replace(catalog.listing, kitsu_id=None, specials=())
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter", "down", "enter"):
        _key(controller, key)
    controller.handle_key("text:d")
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
def test_skipped_entry_keeps_groups_and_subscription_route_reachable() -> None:
    catalog: _GroupCatalog = _GroupCatalog()
    catalog.view = Franchise(1, (_entry(),), (), True)
    catalog.listing = replace(catalog.listing, specials=(), kitsu_id=10)
    controller: AnimeController = _controller(catalog)
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert "G grupy" in _frame(controller)
    _key(controller, "text:s")
    assert controller._notice == "Subskrypcje: użyj G grupy"
    assert "Subskrypcje: użyj G grupy" in _frame(controller)
    _key(controller, "text:g")
    assert _at(controller) is _Screen.RESULTS
    assert catalog.calls[-1] == ("releases", 1)
    assert "O subskrybuj" in _frame(controller)
    _key(controller, "escape")
    assert _at(controller) is _Screen.EPISODES
    assert "G grupy" in _frame(controller)


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
    assert "G grupy" in _frame(controller)
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
    with set_app(app):
        for key in ("text:z", "text:1-3", "select-all", "interrupt"):
            _key(controller, key)
        assert app.clipboard.get_data().text == "1-3"
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
    assert "Zaznaczone (4): 1–3, 6" in _frame(controller)


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
    assert "Esc tytuły" in _frame(controller)
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
    assert controller._positions[_Screen.ENTRIES] == 1
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
def test_entry_releases_open_only_for_an_entry_found_by_the_search(moves: tuple[str, ...], searched: bool) -> None:
    catalog: _Catalog = _Catalog()
    catalog.view = Franchise(1, (_entry(1), _entry(7)), (), True)
    controller: AnimeController = _controller(catalog)
    for key in ("text:/", "text:slime", "enter", *moves, "text:g"):
        _key(controller, key)
    assert (catalog.calls[-1] == ("releases", 1)) is searched
    assert _at(controller) is (_Screen.PROBLEM if searched else _Screen.ENTRIES)
    assert ("G działa dla tytułów z wyników wyszukiwania" in _frame(controller)) is not searched


@pytest.mark.unit
def test_entry_group_shortcut_follows_available_search_results() -> None:
    controller: AnimeController = _controller(_Catalog())
    for key in ("paste:slime", "enter"):
        _key(controller, key)
    assert "G grupy" in _frame(controller)
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
    assert "Zaznaczone (4): 1–4" in _frame(controller)
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
        seeded = replace(seeded, facts=ReleaseFacts(1080, True, True, None, False, ".avi", False))
    catalog.offer_read = lambda key: _offer(key, (seeded, first))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:d", "text:i"):
        _key(controller, key)
    lines: list[str] = controller.render(width, 40).plain.splitlines()
    header: str = next(line for line in lines if "Wydanie" in line and "Seedy" in line)
    known: str = next(line for line in lines if "321" in line)
    unknown: str = next(line for line in lines if "[Group]" in line and "321" not in line)
    assert header.index("Seedy") == known.index("321")
    assert unknown[header.index("Seedy")] == "?"
    if unsupported:
        assert "PL · MultiSub" in known
        assert "1080p (.avi)" in known[header.index("Obraz") : header.index("Język")]
        assert "format nieobsługiwany (.avi)" in " ".join(" ".join(lines).split())
    assert all(Text(line).cell_len <= width for line in lines)


@pytest.mark.unit
@pytest.mark.parametrize("width", [50, 80, 120])
@pytest.mark.parametrize("verdict", list(IdentityVerdict))
def test_release_views_keep_decision_columns_and_put_size_in_details(width: int, verdict: IdentityVerdict) -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = _candidate(verdict)
    item = replace(
        item,
        facts=replace(item.facts, polish=True, multisub=True),
        stream=replace(item.stream, seeders=321, size_text="1.4 GB"),
    )
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    for key in ("text:d", "text:i"):
        _key(controller, key)
        lines: list[str] = controller.render(width, 24).plain.splitlines()
        header: str = next(line for line in lines if "Obraz" in line)
        assert "Seedy" in header
        assert "Język" in header
        assert "Rozm" not in header
        assert "Tożsamość" not in header
        if key == "text:d" and verdict is IdentityVerdict.MISMATCH:
            continue
        row: str = next(line for line in lines if "1080p" in line)
        assert "PL · MultiSub" in row
        assert "321" in row
        assert any("Rozmiar: 1.4 GB" in line for line in lines)
        assert "indeks:" not in " ".join(lines)
        assert "platforma: —" not in " ".join(lines)
        if verdict is IdentityVerdict.INSUFFICIENT:
            assert "niepewne" in row
        if verdict is IdentityVerdict.MISMATCH:
            assert "niezgodne" in row


@pytest.mark.unit
def test_offer_language_width_follows_the_longest_visible_suggestion() -> None:
    catalog: _Catalog = _Catalog()
    item: RankedCandidate = replace(_candidate(), stream=replace(_candidate().stream, seeders=321))
    catalog.offer_read = lambda key: _offer(key, (item,))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:d")
    lines: list[str] = controller.render(50, 24).plain.splitlines()
    compact: str = next(line for line in lines if "Obraz" in line)
    reason: str = next(line.strip() for line in lines if "zgodny:" in line)
    _key(controller, "text:i")
    assert reason in controller.render(50, 24).plain
    for key in ("escape", "escape"):
        _key(controller, key)
    item = replace(item, facts=replace(item.facts, polish=True, multisub=True))
    _key(controller, "text:d")
    lines = controller.render(50, 24).plain.splitlines()
    expanded: str = next(line for line in lines if "Obraz" in line)
    assert expanded.index("Obraz") < compact.index("Obraz")
    assert "PL · MultiSub" in "\n".join(lines)
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
    if "30" in typed:
        assert "Brak odcinka 30 w tym wpisie" in _frame(controller)


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
    for key in ("home", "down", "text:d"):
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
    _key(controller, "text:d")
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
    controller.handle_key("text:d")
    worker: threading.Thread | None = controller._worker
    try:
        assert entered.wait(5)
        assert "[Group]" in _frame(controller)
        assert "Szukam…" in _frame(controller)
        controller.cancel() if leave == "cancel" else controller.handle_key(leave)
        before: str = _frame(controller)
    finally:
        release.set()
        assert worker is not None
        worker.join(5)
    assert _frame(controller) == before
    assert catalog.calls[-2:] == [("offer", 1), ("offer", 2)]
    assert 2 not in controller._offers


@pytest.mark.unit
@pytest.mark.parametrize("verdict", list(IdentityVerdict))
def test_offer_verdict_labels_uncertainty_and_empty_suggestion_are_explicit(verdict: IdentityVerdict) -> None:
    catalog: _Catalog = _Catalog()
    catalog.offer_read = lambda key: _offer(key, (_candidate(verdict),))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:d")
    frame: str = _frame(controller)
    assert ("niepewne ·" in frame) is (verdict is IdentityVerdict.INSUFFICIENT)
    assert ("Brak pasującego wydania E1" in frame) is (verdict is IdentityVerdict.MISMATCH)
    reason: str = "niepewny: Brak wskazanego pliku."
    if verdict is IdentityVerdict.INSUFFICIENT:
        assert reason in frame
    _key(controller, "text:i")
    if verdict is IdentityVerdict.INSUFFICIENT:
        assert reason in _frame(controller)
    assert "Brak wskazanego pliku." in _frame(controller)
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
    _key(controller, "text:d")
    _key(controller, "text:i")
    assert [item.facts.resolution for item in controller._release_candidates] == (
        [2160, None] if high_verdict is IdentityVerdict.MATCH else [2160, 720, 480, 1440, None]
    )


@pytest.mark.unit
def test_unsupported_high_resolution_match_does_not_hide_a_supported_lower_match() -> None:
    catalog: _Catalog = _Catalog()
    avi: RankedCandidate = replace(_candidate(), facts=ReleaseFacts(1080, False, False, None, False, ".avi", False))
    catalog.offer_read = lambda key: _offer(key, (avi, _candidate(resolution=720)))
    controller: AnimeController = _controller(catalog)
    _open(controller)
    _key(controller, "text:d")
    _key(controller, "text:i")
    assert [item.facts.resolution for item in controller._release_candidates] == [1080, 720]


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
    assert "\u276f [ ]  2" in frame
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
    assert "Anime \u203a Slime" in entries
    assert all(label in entries for label in ("Rok", "Tytuł", "Typ", "Status"))
    _key(controller, "enter")
    episodes: list[str] = controller.render(width, 40).plain.splitlines()
    header: str = next(line for line in episodes if "Stan" in line)
    episode: str = next(line for line in episodes if "Nie zamówiono" in line)
    assert header.index("Stan") == episode.index("Nie zamówiono")
    _key(controller, "text:d")
    offers: list[str] = controller.render(width, 40).plain.splitlines()
    assert any("Plik:" in line for line in offers)
    header = next(line for line in offers if "Sugerowane" in line)
    offered: str = next(line for line in offers if "E1" in line and "1080p" in line and "Powód" not in line)
    assert header.index("Obraz") == offered.index("1080p")
    _key(controller, "text:i")
    candidates: list[str] = controller.render(width, 40).plain.splitlines()
    assert candidates[0] == ""
    assert "Inne wydania \u203a Slime \u203a E1" in candidates[1]
    header = next(line for line in candidates if "Wydanie" in line and "Seedy" in line)
    image_column: int = Text(header[: header.index("Obraz")]).cell_len
    release_rows: list[str] = [line for line in candidates if "1080p" in line]
    assert len(release_rows) == 2
    assert all(Text(line[: line.index("1080p")]).cell_len == image_column for line in release_rows)
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
    _key(controller, "text:d")
    _key(controller, "text:i")
    frame: str = controller.render(50, 24).plain
    normalized: str = " ".join(frame.split())
    assert _REASON_TEXTS[reason] not in normalized
    assert f"Plik: {filename} · Rozmiar: ?" in normalized
    _key(controller, "text:?")
    assert _REASON_TEXTS[reason] in " ".join(controller.render(50, 24).plain.split())
    _key(controller, "escape")
    assert _at(controller) is _Screen.CANDIDATES
    assert all(Text(line).cell_len <= 50 for line in frame.splitlines())
    assert "Esc podgląd" in frame


class _Owner(_Catalog):
    def __init__(self) -> None:
        super().__init__()
        self.release: threading.Event = threading.Event()
        self.batches: list[tuple[tuple[EpisodeKey, ...], str]] = []

    def episode_states(self, anilist_id: int, numbers: Sequence[int]) -> tuple[EpisodeStatus, ...]:
        return tuple(
            EpisodeStatus(EpisodeKey(anilist_id, number), "ordered" if number == 2 else "not_ordered")
            for number in numbers
        )

    def episode_download(self, keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch:
        self.batches.append((tuple(keys), command_id))
        if len(self.batches) == 1:
            assert self.release.wait(10)
            return EpisodeBatch(command_id, "fixture", tuple(keys), "accepted")
        results: tuple[EpisodeResult, ...] = (
            EpisodeResult(keys[0], "admitted", "a1", "o1"),
            EpisodeResult(keys[1], "no_suggestion"),
        )
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
        ("not_ordered", "Nie zamówiono"),
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

    assert re.search(rf"1\s+Episode 1\s+.*{re.escape(label)}", _frame(controller))
    assert ("Nie zamówiono" in _frame(controller)) is (state == "not_ordered")


@pytest.mark.unit
def test_download_orders_marked_episodes_through_the_owner_and_stays_on_the_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(anime_module, "_BATCH_POLL_S", 0.0)
    owner: _Owner = _Owner()
    controller: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    _open(controller)
    assert re.search(r"2\s+Episode 2\s+.*Zlecono", _frame(controller))
    for key in ("space", "down", "down", "space", "text:d"):
        _key(controller, key)
    assert _at(controller) is _Screen.EPISODES
    assert "szukam" in _frame(controller)
    assert "Zaznaczone" not in _frame(controller)
    owner.release.set()
    deadline: float = time.monotonic() + 10
    while controller._sending and time.monotonic() < deadline:
        time.sleep(0.01)
    frame: str = _frame(controller)
    assert _at(controller) is _Screen.EPISODES
    assert "Zlecono E1" in frame
    assert re.search(r"1\s+Episode 1\s+.*Zlecono", frame)
    assert re.search(r"3\s+Episode 3\s+.*Brak wydania", frame)
    assert [keys for keys, _ in owner.batches] == [(EpisodeKey(1, 1), EpisodeKey(1, 3))] * 2
    assert len({command_id for _, command_id in owner.batches}) == 1
    assert not any(operation == "offer" for operation, _ in owner.calls)
    _key(controller, "text:i")
    assert _at(controller) is _Screen.OFFER


@pytest.mark.unit
def test_episode_footer_wraps_only_between_complete_shortcuts() -> None:
    controller: AnimeController = _controller(_Catalog())
    _open(controller)
    lines: list[str] = controller.render(50, 24).plain.splitlines()
    assert all(
        any(hint in line for line in lines)
        for hint in ("Space zaznacz", "A wszystkie/żadne", "Z zakres", "D pobierz", "I wybierz wydanie", "Esc wpisy")
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
        _key(controller, "text:d")
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
    _key(controller, "text:d")
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
    session: ResidentSession = cast("ResidentSession", SimpleNamespace(command=lambda *args: {}, library=lambda: ()))
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
def _running_panel(
    tmp_path: Path,
    scenario: list[str],
    sent: list[str],
    now: list[float],
    *,
    remote: bool,
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
        for key in ("down", "down", "down", "text:d"):
            _key(controller, key)
        assert controller._offers[4].suggestion is not None
        offer: EpisodeOffer = controller._offers[4]
        assert offer.suggestion is not None
        assert offer.candidates[offer.suggestion].identity.verdict is IdentityVerdict.MATCH
        assert "Szukam…" not in _frame(controller)
        _key(controller, "text:i")
        assert "zgodny" in _frame(controller)
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
        assert "Tylko podgląd wydań" in _frame(controller)
        assert controller._listing is not None
        assert len(controller._listing.episodes) == 1
        _key(controller, "text:d")
        assert controller._offers[1].key == EpisodeKey(139498, 1)
        assert "Brak wydań w źródle" in _frame(controller)
        assert "torrentio.strem.fun/stream/movie/kitsu:99.json" in sent
        assert not any("/stream/series/" in url for url in sent)


@pytest.mark.integration
@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("provider", ["anilist", "anizip", "torrentio"])
def test_http_429_reaches_panel_with_source_deadline_and_no_fallback(
    tmp_path: Path,
    remote: bool,
    provider: str,
) -> None:
    sent: list[str] = []
    now: list[float] = [datetime(2026, 9, 29, tzinfo=UTC).timestamp()]
    with _running_panel(tmp_path, [provider], sent, now, remote=remote) as (controller, panel, _):
        for key in ("text:/", "text:slime", "enter", "enter", "enter", "down", "down", "down", "text:d"):
            _key(controller, key)
            if controller._screen is _Screen.PROBLEM:
                break
        if panel is not None:
            panel._receive(panel._parent, {"event": "state_changed", "payload": panel._parent.command("status")})
        assert controller._screen is _Screen.PROBLEM
        expected: str = {
            "anilist": "AniList nie odpowiada",
            "anizip": "Lista odcinków niedostępna",
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

            def broken(key: EpisodeKey) -> EpisodeOffer:
                raise ValueError("private-payload")

            monkeypatch.setattr(acquisition, "offer", broken)
            _key(controller, "text:d")
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
        monkeypatch.setattr(acquisition, "offer", lambda key: _offer(key, (item,)))
        _key(controller, "text:d")
        assert "Odpowiedź rezydenta jest za duża" in _frame(controller)
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
