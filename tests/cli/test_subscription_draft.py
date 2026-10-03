from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from rich.text import Text

from anishift.application import (
    AppService,
    EntryGroup,
    EpisodeKey,
    EpisodeListing,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    FranchiseRelation,
    ListedEpisode,
    ListedSpecial,
    TitleCandidate,
    TitleStatus,
    encode_view,
)
from anishift.application.subscription_targets import SubscriptionRow
from anishift.cli.interactive.anime import AnimeController, _Screen
from anishift.cli.interactive.state import StateController, _Tab
from anishift.cli.interactive.subscription_texts import (
    SubscriptionDraft,
    check_text,
    row_state,
    subscription_draft,
)
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import ControlError, ControlErrorCode

pytestmark = pytest.mark.unit

_NOW: datetime = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _listing(
    status: str = "RELEASING",
    episodes: tuple[ListedEpisode, ...] = (),
    count: int | None = 12,
    schedule_warning: str | None = None,
) -> EpisodeListing:
    return EpisodeListing(7, None, "TV", status, count, episodes, (), None, schedule_warning, None)


def _weekly(aired: int, total: int) -> tuple[ListedEpisode, ...]:
    return tuple(
        ListedEpisode(
            number,
            f"Odcinek {number}",
            airs_at=_NOW + timedelta(days=7 * (number - aired) - 1),
            aired=number <= aired,
        )
        for number in range(1, total + 1)
    )


def _title(identifier: int, status: TitleStatus) -> TitleCandidate:
    return TitleCandidate(
        identifier, f"Slime {identifier}", f"Slime {identifier}", None, (), 2026, None, "TV", 3, status, ()
    )


def _entry(identifier: int) -> FranchiseEntry:
    return FranchiseEntry(identifier, "Slime", "Slime", None, "TV", "RELEASING", 2026, None, "SELF", EntryGroup.SEASON)


def _row(subscription_id: str, title: str, **changes: object) -> dict[str, object]:
    row: SubscriptionRow = SubscriptionRow(
        subscription_id=subscription_id,
        anilist_id=1,
        title=title,
        from_number=3,
        downloaded=1,
        targets_total=4,
        due_at=None,
        paused=False,
        pause_reason=None,
        problem=None,
        review_pending=False,
    )
    return {**encode_view(row), **changes}


class _Owner:
    def __init__(self) -> None:
        self.titles: tuple[TitleCandidate, ...] = (
            _title(1, TitleStatus.RELEASING),
            _title(7, TitleStatus.NOT_YET_RELEASED),
        )
        self.listings: dict[int, EpisodeListing] = {
            1: replace(_listing(episodes=_weekly(2, 4), count=4), anilist_id=1),
            7: _listing("NOT_YET_RELEASED", count=None),
        }
        self.details: dict[str, object] = {}
        self.extras: tuple[FranchiseEntry, ...] = ()
        self.calls: list[tuple[str, object]] = []
        self.numbers: list[tuple[int, ...]] = []
        self.refusal: str = ""

    def new_session(self) -> _Owner:
        return self

    def find_titles(self, query: str) -> tuple[TitleCandidate, ...]:
        del query
        return self.titles

    def franchise(self, identifier: int, *, cancel: object = None) -> Franchise:
        del cancel
        return Franchise(
            identifier,
            (_entry(identifier), *self.extras),
            tuple(FranchiseRelation(identifier, item.anilist_id, item.relation) for item in self.extras),
            True,
        )

    def episodes(self, identifier: int) -> EpisodeListing:
        self.calls.append(("episodes", identifier))
        return self.listings[identifier]

    def episode_states(self, identifier: int, numbers: tuple[int, ...]) -> tuple[EpisodeStatus, ...]:
        del identifier
        self.numbers.append(tuple(numbers))
        return ()

    def subscription_add(self, anilist_id: int, *, command_id: str) -> Mapping[str, object]:
        self.calls.append(("subscription_add", anilist_id))
        assert command_id
        if self.refusal:
            raise ControlError("refused", code=ControlErrorCode.REFUSED, reason=self.refusal, answered=True)
        return {"subscription_id": "new"}

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        self.calls.append((kind, payload))
        return self.details if kind == "subscription_get" else {}

    def interrupt_reads(self) -> None:
        return

    def close(self) -> None:
        return


