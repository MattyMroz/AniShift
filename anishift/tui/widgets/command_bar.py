"""Persistent bottom command input and session status."""

from __future__ import annotations

from typing import Final

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Static

from anishift.tui.messages import CommandSubmitted
from anishift.tui.state import SessionState

# ── Constants ────────────────────────────────────────────────────────────────

COMMAND_INPUT_ID: Final[str] = "command-input"
"""Widget ID of the persistent command input."""

COMMAND_PROMPT: Final[str] = "\u276f"
"""Fixed prompt shown beside the command value."""

COMMAND_FEEDBACK_ID: Final[str] = "command-feedback"
"""Widget ID of command help and parse feedback."""

STATUS_FOOTER_ID: Final[str] = "status-footer"
"""Widget ID of the persistent session summary."""


class CommandBar(Horizontal):
    """Submit raw text without owning command behavior."""

    def compose(self) -> ComposeResult:
        """Compose a fixed prompt, input, and compact feedback line."""
        yield Static(COMMAND_PROMPT, id="command-prompt")
        yield Input(placeholder="auto, manual, settings, refresh, doctor, setup, help", id=COMMAND_INPUT_ID)
        yield Static("", id=COMMAND_FEEDBACK_ID)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Clear the value and publish one typed submission."""
        if event.input.id != COMMAND_INPUT_ID:
            return
        value: str = event.value
        event.input.clear()
        event.stop()
        self.post_message(CommandSubmitted(value))

    def set_feedback(self, text: str) -> None:
        """Render parse or navigation feedback without executing a command."""
        self.query_one(f"#{COMMAND_FEEDBACK_ID}", Static).update(text)


class StatusFooter(Static):
    """Render workspace, selection, run state, and elapsed time."""

    def __init__(self) -> None:
        super().__init__("", id=STATUS_FOOTER_ID)

    def refresh_from_state(self, state: SessionState) -> None:
        """Replace the footer from the current presentation snapshot."""
        self.update(
            f"workspace: {state.workspace_label} | mode: {state.mode} | "
            f"preset: {state.preset} | run: {state.run_state} | elapsed: {state.elapsed_seconds}s"
        )
