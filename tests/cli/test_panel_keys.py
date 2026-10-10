from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time
from types import SimpleNamespace
from typing import Final, cast

import pytest
import test_anime_episodes as episodes
import test_subscription_draft as drafts
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from rich.text import Text
from test_interactive_mouse import _application, _click, _row_at, _row_of
from test_interactive_state import _live_material, _live_snapshot

from anishift.application import (
    AppService,
    EntryGroup,
    EpisodeKey,
    EpisodeOfferView,
    EpisodeStatus,
    FranchiseEntry,
    HistoryEvent,
    HistoryKind,
    ListedEpisode,
    RunEvent,
    RunEventKind,
    TaskState,
    TitleCandidate,
    TitleStatus,
)
from anishift.application.control_views import (
    LibraryFile,
    LibraryFileIdentity,
    LibrarySet,
    RetryProposal,
    RunProgressSnapshot,
    encode_view,
)
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.actions import Action, ScreenActions, footer_segments, pack_footer
from anishift.cli.interactive.anime import AnimeController, _Screen
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeViewState
from anishift.cli.interactive.pointer import CRUMB_SEPARATOR, Click, ClickKind, FrameSelection
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.state import StateController, StateResult, _Tab
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_KEYS: Final[tuple[str, ...]] = (
    *(f"text:{letter}" for letter in "abcdefghijklmnopqrstuvwxyz"),
    "space",
    "enter",
    "delete",
    "text:/",
    "text:?",
)

_EVERYWHERE: Final[frozenset[str]] = frozenset({"text:o", "text:?"})

_PANEL: Final[tuple[Action, ...]] = (("M", "ręczny"), ("U", "ustawienia"))

_EPISODE_MORE: Final[tuple[Action, ...]] = (("I", "wydania"), ("Z", "zakres"), ("A", "wszystkie"), ("P", "ponownie"))

_LISTED: Final[tuple[Action, ...]] = (("/", "szukaj"), ("C", "kopiuj"))

_U08: Final[tuple[Action, ...]] = (
    ("Space", "zaznacz"),
    ("D", "pobierz"),
    ("W", "wstrzymaj"),
    ("R", "sprawdź teraz"),
    ("X", "usuń"),
    *_EPISODE_MORE,
    ("S", "subskrybuj"),
    *_LISTED,
)

_HASH: Final[str] = "a" * 40

_FILE: Final[LibraryFileIdentity] = LibraryFileIdentity("ready/Slime.pl.mkv", 10, 1, 2, 3)


@dataclass
class _Probe:
    panel: StateController
    owner: object
    work: list[object]
    copied: list[str]

    @property
    def anime(self) -> AnimeController:
        anime: AnimeController | None = self.panel._anime
        assert anime is not None
        return anime


class _Library:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def new_session(self) -> _Library:
        return self

    def close(self) -> None:
        return

    def interrupt_reads(self) -> None:
        return

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        self.calls.append((kind, payload))
        return {"subscriptions": []}

    def library_details(self, set_id: str) -> LibrarySet:
        self.calls.append(("details", set_id))
        return _details_view()

    def library_file(self, set_id: str, identity: LibraryFileIdentity) -> Path:
        self.calls.append(("file", identity))
        return Path(identity.path)

    def library_result(self, set_id: str) -> Path:
        self.calls.append(("result", set_id))
        return Path(set_id)


class _SubscriptionOwner(drafts._Owner):
    def __init__(self) -> None:
        super().__init__()
        self.offer_view: EpisodeOfferView | None = None

    def episode_offer_start(self, key: EpisodeKey, *, repeat: bool = False, command_id: str) -> Mapping[str, object]:
        del command_id
        self.calls.append(("repeat" if repeat else "offer", key.number))
        self.offer_view = EpisodeOfferView("offer", "fixture", episodes._offer(key))
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


def _details_view() -> LibrarySet:
    return LibrarySet(
        "set",
        "group",
        "Slime",
        None,
        _FILE.path,
        (
            LibraryFile(_FILE.path, "product", "MKV", _FILE),
            LibraryFile("ready/Slime.mkv", "source", "MKV", LibraryFileIdentity("ready/Slime.mkv", 9, 1, 2, 4)),
        ),
        True,
    )


def _probe(
    monkeypatch: pytest.MonkeyPatch,
    owner: object,
    anime: AnimeController | None = None,
    subscriptions: tuple[Mapping[str, object], ...] = (),
) -> _Probe:
    panel: StateController = StateController(cast("ResidentSession", owner), lambda: None)
    panel._connected = True
    panel._notice = ""
    panel._snapshot = {"auto_enabled": True}
    panel._subscriptions = list(subscriptions)
    work: list[object] = []
    copied: list[str] = []
    monkeypatch.setattr(panel, "_work", lambda action, **options: work.append(action))

    def copy(text: str) -> bool:
        copied.append(text)
        return True

    if anime is not None:
        panel.attach_anime(anime)
        anime._panel._clipboard = copy
    return _Probe(panel, owner, work, copied)


def _catalogue(owner: episodes._ChoiceOwner) -> AnimeController:
    owner.release.set()
    return AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )


def _anime_probe(monkeypatch: pytest.MonkeyPatch, owner: episodes._ChoiceOwner, *keys: str) -> _Probe:
    anime: AnimeController = _catalogue(owner)
    probe: _Probe = _probe(monkeypatch, owner, anime)
    probe.panel._tab = _Tab.ANIME
    for key in keys:
        probe.panel.handle_key(key)
        episodes._settle(anime)
    return probe


