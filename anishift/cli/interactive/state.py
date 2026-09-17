"""Resident state and actions in the existing terminal renderer."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final

from natsort import os_sorted
from rich.console import Console
from rich.text import Text

from anishift.application import (
    DeletionPreview,
    HistoryEvent,
    LibrarySet,
    PendingDeletion,
    RefusalReason,
    RetryProposal,
    RunProgressSnapshot,
    Subscription,
    decode_view,
)
from anishift.application.events import RunEvent, sanitize_event_message
from anishift.cli.interactive.anime import AnimeController, AnimeResult
from anishift.cli.interactive.menu import (
    append_wrapped_row,
    fit_entries,
    left_padding,
    visible_window,
    with_footer,
    wrap_entries,
)
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.subscriptions import SubscriptionDraft
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError
from anishift.platform.local_control import ControlError
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
}
"""Operation boundary labels shown once per logical material."""

_HISTORY_PROBLEMS: Final[dict[str, str]] = {
    "history_corrupt": "Historia niedostępna · uszkodzony zapis; przetwarzanie działa dalej",
    "history_unavailable": "Historia niedostępna · błąd odczytu lub zapisu; przetwarzanie działa dalej",
}
"""Persistent observation warnings distinct from an empty history."""

_TABS: Final[tuple[str, ...]] = ("Anime", "Subskrypcje", "Przetwarzanie", "Biblioteka")
"""Views of the same resident snapshot, switched without network requests."""

_MINIMUM_HEADER_ROWS: Final[int] = 12
"""Minimum height retaining the heading as well as tabs and actions."""

_TRANSFER_LABELS: Final[dict[str, str]] = {
    "downloading": "pobieranie",
    "forcedDL": "pobieranie",
    "stalledDL": "czeka na źródła",
    "metaDL": "szuka metadanych",
    "forcedMetaDL": "szuka metadanych",
    "queuedDL": "w kolejce",
    "pausedDL": "wstrzymane",
    "stoppedDL": "wstrzymane",
    "checkingDL": "sprawdzanie",
    "checkingUP": "sprawdzanie",
    "checkingResumeData": "sprawdzanie",
    "moving": "przenoszenie",
    "uploading": "pobrane",
    "stalledUP": "pobrane",
    "forcedUP": "pobrane",
    "queuedUP": "pobrane",
    "pausedUP": "pobrane",
    "stoppedUP": "pobrane",
    "missingFiles": "brakuje plików",
    "error": "błąd klienta",
}
"""User-facing download states returned by qBittorrent."""

_ATTENTION_LABEL: Final[str] = "wymaga uwagi"
"""Label of a release that recorded a problem, whether or not the client still reports its transfer."""

_UNCONFIRMED_LABEL: Final[str] = "brak potwierdzenia klienta"
"""Label of an ordered release the torrent client does not report at all."""

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
    }
)
"""Polish sentence the panel shows for every refusal cause the resident names."""

_UNKNOWN_REFUSAL: Final[str] = "Proces w tle odrzucił polecenie"
"""Polish sentence for a refusal this version cannot name any more precisely."""

_SUBSCRIPTION_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "subscription_season_ambiguous": "Nie można jednoznacznie rozpoznać sezonu · wybierz go z katalogu AniList",
        "subscription_source_available": "Źródło jest dostępne · użyj Ręcznego, aby je przetworzyć",
    }
)
"""Polish subscription refusals selected by machine reason rather than application prose."""

_LIBRARY_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "library_set_missing": "Tego zestawu nie ma już w bibliotece",
        "library_result_missing": "Brakuje potwierdzonego głównego wyniku",
        "library_result_changed": "Główny wynik istnieje, ale jest zmieniony lub niepotwierdzony",
        "library_ownership_unknown": "Pochodzenie zestawu wymaga rozstrzygnięcia przed usunięciem",
        "library_source_held": "Źródło czeka na zwolnienie przez torrent",
        "library_scope_changed": "Zestaw zmienił się · przygotuj nowe potwierdzenie",
        "library_source_busy": "Plik jest nadal zapisywany lub niedostępny",
        "library_deleting": "Trwa przenoszenie tego zestawu do Kosza",
        "recycle_unsupported": "Kosz jest niedostępny dla tego środowiska",
        "recycle_unavailable": "Nie udało się potwierdzić dostępności operacji Kosza",
        "recycle_refused": "System odmówił przeniesienia pliku do Kosza",
        "recycle_timeout": "Upłynął limit operacji · jej wynik pozostaje niepewny",
        "recycle_cleanup_timeout": "Upłynął limit zamykania operacji · jej wynik pozostaje niepewny",
        "recycle_interrupted": "Operacja została przerwana · jej wynik pozostaje niepewny",
        "recycle_invalid_evidence": "Brak poprawnego potwierdzenia operacji Kosza",
        "recycle_incomplete": "System nie potwierdził pełnego wyniku operacji",
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

_DELETION_STATUSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "inflight": "w toku",
        "recycled": "w Koszu",
        "refused": "odmowa",
        "uncertain": "wynik niepewny",
        "pending": "nie podjęto",
    }
)
"""File outcome labels keyed by durable deletion status, never native error prose."""


def refusal_text(problem: BaseException) -> str:
    """Return the Polish sentence for a refusal, degrading to its sanitized message."""
    reason: str = problem.reason if isinstance(problem, ControlError) else ""
    if reason in _RETRY_PROBLEMS:
        return _RETRY_PROBLEMS[reason]
    if reason in _SUBSCRIPTION_PROBLEMS and isinstance(problem, ControlError):
        numbers: object = problem.context.details.get("episodes")
        suffix: str = ""
        if isinstance(numbers, list) and all(isinstance(number, str) for number in numbers):
            suffix = f" · odcinki: {_safe_text(', '.join(numbers))}"
        return _SUBSCRIPTION_PROBLEMS[reason] + suffix
    return _REFUSAL_TEXTS.get(reason) or _LIBRARY_PROBLEMS.get(reason) or _safe_text(str(problem)) or _UNKNOWN_REFUSAL


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

    def __init__(self, session: ResidentSession, invalidate: Callable[[], None]) -> None:
        self._parent: ResidentSession = session
        self._session: ResidentSession | None = None
        self._invalidate: Callable[[], None] = invalidate
        self._lock: threading.RLock = threading.RLock()
        self._stop: threading.Event = threading.Event()
        self._finished: bool = False
        self._open_requested: threading.Event = threading.Event()
        self._notification_notice: str | None = None
        self._snapshot: Mapping[str, object] = {}
        self._subscriptions: list[Mapping[str, object]] = []
        self._runs: dict[str, tuple[str, RichRunProgress]] = {}
        self._tab: int = _Tab.PROGRESS
        self._selected: int = 0
        self._positions: dict[int, int] = {}
        self._offsets: dict[int, int] = {}
        self._follow_cursor: dict[int, bool] = {}
        self._anime: AnimeController | None = None
        self._anime_return: int = _Tab.ANIME
        self._draft: SubscriptionDraft | None = None
        self._connected: bool = False
        self._busy: bool = False
        self._notice: str = "Łączenie z procesem w tle…"
        self._state_version: int = 0
        self._notice_version: int = -1
        self._details: LibrarySet | None = None
        self._operation_details: PendingDeletion | None = None
        self._operation_name: str = ""
        self._detail_selection: int = 0
        self._deletion: DeletionPreview | None = None
        self._deletion_session: ResidentSession | None = None
        self._delete_confirmed: bool = False
        self._view_generation: int = 0
        self._history_open: bool = False
        self._history_items: tuple[HistoryEvent, ...] = ()
        self._history_query: str = ""
        self._history_problem: str = ""
        self._history_input: TextInput | None = None
        self._active_position: int = 0
        self._retry: RetryProposal | None = None
        self._manual_retry: RetryProposal | None = None
        self._thread: threading.Thread = threading.Thread(target=self._watch, name="anishift-state", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Detach this panel without stopping resident work."""
        self._stop.set()
        if self._anime is not None:
            self._anime.cancel()
        with self._lock:
            self._view_generation += 1
            self._cancel_deletion()
        session: ResidentSession | None = self._session
        if session is not None:
            session.close()

    def finished(self) -> bool:
        """Answer whether the resident announced its end, so this view has to close with it."""
        return self._finished

    def take_open_request(self) -> bool:
        """Consume a tray request on the panel's event loop."""
        requested: bool = self._open_requested.is_set()
        self._open_requested.clear()
        return requested

    def take_manual_retry(self) -> RetryProposal | None:
        """Transfer a confirmed local proposal to the existing Manual controller."""
        with self._lock:
            proposal: RetryProposal | None = self._manual_retry
            self._manual_retry = None
            return proposal

    def take_notification_notice(self) -> str | None:
        """Consume desktop refusal feedback on the renderer thread, including a newly attached panel."""
        with self._lock:
            notice: str | None = self._notification_notice
            self._notification_notice = None
            return notice

    def show_processing(self) -> None:
        """Select current processing after the user starts a run."""
        with self._lock:
            self._view_generation += 1
            self._cancel_deletion()
            self._details = None
            self._operation_details = None
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

    def handle_key(self, key: str) -> StateResult:
        """Navigate the shared list or submit one explicit action."""
        with self._lock:
            if self._history_input is not None:
                self._history_input_key(key)
                return StateResult.CONTINUE
            if self._retry is not None:
                return self._retry_key(key)
            if self._tab == _Tab.ANIME and self._anime is not None:
                return self._anime_key(key)
            if self._draft is not None:
                self._draft_key(key)
                return StateResult.CONTINUE
            if self._modal_key(key) or self._history_navigation(key):
                return StateResult.CONTINUE
            return self._list_key(key)

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
        if key in {"tab", "backtab", "left", "right"}:
            self._view_generation += 1
            self._details = None
            self._switch_tab((self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS))
            self._notify("")
            if self._tab == _Tab.FILES:
                self._work(lambda session: session.library())
        elif key in {"up", "down", "home", "end"}:
            self._follow_cursor[self._tab] = True
            count: int = max(len(self._entries(120)), 1)
            if key in {"home", "end"}:
                self._selected = 0 if key == "home" else count - 1
            else:
                self._selected = (self._selected + (-1 if key == "up" else 1)) % count
        elif key in {"space", "enter"} and self._tab == _Tab.SUBSCRIPTIONS:
            return self._subscription_key(key)
        elif self._selected_deletion() is not None and key.casefold() in {"enter", "delete", "text:p", "text:d"}:
            self._deletion_action(key.removeprefix("text:").casefold())
        elif key == "enter" and self._tab == _Tab.FILES:
            self._file_action("open")
        elif key == "delete" and self._tab == _Tab.FILES:
            self._file_action("delete")
        elif key.startswith("text:"):
            return self._action_key(key.removeprefix("text:").casefold())
        self._invalidate()
        return StateResult.CONTINUE

    def _modal_key(self, key: str) -> bool:
        if self._deletion is not None:
            self._deletion_key(key)
            return True
        if self._operation_details is not None:
            if key in {"escape", "interrupt", "backspace"}:
                self._view_generation += 1
                self._operation_details = None
                self._selected = self._detail_selection
            elif key.casefold() in {"text:p", "delete"}:
                self._deletion_action(key.removeprefix("text:").casefold())
            elif key in {"up", "down", "home", "end"}:
                self._follow_cursor[self._viewport()] = True
                count: int = max(len(self._entries(120)), 1)
                self._selected = (self._selected + (-1 if key == "up" else 1)) % count
                if key in {"home", "end"}:
                    self._selected = 0 if key == "home" else count - 1
            self._invalidate()
            return True
        if self._details is not None:
            self._details_key(key)
            return True
        return False

    def _subscription_key(self, key: str) -> StateResult:
        if key == "space":
            return self._action_key("w")
        self._open_subscription()
        return StateResult.CONTINUE

    def _details_key(self, key: str) -> None:
        if key in {"escape", "interrupt", "backspace"}:
            self._view_generation += 1
            self._details = None
            self._selected = self._detail_selection
        elif key == "delete" and self._details is not None:
            set_id: str = self._details.set_id
            generation: int = self._view_generation
            self._work(lambda session: self._show_deletion(session, set_id, generation))
        elif key in {"up", "down", "home", "end"}:
            self._follow_cursor[self._viewport()] = True
            count: int = max(len(self._entries(120)), 1)
            self._selected = (self._selected + (-1 if key == "up" else 1)) % count
            if key in {"home", "end"}:
                self._selected = 0 if key == "home" else count - 1
        self._invalidate()

    def attach_anime(self, controller: AnimeController) -> None:
        """Reuse the session's one search controller inside the Anime tab."""
        self._anime = controller

    def _switch_tab(self, tab: int) -> None:
        self._view_generation += 1
        if self._tab == _Tab.ANIME and self._anime is not None:
            self._anime.cancel()
        self._positions[self._tab] = self._selected
        self._tab = tab
        self._selected = self._positions.get(tab, 0)

    def _viewport(self) -> int:
        if self._draft is not None:
            return len(_TABS)
        if self._details is not None or self._operation_details is not None:
            return len(_TABS) + 1
        return self._tab

    def scroll(self, direction: int) -> None:
        """Move the visible list without changing its selected identity."""
        with self._lock:
            viewport: int = self._viewport()
            if self._tab == _Tab.ANIME or self._deletion is not None:
                return
            self._offsets[viewport] = max(self._offsets.get(viewport, 0) + direction * 3, 0)
            self._follow_cursor[viewport] = False
        self._invalidate()

    def poll(self) -> None:
        """Show an admitted download only while its initiating view remains active."""
        with self._lock:
            if self._anime is not None and self._anime.take_downloaded() and self._tab == _Tab.ANIME:
                self.show_processing()

    def _anime_key(self, key: str) -> StateResult:
        anime: AnimeController | None = self._anime
        if anime is None:
            return StateResult.CONTINUE
        if key in {"tab", "backtab"} or (key in {"left", "right"} and not anime.editing):
            self._switch_tab((self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS))
            self._invalidate()
            return StateResult.CONTINUE
        result: AnimeResult = anime.handle_key(key)
        if result is AnimeResult.SUBSCRIBE:
            self._draft = anime.take_draft()
            self._follow_cursor[len(_TABS)] = True
            self._switch_tab(_Tab.SUBSCRIPTIONS)
        elif result is AnimeResult.HOME:
            if self._anime_return == _Tab.SUBSCRIPTIONS:
                self._switch_tab(_Tab.SUBSCRIPTIONS)
                self._anime_return = _Tab.ANIME
            else:
                return StateResult.HOME
        self._invalidate()
        return StateResult.CONTINUE

    def _open_subscription(self) -> None:
        if not self._subscriptions:
            return
        identifier: str = str(self._subscriptions[min(self._selected, len(self._subscriptions) - 1)]["subscription_id"])
        generation: int = self._view_generation

        def load(session: ResidentSession) -> None:
            payload: Mapping[str, object] = session.command("subscription_get", {"subscription_id": identifier})
            subscription: Subscription = decode_view(Subscription, payload)
            work_states: object = payload.get("work_states")
            with self._lock:
                if generation == self._view_generation and not self._stop.is_set():
                    self._draft = SubscriptionDraft.from_subscription(
                        subscription, work_states if isinstance(work_states, Mapping) else None
                    )
                    self._follow_cursor[len(_TABS)] = True

        self._work(load)

    def _draft_key(self, key: str) -> None:
        draft: SubscriptionDraft | None = self._draft
        if draft is None:
            return
        if key in {"escape", "interrupt"}:
            self._draft = None
            self._view_generation += 1
        elif key.casefold() == "text:p" and draft.subscription is not None:
            repeated: tuple[Decimal, ...] = tuple(sorted(draft.selected & draft.completed))
            if not repeated and draft.cursor < len(draft.numbers):
                repeated = (draft.numbers[draft.cursor],)
            if repeated:
                identifier: str = draft.subscription.subscription_id
                self._prepare_retry(lambda session: session.subscription_retry_proposal(identifier, repeated))
        elif key == "enter":
            repeating: tuple[Decimal, ...] = tuple(sorted(draft.selected & draft.completed))
            if repeating:
                self._notify("Ukończone numery wymagają jawnego P Ponów")
            else:
                self._apply_draft(draft)
        else:
            self._follow_cursor[self._viewport()] = True
            draft.handle_key(key)
        self._invalidate()

    def _apply_draft(self, draft: SubscriptionDraft) -> None:
        generation: int = self._view_generation
        selected: tuple[Decimal, ...] = tuple(sorted(draft.selected))
        future_from: Decimal | None = draft.future_from

        def apply(session: ResidentSession) -> None:
            if draft.order is not None:
                session.follow(draft.order, selected=selected, future_from=future_from)
            elif draft.subscription is not None:
                session.set_range(draft.subscription.subscription_id, selected=selected, future_from=future_from)
            with self._lock:
                if generation == self._view_generation and self._draft is draft:
                    self._draft = None

        self._work(apply)

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
        elif key == "f" and self._tab == _Tab.SUBSCRIPTIONS:
            self._command("subscriptions_check")
        elif key == "d" and self._tab == _Tab.SUBSCRIPTIONS:
            self._anime_return = _Tab.SUBSCRIPTIONS
            self._switch_tab(_Tab.ANIME)
        elif self._tab == _Tab.SUBSCRIPTIONS and self._subscriptions and key in {"w", "x"}:
            item: Mapping[str, object] = self._subscriptions[min(self._selected, len(self._subscriptions) - 1)]
            kind: str = (
                "subscription_remove"
                if key == "x"
                else ("subscription_disable" if item.get("enabled") else "subscription_enable")
            )
            self._command(kind, {"subscription_id": item["subscription_id"]})
        elif self._tab == _Tab.PROGRESS and not self._history_open:
            self._processing_action(key)
        elif self._tab == _Tab.FILES:
            self._file_action(key)
        self._invalidate()
        return StateResult.CONTINUE

    def _processing_action(self, key: str) -> None:
        materials: list[Mapping[str, object]] = _rows(self._snapshot.get("materials"))
        if self._selected >= len(materials):
            if key == "p" and _relocation_problems(self._snapshot):
                self._command("ready_retry")
            return
        item: Mapping[str, object] = materials[self._selected]
        if item.get("stage") == "download" and key in {"p", "w", "x"}:
            self._command(
                "transfer", {"info_hash": item["info_hash"], "action": {"p": "stop", "w": "resume", "x": "cancel"}[key]}
            )
        elif item.get("run_id") and key == "c" and item.get("active"):
            self._command("cancel", {"run_id": item["run_id"]})
        elif item.get("run_id") and key == "p" and item.get("state") in {"failed", "partial", "paused", "cancelled"}:
            identifier: str = str(item["group_id"])
            self._prepare_retry(lambda session: session.retry_proposal(identifier))

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
            success: str = (
                f"Przyjęto ponowienie: {', '.join(f'{number.normalize():f}' for number in proposal.episodes)}"
                " · Enter stosuje pozostały zakres"
                if proposal.action == "subscription"
                else "Polecenie przyjęte"
            )
            self._work(lambda session: self._execute_repeat(session, proposal, generation), success=success)
        self._invalidate()
        return StateResult.CONTINUE

    def _execute_repeat(self, session: ResidentSession, proposal: RetryProposal, generation: int) -> None:
        if proposal.action == "reacquire" and proposal.operation_id is not None:
            session.reacquire(proposal.operation_id)
        elif proposal.action == "subscription" and proposal.subscription_id is not None:
            subscription: Subscription = session.repeat(proposal.subscription_id, proposal.episodes)
            with self._lock:
                if generation != self._view_generation or self._stop.is_set():
                    return
                draft: SubscriptionDraft | None = self._draft
                if (
                    draft is not None
                    and draft.subscription is not None
                    and draft.subscription.subscription_id == subscription.subscription_id
                ):
                    draft.subscription = subscription
                    draft.completed = draft.completed.difference(proposal.episodes)
                    draft.states.update(
                        {
                            item.number: item.state.value
                            for item in subscription.episodes
                            if item.number in proposal.episodes
                        }
                    )
        else:
            msg = "Nieaktualne ponowienie; wybierz materiał jeszcze raz"
            raise ValueError(msg)

    def _file_action(self, key: str) -> None:
        if key == "p":
            if self._selected_deletion() is not None:
                self._deletion_action(key)
            elif _relocation_problems(self._snapshot):
                self._command("ready_retry")
            return
        library: list[Mapping[str, object]] = _library_rows(self._snapshot)
        if key not in {"open", "f", "d", "delete"} or self._selected >= len(library):
            return
        if "operation_id" in library[self._selected]:
            self._deletion_action(key)
            return
        set_id: str = str(library[self._selected]["set_id"])
        if key == "delete":
            generation: int = self._view_generation
            self._work(lambda session: self._show_deletion(session, set_id, generation))
            return
        if key == "d":
            generation = self._view_generation
            self._work(lambda session: self._show_details(session, set_id, generation))
            return
        self._work(lambda session: _open_episode(session, set_id, show_folder=key == "f"))

    def _selected_deletion(self) -> Mapping[str, object] | None:
        if self._tab == _Tab.PROGRESS and self._history_open:
            return None
        operations: list[Mapping[str, object]] = _deletion_rows(self._snapshot)
        if self._operation_details is not None:
            return next(
                (item for item in operations if item["operation_id"] == self._operation_details.operation_id), None
            )
        if self._details is not None:
            return None
        if self._tab == _Tab.FILES:
            rows: list[Mapping[str, object]] = _library_rows(self._snapshot)
            return (
                rows[self._selected] if self._selected < len(rows) and "operation_id" in rows[self._selected] else None
            )
        position: int = self._selected - len(self._processing_entries(120))
        return operations[position] if self._tab == _Tab.PROGRESS and 0 <= position < len(operations) else None

    def _deletion_action(self, key: str) -> None:
        operation: Mapping[str, object] | None = self._selected_deletion()
        if operation is None:
            return
        generation: int = self._view_generation
        if key in {"enter", "d"}:
            self._work(lambda session: self._show_operation_details(session, operation, generation))
        elif key == "p" and operation.get("retryable") and not operation.get("active"):
            self._command("deletion_retry", {"operation_id": operation["operation_id"]})
        elif key == "delete" and operation.get("can_confirm") and not operation.get("active"):
            self._work(lambda session: self._show_deletion(session, str(operation["set_id"]), generation))

    def _show_operation_details(
        self, session: ResidentSession, operation: Mapping[str, object], generation: int
    ) -> None:
        details: PendingDeletion = decode_view(
            PendingDeletion, session.command("deletion_get", {"operation_id": operation["operation_id"]})
        )
        with self._lock:
            if self._stop.is_set() or generation != self._view_generation:
                return
            self._detail_selection = self._selected
            self._selected = 0
            self._follow_cursor[len(_TABS) + 1] = True
            self._operation_name = str(operation["name"])
            self._operation_details = details

    def _show_deletion(self, session: ResidentSession, set_id: str, generation: int) -> None:
        preview: DeletionPreview = session.preview_deletion(set_id)
        with self._lock:
            if self._stop.is_set() or generation != self._view_generation:
                return
            self._deletion = preview
            self._deletion_session = session
            self._delete_confirmed = False

    def _cancel_deletion(self) -> None:
        session: ResidentSession | None = self._deletion_session
        self._deletion_session = None
        self._deletion = None
        self._delete_confirmed = False
        if session is not None:
            session.close()

    def _deletion_key(self, key: str) -> None:
        if key in {"escape", "interrupt", "backspace"}:
            self._cancel_deletion()
        elif key in {"left", "right", "tab", "backtab", "up", "down"}:
            self._delete_confirmed = not self._delete_confirmed
        elif key == "enter" and not self._busy:
            if not self._delete_confirmed:
                self._cancel_deletion()
            else:
                self._confirm_deletion()
        self._invalidate()

    def _confirm_deletion(self) -> None:
        preview: DeletionPreview | None = self._deletion
        session: ResidentSession | None = self._deletion_session
        if preview is None or session is None:
            return
        self._deletion = None
        self._deletion_session = None

        def submit(_unused: ResidentSession) -> None:
            try:
                session.delete_set(preview)
            finally:
                session.close()

        self._work(submit)

    def _show_details(self, session: ResidentSession, set_id: str, generation: int) -> None:
        details: LibrarySet = session.library_details(set_id)
        with self._lock:
            if self._tab != _Tab.FILES or generation != self._view_generation or self._stop.is_set():
                return
            self._detail_selection = self._selected
            self._selected = 0
            self._follow_cursor[len(_TABS) + 1] = True
            self._details = details

    def _command(self, kind: str, payload: Mapping[str, object] | None = None) -> None:
        self._work(lambda session: session.command(kind, payload))

    def _work(self, action: Callable[[ResidentSession], object], *, success: str = "Polecenie przyjęte") -> None:
        if self._busy:
            self._notify("Poprzednia czynność jeszcze trwa; możesz przejść do ustawień")
            return
        self._busy = True
        self._notify("Wykonywanie polecenia…")
        threading.Thread(
            target=self._perform, args=(action, success), name="anishift-state-action", daemon=True
        ).start()

    def _perform(self, action: Callable[[ResidentSession], object], success: str = "Polecenie przyjęte") -> None:
        session: ResidentSession | None = None
        try:
            session = self._parent.new_session()
            action(session)
            with self._lock:
                self._notify(success)
        except (AniShiftError, ControlError, OSError, ValueError) as error:
            with self._lock:
                self._notify(refusal_text(error))
        finally:
            if session is not None and session is not self._deletion_session:
                session.close()
            with self._lock:
                self._busy = False
            self._invalidate()

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                session: ResidentSession = self._parent.new_session()
                self._session = session
                session.command("panel_attach")
                with self._lock:
                    self._runs.clear()
                for frame in session.observe():
                    if self._stop.is_set():
                        break
                    self._receive(session, frame)
            except (AniShiftError, ControlError, OSError, ValueError, TypeError) as error:
                with self._lock:
                    self._notify(refusal_text(error))
            finally:
                if self._session is not None:
                    self._session.close()
                with self._lock:
                    self._connected = False
                self._invalidate()
            if self._stop.wait(_RECONNECT_S):
                break

    def _remember_notification_notice(self, payload: Mapping[str, object]) -> None:
        notice: object = payload.get("notification_problem")
        if notice and notice != self._snapshot.get("notification_problem"):
            self._notification_notice = _safe_text(notice)

    def _receive(self, session: ResidentSession, frame: Mapping[str, object]) -> None:
        payload: object = frame.get("payload")
        if frame.get("event") == "panel_open":
            with self._lock:
                notice: object = payload.get("notification_problem") if isinstance(payload, Mapping) else None
                self._notification_notice = _safe_text(notice) if notice else None
            self._open_requested.set()
            self._invalidate()
            return
        if not isinstance(payload, Mapping):
            return
        if frame.get("event") == "state_changed":
            subscriptions: list[Mapping[str, object]] = _rows(
                session.command("subscriptions_list").get("subscriptions")
            )
            with self._lock:
                previous_operation_details: PendingDeletion | None = self._operation_details
            self._restore_progress(session, payload)
            operation_details: PendingDeletion | None = (
                decode_view(
                    PendingDeletion,
                    session.command("deletion_get", {"operation_id": previous_operation_details.operation_id}),
                )
                if previous_operation_details is not None
                else None
            )
            with self._lock:
                previous_details: LibrarySet | None = self._details
            details: LibrarySet | None = self._refresh_details(session, previous_details)
            with self._lock:
                self._remember_notification_notice(payload)
                if payload != self._snapshot:
                    self._state_version += 1
                self._preserve_tab_selection(_Tab.SUBSCRIPTIONS, self._subscriptions, subscriptions, "subscription_id")
                self._preserve_processing_selection(payload)
                self._preserve_library_selection(payload)
                self._snapshot = payload
                if self._operation_details is previous_operation_details:
                    self._operation_details = operation_details
                if self._details is previous_details:
                    self._details = details
                    if previous_details is not None and details is None:
                        self._selected = self._detail_selection
                self._subscriptions = subscriptions
                self._refresh_draft_work()
                self._connected = True
                if self._notice_version < self._state_version:
                    self._notice = ""
                if payload.get("shutting_down"):
                    self._finished = True
                    self._stop.set()
        elif frame.get("event") == "run_event":
            event: RunEvent = decode_view(RunEvent, payload)
            with self._lock:
                progress: tuple[str, RichRunProgress] | None = self._runs.get(event.run_id)
            if progress is None:
                self._restore_progress(session, session.command("status"))
                progress = self._runs.get(event.run_id)
            if progress is not None:
                progress[1].emit(event)
        self._invalidate()

    def _refresh_draft_work(self) -> None:
        draft: SubscriptionDraft | None = self._draft
        if draft is None or draft.subscription is None:
            return
        item: Mapping[str, object] = next(
            (item for item in self._subscriptions if item["subscription_id"] == draft.subscription.subscription_id), {}
        )
        states: object = item.get("work_states")
        if isinstance(states, Mapping):
            draft.refresh_work_states(states)

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

    def _preserve_processing_selection(self, payload: Mapping[str, object]) -> None:
        old: list[str] = _processing_row_ids(self._snapshot)
        new: list[str] = _processing_row_ids(payload)
        position: int = self._selected if self._operation_details is None else self._detail_selection
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
        if self._operation_details is None:
            self._selected = position
        else:
            self._detail_selection = position

    def _preserve_library_selection(self, payload: Mapping[str, object]) -> None:
        old: list[Mapping[str, object]] = _library_rows(self._snapshot)
        new: list[Mapping[str, object]] = _library_rows(payload)
        position: int = (
            self._selected if self._details is None and self._operation_details is None else self._detail_selection
        )
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
        if self._details is None and self._operation_details is None:
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
            if existing is not None and existing[0] == item.get("preview_id"):
                continue
            snapshot: RunProgressSnapshot = decode_view(
                RunProgressSnapshot, session.command("run_progress", {"run_id": run_id})
            )
            restored: RichRunProgress = RichRunProgress.from_snapshot(snapshot, self._invalidate)
            with self._lock:
                self._runs[run_id] = (snapshot.preview.preview_id, restored)

    def render(self, columns: int, rows: int) -> Text:
        """Render tabs and the same centered selectable list used by Manual."""
        with self._lock:
            if self._deletion is not None and rows < _MINIMUM_HEADER_ROWS:
                return self._compact_deletion(columns, rows)
            content: Text = Text()
            if rows >= _MINIMUM_HEADER_ROWS:
                content.append(" " * max((columns - 5) // 2, 0) + "PANEL\n\n", style="white_bold")
            tabs: Text = self._tabs(columns)
            content.append(" " * max((columns - tabs.cell_len) // 2, 0))
            content.append_text(tabs)
            content.append("\n")
            heading_rows: int = content.plain.count("\n")
            if self._tab == _Tab.ANIME and self._anime is not None:
                status: str = self._global_status()
                status_rows: int = len(Text(status).wrap(Console(width=max(columns - 2, 1)), max(columns - 2, 1)))
                content.append_text(self._anime.render(columns, max(rows - heading_rows - status_rows, 1)))
                return with_footer(content, (status,), columns, rows)
            entries: list[tuple[str | Text, bool | None]] = (
                [(label, checked) for label, checked in self._draft.entries()]
                if self._draft is not None and self._retry is None
                else self._entries(max(columns - 8, 1))
            )
            selected: int = (
                self._draft.cursor
                if self._draft is not None and self._retry is None
                else min(self._selected, max(len(entries) - 1, 0))
            )
            if self._deletion is not None:
                selected = 0
            if self._deletion is None and self._draft is None and self._retry is None:
                self._selected = selected
            labels: tuple[str, ...] = fit_entries(
                tuple(label.plain if isinstance(label, Text) else label for label, _ in entries), columns
            )
            console: Console = Console(width=max(columns - 2, 1))
            footer: list[Text] = [
                line
                for hint in self._view_footer()
                if hint
                for line in (hint if isinstance(hint, Text) else Text(hint, style="gray")).wrap(
                    console, max(columns - 2, 1)
                )
            ]
            footer = footer[: max(rows - heading_rows - 2, 1)]
            wrapped: tuple[tuple[str | Text, ...], ...] = wrap_entries(tuple(label for label, _ in entries), columns)
            remaining: int = max(rows - 1 - len(footer) - heading_rows, 1)
            start, end = visible_window(len(labels), selected, remaining + 7, heights=tuple(map(len, wrapped)))
            viewport: int = self._viewport()
            if self._follow_cursor.get(viewport, True) or self._deletion is not None:
                self._offsets[viewport] = start
            else:
                start = min(self._offsets.get(viewport, 0), max(len(entries) - 1, 0))
                end = len(entries)
            left: int = left_padding(columns, labels)
            for index in range(start, end):
                if remaining <= 0:
                    break
                checked: bool | None = entries[index][1]
                marker: str = "" if checked is None else ("● " if checked else "○ ")
                lines: tuple[str | Text, ...] = wrapped[index][:remaining]
                append_wrapped_row(content, left, lines, index == selected, marker)
                remaining -= len(lines)
            if not entries:
                empty: str = "Brak zadań" if self._tab == _Tab.PROGRESS else "Brak pozycji"
                if self._tab == _Tab.PROGRESS and self._history_open and self._history_problem:
                    empty = "Historia niedostępna"
                content.append(" " * max((columns - len(empty)) // 2, 0) + empty + "\n", style="gray")
            return with_footer(content, footer, columns, rows)

    def _compact_deletion(self, columns: int, rows: int) -> Text:
        preview: DeletionPreview | None = self._deletion
        if preview is None:
            return Text()
        title: Text = Text(f"Kosz · {len(preview.files)} plików · {_safe_text(preview.name)}", style="white_bold")
        title.truncate(max(columns - 2, 1), overflow="ellipsis")
        selected: str = "[Przenieś do Kosza]" if self._delete_confirmed else "[Anuluj]"
        return with_footer(title, (selected, "←→ wybierz · Enter · Esc anuluj"), columns, rows)

    def _tabs(self, columns: int = 120) -> Text:
        tabs: Text = Text()
        for index, name in enumerate(_TABS):
            if index:
                tabs.append(" · ", style="gray")
            tabs.append(name, style="brand_accent" if self._tab == index else "gray")
        if tabs.cell_len > max(columns - 2, 1):
            return Text(f"← {_TABS[self._tab]} ({self._tab + 1}/4) →", style="brand_accent")
        return tabs

    def _view_footer(self) -> list[str | Text]:
        if self._retry is not None:
            return ["Enter przygotuj · Esc anuluj", self._notice, self._global_status()]
        if self._tab == _Tab.PROGRESS and self._history_open:
            if self._history_input is not None:
                return [
                    self._history_input.render(100),
                    "Enter szukaj · Esc anuluj",
                    self._history_problem,
                    self._global_status(),
                ]
            return [
                "Historia · ostatnie 30 dni",
                "Enter otwórz · P Ponów · S szukaj · Esc bieżące",
                self._history_problem,
                self._notice,
                self._global_status(),
            ]
        if self._draft is not None:
            identifier: str | None = (
                None if self._draft.subscription is None else self._draft.subscription.subscription_id
            )
            subscription: Mapping[str, object] = next(
                (item for item in self._subscriptions if item.get("subscription_id") == identifier), {}
            )
            return [
                "Space wybór · Enter zastosuj · Esc odrzuć · A zwykłe · P Ponów",
                _subscription_term(subscription),
                self._draft.name,
                self._notice,
                self._global_status(),
            ]
        return self._footer()

    def _footer(self) -> list[str | Text]:
        result: list[str | Text] = []
        if self._deletion is not None:
            return [
                "Anuluj   [Przenieś do Kosza]" if self._delete_confirmed else "[Anuluj]   Przenieś do Kosza",
                f"{len(self._deletion.files)} plików · {self._deletion.total_size:,} B · cały zestaw",
                "←→ wybierz · Enter zatwierdź · Esc anuluj",
            ]
        operation: Mapping[str, object] | None = self._selected_deletion()
        if operation is not None:
            result.append(_deletion_label(operation))
            actions: str = "D szczegóły"
            if operation.get("retryable") and not operation.get("active"):
                actions += " · P ponów pozostałe pliki"
            elif operation.get("can_confirm") and not operation.get("active"):
                actions += " · Delete nowe potwierdzenie"
            result.append(actions)
        if self._notice:
            result.append(self._notice.rstrip("."))
        if self._snapshot.get("notification_problem"):
            result.append(_safe_text(self._snapshot["notification_problem"]))
        if not self._connected:
            result.append("Brak połączenia")
        if self._operation_details is not None or self._details is not None:
            return [
                *result,
                "↑↓ pliki · Esc wróć" + (" do biblioteki" if self._details is not None else ""),
                self._global_status(),
            ]
        if operation is not None:
            return [*result, "←→ widok · ↑↓ wybierz · Esc wróć", self._global_status()]
        relocations: list[Mapping[str, object]] = _relocation_problems(self._snapshot)
        if self._tab == _Tab.FILES and relocations:
            names: str = ", ".join(_safe_text(item["name"]) for item in relocations)
            result.append(f"P ponów przenoszenie do biblioteki · {names}")
        hints: tuple[str | Text, ...] = (
            "Tab widok",
            "Space aktywność · Enter odcinki · D dodaj · X usuń · F sprawdź",
            "H historia · M ręczny · O zatrzymaj/wznów · U ustawienia",
            "Enter otwórz · F folder · D szczegóły · Delete Kosz",
        )
        result.append("←→ widok · ↑↓ wybierz · Esc wróć")
        result.append(hints[self._tab])
        result.append(self._processing_hint() if self._tab == _Tab.PROGRESS else "")
        result.append(self._global_status())
        return result

    def _processing_hint(self) -> str:
        materials: list[Mapping[str, object]] = _rows(self._snapshot.get("materials"))
        if self._selected >= len(materials):
            return "P ponów wszystkie przenoszenia do biblioteki" if _relocation_problems(self._snapshot) else ""
        item: Mapping[str, object] = materials[self._selected]
        if item.get("stage") == "download":
            return "P wstrzymaj cały torrent · W wznów · X anuluj cały torrent"
        if item.get("run_id"):
            scope: object = item.get("group_ids", [])
            count: int = len(scope) if isinstance(scope, list) else 1
            return f"{'C anuluj' if item.get('active') else 'P ponów'} całe zlecenie · {count} materiałów"
        return "M ręczny wybór źródła"

    def _global_status(self) -> str:
        counts: object = self._snapshot.get("material_counts", {})
        values: Mapping[str, object] = counts if isinstance(counts, Mapping) else {}
        status: str = "Praca" if self._snapshot.get("auto_enabled") else "Wstrzymano"
        if self._snapshot.get("pausing"):
            status = "Zatrzymywanie"
        if self._snapshot.get("pause_incomplete"):
            status = "Pauza niepełna"
        return (
            f"↓ {values.get('downloading', 0)} · Przetwarzanie {values.get('processing', 0)}"
            f" · Czeka {values.get('waiting', 0)} · {status}"
        )

    def _entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        if self._retry is not None:
            labels: dict[str, str] = {
                "resume": f"Dokończ całe zapisane zlecenie · {len(self._retry.group_ids)} materiałów · podgląd",
                "manual": "Popraw wybrany lokalny materiał w Ręcznym · wybór zakresu przebudowy",
                "reacquire": "Pobierz ponownie zachowane wydanie · nowe jawne zamówienie",
                "subscription": "Ponów wskazany zakres internetowy · nowe jawne zamówienie",
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
        if self._deletion is not None:
            entries = [("PRZENIEŚ CAŁY ZESTAW DO KOSZA?", None), (_safe_text(self._deletion.name), None)]
        elif self._operation_details is not None:
            entries = self._operation_entries(self._operation_details)
        elif self._details is not None:
            entries = _library_detail_entries(self._details)
        if self._deletion is not None or self._details is not None or self._operation_details is not None:
            return entries
        if self._tab == _Tab.PROGRESS:
            return [
                *self._processing_entries(columns),
                *((_deletion_label(item), None) for item in _deletion_rows(self._snapshot)),
            ]
        if self._tab == _Tab.SUBSCRIPTIONS:
            return [
                (
                    f"{_safe_text(item.get('series', ''))} [{_safe_text(item.get('group', ''))}]"
                    f" · {_subscription_term(item)}",
                    bool(item.get("enabled")),
                )
                for item in self._subscriptions
            ]
        if self._tab == _Tab.FILES:
            entries = [
                (
                    _deletion_label(item) if "operation_id" in item else _library_label(item),
                    None,
                )
                for item in _library_rows(self._snapshot)
            ]
        return entries

    def _operation_entries(self, operation: PendingDeletion) -> list[tuple[str | Text, bool | None]]:
        selected: Mapping[str, object] = self._selected_deletion() or {}
        statuses: dict[str, str] = {
            item.path: (
                "uncertain" if item.status.value == "inflight" and not selected.get("active") else item.status.value
            )
            for item in operation.outcomes
        }
        entries: list[tuple[str | Text, bool | None]] = [(_safe_text(self._operation_name), None)]
        reasons: dict[str, str] = {item.path: _LIBRARY_PROBLEMS.get(item.reason, "") for item in operation.outcomes}
        for path, _size, _stamp in operation.files:
            status: str = statuses.get(path, "recycled" if path in operation.recycled else "pending")
            explanation: str = f" · {reasons[path]}" if reasons.get(path) else ""
            entries.append((f"{_safe_text(path)} · {_DELETION_STATUSES[status]}{explanation}", None))
        return entries

    def _processing_entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        entries: list[tuple[str | Text, bool | None]] = []
        measured: bool = self._connected and not self._snapshot.get("transfers_problem")
        for item in _rows(self._snapshot.get("materials")):
            progress: tuple[str, RichRunProgress] | None = self._runs.get(str(item.get("run_id", "")))
            if progress is not None:
                line: Text = progress[1].render_group(str(item.get("group_id", "")), columns)
                if line.plain:
                    entries.append((line, None))
                    continue
            stage: str = str(item.get("stage"))
            label: str = _safe_text(item.get("name", ""))
            if stage == "download":
                fraction: object = item.get("progress")
                percentage: str = f" · {float(str(fraction)) * 100:.1f}%" if fraction is not None and measured else ""
                label += f" · Pobieranie{percentage} · {_transfer_label(item, measured=measured)}"
            elif stage == "waiting":
                label += f" · {_waiting_label(str(item.get('reason')))}"
            else:
                label += f" · {_processing_label(str(item.get('state')))}"
            entries.append((label, None))
        return [*entries, *self._relocation_entries()]

    def _relocation_entries(self) -> list[tuple[str | Text, bool | None]]:
        return [
            (f"{_safe_text(item['name'])} · błąd przenoszenia do biblioteki", None)
            for item in _relocation_problems(self._snapshot)
        ]


def _transfer_label(row: Mapping[str, object], *, measured: bool) -> str:
    """Return the Polish label of one download row, naming a recorded problem before any client state."""
    if row.get("problem"):
        return _ATTENTION_LABEL
    if row.get("state") is None:
        return _UNCONFIRMED_LABEL
    return _TRANSFER_LABELS.get(str(row.get("state")), "") if measured else ""


def _waiting_label(reason: str) -> str:
    return {
        "preparing": "pobrano · przygotowanie",
        "video_missing": "czeka na film",
        "sidecar_missing": "czeka na napisy",
        "subtitle_source_missing": "potrzebne napisy",
        "image_missing": "czeka na obraz",
        "content_source_missing": "czeka na treść",
        "source_incomplete": "czeka na komplet plików",
        "ambiguous_sidecar": "wybierz napisy",
        "ambiguous_image": "wybierz obraz",
        "ambiguous_content_source": "wybierz źródło",
        "source_path_collision": "konflikt ścieżek",
        "unsupported_source": "źródło wymaga Ręcznego",
    }.get(reason, "czeka na komplet")


def _subscription_term(item: Mapping[str, object], now: datetime | None = None) -> str:
    airing: object = item.get("airing_at")
    moment: datetime | None = None
    if isinstance(airing, str):
        with suppress(ValueError):
            moment = datetime.fromisoformat(airing)
    if moment is None or moment.tzinfo is None:
        return (
            "Brak terminu · Kalendarz niedostępny · F: sprawdź ponownie"
            if item.get("calendar_problem")
            else "Brak terminu"
        )
    remaining: float = (moment - (now if now is not None else datetime.now(UTC))).total_seconds()
    seconds: int = max(1, int(remaining)) if remaining > 0 else 0
    days: int
    hours: int
    minutes: int
    remainder: int
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    term: str = (
        f"Emisja za {days:02d}d {hours:02d}:{minutes:02d}:{seconds:02d}" if remaining > 0 else "Czeka na wydanie"
    )
    number: object = item.get("airing_episode")
    if number is not None:
        term = f"Odc. {_safe_text(number)} · {term}"
    if item.get("calendar_problem"):
        term += " · Kalendarz niedostępny"
    return term


def _processing_row_ids(snapshot: Mapping[str, object]) -> list[str]:
    return [
        *(f"material:{item['material_id']}" for item in _rows(snapshot.get("materials"))),
        *(f"relocation:{item['group_id']}" for item in _relocation_problems(snapshot)),
        *(f"deletion:{item['operation_id']}" for item in _deletion_rows(snapshot)),
    ]


def _processing_label(state: str) -> str:
    return {
        "accepted": "Przygotowanie",
        "running": "Przetwarzanie",
        "paused": "Wstrzymano",
        "failed": "Błąd · wymaga ponowienia",
        "partial": "Niepełne · wymaga ponowienia",
        "cancelled": "Anulowano",
    }.get(state, "Przygotowanie")


def _rows(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _safe_text(value: object) -> str:
    message: str = sanitize_event_message(str(value)) or ""
    return _CLIENT_PROBLEMS.get(message, message)


def _relocation_problems(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in _rows(snapshot.get("relocations")) if item.get("problem")]


def _library_rows(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    return os_sorted(
        [*_rows(snapshot.get("library")), *_rows(snapshot.get("library_problems")), *_deletion_rows(snapshot)],
        key=lambda item: (str(item.get("name", "")), _library_row_id(item)),
    )


def _library_row_id(item: Mapping[str, object]) -> str:
    return str(item.get("operation_id", item.get("set_id", "")))


def _library_label(item: Mapping[str, object]) -> str:
    label: str = _safe_text(item.get("name", ""))
    if item.get("available") is False:
        label += " · " + _LIBRARY_PROBLEMS.get(str(item.get("problem")), _LIBRARY_PROBLEMS["library_result_missing"])
    return label


def _deletion_rows(snapshot: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [
        item
        for item in _rows(snapshot.get("deletions"))
        if item.get("active") or item.get("recycled") != item.get("total")
    ]


def _deletion_label(item: Mapping[str, object]) -> str:
    status: str = "trwa" if item.get("active") else "niepełne"
    if item.get("uncertain"):
        status = "wynik niepewny"
    return (
        f"Kosz: {_safe_text(item.get('name', item.get('set_id', '')))} · {status} · "
        f"nierozliczone: {item.get('remaining')}/{item.get('total')}"
    )


def _library_detail_entries(details: LibrarySet) -> list[tuple[str | Text, bool | None]]:
    entries: list[tuple[str | Text, bool | None]] = [(_safe_text(details.name), None)]
    if details.target is None:
        entries.append(("Cel nierozstrzygnięty · regeneracja wymaga wyboru", None))
    if details.problem is not None and details.problem in _LIBRARY_PROBLEMS:
        entries.append((_LIBRARY_PROBLEMS[details.problem], None))
    elif not details.available:
        entries.append((_LIBRARY_PROBLEMS["library_result_missing"], None))
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
    _open_path(session.library_result(set_id), show_folder=show_folder)
