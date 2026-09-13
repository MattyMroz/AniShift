from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from rich.text import Text

from anishift.application import (
    AppService,
    CatalogOrder,
    DownloadReceipt,
    EpisodeRange,
    EpisodeReading,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    SeriesGroup,
    TitleCandidate,
    TitleCatalogError,
    TitleStatus,
)
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.anime import AnimeController, AnimeResult, _Screen
from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.services.torrents.types import Release, ReleaseName


class _Renderer:
    def __init__(
        self,
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> None:
        self.frame_provider: Callable[[int, int], Text] = frame_provider
        self.key_handler: Callable[[str], None] = key_handler
        self.idle_handler: Callable[[], None] | None = idle_handler
        self.scroll_handler: Callable[[int], None] | None = scroll_handler
        self.native_mascot_size: tuple[int, int] | None = None
        self.exits: int = 0

    def run(self) -> None:
        return

    def invalidate(self) -> None:
        return

    def exit(self) -> None:
        self.exits += 1


def _reading(episode: str, *, absolute: str | None = None, other_season: bool = False) -> EpisodeReading:
    return EpisodeReading(
        Decimal(episode),
        absolute=None if absolute is None else Decimal(absolute),
        other_season=other_season,
    )


def _choice(
    episode: str | None,
    *,
    batch: bool = False,
    seeders: int = 159,
    series: str = "Oshi no Ko",
    reading: EpisodeReading | None = None,
) -> ReleaseChoice:
    release: Release = Release(
        title=f"[SubsPlease] {series}",
        torrent_url=f"https://nyaa.si/download/{episode or 'batch'}.torrent",
        info_hash=f"hash-{series}-{episode or 'batch'}",
        seeders=seeders,
        size_text="227.4 MiB",
        published=None,
    )
    name: ReleaseName = ReleaseName(
        group="SubsPlease",
        series=series,
        episode=None if episode is None else Decimal(episode),
        season=None,
        resolution=1080,
        batch=batch,
        version=None,
    )
    return ReleaseChoice(release, name, reading)


def _group(
    choices: Sequence[ReleaseChoice],
    *,
    series: str = "Oshi no Ko",
    group: str = "SubsPlease",
    language: str | None = None,
    newest: datetime | None = None,
) -> SeriesGroup:
    return SeriesGroup(series, group, tuple(choices), language, newest)


def _catalog(
    choices: Sequence[ReleaseChoice],
    hidden: int = 0,
    filtered: int = 0,
    excluded: int = 0,
) -> ReleaseCatalog:
    return ReleaseCatalog((_group(choices),), hidden, filtered, excluded)


def _title(
    romaji: str = "Oshi no Ko",
    *,
    english: str | None = None,
    year: int | None = 2023,
    episodes: int | None = 11,
    status: TitleStatus = TitleStatus.FINISHED,
) -> TitleCandidate:
    return TitleCandidate(
        anilist_id=1,
        romaji=romaji,
        english=english,
        native=None,
        synonyms=(),
        year=year,
        season=None,
        format="TV",
        episodes=episodes,
        status=status,
        prequel_ids=(),
    )


def _season(index: int = 1, offset: int = 0, episodes: int | None = 11) -> SeasonContext:
    return SeasonContext(index=index, offset=offset, episodes=episodes)


def _service(
    search: Callable[[str], ReleaseCatalog] | None = None,
    download: Callable[..., DownloadReceipt] | None = None,
    subscriptions: SimpleNamespace | None = None,
    extra: dict[str, object] | None = None,
) -> AppService:
    acquisition: SimpleNamespace | None = None
    if search is not None or download is not None or extra is not None:
        fields: dict[str, object] = {
            "search": search,
            "download": download,
            "find_titles": lambda text: (),
            "season_context": lambda candidate: _season(),
            "search_title": lambda candidate, **options: _catalog(()),
        }
        fields.update(extra or {})
        acquisition = SimpleNamespace(**fields)
    return cast("AppService", SimpleNamespace(acquisition=acquisition, subscriptions=subscriptions))


def _subscription(episode: str = "9") -> SimpleNamespace:
    return SimpleNamespace(series="Oshi no Ko", group="SubsPlease", next_episode=Decimal(episode))


def _outcome(downloaded: int = 0, problem: str = "") -> SimpleNamespace:
    return SimpleNamespace(downloaded=downloaded, problem=problem)


def _controller(service: AppService) -> AnimeController:
    return AnimeController(service, lambda: None)


def _type(controller: AnimeController, value: str) -> None:
    for character in value:
        controller.handle_key("space" if character == " " else f"text:{character}")


def _settle(controller: AnimeController) -> None:
    worker: threading.Thread | None = controller._worker
    if worker is None:
        return
    worker.join(timeout=5)
    assert not worker.is_alive()


def _screen(controller: AnimeController) -> _Screen:
    return controller._screen


def _mode(application: interactive_app._InteractiveApplication) -> interactive_app._ViewMode:
    return application._mode


def _frame(controller: AnimeController, columns: int = 120, rows: int = 30) -> str:
    return controller.render(columns, rows).plain


@pytest.mark.parametrize("query", ["", "frieren", "a longer anime title with a release group"])
def test_search_hint_stays_centered_independently_of_input_width(query: str) -> None:
    controller: AnimeController = _controller(_service(extra={}))
    _type(controller, query)
    frame: str = _frame(controller, columns=80)
    hint: str = next(line for line in frame.splitlines() if "Enter szukaj" in line)
    assert len(hint) - len(hint.lstrip()) == (80 - Text(hint.strip()).cell_len) // 2
    assert frame.splitlines()[-1] == hint


def test_search_edits_selected_words_before_submitting_the_final_query() -> None:
    searched: list[str] = []

    def find_titles(text: str) -> tuple[TitleCandidate, ...]:
        searched.append(text)
        return ()

    controller: AnimeController = _controller(
        _service(search=lambda text: _catalog(()), extra={"find_titles": find_titles})
    )
    _type(controller, "old title")
    controller.handle_key("ctrl-shift-left")
    controller.handle_key("text:anime")
    assert controller._query == "old anime"
    controller.handle_key("home")
    controller.handle_key("ctrl-delete")
    controller.handle_key("delete")
    controller.handle_key("enter")
    _settle(controller)
    assert searched == ["anime"]


def _receipt(directory: str = "Oshi no Ko") -> Callable[..., DownloadReceipt]:
    def download(choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        del directory_name
        return DownloadReceipt(len(choices), Path("workspace") / directory)

    return download


def _chosen(controller: AnimeController, phrase: str = "oshi no ko") -> None:
    _type(controller, phrase)
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)


def _application(monkeypatch: pytest.MonkeyPatch, service: AppService) -> interactive_app._InteractiveApplication:
    made: list[_Renderer] = []

    def factory(
        frame_provider: Callable[[int, int], Text],
        key_handler: Callable[[str], None],
        idle_handler: Callable[[], None] | None = None,
        scroll_handler: Callable[[int], None] | None = None,
    ) -> _Renderer:
        renderer: _Renderer = _Renderer(frame_provider, key_handler, idle_handler, scroll_handler)
        made.append(renderer)
        return renderer

    monkeypatch.setattr(interactive_app, "TerminalRenderer", factory)
    return interactive_app._InteractiveApplication(service)


def test_typed_characters_and_backspace_edit_the_searched_title() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog(())))

    _type(controller, "oshi no koo")
    controller.handle_key("backspace")

    assert controller._query == "oshi no ko"
    assert "> oshi no ko▌" in _frame(controller)


