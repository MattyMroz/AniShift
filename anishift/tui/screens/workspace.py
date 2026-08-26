"""Render inspected workspace source groups in the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.tui.widgets.group_table import (
    GroupRow,
    GroupState,
    GroupTable,
    group_line,
    group_rows,
    groups_body,
    state_text,
    table_body,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from anishift.application import InspectedWorkspace

__all__ = [
    "WORKSPACE_ID",
    "GroupRow",
    "GroupState",
    "WorkspaceView",
    "group_line",
    "groups_body",
    "state_text",
    "workspace_body",
]

# ── Constants ──────────────────────────────────────────────────────────────

WORKSPACE_ID: Final[str] = "workspace-view"
"""Id of the one surface the work area lists source groups on."""


def workspace_body(workspace: InspectedWorkspace | None) -> str:
    """Return the table of every inspected group, or the empty-workspace message."""
    return table_body(group_rows(workspace))


class WorkspaceView(GroupTable):
    """Display source groups the session may act on, refresh them and select them."""

    def __init__(self) -> None:
        """Build the one surface the work area lists source groups on."""
        super().__init__(widget_id=WORKSPACE_ID)

    def show_groups(self, rows: Sequence[GroupRow], *, status: str = "") -> None:
        """Update the view from projected group rows and the current run status."""
        self.show_rows(rows, status=status)
