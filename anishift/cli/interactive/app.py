"""Single-event-loop interactive command line for AniShift."""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Final

from rich.text import Text

from anishift import __version__
from anishift.application import AppService
from anishift.application.cancellation import EventCancellationToken
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.home import HomeAction, brand_for_geometry, working_directory_label
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import (
    AutoGeometry,
    HomeGeometry,
    TerminalRenderer,
    resolve_auto_geometry,
    resolve_home_geometry,
    status_line,
)
from anishift.cli.interactive.settings import SettingsController, SettingsResult
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun, execute_auto_run, prepare_auto_run
from anishift.errors import AniShiftError
from anishift.utils.logger import get_logger

__all__ = ["run_interactive"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_LOG_LOCATION: Final[str] = "logs/anishift.log.jsonl"
"""Relative location of the process diagnostic log."""

_HOME_CHOICES: Final[tuple[tuple[str, HomeAction], ...]] = (
    ("Auto", HomeAction.AUTO),
    ("Ręczny", HomeAction.MANUAL),
    ("Ustawienia", HomeAction.SETTINGS),
    ("Wyjście", HomeAction.EXIT),
)
"""Home actions in their product-defined display order."""

_HOME_HINT: Final[str] = "↑↓ · Enter"
"""Compact keyboard hint shown below Home choices."""

_HOME_POINTER: Final[str] = "\u276f"
"""Pointer glyph shown beside the active Home choice."""

_TEMPORARY_ACTIONS: Final[dict[HomeAction, str]] = {
    HomeAction.MANUAL: "Tryb ręczny pojawi się w następnym etapie",
}
"""Neutral messages for actions deferred beyond the current plan."""

_REFUSAL_MESSAGES: Final[dict[str, str]] = {
    "The workspace holds no source group to run.": "Workspace nie zawiera materiału do uruchomienia",
    "No discovered source group is ready to run.": "Żadna wykryta grupa nie jest gotowa do uruchomienia",
    "The plan cannot run because of a blocking problem.": "Plan nie może zostać uruchomiony",
}
"""Polish presentation of stable UI-neutral Auto refusals."""

_REFUSAL_SUGGESTIONS: Final[dict[str, str]] = {
    "Put a video or a subtitle file in the workspace and run the preset again.": (
        "Umieść plik wideo lub napisów w workspace i spróbuj ponownie"
    ),
    "Give every group usable text, resolve its conflict, then run the preset again.": (
        "Usuń konflikty i zapewnij każdej grupie użyteczne napisy"
    ),
}
"""Polish presentation of stable UI-neutral Auto suggestions."""


class _ViewMode(StrEnum):
    """Identify the screen content rendered by the single terminal owner."""

    HOME = "home"
    PREPARING = "preparing"
    AUTO = "auto"
    AUTO_DONE = "auto_done"
    SETTINGS = "settings"
    MESSAGE = "message"


class _InteractiveApplication:
    """Coordinate application work with one Prompt Toolkit renderer."""

    def __init__(self, service: AppService) -> None:
        self._service: AppService = service
        self._lock: threading.Lock = threading.Lock()
        self._mode: _ViewMode = _ViewMode.HOME
        self._selected: int = 0
        self._message: Text = Text()
        self._progress: RichRunProgress | None = None
        self._settings: SettingsController | None = None
        self._cancel_requested: bool = False
        self._preflight_cancel: EventCancellationToken | None = None
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._directory: str = working_directory_label()
        self._renderer: TerminalRenderer = TerminalRenderer(self._render_frame, self._handle_key)

    def run(self) -> None:
        """Run the interactive session until Home exits."""
        self._renderer.run()

    def _handle_key(self, key: str) -> None:
        with self._lock:
            mode: _ViewMode = self._mode
        if mode is _ViewMode.SETTINGS:
            self._handle_settings_key(key)
            return
        if key == "interrupt":
            self._interrupt(mode)
            return
        if mode is _ViewMode.HOME:
            self._handle_home_key(key)
            return
        if mode in {_ViewMode.AUTO_DONE, _ViewMode.MESSAGE}:
            self._show_home()

    def _handle_home_key(self, key: str) -> None:
        if key == "up":
            with self._lock:
                self._selected = (self._selected - 1) % len(_HOME_CHOICES)
            self._renderer.invalidate()
            return
        if key == "down":
            with self._lock:
                self._selected = (self._selected + 1) % len(_HOME_CHOICES)
            self._renderer.invalidate()
            return
        if key != "enter":
            return
        with self._lock:
            action: HomeAction = _HOME_CHOICES[self._selected][1]
        if action is HomeAction.EXIT:
            self._renderer.exit()
        elif action is HomeAction.AUTO:
            self._start_auto()
        elif action is HomeAction.SETTINGS:
            self._show_settings()
        else:
            self._show_message(Text(_TEMPORARY_ACTIONS[action]))

    def _handle_settings_key(self, key: str) -> None:
        with self._lock:
            controller: SettingsController | None = self._settings
        if controller is None:
            self._show_home()
            return
        result: SettingsResult = controller.handle_key(key)
        if result is SettingsResult.BACK_HOME:
            self._show_home()
            return
        self._renderer.invalidate()

    def _interrupt(self, mode: _ViewMode) -> None:
        if mode is _ViewMode.HOME:
            logger.info("Interactive session interrupted")
            self._renderer.exit()
            return
        if mode is _ViewMode.PREPARING:
            preflight_cancel: EventCancellationToken | None
            with self._lock:
                self._generation += 1
                self._mode = _ViewMode.HOME
                self._progress = None
                preflight_cancel = self._preflight_cancel
                self._preflight_cancel = None
            if preflight_cancel is not None:
                preflight_cancel.cancel()
            self._renderer.invalidate()
            return
        if mode is _ViewMode.AUTO:
            progress: RichRunProgress | None
            with self._lock:
                self._generation += 1
                self._cancel_requested = True
                self._mode = _ViewMode.HOME
                progress = self._progress
                self._progress = None
            run_id: str | None = progress.run_id if progress is not None else None
            if run_id is not None:
                self._service.cancel(run_id)
            self._renderer.invalidate()
            return
        self._show_home()

    def _start_auto(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._generation += 1
            generation: int = self._generation
            self._mode = _ViewMode.PREPARING
            self._progress = None
            self._message = Text()
            self._cancel_requested = False
            self._preflight_cancel = EventCancellationToken()
            self._worker = threading.Thread(
                target=self._prepare_and_run,
                args=(generation,),
                name="anishift-auto",
                daemon=True,
            )
            worker: threading.Thread = self._worker
        self._renderer.invalidate()
        worker.start()

    def _prepare_and_run(self, generation: int) -> None:
        try:
            with self._lock:
                preflight_cancel: EventCancellationToken | None = self._preflight_cancel
            if preflight_cancel is None:
                return
            preset_id: str = self._service.default_preset_id()
            preparation: PreparedAutoRun | AutoRunRefusal = prepare_auto_run(
                self._service,
                preset_id,
                cancel=preflight_cancel,
            )
            with self._lock:
                if generation != self._generation:
                    return
                self._preflight_cancel = None
            if isinstance(preparation, AutoRunRefusal):
                self._finish_with_message(generation, _refusal_text(preparation))
                return
            progress = RichRunProgress(
                preparation,
                self._renderer.invalidate,
                self._on_run_started,
            )
            with self._lock:
                if generation != self._generation:
                    return
                self._progress = progress
                self._mode = _ViewMode.AUTO
            self._renderer.invalidate()
            with progress:
                execute_auto_run(self._service, preparation, progress)
            with self._lock:
                if generation != self._generation:
                    return
                self._mode = _ViewMode.AUTO_DONE
                self._cancel_requested = False
                self._worker = None
            self._renderer.invalidate()
        except (AniShiftError, OSError) as problem:
            with self._lock:
                if generation != self._generation:
                    return
            logger.warning("Interactive automatic run failed", error_class=type(problem).__name__)
            self._finish_with_message(generation, _problem_text(problem))

    def _on_run_started(self, run_id: str) -> None:
        with self._lock:
            cancel_requested: bool = self._cancel_requested
        if cancel_requested:
            self._service.cancel(run_id)

    def _finish_with_message(self, generation: int, message: Text) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._message = message
            self._mode = _ViewMode.MESSAGE
            self._progress = None
            self._cancel_requested = False
            self._preflight_cancel = None
            self._worker = None
        self._renderer.invalidate()

    def _show_message(self, message: Text) -> None:
        with self._lock:
            self._message = message
            self._mode = _ViewMode.MESSAGE
        self._renderer.invalidate()

    def _show_settings(self) -> None:
        controller: SettingsController = SettingsController(self._service, self._renderer.invalidate)
        with self._lock:
            self._settings = controller
            self._mode = _ViewMode.SETTINGS
            self._message = Text()
        self._renderer.invalidate()

    def _show_home(self) -> None:
        with self._lock:
            self._mode = _ViewMode.HOME
            self._message = Text()
            self._progress = None
            self._settings = None
            self._cancel_requested = False
        self._renderer.invalidate()

    def _render_frame(self, columns: int, rows: int) -> Text:
        with self._lock:
            mode: _ViewMode = self._mode
            selected: int = self._selected
            message: Text = self._message
            progress: RichRunProgress | None = self._progress
            settings: SettingsController | None = self._settings
        if mode is _ViewMode.HOME:
            content: Text = _home_content(columns, rows, selected)
        elif mode is _ViewMode.PREPARING:
            content = _preparing_content(columns, rows)
        elif mode in {_ViewMode.AUTO, _ViewMode.AUTO_DONE} and progress is not None:
            content = _auto_content(columns, rows, progress)
        elif mode is _ViewMode.SETTINGS and settings is not None:
            content = settings.render(columns, rows)
        else:
            content = _message_content(columns, rows, message)
        return _fit_frame(content, __version__, self._directory, columns, rows)


def run_interactive(service: AppService) -> None:
    """Run the single-owner interactive terminal application."""
    _InteractiveApplication(service).run()


def _home_content(columns: int, rows: int, selected: int) -> Text:
    geometry: HomeGeometry = resolve_home_geometry(columns, rows)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand_for_geometry(geometry))
    content.append("\n\n")
    for index, (label, _action) in enumerate(_HOME_CHOICES):
        content.append(" " * geometry.left_padding)
        if index == selected:
            content.append(f"{_HOME_POINTER} ", style="purple_bold")
            content.append(label, style="purple_bold")
        else:
            content.append(f"  {label}", style="white_bold")
        content.append("\n")
    content.append(" " * geometry.left_padding)
    content.append(f"  {_HOME_HINT}", style="gray")
    return content


def _preparing_content(columns: int, rows: int) -> Text:
    geometry: AutoGeometry = resolve_auto_geometry(columns, rows, 1)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand_for_geometry(geometry))
    return content


