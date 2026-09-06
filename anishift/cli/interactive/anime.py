"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    CatalogOrder,
    CheckOutcome,
    DownloadReceipt,
    EpisodeRange,
    ReleaseCatalog,
    ReleaseChoice,
    SearchQuery,
    SeasonContext,
    SeriesGroup,
    Subscription,
    SubscriptionService,
    TitleCandidate,
    TitleStatus,
    parse_query,
)
from anishift.application.events import sanitize_event_message
from anishift.errors import AniShiftError
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

_QUERY_HINT: Final[str] = "Enter szukaj · Esc wróć"
"""Keyboard hint of the title input."""

_TITLES_HINT: Final[str] = "Enter wybierz · Esc wróć"
"""Keyboard hint of the title candidate list."""

_BUSY_HINT: Final[str] = "Esc anuluj"
"""Keyboard hint shown while the network thread works."""

_DONE_HINT: Final[str] = "dowolny klawisz: powrót"
"""Keyboard hint of the screen confirming the hand-off."""

_PROBLEM_HINT: Final[str] = "Enter wróć · Esc menu"
"""Keyboard hint of the screen reporting a failure."""

_SEARCHING_TITLE: Final[str] = "Szukam tytułu…"
"""Sentence shown while the anime catalog names the title behind the typed phrase."""

