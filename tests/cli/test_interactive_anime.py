from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import cast

import pytest
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from anishift.application import (
    AppService,
    CatalogOrder,
    DownloadReceipt,
    EpisodeRange,
    EpisodeReading,
    RefusalReason,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    SeriesGroup,
    SubscriptionOrder,
    TitleCandidate,
    TitleCatalogError,
    TitleStatus,
    encode_view,
)
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.anime import AnimeController, AnimeResult, _Screen
from anishift.cli.interactive.state import StateController, StateResult
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.platform.local_control import ControlClient, ControlError, ControlErrorCode
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
    if not controller.input_focused:
        controller.handle_key("enter")
    for character in value:
        controller.handle_key("space" if character == " " else f"text:{character}")


def _settle(controller: AnimeController) -> None:
    worker: threading.Thread | None = controller._worker
    if worker is None:
        return
    worker.join(timeout=5)
    assert not worker.is_alive()


def _settle_panel(panel: StateController) -> None:
    deadline: float = monotonic() + 5
    while panel._busy and monotonic() < deadline:
        threading.Event().wait(0.005)
    assert not panel._busy


class _PausedClient:
    def __init__(self) -> None:
        self.enabled: bool = False
        self.calls: list[str] = []
        self.downloads: list[object] = []
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.failure: ControlError | None = None
        self.confirmed: bool = True

    def call(self, kind: str, payload: Mapping[str, object], *, instance_id: str | None = None) -> Mapping[str, object]:
        del instance_id
        self.calls.append(kind)
        if kind == "acquisition":
            if payload["operation"] == "titles":
                return {"items": []}
            return encode_view(_catalog((_choice("11"), _choice("10"))))
        if kind == "download":
            if not self.enabled:
                raise ControlError("Paused", reason=RefusalReason.PAUSED.value, answered=True)
            self.downloads.append(payload["choices"])
            return encode_view(DownloadReceipt(1, Path("workspace")))
        if kind == "set_auto":
            assert payload["enabled"] is True
            self.entered.set()
            assert self.release.wait(5)
            if self.failure is not None:
                raise self.failure
            self.enabled = self.confirmed
            return {"auto_enabled": self.enabled}
        if kind == "subscriptions_list":
            return {"subscriptions": []}
        raise AssertionError(kind)

    def close(self) -> None:
        return


@pytest.fixture
def paused_anime(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[StateController, AnimeController, _PausedClient]]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    client: _PausedClient = _PausedClient()
    session: ResidentSession = ResidentSession(Path("workspace"), lambda: cast("ControlClient", client))
    anime: AnimeController = AnimeController(_service(), lambda: None, resident=session)
    panel: StateController = StateController(session, lambda: None)
    panel.attach_anime(anime)
    panel._connected = True
    panel._notice = ""
    panel.handle_key("left")
    panel.handle_key("left")
    try:
        yield panel, anime, client
    finally:
        client.release.set()
        _settle(anime)
        panel.close()
        session.close()
        panel._thread.join(5)


def _paused_download(panel: StateController, anime: AnimeController) -> str:
    panel.handle_key("enter")
    panel.handle_key("text:oshi")
    panel.handle_key("enter")
    _settle(anime)
    panel.handle_key("enter")
    panel.handle_key("down")
    panel.handle_key("space")
    selected: str = panel.render(120, 40).plain
    panel.handle_key("text:d")
    _settle(anime)
    assert "Enter Wznów AniShift" in panel.render(80, 24).plain
    return selected


def test_paused_download_resumes_once_and_preserves_selection_until_explicit_download(
    paused_anime: tuple[StateController, AnimeController, _PausedClient],
) -> None:
    panel, anime, client = paused_anime
    selected: str = _paused_download(panel, anime)
    assert "set_auto" not in client.calls
    for key in ("text:o", "text:x", "space", "up", "any"):
        assert panel.handle_key(key) is StateResult.CONTINUE
        assert "Enter Wznów AniShift" in panel.render(80, 24).plain
    assert "set_auto" not in client.calls
    panel.handle_key("enter")
    assert client.entered.wait(5)
    for _ in range(5):
        panel.handle_key("enter")
    assert "Wznawiam AniShift" in panel.render(80, 24).plain
    assert client.calls.count("set_auto") == 1
    client.release.set()
    _settle(anime)
    assert panel.render(120, 40).plain == selected
    assert client.downloads == []
    panel.handle_key("text:d")
    _settle(anime)
    assert client.downloads == [[encode_view(_choice("10"))]]
    assert "Przyjęto 1 zamówień" in panel.render(120, 40).plain


@pytest.mark.parametrize("failure", ["refused", "unanswered", "unconfirmed"])
def test_failed_resume_stays_visible_and_requires_explicit_retry(
    paused_anime: tuple[StateController, AnimeController, _PausedClient], failure: str
) -> None:
    panel, anime, client = paused_anime
    _paused_download(panel, anime)
    client.confirmed = failure != "unconfirmed"
    if failure != "unconfirmed":
        client.failure = ControlError("private failure", code=ControlErrorCode.INTERNAL, answered=failure == "refused")
    client.release.set()
    panel.handle_key("enter")
    _settle(anime)
    frame: str = panel.render(120, 40).plain
    expected: str = {
        "refused": "Wewnętrzny błąd procesu w tle",
        "unanswered": "Brak potwierdzonej odpowiedzi procesu w tle",
        "unconfirmed": "Brak potwierdzenia wznowienia AniShift",
    }[failure]
    assert expected in frame
    assert "Enter Wznów AniShift" in frame
    assert "private failure" not in frame
    assert "Przyjęto" not in frame
    assert client.downloads == []
    assert client.calls.count("set_auto") == 1
    client.failure = None
    client.confirmed = True
    panel.handle_key("enter")
    _settle(anime)
    assert "Pobierz (1)" in panel.render(120, 40).plain
    assert client.calls.count("set_auto") == 2
    assert client.downloads == []


