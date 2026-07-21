"""Define portability manifest for ``utils/`` — copy this package to any project.

Each sub-package below is **self-contained** and can be copied independently.
Install the required dependencies listed per module and adjust ``<pkg>``
placeholders in docstrings/examples to your actual package name.

Required (all modules):
    loguru >= 0.7
    rich >= 13.0

Required (logger only):
    pydantic >= 2.0

Optional (device only):
    torch >= 2.0              # falls back to CPU if missing

Dev / test only:
    pytest >= 8.0

Python: >= 3.10

Portable modules:
    logger/          — loguru wrapper: modes, decorators, Rich handlers, CLI viewer
    timer/           — nanosecond Timer, ExecutionTimer, @timed decorator
    rich_console/    — themed Rich console, auto-highlight, progress manager
    device.py        — CUDA > MPS > CPU device selection
    safe_path.py     — path traversal protection
    safe_fs.py       — retry-on-lock filesystem ops (safe_rmtree, safe_move)

Smoke test (after copying to a clean project):
    python -c "from anishift.utils.logger import setup_mode, LoggerMode; setup_mode(LoggerMode.SILENT); print('OK')"
    python -c "from anishift.utils.timer import Timer; t = Timer('x', auto_start=True); t.stop(); print('OK')"
    python -c "from anishift.utils.rich_console import console; console.print('[bold]OK[/bold]')"
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "MIN_PYTHON",
    "MODULE_DEPS",
    "OPTIONAL_DEPS",
    "PORTABLE_MODULES",
    "REQUIRED_DEPS",
]

REQUIRED_DEPS: Final[dict[str, str]] = {
    "loguru": ">=0.7",
    "rich": ">=13.0",
}
"""Dependencies required by all portable modules."""

MODULE_DEPS: Final[dict[str, dict[str, str]]] = {
    "logger": {"pydantic": ">=2.0"},
}
"""Extra dependencies required by specific modules."""

OPTIONAL_DEPS: Final[dict[str, dict[str, str]]] = {
    "device": {"torch": ">=2.0"},
}
"""Optional dependencies that enable additional functionality."""

PORTABLE_MODULES: Final[list[str]] = [
    "logger",
    "timer",
    "rich_console",
    "device",
    "safe_path",
    "safe_fs",
]
"""Names of all portable modules/packages in utils/."""

MIN_PYTHON: Final[str] = "3.10"
"""Minimum Python version required by all portable modules."""
