"""Render inspected workspace source groups in the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

from anishift.tui.strings import WORKSPACE_EMPTY

if TYPE_CHECKING:
    from anishift.application import InspectedSourceGroup, InspectedWorkspace

__all__ = ["WorkspaceView", "workspace_body"]


def workspace_body(workspace: InspectedWorkspace | None) -> str:
    """Return source stems or the empty-workspace message."""
    groups: tuple[InspectedSourceGroup, ...] = () if workspace is None else workspace.groups
    if not groups:
        return WORKSPACE_EMPTY
    return "\n".join(group.source.stem for group in groups)


class WorkspaceView(Static):
    """Display source stems from an inspected workspace."""

    def show(self, workspace: InspectedWorkspace | None) -> None:
        """Update the view from an inspected workspace."""
        self.update(workspace_body(workspace))