def test_enter_on_a_blank_title_starts_no_search() -> None:
    searched: list[str] = []

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog(())

    controller: AnimeController = _controller(_service(search=search))

    _type(controller, "   ")
    controller.handle_key("enter")

    assert searched == []
    assert _screen(controller) is _Screen.QUERY
    assert controller._worker is None


def test_a_search_lists_the_group_header_episode_rows_and_the_hidden_count() -> None:
    searched: list[str] = []

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog((_choice("11"), _choice("10"), _choice(None, batch=True)), hidden=4)

    controller: AnimeController = _controller(_service(search=search))
    _type(controller, "oshi no ko")
    controller.handle_key("enter")
    _settle(controller)
    listed: str = _frame(controller)

    assert searched == ["oshi no ko"]
    assert _screen(controller) is _Screen.RESULTS
    assert "[SubsPlease] Oshi no Ko" in listed
    assert "odc. 11  1080p  159 seedów  227.4 MiB" in listed
    assert "paczka  1080p" in listed
    assert "ukryte poniżej 1080p: 4" in listed


def test_an_empty_catalog_reports_the_missing_quality_and_enter_returns_to_the_title() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((), hidden=7)))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    empty: str = _frame(controller)

    assert "Brak wydań w 1080p+ dla tego tytułu" in empty
    assert "ukryte poniżej 1080p: 7" in empty

    controller.handle_key("enter")

    assert _screen(controller) is _Screen.QUERY


def test_space_marks_a_release_and_the_footer_counts_it() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"), _choice("10")))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)

    assert "zaznaczone: 0" in _frame(controller)

    controller.handle_key("space")
    controller.handle_key("down")
    controller.handle_key("space")

    assert "zaznaczone: 2" in _frame(controller)

    controller.handle_key("space")

    assert "zaznaczone: 1" in _frame(controller)