def _query(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _anime_probe(monkeypatch, episodes._ChoiceOwner())


def _titles(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    owner: episodes._ChoiceOwner = episodes._ChoiceOwner()
    other: TitleCandidate = TitleCandidate(
        99, "Other Show", "Other Show", None, (), 2020, None, "TV", 12, TitleStatus.FINISHED, ()
    )
    owner.titles = (episodes._title(), other)
    probe: _Probe = _anime_probe(monkeypatch, owner, "text:/", "text:slime", "enter")
    assert probe.anime._screen is _Screen.TITLES
    return probe


def _entries(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _anime_probe(monkeypatch, episodes._ChoiceOwner(), "text:/", "text:slime", "enter")
    assert probe.anime._screen is _Screen.ENTRIES
    return probe


def _episodes_at(monkeypatch: pytest.MonkeyPatch, row: int, owner: episodes._ChoiceOwner | None = None) -> _Probe:
    probe: _Probe = _anime_probe(
        monkeypatch, owner or episodes._ChoiceOwner(), "text:/", "text:slime", "enter", "enter"
    )
    assert probe.anime._screen is _Screen.EPISODES
    probe.anime._positions[_Screen.EPISODES] = row
    return probe


def _episodes(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _episodes_at(monkeypatch, 2)


def _episodes_file(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _episodes_at(monkeypatch, 1)


def _episodes_ordered(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _episodes_at(monkeypatch, 0)


def _episodes_airing(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    owner: episodes._ChoiceOwner = episodes._ChoiceOwner()
    now: datetime = datetime.now(UTC)
    owner.listing = replace(
        episodes._listing(),
        status="RELEASING",
        episodes=tuple(
            ListedEpisode(
                number, f"Episode {number}", aired=number <= 3, airs_at=now + timedelta(days=7 * (number - 3))
            )
            for number in range(1, 7)
        ),
    )
    return _episodes_at(monkeypatch, 2, owner)


def _candidates(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _episodes(monkeypatch)
    probe.panel.handle_key("text:i")
    episodes._settle(probe.anime)
    assert probe.anime._screen is _Screen.CANDIDATES
    return probe


def _files(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _episodes_file(monkeypatch)
    probe.panel.handle_key("enter")
    episodes._settle(probe.anime)
    assert probe.anime._files is not None
    return probe


def _draft(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _episodes_airing(monkeypatch)
    probe.panel.handle_key("text:s")
    episodes._settle(probe.anime)
    assert probe.anime._screen is _Screen.DRAFT
    return probe


def _busy(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _episodes(monkeypatch)
    probe.anime._busy = "Wczytuję odcinki…"
    probe.anime._busy_return = _Screen.ENTRIES
    probe.anime._screen = _Screen.BUSY
    return probe


def _problem(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _episodes(monkeypatch)
    probe.anime._problem = "Źródło wydań nie odpowiada"
    probe.anime._problem_return = _Screen.EPISODES
    probe.anime._screen = _Screen.PROBLEM
    return probe


def _subscription(monkeypatch: pytest.MonkeyPatch, owner: drafts._Owner | None = None) -> _Probe:
    owner = owner or _SubscriptionOwner()
    drafts._details(owner)
    anime: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    probe: _Probe = _probe(monkeypatch, owner, anime, (drafts._row("a", "Alpha"),))
    probe.panel._tab = _Tab.SUBSCRIPTIONS
    probe.panel.handle_key("enter")
    drafts._settle(probe.panel)
    assert anime._screen is _Screen.EPISODES
    assert anime._subscription is not None
    return probe


def _u08(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _subscription(monkeypatch)


def _u08_ordered(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _subscription(monkeypatch)
    probe.anime._episode_states[EpisodeKey(1, 1)] = EpisodeStatus(EpisodeKey(1, 1), "ordered")
    return probe


def _u08_waiting(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _subscription(monkeypatch)
    probe.anime._episode_states[EpisodeKey(1, 1)] = drafts._due(1, polish_wait_until=drafts._WAITS)
    return probe


def _u08_extra(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    owner: drafts._Owner = _SubscriptionOwner()
    owner.extras = (
        FranchiseEntry(
            9, "Slime OVA", "Slime OVA", None, "OVA", "FINISHED", 2025, None, "SIDE_STORY", EntryGroup.EXTRA
        ),
    )
    owner.listings[9] = replace(drafts._listing("FINISHED", episodes=drafts._weekly(1, 1), count=1), anilist_id=9)
    probe: _Probe = _subscription(monkeypatch, owner)
    probe.panel.handle_key("end")
    return probe


def _list_probe(
    monkeypatch: pytest.MonkeyPatch, tab: int, snapshot: Mapping[str, object], *rows: Mapping[str, object]
) -> _Probe:
    owner: drafts._Owner = drafts._Owner()
    anime: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    probe: _Probe = _probe(monkeypatch, owner, anime, rows)
    probe.panel._tab = tab
    probe.panel._snapshot = {"auto_enabled": True, **snapshot}
    return probe


def _subscriptions(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.SUBSCRIPTIONS, {}, drafts._row("a", "Alpha"))


def _subscriptions_empty(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.SUBSCRIPTIONS, {})


def _download(info_hash: str = "hash", material: str = "one") -> dict[str, object]:
    return {
        "material_id": material,
        "acquisition_id": material,
        "info_hash": info_hash,
        "stage": "download",
        "acquisition_state": "accepted",
        "state": "downloading",
        "name": f"{material}.mkv",
        "progress": 0.5,
    }


def _run(run_id: str = "run", group: str = "group") -> dict[str, object]:
    return {
        "material_id": group,
        "group_id": group,
        "name": f"{group}.mkv",
        "stage": "processing",
        "state": "running",
        "run_id": run_id,
        "group_ids": [group],
    }


def _processing_download(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.PROGRESS, {"materials": [_download()]})


def _processing_run(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(
        monkeypatch, _Tab.PROGRESS, {"materials": [_run()], "requests": [{"request_id": "run", "state": "running"}]}
    )


def _processing_empty(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.PROGRESS, {})


def _history(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _list_probe(monkeypatch, _Tab.PROGRESS, {})
    probe.panel._history_open = True
    probe.panel._history_items = (
        HistoryEvent("event", "material", "operation", "2026-10-09T20:15:00+00:00", HistoryKind.SUCCESS, "Slime"),
    )
    return probe


def _event(material: str) -> HistoryEvent:
    return HistoryEvent(
        f"event-{material}", material, "operation", "2026-10-09T20:15:00+00:00", HistoryKind.SUCCESS, material
    )


def _library(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.FILES, {"library": [{"set_id": "set", "name": "Slime"}]})


def _library_relocation(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(
        monkeypatch,
        _Tab.FILES,
        {"library": [{"set_id": "set", "name": "Slime"}], "relocations": [{"name": "Slime", "problem": "busy"}]},
    )


def _library_details(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    probe: _Probe = _library(monkeypatch)
    probe.panel._details = _details_view()
    probe.panel._detail_selection = 0
    probe.panel._selected = 2
    return probe


def _library_empty(monkeypatch: pytest.MonkeyPatch) -> _Probe:
    return _list_probe(monkeypatch, _Tab.FILES, {})


_FIXTURES: Final[dict[str, Callable[[pytest.MonkeyPatch], _Probe]]] = {
    "query": _query,
    "titles": _titles,
    "entries": _entries,
    "episodes": _episodes,
    "episodes_file": _episodes_file,
    "episodes_ordered": _episodes_ordered,
    "episodes_airing": _episodes_airing,
    "candidates": _candidates,
    "files": _files,
    "draft": _draft,
    "busy": _busy,
    "problem": _problem,
    "u08": _u08,
    "u08_ordered": _u08_ordered,
    "u08_waiting": _u08_waiting,
    "u08_extra": _u08_extra,
    "subscriptions": _subscriptions,
    "subscriptions_empty": _subscriptions_empty,
    "processing_download": _processing_download,
    "processing_run": _processing_run,
    "processing_empty": _processing_empty,
    "history": _history,
    "library": _library,
    "library_relocation": _library_relocation,
    "library_details": _library_details,
    "library_empty": _library_empty,
}

_ACTIONS: Final[dict[str, tuple[Action, ...]]] = {
    "titles": (("Enter", "wybierz"), ("S", "subskrybuj"), *_LISTED),
    "entries": (("Enter", "odcinki"), ("S", "subskrybuj"), *_LISTED),
    "episodes": (("Space", "zaznacz"), ("D", "pobierz"), ("S", "subskrybuj"), *_EPISODE_MORE, *_LISTED),
    "episodes_file": (
        ("Enter", "wskaż plik"),
        ("Space", "zaznacz"),
        ("D", "pobierz"),
        ("S", "subskrybuj"),
        *_EPISODE_MORE,
        *_LISTED,
    ),
    "candidates": (("Space", "zaznacz"), ("D", "pobierz"), *_LISTED),
    "files": (("Enter", "wybierz"), *_LISTED),
    "draft": (("Enter", "wybierz"), ("Space", "zaznacz"), ("A", "wszystkie"), *_LISTED),
    "busy": (("C", "kopiuj"),),
    "problem": (("Enter", "wróć"), ("C", "kopiuj")),
    "u08": _U08,
    "u08_waiting": (_U08[0], _U08[1], ("T", "pobierz teraz"), *_U08[2:]),
    "u08_extra": (("Enter", "otwórz"), *_U08),
    "subscriptions": (
        ("Enter", "szczegóły"),
        ("D lub /", "dodaj"),
        ("W", "wstrzymaj"),
        ("R", "sprawdź teraz"),
        ("X", "usuń"),
        ("Ctrl+Z", "cofnij"),
        *_PANEL,
    ),
    "subscriptions_empty": (("D lub /", "dodaj pierwszą"), ("Ctrl+Z", "cofnij"), *_PANEL),
    "processing_download": (("W", "wstrzymaj"), ("X", "anuluj"), ("H", "historia"), *_PANEL),
    "processing_run": (("X", "anuluj"), ("H", "historia"), *_PANEL),
    "processing_empty": (("H", "historia"), *_PANEL),
    "history": (("Enter", "otwórz"), ("P", "ponów"), ("/", "szukaj"), ("H", "zamknij"), *_PANEL),
    "library": (("Enter", "otwórz"), ("F", "folder"), ("X", "usuń"), ("Ctrl+Z", "cofnij"), *_PANEL),
    "library_relocation": (
        ("Enter", "otwórz"),
        ("F", "folder"),
        ("X", "usuń"),
        ("Ctrl+Z", "cofnij"),
        ("P", "ponów przenoszenie"),
        *_PANEL,
    ),
    "library_details": (("Enter", "otwórz plik"), ("F", "folder"), ("X", "usuń"), ("Ctrl+Z", "cofnij"), *_PANEL),
    "library_empty": (("Ctrl+Z", "cofnij"), *_PANEL),
}

_ALIASES: Final[dict[str, frozenset[str]]] = {
    "u08": frozenset({"text:f", "delete"}),
    "u08_waiting": frozenset({"text:f", "delete"}),
    "u08_extra": frozenset({"text:f", "delete"}),
    "subscriptions": frozenset({"text:f", "space", "delete"}),
    "subscriptions_empty": frozenset({"enter"}),
    "processing_download": frozenset({"text:c", "delete"}),
    "processing_run": frozenset({"text:c", "delete"}),
    "processing_empty": frozenset({"text:c", "delete"}),
    "history": frozenset({"text:s"}),
    "library": frozenset({"text:d", "delete"}),
    "library_relocation": frozenset({"text:d", "delete"}),
    "library_details": frozenset({"delete"}),
    "library_empty": frozenset({"text:d", "delete"}),
}

_APPLIES: Final[dict[tuple[str, str], str]] = {
    ("episodes", "text:p"): "episodes_ordered",
    ("episodes", "text:s"): "episodes_airing",
    ("episodes_file", "space"): "episodes",
    ("episodes_file", "text:d"): "episodes",
    ("episodes_file", "text:s"): "episodes_airing",
    ("u08", "text:p"): "u08_ordered",
    ("u08_waiting", "text:p"): "u08_ordered",
    ("u08_extra", "space"): "u08",
    ("u08_extra", "text:d"): "u08",
    ("u08_extra", "text:i"): "u08",
    ("u08_extra", "text:p"): "u08_ordered",
}

_FOOTERS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "query": ("Enter szukaj · Esc wróć", ()),
    "titles": ("Enter wybierz · S subskrybuj · ? więcej · Esc wróć", ()),
    "entries": ("Enter odcinki · S subskrybuj · ? więcej · Esc wróć", ()),
    "episodes": ("Space zaznacz · D pobierz · S subskrybuj · ? więcej · Esc wróć", ()),
    "candidates": ("Space zaznacz · D pobierz · ? więcej · Esc wróć", ()),
    "files": ("Enter wybierz · ? więcej · Esc wróć", ()),
    "draft": ("Enter wybierz · Space zaznacz · ? więcej · Esc wróć", ()),
    "u08": ("Space zaznacz · D pobierz · W wstrzymaj · ? więcej · Esc wróć", ()),
    "u08_waiting": ("Space zaznacz · D pobierz · T pobierz teraz · ? więcej · Esc wróć", ()),
    "subscriptions": ("Enter szczegóły · D lub / dodaj · W wstrzymaj · ? więcej · Esc wróć", ()),
    "subscriptions_empty": ("D lub / dodaj pierwszą · ? więcej · Esc wróć", ()),
    "processing_download": ("W wstrzymaj · X anuluj · H historia · ? więcej · Esc wróć", ()),
    "processing_run": ("X anuluj · H historia · ? więcej · Esc wróć", ()),
    "history": ("Enter otwórz · P ponów · / szukaj · ? więcej · Esc wróć", ()),
    "library": ("Enter otwórz · F folder · X usuń · ? więcej · Esc wróć", ()),
    "library_details": ("Enter otwórz plik · F folder · X usuń · Esc wróć", ()),
    "episodes_details": ("C kopiuj · Esc wróć", ("text:?",)),
    "u08_details": ("C kopiuj · Esc wróć", ("text:?",)),
    "subscriptions_help": ("Esc wróć", ("text:?",)),
    "problem": ("Enter/Esc wróć", ()),
}

_HELP_SCREENS: Final[tuple[str, ...]] = (
    "subscriptions",
    "subscriptions_empty",
    "processing_download",
    "processing_run",
    "processing_empty",
    "history",
    "library_empty",
)

_DETAIL_SCREENS: Final[tuple[str, ...]] = (
    "titles",
    "entries",
    "episodes",
    "candidates",
    "files",
    "draft",
    "u08",
)


@pytest.fixture
def build(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], _Probe]]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    built: list[StateController] = []

    def make(name: str) -> _Probe:
        base: str = name.removesuffix("_details") if name in {"episodes_details", "u08_details"} else name
        probe: _Probe = _FIXTURES[base.removesuffix("_help")](monkeypatch)
        built.append(probe.panel)
        probe.panel.render(80, 24)
        return probe

    yield make
    for panel in built:
        panel.close()
        panel._thread.join(5)


def _listed(probe: _Probe) -> tuple[Action, ...]:
    if probe.panel._tab == _Tab.ANIME:
        return probe.anime._screen_actions().listed
    return probe.panel._actions().listed


def _probe_keys(action: str) -> tuple[str, ...]:
    named: dict[str, str] = {"Enter": "enter", "Space": "space"}
    keys: list[str] = action.split(" lub ")
    return tuple(named.get(key, f"text:{key.lower()}") for key in keys if key in named or len(key) == 1)


def _state(probe: _Probe) -> tuple[object, ...]:
    panel: StateController = probe.panel
    anime: AnimeController | None = panel._anime
    calls: tuple[int, ...] = tuple(
        len(cast("list[object]", getattr(probe.owner, name, [])))
        for name in ("calls", "batches", "choices", "file_choices")
    )
    view: tuple[object, ...] = (
        ()
        if anime is None
        else (
            anime._screen,
            anime._highlighted,
            tuple(sorted(anime._positions.items())),
            frozenset(anime._episode_marks),
            frozenset(anime._view.selected),
            anime._details_open,
            anime._range_input is not None,
            anime._input_focused,
            frozenset(anime._draft_marks),
            anime._from_subscriptions,
            anime._subscription is not None,
            anime._pending_batch is not None,
            frozenset(anime._sending),
        )
    )
    return (
        panel._tab,
        panel._selected,
        panel._details is not None,
        panel._help,
        panel._history_open,
        panel._history_input is not None,
        panel._question,
        panel._retry is not None,
        len(probe.work),
        len(probe.copied),
        calls,
        view,
    )


def _changes(probe: _Probe, key: str) -> bool:
    before: tuple[object, ...] = _state(probe)
    result: StateResult = probe.panel.handle_key(key)
    if probe.panel._anime is not None:
        episodes._settle(probe.panel._anime)
    return result is not StateResult.CONTINUE or _state(probe) != before


def _footer(frame: str, golden: str) -> list[str]:
    lines: list[str] = [line.strip() for line in frame.splitlines()]
    end: int = max(index for index, line in enumerate(lines) if line and golden.endswith(line))
    start: int = end
    while start > 0 and lines[start - 1] and golden.endswith(" · ".join(lines[start - 1 : end + 1])):
        start -= 1
    return lines[start : end + 1]


@pytest.mark.parametrize("name", sorted(_ACTIONS))
def test_screen_actions_match_the_golden_sets(build: Callable[[str], _Probe], name: str) -> None:
    assert _listed(build(name)) == _ACTIONS[name]


@pytest.mark.parametrize("name", sorted(_FOOTERS))
def test_footers_match_the_golden_strings_at_80_columns(build: Callable[[str], _Probe], name: str) -> None:
    golden, keys = _FOOTERS[name]
    probe: _Probe = build(name)
    for key in keys:
        probe.panel.handle_key(key)
    lines: list[str] = [line.strip() for line in probe.panel.render(80, 24).plain.splitlines()]
    assert golden in lines


@pytest.mark.parametrize("name", sorted(_FOOTERS))
def test_footers_wrap_only_between_hints_at_50_columns(build: Callable[[str], _Probe], name: str) -> None:
    golden, keys = _FOOTERS[name]
    probe: _Probe = build(name)
    for key in keys:
        probe.panel.handle_key(key)
    footer: list[str] = _footer(probe.panel.render(50, 24).plain, golden)
    assert " · ".join(footer) == golden
    assert all(Text(line).cell_len <= 46 for line in footer)


def test_subscription_list_without_rows_says_so_once(build: Callable[[str], _Probe]) -> None:
    frame: str = build("subscriptions_empty").panel.render(80, 24).plain
    assert "Brak subskrypcji" in frame
    assert "D dodaj" not in frame


@pytest.mark.parametrize("name", sorted(set(_ACTIONS)))
def test_every_key_that_changes_a_screen_is_listed_or_an_alias(build: Callable[[str], _Probe], name: str) -> None:
    listed: set[str] = {key for action, _label in _ACTIONS[name] for key in _probe_keys(action)}
    allowed: set[str] = listed | _ALIASES.get(name, frozenset()) | _EVERYWHERE
    changed: list[str] = [key for key in _KEYS if _changes(build(name), key)]
    assert [key for key in changed if key not in allowed] == []


@pytest.mark.parametrize("name", sorted(_ACTIONS))
def test_every_listed_action_changes_a_screen_where_it_applies(build: Callable[[str], _Probe], name: str) -> None:
    keys: list[str] = [key for action, _label in _ACTIONS[name] for key in _probe_keys(action)]
    inert: list[str] = [key for key in keys if not _changes(build(_APPLIES.get((name, key), name)), key)]
    assert inert == []


@pytest.mark.parametrize(("name", "keys"), [(name, alias) for name, alias in sorted(_ALIASES.items())])
def test_every_alias_still_changes_its_screen(build: Callable[[str], _Probe], name: str, keys: frozenset[str]) -> None:
    applies: dict[str, str] = {"processing_empty": "processing_download", "library_empty": "library"}
    inert: list[str] = [key for key in sorted(keys) if not _changes(build(applies.get(name, name)), key)]
    assert inert == []


@pytest.mark.parametrize("name", _HELP_SCREENS)
def test_question_mark_opens_and_closes_the_help_block(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:?")
    assert probe.panel._help
    frame: str = probe.panel.render(80, 24).plain
    assert "Ten ekran" in frame
    assert "↑↓ wybierz · ←→ zakładki · Tab zakładki · O automat · Esc wróć" in frame
    probe.panel.handle_key("text:?")
    assert not probe.panel._help


@pytest.mark.parametrize("name", _DETAIL_SCREENS)
def test_question_mark_opens_and_closes_anime_details(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:?")
    assert probe.anime._details_open
    text: str = " ".join(item.title for item in probe.anime._view.items)
    assert "Ten ekran" in text
    assert "Wszędzie" in text
    probe.panel.handle_key("text:?")
    assert not probe.anime._details_open


def test_anime_help_lists_only_this_screen_without_aliases(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("candidates")
    probe.panel.handle_key("text:?")
    text: str = " ".join(item.title for item in probe.anime._view.items)
    assert "Space zaznacz · D pobierz · / szukaj · C kopiuj" in text
    assert "I " not in text.split("Ten ekran")[1]
    assert "Z zakres" not in text


def test_history_help_names_the_retention(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("history")
    probe.panel.handle_key("text:?")
    assert "Historia z ostatnich 30 dni" in probe.panel.render(80, 24).plain
    assert "ostatnie 30 dni" not in build("history").panel.render(80, 24).plain


@pytest.mark.parametrize("name", _HELP_SCREENS)
def test_help_block_ignores_actions_and_clicks(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:?")
    probe.panel._subscriptions = [drafts._row("a", "Alpha"), drafts._row("b", "Beta")]
    probe.panel._snapshot = {
        **probe.panel._snapshot,
        "materials": [_download(), _download("other", "two")],
        "library": [{"set_id": "one", "name": "One"}, {"set_id": "two", "name": "Two"}],
    }
    probe.panel._history_items = (_event("one"), _event("two"))
    assert len(probe.panel._entries(120)) >= 2
    selected: int = probe.panel._selected
    for key in _KEYS:
        if key in _EVERYWHERE:
            continue
        assert probe.panel.handle_key(key) is StateResult.CONTINUE
        assert probe.panel._help
    frame: Text = probe.panel.render(80, 24)
    probe.panel.select(1 - selected)
    assert probe.work == []
    assert probe.panel._selected == selected
    assert probe.panel._question is None
    assert all(_row_at(frame, row) is None for row in range(24))
    assert probe.panel.view_key()[-1] is True


def test_help_block_scrolls_closes_and_switches_tabs(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("subscriptions")
    probe.panel.handle_key("text:?")
    probe.panel.render(50, 12)
    probe.panel.handle_key("pagedown")
    assert probe.panel._help_offset == probe.panel._page
    probe.panel.handle_key("end")
    probe.panel.render(50, 12)
    last: int = probe.panel._help_offset
    assert last > 0
    probe.panel.handle_key("down")
    probe.panel.render(50, 12)
    assert probe.panel._help_offset == last
    probe.panel.handle_key("home")
    assert probe.panel._help_offset == 0
    probe.panel.scroll(1)
    assert probe.panel._help_offset == 3
    probe.panel.handle_key("text:o")
    assert len(probe.work) == 1
    assert probe.panel._help
    for key in ("escape", "backspace", "interrupt"):
        assert probe.panel.handle_key(key) is StateResult.CONTINUE
        assert not probe.panel._help
        probe.panel.handle_key("text:?")
    probe.panel.handle_key("tab")
    assert not probe.panel._help
    assert probe.panel._tab == _Tab.PROGRESS


def test_library_question_mark_opens_details_whose_keys_reach_the_right_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    opened: list[tuple[Path, bool]] = []
    monkeypatch.setattr(state_module, "_open_path", lambda path, *, show_folder: opened.append((path, show_folder)))
    owner: _Library = _Library()
    panel: StateController = StateController(cast("ResidentSession", owner), lambda: None)
    monkeypatch.setattr(panel, "_work", lambda action, **options: panel._perform(action, ""))
    panel._tab = _Tab.FILES
    panel._connected = True
    panel._snapshot = {"library": [{"set_id": "set", "name": "Slime"}]}
    try:
        panel.handle_key("text:?")
        assert panel._details is not None
        frame: str = panel.render(80, 24).plain
        assert "Ten ekran" in frame
        for _ in range(5):
            panel.handle_key("down")
            assert panel._selected < 4
        panel._selected = 2
        panel.handle_key("enter")
        panel._selected = 3
        panel.handle_key("text:f")
        assert [call for call in owner.calls if call[0] == "file"] == [
            ("file", _FILE),
            ("file", _details_view().files[1].identity),
        ]
        assert opened == [(Path(_FILE.path), False), (Path("ready/Slime.mkv"), True)]
        panel.handle_key("pagedown")
        assert panel._selected == 3
    finally:
        panel.close()
        panel._thread.join(5)


def test_library_details_drop_their_help_before_any_file_row(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("library_details")
    tall: str = probe.panel.render(80, 24).plain
    low: str = probe.panel.render(80, 9).plain
    assert "Wszędzie" in tall
    assert "Wszędzie" not in low
    assert "ready/Slime.mkv" in low


def test_arriving_library_details_close_the_help_block(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("library")
    probe.panel._connected = False
    probe.panel.handle_key("text:?")
    assert probe.panel._help
    probe.panel._show_details(cast("ResidentSession", _Library()), "set", probe.panel._view_generation)
    assert probe.panel._details is not None
    assert not probe.panel._help


@pytest.mark.parametrize("busy", [False, True])
def test_library_question_mark_without_a_readable_row_opens_help(build: Callable[[str], _Probe], *, busy: bool) -> None:
    probe: _Probe = build("library")
    probe.panel._busy = busy
    probe.panel._connected = busy
    probe.panel.handle_key("text:d")
    assert probe.panel._help
    assert probe.work == []


@pytest.mark.parametrize(
    ("key", "result"), [("text:m", StateResult.MANUAL), ("text:u", StateResult.SETTINGS), ("text:o", None)]
)
def test_library_details_reach_mode_keys_and_the_automat(
    build: Callable[[str], _Probe], key: str, result: StateResult | None
) -> None:
    probe: _Probe = build("library_details")
    answer: StateResult = probe.panel.handle_key(key)
    assert answer is (result or StateResult.CONTINUE)
    assert len(probe.work) == int(result is None)


@pytest.mark.parametrize("key", ["text:x", "delete"])
def test_library_details_delete_the_set_with_x_or_delete(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("library_details")
    probe.panel.handle_key(key)
    assert len(probe.work) == 1


@pytest.mark.parametrize("key", ["tab", "backtab", "left", "right"])
def test_library_details_close_and_switch_the_tab(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("library_details")
    probe.panel.handle_key(key)
    assert probe.panel._details is None
    assert probe.panel._tab == (_Tab.ANIME if key in {"tab", "right"} else _Tab.PROGRESS)
    assert probe.panel._positions[_Tab.FILES] == 0


@pytest.mark.parametrize("key", ["backspace", "text:?", "escape"])
def test_library_details_close_quietly(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("library_details")
    assert probe.panel.handle_key(key) is StateResult.CONTINUE
    assert probe.panel._details is None
    assert probe.panel._tab == _Tab.FILES


@pytest.mark.parametrize("name", ["episodes_details", "u08_details"])
def test_backspace_closes_anime_details(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:?")
    probe.panel.handle_key("backspace")
    assert not probe.anime._details_open
    assert probe.anime._screen is _Screen.EPISODES


def test_library_keeps_the_deletion_notice_until_the_next_move(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    owner: _Library = _Library()
    deleted: list[str] = []
    session: ResidentSession = cast(
        "ResidentSession",
        SimpleNamespace(
            preview_deletion=lambda set_id: set_id,
            delete_set=deleted.append,
            close=lambda: None,
            command=owner.command,
        ),
    )
    panel: StateController = StateController(
        cast("ResidentSession", SimpleNamespace(new_session=lambda: session)), lambda: None
    )
    monkeypatch.setattr(panel, "_work", lambda action, **options: panel._perform(action, ""))
    library: list[dict[str, str]] = [{"set_id": "one", "name": "One"}, {"set_id": "two", "name": "Two"}]
    panel._tab = _Tab.FILES
    panel._connected = True
    panel._snapshot = {"library": library}
    try:
        panel.handle_key("text:x")
        assert deleted == ["one"]
        assert "Usunięto · Ctrl+Z cofnij" in panel.render(80, 24).plain
        panel._receive(session, {"event": "state_changed", "payload": {"library": library[1:]}})
        assert "Usunięto · Ctrl+Z cofnij" in panel.render(80, 24).plain
        panel.handle_key("down")
        assert "Usunięto" not in panel.render(80, 24).plain
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.parametrize(("key", "kind"), [("text:r", "check"), ("text:f", "check"), ("text:w", "pause")])
@pytest.mark.parametrize("name", ["subscriptions", "u08"])
def test_subscription_keys_send_their_command(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, key: str, kind: str
) -> None:
    probe: _Probe = build(name)
    sent: list[str] = []
    monkeypatch.setattr(probe.panel, "_subscription_command", lambda command, row, number=None: sent.append(command))
    probe.panel.handle_key(key)
    assert sent == [f"subscription_{kind}"]


@pytest.mark.parametrize("key", ["text:x", "delete"])
@pytest.mark.parametrize("name", ["subscriptions", "u08"])
def test_subscription_removal_keys(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, key: str
) -> None:
    probe: _Probe = build(name)
    sent: list[str] = []
    monkeypatch.setattr(probe.panel, "_subscription_command", lambda command, row, number=None: sent.append(command))
    probe.panel.handle_key(key)
    assert sent == ["subscription_remove"]
    assert probe.panel._tab == _Tab.SUBSCRIPTIONS


@pytest.mark.parametrize(("name", "key"), [("subscriptions", "text:/"), ("subscriptions", "text:d"), ("u08", "text:/")])
def test_slash_opens_the_subscription_search_without_the_old_subscription(
    build: Callable[[str], _Probe], name: str, key: str
) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key(key)
    assert probe.panel._tab == _Tab.ANIME
    assert probe.anime._screen is _Screen.QUERY
    assert probe.anime.in_subscriptions
    assert probe.anime.input_focused
    assert probe.anime._subscription is None


def test_enter_on_an_empty_subscription_list_opens_the_search(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("subscriptions_empty")
    probe.panel.handle_key("enter")
    assert probe.panel._tab == _Tab.ANIME
    assert probe.anime.in_subscriptions


@pytest.mark.parametrize("key", ["text:/", "text:s"])
def test_history_search_opens_with_slash_or_s(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("history")
    probe.panel.handle_key(key)
    assert probe.panel._history_input is not None


@pytest.mark.parametrize(("name", "subscribed"), [("episodes", False), ("u08", True)])
def test_i_opens_the_release_list_at_once_and_escape_returns_to_its_episodes(
    build: Callable[[str], _Probe], name: str, *, subscribed: bool
) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:i")
    episodes._settle(probe.anime)
    probe.panel.render(80, 24)
    opened: _Screen = probe.anime._screen
    assert opened is _Screen.CANDIDATES
    assert probe.anime._view.items[probe.anime._view.cursor].suggested
    assert "Space zaznacz · D pobierz · ? więcej · Esc wróć" in probe.panel.render(80, 24).plain
    probe.panel.handle_key("escape")
    assert probe.anime._screen is _Screen.EPISODES
    assert probe.anime.in_subscriptions is subscribed
    assert (probe.anime._subscription is not None) is subscribed


@pytest.mark.parametrize("name", ["subscriptions", "library_details"])
def test_page_keys_move_the_list_cursor_by_the_painted_page(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    probe.panel._subscriptions = [drafts._row(f"s{index}", f"Series {index}") for index in range(30)]
    probe.panel._selected = 0
    probe.panel.render(80, 24)
    page: int = probe.panel._page
    count: int = len(probe.panel._entries(120))
    probe.panel.handle_key("pagedown")
    assert probe.panel._selected == min(page, count - 1)
    probe.panel.handle_key("pageup")
    assert probe.panel._selected == 0


@pytest.mark.parametrize("key", ["text:x", "delete", "text:c"])
def test_cancel_keys_arm_the_question_only_on_a_row_with_a_target(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("processing_download")
    probe.panel.handle_key(key)
    assert probe.panel._question == ("info_hash", "hash")
    frame: str = probe.panel.render(80, 24).plain
    assert "Anulować pobieranie? Enter tak · Esc nie" in frame
    assert "? więcej" not in frame
    empty: _Probe = build("processing_empty")
    empty.panel.handle_key(key)
    assert empty.panel._question is None
    history: _Probe = build("history")
    history.panel.handle_key(key)
    assert history.panel._question is None


def test_the_question_names_a_pack_and_a_whole_run(build: Callable[[str], _Probe]) -> None:
    pack: _Probe = build("processing_download")
    pack.panel._snapshot = {**pack.panel._snapshot, "materials": [_download(), _download(material="two")]}
    pack.panel.handle_key("text:x")
    assert "Anulować pobieranie (2 materiałów)? Enter tak · Esc nie" in pack.panel.render(80, 24).plain
    run: _Probe = build("processing_run")
    run.panel.handle_key("text:x")
    assert run.panel._question == ("run_id", "run")
    assert "Anulować całe zlecenie (1 materiałów)? Enter tak · Esc nie" in run.panel.render(80, 24).plain


@pytest.mark.parametrize(
    ("name", "command"),
    [
        ("processing_download", ("transfer", {"info_hash": "hash", "action": "cancel"})),
        ("processing_run", ("cancel", {"run_id": "run"})),
    ],
)
def test_enter_cancels_the_target_unless_work_is_still_running(
    build: Callable[[str], _Probe],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    command: tuple[str, Mapping[str, object]],
) -> None:
    probe: _Probe = build(name)
    sent: list[tuple[str, Mapping[str, object] | None]] = []
    monkeypatch.setattr(probe.panel, "_command", lambda kind, payload=None: sent.append((kind, payload)))
    probe.panel.handle_key("text:x")
    probe.panel._busy = True
    probe.panel.handle_key("enter")
    assert sent == []
    assert probe.panel._question is not None
    probe.panel._busy = False
    probe.panel.handle_key("enter")
    assert sent == [command]
    assert probe.panel._question is None


@pytest.mark.parametrize("key", ["escape", "interrupt", "tab", "left", "text:h", "down", "text:m", "text:?"])
def test_any_other_key_clears_the_question_and_is_swallowed(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("processing_download")
    probe.panel.handle_key("text:x")
    assert probe.panel.handle_key(key) is StateResult.CONTINUE
    assert probe.panel._question is None
    assert probe.panel._tab == _Tab.PROGRESS
    assert probe.panel._selected == 0
    assert not probe.panel._history_open
    assert not probe.panel._help
    assert probe.work == []


@pytest.mark.parametrize("button", [MouseButton.LEFT, MouseButton.RIGHT])
def test_a_mouse_press_clears_the_question_without_selecting(
    build: Callable[[str], _Probe], button: MouseButton
) -> None:
    probe: _Probe = build("processing_download")
    probe.panel._snapshot = {**probe.panel._snapshot, "materials": [_download(), _download("other", "two")]}
    probe.panel.handle_key("text:x")
    taken: Click | None = probe.panel.mouse(MouseEvent(Point(10, 5), MouseEventType.MOUSE_DOWN, button, frozenset()))
    assert taken == Click()
    assert probe.panel._question is None
    assert probe.panel._selected == 0
    assert probe.panel.mouse(MouseEvent(Point(10, 5), MouseEventType.MOUSE_UP, button, frozenset())) is None


@pytest.mark.parametrize("leave", ["library", "subscriptions", "suspend", "tab"])
def test_leaving_processing_clears_the_question(build: Callable[[str], _Probe], leave: str) -> None:
    probe: _Probe = build("processing_download")
    probe.panel.handle_key("text:x")
    if leave == "library":
        probe.panel.show_library({})
    elif leave == "subscriptions":
        probe.panel._show_subscription_list(None, "")
    elif leave == "suspend":
        probe.panel.suspend()
    else:
        probe.panel._switch_tab(_Tab.ANIME)
    assert probe.panel._question is None


def test_the_question_follows_its_target_and_ends_when_it_vanishes(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = build("processing_download")
    sent: list[tuple[str, Mapping[str, object] | None]] = []
    monkeypatch.setattr(probe.panel, "_command", lambda kind, payload=None: sent.append((kind, payload)))
    session: ResidentSession = cast("ResidentSession", _Library())
    first: dict[str, object] = _download("first", "one")
    second: dict[str, object] = _download("second", "two")
    probe.panel._snapshot = {"auto_enabled": True, "materials": [first, second]}
    probe.panel.handle_key("text:x")
    probe.panel._receive(session, {"event": "state_changed", "payload": {"materials": [second, first]}})
    assert probe.panel._question == ("info_hash", "first")
    probe.panel._perform(lambda work: None, "Polecenie przyjęte")
    assert "Anulować pobieranie? Enter tak · Esc nie" in probe.panel.render(80, 24).plain
    probe.panel.handle_key("enter")
    assert sent == [("transfer", {"info_hash": "first", "action": "cancel"})]
    probe.panel.handle_key("text:x")
    probe.panel._receive(session, {"event": "state_changed", "payload": {"materials": [second]}})
    assert probe.panel._question is None


@pytest.mark.parametrize(
    ("name", "lines"),
    [
        ("processing_download", ("Anulować pobieranie? Enter tak · Esc nie",)),
        ("processing_run", ("Anulować całe zlecenie (1 materiałów)?", "Enter tak · Esc nie")),
    ],
)
def test_the_question_breaks_only_between_its_sentence_and_keys_at_50_columns(
    build: Callable[[str], _Probe], name: str, lines: tuple[str, ...]
) -> None:
    probe: _Probe = build(name)
    probe.panel.handle_key("text:x")
    shown: list[str] = [line.strip() for line in probe.panel.render(50, 24).plain.splitlines()]
    start: int = shown.index(lines[0])
    assert tuple(shown[start : start + len(lines)]) == lines


def test_a_finished_run_ends_its_question_and_frees_the_keys(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("processing_empty")
    for group in "abc":
        run_id: str = f"run-{group}"
        started: RunEvent = RunEvent(run_id, 1, RunEventKind.TASK_STARTED, group_id=group, task_id=f"tts-{group}")
        view: RunProgressSnapshot = _live_snapshot(run_id, {group: f"{group}.mkv"}, (started,))
        probe.panel._runs[run_id] = (view.preview.preview_id, RichRunProgress.from_snapshot(view, lambda: None))
    probe.panel._snapshot = {
        "auto_enabled": True,
        "materials": [_live_material(group, f"run-{group}") for group in "abc"],
        "requests": [{"request_id": f"run-{group}", "state": "running"} for group in "abc"],
    }
    probe.panel.handle_key("text:x")
    assert probe.panel._question == ("run_id", "run-a")
    finished: RunEvent = RunEvent("run-a", 2, RunEventKind.GROUP_FINISHED, group_id="a", state=TaskState.SUCCEEDED)
    probe.panel._receive_progress(cast("ResidentSession", _Library()), finished)
    assert probe.panel._question is None
    probe.panel.handle_key("down")
    assert probe.panel._selected == 1


def test_a_narrow_footer_drops_actions_from_the_end_and_keeps_help_and_back(build: Callable[[str], _Probe]) -> None:
    actions: ScreenActions = ScreenActions((("W", "wstrzymaj"), ("X", "anuluj"), ("H", "historia")))
    assert pack_footer(footer_segments(actions), 20) == ("W wstrzymaj", "? więcej · Esc wróć")
    lines: list[str] = [line.strip() for line in build("processing_download").panel.render(30, 24).plain.splitlines()]
    assert "W wstrzymaj · X anuluj" in lines
    assert "? więcej · Esc wróć" in lines
    assert not any("H historia" in line for line in lines)


def test_an_arriving_retry_proposal_closes_the_help_block(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("history")
    probe.panel.handle_key("text:p")
    load: Callable[[ResidentSession], object] = cast("Callable[[ResidentSession], object]", probe.work[-1])
    probe.panel.handle_key("text:?")
    assert probe.panel._help
    proposal: RetryProposal = RetryProposal("material", "manual", ("group",))
    load(cast("ResidentSession", SimpleNamespace(retry_proposal=lambda identifier: proposal)))
    assert probe.panel._retry == proposal
    assert not probe.panel._help
    assert "Enter przygotuj · Esc wróć" in probe.panel.render(80, 24).plain


@pytest.mark.parametrize(("key", "tab"), [("left", _Tab.ANIME), ("right", _Tab.PROGRESS)])
def test_a_new_panel_opens_on_subscriptions_between_anime_and_processing(
    monkeypatch: pytest.MonkeyPatch, key: str, tab: int
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    try:
        assert panel._tab == _Tab.SUBSCRIPTIONS
        panel.handle_key(key)
        assert panel._tab == tab
    finally:
        panel.close()
        panel._thread.join(5)


@pytest.mark.parametrize("name", ["subscriptions", "subscriptions_empty", "u08"])
def test_two_escapes_from_the_subscription_search_return_to_the_list(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = build(name)
    for key in ("text:/", "text:slime"):
        probe.panel.handle_key(key)
    assert probe.panel.handle_key("escape") is StateResult.CONTINUE
    assert probe.panel._tab == _Tab.ANIME
    assert probe.anime._screen is _Screen.QUERY
    assert not probe.anime.input_focused
    assert probe.anime._query == "slime"
    assert probe.panel.handle_key("escape") is StateResult.CONTINUE
    assert probe.panel._tab == _Tab.SUBSCRIPTIONS
    assert not probe.anime.in_subscriptions


@pytest.mark.parametrize(
    "name",
    [
        "titles",
        "entries",
        "episodes",
        "episodes_file",
        "candidates",
        "files",
        "draft",
        "busy",
        "problem",
        "u08",
        "u08_extra",
    ],
)
def test_backspace_goes_back_like_escape_on_every_anime_screen_but_the_query(
    build: Callable[[str], _Probe], name: str
) -> None:
    escaped: _Probe = build(name)
    expected: StateResult = escaped.panel.handle_key("escape")
    episodes._settle(escaped.anime)
    erased: _Probe = build(name)
    before: tuple[object, ...] = _state(erased)
    assert erased.panel.handle_key("backspace") is expected
    episodes._settle(erased.anime)
    assert _state(erased) == _state(escaped)
    assert _state(erased) != before


@pytest.mark.parametrize(
    ("name", "keys", "text"),
    [
        ("query", (), ""),
        ("query", ("text:/", "text:slime"), "slim"),
        ("titles", ("escape",), "slim"),
        ("subscriptions", ("text:/", "text:slime", "escape"), "slim"),
    ],
)
def test_backspace_on_the_query_types_into_it_instead_of_leaving(
    build: Callable[[str], _Probe], name: str, keys: tuple[str, ...], text: str
) -> None:
    probe: _Probe = build(name)
    for key in keys:
        probe.panel.handle_key(key)
    assert probe.anime._screen is _Screen.QUERY
    assert probe.panel.handle_key("backspace") is StateResult.CONTINUE
    assert probe.panel._tab == _Tab.ANIME
    assert probe.anime._screen is _Screen.QUERY
    assert probe.anime.input_focused
    assert probe.anime._query == text


def test_backspace_edits_the_episode_range(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("episodes")
    for key in ("text:z", "text:1", "text:-", "text:3"):
        probe.panel.handle_key(key)
    assert probe.panel.handle_key("backspace") is StateResult.CONTINUE
    assert probe.anime._range == "1-"
    assert probe.anime._screen is _Screen.EPISODES


def test_backspace_edits_the_history_search(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("history")
    for key in ("text:/", "text:ab"):
        probe.panel.handle_key(key)
    assert probe.panel.handle_key("backspace") is StateResult.CONTINUE
    assert probe.panel._history_input is not None
    assert probe.panel._history_input.text == "a"
    assert probe.panel._history_open


@pytest.mark.parametrize("key", ["escape", "backspace"])
def test_escape_or_backspace_closes_the_retry_proposal(build: Callable[[str], _Probe], key: str) -> None:
    probe: _Probe = build("history")
    probe.panel.handle_key("text:p")
    load: Callable[[ResidentSession], object] = cast("Callable[[ResidentSession], object]", probe.work[-1])
    proposal: RetryProposal = RetryProposal("material", "manual", ("group",))
    load(cast("ResidentSession", SimpleNamespace(retry_proposal=lambda identifier: proposal)))
    assert probe.panel._retry == proposal
    assert probe.panel.handle_key(key) is StateResult.CONTINUE
    assert probe.panel._retry is None
    assert probe.panel._history_open


def _settle(probe: _Probe) -> None:
    if probe.panel._anime is not None:
        episodes._settle(probe.panel._anime)


def _frozen(probe: _Probe) -> _Probe:
    now: float = time()
    probe.anime._clock = lambda: now
    return probe


def _app(monkeypatch: pytest.MonkeyPatch, probe: _Probe) -> interactive_app._InteractiveApplication:
    application, _copied = _application(monkeypatch, interactive_app._ViewMode.STATE)
    application._frame_selection = FrameSelection(clock=lambda: 0.0)
    application._state = probe.panel
    return application


def _cursor_point(frame: Text, probe: _Probe) -> Point:
    cursor: int = probe.anime._view.cursor if probe.panel._tab == _Tab.ANIME else probe.panel._selected
    lines: list[str] = frame.plain.split("\n")
    row: int = next(row for row in range(len(lines)) if _row_at(frame, row) == cursor)
    return Point(len(lines[row]) - len(lines[row].lstrip()), row)


def _label_point(frame: Text, label: str, line_mark: str) -> Point:
    lines: list[str] = frame.plain.split("\n")
    row: int = next(row for row, line in enumerate(lines) if line_mark in line)
    return Point(Text(lines[row][: lines[row].index(label)]).cell_len, row)


def _tab_point(frame: Text, tab: int) -> Point:
    return _label_point(frame, state_module._TABS[tab], " · ".join(state_module._TABS))


def _right_click(application: interactive_app._InteractiveApplication, point: Point) -> None:
    application._handle_mouse(MouseEvent(point, MouseEventType.MOUSE_DOWN, MouseButton.RIGHT, frozenset()))


@pytest.mark.parametrize(
    "name",
    [
        "titles",
        "entries",
        "episodes",
        "episodes_file",
        "candidates",
        "files",
        "draft",
        "u08",
        "u08_extra",
        "subscriptions",
        "processing_download",
        "history",
        "library",
        "library_details",
    ],
)
def test_a_double_click_on_the_cursor_row_does_what_enter_does(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    pressed: _Probe = _frozen(build(name))
    pressed.panel.handle_key("enter")
    _settle(pressed)
    clicked: _Probe = _frozen(build(name))
    application: interactive_app._InteractiveApplication = _app(monkeypatch, clicked)
    point: Point = _cursor_point(application._render_frame(80, 24), clicked)

    _click(application, point)
    _click(application, point)
    _settle(clicked)

    assert _state(clicked) == _state(pressed)


@pytest.mark.parametrize(
    ("name", "keys", "tab"),
    [
        ("library", (), _Tab.ANIME),
        ("library", (), _Tab.SUBSCRIPTIONS),
        ("library", (), _Tab.PROGRESS),
        ("subscriptions", (), _Tab.FILES),
        ("query", ("text:/", "text:slime"), _Tab.FILES),
        ("history", ("text:/",), _Tab.PROGRESS),
    ],
)
def test_a_click_on_a_tab_name_switches_exactly_where_tab_switches(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, keys: tuple[str, ...], tab: int
) -> None:
    probe: _Probe = build(name)
    for key in keys:
        probe.panel.handle_key(key)
    start: int = probe.panel._shown_tab()
    tabbed: _Probe = build(name)
    for key in (*keys, "tab"):
        tabbed.panel.handle_key(key)
    switches: bool = tabbed.panel._shown_tab() != start
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)

    _click(application, _tab_point(application._render_frame(80, 24), tab))

    assert probe.panel._shown_tab() == (tab if switches else start)
    assert switches == (name != "history")


def test_a_click_on_the_narrow_tab_arrows_moves_to_the_neighbouring_tabs(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = build("library")
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    _click(application, _label_point(application._render_frame(40, 24), "←", "(4/4)"))
    left: int = probe.panel._tab
    _click(application, _label_point(application._render_frame(40, 24), "→", "(3/4)"))

    assert left == _Tab.PROGRESS
    assert probe.panel._tab == _Tab.FILES


@pytest.mark.parametrize(
    ("name", "label", "escapes"),
    [
        ("history", "Przetwarzanie", 1),
        ("library_details", "Biblioteka", 1),
        ("candidates", "Anime", 2),
        ("u08", "Subskrypcje", 1),
        ("draft", "Nowa subskrypcja", 1),
    ],
)
def test_a_click_on_an_earlier_crumb_goes_back_by_escape_until_that_level(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, label: str, escapes: int
) -> None:
    escaped: _Probe = build(name)
    before: tuple[object, ...] = _state(escaped)
    for _escape in range(escapes):
        escaped.panel.handle_key("escape")
        _settle(escaped)
    probe: _Probe = build(name)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    current: Point = _label_point(application._render_frame(80, 24), probe.panel.breadcrumb()[-1], CRUMB_SEPARATOR)

    _click(application, current)
    unchanged: tuple[object, ...] = _state(probe)
    _click(application, _label_point(application._render_frame(80, 24), label, f"{label}{CRUMB_SEPARATOR}"))
    _settle(probe)

    assert unchanged == before
    assert _state(probe) == _state(escaped)
    assert _state(probe) != before


@pytest.mark.parametrize(
    ("name", "keys"),
    [
        ("titles", ()),
        ("episodes", ()),
        ("episodes", ("text:z",)),
        ("candidates", ()),
        ("draft", ()),
        ("u08", ()),
        ("query", ("text:/", "text:slime")),
        ("history", ()),
        ("history", ("text:/",)),
        ("library_details", ()),
    ],
)
def test_a_right_click_does_what_escape_does_also_in_a_focused_field(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, keys: tuple[str, ...]
) -> None:
    escaped: _Probe = build(name)
    clicked: _Probe = build(name)
    for key in keys:
        escaped.panel.handle_key(key)
        clicked.panel.handle_key(key)
    before: tuple[object, ...] = _state(escaped)
    escaped.panel.handle_key("escape")
    _settle(escaped)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, clicked)
    application._render_frame(80, 24)

    _right_click(application, Point(10, 12))
    _settle(clicked)

    assert _state(clicked) == _state(escaped)
    assert _state(clicked) != before


def test_a_right_click_on_a_tab_list_leaves_the_panel_like_escape(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    application: interactive_app._InteractiveApplication = _app(monkeypatch, build("subscriptions"))
    application._render_frame(80, 24)

    _right_click(application, Point(0, 0))

    assert application._mode is interactive_app._ViewMode.HOME


def _field(probe: _Probe) -> TextInput:
    if probe.panel._history_input is not None:
        return probe.panel._history_input
    editor: TextInput | None = probe.anime._range_input
    return probe.anime._query_input if editor is None else editor


@pytest.mark.parametrize(
    ("name", "keys", "shown"),
    [
        ("query", ("text:/", "text:slime", "escape"), ("> ", "slime")),
        ("episodes", ("text:z", "text:1-3"), ("Zakres: ", "1-3")),
        ("history", ("text:/", "text:abc"), ("", "abc ")),
    ],
)
def test_a_click_in_a_text_field_focuses_it_and_puts_the_cursor_there_or_at_its_end(
    build: Callable[[str], _Probe],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    keys: tuple[str, ...],
    shown: tuple[str, str],
) -> None:
    before, value = shown
    probe: _Probe = build(name)
    for key in keys:
        probe.panel.handle_key(key)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    field: Point = _label_point(application._render_frame(80, 24), f"{before}{value}", f"{before}{value}")
    text: str = _field(probe).text

    _click(application, Point(field.x + len(before) + 1, field.y))
    focused: bool = probe.panel._history_input is not None or probe.anime.input_focused
    probe.panel.handle_key("text:Q")
    inserted: str = _field(probe).text
    application._render_frame(80, 24)
    _click(application, Point(79, field.y))
    probe.panel.handle_key("text:E")

    assert focused
    assert inserted == f"{text[0]}Q{text[1:]}"
    assert _field(probe).text == f"{inserted}E"


def _uncertain_release(probe: _Probe) -> _Probe:
    anime: AnimeController = probe.anime
    anime._confirm_choice = anime._release_candidates[0]
    anime._confirm_view = anime._offer_view
    anime._problem = "Wydanie niepewne"
    anime._problem_return = _Screen.CANDIDATES
    anime._screen = _Screen.PROBLEM
    return probe


def _double_click(application: interactive_app._InteractiveApplication, point: Point) -> None:
    _click(application, point)
    _click(application, point)


def test_a_double_click_on_a_problem_text_never_confirms_the_release(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = _uncertain_release(_frozen(build("candidates")))
    owner: episodes._ChoiceOwner = cast("episodes._ChoiceOwner", probe.owner)
    choices: int = len(owner.choices)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    frame: Text = application._render_frame(80, 24)

    _double_click(application, _label_point(frame, "Wydanie niepewne", "Wydanie niepewne"))
    _settle(probe)

    assert len(owner.choices) == choices
    assert probe.anime._screen is _Screen.PROBLEM


@pytest.mark.parametrize("name", ["titles", "episodes"])
def test_a_double_click_in_the_details_text_only_points_at_a_line(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    probe: _Probe = _frozen(build(name))
    probe.panel.handle_key("text:?")
    before: tuple[object, ...] = _state(probe)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    frame: Text = application._render_frame(80, 24)
    lines: list[str] = frame.plain.split("\n")
    row: int = next(row for row in range(len(lines)) if _row_at(frame, row) is not None and lines[row].strip())

    _double_click(application, Point(len(lines[row]) - len(lines[row].lstrip()), row))
    _settle(probe)

    assert probe.anime._details_open
    assert _state(probe) == before


@pytest.mark.parametrize("blocked", ["retry", "help"])
def test_a_double_click_on_a_row_that_takes_no_cursor_runs_nothing(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, blocked: str
) -> None:
    probe: _Probe = build("library")
    if blocked == "retry":
        probe.panel._retry = RetryProposal("material", "reacquire", ("group",), operation_id="operation")
    probe.panel._help = blocked == "help"
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    frame: Text = application._render_frame(80, 24)
    row: int = next((row for row in range(24) if _row_at(frame, row) == 0), 12)

    _double_click(application, Point(4, row))

    assert probe.work == []
    assert (probe.panel._retry is not None) == (blocked == "retry")
    assert probe.panel._help == (blocked == "help")


def test_a_click_on_a_row_that_takes_no_cursor_never_arms_a_double_click(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = build("library")
    probe.panel._retry = RetryProposal("material", "reacquire", ("group",), operation_id="operation")
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    point: Point = Point(4, next(row for row in range(24) if _row_at(application._render_frame(80, 24), row) == 0))

    _click(application, point)
    probe.panel._retry = None
    application._render_frame(80, 24)
    _click(application, point)

    assert probe.panel._selected == 0
    assert probe.work == []


def test_a_click_on_a_placeholder_anime_row_never_arms_a_double_click() -> None:
    panel: AnimePanel = AnimePanel(
        AnimeViewState(screen=AnimeScreen.DRAFT, title="", items=(AnimeRow("busy", "Szukam", navigable=False),)),
        lambda _action, _keys: None,
        lambda: 0.0,
    )
    lines: list[str] = panel.frame(80, 24).plain.split("\n")
    point: Point = Point(4, next(row for row, line in enumerate(lines) if "Szukam" in line))

    def click() -> Click:
        result: Click = Click()
        for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
            result = panel.mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))
        return result

    first: Click = click()
    panel.state.items = (AnimeRow("alpha", "Szukam dalej"),)
    panel.frame(80, 24)
    second: Click = click()

    assert first == Click()
    assert second == Click(ClickKind.ROW, 0)


def _opened(monkeypatch: pytest.MonkeyPatch, probe: _Probe) -> list[tuple[str, object]]:
    monkeypatch.setattr(state_module, "_open_path", lambda path, *, show_folder: None)
    session: _Library = _Library()
    for action in probe.work:
        cast("Callable[[ResidentSession], None]", action)(cast("ResidentSession", session))
    return session.calls


def _double_click_row(application: interactive_app._InteractiveApplication, size: tuple[int, int], index: int) -> None:
    point: Point = Point(4, _row_of(application._render_frame(*size), index))
    _click(application, point)
    application._render_frame(*size)
    _click(application, point)


@pytest.mark.parametrize("rows", [24, 25])
def test_a_double_click_in_library_details_opens_the_clicked_file_when_its_notice_clears(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, rows: int
) -> None:
    probe: _Probe = build("library_details")
    probe.panel._selected = 0
    probe.panel.handle_key("enter")
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)

    _double_click_row(application, (80, rows), 3)

    assert probe.panel._notice == ""
    assert probe.panel._selected == 3
    assert _opened(monkeypatch, probe) == [("file", _details_view().files[1].identity)]


def test_a_double_click_in_a_narrow_library_opens_the_clicked_set_when_its_notice_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    probe: _Probe = _list_probe(
        monkeypatch,
        _Tab.FILES,
        {"library": [{"set_id": "first", "name": "Alpha"}, {"set_id": "second", "name": "Beta"}]},
    )
    probe.panel._notify("Nie udało się otworzyć pliku wideo w odtwarzaczu")
    probe.panel._notice_persistent = True
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)

    _double_click_row(application, (40, 12), 1)

    assert probe.panel._selected == 1
    assert _opened(monkeypatch, probe) == [("result", "second")]


def test_a_double_click_across_a_library_change_opens_the_first_clicked_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    library: list[dict[str, str]] = [
        {"set_id": f"e{number:02d}", "name": f"[Grp] Show - {number:02d} [1080p]"} for number in range(2, 42, 2)
    ]
    probe: _Probe = _list_probe(monkeypatch, _Tab.FILES, {"library": library})
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    point: Point = Point(4, _row_of(application._render_frame(80, 24), 1))

    _click(application, point)
    changed: dict[str, object] = {"library": [{"set_id": "e03", "name": "[Grp] Show - 03 [1080p]"}, *library]}
    probe.panel._preserve_library_selection(changed)
    probe.panel._snapshot = changed
    frame: Text = application._render_frame(80, 24)
    _click(application, point)

    assert _row_at(frame, point.y) == 1
    assert probe.panel._selected == 2
    assert _opened(monkeypatch, probe) == [("result", "e04")]


def test_a_wheel_between_two_anime_clicks_cancels_the_double_click(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = _frozen(build("titles"))
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    point: Point = _cursor_point(application._render_frame(80, 24), probe)

    _click(application, point)
    application._handle_scroll(1)
    application._render_frame(80, 24)
    _click(application, point)
    _settle(probe)

    assert probe.anime._screen is _Screen.TITLES


def test_a_second_click_on_a_problem_painted_over_the_clicked_row_confirms_nothing() -> None:
    panel: AnimePanel = AnimePanel(
        AnimeViewState(
            screen=AnimeScreen.RELEASES,
            title="",
            items=tuple(AnimeRow(f"release-{index}", f"Wydanie {index}") for index in range(8)),
        ),
        lambda _action, _keys: None,
        lambda: 0.0,
    )
    lines: list[str] = panel.frame(80, 24).plain.split("\n")
    point: Point = Point(10, next(row for row, line in enumerate(lines) if "Wydanie 6" in line))

    def click() -> Click:
        result: Click = Click()
        for kind in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP):
            result = panel.mouse(MouseEvent(point, kind, MouseButton.LEFT, frozenset()))
        return result

    first: Click = click()
    panel.state.screen = AnimeScreen.PROBLEM
    panel.state.items = (AnimeRow("problem", "Wydanie niepewne", navigable=False),)
    panel.state.cursor = 0
    panel.frame(80, 24)
    second: Click = click()

    assert first == Click(ClickKind.ROW, 6)
    assert second == Click()


def test_a_click_in_the_history_search_reaches_the_scrolled_character(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = build("history")
    value: str = "abcdefghij" * 7
    for key in ("text:/", f"text:{value}"):
        probe.panel.handle_key(key)
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    lines: list[str] = application._render_frame(60, 24).plain.split("\n")
    row: int = next(row for row, line in enumerate(lines) if "abcdefghij" in line)
    shown: str = lines[row].strip()

    _click(application, Point(len(lines[row]) - len(lines[row].lstrip()), row))

    assert sum("abcdefghij" in line for line in lines) == 1
    assert probe.panel._history_input is not None
    assert probe.panel._history_input.cursor == len(value) - len(shown)


def test_a_crumb_level_counts_parts_even_when_a_title_contains_the_separator(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch
) -> None:
    probe: _Probe = build("history")
    monkeypatch.setattr(state_module, "_HISTORY_CRUMB", ("Przetwarzanie", f"Hist{CRUMB_SEPARATOR}oria"))
    application: interactive_app._InteractiveApplication = _app(monkeypatch, probe)
    mark: str = f"Hist{CRUMB_SEPARATOR}oria"

    _click(application, _label_point(application._render_frame(80, 24), "oria", mark))
    stayed: bool = probe.panel._history_open
    _click(application, _label_point(application._render_frame(80, 24), "Przetwarzanie", mark))

    assert stayed
    assert not probe.panel._history_open
