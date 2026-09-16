"""Resident state and actions in the existing terminal renderer."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from enum import IntEnum, StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from natsort import os_sorted
from rich.text import Text

from anishift.application import (
    DeletionPreview,
    LibrarySet,
    PendingDeletion,
    RefusalReason,
    RunProgressSnapshot,
    Subscription,
    SubscriptionOrder,
    TitleCandidate,
    decode_view,
)
from anishift.application.events import RunEvent, sanitize_event_message
from anishift.cli.interactive.menu import (
    append_wrapped_row,
    fit_entries,
    header,
    left_padding,
    visible_window,
    with_footer,
    wrap_entries,
)
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError
from anishift.platform.local_control import ControlError

__all__ = ["StateController", "StateResult", "refusal_text"]

# ── Constants ─────────────────────────────────────────────────────────────────

_TABS: Final[tuple[str, ...]] = ("Przetwarzanie", "Pobrania", "Subskrypcje", "Biblioteka")
"""Views of the same resident snapshot, switched without network requests."""


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

_ADD_FIELDS: Final[tuple[str, ...]] = ("Tytuł serii", "Grupa wydająca", "Pierwszy odcinek")
"""Fields needed to follow a series even before its first torrent exists."""

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
    return _REFUSAL_TEXTS.get(reason) or _LIBRARY_PROBLEMS.get(reason) or _safe_text(str(problem)) or _UNKNOWN_REFUSAL


class _Tab(IntEnum):
    PROGRESS = 0
    TRANSFERS = 1
    SUBSCRIPTIONS = 2
    FILES = 3


class StateResult(StrEnum):
    """Navigation requested from the state screen."""

    CONTINUE = "continue"
    HOME = "home"
    SETTINGS = "settings"
    AUTO = "auto"
    MANUAL = "manual"
    ANIME = "anime"


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
        self._snapshot: Mapping[str, object] = {}
        self._subscriptions: list[Mapping[str, object]] = []
        self._runs: dict[str, tuple[str, RichRunProgress]] = {}
        self._tab: int = 0
        self._selected: int = 0
        self._connected: bool = False
        self._busy: bool = False
        self._notice: str = "Łączenie z procesem w tle…"
        self._state_version: int = 0
        self._notice_version: int = -1
        self._form: list[str] | None = None
        self._input: TextInput = TextInput()
        self._binding: Subscription | None = None
        self._details: LibrarySet | None = None
        self._operation_details: PendingDeletion | None = None
        self._operation_name: str = ""
        self._detail_selection: int = 0
        self._deletion: DeletionPreview | None = None
        self._deletion_session: ResidentSession | None = None
        self._delete_confirmed: bool = False
        self._view_generation: int = 0
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._thread: threading.Thread = threading.Thread(target=self._watch, name="anishift-state", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Detach this panel without stopping resident work."""
        self._stop.set()
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

    def show_processing(self) -> None:
        """Select current processing after the user starts a run."""
        with self._lock:
            self._view_generation += 1
            self._cancel_deletion()
            self._details = None
            self._operation_details = None
            self._tab = _Tab.PROGRESS
            self._selected = 0
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
            if self._modal_key(key):
                return StateResult.CONTINUE
            if key in {"escape", "interrupt", "backspace"}:
                self._view_generation += 1
                return StateResult.HOME
            if key in {"tab", "backtab", "left", "right"}:
                self._view_generation += 1
                self._details = None
                self._tab = (self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS)
                self._selected = 0
                self._notify("")
                if self._tab == _Tab.FILES:
                    self._work(lambda session: session.library())
            elif key in {"up", "down", "home", "end"}:
                count: int = max(len(self._entries(120)), 1)
                if key in {"home", "end"}:
                    self._selected = 0 if key == "home" else count - 1
                else:
                    self._selected = (self._selected + (-1 if key == "up" else 1)) % count
            elif key in {"space", "enter"} and self._tab == _Tab.SUBSCRIPTIONS:
                return self._action_key("w")
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
                count: int = max(len(self._entries(120)), 1)
                self._selected = (self._selected + (-1 if key == "up" else 1)) % count
                if key in {"home", "end"}:
                    self._selected = 0 if key == "home" else count - 1
            self._invalidate()
            return True
        if self._details is not None:
            self._details_key(key)
            return True
        if self._form is not None:
            self._edit_form(key)
            return True
        if self._binding is not None:
            self._binding_key(key)
            return True
        return False

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
            count: int = max(len(self._entries(120)), 1)
            self._selected = (self._selected + (-1 if key == "up" else 1)) % count
            if key in {"home", "end"}:
                self._selected = 0 if key == "home" else count - 1
        self._invalidate()

    def _action_key(self, key: str) -> StateResult:
        navigation: dict[str, StateResult] = {
            "u": StateResult.SETTINGS,
            "r": StateResult.AUTO,
            "m": StateResult.MANUAL,
            "a": StateResult.ANIME,
        }
        if key in navigation:
            self._view_generation += 1
            return navigation[key]
        if key == "o":
            self._command("set_auto", {"enabled": not self._snapshot.get("auto_enabled", False)})
        elif key == "f" and self._tab == _Tab.SUBSCRIPTIONS:
            self._command("subscriptions_check")
        elif key == "d" and self._tab == _Tab.SUBSCRIPTIONS:
            self._form = []
            self._input.reset()
        elif self._tab == _Tab.SUBSCRIPTIONS and self._subscriptions and key in {"w", "x"}:
            item: Mapping[str, object] = self._subscriptions[min(self._selected, len(self._subscriptions) - 1)]
            kind: str = (
                "subscription_remove"
                if key == "x"
                else ("subscription_disable" if item.get("enabled") else "subscription_enable")
            )
            self._command(kind, {"subscription_id": item["subscription_id"]})
        elif self._tab == _Tab.SUBSCRIPTIONS and self._subscriptions and key == "b":
            item = self._subscriptions[min(self._selected, len(self._subscriptions) - 1)]
            identifier: str = str(item["subscription_id"])
            self._work(lambda session: self._binding_candidates(session, identifier))
        elif self._tab == _Tab.PROGRESS and key == "c":
            offset: int = self._selected
            for run_id, (_, progress) in self._runs.items():
                if offset < progress.pending_row_count:
                    self._command("cancel", {"run_id": run_id})
                    break
                offset -= progress.pending_row_count
        elif self._tab == _Tab.TRANSFERS and key in {"p", "w", "x"}:
            transfers: list[Mapping[str, object]] = self._transfer_rows()
            if transfers:
                transfer: Mapping[str, object] = transfers[min(self._selected, len(transfers) - 1)]
                self._command(
                    "transfer",
                    {"info_hash": transfer["info_hash"], "action": {"p": "stop", "w": "resume", "x": "cancel"}[key]},
                )
        elif self._tab == _Tab.FILES:
            self._file_action(key)
        self._invalidate()
        return StateResult.CONTINUE

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
            self._work(lambda session: self._show_details(session, set_id))
            return
        self._work(lambda session: _open_episode(session, set_id, show_folder=key == "f"))

    def _selected_deletion(self) -> Mapping[str, object] | None:
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
        position: int = self._selected - len(self._progress_entries(120))
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

    def _show_details(self, session: ResidentSession, set_id: str) -> None:
        details: LibrarySet = session.library_details(set_id)
        with self._lock:
            if self._tab != _Tab.FILES:
                return
            self._detail_selection = self._selected
            self._selected = 0
            self._details = details

    def _binding_candidates(self, session: ResidentSession, identifier: str) -> None:
        subscription: Subscription = decode_view(
            Subscription, session.command("subscription_get", {"subscription_id": identifier})
        )
        candidates: tuple[TitleCandidate, ...] = session.find_titles(subscription.series)
        with self._lock:
            self._binding = subscription if candidates else None
            self._candidates = candidates
            self._selected = 0
            if not candidates:
                self._notify("Katalog nie zwrócił pasującego sezonu")

    def _binding_key(self, key: str) -> None:
        if key in {"escape", "interrupt"}:
            self._binding = None
        elif key in {"up", "down"}:
            self._selected = (self._selected + (-1 if key == "up" else 1)) % max(len(self._candidates), 1)
        elif key == "enter" and self._binding is not None and self._candidates:
            subscription: Subscription = self._binding
            candidate: TitleCandidate = self._candidates[self._selected]
            self._binding = None

            def bind(session: ResidentSession) -> object:
                return session.follow(
                    SubscriptionOrder(
                        series=subscription.series,
                        group=subscription.group,
                        query=subscription.query,
                        first_episode=subscription.next_episode,
                        directory_name=subscription.directory,
                        context=session.season_context(candidate),
                        anilist_id=candidate.anilist_id,
                    )
                )

            self._work(bind)
        self._invalidate()

    def _edit_form(self, key: str) -> None:
        if self._input.handle(key):
            self._invalidate()
            return
        if key in {"escape", "interrupt"}:
            self._form = None
        elif key == "enter" and self._form is not None:
            self._accept_field()
        self._invalidate()

    def _accept_field(self) -> None:
        if self._form is None or not self._input.text.strip():
            return
        values: list[str] = [*self._form, self._input.text.strip()]
        if len(values) < len(_ADD_FIELDS):
            self._form = values
            self._input.reset("1" if len(values) == len(_ADD_FIELDS) - 1 else "")
            return
        try:
            order: SubscriptionOrder = SubscriptionOrder(
                series=values[0],
                group=values[1],
                query=f"{values[0]} {values[1]}",
                first_episode=Decimal(values[2]),
                directory_name=values[0],
            )
        except ValueError, InvalidOperation:
            self._notify("Podaj poprawny dodatni numer pierwszego odcinka")
            return
        self._form = None
        self._work(lambda session: session.follow(order))

    def _command(self, kind: str, payload: Mapping[str, object] | None = None) -> None:
        self._work(lambda session: session.command(kind, payload))

    def _work(self, action: Callable[[ResidentSession], object]) -> None:
        if self._busy:
            self._notify("Poprzednia czynność jeszcze trwa; możesz przejść do ustawień")
            return
        self._busy = True
        self._notify("Wykonywanie polecenia…")
        threading.Thread(target=self._perform, args=(action,), name="anishift-state-action", daemon=True).start()

    def _perform(self, action: Callable[[ResidentSession], object]) -> None:
        session: ResidentSession | None = None
        try:
            session = self._parent.new_session()
            action(session)
            with self._lock:
                self._notify("Polecenie przyjęte")
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

    def _receive(self, session: ResidentSession, frame: Mapping[str, object]) -> None:
        if frame.get("event") == "panel_open":
            self._open_requested.set()
            self._invalidate()
            return
        payload: object = frame.get("payload")
        if not isinstance(payload, Mapping):
            return
        if frame.get("event") == "state_changed":
            subscriptions: list[Mapping[str, object]] = _rows(
                session.command("subscriptions_list").get("subscriptions")
            )
            with self._lock:
                selected_operation: Mapping[str, object] | None = self._selected_deletion()
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
                if payload != self._snapshot:
                    self._state_version += 1
                self._preserve_library_selection(payload)
                self._preserve_deletion_selection(payload, selected_operation)
                self._snapshot = payload
                if self._operation_details is previous_operation_details:
                    self._operation_details = operation_details
                if self._details is previous_details:
                    self._details = details
                    if previous_details is not None and details is None:
                        self._selected = self._detail_selection
                self._subscriptions = subscriptions
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

    def _preserve_deletion_selection(
        self, payload: Mapping[str, object], selected: Mapping[str, object] | None
    ) -> None:
        if self._tab != _Tab.PROGRESS or selected is None:
            return
        position: int = next(
            (
                index
                for index, item in enumerate(_deletion_rows(payload))
                if item["operation_id"] == selected["operation_id"]
            ),
            0,
        ) + len(self._progress_entries(120))
        if self._operation_details is None:
            self._selected = position
        else:
            self._detail_selection = position

    def _preserve_library_selection(self, payload: Mapping[str, object]) -> None:
        if self._tab != _Tab.FILES:
            return
        old: list[Mapping[str, object]] = _library_rows(self._snapshot)
        new: list[Mapping[str, object]] = _library_rows(payload)
        position: int = (
            self._selected if self._details is None and self._operation_details is None else self._detail_selection
        )
        selected_id: object = _library_row_id(old[position]) if position < len(old) else None
        position = next(
            (index for index, item in enumerate(new) if _library_row_id(item) == selected_id),
            min(position, max(len(new) - 1, 0)),
        )
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
            entries: list[tuple[str | Text, bool | None]] = self._entries(max(columns - 8, 1))
            selected: int = 0 if self._deletion is not None else min(self._selected, max(len(entries) - 1, 0))
            if self._deletion is None:
                self._selected = selected
            labels: tuple[str, ...] = fit_entries(
                tuple(label.plain if isinstance(label, Text) else label for label, _ in entries), columns
            )
            footer: list[str | Text] = self._footer()
            list_rows: int = rows - max(len(footer) - 2, 0) - int(self._form is not None)
            wrapped: tuple[tuple[str | Text, ...], ...] = wrap_entries(tuple(label for label, _ in entries), columns)
            start, end = visible_window(len(labels), selected, list_rows, heights=tuple(map(len, wrapped)))
            left: int = left_padding(columns, labels)
            content: Text = header("PANEL", columns, rows, max(rows - 5, 1))
            tabs: Text = self._tabs()
            tabs.truncate(max(columns - 2, 1), overflow="ellipsis")
            content.append(" " * max((columns - tabs.cell_len) // 2, 0))
            content.append_text(tabs)
            content.append("\n\n")
            remaining: int = max(list_rows - 7, 1)
            for index in range(start, end):
                checked: bool | None = entries[index][1]
                marker: str = "" if checked is None else ("● " if checked else "○ ")
                lines: tuple[str | Text, ...] = wrapped[index][:remaining]
                append_wrapped_row(content, left, lines, index == selected, marker)
                remaining -= len(lines)
            if not entries:
                empty: str = "Brak zadań" if self._tab == _Tab.PROGRESS else "Brak pozycji"
                content.append(" " * max((columns - len(empty)) // 2, 0) + empty + "\n", style="gray")
            if self._form is not None:
                prompt: str = f"{_ADD_FIELDS[len(self._form)]}: "
                content.append(" " * left + prompt, style="white_bold")
                content.append_text(self._input.render(max(columns - left - len(prompt) - 1, 1)))
                content.append("\n")
            return with_footer(content, footer, columns, rows)

    def _tabs(self) -> Text:
        tabs: Text = Text()
        for index, name in enumerate(_TABS):
            if index:
                tabs.append(" · ", style="gray")
            tabs.append(name, style="brand_accent" if self._tab == index else "gray")
        return tabs

    def _footer(self) -> list[str | Text]:
        result: list[str | Text] = []
        if self._deletion is not None:
            return [
                f"{len(self._deletion.files)} plików · {self._deletion.total_size:,} B · cały zestaw",
                "Anuluj   [Przenieś do Kosza]" if self._delete_confirmed else "[Anuluj]   Przenieś do Kosza",
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
        if not self._connected:
            result.append("Brak połączenia")
        if self._operation_details is not None or self._details is not None:
            return [*result, "↑↓ pliki · Esc wróć" + (" do biblioteki" if self._details is not None else "")]
        if operation is not None:
            return [*result, "←→ widok · ↑↓ wybierz · Esc wróć"]
        if self._form is not None:
            return [*result, "Enter zatwierdź · Esc anuluj"]
        if self._binding is not None:
            return [*result, "↑↓ · Enter wybierz · Esc wróć"]
        relocations: list[Mapping[str, object]] = _relocation_problems(self._snapshot)
        if self._tab == _Tab.FILES and relocations:
            names: str = ", ".join(_safe_text(item["name"]) for item in relocations)
            result.append(f"P ponów przenoszenie do biblioteki · {names}")
        hints: tuple[str | Text, ...] = (
            Text("R uruchom · M ręczny · ", style="gray")
            + Text(f"O {'●' if self._snapshot.get('auto_enabled') else '○'} Auto", style="brand_accent")
            + Text(" · C anuluj zlecenie", style="gray"),
            "P wstrzymaj · W wznów · X anuluj",
            "Space wybierz · D dodaj · X usuń · B sezon · F sprawdź",
            "Enter otwórz · F folder · D szczegóły · Delete Kosz",
        )
        result.append("←→ widok · ↑↓ wybierz · Esc wróć")
        result.append(hints[self._tab])
        return result

    def _entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        entries: list[tuple[str | Text, bool | None]] = []
        if self._deletion is not None:
            entries = [("PRZENIEŚ CAŁY ZESTAW DO KOSZA?", None), (_safe_text(self._deletion.name), None)]
        elif self._operation_details is not None:
            entries = self._operation_entries(self._operation_details)
        elif self._details is not None:
            entries = _library_detail_entries(self._details)
        if self._deletion is not None or self._details is not None or self._operation_details is not None:
            return entries
        if self._binding is not None:
            return [(_safe_text(item.romaji), None) for item in self._candidates]
        if self._tab == _Tab.PROGRESS:
            return [
                *self._progress_entries(columns),
                *((_deletion_label(item), None) for item in _deletion_rows(self._snapshot)),
            ]
        if self._tab == _Tab.SUBSCRIPTIONS:
            return [
                (
                    f"{_safe_text(item.get('series', ''))} [{_safe_text(item.get('group', ''))}]"
                    f" · {item.get('next_episode', '')}",
                    bool(item.get("enabled")),
                )
                for item in self._subscriptions
            ]
        if self._tab == _Tab.FILES:
            return [
                (
                    _deletion_label(item) if "operation_id" in item else _library_label(item),
                    None,
                )
                for item in _library_rows(self._snapshot)
            ]
        measured: bool = self._connected and not self._snapshot.get("transfers_problem")
        for item in self._transfer_rows():
            value: object = item.get("progress")
            progress_text: str = (
                f"{float(str(value)) * 100:.1f}%" if measured and isinstance(value, (int, float)) else "—"
            )
            state: str = _transfer_label(item, measured=measured)
            entries.append(
                (
                    f"{_safe_text(item.get('name', ''))} · {progress_text}" + (f" · {state}" if state else ""),
                    None,
                )
            )
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

    def _progress_entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        return [
            (line, None)
            for _, progress in self._runs.values()
            for line in progress.render(columns, include_completed=False).split("\n")
            if line.plain.strip()
        ]

    def _transfer_rows(self) -> list[Mapping[str, object]]:
        acquisitions: list[Mapping[str, object]] = _rows(self._snapshot.get("acquisitions"))
        attention: set[str] = {str(item.get("info_hash")) for item in acquisitions if item.get("problem")}
        reported: list[Mapping[str, object]] = _rows(self._snapshot.get("transfers"))
        known: set[str] = {str(item["info_hash"]) for item in reported}
        rows: list[Mapping[str, object]] = [
            {**item, "problem": str(item["info_hash"]) in attention} for item in reported
        ]
        rows.extend(
            {
                "info_hash": item["info_hash"],
                "name": f"{item.get('directory', '')} · odc. {item.get('episode', '?')}",
                "state": None,
                "problem": bool(item.get("problem")),
                "progress": None,
            }
            for item in acquisitions
            if str(item.get("info_hash")) not in known
            and item.get("state") != "complete"
            and (item.get("state") != "failed" or item.get("problem"))
        )
        return rows


def _transfer_label(row: Mapping[str, object], *, measured: bool) -> str:
    """Return the Polish label of one download row, naming a recorded problem before any client state."""
    if row.get("problem"):
        return _ATTENTION_LABEL
    if row.get("state") is None:
        return _UNCONFIRMED_LABEL
    return _TRANSFER_LABELS.get(str(row.get("state")), "") if measured else ""


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


def _open_path(path: Path, *, show_folder: bool = False) -> None:
    if sys.platform == "win32":
        if show_folder:
            explorer: Path = Path(os.environ["SYSTEMROOT"]) / "explorer.exe"
            subprocess.Popen([str(explorer), "/select,", str(path)])  # noqa: S603 - explicitly selected workspace file
        else:
            os.startfile(path)  # noqa: S606 - explicitly selected workspace file or directory
    else:
        target: Path = path.parent if show_folder else path
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])  # noqa: S603 - desktop opener