class _Clock:
    def __init__(self) -> None:
        self.now: datetime = _NOW

    def __call__(self) -> datetime:
        return self.now

    def timestamp(self) -> float:
        return self.now.timestamp()


@pytest.fixture
def owner() -> _Owner:
    return _Owner()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def panel(monkeypatch: pytest.MonkeyPatch, owner: _Owner, clock: _Clock) -> Iterator[StateController]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", owner), lambda: None, clock=clock)
    anime: AnimeController = AnimeController(
        cast("AppService", SimpleNamespace(acquisition=None)), lambda: None, resident=cast("ResidentSession", owner)
    )
    anime._clock = clock.timestamp
    controller._tab = _Tab.SUBSCRIPTIONS
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {"auto_enabled": True}
    controller._subscriptions = [_row("a", "Alpha")]
    controller.attach_anime(anime)
    try:
        yield controller
    finally:
        controller.close()
        controller._thread.join(5)


def _anime(panel: StateController) -> AnimeController:
    anime: AnimeController | None = panel._anime
    assert anime is not None
    return anime


def _settle(panel: StateController) -> None:
    anime: AnimeController = _anime(panel)
    deadline: float = time.monotonic() + 5
    while time.monotonic() < deadline:
        worker: threading.Thread | None = anime._worker
        if worker is not None:
            worker.join(5)
        if (anime._worker is None or not anime._worker.is_alive()) and not panel._busy:
            return
        threading.Event().wait(0.005)
    raise AssertionError


def _keys(panel: StateController, *keys: str) -> None:
    for key in keys:
        panel.handle_key(key)
        _settle(panel)


def _frame(panel: StateController, columns: int = 120, rows: int = 30) -> str:
    return panel.render(columns, rows).plain


def _titles(panel: StateController) -> None:
    _keys(panel, "text:d", "text:slime", "enter")
    assert panel._tab == _Tab.ANIME
    assert _anime(panel)._screen is _Screen.TITLES


def test_a_draft_follows_the_episodes_airing_after_now_and_names_the_aired_ones() -> None:
    draft: SubscriptionDraft | None = subscription_draft(_listing(episodes=_weekly(2, 12)), "Slime", _NOW, paused=False)

    assert draft is not None
    assert draft.addable
    assert draft.lines[:5] == (
        "Tytuł:     Slime",
        "Od odc.:   3",
        f"Później:   E3 — emisja {(_NOW + timedelta(days=6)).astimezone():%d.%m %H:%M}",
        "Koniec:    po pobraniu E12 (sezon ma 12 odcinków)",
        "Dodatki:   nie; pobierasz je osobno z listy wpisów",
    )
    assert "Wyemitowane E1–E2 nie wchodzą do subskrypcji" in draft.lines


def test_an_announcement_without_dates_or_count_follows_every_episode_from_the_first() -> None:
    draft: SubscriptionDraft | None = subscription_draft(
        _listing("NOT_YET_RELEASED", count=None), "Slime", _NOW, paused=False
    )

    assert draft is not None
    assert draft.addable
    assert draft.lines[1:4] == (
        "Od odc.:   1",
        "Później:   od E1 — termin nieznany",
        "Koniec:    gdy sezon się zakończy i wszystkie odcinki będą pobrane",
    )
    assert not any("Wyemitowane" in line for line in draft.lines)


def test_a_draft_under_the_global_pause_says_when_it_starts_working() -> None:
    draft: SubscriptionDraft | None = subscription_draft(_listing(episodes=_weekly(0, 2)), "Slime", _NOW, paused=True)

    assert draft is not None
    assert draft.lines[-1] == "AniShift jest wstrzymany — subskrypcja zacznie działać po wznowieniu"


