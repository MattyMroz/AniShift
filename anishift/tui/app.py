"""The application shell: the one owner of ``SessionState`` and of the fixed frame."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.app import App
from textual.containers import Container, Vertical
from textual.widgets import Static
from textual.worker import Worker, WorkerState

from anishift.tui import auto_trigger, lifecycle, tools, workers
from anishift.tui.brand import logo_for_size
from anishift.tui.commands.catalog import EXIT_COMMAND_NAME, global_commands, palette_command
from anishift.tui.commands.palette import palette_options
from anishift.tui.commands.registry import CommandRegistry
from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectDialog, SelectOption, SelectOutcome, SelectOutcomeKind
from anishift.tui.dialogs.value import ConfirmDialog
from anishift.tui.messages import (
    AutoRequested,
    DoctorReported,
    NavigationRequested,
    PlanFailed,
    PlanReady,
    RunFailed,
    RunFinished,
    RunProgressed,
    SetupReported,
    WorkspaceFailed,
    WorkspaceLoaded,
)
from anishift.tui.models.connect import open_connect_surface
from anishift.tui.models.picker import load_catalog, open_model_picker
from anishift.tui.screens.auto import AutoRequest, AutoSession, AutoView, open_auto_presets, resolve_request
from anishift.tui.screens.execution import ExecutionView
from anishift.tui.screens.manual import ManualView
from anishift.tui.screens.preview import PreviewSession, PreviewView, start_available
from anishift.tui.screens.tools import ToolsView
from anishift.tui.screens.workspace import GroupRow, WorkspaceView
from anishift.tui.settings.tree import SettingDomain, open_settings_panel
from anishift.tui.state import RunUiState, SessionState, UiRoute
from anishift.tui.strings import (
    AUTO_CANCELLED,
    AUTO_OVERWRITE_QUESTION,
    AUTO_OVERWRITE_TITLE,
    AUTO_PLAN_BLOCKED,
    AUTO_PROBLEM_SEPARATOR,
    COMMAND_DOCTOR_TITLE,
    COMMAND_EXIT_TITLE,
    COMMAND_INIT_TITLE,
    COMMAND_THEME_TITLE,
    EXECUTION_CANCEL_QUESTION,
    EXECUTION_CANCEL_TITLE,
    EXIT_ACTIVE_RUN_QUESTION,
    PALETTE_COMMAND_CATEGORY,
    PALETTE_SUGGESTED_CATEGORY,
    PALETTE_TITLE,
    PREVIEW_LEFT,
    SETUP_ACTION_TITLE,
    SETUP_CONFIRM_QUESTION,
    THEME_DARK_DESCRIPTION,
    THEME_DARK_TITLE,
    THEME_LIGHT_DESCRIPTION,
    THEME_LIGHT_TITLE,
    WORKER_FAILED,
)
from anishift.tui.theme import DARK_THEME_ID, LIGHT_THEME_ID, register_themes
from anishift.tui.ui_state import UiState, load_ui_state, save_ui_state
from anishift.tui.widgets.composer import Composer
from anishift.tui.widgets.footer import BottomBar
from anishift.tui.widgets.hints import TIP_MIN_HEIGHT, StartHints, action_hints
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from textual.app import ComposeResult
    from textual.content import Content
    from textual.events import Key, Resize
    from textual.geometry import Size
    from textual.timer import Timer
    from textual.types import CSSPathType

    from anishift.application import AppService, ExecutionPlan, ModelProbeResult
    from anishift.config.model_catalog import ModelCatalog

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

FULL_LAYOUT_MIN_WIDTH: Final[int] = 100
"""Terminal width from which the full layout applies."""

FULL_LAYOUT_MIN_HEIGHT: Final[int] = 30
"""Terminal height from which the full layout applies."""

_COMPACT_CLASS: Final[str] = "compact"
"""Class switching every frame region to its dense variant."""

BODY_ID: Final[str] = "app-body"
"""Id of the column holding every region above the bottom bar."""

BRAND_ID: Final[str] = "app-brand"
"""Id of the region holding the static wordmark."""

CONTENT_ID: Final[str] = "app-content"
"""Id of the work area, which takes the free height above the start block."""

COMPOSER_SLOT_ID: Final[str] = "app-composer"
"""Id of the slot the composer stays mounted in for the whole session."""

SPACER_ID: Final[str] = "app-spacer"
"""Id of the block balancing the start block, so it sits vertically centred."""

FOOTER_ID: Final[str] = "app-footer"
"""Id of the one-row bottom bar pinned to the bottom edge."""

THEME_ROWS: Final[tuple[tuple[str, str, str], ...]] = (
    (DARK_THEME_ID, THEME_DARK_TITLE, THEME_DARK_DESCRIPTION),
    (LIGHT_THEME_ID, THEME_LIGHT_TITLE, THEME_LIGHT_DESCRIPTION),
)
"""Id, title and description of every theme the shell offers a user."""

CANCEL_WORKER_GROUP: Final[str] = "cancel"
"""Group the one worker asking the facade to stop a run is launched under."""

BUSY_RUN_STATES: Final[frozenset[RunUiState]] = frozenset(
    {RunUiState.PLANNING, RunUiState.RUNNING, RunUiState.CANCELLING},
)
"""Run states holding work in flight, which an exit has to confirm first."""


def is_compact(*, width: int, height: int) -> bool:
    """Whether a terminal of this size has to use the dense layout."""
    return width < FULL_LAYOUT_MIN_WIDTH or height < FULL_LAYOUT_MIN_HEIGHT


class AniShiftApp(App[None]):
    """Single owner of ``SessionState`` and host of the fixed frame."""

    CSS_PATH: ClassVar[CSSPathType] = ["styles/base.tcss", "styles/screens.tcss", "styles/dialogs.tcss"]
    ENABLE_COMMAND_PALETTE: ClassVar[bool] = False
    ALLOW_SELECT: ClassVar[bool] = False
    TITLE: str | None = "AniShift"

    def __init__(self, *, service: AppService) -> None:
        """Build the frame regions, select the stored theme and register the commands."""
        super().__init__()
        register_themes(self)
        self.theme = load_ui_state().theme
        self._service: AppService = service
        self._pump: workers.RunEventPump | None = None
        self._drain_timer: Timer | None = None
        self._state: SessionState = SessionState()
        self._model_availability: dict[str, ModelProbeResult] = {}
        self._body: Vertical = Vertical(id=BODY_ID)
        self._brand: Static = Static(id=BRAND_ID)
        self._host: Container = Container(id=CONTENT_ID)
        self._workspace_view: WorkspaceView = WorkspaceView()
        self._auto_view: AutoView = AutoView()
        self._manual_view: ManualView = ManualView()
        self._preview_view: PreviewView = PreviewView()
        self._execution_view: ExecutionView = ExecutionView()
        self._run_origin: UiRoute = UiRoute.WORKSPACE
        self._preview: PreviewSession = PreviewSession()
        self._auto: AutoSession = AutoSession()
        self._tools_view: ToolsView = ToolsView()
        self._composer_slot: Container = Container(id=COMPOSER_SLOT_ID)
        self._hints: StartHints = StartHints()
        self._spacer: Container = Container(id=SPACER_ID)
        self._footer: BottomBar = BottomBar(widget_id=FOOTER_ID)
        self._compact: bool = False
        self._has_logo: bool = False
        self._has_tip_room: bool = False
        self._has_work: bool = False
        self._group_rows: tuple[GroupRow, ...] = ()
        self._run_status: str = ""
        self._tools_report: tools.ToolsReport | None = None
        self._tools_intent: tools.ToolsIntent | None = None
        self._commands: CommandRegistry = CommandRegistry(lambda: self._state)
        self._commands.register(
            (*global_commands(self), palette_command(self._open_palette), tools.setup_action(self.run_setup)),
        )
        self._composer: Composer = Composer(self._commands)

    @property
    def service(self) -> AppService:
        """The one application facade every workflow of this shell goes through."""
        return self._service

    @property
    def session_state(self) -> SessionState:
        """The session state this shell owns."""
        return self._state

    @property
    def is_draining(self) -> bool:
        """Whether the shell currently drains the events of an active run."""
        return self._pump is not None

    @property
    def commands(self) -> CommandRegistry:
        """The command registry this shell owns."""
        return self._commands

    @property
    def workspace_root(self) -> Path:
        """The directory every location this shell renders stays inside of."""
        return self._service.workspace_root

    @property
    def tools_report(self) -> tools.ToolsReport | None:
        """The report the work area shows, while one tools command asked for it."""
        return self._tools_report

    @property
    def model_availability(self) -> dict[str, ModelProbeResult]:
        """Availability answers of this session alone, never written anywhere."""
        return self._model_availability

    def compose(self) -> ComposeResult:
        """Build the work area, the start block under it, then the bottom bar."""
        with self._body:
            with self._host:
                yield self._workspace_view
                yield self._auto_view
                yield self._manual_view
                yield self._preview_view
                yield self._execution_view
                yield self._tools_view
            yield self._brand
            with self._composer_slot:
                yield self._composer
            yield self._hints
            yield self._spacer
        yield self._footer

    def on_mount(self) -> None:
        """Draw the frame for the current state and the terminal size."""
        self._render_frame()
        self._apply_size(self.size)

    def show_groups(self, rows: Sequence[GroupRow], *, status: str = "") -> None:
        """Show *rows* and *status* in the work area, in place of the start block."""
        self._group_rows = tuple(rows)
        self._run_status = status
        self._render_frame()

    def on_resize(self, event: Resize) -> None:
        """Reflow the frame without rebuilding state or remounting a slot."""
        self._apply_size(event.size)

    def on_key(self, event: Key) -> None:
        """Run the command the registry binds to the pressed key, leaving it to any narrower context first."""
        if event.key in self.screen.active_bindings:
            return
        if self._commands.dispatch_key(event.key):
            event.stop()
            event.prevent_default()

    async def action_quit(self) -> None:
        """Route the inherited ``Ctrl+Q`` action through the one registry."""
        self._commands.dispatch(EXIT_COMMAND_NAME)

    @on(NavigationRequested)
    def _on_navigation_requested(self, message: NavigationRequested) -> None:
        """Show another route, keeping the active run, the plan and drafts."""
        if lifecycle.navigate(self._state, message.route):
            self._render_frame()

    @on(WorkspaceLoaded)
    def _on_workspace_loaded(self, message: WorkspaceLoaded) -> None:
        """Store an inspection that still belongs to the current generation."""
        if not self._accepts(message.generation):
            return
        lifecycle.set_workspace(self._state, message.workspace)
        self._render_frame()

    @on(WorkspaceFailed)
    def _on_workspace_failed(self, message: WorkspaceFailed) -> None:
        """Keep the reason of an inspection the session still waits for."""
        if not self._accepts(message.generation):
            return
        lifecycle.report_error(self._state, message.reason)
        self._render_frame()

    @on(PlanReady)
    def _on_plan_ready(self, message: PlanReady) -> None:
        """Store a plan the session may preview and start."""
        if not self._accepts(message.generation):
            return
        lifecycle.plan_ready(self._state, message.plan)
        if message.generation == self._auto.generation:
            self._decide_auto(message.plan, message.generation)
            return
        self._preview.origin = self._state.route
        lifecycle.navigate(self._state, UiRoute.PREVIEW)
        self._render_frame()

    @on(PlanFailed)
    def _on_plan_failed(self, message: PlanFailed) -> None:
        """Give the Auto reservation back and keep the reason of the failed plan."""
        if not auto_trigger.release(self._state, generation=message.generation, reason=message.reason):
            return
        self._auto.generation = None
        self._stop_drain()
        self._render_frame()

    @on(Composer.EmptySubmitted)
    def _on_empty_submitted(self, _message: Composer.EmptySubmitted) -> None:
        """Turn one accepted empty line into exactly one Auto request."""
        generation: int | None = auto_trigger.reserve(self._state)
        if generation is None:
            return
        self.post_message(AutoRequested(generation))
        self._composer.clear()
        self._render_frame()

    @on(AutoRequested)
    def _on_auto_requested(self, message: AutoRequested) -> None:
        """Hand one still-current Auto request to the workflow that answers it."""
        if not self._accepts(message.generation):
            return
        self.plan_auto_request(message.generation)

    def plan_auto_request(self, generation: int) -> None:
        """Resolve the default Auto run of *generation* and plan it off the UI thread."""
        request: AutoRequest = resolve_request(self._state, self._service, self._auto)
        if request.preset is None:
            auto_trigger.release(self._state, generation=generation, reason=request.refusal)
            self._auto.verdict = None
            lifecycle.navigate(self._state, UiRoute.AUTO)
            self._render_frame()
            return
        self._auto.generation = generation
        self._auto.verdict = None
        workers.plan_auto(
            self,
            self._service,
            generation=generation,
            group_ids=request.group_ids,
            preset=request.preset,
        )
        self._render_frame()

    def _decide_auto(
        self,
        plan: ExecutionPlan,
        generation: int,
        *,
        blocked_route: UiRoute = UiRoute.AUTO,
    ) -> None:
        """Start, confirm or refuse this planned run from the one verdict of its plan."""
        verdict: auto_trigger.AutoVerdict = auto_trigger.classify(
            plan,
            accepted=self._auto.accepted_artifact_ids,
        )
        self._auto.verdict = verdict
        self._auto.generation = None
        if verdict.kind is auto_trigger.AutoVerdictKind.BLOCKED:
            auto_trigger.release(self._state, generation=generation, reason=AUTO_PLAN_BLOCKED)
            lifecycle.navigate(self._state, blocked_route)
            self._render_frame()
            return
        if verdict.kind is auto_trigger.AutoVerdictKind.CONFIRM:
            self._confirm_auto(plan, generation, verdict)
            return
        self._start_auto_run(plan)

    def start_previewed_run(self) -> bool:
        """Run the previewed plan through the one gate that decides it may start."""
        plan: ExecutionPlan | None = self._state.plan
        if plan is None or not start_available(self._state):
            logger.debug("Previewed start refused", run_state=self._state.run_state.value)
            return False
        self._decide_auto(plan, self._state.generation, blocked_route=UiRoute.PREVIEW)
        return True

    def leave_preview(self, route: UiRoute) -> None:
        """Give the reservation back and show the screen that prepared the plan."""
        auto_trigger.release(self._state, generation=self._state.generation, reason=PREVIEW_LEFT)
        self._auto.verdict = None
        lifecycle.navigate(self._state, route)
        self._render_frame()

    def _start_auto_run(self, plan: ExecutionPlan) -> None:
        """Show the groups of the accepted Auto plan and enter its run."""
        lifecycle.navigate(self._state, UiRoute.WORKSPACE)
        self.start_execution(plan)
        self._render_frame()

    def _confirm_auto(self, plan: ExecutionPlan, generation: int, verdict: auto_trigger.AutoVerdict) -> None:
        """Ask before the accepted plan replaces the products it names, and start only then."""

        def answered(accepted: bool | None) -> None:
            """Start the run the user accepted, or give the reservation back."""
            if not accepted:
                auto_trigger.release(self._state, generation=generation, reason=AUTO_CANCELLED)
                self._render_frame()
                return
            self._auto.accepted_artifact_ids |= verdict.artifact_ids
            self._auto.verdict = None
            self._start_auto_run(plan)

        question: str = AUTO_OVERWRITE_QUESTION.format(products=AUTO_PROBLEM_SEPARATOR.join(verdict.problems))
        opened: bool = open_dialog(
            self,
            self._state,
            ConfirmDialog(title=AUTO_OVERWRITE_TITLE, question=question),
            answered,
        )
        if not opened:
            auto_trigger.release(self._state, generation=generation, reason=AUTO_CANCELLED)
        self._render_frame()

    @on(RunProgressed)
    def _on_run_progressed(self, message: RunProgressed) -> None:
        """Append events of the run the session currently tracks."""
        if not self._accepts_run(message.generation, message.run_id, announced=message.announces_run):
            return
        lifecycle.record_run_events(self._state, message.events)
        self._paint_run()

    @on(RunFinished)
    def _on_run_finished(self, message: RunFinished) -> None:
        """Store the terminal result of the run the session started."""
        if not self._accepts_run(message.generation, message.run_id, announced=True):
            return
        lifecycle.finish_run(self._state, message.result)
        self._stop_drain()
        self._close_run_view()
        self._render_frame()

    @on(RunFailed)
    def _on_run_failed(self, message: RunFailed) -> None:
        """End the tracked run without a result and keep its reason."""
        if not self._accepts_run(message.generation, message.run_id, announced=True):
            return
        lifecycle.fail_run(self._state, message.reason)
        self._stop_drain()
        self._close_run_view()
        logger.warning("Run ended without a result", generation=message.generation)
        self._render_frame()

    @on(DoctorReported)
    def _on_doctor_reported(self, message: DoctorReported) -> None:
        """Show the diagnostics in the form the command that asked for them expects."""
        if not self._accepts(message.generation):
            return
        if self._tools_intent is tools.ToolsIntent.INIT:
            self._show_tools(tools.init_report(message.checks, self._session_facts(), self._commands))
            return
        self._show_tools(tools.doctor_report(message.checks))

    @on(SetupReported)
    def _on_setup_reported(self, message: SetupReported) -> None:
        """Show the answer of every resource the confirmed installation touched."""
        if not self._accepts(message.generation):
            return
        self._show_tools(tools.setup_report(message.resources))

    @on(Worker.StateChanged)
    def _on_worker_state_changed(self, message: Worker.StateChanged) -> None:
        """Report the redacted failure of a worker that ended outside its own contract."""
        if message.state is not WorkerState.ERROR:
            return
        generation: int | None = workers.worker_generation(message.worker.name)
        if generation is None or not self._accepts(generation):
            return
        logger.error("Worker ended unexpectedly", operation=message.worker.group, generation=generation)
        self._report_worker_failure()
        self._stop_drain()
        self._close_run_view()
        self._render_frame()

    def start_execution(self, plan: ExecutionPlan) -> bool:
        """Run *plan* off the UI thread, draining its events until it ends.

        Refuses every view that has not reserved a generation through
        ``begin_planning``, because only a planned view can enter the run its
        events belong to. A refusal starts no worker and leaves the state
        untouched.
        """
        if self._pump is not None or self._state.run_state is not RunUiState.PLANNING:
            logger.error(
                "Execution refused outside a planned view",
                run_state=self._state.run_state.value,
                draining=self._pump is not None,
            )
            return False
        self._run_origin = self._state.route
        pump: workers.RunEventPump = workers.RunEventPump(self._state.generation)
        self._pump = pump
        self._drain_timer = self.set_interval(workers.DRAIN_INTERVAL_SECONDS, self.drain_run_events)
        workers.execute(self, self._service, plan=plan, pump=pump)
        lifecycle.navigate(self._state, UiRoute.EXECUTION)
        self._render_frame()
        return True

    def cancel_run(self) -> bool:
        """Ask the active run to stop, once the user confirms leaving its remaining work."""
        run_id: str | None = self._state.active_run_id
        if run_id is None or self._state.run_state is not RunUiState.RUNNING:
            logger.debug("Cancel refused outside an active run", run_state=self._state.run_state.value)
            return False

        def confirmed(accepted: bool | None) -> None:
            """Stop the run the user gave up, or leave it running untouched."""
            if accepted:
                self._request_cancel(run_id)

        return open_dialog(
            self,
            self._state,
            ConfirmDialog(title=EXECUTION_CANCEL_TITLE, question=EXECUTION_CANCEL_QUESTION),
            confirmed,
        )

    def _request_cancel(self, run_id: str) -> None:
        """Enter the cancelling state and ask the facade to stop *run_id* exactly once."""
        if self._state.active_run_id != run_id or not lifecycle.request_cancel(self._state):
            logger.debug("Cancel request dropped", run_state=self._state.run_state.value)
            return

        def work() -> None:
            """Ask the facade to stop the run, which never blocks on its tasks."""
            self._service.cancel(run_id)

        logger.info("Run cancel requested", generation=self._state.generation)
        self.run_worker(work, group=CANCEL_WORKER_GROUP, exit_on_error=False, thread=True)
        self._paint_run()

    def drain_run_events(self) -> None:
        """Deliver the events the active run buffered since the previous drain."""
        pump: workers.RunEventPump | None = self._pump
        if pump is None:
            return
        workers.flush(self, pump)

    def _paint_run(self) -> None:
        """Repaint the watched run once per drained batch, and never once per event."""
        if self._state.route is UiRoute.EXECUTION:
            self._execution_view.show(self._state)

    def _close_run_view(self) -> None:
        """Paint the last frame of the run that ended, then leave the surface watching it."""
        if self._state.route is not UiRoute.EXECUTION:
            return
        self._execution_view.show(self._state)
        lifecycle.navigate(self._state, self._run_origin)

    def _stop_drain(self) -> None:
        """Stop the drain timer and release the pump of the run that ended."""
        if self._drain_timer is not None:
            self._drain_timer.stop()
            self._drain_timer = None
        self._pump = None

    def _report_worker_failure(self) -> None:
        """Leave the run or the reservation the crashed worker held, with a safe reason."""
        if self._state.run_state in {RunUiState.RUNNING, RunUiState.CANCELLING}:
            lifecycle.fail_run(self._state, WORKER_FAILED)
            return
        if self._state.run_state is RunUiState.PLANNING:
            lifecycle.abandon_planning(self._state, WORKER_FAILED)
            return
        lifecycle.report_error(self._state, WORKER_FAILED)

    def open_init(self) -> None:
        """Ask for every diagnostic, then propose the first steps that are still missing."""
        self._collect_diagnostics(tools.ToolsIntent.INIT, COMMAND_INIT_TITLE)

    def open_connect(self) -> None:
        """Offer the enrollment address, the token and one confirmed connection test."""
        open_connect_surface(self, self._state, self._service, self._model_availability)

    def show_status(self) -> None:
        """Show the safe summary of this session, holding no secret and no path."""
        self._show_tools(tools.status_report(self._session_facts()))

    def show_debug(self) -> None:
        """Show the wider diagnostics, which extend the rows of the status report."""
        catalog: ModelCatalog | None = load_catalog(self._state, self._service)
        runtime: tools.RuntimeFacts = tools.runtime_facts(
            self._state,
            self._model_availability,
            catalog,
            draining=self.is_draining,
        )
        self._show_tools(tools.debug_report(self._session_facts(), runtime))

    def show_help(self) -> None:
        """Show every command, action and key the registry holds right now."""
        self._show_tools(tools.help_report(self._commands))

    def exit_app(self) -> None:
        """Leave the application, asking first while work is still in flight."""
        if self._state.run_state not in BUSY_RUN_STATES:
            self.exit()
            return

        def confirmed(accepted: bool | None) -> None:
            """Leave only once the user accepts abandoning the work in flight."""
            if accepted:
                self.exit()

        open_dialog(
            self,
            self._state,
            ConfirmDialog(title=COMMAND_EXIT_TITLE, question=EXIT_ACTIVE_RUN_QUESTION),
            confirmed,
        )

    def open_auto(self) -> None:
        """Offer every stored automatic preset, planning and starting nothing."""
        lifecycle.navigate(self._state, UiRoute.AUTO)
        self._render_frame()
        open_auto_presets(self, self._state, self._service, self._auto)

    def open_manual(self) -> None:
        """Show the manual-mode route."""
        self.post_message(NavigationRequested(UiRoute.MANUAL))

    def open_model(self) -> None:
        """Offer every configured catalog alias and change only the main model."""
        open_model_picker(self, self._state, self._service, self._model_availability)

    def open_translation(self) -> None:
        """Offer the translation settings, each with the editor it needs."""
        self._open_settings(SettingDomain.TRANSLATION)

    def open_prompts(self) -> None:
        """Offer the prompt settings, each with the editor it needs."""
        self._open_settings(SettingDomain.PROMPTS)

    def open_tts(self) -> None:
        """Offer the speech settings, each with the editor it needs."""
        self._open_settings(SettingDomain.TTS)

    def _open_settings(self, domain: SettingDomain) -> None:
        """Open the settings panel of *domain*."""
        open_settings_panel(self, self._state, self._service, domain)

    def open_theme(self) -> None:
        """Offer both themes, previewing every row and keeping only a confirmed one."""
        previous: str = self.theme
        options: tuple[SelectOption[str], ...] = tuple(
            SelectOption(value=theme_id, title=title, description=description)
            for theme_id, title, description in THEME_ROWS
        )

        def preview(theme_id: str) -> None:
            """Show the highlighted theme without keeping it."""
            self.theme = theme_id

        def chosen(outcome: SelectOutcome[str] | None) -> None:
            """Keep a confirmed theme, or bring back the one that was in use."""
            picked: str | None = None
            if outcome is not None and outcome.kind is SelectOutcomeKind.SINGLE:
                picked = outcome.value
            if picked is None:
                self.theme = previous
                return
            self.theme = picked
            save_ui_state(UiState(theme=picked))

        dialog: SelectDialog[str] = SelectDialog(
            title=COMMAND_THEME_TITLE,
            options=options,
            current=previous,
            on_highlight=preview,
        )
        open_dialog(self, self._state, dialog, chosen)

    def run_doctor(self) -> None:
        """Ask for every diagnostic and show all of it, with every suggestion it carries."""
        self._collect_diagnostics(tools.ToolsIntent.DOCTOR, COMMAND_DOCTOR_TITLE)

    def run_setup(self) -> None:
        """Install the external tools, but only after the user confirms the download."""

        def confirmed(accepted: bool | None) -> None:
            """Start the installation the user confirmed, or leave everything alone."""
            if not accepted:
                return
            self._tools_intent = tools.ToolsIntent.SETUP
            self._show_tools(tools.pending_report(SETUP_ACTION_TITLE))
            workers.run_setup(self, self._service, generation=self._state.generation)

        open_dialog(
            self,
            self._state,
            ConfirmDialog(title=SETUP_ACTION_TITLE, question=SETUP_CONFIRM_QUESTION),
            confirmed,
        )

    def _collect_diagnostics(self, intent: tools.ToolsIntent, title: str) -> None:
        """Collect every diagnostic off the UI thread, showing *title* while it runs."""
        self._tools_intent = intent
        self._show_tools(tools.pending_report(title))
        workers.run_doctor(self, self._service, generation=self._state.generation)

    def _session_facts(self) -> tools.SessionFacts:
        """Collect the facts of this session from the state and the one facade."""
        return tools.session_facts(self._state, self._service, self._model_availability)

    def _show_tools(self, report: tools.ToolsReport) -> None:
        """Show *report* in the work area, on the route the tools commands share."""
        self._tools_report = report
        lifecycle.navigate(self._state, UiRoute.TOOLS)
        self._render_frame()

    def _open_palette(self) -> None:
        """Open the palette of every command and action the session allows."""
        options: tuple[SelectOption[str], ...] = tuple(
            SelectOption(
                value=option.name,
                title=option.label,
                description=option.description,
                footer=option.keys,
                category=PALETTE_SUGGESTED_CATEGORY if option.suggested else PALETTE_COMMAND_CATEGORY,
            )
            for option in palette_options(self._commands)
        )

        def chosen(outcome: SelectOutcome[str] | None) -> None:
            """Run the command of the picked row."""
            if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE or outcome.value is None:
                return
            self._commands.dispatch(outcome.value)

        open_dialog(self, self._state, SelectDialog(title=PALETTE_TITLE, options=options), chosen)

    def _accepts(self, generation: int, *, run_id: str | None = None) -> bool:
        """Whether a delivered message still belongs to the current view."""
        if lifecycle.accepts_message(self._state, generation=generation, run_id=run_id):
            return True
        logger.debug("Late message dropped", generation=generation)
        return False

    def _accepts_run(self, generation: int, run_id: str, *, announced: bool) -> bool:
        """Whether a run message is current, entering the run it authoritatively names."""
        if not self._accepts(generation):
            return False
        if announced and self._state.active_run_id is None:
            lifecycle.begin_run(self._state, run_id)
        return self._accepts(generation, run_id=run_id)

    def _render_frame(self) -> None:
        """Redraw every region that projects the session state."""
        has_groups: bool = bool(self._group_rows) or self._state.workspace is not None
        on_auto: bool = self._state.route is UiRoute.AUTO
        on_preview: bool = self._state.route is UiRoute.PREVIEW
        on_execution: bool = self._state.route is UiRoute.EXECUTION
        self._has_work = has_groups or on_auto or on_preview or on_execution or self._tools_report is not None
        self._workspace_view.display = self._state.route is UiRoute.WORKSPACE and has_groups
        self._auto_view.display = on_auto
        self._auto_view.show(self._state, self._auto)
        self._manual_view.display = self._state.route is UiRoute.MANUAL and has_groups
        self._preview_view.display = on_preview
        if on_preview:
            self._preview_view.show(self._state, self._preview, root=self.workspace_root)
        self._execution_view.display = on_execution
        if on_execution:
            self._execution_view.show(self._state)
        self._tools_view.display = self._state.route is UiRoute.TOOLS and self._tools_report is not None
        self._tools_view.show(self._tools_report)
        if self._group_rows:
            self._workspace_view.show_groups(self._group_rows, status=self._run_status)
        else:
            self._workspace_view.show(self._state.workspace)
        self._hints.show(action_hints(self._commands))
        self._apply_layout()

    def _apply_size(self, size: Size) -> None:
        """Pick the wordmark and the density the current terminal has room for."""
        self._compact = is_compact(width=size.width, height=size.height)
        self._has_tip_room = size.height >= TIP_MIN_HEIGHT
        logo: Content | None = logo_for_size(width=size.width, height=size.height)
        self._has_logo = logo is not None
        if logo is not None:
            self._brand.update(logo)
        self._apply_layout()

    def _apply_layout(self) -> None:
        """Set the density class and hide the start block once the work area has a surface."""
        self.screen.set_class(self._compact, _COMPACT_CLASS)
        self._brand.display = self._has_logo and not self._has_work
        self._spacer.display = not self._has_work
        self._hints.show_tip(visible=self._has_tip_room and not self._has_work)
