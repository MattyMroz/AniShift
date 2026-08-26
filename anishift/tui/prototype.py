"""Temporary visual prototype of the shell, launched on the production application facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual import on

from anishift.application import GroupResult, GroupStatus, RunResult
from anishift.tui import lifecycle
from anishift.tui.app import AniShiftApp
from anishift.tui.messages import AutoRequested, RunFinished
from anishift.tui.screens.workspace import GroupRow, GroupState
from anishift.tui.strings import (
    CONTEXT_MODE_DEMO,
    CONTEXT_MODEL_UNSET,
    CONTEXT_PROVIDER,
    DEMO_GROUP_FIVE,
    DEMO_GROUP_FOUR,
    DEMO_GROUP_ONE,
    DEMO_GROUP_THREE,
    DEMO_GROUP_TWO,
    DEMO_TITLE,
    GROUP_COLUMN_GAP,
    RUN_DONE,
    RUN_PLANNING,
    RUN_STEP_SPEECH,
    RUN_WORKING,
)
from anishift.tui.widgets.composer import Composer

if TYPE_CHECKING:
    from anishift.application import AppService

__all__ = [
    "DEMO_RUN_ID",
    "DEMO_STEP_SECONDS",
    "PrototypeApp",
    "demo_rows",
    "production_service",
    "working_status",
]

# ── Constants ──────────────────────────────────────────────────────────────

DEMO_STEP_SECONDS: Final[float] = 0.7
"""Seconds one stage of the simulated sequence stays on screen."""

DEMO_RUN_ID: Final[str] = "demo-run"
"""Identity of the one run the simulated sequence starts."""


def demo_rows() -> tuple[GroupRow, ...]:
    """Return the source groups the simulated session lists."""
    return (
        GroupRow(name=DEMO_GROUP_ONE, state=GroupState.READY, selected=True),
        GroupRow(name=DEMO_GROUP_TWO, state=GroupState.NO_SIDECAR, selected=True),
        GroupRow(name=DEMO_GROUP_THREE, state=GroupState.CONFLICT, selected=False),
        GroupRow(name=DEMO_GROUP_FOUR, state=GroupState.READY, selected=False),
        GroupRow(name=DEMO_GROUP_FIVE, state=GroupState.READY, selected=False),
    )


def production_service() -> AppService:
    """Compose the one application facade this launcher runs the shell on."""
    from anishift.bootstrap import bootstrap, create_app_service  # noqa: PLC0415 - keeps the backend lazy

    return create_app_service(bootstrap())


def working_status() -> str:
    """Return the running state together with the operation it is on."""
    return f"{RUN_WORKING}{GROUP_COLUMN_GAP}{RUN_STEP_SPEECH}"


class PrototypeApp(AniShiftApp):
    """The shell with one simulated sequence in place of every workflow needing a backend."""

    def __init__(self, *, service: AppService | None = None, step: float = DEMO_STEP_SECONDS) -> None:
        """Compose the production facade unless one is given, then hold the simulated pace."""
        super().__init__(service=service if service is not None else production_service())
        self._step: float = step
        self._rows: tuple[GroupRow, ...] = demo_rows()

    def on_mount(self) -> None:
        """Draw the frame, then say in the title and the context line that nothing is real."""
        super().on_mount()
        self.title = DEMO_TITLE
        self.query_one(Composer).show_context(
            mode=CONTEXT_MODE_DEMO,
            provider=CONTEXT_PROVIDER,
            model=CONTEXT_MODEL_UNSET,
        )

    @on(AutoRequested)
    def _on_auto_requested(self, message: AutoRequested) -> None:
        """Enter the simulated plan of the one reserved generation."""
        self.show_groups(self._rows, status=RUN_PLANNING)
        self.set_timer(self._step, lambda: self._begin(message.generation))

    def _begin(self, generation: int) -> None:
        """Enter the run the simulated plan produced."""
        if not lifecycle.begin_run(self.session_state, DEMO_RUN_ID):
            return
        self.show_groups(self._rows, status=working_status())
        self.set_timer(self._step, lambda: self._finish(generation))

    def _finish(self, generation: int) -> None:
        """End the simulated run with the result of every selected group."""
        self.show_groups(self._rows, status=RUN_DONE)
        self.post_message(RunFinished(result=self._result(), run_id=DEMO_RUN_ID, generation=generation))

    def _result(self) -> RunResult:
        """Build the terminal result of every group the sequence acted on."""
        return RunResult(
            run_id=DEMO_RUN_ID,
            groups=tuple(
                GroupResult(group_id=row.name, status=GroupStatus.SUCCEEDED) for row in self._rows if row.selected
            ),
        )