@pytest.mark.parametrize("key", ["escape", "tab"])
def test_leaving_pending_resume_discards_response_but_observes_owner_state(
    paused_anime: tuple[StateController, AnimeController, _PausedClient], key: str
) -> None:
    panel, anime, client = paused_anime
    _paused_download(panel, anime)
    panel.handle_key("enter")
    assert client.entered.wait(5)
    worker: threading.Thread | None = anime._worker
    assert worker is not None
    panel.handle_key(key)
    before: str = panel.render(120, 40).plain
    client.release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert client.enabled
    assert client.calls.count("set_auto") == 1
    assert client.downloads == []
    assert panel.render(120, 40).plain == before
    panel._receive(panel._parent, {"event": "state_changed", "payload": {"auto_enabled": True}})
    assert "Praca" in panel.render(120, 40).plain
    assert "Wstrzymano" not in panel.render(120, 40).plain


def test_normal_anime_search_and_subscription_never_resume_automation(
    paused_anime: tuple[StateController, AnimeController, _PausedClient],
) -> None:
    panel, anime, client = paused_anime
    panel.handle_key("enter")
    panel.handle_key("text:o")
    panel.handle_key("enter")
    _settle(anime)
    assert "O subskrybuj" in panel.render(120, 40).plain
    panel.handle_key("text:o")
    assert panel._draft is not None
    assert panel._tab == 1
    assert "set_auto" not in client.calls
    assert "download" not in client.calls


def _search_panel_from_subscriptions(panel: StateController, anime: AnimeController) -> None:
    assert panel._tab == 2
    panel.handle_key("left")
    assert panel._tab == 1
    panel.handle_key("text:d")
    assert panel._tab == 0
    assert "←→ widok" in panel.render(80, 24).plain
    panel.handle_key("escape")
    assert panel._tab == 1
    panel.handle_key("text:d")
    panel.handle_key("enter")
    panel.handle_key("text:oshi")
    panel.handle_key("enter")
    _settle(anime)
    panel.handle_key("enter")
    _settle(anime)


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (40, 6)])
def test_panel_query_requires_focus_and_preserves_text_across_tabs(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    anime: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("1"),))))
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    try:
        panel.handle_key("left")
        panel.handle_key("left")
        assert not any(span.style == "reverse" for span in panel.render(*size).spans)
        panel.handle_key("text:ignored")
        assert anime._query == ""
        panel.handle_key("enter")
        panel.handle_key("text:abc")
        panel.handle_key("left")
        assert panel._tab == 0
        panel.handle_key("text:x")
        assert anime._query == "abxc"
        panel.handle_key("escape")
        assert not anime.input_focused
        panel.handle_key("left")
        assert panel._tab == 3
        panel.handle_key("right")
        assert panel._tab == 0
        assert anime._query == "abxc"
        panel.handle_key("enter")
        panel.handle_key("shift-left")
        panel.handle_key("text:y")
        assert anime._query == "abyc"
        assert panel._tab == 0
        panel.handle_key("escape")
        frame: str = panel.render(*size).plain
        assert not any(span.style == "reverse" for span in panel.render(*size).spans)
        assert "←→ widok" in frame
        assert "Przetwarzanie 0" in frame
        assert len(frame.splitlines()) <= size[1]
        assert all(Text(line).cell_len <= size[0] for line in frame.splitlines())
        panel.handle_key("enter")
        panel.handle_key("select-all")
        panel.handle_key("tab")
        assert panel._tab == 1
        panel.handle_key("backtab")
        assert panel._tab == 0
        assert panel.render(*size).plain == frame
        assert anime._worker is None
        assert panel._draft is None
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.parametrize("editor", ["range", "group"])
@pytest.mark.parametrize("blur", ["escape", "interrupt"])
def test_panel_navigation_blurs_and_preserves_range_and_group_inputs_without_submitting(
    monkeypatch: pytest.MonkeyPatch, editor: str, blur: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    anime: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda query: (_title(),),
                "search_title": lambda candidate, **options: _catalog((_choice("1"),) if editor == "range" else ()),
            }
        )
    )
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    try:
        for key in ("left", "left"):
            panel.handle_key(key)
        _chosen(anime, "oshi")
        if editor == "range":
            for key in ("enter", "space", "text:z", "text:1-3"):
                panel.handle_key(key)
        else:
            panel.handle_key("text:o")
            panel.handle_key("text:SomeGroup")
        panel.handle_key("left")
        panel.handle_key("right")
        assert panel._tab == 0
        assert any(span.style == "reverse" for span in panel.render(80, 24).spans)
        panel.handle_key(blur)
        frame: str = panel.render(80, 24).plain
        assert not any(span.style == "reverse" for span in panel.render(80, 24).spans)
        marked: set[int] = anime._marked.copy()
        for leave, destination, back in (("left", 3, "right"), ("right", 1, "left")):
            panel.handle_key(leave)
            panel.poll()
            assert panel._tab == destination
            panel.handle_key(back)
            assert panel._tab == 0
            assert panel.render(80, 24).plain == frame
            assert anime._marked == marked
            assert panel._draft is None
        for key in ("text:d", "text:o", "paste:ignored", "delete", "backspace"):
            panel.handle_key(key)
        assert panel.render(80, 24).plain == frame
        for key in ("enter", "shift-left", "paste:x"):
            panel.handle_key(key)
        if editor == "range":
            assert anime._range == "1-x"
        else:
            assert anime._group_input is not None
            assert anime._group_input.text == "SomeGroux"
        for key in ("tab", "backtab"):
            panel.handle_key(key)
        assert not anime.input_focused
        assert not any(span.style == "reverse" for span in panel.render(80, 24).spans)
        for key in ("enter", "escape"):
            panel.handle_key(key)
        assert "Enter edytuj" in panel.render(80, 24).plain
        panel.handle_key("escape")
        assert anime._range_input is None
        assert anime._group_input is None
        assert anime._marked == marked
        assert panel._draft is None
    finally:
        panel.close()
        panel._thread.join(5)