def test_navigation_skips_the_group_header_rows() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"), _choice("10")))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    first: int = controller._selected

    controller.handle_key("down")
    controller.handle_key("down")

    assert controller._rows[first].choice is not None
    assert controller._selected == first
    assert all(controller._rows[index].choice is not None for index in controller._choices)


def test_enter_sends_exactly_the_marked_releases_and_names_the_directory() -> None:
    sent: list[tuple[ReleaseChoice, ...]] = []
    wanted: ReleaseChoice = _choice("10")

    def download(choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        del directory_name
        sent.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("workspace") / "Oshi no Ko")

    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"), wanted)), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("down")
    controller.handle_key("space")
    controller.handle_key("enter")
    _settle(controller)
    finished: str = _frame(controller)

    assert sent == [(wanted,)]
    assert _screen(controller) is _Screen.DONE
    assert "Wysłano 1 do qBittorrenta → Oshi no Ko" in finished
    assert "workspace" not in finished


def test_enter_without_a_mark_sends_the_highlighted_release() -> None:
    sent: list[tuple[ReleaseChoice, ...]] = []
    newest: ReleaseChoice = _choice("11")

    def download(choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        del directory_name
        sent.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("workspace") / "Oshi no Ko")

    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((newest, _choice("10"))), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)

    assert sent == [(newest,)]
    assert "Wysłano 1 do qBittorrenta" in _frame(controller)


def test_a_finished_download_returns_home_on_any_key() -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), download=_receipt())
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)

    assert controller.handle_key("any") is AnimeResult.HOME


def test_a_failed_search_states_a_known_error_code_in_polish() -> None:
    def search(query: str) -> ReleaseCatalog:
        del query
        raise AniShiftError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_SOURCE_FAILED,
                message="Nyaa could not be reached",
                suggestion="Check the connection and try again",
            )
        )

    controller: AnimeController = _controller(_service(search=search))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    reported: str = _frame(controller)

    assert _screen(controller) is _Screen.PROBLEM
    assert "Nyaa nie odpowiada" in reported
    assert "Sprawdź połączenie i spróbuj ponownie" in reported
    assert "could not be reached" not in reported
    assert "Traceback" not in reported

    assert controller.handle_key("enter") is AnimeResult.CONTINUE
    assert _screen(controller) is _Screen.QUERY


def test_a_refused_subscription_says_the_release_cannot_be_watched() -> None:
    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        del query, choice, options
        raise ValueError("release carries no episode number")

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("9"),)),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=lambda subscription: _outcome()),
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:o")
    _settle(controller)
    reported: str = _frame(controller)

    assert _screen(controller) is _Screen.PROBLEM
    assert "To wydanie nie nadaje się do obserwowania" in reported
    assert "carries no episode number" not in reported


def test_a_pasted_title_drops_its_control_characters() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog(())))

    controller.handle_key("paste:oshi no ko\r\n")

    assert controller._query == "oshi no ko"
    assert "> oshi no ko▌" in _frame(controller)


def test_an_empty_result_after_an_episode_filter_names_the_filter_and_offers_f() -> None:
    asked: list[object] = []

    def search_title(chosen: TitleCandidate, **options: object) -> ReleaseCatalog:
        del chosen
        asked.append(options["episodes"])
        if options["episodes"] is None:
            return _catalog((_choice("11"),))
        return ReleaseCatalog((), 0, 17)

    controller: AnimeController = _controller(
        _service(extra={"find_titles": lambda text: (_title(),), "search_title": search_title})
    )
    _chosen(controller, "frieren 99")
    empty: str = _frame(controller)

    assert "Brak odc. 99 w 1080p+ dla tego tytułu" in empty
    assert "poza filtrem: 17" in empty
    assert "F pokaż wszystkie" in empty
    assert "Esc wróć" in empty
    assert "ukryte poniżej" not in empty

    controller.handle_key("text:f")
    _settle(controller)

    assert asked[1] is None
    assert "odc. 11" in _frame(controller)


def test_an_empty_result_without_a_filter_keeps_the_quality_sentence_and_both_counters() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: ReleaseCatalog((), 7, 0, 4)))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    empty: str = _frame(controller)

    assert "Brak wydań w 1080p+ dla tego tytułu" in empty
    assert "ukryte poniżej 1080p: 7" in empty
    assert "bez napisów/dubbing: 4" in empty


def test_the_results_footer_counts_the_quality_and_the_language_reasons_apart() -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: ReleaseCatalog((_group((_choice("11"),)),), 4, 0, 6))
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    listed: str = _frame(controller)

    assert "ukryte poniżej 1080p: 4" in listed
    assert "bez napisów/dubbing: 6" in listed


