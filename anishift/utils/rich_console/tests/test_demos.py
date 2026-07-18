"""Smoke tests for rich_console.examples demo scripts.

Verify each demo module imports successfully and its main function
is callable. Full visual demos require a terminal and are validated
by manual execution.
"""

from __future__ import annotations

from ..examples.demo_colors import demo_colors
from ..examples.demo_progress import run_all_demos as progress_demos
from ..examples.demo_theme import run_all_demos as theme_demos
from ..examples.demo_utilities import run_all_demos as utility_demos
from ..examples.run_demos import main


class TestDemoImports:
    """Verify demo modules import and expose expected callables."""

    def test_demo_colors_callable(self):
        assert callable(demo_colors)

    def test_demo_theme_callable(self):
        assert callable(theme_demos)

    def test_demo_utilities_callable(self):
        assert callable(utility_demos)

    def test_demo_progress_callable(self):
        assert callable(progress_demos)

    def test_run_demos_main_callable(self):
        assert callable(main)


class TestModulePublicAPI:
    """Verify rich_console public API is importable."""

    def test_console_import(self):
        from .. import console

        assert console is not None

    def test_progress_bar_manager_import(self):
        from .. import ProgressBarManager

        assert ProgressBarManager is not None

    def test_theme_import(self):
        from .. import RICH_THEME, Colors

        assert RICH_THEME is not None
        assert Colors is not None

    def test_utilities_import(self):
        from .. import (
            format_bytes,
            format_duration,
            format_percentage,
            get_progress_color,
            get_status_icon,
        )

        assert all(
            callable(f) for f in [format_bytes, format_duration, format_percentage, get_progress_color, get_status_icon]
        )

    def test_version(self):
        from .. import __version__

        assert __version__ == "1.0.0"
