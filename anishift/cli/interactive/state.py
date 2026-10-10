"""Resident state and actions in the existing terminal renderer."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from enum import IntEnum, StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from natsort import os_sorted
from prompt_toolkit.data_structures import Point
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from rich.console import Console
from rich.text import Text

from anishift.application import (
    DeletionPreview,
    EpisodeReason,
    HistoryEvent,
    LibraryFileIdentity,
    LibrarySet,
    RefusalReason,
    RetryProposal,
    RunProgressSnapshot,
    decode_view,
)
from anishift.application.events import RunEvent, sanitize_event_message
from anishift.cli.interactive.actions import Action, ScreenActions, footer_segments, help_lines, pack_footer
from anishift.cli.interactive.anime import EPISODE_REASON_LABELS, AnimeController, AnimeResult
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeSnapshot
from anishift.cli.interactive.anime_view import (
    MIN_COLUMNS,
    MIN_ROWS,
    AnimeFrame,
    fit,
    render_anime,
    visible_rows,
)
from anishift.cli.interactive.menu import (
    append_wrapped_row,
    pack_keys,
    visible_window,
    wrap_entries,
)
from anishift.cli.interactive.progress import ObservedProgressTimer, RichRunProgress, render_material_progress
from anishift.cli.interactive.subscription_texts import (
    CHECK_SHOWN_S,
    SubscriptionState,
    check_state,
    check_text,
    row_columns,
    row_state,
)
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError
from anishift.platform.local_control import ControlError, ControlErrorCode
from anishift.platform.tray import open_path as _open_path

__all__ = ["StateController", "StateResult", "refusal_text"]

# ── Constants ─────────────────────────────────────────────────────────────────

_RETRY_PROBLEMS: Final[dict[str, str]] = {
    "retry_source_missing": "Brak lokalnego źródła; usuniętej treści nie można odtworzyć",
    "retry_reference_missing": "Brak zachowanej referencji wydania; wybierz wydanie ponownie w Anime",
    "retry_choose_one": (
        "Zakres zawiera lokalne materiały; wybierz jeden numer, aby zobaczyć właściwe dokończenie lub poprawkę"
    ),
    "retry_source_available": "Źródło jest już lokalnie; ponownie wybierz Ponów, aby przygotować Ręczny",
    "retry_acquisition_pending": "Wcześniejsze przekazanie nadal wymaga uzgodnienia; nie dodano drugiego pobrania",
    "legacy_subscription_retry": "Pobierz ten odcinek ponownie z Anime (P)",
}
"""Actionable retry refusals without claiming missing source bytes can be recovered."""

_HISTORY_LABELS: Final[dict[str, str]] = {
    "order_admitted": "przyjęto zamówienie",
    "download_confirmed": "pobrano źródło",
    "regeneration": "przyjęto regenerację",
    "processing_success": "ukończono",
    "processing_error": "błąd",
    "processing_interrupted": "przerwano",
    "delete_outcome": "usuwanie",
    "subscription_finished": "subskrypcja zakończona",
}
"""Operation boundary labels shown once per logical material."""

_HISTORY_PROBLEMS: Final[dict[str, str]] = {
    "history_corrupt": "Historia niedostępna · uszkodzony zapis; przetwarzanie działa dalej",
    "history_unavailable": "Historia niedostępna · błąd odczytu lub zapisu; przetwarzanie działa dalej",
}
"""Persistent observation warnings distinct from an empty history."""

_TABS: Final[tuple[str, ...]] = ("Anime", "Subskrypcje", "Przetwarzanie", "Biblioteka")
"""Views of the same resident snapshot, switched without network requests."""

_MINIMUM_HEADER_ROWS: Final[int] = 16
"""Minimum height retaining blank lines around the PANEL heading and tabs."""

_MINIMUM_TITLE_ROWS: Final[int] = 12
"""Minimum height retaining the PANEL heading above the tabs."""

_RECONNECT_S: Final[float] = 2.0
"""Delay before reconnecting a lost panel event stream."""

_CLIENT_PROBLEMS: Final[dict[str, str]] = {
    "The private torrent window was closed; downloads remain stopped until explicitly resumed": (
        "qBittorrent wyłączony · zlecenia czekają na wznowienie"
    ),
    "The private torrent client was taken over; automatic control is disabled": ("qBittorrent sterowany ręcznie"),
    "The private torrent client was opened manually; automatic control stopped": (
        "Otwarto qBittorrenta · sterowanie automatyczne wstrzymane"
    ),
    "The private torrent client could not start; resolve the problem and explicitly resume": (
        "Nie udało się uruchomić qBittorrenta · usuń przyczynę i wybierz Wznów"
    ),
}
"""Polish explanations of private client states surfaced by the transport boundary."""

_REFUSAL_TEXTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        RefusalReason.GROUP_RESERVED.value: "Inny panel zajął ten odcinek",
        RefusalReason.GROUP_PROCESSING.value: "Ten odcinek jest już przetwarzany",
        RefusalReason.GROUP_RELOCATING.value: "Gotowy odcinek jest przenoszony do biblioteki",
        RefusalReason.SESSION_CLOSED.value: "Połączenie z procesem w tle wygasło",
        RefusalReason.CLIENT_BOUND.value: "Ten panel jest już połączony w innej sesji",
        RefusalReason.NOT_RESERVED.value: "Najpierw zajmij odcinek, potem dodaj do niego plik",
        RefusalReason.FOREIGN_PREVIEW.value: "Ten wybór należy do innego panelu",
        RefusalReason.NOT_RESUMABLE.value: "Tej pracy nie da się wznowić",
        RefusalReason.PAUSED.value: "AniShift jest wstrzymany · wybierz Wznów, aby podjąć pracę",
        RefusalReason.SHUTTING_DOWN.value: "AniShift się kończy · nie przyjmuje już nowej pracy",
        RefusalReason.TRANSFER_METADATA_PENDING.value: (
            "Trwa przygotowanie pobrania · poczekaj na potwierdzenie wyboru plików"
        ),
    }
)
"""Polish sentence the panel shows for every refusal cause the resident names."""

_UNKNOWN_REFUSAL: Final[str] = "Proces w tle odrzucił polecenie"
"""Polish sentence for a refusal this version cannot name any more precisely."""

_CONTROL_PROBLEMS: Final[Mapping[ControlErrorCode, str]] = MappingProxyType(
    {
        ControlErrorCode.STALE_INSTANCE: "Proces w tle został uruchomiony ponownie · otwórz panel ponownie",
        ControlErrorCode.UNKNOWN_COMMAND: "Proces w tle nie obsługuje tego polecenia",
        ControlErrorCode.INVALID_PAYLOAD: "Proces w tle odrzucił niepoprawne dane polecenia",
        ControlErrorCode.STALE_PREVIEW: "Podgląd jest nieaktualny · przygotuj go ponownie",
        ControlErrorCode.CONFLICT: "Polecenie koliduje z bieżącą pracą",
        ControlErrorCode.ALREADY_PROCESSING: "Ten odcinek jest już przetwarzany",
        ControlErrorCode.REFUSED: _UNKNOWN_REFUSAL,
        ControlErrorCode.INTERNAL: "Wewnętrzny błąd procesu w tle · sprawdź log",
    }
)
"""Polish fallback for each public control code when no more precise reason is known."""

_SUBSCRIPTION_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "subscription_missing": "Tej subskrypcji już nie ma",
        "nothing_to_restore": "Brak usuniętej subskrypcji do przywrócenia",
        "subscription_exists": "Ten sezon jest już subskrybowany",
        "subscription_limit": "Osiągnięto limit subskrypcji; usuń jedną, aby dodać lub przywrócić",
        "subscription_not_airing": "Ten wpis nie ma przyszłych odcinków",
        "subscription_cut_unknown": "Nie wiadomo, ile odcinków już wyemitowano · spróbuj później",
        "source_failed": "Nie udało się odczytać katalogu · spróbuj ponownie",
        "target_not_waiting": "Ten odcinek już nie czeka na polskie napisy",
    }
)
"""Polish subscription refusals selected by machine reason rather than application prose."""

_SUBSCRIPTION_CHECKING: Final[str] = "Sprawdzam…"
"""Stan of a subscription whose requested check has not answered yet."""

_SHADOW_WARNING: Final[str] = "Tryb cienia — subskrypcje tylko zapisują propozycje"
"""Status row above the list while the owner records proposals instead of attempts."""

_NO_SUBSCRIPTIONS: Final[str] = "Brak subskrypcji"
"""Only line of an empty subscription list."""

_CONNECTING: Final[str] = "Łączenie…"
"""Only line of the subscription list before the owner's first listing."""

_NO_CONNECTION: Final[str] = "Automat: brak połączenia"
"""Status line without a live owner snapshot."""

_STATUS_COUNTS: Final[tuple[tuple[str, str], ...]] = (
    ("downloading", "pobiera"),
    ("processing", "przetwarza"),
    ("waiting", "czeka"),
)
"""Owner material counters in the order the status line names them."""

_DETAIL_HELP_ROWS: Final[int] = 3
"""Rows the help under Library files needs: a blank line, the "Ten ekran" heading and one hint line."""

_HISTORY_CRUMB: Final[str] = "Przetwarzanie \u203a Historia"
"""Breadcrumb above the History list."""

_ANSWERS: Final[str] = "Enter tak · Esc nie"
"""Keys answering the cancellation question."""