def test_s_keeps_a_group_of_another_season_below_the_chosen_one() -> None:
    foreign: SeriesGroup = _group(
        (_choice("3", seeders=900, series="Foreign", reading=_reading("3", other_season=True)),),
        series="Foreign",
        group="Erai-raws",
    )
    wanted: SeriesGroup = _group(
        (_choice("9", seeders=5, series="Wanted"),),
        series="Wanted",
        newest=datetime(2026, 9, 5, tzinfo=UTC),
    )
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(),),
                "search_title": lambda chosen, **options: ReleaseCatalog((wanted, foreign), 0),
            }
        )
    )
    _chosen(controller)
    controller.handle_key("text:s")
    seeded: str = _frame(controller)
    controller.handle_key("text:s")
    newest: str = _frame(controller)

    assert seeded.index("Wanted") < seeded.index("Foreign")
    assert newest.index("Wanted") < newest.index("Foreign")


def test_the_fallback_results_name_the_order_they_arrived_in() -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), extra={"find_titles": lambda text: ()})
    )
    _type(controller, "oshi no ko")
    controller.handle_key("enter")
    _settle(controller)

    assert "S najnowsze" in _frame(controller)


def test_a_broken_season_lookup_notes_that_the_numbering_is_missing() -> None:
    def season_context(candidate: TitleCandidate) -> SeasonContext:
        del candidate
        raise TitleCatalogError(
            context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="AniList nie odpowiada")
        )

    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(),),
                "season_context": season_context,
                "search_title": lambda chosen, **options: _catalog((_choice("11"),)),
            }
        )
    )
    _chosen(controller)
    listed: str = _frame(controller)

    assert _screen(controller) is _Screen.RESULTS
    assert "numeracja sezonu niedostępna" in listed


def test_escape_from_the_results_returns_to_the_title_list_and_then_to_the_query() -> None:
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(), _title("Oshi no Ko II")),
                "search_title": lambda chosen, **options: _catalog((_choice("11"),)),
            }
        )
    )
    _chosen(controller)

    controller.handle_key("escape")

    assert _screen(controller) is _Screen.TITLES

    controller.handle_key("escape")

    assert _screen(controller) is _Screen.QUERY


def test_escape_from_the_fallback_results_returns_to_the_query() -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), extra={"find_titles": lambda text: ()})
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)

    controller.handle_key("escape")

    assert _screen(controller) is _Screen.QUERY


def test_a_failed_download_returns_to_the_results_and_escape_leaves_home() -> None:
    def download(choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        del choices, directory_name
        raise AniShiftError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                message="qBittorrent Web UI is not reachable",
                suggestion="Enable the Web UI",
            )
        )

    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)
    reported: str = _frame(controller)

    assert "qBittorrent nie odpowiada" in reported
    assert "Uruchom qBittorrenta z włączonym Web UI" in reported
    assert "not reachable" not in reported

    controller.handle_key("enter")

    assert _screen(controller) is _Screen.RESULTS
    assert controller.handle_key("escape") is AnimeResult.CONTINUE


def test_escape_during_the_search_discards_a_late_result() -> None:
    release: threading.Event = threading.Event()

    def search(query: str) -> ReleaseCatalog:
        del query
        assert release.wait(timeout=5)
        return _catalog((_choice("11"),))

    controller: AnimeController = _controller(_service(search=search))
    _type(controller, "oshi")
    controller.handle_key("enter")
    worker: threading.Thread | None = controller._worker

    assert _screen(controller) is _Screen.BUSY
    assert "Szukam tytułu…" in _frame(controller)

    controller.handle_key("escape")
    release.set()
    assert worker is not None
    worker.join(timeout=5)

    assert _screen(controller) is _Screen.QUERY
    assert controller._rows == ()
    assert "odc. 11" not in _frame(controller)


def test_a_session_without_the_acquisition_boundary_reports_it_and_escape_returns_home() -> None:
    controller: AnimeController = _controller(_service())

    assert _screen(controller) is _Screen.PROBLEM
    assert "Pobieranie jest niedostępne w tej sesji" in _frame(controller)
    assert controller.handle_key("escape") is AnimeResult.HOME


def test_o_on_a_numbered_episode_subscribes_to_it_and_reports_the_download_count() -> None:
    subscribed: list[tuple[str, ReleaseChoice]] = []
    checked: list[object] = []
    wanted: ReleaseChoice = _choice("9")
    created: SimpleNamespace = _subscription()

    def subscribe(
        query: str,
        choice: ReleaseChoice,
        *,
        directory_name: str | None = None,
        context: SeasonContext | None = None,
    ) -> SimpleNamespace:
        del directory_name, context
        subscribed.append((query, choice))
        return created

    def check(subscription: object) -> SimpleNamespace:
        checked.append(subscription)
        return _outcome(downloaded=3)

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("11"), wanted)),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=check),
        )
    )
    _type(controller, "oshi no ko")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("down")
    controller.handle_key("text:o")
    _settle(controller)
    watched: str = _frame(controller)

    assert subscribed == [("oshi no ko", wanted)]
    assert checked == [created]
    assert _screen(controller) is _Screen.DONE
    assert "Obserwuję [SubsPlease] Oshi no Ko od odc. 9 · pobrano 3 · sprawdzam co godzinę" in watched
    assert controller.handle_key("any") is AnimeResult.HOME


