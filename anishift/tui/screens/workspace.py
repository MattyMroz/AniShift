"""The workspace route: the source groups one session can act on.

Public API:
    EMPTY_WORKSPACE_TEXT: Base state shown when no source file was found.
    workspace_body: Render the body of the workspace route.
    WorkspaceView: Widget of the workspace route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.widgets import Static

if TYPE_CHECKING:
    from anishift.application import InspectedSourceGroup, InspectedWorkspace

__all__ = ["EMPTY_WORKSPACE_TEXT", "WorkspaceView", "workspace_body"]

# ── Constants ──────────────────────────────────────────────────────────────

EMPTY_WORKSPACE_TEXT: Final[str] = "Nie znaleziono obsługiwanych plików w workspace."
"""Base state shown while the workspace holds no supported source file."""


def workspace_body(workspace: InspectedWorkspace | None) -> str:
    """Return one row per source group, or the empty base state."""
    groups: tuple[InspectedSourceGroup, ...] = () if workspace is None else workspace.groups
    if not groups:
        return EMPTY_WORKSPACE_TEXT
    return "\n".join(group.source.stem for group in groups)


class WorkspaceView(Static):
    """One row per discovered source group, or the empty base state."""

    def show(self, workspace: InspectedWorkspace | None) -> None:
        """Render the source groups of *workspace*."""
        self.update(workspace_body(workspace))