@pytest.mark.parametrize(
    "listing",
    [
        _listing(episodes=(ListedEpisode(1, aired=True),)),
        _listing("HIATUS"),
        _listing(episodes=_weekly(2, 4), schedule_warning="anilist"),
        _listing(episodes=tuple(replace(item, airs_at_fallback=True) for item in _weekly(2, 4))),
    ],
)
def test_an_unknown_cut_point_offers_no_add_button(listing: EpisodeListing) -> None:
    draft: SubscriptionDraft | None = subscription_draft(listing, "Slime", _NOW, paused=False)

    assert draft is not None
    assert not draft.addable
    assert draft.lines[-1] == "Nie wiadomo, ile odcinków już wyemitowano · spróbuj później"


def test_a_finished_entry_has_no_draft() -> None:
    assert subscription_draft(_listing("FINISHED", episodes=_weekly(4, 4)), "Slime", _NOW, paused=False) is None


@pytest.mark.parametrize(
    ("changes", "state"),
    [
        ({"due_at": (_NOW + timedelta(minutes=30)).isoformat(), "due_number": 8}, "Emisja E8 za 00:30:00"),
        ({"due_at": (_NOW + timedelta(days=2, seconds=5)).isoformat()}, "Emisja za 2 d 00:00:05"),
        ({"due_at": (_NOW - timedelta(minutes=5)).isoformat(), "due_number": 8}, "Czeka na wydanie E8 (od 5 min)"),
        ({"due_at": (_NOW - timedelta(hours=5)).isoformat(), "due_number": 8}, "Czeka na wydanie E8 (od 5 h)"),
        ({"due_at": (_NOW - timedelta(hours=25)).isoformat()}, "Czeka na wydanie (od 1 dzień)"),
        (
            {"due_at": (_NOW - timedelta(hours=73)).isoformat(), "due_number": 8},
            "Czeka na wydanie E8 (od 3 dni; sprawdzam raz dziennie)",
        ),
        ({"catalog_status": "HIATUS"}, "Przerwa w emisji"),
        ({"catalog_status": "RELEASING"}, "Termin nieznany"),
        ({"review_pending": True, "due_at": _NOW.isoformat()}, "Sprawdzam przeniesioną subskrypcję"),
        (
            {"paused": True, "pause_reason": "migrated_due", "review_pending": True},
            "Wstrzymana — przeniesiona; zaległe odcinki · W wznów",
        ),
        (
            {"problem": "catalog_conflict", "paused": True, "pause_reason": "user"},
            "Katalog wskazuje inny sezon — sprawdzam ponownie",
        ),
        (
            {"episode_count": 4, "beyond_count": 6, "paused": True, "pause_reason": "user"},
            "AniList podaje 4 odcinki, a subskrypcja czeka na E6 · pobierz ręcznie albo usuń",
        ),
        ({"episode_count": 4, "beyond_count": None}, "Termin nieznany"),
        (
            {"due_at": (_NOW - timedelta(hours=1)).isoformat(), "due_number": 3, "checking_number": 3},
            "Kontrola E3",
        ),
        ({"checking_number": 3, "paused": True, "pause_reason": "user"}, "Wstrzymana · W wznów"),
    ],
)
def test_a_row_shows_its_strongest_state(changes: Mapping[str, object], state: str) -> None:
    assert row_state(_row("a", "Alpha", **changes), _NOW) == state


