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

Because the shell owns the state, it is also the only place that may accept an
empty composer line: ``auto_trigger`` reserves one generation, the shell
publishes one ``AutoRequested`` for it and clears the field afterwards. The
shell declares no binding for ``Enter``, so the composer is the only way in.

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

from anishift.tui import auto_trigger, lifecycle
from anishift.tui.brand import logo_for_size
from anishift.tui.commands.catalog import EXIT_COMMAND_NAME, global_commands, palette_command
from anishift.tui.commands.palette import palette_options
from anishift.tui.commands.registry import CommandRegistry
from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectDialog, SelectOption, SelectOutcome, SelectOutcomeKind
from anishift.tui.messages import (
    AutoRequested,
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
from anishift.tui.widgets.composer import Composer
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

_PALETTE_TITLE: Final[str] = "Paleta komend"
"""Heading of the palette dialog."""

_SUGGESTED_CATEGORY: Final[str] = "Sugerowane"
"""Heading the palette groups the likely next steps under."""

_COMMAND_CATEGORY: Final[str] = "Komendy"
"""Heading the palette groups every remaining command under."""


def is_compact(*, width: int, height: int) -> bool:
    """Whether a terminal of this size has to use the dense layout."""
    return width < FULL_LAYOUT_MIN_WIDTH or height < FULL_LAYOUT_MIN_HEIGHT


class AniShiftApp(App[None]):
    """Single owner of ``SessionState`` and host of the fixed frame."""

    CSS_PATH: ClassVar[CSSPathType] = ["styles/base.tcss", "styles/screens.tcss", "styles/dialogs.tcss"]
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
        self._composer: Composer = Composer(self._commands)

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
        with self._composer_slot:
            yield self._composer
        yield self._footer

    def on_mount(self) -> None:
        """Draw the frame for the current state and terminal size."""
        self._render_frame()
        self._apply_size(self.size)

    def on_resize(self, event: Resize) -> None:
        """Reflow the frame without rebuilding state or remounting a slot."""
        self._apply_size(event.size)

    def on_key(self, event: Key) -> None:
        """Run the command the registry binds to the pressed key, if it has one.

        A key the registry answered is fully claimed, so no inherited Textual
        binding may answer it a second time.
        """
        if self._commands.dispatch_key(event.key):
            event.stop()
            event.prevent_default()

    async def action_quit(self) -> None:
        """Route the inherited quit key through the one registry.

        Textual binds ``Ctrl+Q`` to this action with ``priority=True``, so the
        key never reaches ``on_key``. Delegating here keeps ``dispatch`` the
        only point that runs a command, instead of a second way out.
        """
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
        self._render_frame()

    @on(PlanFailed)
    def _on_plan_failed(self, message: PlanFailed) -> None:
        """Give the Auto reservation back and keep the reason of the failed plan."""
        if not auto_trigger.release(self._state, generation=message.generation, reason=message.reason):
            return
        self._render_frame()

    @on(Composer.EmptySubmitted)
    def _on_empty_submitted(self, _message: Composer.EmptySubmitted) -> None:
        """Turn one accepted empty line into exactly one Auto request.

        The reservation is what makes this exactly once: a second submission of
        the same physical key, an auto-repeat or a duplicated message finds the
        gate taken and leaves the field, the state and the workflow untouched.
        """
        generation: int | None = auto_trigger.reserve(self._state)
        if generation is None:
            return
        self.post_message(AutoRequested(generation))
        self._composer.clear()
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
        """Open the palette of every command and action the session allows.

        The rows are the projection ``palette_options`` already built, and the
        chosen row goes straight back to ``dispatch``: the palette owns no
        command and no second way of running one.
        """
        options: tuple[SelectOption[str], ...] = tuple(
            SelectOption(
                value=option.name,
                title=option.label,
                description=option.description,
                footer=option.keys,
                category=_SUGGESTED_CATEGORY if option.suggested else _COMMAND_CATEGORY,
            )
            for option in palette_options(self._commands)
        )

        def chosen(outcome: SelectOutcome[str] | None) -> None:
            """Run the command of the picked row, and nothing else."""
            if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE or outcome.value is None:
                return
            self._commands.dispatch(outcome.value)

        open_dialog(self, self._state, SelectDialog(title=_PALETTE_TITLE, options=options), chosen)

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
