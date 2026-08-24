"""One-row status footer projecting the session state.

The footer shows counts and the run state only. Paths, file names, provider
answers and secrets never reach it.

Public API:
    footer_text: Render the status row of one session state.
    SessionFooter: Widget of the one-row status footer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from anishift.tui.state import SessionState

__all__ = ["SessionFooter", "footer_text"]


def footer_text(state: SessionState) -> str:
    """Return the safe status projection of *state*."""
    return f"workspace: {state.group_count} · selected: {len(state.selected_group_ids)} · run: {state.run_state.value}"


class SessionFooter(Static):
    """One-row status footer of the fixed application frame."""

    def show(self, state: SessionState) -> None:
        """Render the current safe projection of *state*."""
        self.update(footer_text(state))