@pytest.mark.parametrize(
    ("check", "text"),
    [
        (
            {"number": 6, "matching": 0, "uncertain": 8, "mismatched": 4, "outcome": "no_match"},
            "Sprawdzono E6: 12 kandydatów, 0 zgodnych (8 niepewnych, 4 niezgodnych)",
        ),
        (
            {"number": 6, "matching": 1, "uncertain": 0, "mismatched": 0, "outcome": "proposed"},
            "Sprawdzono E6: 1 kandydat, 1 zgodnych · propozycja zapisana",
        ),
        ({"number": 6, "outcome": "no_candidates"}, "Sprawdzono E6: brak wydań w źródle"),
        ({"number": 6, "outcome": "source_failed"}, "E6: źródło wydań nie odpowiada · ponowię później"),
        ({"number": 6, "outcome": "rate_limited"}, "E6: źródło wydań ogranicza zapytania · ponowię później"),
        ({"number": None, "outcome": "refreshed"}, "Sprawdzono listę odcinków"),
        ({"number": None, "outcome": "source_failed"}, "Katalog odcinków nie odpowiada · ponowię później"),
        ({"number": None, "outcome": "rate_limited"}, "Katalog odcinków ogranicza zapytania · ponowię później"),
    ],
)
def test_a_check_is_summarized_with_its_candidate_counts(check: Mapping[str, object], text: str) -> None:
    assert check_text(check) == text


def test_d_on_the_list_searches_and_s_on_an_announced_title_adds_and_highlights_it(
    panel: StateController, owner: _Owner
) -> None:
    _titles(panel)
    _keys(panel, "down", "enter")
    assert "odcinków jeszcze nie ma" in _frame(panel)
    assert _anime(panel)._screen is _Screen.TITLES

    _keys(panel, "text:s")
    frame: str = _frame(panel)
    assert _anime(panel)._screen is _Screen.DRAFT
    assert "Nowa subskrypcja" in frame
    assert "Od odc.:   1" in frame
    assert "\u276f [ Dodaj subskrypcję ]" in frame

    _keys(panel, "enter")
    assert ("subscription_add", 7) in owner.calls
    assert panel._tab == _Tab.SUBSCRIPTIONS
    with panel._lock:
        panel._adopt_subscriptions({}, [_row("a", "Alpha"), _row("new", "Slime 7", anilist_id=7)])
    assert panel._selected == 2


def test_esc_leaves_the_draft_for_its_source_screen_and_the_search_for_the_list(panel: StateController) -> None:
    _titles(panel)
    _keys(panel, "text:s")
    assert _anime(panel)._screen is _Screen.DRAFT

    _keys(panel, "escape")
    assert _anime(panel)._screen is _Screen.TITLES

    _keys(panel, "escape", "escape")
    assert panel._tab == _Tab.SUBSCRIPTIONS


def test_s_on_an_episode_list_drafts_from_the_loaded_list_without_reading_it_again(
    panel: StateController, owner: _Owner
) -> None:
    owner.titles = (_title(1, TitleStatus.RELEASING),)
    with panel._lock:
        panel._adopt_subscriptions({}, [])
    _keys(panel, "text:d", "text:slime", "enter")
    assert _anime(panel)._screen is _Screen.EPISODES
    reads: int = owner.calls.count(("episodes", 1))

    _keys(panel, "text:s")

    assert _anime(panel)._screen is _Screen.DRAFT
    assert owner.calls.count(("episodes", 1)) == reads
    assert "Od odc.:   3" in _frame(panel)


def test_a_subscribed_entry_offers_its_subscription_instead_of_a_second_one(
    panel: StateController, owner: _Owner
) -> None:
    with panel._lock:
        panel._adopt_subscriptions({}, [_row("a", "Alpha", anilist_id=7)])
    _titles(panel)
    _keys(panel, "down", "text:s")
    assert "Ten sezon jest już subskrybowany · Enter pokaż" in _frame(panel)
    assert ("episodes", 7) not in owner.calls

    _keys(panel, "enter")

    assert ("subscription_get", {"subscription_id": "a"}) in owner.calls
    assert "Subskrypcje \u203a Alpha" in _frame(panel)


