from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from rich.text import Text

from anishift.application import AppService, DownloadReceipt, ReleaseCatalog, ReleaseChoice, SeriesGroup
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


def _choice(
    episode: str | None, *, batch: bool = False, seeders: int = 159, series: str = "Oshi no Ko"
) -> ReleaseChoice:
    release: Release = Release(
        title=f"[SubsPlease] {series}",
        torrent_url=f"https://nyaa.si/download/{episode or 'batch'}.torrent",
        info_hash=f"hash-{episode or 'batch'}",
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
    return ReleaseChoice(release, name)


def _catalog(choices: Sequence[ReleaseChoice], hidden: int = 0) -> ReleaseCatalog:
    return ReleaseCatalog((SeriesGroup("Oshi no Ko", "SubsPlease", tuple(choices)),), hidden)


def _service(
    search: Callable[[str], ReleaseCatalog] | None = None,
    download: Callable[[Sequence[ReleaseChoice]], DownloadReceipt] | None = None,
) -> AppService:
    acquisition: SimpleNamespace | None = None
    if search is not None or download is not None:
        acquisition = SimpleNamespace(search=search, download=download)
    return cast("AppService", SimpleNamespace(acquisition=acquisition))


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


def _receipt(directory: str = "Oshi no Ko") -> Callable[[Sequence[ReleaseChoice]], DownloadReceipt]:
    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        return DownloadReceipt(len(choices), Path("workspace") / directory)

    return download


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

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
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

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
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


def test_a_failed_search_shows_the_sentence_with_its_suggestion_and_no_traceback() -> None:
    def search(query: str) -> ReleaseCatalog:
        del query
        raise AniShiftError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_SOURCE_FAILED,
                message="Nyaa nie odpowiedziało poprawnie",
                suggestion="Sprawdź połączenie i spróbuj ponownie",
            )
        )

    controller: AnimeController = _controller(_service(search=search))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    reported: str = _frame(controller)

    assert _screen(controller) is _Screen.PROBLEM
    assert "Nyaa nie odpowiedziało poprawnie" in reported
    assert "Sprawdź połączenie i spróbuj ponownie" in reported
    assert "Traceback" not in reported

    assert controller.handle_key("enter") is AnimeResult.CONTINUE
    assert _screen(controller) is _Screen.QUERY


def test_a_failed_download_returns_to_the_results_and_escape_leaves_home() -> None:
    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        del choices
        raise AniShiftError(
            context=ErrorContext(
                code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                message="qBittorrent nie odpowiada",
                suggestion="Włącz Web UI w qBittorrent",
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
    assert "Włącz Web UI w qBittorrent" in reported

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
    assert "Szukam…" in _frame(controller)

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
