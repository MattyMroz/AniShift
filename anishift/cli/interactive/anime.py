"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from math import ceil
from time import sleep, time
from typing import Final
from uuid import uuid4

from natsort import natsorted
from prompt_toolkit.mouse_events import MouseEvent
from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    EpisodeBatch,
    EpisodeFile,
    EpisodeFiles,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeOfferView,
    EpisodeReason,
    EpisodeResult,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    IdentityVerdict,
    ListedEpisode,
    RankedCandidate,
    SearchQuery,
    TitleCandidate,
    TitleStatus,
    decode_view,
    parse_query,
    premiere_order,
    visible,
)
from anishift.application.cancellation import EventCancellationToken
from anishift.application.episode_commands import MAX_EPISODE_KEYS
from anishift.cli.interactive.actions import Action, ScreenActions, footer_segments, help_lines
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_releases import candidate_reason, release_rows, repeat_warning, suggested_position
from anishift.cli.interactive.anime_rows import (
    draft_rows,
    entry_rows,
    episode_row,
    file_rows,
    special_rows,
    text_rows,
    title_rows,
)
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeViewState, NoticeKind
from anishift.cli.interactive.anime_texts import (
    COMMAND_FAILED,
    EPISODE_REASON_LABELS,
    IN_PROGRESS_HINT,
    UNAVAILABLE,
    error_code,
    refused_result,
    safe,
    stated,
)
from anishift.cli.interactive.anime_view import WIDE_COLUMNS, overflows, shown_rows
from anishift.cli.interactive.pointer import Click, ClickKind
from anishift.cli.interactive.subscription_texts import (
    SubscriptionDraft,
    SubscriptionState,
    check_text,
    episode_label,
    notice_line,
    polish_line,
    row_state,
    row_summary,
    subscription_draft,
    watched_line,
)
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError, ControlErrorCode
from anishift.utils.logger import get_logger

