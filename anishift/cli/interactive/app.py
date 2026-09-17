"""Single-event-loop interactive command line for AniShift."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Final

from rich.text import Text

from anishift import __version__
from anishift.application import (
    AppService,
    AutoPreset,
    InspectedWorkspace,
    PlanPreview,
    RetryProposal,
    RunResult,
    ready_group_ids,
)
from anishift.application.cancellation import EventCancellationToken
from anishift.application.events import sanitize_event_message
from anishift.cli.exit_codes import EXIT_CANCELLED, EXIT_INCOMPLETE, EXIT_REFUSED, EXIT_SUCCESS, run_exit_code
from anishift.cli.interactive.anime import AnimeController
from anishift.cli.interactive.home import HomeAction, brand_for_geometry, working_directory_label
from anishift.cli.interactive.manual import ManualController, ManualResult, ManualRun
from anishift.cli.interactive.mascot import MascotController, MascotState
from anishift.cli.interactive.mascot_native import MASCOT_REST_TOP_ROWS, NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.menu import with_footer
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import (
    TEXT_MASCOT_SIZE,
    AutoGeometry,
    HomeGeometry,
    TerminalRenderer,
    resolve_auto_geometry,
    resolve_home_geometry,
    status_line,
)
from anishift.cli.interactive.settings import SettingsController, SettingsResult
from anishift.cli.interactive.state import StateController, StateResult, refusal_text
from anishift.cli.resident import ResidentSession
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun, execute_plan, prepare_auto_run
from anishift.errors import AniShiftError
from anishift.paths import config_dir, log_path
from anishift.platform.local_control import ControlError, ControlErrorCode
from anishift.utils.logger import get_logger

__all__ = ["run_interactive"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_LOG_LOCATION: Final[str] = log_path().relative_to(config_dir().parent).as_posix()
"""Relative location of the process diagnostic log."""

_HOME_CHOICES: Final[tuple[tuple[str, HomeAction], ...]] = (
    ("Panel", HomeAction.STATE),
    ("Ręczny", HomeAction.MANUAL),
    ("Ustawienia", HomeAction.SETTINGS),
    ("Wyjście", HomeAction.EXIT),
)
"""Home actions in their product-defined display order."""

_HOME_HINT: Final[str] = "↑↓ · Enter"
"""Compact keyboard hint shown below Home choices."""

_HOME_FOOTER_ROWS: Final[int] = 2
"""Rows reserved for the keyboard hint and application status."""

_HOME_POINTER: Final[str] = "\u276f"
"""Pointer glyph shown beside the active Home choice."""

_QUEUE_SCROLL_KEYS: Final[frozenset[str]] = frozenset({"up", "down", "pageup", "pagedown", "home", "end"})
"""Keys that move the Auto queue instead of leaving the view."""

_QUEUE_WHEEL_ROWS: Final[int] = 3
"""Queue rows one wheel notch moves."""

_QUEUE_MARKER_ROWS: Final[int] = 2
"""Rows reserved above and below the queue for the hidden-row markers."""

_MINIMUM_BRANDED_ROWS: Final[int] = 8
"""Minimum terminal height for a brand, gap, queue markers and progress."""

_BATCH_CLOSE_SECONDS: Final[float] = 10.0
"""Seconds a finished batch window stays readable before it closes itself."""

_BATCH_CLOSING: Final[str] = "Okno zamknie się za {seconds} s · dowolny klawisz zamyka"
"""Footer of a finished batch window while it counts down."""

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


@dataclass(slots=True)
class _QueueView:
    """Own the scroll position of the Auto queue without touching its row order."""

    offset: int = 0
    visible: int = 1
    following: bool = True

    def navigate(self, key: str, total: int) -> None:
        """Move the view by one keyboard step, page or edge."""
        if key == "end":
            self.following = True
            return
        stride: int = max(self.visible - 1, 1)
        moves: dict[str, int] = {
            "up": -1,
            "down": 1,
            "pageup": -stride,
            "pagedown": stride,
            "home": -total,
        }
        self.move(moves.get(key, 0), total)

    def move(self, rows: int, total: int) -> None:
        """Scroll independently of active work until End explicitly resumes following."""
        last: int = _last_offset(total, self.visible)
        self.offset = min(max(self.offset + rows, 0), last)
        self.following = False

    def fit(self, row: int, total: int, visible: int) -> None:
        """Adopt the row budget known only at render time and follow active work."""
        self.visible = max(visible, 1)
        last: int = _last_offset(total, self.visible)
        self.offset = min(self.offset, last)
        if self.following:
            self.offset = min(max(row - self.visible + 1, 0), last)


class _ViewMode(StrEnum):
    """Identify the screen content rendered by the single terminal owner."""

    HOME = "home"
    PREPARING = "preparing"
    MANUAL_PREPARING = "manual_preparing"
    MANUAL = "manual"
    AUTO = "auto"
    AUTO_DONE = "auto_done"
    SETTINGS = "settings"
    STATE = "state"
    MESSAGE = "message"


class _InteractiveApplication:
    """Coordinate application work with one Prompt Toolkit renderer."""

    def __init__(
        self,
        service: AppService,
        *,
        batch: tuple[str, ...] | None = None,
        resident: ResidentSession | None = None,
        show_state: bool = False,
        terminal_window: str | None = None,
    ) -> None:
        self._service: AppService = service
        self._resident: ResidentSession | None = resident
        self._home_choices: tuple[tuple[str, HomeAction], ...] = _HOME_CHOICES
        self._terminal_window: str | None = terminal_window
        self._execution: ResidentSession | None = None
        self._batch: tuple[str, ...] | None = batch
        self._exit_code: int = EXIT_SUCCESS
        self._closing_at: float | None = None
        self._lock: threading.Lock = threading.Lock()
        self._mode: _ViewMode = _ViewMode.STATE if show_state else _ViewMode.HOME
        self._selected: int = 0
        self._message: Text = Text()
        self._message_view: _QueueView = _QueueView(following=False)
        self._progress: RichRunProgress | None = None
        self._queue: _QueueView = _QueueView()
        self._settings: SettingsController | None = None
        self._return_mode: _ViewMode = _ViewMode.HOME
        self._state: StateController | None = None
        self._manual: ManualController | None = None
        self._cancel_requested: bool = False
        self._preflight_cancel: EventCancellationToken | None = None
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._directory: str = working_directory_label()
        self._renderer: TerminalRenderer = TerminalRenderer(
            self._render_frame,
            self._handle_key,
            self._handle_idle,
            self._handle_scroll,
        )
        self._mascot: MascotController = MascotController(self._renderer.invalidate)

    def run(self) -> int:
        """Run the session until Home exits, or until one batch finishes and its window closes."""
        if self._resident is not None:
            self._state = StateController(self._resident, self._renderer.invalidate)
            self._state.attach_anime(AnimeController(self._service, self._renderer.invalidate, resident=self._resident))
        if self._batch is None:
            self._start_prewarm()
        else:
            self._start_auto()
        try:
            self._renderer.run()
        finally:
            self._finish_session()
        return self._exit_code

    def _finish_session(self) -> None:
        """Run every teardown step, settings before the session they need, and never let one failure skip the rest."""
        for step in (self._close_state, self._close_settings, self._cancel_active_work, self._mascot.close):
            try:
                step()
            except (AniShiftError, ControlError, OSError, ValueError) as problem:
                logger.warning("A panel teardown step failed", step=step.__name__, error_class=type(problem).__name__)

    def _close_state(self) -> None:
        if self._state is not None:
            self._state.close()

    def _cancel_active_work(self) -> None:
        """Signal every active operation before the terminal owner closes."""
        with self._lock:
            self._cancel_requested = self._resident is None
            preflight: EventCancellationToken | None = self._preflight_cancel
            progress: RichRunProgress | None = self._progress
            manual: ManualController | None = self._manual
        if preflight is not None:
            preflight.cancel()
        if manual is not None:
            manual.cancel()
        if self._resident is not None:
            self._resident.close()
            if self._execution is not None:
                self._execution.close()
            return
        if progress is not None and progress.run_id is not None:
            self._service.cancel(progress.run_id)

    def _close_settings(self) -> None:
        """Let the settings panel persist a delayed edit before it stops existing."""
        with self._lock:
            controller: SettingsController | None = self._settings
        if controller is not None:
            controller.close()
            if self._resident is not None:
                self._resident.command("reload_settings")
        with self._lock:
            self._settings = None

    def _start_prewarm(self) -> None:
        """Inspect the workspace while Home is idle so Auto and Manual start at once."""
        threading.Thread(target=self._prewarm_workspace, name="anishift-prewarm", daemon=True).start()

    def _prewarm_workspace(self) -> None:
        try:
            (self._resident or self._service).discover()
        except (AniShiftError, OSError) as problem:
            logger.info("Workspace prewarm skipped", error_class=type(problem).__name__)

    def _copy_selection(self, mode: _ViewMode) -> bool:
        controller: ManualController | None = self._manual if mode is _ViewMode.MANUAL else None
        return controller is not None and controller.copy_selection()

    def _handle_key(self, key: str) -> None:
        with self._lock:
            mode: _ViewMode = self._mode
        if mode is _ViewMode.SETTINGS:
            self._handle_settings_key(key)
            return
        if mode is _ViewMode.STATE:
            self._handle_state_key(key)
            return
        if key == "interrupt":
            if self._copy_selection(mode):
                self._renderer.invalidate()
            else:
                self._interrupt(mode)
            return
        screen: Callable[[str], None] | None = {
            _ViewMode.HOME: self._handle_home_key,
            _ViewMode.MANUAL: self._handle_manual_key,
        }.get(mode)
        if screen is not None:
            screen(key)
            return
        if mode in {_ViewMode.AUTO, _ViewMode.AUTO_DONE} and key in _QUEUE_SCROLL_KEYS:
            self._navigate_queue(key)
            return
        if mode is _ViewMode.MESSAGE and key in _QUEUE_SCROLL_KEYS:
            with self._lock:
                self._message_view.navigate(key, len(self._message.split("\n")))
            self._renderer.invalidate()
            return
        if mode in {_ViewMode.AUTO_DONE, _ViewMode.MESSAGE}:
            self._leave_finished_view()

    def _leave_finished_view(self) -> None:
        """Return to the initiating view, or close a batch after its outcome was read."""
        if self._batch is not None:
            self._renderer.exit()
            return
        self._return_to_context()

    def _close_batch(self, exit_code: int) -> None:
        """Stop the work of a batch window and close it with the given outcome."""
        self._exit_code = exit_code
        self._cancel_active_work()
        self._renderer.exit()

    def _handle_idle(self) -> None:
        if self._mode is _ViewMode.STATE and self._state is not None:
            self._state.poll()
        if self._state is not None and self._state.finished():
            self._renderer.exit()
            return
        navigation: Mapping[str, object] | None = (
            self._state.take_open_request()
            if self._state is not None and self._mode is not _ViewMode.SETTINGS
            else None
        )
        if self._state is not None and navigation is not None:
            from anishift.platform.tray import raise_panel  # noqa: PLC0415

            raise_panel(self._terminal_window)
            if navigation.get("tab") == "library":
                self._state.show_library(navigation)
                self._show_state()
            else:
                self._show_home()
        with self._lock:
            controller: SettingsController | None = self._settings if self._mode is _ViewMode.SETTINGS else None
            closing_at: float | None = self._closing_at
        if controller is not None:
            controller.flush_pending()
        if closing_at is not None and monotonic() >= closing_at:
            self._renderer.exit()

    def _handle_scroll(self, direction: int) -> None:
        with self._lock:
            mode: _ViewMode = self._mode
            controller: SettingsController | None = self._settings if mode is _ViewMode.SETTINGS else None
            progress: RichRunProgress | None = self._progress
        if mode is _ViewMode.STATE and self._state is not None:
            self._state.scroll(direction)
            return
        if mode is _ViewMode.MESSAGE:
            self._message_view.move(direction * _QUEUE_WHEEL_ROWS, len(self._message.split("\n")))
            self._renderer.invalidate()
            return
        if mode in {_ViewMode.AUTO, _ViewMode.AUTO_DONE} and progress is not None:
            self._queue.move(direction * _QUEUE_WHEEL_ROWS, progress.row_count)
            self._renderer.invalidate()
            return
        if controller is None:
            return
        controller.scroll(direction)
        self._renderer.invalidate()

    def _navigate_queue(self, key: str) -> None:
        with self._lock:
            progress: RichRunProgress | None = self._progress
        if progress is None:
            return
        self._queue.navigate(key, progress.row_count)
        self._renderer.invalidate()

    def _handle_home_key(self, key: str) -> None:
        if key == "up":
            with self._lock:
                self._selected = (self._selected - 1) % len(self._home_choices)
            self._renderer.invalidate()
            return
        if key == "down":
            with self._lock:
                self._selected = (self._selected + 1) % len(self._home_choices)
            self._renderer.invalidate()
            return
        if key != "enter":
            return
        with self._lock:
            action: HomeAction = self._home_choices[self._selected][1]
        if action is HomeAction.EXIT:
            self._renderer.exit()
        elif action is HomeAction.STATE:
            self._show_state()
        elif action is HomeAction.SETTINGS:
            self._show_settings()
        else:
            self._start_manual()

    def _handle_settings_key(self, key: str) -> None:
        with self._lock:
            controller: SettingsController | None = self._settings
        if controller is None:
            self._show_home()
            return
        result: SettingsResult = controller.handle_key(key)
        if result is SettingsResult.BACK_HOME:
            self._return_to_context()
            return
        self._renderer.invalidate()

    def _handle_manual_key(self, key: str) -> None:
        with self._lock:
            controller: ManualController | None = self._manual
        if controller is None:
            self._show_home()
            return
        result: ManualResult = controller.handle_key(key)
        if result is ManualResult.BACK_HOME:
            self._return_to_context()
            return
        if result is ManualResult.START_RUN:
            prepared: ManualRun | None = controller.take_ready_run()
            if prepared is not None:
                self._start_manual_run(prepared)
                return
        self._renderer.invalidate()

    def _interrupt(self, mode: _ViewMode) -> None:
        if self._batch is not None:
            self._close_batch(EXIT_CANCELLED)
            return
        if mode is _ViewMode.HOME:
            logger.info("Interactive session interrupted")
            self._renderer.exit()
            return
        if mode in {_ViewMode.PREPARING, _ViewMode.MANUAL_PREPARING}:
            preflight_cancel: EventCancellationToken | None
            with self._lock:
                self._generation += 1
                self._mode = _ViewMode.HOME
                self._progress = None
                self._manual = None
                preflight_cancel = self._preflight_cancel
                self._preflight_cancel = None
            if preflight_cancel is not None:
                preflight_cancel.cancel()
            self._mascot.reset()
            if mode is _ViewMode.MANUAL_PREPARING:
                self._return_to_context()
            self._renderer.invalidate()
            return
        if mode is _ViewMode.MANUAL:
            with self._lock:
                self._generation += 1
                manual: ManualController | None = self._manual
            if manual is not None:
                manual.cancel()
            self._return_to_context()
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
                self._cancel_run(run_id)
            self._mascot.reset()
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
        self._mascot.show(MascotState.DISCOVER)
        if self._resident is not None:
            self._show_state(processing=True, notice="Przygotowanie")
        worker.start()

    def _start_manual(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._return_mode = _ViewMode.STATE if self._mode is _ViewMode.STATE else _ViewMode.HOME
            self._generation += 1
            generation: int = self._generation
            self._mode = _ViewMode.MANUAL_PREPARING
            self._manual = None
            self._message = Text()
            self._preflight_cancel = EventCancellationToken()
            retry: RetryProposal | None = (
                self._state.take_manual_retry()
                if self._return_mode is _ViewMode.STATE and self._state is not None
                else None
            )
            self._worker = threading.Thread(
                target=self._prepare_manual,
                args=(generation, retry),
                name="anishift-manual-discovery",
                daemon=True,
            )
            worker: threading.Thread = self._worker
        self._renderer.invalidate()
        self._mascot.show(MascotState.DISCOVER)
        worker.start()

    def _prepare_manual(self, generation: int, retry: RetryProposal | None = None) -> None:
        backend: AppService | ResidentSession = self._service
        attached: bool = False
        try:
            if self._resident is not None:
                backend = self._resident.new_session()
            with self._lock:
                preflight_cancel: EventCancellationToken | None = self._preflight_cancel
            if preflight_cancel is None:
                return
            workspace: InspectedWorkspace = backend.discover(cancel=preflight_cancel)
            preflight_cancel.raise_if_cancelled()
            if not workspace.groups:
                self._finish_with_message(
                    generation, Text("Nie znaleziono materiału do przetworzenia", style="warning")
                )
                return
            preset: AutoPreset = self._service.get_preset(self._service.default_preset_id())
            controller: ManualController = ManualController(
                backend,
                workspace,
                preset,
                self._renderer.invalidate,
            )
            if retry is not None and isinstance(backend, ResidentSession):
                current: RetryProposal = backend.retry_proposal(retry.material_id)
                controller.prepare_retry(current)
            with self._lock:
                if generation != self._generation:
                    return
                self._preflight_cancel = None
                self._manual = controller
                attached = True
                self._mode = _ViewMode.MANUAL
                self._worker = None
            self._mascot.reset()
            self._renderer.invalidate()
        except (AniShiftError, OSError, ValueError) as problem:
            with self._lock:
                if generation != self._generation:
                    return
            logger.warning("Interactive manual discovery failed", error_class=type(problem).__name__)
            self._finish_with_message(generation, Text(refusal_text(problem), style="warning"))
        finally:
            if isinstance(backend, ResidentSession) and not attached:
                backend.close()

    def _start_manual_run(self, prepared: ManualRun) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._generation += 1
            generation: int = self._generation
            self._manual = None
            self._mode = _ViewMode.PREPARING
            self._progress = None
            self._cancel_requested = False
            self._worker = threading.Thread(
                target=self._execute_run,
                args=(generation, prepared),
                name="anishift-manual",
                daemon=True,
            )
            worker: threading.Thread = self._worker
        self._mascot.reset()
        self._renderer.invalidate()
        if self._resident is not None:
            self._show_state(processing=True, notice="Przygotowanie")
        worker.start()

    def _prepare_and_run(self, generation: int) -> None:
        try:
            with self._lock:
                preflight_cancel: EventCancellationToken | None = self._preflight_cancel
            if preflight_cancel is None:
                return
            preset_id: str = self._service.default_preset_id()
            preparation: PreparedAutoRun | ManualRun | AutoRunRefusal = self._prepared_auto(preset_id, preflight_cancel)
            with self._lock:
                if generation != self._generation:
                    if isinstance(preparation, ManualRun) and preparation.resident is not None:
                        preparation.resident.close()
                    return
                self._preflight_cancel = None
            if isinstance(preparation, AutoRunRefusal):
                self._finish_batch(EXIT_REFUSED)
                self._report_processing(generation, _refusal_text(preparation))
                return
            self._mascot.reset()
            self._execute_run(generation, preparation)
        except (AniShiftError, OSError) as problem:
            with self._lock:
                if generation != self._generation:
                    return
            code: str = _control_code(problem)
            if code == ControlErrorCode.ALREADY_PROCESSING.value:
                logger.info("Interactive Auto joined the work already in progress", control_code=code)
                self._follow_processing(generation)
                return
            logger.warning(
                "Interactive automatic run failed",
                error_class=type(problem).__name__,
                control_code=code,
                reason=_safe(str(problem)),
            )
            self._finish_batch(EXIT_REFUSED)
            self._report_processing(generation, _problem_text(problem))

    def _follow_processing(self, generation: int) -> None:
        """Show the run that already owns the requested groups, with nothing to explain."""
        if self._resident is None or self._state is None:
            self._finish_with_message(generation, Text())
            return
        self._mascot.reset()
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._preflight_cancel = None
            self._mode = _ViewMode.STATE
        self._state.set_notice("")
        self._state.show_processing()

    def _report_processing(self, generation: int, message: Text) -> None:
        if self._resident is None or self._state is None:
            self._finish_with_message(generation, message)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._preflight_cancel = None
        self._state.set_notice(message.plain)

    def _prepared_auto(
        self, preset_id: str, cancel: EventCancellationToken
    ) -> PreparedAutoRun | ManualRun | AutoRunRefusal:
        """Plan every ready group, or only the groups one batch window was opened for."""
        if self._resident is not None:
            return self._prepare_resident_auto(preset_id, cancel)
        if self._batch is None:
            return prepare_auto_run(self._service, preset_id, cancel=cancel)
        return prepare_auto_run(self._service, preset_id, cancel=cancel, group_ids=self._batch)

    def _prepare_resident_auto(self, preset_id: str, cancel: EventCancellationToken) -> ManualRun | AutoRunRefusal:
        if self._resident is None:
            msg = "The panel has no resident session"
            raise ValueError(msg)
        session: ResidentSession = self._resident.new_session()
        prepared: ManualRun | None = None
        try:
            workspace: InspectedWorkspace = session.discover(cancel=cancel)
            group_ids: tuple[str, ...] = self._batch or ready_group_ids(workspace.groups)
            if not group_ids:
                return AutoRunRefusal("Nie znaleziono gotowych odcinków")
            session.reserve(group_ids)
            preview: PlanPreview = session.plan_auto(group_ids, self._service.get_preset(preset_id))
            cancel.raise_if_cancelled()
            if not preview.can_execute:
                return AutoRunRefusal("Nie można przygotować wybranych odcinków")
            if not preview.tasks:
                return AutoRunRefusal("Wszystkie odcinki są już gotowe")
            prepared = ManualRun(workspace, preview, session)
            return prepared  # noqa: RET504
        finally:
            if prepared is None:
                session.close()

    def _execute_run(self, generation: int, prepared: PreparedAutoRun | ManualRun) -> None:
        backend: ResidentSession | None = prepared.resident if isinstance(prepared, ManualRun) else None
        try:
            if backend is not None and isinstance(prepared.plan, PlanPreview):
                backend.start(prepared.plan)
                with self._lock:
                    if generation != self._generation:
                        return
                    self._worker = None
                    self._manual = None
                self._report_processing(generation, Text())
                return
            progress: RichRunProgress = RichRunProgress(
                prepared,
                self._renderer.invalidate,
                self._on_run_started,
                mascot=self._mascot,
            )
            with self._lock:
                if generation != self._generation:
                    return
                self._progress = progress
                self._execution = backend
                self._mode = _ViewMode.AUTO
            self._renderer.invalidate()
            with progress:
                result: RunResult
                if isinstance(prepared.plan, PlanPreview):
                    if backend is None:
                        msg = "A resident preview requires its session"
                        raise ValueError(msg)
                    result = backend.execute(prepared.plan, progress)
                else:
                    result = execute_plan(self._service, prepared.plan, progress)
            self._finish_batch(run_exit_code(result))
            if not result.succeeded or result.warnings:
                self._finish_with_message(generation, _result_message(result, prepared.workspace))
                return
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
            logger.warning("Interactive run failed", error_class=type(problem).__name__)
            self._finish_batch(EXIT_INCOMPLETE)
            self._report_processing(generation, _problem_text(problem))
        finally:
            if backend is not None and backend is not self._resident:
                backend.close()

    def _finish_batch(self, exit_code: int) -> None:
        """Record the outcome of a batch window and start the countdown that closes it."""
        if self._batch is None:
            return
        with self._lock:
            self._exit_code = exit_code
            self._closing_at = monotonic() + _BATCH_CLOSE_SECONDS

    def _on_run_started(self, run_id: str) -> None:
        with self._lock:
            cancel_requested: bool = self._cancel_requested
        if cancel_requested:
            self._cancel_run(run_id)

    def _cancel_run(self, run_id: str) -> None:
        if self._execution is not None:
            self._execution.cancel(run_id)
        else:
            self._service.cancel(run_id)

    def _finish_with_message(self, generation: int, message: Text) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._message = message
            self._message_view = _QueueView(following=False)
            self._mode = _ViewMode.MESSAGE
            self._progress = None
            self._manual = None
            self._cancel_requested = False
            self._preflight_cancel = None
            self._worker = None
        self._mascot.show(MascotState.ERROR)
        self._renderer.invalidate()

    def _show_settings(self) -> None:
        controller: SettingsController = SettingsController(
            self._service, self._renderer.invalidate, resident=self._resident
        )
        self._mascot.reset()
        with self._lock:
            self._return_mode = _ViewMode.STATE if self._mode is _ViewMode.STATE else _ViewMode.HOME
            self._settings = controller
            self._mode = _ViewMode.SETTINGS
            self._message = Text()
        self._renderer.invalidate()

    def _return_to_context(self) -> None:
        if self._return_mode is _ViewMode.STATE:
            self._show_state()
        else:
            self._show_home()

    def _show_state(self, *, processing: bool = False, notice: str | None = None) -> None:
        self._close_settings()
        if self._state is None and self._resident is not None:
            self._state = StateController(self._resident, self._renderer.invalidate)
            self._state.attach_anime(AnimeController(self._service, self._renderer.invalidate, resident=self._resident))
        if processing and self._state is not None:
            self._state.show_processing()
        if notice is not None and self._state is not None:
            self._state.set_notice(notice)
        with self._lock:
            self._mode = _ViewMode.STATE
        self._renderer.invalidate()

    def _handle_state_key(self, key: str) -> None:
        if self._state is None:
            self._show_home()
            return
        result: StateResult = self._state.handle_key(key)
        action: Callable[[], None] | None = {
            StateResult.HOME: self._show_home,
            StateResult.SETTINGS: self._show_settings,
            StateResult.MANUAL: self._start_manual,
        }.get(result)
        if action is not None:
            action()

    def _show_home(self) -> None:
        self._close_settings()
        if self._state is not None:
            self._state.suspend()
        self._mascot.reset()
        with self._lock:
            self._mode = _ViewMode.HOME
            self._message = Text()
            self._progress = None
            self._manual = None
            self._cancel_requested = False
        self._renderer.invalidate()

    def _render_frame(self, columns: int, rows: int) -> Text:
        with self._lock:
            mode: _ViewMode = self._mode
            selected: int = self._selected
            message: Text = self._message
            message_view: _QueueView = self._message_view
            progress: RichRunProgress | None = self._progress
            settings: SettingsController | None = self._settings
            manual: ManualController | None = self._manual
            closing_at: float | None = self._closing_at
        mascot_state: MascotState = self._mascot.state
        native_size: tuple[int, int] | None = getattr(self._renderer, "native_mascot_size", None)
        animation_phase: int = getattr(self._renderer, "animation_phase", 0)
        if mode in {_ViewMode.HOME, _ViewMode.PREPARING, _ViewMode.MANUAL_PREPARING}:
            content: Text = _home_content(
                columns,
                rows,
                selected,
                mascot_state,
                native_size=native_size,
                animation_phase=animation_phase,
                choices=self._home_choices,
            )
        elif mode is _ViewMode.MANUAL and manual is not None:
            content = manual.render(columns, rows)
        elif mode in {_ViewMode.AUTO, _ViewMode.AUTO_DONE} and progress is not None:
            content = _auto_content(
                (columns, rows),
                progress,
                mascot_state,
                self._queue,
                native_size=native_size,
                animation_phase=animation_phase,
            )
        elif mode is _ViewMode.SETTINGS and settings is not None:
            content = settings.render(columns, rows)
        elif mode is _ViewMode.STATE and self._state is not None:
            content = self._state.render(columns, rows)
        else:
            content = _message_content(columns, rows, message, mascot_state, view=message_view)
        footer: str = self._directory if closing_at is None else _closing_label(closing_at)
        return _fit_frame(content, __version__, footer, columns, rows)


def run_interactive(
    service: AppService,
    *,
    batch: Sequence[str] | None = None,
    resident: ResidentSession | None = None,
    show_state: bool = False,
    terminal_window: str | None = None,
) -> int:
    """Run the single-owner interactive session; a batch runs its groups and closes on its own."""
    groups: tuple[str, ...] | None = tuple(batch) if batch is not None else None
    return _InteractiveApplication(
        service, batch=groups, resident=resident, show_state=show_state, terminal_window=terminal_window
    ).run()


def _closing_label(closing_at: float) -> str:
    remaining: int = max(int(closing_at - monotonic() + 0.999), 0)
    return _BATCH_CLOSING.format(seconds=remaining)


def _home_content(  # noqa: PLR0913
    columns: int,
    rows: int,
    selected: int,
    mascot_state: MascotState,
    *,
    native_size: tuple[int, int] | None = None,
    animation_phase: int = 0,
    choices: tuple[tuple[str, HomeAction], ...] = _HOME_CHOICES,
) -> Text:
    if rows < max(_MINIMUM_BRANDED_ROWS, len(choices) + 3):
        return _small_home_content(columns, rows, selected, choices)
    geometry: HomeGeometry = resolve_home_geometry(columns, rows, native_size or TEXT_MASCOT_SIZE)
    brand: Text = brand_for_geometry(
        geometry, mascot_state, native_mascot=native_size is not None, animation_phase=animation_phase
    )
    brand_rows: int = len(brand.split("\n"))
    menu_rows: int = len(choices) + 1
    body_rows: int = max(rows - 1, 1)
    resting: Text = brand_for_geometry(geometry, mascot_state, native_mascot=native_size is not None)
    resting_top: int = next(
        (
            index
            for index, line in enumerate(resting.split("\n"))
            if line.plain.replace(NATIVE_MASCOT_ANCHOR, "").strip()
        ),
        brand_rows,
    )
    if native_size is not None and geometry.show_mascot:
        resting_top = min(resting_top, MASCOT_REST_TOP_ROWS)
    free_rows: int = max(body_rows - (brand_rows - resting_top) - menu_rows, 0)
    brand_top: int = max(free_rows // 3 - resting_top, 0)
    menu_region_top: int = brand_top + brand_rows
    menu_region_rows: int = max(body_rows - menu_region_top, menu_rows)
    menu_top: int = menu_region_top + max((menu_region_rows - menu_rows) // 2, 0)
    brand_bottom: int = brand_top + brand_rows - 1
    content = Text("\n" * brand_top)
    content.append_text(brand)
    content.append("\n" * max(menu_top - brand_bottom, 1))
    for index, (label, _action) in enumerate(choices):
        content.append(" " * geometry.left_padding)
        if index == selected:
            content.append(f"{_HOME_POINTER} ", style="brand_accent")
            content.append(label, style="brand_accent")
        else:
            content.append(f"  {label}", style="white_bold")
        content.append("\n")
    return with_footer(content, (_HOME_HINT,), columns, rows)


def _small_home_content(
    columns: int, rows: int, selected: int, choices: tuple[tuple[str, HomeAction], ...] = _HOME_CHOICES
) -> Text:
    """Keep the selected Home action reachable when branding cannot fit."""
    visible: int = min(len(choices), max(rows - _HOME_FOOTER_ROWS, 1))
    start: int = max(selected - visible + 1, 0)
    content = Text()
    for index in range(start, min(start + visible, len(choices))):
        label: str = choices[index][0]
        pointer: str = _HOME_POINTER if index == selected else " "
        content.append(f"{pointer} {label}\n", style="brand_accent" if index == selected else "white_bold")
    if rows > _HOME_FOOTER_ROWS:
        return with_footer(content, (_HOME_HINT,), columns, rows)
    return content


def _auto_content(  # noqa: PLR0913
    size: tuple[int, int],
    progress: RichRunProgress,
    mascot_state: MascotState,
    view: _QueueView,
    *,
    native_size: tuple[int, int] | None = None,
    animation_phase: int = 0,
) -> Text:
    columns, rows = size
    if rows < _MINIMUM_BRANDED_ROWS:
        visible_rows: int = max(rows - 2, 1)
        view.fit(progress.active_row, progress.row_count, visible_rows)
        tiny = Text(f"↑ {view.offset} · ↓ {max(progress.row_count - view.offset - visible_rows, 0)}\n", style="gray")
        tiny.append_text(progress.render(columns, offset=view.offset, limit=visible_rows))
        return tiny
    geometry: AutoGeometry = resolve_auto_geometry(columns, rows, progress.row_count, native_size or TEXT_MASCOT_SIZE)
    brand: Text = brand_for_geometry(
        geometry, mascot_state, native_mascot=native_size is not None, animation_phase=animation_phase
    )
    budget: int = max(rows - 1 - geometry.top_padding - len(brand.split("\n")) - 1, 1)
    total: int = progress.row_count
    paged: bool = total > budget
    visible: int = max(budget - _QUEUE_MARKER_ROWS, 1) if paged else total
    view.fit(progress.active_row, total, visible)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand)
    content.append("\n\n")
    if paged:
        content.append_text(_queue_marker("↑", view.offset))
    content.append_text(progress.render(columns, offset=view.offset, limit=visible))
    if paged:
        content.append("\n")
        content.append_text(_queue_marker("↓", total - view.offset - visible))
    return content


def _queue_marker(arrow: str, hidden: int) -> Text:
    if hidden <= 0:
        return Text("\n")
    return Text(f"{arrow} {hidden} poza widokiem\n", style="gray")


def _last_offset(total: int, visible: int) -> int:
    return max(total - visible, 0)


def _message_content(
    columns: int,
    rows: int,
    message: Text,
    mascot_state: MascotState,
    *,
    view: _QueueView | None = None,
) -> Text:
    geometry: HomeGeometry = resolve_home_geometry(columns, rows)
    content = Text("\n" * geometry.top_padding)
    content.append_text(brand_for_geometry(geometry, mascot_state, show_mascot=False))
    content.append("\n\n")
    lines: list[Text] = list(message.split("\n"))
    budget: int = max(rows - len(content.split("\n")) - 3, 1)
    window: _QueueView = view if view is not None else _QueueView(following=False)
    window.fit(len(lines) - 1, len(lines), budget)
    content.append_text(Text("\n").join(lines[window.offset : window.offset + budget]))
    return with_footer(content, ("↑↓ przewijanie · dowolny inny klawisz: powrót",), columns, rows)


def _result_message(result: RunResult, workspace: InspectedWorkspace) -> Text:
    """Show safe failure causes and products preserved by each source group."""
    names: dict[str, str] = {group.group_id: group.source.stem for group in workspace.groups}
    message = Text("Przetwarzanie anulowane" if result.cancelled else "Wynik przetwarzania", style="brand_accent")
    for group in result.groups:
        message.append(
            f"\n\n{_safe(names.get(group.group_id, group.group_id))}: {group.status.value}", style="white_bold"
        )
        for error in group.error_messages:
            message.append(f"\n  {_safe(error)}", style="error")
        for product in (*group.products, *group.preserved_products):
            message.append(f"\n  ✓ Zachowano: {_safe(product.path.name)}", style="brand_accent")
    for warning in result.warnings:
        message.append(f"\n{_safe(warning)}", style="warning")
    message.append(f"\n\nSzczegóły: {_LOG_LOCATION}", style="gray")
    return message


def _fit_frame(content: Text, version: str, directory: str, columns: int, rows: int) -> Text:
    body_rows: int = max(rows - 1, 0)
    lines: list[Text] = list(content.split("\n"))[:body_rows]
    for line in lines:
        # A line wider than the terminal would wrap, push every later row down and
        # move the screen row the native mascot is anchored to.
        line.truncate(max(columns, 1), overflow="crop")
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


def _control_code(problem: AniShiftError | OSError) -> str:
    return problem.code.value if isinstance(problem, ControlError) else ""


def _problem_text(problem: AniShiftError | OSError) -> Text:
    message: Text = Text(f"Błąd · {refusal_text(problem)}", style="error")
    suggestion: str = (
        problem.context.suggestion
        if isinstance(problem, AniShiftError) and not isinstance(problem, ControlError)
        else ""
    )
    if suggestion:
        message.append(f"\n  {_safe(suggestion)}", style="gray")
    message.append(f"\nSzczegóły: {_LOG_LOCATION}", style="gray")
    return message


def _safe(text: str) -> str:
    return (sanitize_event_message(text) or "").rstrip(".")
