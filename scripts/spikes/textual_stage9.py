"""Disposable Textual spike for the Stage 9 interface decision."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Final

from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static

GROUP_TABLE_ID: Final[str] = "group-table"
"""Widget ID of the episode group table."""

MANUAL_FORM_ID: Final[str] = "manual-form"
"""Widget ID of the disposable manual form."""

COMMAND_INPUT_ID: Final[str] = "command-input"
"""Widget ID of the bottom command input."""

COMMAND_PROMPT: Final[str] = "\u276f"
"""Fixed prompt rendered before the bottom command input."""

RUN_BUTTON_ID: Final[str] = "run-button"
"""Widget ID of the simulated run action."""

CANCEL_BUTTON_ID: Final[str] = "cancel-button"
"""Widget ID of the simulated cancel action."""

STATUS_ID: Final[str] = "status-footer"
"""Widget ID of the persistent status line."""

MANUAL_BUTTON_ID: Final[str] = "manual-button"
"""Widget ID of the manual form action."""

MANUAL_VALUE_ID: Final[str] = "manual-value"
"""Widget ID of the editable manual value."""

SMALL_TERMINAL_ID: Final[str] = "small-terminal"
"""Widget ID of the small-terminal warning."""

CONTENT_ID: Final[str] = "content"
"""Widget ID of the main spike content."""

MINIMUM_WIDTH: Final[int] = 100
"""Minimum terminal width tested by the Stage 9 requirements."""

MINIMUM_HEIGHT: Final[int] = 30
"""Minimum terminal height tested by the Stage 9 requirements."""

GROUP_COUNT: Final[int] = 20
"""Number of fake groups rendered by the spike."""

WORKER_STEPS: Final[int] = 100
"""Number of progress updates produced by the simulated worker."""

WORKER_STEP_DELAY_SECONDS: Final[float] = 0.01
"""Delay between simulated worker progress updates."""


@dataclass(frozen=True, slots=True)
class FakeGroup:
    """One local-only group displayed by the spike."""

    name: str
    mode: str
    status: str


class ManualModal(ModalScreen[None]):
    """Minimal modal proving that per-group editing is practical."""

    def compose(self) -> ComposeResult:
        """Compose the disposable manual form."""
        with Vertical(id=MANUAL_FORM_ID):
            yield Label("Manual group intent")
            yield Input(value="embedded:eng", id=MANUAL_VALUE_ID)
            yield Button("Close", id="manual-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Close the modal when its only action is pressed."""
        if event.button.id == "manual-close":
            self.dismiss(None)


class Stage9SpikeApp(App[None]):
    """Disposable full-screen Textual proof for the Stage 9 workflow."""

    CSS = """
    #content {
        height: 1fr;
    }

    #group-table {
        height: 1fr;
    }

    #small-terminal {
        height: 1fr;
        content-align: center middle;
        display: none;
    }

    #actions {
        height: auto;
    }

    #command-bar {
        dock: bottom;
        height: 3;
        border-top: solid $primary;
    }

    #command-prompt {
        width: 3;
        content-align: center middle;
    }

    #command-input {
        width: 1fr;
    }

    #status-footer {
        dock: bottom;
        height: 1;
        padding-left: 1;
    }

    #manual-form {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.refresh_count: int = 0
        self.run_start_count: int = 0
        self.active_worker_count: int = 0
        self._is_running: bool = False
        self._cancel_event: Event = Event()

    def compose(self) -> ComposeResult:
        """Compose the table, actions, command bar, and status line."""
        with Vertical(id=CONTENT_ID):
            yield DataTable(id=GROUP_TABLE_ID, zebra_stripes=True)
            with Horizontal(id="actions"):
                yield Button("Manual", id=MANUAL_BUTTON_ID)
                yield Button("Run", id=RUN_BUTTON_ID, variant="success")
                yield Button("Cancel", id=CANCEL_BUTTON_ID, disabled=True)
        yield Static("Terminal must be at least 100x30", id=SMALL_TERMINAL_ID)
        with Horizontal(id="command-bar"):
            yield Label(COMMAND_PROMPT, id="command-prompt")
            yield Input(placeholder="Type a command", id=COMMAND_INPUT_ID)
        yield Static("idle | refreshes: 0", id=STATUS_ID)

    def on_mount(self) -> None:
        """Populate the fake workspace and apply the initial size state."""
        table: DataTable[str] = self.query_one(f"#{GROUP_TABLE_ID}", DataTable)
        table.add_columns("Group", "Mode", "Status")
        for group in _build_fake_groups():
            table.add_row(group.name, group.mode, group.status)
        self._apply_size(self.size.width, self.size.height)

    def on_resize(self, event: events.Resize) -> None:
        """Keep safe actions visible when the terminal is too small."""
        self._apply_size(event.size.width, event.size.height)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Route the three disposable spike actions."""
        match event.button.id:
            case "manual-button":
                self.push_screen(ManualModal())
            case "run-button":
                self._start_run()
            case "cancel-button":
                self._cancel_run()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle the one command needed by the technology spike."""
        if event.input.id != COMMAND_INPUT_ID:
            return
        command: str = event.value.strip().casefold()
        event.input.clear()
        if command != "refresh":
            return
        self.refresh_count += 1
        self._set_status(f"idle | refreshes: {self.refresh_count}")

    def _start_run(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self.run_start_count += 1
        self.active_worker_count = 1
        self._cancel_event.clear()
        self.query_one(f"#{RUN_BUTTON_ID}", Button).disabled = True
        self.query_one(f"#{CANCEL_BUTTON_ID}", Button).disabled = False
        self._set_status("running | 0%")
        self._simulate_run()

    def _cancel_run(self) -> None:
        if not self._is_running:
            return
        self._cancel_event.set()
        self._set_status("cancelling")

    @work(thread=True, exclusive=True, group="stage9-spike")
    def _simulate_run(self) -> None:
        for progress in range(1, WORKER_STEPS + 1):
            if self._cancel_event.wait(WORKER_STEP_DELAY_SECONDS):
                self.call_from_thread(self._finish_run, "cancelled")
                return
            self.call_from_thread(self._set_status, f"running | {progress}%")
        self.call_from_thread(self._finish_run, "completed")

    def _finish_run(self, status: str) -> None:
        self._is_running = False
        self.active_worker_count = 0
        self.query_one(f"#{RUN_BUTTON_ID}", Button).disabled = False
        self.query_one(f"#{CANCEL_BUTTON_ID}", Button).disabled = True
        self._set_status(status)

    def _set_status(self, text: str) -> None:
        self.query_one(f"#{STATUS_ID}", Static).update(text)

    def _apply_size(self, width: int, height: int) -> None:
        is_small: bool = width < MINIMUM_WIDTH or height < MINIMUM_HEIGHT
        self.query_one(f"#{CONTENT_ID}", Vertical).display = not is_small
        self.query_one(f"#{SMALL_TERMINAL_ID}", Static).display = is_small


def _build_fake_groups() -> tuple[FakeGroup, ...]:
    return tuple(
        FakeGroup(name=f"episode-{index:02d}.mkv", mode="auto", status="ready") for index in range(1, GROUP_COUNT + 1)
    )


if __name__ == "__main__":
    Stage9SpikeApp().run()