def _select_panel_episode_range(panel: StateController) -> None:
    for key in ("home", "down", "down", "space", "end", "up", "space"):
        panel.handle_key(key)
    assert panel._draft is not None
    assert panel._draft.selected == {Decimal(3), Decimal("7.5"), Decimal(8)}


@pytest.mark.parametrize("size", [(120, 40), (80, 24), (40, 6)])
def test_panel_search_draft_confirm_and_one_off_download_keep_the_same_controller(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    calls: list[tuple[SubscriptionOrder, tuple[Decimal, ...], Decimal | None]] = []
    downloaded: list[tuple[ReleaseChoice, ...]] = []

    def follow(order: SubscriptionOrder, *, selected: Sequence[Decimal], future_from: Decimal | None) -> None:
        calls.append((order, tuple(selected), future_from))

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        downloaded.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("workspace"))

    session: ResidentSession = cast(
        "ResidentSession",
        SimpleNamespace(
            follow=follow,
            close=lambda: None,
            library=lambda: (),
        ),
    )
    parent: ResidentSession = cast("ResidentSession", SimpleNamespace(new_session=lambda: session))
    service: AppService = _service(
        download=download,
        extra={
            "find_titles": lambda text: (_title(episodes=8),),
            "season_context": lambda candidate: _season(episodes=8),
            "search_title": lambda candidate, **options: _catalog((_choice("8"), _choice("7.5"), _choice("3"))),
        },
    )
    anime: AnimeController = AnimeController(service, lambda: None)
    panel: StateController = StateController(parent, lambda: None)
    panel.attach_anime(anime)
    panel._connected = True
    try:
        _search_panel_from_subscriptions(panel, anime)
        panel.handle_key("text:o")
        assert panel._tab == 1
        assert calls == []
        assert downloaded == []
        assert panel._draft is not None
        _select_panel_episode_range(panel)
        frame: Text = panel.render(*size)
        assert len(frame.split("\n")) <= size[1]
        assert calls == []
        panel.handle_key("enter")
        _settle_panel(panel)
        assert len(calls) == 1
        assert calls[0][0].series == "Oshi no Ko"
        assert calls[0][1:] == ((Decimal(3), Decimal("7.5"), Decimal(8)), None)
        panel.handle_key("left")
        assert panel._anime is anime
        assert anime._query == "oshi"
        for key in ("enter", "space", "text:d"):
            panel.handle_key(key)
        _settle(anime)
        assert panel._tab == 0
        assert "Wysłano 1" in panel.render(120, 40).plain
        assert len(downloaded) == 1
        assert len(calls) == 1
        panel.handle_key("left")
        assert panel._tab == 3
        panel.render(*size)
        panel.handle_key("right")
        assert panel._tab == 0
        assert "Anime" in panel.render(*size).plain
    finally:
        panel.close()
        panel._thread.join(5)


def _screen(controller: AnimeController) -> _Screen:
    return controller._screen


@pytest.mark.parametrize("inflight", [False, True])
@pytest.mark.parametrize("key", ["tab", "backtab", "left", "right"])
def test_download_completion_after_leaving_anime_never_steals_the_tab(
    monkeypatch: pytest.MonkeyPatch, inflight: bool, key: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        entered.set()
        assert release.wait(5)
        return DownloadReceipt(len(choices), Path("workspace"))

    anime: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("8"),)), download=download))
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(anime)
    worker: threading.Thread | None = None
    try:
        panel.handle_key("left")
        panel.handle_key("left")
        panel.handle_key("enter")
        panel.handle_key("text:oshi")
        panel.handle_key("enter")
        _settle(anime)
        panel.handle_key("enter")
        panel.handle_key("space")
        panel.handle_key("text:d")
        assert entered.wait(5)
        worker = anime._worker
        if not inflight:
            release.set()
            _settle(anime)
        panel.handle_key(key)
        release.set()
        assert worker is not None
        worker.join(5)
        assert not worker.is_alive()
        panel.poll()
        assert panel._tab == (3 if key in {"left", "backtab"} else 1)
        panel.handle_key("right" if key in {"left", "backtab"} else "left")
        panel.poll()
        assert panel._tab == 0
        assert anime._query == "oshi"
        assert anime._screen is _Screen.RESULTS
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        panel.close()
        panel._thread.join(5)


def test_upcoming_title_group_input_is_local_and_routes_command_letters_as_text() -> None:
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda query: (_title(episodes=None, status=TitleStatus.NOT_YET_RELEASED),),
                "season_context": lambda candidate: _season(episodes=None),
                "search_title": lambda candidate, **options: _catalog(()),
            }
        )
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:o")
    controller.handle_key("text:SomeGroup")
    controller.handle_key("left")
    controller.handle_key("text:x")
    assert controller.take_draft() is None
    assert controller.handle_key("enter") is AnimeResult.SUBSCRIBE
    draft = controller.take_draft()
    assert draft is not None
    assert draft.order is not None
    assert draft.order.group == "SomeGrouxp"
    assert [label for label, _selected in draft.entries()].count("Kolejne odcinki") == 1


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
    assert "> oshi no ko " in _frame(controller)
    assert any(span.style == "reverse" for span in controller.render(120, 30).spans)


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
    assert "2 odc. / 3 wydania" in _frame(controller)
    controller.handle_key("enter")
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
    controller.handle_key("enter")

    assert "zaznaczone: 0" in _frame(controller)

    controller.handle_key("space")
    controller.handle_key("down")
    controller.handle_key("space")

    assert "zaznaczone: 2" in _frame(controller)

    controller.handle_key("space")

    assert "zaznaczone: 1" in _frame(controller)