_LIBRARY_DELETED: Final[str] = "Usunięto · Ctrl+Z cofnij"
"""Library notice kept after a deleted set leaves the list, until the next move."""

_HISTORY_SPAN: Final[str] = "Historia z ostatnich 30 dni"
"""Help line naming how far back the default history reaches."""

_PANEL_ACTIONS: Final[tuple[Action, ...]] = (("M", "ręczny"), ("U", "ustawienia"))
"""Mode switches listed under ? on every list outside Anime."""

_TAB_KEYS: Final[frozenset[str]] = frozenset({"tab", "backtab", "left", "right"})
"""Keys switching the panel tab."""

_MOVE_KEYS: Final[frozenset[str]] = frozenset({"up", "down", "pageup", "pagedown", "home", "end"})
"""Keys moving a list cursor or scrolling a help block."""

_LIBRARY_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "library_set_missing": "Tego zestawu nie ma już w bibliotece",
        "library_result_missing": "Brakuje potwierdzonego głównego wyniku",
        "library_result_changed": "Główny wynik istnieje, ale jest zmieniony lub niepotwierdzony",
        "library_ownership_unknown": "Pochodzenie zestawu wymaga rozstrzygnięcia przed usunięciem",
        "library_source_held": "Źródło czeka na zwolnienie przez torrent",
        "library_source_missing": "Brakuje źródłowego pliku wideo tego zestawu",
        "library_scope_changed": "Zestaw zmienił się · przygotuj nowe potwierdzenie",
        "library_source_busy": "Plik jest nadal zapisywany lub niedostępny",
        "library_deleting": "Zestaw jest chroniony przez operację Kosza lub przywracania",
        "recycle_unsupported": "Kosz jest niedostępny dla tego środowiska",
        "recycle_unavailable": "Nie udało się potwierdzić dostępności operacji Kosza",
        "recycle_refused": "System odmówił przeniesienia pliku do Kosza",
        "recycle_timeout": "Upłynął limit operacji · jej wynik pozostaje niepewny",
        "recycle_cleanup_timeout": "Upłynął limit zamykania operacji · jej wynik pozostaje niepewny",
        "recycle_interrupted": "Operacja została przerwana · jej wynik pozostaje niepewny",
        "recycle_invalid_evidence": "Brak poprawnego potwierdzenia operacji Kosza",
        "recycle_incomplete": "System nie potwierdził pełnego wyniku operacji",
        "library_release_unavailable": "Nie można odczytać potwierdzenia zwolnienia torrenta",
        "restore_nothing": "Brak usuniętego zestawu do przywrócenia",
        "restore_already_completed": "Ostatnie usunięcie zostało już cofnięte",
        "restore_destination_occupied": "Miejsce przywracania jest zajęte · istniejący plik pozostawiono bez zmian",
        "restore_receipt_missing": "Brak dokładnego elementu w Koszu · mógł zostać opróżniony",
        "restore_unsupported_destination": "Przywracanie wymaga dostępnego miejsca na tym samym woluminie NTFS",
        "restore_unsafe_path": "Ścieżka przywracania jest niedostępna lub prowadzi przez dowiązanie",
        "restore_scope_changed": "Pliki przywracania zmieniły się · nie wykonano kolejnej operacji",
        "restore_interrupted": "Przywracanie przerwane · Ctrl+Z sprawdzi zapisany stan przed ponowieniem",
        "restore_incomplete": "System nie potwierdził pełnego przywrócenia",
        "restore_inflight": "Przywracanie wymaga rozliczenia zapisanej operacji",
    }
)
"""Polish explanations keyed by the owner's library reason codes."""

_FILE_ROLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "source": "źródło",
        "product": "wynik",
        "pending_source": "źródło · czeka na zwolnienie",
    }
)
"""Roles shown beside files without implying ownership of an external manual reference."""


def refusal_text(problem: BaseException) -> str:
    """Translate ControlError reasons and codes, otherwise return sanitized exception text."""
    reason: str = problem.reason if isinstance(problem, ControlError) else ""
    if reason in _RETRY_PROBLEMS:
        return _RETRY_PROBLEMS[reason]
    if reason in _SUBSCRIPTION_PROBLEMS:
        return _SUBSCRIPTION_PROBLEMS[reason]
    fallback: str = _safe_text(str(problem))
    if isinstance(problem, ControlError):
        fallback = (
            _CONTROL_PROBLEMS[problem.code]
            if problem.answered
            else (
                "Brak potwierdzonej odpowiedzi procesu w tle · sprawdź, czy proces działa, "
                "oraz Historię i log przed ponowieniem"
            )
        )
    return _REFUSAL_TEXTS.get(reason) or _LIBRARY_PROBLEMS.get(reason) or fallback or _UNKNOWN_REFUSAL


class _Tab(IntEnum):
    ANIME = 0
    SUBSCRIPTIONS = 1
    PROGRESS = 2
    FILES = 3


class StateResult(StrEnum):
    """Navigation requested from the state screen."""

    CONTINUE = "continue"
    HOME = "home"
    SETTINGS = "settings"
    MANUAL = "manual"