def test_o_on_a_batch_reports_that_only_a_numbered_episode_can_be_watched() -> None:
    calls: list[str] = []

    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        calls.append("subscribe")
        return _subscription()

    def check(subscription: object) -> SimpleNamespace:
        calls.append("check")
        return _outcome()

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("11"), _choice(None, batch=True))),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=check),
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("down")
    controller.handle_key("text:o")
    noticed: str = _frame(controller)

    assert calls == []
    assert controller._worker is None
    assert _screen(controller) is _Screen.RESULTS
    assert "Obserwuj działa tylko na numerowanym odcinku" in noticed

    controller.handle_key("up")

    assert "Obserwuj działa tylko na numerowanym odcinku" not in _frame(controller)


def test_o_without_the_subscriptions_boundary_reports_it_and_enter_returns_to_the_results() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:O")
    _settle(controller)

    assert _screen(controller) is _Screen.PROBLEM
    assert "Subskrypcje są niedostępne w tej sesji" in _frame(controller)

    controller.handle_key("enter")

    assert _screen(controller) is _Screen.RESULTS


def test_a_failed_first_check_replaces_the_download_count_with_the_problem() -> None:
    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        return _subscription()

    def check(subscription: object) -> SimpleNamespace:
        return _outcome(problem="Nyaa nie odpowiedziało")

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("9"),)),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=check),
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:o")
    _settle(controller)
    watched: str = _frame(controller)

    assert _screen(controller) is _Screen.DONE
    assert (
        "Obserwuję [SubsPlease] Oshi no Ko od odc. 9 · sprawdzenie nie powiodło się: "
        "Nyaa nie odpowiedziało · sprawdzam co godzinę"
    ) in watched
    assert "pobrano" not in watched


def test_a_failed_subscribe_shows_its_suggestion_and_enter_returns_to_the_results() -> None:
    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        raise AniShiftError(
            context=ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message="Nie mogę zapisać obserwacji",
                suggestion="Sprawdź katalog config",
            )
        )

    def check(subscription: object) -> SimpleNamespace:
        return _outcome()

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("9"),)),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=check),
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:o")
    _settle(controller)
    reported: str = _frame(controller)

    assert _screen(controller) is _Screen.PROBLEM
    assert "Nie mogę zapisać obserwacji" in reported
    assert "Sprawdź katalog config" in reported
    assert "Traceback" not in reported

    controller.handle_key("enter")

    assert _screen(controller) is _Screen.RESULTS