def test_navigation_visits_releases_and_explicit_action_rows() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"), _choice("10")))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    first: int = controller._selected

    for _ in range(5):
        controller.handle_key("down")

    assert controller._rows[first].choice is not None
    assert controller._selected == first
    assert len(controller._choices) == 5


def test_download_sends_exactly_the_marked_releases_and_names_the_directory() -> None:
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
    controller.handle_key("enter")
    controller.handle_key("down")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)
    finished: str = _frame(controller)

    assert sent == [(wanted,)]
    assert _screen(controller) is _Screen.DONE
    assert "Wysłano 1 do qBittorrenta → Oshi no Ko" in finished
    assert "workspace" not in finished


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_group_entry_and_single_episode_selection_require_explicit_download(size: tuple[int, int]) -> None:
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
    assert "Enter otwórz grupę" in _frame(controller, *size)
    assert "[ ]" not in _frame(controller, *size)
    controller.handle_key("enter")
    opened: str = _frame(controller, *size)
    assert opened.count("[ ]") == 2
    assert "[x]" not in opened
    assert all(label in opened for label in ("Zaznacz wszystkie", "Pobierz (0)", "Cofnij"))
    assert sent == []
    controller.handle_key("end")
    controller.handle_key("up")
    controller.handle_key("enter")
    assert sent == []
    assert "Zaznacz co najmniej jedno wydanie" in _frame(controller, *size)
    controller.handle_key("home")
    controller.handle_key("enter")
    assert "Pobierz (1)" in _frame(controller, *size)
    assert sent == []
    controller.handle_key("down")
    controller.handle_key("end")
    controller.handle_key("up")
    controller.handle_key("enter")
    _settle(controller)

    assert sent == [(newest,)]
    assert "Wysłano 1 do qBittorrenta" in _frame(controller)


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_group_drafts_and_pinned_actions_keep_other_groups_out_of_download(size: tuple[int, int]) -> None:
    sent: list[tuple[ReleaseChoice, ...]] = []
    first: SeriesGroup = _group(tuple(_choice(str(number)) for number in range(30, 0, -1)))
    second: SeriesGroup = _group((_choice("1", series="Other"),), series="Other", group="ASW")

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        sent.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("workspace"))

    controller: AnimeController = _controller(
        _service(search=lambda query: ReleaseCatalog((first, second), 0), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    controller.handle_key("space")
    for _ in range(30):
        frame: str = _frame(controller, *size)
        assert len(frame.splitlines()) <= size[1]
        assert all(Text(line).cell_len <= size[0] for line in frame.splitlines())
        assert all(label in frame for label in ("Zaznacz wszystkie", "Pobierz (1)", "Cofnij"))
        controller.handle_key("down")
    controller.handle_key("end")
    controller.handle_key("enter")
    controller.handle_key("down")
    controller.handle_key("enter")
    assert "Pobierz (0)" in _frame(controller, *size)
    controller.handle_key("text:d")
    assert sent == []
    controller.handle_key("escape")
    assert "\u276f [ASW] Other" in _frame(controller, *size)
    controller.handle_key("up")
    controller.handle_key("enter")
    assert "Pobierz (1)" in _frame(controller, *size)
    controller.handle_key("escape")
    controller.handle_key("down")
    controller.handle_key("enter")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)
    assert sent == [second.choices]


def test_versions_and_whole_packs_remain_individual_explicit_choices() -> None:
    original: ReleaseChoice = _choice("2")
    revised: ReleaseChoice = replace(
        original,
        release=replace(original.release, info_hash="revised-hash"),
        name=replace(original.name, version=2),
    )
    pack: ReleaseChoice = _choice("1", batch=True)
    foreign: ReleaseChoice = _choice("3", reading=_reading("3", other_season=True))
    sent: list[tuple[ReleaseChoice, ...]] = []

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        sent.append(tuple(choices))
        return DownloadReceipt(len(choices), Path("workspace"))

    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((original, revised, pack, foreign)), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    frame: str = _frame(controller)
    assert frame.count("[ ]") == 4
    assert "odc. 2  v2" in frame
    assert "cała paczka" in frame
    controller.handle_key("down")
    controller.handle_key("space")
    assert _frame(controller).count("[x]") == 1
    controller.handle_key("text:d")
    _settle(controller)
    assert sent == [(revised,)]
    controller.handle_key("enter")
    controller.handle_key("end")
    controller.handle_key("up")
    controller.handle_key("up")
    controller.handle_key("enter")
    assert "Pobierz (1)" in _frame(controller)
    controller.handle_key("text:d")
    _settle(controller)
    assert sent[1] == (original,)
    controller.handle_key("enter")
    controller.handle_key("home")
    controller.handle_key("down")
    controller.handle_key("down")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)
    assert sent == [(revised,), (original,), (pack,)]


def test_a_finished_download_returns_to_the_release_selection_on_any_key() -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), download=_receipt())
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)

    assert controller.handle_key("any") is AnimeResult.CONTINUE
    assert "Pobierz (0)" in _frame(controller)


def test_returning_to_the_same_title_keeps_marks_but_new_search_clears_them() -> None:
    searches: list[TitleCandidate] = []

    def search_title(candidate: TitleCandidate, **options: object) -> ReleaseCatalog:
        searches.append(candidate)
        return _catalog((_choice("1"),))

    controller: AnimeController = _controller(
        _service(extra={"find_titles": lambda text: (_title(),), "search_title": search_title})
    )
    _chosen(controller)
    for key in ("enter", "space", "escape", "escape", "enter", "enter"):
        controller.handle_key(key)
    assert "Pobierz (1)" in _frame(controller)
    assert len(searches) == 1
    for key in ("escape", "escape", "escape", "enter", "enter"):
        controller.handle_key(key)
    _settle(controller)
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    assert "Pobierz (0)" in _frame(controller)
    assert len(searches) == 2


