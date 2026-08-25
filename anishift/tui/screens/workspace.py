"""Render inspected workspace source groups in the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from textual.widgets import Static

from anishift.tui.strings import (
    GLYPH_GAP,
    GROUP_COLUMN_GAP,
    GROUP_CONFLICT_GLYPH,
    GROUP_MISSING_GLYPH,
    GROUP_READY_GLYPH,
    GROUP_SELECTED_GLYPH,
    GROUP_STATE_CONFLICT,
    GROUP_STATE_NO_SIDECAR,
    GROUP_STATE_READY,
    GROUP_UNSELECTED_GLYPH,
    SELECTION_SUMMARY,
    STATUS_GLYPH,
    WORKSPACE_EMPTY,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from anishift.application import InspectedSourceGroup, InspectedWorkspace

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


class GroupState(StrEnum):
    """What an inspection found about one source group."""

    READY = "ready"
    CONFLICT = "conflict"
    NO_SIDECAR = "no_sidecar"


_STATE_GLYPHS: Final[dict[GroupState, str]] = {
    GroupState.READY: GROUP_READY_GLYPH,
    GroupState.CONFLICT: GROUP_CONFLICT_GLYPH,
    GroupState.NO_SIDECAR: GROUP_MISSING_GLYPH,
}
"""Glyph every group state is marked with, so colour is never the only signal."""

_STATE_WORDS: Final[dict[GroupState, str]] = {
    GroupState.READY: GROUP_STATE_READY,
    GroupState.CONFLICT: GROUP_STATE_CONFLICT,
    GroupState.NO_SIDECAR: GROUP_STATE_NO_SIDECAR,
}
"""Word every group state is named by."""


@dataclass(frozen=True, slots=True)
class GroupRow:
    """One source group as the work area lists it."""

    name: str
    state: GroupState
    selected: bool


def state_text(state: GroupState) -> str:
    """Return the glyph and the word one group state is shown as."""
    return f"{_STATE_GLYPHS[state]}{GLYPH_GAP}{_STATE_WORDS[state]}"


def group_line(row: GroupRow, *, name_width: int) -> str:
    """Return one group row: its selection marker, its name and its state."""
    marker: str = GROUP_SELECTED_GLYPH if row.selected else GROUP_UNSELECTED_GLYPH
    return f"{marker}{GLYPH_GAP}{row.name.ljust(name_width)}{GROUP_COLUMN_GAP}{state_text(row.state)}"


def groups_body(rows: Sequence[GroupRow], *, status: str = "") -> str:
    """Return the selection summary, the run status and one line per group."""
    if not rows:
        return WORKSPACE_EMPTY
    name_width: int = max(len(row.name) for row in rows)
    summary: str = SELECTION_SUMMARY.format(
        selected=sum(1 for row in rows if row.selected),
        total=len(rows),
    )
    header: list[str] = [summary]
    if status:
        header.append(f"{STATUS_GLYPH}{GLYPH_GAP}{status}")
    lines: list[str] = [group_line(row, name_width=name_width) for row in rows]
    return "\n".join([*header, "", *lines])


def workspace_body(workspace: InspectedWorkspace | None) -> str:
    """Return source stems or the empty-workspace message."""
    groups: tuple[InspectedSourceGroup, ...] = () if workspace is None else workspace.groups
    if not groups:
        return WORKSPACE_EMPTY
    return "\n".join(group.source.stem for group in groups)


class WorkspaceView(Static):
    """Display source groups the session may act on."""

    def __init__(self) -> None:
        """Build the one surface the work area lists source groups on."""
        super().__init__(id=WORKSPACE_ID)

    def show(self, workspace: InspectedWorkspace | None) -> None:
        """Update the view from an inspected workspace."""
        self.update(workspace_body(workspace))

    def show_groups(self, rows: Sequence[GroupRow], *, status: str = "") -> None:
        """Update the view from projected group rows and the current run status."""
        self.update(groups_body(rows, status=status))