def test_escape_during_the_subscription_discards_a_late_result() -> None:
    release: threading.Event = threading.Event()

    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        assert release.wait(timeout=5)
        return _subscription()

    def check(subscription: object) -> SimpleNamespace:
        return _outcome(downloaded=3)

    controller: AnimeController = _controller(
        _service(
            search=lambda query: _catalog((_choice("9"),)),
            subscriptions=SimpleNamespace(subscribe=subscribe, check=check),
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:o")
    worker: threading.Thread | None = controller._worker

    assert _screen(controller) is _Screen.BUSY
    assert "Zapisuję obserwację…" in _frame(controller)

    controller.handle_key("escape")
    release.set()
    assert worker is not None
    worker.join(timeout=5)

    assert _screen(controller) is _Screen.QUERY
    assert "Obserwuję" not in _frame(controller)


def test_the_results_footer_offers_the_watch_key() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)

    assert "O obserwuj" in _frame(controller)


@pytest.mark.parametrize("size", [(120, 30), (80, 24), (60, 10), (40, 6)])
def test_the_results_fit_inside_every_terminal_height(size: tuple[int, int]) -> None:
    columns, rows = size
    catalog: ReleaseCatalog = _catalog(tuple(_choice(str(number)) for number in range(24, 0, -1)), hidden=3)
    controller: AnimeController = _controller(_service(search=lambda query: catalog))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    lines: list[str] = _frame(controller, columns, rows).split("\n")

    assert len(lines) <= rows
    assert any("\u276f" in line for line in lines)


def test_enter_lists_every_title_candidate_with_its_year_format_and_status() -> None:
    asked: list[str] = []

    def find_titles(text: str) -> tuple[TitleCandidate, ...]:
        asked.append(text)
        return (
            _title("Solo Leveling", english="Solo Leveling", year=2024, episodes=12),
            _title(
                "Ore dake Level Up na Ken Season 2",
                english="Solo Leveling Season 2",
                year=2025,
                episodes=13,
                status=TitleStatus.RELEASING,
            ),
        )

    controller: AnimeController = _controller(_service(extra={"find_titles": find_titles}))
    _type(controller, "solo leveling 1")
    controller.handle_key("enter")
    _settle(controller)
    listed: str = _frame(controller)

    assert asked == ["solo leveling"]
    assert _screen(controller) is _Screen.TITLES
    assert "Solo Leveling · 2024 · TV · 12 odc. · zakończone" in listed
    assert "Ore dake Level Up na Ken Season 2 · 2025 · TV · 13 odc. · w emisji · Solo Leveling Season 2" in listed
    assert "Enter wybierz · Esc wróć" in listed

    controller.handle_key("escape")

    assert _screen(controller) is _Screen.QUERY


def test_choosing_a_candidate_searches_its_releases_with_the_parsed_filter_and_the_season_context() -> None:
    calls: list[dict[str, object]] = []
    candidate: TitleCandidate = _title("Ore dake Level Up na Ken", english="Solo Leveling")
    context: SeasonContext = _season(index=2, offset=12, episodes=13)

    def search_title(chosen: TitleCandidate, **options: object) -> ReleaseCatalog:
        calls.append({"candidate": chosen, **options})
        return _catalog((_choice("1"),))

    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (candidate,),
                "season_context": lambda chosen: context,
                "search_title": search_title,
            }
        )
    )
    _chosen(controller, "solo leveling 1")
    episodes: EpisodeRange = cast("EpisodeRange", calls[0]["episodes"])

    assert _screen(controller) is _Screen.RESULTS
    assert calls[0]["candidate"] is candidate
    assert calls[0]["context"] is context
    assert calls[0]["order"] is CatalogOrder.NEWEST
    assert (episodes.first, episodes.last) == (Decimal(1), Decimal(1))


def test_a_broken_title_catalog_falls_back_to_the_typed_phrase() -> None:
    searched: list[str] = []

    def find_titles(text: str) -> tuple[TitleCandidate, ...]:
        del text
        raise TitleCatalogError(
            context=ErrorContext(code=ErrorCode.TITLE_CATALOG_FAILED, message="AniList nie odpowiada")
        )

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog((_choice("11"),))

    controller: AnimeController = _controller(_service(search=search, extra={"find_titles": find_titles}))
    _type(controller, "oshi no ko 1")
    controller.handle_key("enter")
    _settle(controller)
    listed: str = _frame(controller)

    assert searched == ["oshi no ko 1"]
    assert _screen(controller) is _Screen.RESULTS
    assert "AniList nie odpowiada, wyniki dla hasła" in listed
    assert "filtr:" not in listed


def test_an_unknown_title_falls_back_to_the_typed_phrase() -> None:
    searched: list[str] = []

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog((_choice("11"),))

    controller: AnimeController = _controller(_service(search=search, extra={"find_titles": lambda text: ()}))
    _type(controller, "oshi no ko")
    controller.handle_key("enter")
    _settle(controller)
    listed: str = _frame(controller)

    assert searched == ["oshi no ko"]
    assert "Brak tytułu w AniList, wyniki dla hasła" in listed


def test_the_results_name_the_chosen_title_and_carry_the_group_language() -> None:
    candidate: TitleCandidate = _title(
        "Ore dake Level Up na Ken",
        english="Solo Leveling",
        year=2024,
        episodes=13,
        status=TitleStatus.RELEASING,
    )
    group: SeriesGroup = _group(
        (
            _choice("1", series="Solo Leveling", reading=_reading("1", absolute="13")),
            _choice("3", series="Solo Leveling", reading=_reading("3", other_season=True)),
        ),
        series="Solo Leveling",
        language="en",
        newest=datetime(2026, 9, 4, tzinfo=UTC),
    )
    multi: SeriesGroup = _group((_choice("1", series="Solo"),), series="Solo", group="MTBB", language="multi")
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (candidate,),
                "search_title": lambda chosen, **options: ReleaseCatalog((group, multi), 2),
            }
        )
    )
    _chosen(controller, "solo leveling")
    listed: str = _frame(controller)

    assert "Ore dake Level Up na Ken · Solo Leveling · w emisji · 13 odc." in listed
    assert "[SubsPlease · EN] Solo Leveling  najnowsze: 04.09.2026" in listed
    assert "[MTBB · MULTI] Solo" in listed
    assert "odc. 1 (13)" in listed
    assert "odc. 3 · sezon?" in listed