@pytest.mark.parametrize(
    "details",
    [
        None,
        {},
        {"sent": 1, "accepted": 0},
        {"sent": "1", "accepted": 0, "uncertain": 1},
        {"sent": True, "accepted": 0, "uncertain": 1},
        {"sent": 1, "accepted": -1, "uncertain": 1},
        {"sent": 1, "accepted": 0, "uncertain": -1},
        {"sent": -1, "accepted": 0, "uncertain": 1},
    ],
)
def test_incomplete_or_invalid_download_counts_do_not_invent_an_outcome(details: dict[str, object] | None) -> None:
    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        del choices
        raise ControlError("private payload", reason="download_recorded", answered=True, details=details)

    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog((_choice("11"),)), download=download)
    )
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)

    assert controller._problem == "Nie można potwierdzić wyniku zamówienia"
    assert controller._suggestion == "Sprawdź prywatny klient AniShift i log"
    assert _screen(controller) is _Screen.PROBLEM
    assert "Wysłano" not in _frame(controller)


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


def test_a_draft_does_not_call_the_subscription_admission_boundary() -> None:
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

    assert _screen(controller) is _Screen.RESULTS
    assert controller.take_draft() is not None
    assert "carries no episode number" not in reported


def test_a_pasted_title_drops_its_control_characters() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog(())))

    controller.handle_key("enter")
    controller.handle_key("paste:oshi no ko\r\n")

    assert controller._query == "oshi no ko"
    assert "> oshi no ko " in _frame(controller)
    assert any(span.style == "reverse" for span in controller.render(120, 30).spans)


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
    controller.handle_key("enter")
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


@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("code", [ErrorCode.TITLE_CATALOG_FAILED, ErrorCode.IO_ERROR, ErrorCode.UNKNOWN])
def test_only_a_catalog_failure_falls_back_to_release_search(remote: bool, code: ErrorCode) -> None:
    searched: list[str] = []

    def titles(text: str) -> tuple[TitleCandidate, ...]:
        del text
        if remote:
            raise ControlError("private failure", reason=code.value, answered=True)
        raise AniShiftError(context=ErrorContext(code=code, message="private failure"))

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog((_choice("11"),))

    controller: AnimeController = _controller(_service(search=search, extra={"find_titles": titles}))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)

    assert searched == (["oshi"] if code is ErrorCode.TITLE_CATALOG_FAILED else [])
    assert _screen(controller) is (_Screen.RESULTS if code is ErrorCode.TITLE_CATALOG_FAILED else _Screen.PROBLEM)


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
    controller.handle_key("space")
    controller.handle_key("text:d")
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


def test_o_on_a_numbered_episode_returns_a_draft_without_subscribing_or_checking() -> None:
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
    controller.handle_key("enter")
    controller.handle_key("down")
    controller.handle_key("text:o")
    _settle(controller)
    draft = controller.take_draft()
    assert draft is not None
    assert draft.order is not None
    assert draft.order.query == "oshi no ko"
    assert draft.order.first_episode == Decimal(9)
    assert subscribed == []
    assert checked == []
    assert _screen(controller) is _Screen.RESULTS
    assert controller.take_draft() is None


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
    controller.handle_key("enter")
    controller.handle_key("down")
    controller.handle_key("text:o")
    noticed: str = _frame(controller)

    assert calls == []
    assert controller._worker is None
    assert _screen(controller) is _Screen.RESULTS
    assert "Subskrybuj działa tylko na numerowanym odcinku" in noticed

    controller.handle_key("up")

    assert "Subskrybuj działa tylko na numerowanym odcinku" not in _frame(controller)


def test_a_subscription_draft_needs_no_local_persistence_boundary() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("text:O")
    _settle(controller)

    assert controller.take_draft() is not None
    assert _screen(controller) is _Screen.RESULTS


def test_drafting_never_checks_or_reports_a_download_count() -> None:
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

    assert _screen(controller) is _Screen.RESULTS
    assert controller.take_draft() is not None
    assert "Nyaa nie odpowiedziało" not in watched
    assert "pobrano" not in watched


def test_a_draft_is_available_even_when_the_local_subscription_store_would_fail() -> None:
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

    assert _screen(controller) is _Screen.RESULTS
    assert controller.take_draft() is not None
    assert "Nie mogę zapisać obserwacji" not in reported
    assert "Sprawdź katalog config" not in reported
    assert "Traceback" not in reported

    assert _screen(controller) is _Screen.RESULTS


def test_cancel_discards_the_unconsumed_subscription_draft() -> None:
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
    assert controller._worker is None
    controller.cancel()
    release.set()
    assert controller.take_draft() is None
    assert _screen(controller) is _Screen.RESULTS
    assert "Obserwuję" not in _frame(controller)


def test_the_results_footer_offers_the_watch_key() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("11"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)

    assert "O subskrybuj" in _frame(controller)


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
    assert "[SubsPlease · EN] Solo Leveling · 1 odc. / 2 wydania  najnowsze: 04.09.2026" in listed
    assert "[MTBB · MULTI] Solo" in listed
    controller.handle_key("enter")
    assert "odc. 1 (13)" in _frame(controller)
    assert "odc. 3 · sezon?" in _frame(controller)


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
    controller.handle_key("enter")
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
    controller.handle_key("enter")
    controller.handle_key("text:z")

    assert "zakres (np. 4-10):  " in _frame(controller)
    assert any(span.style == "reverse" for span in controller.render(120, 30).spans)

    _type(controller, "4-10")

    assert "zakres (np. 4-10): 4-10 " in _frame(controller)

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
    controller.handle_key("enter")
    controller.handle_key("text:z")
    _type(controller, "5-")
    controller.handle_key("enter")

    assert "zaznaczono 2" in _frame(controller)