def test_a_refused_add_keeps_the_draft_and_names_the_reason(panel: StateController, owner: _Owner) -> None:
    owner.refusal = "subscription_limit"
    _titles(panel)
    _keys(panel, "down", "text:s", "enter")

    assert _anime(panel)._screen is _Screen.DRAFT
    assert panel._tab == _Tab.ANIME
    assert "Osiągnięto limit subskrypcji; usuń jedną, aby dodać lub przywrócić" in _frame(panel)


def test_a_finished_entry_explains_that_it_cannot_be_subscribed(panel: StateController, owner: _Owner) -> None:
    owner.listings[7] = _listing("FINISHED", episodes=_weekly(4, 4))
    _titles(panel)
    _keys(panel, "down", "text:s")

    assert _anime(panel)._screen is _Screen.TITLES
    assert "Ten wpis nie ma przyszłych odcinków" in _frame(panel)


def test_an_unknown_cut_point_shows_the_refusal_without_an_add_button(panel: StateController, owner: _Owner) -> None:
    owner.listings[7] = _listing("HIATUS")
    _titles(panel)
    _keys(panel, "down", "text:s")

    frame: str = _frame(panel)
    assert "Nie wiadomo, ile odcinków już wyemitowano" in frame
    assert "Dodaj subskrypcję" not in frame
    assert "\u276f [ Anuluj ]" in frame


def test_the_list_counts_down_with_the_renderer_clock(panel: StateController, clock: _Clock) -> None:
    panel._subscriptions = [_row("a", "Alpha", due_at=(_NOW + timedelta(minutes=30)).isoformat(), due_number=8)]
    assert "Emisja E8 za 00:30:00" in _frame(panel)

    clock.now += timedelta(seconds=1)

    assert "Emisja E8 za 00:29:59" in _frame(panel)


def test_f_shows_the_check_result_in_the_row_for_ten_seconds(
    panel: StateController, owner: _Owner, clock: _Clock
) -> None:
    panel._selected = 1
    _keys(panel, "text:f")
    assert ("subscription_check", {"subscription_id": "a"}) in owner.calls
    assert "Sprawdzam…" in _frame(panel)

    panel._receive_check(
        {
            "subscription_id": "a",
            "last_check": {"number": 6, "matching": 0, "uncertain": 8, "mismatched": 4, "outcome": "no_match"},
        }
    )
    assert "Sprawdzono E6: 12 kandydatów, 0 zgodnych (8 niepewnych, 4 niezgodnych)" in _frame(panel)

    clock.now += timedelta(seconds=11)

    assert "Sprawdzono E6" not in _frame(panel)
    assert "Termin nieznany" in _frame(panel)


@pytest.mark.parametrize(
    ("problem", "auto_enabled", "banner"),
    [
        ("", True, "Tryb cienia — subskrypcje tylko zapisują propozycje"),
        ("", False, "AniShift wstrzymany — subskrypcje czekają"),
        ("save_failed", False, "Monitoring nie działa: nie można zapisać stanu"),
    ],
)
def test_the_shadow_banner_yields_to_the_pause_and_to_a_monitoring_problem(
    panel: StateController, problem: str, auto_enabled: bool, banner: str
) -> None:
    panel._subscriptions_shadow = True
    panel._subscriptions_problem = problem
    panel._snapshot = {"auto_enabled": auto_enabled}

    assert banner in _frame(panel)


def _details(owner: _Owner) -> None:
    owner.listings[1] = replace(
        _listing(episodes=_weekly(2, 4), count=4),
        anilist_id=1,
        specials=(ListedSpecial("S1", "OVA", None),),
    )
    owner.details = {
        "first_target": 3,
        "last_target": 6,
        "last_check": {
            "checked_at": _NOW.isoformat(),
            "number": 3,
            "matching": 0,
            "uncertain": 0,
            "mismatched": 0,
            "outcome": "no_candidates",
        },
    }


