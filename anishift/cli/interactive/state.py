"""Resident state and actions in the existing terminal renderer."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.application import (
    AutomationPolicy,
    RunProgressSnapshot,
    Subscription,
    SubscriptionOrder,
    TitleCandidate,
    decode_view,
)
from anishift.application.events import RunEvent, sanitize_event_message
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError
from anishift.platform.local_control import ControlError

__all__ = ["StateController", "StateResult"]

# ── Constants ─────────────────────────────────────────────────────────────────

_TABS: Final[tuple[str, ...]] = ("Postęp", "Pobrania", "Subskrypcje", "Pliki")
"""Views of the same resident snapshot, switched without network requests."""

_ADD_FIELDS: Final[tuple[str, ...]] = ("Tytuł serii", "Grupa wydająca", "Pierwszy odcinek")
"""Fields needed to follow a series even before its first torrent exists."""

_RECONNECT_S: Final[float] = 2.0
"""Delay before reconnecting a lost panel event stream."""


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
    """Keep a local snapshot while events and explicit commands run outside rendering."""

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
        self._offset: int = 0
        self._connected: bool = False
        self._busy: bool = False
        self._notice: str = "Łączenie z procesem w tle…"
        self._form: list[str] | None = None
        self._typed: str = ""
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

    def handle_key(self, key: str) -> StateResult:
        """Navigate cached views or queue one explicit user action."""
        with self._lock:
            if self._form is not None:
                self._edit_form(key)
                return StateResult.CONTINUE
            if self._binding is not None:
                self._binding_key(key)
                return StateResult.CONTINUE
            if key in {"escape", "interrupt"}:
                return StateResult.HOME
            if key in {"tab", "right", "left", "backtab"}:
                self._tab = (self._tab + (-1 if key in {"left", "backtab"} else 1)) % len(_TABS)
                self._selected = self._offset = 0
            elif key in {"up", "down"}:
                self._selected = max(0, self._selected + (-1 if key == "up" else 1))
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
            self._form, self._typed = [], ""
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
                if offset < progress.row_count:
                    self._command("cancel", {"run_id": run_id})
                    break
                offset -= progress.row_count
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
        if key not in {"w", "f"} or self._selected >= len(library):
            return
        directory: str = str(library[self._selected]["directory"])
        directory = "" if directory == "." else directory
        if key == "f":
            self._work(lambda session: _open_folder(session.workspace_root, directory))
            return
        enabled: bool = not self._policy(auto_enabled=True).effective_auto(directory)
        self._command("set_directory_auto", {"directory": directory, "enabled": enabled})

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
        if key in {"escape", "interrupt"}:
            self._form = None
        elif key == "backspace":
            self._typed = self._typed[:-1]
        elif key == "space":
            self._typed += " "
        elif key.startswith(("text:", "paste:")):
            self._typed += "".join(character for character in key.split(":", 1)[1] if character.isprintable())
        elif key == "enter" and self._form is not None:
            self._accept_field()
        self._invalidate()

    def _accept_field(self) -> None:
        if self._form is None or not self._typed.strip():
            return
        values: list[str] = [*self._form, self._typed.strip()]
        if len(values) < len(_ADD_FIELDS):
            self._form, self._typed = values, "1" if len(values) == len(_ADD_FIELDS) - 1 else ""
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
        """Render only cached state, keeping settings and navigation available during work."""
        with self._lock:
            result: Text = Text("Stan · ", style="bold")
            result.append("Auto włączone" if self._snapshot.get("auto_enabled") else "Auto wyłączone")
            if not self._connected:
                result.append(" · rozłączono, dane mogą być nieaktualne", style="yellow")
            result.append("\n")
            for index, name in enumerate(_TABS):
                result.append(f" {name} ", style="reverse" if self._tab == index else "")
            result.append("\n\n")
            content: list[Text] = self._content(columns)
            visible: int = max(rows - 9, 1)
            self._selected = min(self._selected, max(len(content) - 1, 0))
            self._offset = min(self._offset, self._selected)
            self._offset = max(self._offset, self._selected - visible + 1)
            for index in range(self._offset, min(len(content), self._offset + visible)):
                result.append("\u276f " if index == self._selected else "  ")
                result.append_text(content[index])
                result.append("\n")
            if not content:
                result.append("Brak pozycji\n", style="dim")
            result.append("\n" + self._notice + "\n", style="yellow")
            if self._tab == _Tab.SUBSCRIPTIONS and self._snapshot.get("subscriptions_problem"):
                result.append(_safe_text(self._snapshot["subscriptions_problem"]) + "\n", style="yellow")
            if self._form is not None:
                result.append(f"{_ADD_FIELDS[len(self._form)]}: {self._typed}▏\nEnter · Esc anuluje")
            else:
                result.append(
                    "Tab widok · O Auto wł./wył. · R uruchom teraz · M wybierz pliki · U ustawienia · Esc menu\n",
                    style="dim",
                )
                if self._tab == _Tab.SUBSCRIPTIONS:
                    result.append("D dodaj · W włącz/wyłącz · X usuń wpis · B powiąż sezon · F sprawdź", style="dim")
                elif self._tab == _Tab.TRANSFERS:
                    result.append("P wstrzymaj · W wznów · X anuluj (pliki zostają) · A inne wydanie", style="dim")
                elif self._tab == _Tab.PROGRESS:
                    result.append("C anuluj zaznaczone zlecenie", style="dim")
                elif self._tab == _Tab.FILES:
                    result.append(
                        "W Auto katalogu · M wybór i regeneracja · F folder · P ponów przenoszenie", style="dim"
                    )
            return result

    def _content(self, columns: int) -> list[Text]:
        if self._binding is not None:
            return [Text(_safe_text(candidate.romaji)) for candidate in self._candidates]
        if self._tab == _Tab.PROGRESS:
            progress: list[Text] = [
                line for _, progress in self._runs.values() for line in progress.render(max(columns - 2, 1)).split("\n")
            ]
            progress.extend(
                Text(f"{_safe_text(item.get('problem'))} · M wybierz pliki i dokończ pracę", style="yellow")
                for item in _rows(self._snapshot.get("recovery_problems"))
            )
            return progress
        if self._tab == _Tab.TRANSFERS:
            messages: dict[str, object] = {
                str(item.get("info_hash")): item.get("problem") for item in _rows(self._snapshot.get("acquisitions"))
            }
            content: list[Text] = [
                Text(
                    f"{float(str(item.get('progress', 0))) * 100:5.1f}% · {item.get('state')} · "
                    f"{_safe_text(item.get('name', ''))}"
                )
                + Text(
                    f" · {messages[str(item['info_hash'])]}" if messages.get(str(item.get("info_hash"))) else "",
                    style="yellow",
                )
                for item in self._transfer_rows()
            ]
            problem: object = self._snapshot.get("transfers_problem")
            if problem:
                content.append(Text(_safe_text(str(problem)), style="yellow"))
            return content
        if self._tab == _Tab.FILES:
            policy: AutomationPolicy = self._policy()
            content = [
                Text(
                    _safe_text(str(item.get("name")))
                    + (
                        " · Auto włączone · "
                        if policy.effective_auto(str(item["directory"]))
                        else " · Auto wyłączone · "
                    )
                    + ", ".join(
                        f"{product.get('kind')}: {product.get('state')}" for product in _rows(item.get("products"))
                    )
                )
                for item in _rows(self._snapshot.get("library"))
            ]
            content.extend(
                Text(
                    f"{_safe_text(item.get('name'))} · {_safe_text(item.get('problem') or 'przenoszenie do ready')}",
                    style="yellow",
                )
                for item in _rows(self._snapshot.get("relocations"))
            )
            return content
        return [
            Text(
                f"{'włączona' if item.get('enabled') else 'wyłączona'} · {_safe_text(str(item.get('series')))} "
                f"[{_safe_text(str(item.get('group')))}] · odc. {item.get('next_episode')} · "
                f"{item.get('end_state')}" + _schedule_label(item)
            )
            for item in self._subscriptions
        ]

    def _policy(self, *, auto_enabled: bool | None = None) -> AutomationPolicy:
        exceptions: object = self._snapshot.get("directory_exceptions", {})
        return AutomationPolicy(
            auto_enabled=bool(self._snapshot.get("auto_enabled")) if auto_enabled is None else auto_enabled,
            directory_exceptions={str(key): value for key, value in exceptions.items() if isinstance(value, bool)}
            if isinstance(exceptions, Mapping)
            else {},
        )

    def _transfer_rows(self) -> list[Mapping[str, object]]:
        rows: list[Mapping[str, object]] = _rows(self._snapshot.get("transfers"))
        known: set[str] = {str(item["info_hash"]) for item in rows}
        rows.extend(
            {
                "info_hash": item["info_hash"],
                "name": f"{item.get('directory', '')} · odc. {item.get('episode', '?')}",
                "state": "wymaga uwagi" if item.get("problem") else "brak potwierdzenia klienta",
                "progress": 0,
            }
            for item in _rows(self._snapshot.get("acquisitions"))
            if str(item.get("info_hash")) not in known
            and item.get("state") != "complete"
            and (item.get("state") != "failed" or item.get("problem"))
        )
        return rows


def _rows(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _schedule_label(item: Mapping[str, object]) -> str:
    if item.get("anilist_id") is None:
        return " · bez kalendarza, sprawdzanie co godzinę"
    episodes: list[Mapping[str, object]] = _rows(item.get("episodes"))
    dates: list[str] = [
        str(episode["due_at"]) for episode in episodes if episode.get("due_at") and episode.get("state") == "pending"
    ]
    if not dates:
        return " · brak następnego terminu"
    return " · sprawdzenie " + datetime.fromisoformat(min(dates)).astimezone().strftime("%d.%m %H:%M")


def _safe_text(value: object) -> str:
    return sanitize_event_message(str(value)) or ""


def _open_folder(root: Path, directory: str) -> None:
    folder: Path = (root / directory).resolve()
    if not folder.is_relative_to(root.resolve()) or not folder.is_dir():
        message: str = "Folder is no longer available in the workspace"
        raise ValueError(message)
    if sys.platform == "win32":
        os.startfile(folder)  # noqa: S606 - explicitly selected workspace directory
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])  # noqa: S603 - desktop opener