def test_an_unreadable_range_says_how_to_type_it_and_escape_closes_the_prompt() -> None:
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((_choice("4"),))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    controller.handle_key("text:z")
    _type(controller, "-")
    controller.handle_key("enter")

    assert "zakres: podaj np. 4-10" in _frame(controller)
    assert controller._marked == set()

    controller.handle_key("text:z")
    controller.handle_key("escape")
    assert "zakres (np. 4-10)" in _frame(controller)
    assert not any(span.style == "reverse" for span in controller.render(120, 30).spans)
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
    controller.handle_key("enter")
    controller.handle_key("space")
    controller.handle_key("escape")
    before: str = _frame(controller)
    controller.handle_key("text:s")
    after: str = _frame(controller)

    assert before.index("Fresh") < before.index("Seeded")
    assert after.index("Seeded") < after.index("Fresh")
    assert len(searches) == 1
    assert "S najnowsze" in after
    assert controller._rows[next(iter(controller._marked))].choice is fresh.choices[0]
    controller.handle_key("enter")
    assert "Pobierz (1)" in _frame(controller)


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

    draft = controller.take_draft()
    assert draft is not None
    assert draft.order is not None
    assert draft.order.query == "Solo Leveling SubsPlease"
    assert draft.order.context == context
    assert draft.order.anilist_id == candidate.anilist_id
    assert recorded == []


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


def test_explicit_download_sends_the_chosen_release_into_the_flat_library() -> None:
    sent: list[int] = []
    candidate: TitleCandidate = _title("Ore dake Level Up na Ken", english="Solo Leveling")

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        sent.append(len(choices))
        return DownloadReceipt(len(choices), Path("workspace"))

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
    controller.handle_key("space")
    controller.handle_key("text:d")
    _settle(controller)

    assert sent == [1]
    assert "Wysłano 1 do qBittorrenta → workspace" in _frame(controller)


def test_a_finished_title_opens_unchecked_releases_with_explicit_select_all() -> None:
    controller: AnimeController = _controller(
        _service(
            extra={
                "find_titles": lambda text: (_title(status=TitleStatus.FINISHED),),
                "search_title": lambda chosen, **options: _catalog((_choice("1"),)),
            }
        )
    )
    _chosen(controller)
    controller.handle_key("enter")
    listed: str = _frame(controller)

    assert "Zaznacz wszystkie" in listed
    assert "[x]" not in listed
    assert "Pobierz (0)" in listed


@pytest.mark.parametrize("size", [(80, 24), (120, 40), (40, 6)])
@pytest.mark.parametrize("blur", ["escape", "interrupt"])
def test_application_explicit_query_focus_edits_then_returns_home_with_the_draft(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int], blur: str
) -> None:
    application: interactive_app._InteractiveApplication = _application(
        monkeypatch, _service(search=lambda query: _catalog(()))
    )
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    application._resident = cast("ResidentSession", SimpleNamespace())
    application._show_state()
    application._handle_key("left")
    application._handle_key("left")
    assert application._state is not None
    panel: StateController = application._state
    assert panel._anime is not None
    anime: AnimeController = panel._anime
    try:
        assert not any(span.style == "reverse" for span in application._render_frame(*size).spans)
        for key in ("text:d", "text:o", "paste:ignored"):
            application._handle_key(key)
        assert anime._query == ""
        application._handle_key("enter")
        assert anime._worker is None
        assert any(span.style == "reverse" for span in application._render_frame(*size).spans)
        for key in ("text:osh", "left", "text:x", "backspace", "right", "text:i"):
            application._handle_key(key)
        assert anime._query == "oshi"
        assert panel._tab == 0
        application._handle_key(blur)
        assert _mode(application) is interactive_app._ViewMode.STATE
        assert anime._query == "oshi"
        opened: str = application._render_frame(*size).plain
        assert not any(span.style == "reverse" for span in application._render_frame(*size).spans)
        assert "Enter edytuj" in opened
        assert len(opened.splitlines()) <= size[1]
        assert all(Text(line).cell_len <= size[0] for line in opened.splitlines())
        for leave, destination, back in (("left", 3, "right"), ("right", 1, "left")):
            application._handle_key(leave)
            assert panel._tab == destination
            application._handle_key(back)
            assert panel._tab == 0
            assert application._render_frame(*size).plain == opened
        for leave, back in (("tab", "backtab"), ("backtab", "tab")):
            application._handle_key("enter")
            application._handle_key("select-all")
            application._handle_key(leave)
            application._handle_key(back)
            assert application._render_frame(*size).plain == opened
        assert anime._worker is None
        assert panel._draft is None
        application._handle_key(blur)
        assert _mode(application) is interactive_app._ViewMode.HOME
        assert anime._query == "oshi"
    finally:
        panel.close()
        panel._thread.join(5)


