"""The screen showing what a planned run would do, and the gate that starts it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from textual.widgets import Static

from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.state import RunUiState, UiRoute
from anishift.tui.strings import (
    PREVIEW_BACK_DESCRIPTION,
    PREVIEW_BACK_TITLE,
    PREVIEW_START_DESCRIPTION,
    PREVIEW_START_TITLE,
    PREVIEW_TITLE,
)
from anishift.tui.widgets.plan_view import plan_body
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandRun
    from anishift.tui.state import SessionState

__all__ = [
    "BACK_COMMAND_NAME",
    "BACK_KEY",
    "PREVIEW_ID",
    "PREVIEW_SCOPE",
    "START_COMMAND_NAME",
    "START_KEY",
    "PreviewHost",
    "PreviewSession",
    "PreviewView",
    "back_route",
    "preview_body",
    "start_available",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

PREVIEW_ID: Final[str] = "preview-view"
"""Identifier of the one region rendering a planned run."""

PREVIEW_SCOPE: Final[str] = "preview"
"""Registry scope the preview owns while it is on screen, and never longer."""

START_COMMAND_NAME: Final[str] = "start"
"""Name of the contextual action running the previewed plan."""

BACK_COMMAND_NAME: Final[str] = "back"
"""Name of the contextual action leaving the preview without starting."""

START_KEY: Final[str] = "ctrl+s"
"""Key running the previewed plan while the preview is on screen."""

BACK_KEY: Final[str] = "ctrl+b"
"""Key leaving the preview for the screen that opened it."""

_PLANNING_ROUTES: Final[frozenset[UiRoute]] = frozenset({UiRoute.AUTO, UiRoute.MANUAL})
"""Routes a preview may return to, because a plan can be prepared there."""


@runtime_checkable
class PreviewHost(Protocol):
    """What the preview needs from the shell that owns it."""

    @property
    def session_state(self) -> SessionState:
        """The one session state the shell owns."""

    @property
    def commands(self) -> CommandRegistry:
        """The one command registry the shell owns."""

    @property
    def workspace_root(self) -> Path | None:
        """The directory every rendered location stays inside of."""

    def start_previewed_run(self) -> bool:
        """Run the previewed plan, deciding once whether it may start."""

    def leave_preview(self, route: UiRoute) -> None:
        """Show *route* again, keeping every draft the session holds."""


@dataclass(slots=True)
class PreviewSession:
    """What the shell remembers about the preview between two frames."""

    origin: UiRoute = UiRoute.MANUAL


def start_available(state: SessionState) -> bool:
    """Whether *state* holds a plan this session is allowed to start right now."""
    if state.plan is None or not state.plan.can_execute:
        return False
    return state.run_state is RunUiState.PLANNING and not state.modal_focus_stack


def back_route(session: PreviewSession) -> UiRoute:
    """Return the screen the preview came from, defaulting to manual preparation."""
    return session.origin if session.origin in _PLANNING_ROUTES else UiRoute.MANUAL


def preview_body(state: SessionState, *, root: Path | None) -> str:
    """Return the rendered text of the plan this session would start."""
    return f"{PREVIEW_TITLE}\n\n{plan_body(state.plan, root=root)}"


def _start_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the start key and its palette row."""
    return CommandSpec(
        name=START_COMMAND_NAME,
        title=PREVIEW_START_TITLE,
        description=PREVIEW_START_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=start_available,
        keys=(START_KEY,),
    )


def _back_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the back key and its palette row."""
    return CommandSpec(
        name=BACK_COMMAND_NAME,
        title=PREVIEW_BACK_TITLE,
        description=PREVIEW_BACK_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        keys=(BACK_KEY,),
    )


class PreviewView(Static):
    """The one region rendering a planned run and offering to start it."""

    def __init__(self) -> None:
        """Render nothing until the shell hands this view a plan."""
        super().__init__("", id=PREVIEW_ID)
        self._session: PreviewSession = PreviewSession()

    def show(self, state: SessionState, session: PreviewSession, *, root: Path | None) -> None:
        """Render the plan of *state* and remember where a back action returns."""
        self._session = session
        self.update(preview_body(state, root=root))

    def on_show(self) -> None:
        """Own the start and back actions for exactly as long as this view is on screen."""
        host: PreviewHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(PREVIEW_SCOPE)
        host.commands.register(
            (_start_action(self.action_start), _back_action(self.action_back)),
            scope=PREVIEW_SCOPE,
        )

    def on_hide(self) -> None:
        """Give both actions back the moment this view leaves the screen."""
        host: PreviewHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(PREVIEW_SCOPE)

    def action_start(self) -> None:
        """Run the previewed plan through the one gate that decides it may start."""
        host: PreviewHost | None = self._host()
        if host is None:
            return
        host.start_previewed_run()

    def action_back(self) -> None:
        """Leave the preview for the screen that prepared this plan."""
        host: PreviewHost | None = self._host()
        if host is None:
            return
        host.leave_preview(back_route(self._session))

    def _host(self) -> PreviewHost | None:
        """Return the shell this view renders for, when it is a preview host."""
        app: object = self.app
        return app if isinstance(app, PreviewHost) else None
