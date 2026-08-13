"""Main AniShift TUI routes."""

from anishift.tui.screens.auto import AutoScreen
from anishift.tui.screens.execution import ExecutionScreen
from anishift.tui.screens.manual import ManualScreen
from anishift.tui.screens.preview import PreviewScreen
from anishift.tui.screens.results import ResultsScreen
from anishift.tui.screens.settings import SettingsScreen
from anishift.tui.screens.tools import ToolsScreen
from anishift.tui.screens.workspace import WorkspaceScreen

__all__ = [
    "AutoScreen",
    "ExecutionScreen",
    "ManualScreen",
    "PreviewScreen",
    "ResultsScreen",
    "SettingsScreen",
    "ToolsScreen",
    "WorkspaceScreen",
]
