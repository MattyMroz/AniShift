"""The screen watching the run under way, and the one action asking it to stop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from textual.widgets import Static

from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.state import RunUiState
from anishift.tui.strings import (
    EXECUTION_CANCEL_DESCRIPTION,
    EXECUTION_CANCEL_TITLE,
    EXECUTION_DETAILS_DESCRIPTION,
    EXECUTION_DETAILS_TITLE,
    EXECUTION_FILTER_DESCRIPTION,
    EXECUTION_FILTER_TITLE,
    EXECUTION_TITLE,
)
from anishift.tui.widgets.progress_table import ProgressFilter, next_filter, progress_body

if TYPE_CHECKING:
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandRun
    from anishift.tui.state import SessionState

__all__ = [
    "CANCEL_COMMAND_NAME",
    "CANCEL_KEY",
    "DETAILS_COMMAND_NAME",
    "DETAILS_KEY",
    "EXECUTION_ID",
    "EXECUTION_SCOPE",
    "FILTER_COMMAND_NAME",
    "FILTER_KEY",
    "ExecutionHost",
    "ExecutionView",
    "cancel_available",
    "execution_body",
    "table_available",
]

# ── Constants ──────────────────────────────────────────────────────────────

EXECUTION_ID: Final[str] = "execution-view"
"""Identifier of the one region watching an active run."""

EXECUTION_SCOPE: Final[str] = "execution"
"""Registry scope the execution screen owns while it is on screen, and never longer."""

CANCEL_COMMAND_NAME: Final[str] = "cancel-run"
"""Name of the contextual action asking the watched run to stop."""

FILTER_COMMAND_NAME: Final[str] = "filter-run"
"""Name of the contextual action narrowing the table to some groups."""

DETAILS_COMMAND_NAME: Final[str] = "details-run"
"""Name of the contextual action opening the details under every row."""

CANCEL_KEY: Final[str] = "ctrl+t"
"""Key asking the watched run to stop, which always confirms first."""

FILTER_KEY: Final[str] = "ctrl+f"
"""Key moving the table to the next filter."""

DETAILS_KEY: Final[str] = "ctrl+o"
"""Key opening the details of every listed row, and closing them again."""


@runtime_checkable
class ExecutionHost(Protocol):
    """What the execution screen needs from the shell that owns it."""

    @property
    def session_state(self) -> SessionState:
        """The one session state the shell owns."""

    @property
    def commands(self) -> CommandRegistry:
        """The one command registry the shell owns."""

    def cancel_run(self) -> bool:
        """Ask the active run to stop, confirming that once before anything stops."""


def cancel_available(state: SessionState) -> bool:
    """Whether *state* holds a run this session may ask to stop right now."""
    if state.run_state is not RunUiState.RUNNING or state.active_run_id is None:
        return False
    return not state.modal_focus_stack


def table_available(state: SessionState) -> bool:
    """Whether *state* lets the table change what it lists right now."""
    return not state.modal_focus_stack


def execution_body(
    state: SessionState,
    *,
    listed: ProgressFilter = ProgressFilter.ALL,
    details: bool = False,
) -> str:
    """Return the rendered text of the run this session watches."""
    return f"{EXECUTION_TITLE}\n\n{progress_body(state, listed=listed, details=details)}"


def _cancel_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the cancel key and its palette row."""
    return CommandSpec(
        name=CANCEL_COMMAND_NAME,
        title=EXECUTION_CANCEL_TITLE,
        description=EXECUTION_CANCEL_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=cancel_available,
        keys=(CANCEL_KEY,),
    )


def _filter_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the filter key and its palette row."""
    return CommandSpec(
        name=FILTER_COMMAND_NAME,
        title=EXECUTION_FILTER_TITLE,
        description=EXECUTION_FILTER_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=table_available,
        keys=(FILTER_KEY,),
    )


def _details_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the details key and its palette row."""
    return CommandSpec(
        name=DETAILS_COMMAND_NAME,
        title=EXECUTION_DETAILS_TITLE,
        description=EXECUTION_DETAILS_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=table_available,
        keys=(DETAILS_KEY,),
    )


class ExecutionView(Static):
    """The one region watching an active run and offering to stop it."""

    def __init__(self) -> None:
        """Render nothing until the shell hands this view the events of a run."""
        super().__init__("", id=EXECUTION_ID, markup=False)
        self._listed: ProgressFilter = ProgressFilter.ALL
        self._details: bool = False

    @property
    def listed(self) -> ProgressFilter:
        """Filter deciding which of the folded rows this view lists."""
        return self._listed

    @property
    def details(self) -> bool:
        """Whether every row currently shows all of its details."""
        return self._details

    def show(self, state: SessionState) -> None:
        """Render the run *state* holds the events of, under the current filter."""
        self.update(execution_body(state, listed=self._listed, details=self._details))

    def on_show(self) -> None:
        """Own the cancel, filter and details actions for as long as this view is on screen."""
        host: ExecutionHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(EXECUTION_SCOPE)
        host.commands.register(
            (
                _cancel_action(self.action_cancel),
                _filter_action(self.action_filter),
                _details_action(self.action_details),
            ),
            scope=EXECUTION_SCOPE,
        )

    def on_hide(self) -> None:
        """Give all three actions back the moment this view leaves the screen."""
        host: ExecutionHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(EXECUTION_SCOPE)

    def action_cancel(self) -> None:
        """Ask the active run to stop through the one gate that confirms it."""
        host: ExecutionHost | None = self._host()
        if host is None:
            return
        host.cancel_run()

    def action_filter(self) -> None:
        """List the groups of the next filter, folding the same events again."""
        self._listed = next_filter(self._listed)
        self._paint()

    def action_details(self) -> None:
        """Open the details of every listed row, or close them again."""
        self._details = not self._details
        self._paint()

    def _paint(self) -> None:
        """Redraw from the events the session state holds right now."""
        host: ExecutionHost | None = self._host()
        if host is None:
            return
        self.show(host.session_state)

    def _host(self) -> ExecutionHost | None:
        """Return the shell this view renders for, when it is an execution host."""
        app: object = self.app
        return app if isinstance(app, ExecutionHost) else None