def test_application_focused_query_uses_shared_shortcuts_and_submits_only_on_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    searched: list[str] = []

    def search(query: str) -> ReleaseCatalog:
        searched.append(query)
        return _catalog((_choice("1"),))

    application: interactive_app._InteractiveApplication = _application(monkeypatch, _service(search=search))
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    application._resident = cast("ResidentSession", SimpleNamespace(find_titles=lambda title: (), search=search))
    application._show_state()
    assert application._state is not None
    panel: StateController = application._state
    assert panel._anime is not None
    anime: AnimeController = panel._anime
    clipboard: Application[None] = Application(input=DummyInput(), output=DummyOutput())
    try:
        with set_app(clipboard):
            for key in ("left", "left", "enter", "text:old title", "select-all", "interrupt", "cut"):
                application._handle_key(key)
            assert anime._query == ""
            assert anime.input_focused
            assert clipboard.clipboard.get_data().text == "old title"
            assert _mode(application) is interactive_app._ViewMode.STATE
            application._handle_key("paste")
            assert anime._query == "old title"
            for key in ("ctrl-shift-left", "text:anime", "undo"):
                application._handle_key(key)
            assert anime._query == "old title"
            application._handle_key("redo")
            assert anime._query == "old anime"
            for key in ("home", "ctrl-right", "ctrl-backspace"):
                application._handle_key(key)
            assert anime._query == "anime"
            for key in ("end", "text: extra", "ctrl-left", "ctrl-delete", "backspace"):
                application._handle_key(key)
            assert anime._query == "anime"
            assert searched == []
            assert panel._tab == 0
            application._handle_key("enter")
            _settle(anime)
            assert searched == ["anime"]
            assert not anime.input_focused
            assert not any(span.style == "reverse" for span in application._render_frame(80, 24).spans)
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.parametrize(("leave", "back"), [("tab", "backtab"), ("backtab", "tab")])
def test_application_tab_cancels_pending_search_and_returns_to_an_idle_draft(
    monkeypatch: pytest.MonkeyPatch, leave: str, back: str
) -> None:
    entered: threading.Event = threading.Event()
    release: threading.Event = threading.Event()

    def search(query: str) -> ReleaseCatalog:
        del query
        entered.set()
        assert release.wait(5)
        return _catalog((_choice("1"),))

    application: interactive_app._InteractiveApplication = _application(monkeypatch, _service(search=search))
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    application._resident = cast("ResidentSession", SimpleNamespace(find_titles=lambda title: (), search=search))
    application._show_state()
    assert application._state is not None
    panel: StateController = application._state
    assert panel._anime is not None
    anime: AnimeController = panel._anime
    worker: threading.Thread | None = None
    try:
        for key in ("left", "left", "enter", "text:oshi", "enter"):
            application._handle_key(key)
        assert entered.wait(5)
        worker = anime._worker
        application._handle_key(leave)
        application._handle_key(back)
        before: str = application._render_frame(80, 24).plain
        assert "oshi" in before
        assert not any(span.style == "reverse" for span in application._render_frame(80, 24).spans)
        release.set()
        assert worker is not None
        worker.join(5)
        assert not worker.is_alive()
        application._handle_idle()
        assert application._render_frame(80, 24).plain == before
        application._handle_key("enter")
        assert anime.input_focused
        assert anime._worker is None
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        panel.close()
        panel._thread.join(5)


def test_an_interrupt_inside_panel_search_rejects_late_results(monkeypatch: pytest.MonkeyPatch) -> None:
    release: threading.Event = threading.Event()

    def search(query: str) -> ReleaseCatalog:
        del query
        assert release.wait(timeout=5)
        return _catalog((_choice("11"),))

    application: interactive_app._InteractiveApplication = _application(monkeypatch, _service(search=search))
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller: AnimeController = _controller(application._service)
    panel.attach_anime(controller)
    application._state = panel
    application._show_state()
    application._handle_key("left")
    application._handle_key("left")

    assert controller is not None
    _type(controller, "oshi")
    application._handle_key("enter")
    worker: threading.Thread | None = controller._worker

    application._handle_key("interrupt")
    assert _mode(application) is interactive_app._ViewMode.STATE
    application._handle_key("interrupt")
    release.set()
    assert worker is not None
    worker.join(timeout=5)

    assert _mode(application) is interactive_app._ViewMode.HOME
    assert controller._rows == ()
    panel.close()
    panel._thread.join(5)


@pytest.mark.parametrize("bulk", ["text:a", "text:z"])
def test_explicit_variant_replaces_previous_and_bulk_preserves_it(bulk: str) -> None:
    first: ReleaseChoice = _choice("1")
    second: ReleaseChoice = replace(
        first,
        release=replace(first.release, info_hash="variant", title="Alternative release"),
        name=replace(first.name, version=2),
    )
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((first, second, _choice("2")))))
    _type(controller, "oshi")
    controller.handle_key("enter")
    _settle(controller)
    for key in ("enter", "enter", "down", "enter"):
        controller.handle_key(key)
    assert "Zmieniono wersję" in _frame(controller)
    controller.handle_key(bulk)
    if bulk == "text:z":
        controller.handle_key("text:1-2")
        controller.handle_key("enter")
    assert {controller._rows[index].choice for index in controller._marked} == {second, _choice("2")}
    assert "pominięto alternatywy: 1" in _frame(controller)
    assert "v2" in _frame(controller)


@pytest.mark.parametrize("height", [3, 5, 8, 10])
def test_low_picker_keeps_selected_action_visible(height: int) -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog(tuple(_choice(str(n)) for n in range(20))))
    )
    controller.handle_key("enter")
    controller.handle_key("text:oshi")
    controller.handle_key("enter")
    _settle(controller)
    for key in ("enter", "end", "up"):
        controller.handle_key(key)
    frame: str = controller.render(80, height).plain
    assert "\u276f Pobierz (0)" in frame
    assert len(frame.splitlines()) <= height


@pytest.mark.parametrize("height", [5, 8, 10, 12, 16, 19, 20, 24])
def test_range_editor_remains_visible_with_twenty_releases(height: int) -> None:
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog(tuple(_choice(str(n)) for n in range(1, 21))))
    )
    for key in ("enter", "text:oshi", "enter"):
        controller.handle_key(key)
    _settle(controller)
    for key in ("enter", "text:z", "text:4-10"):
        controller.handle_key(key)
    frame: str = controller.render(80, height).plain
    assert "zakres (np. 4-10): 4-10 " in frame
    assert any(span.style == "reverse" for span in controller.render(80, height).spans)
    assert "Enter zatwierdź" in frame
    assert len(frame.splitlines()) <= height
    controller.handle_key("enter")
    assert len(controller._marked) == 7


