"""One-row status footer projecting the session state.

The footer shows counts, the selected auto-preset, the run state and the key
hints the command registry currently offers. Paths, file names, provider answers
and secrets never reach it, and no label is written by hand: every hint comes
from the one registry.

Public API:
    footer_text: Render the status row of one session state.
    SessionFooter: Widget of the one-row status footer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.widgets import Static

from anishift.tui.commands.spec import key_display

if TYPE_CHECKING:
    from collections.abc import Iterable

    from anishift.tui.commands.spec import KeyHint
    from anishift.tui.state import SessionState

__all__ = ["SessionFooter", "footer_text"]

# ── Constants ──────────────────────────────────────────────────────────────

_SEGMENT_SEPARATOR: Final[str] = " · "
"""Separator between the segments of the one-row status footer."""


def footer_text(state: SessionState, hints: Iterable[KeyHint] = ()) -> str:
    """Return the safe status projection of *state*, followed by *hints*."""
    segments: list[str] = [
        f"workspace: {state.group_count}",
        f"selected: {len(state.selected_group_ids)}",
        f"preset: {state.default_preset_id}",
        f"run: {state.run_state.value}",
    ]
    segments.extend(f"{key_display(hint.key)} {hint.label}" for hint in hints)
    return _SEGMENT_SEPARATOR.join(segments)


class SessionFooter(Static):
    """One-row status footer of the fixed application frame."""

    def show(self, state: SessionState, hints: Iterable[KeyHint] = ()) -> None:
        """Render the current safe projection of *state* with its *hints*."""
        self.update(footer_text(state, hints))
