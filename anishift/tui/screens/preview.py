"""Immutable execution-plan preview screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Label, Static

from anishift.application.planning import ExecutionPlan
from anishift.tui.widgets import CommandBar, StatusFooter
from anishift.tui.widgets.plan_view import PlanView

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class StartConfirmationScreen(ModalScreen[bool]):
    """Require one explicit decision before paid work or replacement."""

    def __init__(self, *, paid_tasks: int, overwrite_count: int) -> None:
        super().__init__()
        self._paid_tasks: int = paid_tasks
        self._overwrite_count: int = overwrite_count

    def compose(self) -> ComposeResult:
        """Compose a compact summary without exposing credentials or payloads."""
        with Vertical(id="start-confirmation"):
            yield Label("Confirm execution", classes="route-title")
            yield Static(
                f"Paid tasks: {self._paid_tasks} | Products replaced: {self._overwrite_count}",
                id="confirmation-summary",
            )
            with Horizontal(classes="screen-actions"):
                yield Button("Confirm", id="confirm-start", variant="warning")
                yield Button("Cancel", id="cancel-start")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Return the explicit confirmation decision to Preview."""
        self.dismiss(event.button.id == "confirm-start")


class PreviewScreen(Screen[None]):
    """Show exactly the immutable plan that execution will receive."""

    def __init__(self) -> None:
        super().__init__()
        self._pending_plan: ExecutionPlan | None = None

    def compose(self) -> ComposeResult:
        """Compose plan details and gate Start on planner executability."""
        plan = self._shell.session.preview_plan
        with Vertical(classes="route-content"):
            if plan is None:
                yield Static("No plan has been prepared", id="preview-empty")
            else:
                yield PlanView(plan)
                with Horizontal(classes="screen-actions"):
                    yield Button("Start", id="preview-start", variant="success", disabled=not plan.can_execute)
                    yield Button("Back", id="back")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Return to the chosen mode or start the exact displayed plan once."""
        if event.button.id == "back":
            await self._shell.open_route(self._shell.session.mode)
            return
        plan = self._shell.session.preview_plan
        if event.button.id == "preview-start" and plan is not None:
            paid_tasks: int = sum(task.is_paid for task in plan.tasks)
            overwrite_count: int = sum(problem.code == "product_overwrite" for problem in plan.problems)
            if paid_tasks or overwrite_count:
                if self._pending_plan is not None:
                    return
                self._pending_plan = plan
                self.app.push_screen(
                    StartConfirmationScreen(
                        paid_tasks=paid_tasks,
                        overwrite_count=overwrite_count,
                    ),
                    callback=self._start_after_confirmation,
                )
                return
            await self._shell.start_execution(plan)

    async def _start_after_confirmation(self, confirmed: bool | None) -> None:
        plan = self._pending_plan
        self._pending_plan = None
        if confirmed and plan is not None:
            await self._shell.start_execution(plan)
