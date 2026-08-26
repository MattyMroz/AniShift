"""Render the report of one tools command in the work area."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from textual.widgets import Static

from anishift.tui.tools import report_body

if TYPE_CHECKING:
    from anishift.tui.tools import ToolsReport

__all__ = ["TOOLS_ID", "ToolsView", "tools_body"]

# ── Constants ──────────────────────────────────────────────────────────────

TOOLS_ID: Final[str] = "tools-view"
"""Id of the one surface the work area shows a tools report on."""


def tools_body(report: ToolsReport | None) -> str:
    """Return the rendered *report*, or nothing while the session holds none."""
    return "" if report is None else report_body(report)


class ToolsView(Static):
    """The answer of one tools command, as plain text no markup can reinterpret."""

    can_focus = False

    def __init__(self) -> None:
        """Build the empty surface; the shell fills it from one report."""
        super().__init__(id=TOOLS_ID, markup=False)

    def show(self, report: ToolsReport | None) -> None:
        """Render *report*, clearing the surface while the session holds none."""
        self.update(tools_body(report))
