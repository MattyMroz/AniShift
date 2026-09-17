"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    CatalogOrder,
    DownloadReceipt,
    EpisodeRange,
    RefusalReason,
    ReleaseCatalog,
    ReleaseChoice,
    SearchQuery,
    SeasonContext,
    SeriesGroup,
    SubscriptionOrder,
    TitleCandidate,
    TitleStatus,
    order_groups,
    parse_query,
)
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.menu import with_footer
from anishift.cli.interactive.subscriptions import SubscriptionDraft
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError
from anishift.utils.logger import get_logger

__all__ = ["AnimeController", "AnimeResult"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TITLE: Final[str] = "ANIME"
"""Heading shown above every screen of this controller."""

_POINTER: Final[str] = "\u276f"
"""Marker placed before the highlighted release row."""

_BULLET: Final[str] = "▸"
"""Glyph opening one release row under its group header."""

_WORKER_NAME: Final[str] = "anishift-anime"
"""Name of the thread carrying every search and download of this screen."""

_MIN_RESOLUTION_LABEL: Final[str] = "1080p"
"""Lowest release quality the catalog lists, named for the user."""

_QUERY_HINT: Final[str] = "Enter edytuj · ←→ widok · Esc wróć"
"""Keyboard hint of the title input."""

_TITLES_HINT: Final[str] = "Enter wybierz · Esc wróć"
"""Keyboard hint of the title candidate list."""

_BUSY_HINT: Final[str] = "Esc anuluj"
"""Keyboard hint shown while the network thread works."""

_DONE_HINT: Final[str] = "dowolny klawisz: powrót"
"""Keyboard hint of the screen confirming the hand-off."""

_PROBLEM_HINT: Final[str] = "Enter wróć · Esc menu"
"""Keyboard hint of the screen reporting a failure."""

_RESUME_HINT: Final[str] = "Enter Wznów AniShift · Esc menu"
"""Explicit recovery action offered after a paused download refusal."""

_RESUMING: Final[str] = "Wznawiam AniShift…"
"""Sentence shown while the owner processes an explicit resume command."""

_SEARCHING_TITLE: Final[str] = "Szukam tytułu…"
"""Sentence shown while the anime catalog names the title behind the typed phrase."""

_SEARCHING_RELEASES: Final[str] = "Szukam wydań…"
"""Sentence shown while the release index answers for the chosen title."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
"""Sentence shown when the session was built without an acquisition boundary."""

_EPISODE_ONLY: Final[str] = "Subskrybuj działa tylko na numerowanym odcinku"
"""Notice shown when the highlighted release carries no episode number to watch from."""

_OTHER_SEASON: Final[str] = "To wydanie wygląda na inny sezon"
"""Notice shown when the highlighted release belongs to a season other than the chosen one."""

_CATALOG_DOWN: Final[str] = "AniList nie odpowiada, wyniki dla hasła"
"""Footer note shown when the title catalog failed and the raw phrase was searched instead."""

_NO_TITLE: Final[str] = "Brak tytułu w AniList, wyniki dla hasła"
"""Footer note shown when the title catalog knows no title and the raw phrase was searched instead."""

_RANGE_PROMPT: Final[str] = "zakres (np. 4-10)"
"""Question opening the footer prompt that marks a span of episodes."""

_RANGE_INVALID: Final[str] = "zakres: podaj np. 4-10"
"""Notice shown when the typed span cannot be read."""

_EMPTY_CATALOG: Final[str] = f"Brak wydań w {_MIN_RESOLUTION_LABEL}+ dla tego tytułu"
"""Sentence shown when the query matched nothing of the required quality."""

_EMPTY_FILTERED: Final[str] = "Brak odc. {episodes} w " + _MIN_RESOLUTION_LABEL + "+ dla tego tytułu"
"""Sentence shown when only the episode filter left the listing empty."""

_NO_SEASON_NUMBERING: Final[str] = "numeracja sezonu niedostępna"
"""Footer note shown when the season chain failed and episodes are numbered as named."""

_PROBLEM_TEXTS: Final[dict[ErrorCode, tuple[str, str]]] = {
    ErrorCode.TORRENT_SOURCE_FAILED: ("Nyaa nie odpowiada", "Sprawdź połączenie i spróbuj ponownie"),
    ErrorCode.TORRENT_CLIENT_UNAVAILABLE: ("qBittorrent nie odpowiada", "Uruchom qBittorrenta z włączonym Web UI"),
    ErrorCode.TORRENT_CLIENT_UNAUTHORIZED: (
        "qBittorrent odrzucił logowanie",
        "Sprawdź login i hasło Web UI w pliku .env",
    ),
    ErrorCode.TORRENT_CLIENT_REFUSED: ("qBittorrent odrzucił żądanie", "Sprawdź ustawienia Web UI i spróbuj ponownie"),
    ErrorCode.TITLE_CATALOG_FAILED: ("AniList nie odpowiada", "Spróbuj ponownie za chwilę"),
}
"""Polish sentence and hint of every failure this screen can meet."""

_CHOICE_SEPARATOR: Final[str] = "  "
"""Separation between the facts of one release row."""

_HINT_SEPARATOR: Final[str] = " · "
"""Separation between the keyboard hints of one footer."""

_HEADER_ROWS: Final[int] = 7
"""Rows the heading, hint and footer take away from a list without its own measurement."""

_FULL_PICKER_ROWS: Final[int] = 11
"""Minimum height retaining the heading, releases, pinned actions and help."""

_STATUS_LABELS: Final[dict[TitleStatus, str]] = {
    TitleStatus.FINISHED: "zakończone",
    TitleStatus.RELEASING: "w emisji",
    TitleStatus.NOT_YET_RELEASED: "zapowiedź",
    TitleStatus.CANCELLED: "przerwane",
    TitleStatus.HIATUS: "przerwane",
}
"""Polish name of every airing state worth showing; an unknown one is left out of the row."""

_RANGE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?P<first>\d{1,4})(?P<dash>-)?(?P<last>\d{1,4})?|-(?P<upto>\d{1,4}))$"
)
"""Span typed in the footer: one episode, a closed span, an open end, or an upper bound."""


class AnimeResult(StrEnum):
    """Signal whether the anime controller stays open or returns Home."""

    CONTINUE = "continue"
    HOME = "home"
    SUBSCRIBE = "subscribe"


class _Screen(StrEnum):
    QUERY = "query"
    TITLES = "titles"
    BUSY = "busy"
    RESULTS = "results"
    DONE = "done"
    PROBLEM = "problem"


class _Action(StrEnum):
    SELECT_ALL = "select_all"
    DOWNLOAD = "download"
    BACK = "back"


@dataclass(frozen=True, slots=True)
class _Listing:
    """How one catalog was asked for, carried from the worker thread into the screen state."""

    order: CatalogOrder
    episodes: EpisodeRange | None = None
    context: SeasonContext | None = None
    fallback: str = ""


@dataclass(frozen=True, slots=True)
class _Row:
    """One selectable group, release or explicit action."""

    label: str
    choice: ReleaseChoice | None = None
    group: int = 0
    detail: str = ""
    action: _Action | None = None


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
        self._lock: threading.Lock = threading.Lock()
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._screen: _Screen = _Screen.QUERY
        self._query_input: TextInput = TextInput()
        self._input_focused: bool = False
        self._searched: str = ""
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._highlighted: int = 0
        self._candidate: TitleCandidate | None = None
        self._context: SeasonContext | None = None
        self._episodes: EpisodeRange | None = None
        self._order: CatalogOrder = CatalogOrder.NEWEST
        self._groups: tuple[SeriesGroup, ...] = ()
        self._opened_group: int | None = None
        self._rows: tuple[_Row, ...] = ()
        self._choices: tuple[int, ...] = ()
        self._marked: set[int] = set()
        self._recorded: dict[str, str] = {}
        self._downloaded: str | None = None
        self._selected: int = 0
        self._hidden: int = 0
        self._excluded: int = 0
        self._filtered: int = 0
        self._range_input: TextInput | None = None
        self._group_input: TextInput | None = None
        self._fallback: str = ""
        self._busy: str = _SEARCHING_TITLE
        self._done: str = ""
        self._notice: str = ""
        self._problem: str = ""
        self._suggestion: str = ""
        self._problem_return: _Screen = _Screen.QUERY
        self._resume_available: bool = False
        self._draft: SubscriptionDraft | None = None
        if self._acquisition is None:
            self._screen = _Screen.PROBLEM
            self._problem = _UNAVAILABLE

    def handle_key(self, key: str) -> AnimeResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            if key in {"escape", "interrupt"}:
                self._downloaded = None
            if self._handle_input(key):
                return AnimeResult.CONTINUE
            if self._screen is _Screen.QUERY:
                result: AnimeResult = self._handle_query(key)
            elif self._screen is _Screen.TITLES:
                result = self._handle_titles(key)
            elif self._screen is _Screen.BUSY:
                result = self._handle_busy(key)
            elif self._screen is _Screen.RESULTS:
                result = self._handle_results(key)
            elif self._screen is _Screen.DONE:
                self._screen = _Screen.RESULTS
                result = AnimeResult.CONTINUE
            else:
                result = self._handle_problem(key)
            if self._draft is not None:
                return AnimeResult.SUBSCRIBE
        return result

    def take_draft(self) -> SubscriptionDraft | None:
        """Consume a prepared subscription without storing or checking it."""
        with self._lock:
            draft: SubscriptionDraft | None = self._draft
            self._draft = None
            return draft

    def refresh_acquisitions(self, acquisitions: Sequence[Mapping[str, object]]) -> None:
        """Apply recorded owner facts without creating a local admission history."""
        with self._lock:
            self._recorded = {
                str(item["info_hash"]).casefold(): str(item.get("state", ""))
                for item in acquisitions
                if item.get("info_hash")
            }
            self._marked = {index for index in self._marked if not self._recorded_label(self._rows[index].choice)}

    def take_downloaded(self) -> str | None:
        """Consume completion only while its initiating generation remains current."""
        with self._lock:
            notice: str | None = self._downloaded
            self._downloaded = None
            return notice

    def render(self, columns: int, rows: int) -> Text:
        """Render the cached state of the current screen for one terminal geometry."""
        with self._lock:
            renderer: Callable[[int, int], Text] = {
                _Screen.QUERY: self._render_query,
                _Screen.TITLES: self._render_titles,
                _Screen.BUSY: self._render_busy,
                _Screen.RESULTS: self._render_results,
                _Screen.DONE: self._render_done,
                _Screen.PROBLEM: self._render_problem,
            }[self._screen]
            rendered: Text = renderer(columns, rows)
        return rendered

    def cancel(self) -> None:
        """Blur retained inputs and discard the result of network work still in flight."""
        with self._lock:
            self._input_focused = False
            self._generation += 1
            self._downloaded = None
            self._draft = None
            if self._screen is _Screen.DONE:
                self._screen = _Screen.RESULTS
            if self._screen is _Screen.BUSY:
                self._screen = self._work_return()
                self._worker = None

    @property
    def input_focused(self) -> bool:
        """Whether Anime currently owns cursor and selection navigation."""
        with self._lock:
            return self._input_focused

    def _handle_input(self, key: str) -> bool:
        editor: TextInput | None = None
        if self._screen is _Screen.QUERY:
            editor = self._query_input
        elif self._screen is _Screen.RESULTS:
            editor = self._group_input or self._range_input
        if editor is None:
            return False
        if self._input_focused and key == "interrupt" and editor.handle(key):
            return True
        if key in {"escape", "interrupt"} and self._input_focused:
            self._input_focused = False
            return True
        if not self._input_focused:
            if key == "enter":
                self._input_focused = True
            return key not in {"escape", "interrupt"}
        return editor.handle(key)

    def _handle_query(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return AnimeResult.HOME
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

    def _handle_titles(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"} or not self._candidates:
            self._screen = _Screen.QUERY
        elif key in {"up", "down"}:
            delta: int = -1 if key == "up" else 1
            self._highlighted = (self._highlighted + delta) % len(self._candidates)
        elif key == "enter":
            self._start_title_search()
        return AnimeResult.CONTINUE

    def _handle_busy(self, key: str) -> AnimeResult:
        if key not in {"escape", "interrupt"}:
            return AnimeResult.CONTINUE
        self._generation += 1
        self._worker = None
        self._screen = self._work_return()
        return AnimeResult.CONTINUE

    def _work_return(self) -> _Screen:
        return _Screen.RESULTS if self._busy in {_SENDING, _RESUMING} else _Screen.QUERY

    def _handle_results(self, key: str) -> AnimeResult:
        if self._group_input is not None:
            self._handle_group_input(key)
            return AnimeResult.CONTINUE
        if self._range is not None:
            return self._handle_range(key)
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._leave_results()
            return AnimeResult.CONTINUE
        if not self._choices:
            return self._handle_empty(key)
        self._apply_results_key(key)
        return AnimeResult.CONTINUE

    def _handle_empty(self, key: str) -> AnimeResult:
        if key.casefold() == "text:o" and self._candidate is not None:
            self._group_input = TextInput()
            self._input_focused = True
        elif key in {"text:f", "text:F"} and self._episodes is not None:
            self._start_unfiltered_search()
        elif key == "enter":
            self._leave_results()
        return AnimeResult.CONTINUE

    def _handle_group_input(self, key: str) -> None:
        editor: TextInput | None = self._group_input
        if editor is None:
            return
        if key in {"escape", "interrupt"}:
            self._group_input = None
            self._input_focused = False
            return
        if key != "enter" or not editor.text.strip() or self._candidate is None:
            return
        group: str = editor.text.strip()
        order: SubscriptionOrder = SubscriptionOrder(
            self._candidate.romaji,
            group,
            f"{self._candidate.romaji} {group}",
            Decimal(1),
            context=self._context,
            anilist_id=self._candidate.anilist_id,
        )
        self._draft = SubscriptionDraft.from_order(order, ())
        self._group_input = None
        self._input_focused = False

    def _leave_results(self) -> None:
        if self._opened_group is not None:
            group: int = self._opened_group
            self._opened_group = None
            self._choices = tuple(
                index for index, row in enumerate(self._rows) if row.choice is None and row.action is None
            )
            self._selected = next(index for index in self._choices if self._rows[index].group == group)
            return
        self._screen = _Screen.TITLES if self._candidates else _Screen.QUERY

    def _apply_results_key(self, key: str) -> None:
        if key in {"up", "down"}:
            self._move(-1 if key == "up" else 1)
        elif key in {"home", "end"}:
            self._selected = self._choices[0 if key == "home" else -1]
        elif key == "space":
            self._toggle()
        elif key == "enter":
            self._activate_row()
        elif key in {"text:d", "text:D"} and self._opened_group is not None:
            self._start_download()
        elif key in {"text:o", "text:O"}:
            self._start_subscription()
        elif key in {"text:a", "text:A"} and self._opened_group is not None:
            self._mark_group()
        elif key in {"text:z", "text:Z"} and self._opened_group is not None:
            self._range = ""
        elif key in {"text:s", "text:S"}:
            self._reorder()
        elif key in {"text:f", "text:F"} and self._episodes is not None:
            self._start_unfiltered_search()

    def _activate_row(self) -> None:
        row: _Row = self._rows[self._selected]
        if self._opened_group is None:
            self._opened_group = row.group
            self._choices = tuple(
                index
                for index, item in enumerate(self._rows)
                if item.group == row.group and (item.choice is not None or item.action is not None)
            )
            self._selected = self._choices[0]
        elif row.action is _Action.SELECT_ALL:
            self._mark_group()
        elif row.action is _Action.DOWNLOAD:
            self._start_download()
        elif row.action is _Action.BACK:
            self._leave_results()
        else:
            self._toggle()

    def _handle_range(self, key: str) -> AnimeResult:
        typed: str = self._range or ""
        if key in {"escape", "interrupt"}:
            self._range = None
        elif key == "enter":
            self._range = None
            self._apply_range(typed)
        return AnimeResult.CONTINUE

    def _handle_problem(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return AnimeResult.HOME
        if key != "enter":
            return AnimeResult.CONTINUE
        if self._resume_available:
            generation: int = self._start_work(_RESUMING)
            self._spawn(self._resume, (generation,))
            return AnimeResult.CONTINUE
        self._screen = self._problem_return
        self._problem = ""
        self._suggestion = ""
        return AnimeResult.CONTINUE

    def _move(self, delta: int) -> None:
        position: int = self._choices.index(self._selected) if self._selected in self._choices else 0
        self._selected = self._choices[(position + delta) % len(self._choices)]

    def _toggle(self) -> None:
        row: _Row = self._rows[self._selected]
        choice: ReleaseChoice | None = row.choice
        if choice is None:
            return
        recorded: str = self._recorded_label(choice)
        if recorded:
            self._notice = f"{recorded} · ponowienie przez Historię"
            return
        if self._selected in self._marked:
            self._marked.discard(self._selected)
            return
        alternatives: set[int] = {
            index
            for index in self._marked
            if _is_markable(choice, None)
            and self._rows[index].group == row.group
            and (other := self._rows[index].choice) is not None
            and _is_markable(other, None)
            and other.episode == choice.episode
        }
        self._marked.difference_update(alternatives)
        if alternatives:
            self._notice = "Zmieniono wersję odcinka"
        self._marked.add(self._selected)

    def _recorded_label(self, choice: ReleaseChoice | None) -> str:
        if choice is None:
            return ""
        state: str | None = self._recorded.get(choice.release.info_hash.casefold())
        if state is None:
            return ""
        return "Pobrano" if state == "complete" else ("Zamówiono" if state == "accepted" else "Sprawdź historię")

    def _apply_range(self, typed: str) -> None:
        episodes: EpisodeRange | None = _parse_range(typed)
        if episodes is None:
            self._notice = _RANGE_INVALID
            return
        self._mark_group(episodes)

    def _mark_group(self, episodes: EpisodeRange | None = None) -> None:
        group: int = self._rows[self._selected].group
        candidates: tuple[int, ...] = tuple(
            index
            for index in self._choices
            if self._rows[index].group == group
            and _is_markable(self._rows[index].choice, episodes)
            and not self._recorded_label(self._rows[index].choice)
        )
        selected: dict[Decimal, int] = {
            choice.episode: index
            for index in candidates
            if index in self._marked and (choice := self._rows[index].choice) is not None and choice.episode is not None
        }
        for index in candidates:
            choice = self._rows[index].choice
            if choice is not None and choice.episode is not None:
                selected.setdefault(choice.episode, index)
        marked: tuple[int, ...] = tuple(selected.values())
        self._marked.update(marked)
        wanted: int | None = None if episodes is None else _range_size(episodes)
        self._notice = f"zaznaczono {len(marked)}"
        if wanted is not None and len(marked) < wanted:
            self._notice += f" z {wanted}"
        if len(candidates) > len(marked):
            self._notice += f" · pominięto alternatywy: {len(candidates) - len(marked)}"

    def _reorder(self) -> None:
        marked: frozenset[str] = frozenset(
            choice.release.info_hash for index in self._marked if (choice := self._rows[index].choice) is not None
        )
        highlighted: _Row = self._rows[self._selected]
        group: SeriesGroup = self._groups[highlighted.group]
        self._order = CatalogOrder.SEEDERS if self._order is CatalogOrder.NEWEST else CatalogOrder.NEWEST
        ranked: bool = any(group.matches_title for group in self._groups)
        self._groups = order_groups(self._groups, self._order, ranked=ranked)
        self._rows, self._choices = _catalog_rows(self._groups)
        self._marked = {index for index, row in enumerate(self._rows) if _has_hash(row.choice, marked)}
        self._selected = next(index for index in self._choices if self._groups[self._rows[index].group] is group)
        if self._opened_group is not None:
            self._opened_group = None
            self._activate_row()
            self._selected = next(
                (
                    index
                    for index in self._choices
                    if self._rows[index].action == highlighted.action and self._rows[index].choice == highlighted.choice
                ),
                self._selected,
            )

    def _start_search(self, text: str) -> None:
        self._searched = text
        self._candidates = ()
        self._candidate = None
        self._groups = ()
        self._rows = ()
        self._choices = ()
        self._marked.clear()
        self._opened_group = None
        self._context = None
        query: SearchQuery = parse_query(text)
        self._episodes = query.episodes
        generation: int = self._start_work(_SEARCHING_TITLE)
        self._spawn(self._find_titles, (query.title, text, generation))

    def _start_title_search(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        if candidate == self._candidate and self._rows:
            self._screen = _Screen.RESULTS
            return
        self._candidate = candidate
        self._groups = ()
        self._rows = ()
        self._choices = ()
        self._marked.clear()
        self._opened_group = None
        generation: int = self._start_work(_SEARCHING_RELEASES)
        self._spawn(self._search_title, (candidate, self._episodes, self._order, generation))

    def _start_unfiltered_search(self) -> None:
        candidate: TitleCandidate | None = self._candidate
        if candidate is None:
            return
        generation: int = self._start_work(_SEARCHING_RELEASES)
        listing: _Listing = _Listing(self._order, context=self._context, fallback=self._fallback)
        self._spawn(self._search_releases, (candidate, listing, generation))

    def _start_download(self) -> None:
        chosen: tuple[ReleaseChoice, ...] = tuple(
            choice
            for index in self._choices
            if index in self._marked
            and (choice := self._rows[index].choice) is not None
            and not self._recorded_label(choice)
        )
        if not chosen:
            self._notice = "Zaznacz co najmniej jedno wydanie"
            return
        generation: int = self._start_work(_SENDING)
        self._spawn(self._download, (chosen, generation))

    def _start_subscription(self) -> None:
        row: _Row = self._rows[self._selected]
        group: SeriesGroup = self._groups[row.group]
        choice: ReleaseChoice | None = row.choice
        if self._opened_group is None:
            choice = max(
                (item for item in group.choices if _is_markable(item, None)),
                key=lambda item: item.episode if item.episode is not None else Decimal(0),
                default=group.choices[0],
            )
        if choice is None:
            return
        if choice.name.is_pack or choice.episode is None:
            self._notice = _EPISODE_ONLY
            return
        if choice.other_season:
            self._notice = _OTHER_SEASON
            return
        order: SubscriptionOrder = SubscriptionOrder(
            group.series,
            group.group,
            self._subscription_query(),
            choice.episode,
            context=self._context,
            anilist_id=self._candidate.anilist_id if self._candidate is not None else None,
        )
        numbers: tuple[Decimal, ...] = tuple(
            item.episode for item in group.choices if item.episode is not None and _is_markable(item, None)
        )
        self._draft = SubscriptionDraft.from_order(order, numbers)

    def _subscription_query(self) -> str:
        if self._candidate is None:
            return self._searched
        group: SeriesGroup = self._groups[self._rows[self._selected].group]
        return f"{group.series} {group.group}"

    def _start_work(self, sentence: str) -> int:
        self._input_focused = False
        self._generation += 1
        self._downloaded = None
        self._resume_available = False
        self._screen = _Screen.BUSY
        self._busy = sentence
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _find_titles(self, title: str, text: str, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            candidates: tuple[TitleCandidate, ...] = acquisition.find_titles(title)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title lookup failed", error_class=type(problem).__name__)
            if _code(problem) is not ErrorCode.TITLE_CATALOG_FAILED:
                self._report(generation, problem, _Screen.QUERY)
                return
            self._search(text, _CATALOG_DOWN, generation)
            return
        if not candidates:
            self._search(text, _NO_TITLE, generation)
            return
        self._show_titles(generation, candidates)

    def _search(self, query: str, fallback: str, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search(query)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime search failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY)
            return
        self._show_results(generation, catalog, _Listing(CatalogOrder.SEEDERS, fallback=fallback))

    def _search_title(
        self,
        candidate: TitleCandidate,
        episodes: EpisodeRange | None,
        order: CatalogOrder,
        generation: int,
    ) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        note: str = ""
        try:
            context: SeasonContext | None = acquisition.season_context(candidate)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime season lookup failed", error_class=type(problem).__name__)
            context = None
            note = _NO_SEASON_NUMBERING
        self._search_releases(candidate, _Listing(order, episodes, context, note), generation)

    def _search_releases(self, candidate: TitleCandidate, listing: _Listing, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search_title(
                candidate, episodes=listing.episodes, order=listing.order, context=listing.context
            )
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title search failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY)
            return
        self._show_results(generation, catalog, listing)

    def _download(self, choices: Sequence[ReleaseChoice], generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.RESULTS)
            return
        try:
            receipt: DownloadReceipt = acquisition.download(choices)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime download failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.RESULTS)
            return
        sentence: str = f"Wysłano {receipt.count} do qBittorrenta → {_safe(receipt.directory.name)}"
        if isinstance(acquisition, ResidentSession):
            sentence = (
                f"Przyjęto {receipt.count} zamówień · pobieranie w prywatnym kliencie AniShift"
                if receipt.count > 0
                else "Zamówienia już zapisane · sprawdź prywatny klient AniShift"
            )
            if receipt.count < len(choices):
                sentence += f" · już zapisane: {len(choices) - receipt.count}"
        self._show_done(generation, sentence, choices)

    def _resume(self, generation: int) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        try:
            if resident.command("set_auto", {"enabled": True}).get("auto_enabled") is not True:
                self._fail(generation, "Brak potwierdzenia wznowienia AniShift", "", _Screen.RESULTS, resume=True)
                return
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Anime resume failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.RESULTS, resume=True)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._screen = _Screen.RESULTS
            self._problem = ""
            self._suggestion = ""
        self._invalidate()

    def _show_titles(self, generation: int, candidates: tuple[TitleCandidate, ...]) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._candidates = candidates
            self._highlighted = 0
            self._screen = _Screen.TITLES
        self._invalidate()

    def _show_results(self, generation: int, catalog: ReleaseCatalog, listing: _Listing) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._order = listing.order
            self._episodes = listing.episodes
            self._context = listing.context
            self._fallback = listing.fallback
            self._groups = catalog.groups
            self._opened_group = None
            self._rows, self._choices = _catalog_rows(catalog.groups)
            self._hidden = catalog.hidden
            self._excluded = catalog.excluded
            self._filtered = catalog.filtered
            self._marked = set()
            self._range = None
            self._notice = ""
            self._selected = self._choices[0] if self._choices else 0
            self._screen = _Screen.RESULTS
        self._invalidate()

    def _show_done(self, generation: int, sentence: str, choices: Sequence[ReleaseChoice] = ()) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._done = sentence
            hashes: frozenset[str] = frozenset(choice.release.info_hash for choice in choices)
            self._marked = {index for index in self._marked if not _has_hash(self._rows[index].choice, hashes)}
            self._downloaded = sentence
            self._screen = _Screen.DONE
        self._invalidate()

    def _report(
        self, generation: int, problem: AniShiftError | OSError | ValueError, back: _Screen, *, resume: bool = False
    ) -> None:
        """State one failure of this screen in Polish and return the user to *back*."""
        sentence, hint = _stated(problem)
        resume = resume or (
            self._resident is not None
            and back is _Screen.RESULTS
            and isinstance(problem, ControlError)
            and problem.reason == RefusalReason.PAUSED.value
        )
        self._fail(generation, sentence, hint, back, resume=resume)

    def _fail(self, generation: int, sentence: str, suggestion: str, back: _Screen, *, resume: bool = False) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._problem = sentence
            self._suggestion = suggestion
            self._problem_return = back
            self._resume_available = resume
            self._screen = _Screen.PROBLEM
        self._invalidate()

    def _render_query(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2) if rows >= _HEADER_ROWS else Text()
        left: int = max((columns - min(max(len(self._query) + 3, 32), columns)) // 2, 0)
        width: int = max(columns - left - 3, 1)
        content.append(f"{' ' * left}> ", style="brand_accent" if self._input_focused else "gray")
        content.append_text(self._query_input.render(width, focused=self._input_focused))
        content.append("\n")
        hint: str = "Enter szukaj · Esc zakończ · Tab widok" if self._input_focused else _QUERY_HINT
        return _finish(content, hint, columns, rows)

    def _render_titles(self, columns: int, rows: int) -> Text:
        labels: tuple[str, ...] = tuple(
            _truncate_right(_candidate_label(candidate), max(columns - 4, 1)) for candidate in self._candidates
        )
        left: int = max((columns - min(max((len(label) for label in labels), default=1) + 4, columns)) // 2, 0)
        start, end = _visible_window(len(labels), self._highlighted, rows)
        content: Text = _header(_TITLE, columns, rows, end - start)
        for index in range(start, end):
            style: str = "brand_accent" if index == self._highlighted else "white_bold"
            content.append(" " * left)
            content.append(f"{_POINTER} " if index == self._highlighted else "  ", style=style)
            content.append(f"{labels[index]}\n", style=style)
        return _finish(content, _TITLES_HINT, columns, rows)

    def _render_busy(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._busy)) // 2, 0)
        content.append(f"{' ' * left}{self._busy}\n", style="brand_accent")
        hint: str = "Esc wróć · polecenie pozostaje w toku" if self._busy == _RESUMING else _BUSY_HINT
        return _finish(content, hint, columns, rows)

    def _render_results(self, columns: int, rows: int) -> Text:
        subtitle: str = (
            _group_label(self._groups[self._opened_group]) if self._opened_group is not None else self._title_header()
        )
        if not self._choices:
            return self._render_empty(columns, rows, subtitle)
        if rows < _FULL_PICKER_ROWS:
            return self._render_compact_results(columns, rows)
        labels: tuple[str, ...] = tuple(self._result_label(row, max(columns - 8, 1)) for row in self._rows)
        left: int = max((columns - min(max((len(label) for label in labels), default=1) + 8, columns)) // 2, 0)
        heading: int = 2 + int(bool(subtitle))
        lines: tuple[str | Text, ...] = (
            self._range_footer(columns)
            if self._range_input is not None
            else _wrapped_hint(self._footer(), max(columns - 2, 1))[: max(rows - heading - 2, 1)]
        )
        actions: tuple[int, ...] = tuple(index for index in self._choices if self._rows[index].action is not None)
        entries: tuple[int, ...] = tuple(index for index in self._choices if self._rows[index].action is None)
        position: int = entries.index(self._selected) if self._selected in entries else len(entries) - 1
        start, end = _visible_window(len(entries), position, max(rows - 1, 1), heading + len(lines) + len(actions))
        content: Text = _header(
            _TITLE, columns, rows, end - start + len(actions) + len(lines) - 1 + int(bool(subtitle)), subtitle
        )
        for index in (*entries[start:end], *actions):
            self._append_row(content, left, labels[index], index)
        return with_footer(content, lines, columns, rows)

    def _range_footer(self, columns: int) -> tuple[str | Text, ...]:
        prompt: Text = Text(f"{_RANGE_PROMPT}: ", style="gray")
        if self._range_input is not None:
            prompt.append_text(
                self._range_input.render(max(columns - 2 - prompt.cell_len, 1), focused=self._input_focused)
            )
        hint: str = "Enter zatwierdź · Esc zakończ" if self._input_focused else "Enter edytuj · Esc anuluj"
        return prompt, hint

    def _result_label(self, row: _Row, width: int) -> str:
        if row.action is _Action.DOWNLOAD:
            count: int = len(self._marked.intersection(self._choices))
            return f"Pobierz ({count})"
        recorded: str = self._recorded_label(row.choice)
        if recorded:
            return _truncate_right(f"{recorded} · {row.label}", width)
        return _row_label(row, width)

    def _render_compact_results(self, columns: int, rows: int) -> Text:
        position: int = self._choices.index(self._selected)
        footer: tuple[str | Text, ...] = (
            self._range_footer(columns) if self._range_input is not None else ("Enter wybierz · Esc wróć",)
        )
        start, end = _visible_window(len(self._choices), position, rows, 1 + len(footer))
        content: Text = Text()
        for index in self._choices[start:end]:
            self._append_row(content, 0, self._result_label(self._rows[index], max(columns - 8, 1)), index)
        return with_footer(content, footer, columns, rows)

    def _render_empty(self, columns: int, rows: int, subtitle: str) -> Text:
        if self._group_input is not None:
            content: Text = _header(_TITLE, columns, rows, 2, subtitle)
            content.append("Grupa wydająca: ", style="brand_accent" if self._input_focused else "gray")
            content.append_text(self._group_input.render(max(columns - 17, 1), focused=self._input_focused))
            hint: str = "Enter wybierz zakres · Esc zakończ" if self._input_focused else "Enter edytuj · Esc anuluj"
            return _finish(content, hint, columns, rows)
        sentence: str = self._empty_sentence()
        content = _header(_TITLE, columns, rows, 2, subtitle)
        left: int = max((columns - len(sentence)) // 2, 0)
        content.append(f"{' ' * left}{sentence}\n", style="warning")
        return _finish(content, _HINT_SEPARATOR.join(self._empty_hints()), columns, rows)

    def _empty_sentence(self) -> str:
        if self._filtered and self._episodes is not None:
            return _EMPTY_FILTERED.format(episodes=self._episodes.text)
        return _EMPTY_CATALOG

    def _empty_hints(self) -> tuple[str, ...]:
        hints: list[str] = [self._fallback] if self._fallback else []
        if self._candidate is not None:
            hints.append("O subskrybuj")
        if self._filtered and self._episodes is not None:
            hints.extend((f"poza filtrem: {self._filtered}", "F pokaż wszystkie", "Esc wróć"))
            return tuple(hints)
        hints.extend(self._counters())
        hints.append("Enter wróć")
        return tuple(hints)

    def _append_row(self, content: Text, left: int, label: str, index: int) -> None:
        style: str = "brand_accent" if index == self._selected else "white_bold"
        marker: str = ""
        if self._rows[index].choice is not None:
            marker = f"{'[x]' if index in self._marked else '[ ]'} {_BULLET} "
        content.append(" " * left)
        content.append(f"{_POINTER} " if index == self._selected else "  ", style=style)
        content.append(f"{marker}{label}\n", style=style)

    def _render_done(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._done)) // 2, 0)
        content.append(f"{' ' * left}{self._done}\n", style="brand_accent")
        return _finish(content, _DONE_HINT, columns, rows)

    def _render_problem(self, columns: int, rows: int) -> Text:
        lines: tuple[str, ...] = tuple(
            _truncate_right(line, max(columns - 4, 1)) for line in (self._problem, self._suggestion) if line
        )
        content: Text = _header(_TITLE, columns, rows, len(lines))
        left: int = max((columns - min(max((len(line) for line in lines), default=1), columns)) // 2, 0)
        for index, line in enumerate(lines):
            content.append(f"{' ' * left}{line}\n", style="error" if index == 0 else "gray")
        return _finish(content, _RESUME_HINT if self._resume_available else _PROBLEM_HINT, columns, rows)

    def _title_header(self) -> str:
        candidate: TitleCandidate | None = self._candidate
        if candidate is None:
            return ""
        parts: tuple[str, ...] = (
            _safe(candidate.romaji),
            _english_title(candidate),
            _status_label(candidate.status),
            f"{candidate.episodes} odc." if candidate.episodes else "",
        )
        return _HINT_SEPARATOR.join(part for part in parts if part)

    def _footer(self) -> str:
        if not self._notice and self._choices and self._opened_group is not None:
            choice: ReleaseChoice | None = self._rows[self._selected].choice
            if (
                choice is not None
                and sum(
                    _choice_label(other) == _choice_label(choice) for other in self._groups[self._opened_group].choices
                )
                > 1
            ):
                return f"{_safe(choice.release.title)} · Enter zaznacz · D pobierz · Esc wróć"
        return self._notice or self._results_hint()

    def _results_hint(self) -> str:
        hints: list[str] = [self._fallback] if self._fallback else []
        if self._opened_group is not None:
            hints.append(f"zaznaczone: {len(self._marked.intersection(self._choices))}")
        if self._episodes is not None:
            hints.append(f"filtr: odc. {self._episodes.text}")
        hints.extend(self._counters())
        if self._filtered:
            hints.append(f"poza filtrem: {self._filtered}")
        if self._opened_group is not None:
            hints.extend(("Space/Enter zaznacz", "A wszystkie", "Z zakres", "D pobierz"))
        else:
            hints.append("Enter otwórz grupę")
        hints.extend(("O subskrybuj", self._order_hint()))
        if self._episodes is not None:
            hints.append("F pokaż wszystkie")
        hints.append("Esc wróć")
        return _HINT_SEPARATOR.join(hints)

    def _order_hint(self) -> str:
        return "S najnowsze" if self._order is CatalogOrder.SEEDERS else "S seedy"

    def _counters(self) -> tuple[str, ...]:
        counters: list[str] = [f"ukryte poniżej {_MIN_RESOLUTION_LABEL}: {self._hidden}"]
        if self._excluded:
            counters.append(f"bez napisów/dubbing: {self._excluded}")
        return tuple(counters)


def _catalog_rows(groups: Sequence[SeriesGroup]) -> tuple[tuple[_Row, ...], tuple[int, ...]]:
    """Build catalog rows and the indexes of the initial group page."""
    rows: list[_Row] = []
    choices: list[int] = []
    for index, group in enumerate(groups):
        if not group.choices:
            continue
        choices.append(len(rows))
        rows.append(_Row(_group_label(group), None, index, _newest_detail(group)))
        labels: tuple[str, ...] = tuple(_choice_label(choice) for choice in group.choices)
        for choice, label in zip(group.choices, labels, strict=True):
            identified: str = label
            if labels.count(label) > 1:
                date: str = choice.release.published.strftime("%d.%m.%Y %H:%M") if choice.release.published else ""
                identified = f"{label} · {date} {_safe(choice.release.title)}".strip()
            rows.append(_Row(identified, choice, index))
        rows.extend(
            (
                _Row("Zaznacz wszystkie", group=index, action=_Action.SELECT_ALL),
                _Row("Pobierz", group=index, action=_Action.DOWNLOAD),
                _Row("Cofnij", group=index, action=_Action.BACK),
            )
        )
    return tuple(rows), tuple(choices)


def _group_label(group: SeriesGroup) -> str:
    """Name one listed group by its release group, subtitle language, and series."""
    language: str = f"{_HINT_SEPARATOR}{group.subtitle_language.upper()}" if group.subtitle_language else ""
    episodes: int = len({choice.episode for choice in group.choices if _is_markable(choice, None)})
    count: int = len(group.choices)
    noun: str = (
        "wydanie"
        if count == 1
        else ("wydania" if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14} else "wydań")
    )
    return f"[{_safe(group.group)}{language}] {_safe(group.series)} · {episodes} odc. / {count} {noun}"


def _newest_detail(group: SeriesGroup) -> str:
    """Return the publication tail of one group, shown only when the terminal has room."""
    if group.newest is None:
        return ""
    return f"  najnowsze: {group.newest.strftime('%d.%m.%Y')}"


def _choice_label(choice: ReleaseChoice) -> str:
    facts: tuple[str, ...] = (
        _episode_label(choice),
        f"v{choice.name.version}" if choice.name.version is not None else "",
        f"{choice.name.resolution}p" if choice.name.resolution is not None else "",
        f"{choice.release.seeders} seedów",
        _safe(choice.release.size_text),
    )
    return _CHOICE_SEPARATOR.join(fact for fact in facts if fact)


def _episode_label(choice: ReleaseChoice) -> str:
    if choice.name.is_pack:
        return "cała paczka"
    episode: Decimal | None = choice.episode
    if episode is None:
        return "wydanie"
    if choice.absolute is not None:
        return f"{_episode_number(episode)} ({format(choice.absolute.normalize(), 'f')})"
    if choice.other_season:
        return f"{_episode_number(episode)}{_HINT_SEPARATOR}sezon?"
    return _episode_number(episode)


def _episode_number(episode: Decimal) -> str:
    return f"odc. {format(episode.normalize(), 'f')}"


def _candidate_label(candidate: TitleCandidate) -> str:
    """Describe one title candidate the way the chooser lists it."""
    facts: tuple[str, ...] = (
        _safe(candidate.romaji),
        str(candidate.year) if candidate.year else "",
        _safe(candidate.format or ""),
        f"{candidate.episodes} odc." if candidate.episodes else "",
        _status_label(candidate.status),
        _english_title(candidate),
    )
    return _HINT_SEPARATOR.join(fact for fact in facts if fact)


def _english_title(candidate: TitleCandidate) -> str:
    """Return the English title only when it says something the romaji one does not."""
    english: str = (candidate.english or "").strip()
    if not english or english.casefold() == candidate.romaji.casefold():
        return ""
    return _safe(english)


def _status_label(status: TitleStatus) -> str:
    return _STATUS_LABELS.get(status, "")


def _parse_range(typed: str) -> EpisodeRange | None:
    """Read the span typed in the footer, or nothing when it says no usable range."""
    match: re.Match[str] | None = _RANGE_RE.fullmatch(typed.strip())
    if match is None:
        return None
    upto: str | None = match.group("upto")
    if upto is not None:
        return EpisodeRange(first=None, last=Decimal(upto))
    first: Decimal = Decimal(match.group("first"))
    if match.group("dash") is None:
        return EpisodeRange(first=first, last=first)
    last: str | None = match.group("last")
    return EpisodeRange(first=first, last=None if last is None else Decimal(last))


def _range_size(episodes: EpisodeRange) -> int | None:
    """Return how many episodes a closed span asks for, or nothing when one end is open."""
    if episodes.first is None or episodes.last is None:
        return None
    return int(episodes.last - episodes.first) + 1


def _is_markable(choice: ReleaseChoice | None, episodes: EpisodeRange | None) -> bool:
    """Whether one release is a numbered episode of the chosen season inside *episodes*."""
    if choice is None or choice.name.is_pack or choice.episode is None or choice.other_season:
        return False
    return episodes is None or episodes.contains(choice.episode)


def _has_hash(choice: ReleaseChoice | None, hashes: frozenset[str]) -> bool:
    return choice is not None and choice.release.info_hash in hashes


def _row_label(row: _Row, width: int) -> str:
    full: str = f"{row.label}{row.detail}"
    return _truncate_right(full if len(full) <= width else row.label, width)


def _header(title: str, columns: int, rows: int, content_rows: int, subtitle: str = "") -> Text:
    top: int = max((rows - content_rows - 5) // 2, 0)
    shown: str = _truncate_right(title, max(columns - 2, 1))
    left: int = max((columns - len(shown)) // 2, 0)
    content = Text("\n" * top)
    content.append(f"{' ' * left}{shown}\n", style="white_bold")
    if subtitle:
        named: str = _truncate_right(subtitle, max(columns - 2, 1))
        content.append(f"{' ' * max((columns - len(named)) // 2, 0)}{named}\n", style="brand_accent")
    content.append("\n")
    return content


def _finish(content: Text, hint: str, columns: int, rows: int) -> Text:
    return with_footer(content, (hint,), columns, rows)


def _wrapped_hint(hint: str, width: int) -> tuple[str, ...]:
    lines: list[str] = []
    current: str = ""
    for part in hint.split(_HINT_SEPARATOR):
        candidate: str = f"{current}{_HINT_SEPARATOR}{part}" if current else part
        if current and len(candidate) > width:
            lines.append(current)
            current = part
            continue
        current = candidate
    lines.append(current)
    return tuple(_truncate_right(line, width) for line in lines)


def _visible_window(count: int, selected: int, rows: int, reserved: int = _HEADER_ROWS) -> tuple[int, int]:
    budget: int = max(rows - reserved, 1)
    if count <= budget:
        return 0, count
    start: int = min(max(selected - budget // 2, 0), count - budget)
    return start, start + budget


def _truncate_right(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _stated(problem: AniShiftError | OSError | ValueError) -> tuple[str, str]:
    """Translate domain codes preserved locally or carried by a resident refusal."""
    from anishift.cli.interactive.state import refusal_text  # noqa: PLC0415

    if not isinstance(problem, AniShiftError):
        return refusal_text(problem), ""
    if isinstance(problem, ControlError) and problem.reason == "download_recorded":
        counts: dict[str, int] | None = _download_counts(problem)
        if counts is None:
            return "Nie można potwierdzić wyniku zamówienia", "Sprawdź prywatny klient AniShift i log"
        return (
            f"Przyjęto: {counts['sent']} · już przyjęte: {counts['accepted']}"
            f" · wynik przekazania niepotwierdzony: {counts['uncertain']}",
            "Sprawdź prywatny klient AniShift i log",
        )
    code: ErrorCode | None = _code(problem)
    stated: tuple[str, str] | None = _PROBLEM_TEXTS.get(code) if code is not None else None
    if stated is not None:
        if isinstance(problem, ControlError) and code in {
            ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            ErrorCode.TORRENT_CLIENT_UNAUTHORIZED,
            ErrorCode.TORRENT_CLIENT_REFUSED,
        }:
            return stated[0], "Sprawdź prywatny klient AniShift i log"
        return stated
    return refusal_text(problem), "" if isinstance(problem, ControlError) else _safe(problem.context.suggestion)


def _download_counts(problem: AniShiftError | OSError | ValueError) -> dict[str, int] | None:
    if not isinstance(problem, ControlError) or problem.reason != "download_recorded":
        return None
    keys: tuple[str, ...] = ("sent", "accepted", "uncertain")
    counts: dict[str, int] = {
        key: value for key in keys if type(value := problem.context.details.get(key)) is int and value >= 0
    }
    return counts if len(counts) == len(keys) else None


def _code(problem: AniShiftError | OSError | ValueError) -> ErrorCode | None:
    if isinstance(problem, ControlError):
        try:
            return ErrorCode(problem.reason)
        except ValueError:
            return None
    return problem.context.code if isinstance(problem, AniShiftError) else None


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")