def test_a_marks_every_numbered_episode_of_the_highlighted_group() -> None:
    group: SeriesGroup = _group(
        (
            _choice("2"),
            _choice("1"),
            _choice("5", reading=_reading("5", other_season=True)),
            _choice(None, batch=True),
        )
    )
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(),),
                "search_title": lambda chosen, **options: ReleaseCatalog((group,), 0),
            }
        )
    )
    _chosen(controller)
    controller.handle_key("text:a")
    marked: str = _frame(controller)

    assert "zaznaczono 2" in marked
    assert len(controller._marked) == 2


def test_z_marks_the_typed_range_and_names_the_missing_episodes() -> None:
    group: SeriesGroup = _group((_choice("6"), _choice("5"), _choice("4"), _choice("2")))
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(),),
                "search_title": lambda chosen, **options: ReleaseCatalog((group,), 0),
            }
        )
    )
    _chosen(controller)
    controller.handle_key("text:z")

    assert "zakres (np. 4-10): ▌" in _frame(controller)

    _type(controller, "4-10")

    assert "zakres (np. 4-10): 4-10▌" in _frame(controller)

    controller.handle_key("enter")

    assert "zaznaczono 3 z 7" in _frame(controller)
    assert len(controller._marked) == 3


def test_z_with_an_open_range_marks_every_later_episode() -> None:
    group: SeriesGroup = _group((_choice("6"), _choice("5"), _choice("4")))
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(),),
                "search_title": lambda chosen, **options: ReleaseCatalog((group,), 0),
            }
        )
    )
    _chosen(controller)
    controller.handle_key("text:z")
    _type(controller, "5-")
    controller.handle_key("enter")

    assert "zaznaczono 2" in _frame(controller)


def test_an_unreadable_range_says_how_to_type_it_and_escape_closes_the_prompt() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("4"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:z")
    _type(controller, "-")
    controller.handle_key("enter")

    assert "zakres: podaj np. 4-10" in _frame(controller)
    assert controller._marked == set()

    controller.handle_key("text:z")
    controller.handle_key("escape")

    assert "zakres (np. 4-10)" not in _frame(controller)
    assert _screen(controller) is _Screen.RESULTS


def test_s_reorders_the_groups_without_a_new_search_and_keeps_the_marks() -> None:
    searches: list[object] = []
    fresh: SeriesGroup = _group(
        (_choice("9", seeders=5, series="Fresh"),),
        series="Fresh",
        group="Erai-raws",
        newest=datetime(2026, 9, 5, tzinfo=UTC),
    )
    seeded: SeriesGroup = _group(
        (_choice("9", seeders=900, series="Seeded"),),
        series="Seeded",
        newest=datetime(2026, 1, 1, tzinfo=UTC),
    )

    def search_title(chosen: TitleCandidate, **options: object) -> ReleaseCatalog:
        searches.append(chosen)
        return ReleaseCatalog((fresh, seeded), 0)

    controller: AnimeController = _controller(
        _service(extra={"find_titles": lambda text: (_title(),), "search_title": search_title})
    )
    _chosen(controller)
    controller.handle_key("space")
    before: str = _frame(controller)
    controller.handle_key("text:s")
    after: str = _frame(controller)

    assert before.index("Fresh") < before.index("Seeded")
    assert after.index("Seeded") < after.index("Fresh")
    assert len(searches) == 1
    assert "zaznaczone: 1" in after
    assert "S najnowsze" in after
    assert controller._rows[next(iter(controller._marked))].choice is fresh.choices[0]


def test_f_searches_the_title_again_without_the_episode_filter() -> None:
    asked: list[object] = []

    def search_title(chosen: TitleCandidate, **options: object) -> ReleaseCatalog:
        asked.append(options["episodes"])
        return _catalog((_choice("1"),), filtered=4)

    controller: AnimeController = _controller(
        _service(extra={"find_titles": lambda text: (_title(),), "search_title": search_title})
    )
    _chosen(controller, "oshi no ko 1")
    filtered: str = _frame(controller)

    assert "filtr: odc. 1" in filtered
    assert "poza filtrem: 4" in filtered
    assert "F pokaż wszystkie" in filtered

    controller.handle_key("text:f")
    _settle(controller)
    everything: str = _frame(controller)

    assert asked[1] is None
    assert "filtr:" not in everything
    assert "F pokaż wszystkie" not in everything


def test_o_follows_the_highlighted_group_of_the_chosen_title() -> None:
    recorded: list[tuple[str, str | None, SeasonContext | None]] = []
    candidate: TitleCandidate = _title("Ore dake Level Up na Ken", english="Solo Leveling")
    context: SeasonContext = _season(index=2, offset=12, episodes=13)

    def subscribe(
        query: str,
        choice: ReleaseChoice,
        *,
        directory_name: str | None = None,
        context: SeasonContext | None = None,
    ) -> SimpleNamespace:
        del choice
        recorded.append((query, directory_name, context))
        return _subscription()

    group: SeriesGroup = _group((_choice("1", series="Solo Leveling"),), series="Solo Leveling")
    controller: AnimeController = _controller(
        _service(
            subscriptions=SimpleNamespace(subscribe=subscribe, check=lambda subscription: _outcome(downloaded=1)),
            extra={
                "find_titles": lambda text: (candidate,),
                "season_context": lambda chosen: context,
                "search_title": lambda chosen, **options: ReleaseCatalog((group,), 0),
            },
        )
    )
    _chosen(controller, "solo leveling")
    controller.handle_key("text:o")
    _settle(controller)

    assert recorded == [("Solo Leveling SubsPlease", "Solo Leveling", context)]


def test_o_refuses_a_release_that_belongs_to_another_season() -> None:
    calls: list[str] = []
    group: SeriesGroup = _group((_choice("3", reading=_reading("3", other_season=True)),))

    def subscribe(query: str, choice: ReleaseChoice, **options: object) -> SimpleNamespace:
        calls.append(query)
        return _subscription()

    controller: AnimeController = _controller(
        _service(
            subscriptions=SimpleNamespace(subscribe=subscribe, check=lambda subscription: _outcome()),
            extra={
                "find_titles": lambda text: (_title(),),
                "search_title": lambda chosen, **options: ReleaseCatalog((group,), 0),
            },
        )
    )
    _chosen(controller)
    controller.handle_key("text:o")

    assert calls == []
    assert _screen(controller) is _Screen.RESULTS
    assert "To wydanie wygląda na inny sezon" in _frame(controller)


def test_enter_downloads_into_the_folder_of_the_chosen_title() -> None:
    sent: list[str | None] = []
    candidate: TitleCandidate = _title("Ore dake Level Up na Ken", english="Solo Leveling")

    def download(choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        sent.append(directory_name)
        return DownloadReceipt(len(choices), Path("workspace") / "Solo Leveling")

    controller: AnimeController = _controller(
        _service(
            download=download,
            extra={
                "find_titles": lambda text: (candidate,),
                "search_title": lambda chosen, **options: _catalog((_choice("1"),)),
            },
        )
    )
    _chosen(controller, "solo leveling")
    controller.handle_key("enter")
    _settle(controller)

    assert sent == ["Solo Leveling"]
    assert "Wysłano 1 do qBittorrenta → Solo Leveling" in _frame(controller)


def test_a_finished_title_offers_the_whole_group_first() -> None:
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(status=TitleStatus.FINISHED),),
                "search_title": lambda chosen, **options: _catalog((_choice("1"),)),
            }
        )
    )
    _chosen(controller)
    listed: str = _frame(controller)

    assert "A cała grupa" in listed
    assert listed.index("A cała grupa") < listed.index("Space/Z zaznacz")


