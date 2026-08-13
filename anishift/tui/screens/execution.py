"""Execution route placeholder."""

from __future__ import annotations

from anishift.tui.screens.base import PlaceholderScreen


class ExecutionScreen(PlaceholderScreen):
    """Route reserved for live task progress and cancellation."""

    route_id = "execution"
    route_title = "Execution"