def test_enter_opens_the_subscription_details_with_header_targets_and_specials(
    panel: StateController, owner: _Owner
) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter")

    frame: str = _frame(panel)
    assert panel._tab == _Tab.ANIME
    assert "Subskrypcje \u203a Alpha" in frame
    assert "Od odc. 3 · Pobrano 1/4 · Gotowe 0 · Termin nieznany" in frame
    assert "Sprawdzono E3: brak wydań w źródle" in frame
    specials: list[str] = [line for line in frame.splitlines() if "Dodatki tego sezonu" in line or "OVA" in line]
    assert len(specials) == 2
    assert all("[ ]" not in line for line in specials)
    assert "W wstrzymaj · F szukaj teraz · X usuń · Esc lista" in frame
    assert owner.numbers[-1] == (1, 2, 3, 4, 5, 6)


@pytest.mark.parametrize(
    ("key", "kind"),
    [("text:w", "subscription_pause"), ("text:f", "subscription_check")],
)
def test_details_keys_send_the_subscription_command_and_stay(
    panel: StateController, owner: _Owner, key: str, kind: str
) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter", key)

    assert (kind, {"subscription_id": "a"}) in owner.calls
    assert panel._tab == _Tab.ANIME
    assert _anime(panel)._screen is _Screen.EPISODES


@pytest.mark.parametrize("key", ["text:x", "delete"])
def test_removing_from_the_details_returns_to_the_list_with_undo(
    panel: StateController, owner: _Owner, key: str
) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter", key)

    assert ("subscription_remove", {"subscription_id": "a"}) in owner.calls
    assert panel._tab == _Tab.SUBSCRIPTIONS
    assert "Usunięto Alpha · Ctrl+Z cofnij" in _frame(panel)


def test_esc_from_the_details_returns_to_the_list(panel: StateController, owner: _Owner) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter", "escape")

    assert panel._tab == _Tab.SUBSCRIPTIONS
    assert panel._selected == 1


def test_a_check_finished_while_the_details_are_open_updates_their_header(
    panel: StateController, owner: _Owner
) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter")

    panel._receive_check(
        {
            "subscription_id": "a",
            "last_check": {"checked_at": _NOW.isoformat(), "number": 3, "matching": 1, "outcome": "proposed"},
        }
    )

    assert "Sprawdzono E3: 1 kandydat, 1 zgodnych · propozycja zapisana" in _frame(panel)


@pytest.mark.parametrize(("columns", "rows"), [(120, 30), (50, 24), (50, 12)])
@pytest.mark.parametrize("screen", ["draft", "details"])
def test_the_draft_and_the_details_fit_narrow_and_short_terminals(
    panel: StateController, owner: _Owner, screen: str, columns: int, rows: int
) -> None:
    _details(owner)
    if screen == "draft":
        _titles(panel)
        _keys(panel, "down", "text:s")
    else:
        panel._selected = 1
        _keys(panel, "enter")

    lines: list[str] = _frame(panel, columns, rows).splitlines()

    assert len(lines) <= rows
    assert all(Text(line).cell_len <= columns for line in lines)


def test_targets_beyond_the_catalogue_stay_listed_with_the_count_conflict_in_the_list_and_details(
    panel: StateController, owner: _Owner
) -> None:
    _details(owner)
    conflict: str = "AniList podaje 4 odcinki, a subskrypcja czeka na E6"
    panel._subscriptions = [_row("a", "Alpha", episode_count=4, beyond_count=6)]
    assert conflict in _frame(panel)

    panel._selected = 1
    _keys(panel, "enter")
    frame: str = _frame(panel)

    assert conflict in frame
    assert "Odcinek 5" in frame
    assert "Odcinek 6" in frame


