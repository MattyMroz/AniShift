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
from typing import Final

from rich.text import Text

from anishift.application import (
    ArtifactKind,
    InspectedSourceGroup,
    InspectedWorkspace,
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

__all__ = ["StateController", "StateResult"]

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
        self._open_requested: threading.Event = threading.Event()
        self._snapshot: Mapping[str, object] = {}
        self._subscriptions: list[Mapping[str, object]] = []
        self._runs: dict[str, tuple[str, RichRunProgress]] = {}
        self._tab: int = 0
        self._selected: int = 0
        self._connected: bool = False
        self._busy: bool = False
        self._notice: str = "Łączenie z procesem w tle…"
        self._form: list[str] | None = None
        self._input: TextInput = TextInput()
        self._binding: Subscription | None = None
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._thread: threading.Thread = threading.Thread(target=self._watch, name="anishift-state", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Detach this panel without stopping resident work."""
        self._stop.set()
        session: ResidentSession | None = self._session
        if session is not None:
            session.close()

    def take_open_request(self) -> bool:
        """Consume a tray request on the panel's event loop."""
        requested: bool = self._open_requested.is_set()
        self._open_requested.clear()
        return requested

    def show_processing(self) -> None:
        """Select current processing after the user starts a run."""
        with self._lock:
            self._tab = _Tab.PROGRESS
            self._selected = 0
        self._invalidate()

    def set_notice(self, message: str) -> None:
        """Show preparation or submission feedback without changing the selected view."""
        with self._lock:
            self._notice = _safe_text(message).rstrip(".")
        self._invalidate()

    def handle_key(self, key: str) -> StateResult:
        """Navigate the shared list or submit one explicit action."""
        with self._lock:
            if self._form is not None:
                self._edit_form(key)
                return StateResult.CONTINUE
            if self._binding is not None:
                self._binding_key(key)
                return StateResult.CONTINUE
            if key in {"escape", "interrupt", "backspace"}:
                return StateResult.HOME
            if key in {"tab", "backtab", "left", "right"}:
                self._tab = (self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS)
                self._selected = 0
                self._notice = ""
            elif key in {"up", "down", "home", "end"}:
                count: int = max(len(self._entries(120)), 1)
                if key in {"home", "end"}:
                    self._selected = 0 if key == "home" else count - 1
                else:
                    self._selected = (self._selected + (-1 if key == "up" else 1)) % count
            elif key in {"space", "enter"} and self._tab == _Tab.SUBSCRIPTIONS:
                return self._action_key("w")
            elif key == "enter" and self._tab == _Tab.FILES:
                self._file_action("open")
            elif key.startswith("text:"):
                return self._action_key(key.removeprefix("text:").casefold())
            self._invalidate()
            return StateResult.CONTINUE

    def _action_key(self, key: str) -> StateResult:
        navigation: dict[str, StateResult] = {
            "u": StateResult.SETTINGS,
            "r": StateResult.AUTO,
            "m": StateResult.MANUAL,
            "a": StateResult.ANIME,
        }
        if key in navigation:
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
            self._command("ready_retry")
            return
        library: list[Mapping[str, object]] = _rows(self._snapshot.get("library"))
        if key not in {"open", "f"} or self._selected >= len(library):
            return
        directory: str = str(library[self._selected]["directory"])
        directory = "" if directory == "." else directory
        group_id: str = str(library[self._selected]["group_id"])
        self._work(lambda session: _open_episode(session, group_id, directory, show_folder=key == "f"))

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
                self._notice = "Katalog nie zwrócił pasującego sezonu"

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
            self._notice = "Podaj poprawny dodatni numer pierwszego odcinka"
            return
        self._form = None
        self._work(lambda session: session.follow(order))

    def _command(self, kind: str, payload: Mapping[str, object] | None = None) -> None:
        self._work(lambda session: session.command(kind, payload))

    def _work(self, action: Callable[[ResidentSession], object]) -> None:
        if self._busy:
            self._notice = "Poprzednia czynność jeszcze trwa; możesz przejść do ustawień"
            return
        self._busy = True
        self._notice = "Wykonywanie polecenia…"
        threading.Thread(target=self._perform, args=(action,), name="anishift-state-action", daemon=True).start()

    def _perform(self, action: Callable[[ResidentSession], object]) -> None:
        session: ResidentSession | None = None
        try:
            session = self._parent.new_session()
            action(session)
            with self._lock:
                self._notice = "Polecenie przyjęte"
        except (AniShiftError, ControlError, OSError, ValueError) as error:
            with self._lock:
                self._notice = _safe_text(str(error))
        finally:
            if session is not None:
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
                    self._notice = _safe_text(str(error))
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
            self._restore_progress(session, payload)
            with self._lock:
                self._snapshot = payload
                self._subscriptions = subscriptions
                self._connected = True
                if self._notice.startswith("Łączenie"):
                    self._notice = ""
                if payload.get("shutting_down"):
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
            self._selected = min(self._selected, max(len(entries) - 1, 0))
            labels: tuple[str, ...] = fit_entries(
                tuple(label.plain if isinstance(label, Text) else label for label, _ in entries), columns
            )
            footer: list[str | Text] = self._footer()
            list_rows: int = rows - max(len(footer) - 2, 0) - int(self._form is not None)
            wrapped: tuple[tuple[str | Text, ...], ...] = wrap_entries(tuple(label for label, _ in entries), columns)
            start, end = visible_window(len(labels), self._selected, list_rows, heights=tuple(map(len, wrapped)))
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
                append_wrapped_row(content, left, lines, index == self._selected, marker)
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
        if self._notice:
            result.append(self._notice.rstrip("."))
        if not self._connected:
            result.append("Brak połączenia")
        if self._form is not None:
            return [*result, "Enter zatwierdź · Esc anuluj"]
        if self._binding is not None:
            return [*result, "↑↓ · Enter wybierz · Esc wróć"]
        hints: tuple[str | Text, ...] = (
            Text("R uruchom · M ręczny · ", style="gray")
            + Text(f"O {'●' if self._snapshot.get('auto_enabled') else '○'} Auto", style="brand_accent")
            + Text(" · C anuluj zlecenie", style="gray"),
            "P wstrzymaj · W wznów · X anuluj",
            "Space wybierz · D dodaj · X usuń · B sezon · F sprawdź",
            "Enter odtwórz · F folder · M ręczny · P ponów",
        )
        result.append("←→ widok · ↑↓ wybierz · Esc wróć")
        result.append(hints[self._tab])
        return result

    def _entries(self, columns: int) -> list[tuple[str | Text, bool | None]]:
        if self._binding is not None:
            return [(_safe_text(item.romaji), None) for item in self._candidates]
        if self._tab == _Tab.PROGRESS:
            return [
                (line, None)
                for _, progress in self._runs.values()
                for line in progress.render(columns, include_completed=False).split("\n")
                if line.plain.strip()
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
            return [(_safe_text(item.get("name", "")), None) for item in _rows(self._snapshot.get("library"))]
        measured: bool = self._connected and not self._snapshot.get("transfers_problem")
        entries: list[tuple[str | Text, bool | None]] = []
        for item in self._transfer_rows():
            value: object = item.get("progress")
            progress_text: str = (
                f"{float(str(value)) * 100:.1f}%" if measured and isinstance(value, (int, float)) else "—"
            )
            state: str = _TRANSFER_LABELS.get(str(item.get("state")), "") if measured else ""
            entries.append(
                (
                    f"{_safe_text(item.get('name', ''))} · {progress_text}" + (f" · {state}" if state else ""),
                    None,
                )
            )
        return entries

    def _transfer_rows(self) -> list[Mapping[str, object]]:
        rows: list[Mapping[str, object]] = _rows(self._snapshot.get("transfers"))
        known: set[str] = {str(item["info_hash"]) for item in rows}
        rows.extend(
            {
                "info_hash": item["info_hash"],
                "name": f"{item.get('directory', '')} · odc. {item.get('episode', '?')}",
                "state": "wymaga uwagi" if item.get("problem") else "brak potwierdzenia klienta",
                "progress": None,
            }
            for item in _rows(self._snapshot.get("acquisitions"))
            if str(item.get("info_hash")) not in known
            and item.get("state") != "complete"
            and (item.get("state") != "failed" or item.get("problem"))
        )
        return rows


def _rows(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _safe_text(value: object) -> str:
    message: str = sanitize_event_message(str(value)) or ""
    return _CLIENT_PROBLEMS.get(message, message)


def _open_folder(root: Path, directory: str) -> None:
    folder: Path = (root / directory).resolve()
    if not folder.is_relative_to(root.resolve()) or not folder.is_dir():
        message: str = "Folder is no longer available in the workspace"
        raise ValueError(message)
    _open_path(folder)


def _open_episode(session: ResidentSession, group_id: str, directory: str, *, show_folder: bool = False) -> None:
    workspace: InspectedWorkspace = session.discover()
    group: InspectedSourceGroup | None = next((item for item in workspace.groups if item.group_id == group_id), None)
    if group is None:
        _open_folder(session.workspace_root, directory)
        return
    kinds: tuple[ArtifactKind, ...] = (
        ArtifactKind.FINAL_MKV,
        ArtifactKind.FINAL_MP4,
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.VIDEO_MP4,
    )
    paths: dict[ArtifactKind, Path] = {
        item.kind: item.path.resolve()
        for item in group.artifacts
        if item.path is not None and item.kind in kinds and item.path.is_file()
    }
    selected: Path | None = next((paths[kind] for kind in kinds if kind in paths), None)
    if selected is None or not selected.is_relative_to(session.workspace_root.resolve()):
        _open_folder(session.workspace_root, directory)
        return
    _open_path(selected, show_folder=show_folder)


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
