"""Manual workflow route placeholder."""

from __future__ import annotations

from anishift.tui.screens.base import PlaceholderScreen


class ManualScreen(PlaceholderScreen):
    """Route reserved for per-group source and product choices."""

    route_id = "manual"
    route_title = "Manual workflow"