class StateController:
    """Present resident work through the shared selectable-list interface."""

    def __init__(
        self,
        session: ResidentSession,
        invalidate: Callable[[], None],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._parent: ResidentSession = session
        self._clock: Callable[[], datetime] = clock
        self._session: ResidentSession | None = None
        self._invalidate: Callable[[], None] = invalidate
        self._lock: threading.RLock = threading.RLock()
        self._stop: threading.Event = threading.Event()
        self._finished: bool = False
        self._open_requested: Mapping[str, object] | None = None
        self._library_target: str | None = None
        self._library_notice: str = ""
        self._snapshot: Mapping[str, object] = {}
        self._subscriptions: list[Mapping[str, object]] = []
        self._subscriptions_problem: str = ""
        self._subscriptions_shadow: bool = False
        self._subscription_checks: dict[str, tuple[str, str, datetime]] = {}
        self._subscription_target: str | None = None
        self._runs: dict[str, tuple[str, RichRunProgress]] = {}
        self._download_timers: dict[str, ObservedProgressTimer] = {}
        self._tab: int = _Tab.PROGRESS
        self._selected: int = 0
        self._positions: dict[int, int] = {}
        self._offsets: dict[int, int] = {}
        self._follow_cursor: dict[int, bool] = {}
        self._anime: AnimeController | None = None
        self._anime_top: int = 0
        self._connected: bool = False
        self._busy: bool = False
        self._notice: str = ""
        self._state_version: int = 0
        self._notice_version: int = -1
        self._notice_persistent: bool = False
        self._details: LibrarySet | None = None
        self._detail_selection: int = 0
        self._view_generation: int = 0
        self._history_open: bool = False
        self._history_items: tuple[HistoryEvent, ...] = ()
        self._history_query: str = ""
        self._history_problem: str = ""
        self._history_input: TextInput | None = None
        self._active_position: int = 0
        self._retry: RetryProposal | None = None
        self._manual_retry: RetryProposal | None = None
        self._question: tuple[str, str] | None = None
        self._help: bool = False
        self._help_offset: int = 0
        self._page: int = 1
        self._thread: threading.Thread = threading.Thread(target=self._watch, name="anishift-state", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Detach this panel without stopping resident work."""
        self._stop.set()
        if self._anime is not None:
            self._anime.cancel()
        with self._lock:
            self._view_generation += 1
        session: ResidentSession | None = self._session
        if session is not None:
            session.close()

    def finished(self) -> bool:
        """Answer whether the resident announced its end, so this view has to close with it."""
        return self._finished

    def take_open_request(self) -> Mapping[str, object] | None:
        """Consume a tray request on the panel's event loop."""
        with self._lock:
            requested: Mapping[str, object] | None = self._open_requested
            self._open_requested = None
            return requested

    def take_manual_retry(self) -> RetryProposal | None:
        """Transfer a confirmed local proposal to the existing Manual controller."""
        with self._lock:
            proposal: RetryProposal | None = self._manual_retry
            self._manual_retry = None
            return proposal

    def show_library(self, navigation: Mapping[str, object]) -> None:
        """Open Library and select an owner-validated set once its snapshot arrives."""
        with self._lock:
            self._details = None
            self._history_open = False
            self._history_input = None
            self._retry = None
            self._switch_tab(_Tab.FILES)
            target: object = navigation.get("set_id")
            self._library_target = target if isinstance(target, str) else None
            self._library_notice = _safe_text(navigation.get("notification_problem") or "")
            self._select_library_target(self._snapshot)
            self._follow_cursor[_Tab.FILES] = True
            self._work(lambda session: session.library(), success="")
        self._invalidate()

    def _select_library_target(self, payload: Mapping[str, object]) -> None:
        if self._library_target is None:
            return
        position: int | None = next(
            (index for index, item in enumerate(_library_rows(payload)) if item.get("set_id") == self._library_target),
            None,
        )
        if position is not None:
            self._selected = position
            self._positions[_Tab.FILES] = position
            self._library_target = None

    def show_processing(self) -> None:
        """Select current processing after the user starts a run."""
        with self._lock:
            self._view_generation += 1
            self._details = None
            self._history_open = False
            self._switch_tab(_Tab.PROGRESS)
        self._invalidate()

    def set_notice(self, message: str) -> None:
        """Show preparation or submission feedback without changing the selected view."""
        with self._lock:
            self._notify(message)
        self._invalidate()

    def _notify(self, message: str) -> None:
        self._notice = _safe_text(message).rstrip(".")
        self._notice_version = self._state_version
        self._notice_persistent = False

    def _library_context(self) -> tuple[str, str] | None:
        if self._tab != _Tab.FILES:
            return None
        details: LibrarySet | None = self._details
        if details is not None:
            return details.set_id, str(self._selected)
        rows: list[Mapping[str, object]] = _library_rows(self._snapshot)
        return (_library_row_id(rows[self._selected]), "") if self._selected < len(rows) else ("", "")

    def handle_key(self, key: str) -> StateResult:  # noqa: PLR0911
        """Navigate the shared list or submit one explicit action."""
        with self._lock:
            self._library_target = None
            if self._tab in {_Tab.FILES, _Tab.SUBSCRIPTIONS} and key in {
                *_MOVE_KEYS,
                *_TAB_KEYS,
                "escape",
                "backspace",
            }:
                self._view_generation += 1
                self._notify("")
            if self._question is not None:
                return self._question_key(key)
            if self._history_input is not None:
                self._history_input_key(key)
                return StateResult.CONTINUE
            if self._retry is not None:
                return self._retry_key(key)
            if self._tab == _Tab.ANIME and self._anime is not None:
                return self._anime_key(key)
            if self._help:
                return self._help_key(key)
            if self._tab == _Tab.FILES and key == "undo":
                self._work(lambda session: session.undo_deletion(), success="")
                self._invalidate()
                return StateResult.CONTINUE
            if self._details is not None:
                return self._details_key(key)
            if self._history_navigation(key):
                return StateResult.CONTINUE
            return self._list_key(key)

    def _question_key(self, key: str) -> StateResult:
        target: tuple[str, str] | None = self._question
        self._question = None
        if key == "enter" and target is not None and self._question_rows(target):
            if self._busy:
                self._question = target
            else:
                self._command(*_cancel_command(target))
        self._invalidate()
        return StateResult.CONTINUE

    def _question_rows(self, target: tuple[str, str]) -> list[Mapping[str, object]]:
        return [item for item in self._processing_rows() if _cancel_target(item) == target]

    def _drop_vanished_question(self) -> None:
        if self._question is not None and not self._question_rows(self._question):
            self._question = None

    def _question_text(self) -> str:
        target: tuple[str, str] | None = self._question
        rows: list[Mapping[str, object]] = [] if target is None else self._question_rows(target)
        if target is None or not rows:
            return ""
        if target[0] == "info_hash":
            head: str = "Anulować pobieranie?" if len(rows) == 1 else f"Anulować pobieranie ({len(rows)} materiałów)?"
        else:
            scope: object = rows[0].get("group_ids", [])
            head = f"Anulować całe zlecenie ({len(scope) if isinstance(scope, list) else 1} materiałów)?"
        return head

    def _help_key(self, key: str) -> StateResult:
        if key in {"text:?", "escape", "backspace", "interrupt"}:
            self._help = False
        elif key in _TAB_KEYS:
            self._help = False
            return self._list_key(key)
        elif key.casefold() == "text:o":
            return self._action_key("o")
        elif key in _MOVE_KEYS:
            offset: int = self._help_offset
            moves: dict[str, int] = {
                "up": offset - 1,
                "down": offset + 1,
                "pageup": offset - self._page,
                "pagedown": offset + self._page,
                "home": 0,
                "end": sys.maxsize,
            }
            self._help_offset = max(moves[key], 0)
        self._invalidate()
        return StateResult.CONTINUE

    def _open_help(self) -> None:
        self._help = True
        self._help_offset = 0

    def _history_navigation(self, key: str) -> bool:
        if self._tab != _Tab.PROGRESS or not self._history_open:
            return False
        if key in {"escape", "interrupt", "backspace", "text:h", "text:H"}:
            self._history_open = False
            self._selected = self._active_position
            self._view_generation += 1
            self._invalidate()
            return True
        if key == "enter" or key.casefold() in {"text:p", "text:s", "text:/"}:
            self._history_key(key)
            return True
        return False

    def _list_key(self, key: str) -> StateResult:
        if key in {"escape", "interrupt", "backspace"}:
            self._view_generation += 1
            return StateResult.HOME
        if key in _TAB_KEYS:
            self._view_generation += 1
            self._details = None
            self._switch_tab((self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS))
            self._notify("")
            if self._tab == _Tab.FILES:
                self._work(lambda session: session.library())
        elif key in _MOVE_KEYS:
            self._follow_cursor[self._tab] = True
            self._selected = _moved(self._selected, key, max(len(self._entries(120)), 1), self._page)
        elif key in {"space", "enter", "delete", "undo"} and self._tab == _Tab.SUBSCRIPTIONS:
            self._subscription_key(key)
        elif key == "enter" and self._tab == _Tab.FILES:
            self._file_action("open")
        elif key == "delete" and self._tab == _Tab.FILES:
            self._file_action("delete")
        elif key == "delete" and self._tab == _Tab.PROGRESS and not self._history_open:
            self._processing_action("x")
        elif key.startswith("text:"):
            return self._action_key(key.removeprefix("text:").casefold())
        self._invalidate()
        return StateResult.CONTINUE

    def _subscription_key(self, key: str) -> None:
        if key == "undo":
            self._work(lambda session: session.command("subscription_restore"), success="")
            return
        if key == "enter" and self._anime is not None and self._anime.replay_list_batch():
            self._notify("Sprawdzam wynik…")
            self._notice_persistent = True
            return
        row: Mapping[str, object] | None = self._selected_subscription()
        if key in {"text:/", "text:d"} or (key == "enter" and row is None):
            if self._anime is not None:
                self._switch_tab(_Tab.ANIME)
                self._anime.start_subscription_search()
            return
        if row is None:
            return
        if key == "enter":
            if not isinstance(row.get("anilist_id"), int):
                self._notify("Ta subskrypcja nie ma wpisu AniList · usuń ją i dodaj ponownie")
            elif self._anime is not None:
                self._switch_tab(_Tab.ANIME)
                self._anime.open_subscription(row)
            return
        kind: str = {
            "delete": "subscription_remove",
            "text:x": "subscription_remove",
            "text:r": "subscription_check",
            "text:f": "subscription_check",
        }.get(key, "subscription_resume" if row.get("paused") else "subscription_pause")
        self._subscription_command(kind, row)

    def _selected_subscription(self) -> Mapping[str, object] | None:
        if self._selected < len(self._subscriptions):
            return self._subscriptions[self._selected]
        return None

    def _subscription_command(self, kind: str, row: Mapping[str, object], number: int | None = None) -> None:
        identifier: str = str(row["subscription_id"])
        payload: dict[str, object] = {"subscription_id": identifier}
        if number is not None:
            self._work(lambda session: self._download_now(session, {**payload, "number": number}), success="")
            return
        if kind == "subscription_remove":
            removed: str = f"Usunięto {_safe_text(row.get('title', ''))} · Ctrl+Z cofnij"
            self._work(lambda session: session.command(kind, payload), success=removed, persistent=True)
            return
        if kind == "subscription_check":
            self._subscription_checks[identifier] = (
                _SUBSCRIPTION_CHECKING,
                _SUBSCRIPTION_CHECKING,
                self._clock() + timedelta(seconds=CHECK_SHOWN_S),
            )
        self._work(lambda session: session.command(kind, payload), success="")

    def _download_now(self, session: ResidentSession, payload: Mapping[str, object]) -> None:
        try:
            session.command("subscription_check", payload)
        except ControlError as error:
            if error.reason != "target_not_waiting" or self._anime is None:
                raise
            self._anime.polish_refused(refusal_text(error))

    def _show_subscription_list(self, subscription_id: str | None, notice: str) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            self._switch_tab(_Tab.SUBSCRIPTIONS)
            self._subscription_target = subscription_id
            self._select_subscription_target()
            if notice:
                self._notify(notice)
                self._notice_persistent = True
        self._invalidate()

    def _subscription_notice(self, notice: str) -> None:
        with self._lock:
            if self._stop.is_set() or self._tab != _Tab.SUBSCRIPTIONS:
                return
            self._notify(notice)
            self._notice_persistent = bool(notice)
        self._invalidate()

    def _select_subscription_target(self) -> None:
        position: int | None = next(
            (
                index
                for index, item in enumerate(self._subscriptions)
                if item.get("subscription_id") == self._subscription_target
            ),
            None,
        )
        if position is None:
            return
        self._subscription_target = None
        self._positions[_Tab.SUBSCRIPTIONS] = position
        if self._tab == _Tab.SUBSCRIPTIONS:
            self._selected = position

    def _details_key(self, key: str) -> StateResult:
        details: LibrarySet | None = self._details
        letter: str = key.removeprefix("text:").casefold() if key.startswith("text:") else ""
        if key in {"escape", "interrupt", "backspace", "text:?", *_TAB_KEYS}:
            self._view_generation += 1
            self._details = None
            self._selected = self._detail_selection
            if key in _TAB_KEYS:
                return self._list_key(key)
        elif letter in {"o", "m", "u"}:
            return self._action_key(letter)
        elif (key == "delete" or letter == "x") and details is not None:
            set_id: str = details.set_id
            generation: int = self._view_generation
            self._work(lambda session: self._delete_set(session, set_id, generation), success="")
        elif key == "enter" or letter == "f":
            self._open_detail_file(reveal=key != "enter")
        elif key in _MOVE_KEYS:
            self._follow_cursor[self._viewport()] = True
            self._selected = _moved(self._selected, key, max(len(self._entries(120)), 1), self._page)
        self._invalidate()
        return StateResult.CONTINUE

    def _open_detail_file(self, *, reveal: bool) -> None:
        details: LibrarySet | None = self._details
        index: int = self._selected - (len(_library_detail_entries(details)) - len(details.files)) if details else -1
        if details is None or not 0 <= index < len(details.files):
            self._notify("Wybierz wiersz pliku")
            self._notice_persistent = True
            return
        identity: LibraryFileIdentity | None = details.files[index].identity
        if identity is None:
            self._notify("Wybrany plik jest niedostępny")
            self._notice_persistent = True
            return
        generation: int = self._view_generation

        def action(session: ResidentSession) -> None:
            path: Path = session.library_file(details.set_id, identity)
            with self._lock:
                if generation != self._view_generation or self._stop.is_set():
                    return
            _open_path(path, show_folder=reveal)

        self._work(action, success="")

    def attach_anime(self, controller: AnimeController) -> None:
        """Reuse the session's one search controller inside the Anime tab."""
        with self._lock:
            self._anime = controller
            controller.refresh_provider_locks(_rows(self._snapshot.get("provider_locks")))
            controller.link_subscriptions(self._show_subscription_list, self._subscription_notice)
            controller.refresh_subscriptions(self._subscriptions, paused=self._snapshot.get("auto_enabled") is False)

    def suspend(self) -> None:
        """Invalidate child completion navigation when the enclosing panel is hidden."""
        with self._lock:
            self._library_target = None
            self._question = None
            if self._anime is not None:
                self._anime.cancel()

    def _switch_tab(self, tab: int) -> None:
        self._library_target = None
        self._question = None
        self._help = False
        self._view_generation += 1
        if self._tab == _Tab.ANIME and self._anime is not None:
            if self._anime.in_subscriptions:
                self._anime.leave_subscriptions()
            self._anime.cancel()
        self._positions[self._tab] = self._selected
        self._tab = tab
        self._selected = self._positions.get(tab, 0)

    def _viewport(self) -> int:
        if self._details is not None:
            return len(_TABS) + 1
        return self._tab

    def mouse(self, event: MouseEvent) -> bool:
        """Cancel an open question on a press or forward Anime cells, reporting whether the panel took the event."""
        with self._lock:
            if self._question is not None and event.event_type is MouseEventType.MOUSE_DOWN:
                self._question = None
            elif self._tab != _Tab.ANIME or self._anime is None:
                return False
            else:
                self._anime.mouse(
                    MouseEvent(
                        Point(event.position.x, event.position.y - self._anime_top),
                        event.event_type,
                        event.button,
                        event.modifiers,
                    )
                )
        self._invalidate()
        return True

    def view_key(self) -> tuple[object, ...]:
        """Identify the painted tab and list, so a selection never outlives them."""
        with self._lock:
            return (self._shown_tab(), self._viewport(), self._history_open, self._retry is not None, self._help)

    def select(self, index: int) -> None:
        """Move the cursor to a clicked row outside Anime without running its action."""
        with self._lock:
            if self._tab == _Tab.ANIME or self._retry is not None or self._help:
                return
            if not 0 <= index < len(self._entries(120)):
                return
            if index != self._selected and self._tab in {_Tab.FILES, _Tab.SUBSCRIPTIONS}:
                self._view_generation += 1
                self._notify("")
            self._library_target = None
            self._selected = index
            self._follow_cursor[self._viewport()] = False
        self._invalidate()

    def scroll(self, direction: int) -> None:
        """Move the visible list without changing its selected identity."""
        with self._lock:
            viewport: int = self._viewport()
            if self._tab == _Tab.ANIME:
                if self._anime is not None:
                    self._anime.scroll(direction)
                self._invalidate()
                return
            if self._help:
                self._help_offset = max(self._help_offset + direction * 3, 0)
                self._invalidate()
                return
            self._offsets[viewport] = max(self._offsets.get(viewport, 0) + direction * 3, 0)
            self._follow_cursor[viewport] = False
        self._invalidate()

    def _anime_key(self, key: str) -> StateResult:
        anime: AnimeController | None = self._anime
        if anime is None:
            return StateResult.CONTINUE
        if key in {"tab", "backtab"} or (key in {"left", "right"} and not anime.input_focused):
            self._switch_tab((self._shown_tab() + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS))
            self._invalidate()
            return StateResult.CONTINUE
        if key.casefold() == "text:o" and not anime.accepts_text:
            return self._action_key("o")
        result: AnimeResult = anime.handle_key(key)
        command: tuple[str, Mapping[str, object], int | None] | None = anime.take_subscription_command()
        if result is AnimeResult.HOME:
            return StateResult.HOME
        if result is AnimeResult.SUBSCRIPTIONS:
            self._switch_tab(_Tab.SUBSCRIPTIONS)
            self._notify("")
        if command is not None:
            self._subscription_command(*command)
        self._invalidate()
        return StateResult.CONTINUE

    def _action_key(self, key: str) -> StateResult:
        navigation: dict[str, StateResult] = {
            "u": StateResult.SETTINGS,
            "m": StateResult.MANUAL,
        }
        if key in navigation:
            self._view_generation += 1
            return navigation[key]
        if key == "h" and self._tab == _Tab.PROGRESS:
            self._active_position = self._selected
            self._selected = 0
            self._history_open = True
            self._load_history()
        elif key == "o":
            self._command("set_auto", {"enabled": not self._snapshot.get("auto_enabled", False)})
        elif self._tab == _Tab.FILES and key in {"?", "d"}:
            self._library_details()
        elif key == "?":
            self._open_help()
        elif self._tab == _Tab.SUBSCRIPTIONS and key in {"/", "d", "f", "r", "w", "x"}:
            self._subscription_key(f"text:{key}")
        elif self._tab == _Tab.PROGRESS and not self._history_open:
            self._processing_action(key)
        elif self._tab == _Tab.FILES:
            self._file_action(key)
        self._invalidate()
        return StateResult.CONTINUE

    def _library_details(self) -> None:
        if self._selected < len(_library_rows(self._snapshot)) and self._connected and not self._busy:
            self._file_action("d")
        else:
            self._open_help()

    def _processing_action(self, key: str) -> None:
        item: Mapping[str, object] | None = self._selected_material()
        if item is None:
            return
        target: tuple[str, str] | None = _cancel_target(item)
        if key in {"c", "x"}:
            self._question = target
            return
        toggle: tuple[str, str] | None = _download_toggle(item)
        if key == "w" and target is not None and target[0] == "info_hash" and toggle is not None:
            self._command("transfer", {"info_hash": target[1], "action": toggle[0]})

    def _selected_material(self) -> Mapping[str, object] | None:
        materials: list[Mapping[str, object]] = self._processing_rows()
        return materials[self._selected] if self._selected < len(materials) else None

    def _load_history(self) -> None:
        generation: int = self._view_generation
        query: str = self._history_query

        def load(session: ResidentSession) -> None:
            items: tuple[HistoryEvent, ...] | None = None
            problem: str = ""
            try:
                items = session.history(query)
            except ControlError as error:
                if error.reason not in _HISTORY_PROBLEMS:
                    raise
                problem = _HISTORY_PROBLEMS[error.reason]
            with self._lock:
                if generation != self._view_generation or not self._history_open or self._stop.is_set():
                    return
                self._history_problem = problem
                if items is None:
                    return
                selected: str | None = (
                    self._history_items[self._selected].material_id
                    if self._selected < len(self._history_items)
                    else None
                )
                self._history_items = items
                self._selected = next((index for index, item in enumerate(items) if item.material_id == selected), 0)

        self._work(load, success="")

    def _history_key(self, key: str) -> None:
        if key.casefold() in {"text:s", "text:/"}:
            self._history_input = TextInput(self._history_query)
        elif self._selected < len(self._history_items):
            identifier: str = self._history_items[self._selected].material_id
            if key == "enter":
                self._work(lambda session: _open_episode(session, identifier), success="")
            else:
                self._prepare_retry(lambda session: session.retry_proposal(identifier))
        self._invalidate()

    def _history_input_key(self, key: str) -> None:
        editor: TextInput | None = self._history_input
        if editor is None:
            return
        if editor.handle(key):
            self._invalidate()
            return
        if key == "enter":
            if self._busy:
                self._notify("Poprzednia czynność jeszcze trwa; zatwierdź wyszukiwanie po jej zakończeniu")
                self._invalidate()
                return
            self._history_query = editor.text
            self._history_input = None
            self._load_history()
        elif key in {"escape", "interrupt"}:
            self._history_input = None
        self._invalidate()

    def _prepare_retry(self, prepare: Callable[[ResidentSession], RetryProposal]) -> None:
        generation: int = self._view_generation

        def load(session: ResidentSession) -> None:
            proposal: RetryProposal = prepare(session)
            with self._lock:
                if generation == self._view_generation and not self._stop.is_set():
                    self._retry = proposal
                    self._help = False

        self._work(load, success="")

    def _retry_key(self, key: str) -> StateResult:
        proposal: RetryProposal | None = self._retry
        if proposal is None:
            return StateResult.CONTINUE
        if key in {"escape", "interrupt"}:
            self._retry = None
        elif key == "enter" and proposal.action in {"manual", "resume"}:
            self._manual_retry = proposal
            self._retry = None
            return StateResult.MANUAL
        elif key == "enter":
            self._retry = None
            generation: int = self._view_generation
            self._work(lambda session: self._execute_repeat(session, proposal, generation))
        self._invalidate()
        return StateResult.CONTINUE

    def _execute_repeat(self, session: ResidentSession, proposal: RetryProposal, generation: int) -> None:
        if proposal.action == "reacquire" and proposal.operation_id is not None:
            session.reacquire(proposal.operation_id)
        else:
            msg = "Nieaktualne ponowienie; wybierz materiał jeszcze raz"
            raise ValueError(msg)

    def _file_action(self, key: str) -> None:
        if key == "p":
            if _relocation_problems(self._snapshot):
                self._command("ready_retry")
            return
        library: list[Mapping[str, object]] = _library_rows(self._snapshot)
        if key not in {"open", "f", "d", "delete", "x"} or self._selected >= len(library):
            return
        set_id: str = str(library[self._selected]["set_id"])
        if key in {"delete", "x"}:
            generation: int = self._view_generation
            self._work(lambda session: self._delete_set(session, set_id, generation), success="")
            return
        if key == "d":
            generation = self._view_generation
            self._work(lambda session: self._show_details(session, set_id, generation))
            return
        self._work(lambda session: _open_episode(session, set_id, show_folder=key == "f"))

    def _delete_set(self, session: ResidentSession, set_id: str, generation: int) -> None:
        preview: DeletionPreview = session.preview_deletion(set_id)
        with self._lock:
            if self._stop.is_set() or generation != self._view_generation:
                return
        session.delete_set(preview)
        with self._lock:
            if generation != self._view_generation or self._stop.is_set():
                return
            if self._details is not None and self._details.set_id == set_id:
                self._details = None
                self._selected = self._detail_selection
            self._notify(_LIBRARY_DELETED)
            self._notice_persistent = True

    def _show_details(self, session: ResidentSession, set_id: str, generation: int) -> None:
        details: LibrarySet = session.library_details(set_id)
        with self._lock:
            if self._tab != _Tab.FILES or generation != self._view_generation or self._stop.is_set():
                return
            self._detail_selection = self._selected
            self._selected = 0
            self._follow_cursor[len(_TABS) + 1] = True
            self._details = details
            self._help = False

    def _command(self, kind: str, payload: Mapping[str, object] | None = None) -> None:
        self._work(lambda session: session.command(kind, payload))

    def _work(
        self,
        action: Callable[[ResidentSession], object],
        *,
        success: str = "Polecenie przyjęte",
        persistent: bool = False,
    ) -> None:
        if self._busy:
            if self._tab != _Tab.FILES:
                self._notify("Poprzednia czynność jeszcze trwa; możesz przejść do ustawień")
            return
        self._busy = True
        self._notify("" if self._tab == _Tab.FILES else "Wykonywanie polecenia…")
        threading.Thread(
            target=self._perform,
            args=(action, success, self._view_generation),
            kwargs={"persistent": persistent},
            name="anishift-state-action",
            daemon=True,
        ).start()

    def _perform(
        self,
        action: Callable[[ResidentSession], object],
        success: str = "Polecenie przyjęte",
        generation: int | None = None,
        *,
        persistent: bool = False,
    ) -> None:
        session: ResidentSession | None = None
        context: tuple[str, str] | None = None
        try:
            with self._lock:
                if generation is None:
                    generation = self._view_generation
                context = self._library_context()
            session = self._parent.new_session()
            action(session)
            with self._lock:
                if (
                    generation == self._view_generation
                    and context == self._library_context()
                    and self._notice != _LIBRARY_DELETED
                ):
                    self._notify("" if self._tab == _Tab.FILES else success)
                    self._notice_persistent = persistent
        except (AniShiftError, ControlError, OSError, ValueError) as error:
            with self._lock:
                if generation == self._view_generation and context == self._library_context():
                    self._notify(refusal_text(error))
                    self._notice_persistent = self._tab == _Tab.FILES
        finally:
            if session is not None:
                session.close()
            with self._lock:
                self._busy = False
            self._invalidate()

    def _watch(self) -> None:
        while not self._stop.is_set():
            lost: bool = True
            try:
                session: ResidentSession = self._parent.new_session()
                self._session = session
                for frame in session.observe(panel=True):
                    if self._stop.is_set():
                        break
                    self._receive(session, frame)
            except (AniShiftError, ControlError, OSError, ValueError, TypeError) as error:
                lost = isinstance(error, OSError) or (isinstance(error, ControlError) and error.connection_lost)
                with self._lock:
                    self._notify(refusal_text(error))
                    self._notice_persistent = self._tab == _Tab.FILES
            finally:
                if lost and not self._stop.is_set():
                    self._parent.disconnect()
                if self._session is not None:
                    self._session.close()
                with self._lock:
                    self._connected = False
                    self._observe_downloads()
                self._invalidate()
            if self._stop.wait(_RECONNECT_S):
                break

    def _receive(self, session: ResidentSession, frame: Mapping[str, object]) -> None:  # noqa: C901, PLR0912, PLR0915
        payload: object = frame.get("payload")
        if frame.get("event") == "panel_open":
            with self._lock:
                self._open_requested = payload if isinstance(payload, Mapping) else {}
            self._invalidate()
            return
        if not isinstance(payload, Mapping):
            return
        event: str = str(frame.get("event", ""))
        self._forward_anime(event, payload)
        if frame.get("event") == "control_problem":
            with self._lock:
                self._notify("Widok nieaktualny: odpowiedź przekracza limit.")
            self._invalidate()
            return
        if event == "subscription_checked":
            self._receive_check(payload)
            return
        if frame.get("event") == "state_changed":
            if not self._connected and self._anime is not None:
                self._anime.refresh_offer()
            listing: Mapping[str, object] = session.command("subscriptions_list")
            subscriptions: list[Mapping[str, object]] = _rows(listing.get("subscriptions"))
            with self._lock:
                previous_processing: list[str] = self._processing_row_ids()
            self._restore_progress(session, payload)
            with self._lock:
                previous_details: LibrarySet | None = self._details
            details: LibrarySet | None = self._refresh_details(session, previous_details)
            anime: AnimeController | None = self._anime
            with self._lock:
                refresh_episodes: bool = self._tab == _Tab.ANIME and payload != self._snapshot
            if anime is not None and refresh_episodes:
                anime.refresh_episode_states()
            with self._lock:
                context: tuple[str, str] | None = self._library_context()
                if payload != self._snapshot:
                    self._state_version += 1
                self._preserve_tab_selection(_Tab.SUBSCRIPTIONS, self._subscriptions, subscriptions, "subscription_id")
                self._preserve_processing_selection(previous_processing, self._processing_row_ids(payload))
                self._preserve_library_selection(payload)
                self._snapshot = payload
                self._select_library_target(payload)
                if self._anime is not None and self._anime is anime:
                    self._anime.refresh_provider_locks(_rows(payload.get("provider_locks")))
                if self._details is previous_details:
                    self._details = details
                    if previous_details is not None and details is None:
                        self._selected = self._detail_selection
                self._adopt_subscriptions(listing, subscriptions)
                self._connected = True
                self._observe_downloads()
                if self._notice_version < self._state_version and not self._notice_persistent:
                    self._notice = ""
                if context != self._library_context() and self._notice_persistent and self._notice != _LIBRARY_DELETED:
                    self._notify("")
                self._drop_vanished_question()
                if payload.get("shutting_down"):
                    self._finished = True
                    self._stop.set()
        elif frame.get("event") == "run_event":
            self._receive_progress(session, decode_view(RunEvent, payload))
        self._invalidate()

    def _forward_anime(self, event: str, payload: Mapping[str, object]) -> None:
        if self._anime is not None and event in {
            "episode_searching",
            "episode_result",
            "episode_batch",
            "episode_offer_partial",
            "control_problem",
        }:
            self._anime.receive(event, payload)

    def _adopt_subscriptions(self, listing: Mapping[str, object], subscriptions: list[Mapping[str, object]]) -> None:
        self._subscriptions = subscriptions
        self._subscriptions_problem = str(listing.get("problem") or "")
        self._subscriptions_shadow = listing.get("shadow") is True
        if self._subscription_target is not None:
            self._select_subscription_target()
        if self._anime is not None:
            self._anime.refresh_subscriptions(subscriptions, paused=self._snapshot.get("auto_enabled") is False)

    def _receive_check(self, payload: Mapping[str, object]) -> None:
        check: object = payload.get("last_check")
        identifier: object = payload.get("subscription_id")
        if not isinstance(check, Mapping) or not isinstance(identifier, str):
            return
        with self._lock:
            self._subscription_checks[identifier] = (
                check_state(check),
                check_text(check),
                self._clock() + timedelta(seconds=CHECK_SHOWN_S),
            )
            if self._anime is not None:
                self._anime.subscription_checked(identifier, check)
        self._invalidate()

    def _receive_progress(self, session: ResidentSession, event: RunEvent) -> None:
        with self._lock:
            progress: tuple[str, RichRunProgress] | None = self._runs.get(event.run_id)
        if progress is None:
            self._restore_progress(session, session.command("status"))
        with self._lock:
            progress = self._runs.get(event.run_id)
            if progress is None:
                return
            previous: list[str] = self._processing_row_ids()
            progress[1].emit(event)
            self._preserve_processing_selection(previous, self._processing_row_ids())
            self._observe_downloads()
            self._drop_vanished_question()

    def _preserve_tab_selection(
        self,
        tab: int,
        old: list[Mapping[str, object]],
        new: list[Mapping[str, object]],
        key: str,
    ) -> None:
        position: int = self._selected if self._tab == tab else self._positions.get(tab, 0)
        if position >= len(old):
            return
        identifier: object = old[position].get(key)
        position = next(
            (index for index, item in enumerate(new) if item.get(key) == identifier),
            min(position, max(len(new) - 1, 0)),
        )
        self._positions[tab] = position
        if self._tab == tab:
            self._selected = position

    @staticmethod
    def _refresh_details(session: ResidentSession, previous: LibrarySet | None) -> LibrarySet | None:
        if previous is None:
            return None
        try:
            return session.library_details(previous.set_id)
        except ControlError as error:
            if error.reason != "library_set_missing":
                raise
            return None

    def _preserve_processing_selection(self, old: list[str], new: list[str]) -> None:
        position: int = self._selected
        if self._tab != _Tab.PROGRESS:
            position = self._positions.get(_Tab.PROGRESS, 0)
        if self._history_open:
            position = self._active_position
        identifier: str | None = old[position] if position < len(old) else None
        position = new.index(identifier) if identifier in new else min(position, max(len(new) - 1, 0))
        if self._history_open:
            self._active_position = position
            return
        self._positions[_Tab.PROGRESS] = position
        if self._tab != _Tab.PROGRESS:
            return
        self._selected = position

    def _preserve_library_selection(self, payload: Mapping[str, object]) -> None:
        old: list[Mapping[str, object]] = _library_rows(self._snapshot)
        new: list[Mapping[str, object]] = _library_rows(payload)
        position: int = self._selected if self._details is None else self._detail_selection
        if self._tab != _Tab.FILES:
            position = self._positions.get(_Tab.FILES, 0)
        selected_id: object = _library_row_id(old[position]) if position < len(old) else None
        position = next(
            (index for index, item in enumerate(new) if _library_row_id(item) == selected_id),
            min(position, max(len(new) - 1, 0)),
        )
        self._positions[_Tab.FILES] = position
        if self._tab != _Tab.FILES:
            return
        if self._details is None:
            self._selected = position
        else:
            self._detail_selection = position

    def _restore_progress(self, session: ResidentSession, payload: Mapping[str, object]) -> None:
        entries: list[Mapping[str, object]] = _rows(payload.get("run_progress"))
        identifiers: set[str] = {str(item["run_id"]) for item in entries}
        with self._lock:
            self._runs = {key: value for key, value in self._runs.items() if key in identifiers}
        for item in entries:
            run_id: str = str(item["run_id"])
            with self._lock:
                existing: tuple[str, RichRunProgress] | None = self._runs.get(run_id)
            if existing is not None and existing[0] == item.get("preview_id") and self._connected:
                continue
            snapshot: RunProgressSnapshot = decode_view(
                RunProgressSnapshot, session.command("run_progress", {"run_id": run_id})
            )
            if existing is not None and existing[0] == snapshot.preview.preview_id:
                for event in snapshot.events:
                    existing[1].emit(event)
                continue
            restored: RichRunProgress = RichRunProgress.from_snapshot(snapshot, self._invalidate)
            with self._lock:
                self._runs[run_id] = (snapshot.preview.preview_id, restored)

    def render(self, columns: int, rows: int) -> Text:
        """Pin heading and tabs to the top and the body's keys above the status line."""
        with self._lock:
            budget: int = max(rows - 1, 1)
            spaced: bool = rows >= _MINIMUM_HEADER_ROWS
            heading: list[Text] = []
            if rows >= _MINIMUM_TITLE_ROWS:
                heading.append(_centered(Text("PANEL", style="white_bold"), columns))
            if spaced:
                heading.append(Text())
            heading.append(_centered(self._tabs(columns), columns))
            if spaced:
                heading.append(Text())
            area: int = max(budget - len(heading), 1)
            if self._tab == _Tab.ANIME and self._anime is not None and area > MIN_ROWS:
                body: Text = self._pin_status(self._anime.render(columns, area - 1), columns, area)
            elif self._tab == _Tab.ANIME and self._anime is not None:
                body = self._anime.render(columns, area)
            elif self._help:
                body = self._help_body(columns, area)
            elif self._tab == _Tab.SUBSCRIPTIONS and self._retry is None:
                body = self._subscription_body(columns, area)
            else:
                body = self._list_body(columns, area)
            self._anime_top = len(heading)
            return Text("\n").join([*heading, *body.split("\n", allow_blank=True)])

    def _list_body(self, columns: int, rows: int) -> Text:
        entries: list[tuple[str | Text, bool | None]] = self._entries(max(columns - 8, 1))
        selected: int = min(self._selected, max(len(entries) - 1, 0))
        if self._retry is None:
            self._selected = selected
        console: Console = Console(width=max(columns - 2, 1))
        footer: list[Text] = [
            line
            for hint in self._view_footer(max(columns - 4, 1))
            if hint
            for line in (hint if isinstance(hint, Text) else Text(hint, style="gray")).wrap(
                console, max(columns - 2, 1)
            )
        ]
        status: Text = Text(self._global_status(max(columns - 4, 1)), style="gray")
        footer = [*footer[: max(rows - 4, 0)], status]
        wrapped: tuple[tuple[str | Text, ...], ...] = wrap_entries(tuple(label for label, _ in entries), columns)
        remaining: int = max(rows - 2 - len(footer), 1)
        heights: tuple[int, ...] = tuple(map(len, wrapped))
        start, end = visible_window(len(entries), selected, remaining + 7, heights=heights)
        viewport: int = self._viewport()
        if self._follow_cursor.get(viewport, True):
            self._offsets[viewport] = start
        else:
            last: int = visible_window(len(entries), len(entries) - 1, remaining + 7, heights=heights)[0]
            start = min(self._offsets.get(viewport, 0), last)
            self._offsets[viewport] = start
            end = len(entries)
        content: Text = Text()
        markers: int = 2 if any(checked is not None for _label, checked in entries) else 0
        widths: list[int] = [
            line.cell_len if isinstance(line, Text) else Text(line).cell_len for lines in wrapped for line in lines
        ]
        left: int = max((columns - 2 - markers - max(widths, default=0)) // 2, 0)
        for index in range(start, end):
            if remaining <= 0:
                break
            checked: bool | None = entries[index][1]
            marker: str = "" if checked is None else ("● " if checked else "○ ")
            lines: tuple[str | Text, ...] = wrapped[index][:remaining]
            append_wrapped_row(content, left, lines, index == selected, marker, index=index)
            remaining -= len(lines)
            self._page = max(index - start + 1, 1)
        if self._details is not None and remaining >= _DETAIL_HELP_ROWS:
            for line in ("", *help_lines(self._actions().listed, max(columns - left - 4, 1)))[:remaining]:
                content.append(f"{' ' * (left + 2)}{line}\n", style="gray")
        if not entries:
            empty: str = (
                "Brak aktywnego przetwarzania"
                if self._tab == _Tab.PROGRESS and not self._history_open
                else "Brak pozycji"
            )
            if self._tab == _Tab.PROGRESS and self._history_open and self._history_problem:
                empty = "Historia niedostępna"
            content.append_text(_centered(Text(empty, style="gray"), columns))
        body: list[Text] = [self._breadcrumb(columns), *content.split("\n")]
        area: int = rows - len(footer)
        top: int = max((area - len(body)) // 2, 0)
        padding: list[Text] = [Text() for _ in range(max(area - top - len(body), 0))]
        return Text("\n").join(
            [*(Text() for _ in range(top)), *body, *padding, *(_centered(line, columns) for line in footer)]
        )

    def _shown_tab(self) -> int:
        if self._tab == _Tab.ANIME and self._anime is not None and self._anime.in_subscriptions:
            return _Tab.SUBSCRIPTIONS
        return self._tab

    def _tabs(self, columns: int = 120) -> Text:
        shown: int = self._shown_tab()
        tabs: Text = Text()
        for index, name in enumerate(_TABS):
            if index:
                tabs.append(" · ", style="gray")
            tabs.append(name, style="brand_accent" if shown == index else "gray")
        if tabs.cell_len > max(columns - 2, 1):
            return Text(f"← {_TABS[shown]} ({shown + 1}/{len(_TABS)}) →", style="brand_accent")
        return tabs

    def _view_footer(self, width: int) -> list[str | Text]:
        question: str = self._question_text()
        if question:
            asked: str = f"{question} {_ANSWERS}"
            return [asked] if Text(asked).cell_len <= width else [question, _ANSWERS]
        if self._retry is not None:
            return ["Enter przygotuj · Esc wróć", self._notice]
        if self._tab == _Tab.PROGRESS and self._history_open:
            if self._history_input is not None:
                return [self._history_input.render(100), "Enter szukaj · Esc anuluj", self._history_problem]
            return [*pack_footer(footer_segments(self._actions()), width), self._history_problem, self._notice]
        return self._footer(width)

    def _footer(self, width: int) -> list[str | Text]:
        result: list[str | Text] = []
        if self._notice and (self._tab != _Tab.FILES or self._notice_persistent):
            result.append(self._notice.rstrip("."))
        if self._tab == _Tab.FILES and self._library_notice:
            result.append(self._library_notice)
        relocations: list[Mapping[str, object]] = _relocation_problems(self._snapshot)
        if self._details is None and self._tab == _Tab.FILES and relocations:
            names: str = ", ".join(_safe_text(item["name"]) for item in relocations)
            result.append(f"P ponów przenoszenie do biblioteki · {names}")
        result.extend(pack_footer(footer_segments(self._actions(), more=self._details is None), width))
        return result

    def _help_body(self, columns: int, rows: int) -> Text:
        width: int = max(columns - 4, 1)
        intro: tuple[str, ...] = (_HISTORY_SPAN,) if self._tab == _Tab.PROGRESS and self._history_open else ()
        lines: tuple[str, ...] = help_lines(self._actions().listed, width, intro=intro)
        footer: list[Text] = [Text("Esc wróć", style="gray"), Text(self._global_status(width), style="gray")]
        area: int = rows - len(footer)
        visible: int = max(area - 2, 1)
        self._page = visible
        self._help_offset = min(self._help_offset, max(len(lines) - visible, 0))
        shown: tuple[str, ...] = lines[self._help_offset : self._help_offset + visible]
        left: int = max((columns - max((Text(line).cell_len for line in shown), default=0)) // 2, 0)
        top: int = max((area - len(shown) - 1) // 2, 0)
        return Text("\n").join(
            [
                *(Text() for _ in range(top)),
                self._breadcrumb(columns),
                *(Text(f"{' ' * left}{line}", style="gray") for line in shown),
                *(Text() for _ in range(max(area - top - len(shown) - 1, 0))),
                *(_centered(line, columns) for line in footer),
            ]
        )

    def _actions(self) -> ScreenActions:
        if self._details is not None:
            return ScreenActions(
                (("Enter", "otwórz plik"), ("F", "folder"), ("X", "usuń")), (("Ctrl+Z", "cofnij"), *_PANEL_ACTIONS)
            )
        if self._tab == _Tab.SUBSCRIPTIONS:
            return self._subscription_actions()
        if self._tab == _Tab.PROGRESS and self._history_open:
            return ScreenActions(
                (("Enter", "otwórz"), ("P", "ponów"), ("/", "szukaj")), (("H", "zamknij"), *_PANEL_ACTIONS)
            )
        if self._tab == _Tab.PROGRESS:
            return self._processing_actions()
        listed: bool = self._selected < len(_library_rows(self._snapshot))
        relocation: tuple[Action, ...] = (("P", "ponów przenoszenie"),) if _relocation_problems(self._snapshot) else ()
        return ScreenActions(
            (("Enter", "otwórz"), ("F", "folder"), ("X", "usuń")) if listed else (),
            (("Ctrl+Z", "cofnij"), *relocation, *_PANEL_ACTIONS),
        )

    def _subscription_actions(self) -> ScreenActions:
        row: Mapping[str, object] | None = self._selected_subscription()
        undo: tuple[Action, ...] = (("Ctrl+Z", "cofnij"), *_PANEL_ACTIONS)
        if row is None:
            return ScreenActions((("/", "dodaj pierwszą"),) if self._snapshot else (), undo)
        toggle: Action = ("W", "wznów" if row.get("paused") else "wstrzymaj")
        return ScreenActions(
            (("Enter", "szczegóły"), ("/", "dodaj"), toggle), (("R", "sprawdź teraz"), ("X", "usuń"), *undo)
        )

    def _processing_actions(self) -> ScreenActions:
        item: Mapping[str, object] | None = self._selected_material()
        target: tuple[str, str] | None = None if item is None else _cancel_target(item)
        toggle: tuple[str, str] | None = (
            _download_toggle(item) if item is not None and target is not None and target[0] == "info_hash" else None
        )
        footer: tuple[Action, ...] = (
            *((("W", toggle[1]),) if toggle is not None else ()),
            *((("X", "anuluj"),) if target is not None else ()),
            ("H", "historia"),
        )
        return ScreenActions(footer, _PANEL_ACTIONS)

    def _subscription_body(self, columns: int, rows: int) -> Text:
        tight: bool = rows == MIN_ROWS and columns >= MIN_COLUMNS
        area: int = rows if tight else max(rows - 1, 1)
        items: tuple[AnimeRow, ...] = self._subscription_rows()
        self._selected = min(self._selected, max(len(items) - 1, 0))
        visible: int = visible_rows(area)
        self._page = visible
        offset: int = min(self._offsets.get(_Tab.SUBSCRIPTIONS, 0), max(len(items) - visible, 0))
        if self._follow_cursor.get(_Tab.SUBSCRIPTIONS, True):
            offset = max(min(offset, self._selected), self._selected - visible + 1)
        self._offsets[_Tab.SUBSCRIPTIONS] = offset
        empty: str = _NO_SUBSCRIPTIONS if self._snapshot else _CONNECTING
        snapshot: AnimeSnapshot = AnimeSnapshot(
            AnimeScreen.SUBSCRIPTIONS if items else AnimeScreen.DETAILS,
            "",
            items or (AnimeRow("empty", empty, navigable=False),),
            cursor=self._selected,
            offset=offset,
            notice=self._notice.rstrip("."),
            controls=footer_segments(self._actions()),
            global_status=self._subscription_warning(),
        )
        frame: AnimeFrame = render_anime(snapshot, columns, area, self._clock().timestamp())
        lines: list[Text] = list(frame.text.split("\n"))
        if tight:
            del lines[next(index for index in range(frame.first_row, rows) if not lines[index].plain.strip())]
        return self._pin_status(Text("\n").join(lines), columns, rows)

    def _pin_status(self, body: Text, columns: int, rows: int) -> Text:
        lines: list[Text] = list(body.split("\n", allow_blank=True))[: max(rows - 1, 0)]
        padding: list[Text] = [Text() for _ in range(max(rows - 1 - len(lines), 0))]
        status: Text = _centered(Text(self._global_status(max(columns - 4, 1)), style="gray"), columns)
        return Text("\n").join([*lines, *padding, status])

    def _breadcrumb(self, columns: int) -> Text:
        crumb: str = ""
        if self._tab == _Tab.PROGRESS and self._history_open:
            crumb = _HISTORY_CRUMB
        elif self._details is not None:
            crumb = f"Biblioteka \u203a {_safe_text(self._details.name)}"
        return _centered(Text(fit(crumb, max(columns - 2, 1)), style="white_bold"), columns)

    def _subscription_rows(self) -> tuple[AnimeRow, ...]:
        now: datetime = self._clock()
        rows: list[AnimeRow] = []
        for item in self._subscriptions:
            state: SubscriptionState = row_state(item, now)
            shown: tuple[str, str, datetime] | None = self._subscription_checks.get(str(item.get("subscription_id")))
            if shown is not None and now < shown[2]:
                state = SubscriptionState(shown[0], shown[1])
            episodes, ready = row_columns(item)
            title: str = _safe_text(item.get("title", ""))
            rows.append(
                AnimeRow(
                    str(item.get("subscription_id")),
                    title,
                    number=episodes,
                    ready=ready,
                    status=state.text,
                    detail="" if state.detail == state.text else state.detail,
                )
            )
        return tuple(rows)

    def _subscription_warning(self) -> str:
        if self._subscriptions_problem:
            return "Monitoring nie działa: nie można zapisać stanu"
        return _SHADOW_WARNING if self._subscriptions_shadow else ""

    def _global_status(self, width: int) -> str:
        if not self._connected or not self._snapshot:
            return fit(_NO_CONNECTION, width)
        counts: object = self._snapshot.get("material_counts", {})
        values: Mapping[str, object] = counts if isinstance(counts, Mapping) else {}
        counted: tuple[str, ...] = tuple(f"{label} {values[key]}" for key, label in _STATUS_COUNTS if values.get(key))
        if self._snapshot.get("pause_incomplete"):
            state: str = "Automat: pauza niepełna"
        elif self._snapshot.get("pausing"):
            state = "Automat: zatrzymywanie"
        elif not self._snapshot.get("auto_enabled"):
            return fit("Automat wstrzymany", width)
        else:
            state = "Automat: praca" if counted else "Automat: bezczynny"
        return pack_keys((state, *counted), width, optional=tuple(reversed(counted)), limit=1)[0]

    def _entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        if self._retry is not None:
            labels: dict[str, str] = {
                "resume": f"Dokończ całe zapisane zlecenie · {len(self._retry.group_ids)} materiałów · podgląd",
                "manual": "Popraw wybrany lokalny materiał w Ręcznym · wybór zakresu przebudowy",
                "reacquire": "Pobierz ponownie zachowane wydanie · nowe jawne zamówienie",
            }
            return [(labels.get(self._retry.action, "Nieznana droga ponowienia"), None)]
        if self._tab == _Tab.PROGRESS and self._history_open:
            return [
                (
                    f"{item.occurred_at[:19].replace('T', ' ')} · {_safe_text(item.name)}"
                    f" · {_HISTORY_LABELS.get(item.kind, item.kind)}"
                    + (" · odtworzony zapis · czas przyjęcia" if item.recovered_from_admission else ""),
                    None,
                )
                for item in self._history_items
            ]
        entries: list[tuple[str | Text, bool | None]] = []
        if self._details is not None:
            return _library_detail_entries(self._details)
        if self._tab == _Tab.PROGRESS:
            return self._processing_entries(columns)
        if self._tab == _Tab.SUBSCRIPTIONS:
            return [(_safe_text(item.get("title", "")), None) for item in self._subscriptions]
        if self._tab == _Tab.FILES:
            entries = [(_safe_text(item.get("name", "")), None) for item in _library_rows(self._snapshot)]
        return entries

    def _processing_entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        entries: list[tuple[str | Text, bool | None]] = []
        for item in self._processing_rows():
            if item.get("stage") == "processing":
                status: str | None = (
                    "Brak odczytu" if not self._connected else ("Wstrzymano" if self._held(item) else None)
                )
                line: Text = self._runs[str(item["run_id"])][1].render_group(
                    str(item["group_id"]), columns, status=status
                )
            else:
                label, fraction = self._download_progress(item)
                name: str = _safe_text(item.get("name", ""))
                if not name or name in {item.get("info_hash"), item.get("material_id"), item.get("group_id")}:
                    name = "Materiał"
                timer: ObservedProgressTimer | None = self._download_timers.get(str(item.get("material_id")))
                line = render_material_progress(
                    name,
                    label,
                    fraction if fraction is not None or timer is None else timer.fraction,
                    columns,
                    elapsed_seconds=None if timer is None else timer.elapsed(),
                )
            entries.append((line, None))
        return entries

    def _held(self, item: Mapping[str, object]) -> bool:
        return bool(self._snapshot.get("paused")) and item.get("automatic") is not False

    def _observe_downloads(self) -> None:
        manual: set[str] = {
            str(item.get("run_id")) for item in self._processing_rows() if item.get("automatic") is False
        }
        for run_id, (_preview, progress) in self._runs.items():
            progress.observe_activity(active=self._connected and (not self._snapshot.get("paused") or run_id in manual))
        current: dict[str, ObservedProgressTimer] = {}
        for item in self._processing_rows():
            if item.get("stage") == "processing":
                continue
            identifier: str = str(item.get("material_id"))
            timer: ObservedProgressTimer = self._download_timers.get(identifier) or ObservedProgressTimer()
            generation: str = str(item.get("acquisition_id"))
            if item.get("stage") == "waiting" or timer.generation != generation:
                timer = ObservedProgressTimer(generation=generation)
            _label, fraction = self._download_progress(item)
            timer.observe(
                active=self._connected
                and not self._snapshot.get("transfers_problem")
                and not item.get("problem")
                and item.get("acquisition_state") == "accepted"
                and item.get("stage") == "download"
                and item.get("state") in {"downloading", "forcedDL"}
                and fraction is not None,
                fraction=fraction,
            )
            current[identifier] = timer
        self._download_timers = current

    def _download_progress(self, item: Mapping[str, object]) -> tuple[str, float | None]:  # noqa: PLR0911
        fraction: object = item.get("progress")
        measured: float | None = float(fraction) if isinstance(fraction, (int, float)) else None
        if item.get("reason") == EpisodeReason.FINALIZATION_FAILED:
            return "Finalizacja", None
        if item.get("stage") == "waiting":
            return ("Wstrzymano" if self._held(item) else "Przygotowanie"), None
        if item.get("problem"):
            return "Wymaga uwagi", None
        if item.get("reason") == EpisodeReason.WAITING_PREVIOUS_TRANSFER:
            return EPISODE_REASON_LABELS[EpisodeReason.WAITING_PREVIOUS_TRANSFER], None
        if not self._connected or self._snapshot.get("transfers_problem"):
            return "Brak odczytu", None
        state: object = item.get("state")
        if _download_toggle(item) == ("resume", "wznów"):
            return "Wstrzymano", measured
        if state in {"metaDL", "forcedMetaDL"} or item.get("acquisition_state") == "pending_send":
            return "Metadane", measured
        if state is None:
            return "Brak transferu", None
        if state in {"error", "missingFiles"}:
            return "Błąd transferu", None
        if state in {"downloading", "forcedDL", "stalledDL"}:
            return (
                "Brak odczytu" if measured is None else ("Brak źródeł" if state == "stalledDL" else "Pobieranie")
            ), measured
        return {
            "queuedDL": "W kolejce",
            "uploading": "Pobrane",
            "stalledUP": "Pobrane",
            "forcedUP": "Pobrane",
            "queuedUP": "Pobrane",
            "moving": "Przenoszenie",
        }.get(str(state), "Sprawdzanie"), measured

    def _processing_rows(self, snapshot: Mapping[str, object] | None = None) -> list[Mapping[str, object]]:
        payload: Mapping[str, object] = self._snapshot if snapshot is None else snapshot
        running: set[str] = {
            str(item["request_id"])
            for item in _rows(payload.get("requests"))
            if item.get("state") in {"accepted", "running"}
        }
        processing: list[Mapping[str, object]] = [
            item
            for item in _rows(payload.get("materials"))
            if item.get("stage") == "processing"
            and item.get("state") in {"accepted", "running"}
            and str(item.get("run_id")) in running
            and (progress := self._runs.get(str(item.get("run_id")))) is not None
            and progress[1].group_active(str(item.get("group_id")))
        ]
        downloads: list[Mapping[str, object]] = [
            item
            for item in _rows(payload.get("materials"))
            if item.get("acquisition_state") in {"pending_send", "accepted", "complete"}
            and (
                item.get("stage") == "download"
                or (
                    item.get("stage") == "waiting"
                    and item.get("reason") in {"preparing", EpisodeReason.FINALIZATION_FAILED}
                )
            )
        ]
        preparing: list[Mapping[str, object]] = [
            {**item, "stage": "waiting", "reason": "preparing", "admitted_processing": True}
            for item in _rows(payload.get("materials"))
            if item.get("stage") == "processing"
            and item.get("state") in {"accepted", "running"}
            and str(item.get("run_id")) in running
            and (
                (progress := self._runs.get(str(item.get("run_id")))) is None
                or progress[1].group_pending(str(item.get("group_id")))
            )
        ]
        return [*downloads, *preparing, *processing]

    def _processing_row_ids(self, snapshot: Mapping[str, object] | None = None) -> list[str]:
        rows: list[Mapping[str, object]] = self._processing_rows(snapshot)
        return [
            str(item["acquisition_id"])
            if item.get("acquisition_id")
            and sum(other.get("acquisition_id") == item["acquisition_id"] for other in rows) == 1
            else str(item.get("material_id") or f"{item.get('run_id')}:{item.get('group_id')}")
            for item in rows
        ]


def _centered(line: Text, columns: int) -> Text:
    result: Text = Text(" " * max((columns - line.cell_len) // 2, 0))
    result.append_text(line)
    return result


def _rows(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _safe_text(value: object) -> str:
    message: str = sanitize_event_message(str(value)) or ""
    return _CLIENT_PROBLEMS.get(message, message)


def _download_toggle(item: Mapping[str, object]) -> tuple[str, str] | None:
    if item.get("acquisition_state") == "pending_send" or item.get("state") in {
        "metaDL",
        "forcedMetaDL",
        "error",
        "missingFiles",
    }:
        return None
    if item.get("state") in {"pausedDL", "stoppedDL", "pausedUP", "stoppedUP"}:
        return "resume", "wznów"
    return "stop", "wstrzymaj"


def _cancel_target(item: Mapping[str, object]) -> tuple[str, str] | None:
    if item.get("stage") == "download" and item.get("info_hash"):
        return "info_hash", str(item["info_hash"])
    if (item.get("stage") == "processing" or item.get("admitted_processing")) and item.get("run_id"):
        return "run_id", str(item["run_id"])
    return None


def _cancel_command(target: tuple[str, str]) -> tuple[str, Mapping[str, object]]:
    if target[0] == "info_hash":
        return "transfer", {"info_hash": target[1], "action": "cancel"}
    return "cancel", {"run_id": target[1]}


def _moved(selected: int, key: str, count: int, page: int) -> int:
    if key in {"home", "end"}:
        return 0 if key == "home" else count - 1
    if key in {"up", "down"}:
        return (selected + (-1 if key == "up" else 1)) % count
    return min(max(selected + (-page if key == "pageup" else page), 0), count - 1)


def _relocation_problems(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in _rows(snapshot.get("relocations")) if item.get("problem")]


def _library_rows(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    deleted: set[str] = {
        str(item["set_id"])
        for item in _rows(snapshot.get("deletions"))
        if not item.get("restored")
        and (item.get("active") or (item.get("total") and item.get("recycled") == item.get("total")))
    }
    return os_sorted(
        [
            *_rows(snapshot.get("library")),
            *(item for item in _rows(snapshot.get("library_problems")) if str(item.get("set_id")) not in deleted),
        ],
        key=lambda item: (str(item.get("name", "")), _library_row_id(item)),
    )


def _library_row_id(item: Mapping[str, object]) -> str:
    return str(item.get("set_id", ""))


def _library_detail_entries(details: LibrarySet) -> list[tuple[str | Text, bool | None]]:
    entries: list[tuple[str | Text, bool | None]] = [(_safe_text(details.name), None)]
    if details.target is None:
        entries.append(("Cel nierozstrzygnięty · regeneracja wymaga wyboru", None))
    if details.problem == "library_ownership_unknown":
        entries.append((_LIBRARY_PROBLEMS[details.problem], None))
    if details.provisional_timing:
        entries.append(("Czasy robocze · skrypt lektora bez synchronizacji z nagraniem", None))
    entries.extend(
        (
            f"{_safe_text(item.path)} · {item.format} · {_FILE_ROLES[item.role]} · "
            + ("brak" if item.identity is None else f"{item.identity.size:,} B")
            + (" · główny" if item.path == details.main_result else ""),
            None,
        )
        for item in details.files
    )
    return entries


def _open_episode(session: ResidentSession, set_id: str, *, show_folder: bool = False) -> None:
    path: Path = session.library_result(set_id, playback=False) if show_folder else session.library_result(set_id)
    _open_path(path, show_folder=show_folder)