def test_the_anime_row_opens_the_screen_and_a_home_result_returns_to_the_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application: interactive_app._InteractiveApplication = _application(
        monkeypatch, _service(search=lambda query: _catalog(()))
    )
    application._selected = 2

    application._handle_key("enter")
    opened: str = application._render_frame(120, 30).plain

    assert _mode(application) is interactive_app._ViewMode.ANIME
    assert application._anime is not None
    assert "ANIME" in opened
    assert "Enter szukaj · Esc wróć" in opened

    application._handle_key("escape")
    home: str = application._render_frame(120, 30).plain
    rows: list[str] = [line.strip().removeprefix("\u276f").strip() for line in home.split("\n") if line.strip()]
    hint: int = rows.index("↑↓ · Enter")

    assert _mode(application) is interactive_app._ViewMode.HOME
    assert application._anime is None
    assert rows[hint - 5 : hint] == ["Auto", "Ręczny", "Anime", "Ustawienia", "Wyjście"]


def test_an_interrupt_inside_the_anime_screen_cancels_it_and_returns_home(monkeypatch: pytest.MonkeyPatch) -> None:
    release: threading.Event = threading.Event()

    def search(query: str) -> ReleaseCatalog:
        del query
        assert release.wait(timeout=5)
        return _catalog((_choice("11"),))

    application: interactive_app._InteractiveApplication = _application(monkeypatch, _service(search=search))
    application._selected = 2
    application._handle_key("enter")
    controller: AnimeController | None = application._anime

    assert controller is not None
    _type(controller, "oshi")
    application._handle_key("enter")
    worker: threading.Thread | None = controller._worker

    application._handle_key("interrupt")
    release.set()
    assert worker is not None
    worker.join(timeout=5)

    assert _mode(application) is interactive_app._ViewMode.HOME
    assert application._anime is None
    assert controller._rows == ()
