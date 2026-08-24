"""The AniShift application shell: one state owner and one fixed frame.

``AniShiftApp`` owns the single ``SessionState`` of a session and hosts the
fixed frame: brand, contextual header, one route host, a permanent composer
slot and the one-row status footer. Resizing reflows the frame; it never
rebuilds the state and never unmounts the composer slot.

The shell has no backend: it applies state transitions and renders. Discovery,
planning and execution belong to the application layer.

The shell also owns the one ``CommandRegistry``: it registers the frozen
catalogue once and every key, palette row and button runs through its single
``dispatch``. The built-in Textual palette stays switched off, so ``Ctrl+P``
belongs to the registry.

Public API:
    FULL_LAYOUT_MIN_WIDTH: Terminal width from which the full layout applies.
    FULL_LAYOUT_MIN_HEIGHT: Terminal height from which the full layout applies.
    is_compact: Whether a terminal of one size needs the dense layout.
    AniShiftApp: The application shell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.app import App
from textual.containers import Container
from textual.widgets import Static

from anishift.tui import lifecycle
from anishift.tui.brand import logo_for_size
from anishift.tui.commands.catalog import global_commands, palette_command
from anishift.tui.commands.registry import CommandRegistry
from anishift.tui.messages import (
    NavigationRequested,
    PlanFailed,
    PlanReady,
    RunFailed,
    RunFinished,
    RunProgressed,
    WorkspaceFailed,
    WorkspaceLoaded,
)
from anishift.tui.screens.workspace import WorkspaceView
from anishift.tui.state import FeedbackLevel, SessionState, UiFeedback, UiRoute
from anishift.tui.theme import register_themes
from anishift.tui.ui_state import load_ui_state
from anishift.tui.widgets.footer import SessionFooter
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.content import Content
    from textual.events import Key, Resize
    from textual.geometry import Size
    from textual.types import CSSPathType

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

FULL_LAYOUT_MIN_WIDTH: Final[int] = 100
"""Terminal width from which the full layout applies."""

FULL_LAYOUT_MIN_HEIGHT: Final[int] = 30
"""Terminal height from which the full layout applies."""

_COMPACT_CLASS: Final[str] = "compact"
"""Class switching every frame region to its dense variant."""

_MISSING_SURFACE_TEXT: Final[str] = "Warstwa okien dialogowych nie jest jeszcze dostępna."
"""Missing state a command reports while its modal surface is not mounted."""


def is_compact(*, width: int, height: int) -> bool:
    """Whether a terminal of this size has to use the dense layout."""
    return width < FULL_LAYOUT_MIN_WIDTH or height < FULL_LAYOUT_MIN_HEIGHT


class AniShiftApp(App[None]):
    """Single owner of ``SessionState`` and host of the fixed frame."""

    CSS_PATH: ClassVar[CSSPathType] = ["styles/base.tcss", "styles/screens.tcss"]
    ENABLE_COMMAND_PALETTE: ClassVar[bool] = False
    TITLE: str | None = "AniShift"

    def __init__(self) -> None:
        """Build the frame regions, select the stored theme and register the commands.

        The themes have to be registered before Textual parses the style
        sheets, because every colour comes from a theme variable. The frozen
        catalogue is registered exactly once, here.
        """
        super().__init__()
        register_themes(self)
        self.theme = load_ui_state().theme
        self._state: SessionState = SessionState()
        self._brand: Static = Static(id="app-brand")
        self._header: Static = Static(id="app-header")
        self._host: Container = Container(id="app-content")
        self._workspace_view: WorkspaceView = WorkspaceView()
        self._composer_slot: Container = Container(id="app-composer")
        self._footer: SessionFooter = SessionFooter(id="app-footer")
        self._commands: CommandRegistry = CommandRegistry(lambda: self._state)
        self._commands.register((*global_commands(self), palette_command(self._open_palette)))

    @property
    def session_state(self) -> SessionState:
        """The state this shell owns; readers never keep a copy of it."""
        return self._state

    @property
    def commands(self) -> CommandRegistry:
        """The one registry every surface of this shell reads and runs."""
        return self._commands

    def compose(self) -> ComposeResult:
        """Build the fixed frame around the single route host."""
        yield self._brand
        yield self._header
        with self._host:
            yield self._workspace_view
        yield self._composer_slot
        yield self._footer

    def on_mount(self) -> None:
        """Draw the frame for the current state and terminal size."""
        self._render_frame()
        self._apply_size(self.size)

    def on_resize(self, event: Resize) -> None:
        """Reflow the frame without rebuilding state or remounting a slot."""
        self._apply_size(event.size)

    def on_key(self, event: Key) -> None:
        """Run the command the registry binds to the pressed key, if it has one."""
        if self._commands.dispatch_key(event.key):
            event.stop()

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
        self._render_frame()

    @on(PlanFailed)
    def _on_plan_failed(self, message: PlanFailed) -> None:
        """Leave planning without a run and keep its reason."""
        if not self._accepts(message.generation):
            return
        lifecycle.abandon_planning(self._state, message.reason)
        self._render_frame()

    @on(RunProgressed)
    def _on_run_progressed(self, message: RunProgressed) -> None:
        """Append events of the run the session currently tracks."""
        if not self._accepts(message.generation, run_id=message.run_id):
            return
        lifecycle.record_run_events(self._state, message.events)

    @on(RunFinished)
    def _on_run_finished(self, message: RunFinished) -> None:
        """Store the terminal result of the run the session started."""
        if not self._accepts(message.generation, run_id=message.run_id):
            return
        lifecycle.finish_run(self._state, message.result)
        self._render_frame()

    @on(RunFailed)
    def _on_run_failed(self, message: RunFailed) -> None:
        """End the tracked run without a result and keep its reason."""
        if not self._accepts(message.generation, run_id=message.run_id):
            return
        lifecycle.fail_run(self._state, message.reason)
        logger.warning("Run ended without a result", generation=message.generation)
        self._render_frame()

    def open_init(self) -> None:
        """Prepare the workspace and the configuration, then show the next steps."""
        self._report_missing_surface()

    def open_connect(self) -> None:
        """Edit the Palantir Foundry connection and probe one model on request."""
        self._report_missing_surface()

    def show_status(self) -> None:
        """Show the safe summary of configuration, workspace and current run."""
        self._report_missing_surface()

    def show_debug(self) -> None:
        """Show the wider redacted diagnostics of the current session."""
        self._report_missing_surface()

    def show_help(self) -> None:
        """List the commands and the keys the registry currently holds."""
        self._report_missing_surface()

    def exit_app(self) -> None:
        """Leave the application, confirming first while a run is active."""
        self.exit()

    def open_auto(self) -> None:
        """Configure the default automatic mode and its presets."""
        self.post_message(NavigationRequested(UiRoute.AUTO))

    def open_manual(self) -> None:
        """Prepare the manual intents of the selected groups."""
        self.post_message(NavigationRequested(UiRoute.MANUAL))

    def open_model(self) -> None:
        """Choose the primary Palantir model from the local catalogue."""
        self._report_missing_surface()

    def open_translation(self) -> None:
        """Edit the translation settings and their own model."""
        self._report_missing_surface()

    def open_prompts(self) -> None:
        """Choose the task prompt, the style and the prompt modules."""
        self._report_missing_surface()

    def open_tts(self) -> None:
        """Edit the speech settings, the voices and the audio profile."""
        self._report_missing_surface()

    def open_theme(self) -> None:
        """Choose the theme with a live preview and a rollback."""
        self._report_missing_surface()

    def run_doctor(self) -> None:
        """Run the technical diagnostics without repairing anything."""
        self._report_missing_surface()

    def _open_palette(self) -> None:
        """Open the palette of every command and action the session allows."""
        self._report_missing_surface()

    def _report_missing_surface(self) -> None:
        """Keep the missing state of a command whose modal surface is absent."""
        self._state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=_MISSING_SURFACE_TEXT)

    def _accepts(self, generation: int, *, run_id: str | None = None) -> bool:
        """Whether a delivered message still belongs to the current view."""
        if lifecycle.accepts_message(self._state, generation=generation, run_id=run_id):
            return True
        logger.debug("Late message dropped", generation=generation)
        return False

    def _render_frame(self) -> None:
        """Redraw every region that projects the session state."""
        self._header.update(self._state.route.value)
        self._workspace_view.display = self._state.route is UiRoute.WORKSPACE
        self._workspace_view.show(self._state.workspace)
        self._footer.show(self._state, self._commands.key_hints())

    def _apply_size(self, size: Size) -> None:
        """Switch the frame between the full and the dense layout."""
        self.screen.set_class(is_compact(width=size.width, height=size.height), _COMPACT_CLASS)
        logo: Content | None = logo_for_size(width=size.width, height=size.height)
        self._brand.display = logo is not None
        if logo is not None:
            self._brand.update(logo)
