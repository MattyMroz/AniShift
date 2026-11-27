"""Portability manifest of ``utils/``: modules, their dependencies and the minimum Python; notes in AGENTS.md."""

from __future__ import annotations

from typing import Final

__all__ = [
    "MIN_PYTHON",
    "MODULE_DEPS",
    "OPTIONAL_DEPS",
    "PORTABLE_MODULES",
    "REQUIRED_DEPS",
]

# ── Constants ────────────────────────────────────────────────────────────────

REQUIRED_DEPS: Final[dict[str, str]] = {
    "loguru": ">=0.7",
    "rich": ">=13.0",
}
"""Dependencies required by all portable modules."""

MODULE_DEPS: Final[dict[str, dict[str, str]]] = {
    "logger": {"pydantic": ">=2.0"},
    "_retry": {"tenacity": ">=9.0"},
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
    "_retry",
    "mp3_frames",
    "pauses",
]
"""Names of all portable modules/packages in utils/."""

MIN_PYTHON: Final[str] = "3.14"
"""Minimum Python version required by all portable modules."""