def _beyond_target(
    panel: StateController, owner: _Owner, monkeypatch: pytest.MonkeyPatch, state: str, reason: str
) -> threading.Event:
    reached: threading.Event = threading.Event()

    def statuses(identifier: int, numbers: tuple[int, ...]) -> tuple[EpisodeStatus, ...]:
        del numbers
        return (EpisodeStatus(EpisodeKey(identifier, 6), state, reason, "previous"),)

    def boundary(*args: object, **kwargs: object) -> None:
        del args, kwargs
        reached.set()
        raise OSError

    monkeypatch.setattr(owner, "episode_states", statuses)
    monkeypatch.setattr(owner, "episode_download", boundary, raising=False)
    monkeypatch.setattr(owner, "episode_offer", boundary, raising=False)
    panel._selected = 1
    _keys(panel, "enter")
    _frame(panel)
    _keys(panel, "end")
    _frame(panel)
    anime: AnimeController = _anime(panel)
    assert anime._view.items[anime._view.cursor].key == "6"
    return reached


@pytest.mark.parametrize("key", ["text:d", "text:i", "text:p"])
@pytest.mark.parametrize("empty", [False, True])
def test_d_i_and_p_on_a_target_beyond_the_catalogue_reach_the_owner(
    panel: StateController, owner: _Owner, monkeypatch: pytest.MonkeyPatch, key: str, empty: bool
) -> None:
    _details(owner)
    if empty:
        owner.listings[1] = replace(owner.listings[1], episodes=())
    reached: threading.Event = _beyond_target(panel, owner, monkeypatch, "failed", "source_failed")
    assert {"3", "4", "5", "6"} <= {item.key for item in _anime(panel)._view.items}

    _keys(panel, key)

    assert reached.wait(5)


def test_a_target_the_owner_reports_as_not_aired_is_not_sent(
    panel: StateController, owner: _Owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _details(owner)
    reached: threading.Event = _beyond_target(panel, owner, monkeypatch, "not_ordered", "subscription_awaiting_airing")

    _keys(panel, "text:d")

    assert not reached.is_set()
    assert "E6 jeszcze nie wyemitowano" in _frame(panel)


def test_a_related_ova_is_listed_in_the_details_and_enter_opens_its_episodes(
    panel: StateController, owner: _Owner
) -> None:
    _details(owner)
    owner.extras = (
        FranchiseEntry(
            9, "Slime OVA", "Slime OVA", None, "OVA", "FINISHED", 2025, None, "SIDE_STORY", EntryGroup.EXTRA
        ),
    )
    owner.listings[9] = replace(_listing("FINISHED", episodes=_weekly(1, 1), count=1), anilist_id=9)
    panel._selected = 1
    _keys(panel, "enter")
    assert "Slime OVA" in _frame(panel)

    _keys(panel, "end", "enter")

    assert ("episodes", 9) in owner.calls
    assert _anime(panel)._screen is _Screen.EPISODES
    assert "Subskrypcje \u203a" not in _frame(panel)


def test_the_draft_description_is_reachable_by_keyboard_in_a_short_terminal(panel: StateController) -> None:
    _titles(panel)
    _keys(panel, "down", "text:s")
    assert "\u276f [ Dodaj subskrypcję ]" in _frame(panel)
    _keys(panel, "down", "up")
    assert "\u276f [ Dodaj subskrypcję ]" in _frame(panel)
    frames: list[str] = [_frame(panel, 50, 12)]
    assert "\u276f [ Dodaj subskrypcję ]" in frames[0]

    for _ in range(12):
        _keys(panel, "up")
        frames.append(_frame(panel, 50, 12))

    assert any("Tytuł:" in frame for frame in frames)
    assert any("Od odc.:   1" in frame for frame in frames)
    assert any("Koniec:" in frame for frame in frames)


def test_the_details_keep_every_subscription_key_visible_in_a_narrow_terminal(
    panel: StateController, owner: _Owner
) -> None:
    _details(owner)
    panel._selected = 1
    _keys(panel, "enter")

    frame: str = _frame(panel, 50, 24)

    for hint in ("D pobierz", "P ponownie", "W wstrzymaj", "F szukaj", "X usuń", "Esc lista"):
        assert hint in frame