def test_range_editor_is_visible_inside_production_panel_at_80_by_24(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: AnimeController = _controller(
        _service(search=lambda query: _catalog(tuple(_choice(str(n)) for n in range(1, 21))))
    )
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel.attach_anime(controller)
    try:
        for key in ("left", "left", "enter", "text:oshi", "enter"):
            panel.handle_key(key)
        _settle(controller)
        for key in ("enter", "text:z", "text:4-10"):
            panel.handle_key(key)
        frame: str = panel.render(80, 24).plain
        assert "zakres (np. 4-10): 4-10 " in frame
        assert any(span.style == "reverse" for span in panel.render(80, 24).spans)
        assert "Enter zatwierdź" in frame
        assert len(frame.splitlines()) <= 24
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.parametrize("admitted", [0, 2])
def test_stale_download_notice_counts_already_recorded_choices(admitted: int) -> None:
    choices: tuple[ReleaseChoice, ...] = tuple(_choice(str(n)) for n in range(1, 4))
    calls: list[object] = []

    def call(kind: str, payload: Mapping[str, object], **options: object) -> Mapping[str, object]:
        del options
        if kind == "acquisition":
            return {"items": []} if payload["operation"] == "titles" else encode_view(_catalog(choices))
        assert kind == "download"
        calls.append(payload["choices"])
        return encode_view(DownloadReceipt(admitted, Path("workspace")))

    client: ControlClient = cast("ControlClient", SimpleNamespace(call=call))
    session: ResidentSession = ResidentSession(Path("workspace"), lambda: client)
    controller: AnimeController = AnimeController(_service(), lambda: None, resident=session)
    for key in ("enter", "text:oshi", "enter"):
        controller.handle_key(key)
    _settle(controller)
    for key in ("enter", "text:a", "text:d"):
        controller.handle_key(key)
    _settle(controller)
    notice: str | None = controller.take_downloaded()
    assert notice is not None
    assert f"już zapisane: {3 - admitted}" in notice
    assert (f"Przyjęto {admitted}" in notice) if admitted else "Zamówienia już zapisane" in notice
    assert not controller._marked
    controller.handle_key("any")
    controller.handle_key("text:d")
    assert calls == [[encode_view(choice) for choice in choices]]


def test_equal_sized_same_version_releases_show_available_date_and_title() -> None:
    first: ReleaseChoice = _choice("1")
    first = replace(
        first, release=replace(first.release, title="Edition Alpha", published=datetime(2026, 9, 1, tzinfo=UTC))
    )
    second: ReleaseChoice = replace(
        first,
        release=replace(
            first.release, info_hash="different", title="Edition Beta", published=datetime(2026, 9, 2, tzinfo=UTC)
        ),
    )
    controller: AnimeController = _controller(_service(search=lambda query: _catalog((first, second))))
    controller.handle_key("enter")
    controller.handle_key("text:oshi")
    controller.handle_key("enter")
    _settle(controller)
    controller.handle_key("enter")
    frame: str = controller.render(120, 24).plain
    assert "Edition Alpha" in frame
    assert "Edition Beta" in frame
    assert "01.09.2026" in frame
    assert "02.09.2026" in frame


@pytest.mark.parametrize("state", ["accepted", "uncertain", "complete", "failed"])
def test_owner_refresh_clears_marks_and_blocks_fresh_selection(
    paused_anime: tuple[StateController, AnimeController, _PausedClient], state: str
) -> None:
    panel, anime, client = paused_anime
    _paused_download(panel, anime)
    panel.handle_key("escape")
    panel._receive(
        panel._parent,
        {
            "event": "state_changed",
            "payload": {"acquisitions": [{"info_hash": _choice("10").release.info_hash, "state": state}]},
        },
    )
    assert not anime._marked
    panel.handle_key("enter")
    panel.handle_key("text:a")
    assert all(anime._rows[index].choice != _choice("10") for index in anime._marked)
    assert client.downloads == []


@pytest.mark.parametrize("leave", [None, "escape", "tab"])
def test_explicit_download_completion_navigates_only_current_visible_panel_on_idle(
    monkeypatch: pytest.MonkeyPatch, leave: str | None
) -> None:
    released: threading.Event = threading.Event()
    sent: list[ReleaseChoice] = []

    def download(choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        sent.extend(choices)
        assert released.wait(5)
        return DownloadReceipt(len(choices), Path("workspace"))

    service: AppService = _service(search=lambda query: _catalog((_choice("1"),)), download=download)
    application: interactive_app._InteractiveApplication = _application(monkeypatch, service)
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    anime: AnimeController = _controller(service)
    panel.attach_anime(anime)
    application._state = panel
    application._show_state()
    try:
        for key in ("left", "left", "enter", "text:oshi", "enter"):
            application._handle_key(key)
        _settle(anime)
        for key in ("enter", "enter"):
            application._handle_key(key)
        assert sent == []
        for key in ("end", "up", "enter"):
            application._handle_key(key)
        worker: threading.Thread | None = anime._worker
        if leave is not None:
            application._handle_key(leave)
        released.set()
        assert worker is not None
        worker.join(5)
        application._handle_idle()
        assert (panel._tab == 2) is (leave is None)
        assert sent == [_choice("1")]
        if leave is None:
            assert "Wysłano 1" in panel.render(120, 40).plain
            assert not anime._marked
            application._handle_key("left")
            application._handle_idle()
            assert panel._tab == 1
    finally:
        released.set()
        panel.close()
        panel._thread.join(5)
