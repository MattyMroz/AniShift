"""Plan-preview route placeholder."""

from __future__ import annotations

from anishift.tui.screens.base import PlaceholderScreen


class PreviewScreen(PlaceholderScreen):
    """Route reserved for executable-plan review."""

    route_id = "preview"
    route_title = "Plan preview"