__all__ = ["EPISODE_REASON_LABELS", "AnimeController", "AnimeResult"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_WORKER_NAME: Final[str] = "anishift-anime"
"""Name of the thread carrying every search and download of this screen."""

_SEARCHING_TITLE: Final[str] = "Szukam tytułu…"
"""Sentence shown while the anime catalog names the title behind the typed phrase."""

_LOADING_ENTRIES: Final[str] = "Wczytuję wpisy…"
"""Sentence shown while the franchise of a title is fetched."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_ADDING: Final[str] = "Dodaję subskrypcję…"
"""Sentence shown while the owner reads the season and saves a new subscription."""

_NOT_AIRING: Final[str] = "Ten wpis nie ma przyszłych odcinków"
"""Notice for S on an entry that cannot be subscribed."""

_ANNOUNCED: Final[str] = "Zapowiedź · odcinków jeszcze nie ma · S subskrybuj"
"""Notice for Enter on an announced entry, which opens nothing."""


_COPY: Final[tuple[Action, ...]] = (("C", "kopiuj"),)
"""Copy action of every Anime screen showing rows."""

_LISTED: Final[tuple[Action, ...]] = (("/", "szukaj"), *_COPY)
"""Actions every catalogue list lists only under ?."""

_MAX_BATCH: Final[int] = MAX_EPISODE_KEYS
"""Most episodes one D press sends to the owner, matching its batch limit."""

_BATCH_POLL_S: Final[float] = 1.0
"""Pause between reads of one accepted episode batch receipt."""

_BATCH_WAIT_S: Final[float] = 180.0
"""Longest time the panel follows one episode batch before leaving it to the owner."""


class AnimeResult(StrEnum):
    """Signal whether the anime controller stays open, returns Home or returns to the subscription list."""

    CONTINUE = "continue"
    HOME = "home"
    SUBSCRIPTIONS = "subscriptions"


class _Screen(StrEnum):
    QUERY = "query"
    TITLES = "titles"
    BUSY = "busy"
    PROBLEM = "problem"
    ENTRIES = "entries"
    EPISODES = "episodes"
    FILES = "files"
    CANDIDATES = "candidates"
    DRAFT = "draft"


_NO_HELP: Final[frozenset[_Screen]] = frozenset({_Screen.QUERY, _Screen.BUSY, _Screen.PROBLEM})
"""Screens whose footer offers no ? help."""


class AnimeController:
    """Own one ephemeral release search while AppService owns the network boundary."""

    def __init__(
        self,
        service: AppService,
        invalidate: Callable[[], None],
        *,
        resident: ResidentSession | None = None,
    ) -> None:
        self._service: AppService = service
        self._resident: ResidentSession | None = resident
        self._acquisition: AcquisitionService | ResidentSession | None = resident or service.acquisition
        self._invalidate: Callable[[], None] = invalidate
        self._lock: threading.RLock = threading.RLock()
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._current_screen: _Screen = _Screen.QUERY
        self._query_input: TextInput = TextInput()
        self._input_focused: bool = False
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._titles_shown: bool = False
        self._entries_skipped: bool = False
        self._highlighted: int = 0
        self._range_input: TextInput | None = None
        self._busy: str = _SEARCHING_TITLE
        self._work_sending: bool = False
        self._notice: str = ""
        self._problem: str = ""
        self._suggestion: str = ""
        self._problem_return: _Screen = _Screen.QUERY
        self._clock: Callable[[], float] = time
        self._show_list: Callable[[str | None, str], None] | None = None
        self._notify_list: Callable[[str], None] | None = None
        self._list_batch: str | None = None
        self._list_notice: str | None = None
        self._list_hold: bool = False
        self._subscription_command: tuple[str, Mapping[str, object], int | None] | None = None
        self._subscribed: dict[int, Mapping[str, object]] = {}
        self._paused: bool = False
        self._from_subscriptions: bool = False
        self._subscription: Mapping[str, object] | None = None
        self._subscription_details: Mapping[str, object] = {}
        self._draft: SubscriptionDraft | None = None
        self._draft_id: int = 0
        self._draft_title: str = ""
        self._draft_return: _Screen = _Screen.QUERY
        self._draft_cursor: str = ""
        self._draft_command: str = ""
        self._draft_listing: EpisodeListing | None = None
        self._draft_marks: set[int] = set()
        self._initialize_episode_state()
        self._view: AnimeViewState = AnimeViewState(query=self._query_input, query_focused=False)
        self._panel: AnimePanel = AnimePanel(self._view, self._panel_action, self._now)
        self._notice_kind: NoticeKind = NoticeKind.INFO
        if self._acquisition is None:
            self._screen = _Screen.PROBLEM
            self._problem = UNAVAILABLE

    def _initialize_episode_state(self) -> None:
        self._franchise: Franchise | None = None
        self._entry: FranchiseEntry | None = None
        self._shown_entry: FranchiseEntry | None = None
        self._listing: EpisodeListing | None = None
        self._episode_marks: set[int] = set()
        self._offer: EpisodeOffer | None = None
        self._offers_running: bool = False
        self._release_candidates: tuple[RankedCandidate, ...] = ()
        self._positions: dict[_Screen, int] = {}
        self._offsets: dict[_Screen, int] = {}
        self._visible_count: int = 1
        self.lead: int = 0
        self._follow_cursor: bool = True
        self._release_moved: bool = False
        self._busy_return: _Screen = _Screen.QUERY
        self._work_cancel: EventCancellationToken = EventCancellationToken()
        self._provider_locks: dict[str, float] = {}
        self._problem_provider: str = ""
        self._sending: set[EpisodeKey] = set()
        self._episode_states: dict[EpisodeKey, EpisodeStatus] = {}
        self._offer_view: EpisodeOfferView | None = None
        self._offer_id: str | None = None
        self._offer_refreshing: bool = False
        self._offer_refresh_pending: bool = False
        self._choice_sending: bool = False
        self._confirm_view: EpisodeOfferView | None = None
        self._files: EpisodeFiles | None = None
        self._confirm_choice: RankedCandidate | None = None
        self._pending_batch: EpisodeBatch | None = None
        self._batch_listing: EpisodeListing | None = None
        self._batch_running: bool = False
        self._batch_results: dict[EpisodeKey, EpisodeResult] = {}
        self._stale: bool = False
        self._details_open: bool = False
        self._columns: int = WIDE_COLUMNS

    @property
    def _screen(self) -> _Screen:
        return self._current_screen

    @_screen.setter
    def _screen(self, screen: _Screen) -> None:
        self._current_screen = screen
        if screen in {_Screen.QUERY, _Screen.TITLES, _Screen.ENTRIES}:
            self._shown_entry = None

    def handle_key(self, key: str) -> AnimeResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            self._sync_view()
            if key in {"interrupt", "copy", "text:c", "text:C"} and self._panel.copy(key):
                self._notice = self._view.notice
                self._notice_kind = self._view.notice_kind
                return AnimeResult.CONTINUE
            if self._handle_input(key):
                return AnimeResult.CONTINUE
            key = "escape" if key == "backspace" else key
            if self._details_open:
                if key in {"escape", "interrupt", "text:?"}:
                    self._details_open = False
                    self._view.selection = None
                else:
                    self._panel.handle(key)
                return AnimeResult.CONTINUE
            self._notice_kind = NoticeKind.INFO
            if self._pending_batch is not None and key == "enter" and not self._batch_running:
                self._resume_batch()
                return AnimeResult.CONTINUE
            if self._stale and key.casefold() in {"text:d", "text:p", "enter"}:
                self._notice = "Widok nieaktualny · otwórz odcinki ponownie"
                self._notice_kind = NoticeKind.WARNING
                return AnimeResult.CONTINUE
            if self._screen is _Screen.QUERY:
                result: AnimeResult = self._handle_query(key)
            elif self._screen is _Screen.TITLES:
                result = self._panel_key(key)
            elif self._screen is _Screen.BUSY:
                result = self._handle_busy(key)
            elif self._screen in {_Screen.ENTRIES, _Screen.EPISODES, _Screen.FILES, _Screen.CANDIDATES, _Screen.DRAFT}:
                result = self._draft_mark_key(key) or self._subscription_key(key) or self._panel_key(key)
            else:
                result = self._handle_problem(key)
        return result

    def _panel_key(self, key: str) -> AnimeResult:
        self._panel.handle(key)
        self._adopt_view_input()
        return AnimeResult.CONTINUE

    def link_subscriptions(
        self, show_list: Callable[[str | None, str], None], notify_list: Callable[[str], None]
    ) -> None:
        """Receive the panel callbacks that open the subscription list and later update its notice."""
        with self._lock:
            self._show_list = show_list
            self._notify_list = notify_list

    def replay_list_batch(self) -> bool:
        """Replay the draft's order whose answer was lost, under its command ID, when one waits."""
        with self._lock:
            batch: EpisodeBatch | None = self._pending_batch
            if batch is None or batch.command_id != self._list_batch or self._batch_running:
                return False
            self._resume_batch()
            return True

    def _flush_list_notice(self) -> None:
        with self._lock:
            if self._list_hold:
                return
            notice: str | None = self._list_notice
            self._list_notice = None
            notify: Callable[[str], None] | None = self._notify_list
        if notice is not None and notify is not None:
            notify(notice)

    def refresh_subscriptions(self, rows: Sequence[Mapping[str, object]], *, paused: bool) -> None:
        """Project the owner's subscription rows used by drafts and the open subscription header."""
        with self._lock:
            self._subscribed = {key: row for row in rows if isinstance(key := row.get("anilist_id"), int)}
            self._paused = paused
            if self._subscription is not None:
                identifier: object = self._subscription.get("subscription_id")
                self._subscription = next(
                    (row for row in rows if row.get("subscription_id") == identifier), self._subscription
                )

    def take_subscription_command(self) -> tuple[str, Mapping[str, object], int | None] | None:
        """Hand one subscription command chosen in the details, with its target number, to the panel."""
        with self._lock:
            command: tuple[str, Mapping[str, object], int | None] | None = self._subscription_command
            self._subscription_command = None
            return command

    def start_subscription_search(self) -> None:
        """Open the title search on behalf of the subscription list, to which Esc returns."""
        with self._lock:
            self._generation += 1
            self._subscription = None
            self._from_subscriptions = True
            self._details_open = False
            self._screen = _Screen.QUERY
            self._input_focused = True

    @property
    def in_subscriptions(self) -> bool:
        """Whether the shown screen serves the subscription list: U08 or a search started there."""
        with self._lock:
            return self._from_subscriptions

    def leave_subscriptions(self) -> None:
        """Drop the subscription context so the Anime tab shows its own search."""
        with self._lock:
            self._leave_subscriptions()

    def open_subscription(self, row: Mapping[str, object]) -> None:
        """Show the episodes of one followed season under its subscription header."""
        with self._lock:
            self._open_subscription(row)

    def _open_subscription(self, row: Mapping[str, object]) -> None:
        self._subscription = row
        self._subscription_details = {}
        self._from_subscriptions = True
        self._details_open = False
        self._episode_marks.clear()
        self._positions[_Screen.EPISODES] = 0
        self._offsets[_Screen.EPISODES] = 0
        generation: int = self._start_work("Wczytuję odcinki…", _Screen.QUERY)
        self._spawn(self._load_subscription, (row, generation, self._work_cancel))

    def subscription_checked(self, subscription_id: str, check: Mapping[str, object]) -> None:
        """Show a finished check in the header of the open subscription."""
        with self._lock:
            if self._subscription is None or self._subscription.get("subscription_id") != subscription_id:
                return
            self._subscription_details = {**self._subscription_details, "last_check": check}
            self._notice = ""

    def _subscription_key(self, key: str) -> AnimeResult | None:
        row: Mapping[str, object] | None = self._subscription
        if row is None or self._screen is not _Screen.EPISODES:
            return None
        folded: str = key.casefold()
        if folded == "text:/":
            self._leave_subscriptions()
            self.start_subscription_search()
            return AnimeResult.CONTINUE
        kind: str | None = {
            "text:w": "subscription_resume" if row.get("paused") else "subscription_pause",
            "text:r": "subscription_check",
            "text:f": "subscription_check",
            "text:x": "subscription_remove",
            "delete": "subscription_remove",
        }.get(folded)
        number: int | None = self._waiting_number() if folded == "text:t" else None
        if number is not None:
            kind = "subscription_check"
        if kind is not None:
            self._subscription_command = (kind, row, number)
            self._notice = "Sprawdzam…" if kind == "subscription_check" else ""
        if kind == "subscription_remove" or key in {"escape", "interrupt"}:
            self._leave_subscriptions()
            return AnimeResult.SUBSCRIPTIONS
        return None if kind is None else AnimeResult.CONTINUE

    def _waiting_number(self) -> int | None:
        status: EpisodeStatus | None = self._cursor_status()
        return None if status is None or status.polish_wait_until is None else status.key.number

    def _cursor_status(self) -> EpisodeStatus | None:
        listing: EpisodeListing | None = self._listing
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        position: int = self._positions.get(_Screen.EPISODES, 0)
        if listing is None or position >= len(shown):
            return None
        return self._episode_states.get(EpisodeKey(listing.anilist_id, shown[position].number))

    def _leave_subscriptions(self) -> None:
        self._generation += 1
        self._subscription = None
        self._subscription_details = {}
        self._from_subscriptions = False
        self._range = None
        self._episode_marks.clear()
        self._details_open = False
        self._notice = ""
        self._screen = _Screen.QUERY

    def _load_subscription(self, row: Mapping[str, object], generation: int, cancel: EventCancellationToken) -> None:
        anilist_id: object = row.get("anilist_id")
        if self._resident is None or self._acquisition is None or not isinstance(anilist_id, int):
            self._fail(generation, UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            details: Mapping[str, object] = self._resident.command(
                "subscription_get", {"subscription_id": row.get("subscription_id")}
            )
            franchise: Franchise = self._acquisition.franchise(anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.QUERY, "anilist")
            return
        entry: FranchiseEntry | None = next((item for item in franchise.entries if item.anilist_id == anilist_id), None)
        if entry is None:
            self._fail(generation, "Katalog nie zawiera już tego wpisu", "", _Screen.QUERY)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._subscription_details = details
            self._adopt_franchise(franchise)
            self._entries_skipped = False
            self._entry = entry
            self._shown_entry = entry
            self._listing = None
        self._load_episodes(entry, generation)

    def _start_draft(self) -> None:
        anilist_id, title, listing = self._draft_source()
        if anilist_id is None:
            return
        self._draft_return = self._screen
        self._draft_command = uuid4().hex
        self._draft_id = anilist_id
        self._draft_title = title
        if anilist_id in self._subscribed or listing is not None:
            self._open_draft(listing)
            return
        generation: int = self._start_work("Wczytuję odcinki…", self._screen)
        self._spawn(self._load_draft, (anilist_id, generation))

    def _draft_source(self) -> tuple[int | None, str, EpisodeListing | None]:
        if self._screen is _Screen.TITLES and self._candidates:
            candidate: TitleCandidate = self._candidates[self._highlighted]
            return candidate.anilist_id, candidate.english or candidate.romaji, None
        if self._screen is _Screen.ENTRIES and self._franchise is not None and self._franchise.entries:
            entry: FranchiseEntry = self._franchise.entries[self._positions.get(_Screen.ENTRIES, 0)]
            return entry.anilist_id, entry.english or entry.romaji, None
        if self._screen is _Screen.EPISODES and self._listing is not None and self._entry is not None:
            return self._listing.anilist_id, self._entry.english or self._entry.romaji, self._listing
        return None, "", None

    def _load_draft(self, anilist_id: int, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            listing: EpisodeListing = self._acquisition.episodes(anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, self._draft_return, "anizip")
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._episode_states.update(states)
            self._open_draft(listing)
        self._invalidate()

    def _open_draft(self, listing: EpisodeListing | None) -> None:
        self._screen = self._draft_return
        if self._draft_id not in self._subscribed:
            draft: SubscriptionDraft | None = (
                None if listing is None else subscription_draft(listing, self._moment(), paused=self._paused)
            )
            if draft is None:
                self._notice = _NOT_AIRING
                self._notice_kind = NoticeKind.WARNING
                return
            self._draft = draft
        else:
            self._draft = None
        self._draft_listing = listing
        self._draft_marks = {item.number for item in self._draft_episodes()}
        self._draft_cursor = ""
        self._offsets[_Screen.DRAFT] = 0
        self._follow_cursor = True
        self._screen = _Screen.DRAFT

    def _draft_episodes(self) -> tuple[ListedEpisode, ...]:
        listing: EpisodeListing | None = self._draft_listing
        if self._draft is None or listing is None:
            return ()
        return tuple(item for item in self._draft.aired if self._unordered(EpisodeKey(listing.anilist_id, item.number)))

    def _unordered(self, key: EpisodeKey) -> bool:
        status: EpisodeStatus | None = self._episode_states.get(key)
        return key not in self._sending and (status is None or status.state == "not_ordered")

    def _draft_mark_key(self, key: str) -> AnimeResult | None:
        if self._screen is not _Screen.DRAFT or key.casefold() not in {"space", "text:a"}:
            return None
        self._toggle_draft(every=key.casefold() == "text:a")
        return AnimeResult.CONTINUE

    def _toggle_draft(self, *, every: bool) -> None:
        numbers: set[int] = {item.number for item in self._draft_episodes()}
        if every:
            self._draft_marks = set() if numbers <= self._draft_marks else numbers
            return
        chosen: str = self._view.items[self._view.cursor].key if self._view.items else ""
        if chosen.startswith("ep:"):
            self._draft_marks ^= {int(chosen.removeprefix("ep:"))}

    def _draft_key(self, key: str) -> None:
        if key in {"escape", "interrupt"}:
            self._screen = self._draft_return
            return
        if key != "enter" or not self._view.items:
            return
        chosen: str = self._view.items[self._view.cursor].key
        if chosen.startswith("ep:"):
            self._toggle_draft(every=False)
        elif chosen == "cancel":
            self._screen = self._draft_return
        elif chosen == "show" and self._draft_id in self._subscribed:
            self._open_subscription(self._subscribed[self._draft_id])
        elif chosen == "add" and self._resident is not None:
            self._add_draft()

    def _add_draft(self) -> None:
        keys: tuple[EpisodeKey, ...] = tuple(
            EpisodeKey(self._draft_id, item.number)
            for item in self._draft_episodes()
            if item.number in self._draft_marks
        )
        if keys and self._pending_batch is not None:
            self._notice = "Trwa partia · Enter sprawdź wynik"
            return
        if len(keys) > _MAX_BATCH:
            self._notice = "Limit: 100 odcinków · A odznacz wszystkie"
            return
        generation: int = self._start_work(_ADDING, _Screen.DRAFT, sending=True)
        self._spawn(self._add_subscription, (self._draft_id, self._draft_command, keys, generation))

    def _add_subscription(
        self, anilist_id: int, command_id: str, keys: tuple[EpisodeKey, ...], generation: int
    ) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        try:
            answer: Mapping[str, object] = resident.subscription_add(anilist_id, command_id=command_id)
        except (AniShiftError, OSError, ValueError) as problem:
            with self._lock:
                if generation != self._generation:
                    return
                self._worker = None
                self._screen = _Screen.DRAFT
                self._notice = stated(problem)[0]
                self._notice_kind = NoticeKind.WARNING
            self._invalidate()
            return
        identifier: object = answer.get("subscription_id")
        refusal: str = self._order_aired(resident, keys)
        show_list: Callable[[str | None, str], None] | None = None
        with self._lock:
            if generation == self._generation:
                self._worker = None
                self._from_subscriptions = False
                self._screen = self._draft_return
                show_list = self._show_list
        if show_list is not None:
            show_list(
                identifier if isinstance(identifier, str) else None,
                f"Dodano subskrypcję · {refusal}" if refusal else "",
            )
        with self._lock:
            self._list_hold = False
        self._flush_list_notice()
        self._invalidate()

    def _order_aired(self, resident: ResidentSession, keys: tuple[EpisodeKey, ...]) -> str:
        with self._lock:
            listing: EpisodeListing | None = self._draft_listing
            if not keys or listing is None or self._pending_batch is not None:
                return ""
            command_id: str = self._open_batch(listing, keys)
            self._batch_running = True
            self._list_hold = True
        try:
            batch: EpisodeBatch = resident.episode_download(keys, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime aired episodes order failed", error_class=type(problem).__name__)
            with self._lock:
                notice: str = self._batch_failed(problem, keys)
                if self._pending_batch is not None:
                    self._list_batch = command_id
                return notice
        with self._lock:
            self._batch_running = False
            self._accept_batch(batch)
            if self._pending_batch is None:
                return self._refusals(keys)
            self._list_batch = command_id
            self._resume_batch()
        return ""

    def _sync_subscription_view(self) -> None:
        if self._screen is _Screen.DRAFT:
            self._view.crumbs = ("Nowa subskrypcja", safe(self._draft_title))
            keys: list[str] = [item.key for item in self._view.items]
            wanted: str = self._draft_cursor if self._draft_cursor in keys else self._draft_cursor.split(".")[0] + ".0"
            if wanted not in keys:
                wanted = next((key for key in keys if key.startswith("ep:")), "") or next(
                    (key for key in keys if key in {"add", "cancel", "show"}), ""
                )
            if wanted in keys:
                self._view.cursor = keys.index(wanted)
                self._positions[_Screen.DRAFT] = self._view.cursor
            if self._view.items and not self._view.items[self._view.cursor].navigable:
                self._view.cursor = next(
                    (index for index, item in enumerate(self._view.items) if item.navigable), self._view.cursor
                )
        facts: tuple[str, ...] = self._subscription_facts()
        if not facts or self._subscription is None:
            return
        self._view.crumbs = ("Subskrypcje", facts[0])
        self._view.global_status = facts[1]
        self._view.status_kind = NoticeKind.INFO
        self._view.notice = self._view.notice or " · ".join(note for note in facts[2:] if note)

    def _subscription_facts(self) -> tuple[str, ...]:
        if self._screen is not _Screen.EPISODES or self._subscription is None:
            return ()
        state: SubscriptionState = row_state(self._subscription, self._moment())
        return (
            safe(str(self._subscription.get("title", ""))),
            f"{state.text} · {row_summary(self._subscription)}",
            self._last_check(),
            "" if state.detail == state.text else state.detail,
            self._polish_line(),
            self._notice_line(),
            watched_line(self._subscription),
        )

    def _polish_line(self) -> str:
        due: EpisodeStatus | None = self._focused_status(lambda item: item.polish is not None)
        if due is None:
            return ""
        return f"E{due.key.number} {polish_line(due.polish, due.polish_wait_until, skipped=due.polish_skipped)}"

    def _notice_line(self) -> str:
        noted: EpisodeStatus | None = self._focused_status(lambda item: bool(item.notices))
        return "" if noted is None else notice_line(noted.key.number, noted.notices)

    def _focused_status(self, shown: Callable[[EpisodeStatus], bool]) -> EpisodeStatus | None:
        """Return the highlighted episode state when it has the fact, else the lowest episode that has it."""
        listing: EpisodeListing | None = self._listing
        due: EpisodeStatus | None = self._cursor_status()
        if due is not None and shown(due):
            return due
        return min(
            (
                item
                for item in self._episode_states.values()
                if shown(item) and listing is not None and item.key.anilist_id == listing.anilist_id
            ),
            key=lambda item: item.key.number,
            default=None,
        )

    def _moment(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)

    def _last_check(self) -> str:
        check: object = self._subscription_details.get("last_check")
        if not isinstance(check, Mapping):
            return ""
        moment: object = check.get("checked_at")
        at: str = datetime.fromisoformat(moment).astimezone().strftime("%H:%M") if isinstance(moment, str) else "—"
        return f"Ostatnie sprawdzenie {at}: {check_text(check)}"

    def _now(self) -> float:
        return self._clock()

    def _adopt_view_input(self) -> None:
        if self._details_open:
            return
        self._adopt_cursor()
        if self._screen is _Screen.EPISODES:
            self._episode_marks = {int(key) for key in self._view.selected}
        if self._screen is _Screen.DRAFT and self._view.items:
            self._draft_cursor = self._view.items[self._view.cursor].key
        self._range_input = self._view.range_input
        self._input_focused = (
            self._view.query_focused if self._screen is _Screen.QUERY else self._range_input is not None
        )
        self._notice = self._view.notice
        self._notice_kind = self._view.notice_kind
        self._offsets[self._screen] = self._view.offset
        self._follow_cursor = True

    def refresh_provider_locks(self, locks: Sequence[Mapping[str, object]]) -> None:
        """Project owner retry deadlines without admitting or repeating a request."""
        deadlines: dict[str, float] = {}
        for item in locks:
            provider, until = item.get("provider"), item.get("until")
            if not isinstance(provider, str) or not isinstance(until, str):
                continue
            deadline: float | None = _deadline(until)
            if deadline is not None:
                deadlines[provider] = deadline
        with self._lock:
            self._provider_locks = deadlines

    def scroll(self, direction: int) -> None:
        """Scroll a catalogue view without changing its highlighted identity."""
        with self._lock:
            self._sync_view()
            self._panel.scroll(direction * 3)
            if not self._details_open:
                self._offsets[self._screen] = self._view.offset
            self._notice = ""
            self._follow_cursor = False

    def render(self, columns: int, rows: int, gap: int = 0) -> Text:
        """Render ``rows`` lines: a table overflowing ``rows - gap`` fills them, otherwise ``gap`` blank lines lead."""
        with self._lock:
            self._columns = min(columns - 4, WIDE_COLUMNS)
            self._sync_view()
            self._view.fill = overflows(self._view.screen, len(self._view.items), rows - gap)
            self.lead = 0 if self._view.fill else gap
            rows -= self.lead
            self._visible_count = max(shown_rows(self._view.snapshot(columns), columns, rows), 1)
            offset: int = min(
                self._view.offset if self._details_open else self._offsets.get(self._screen, 0),
                max(len(self._view.items) - self._visible_count, 0),
            )
            if self._follow_cursor:
                offset = max(min(offset, self._view.cursor), self._view.cursor - self._visible_count + 1)
            self._view.offset = offset
            if not self._details_open:
                self._offsets[self._screen] = offset
            return Text("\n").join([*(Text() for _ in range(self.lead)), self._panel.frame(columns, rows)])

    def mouse(self, event: MouseEvent) -> Click:
        """Delegate text selection and row clicks to the shared Anime panel and name what the click asks for."""
        with self._lock:
            self._sync_view()
            click: Click = self._panel.mouse(event)
            if self._details_open:
                return click
            if click.kind in {ClickKind.ROW, ClickKind.LINE}:
                self._adopt_cursor()
            self._notice = self._view.notice
            return click

    def place(self, index: int) -> None:
        """Focus the shown search or range field and put its cursor before a clicked character."""
        with self._lock:
            editor: TextInput | None = self._range_input
            if editor is None and self._screen is _Screen.QUERY:
                editor = self._query_input
            if editor is None:
                return
            editor.place(index)
            self._input_focused = True

    def points_at(self, index: int) -> bool:
        """Report whether the cursor of the shown list stands on row ``index``."""
        with self._lock:
            return self._view.cursor == index

    def breadcrumb(self) -> tuple[str, ...]:
        """Return the breadcrumb levels above the shown screen, none on the list levels."""
        with self._lock:
            self._sync_view()
            return self._view.crumbs

    def _adopt_cursor(self) -> None:
        if self._screen is _Screen.TITLES:
            self._highlighted = self._view.cursor
            return
        if self._screen is _Screen.CANDIDATES and self._view.cursor != self._positions.get(self._screen, 0):
            self._release_moved = True
        self._positions[self._screen] = self._view.cursor

    def _panel_action(self, action: str, keys: tuple[str, ...]) -> None:
        del keys
        self._adopt_view_input()
        key: str = {"back": "escape", "download": "text:d", "enter": "enter"}.get(action, f"text:{action}")
        if action == "?":
            self._details_open = True
            self._view.cursor = 0
            self._view.offset = 0
        elif action == "/":
            self._screen = _Screen.QUERY
            self._input_focused = True
        elif self._screen is _Screen.DRAFT:
            self._draft_key(key)
        elif key == "text:s":
            self._start_draft()
        elif self._screen is _Screen.TITLES:
            self._handle_titles(key)
        else:
            self._handle_episode_screen(key)
        self._sync_view()

    def _sync_view(self) -> None:
        screens: dict[_Screen, AnimeScreen] = {
            _Screen.QUERY: AnimeScreen.QUERY,
            _Screen.TITLES: AnimeScreen.TITLES,
            _Screen.ENTRIES: AnimeScreen.ENTRIES,
            _Screen.EPISODES: AnimeScreen.EPISODES,
            _Screen.FILES: AnimeScreen.FILES,
            _Screen.CANDIDATES: AnimeScreen.RELEASES,
            _Screen.BUSY: AnimeScreen.QUERY if self._busy_return is _Screen.QUERY else AnimeScreen.BUSY,
            _Screen.PROBLEM: AnimeScreen.PROBLEM,
            _Screen.DRAFT: AnimeScreen.DRAFT,
        }
        screen: AnimeScreen = screens.get(self._screen, AnimeScreen.DETAILS)
        previous_cursor: int = self._view.cursor
        if self._view.screen is not (AnimeScreen.DETAILS if self._details_open else screen):
            self._view.selection = None
            self._view.selected.clear()
        self._view.screen = screen
        self._view.title = ""
        self._view.crumbs = self._entry_heading()
        self._view.cursor = (
            self._highlighted if self._screen is _Screen.TITLES else self._positions.get(self._screen, 0)
        )
        self._view.query_focused = self._input_focused
        self._view.range_input = self._range_input
        self._view.notice = self._notice
        self._view.notice_kind = self._notice_kind
        self._view.global_status = ""
        self._view.status_kind = NoticeKind.WARNING
        self._view.busy = self._busy if self._screen is _Screen.BUSY else ""
        self._view.items = self._display_rows()
        self._view.cursor = min(self._view.cursor, max(len(self._view.items) - 1, 0))
        if screen is AnimeScreen.EPISODES:
            self._view.selected = {str(number) for number in self._episode_marks}
        if screen is AnimeScreen.DRAFT:
            self._view.selected = {f"ep:{number}" for number in self._draft_marks}
        self._view.searching = (
            {
                str(key.number)
                for key in self._sending
                if self._listing is not None and key.anilist_id == self._listing.anilist_id
            }
            if screen is AnimeScreen.EPISODES
            else set()
        )
        if self._choice_sending or (
            self._pending_batch is not None and screen in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}
        ):
            self._view.searching.add("pending")
        self._view.controls = footer_segments(self._screen_actions(), more=self._screen not in _NO_HELP)
        if self._screen is _Screen.PROBLEM:
            self._view.notice_kind = NoticeKind.WARNING
        elif self._screen is _Screen.CANDIDATES:
            self._view.notice = self._notice or " · ".join(repeat_warning(self._offer_view))
            if self._offer_view is not None and self._offer_view.unknown_previous:
                self._view.global_status = "Nie można potwierdzić odmienności wydania"
        elif self._screen is _Screen.ENTRIES and self._franchise is not None and not self._franchise.complete:
            self._view.notice = self._notice or "Lista niepełna"
        else:
            self._sync_subscription_view()
        if screen is AnimeScreen.RELEASES and self._offer_view is not None and self._offers_running:
            pending: str = ", ".join(self._offer_view.offer.pending) or "uzupełnienia spisów"
            self._view.global_status = f"szukam jeszcze: {pending}"
        if self._details_open:
            item: AnimeRow | None = self._view.items[self._view.cursor] if self._view.items else None
            self._view.screen = AnimeScreen.DETAILS
            self._view.items = text_rows(
                (
                    *self._subscription_facts(),
                    item.copy_text if item else "Anime",
                    item.detail if item else "",
                    *help_lines(self._screen_actions().listed, self._columns - 4),
                ),
                self._columns - 4,
            )
            self._view.cursor = min(previous_cursor, max(len(self._view.items) - 1, 0))
            self._view.controls = footer_segments(ScreenActions(_COPY), more=False)

    def _screen_actions(self) -> ScreenActions:
        actions: ScreenActions = self._base_actions()
        if self._screen is _Screen.QUERY or self._pending_batch is None or self._batch_running:
            return actions
        others: tuple[Action, ...] = tuple(action for action in actions.footer if action[0] != "Enter")
        return ScreenActions((("Enter", "sprawdź wynik"), *others), actions.more)

    def _base_actions(self) -> ScreenActions:  # noqa: PLR0911
        screen: _Screen = self._screen
        if screen is _Screen.QUERY:
            return ScreenActions((("Enter", "szukaj"),))
        if screen is _Screen.BUSY:
            return ScreenActions(more=() if self._busy_return is _Screen.QUERY else _COPY)
        if screen is _Screen.PROBLEM:
            return ScreenActions((("Enter", "pobierz mimo to" if self._confirm_choice else "wróć"),), _COPY)
        if screen in {_Screen.TITLES, _Screen.ENTRIES}:
            label: str = "wybierz" if screen is _Screen.TITLES else "odcinki"
            return ScreenActions((("Enter", label), ("S", "subskrybuj")), _LISTED)
        if screen is _Screen.FILES:
            return ScreenActions((("Enter", "wybierz"),), _LISTED)
        if screen is _Screen.CANDIDATES:
            return ScreenActions((("Space", "zaznacz"), ("D", "pobierz")), _LISTED)
        if screen is _Screen.DRAFT:
            if not self._draft_episodes():
                return ScreenActions((("Enter", "wybierz"),), _LISTED)
            return ScreenActions((("Enter", "wybierz"), ("Space", "zaznacz")), (("A", "wszystkie"), *_LISTED))
        return self._episode_actions()

    def _episode_actions(self) -> ScreenActions:
        enter: str = self._episode_enter()
        footer: list[Action] = [*((("Enter", enter),) if enter else ()), ("Space", "zaznacz"), ("D", "pobierz")]
        more: list[Action] = [("I", "wydania"), ("Z", "zakres"), ("A", "wszystkie"), ("P", "ponownie")]
        row: Mapping[str, object] | None = self._subscription
        if row is None:
            footer.append(("S", "subskrybuj"))
            return ScreenActions(tuple(footer), (*more, *_LISTED))
        toggle: Action = ("W", "wznów" if row.get("paused") else "wstrzymaj")
        waiting: bool = self._waiting_number() is not None
        footer.append(("T", "pobierz teraz") if waiting else toggle)
        subscription: tuple[Action, ...] = (*((toggle,) if waiting else ()), ("R", "sprawdź teraz"), ("X", "usuń"))
        return ScreenActions(tuple(footer), (*subscription, *more, ("S", "subskrybuj"), *_LISTED))

    def _episode_enter(self) -> str:
        listing: EpisodeListing | None = self._listing
        if listing is None:
            return ""
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        position: int = self._positions.get(_Screen.EPISODES, 0)
        if position >= len(shown):
            extras: tuple[AnimeRow, ...] = self._special_rows()[position - len(shown) :]
            return "otwórz" if extras and extras[0].key.startswith("related:") else ""
        status: EpisodeStatus | None = self._episode_states.get(EpisodeKey(listing.anilist_id, shown[position].number))
        if status is None or status.reason != EpisodeReason.EPISODE_FILE_UNRESOLVED or status.admission_id is None:
            return ""
        return "wskaż plik"

    def _display_rows(self) -> tuple[AnimeRow, ...]:  # noqa: PLR0911
        if self._screen is _Screen.TITLES:
            return title_rows(self._candidates)
        if self._screen is _Screen.ENTRIES:
            return entry_rows(self._franchise.entries) if self._franchise else ()
        if self._screen is _Screen.EPISODES:
            return self._episode_rows() + self._special_rows()
        if self._screen is _Screen.DRAFT:
            return draft_rows(self._draft, self._draft_episodes(), self._columns - 4)
        if self._screen is _Screen.FILES and self._files is not None:
            return file_rows(self._files)
        if self._screen is _Screen.CANDIDATES:
            offer: EpisodeOffer | None = self._offer
            self._view.global_status = offer.status or "" if offer is not None else ""
            return release_rows(
                self._release_candidates, offer, searching=self._offers_running and self._offer_view is None
            )
        if self._screen is _Screen.BUSY:
            return (AnimeRow("busy", self._busy, navigable=False),)
        if self._screen is _Screen.PROBLEM:
            hint: str = self._retry_hint(self._problem_provider) or self._suggestion
            return text_rows((self._problem, hint), self._columns - 4)
        return ()

    def _episode_rows(self) -> tuple[AnimeRow, ...]:
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        if self._listing is None or not shown:
            self._view.notice = self._notice or "Nie znam odcinków tego wpisu"
            return ()
        film: bool = self._entry is not None and self._entry.format == "MOVIE"
        rows: tuple[AnimeRow, ...] = tuple(
            episode_row(
                episode,
                self._episode_states.get(EpisodeKey(self._listing.anilist_id, episode.number)),
                film=film,
                eligible=self._episode_available(episode),
            )
            for episode in shown
        )
        if self._listing.schedule_warning and not self._notice:
            deadline: float = self._listing.schedule_retry_at.timestamp() if self._listing.schedule_retry_at else 0.0
            remaining: int = max(ceil(self._provider_locks.get("anilist", deadline) - self._clock()), 0)
            self._view.notice = "Brak terminów emisji (AniList) · " + (
                f"ponów za {remaining} s" if remaining else "wróć i otwórz ponownie"
            )
        return rows

    def _shown_episodes(self) -> tuple[ListedEpisode, ...]:
        if self._listing is None:
            return ()
        first: object = self._subscription_details.get("first_target")
        last: object = self._subscription_details.get("last_target")
        if self._subscription is None or not isinstance(first, int) or not isinstance(last, int):
            return self._listing.episodes
        known: set[int] = {item.number for item in self._listing.episodes}
        return (
            *self._listing.episodes,
            *(
                ListedEpisode(number, aired=self._target_aired(EpisodeKey(self._listing.anilist_id, number)))
                for number in range(first, last + 1)
                if number not in known
            ),
        )

    def _target_aired(self, key: EpisodeKey) -> bool:
        status: EpisodeStatus | None = self._episode_states.get(key)
        return status is None or status.reason != EpisodeReason.SUBSCRIPTION_AWAITING_AIRING

    def _special_rows(self) -> tuple[AnimeRow, ...]:
        if self._subscription is None or self._listing is None:
            return ()
        return special_rows(self._listing, self._franchise)

    def _open_extra(self, anilist_id: int) -> None:
        if self._franchise is None:
            return
        self._positions[_Screen.ENTRIES] = next(
            index for index, item in enumerate(self._franchise.entries) if item.anilist_id == anilist_id
        )
        self._subscription = None
        self._subscription_details = {}
        self._from_subscriptions = False
        self._entries_skipped = False
        self._start_episodes()

    def cancel(self) -> None:
        """Blur retained inputs and discard the result of network work still in flight."""
        with self._lock:
            self._from_subscriptions = self._from_subscriptions and self._subscription is not None
            self._input_focused = False
            self._generation += 1
            self._offers_running = False
            if self._confirm_choice is not None:
                self._screen = self._problem_return
            self._confirm_choice = None
            self._offer_view = None
            self._offer_id = None
            self._confirm_view = None
            if self._resident is not None:
                self._resident.interrupt_reads()
            if self._screen is _Screen.BUSY:
                self._stop_work()
                self._screen = self._busy_return
                self._worker = None

    @property
    def input_focused(self) -> bool:
        """Whether Anime currently owns cursor and selection navigation."""
        with self._lock:
            return self._input_focused

    @property
    def accepts_text(self) -> bool:
        """Whether a printable key is typed into a field instead of acting."""
        with self._lock:
            return self._input_focused or self._screen is _Screen.QUERY

    def _handle_input(self, key: str) -> bool:
        editor: TextInput | None = None
        if self._screen is _Screen.QUERY:
            editor = self._query_input
        elif self._screen is _Screen.EPISODES:
            editor = self._range_input
        if editor is None:
            return False
        if self._input_focused and key == "interrupt" and editor.handle(key):
            return True
        if self._screen is _Screen.EPISODES and key in {"escape", "interrupt"}:
            self._range = None
            return True
        if key in {"escape", "interrupt"} and self._input_focused:
            self._input_focused = False
            return True
        if not self._input_focused:
            if key == "enter" or (self._screen is _Screen.QUERY and key == "text:/"):
                self._input_focused = True
            elif self._screen is _Screen.QUERY and (
                key.startswith(("text:", "paste:")) or key in {"space", "paste", "backspace"}
            ):
                self._input_focused = True
                editor.handle(key)
            return key not in {"escape", "interrupt"}
        return editor.handle(key)

    def _back_out(self) -> AnimeResult:
        if not self._from_subscriptions:
            return AnimeResult.HOME
        self._from_subscriptions = False
        self._subscription = None
        return AnimeResult.SUBSCRIPTIONS

    def _handle_query(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return self._back_out()
        if key == "enter" and self._query.strip():
            self._start_search(self._query.strip())
        return AnimeResult.CONTINUE

    @property
    def _query(self) -> str:
        return self._query_input.text

    @property
    def _range(self) -> str | None:
        return None if self._range_input is None else self._range_input.text

    @_range.setter
    def _range(self, value: str | None) -> None:
        self._range_input = None if value is None else TextInput(value)
        self._input_focused = value is not None

    def _handle_titles(self, key: str) -> None:
        if key in {"escape", "interrupt"} or not self._candidates:
            self._screen = _Screen.QUERY
        elif key == "enter":
            self._start_franchise()
        elif key == "text:/":
            self._screen = _Screen.QUERY
            self._input_focused = True

    def _handle_busy(self, key: str) -> AnimeResult:
        if key not in {"escape", "interrupt"}:
            return AnimeResult.CONTINUE
        self._generation += 1
        self._stop_work()
        self._worker = None
        self._screen = self._busy_return
        return AnimeResult.CONTINUE

    def _stop_work(self) -> None:
        if self._work_sending:
            return
        self._work_cancel.cancel()
        if self._resident is not None:
            self._resident.interrupt_reads()

    def _handle_problem(self, key: str) -> AnimeResult:
        if self._confirm_choice is not None:
            choice: RankedCandidate = self._confirm_choice
            if key in {"escape", "interrupt", "enter"}:
                self._confirm_choice = None
                self._screen = self._problem_return
                if key == "enter":
                    self._choose_release(choice, confirmed=True, shown=self._confirm_view)
                self._confirm_view = None
            return AnimeResult.CONTINUE
        if key in {"escape", "interrupt"}:
            if self._problem_return in {
                _Screen.TITLES,
                _Screen.ENTRIES,
                _Screen.EPISODES,
                _Screen.FILES,
                _Screen.CANDIDATES,
                _Screen.DRAFT,
            }:
                self._screen = self._problem_return
                return AnimeResult.CONTINUE
            return self._back_out()
        if key != "enter":
            return AnimeResult.CONTINUE
        self._screen = self._problem_return
        self._problem = ""
        self._suggestion = ""
        return AnimeResult.CONTINUE

    def _handle_episode_screen(self, key: str) -> None:
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._back_episode_screen()
            return
        count: int = self._episode_screen_count()
        if not count:
            return
        if self._screen is _Screen.ENTRIES and key == "enter":
            self._start_episodes()
        elif self._screen is _Screen.EPISODES:
            self._episode_key(key)
        elif self._screen is _Screen.FILES and key == "enter":
            self._choose_file()
        elif self._screen is _Screen.CANDIDATES and key.casefold() == "text:d":
            chosen: RankedCandidate | None = (
                next((item for item in self._release_candidates if item.stream.info_hash in self._view.selected), None)
                if self._view.selected
                else self._release_candidates[self._view.cursor]
            )
            if chosen is not None:
                self._choose_release(chosen)

    def _episode_screen_count(self) -> int:
        if self._screen is _Screen.ENTRIES:
            return len(self._franchise.entries) if self._franchise else 0
        if self._screen is _Screen.EPISODES:
            return len(self._shown_episodes())
        if self._screen is _Screen.FILES:
            return len(self._files.files) if self._files is not None else 0
        return len(self._release_candidates)

    def _back_episode_screen(self) -> None:
        if self._screen in {_Screen.CANDIDATES, _Screen.FILES}:
            self._generation += 1
            self._offer_id = None
            self._offer_view = None
            if self._resident is not None:
                self._resident.interrupt_reads()
            self._worker = None
            self._offers_running = False
            self._screen = _Screen.EPISODES
        elif self._screen is _Screen.EPISODES:
            self._generation += 1
            if not self._entries_skipped:
                self._screen = _Screen.ENTRIES
            else:
                self._screen = _Screen.TITLES if self._titles_shown else _Screen.QUERY
        else:
            self._screen = _Screen.TITLES if self._titles_shown else _Screen.QUERY

    def _episode_key(self, key: str) -> None:
        listing: EpisodeListing | None = self._listing
        if listing is None:
            return
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        position: int = self._positions.get(_Screen.EPISODES, 0)
        if position >= len(shown):
            extra: str = self._special_rows()[position - len(shown)].key
            if key == "enter" and extra.startswith("related:"):
                self._open_extra(int(extra.removeprefix("related:")))
            return
        episode: ListedEpisode = shown[position]
        status: EpisodeStatus | None = self._episode_states.get(EpisodeKey(listing.anilist_id, episode.number))
        if key == "enter" and status is not None and status.reason == EpisodeReason.EPISODE_FILE_UNRESOLVED:
            if status.admission_id is not None:
                self._start_files(status.admission_id)
        elif (
            key.casefold() == "text:p"
            and status is not None
            and (status.state != "not_ordered" or status.admission_id is not None)
        ):
            self._start_owner_offer(episode, repeat=True)
        elif key.casefold() == "text:i":
            self._inspect_episode(episode)
        elif key.casefold() == "text:d":
            if self._resident is None:
                self._notice = UNAVAILABLE
            else:
                self._start_episode_download(listing, episode)

    def _inspect_episode(self, episode: ListedEpisode) -> None:
        if self._resident is not None and self._listing is not None:
            self._start_owner_offer(episode)
            return
        self._start_offers(episode)

    def _start_episode_download(self, listing: EpisodeListing, highlighted: ListedEpisode) -> None:
        if self._pending_batch is not None:
            self._notice = "Trwa partia · Enter sprawdź wynik"
            return
        selected: set[int] = self._episode_marks or {highlighted.number}
        if len(selected) > _MAX_BATCH:
            self._notice = "Limit: 100 odcinków · Z zmień zakres"
            return
        keys: tuple[EpisodeKey, ...] = tuple(
            EpisodeKey(listing.anilist_id, item.number)
            for item in self._shown_episodes()
            if item.number in selected and self._episode_available(item)
        )
        if not keys:
            self._notice = IN_PROGRESS_HINT if highlighted.aired else f"E{highlighted.number} jeszcze nie wyemitowano"
            return
        self._notice = "Szukam wydań…"
        self._open_batch(listing, keys)
        self._resume_batch()

    def _open_batch(self, listing: EpisodeListing, keys: tuple[EpisodeKey, ...]) -> str:
        self._sending.update(keys)
        command_id: str = uuid4().hex
        self._pending_batch = EpisodeBatch(command_id, "", keys, "accepted")
        self._batch_listing = listing
        self._batch_results.clear()
        self._view.batch_results.clear()
        return command_id

    def _batch_failed(self, problem: AniShiftError | OSError, keys: tuple[EpisodeKey, ...]) -> str:
        self._batch_running = False
        listed: bool = self._pending_batch is not None and self._pending_batch.command_id == self._list_batch
        notice: str = "Wynik nieznany · Enter sprawdź wynik"
        if isinstance(problem, ControlError) and problem.answered and problem.code is ControlErrorCode.REFUSED:
            self._pending_batch = None
            self._list_batch = None if listed else self._list_batch
            self._sending.difference_update(keys)
            notice = "Nie zlecono · " + stated(problem)[0]
        if listed:
            self._list_notice = notice
        return notice

    def _refusals(self, keys: tuple[EpisodeKey, ...]) -> str:
        causes: dict[str, list[int]] = {}
        for key in keys:
            result: EpisodeResult | None = self._batch_results.get(key)
            if result is None or result.reason != EpisodeReason.ADMITTED:
                causes.setdefault("przerwano" if result is None else refused_result(result.reason)[1], []).append(
                    key.number
                )
        named: str = " · ".join(
            f"{episode_label(numbers)}: {cause}" if cause else episode_label(numbers)
            for cause, numbers in causes.items()
        )
        return f"Nie zlecono {named}" if named else ""

    def _resume_batch(self) -> None:
        batch: EpisodeBatch | None = self._pending_batch
        if batch is None or self._batch_running or self._batch_listing is None:
            return
        self._batch_running = True
        threading.Thread(
            target=self._send_episodes,
            args=(self._batch_listing, batch.keys, batch.command_id, self._generation),
            name=_WORKER_NAME,
            daemon=True,
        ).start()

    def receive(self, event: str, payload: Mapping[str, object]) -> None:
        """Correlate owner results independently of navigation and retain unknown intentions."""
        if event == "episode_offer_partial":
            with self._lock:
                if self._offer_id is not None and payload.get("offer_id") == self._offer_id:
                    self.refresh_offer()
            return
        with self._lock:
            if event == "control_problem":
                self._stale = True
                self._notice = "Widok nieaktualny: odpowiedź przekracza limit"
                self._notice_kind = NoticeKind.WARNING
                return
            batch: EpisodeBatch | None = self._pending_batch
            if batch is None or payload.get("command_id") != batch.command_id:
                return
            if event == "episode_result":
                self._accept_result(
                    decode_view(EpisodeResult, {key: value for key, value in payload.items() if key != "command_id"})
                )
            elif event == "episode_batch":
                self._accept_batch(decode_view(EpisodeBatch, payload))
        self._invalidate()
        self._flush_list_notice()

    def _accept_result(self, result: EpisodeResult) -> None:
        batch: EpisodeBatch | None = self._pending_batch
        if batch is None or result.key not in batch.keys or result.key in self._batch_results:
            return
        self._batch_results[result.key] = result
        self._sending.discard(result.key)
        self._episode_states[result.key] = EpisodeStatus(
            result.key,
            "ordered" if result.reason == EpisodeReason.ADMITTED else "not_ordered",
            None if result.reason == EpisodeReason.ADMITTED else result.reason,
            result.admission_id,
            result.operation_id,
        )
        if self._listing is None or self._listing.anilist_id != result.key.anilist_id:
            return
        if result.reason == EpisodeReason.ADMITTED:
            self._episode_marks.discard(result.key.number)
        if self._screen is not _Screen.EPISODES or self._details_open:
            return
        self._sync_view()
        if result.reason == EpisodeReason.ADMITTED:
            self._panel.result(str(result.key.number), admitted=True)
        else:
            status, cause = refused_result(result.reason)
            self._panel.result(str(result.key.number), admitted=False, status=status, cause=cause)
        self._notice = self._view.notice
        self._notice_kind = self._view.notice_kind

    def _accept_batch(self, batch: EpisodeBatch) -> None:
        pending: EpisodeBatch | None = self._pending_batch
        if pending is None or batch.command_id != pending.command_id or batch.keys != pending.keys:
            return
        for result in batch.results:
            self._accept_result(result)
        if batch.state == "accepted":
            return
        self._sending.difference_update(batch.keys)
        self._pending_batch = None
        self._batch_running = False
        if batch.command_id == self._list_batch:
            self._list_batch = None
            self._list_notice = self._refusals(batch.keys)
        if batch.state == "interrupted":
            remaining: str = ", ".join(
                f"E{key.number}"
                for key in batch.keys
                if key not in self._batch_results or self._batch_results[key].reason != EpisodeReason.ADMITTED
            )
            if remaining:
                self._notice = f"Nie zlecono {remaining} · zaznacz je ponownie"
                self._notice_kind = NoticeKind.WARNING

    def _episode_available(self, episode: ListedEpisode) -> bool:
        if self._listing is None or not episode.aired:
            return False
        key: EpisodeKey = EpisodeKey(self._listing.anilist_id, episode.number)
        status: EpisodeStatus | None = self._episode_states.get(key)
        return key not in self._sending and (status is None or not status.active or status.attempt)

    def _send_episodes(
        self, listing: EpisodeListing, keys: tuple[EpisodeKey, ...], command_id: str, generation: int
    ) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        batch: EpisodeBatch | None = None
        try:
            batch = resident.episode_download(keys, command_id=command_id)
            deadline: float = self._clock() + _BATCH_WAIT_S
            while batch.state == "accepted" and self._clock() < deadline:
                with self._lock:
                    self._accept_batch(batch)
                sleep(_BATCH_POLL_S)
                batch = resident.episode_download(keys, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime episode download failed", error_class=type(problem).__name__)
            with self._lock:
                notice: str = self._batch_failed(problem, keys)
                if generation == self._generation:
                    self._notice = notice
                    self._notice_kind = NoticeKind.WARNING
            self._invalidate()
            self._flush_list_notice()
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            self._accept_batch(batch)
            self._batch_running = False
            self._episode_states.update(
                {
                    key: state
                    for key, state in states.items()
                    if state.state != "not_ordered" or key not in self._batch_results
                }
            )
            if batch.state == "accepted" and generation == self._generation:
                self._notice = "Partia trwa · Enter sprawdź wynik"
        self._invalidate()
        self._flush_list_notice()

    def _start_franchise(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        if candidate.status is TitleStatus.NOT_YET_RELEASED:
            self._notice = _ANNOUNCED
            return
        if self._franchise is not None and self._franchise.selected_id == candidate.anilist_id:
            self._open_entries(self._franchise)
            return
        self._franchise = None
        self._entry = None
        self._listing = None
        self._episode_marks.clear()
        self._offer = None
        generation: int = self._start_work(_LOADING_ENTRIES, _Screen.TITLES)
        self._spawn(self._load_franchise, (candidate.anilist_id, generation, self._work_cancel))

    def _load_franchise(self, anilist_id: int, generation: int, cancel: EventCancellationToken) -> None:
        if self._acquisition is None:
            return
        try:
            franchise: Franchise = self._acquisition.franchise(anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.TITLES, "anilist")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._open_entries(franchise)
        self._invalidate()

    def _open_entries(self, franchise: Franchise) -> None:
        self._adopt_franchise(franchise)
        self._entries_skipped = len(franchise.entries) == 1 and franchise.complete
        if self._entries_skipped:
            self._start_episodes(_Screen.TITLES if self._titles_shown else _Screen.QUERY)
            return
        self._screen = _Screen.ENTRIES

    def _adopt_franchise(self, franchise: Franchise) -> None:
        franchise = replace(
            franchise,
            entries=tuple(
                sorted(franchise.entries, key=lambda entry: premiere_order(entry.year, entry.start), reverse=True)
            ),
        )
        self._franchise = franchise
        self._positions[_Screen.ENTRIES] = 0
        self._offsets[_Screen.ENTRIES] = 0
        self._follow_cursor = True

    def _start_episodes(self, back: _Screen = _Screen.ENTRIES) -> None:
        if self._franchise is None:
            return
        entry: FranchiseEntry = self._franchise.entries[self._positions.get(_Screen.ENTRIES, 0)]
        if entry.status == "NOT_YET_RELEASED":
            self._notice = _ANNOUNCED
            return
        same: bool = self._entry == entry and self._listing is not None
        self._entry = entry
        self._shown_entry = entry
        if not same:
            self._listing = None
            self._episode_marks.clear()
            self._positions[_Screen.EPISODES] = 0
            self._offsets[_Screen.EPISODES] = 0
        generation: int = self._start_work("Wczytuję odcinki…", back)
        self._spawn(self._load_episodes, (entry, generation))

    def _read_episode_states(self, listing: EpisodeListing) -> dict[EpisodeKey, EpisodeStatus]:
        numbers: list[int] = [item.number for item in listing.episodes if item.aired]
        first: object = self._subscription_details.get("first_target")
        last: object = self._subscription_details.get("last_target")
        if self._subscription is not None and isinstance(first, int) and isinstance(last, int):
            numbers = sorted({*numbers, *range(first, last + 1)})
        if self._resident is None or not numbers:
            return {}
        try:
            statuses: tuple[EpisodeStatus, ...] = tuple(
                status
                for start in range(0, len(numbers), _MAX_BATCH)
                for status in self._resident.episode_states(listing.anilist_id, numbers[start : start + _MAX_BATCH])
            )
        except (AniShiftError, OSError, TypeError) as problem:
            logger.warning("Anime episode states read failed", error_class=type(problem).__name__)
            return {}
        return {item.key: item for item in statuses}

    def _load_episodes(self, entry: FranchiseEntry, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            listing: EpisodeListing = self._acquisition.episodes(entry.anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            with self._lock:
                if generation != self._generation:
                    return
                self._entries_skipped = False
            self._catalog_failure(generation, problem, _Screen.ENTRIES, "anizip")
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            if generation != self._generation:
                return
            self._episode_states.update(states)
            if entry.format == "MOVIE":
                film: ListedEpisode = next((item for item in listing.episodes if item.number == 1), ListedEpisode(1))
                listing = replace(listing, episodes=(film,))
            self._listing = listing
            self._stale = False
            shown: tuple[ListedEpisode, ...] = self._shown_episodes()
            self._episode_marks.intersection_update(item.number for item in shown)
            self._positions[_Screen.EPISODES] = min(self._positions.get(_Screen.EPISODES, 0), max(len(shown) - 1, 0))
            self._follow_cursor = True
            self._screen = _Screen.EPISODES
            self._worker = None
        self._invalidate()

    def _start_offers(self, highlighted: ListedEpisode) -> None:
        self._files = None
        self._offer_view = None
        if self._listing is None:
            self._notice = "Brak mapowania"
            return
        if not highlighted.aired:
            self._notice = f"E{highlighted.number} jeszcze nie wyemitowano"
            return
        generation: int = self._start_work("Szukam…", _Screen.EPISODES)
        self._open_candidates()
        self._spawn(self._load_offer, (EpisodeKey(self._listing.anilist_id, highlighted.number), generation))

    def _start_owner_offer(self, episode: ListedEpisode, *, repeat: bool = False) -> None:
        if self._resident is None or self._listing is None or not episode.aired:
            return
        self._files = None
        self._offer_view = None
        self._offer_id = None
        self._offer_refreshing = False
        self._offer_refresh_pending = False
        self._choice_sending = False
        self._resident.interrupt_reads()
        generation: int = self._start_work("Szukam…", _Screen.EPISODES)
        self._open_candidates()
        self._spawn(
            partial(self._load_owner_offer, repeat=repeat),
            (EpisodeKey(self._listing.anilist_id, episode.number), generation),
        )

    def _load_owner_offer(self, key: EpisodeKey, generation: int, *, repeat: bool) -> None:
        if self._resident is None:
            return
        try:
            started: Mapping[str, object] = self._resident.episode_offer_start(
                key, repeat=repeat, command_id=uuid4().hex
            )
        except (AniShiftError, OSError) as problem:
            self._catalog_failure(generation, problem, _Screen.EPISODES, "torrentio")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._offer_id = decode_view(str, started.get("offer_id"))
            self._worker = None
            self.refresh_offer()

    def refresh_offer(self) -> None:
        """Recover the latest offer after a signal or a reconnected observation channel."""
        with self._lock:
            if self._offer_id is None:
                return
            if self._offer_refreshing:
                self._offer_refresh_pending = True
                return
            self._offer_refreshing = True
            self._spawn(self._read_owner_offer, (self._offer_id, self._generation))

    def _read_owner_offer(self, offer_id: str, generation: int) -> None:  # noqa: PLR0911
        if self._resident is None:
            return
        while True:
            try:
                result: Mapping[str, object] = self._resident.episode_offer_get(offer_id)
            except (AniShiftError, OSError) as problem:
                with self._lock:
                    if generation != self._generation or offer_id != self._offer_id:
                        return
                    self._offer_refreshing = False
                    self._worker = None
                    if self._choice_sending and isinstance(problem, ControlError) and problem.reason == "offer_expired":
                        return
                    if isinstance(problem, ControlError) and problem.reason == "response_too_large":
                        self.receive("control_problem", {})
                        self._invalidate()
                        return
                    self._offer_id = None
                    self._catalog_failure(generation, problem, _Screen.EPISODES, "")
                return
            with self._lock:
                if generation != self._generation or offer_id != self._offer_id:
                    return
                self._accept_offer_state(result, generation)
                if not self._offer_refresh_pending or self._offer_id is None:
                    self._offer_refreshing = False
                    self._worker = None
                    self._invalidate()
                    return
                self._offer_refresh_pending = False

    def _accept_offer_state(self, result: Mapping[str, object], generation: int) -> None:
        if result.get("state") == "failed":
            self._offer_id = None
            self._offer_view = None
            self._confirm_choice = None
            self._confirm_view = None
            reason: str = str(result.get("message"))
            self._catalog_failure(
                generation,
                ControlError(reason, code=ControlErrorCode.INTERNAL, reason=reason, answered=True),
                _Screen.EPISODES,
                "torrentio",
            )
            return
        if result.get("state") != "ready":
            return
        view: EpisodeOfferView = decode_view(EpisodeOfferView, result.get("view"))
        if self._offer_view is not None and view.revision <= self._offer_view.revision:
            return
        highlighted: str | None = (
            self._release_candidates[self._positions.get(_Screen.CANDIDATES, 0)].stream.info_hash
            if self._release_candidates
            and ((self._screen is _Screen.CANDIDATES and self._release_moved) or self._confirm_choice is not None)
            else None
        )
        self._offer_view = view
        self._stale = False
        self._offer = view.offer
        self._offers_running = result.get("final") is not True
        self._release_candidates = visible(view.offer.candidates, view.offer.suggestion)
        self._positions[_Screen.CANDIDATES] = next(
            (index for index, item in enumerate(self._release_candidates) if item.stream.info_hash == highlighted),
            suggested_position(self._offer, self._release_candidates),
        )
        self._view.selected.intersection_update(item.stream.info_hash for item in self._release_candidates)
        self._view.selection = None

    def _choose_release(
        self, choice: RankedCandidate, *, confirmed: bool = False, shown: EpisodeOfferView | None = None
    ) -> None:
        if self._choice_sending:
            return
        if self._pending_batch is not None:
            self._notice = "Trwa partia · po jej zakończeniu otwórz wydania ponownie"
            return
        view: EpisodeOfferView | None = shown or self._offer_view
        if self._resident is None or view is None or choice.supported is False:
            return
        if choice.identity.verdict is not IdentityVerdict.MATCH and not confirmed:
            self._confirm_choice = choice
            self._confirm_view = view
            self._problem_return = self._screen
            self._problem = "Pobrać mimo niepewnej tożsamości?"
            self._suggestion = " · ".join(
                (choice.stream.release, f"E{view.offer.key.number}", candidate_reason(choice))
            )
            self._screen = _Screen.PROBLEM
            return
        generation: int = self._generation
        self._choice_sending = True
        self._notice = _SENDING
        self._spawn(self._send_choice, (view, choice, generation, uuid4().hex))

    def _send_choice(self, view: EpisodeOfferView, choice: RankedCandidate, generation: int, command_id: str) -> None:
        if self._resident is None:
            return
        try:
            self._resident.episode_choose(
                view,
                choice.stream,
                command_id=command_id,
                deviation_confirmed=choice.identity.verdict is not IdentityVerdict.MATCH,
                conflict_confirmed=bool(view.conflict),
            )
        except (AniShiftError, OSError) as problem:
            with self._lock:
                if generation == self._generation:
                    self._choice_sending = False
                    self._offer_id = None
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        self._finish_episode_choice(generation, f"Zlecono E{view.offer.key.number}")

    def _start_files(self, admission_id: str) -> None:
        self._offer_view = None
        self._files = None
        self._offer = None
        self._positions[_Screen.FILES] = 0
        self._offsets[_Screen.FILES] = 0
        generation: int = self._start_work("Wczytuję pliki…", _Screen.EPISODES)
        self._spawn(self._load_files, (admission_id, generation))

    def _load_files(self, admission_id: str, generation: int, notice: str = "") -> None:
        if self._resident is None:
            return
        try:
            files: EpisodeFiles = self._resident.episode_files(admission_id)
        except (AniShiftError, OSError) as problem:
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._files = files
            self._notice = notice
            self._positions[_Screen.FILES] = 0
            self._screen = _Screen.FILES
            self._worker = None
        self._invalidate()

    def _choose_file(self) -> None:
        files: EpisodeFiles | None = self._files
        if files is None or not files.files:
            return
        selected: EpisodeFile = files.files[self._positions.get(_Screen.FILES, 0)]
        generation: int = self._start_work(_SENDING, _Screen.EPISODES, sending=True)
        self._spawn(self._send_file, (files, selected, generation, uuid4().hex))

    def _send_file(self, files: EpisodeFiles, selected: EpisodeFile, generation: int, command_id: str) -> None:
        if self._resident is None:
            return
        try:
            self._resident.episode_file_choose(files, selected, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            if isinstance(problem, ControlError) and problem.reason == "file_map_changed":
                self._load_files(files.admission_id, generation, "Lista plików zmieniła się · wybierz ponownie")
                return
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        self._finish_episode_choice(generation, "Wybrano plik")

    def _finish_episode_choice(self, generation: int, notice: str) -> None:
        with self._lock:
            listing: EpisodeListing | None = self._listing
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing) if listing is not None else {}
        with self._lock:
            if generation != self._generation:
                return
            self._episode_states.update(states)
            self._notice = notice
            self._notice_kind = NoticeKind.SUCCESS
            self._offer_view = None
            self._offer_id = None
            self._choice_sending = False
            self._offers_running = False
            self._files = None
            self._screen = _Screen.EPISODES
            self._worker = None
        self._invalidate()

    def polish_refused(self, notice: str) -> None:
        """Name why the owner refused to stop a Polish wait and reread the episode states that offered it."""
        with self._lock:
            self._notice = notice
        self.refresh_episode_states()

    def refresh_episode_states(self) -> None:
        """Refresh at most one owner page around the visible episode window."""
        with self._lock:
            listing: EpisodeListing | None = self._listing
            if listing is None or self._screen is not _Screen.EPISODES:
                return
            anchor: int = (
                self._positions.get(_Screen.EPISODES, 0)
                if self._follow_cursor
                else self._offsets.get(_Screen.EPISODES, 0)
            )
            start: int = max(anchor - _MAX_BATCH // 2, 0)
            visible: EpisodeListing = replace(listing, episodes=listing.episodes[start : start + _MAX_BATCH])
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(visible)
        with self._lock:
            if listing is self._listing:
                self._episode_states.update(states)
                self._episode_marks.difference_update(item.key.number for item in states.values() if item.active)

    def _load_offer(self, key: EpisodeKey, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            offer: EpisodeOffer = self._acquisition.offer(key)
        except Exception as problem:  # noqa: BLE001 - defects fail the whole offer instead of inventing a verdict
            self._catalog_failure(generation, problem, _Screen.EPISODES, "torrentio")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._offer = offer
            self._release_candidates = visible(offer.candidates, offer.suggestion)
            self._positions[_Screen.CANDIDATES] = suggested_position(offer, self._release_candidates)
            self._worker = None
            self._offers_running = False
        self._invalidate()

    def _catalog_failure(self, generation: int, problem: Exception, back: _Screen, provider: str) -> None:
        if isinstance(problem, ControlError) and problem.code is ControlErrorCode.REFUSED:
            logger.info("Anime catalogue command refused", reason=problem.reason)
        else:
            logger.warning("Anime catalogue command failed", error_class=type(problem).__name__)
        if isinstance(problem, (AniShiftError, OSError)):
            self._report(generation, problem, back, provider=provider, catalog_command=True)
            return
        self._fail(generation, COMMAND_FAILED, "", back)

    def _open_candidates(self) -> None:
        self._screen = _Screen.CANDIDATES
        self._offers_running = True
        self._offer = None
        self._release_candidates = ()
        self._positions[_Screen.CANDIDATES] = 0
        self._offsets[_Screen.CANDIDATES] = 0
        self._release_moved = False
        self._follow_cursor = True

    def _start_search(self, text: str) -> None:
        self._subscription = None
        self._candidates = ()
        self._titles_shown = False
        self._entries_skipped = False
        self._franchise = None
        self._entry = None
        self._listing = None
        self._offer = None
        self._episode_marks.clear()
        query: SearchQuery = parse_query(text)
        generation: int = self._start_work(_SEARCHING_TITLE, _Screen.QUERY)
        self._spawn(self._find_titles, (query.title, generation, self._work_cancel))

    def _start_work(self, sentence: str, back: _Screen, *, sending: bool = False) -> int:
        self._input_focused = False
        self._generation += 1
        self._problem_provider = ""
        self._offers_running = False
        self._busy_return = back
        self._screen = _Screen.BUSY
        self._busy = sentence
        self._work_sending = sending
        self._work_cancel = EventCancellationToken()
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _find_titles(self, title: str, generation: int, cancel: EventCancellationToken) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            candidates: tuple[TitleCandidate, ...] = acquisition.find_titles(title)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title lookup failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY, provider="anilist")
            return
        if not candidates:
            self._fail(generation, "Nie znaleziono tytułu", "", _Screen.QUERY)
            return
        self._open_first_title(acquisition, candidates, generation, cancel)

    def _open_first_title(
        self,
        acquisition: AcquisitionService | ResidentSession,
        candidates: tuple[TitleCandidate, ...],
        generation: int,
        cancel: EventCancellationToken,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._busy = _LOADING_ENTRIES
        self._invalidate()
        try:
            franchise: Franchise = acquisition.franchise(candidates[0].anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            with self._lock:
                if generation != self._generation:
                    return
                self._store_titles(candidates, None)
            self._catalog_failure(generation, problem, _Screen.TITLES, "anilist")
            return
        self._show_titles(generation, candidates, franchise)

    def _show_titles(self, generation: int, candidates: tuple[TitleCandidate, ...], franchise: Franchise) -> None:
        entry: FranchiseEntry | None = None
        with self._lock:
            if generation != self._generation:
                return
            self._store_titles(candidates, franchise)
            if self._titles_shown:
                self._screen = _Screen.TITLES
            else:
                self._highlighted = self._candidates.index(candidates[0])
                self._screen = _Screen.ENTRIES
            if (
                not self._titles_shown
                and len(franchise.entries) == 1
                and franchise.complete
                and franchise.entries[0].status != "NOT_YET_RELEASED"
            ):
                entry = franchise.entries[0]
            if entry is not None:
                self._entries_skipped = True
                self._entry = entry
                self._shown_entry = entry
                self._positions[_Screen.EPISODES] = 0
                self._offsets[_Screen.EPISODES] = 0
                self._screen = _Screen.BUSY
                self._busy = "Wczytuję odcinki…"
                self._busy_return = _Screen.QUERY
            else:
                self._worker = None
        self._invalidate()
        if entry is not None:
            self._load_episodes(entry, generation)

    def _store_titles(self, candidates: tuple[TitleCandidate, ...], franchise: Franchise | None) -> None:
        self._candidates = tuple(
            sorted(
                natsorted(candidates, key=lambda item: (item.english or item.romaji).casefold()),
                key=lambda item: premiere_order(item.year, item.start),
                reverse=True,
            )
        )
        self._highlighted = 0
        self._franchise = None
        if franchise is not None:
            self._adopt_franchise(franchise)
        members: set[int] = {entry.anilist_id for entry in franchise.entries} if franchise is not None else set()
        self._titles_shown = any(item.anilist_id not in members for item in candidates)

    def _report(
        self,
        generation: int,
        problem: AniShiftError | OSError | ValueError,
        back: _Screen,
        *,
        provider: str = "",
        catalog_command: bool = False,
    ) -> None:
        """State one failure of this screen in Polish and return the user to *back*."""
        sentence, hint = stated(problem)
        code: ErrorCode | None = error_code(problem)
        provider = (
            {
                ErrorCode.TITLE_CATALOG_FAILED: "anilist",
                ErrorCode.EPISODE_CATALOG_FAILED: "anizip",
            }.get(code, provider)
            if code is not None
            else provider
        )
        if (
            catalog_command
            and isinstance(problem, ControlError)
            and (problem.code is ControlErrorCode.INTERNAL and problem.reason == "command_failed")
        ):
            sentence, hint = COMMAND_FAILED, ""
        if code not in {
            ErrorCode.TITLE_CATALOG_FAILED,
            ErrorCode.EPISODE_CATALOG_FAILED,
            ErrorCode.TORRENT_SOURCE_FAILED,
        }:
            provider = ""
        deadline: float = 0.0
        if provider and isinstance(self._acquisition, AcquisitionService):
            deadline = self._acquisition.blocked_until((provider,))
        self._fail(generation, sentence, hint, back, provider=provider, deadline=deadline)

    def _fail(  # noqa: PLR0913
        self,
        generation: int,
        sentence: str,
        suggestion: str,
        back: _Screen,
        *,
        provider: str = "",
        deadline: float = 0.0,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._offers_running = False
            if back is _Screen.EPISODES:
                self._offer = None
                self._release_candidates = ()
            self._problem_provider = provider
            if deadline:
                self._provider_locks[provider] = deadline
            self._problem = sentence
            self._suggestion = suggestion
            self._problem_return = back
            self._screen = _Screen.PROBLEM
        self._invalidate()

    def _retry_hint(self, provider: str) -> str:
        deadline: float = self._provider_locks.get(provider, 0.0)
        if not deadline:
            return ""
        remaining: int = max(ceil(deadline - self._clock()), 0)
        return f"spróbuj za {remaining} s" if remaining else "Możesz spróbować ponownie"

    def _entry_heading(self) -> tuple[str, ...]:
        entry: FranchiseEntry | None = self._shown_entry
        if entry is None:
            return ()
        return ("Anime", f"{safe(entry.english or entry.romaji)} ({entry.year or '—'})")


def _deadline(value: str) -> float | None:
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None
