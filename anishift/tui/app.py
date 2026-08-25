"""The application shell: the one owner of ``SessionState`` and of the fixed frame."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from textual import on
from textual.app import App
from textual.containers import Container, Vertical
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
from anishift.tui.screens.workspace import GroupRow, WorkspaceView
from anishift.tui.settings.tree import open_speech_panel, speech_values
from anishift.tui.state import FeedbackLevel, SessionState, UiFeedback, UiRoute
from anishift.tui.strings import (
    COMMAND_THEME_TITLE,
    MISSING_SURFACE,
    PALETTE_COMMAND_CATEGORY,
    PALETTE_SUGGESTED_CATEGORY,
    PALETTE_TITLE,
    THEME_DARK_DESCRIPTION,
    THEME_DARK_TITLE,
    THEME_LIGHT_DESCRIPTION,
    THEME_LIGHT_TITLE,
)
from anishift.tui.theme import DARK_THEME_ID, LIGHT_THEME_ID, register_themes
from anishift.tui.ui_state import UiState, load_ui_state, save_ui_state
from anishift.tui.widgets.composer import Composer
from anishift.tui.widgets.footer import BottomBar
from anishift.tui.widgets.hints import StartHints, action_hints
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def is_compact(*, width: int, height: int) -> bool:
    """Whether a terminal of this size has to use the dense layout."""
    return width < FULL_LAYOUT_MIN_WIDTH or height < FULL_LAYOUT_MIN_HEIGHT


class AniShiftApp(App[None]):
    """Single owner of ``SessionState`` and host of the fixed frame."""

    CSS_PATH: ClassVar[CSSPathType] = ["styles/base.tcss", "styles/screens.tcss", "styles/dialogs.tcss"]
    ENABLE_COMMAND_PALETTE: ClassVar[bool] = False
    TITLE: str | None = "AniShift"

    def __init__(self) -> None:
        """Build the frame regions, select the stored theme and register the commands."""
        super().__init__()
        register_themes(self)
        self.theme = load_ui_state().theme
        self._state: SessionState = SessionState()
        self._body: Vertical = Vertical(id=BODY_ID)
        self._brand: Static = Static(id=BRAND_ID)
        self._host: Container = Container(id=CONTENT_ID)
        self._workspace_view: WorkspaceView = WorkspaceView()
        self._composer_slot: Container = Container(id=COMPOSER_SLOT_ID)
        self._hints: StartHints = StartHints()
        self._spacer: Container = Container(id=SPACER_ID)
        self._footer: BottomBar = BottomBar(widget_id=FOOTER_ID)
        self._compact: bool = False
        self._has_logo: bool = False
        self._has_work: bool = False
        self._group_rows: tuple[GroupRow, ...] = ()
        self._run_status: str = ""
        self._speech_values: dict[str, object] = speech_values()
        self._commands: CommandRegistry = CommandRegistry(lambda: self._state)
        self._commands.register((*global_commands(self), palette_command(self._open_palette)))
        self._composer: Composer = Composer(self._commands)

    @property
    def session_state(self) -> SessionState:
        """The session state this shell owns."""
        return self._state

    @property
    def commands(self) -> CommandRegistry:
        """The command registry this shell owns."""
        return self._commands

    def compose(self) -> ComposeResult:
        """Build the work area, the start block under it, then the bottom bar."""
        with self._body:
            with self._host:
                yield self._workspace_view
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
        """Run the command the registry binds to the pressed key, and claim that key."""
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
        self._render_frame()

    @on(PlanFailed)
    def _on_plan_failed(self, message: PlanFailed) -> None:
        """Give the Auto reservation back and keep the reason of the failed plan."""
        if not auto_trigger.release(self._state, generation=message.generation, reason=message.reason):
            return
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
        """Report that the session-setup surface is not available yet."""
        self._report_missing_surface()

    def open_connect(self) -> None:
        """Report that the connection surface is not available yet."""
        self._report_missing_surface()

    def show_status(self) -> None:
        """Report that the status surface is not available yet."""
        self._report_missing_surface()

    def show_debug(self) -> None:
        """Report that the diagnostics surface is not available yet."""
        self._report_missing_surface()

    def show_help(self) -> None:
        """Report that the help surface is not available yet."""
        self._report_missing_surface()

    def exit_app(self) -> None:
        """Leave the application."""
        self.exit()

    def open_auto(self) -> None:
        """Show the automatic-mode route."""
        self.post_message(NavigationRequested(UiRoute.AUTO))

    def open_manual(self) -> None:
        """Show the manual-mode route."""
        self.post_message(NavigationRequested(UiRoute.MANUAL))

    def open_model(self) -> None:
        """Report that the model surface is not available yet."""
        self._report_missing_surface()

    def open_translation(self) -> None:
        """Report that the translation surface is not available yet."""
        self._report_missing_surface()

    def open_prompts(self) -> None:
        """Report that the prompts surface is not available yet."""
        self._report_missing_surface()

    def open_tts(self) -> None:
        """Offer the representative speech fields, each with the editor it needs."""
        open_speech_panel(self, self._state, self._speech_values)

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
        """Report that the doctor surface is not available yet."""
        self._report_missing_surface()

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

    def _report_missing_surface(self) -> None:
        """Store the feedback of a command whose surface is not available yet."""
        self._state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=MISSING_SURFACE)

    def _accepts(self, generation: int, *, run_id: str | None = None) -> bool:
        """Whether a delivered message still belongs to the current view."""
        if lifecycle.accepts_message(self._state, generation=generation, run_id=run_id):
            return True
        logger.debug("Late message dropped", generation=generation)
        return False

    def _render_frame(self) -> None:
        """Redraw every region that projects the session state."""
        self._has_work = bool(self._group_rows) or self._state.workspace is not None
        self._workspace_view.display = self._state.route is UiRoute.WORKSPACE and self._has_work
        if self._group_rows:
            self._workspace_view.show_groups(self._group_rows, status=self._run_status)
        else:
            self._workspace_view.show(self._state.workspace)
        self._hints.show(action_hints(self._commands))
        self._apply_layout()

    def _apply_size(self, size: Size) -> None:
        """Pick the wordmark and the density the current terminal has room for."""
        self._compact = is_compact(width=size.width, height=size.height)
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
        self._hints.show_tip(visible=not self._compact and not self._has_work)