def _auto_content(
    columns: int,
    rows: int,
    progress: RichRunProgress,
) -> Text:
    geometry: AutoGeometry = resolve_auto_geometry(columns, rows, progress.row_count)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand_for_geometry(geometry))
    content.append("\n")
    content.append_text(progress.render(columns))
    return content


def _message_content(columns: int, rows: int, message: Text) -> Text:
    geometry: HomeGeometry = resolve_home_geometry(columns, rows)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand_for_geometry(geometry))
    content.append("\n\n")
    content.append_text(message)
    content.append("\n\nNaciśnij dowolny klawisz, aby wrócić", style="gray")
    return content


def _fit_frame(content: Text, version: str, directory: str, columns: int, rows: int) -> Text:
    body_rows: int = max(rows - 1, 0)
    lines: list[Text] = list(content.split("\n"))[:body_rows]
    lines.extend(Text() for _ in range(body_rows - len(lines)))
    lines.append(Text(status_line(version, directory, columns), style="gray"))
    frame = Text()
    for index, line in enumerate(lines):
        frame.append_text(line)
        if index < len(lines) - 1:
            frame.append("\n")
    return frame


def _refusal_text(refusal: AutoRunRefusal) -> Text:
    message = Text(_REFUSAL_MESSAGES.get(refusal.message, _safe(refusal.message)), style="warning")
    for blocker in refusal.blockers:
        message.append(f"\n  {_safe(blocker.scope)}: {_safe(blocker.message)}")
    if refusal.suggestion:
        suggestion: str = _REFUSAL_SUGGESTIONS.get(refusal.suggestion, _safe(refusal.suggestion))
        message.append(f"\n  {suggestion}", style="gray")
    return message


def _problem_text(problem: AniShiftError | OSError) -> Text:
    message = Text(f"Błąd · {_safe(str(problem))}", style="error")
    suggestion: str = problem.context.suggestion if isinstance(problem, AniShiftError) else ""
    if suggestion:
        message.append(f"\n  {_safe(suggestion)}", style="gray")
    message.append(f"\nSzczegóły: {_LOG_LOCATION}", style="gray")
    return message


def _safe(text: str) -> str:
    return (sanitize_event_message(text) or "").rstrip(".")