_SEARCHING_RELEASES: Final[str] = "Szukam wydań…"
"""Sentence shown while the release index answers for the chosen title."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_SUBSCRIBING: Final[str] = "Zapisuję obserwację…"
"""Sentence shown while the subscription is stored and checked for the first time."""

_UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
"""Sentence shown when the session was built without an acquisition boundary."""

_NO_SUBSCRIPTIONS: Final[str] = "Subskrypcje są niedostępne w tej sesji"
"""Sentence shown when the session was built without a subscription boundary."""

_EPISODE_ONLY: Final[str] = "Obserwuj działa tylko na numerowanym odcinku"
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

_RANGE_CHARACTERS: Final[frozenset[str]] = frozenset("0123456789-")
"""Characters the range prompt accepts."""

_CHECK_CADENCE: Final[str] = "sprawdzam co godzinę"
"""Tail of the confirmation naming how often the watch looks for new episodes."""

_EMPTY_CATALOG: Final[str] = f"Brak wydań w {_MIN_RESOLUTION_LABEL}+ dla tego tytułu"
"""Sentence shown when the query matched nothing of the required quality."""

_CHOICE_SEPARATOR: Final[str] = "  "
"""Separation between the facts of one release row."""

_HINT_SEPARATOR: Final[str] = " · "
"""Separation between the keyboard hints of one footer."""

_HEADER_ROWS: Final[int] = 7
"""Rows the heading, hint and footer take away from a list without its own measurement."""

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


class _Screen(StrEnum):
    QUERY = "query"
    TITLES = "titles"
    BUSY = "busy"
    RESULTS = "results"
    DONE = "done"
    PROBLEM = "problem"


@dataclass(frozen=True, slots=True)
class _Row:
    """One rendered result line: a group header, or one selectable release.

    ``group`` names the listed group the line belongs to, and ``detail`` carries the tail
    shown only when the terminal is wide enough for it.
    """

    label: str
    choice: ReleaseChoice | None = None
    group: int = 0
    detail: str = ""


class AnimeController:
    """Own one ephemeral release search while AppService owns the network boundary."""

    def __init__(self, service: AppService, invalidate: Callable[[], None]) -> None:
        self._service: AppService = service
        self._invalidate: Callable[[], None] = invalidate
        self._lock: threading.Lock = threading.Lock()
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._screen: _Screen = _Screen.QUERY
        self._query: str = ""
        self._searched: str = ""
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._highlighted: int = 0
        self._candidate: TitleCandidate | None = None
        self._context: SeasonContext | None = None
        self._folder: str | None = None
        self._episodes: EpisodeRange | None = None
        self._order: CatalogOrder = CatalogOrder.NEWEST
        self._groups: tuple[SeriesGroup, ...] = ()
        self._rows: tuple[_Row, ...] = ()
        self._choices: tuple[int, ...] = ()
        self._marked: set[int] = set()
        self._selected: int = 0
        self._hidden: int = 0
        self._filtered: int = 0
        self._range: str | None = None
        self._fallback: str = ""
        self._busy: str = _SEARCHING_TITLE
        self._done: str = ""
        self._notice: str = ""
        self._problem: str = ""
        self._suggestion: str = ""
        self._problem_return: _Screen = _Screen.QUERY
        if service.acquisition is None:
            self._screen = _Screen.PROBLEM
            self._problem = _UNAVAILABLE

    def handle_key(self, key: str) -> AnimeResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            if self._screen is _Screen.QUERY:
                result: AnimeResult = self._handle_query(key)
            elif self._screen is _Screen.TITLES:
                result = self._handle_titles(key)
            elif self._screen is _Screen.BUSY:
                result = self._handle_busy(key)
            elif self._screen is _Screen.RESULTS:
                result = self._handle_results(key)
            elif self._screen is _Screen.DONE:
                result = AnimeResult.HOME
            else:
                result = self._handle_problem(key)
        return result

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
        """Discard the result of network work still in flight."""
        with self._lock:
            self._generation += 1

    def _handle_query(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return AnimeResult.HOME
        if key == "backspace":
            self._query = self._query[:-1]
        elif key == "space":
            self._query += " "
        elif key.startswith("text:"):
            self._query += key.removeprefix("text:")
        elif key == "enter" and self._query.strip():
            self._start_search(self._query.strip())
        return AnimeResult.CONTINUE

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
        self._screen = _Screen.QUERY
        return AnimeResult.CONTINUE

    def _handle_results(self, key: str) -> AnimeResult:
        if self._range is not None:
            return self._handle_range(key)
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._screen = _Screen.QUERY
            return AnimeResult.CONTINUE
        if not self._choices:
            if key == "enter":
                self._screen = _Screen.QUERY
            return AnimeResult.CONTINUE
        self._apply_results_key(key)
        return AnimeResult.CONTINUE

    def _apply_results_key(self, key: str) -> None:
        if key in {"up", "down"}:
            self._move(-1 if key == "up" else 1)
        elif key == "space":
            self._toggle()
        elif key == "enter":
            self._start_download()
        elif key in {"text:o", "text:O"}:
            self._start_subscription()
        elif key in {"text:a", "text:A"}:
            self._mark_group()
        elif key in {"text:z", "text:Z"}:
            self._range = ""
        elif key in {"text:s", "text:S"}:
            self._reorder()
        elif key in {"text:f", "text:F"} and self._episodes is not None:
            self._start_unfiltered_search()

    def _handle_range(self, key: str) -> AnimeResult:
        typed: str = self._range or ""
        if key in {"escape", "interrupt"}:
            self._range = None
        elif key == "enter":
            self._range = None
            self._apply_range(typed)
        elif key == "backspace":
            self._range = typed[:-1]
        elif key.startswith("text:") and key.removeprefix("text:") in _RANGE_CHARACTERS:
            self._range = typed + key.removeprefix("text:")
        return AnimeResult.CONTINUE

    def _handle_problem(self, key: str) -> AnimeResult:
        if key != "enter":
            return AnimeResult.HOME
        self._screen = self._problem_return
        self._problem = ""
        self._suggestion = ""
        return AnimeResult.CONTINUE

    def _move(self, delta: int) -> None:
        position: int = self._choices.index(self._selected) if self._selected in self._choices else 0
        self._selected = self._choices[(position + delta) % len(self._choices)]

    def _toggle(self) -> None:
        if self._selected in self._marked:
            self._marked.discard(self._selected)
            return
        self._marked.add(self._selected)

    def _apply_range(self, typed: str) -> None:
        episodes: EpisodeRange | None = _parse_range(typed)
        if episodes is None:
            self._notice = _RANGE_INVALID
            return
        self._mark_group(episodes)

    def _mark_group(self, episodes: EpisodeRange | None = None) -> None:
        group: int = self._rows[self._selected].group
        marked: tuple[int, ...] = tuple(
            index
            for index in self._choices
            if self._rows[index].group == group and _is_markable(self._rows[index].choice, episodes)
        )
        self._marked.update(marked)
        wanted: int | None = None if episodes is None else _range_size(episodes)
        if wanted is None or len(marked) >= wanted:
            self._notice = f"zaznaczono {len(marked)}"
            return
        self._notice = f"zaznaczono {len(marked)} z {wanted}"

    def _reorder(self) -> None:
        marked: frozenset[str] = frozenset(
            choice.release.info_hash for index in self._marked if (choice := self._rows[index].choice) is not None
        )
        highlighted: ReleaseChoice | None = self._rows[self._selected].choice
        self._order = CatalogOrder.SEEDERS if self._order is CatalogOrder.NEWEST else CatalogOrder.NEWEST
        ranked: bool = any(group.matches_title for group in self._groups)
        self._groups = tuple(sorted(self._groups, key=lambda group: _group_order(group, self._order, ranked=ranked)))
        self._rows, self._choices = _catalog_rows(self._groups)
        self._marked = {index for index in self._choices if _has_hash(self._rows[index].choice, marked)}
        self._selected = _same_choice(self._rows, self._choices, highlighted)

    def _start_search(self, text: str) -> None:
        self._searched = text
        self._candidate = None
        self._context = None
        self._folder = None
        query: SearchQuery = parse_query(text)
        self._episodes = query.episodes
        generation: int = self._start_work(_SEARCHING_TITLE)
        self._spawn(self._find_titles, (query.title, text, generation))

    def _start_title_search(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        self._candidate = candidate
        self._folder = candidate.folder_title()
        generation: int = self._start_work(_SEARCHING_RELEASES)
        self._spawn(self._search_title, (candidate, self._episodes, self._order, generation))

    def _start_unfiltered_search(self) -> None:
        candidate: TitleCandidate | None = self._candidate
        if candidate is None:
            return
        generation: int = self._start_work(_SEARCHING_RELEASES)
        self._spawn(self._search_releases, (candidate, None, self._order, self._context, generation))

    def _start_download(self) -> None:
        chosen: tuple[ReleaseChoice, ...] = tuple(
            choice for index in sorted(self._marked) if (choice := self._rows[index].choice) is not None
        )
        if not chosen:
            highlighted: ReleaseChoice | None = self._rows[self._selected].choice
            if highlighted is None:
                return
            chosen = (highlighted,)
        generation: int = self._start_work(_SENDING)
        self._spawn(self._download, (chosen, self._folder, generation))

    def _start_subscription(self) -> None:
        choice: ReleaseChoice | None = self._rows[self._selected].choice
        if choice is None:
            return
        if choice.name.is_pack or choice.episode is None:
            self._notice = _EPISODE_ONLY
            return
        if choice.other_season:
            self._notice = _OTHER_SEASON
            return
        generation: int = self._start_work(_SUBSCRIBING)
        self._spawn(self._subscribe, (choice, self._subscription_query(), self._folder, self._context, generation))

    def _subscription_query(self) -> str:
        if self._candidate is None:
            return self._searched
        group: SeriesGroup = self._groups[self._rows[self._selected].group]
        return f"{group.series} {group.group}"

    def _start_work(self, sentence: str) -> int:
        self._generation += 1
        self._screen = _Screen.BUSY
        self._busy = sentence
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _find_titles(self, title: str, text: str, generation: int) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            candidates: tuple[TitleCandidate, ...] = acquisition.find_titles(title)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title lookup failed", error_class=type(problem).__name__)
            self._search(text, _CATALOG_DOWN, generation)
            return
        if not candidates:
            self._search(text, _NO_TITLE, generation)
            return
        self._show_titles(generation, candidates)

    def _search(self, query: str, fallback: str, generation: int) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search(query)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime search failed", error_class=type(problem).__name__)
            self._fail(generation, _safe(str(problem)), _hint(problem), _Screen.QUERY)
            return
        self._show_results(generation, catalog, fallback=fallback)

    def _search_title(
        self,
        candidate: TitleCandidate,
        episodes: EpisodeRange | None,
        order: CatalogOrder,
        generation: int,
    ) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            context: SeasonContext | None = acquisition.season_context(candidate)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime season lookup failed", error_class=type(problem).__name__)
            context = None
        self._search_releases(candidate, episodes, order, context, generation)

    def _search_releases(
        self,
        candidate: TitleCandidate,
        episodes: EpisodeRange | None,
        order: CatalogOrder,
        context: SeasonContext | None,
        generation: int,
    ) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search_title(
                candidate, episodes=episodes, order=order, context=context
            )
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title search failed", error_class=type(problem).__name__)
            self._fail(generation, _safe(str(problem)), _hint(problem), _Screen.QUERY)
            return
        self._show_results(generation, catalog, episodes=episodes, context=context)

    def _download(self, choices: Sequence[ReleaseChoice], directory: str | None, generation: int) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.RESULTS)
            return
        try:
            receipt: DownloadReceipt = acquisition.download(choices, directory_name=directory)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime download failed", error_class=type(problem).__name__)
            self._fail(generation, _safe(str(problem)), _hint(problem), _Screen.RESULTS)
            return
        self._show_done(generation, f"Wysłano {receipt.count} do qBittorrenta → {_safe(receipt.directory.name)}")

    def _subscribe(
        self,
        choice: ReleaseChoice,
        query: str,
        directory: str | None,
        context: SeasonContext | None,
        generation: int,
    ) -> None:
        subscriptions: SubscriptionService | None = self._service.subscriptions
        if subscriptions is None:
            self._fail(generation, _NO_SUBSCRIPTIONS, "", _Screen.RESULTS)
            return
        try:
            subscription: Subscription = subscriptions.subscribe(
                query, choice, directory_name=directory, context=context
            )
            outcome: CheckOutcome = subscriptions.check(subscription)
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Anime subscription failed", error_class=type(problem).__name__)
            self._fail(generation, _safe(str(problem)), _hint(problem), _Screen.RESULTS)
            return
        result: str = (
            f"sprawdzenie nie powiodło się: {_safe(outcome.problem)}"
            if outcome.problem
            else f"pobrano {outcome.downloaded}"
        )
        self._show_done(
            generation,
            f"Obserwuję [{_safe(subscription.group)}] {_safe(subscription.series)} "
            f"od {_episode_number(subscription.next_episode)}"
            f"{_HINT_SEPARATOR}{result}{_HINT_SEPARATOR}{_CHECK_CADENCE}",
        )

    def _show_titles(self, generation: int, candidates: tuple[TitleCandidate, ...]) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._candidates = candidates
            self._highlighted = 0
            self._screen = _Screen.TITLES
        self._invalidate()

    def _show_results(
        self,
        generation: int,
        catalog: ReleaseCatalog,
        *,
        episodes: EpisodeRange | None = None,
        context: SeasonContext | None = None,
        fallback: str = "",
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._episodes = episodes
            self._context = context
            self._fallback = fallback
            self._groups = catalog.groups
            self._rows, self._choices = _catalog_rows(catalog.groups)
            self._hidden = catalog.hidden
            self._filtered = catalog.filtered
            self._marked = set()
            self._range = None
            self._notice = ""
            self._selected = self._choices[0] if self._choices else 0
            self._screen = _Screen.RESULTS
        self._invalidate()

    def _show_done(self, generation: int, sentence: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._done = sentence
            self._screen = _Screen.DONE
        self._invalidate()

    def _fail(self, generation: int, sentence: str, suggestion: str, back: _Screen) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._problem = sentence
            self._suggestion = suggestion
            self._problem_return = back
            self._screen = _Screen.PROBLEM
        self._invalidate()

    def _render_query(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - min(max(len(self._query) + 3, 32), columns)) // 2, 0)
        width: int = max(columns - left - 3, 1)
        content.append(f"{' ' * left}> {self._query[-width:]}▌\n", style="white_bold")
        return _finish(content, left, _QUERY_HINT, columns)

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
        return _finish(content, left, _TITLES_HINT, columns)

    def _render_busy(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._busy)) // 2, 0)
        content.append(f"{' ' * left}{self._busy}\n", style="brand_accent")
        return _finish(content, left, _BUSY_HINT, columns)

    def _render_results(self, columns: int, rows: int) -> Text:
        subtitle: str = self._title_header()
        if not self._choices:
            return self._render_empty(columns, rows, subtitle)
        labels: tuple[str, ...] = tuple(_row_label(row, max(columns - 8, 1)) for row in self._rows)
        left: int = max((columns - min(max((len(label) for label in labels), default=1) + 8, columns)) // 2, 0)
        heading: int = 2 + int(bool(subtitle))
        lines: tuple[str, ...] = _wrapped_hint(self._footer(), max(columns - left, 1))[: max(rows - heading - 1, 1)]
        start, end = _visible_window(len(self._rows), self._selected, rows, heading + len(lines))
        content: Text = _header(_TITLE, columns, rows, end - start + len(lines) - 1 + int(bool(subtitle)), subtitle)
        for index in range(start, end):
            self._append_row(content, left, labels[index], index)
        _append_hint(content, left, lines)
        return content

    def _render_empty(self, columns: int, rows: int, subtitle: str) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2, subtitle)
        left: int = max((columns - len(_EMPTY_CATALOG)) // 2, 0)
        content.append(f"{' ' * left}{_EMPTY_CATALOG}\n", style="warning")
        hints: list[str] = [self._fallback] if self._fallback else []
        hints.extend((self._hidden_label(), "Enter wróć"))
        return _finish(content, left, _HINT_SEPARATOR.join(hints), columns)

    def _append_row(self, content: Text, left: int, label: str, index: int) -> None:
        if self._rows[index].choice is None:
            content.append(f"{' ' * left}{label}\n", style="white_bold")
            return
        style: str = "brand_accent" if index == self._selected else "white_bold"
        marker: str = "[x] " if index in self._marked else "[ ] "
        content.append(" " * left)
        content.append(f"{_POINTER} " if index == self._selected else "  ", style=style)
        content.append(f"{marker}{_BULLET} {label}\n", style=style)

    def _render_done(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._done)) // 2, 0)
        content.append(f"{' ' * left}{self._done}\n", style="brand_accent")
        return _finish(content, left, _DONE_HINT, columns)

    def _render_problem(self, columns: int, rows: int) -> Text:
        lines: tuple[str, ...] = tuple(
            _truncate_right(line, max(columns - 4, 1)) for line in (self._problem, self._suggestion) if line
        )
        content: Text = _header(_TITLE, columns, rows, len(lines))
        left: int = max((columns - min(max((len(line) for line in lines), default=1), columns)) // 2, 0)
        for index, line in enumerate(lines):
            content.append(f"{' ' * left}{line}\n", style="error" if index == 0 else "gray")
        return _finish(content, left, _PROBLEM_HINT, columns)

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
        if self._range is not None:
            return f"{_RANGE_PROMPT}: {self._range}▌"
        return self._notice or self._results_hint()

    def _results_hint(self) -> str:
        hints: list[str] = [self._fallback] if self._fallback else []
        hints.append(f"zaznaczone: {len(self._marked)}")
        if self._episodes is not None:
            hints.append(f"filtr: {self._episodes.label}")
        hints.append(self._hidden_label())
        if self._filtered:
            hints.append(f"poza filtrem: {self._filtered}")
        hints.extend(self._marking_hints())
        hints.extend(("Enter pobierz", "O obserwuj", self._order_hint()))
        if self._episodes is not None:
            hints.append("F pokaż wszystkie")
        hints.append("Esc wróć")
        return _HINT_SEPARATOR.join(hints)

    def _marking_hints(self) -> tuple[str, ...]:
        finished: bool = self._candidate is not None and self._candidate.status is TitleStatus.FINISHED
        return ("A cała grupa", "Space/Z zaznacz") if finished else ("Space/A/Z zaznacz",)

    def _order_hint(self) -> str:
        return "S najnowsze" if self._order is CatalogOrder.SEEDERS else "S seedy"

    def _hidden_label(self) -> str:
        return f"ukryte poniżej {_MIN_RESOLUTION_LABEL}: {self._hidden}"


def _catalog_rows(groups: Sequence[SeriesGroup]) -> tuple[tuple[_Row, ...], tuple[int, ...]]:
    """Flatten the listed groups into rendered rows and the indexes of the selectable ones."""
    rows: list[_Row] = []
    choices: list[int] = []
    for index, group in enumerate(groups):
        rows.append(_Row(_group_label(group), None, index, _newest_detail(group)))
        for choice in group.choices:
            choices.append(len(rows))
            rows.append(_Row(_choice_label(choice), choice, index))
    return tuple(rows), tuple(choices)


def _group_label(group: SeriesGroup) -> str:
    """Name one listed group by its release group, subtitle language, and series."""
    language: str = f"{_HINT_SEPARATOR}{group.subtitle_language.upper()}" if group.subtitle_language else ""
    return f"[{_safe(group.group)}{language}] {_safe(group.series)}"


def _newest_detail(group: SeriesGroup) -> str:
    """Return the publication tail of one group, shown only when the terminal has room."""
    if group.newest is None:
        return ""
    return f"  najnowsze: {group.newest.strftime('%d.%m.%Y')}"


def _choice_label(choice: ReleaseChoice) -> str:
    facts: tuple[str, ...] = (
        _episode_label(choice),
        f"{choice.name.resolution}p" if choice.name.resolution is not None else "",
        f"{choice.release.seeders} seedów",
        _safe(choice.release.size_text),
    )
    return _CHOICE_SEPARATOR.join(fact for fact in facts if fact)


def _episode_label(choice: ReleaseChoice) -> str:
    if choice.name.is_pack:
        return "paczka"
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
    if choice is None or choice.episode is None or choice.other_season:
        return False
    return episodes is None or episodes.contains(choice.episode)


def _has_hash(choice: ReleaseChoice | None, hashes: frozenset[str]) -> bool:
    return choice is not None and choice.release.info_hash in hashes


def _same_choice(rows: Sequence[_Row], choices: Sequence[int], wanted: ReleaseChoice | None) -> int:
    """Return the row holding *wanted* after a reorder, or the first selectable row."""
    if wanted is not None:
        for index in choices:
            if _has_hash(rows[index].choice, frozenset({wanted.release.info_hash})):
                return index
    return choices[0] if choices else 0


def _group_order(group: SeriesGroup, order: CatalogOrder, *, ranked: bool) -> tuple[int, float, str, str]:
    """Order one group the way the facade does, so a local reorder needs no new search."""
    priority: int = int(not group.matches_title) if ranked else 0
    if order is CatalogOrder.NEWEST:
        weight: float = float("inf") if group.newest is None else -group.newest.timestamp()
    else:
        weight = -float(sum(choice.release.seeders for choice in group.choices))
    return (priority, weight, group.series.casefold(), group.group.casefold())


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


def _finish(content: Text, left: int, hint: str, columns: int) -> Text:
    _append_hint(content, left, _wrapped_hint(hint, max(columns - left, 1)))
    return content


def _append_hint(content: Text, left: int, lines: Sequence[str]) -> None:
    for index, line in enumerate(lines):
        if index:
            content.append("\n")
        content.append(f"{' ' * left}{line}", style="gray")


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
    return tuple(lines)


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


def _hint(problem: AniShiftError | OSError | ValueError) -> str:
    if not isinstance(problem, AniShiftError):
        return ""
    return _safe(problem.context.suggestion)


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")
