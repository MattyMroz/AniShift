"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

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
    DownloadReceipt,
    ReleaseCatalog,
    ReleaseChoice,
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

_BUSY_HINT: Final[str] = "Esc anuluj"
"""Keyboard hint shown while the network thread works."""

_DONE_HINT: Final[str] = "dowolny klawisz: powrót"
"""Keyboard hint of the screen confirming the hand-off."""

_PROBLEM_HINT: Final[str] = "Enter wróć · Esc menu"
"""Keyboard hint of the screen reporting a failure."""

_SEARCHING: Final[str] = "Szukam…"
"""Sentence shown while the release index answers."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
"""Sentence shown when the session was built without an acquisition boundary."""

_EMPTY_CATALOG: Final[str] = f"Brak wydań w {_MIN_RESOLUTION_LABEL}+ dla tego tytułu"
"""Sentence shown when the query matched nothing of the required quality."""

_CHOICE_SEPARATOR: Final[str] = "  "
"""Separation between the facts of one release row."""

_HINT_SEPARATOR: Final[str] = " · "
"""Separation between the keyboard hints of one footer."""

_HEADER_ROWS: Final[int] = 7
"""Rows the heading, hint and footer take away from the release list."""


class AnimeResult(StrEnum):
    """Signal whether the anime controller stays open or returns Home."""

    CONTINUE = "continue"
    HOME = "home"


class _Screen(StrEnum):
    QUERY = "query"
    BUSY = "busy"
    RESULTS = "results"
    DONE = "done"
    PROBLEM = "problem"


@dataclass(frozen=True, slots=True)
class _Row:
    """One rendered result line: a group header, or one selectable release."""

    label: str
    choice: ReleaseChoice | None = None


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
        self._rows: tuple[_Row, ...] = ()
        self._choices: tuple[int, ...] = ()
        self._marked: set[int] = set()
        self._selected: int = 0
        self._hidden: int = 0
        self._busy: str = _SEARCHING
        self._done: str = ""
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

    def _handle_busy(self, key: str) -> AnimeResult:
        if key not in {"escape", "interrupt"}:
            return AnimeResult.CONTINUE
        self._generation += 1
        self._worker = None
        self._screen = _Screen.QUERY
        return AnimeResult.CONTINUE

    def _handle_results(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            self._screen = _Screen.QUERY
            return AnimeResult.CONTINUE
        if not self._choices:
            if key == "enter":
                self._screen = _Screen.QUERY
            return AnimeResult.CONTINUE
        if key in {"up", "down"}:
            self._move(-1 if key == "up" else 1)
        elif key == "space":
            self._toggle()
        elif key == "enter":
            self._start_download()
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

    def _start_search(self, query: str) -> None:
        generation: int = self._start_work(_SEARCHING)
        self._spawn(self._search, (query, generation))

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
        self._spawn(self._download, (chosen, generation))

    def _start_work(self, sentence: str) -> int:
        self._generation += 1
        self._screen = _Screen.BUSY
        self._busy = sentence
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _search(self, query: str, generation: int) -> None:
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
        self._show_results(generation, catalog)

    def _download(self, choices: Sequence[ReleaseChoice], generation: int) -> None:
        acquisition: AcquisitionService | None = self._service.acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.RESULTS)
            return
        try:
            receipt: DownloadReceipt = acquisition.download(choices)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime download failed", error_class=type(problem).__name__)
            self._fail(generation, _safe(str(problem)), _hint(problem), _Screen.RESULTS)
            return
        self._show_done(generation, receipt)

    def _show_results(self, generation: int, catalog: ReleaseCatalog) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._rows, self._choices = _catalog_rows(catalog)
            self._hidden = catalog.hidden
            self._marked = set()
            self._selected = self._choices[0] if self._choices else 0
            self._screen = _Screen.RESULTS
        self._invalidate()

    def _show_done(self, generation: int, receipt: DownloadReceipt) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._done = f"Wysłano {receipt.count} do qBittorrenta → {_safe(receipt.directory.name)}"
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

    def _render_busy(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._busy)) // 2, 0)
        content.append(f"{' ' * left}{self._busy}\n", style="brand_accent")
        return _finish(content, left, _BUSY_HINT, columns)

    def _render_results(self, columns: int, rows: int) -> Text:
        if not self._choices:
            content: Text = _header(_TITLE, columns, rows, 2)
            left: int = max((columns - len(_EMPTY_CATALOG)) // 2, 0)
            content.append(f"{' ' * left}{_EMPTY_CATALOG}\n", style="warning")
            return _finish(content, left, f"{self._hidden_label()} · Enter wróć", columns)
        start, end = _visible_window(len(self._rows), self._selected, rows)
        labels: tuple[str, ...] = tuple(_truncate_right(row.label, max(columns - 8, 1)) for row in self._rows)
        left = max((columns - min(max((len(label) for label in labels), default=1) + 8, columns)) // 2, 0)
        content = _header(_TITLE, columns, rows, end - start)
        for index in range(start, end):
            self._append_row(content, left, labels[index], index)
        return _finish(content, left, self._results_hint(), columns)

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

    def _results_hint(self) -> str:
        return f"zaznaczone: {len(self._marked)} · {self._hidden_label()} · Space zaznacz · Enter pobierz · Esc wróć"

    def _hidden_label(self) -> str:
        return f"ukryte poniżej {_MIN_RESOLUTION_LABEL}: {self._hidden}"


def _catalog_rows(catalog: ReleaseCatalog) -> tuple[tuple[_Row, ...], tuple[int, ...]]:
    """Flatten the catalog into rendered rows and the indexes of the selectable ones."""
    rows: list[_Row] = []
    choices: list[int] = []
    for group in catalog.groups:
        rows.append(_Row(f"[{_safe(group.group)}] {_safe(group.series)}"))
        for choice in group.choices:
            choices.append(len(rows))
            rows.append(_Row(_choice_label(choice), choice))
    return tuple(rows), tuple(choices)


def _choice_label(choice: ReleaseChoice) -> str:
    facts: tuple[str, ...] = (
        _episode_label(choice),
        f"{choice.name.resolution}p" if choice.name.resolution is not None else "",
        f"{choice.release.seeders} seedów",
        _safe(choice.release.size_text),
    )
    return _CHOICE_SEPARATOR.join(fact for fact in facts if fact)


def _episode_label(choice: ReleaseChoice) -> str:
    episode: Decimal | None = choice.name.episode
    if episode is None:
        return "paczka" if choice.name.batch else "wydanie"
    return f"odc. {format(episode.normalize(), 'f')}"


def _header(title: str, columns: int, rows: int, content_rows: int) -> Text:
    top: int = max((rows - content_rows - 5) // 2, 0)
    shown: str = _truncate_right(title, max(columns - 2, 1))
    left: int = max((columns - len(shown)) // 2, 0)
    content = Text("\n" * top)
    content.append(f"{' ' * left}{shown}\n\n", style="white_bold")
    return content


def _finish(content: Text, left: int, hint: str, columns: int) -> Text:
    for index, line in enumerate(_wrapped_hint(hint, max(columns - left, 1))):
        if index:
            content.append("\n")
        content.append(f"{' ' * left}{line}", style="gray")
    return content


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


def _visible_window(count: int, selected: int, rows: int) -> tuple[int, int]:
    budget: int = max(rows - _HEADER_ROWS, 1)
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


def _hint(problem: AniShiftError | OSError) -> str:
    if not isinstance(problem, AniShiftError):
        return ""
    return _safe(problem.context.suggestion)


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")
