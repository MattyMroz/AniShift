"""Automatic workflow route placeholder."""

from __future__ import annotations

from anishift.tui.screens.base import PlaceholderScreen


class AutoScreen(PlaceholderScreen):
    """Route reserved for automatic product selection."""

    route_id = "auto"
    route_title = "Automatic workflow"
